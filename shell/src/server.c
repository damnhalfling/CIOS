/*
 * CIOS Shell — Server initialization, event loop, and cleanup
 *
 * Creates the wlroots backend, renderer, allocator, scene graph with
 * five layers (BG, BOTTOM, NORMAL, TOP, OVERLAY), output layout,
 * seat with keyboard+pointer capabilities, and manages the display socket.
 *
 * Requirements: 10.1 (scene layers), 10.2 (BG color), 7.1 (fast startup), 12.1 (seat)
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>

#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/xwayland.h>

#include "log.h"
#include "server.h"

/* BG color: #0a0a0f — very dark blue-black (sRGB float) */
static const float bg_color[4] = {
    0.0392f,  /* 0x0a / 255 */
    0.0392f,  /* 0x0a / 255 */
    0.0588f,  /* 0x0f / 255 */
    1.0f,
};

bool server_init(struct CiosServer *server) {
    struct wl_display *display = server->display;

    /* Initialize lists */
    wl_list_init(&server->outputs);
    wl_list_init(&server->surfaces);
    server->focused = NULL;
    server->next_surface_id = 1;

    /*
     * Create the backend — auto-detects DRM/KMS on real hardware,
     * or uses headless/wayland/x11 when WLR_BACKENDS is set.
     */
    server->backend = wlr_backend_autocreate(wl_display_get_event_loop(display), NULL);
    if (!server->backend) {
        LOG_ERROR("failed to create wlr_backend");
        return false;
    }

    /* Create the renderer (OpenGL/Vulkan, auto-detected) */
    server->renderer = wlr_renderer_autocreate(server->backend);
    if (!server->renderer) {
        LOG_ERROR("failed to create wlr_renderer");
        return false;
    }
    wlr_renderer_init_wl_display(server->renderer, display);

    /* Create the allocator for buffer allocation */
    server->allocator = wlr_allocator_autocreate(server->backend, server->renderer);
    if (!server->allocator) {
        LOG_ERROR("failed to create wlr_allocator");
        return false;
    }

    /* Create the compositor and subcompositor globals */
    server->compositor = wlr_compositor_create(display, 5, server->renderer);
    wlr_subcompositor_create(display);

    /* Create the data device manager (clipboard support) */
    wlr_data_device_manager_create(display);

    /*
     * Output layout — tracks the spatial arrangement of outputs.
     * The scene_output_layout bridges the scene graph to the output layout.
     */
    server->output_layout = wlr_output_layout_create(display);
    if (!server->output_layout) {
        LOG_ERROR("failed to create wlr_output_layout");
        return false;
    }

    /*
     * Scene graph — declarative rendering tree.
     * All surfaces and rects are children of scene layer trees.
     */
    server->scene = wlr_scene_create();
    if (!server->scene) {
        LOG_ERROR("failed to create wlr_scene");
        return false;
    }

    server->scene_layout = wlr_scene_attach_output_layout(server->scene,
        server->output_layout);
    if (!server->scene_layout) {
        LOG_ERROR("failed to attach scene to output layout");
        return false;
    }

    /*
     * Create five scene layer trees in ascending z-order:
     *   BG < BOTTOM < NORMAL < TOP < OVERLAY
     *
     * Each layer is a child of the scene root tree. Children added
     * later render on top of earlier siblings.
     */
    server->layer_bg = wlr_scene_tree_create(&server->scene->tree);
    server->layer_bottom = wlr_scene_tree_create(&server->scene->tree);
    server->layer_normal = wlr_scene_tree_create(&server->scene->tree);
    server->layer_top = wlr_scene_tree_create(&server->scene->tree);
    server->layer_overlay = wlr_scene_tree_create(&server->scene->tree);

    if (!server->layer_bg || !server->layer_bottom || !server->layer_normal ||
        !server->layer_top || !server->layer_overlay) {
        LOG_ERROR("failed to create scene layer trees");
        return false;
    }

    /*
     * Set the BG layer to solid color #0a0a0f.
     * We create a large rect that covers any reasonable output size.
     * It will be repositioned/resized when outputs are configured.
     */
    struct wlr_scene_rect *bg_rect = wlr_scene_rect_create(
        server->layer_bg, 8192, 8192, bg_color);
    if (!bg_rect) {
        LOG_WARN("failed to create background rect");
        /* Non-fatal: compositor can still function without BG */
    }

    /*
     * Boot splash: create an overlay rect on the OVERLAY layer that covers
     * the entire screen during boot. This hides all surfaces until the
     * runtime sends the "ready" command. The splash is the same #0a0a0f
     * color as the background — a seamless dark screen.
     *
     * Requirements: 7.2 (splash as first frame), 7.3 (fade on ready)
     */
    server->splash_active = true;
    server->splash_timer = NULL;
    server->splash_overlay = wlr_scene_rect_create(
        server->layer_overlay, 8192, 8192, bg_color);
    if (!server->splash_overlay) {
        LOG_WARN("failed to create splash overlay rect");
        server->splash_active = false;
    } else {
        LOG_INFO("splash overlay active — waiting for runtime ready");
    }

    /*
     * Create the seat — manages keyboard and pointer focus.
     * Capabilities: keyboard + pointer (no touch for now).
     */
    server->seat = wlr_seat_create(display, "seat0");
    if (!server->seat) {
        LOG_ERROR("failed to create wlr_seat");
        return false;
    }
    wlr_seat_set_capabilities(server->seat,
        WL_SEAT_CAPABILITY_KEYBOARD | WL_SEAT_CAPABILITY_POINTER);

    /*
     * Add a Wayland display socket for clients to connect.
     * wl_display_add_socket_auto picks the next available name (wayland-0, wayland-1, ...).
     */
    const char *socket = wl_display_add_socket_auto(display);
    if (!socket) {
        LOG_ERROR("failed to add wayland display socket");
        return false;
    }
    LOG_INFO("wayland socket: %s", socket);

    /* Set WAYLAND_DISPLAY for child processes */
    setenv("WAYLAND_DISPLAY", socket, 1);

    /*
     * Initialize output management — must be done before backend start
     * so we catch the initial new_output events.
     */
    output_init(server);

    /*
     * Initialize input handling — creates cursor, loads xcursor theme,
     * and registers new_input listener. Must be before backend start
     * so we catch initial input device events.
     */
    input_init(server);

    /*
     * Initialize layer shell — registers wlr-layer-shell-unstable-v1
     * protocol for surfaces with exclusive zones (topbar).
     * Must be before backend start so the global is available when
     * clients connect.
     *
     * Requirements: 5.1, 5.2, 10.4
     */
    layer_shell_init(server);

    /*
     * Start the backend — begins listening for DRM/KMS events,
     * input devices, and output hotplug.
     */
    if (!wlr_backend_start(server->backend)) {
        LOG_ERROR("failed to start backend");
        return false;
    }

    /*
     * Initialize XWayland — must be done after backend start so that
     * the compositor is ready to handle X11 client connections.
     * Sets DISPLAY env var for child processes.
     */
    xwayland_init(server);

    /*
     * Initialize IPC — create Unix socket for runtime communication.
     * Must be done before process_init so the socket is ready when
     * the runtime starts and tries to connect.
     */
    struct CiosIpc *ipc = calloc(1, sizeof(struct CiosIpc));
    if (ipc) {
        if (!ipc_init(ipc, server)) {
            LOG_WARN("failed to initialize IPC");
            free(ipc);
            /* Non-fatal: compositor can still run without IPC */
        }
    } else {
        LOG_WARN("failed to allocate CiosIpc");
    }

    /*
     * Initialize process management — spawn the runtime process.
     * Must be done after XWayland so DISPLAY is available.
     */
    if (!process_init(server)) {
        LOG_WARN("failed to spawn runtime process");
        /* Non-fatal: compositor can still run without runtime */
    }

    LOG_INFO("server initialized successfully");
    return true;
}

