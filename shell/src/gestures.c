/*
 * CIOS Shell — Touchpad gesture handling
 *
 * Detects multi-finger swipe and pinch gestures from libinput
 * and maps them to compositor actions:
 *
 * - 3-finger swipe up: overview / app switcher (Alt+Tab equivalent)
 * - 3-finger swipe down: minimize focused window
 * - 3-finger swipe left/right: switch workspace (future)
 * - 4-finger swipe up: show all windows
 * - Pinch in: zoom out (future accessibility)
 * - Pinch out: zoom in (future accessibility)
 *
 * Requires: libinput gesture events via wlroots.
 * Integration: called from input.c when pointer_gesture events arrive.
 *
 * #524 — Touchpad gestures no compositor
 */

#define _POSIX_C_SOURCE 200809L

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_pointer.h>

#include "log.h"
#include "server.h"

/* Gesture detection thresholds */
#define SWIPE_THRESHOLD 50.0    /* pixels to trigger a swipe */
#define PINCH_THRESHOLD 0.3     /* scale delta to trigger pinch */

/* Gesture state tracking */
struct GestureState {
    bool active;
    int fingers;
    double dx;          /* accumulated horizontal delta */
    double dy;          /* accumulated vertical delta */
    double scale;       /* accumulated pinch scale (1.0 = no change) */
};

static struct GestureState gesture = {0};

/* ═══════════════════════════════════════════════════════════════
 *  Gesture event handlers (called from input.c)
 * ═══════════════════════════════════════════════════════════════ */

void gesture_swipe_begin(struct CiosServer *server, uint32_t fingers) {
    gesture.active = true;
    gesture.fingers = fingers;
    gesture.dx = 0.0;
    gesture.dy = 0.0;
    CIOS_LOG_DEBUG("Gesture swipe begin: %d fingers", fingers);
}

void gesture_swipe_update(struct CiosServer *server, double dx, double dy) {
    if (!gesture.active) return;
    gesture.dx += dx;
    gesture.dy += dy;
}

void gesture_swipe_end(struct CiosServer *server) {
    if (!gesture.active) return;

    double abs_dx = fabs(gesture.dx);
    double abs_dy = fabs(gesture.dy);

    /* Determine dominant direction */
    if (abs_dx < SWIPE_THRESHOLD && abs_dy < SWIPE_THRESHOLD) {
        /* Too small — not a gesture */
        goto cleanup;
    }

    bool horizontal = abs_dx > abs_dy;

    if (gesture.fingers == 3) {
        if (!horizontal && gesture.dy < -SWIPE_THRESHOLD) {
            /* 3-finger swipe UP — trigger app switcher */
            CIOS_LOG_INFO("Gesture: 3-finger swipe up → app switcher");
            _gesture_trigger_app_switcher(server);
        } else if (!horizontal && gesture.dy > SWIPE_THRESHOLD) {
            /* 3-finger swipe DOWN — minimize focused */
            CIOS_LOG_INFO("Gesture: 3-finger swipe down → minimize");
            _gesture_minimize_focused(server);
        } else if (horizontal && gesture.dx < -SWIPE_THRESHOLD) {
            /* 3-finger swipe LEFT — (future: prev workspace) */
            CIOS_LOG_INFO("Gesture: 3-finger swipe left");
        } else if (horizontal && gesture.dx > SWIPE_THRESHOLD) {
            /* 3-finger swipe RIGHT — (future: next workspace) */
            CIOS_LOG_INFO("Gesture: 3-finger swipe right");
        }
    } else if (gesture.fingers == 4) {
        if (!horizontal && gesture.dy < -SWIPE_THRESHOLD) {
            /* 4-finger swipe UP — show all windows */
            CIOS_LOG_INFO("Gesture: 4-finger swipe up → show all");
            _gesture_show_all_windows(server);
        }
    }

cleanup:
    gesture.active = false;
    gesture.fingers = 0;
    gesture.dx = 0.0;
    gesture.dy = 0.0;
}

void gesture_pinch_begin(struct CiosServer *server, uint32_t fingers) {
    gesture.active = true;
    gesture.fingers = fingers;
    gesture.scale = 1.0;
    CIOS_LOG_DEBUG("Gesture pinch begin: %d fingers", fingers);
}

void gesture_pinch_update(struct CiosServer *server, double scale) {
    if (!gesture.active) return;
    gesture.scale = scale;
}

void gesture_pinch_end(struct CiosServer *server) {
    if (!gesture.active) return;

    double delta = gesture.scale - 1.0;

    if (fabs(delta) > PINCH_THRESHOLD) {
        if (delta > 0) {
            /* Pinch OUT (spread) — zoom in (future) */
            CIOS_LOG_INFO("Gesture: pinch out → zoom in");
        } else {
            /* Pinch IN (squeeze) — zoom out (future) */
            CIOS_LOG_INFO("Gesture: pinch in → zoom out");
        }
    }

    gesture.active = false;
    gesture.scale = 1.0;
}

/* ═══════════════════════════════════════════════════════════════
 *  Gesture actions
 * ═══════════════════════════════════════════════════════════════ */

static void _gesture_trigger_app_switcher(struct CiosServer *server) {
    /* Send Alt+Tab equivalent via IPC to runtime */
    if (server->ipc && server->ipc->connected) {
        ipc_send_event(server->ipc, "gesture", "{\"action\":\"app_switcher\"}");
    }
}

static void _gesture_minimize_focused(struct CiosServer *server) {
    if (server->focused) {
        decorations_minimize(server->focused);
    }
}

static void _gesture_show_all_windows(struct CiosServer *server) {
    /* Send show-all event via IPC */
    if (server->ipc && server->ipc->connected) {
        ipc_send_event(server->ipc, "gesture", "{\"action\":\"show_all\"}");
    }
}
