/*
 * CIOS Shell — Input handling (keyboard and pointer forwarding)
 *
 * Listens for new input devices on the backend, configures keyboards
 * with XKB default keymap, forwards keyboard events to the focused
 * surface via wlr_seat, forwards pointer motion/button events to the
 * surface under the cursor, and manages xcursor theme rendering.
 *
 * Requirements: 9.1 (keyboard forwarding), 9.2 (pointer forwarding),
 *               9.4 (xcursor theme)
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>
#include <linux/input-event-codes.h>

#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_input_device.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <xkbcommon/xkbcommon.h>

#include "log.h"
#include "server.h"

/* Default xcursor theme size */
#define XCURSOR_SIZE 24

/* Drag state for titlebar window move */
static struct {
    struct CiosSurface *surface;
    double grab_x, grab_y;      /* cursor position at grab start */
    int orig_x, orig_y;         /* surface position at grab start */
    bool active;
} drag_state = {0};

/* Keyboard wrapper — holds listeners and back-pointer to server */
struct CiosKeyboard {
    struct CiosServer *server;
    struct wlr_keyboard *keyboard;
    struct wl_listener key;
    struct wl_listener modifiers;
    struct wl_listener destroy;
};

/* ═══════════════════════════════════════════════════════════════
 *  Focus management
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Set keyboard focus on a surface. Updates server->focused and
 * notifies the seat to send keyboard enter/leave events.
 */