void server_run(struct CiosServer *server) {
    LOG_INFO("entering event loop");
    wl_display_run(server->display);
}

void server_destroy(struct CiosServer *server) {
    LOG_INFO("destroying server");

    /*
     * Destroy IPC first — close socket and client connections
     * before tearing down the compositor.
     */
    if (server->ipc) {
        ipc_destroy(server->ipc);
        free(server->ipc);
        server->ipc = NULL;
    }

    /* Remove splash timer if still pending */
    if (server->splash_timer) {
        wl_event_source_remove(server->splash_timer);
        server->splash_timer = NULL;
    }

    /*
     * Close all surfaces — send close request to each XWayland surface
     * for clean session termination (Req 12.2).
     */
    struct CiosSurface *surface, *tmp;
    wl_list_for_each_safe(surface, tmp, &server->surfaces, link) {
        if (surface->xsurface) {
            wlr_xwayland_surface_close(surface->xsurface);
        }
    }

    /*
     * Destroy XWayland — releases the X server and all associated
     * resources before tearing down the compositor (Req 12.2).
     */
    if (server->xwayland) {
        wlr_xwayland_destroy(server->xwayland);
        server->xwayland = NULL;
    }

    /*
     * Destroy process manager — terminates the runtime child
     * before we tear down the compositor infrastructure.
     */
    if (server->proc_runtime) {
        process_destroy(server->proc_runtime);
        free(server->proc_runtime);
        server->proc_runtime = NULL;
    }

    /*
     * Release the seat — relinquishes input device access
     * back to the session manager (Req 12.2).
     */
    if (server->seat) {
        /* Seat is a wl_display global; it will be fully cleaned up
         * when wl_display_destroy is called in main.c. We just
         * clear our pointer here. */
        server->seat = NULL;
    }

    /*
     * Stop the backend first — this prevents new events from
     * being dispatched while we tear down.
     */
    if (server->backend) {
        wlr_backend_destroy(server->backend);
        server->backend = NULL;
    }

    /* Destroy cursor and xcursor manager */
    if (server->cursor) {
        wlr_cursor_destroy(server->cursor);
        server->cursor = NULL;
    }
    if (server->cursor_mgr) {
        wlr_xcursor_manager_destroy(server->cursor_mgr);
        server->cursor_mgr = NULL;
    }

    /*
     * Destroy the scene graph — this cleans up all scene nodes,
     * including layer trees and their children.
     */
    if (server->scene) {
        wlr_scene_node_destroy(&server->scene->tree.node);
        server->scene = NULL;
    }

    /* Destroy the allocator */
    if (server->allocator) {
        wlr_allocator_destroy(server->allocator);
        server->allocator = NULL;
    }

    /* Destroy the renderer */
    if (server->renderer) {
        wlr_renderer_destroy(server->renderer);
        server->renderer = NULL;
    }

    /*
     * Note: wl_display is destroyed by main.c after server_destroy().
     * The output_layout is a wl_display global and will be
     * cleaned up when the display is destroyed.
     */

    LOG_INFO("server destroyed");
}

