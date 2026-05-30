/*
 * CIOS Shell — XWayland surface lifecycle management
 *
 * Initializes wlr_xwayland, handles surface map/unmap/destroy events,
 * assigns unique surface IDs (s_N format), manages scene tree nodes,
 * and acknowledges configure requests.
 *
 * Requirements: 2.1 (surface ID assignment), 11.1 (XWayland + DISPLAY),
 *               11.2 (X11 windows as surfaces), 11.3 (configure acknowledge)
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/xwayland.h>

#include "log.h"
#include "server.h"

/*
 * Timer callback: fires 500ms after surface_mapped if the runtime hasn't
 * sent a configure_surface for this surface. Places the surface in the
 * primary output's usable_area on BOTTOM layer as default. (Req 2.4)
 */
static int handle_map_timeout(void *data) {
    struct CiosSurface *surface = data;
    struct CiosServer *server = surface->server;

    LOG_WARN("surface s_%u: runtime did not respond within 500ms, applying default placement",
        surface->id);

    /* Clear the timer reference (one-shot) */
    surface->map_timer = NULL;

    /* Place surface in usable_area on BOTTOM layer */
    struct CiosOutput *primary = output_get_primary(server);
    if (primary && surface->scene_tree) {
        /* Offset Y by titlebar height if decorated */
        int y_offset = surface->decorated ? CIOS_TITLEBAR_HEIGHT : 0;
        wlr_scene_node_set_position(&surface->scene_tree->node,
            primary->usable_x, primary->usable_y + y_offset);

        /* Configure the XWayland surface geometry to fill usable area */
        wlr_xwayland_surface_configure(surface->xsurface,
            primary->usable_x, primary->usable_y + y_offset,
            primary->usable_width, primary->usable_height - y_offset);

        /* Update decoration width */
        decorations_update_size(surface, primary->usable_width);

        /* Ensure it's on BOTTOM layer (already default, but be explicit) */
        surface->layer = server->layer_bottom;
        surface->visible = true;
        wlr_scene_node_set_enabled(&surface->scene_tree->node, true);
    }

    return 0;
}

/*
 * Handle XWayland surface map — surface is ready to be displayed.
 * Create scene tree node in BOTTOM layer, add to server surfaces list,
 * send surface_mapped event via IPC, and start 500ms timeout. (Req 2.2, 2.4)
 */
static void handle_xwayland_surface_map(struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, map);
    struct CiosServer *server = surface->server;
    struct wlr_xwayland_surface *xsurface = surface->xsurface;

    /* Create scene subsurface tree in BOTTOM layer (default for new surfaces) */
    surface->scene_tree = wlr_scene_subsurface_tree_create(
        server->layer_bottom, xsurface->surface);
    if (!surface->scene_tree) {
        LOG_ERROR("failed to create scene tree for surface s_%u", surface->id);
        return;
    }

    surface->layer = server->layer_bottom;
    surface->visible = true;

    /* Position at the surface's requested coordinates */
    wlr_scene_node_set_position(&surface->scene_tree->node,
        xsurface->x, xsurface->y);

    /*
     * If the splash screen is still active (boot in progress),
     * hide the surface until the runtime sends "ready" and the
     * splash fade completes. (Req 7.3)
     */
    if (server->splash_active) {
        wlr_scene_node_set_enabled(&surface->scene_tree->node, false);
        surface->visible = false;
    }

    /* Add to server's surfaces list */
    wl_list_insert(&server->surfaces, &surface->link);

    /* Create server-side decorations (titlebar + buttons) */
    decorations_create(surface);

    LOG_INFO("surface mapped: s_%u (class=%s, title=%s, pid=%d)",
        surface->id,
        xsurface->class ? xsurface->class : "(null)",
        xsurface->title ? xsurface->title : "(null)",
        xsurface->pid);

    /* Send surface_mapped event to runtime via IPC (Req 2.2) */
    if (server->ipc) {
        char payload[512];
        snprintf(payload, sizeof(payload),
            "\"surface_id\":\"s_%u\",\"wm_class\":\"%s\",\"title\":\"%s\",\"pid\":%d",
            surface->id,
            xsurface->class ? xsurface->class : "",
            xsurface->title ? xsurface->title : "",
            xsurface->pid);
        ipc_send_event(server->ipc, "surface_mapped", payload);
    }

    /* Start 500ms timeout: if runtime doesn't configure, apply default (Req 2.4) */
    struct wl_event_loop *loop = wl_display_get_event_loop(server->display);
    surface->map_timer = wl_event_loop_add_timer(loop, handle_map_timeout, surface);
    if (surface->map_timer) {
        wl_event_source_timer_update(surface->map_timer, 500);
    } else {
        LOG_WARN("surface s_%u: failed to create map timeout timer", surface->id);
    }
}

/*
 * Handle XWayland surface unmap — surface is no longer visible.
 * Cancel map timer, send surface_unmapped event via IPC,
 * remove scene tree node, remove from surfaces list. (Req 2.3)
 */
