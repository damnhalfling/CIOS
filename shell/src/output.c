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
#define TOPBAR_HEIGHT 32

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
 * Strategy: first output in list, or largest by pixel area.
 */
static void output_update_primary(struct CiosServer *server) {
    struct CiosOutput *best = NULL;
    int best_area = 0;

    struct CiosOutput *output;
    wl_list_for_each(output, &server->outputs, link) {
        int width, height;
        wlr_output_effective_resolution(output->wlr_output, &width, &height);
        int area = width * height;

        output->is_primary = false;

        if (!best || area > best_area) {
            best = output;
            best_area = area;
        }
    }

    if (best) {
        best->is_primary = true;
        server->primary_output = best;
        LOG_INFO("primary output: %s (%dx%d)",
            best->wlr_output->name,
            best->usable_width,
            best->usable_height + TOPBAR_HEIGHT);
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

    wlr_scene_output_commit(scene_output, NULL);

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

    /* Configure preferred mode using output state */
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

    /* Create scene output and add to output layout */
    output->scene_output = wlr_scene_output_create(server->scene, wlr_output);
    if (!output->scene_output) {
        LOG_ERROR("failed to create scene output for %s", wlr_output->name);
        free(output);
        return;
    }

    wlr_output_layout_add_auto(server->output_layout, wlr_output);

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
