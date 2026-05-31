/*
 * CIOS Shell — Output (monitor) management
 *
 * Handles output hotplug: configures preferred mode, creates scene output,
 * adds to output layout, tracks in list, designates primary output,
 * and calculates usable area (full output minus 32px topbar).
 *
 * Requirements: 5.3 (usable area), 8.1 (output added), 8.2 (output removed), 8.3 (primary output)
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>

#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_scene.h>

#include "log.h"
#include "server.h"

/* Topbar exclusive zone height in pixels */
#define TOPBAR_HEIGHT 0

/*
 * Recalculate usable area for an output.
 * Usable area = full output minus topbar (32px at top).
 */
static void output_update_usable_area(struct CiosOutput *output) {
    int width, height;
    wlr_output_effective_resolution(output->wlr_output, &width, &height);

    output->usable_x = 0;
    output->usable_y = TOPBAR_HEIGHT;
    output->usable_width = width;
    output->usable_height = height - TOPBAR_HEIGHT;
}

/*
 * Determine which output should be primary.
 * Strategy: prefer internal displays (eDP, LVDS, DSI) over external.
 * Among same type, prefer largest by pixel area.
 */
static void output_update_primary(struct CiosServer *server) {
    struct CiosOutput *best = NULL;
    int best_area = 0;
    bool best_is_internal = false;

    struct CiosOutput *output;
    wl_list_for_each(output, &server->outputs, link) {
        int width, height;
        wlr_output_effective_resolution(output->wlr_output, &width, &height);
        int area = width * height;

        output->is_primary = false;

        /* Internal displays: eDP, LVDS, DSI */
        const char *name = output->wlr_output->name;
        bool is_internal = (strncmp(name, "eDP", 3) == 0 ||
                           strncmp(name, "LVDS", 4) == 0 ||
                           strncmp(name, "DSI", 3) == 0);

        /* Prefer internal over external, then largest area */
        if (!best ||
            (is_internal && !best_is_internal) ||
            (is_internal == best_is_internal && area > best_area)) {
            best = output;
            best_area = area;
            best_is_internal = is_internal;
        }
    }

    if (best) {
        best->is_primary = true;
        server->primary_output = best;
        LOG_INFO("primary output: %s (%dx%d)%s",
            best->wlr_output->name,
            best->usable_width,
            best->usable_height + TOPBAR_HEIGHT,
            best_is_internal ? " [internal]" : " [external]");
    } else {
        server->primary_output = NULL;
    }
}

/*
 * Handle output frame event — commit pending scene output state.
 */
static void handle_output_frame(struct wl_listener *listener, void *data) {
    struct CiosOutput *output = wl_container_of(listener, output, frame);
    struct wlr_scene_output *scene_output = output->scene_output;

    if (!scene_output || !output->wlr_output || !output->wlr_output->enabled) {
        return;
    }

    if (!wlr_scene_output_commit(scene_output, NULL)) {
        return;  /* Commit failed — skip frame done notification */
    }

    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    wlr_scene_output_send_frame_done(scene_output, &now);
}

/*
 * Handle output request_state event — apply requested output state.
 */
static void handle_output_request_state(struct wl_listener *listener, void *data) {
    struct CiosOutput *output = wl_container_of(listener, output, request_state);
    const struct wlr_output_event_request_state *event = data;

    wlr_output_commit_state(output->wlr_output, event->state);

    /* Recalculate usable area after state change */
    output_update_usable_area(output);
}

/*
 * Handle output destroy — remove from list, update primary, notify runtime.
 */
static void handle_output_destroy(struct wl_listener *listener, void *data) {
    struct CiosOutput *output = wl_container_of(listener, output, destroy);
    struct CiosServer *server = output->server;

    LOG_INFO("output removed: %s", output->wlr_output->name);

    /* Send output_removed event to runtime via IPC (Req 8.2) */
    if (server->ipc && output->wlr_output->name) {
        char payload[256];
        snprintf(payload, sizeof(payload),
                 "\"output_id\":\"%s\"",
                 output->wlr_output->name);
        ipc_send_event(server->ipc, "output_removed", payload);
    }

    /* Remove listeners */
    wl_list_remove(&output->frame.link);
    wl_list_remove(&output->request_state.link);
    wl_list_remove(&output->destroy.link);

    /* Remove from outputs list */
    wl_list_remove(&output->link);

    free(output);

    /* Update primary output designation */
    output_update_primary(server);
}

/*
 * Handle new output event from backend.
 * Configure preferred mode, create scene output, add to layout.
 */