void server_focus_surface(struct CiosServer *server, struct CiosSurface *surface) {
    if (!server) {
        return;
    }

    struct CiosSurface *prev_focused = server->focused;

    /* No change in focus */
    if (prev_focused == surface) {
        return;
    }

    /* Clear previous focus */
    if (prev_focused && prev_focused->xsurface && prev_focused->xsurface->surface) {
        wlr_seat_keyboard_clear_focus(server->seat);
    }

    /* Set new focus */
    server->focused = surface;

    if (!surface || !surface->xsurface || !surface->xsurface->surface) {
        return;
    }

    /* Activate the XWayland surface */
    wlr_xwayland_surface_activate(surface->xsurface, true);

    /* Ensure the surface is visible (may have been hidden during splash) */
    if (surface->scene_tree && !surface->visible) {
        wlr_scene_node_set_enabled(&surface->scene_tree->node, true);
        surface->visible = true;
    }

    /* Raise surface to top of its layer (z-order) */
    if (surface->scene_tree) {
        wlr_scene_node_raise_to_top(&surface->scene_tree->node);
    }

    /* Deactivate previous surface */
    if (prev_focused && prev_focused->xsurface) {
        wlr_xwayland_surface_activate(prev_focused->xsurface, false);
        decorations_set_focused(prev_focused, false);
    }

    /* Update decoration focus state */
    decorations_set_focused(surface, true);

    /* Set keyboard focus on the surface */
    struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
    if (keyboard) {
        wlr_seat_keyboard_notify_enter(server->seat,
            surface->xsurface->surface,
            keyboard->keycodes, keyboard->num_keycodes,
            &keyboard->modifiers);
    }

    LOG_INFO("focus changed: s_%u", surface->id);

    /* Send focus_changed event to runtime via IPC (Req 9.3) */
    if (server->ipc) {
        char payload[64];
        snprintf(payload, sizeof(payload), "\"surface_id\":\"s_%u\"", surface->id);
        ipc_send_event(server->ipc, "focus_changed", payload);
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  Helper: find surface under cursor
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Find the CiosSurface under the given layout coordinates.
 * Returns NULL if no surface is found. Sets sx/sy to surface-local coords.
 */
static struct CiosSurface *surface_at(struct CiosServer *server,
        double lx, double ly, struct wlr_surface **wlr_surface,
        double *sx, double *sy) {
    struct wlr_scene_node *node = wlr_scene_node_at(
        &server->scene->tree.node, lx, ly, sx, sy);

    if (!node || node->type != WLR_SCENE_NODE_BUFFER) {
        return NULL;
    }

    /* Walk up the scene tree to find a node with data pointing to a surface */
    struct wlr_scene_buffer *scene_buffer = wlr_scene_buffer_from_node(node);
    struct wlr_scene_surface *scene_surface =
        wlr_scene_surface_try_from_buffer(scene_buffer);
    if (!scene_surface) {
        return NULL;
    }

    *wlr_surface = scene_surface->surface;

    /* Walk up the tree to find the CiosSurface that owns this node */
    struct wlr_scene_tree *tree = node->parent;
    while (tree) {
        /* Check if this tree matches any of our surfaces */
        struct CiosSurface *surf;
        wl_list_for_each(surf, &server->surfaces, link) {
            if (surf->scene_tree == tree) {
                return surf;
            }
        }
        tree = tree->node.parent;
    }

    return NULL;
}

/* ═══════════════════════════════════════════════════════════════
 *  Cursor event handlers
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Process cursor motion — find surface under cursor, forward pointer,
 * and set cursor image.
 */
static void process_cursor_motion(struct CiosServer *server, uint32_t time_msec) {
    /* Handle active drag (titlebar move) */
    if (drag_state.active && drag_state.surface) {
        int new_x = drag_state.orig_x + (int)(server->cursor->x - drag_state.grab_x);
        int new_y = drag_state.orig_y + (int)(server->cursor->y - drag_state.grab_y);
        wlr_scene_node_set_position(&drag_state.surface->scene_tree->node, new_x, new_y);
        return;
    }

    double sx, sy;
    struct wlr_surface *wlr_surface = NULL;

    struct CiosSurface *surface = surface_at(server,
        server->cursor->x, server->cursor->y,
        &wlr_surface, &sx, &sy);

    if (!surface) {
        /* No surface under cursor — set default cursor image */
        wlr_cursor_set_xcursor(server->cursor, server->cursor_mgr, "default");
        wlr_seat_pointer_clear_focus(server->seat);
        return;
    }

    /* Notify the seat of pointer motion over the surface */
    wlr_seat_pointer_notify_enter(server->seat, wlr_surface, sx, sy);
    wlr_seat_pointer_notify_motion(server->seat, time_msec, sx, sy);
}

/*
 * Handle relative pointer motion event.
 */
static void handle_cursor_motion(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, cursor_motion);
    struct wlr_pointer_motion_event *event = data;

    wlr_cursor_move(server->cursor, &event->pointer->base,
        event->delta_x, event->delta_y);
    process_cursor_motion(server, event->time_msec);
}

/*
 * Handle absolute pointer motion event (e.g., tablet, touchscreen).
 */
static void handle_cursor_motion_absolute(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, cursor_motion_absolute);
    struct wlr_pointer_motion_absolute_event *event = data;

    wlr_cursor_warp_absolute(server->cursor, &event->pointer->base,
        event->x, event->y);
    process_cursor_motion(server, event->time_msec);
}

/*
 * Handle pointer button event — forward to surface under cursor.
 * Also focus the surface on click.
 */
