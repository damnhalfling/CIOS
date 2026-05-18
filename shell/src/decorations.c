/*
 * CIOS Shell — Server-side decorations (SSD)
 *
 * Draws a minimal titlebar above each managed surface with:
 *   - Title text (via colored rect as placeholder)
 *   - Close button (red rect, right side)
 *   - Minimize button (yellow rect, next to close)
 *
 * The titlebar is a wlr_scene_tree that is a sibling of the surface's
 * scene_tree, positioned above it. Click detection is handled in input.c.
 *
 * Design: dark titlebar (#1a1a2e), 28px height, 2px border radius feel.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/xwayland.h>

#include "log.h"
#include "server.h"

/* Titlebar dimensions */
#define TITLEBAR_HEIGHT CIOS_TITLEBAR_HEIGHT
#define BUTTON_SIZE 14
#define BUTTON_MARGIN 8
#define BUTTON_SPACING 6

/* Colors (sRGB float) */
static const float color_titlebar[4] = {0.102f, 0.102f, 0.180f, 1.0f};        /* #1a1a2e */
static const float color_titlebar_focused[4] = {0.133f, 0.133f, 0.220f, 1.0f}; /* #222238 */
static const float color_close[4] = {0.878f, 0.282f, 0.282f, 1.0f};           /* #e04848 */
static const float color_close_hover[4] = {1.0f, 0.333f, 0.333f, 1.0f};       /* #ff5555 */
static const float color_minimize[4] = {0.878f, 0.749f, 0.282f, 1.0f};        /* #e0bf48 */
static const float color_maximize[4] = {0.282f, 0.878f, 0.439f, 1.0f};        /* #48e070 */

/*
 * Create decorations for a surface.
 * The decoration tree is created as a parent that contains:
 *   1. Titlebar rect (full width, TITLEBAR_HEIGHT)
 *   2. Close button rect
 *   3. Minimize button rect
 *   4. Maximize button rect
 *
 * The surface's scene_tree is then reparented under this decoration tree,
 * offset by TITLEBAR_HEIGHT pixels.
 */
bool decorations_create(struct CiosSurface *surface) {
    if (!surface || !surface->scene_tree) {
        return false;
    }

    struct CiosServer *server = surface->server;

    /* Get surface dimensions */
    int width = 800;  /* default, will be updated */
    if (surface->xsurface) {
        width = surface->xsurface->width > 0 ? surface->xsurface->width : 800;
    } else if (surface->xdg_toplevel && surface->xdg_toplevel->base->surface) {
        /* XDG surfaces manage their own decorations typically, skip */
        return false;
    }

    /* Create titlebar rect above the surface */
    surface->titlebar = wlr_scene_rect_create(
        surface->scene_tree, width, TITLEBAR_HEIGHT, color_titlebar);
    if (!surface->titlebar) {
        LOG_WARN("decorations: failed to create titlebar for s_%u", surface->id);
        return false;
    }

    /* Position titlebar at top (surface content will be offset down) */
    wlr_scene_node_set_position(&surface->titlebar->node, 0, -TITLEBAR_HEIGHT);

    /* Close button (right side) */
    surface->btn_close = wlr_scene_rect_create(
        surface->scene_tree, BUTTON_SIZE, BUTTON_SIZE, color_close);
    if (surface->btn_close) {
        int close_x = width - BUTTON_MARGIN - BUTTON_SIZE;
        int close_y = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
        wlr_scene_node_set_position(&surface->btn_close->node, close_x, close_y);
    }

    /* Minimize button (left of close) */
    surface->btn_minimize = wlr_scene_rect_create(
        surface->scene_tree, BUTTON_SIZE, BUTTON_SIZE, color_minimize);
    if (surface->btn_minimize) {
        int min_x = width - BUTTON_MARGIN - BUTTON_SIZE - BUTTON_SPACING - BUTTON_SIZE;
        int min_y = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
        wlr_scene_node_set_position(&surface->btn_minimize->node, min_x, min_y);
    }

    /* Maximize button (left of minimize) */
    surface->btn_maximize = wlr_scene_rect_create(
        surface->scene_tree, BUTTON_SIZE, BUTTON_SIZE, color_maximize);
    if (surface->btn_maximize) {
        int max_x = width - BUTTON_MARGIN - BUTTON_SIZE - (BUTTON_SPACING + BUTTON_SIZE) * 2;
        int max_y = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
        wlr_scene_node_set_position(&surface->btn_maximize->node, max_x, max_y);
    }

    surface->decorated = true;
    LOG_INFO("decorations: created for s_%u (width=%d)", surface->id, width);
    return true;
}

/*
 * Update decoration width when surface is resized.
 */
