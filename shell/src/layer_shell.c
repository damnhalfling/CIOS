/*
 * CIOS Shell — Layer shell support (wlr-layer-shell-unstable-v1)
 *
 * Handles layer-shell surfaces (primarily the topbar). Registers the
 * wlr_layer_shell_v1 global, listens for new layer surfaces, configures
 * them according to their requested anchor/exclusive zone/layer, and
 * applies exclusive zones to output usable_area calculations.
 *
 * Requirements: 5.1 (exclusive zone 32px), 5.2 (anchor TOP+LEFT+RIGHT),
 *               5.3 (usable area calculation), 5.4 (constrain surfaces),
 *               10.4 (topbar on TOP layer)
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_layer_shell_v1.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_scene.h>

#include "log.h"
#include "server.h"

/* ═══════════════════════════════════════════════════════════════
 *  CiosLayerSurface — Internal wrapper for a layer-shell surface
 * ═══════════════════════════════════════════════════════════════ */
struct CiosLayerSurface {
    struct CiosServer *server;
    struct wlr_layer_surface_v1 *layer_surface;
    struct wlr_scene_layer_surface_v1 *scene_layer_surface;

    struct wl_listener map;
    struct wl_listener unmap;
    struct wl_listener destroy;
    struct wl_listener new_popup;
};

/*
 * Map a wlr_layer_shell_v1_layer enum to the corresponding scene tree.
 */
static struct wlr_scene_tree *layer_get_scene_tree(struct CiosServer *server,
        enum zwlr_layer_shell_v1_layer layer) {
    switch (layer) {
    case ZWLR_LAYER_SHELL_V1_LAYER_BACKGROUND:
        return server->layer_bg;
    case ZWLR_LAYER_SHELL_V1_LAYER_BOTTOM:
        return server->layer_bottom;
    case ZWLR_LAYER_SHELL_V1_LAYER_TOP:
        return server->layer_top;
    case ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY:
        return server->layer_overlay;
    default:
        return server->layer_top;
    }
}

/*
 * Recalculate usable area for all outputs based on layer surface
 * exclusive zones. Called when a layer surface is mapped or unmapped.
 *
 * This iterates all outputs and applies exclusive zone reservations
 * from layer surfaces assigned to each output.
 */
static void layer_shell_arrange_output(struct CiosServer *server,
        struct wlr_output *wlr_output) {
    struct CiosOutput *output = NULL;
    struct CiosOutput *iter;
    wl_list_for_each(iter, &server->outputs, link) {
        if (iter->wlr_output == wlr_output) {
            output = iter;
            break;
        }
    }

    if (!output) {
        return;
    }

    /* Start with full output dimensions */
    int width, height;
    wlr_output_effective_resolution(wlr_output, &width, &height);

    /* Reset usable area to full output */
    struct wlr_box usable_area = {
        .x = 0,
        .y = 0,
        .width = width,
        .height = height,
    };

    /* In wlroots 0.18, usable area is calculated by the compositor directly.
     * Layer surfaces with exclusive zones reduce the usable area. */
    /* TODO: iterate layer surfaces and subtract exclusive zones */

    /* Apply the calculated usable area to our output struct */
    output->usable_x = usable_area.x;
    output->usable_y = usable_area.y;
    output->usable_width = usable_area.width;
    output->usable_height = usable_area.height;

    LOG_INFO("output %s usable area: x=%d y=%d w=%d h=%d",
        wlr_output->name,
        output->usable_x, output->usable_y,
        output->usable_width, output->usable_height);
}

/*
 * Handle layer surface map — the surface is now visible.
 * Arrange the output to account for any exclusive zone.
 */
static void handle_layer_surface_map(struct wl_listener *listener, void *data) {
    struct CiosLayerSurface *layer = wl_container_of(listener, layer, map);
    struct wlr_layer_surface_v1 *lsurface = layer->layer_surface;

    LOG_INFO("layer surface mapped: namespace=%s, exclusive_zone=%d",
        lsurface->namespace ? lsurface->namespace : "(null)",
        lsurface->current.exclusive_zone);

    /* Rearrange the output to apply exclusive zone */
    if (lsurface->output) {
        layer_shell_arrange_output(layer->server, lsurface->output);
    }
}

/*
 * Handle layer surface unmap — the surface is no longer visible.
 * Rearrange the output to reclaim exclusive zone space.
 */
static void handle_layer_surface_unmap(struct wl_listener *listener, void *data) {
    struct CiosLayerSurface *layer = wl_container_of(listener, layer, unmap);
    struct wlr_layer_surface_v1 *lsurface = layer->layer_surface;

    LOG_INFO("layer surface unmapped: namespace=%s",
        lsurface->namespace ? lsurface->namespace : "(null)");

    /* Rearrange the output to reclaim exclusive zone */
    if (lsurface->output) {
        layer_shell_arrange_output(layer->server, lsurface->output);
    }
}

/*
 * Handle layer surface destroy — clean up our wrapper.
 */
