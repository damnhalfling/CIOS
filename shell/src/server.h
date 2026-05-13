#ifndef CIOS_SERVER_H
#define CIOS_SERVER_H

#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/xwayland.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_layer_shell_v1.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include <sys/types.h>

/* Forward declarations */
struct CiosServer;
struct CiosSurface;
struct CiosOutput;
struct CiosProcess;
struct CiosIpc;

/* ═══════════════════════════════════════════════════════════════
 *  CiosServer — Compositor core state
 * ═══════════════════════════════════════════════════════════════ */
struct CiosServer {
    struct wl_display *display;
    struct wlr_backend *backend;
    struct wlr_renderer *renderer;
    struct wlr_allocator *allocator;
    struct wlr_compositor *compositor;
    struct wlr_scene *scene;
    struct wlr_scene_output_layout *scene_layout;
    struct wlr_output_layout *output_layout;
    struct wlr_xwayland *xwayland;
    struct wlr_seat *seat;
    struct wlr_layer_shell_v1 *layer_shell;
    struct wlr_xdg_shell *xdg_shell;

    /* Scene layers (z-order: bg < bottom < normal < top < overlay) */
    struct wlr_scene_tree *layer_bg;
    struct wlr_scene_tree *layer_bottom;
    struct wlr_scene_tree *layer_normal;
    struct wlr_scene_tree *layer_top;
    struct wlr_scene_tree *layer_overlay;

    /* Cursor */
    struct wlr_cursor *cursor;
    struct wlr_xcursor_manager *cursor_mgr;

    /* State */
    struct wl_list outputs;        /* CiosOutput::link */
    struct CiosOutput *primary_output;
    struct wl_list surfaces;       /* CiosSurface::link */
    struct CiosSurface *focused;
    uint32_t next_surface_id;

    /* Runtime command (set from main.c, used by process.c) */
    const char *runtime_cmd;

    /* Boot / splash state */
    bool splash_active;                /* true until runtime sends "ready" */
    struct wlr_scene_rect *splash_overlay; /* overlay rect covering screen during boot */
    struct wl_event_source *splash_timer;  /* 200ms fade timer */

    /* Subsystems */
    struct CiosProcess *proc_runtime;
    struct CiosIpc *ipc;

    /* Listeners */
    struct wl_listener new_output;
    struct wl_listener new_xwayland_surface;
    struct wl_listener new_layer_surface;
    struct wl_listener new_xdg_toplevel;
    struct wl_listener new_input;
    struct wl_listener cursor_motion;
    struct wl_listener cursor_motion_absolute;
    struct wl_listener cursor_button;
    struct wl_listener cursor_axis;
    struct wl_listener cursor_frame;
};

/* ═══════════════════════════════════════════════════════════════
 *  CiosSurface — Managed XWayland surface
 * ═══════════════════════════════════════════════════════════════ */
struct CiosSurface {
    struct wl_list link;           /* CiosServer::surfaces */
    struct CiosServer *server;
    struct wlr_xwayland_surface *xsurface;
    struct wlr_xdg_toplevel *xdg_toplevel;
    struct wlr_scene_tree *scene_tree;
    uint32_t id;                   /* opaque surface ID (s_1, s_2, ...) */
    struct wlr_scene_tree *layer;  /* which layer tree it belongs to */
    bool visible;
    pid_t pid;

    /* 500ms timeout: if runtime doesn't configure after surface_mapped,
     * place surface in usable_area on BOTTOM layer (Req 2.4) */
    struct wl_event_source *map_timer;

    struct wl_listener map;
    struct wl_listener unmap;
    struct wl_listener destroy;
    struct wl_listener request_configure;
    struct wl_listener set_title;
};

/* ═══════════════════════════════════════════════════════════════
 *  CiosOutput — Monitor/display
 * ═══════════════════════════════════════════════════════════════ */
struct CiosOutput {
    struct wl_list link;           /* CiosServer::outputs */
    struct CiosServer *server;
    struct wlr_output *wlr_output;
    struct wlr_scene_output *scene_output;
    bool is_primary;

    /* Usable area (excludes topbar exclusive zone) */
    int usable_x;
    int usable_y;                  /* 32 (topbar height) */
    int usable_width;
    int usable_height;             /* output height - 32 */

    struct wl_listener frame;
    struct wl_listener request_state;
    struct wl_listener destroy;
};

/* ═══════════════════════════════════════════════════════════════
 *  CiosProcess — Child process manager
 * ═══════════════════════════════════════════════════════════════ */
#define CIOS_MAX_CRASHES 5
#define CIOS_CRASH_WINDOW_SECS 60

struct CiosProcess {
    struct CiosServer *server;
    pid_t pid;
    char **argv;
    int restart_count;
    time_t crash_timestamps[CIOS_MAX_CRASHES];
    bool should_restart;
    bool circuit_breaker_active;
    struct wl_event_source *sigchld_source;
};

/* ═══════════════════════════════════════════════════════════════
 *  CiosIpc — Unix socket IPC with runtime
 * ═══════════════════════════════════════════════════════════════ */
#define CIOS_IPC_BUFFER_SIZE 4096

struct CiosIpc {
    struct CiosServer *server;
    int socket_fd;
    int client_fd;
    struct wl_event_source *socket_source;
    struct wl_event_source *client_source;
    char read_buffer[CIOS_IPC_BUFFER_SIZE];
    size_t read_len;
    uint32_t next_event_id;
    bool connected;
};

/* ═══════════════════════════════════════════════════════════════
 *  Function prototypes
 * ═══════════════════════════════════════════════════════════════ */

/* server.c */
bool server_init(struct CiosServer *server);
void server_run(struct CiosServer *server);
void server_destroy(struct CiosServer *server);
void server_focus_surface(struct CiosServer *server, struct CiosSurface *surface);
void server_begin_splash_fade(struct CiosServer *server);
void server_reveal_surfaces(struct CiosServer *server);

/* output.c */
void output_init(struct CiosServer *server);
struct CiosOutput *output_get_primary(struct CiosServer *server);

/* input.c */
void input_init(struct CiosServer *server);

/* xwayland.c */
void xwayland_init(struct CiosServer *server);

/* xdg_shell.c */
void xdg_shell_init(struct CiosServer *server);
void server_focus_xdg_surface(struct CiosServer *server, struct CiosSurface *surface);

/* layer_shell.c */
void layer_shell_init(struct CiosServer *server);

/* hotkeys.c */
bool hotkeys_handle_key(struct CiosServer *server, uint32_t keycode, uint32_t modifiers, bool pressed);

/* process.c */
bool process_init(struct CiosServer *server);
bool process_spawn(struct CiosProcess *proc, struct CiosServer *server, char **argv);
void process_destroy(struct CiosProcess *proc);
void process_render_circuit_breaker_error(struct CiosServer *server);
bool process_is_circuit_breaker_active(struct CiosServer *server);

/* ipc.c */
bool ipc_init(struct CiosIpc *ipc, struct CiosServer *server);
void ipc_destroy(struct CiosIpc *ipc);
void ipc_send_event(struct CiosIpc *ipc, const char *event_type, const char *payload);
void ipc_send_response(struct CiosIpc *ipc, const char *id, const char *response);

#endif /* CIOS_SERVER_H */
