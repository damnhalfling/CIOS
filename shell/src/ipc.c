/*
 * CIOS Shell — IPC (Unix socket server + JSON protocol)
 *
 * Creates a Unix socket at $XDG_RUNTIME_DIR/cios-shell.sock, accepts
 * exactly one connection (the runtime), and exchanges JSON newline-delimited
 * messages. Every message carries "v":1 and "id" fields.
 *
 * Commands: configure_surface, focus_surface, close_surface, list_surfaces, get_outputs, ready, logout
 * Events: surface_mapped, surface_unmapped, key_intercepted, focus_changed, output_added, output_removed
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
 */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/xwayland.h>

#include "log.h"
#include "server.h"

/* ═══════════════════════════════════════════════════════════════
 *  Minimal JSON helpers
 *
 *  The protocol is simple enough that we use snprintf for output
 *  and basic string searching for input parsing. No external deps.
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Extract a string value for a given key from a JSON object string.
 * Returns a malloc'd string or NULL if not found.
 * Only handles simple flat JSON objects with string values.
 */
static char *json_get_string(const char *json, const char *key) {
    /* Build search pattern: "key":" */
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\":\"", key);

    const char *start = strstr(json, pattern);
    if (!start) {
        /* Try with space after colon: "key": " */
        snprintf(pattern, sizeof(pattern), "\"%s\": \"", key);
        start = strstr(json, pattern);
        if (!start) {
            return NULL;
        }
    }

    /* Find the opening quote of the value */
    start = strchr(start + strlen(key) + 2, '"');
    if (!start) {
        return NULL;
    }
    start++; /* skip opening quote */

    /* Find closing quote (handle escaped quotes) */
    const char *end = start;
    while (*end && *end != '"') {
        if (*end == '\\') {
            end++; /* skip escaped char */
        }
        end++;
    }

    if (!*end) {
        return NULL;
    }

    size_t len = (size_t)(end - start);
    char *value = malloc(len + 1);
    if (!value) {
        return NULL;
    }
    memcpy(value, start, len);
    value[len] = '\0';
    return value;
}

/**
 * Extract an integer value for a given key from a JSON object string.
 * Returns the integer value, or default_val if not found.
 */
static int json_get_int(const char *json, const char *key, int default_val) {
    /* Build search pattern: "key": */
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);

    const char *start = strstr(json, pattern);
    if (!start) {
        return default_val;
    }

    /* Skip past the key and colon */
    start += strlen(pattern);

    /* Skip whitespace */
    while (*start == ' ' || *start == '\t') {
        start++;
    }

    /* If it's a quoted number, skip the quote */
    if (*start == '"') {
        start++;
    }

    char *endptr = NULL;
    long val = strtol(start, &endptr, 10);
    if (endptr == start) {
        return default_val;
    }
    return (int)val;
}

/**
 * Extract a boolean value for a given key from a JSON object string.
 * Returns true/false, or default_val if not found.
 */
static bool json_get_bool(const char *json, const char *key, bool default_val) {
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);

    const char *start = strstr(json, pattern);
    if (!start) {
        return default_val;
    }

    start += strlen(pattern);

    /* Skip whitespace */
    while (*start == ' ' || *start == '\t') {
        start++;
    }

    if (strncmp(start, "true", 4) == 0) {
        return true;
    }
    if (strncmp(start, "false", 5) == 0) {
        return false;
    }
    return default_val;
}

/* ═══════════════════════════════════════════════════════════════
 *  Helper: find surface by string ID ("s_N" format)
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Find a CiosSurface by its string ID (e.g., "s_14").
 * Parses the numeric part after "s_" and searches the surfaces list.
 * Returns NULL if the ID is malformed or no matching surface is found.
 */
static struct CiosSurface *find_surface_by_id(struct CiosServer *server, const char *surface_id_str) {
    if (!surface_id_str || !server) {
        return NULL;
    }

    /* Parse "s_N" format */
    if (surface_id_str[0] != 's' || surface_id_str[1] != '_') {
        return NULL;
    }

    char *endptr = NULL;
    unsigned long parsed_id = strtoul(surface_id_str + 2, &endptr, 10);
    if (endptr == surface_id_str + 2 || *endptr != '\0') {
        return NULL;
    }

