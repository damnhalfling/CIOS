/*
 * CIOS Shell — Child process management (runtime spawn + crash recovery)
 *
 * Manages the lifecycle of the runtime process:
 * - Spawns with correct environment (WAYLAND_DISPLAY, DISPLAY, CIOS_SHELL=1)
 * - Handles SIGCHLD via wl_event_loop signal source
 * - Restarts on non-zero exit with circuit breaker (5 crashes in 60s)
 * - On exit code 0: signals clean logout (wl_display_terminate)
 *
 * Requirements: 6.1, 6.2, 6.3, 6.6
 */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <wayland-server-core.h>

#include <wlr/types/wlr_scene.h>

#include "log.h"
#include "server.h"

/* ═══════════════════════════════════════════════════════════════
 *  Internal helpers
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Record a crash timestamp and check if the circuit breaker should activate.
 * Returns true if circuit breaker has tripped (5 crashes within 60s window).
 */
static bool circuit_breaker_check(struct CiosProcess *proc) {
    time_t now = time(NULL);

    /* Shift timestamps left and record the new crash */
    for (int i = 0; i < CIOS_MAX_CRASHES - 1; i++) {
        proc->crash_timestamps[i] = proc->crash_timestamps[i + 1];
    }
    proc->crash_timestamps[CIOS_MAX_CRASHES - 1] = now;
    proc->restart_count++;

    /* Circuit breaker trips if we have 5 recorded crashes and the oldest
     * is within 60 seconds of now */
    if (proc->restart_count >= CIOS_MAX_CRASHES) {
        time_t oldest = proc->crash_timestamps[0];
        if (oldest > 0 && (now - oldest) <= CIOS_CRASH_WINDOW_SECS) {
            return true;
        }
    }

    return false;
}

/**
 * Fork and exec the runtime process with the required environment variables.
 * Returns the child PID on success, -1 on failure.
 */
static pid_t do_spawn(char **argv) {
    pid_t pid = fork();

    if (pid < 0) {
        LOG_ERROR("fork() failed: %s", strerror(errno));
        return -1;
    }

    if (pid == 0) {
        /* Child process */

        /* Set environment variables for the runtime */
        /* WAYLAND_DISPLAY and DISPLAY should already be in the environment
         * (set by server.c and xwayland.c respectively), but ensure they
         * are inherited. We explicitly set CIOS_SHELL=1 to signal the
         * runtime that it's running under the shell. */
        setenv("CIOS_SHELL", "1", 1);

        /* Execute the runtime command */
        execvp(argv[0], argv);

        /* If execvp returns, it failed */
        fprintf(stderr, "execvp(%s) failed: %s\n", argv[0], strerror(errno));
        _exit(127);
    }

    /* Parent process */
    return pid;
}

/* ═══════════════════════════════════════════════════════════════
 *  SIGCHLD handler (wl_event_loop signal source callback)
 * ═══════════════════════════════════════════════════════════════ */

static int handle_sigchld(int signal_number, void *data) {
    (void)signal_number;
    struct CiosProcess *proc = data;
    int status;
    pid_t pid;

    /* Reap all terminated children (non-blocking) */
    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
        if (pid != proc->pid) {
            /* Not our managed process — ignore */
            continue;
        }

        int exit_code = -1;
        if (WIFEXITED(status)) {
            exit_code = WEXITSTATUS(status);
        } else if (WIFSIGNALED(status)) {
            exit_code = 128 + WTERMSIG(status);
        }

        LOG_INFO("runtime process (pid %d) exited with code %d", pid, exit_code);
        proc->pid = -1;

        /* Exit code 0 = clean logout → terminate the compositor */
        if (exit_code == 0) {
            LOG_INFO("runtime exited cleanly, terminating compositor");
            proc->should_restart = false;
            wl_display_terminate(proc->server->display);
            return 0;
        }

        /* Non-zero exit = crash → attempt restart with circuit breaker */
        LOG_WARN("runtime crashed (exit code %d), checking circuit breaker", exit_code);

        if (circuit_breaker_check(proc)) {
            LOG_ERROR("circuit breaker activated: %d crashes in %d seconds",
                      CIOS_MAX_CRASHES, CIOS_CRASH_WINDOW_SECS);
            proc->circuit_breaker_active = true;
            proc->should_restart = false;
            /* Render error indicator on BG layer */
            process_render_circuit_breaker_error(proc->server);
            return 0;
        }

        /* Restart the runtime */
        if (proc->should_restart) {
            LOG_INFO("restarting runtime (attempt %d)", proc->restart_count);
            pid_t new_pid = do_spawn(proc->argv);
            if (new_pid > 0) {
                proc->pid = new_pid;
                LOG_INFO("runtime restarted with pid %d", new_pid);
            } else {
                LOG_ERROR("failed to restart runtime");
                proc->circuit_breaker_active = true;
                proc->should_restart = false;
                /* Render error indicator since we can't restart */
                process_render_circuit_breaker_error(proc->server);
            }
        }
    }

    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 *  Circuit breaker error rendering
 * ═══════════════════════════════════════════════════════════════ */

