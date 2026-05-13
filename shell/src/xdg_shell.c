/*
 * CIOS Shell — XDG Shell support for native Wayland clients
 *
 * Implements the xdg-shell protocol (xdg_wm_base) which allows
 * Wayland-native applications (GTK4, Qt6, etc.) to create windows
 * without needing XWayland.
 *
 * This is essential for the CIOS runtime (GTK4-based) to render
 * its UI directly on the compositor.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_xdg_shell.h>

#include "log.h"
#include "server.h"

/* ═══════════════════════════════════════════════════════════════
 *  XDG Surface event handlers
 * ═══════════════════════════════════════════════════════════════ */

static void handle_xdg_surface_map(struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, map);
    struct CiosServer *server = surface->server;

    LOG_INFO("xdg surface mapped: s_%u (title: %s)", surface->id,
        surface->xdg_toplevel->title ? surface->xdg_toplevel->title : "(none)");

    /* Place in NORMAL layer */
    surface->layer = server->layer_normal;

    /* Configure size to fill usable area (now safe — surface is initialized) */
    if (server->primary_output) {
        int width = server->primary_output->usable_width;
        int height = server->primary_output->usable_height;
        wlr_xdg_toplevel_set_size(surface->xdg_toplevel, width, height);
        wlr_scene_node_set_position(&surface->scene_tree->node,
            server->primary_output->usable_x,
            server->primary_output->usable_y);
    }

    /* If splash is active, hide until ready */
    if (server->splash_active) {
        wlr_scene_node_set_enabled(&surface->scene_tree->node, false);
        surface->visible = false;
    } else {
        surface->visible = true;
    }

    /* Focus this surface */
    server_focus_xdg_surface(server, surface);

    /* Send surface_mapped event via IPC */
    if (server->ipc) {
        char payload[512];
        snprintf(payload, sizeof(payload),
            "{\"surface_id\":\"s_%u\",\"title\":\"%s\",\"pid\":%d}",
            surface->id,
            surface->xdg_toplevel->title ? surface->xdg_toplevel->title : "",
            surface->pid);
        ipc_send_event(server->ipc, "surface_mapped", payload);
    }
}

static void handle_xdg_surface_unmap(struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, map);

    LOG_INFO("xdg surface unmapped: s_%u", surface->id);

    surface->visible = false;

    /* If this was focused, clear focus */
    if (surface->server->focused == surface) {
        surface->server->focused = NULL;
    }

    /* Send event via IPC */
    if (surface->server->ipc) {
        char payload[128];
        snprintf(payload, sizeof(payload),
            "{\"surface_id\":\"s_%u\"}", surface->id);
        ipc_send_event(surface->server->ipc, "surface_unmapped", payload);
    }
}

static void handle_xdg_surface_destroy(struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, destroy);

    LOG_INFO("xdg surface destroyed: s_%u", surface->id);

    wl_list_remove(&surface->map.link);
    wl_list_remove(&surface->unmap.link);
    wl_list_remove(&surface->destroy.link);
    wl_list_remove(&surface->link);

    free(surface);
}

/* ═══════════════════════════════════════════════════════════════
 *  New XDG toplevel handler
 * ═══════════════════════════════════════════════════════════════ */

static void handle_new_xdg_toplevel(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, new_xdg_toplevel);
    struct wlr_xdg_toplevel *toplevel = data;

    /* Allocate surface */
    struct CiosSurface *surface = calloc(1, sizeof(struct CiosSurface));
    if (!surface) {
        LOG_ERROR("failed to allocate CiosSurface for xdg toplevel");
        return;
    }

    surface->server = server;
    surface->id = server->next_surface_id++;
    surface->xdg_toplevel = toplevel;
    surface->xsurface = NULL;  /* Not an XWayland surface */

    /* Get PID of the client */
    struct wl_client *client = wl_resource_get_client(toplevel->base->resource);
    pid_t pid = 0;
    wl_client_get_credentials(client, &pid, NULL, NULL);
    surface->pid = pid;

    /* Create scene tree for this surface */
    surface->scene_tree = wlr_scene_xdg_surface_create(
        server->layer_normal, toplevel->base);
    if (!surface->scene_tree) {
        LOG_ERROR("failed to create scene tree for xdg surface s_%u", surface->id);
        free(surface);
        return;
    }

    /* Store surface pointer in scene node data for hit testing */
    surface->scene_tree->node.data = surface;

    /* Add to surfaces list */
    wl_list_insert(&server->surfaces, &surface->link);

    /* Listen for surface events */
    surface->map.notify = handle_xdg_surface_map;
    wl_signal_add(&toplevel->base->surface->events.map, &surface->map);

    surface->unmap.notify = handle_xdg_surface_unmap;
    wl_signal_add(&toplevel->base->surface->events.unmap, &surface->unmap);

    surface->destroy.notify = handle_xdg_surface_destroy;
    wl_signal_add(&toplevel->base->events.destroy, &surface->destroy);

    /* Do NOT send configure here — xdg_surface is not initialized yet.
     * GTK4 with fullscreen() will commit its first frame at its own size.
     * We resize to usable_area in the map handler (when surface is ready). */

    LOG_INFO("new xdg toplevel: s_%u (pid: %d)", surface->id, pid);
}

/* ═══════════════════════════════════════════════════════════════
 *  Focus helper for XDG surfaces
 * ═══════════════════════════════════════════════════════════════ */

void server_focus_xdg_surface(struct CiosServer *server, struct CiosSurface *surface) {
    if (!surface || !surface->xdg_toplevel) {
        return;
    }

    struct wlr_surface *wlr_surface = surface->xdg_toplevel->base->surface;

    /* Raise to top of layer */
    wlr_scene_node_raise_to_top(&surface->scene_tree->node);

    /* Activate the toplevel */
    wlr_xdg_toplevel_set_activated(surface->xdg_toplevel, true);

    /* Deactivate previous */
    if (server->focused && server->focused != surface &&
        server->focused->xdg_toplevel) {
        wlr_xdg_toplevel_set_activated(server->focused->xdg_toplevel, false);
    }

    server->focused = surface;

    /* Set keyboard focus */
    struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
    if (keyboard) {
        wlr_seat_keyboard_notify_enter(server->seat, wlr_surface,
            keyboard->keycodes, keyboard->num_keycodes, &keyboard->modifiers);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  Initialize XDG Shell
 * ═══════════════════════════════════════════════════════════════ */

void xdg_shell_init(struct CiosServer *server) {
    server->xdg_shell = wlr_xdg_shell_create(server->display, 3);
    if (!server->xdg_shell) {
        LOG_ERROR("failed to create xdg_shell");
        return;
    }

    server->new_xdg_toplevel.notify = handle_new_xdg_toplevel;
    wl_signal_add(&server->xdg_shell->events.new_toplevel, &server->new_xdg_toplevel);

    LOG_INFO("xdg-shell initialized (version 3)");
}
