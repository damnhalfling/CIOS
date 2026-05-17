/*
 * CIOS Shell — Wayland compositor entry point
 *
 * Parses command-line arguments, initializes the Wayland display,
 * runs the compositor event loop, and cleans up on exit.
 *
 * Requirements: 12.1 (seat via logind/seatd), 7.1 (fast startup)
 */

#define _POSIX_C_SOURCE 200809L

#include <getopt.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <wayland-server-core.h>
#include <wlr/util/log.h>

#include "log.h"
#include "server.h"

#define CIOS_SHELL_VERSION "0.1.0"
#define DEFAULT_RUNTIME_CMD "cios"

/* Global display pointer for SIGTERM handler */
static struct wl_display *g_display = NULL;

/**
 * SIGTERM handler: initiate clean shutdown by terminating the event loop.
 * Same shutdown path as the "logout" IPC command (Req 12.2).
 */
static void handle_sigterm(int sig) {
    (void)sig;
    if (g_display) {
        wl_display_terminate(g_display);
    }
}

static void print_usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s [options]\n"
        "\n"
        "Options:\n"
        "  -l, --log-level <level>   Set log level: quiet, error, info, debug (default: info)\n"
        "  -r, --runtime <command>   Override runtime command (default: " DEFAULT_RUNTIME_CMD ")\n"
        "  -v, --version             Print version and exit\n"
        "  -h, --help                Print this help and exit\n",
        prog);
}

static enum wlr_log_importance parse_log_level(const char *level) {
    if (strcmp(level, "quiet") == 0 || strcmp(level, "none") == 0) {
        return WLR_SILENT;
    } else if (strcmp(level, "error") == 0) {
        return WLR_ERROR;
    } else if (strcmp(level, "info") == 0) {
        return WLR_INFO;
    } else if (strcmp(level, "debug") == 0) {
        return WLR_DEBUG;
    }
    fprintf(stderr, "Unknown log level '%s', using 'info'\n", level);
    return WLR_INFO;
}

int main(int argc, char *argv[]) {
    enum wlr_log_importance log_level = WLR_INFO;
    const char *runtime_cmd = DEFAULT_RUNTIME_CMD;

    /* Parse command-line arguments */
    static const struct option long_options[] = {
        {"log-level", required_argument, NULL, 'l'},
        {"runtime",   required_argument, NULL, 'r'},
        {"version",   no_argument,       NULL, 'v'},
        {"help",      no_argument,       NULL, 'h'},
        {NULL,        0,                 NULL,  0 },
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "l:r:vh", long_options, NULL)) != -1) {
        switch (opt) {
        case 'l':
            log_level = parse_log_level(optarg);
            break;
        case 'r':
            runtime_cmd = optarg;
            break;
        case 'v':
            printf("cios-shell %s\n", CIOS_SHELL_VERSION);
            return 0;
        case 'h':
            print_usage(argv[0]);
            return 0;
        default:
            print_usage(argv[0]);
            return 1;
        }
    }

    /* Initialize wlroots logging */
    wlr_log_init(log_level, NULL);

    LOG_INFO("cios-shell %s starting", CIOS_SHELL_VERSION);
    LOG_INFO("runtime command: %s", runtime_cmd);

    /* Create Wayland display — the core server object */
    struct wl_display *display = wl_display_create();
    if (!display) {
        LOG_ERROR("failed to create wl_display");
        return 1;
    }

    /* Set up SIGTERM handler for clean session termination (Req 12.2) */
    g_display = display;
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handle_sigterm;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);

    /* Initialize the compositor server */
    struct CiosServer server = {0};
    server.display = display;
    server.runtime_cmd = runtime_cmd;

    if (!server_init(&server)) {
        LOG_ERROR("failed to initialize server");
        wl_display_destroy(display);
        return 1;
    }

    LOG_INFO("server initialized, entering event loop");

    /* Run the event loop (blocks until shutdown) */
    server_run(&server);

    /* Clean shutdown */
    LOG_INFO("shutting down");
    server_destroy(&server);
    wl_display_destroy(display);

    LOG_INFO("cios-shell exited cleanly");
    return 0;
}