/* Error indicator colors (sRGB float) */
static const float error_bg_color[4] = {
    0.8f,   /* Red */
    0.1f,   /* Green */
    0.1f,   /* Blue */
    1.0f,   /* Alpha */
};

static const float error_inner_color[4] = {
    0.15f,  /* Dark inner panel */
    0.05f,
    0.05f,
    1.0f,
};

/**
 * Render a visible error indicator on the BG layer when the circuit breaker
 * activates. Creates a large red rect with a darker inner rect to clearly
 * signal that the runtime has failed repeatedly.
 *
 * Since we cannot easily render text in pure C without a font library,
 * we use a distinctive red/dark pattern that is unmistakably an error state.
 * The user can press Super+Q to exit (handled by hotkeys.c).
 *
 * Requirements: 6.4
 */
void process_render_circuit_breaker_error(struct CiosServer *server) {
    if (!server || !server->layer_bg) {
        LOG_ERROR("cannot render circuit breaker error: invalid server state");
        return;
    }

    LOG_ERROR("rendering circuit breaker error indicator on BG layer");

    /*
     * Create a large red background rect covering the screen.
     * Using 8192x8192 to cover any reasonable output size (same approach
     * as the normal BG rect in server.c).
     */
    struct wlr_scene_rect *outer_rect = wlr_scene_rect_create(
        server->layer_bg, 8192, 8192, error_bg_color);
    if (!outer_rect) {
        LOG_ERROR("failed to create error background rect");
        return;
    }

    /*
     * Create a darker inner rect centered on screen to create a visual
     * "panel" effect. Position it with some margin to make the red border
     * visible around the edges.
     */
    struct wlr_scene_rect *inner_rect = wlr_scene_rect_create(
        server->layer_bg, 7000, 7000, error_inner_color);
    if (inner_rect) {
        /* Center the inner rect with ~596px margin on each side */
        wlr_scene_node_set_position(&inner_rect->node, 200, 200);
    }

    /*
     * Create a smaller bright red "X" indicator in the center area
     * to make it even more obvious this is an error state.
     * Two crossing bars forming an X pattern.
     */
    static const float indicator_color[4] = { 1.0f, 0.2f, 0.0f, 1.0f };

    /* Horizontal bar */
    struct wlr_scene_rect *h_bar = wlr_scene_rect_create(
        server->layer_bg, 400, 40, indicator_color);
    if (h_bar) {
        wlr_scene_node_set_position(&h_bar->node, 500, 500);
    }

    /* Vertical bar */
    struct wlr_scene_rect *v_bar = wlr_scene_rect_create(
        server->layer_bg, 40, 400, indicator_color);
    if (v_bar) {
        wlr_scene_node_set_position(&v_bar->node, 680, 320);
    }

    LOG_ERROR("circuit breaker error: runtime crashed %d times in %d seconds. "
              "Press Super+Q to exit.", CIOS_MAX_CRASHES, CIOS_CRASH_WINDOW_SECS);
}

/**
 * Check if the circuit breaker is currently active.
 * Used by hotkeys.c to allow Super+Q to exit when in error state.
 *
 * Requirements: 6.5
 */
bool process_is_circuit_breaker_active(struct CiosServer *server) {
    if (!server || !server->proc_runtime) {
        return false;
    }
    return server->proc_runtime->circuit_breaker_active;
}

/* ═══════════════════════════════════════════════════════════════
 *  Public API
 * ═══════════════════════════════════════════════════════════════ */

/**
 * Initialize process management for the server.
 * Allocates a CiosProcess, builds argv from server->runtime_cmd,
 * and spawns the runtime.
 *
 * @param server The compositor server
 * @return true on success, false on failure
 */