/* ═══════════════════════════════════════════════════════════════
 *  Boot splash fade logic
 *
 *  When the runtime sends "ready", we start a 200ms timer.
 *  When the timer fires, we destroy the splash overlay and
 *  reveal all surfaces that were hidden during boot.
 *
 *  Requirements: 7.3 (fade splash over 200ms, reveal surfaces)
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Timer callback: fires after 200ms to complete the splash fade.
 * Destroys the splash overlay node and marks boot as complete.
 */
static int splash_fade_timer_cb(void *data) {
    struct CiosServer *server = data;

    LOG_INFO("splash fade complete — revealing surfaces");

    /* Destroy the splash overlay node */
    if (server->splash_overlay) {
        wlr_scene_node_destroy(&server->splash_overlay->node);
        server->splash_overlay = NULL;
    }

    /* Mark boot as complete */
    server->splash_active = false;
    server->splash_timer = NULL;

    /* Reveal all surfaces that were hidden during boot */
    server_reveal_surfaces(server);

    return 0;
}

/**
 * Begin the splash fade sequence. Called when the runtime sends "ready".
 * Starts a 200ms timer; when it fires, the splash overlay is removed
 * and surfaces become visible.
 *
 * Requirements: 7.3
 */
void server_begin_splash_fade(struct CiosServer *server) {
    if (!server->splash_active) {
        LOG_WARN("splash fade requested but splash is not active");
        return;
    }

    LOG_INFO("starting splash fade (200ms)");

    struct wl_event_loop *loop = wl_display_get_event_loop(server->display);
    server->splash_timer = wl_event_loop_add_timer(loop, splash_fade_timer_cb, server);
    if (server->splash_timer) {
        wl_event_source_timer_update(server->splash_timer, 200); /* 200ms */
    } else {
        /* If timer creation fails, just remove splash immediately */
        LOG_WARN("failed to create splash fade timer, removing splash immediately");
        if (server->splash_overlay) {
            wlr_scene_node_destroy(&server->splash_overlay->node);
            server->splash_overlay = NULL;
        }
        server->splash_active = false;
        server_reveal_surfaces(server);
    }
}

/**
 * Reveal all surfaces that were hidden during the boot splash.
 * Iterates the surfaces list and enables their scene tree nodes.
 *
 * Requirements: 7.3
 */
void server_reveal_surfaces(struct CiosServer *server) {
    struct CiosSurface *surface;
    wl_list_for_each(surface, &server->surfaces, link) {
        if (surface->scene_tree) {
            wlr_scene_node_set_enabled(&surface->scene_tree->node, true);
            surface->visible = true;
        }
    }
    LOG_INFO("all surfaces revealed after splash fade");
}