    uint32_t target_id = (uint32_t)parsed_id;

    /* Search the surfaces list */
    struct CiosSurface *surface;
    wl_list_for_each(surface, &server->surfaces, link) {
        if (surface->id == target_id) {
            return surface;
        }
    }

    return NULL;
}

/**
 * Resolve a layer name string to the corresponding scene tree.
 * Valid names: "bg", "bottom", "normal", "top", "overlay".
 * Returns NULL if the name is not recognized.
 */
static struct wlr_scene_tree *resolve_layer(struct CiosServer *server, const char *layer_name) {
    if (!layer_name || !server) {
        return NULL;
    }

    if (strcmp(layer_name, "bg") == 0) {
        return server->layer_bg;
    } else if (strcmp(layer_name, "bottom") == 0) {
        return server->layer_bottom;
    } else if (strcmp(layer_name, "normal") == 0) {
        return server->layer_normal;
    } else if (strcmp(layer_name, "top") == 0) {
        return server->layer_top;
    } else if (strcmp(layer_name, "overlay") == 0) {
        return server->layer_overlay;
    }

    return NULL;
}

/**
 * Find an output by its name (connector name, e.g., "HDMI-1").
 * The special name "primary" resolves to the current primary output.
 * Returns NULL if not found.
 */
static struct CiosOutput *find_output_by_name(struct CiosServer *server, const char *name) {
    if (!name || !server) {
        return NULL;
    }

    if (strcmp(name, "primary") == 0) {
        return server->primary_output;
    }

    struct CiosOutput *output;
    wl_list_for_each(output, &server->outputs, link) {
        if (output->wlr_output && output->wlr_output->name &&
            strcmp(output->wlr_output->name, name) == 0) {
            return output;
        }
    }

    return NULL;
}

/* ═══════════════════════════════════════════════════════════════
 *  Command handlers (tasks 8.1-8.5)
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Handle configure_surface command (Req 3.1, 3.2, 3.3, 3.4, 8.4).
 *
 * Applies geometry (x, y, w, h), layer, visibility, and output placement
 * to the specified surface. Cancels the 500ms map_timer if still pending.
 */
static void handle_configure_surface(struct CiosIpc *ipc, const char *json, const char *id) {
    struct CiosServer *server = ipc->server;

    /* Extract surface_id from JSON */
    char *surface_id_str = json_get_string(json, "surface_id");
    if (!surface_id_str) {
        LOG_WARN("ipc: configure_surface missing surface_id, id=%s", id);
        ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"surface not found\"}");
        return;
    }

    /* Find the surface */
    struct CiosSurface *surface = find_surface_by_id(server, surface_id_str);
    free(surface_id_str);

    if (!surface) {
        LOG_WARN("ipc: configure_surface: surface not found, id=%s", id);
        ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"surface not found\"}");
        return;
    }

    /* Cancel the 500ms map_timer if still pending (runtime responded) */
    if (surface->map_timer) {
        wl_event_source_remove(surface->map_timer);
        surface->map_timer = NULL;
    }

    /* Determine base position offset (for output field) */
    int output_offset_x = 0;
    int output_offset_y = 0;
    struct CiosOutput *target_output = NULL;

    char *output_name = json_get_string(json, "output");
    if (output_name) {
        target_output = find_output_by_name(server, output_name);
        if (target_output && target_output->wlr_output) {
            /* Get the output's position in the output layout */
            struct wlr_output_layout_output *lo =
                wlr_output_layout_get(server->output_layout, target_output->wlr_output);
            if (lo) {
                output_offset_x = lo->x;
                output_offset_y = lo->y;
            }
        }
        free(output_name);
    }

    /* Apply geometry (x, y, w, h) */
    int x = json_get_int(json, "x", -1);
    int y = json_get_int(json, "y", -1);
    int w = json_get_int(json, "w", -1);
    int h = json_get_int(json, "h", -1);

    /* Constrain surfaces to usable_area of target output (Req 5.4, 8.4) */
    if (target_output && x >= 0 && y >= 0) {
        /* Clamp position to usable area bounds */
        if (x < target_output->usable_x) {
            x = target_output->usable_x;
        }
        if (y < target_output->usable_y) {
            y = target_output->usable_y;
        }
        /* Clamp size so surface doesn't extend beyond usable area */
        if (w > 0 && x + w > target_output->usable_x + target_output->usable_width) {
            w = target_output->usable_x + target_output->usable_width - x;
            if (w < 1) w = 1;
        }
        if (h > 0 && y + h > target_output->usable_y + target_output->usable_height) {
            h = target_output->usable_y + target_output->usable_height - y;
            if (h < 1) h = 1;
        }
    }

    if (x >= 0 && y >= 0 && surface->scene_tree) {
        wlr_scene_node_set_position(&surface->scene_tree->node,
            output_offset_x + x, output_offset_y + y);
    }

    if (w > 0 && h > 0 && surface->xsurface) {
        int final_x = (x >= 0) ? output_offset_x + x : surface->xsurface->x;
        int final_y = (y >= 0) ? output_offset_y + y : surface->xsurface->y;
        wlr_xwayland_surface_configure(surface->xsurface,
            final_x, final_y, (uint16_t)w, (uint16_t)h);
    }

    /* Handle layer field: reparent scene_tree node to target layer */
    char *layer_name = json_get_string(json, "layer");
    if (layer_name) {
        struct wlr_scene_tree *target_layer = resolve_layer(server, layer_name);
        if (target_layer && surface->scene_tree) {
            wlr_scene_node_reparent(&surface->scene_tree->node, target_layer);
            surface->layer = target_layer;
        }
        free(layer_name);
    }

    /* Handle visible field: show/hide scene node */
    /* Check if "visible" key exists in the JSON before applying */
    char pattern_visible[64];
    snprintf(pattern_visible, sizeof(pattern_visible), "\"visible\":");
    if (strstr(json, pattern_visible)) {
        bool visible = json_get_bool(json, "visible", true);
        if (surface->scene_tree) {
            wlr_scene_node_set_enabled(&surface->scene_tree->node, visible);
        }
        surface->visible = visible;
    }

    LOG_INFO("ipc: configure_surface s_%u id=%s", surface->id, id);
    ipc_send_response(ipc, id, "{\"response\":\"ok\"}");
}