static void handle_cursor_button(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, cursor_button);
    struct wlr_pointer_button_event *event = data;

    if (event->state == WL_POINTER_BUTTON_STATE_PRESSED) {
        double sx, sy;
        struct wlr_surface *wlr_surface = NULL;

        /* Super+Left click: start drag on any surface (no titlebar needed) */
        if (event->button == BTN_LEFT) {
            struct wlr_keyboard *kb = wlr_seat_get_keyboard(server->seat);
            uint32_t mods = kb ? wlr_keyboard_get_modifiers(kb) : 0;
            if (mods & WLR_MODIFIER_LOGO) {
                struct CiosSurface *surface = surface_at(server,
                    server->cursor->x, server->cursor->y,
                    &wlr_surface, &sx, &sy);
                if (surface && surface->scene_tree) {
                    server_focus_surface(server, surface);
                    int surf_x, surf_y;
                    wlr_scene_node_coords(&surface->scene_tree->node, &surf_x, &surf_y);
                    drag_state.surface = surface;
                    drag_state.grab_x = server->cursor->x;
                    drag_state.grab_y = server->cursor->y;
                    drag_state.orig_x = surf_x;
                    drag_state.orig_y = surf_y;
                    drag_state.active = true;
                    return;
                }
            }
        }

        /* Check for decoration clicks (left button only) */
        if (event->button == BTN_LEFT) {
            struct CiosSurface *surf;
            wl_list_for_each(surf, &server->surfaces, link) {
                if (!surf->decorated || !surf->visible || !surf->scene_tree) {
                    continue;
                }
                /* Get surface position in layout coordinates */
                int surf_x, surf_y;
                wlr_scene_node_coords(&surf->scene_tree->node, &surf_x, &surf_y);

                /* Calculate click position relative to surface */
                int rel_x = (int)server->cursor->x - surf_x;
                int rel_y = (int)server->cursor->y - surf_y;

                int hit = decorations_hit_test(surf, rel_x, rel_y);
                if (hit == CIOS_DECO_CLOSE) {
                    LOG_INFO("decoration click: close s_%u", surf->id);
                    if (surf->xsurface) {
                        wlr_xwayland_surface_close(surf->xsurface);
                    } else if (surf->xdg_toplevel) {
                        wlr_xdg_toplevel_send_close(surf->xdg_toplevel);
                    }
                    return;
                } else if (hit == CIOS_DECO_MINIMIZE) {
                    LOG_INFO("decoration click: minimize s_%u", surf->id);
                    decorations_minimize(surf);
                    return;
                } else if (hit == CIOS_DECO_MAXIMIZE) {
                    LOG_INFO("decoration click: maximize s_%u", surf->id);
                    struct CiosOutput *primary = output_get_primary(server);
                    if (primary && surf->xsurface) {
                        int y_off = CIOS_TITLEBAR_HEIGHT;
                        wlr_scene_node_set_position(&surf->scene_tree->node,
                            primary->usable_x, primary->usable_y + y_off);
                        wlr_xwayland_surface_configure(surf->xsurface,
                            primary->usable_x, primary->usable_y + y_off,
                            primary->usable_width, primary->usable_height - y_off);
                        decorations_update_size(surf, primary->usable_width);
                    }
                    return;
                } else if (hit == CIOS_DECO_TITLEBAR) {
                    /* Click on titlebar — start drag to move window */
                    server_focus_surface(server, surf);
                    int surf_x, surf_y_pos;
                    wlr_scene_node_coords(&surf->scene_tree->node, &surf_x, &surf_y_pos);
                    drag_state.surface = surf;
                    drag_state.grab_x = server->cursor->x;
                    drag_state.grab_y = server->cursor->y;
                    drag_state.orig_x = surf_x;
                    drag_state.orig_y = surf_y_pos;
                    drag_state.active = true;
                    wlr_seat_pointer_notify_button(server->seat,
                        event->time_msec, event->button, event->state);
                    return;
                }
            }
        }

        /* Any button press — find surface, focus it, ensure pointer enter */
        struct CiosSurface *surface = surface_at(server,
            server->cursor->x, server->cursor->y,
            &wlr_surface, &sx, &sy);

        if (surface) {
            if (surface->xdg_toplevel) {
                server_focus_xdg_surface(server, surface);
            } else {
                server_focus_surface(server, surface);
            }
            /* Ensure pointer focus is on the correct wlr_surface */
            if (wlr_surface) {
                wlr_seat_pointer_notify_enter(server->seat, wlr_surface, sx, sy);
            }
        }
    }

    /* End drag on button release */
    if (event->state == WL_POINTER_BUTTON_STATE_RELEASED && drag_state.active) {
        drag_state.active = false;
        drag_state.surface = NULL;
    }

    /* Notify the seat of the button event */
    wlr_seat_pointer_notify_button(server->seat,
        event->time_msec, event->button, event->state);
}

/*
 * Handle pointer axis (scroll) event — forward to focused surface.
 */
