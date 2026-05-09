/*
 * CIOS Shell — Hotkey interception
 *
 * Intercepts specific key combinations before they are forwarded to the
 * focused surface. Matched keys are consumed (not forwarded).
 *
 * Hotkeys:
 *   Ctrl+Space  → send key_intercepted event ("ctrl+space") to runtime via IPC
 *   Super       → lone press (press+release with no other key) focuses runtime main surface
 *   Alt+Tab     → cycle focus to next surface in surfaces list
 *   Alt+F4      → close focused surface (skip if pid matches runtime pid)
 *   Super+Q     → send logout_requested event, set pending_logout flag
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
 */

#define _POSIX_C_SOURCE 200809L

#include <stdbool.h>
#include <stdint.h>
#include <linux/input-event-codes.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/xwayland.h>

#include "log.h"
#include "server.h"

/* ═══════════════════════════════════════════════════════════════
 *  State for Super lone-press detection
 *
 *  Super is a "lone press" if:
 *  1. Super is pressed down
 *  2. No other key is pressed while Super is held
 *  3. Super is released
 *
 *  If any other key is pressed between Super press and release,
 *  it's a combo (e.g., Super+Q) and not a lone press.
 * ═══════════════════════════════════════════════════════════════ */

static bool super_pressed = false;
static bool super_used_in_combo = false;

/* Pending logout flag — set when Super+Q is pressed, cleared on confirmation */
static bool pending_logout = false;

/* ═══════════════════════════════════════════════════════════════
 *  Helper: find the first surface owned by the runtime process
 * ═══════════════════════════════════════════════════════════════ */

static struct CiosSurface *find_runtime_main_surface(struct CiosServer *server) {
    if (!server->proc_runtime || server->proc_runtime->pid <= 0) {
        return NULL;
    }

    pid_t runtime_pid = server->proc_runtime->pid;
    struct CiosSurface *surf;

    wl_list_for_each(surf, &server->surfaces, link) {
        if (surf->pid == runtime_pid) {
            return surf;
        }
    }

    return NULL;
}

/* ═══════════════════════════════════════════════════════════════
 *  Helper: get runtime pid
 * ═══════════════════════════════════════════════════════════════ */

static pid_t get_runtime_pid(struct CiosServer *server) {
    if (!server->proc_runtime || server->proc_runtime->pid <= 0) {
        return -1;
    }
    return server->proc_runtime->pid;
}

/* ═══════════════════════════════════════════════════════════════
 *  Hotkey handlers
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Ctrl+Space: send key_intercepted event to runtime via IPC.
 * Requirement 4.1
 */
static void handle_ctrl_space(struct CiosServer *server) {
    LOG_INFO("hotkey: Ctrl+Space → key_intercepted");
    ipc_send_event(server->ipc, "key_intercepted", "\"key\":\"ctrl+space\"");
}

/**
 * Super lone press: focus the runtime main surface.
 * Requirement 4.2
 */
static void handle_super_lone_press(struct CiosServer *server) {
    LOG_INFO("hotkey: Super (lone press) → focus runtime main surface");

    struct CiosSurface *runtime_surface = find_runtime_main_surface(server);
    if (runtime_surface) {
        server_focus_surface(server, runtime_surface);
    } else {
        LOG_WARN("hotkey: no runtime surface found to focus");
    }
}

/**
 * Alt+Tab: cycle focus to next surface in surfaces list.
 * Requirement 4.3
 */
static void handle_alt_tab(struct CiosServer *server) {
    LOG_INFO("hotkey: Alt+Tab → cycle focus");

    /* If surfaces list is empty, nothing to do */
    if (wl_list_empty(&server->surfaces)) {
        return;
    }

    struct CiosSurface *current = server->focused;
    struct CiosSurface *next = NULL;

    if (!current) {
        /* No current focus — focus the first surface */
        next = wl_container_of(server->surfaces.next, next, link);
    } else {
        /* Find the next surface after the currently focused one */
        if (current->link.next == &server->surfaces) {
            /* Wrap around to the first surface */
            next = wl_container_of(server->surfaces.next, next, link);
        } else {
            next = wl_container_of(current->link.next, next, link);
        }
    }

    if (next && next != current) {
        server_focus_surface(server, next);
    }
}