static void handle_focus_surface(struct CiosIpc *ipc, const char *json, const char *id) {
    struct CiosServer *server = ipc->server;

    /* Extract surface_id from JSON */
    char *surface_id_str = json_get_string(json, "surface_id");
    if (!surface_id_str) {
        LOG_WARN("ipc: focus_surface missing surface_id, id=%s", id);
        ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"missing surface_id\"}");
        return;
    }

    struct CiosSurface *surface = NULL;

    /* Handle special "runtime" surface_id: focus the runtime's main surface */
    if (strcmp(surface_id_str, "runtime") == 0) {
        /* Find the first surface whose pid matches the runtime process pid */
        if (server->proc_runtime && server->proc_runtime->pid > 0) {
            pid_t runtime_pid = server->proc_runtime->pid;
            struct CiosSurface *s;
            wl_list_for_each(s, &server->surfaces, link) {
                if (s->pid == runtime_pid) {
                    surface = s;
                    break;
                }
            }
        }
        if (!surface) {
            LOG_WARN("ipc: focus_surface: runtime surface not found, id=%s", id);
            free(surface_id_str);
            ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"surface not found\"}");
            return;
        }
    } else {
        /* Normal surface_id lookup */
        surface = find_surface_by_id(server, surface_id_str);
        if (!surface) {
            LOG_WARN("ipc: focus_surface: surface not found '%s', id=%s", surface_id_str, id);
            free(surface_id_str);
            ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"surface not found\"}");
            return;
        }
    }

    free(surface_id_str);

    /* Give keyboard focus to the surface */
    server_focus_surface(server, surface);

    LOG_INFO("ipc: focus_surface s_%u id=%s", surface->id, id);
    ipc_send_response(ipc, id, "{\"response\":\"ok\"}");
}