bool process_init(struct CiosServer *server) {
    if (!server->runtime_cmd || server->runtime_cmd[0] == '\0') {
        LOG_ERROR("no runtime command specified");
        return false;
    }

    /* Allocate the process struct */
    struct CiosProcess *proc = calloc(1, sizeof(struct CiosProcess));
    if (!proc) {
        LOG_ERROR("failed to allocate CiosProcess");
        return false;
    }

    /* Build argv from the runtime command string.
     * We make a mutable copy and split on spaces for simple tokenization.
     * For the common case this is just ["cios", NULL]. */
    char *cmd_copy = strdup(server->runtime_cmd);
    if (!cmd_copy) {
        LOG_ERROR("failed to duplicate runtime command");
        free(proc);
        return false;
    }

    /* Count tokens */
    int argc = 0;
    char *tmp = strdup(cmd_copy);
    char *saveptr = NULL;
    char *token = strtok_r(tmp, " \t", &saveptr);
    while (token) {
        argc++;
        token = strtok_r(NULL, " \t", &saveptr);
    }
    free(tmp);

    if (argc == 0) {
        LOG_ERROR("empty runtime command");
        free(cmd_copy);
        free(proc);
        return false;
    }

    /* Allocate argv array */
    char **argv = calloc(argc + 1, sizeof(char *));
    if (!argv) {
        LOG_ERROR("failed to allocate argv");
        free(cmd_copy);
        free(proc);
        return false;
    }

    /* Tokenize into argv */
    saveptr = NULL;
    token = strtok_r(cmd_copy, " \t", &saveptr);
    for (int i = 0; i < argc && token; i++) {
        argv[i] = strdup(token);
        token = strtok_r(NULL, " \t", &saveptr);
    }
    argv[argc] = NULL;
    free(cmd_copy);

    /* Spawn the runtime */
    server->proc_runtime = proc;
    if (!process_spawn(proc, server, argv)) {
        LOG_ERROR("failed to spawn runtime process");
        /* Clean up argv */
        for (int i = 0; argv[i]; i++) {
            free(argv[i]);
        }
        free(argv);
        server->proc_runtime = NULL;
        free(proc);
        return false;
    }

    return true;
}

/**
 * Spawn the runtime process and register SIGCHLD handling.
 *
 * @param proc   Pointer to an allocated CiosProcess struct (zeroed)
 * @param server The compositor server (for event loop and display access)
 * @param argv   NULL-terminated argument vector for the runtime command
 * @return true on success, false on failure
 */
bool process_spawn(struct CiosProcess *proc, struct CiosServer *server, char **argv) {
    memset(proc, 0, sizeof(*proc));
    proc->server = server;
    proc->pid = -1;
    proc->argv = argv;
    proc->restart_count = 0;
    proc->should_restart = true;
    proc->circuit_breaker_active = false;

    /* Initialize crash timestamps to 0 */
    memset(proc->crash_timestamps, 0, sizeof(proc->crash_timestamps));

    /* Register SIGCHLD handler via the Wayland event loop.
     * This integrates child process reaping with the compositor's
     * main event loop — no raw signal handlers needed. */
    struct wl_event_loop *loop = wl_display_get_event_loop(server->display);
    proc->sigchld_source = wl_event_loop_add_signal(loop, SIGCHLD,
                                                     handle_sigchld, proc);
    if (!proc->sigchld_source) {
        LOG_ERROR("failed to add SIGCHLD signal source");
        return false;
    }

    /* Fork and exec the runtime */
    pid_t pid = do_spawn(argv);
    if (pid < 0) {
        wl_event_source_remove(proc->sigchld_source);
        proc->sigchld_source = NULL;
        return false;
    }

    proc->pid = pid;
    LOG_INFO("runtime spawned with pid %d (cmd: %s)", pid, argv[0]);

    return true;
}

/**
 * Clean up process management resources.
 * If the runtime is still running, send SIGTERM and wait briefly.
 */
void process_destroy(struct CiosProcess *proc) {
    if (!proc) {
        return;
    }

    proc->should_restart = false;

    /* Terminate the child if still running */
    if (proc->pid > 0) {
        LOG_INFO("sending SIGTERM to runtime (pid %d)", proc->pid);
        kill(proc->pid, SIGTERM);

        /* Give it a moment to exit gracefully */
        int status;
        pid_t result = waitpid(proc->pid, &status, WNOHANG);
        if (result == 0) {
            /* Still running — wait up to 2 seconds */
            usleep(100000); /* 100ms */
            result = waitpid(proc->pid, &status, WNOHANG);
            if (result == 0) {
                LOG_WARN("runtime did not exit after SIGTERM, sending SIGKILL");
                kill(proc->pid, SIGKILL);
                waitpid(proc->pid, &status, 0);
            }
        }
        proc->pid = -1;
    }

    /* Remove the SIGCHLD event source */
    if (proc->sigchld_source) {
        wl_event_source_remove(proc->sigchld_source);
        proc->sigchld_source = NULL;
    }

    LOG_INFO("process manager destroyed");
}