static void handle_new_output(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, new_output);
    struct wlr_output *wlr_output = data;

    LOG_INFO("new output: %s", wlr_output->name);

    /* Initialize the output with the renderer */
    wlr_output_init_render(wlr_output, server->allocator, server->renderer);

    /* Configure output mode — use preferred mode (most compatible).
     * The preferred mode is what the display reports as optimal.
     * Using the largest mode can exceed VRAM in VMs. */
    struct wlr_output_state state;
    wlr_output_state_init(&state);
    wlr_output_state_set_enabled(&state, true);

    struct wlr_output_mode *mode = wlr_output_preferred_mode(wlr_output);
    if (mode) {
        wlr_output_state_set_mode(&state, mode);
    }

    wlr_output_commit_state(wlr_output, &state);
    wlr_output_state_finish(&state);

    /* Allocate our output wrapper */
    struct CiosOutput *output = calloc(1, sizeof(*output));
    if (!output) {
        LOG_ERROR("failed to allocate CiosOutput");
        return;
    }

    output->server = server;
    output->wlr_output = wlr_output;

    /* Add to output layout first (scene_layout needs this to position scene_output) */
    wlr_output_layout_add_auto(server->output_layout, wlr_output);

    /* If this is not the first output, reposition to extend (not mirror).
     * wlr_output_layout_add_auto may place at (0,0) causing mirror.
     * We use the layout's bounding box to find the right edge. */
    if (!wl_list_empty(&server->outputs)) {
        /* Get the bounding box of all outputs currently in the layout */
        struct wlr_box layout_box;
        wlr_output_layout_get_box(server->output_layout, NULL, &layout_box);

        /* Check if this output was placed at origin (overlapping) */
        struct wlr_output_layout_output *lo =
            wlr_output_layout_get(server->output_layout, wlr_output);
        if (lo && lo->x == 0 && lo->y == 0 && layout_box.width > 0) {
            /* Find the right edge of existing outputs (exclude this one's width) */
            int this_w, this_h;
            wlr_output_effective_resolution(wlr_output, &this_w, &this_h);
            int right_edge = layout_box.width - this_w;
            if (right_edge <= 0) {
                /* Fallback: use the first output's width */
                struct CiosOutput *first;
                wl_list_for_each(first, &server->outputs, link) {
                    wlr_output_effective_resolution(first->wlr_output, &right_edge, &this_h);
                    break;
                }
            }
            if (right_edge > 0) {
                wlr_output_layout_add(server->output_layout, wlr_output, right_edge, 0);
                LOG_INFO("output %s repositioned to x=%d (extended)", wlr_output->name, right_edge);
            }
        }
    }

    /* Create scene output AFTER layout positioning — scene_layout auto-syncs */
    output->scene_output = wlr_scene_output_create(server->scene, wlr_output);
    if (!output->scene_output) {
        LOG_ERROR("failed to create scene output for %s", wlr_output->name);
        free(output);
        return;
    }

    /* Calculate usable area */
    output_update_usable_area(output);

    /* Listen for frame, request_state, and destroy events */
    output->frame.notify = handle_output_frame;
    wl_signal_add(&wlr_output->events.frame, &output->frame);

    output->request_state.notify = handle_output_request_state;
    wl_signal_add(&wlr_output->events.request_state, &output->request_state);

    output->destroy.notify = handle_output_destroy;
    wl_signal_add(&wlr_output->events.destroy, &output->destroy);

    /* Add to server's output list */
    wl_list_insert(&server->outputs, &output->link);

    /* Update primary output designation */
    output_update_primary(server);

    /* Send output_added event to runtime via IPC (Req 8.1) */
    if (server->ipc) {
        int width, height;
        wlr_output_effective_resolution(wlr_output, &width, &height);
        char payload[256];
        snprintf(payload, sizeof(payload),
                 "\"output_id\":\"%s\",\"w\":%d,\"h\":%d",
                 wlr_output->name, width, height);
        ipc_send_event(server->ipc, "output_added", payload);
    }

    LOG_INFO("output configured: %s (%dx%d, usable: %dx%d at y=%d)",
        wlr_output->name,
        output->usable_width, output->usable_height + TOPBAR_HEIGHT,
        output->usable_width, output->usable_height,
        output->usable_y);
}

/*
 * Initialize output management — register new_output listener on backend.
 */
void output_init(struct CiosServer *server) {
    server->primary_output = NULL;
    server->new_output.notify = handle_new_output;
    wl_signal_add(&server->backend->events.new_output, &server->new_output);
}

/*
 * Get the primary output (first/largest).
 * Returns NULL if no outputs are connected.
 */
struct CiosOutput *output_get_primary(struct CiosServer *server) {
    return server->primary_output;
}

/*
 * Find an output by name (e.g. "eDP-1", "HDMI-A-1").
 */
struct CiosOutput *output_find_by_name(struct CiosServer *server, const char *name) {
    struct CiosOutput *output;
    wl_list_for_each(output, &server->outputs, link) {
        if (output->wlr_output && output->wlr_output->name &&
            strcmp(output->wlr_output->name, name) == 0) {
            return output;
        }
    }
    return NULL;
}

/*
 * Position an output at specific coordinates in the layout.
 * Used by IPC configure_output command.
 */
bool output_set_position(struct CiosOutput *output, int x, int y) {
    if (!output || !output->wlr_output) return false;

    struct CiosServer *server = output->server;
    wlr_output_layout_add(server->output_layout, output->wlr_output, x, y);
    output_update_usable_area(output);

    /* Update scene output position to match layout */
    if (output->scene_output) {
        wlr_scene_output_set_position(output->scene_output, x, y);
    }

    LOG_INFO("output repositioned: %s at (%d, %d)", output->wlr_output->name, x, y);
    return true;
}

/*
 * Mirror an output to show the same content as another.
 * Positions both at (0,0) in the layout.
 */
bool output_set_mirror(struct CiosOutput *output, struct CiosOutput *mirror_of) {
    if (!output || !mirror_of) return false;

    struct CiosServer *server = output->server;

    /* Position both at origin — wlroots will render same content */
    wlr_output_layout_add(server->output_layout, mirror_of->wlr_output, 0, 0);
    wlr_output_layout_add(server->output_layout, output->wlr_output, 0, 0);

    output_update_usable_area(output);
    output_update_usable_area(mirror_of);

    LOG_INFO("output mirrored: %s mirrors %s",
        output->wlr_output->name, mirror_of->wlr_output->name);
    return true;
}