static void handle_close_surface(struct CiosIpc *ipc, const char *json, const char *id) {
    struct CiosServer *server = ipc->server;

    /* Extract surface_id from JSON */
    char *surface_id_str = json_get_string(json, "surface_id");
    if (!surface_id_str) {
        LOG_WARN("ipc: close_surface missing surface_id, id=%s", id);
        ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"missing surface_id\"}");
        return;
    }

    /* Find the surface */
    struct CiosSurface *surface = find_surface_by_id(server, surface_id_str);
    if (!surface) {
        LOG_WARN("ipc: close_surface: surface not found '%s', id=%s", surface_id_str, id);
        free(surface_id_str);
        ipc_send_response(ipc, id, "{\"response\":\"error\",\"reason\":\"surface not found\"}");
        return;
    }

    free(surface_id_str);

    /* Send close request to the XWayland surface */
    if (surface->xsurface) {
        wlr_xwayland_surface_close(surface->xsurface);
    }

    LOG_INFO("ipc: close_surface s_%u id=%s", surface->id, id);
    ipc_send_response(ipc, id, "{\"response\":\"ok\"}");
}

static void handle_list_surfaces(struct CiosIpc *ipc, const char *json, const char *id) {
    (void)json;
    struct CiosServer *server = ipc->server;

    /*
     * Build JSON response: {"response":"surfaces","surfaces":[...]}
     * Each entry: {"surface_id":"s_N","wm_class":"...","title":"...","pid":N,"output":"...","x":N,"y":N,"w":N,"h":N}
     */
    char buf[CIOS_IPC_BUFFER_SIZE];
    int offset = 0;

    offset += snprintf(buf + offset, sizeof(buf) - (size_t)offset,
                       "{\"response\":\"surfaces\",\"surfaces\":[");

    bool first = true;
    struct CiosSurface *surface;
    wl_list_for_each(surface, &server->surfaces, link) {
        if (!surface->xsurface) {
            continue;
        }

        /* Determine which output this surface is on */
        const char *output_name = "unknown";
        int sx = 0, sy = 0, sw = 0, sh = 0;

        if (surface->xsurface) {
            sx = surface->xsurface->x;
            sy = surface->xsurface->y;
            sw = surface->xsurface->width;
            sh = surface->xsurface->height;
        }

        /* Find the output containing this surface based on its position */
        struct CiosOutput *output;
        wl_list_for_each(output, &server->outputs, link) {
            if (!output->wlr_output) {
                continue;
            }
            struct wlr_output_layout_output *lo =
                wlr_output_layout_get(server->output_layout, output->wlr_output);
            if (!lo) {
                continue;
            }
            /* Check if surface position falls within this output's bounds */
            int ox = lo->x;
            int oy = lo->y;
            int ow = output->wlr_output->width;
            int oh = output->wlr_output->height;
            if (sx >= ox && sx < ox + ow && sy >= oy && sy < oy + oh) {
                output_name = output->wlr_output->name ? output->wlr_output->name : "unknown";
                break;
            }
        }

        const char *wm_class = surface->xsurface->class ? surface->xsurface->class : "";
        const char *title = surface->xsurface->title ? surface->xsurface->title : "";
        pid_t pid = surface->pid;

        if (!first) {
            offset += snprintf(buf + offset, sizeof(buf) - (size_t)offset, ",");
        }
        first = false;

        offset += snprintf(buf + offset, sizeof(buf) - (size_t)offset,
            "{\"surface_id\":\"s_%u\",\"wm_class\":\"%s\",\"title\":\"%s\","
            "\"pid\":%d,\"output\":\"%s\",\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d}",
            surface->id, wm_class, title, (int)pid, output_name, sx, sy, sw, sh);

        /* Safety: don't overflow buffer */
        if ((size_t)offset >= sizeof(buf) - 128) {
            LOG_WARN("ipc: list_surfaces response truncated");
            break;
        }
    }

    snprintf(buf + offset, sizeof(buf) - (size_t)offset, "]}");

    LOG_INFO("ipc: list_surfaces id=%s", id);
    ipc_send_response(ipc, id, buf);
}