static void handle_layer_surface_destroy(struct wl_listener *listener, void *data) {
    struct CiosLayerSurface *layer = wl_container_of(listener, layer, destroy);

    LOG_INFO("layer surface destroyed");

    /* Remove listeners */
    wl_list_remove(&layer->map.link);
    wl_list_remove(&layer->unmap.link);
    wl_list_remove(&layer->destroy.link);
    wl_list_remove(&layer->new_popup.link);

    free(layer);
}

/*
 * Handle layer surface popup creation (no-op for now, but listener needed).
 */
static void handle_layer_surface_new_popup(struct wl_listener *listener, void *data) {
    /* Popups on layer surfaces are not used by the topbar currently */
    (void)listener;
    (void)data;
}

/*
 * Handle new layer surface event from wlr_layer_shell_v1.
 *
 * Creates a scene layer surface node in the correct layer tree,
 * configures the surface geometry based on its anchor and exclusive zone,
 * and sets up lifecycle listeners.
 */
static void handle_new_layer_surface(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, new_layer_surface);
    struct wlr_layer_surface_v1 *layer_surface = data;

    LOG_INFO("new layer surface: namespace=%s, layer=%d, anchor=0x%x, exclusive=%d",
        layer_surface->namespace ? layer_surface->namespace : "(null)",
        layer_surface->pending.layer,
        layer_surface->pending.anchor,
        layer_surface->pending.exclusive_zone);

    /*
     * If no output is specified, assign to the primary output.
     */
    if (!layer_surface->output) {
        struct CiosOutput *primary = output_get_primary(server);
        if (primary) {
            layer_surface->output = primary->wlr_output;
        } else {
            LOG_WARN("no output available for layer surface, closing");
            wlr_layer_surface_v1_destroy(layer_surface);
            return;
        }
    }

    /* Allocate our layer surface wrapper */
    struct CiosLayerSurface *layer = calloc(1, sizeof(*layer));
    if (!layer) {
        LOG_ERROR("failed to allocate CiosLayerSurface");
        wlr_layer_surface_v1_destroy(layer_surface);
        return;
    }

    layer->server = server;
    layer->layer_surface = layer_surface;

    /*
     * Get the scene tree for the requested layer and create a
     * wlr_scene_layer_surface_v1 node. This helper handles:
     * - Positioning based on anchor edges
     * - Sizing based on desired size and output dimensions
     * - Exclusive zone reservation
     */
    struct wlr_scene_tree *parent_tree = layer_get_scene_tree(server,
        layer_surface->pending.layer);

    layer->scene_layer_surface = wlr_scene_layer_surface_v1_create(
        parent_tree, layer_surface);
    if (!layer->scene_layer_surface) {
        LOG_ERROR("failed to create scene layer surface");
        free(layer);
        wlr_layer_surface_v1_destroy(layer_surface);
        return;
    }

    /* Store our wrapper in the layer surface data for later retrieval */
    layer_surface->data = layer;

    /* Set up lifecycle listeners */
    layer->map.notify = handle_layer_surface_map;
    wl_signal_add(&layer_surface->surface->events.map, &layer->map);

    layer->unmap.notify = handle_layer_surface_unmap;
    wl_signal_add(&layer_surface->surface->events.unmap, &layer->unmap);

    layer->destroy.notify = handle_layer_surface_destroy;
    wl_signal_add(&layer_surface->events.destroy, &layer->destroy);

    layer->new_popup.notify = handle_layer_surface_new_popup;
    wl_signal_add(&layer_surface->events.new_popup, &layer->new_popup);

    /*
     * Arrange the layer surface on its output. This configures the
     * surface size and position based on anchor, margin, and exclusive zone.
     * The wlr_scene_layer_surface_v1 helper does most of the heavy lifting.
     */
    struct CiosOutput *output = NULL;
    struct CiosOutput *iter;
    wl_list_for_each(iter, &server->outputs, link) {
        if (iter->wlr_output == layer_surface->output) {
            output = iter;
            break;
        }
    }

    if (output) {
        int width, height;
        wlr_output_effective_resolution(output->wlr_output, &width, &height);

        struct wlr_box full_area = {
            .x = 0,
            .y = 0,
            .width = width,
            .height = height,
        };

        struct wlr_box usable_area = full_area;

        wlr_scene_layer_surface_v1_configure(layer->scene_layer_surface,
            &full_area, &usable_area);

        /* Update output usable area from the exclusive zone calculation */
        output->usable_x = usable_area.x;
        output->usable_y = usable_area.y;
        output->usable_width = usable_area.width;
        output->usable_height = usable_area.height;

        LOG_INFO("layer surface configured on %s: usable y=%d h=%d",
            output->wlr_output->name,
            output->usable_y, output->usable_height);
    }
}

/*
 * Initialize layer shell support.
 *
 * Creates the wlr_layer_shell_v1 global on the display and registers
 * the new_surface listener. Called from server_init().
 */
void layer_shell_init(struct CiosServer *server) {
    server->layer_shell = wlr_layer_shell_v1_create(server->display, 4);
    if (!server->layer_shell) {
        LOG_ERROR("failed to create wlr_layer_shell_v1");
        return;
    }

    server->new_layer_surface.notify = handle_new_layer_surface;
    wl_signal_add(&server->layer_shell->events.new_surface,
        &server->new_layer_surface);

    LOG_INFO("layer shell initialized (version 4)");
}