static void handle_xwayland_surface_unmap(struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, unmap);
    struct CiosServer *server = surface->server;

    LOG_INFO("surface unmapped: s_%u", surface->id);

    /* Cancel the 500ms map timeout if still pending */
    if (surface->map_timer) {
        wl_event_source_remove(surface->map_timer);
        surface->map_timer = NULL;
    }

    /* Send surface_unmapped event to runtime via IPC (Req 2.3) */
    if (server->ipc) {
        char payload[128];
        snprintf(payload, sizeof(payload), "\"surface_id\":\"s_%u\"", surface->id);
        ipc_send_event(server->ipc, "surface_unmapped", payload);
    }

    /* If this surface was focused, clear focus */
    if (server->focused == surface) {
        server->focused = NULL;
    }

    /* Destroy decorations */
    decorations_destroy(surface);

    /* Hide scene tree node (don't destroy — destroy happens in surface_destroy) */
    if (surface->scene_tree) {
        wlr_scene_node_set_enabled(&surface->scene_tree->node, false);
    }

    /* Remove from surfaces list */
    wl_list_remove(&surface->link);
    wl_list_init(&surface->link);
    surface->visible = false;
}

/*
 * Handle XWayland surface destroy — cleanup listeners, timer, and free CiosSurface.
 */
static void handle_xwayland_surface_destroy(struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, destroy);
    struct CiosServer *server = surface->server;

    LOG_INFO("surface destroyed: s_%u", surface->id);

    /* Clear focus if this surface was focused (prevents use-after-free) */
    if (server->focused == surface) {
        server->focused = NULL;
    }

    /* Cancel the 500ms map timeout if still pending */
    if (surface->map_timer) {
        wl_event_source_remove(surface->map_timer);
        surface->map_timer = NULL;
    }

    /* Destroy decorations if still present */
    if (surface->decorated) {
        decorations_destroy(surface);
    }

    /* Remove scene tree node if still present (surface may not have been unmapped) */
    if (surface->scene_tree) {
        wlr_scene_node_destroy(&surface->scene_tree->node);
        surface->scene_tree = NULL;
    }

    /* Remove from surfaces list */
    wl_list_remove(&surface->link);
    /* Initialize to empty so double-remove is safe */
    wl_list_init(&surface->link);

    /* Remove all listeners LAST (after all other cleanup) */
    wl_list_remove(&surface->map.link);
    wl_list_remove(&surface->unmap.link);
    wl_list_remove(&surface->destroy.link);
    wl_list_remove(&surface->request_configure.link);

    /* Zero out the struct before freeing to catch use-after-free earlier */
    surface->server = NULL;
    surface->xsurface = NULL;
    surface->scene_tree = NULL;

    free(surface);
}

/*
 * Handle XWayland surface request_configure — acknowledge with current geometry.
 * We accept whatever the client requests (the runtime will reposition via IPC).
 */
static void handle_xwayland_surface_request_configure(
        struct wl_listener *listener, void *data) {
    struct CiosSurface *surface = wl_container_of(listener, surface, request_configure);
    struct wlr_xwayland_surface_configure_event *event = data;

    wlr_xwayland_surface_configure(surface->xsurface,
        event->x, event->y, event->width, event->height);
}

/*
 * Handle new XWayland surface event — allocate CiosSurface and set up listeners.
 * The surface is not yet mapped; we wait for the map event to add it to the scene.
 */
static void handle_new_xwayland_surface(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, new_xwayland_surface);
    struct wlr_xwayland_surface *xsurface = data;

    /* Allocate CiosSurface */
    struct CiosSurface *surface = calloc(1, sizeof(*surface));
    if (!surface) {
        LOG_ERROR("failed to allocate CiosSurface");
        return;
    }

    surface->server = server;
    surface->xsurface = xsurface;
    surface->scene_tree = NULL;
    surface->layer = NULL;
    surface->visible = false;
    surface->pid = xsurface->pid;
    surface->map_timer = NULL;

    /* Assign unique surface ID (s_N format) */
    surface->id = server->next_surface_id++;

    LOG_INFO("new xwayland surface: s_%u (class=%s, title=%s, pid=%d)",
        surface->id,
        xsurface->class ? xsurface->class : "(null)",
        xsurface->title ? xsurface->title : "(null)",
        xsurface->pid);

    /* Set up listeners */
    surface->map.notify = handle_xwayland_surface_map;
    wl_signal_add(&xsurface->surface->events.map, &surface->map);

    surface->unmap.notify = handle_xwayland_surface_unmap;
    wl_signal_add(&xsurface->surface->events.unmap, &surface->unmap);

    surface->destroy.notify = handle_xwayland_surface_destroy;
    wl_signal_add(&xsurface->events.destroy, &surface->destroy);

    surface->request_configure.notify = handle_xwayland_surface_request_configure;
    wl_signal_add(&xsurface->events.request_configure, &surface->request_configure);
}

/*
 * Initialize XWayland — create wlr_xwayland instance, set DISPLAY env var,
 * and listen for new surface events.
 *
 * XWayland is optional — if the Xwayland binary is not installed or fails
 * to start, the compositor continues without X11 app support.
 */
void xwayland_init(struct CiosServer *server) {
    /* Check if Xwayland binary exists before trying to create it */
    if (access("/usr/bin/Xwayland", X_OK) != 0) {
        LOG_INFO("Xwayland not installed, skipping X11 support");
        server->xwayland = NULL;
        return;
    }

    server->xwayland = wlr_xwayland_create(server->display,
        server->compositor, false);
    if (!server->xwayland) {
        LOG_WARN("failed to create wlr_xwayland (X11 apps unavailable)");
        return;
    }

    /* Listen for new XWayland surfaces */
    server->new_xwayland_surface.notify = handle_new_xwayland_surface;
    wl_signal_add(&server->xwayland->events.new_surface,
        &server->new_xwayland_surface);

    /* Set DISPLAY env var so child processes can connect to XWayland */
    if (server->xwayland->display_name) {
        setenv("DISPLAY", server->xwayland->display_name, 1);
        LOG_INFO("xwayland display: %s", server->xwayland->display_name);
    }
}
