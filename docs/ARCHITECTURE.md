# CIOS — Arquitetura

> v3.0.0-rc14 — Junho 2026

---

## Stack de sessão

```
Boot → GRUB (0s, silent) → Plymouth (splash CIOS) → greetd (login)
  → cios-session → cios-shell (compositor Wayland, wlroots 0.18)
    → CIOS runtime GTK4 (prompt + topbar + chat feed)
```

```
┌─────────────────────────────────────────────┐
│  CIOS (o que o usuário vê)                  │
│  ├── cios-shell (compositor Wayland/wlroots)│
│  ├── cios runtime (Python, intent engine)   │
│  ├── greetd (login, bundlado)               │
│  ├── Plymouth (boot splash)                 │
│  └── cios-setup-ai (Ollama, Whisper, Piper) │
├─────────────────────────────────────────────┤
│  Debian (infraestrutura invisível)          │
│  ├── kernel Linux                           │
│  ├── systemd                                │
│  ├── apt/dpkg                               │
│  ├── glibc, drivers, firmware               │
│  └── security patches automáticos           │
└─────────────────────────────────────────────┘
```

---

## Pipeline de intenção

```
User Input → Parser (240+ patterns) → Classifier (regex → cache → Ollama)
  → MCO (decision layer) → Planner (43 handlers) → Executor
  → Humanizer (260+ translations) → UI (streaming GTK4)
```

### MCP — Model Context Protocol
Live system state. Sempre atualizado.

- Wi-Fi, Volume, CPU, Apps, Disk, Battery, Bluetooth, Networks
- Reactive watchers (nmcli monitor, pactl subscribe)
- Adaptive polling (1s/5s/15s conforme atividade)

### MCO — Model Context Orchestrator
Camada de decisão:
- Contexto suficiente → executa imediatamente
- Ambíguo → pergunta de clarificação
- Desconhecido → guia o usuário

### Fallback chain (quando Ollama indisponível)
1. Pattern matching (regex) — 80%+ dos intents
2. Intent cache (SQLite)
3. Fuzzy cache match (word-overlap similarity)
4. LLM classification (~200-500ms)
5. Full LLM resolve (intents complexos)
6. Graceful error

---

## Conversation Threading & History Sync

### Thread Manager
Gerencia estado conversacional com threading determinístico:

```
User Input → ThreadManager.route_input()
  → ThreadClassifier (pronoun, continuation, intent, temporal signals)
  → RoutingDecision: answer_pending | continue_thread | new_thread
```

- **Thread lifecycle:** active → completed (auto-close após 180s inatividade)
- **Persistence:** SQLite (threads + turns), max 50 threads locais
- **Context:** últimos 5 turns disponíveis para pronoun resolution

### History Sync (Web ↔ OS)

```
┌─────────────────────────────────────────────────────────┐
│  SYNC ARCHITECTURE                                       │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  CIOS OS ──push──→ /v1/sync ←──push── Web (Maestro)     │
│     ↑                  │                    ↑             │
│     └──────pull────────┘────────pull────────┘             │
│                                                           │
│  Bidirectional: push unsynced + pull new_from_server      │
│  Periodic: every 5 minutes (daemon thread)                │
│  On-demand: after thread close (fire-and-forget)          │
└─────────────────────────────────────────────────────────┘
```

**Sanitization pipeline (o que NUNCA é sincronizado):**
- `params` (credenciais, paths, tokens) — excluídos do payload
- Absolute paths → `[path]`
- Passwords/tokens → `[redacted]`
- sudo commands → `sudo [command]`
- Threads marcados `local_only` — nunca saem da máquina

**Campos de controle:**
- `local_only: bool` — thread contém dados sensíveis, fica só local
- `origin: str` — "os" ou "web", indica onde foi criado
- `synced: int` — 0 (pendente) ou 1 (sincronizado)

**Auto-detecção de conteúdo sensível:**
- SSH connections, private keys, .env files, credentials.json
- Intent type "session" (login/logout operations)
- Threads detectados são auto-marcados `local_only`

### Search (Ctrl+K)

```
Ctrl+K → SearchOverlay (GTK4, floating)
  → debounce 300ms → ThreadStore.search(query)
  → LIKE match on user_input + result_summary + summary
  → Results: summary, outcome icon, time, preview
```

Também acessível via intent: "busca no histórico sobre X"

---

## Compositor (cios-shell)

Compositor Wayland purpose-built. Não é WM genérico.

| Spec | Valor |
|------|-------|
| Linguagem | C |
| Biblioteca | wlroots 0.18.1 |
| Build | Meson |
| Linhas | ~4500 |
| Arquivos | 13 (main, server, output, input, hotkeys, xwayland, xdg_shell, layer_shell, decorations, process, ipc, log) |

**Funcionalidades:**
- XWayland para apps legados (browser, editor, terminal)
- Layer-shell (topbar, overlay)
- Server-side decorations (titlebar 28px, close/minimize/maximize)
- IPC via Unix socket (JSON protocol)
- VT switching (Ctrl+Alt+F1-F12)
- Multi-monitor (primário: CIOS, secundário: apps)
- Hotkeys: Ctrl+Space (overlay), Alt+Tab (switch), Alt+F4 (close)
- Crash recovery (reinicia runtime se exit != 0)

**Libs bundled (/usr/lib/cios/):**
- libwlroots-0.18, libwayland 1.23, libdisplay-info, libliftoff
- Isoladas via RPATH (não poluem o sistema)

---

## Security boundary: OS vs Web

**Princípio:** Execução é sempre local, nunca remota. Sync é de conteúdo, nunca de capacidade.