/**
 * Alt+F4: close focused surface, unless it belongs to the runtime process.
 * Requirement 4.4
 */
static void handle_alt_f4(struct CiosServer *server) {
    struct CiosSurface *focused = server->focused;
    if (!focused) {
        LOG_INFO("hotkey: Alt+F4 → no focused surface");
        return;
    }

    pid_t runtime_pid = get_runtime_pid(server);

    /* Skip if the focused surface belongs to the runtime process */
    if (runtime_pid > 0 && focused->pid == runtime_pid) {
        LOG_INFO("hotkey: Alt+F4 → skipping (surface belongs to runtime)");
        return;
    }

    LOG_INFO("hotkey: Alt+F4 → closing surface s_%u", focused->id);

    if (focused->xsurface) {
        wlr_xwayland_surface_close(focused->xsurface);
    }
}

/**
 * Super+Q: send logout_requested event to runtime, or exit immediately
 * if circuit breaker is active.
 * Requirement 4.5, 6.5
 */
static void handle_super_q(struct CiosServer *server) {
    LOG_INFO("hotkey: Super+Q → logout requested");

    /* If circuit breaker is active, exit immediately (Req 6.5) */
    if (process_is_circuit_breaker_active(server)) {
        LOG_INFO("hotkey: Super+Q with circuit breaker active → exiting");
        wl_display_terminate(server->display);
        return;
    }

    /* Send logout_requested event to runtime */
    ipc_send_event(server->ipc, "logout_requested", NULL);
    pending_logout = true;
}

/* ═══════════════════════════════════════════════════════════════
 *  Public API
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Check if a key event matches a hotkey and handle it.
 *
 * Called from input.c BEFORE forwarding the key to the focused surface.
 * If this function returns true, the key was consumed (don't forward).
 * If it returns false, the key should be forwarded normally.
 *
 * @param server    The compositor server
 * @param keycode   The raw keycode (evdev/linux input code)
 * @param modifiers Current modifier mask (WLR_MODIFIER_* flags)
 * @param pressed   true if key was pressed, false if released
 * @return true if the key was consumed by a hotkey, false otherwise
 */
bool hotkeys_handle_key(struct CiosServer *server, uint32_t keycode,
                        uint32_t modifiers, bool pressed) {
    /*
     * Super (lone press) detection:
     *
     * We track Super key state. If Super is pressed and released without
     * any other key being pressed in between, it's a lone press.
     * If another key is pressed while Super is held, it's a combo.
     */

    bool is_super = (keycode == KEY_LEFTMETA || keycode == KEY_RIGHTMETA);

    /* Handle Super key press/release for lone-press detection */
    if (is_super) {
        if (pressed) {
            super_pressed = true;
            super_used_in_combo = false;
            /* Consume the Super press — we'll decide on release */
            return true;
        } else {
            /* Super released */
            bool was_lone_press = super_pressed && !super_used_in_combo;
            super_pressed = false;
            super_used_in_combo = false;

            if (was_lone_press) {
                handle_super_lone_press(server);
            }
            /* Consume the Super release */
            return true;
        }
    }

    /* If Super is held and another key is pressed, mark it as used in combo */
    if (super_pressed && pressed) {
        super_used_in_combo = true;
    }

    /* Only process hotkeys on key press (not release) */
    if (!pressed) {
        return false;
    }

    /* Super+Q: logout (Super is held + Q pressed) */
    if (super_pressed && keycode == KEY_Q) {
        handle_super_q(server);
        return true;
    }

    /* Ctrl+Space */
    if ((modifiers & WLR_MODIFIER_CTRL) && keycode == KEY_SPACE) {
        handle_ctrl_space(server);
        return true;
    }

    /* Alt+Tab */
    if ((modifiers & WLR_MODIFIER_ALT) && keycode == KEY_TAB) {
        handle_alt_tab(server);
        return true;
    }

    /* Alt+F4 */
    if ((modifiers & WLR_MODIFIER_ALT) && keycode == KEY_F4) {
        handle_alt_f4(server);
        return true;
    }

    return false;
}
