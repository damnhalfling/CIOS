/*
 * CIOS Shell — Touchpad gesture handling
 *
 * Detects multi-finger swipe and pinch gestures from libinput
 * and maps them to compositor actions.
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
#define SWIPE_THRESHOLD 50.0
#define PINCH_THRESHOLD 0.3

/* Gesture state tracking */
static struct {
    bool active;
    int fingers;
    double dx;
    double dy;
    double scale;
} gesture = {0};

/* Forward declarations */
static void gesture_action_app_switcher(struct CiosServer *server);
static void gesture_action_minimize(struct CiosServer *server);
static void gesture_action_show_all(struct CiosServer *server);

/* ═══════════════════════════════════════════════════════════════
 *  Gesture event handlers
 * ═══════════════════════════════════════════════════════════════ */

void gesture_swipe_begin(struct CiosServer *server, uint32_t fingers) {
    (void)server;
    gesture.active = true;
    gesture.fingers = fingers;
    gesture.dx = 0.0;
    gesture.dy = 0.0;
}

void gesture_swipe_update(struct CiosServer *server, double dx, double dy) {
    (void)server;
    if (!gesture.active) return;
    gesture.dx += dx;
    gesture.dy += dy;
}

void gesture_swipe_end(struct CiosServer *server) {
    if (!gesture.active) return;

    double abs_dx = fabs(gesture.dx);
    double abs_dy = fabs(gesture.dy);

    if (abs_dx < SWIPE_THRESHOLD && abs_dy < SWIPE_THRESHOLD) {
        goto cleanup;
    }

    bool horizontal = abs_dx > abs_dy;

    if (gesture.fingers == 3) {
        if (!horizontal && gesture.dy < -SWIPE_THRESHOLD) {
            LOG_INFO("gesture: 3-finger swipe up -> app switcher");
            gesture_action_app_switcher(server);
        } else if (!horizontal && gesture.dy > SWIPE_THRESHOLD) {
            LOG_INFO("gesture: 3-finger swipe down -> minimize");
            gesture_action_minimize(server);
        }
    } else if (gesture.fingers == 4) {
        if (!horizontal && gesture.dy < -SWIPE_THRESHOLD) {
            LOG_INFO("gesture: 4-finger swipe up -> show all");
            gesture_action_show_all(server);
        }
    }

cleanup:
    gesture.active = false;
    gesture.fingers = 0;
    gesture.dx = 0.0;
    gesture.dy = 0.0;
}

void gesture_pinch_begin(struct CiosServer *server, uint32_t fingers) {
    (void)server;
    gesture.active = true;
    gesture.fingers = fingers;
    gesture.scale = 1.0;
}

void gesture_pinch_update(struct CiosServer *server, double scale) {
    (void)server;
    if (!gesture.active) return;
    gesture.scale = scale;
}

void gesture_pinch_end(struct CiosServer *server) {
    (void)server;
    if (!gesture.active) return;

    double delta = gesture.scale - 1.0;
    if (fabs(delta) > PINCH_THRESHOLD) {
        if (delta > 0) {
            LOG_INFO("gesture: pinch out (zoom in placeholder)");
        } else {
            LOG_INFO("gesture: pinch in (zoom out placeholder)");
        }
    }

    gesture.active = false;
    gesture.scale = 1.0;
}

/* ═══════════════════════════════════════════════════════════════
 *  Gesture actions
 * ═══════════════════════════════════════════════════════════════ */

static void gesture_action_app_switcher(struct CiosServer *server) {
    if (server->ipc && server->ipc->connected) {
        ipc_send_event(server->ipc, "gesture", "{\"action\":\"app_switcher\"}");
    }
}

static void gesture_action_minimize(struct CiosServer *server) {
    if (server->focused) {
        decorations_minimize(server->focused);
    }
}

static void gesture_action_show_all(struct CiosServer *server) {
    if (server->ipc && server->ipc->connected) {
        ipc_send_event(server->ipc, "gesture", "{\"action\":\"show_all\"}");
    }
}