static void handle_get_outputs(struct CiosIpc *ipc, const char *json, const char *id) {
    (void)json;
    struct CiosServer *server = ipc->server;

    /*
     * Build JSON response: {"response":"outputs","outputs":[...]}
     * Each entry: {"name":"...","width":N,"height":N,"x":N,"y":N,"primary":bool,
     *              "usable_x":N,"usable_y":N,"usable_width":N,"usable_height":N}
     */
    char buf[CIOS_IPC_BUFFER_SIZE];
    int offset = 0;

    offset += snprintf(buf + offset, sizeof(buf) - (size_t)offset,
                       "{\"response\":\"outputs\",\"outputs\":[");

    bool first = true;
    struct CiosOutput *output;
    wl_list_for_each(output, &server->outputs, link) {
        if (!output->wlr_output) {
            continue;
        }

        int ox = 0, oy = 0;
        struct wlr_output_layout_output *lo =
            wlr_output_layout_get(server->output_layout, output->wlr_output);
        if (lo) {
            ox = lo->x;
            oy = lo->y;
        }

        const char *name = output->wlr_output->name ? output->wlr_output->name : "unknown";
        int width = output->wlr_output->width;
        int height = output->wlr_output->height;

        if (!first) {
            offset += snprintf(buf + offset, sizeof(buf) - (size_t)offset, ",");
        }
        first = false;

        offset += snprintf(buf + offset, sizeof(buf) - (size_t)offset,
            "{\"name\":\"%s\",\"width\":%d,\"height\":%d,\"x\":%d,\"y\":%d,"
            "\"primary\":%s,\"usable_x\":%d,\"usable_y\":%d,"
            "\"usable_width\":%d,\"usable_height\":%d}",
            name, width, height, ox, oy,
            output->is_primary ? "true" : "false",
            output->usable_x, output->usable_y,
            output->usable_width, output->usable_height);

        if ((size_t)offset >= sizeof(buf) - 128) {
            LOG_WARN("ipc: get_outputs response truncated");
            break;
        }
    }

    snprintf(buf + offset, sizeof(buf) - (size_t)offset, "]}");

    LOG_INFO("ipc: get_outputs id=%s", id);
    ipc_send_response(ipc, id, buf);
}

static void handle_ready(struct CiosIpc *ipc, const char *json, const char *id) {
    (void)json;
    LOG_INFO("ipc: ready command received id=%s", id);
    ipc->connected = true;

    /* Trigger splash fade — reveals surfaces after 200ms (Req 7.3) */
    if (ipc->server->splash_active) {
        server_begin_splash_fade(ipc->server);
    }

    ipc_send_response(ipc, id, "{\"response\":\"ok\"}");
}

static void handle_logout(struct CiosIpc *ipc, const char *json, const char *id) {
    (void)json;
    LOG_INFO("ipc: logout command received id=%s", id);

    /* Send ok response before terminating */
    ipc_send_response(ipc, id, "{\"response\":\"ok\"}");

    /* Mark clean exit so process manager knows not to restart (Req 12.2) */
    if (ipc->server->proc_runtime) {
        ipc->server->proc_runtime->should_restart = false;
    }

    /* Terminate the compositor event loop — returns control to display manager */
    wl_display_terminate(ipc->server->display);
}

/* ═══════════════════════════════════════════════════════════════
 *  Message routing
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Route a parsed JSON command to the appropriate handler.
 */
static void ipc_route_command(struct CiosIpc *ipc, const char *json) {
    char *id = json_get_string(json, "id");
    char *command = json_get_string(json, "command");

    if (!id) {
        LOG_WARN("ipc: received message without id field");
        free(command);
        return;
    }

    if (!command) {
        LOG_WARN("ipc: received message without command field, id=%s", id);
        /* Send error response with correlation ID */
        char buf[256];
        snprintf(buf, sizeof(buf),
                 "{\"v\":1,\"id\":\"%s\",\"response\":\"error\",\"reason\":\"missing command field\"}\n",
                 id);
        if (ipc->client_fd >= 0) {
            write(ipc->client_fd, buf, strlen(buf));
        }
        free(id);
        return;
    }

    /* Route to handler */
    if (strcmp(command, "configure_surface") == 0) {
        handle_configure_surface(ipc, json, id);
    } else if (strcmp(command, "focus_surface") == 0) {
        handle_focus_surface(ipc, json, id);
    } else if (strcmp(command, "close_surface") == 0) {
        handle_close_surface(ipc, json, id);
    } else if (strcmp(command, "list_surfaces") == 0) {
        handle_list_surfaces(ipc, json, id);
    } else if (strcmp(command, "get_outputs") == 0) {
        handle_get_outputs(ipc, json, id);
    } else if (strcmp(command, "ready") == 0) {
        handle_ready(ipc, json, id);
    } else if (strcmp(command, "logout") == 0) {
        handle_logout(ipc, json, id);
    } else {
        /* Unknown command — respond with error + reason (Req 1.7) */
        LOG_WARN("ipc: unknown command '%s' id=%s", command, id);
        char buf[512];
        snprintf(buf, sizeof(buf),
                 "{\"v\":1,\"id\":\"%s\",\"response\":\"error\",\"reason\":\"unknown command: %s\"}\n",
                 id, command);
        if (ipc->client_fd >= 0) {
            write(ipc->client_fd, buf, strlen(buf));
        }
    }

    free(id);
    free(command);
}