| Camada | Pode | Não pode |
|--------|------|----------|
| **Web (Intelligence)** | Conversar, gerar texto, ver histórico | Executar comandos, acessar filesystem, controlar hardware |
| **OS (CIOS)** | Tudo da web + executar, instalar, configurar | — |
| **Sync** | Transferir texto de conversas, memórias, metadata | Transferir credenciais, comandos executáveis, paths locais |

**Implicações:**
- Breach na web = vazamento de conversas (contido, sem acesso a hardware)
- Breach no OS = requer acesso físico à máquina
- Nenhum servidor tem credenciais de nenhuma máquina
- Funciona offline (skills, intent parser, Ollama)
- Cloud down ≠ computador inutilizável

---

## Background Tasks

- TaskQueue: operações longas (apt install, upgrades) em background threads
- Tasks agrupadas por contexto (package, network, files)
- Execução sequencial dentro do mesmo contexto, paralela entre contextos
- Prompt livre durante execução
- Progress polling (2s) com atualização visual

---

## Cross-Device

- Command Poller: OS recebe e executa comandos remotos (Web → Cloud API → OS)
- Polling thread (5s interval, graceful shutdown)
- Status reporting: delivered → executed/failed
- OS Orchestrator: detecta quando chat web precisa de ação no OS
- Tipos: file_read, file_update, dev_start, package, system

---

## Componentes de IA (opcionais, pós-login)

Instalados via `sudo cios-setup-ai`:

| Componente | Tamanho | Função |
|-----------|---------|--------|
| Ollama | ~500MB | Runtime de LLM local |
| Mistral | ~4GB | Modelo de linguagem |
| Whisper | ~1GB | Speech-to-text (spec pronta, integração pendente) |
| Piper | ~100MB | Text-to-speech (spec pronta, integração pendente) |

---

## Estrutura de código

```
cios-os/
├── cios/                    # Python runtime
│   ├── main.py              # Entry point (6 modos)
│   ├── core/                # Engine cognitiva
│   │   ├── bridge.py        # UI ↔ backend (CIOSBridge) + periodic sync
│   │   ├── intent_parser.py # 240+ regex patterns (incl. Google, desktop, networking)
│   │   ├── intent_classifier.py # Hybrid: regex → cache → Ollama
│   │   ├── planner.py       # 43 handlers + MCO
│   │   ├── mcp.py           # Live system state
│   │   ├── executor.py      # Shell execution (timeout, blocked cmds)
│   │   ├── humanizer.py     # 260+ translations
│   │   ├── memory.py        # SQLite history
│   │   ├── thread_manager.py # Conversation state + sync + sanitization
│   │   ├── task_queue.py    # Background execution
│   │   ├── intelligence.py  # Cloud AI integration
│   │   ├── command_poller.py # Cross-device command polling
│   │   ├── google_mcp.py   # Google Workspace MCP client
│   │   ├── model_router.py  # LLM routing + fallback
│   │   ├── error_recovery.py # 19 error types
│   │   └── handlers/        # 19 handler modules (43 handler methods)
│   │       ├── apps.py, audio.py, desktop.py, dev.py
│   │       ├── disk.py, files.py, gallery.py, google_workspace.py
│   │       ├── logs.py, media.py, misc.py, network.py
│   │       ├── packages.py, peripherals.py, process.py
│   │       ├── screen_capture.py, spreadsheet.py, system.py
│   │       └── _common.py
│   ├── skills/              # 47 system skills
│   ├── ui/                  # GTK4 + CLI + hotkey + topbar
│   │   └── gtk/
│   │       ├── app.py           # Main application (Ctrl+K, overlays)
│   │       ├── search_overlay.py # History search (Ctrl+K)
│   │       ├── hotkey_overlay.py # Quick command (Ctrl+Space)
│   │       ├── ipc_listener.py  # Compositor IPC (hotkeys, logout)
│   │       ├── sidebar.py       # Metrics + history + origin indicators
│   │       ├── chat_feed.py     # Streaming chat messages
│   │       ├── artifact_panel.py # Long content display
│   │       └── ...
│   └── infra/               # Daemon, voice, monitors, deps
├── shell/                   # Compositor C (wlroots 0.18)
│   └── src/                 # 14 source files (incl. gestures.c)
├── tests/                   # 839 testes (36 arquivos)
├── session/                 # Wayland session config
├── scripts/                 # Build/install scripts
└── pyproject.toml           # Project config
```

---

## Completude vs. Desktop Linux

CIOS é um **desktop environment cognitivo** sobre Linux (Debian). Kernel, drivers, init, e networking stack são delegados intencionalmente.

### Cobertura atual (~85% de um desktop completo)

| Área | Cobertura | Notas |
|------|-----------|-------|
| Display/Compositor | ~85% | Display settings via intent, falta gestures |
| Interface/Shell | ~90% | 6 modos, intent-driven |
| System Management | ~90% | Notifications, scheduled tasks, keyring, theming, trash |
| Hardware Integration | ~80% | Wi-Fi, BT, audio, battery, printer, automount, display OK |
| Networking | ~85% | Wi-Fi, VPN (WireGuard + OpenVPN), firewall (ufw), proxy OK |
| Acessibilidade | 0% | Blocker para público amplo |
| Personalização | ~70% | Theming dark/light, night light, locale |

### Gaps críticos restantes

| Gap | Impacto | Solução |
|-----|---------|---------|
| Accessibility | Exclui usuários | AT-SPI + Orca + compositor |
| Touchpad gestures | Compositing incompleto | Extensão do compositor (C) |
| App store integration | Flatpak/Snap via intent | `skills/app_store.py` (parcial) |

### Decisão arquitetural

Cada gap é resolvível como:
1. **Novo skill** (Python module em `skills/`)
2. **Novo handler** no planner (intent routing)
3. **Extensão do compositor** (C, para gestures/zoom)

A arquitetura já suporta. É trabalho incremental, não rewrite.