static void handle_cursor_axis(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, cursor_axis);
    struct wlr_pointer_axis_event *event = data;

    wlr_seat_pointer_notify_axis(server->seat,
        event->time_msec, event->orientation,
        event->delta, event->delta_discrete, event->source,
        event->relative_direction);
}

/*
 * Handle pointer frame event — signals end of a group of pointer events.
 */
static void handle_cursor_frame(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, cursor_frame);
    wlr_seat_pointer_notify_frame(server->seat);
}

/* ═══════════════════════════════════════════════════════════════
 *  Keyboard event handlers
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Handle keyboard key event — check hotkeys first, then forward to surface.
 */
static void handle_keyboard_key(struct wl_listener *listener, void *data) {
    struct CiosKeyboard *kb = wl_container_of(listener, kb, key);
    struct wlr_keyboard_key_event *event = data;

    /* Get current modifier state */
    uint32_t modifiers = wlr_keyboard_get_modifiers(kb->keyboard);
    bool pressed = (event->state == WL_KEYBOARD_KEY_STATE_PRESSED);

    /* Check hotkeys first — if consumed, don't forward to surface */
    if (hotkeys_handle_key(kb->server, event->keycode, modifiers, pressed)) {
        return;
    }

    /* Forward key event to the focused surface */
    wlr_seat_set_keyboard(kb->server->seat, kb->keyboard);
    wlr_seat_keyboard_notify_key(kb->server->seat,
        event->time_msec, event->keycode, event->state);
}

/*
 * Handle keyboard modifiers event — forward to focused surface via seat.
 */
static void handle_keyboard_modifiers(struct wl_listener *listener, void *data) {
    struct CiosKeyboard *kb = wl_container_of(listener, kb, modifiers);

    wlr_seat_set_keyboard(kb->server->seat, kb->keyboard);
    wlr_seat_keyboard_notify_modifiers(kb->server->seat,
        &kb->keyboard->modifiers);
}

/*
 * Handle keyboard destroy — clean up wrapper.
 */
static void handle_keyboard_destroy(struct wl_listener *listener, void *data) {
    struct CiosKeyboard *kb = wl_container_of(listener, kb, destroy);

    wl_list_remove(&kb->key.link);
    wl_list_remove(&kb->modifiers.link);
    wl_list_remove(&kb->destroy.link);
    free(kb);
}

/* ═══════════════════════════════════════════════════════════════
 *  New input device handler
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Configure a new keyboard device with XKB default keymap.
 */
static void handle_new_keyboard(struct CiosServer *server,
        struct wlr_input_device *device) {
    struct wlr_keyboard *keyboard = wlr_keyboard_from_input_device(device);

    /* Create XKB context and load default keymap */
    struct xkb_context *context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
    if (!context) {
        LOG_ERROR("failed to create xkb_context");
        return;
    }

    struct xkb_keymap *keymap = xkb_keymap_new_from_names(context, NULL,
        XKB_KEYMAP_COMPILE_NO_FLAGS);
    if (!keymap) {
        LOG_ERROR("failed to create xkb_keymap");
        xkb_context_unref(context);
        return;
    }

    wlr_keyboard_set_keymap(keyboard, keymap);
    wlr_keyboard_set_repeat_info(keyboard, 25, 600);

    xkb_keymap_unref(keymap);
    xkb_context_unref(context);

    /* Allocate keyboard wrapper with embedded listeners */
    struct CiosKeyboard *kb = calloc(1, sizeof(*kb));
    if (!kb) {
        LOG_ERROR("failed to allocate CiosKeyboard");
        return;
    }

    kb->server = server;
    kb->keyboard = keyboard;

    /* Listen for key, modifier, and destroy events */
    kb->key.notify = handle_keyboard_key;
    wl_signal_add(&keyboard->events.key, &kb->key);

    kb->modifiers.notify = handle_keyboard_modifiers;
    wl_signal_add(&keyboard->events.modifiers, &kb->modifiers);

    kb->destroy.notify = handle_keyboard_destroy;
    wl_signal_add(&device->events.destroy, &kb->destroy);

    /* Set this keyboard on the seat */
    wlr_seat_set_keyboard(server->seat, keyboard);

    LOG_INFO("keyboard configured: %s", device->name ? device->name : "(unnamed)");

    /* If there's a focused surface waiting for keyboard, send enter now.
     * This fixes the race condition where a surface maps before any keyboard
     * is configured — the greeter gets focus but no keyboard_enter. */
    if (server->focused) {
        struct wlr_surface *focused_wlr = NULL;
        if (server->focused->xdg_toplevel) {
            focused_wlr = server->focused->xdg_toplevel->base->surface;
        } else if (server->focused->xsurface && server->focused->xsurface->surface) {
            focused_wlr = server->focused->xsurface->surface;
        }
        if (focused_wlr) {
            wlr_seat_keyboard_notify_enter(server->seat, focused_wlr,
                keyboard->keycodes, keyboard->num_keycodes, &keyboard->modifiers);
        }
    }
}