/* ═══════════════════════════════════════════════════════════════
 *  Client fd read handler
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Process buffered data: extract complete newline-delimited JSON messages.
 */
static void ipc_process_buffer(struct CiosIpc *ipc) {
    while (ipc->read_len > 0) {
        /* Find newline delimiter */
        char *newline = memchr(ipc->read_buffer, '\n', ipc->read_len);
        if (!newline) {
            break; /* No complete message yet */
        }

        /* Null-terminate the message */
        *newline = '\0';
        size_t msg_len = (size_t)(newline - ipc->read_buffer);

        /* Skip empty lines */
        if (msg_len > 0) {
            ipc_route_command(ipc, ipc->read_buffer);
        }

        /* Shift remaining data to front of buffer */
        size_t consumed = msg_len + 1; /* +1 for the newline */
        size_t remaining = ipc->read_len - consumed;
        if (remaining > 0) {
            memmove(ipc->read_buffer, newline + 1, remaining);
        }
        ipc->read_len = remaining;
    }
}

/**
 * wl_event_loop fd callback: read data from the connected client.
 */
static int ipc_client_readable(int fd, uint32_t mask, void *data) {
    struct CiosIpc *ipc = data;

    if (mask & (WL_EVENT_HANGUP | WL_EVENT_ERROR)) {
        LOG_WARN("ipc: client disconnected");
        if (ipc->client_source) {
            wl_event_source_remove(ipc->client_source);
            ipc->client_source = NULL;
        }
        close(ipc->client_fd);
        ipc->client_fd = -1;
        ipc->connected = false;
        ipc->read_len = 0;
        return 0;
    }

    if (!(mask & WL_EVENT_READABLE)) {
        return 0;
    }

    /* Read into buffer */
    size_t space = CIOS_IPC_BUFFER_SIZE - ipc->read_len - 1;
    if (space == 0) {
        LOG_WARN("ipc: read buffer full, discarding");
        ipc->read_len = 0;
        space = CIOS_IPC_BUFFER_SIZE - 1;
    }

    ssize_t n = read(fd, ipc->read_buffer + ipc->read_len, space);
    if (n <= 0) {
        if (n == 0) {
            LOG_WARN("ipc: client closed connection");
        } else if (errno != EAGAIN && errno != EWOULDBLOCK) {
            LOG_ERROR("ipc: read error: %s", strerror(errno));
        }
        if (ipc->client_source) {
            wl_event_source_remove(ipc->client_source);
            ipc->client_source = NULL;
        }
        close(ipc->client_fd);
        ipc->client_fd = -1;
        ipc->connected = false;
        ipc->read_len = 0;
        return 0;
    }

    ipc->read_len += (size_t)n;
    ipc->read_buffer[ipc->read_len] = '\0';

    /* Process complete messages */
    ipc_process_buffer(ipc);

    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 *  Socket accept handler
 * ═══════════════════════════════════════════════════════════════ */

/**
 * wl_event_loop fd callback: accept incoming connection on the listening socket.
 * Only one connection is accepted (Req 1.2). Subsequent connections are rejected.
 */
static int ipc_socket_readable(int fd, uint32_t mask, void *data) {
    struct CiosIpc *ipc = data;

    if (!(mask & WL_EVENT_READABLE)) {
        return 0;
    }

    int client_fd = accept(fd, NULL, NULL);
    if (client_fd < 0) {
        LOG_ERROR("ipc: accept() failed: %s", strerror(errno));
        return 0;
    }

    /* Reject if we already have a connected client (Req 1.2) */
    if (ipc->client_fd >= 0) {
        LOG_WARN("ipc: rejecting additional connection (only one allowed)");
        close(client_fd);
        return 0;
    }

    LOG_INFO("ipc: runtime connected (fd=%d)", client_fd);
    ipc->client_fd = client_fd;
    ipc->connected = true;
    ipc->read_len = 0;

    /* Register the client fd for reading via the event loop */
    struct wl_event_loop *loop = wl_display_get_event_loop(ipc->server->display);
    ipc->client_source = wl_event_loop_add_fd(loop, client_fd,
                                               WL_EVENT_READABLE,
                                               ipc_client_readable, ipc);
    if (!ipc->client_source) {
        LOG_ERROR("ipc: failed to add client fd to event loop");
        close(client_fd);
        ipc->client_fd = -1;
        ipc->connected = false;
        return 0;
    }

    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 *  Connection timeout (10 seconds)
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Timer callback: fires if the runtime hasn't connected within 10 seconds.
 * Logs a warning per Req 1.8.
 */
static int ipc_connection_timeout(void *data) {
    struct CiosIpc *ipc = data;

    if (!ipc->connected) {
        LOG_WARN("ipc: runtime has not connected within 10 seconds");
    }

    /* Timer is one-shot; source will be cleaned up by caller or destroy */
    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 *  Public API
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Initialize the IPC subsystem: create the Unix socket and start listening.
 *
 * @param ipc    Pointer to an allocated CiosIpc struct
 * @param server The compositor server
 * @return true on success, false on failure
 */
bool ipc_init(struct CiosIpc *ipc, struct CiosServer *server) {
    memset(ipc, 0, sizeof(*ipc));
    ipc->server = server;
    ipc->socket_fd = -1;
    ipc->client_fd = -1;
    ipc->socket_source = NULL;
    ipc->client_source = NULL;
    ipc->read_len = 0;
    ipc->next_event_id = 1;
    ipc->connected = false;

    /* Determine socket path (Req 1.1) */
    const char *runtime_dir = getenv("XDG_RUNTIME_DIR");
    if (!runtime_dir) {
        LOG_ERROR("ipc: XDG_RUNTIME_DIR not set");
        return false;
    }

    char socket_path[256];
    snprintf(socket_path, sizeof(socket_path), "%s/cios-shell.sock", runtime_dir);

    /* Remove stale socket file if it exists */
    unlink(socket_path);

    /* Create the Unix socket */
    ipc->socket_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (ipc->socket_fd < 0) {
        LOG_ERROR("ipc: socket() failed: %s", strerror(errno));
        return false;
    }

    /* Bind to the socket path */
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);

    if (bind(ipc->socket_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        LOG_ERROR("ipc: bind(%s) failed: %s", socket_path, strerror(errno));
        close(ipc->socket_fd);
        ipc->socket_fd = -1;
        return false;
    }

    /* Listen for connections (backlog=1, we only accept one) */
    if (listen(ipc->socket_fd, 1) < 0) {
        LOG_ERROR("ipc: listen() failed: %s", strerror(errno));
        close(ipc->socket_fd);
        ipc->socket_fd = -1;
        unlink(socket_path);
        return false;
    }

    LOG_INFO("ipc: listening on %s", socket_path);

    /* Register the listening socket with the Wayland event loop */
    struct wl_event_loop *loop = wl_display_get_event_loop(server->display);
    ipc->socket_source = wl_event_loop_add_fd(loop, ipc->socket_fd,
                                               WL_EVENT_READABLE,
                                               ipc_socket_readable, ipc);
    if (!ipc->socket_source) {
        LOG_ERROR("ipc: failed to add socket fd to event loop");
        close(ipc->socket_fd);
        ipc->socket_fd = -1;
        unlink(socket_path);
        return false;
    }

    /* Set up 10-second connection timeout (Req 1.8) */
    struct wl_event_source *timer = wl_event_loop_add_timer(loop,
                                                             ipc_connection_timeout, ipc);
    if (timer) {
        wl_event_source_timer_update(timer, 10000); /* 10 seconds in ms */
    } else {
        LOG_WARN("ipc: failed to create connection timeout timer");
    }

    /* Store IPC pointer on server */
    server->ipc = ipc;

    return true;
}

/**
 * Clean up the IPC subsystem: close sockets, remove event sources.
 */
void ipc_destroy(struct CiosIpc *ipc) {
    if (!ipc) {
        return;
    }

    if (ipc->client_source) {
        wl_event_source_remove(ipc->client_source);
        ipc->client_source = NULL;
    }

    if (ipc->client_fd >= 0) {
        close(ipc->client_fd);
        ipc->client_fd = -1;
    }

    if (ipc->socket_source) {
        wl_event_source_remove(ipc->socket_source);
        ipc->socket_source = NULL;
    }

    if (ipc->socket_fd >= 0) {
        /* Remove the socket file */
        const char *runtime_dir = getenv("XDG_RUNTIME_DIR");
        if (runtime_dir) {
            char socket_path[256];
            snprintf(socket_path, sizeof(socket_path), "%s/cios-shell.sock", runtime_dir);
            unlink(socket_path);
        }
        close(ipc->socket_fd);
        ipc->socket_fd = -1;
    }

    ipc->connected = false;
    LOG_INFO("ipc: destroyed");
}

/**
 * Send an event to the connected runtime client.
 * Formats a JSON message with "v":1, auto-generated "id", and the event payload.
 *
 * @param ipc        The IPC subsystem
 * @param event_type The event name (e.g., "surface_mapped", "key_intercepted")
 * @param payload    Additional JSON fields to include (without outer braces),
 *                   or NULL for events with no extra data
 */
void ipc_send_event(struct CiosIpc *ipc, const char *event_type, const char *payload) {
    if (!ipc || ipc->client_fd < 0) {
        return;
    }

    char buf[CIOS_IPC_BUFFER_SIZE];
    char id_str[32];
    snprintf(id_str, sizeof(id_str), "e%u", ipc->next_event_id++);

    if (payload && payload[0] != '\0') {
        snprintf(buf, sizeof(buf),
                 "{\"v\":1,\"id\":\"%s\",\"event\":\"%s\",%s}\n",
                 id_str, event_type, payload);
    } else {
        snprintf(buf, sizeof(buf),
                 "{\"v\":1,\"id\":\"%s\",\"event\":\"%s\"}\n",
                 id_str, event_type);
    }

    ssize_t written = write(ipc->client_fd, buf, strlen(buf));
    if (written < 0) {
        LOG_ERROR("ipc: failed to send event '%s': %s", event_type, strerror(errno));
    }
}

/**
 * Send a response to the connected runtime client with a correlation ID.
 * The response string should be the JSON body fields (without outer braces).
 *
 * @param ipc      The IPC subsystem
 * @param id       The correlation ID from the original request
 * @param response The response body (e.g., "{\"response\":\"ok\"}")
 */
void ipc_send_response(struct CiosIpc *ipc, const char *id, const char *response) {
    if (!ipc || ipc->client_fd < 0) {
        return;
    }

    char buf[CIOS_IPC_BUFFER_SIZE];

    /*
     * The response parameter contains the inner JSON fields.
     * We wrap it with v:1 and the correlation id.
     * If response already starts with '{', we merge the fields.
     */
    if (response && response[0] == '{') {
        /* response is like {"response":"ok"} — merge with v and id */
        /* Skip the opening brace of response */
        snprintf(buf, sizeof(buf),
                 "{\"v\":1,\"id\":\"%s\",%s\n",
                 id, response + 1);
        /* The response already has a closing brace, just add newline */
        /* But we need to ensure it ends with }\n */
        size_t len = strlen(buf);
        if (len > 0 && buf[len - 1] == '\n' && len > 1 && buf[len - 2] == '}') {
            /* Already correct: ...}\n */
        } else if (len > 0 && buf[len - 1] == '}') {
            buf[len] = '\n';
            buf[len + 1] = '\0';
        }
    } else {
        /* Plain response string */
        snprintf(buf, sizeof(buf),
                 "{\"v\":1,\"id\":\"%s\",\"response\":\"%s\"}\n",
                 id, response ? response : "ok");
    }

    ssize_t written = write(ipc->client_fd, buf, strlen(buf));
    if (written < 0) {
        LOG_ERROR("ipc: failed to send response id=%s: %s", id, strerror(errno));
    }
}