void decorations_update_size(struct CiosSurface *surface, int width) {
    if (!surface || !surface->decorated || !surface->titlebar) {
        return;
    }

    /* Resize titlebar */
    wlr_scene_rect_set_size(surface->titlebar, width, TITLEBAR_HEIGHT);

    /* Reposition buttons */
    if (surface->btn_close) {
        int close_x = width - BUTTON_MARGIN - BUTTON_SIZE;
        int close_y = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
        wlr_scene_node_set_position(&surface->btn_close->node, close_x, close_y);
    }
    if (surface->btn_minimize) {
        int min_x = width - BUTTON_MARGIN - BUTTON_SIZE - BUTTON_SPACING - BUTTON_SIZE;
        int min_y = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
        wlr_scene_node_set_position(&surface->btn_minimize->node, min_x, min_y);
    }
    if (surface->btn_maximize) {
        int max_x = width - BUTTON_MARGIN - BUTTON_SIZE - (BUTTON_SPACING + BUTTON_SIZE) * 2;
        int max_y = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
        wlr_scene_node_set_position(&surface->btn_maximize->node, max_x, max_y);
    }
}

/*
 * Update titlebar color based on focus state.
 */
void decorations_set_focused(struct CiosSurface *surface, bool focused) {
    if (!surface || !surface->decorated || !surface->titlebar) {
        return;
    }
    wlr_scene_rect_set_color(surface->titlebar,
        focused ? color_titlebar_focused : color_titlebar);
}

/*
 * Remove decorations from a surface.
 */
void decorations_destroy(struct CiosSurface *surface) {
    if (!surface || !surface->decorated) {
        return;
    }
    /* Scene nodes are destroyed when their parent tree is destroyed,
     * so we just clear our references */
    surface->titlebar = NULL;
    surface->btn_close = NULL;
    surface->btn_minimize = NULL;
    surface->btn_maximize = NULL;
    surface->decorated = false;
}

/*
 * Check if a click at (x, y) relative to the surface's scene_tree
 * hits a decoration button. Returns the button type or 0.
 */
int decorations_hit_test(struct CiosSurface *surface, int x, int y) {
    if (!surface || !surface->decorated) {
        return 0;
    }

    /* Check if click is in titlebar area */
    if (y < -TITLEBAR_HEIGHT || y >= 0) {
        return 0;  /* Not in titlebar */
    }

    /* Get surface width */
    int width = 800;
    if (surface->xsurface) {
        width = surface->xsurface->width > 0 ? surface->xsurface->width : 800;
    }

    /* Close button hit test */
    int close_x = width - BUTTON_MARGIN - BUTTON_SIZE;
    int close_y_start = -TITLEBAR_HEIGHT + (TITLEBAR_HEIGHT - BUTTON_SIZE) / 2;
    if (x >= close_x && x < close_x + BUTTON_SIZE &&
        y >= close_y_start && y < close_y_start + BUTTON_SIZE) {
        return CIOS_DECO_CLOSE;
    }

    /* Minimize button hit test */
    int min_x = width - BUTTON_MARGIN - BUTTON_SIZE - BUTTON_SPACING - BUTTON_SIZE;
    if (x >= min_x && x < min_x + BUTTON_SIZE &&
        y >= close_y_start && y < close_y_start + BUTTON_SIZE) {
        return CIOS_DECO_MINIMIZE;
    }

    /* Maximize button hit test */
    int max_x = width - BUTTON_MARGIN - BUTTON_SIZE - (BUTTON_SPACING + BUTTON_SIZE) * 2;
    if (x >= max_x && x < max_x + BUTTON_SIZE &&
        y >= close_y_start && y < close_y_start + BUTTON_SIZE) {
        return CIOS_DECO_MAXIMIZE;
    }

    /* Click on titlebar but not on a button — drag area */
    return CIOS_DECO_TITLEBAR;
}

/*
 * Handle minimize: hide the surface.
 */
void decorations_minimize(struct CiosSurface *surface) {
    if (!surface || !surface->scene_tree) {
        return;
    }
    wlr_scene_node_set_enabled(&surface->scene_tree->node, false);
    surface->visible = false;
    LOG_INFO("decorations: minimized s_%u", surface->id);

    /* Move focus to next surface */
    struct CiosServer *server = surface->server;
    if (server->focused == surface) {
        server->focused = NULL;
        /* Find next visible surface to focus */
        struct CiosSurface *next;
        wl_list_for_each(next, &server->surfaces, link) {
            if (next != surface && next->visible) {
                if (next->xdg_toplevel) {
                    server_focus_xdg_surface(server, next);
                } else {
                    server_focus_surface(server, next);
                }
                break;
            }
        }
    }
}