/*
 * Configure a new pointer device — attach to cursor.
 */
static void handle_new_pointer(struct CiosServer *server,
        struct wlr_input_device *device) {
    wlr_cursor_attach_input_device(server->cursor, device);
    LOG_INFO("pointer attached: %s", device->name ? device->name : "(unnamed)");
}

/*
 * Handle new input device event from backend.
 * Routes to keyboard or pointer handler based on device type.
 */
static void handle_new_input(struct wl_listener *listener, void *data) {
    struct CiosServer *server = wl_container_of(listener, server, new_input);
    struct wlr_input_device *device = data;

    switch (device->type) {
    case WLR_INPUT_DEVICE_KEYBOARD:
        handle_new_keyboard(server, device);
        break;
    case WLR_INPUT_DEVICE_POINTER:
        handle_new_pointer(server, device);
        break;
    default:
        LOG_INFO("ignoring input device type %d: %s",
            device->type, device->name ? device->name : "(unnamed)");
        break;
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  Initialization
 * ═══════════════════════════════════════════════════════════════ */

/*
 * Initialize input handling — create cursor, load xcursor theme,
 * and register new_input listener on backend.
 */
void input_init(struct CiosServer *server) {
    /* Create the cursor — tracks pointer position across outputs */
    server->cursor = wlr_cursor_create();
    if (!server->cursor) {
        LOG_ERROR("failed to create wlr_cursor");
        return;
    }
    wlr_cursor_attach_output_layout(server->cursor, server->output_layout);

    /* Create xcursor manager and load default theme */
    server->cursor_mgr = wlr_xcursor_manager_create(NULL, XCURSOR_SIZE);
    if (!server->cursor_mgr) {
        LOG_ERROR("failed to create wlr_xcursor_manager");
        return;
    }

    /* Set default cursor image */
    wlr_cursor_set_xcursor(server->cursor, server->cursor_mgr, "default");

    /* Register cursor event listeners */
    server->cursor_motion.notify = handle_cursor_motion;
    wl_signal_add(&server->cursor->events.motion, &server->cursor_motion);

    server->cursor_motion_absolute.notify = handle_cursor_motion_absolute;
    wl_signal_add(&server->cursor->events.motion_absolute,
        &server->cursor_motion_absolute);

    server->cursor_button.notify = handle_cursor_button;
    wl_signal_add(&server->cursor->events.button, &server->cursor_button);

    server->cursor_axis.notify = handle_cursor_axis;
    wl_signal_add(&server->cursor->events.axis, &server->cursor_axis);

    server->cursor_frame.notify = handle_cursor_frame;
    wl_signal_add(&server->cursor->events.frame, &server->cursor_frame);

    /* Register new_input listener on backend */
    server->new_input.notify = handle_new_input;
    wl_signal_add(&server->backend->events.new_input, &server->new_input);

    LOG_INFO("input initialized (xcursor size=%d)", XCURSOR_SIZE);
}
