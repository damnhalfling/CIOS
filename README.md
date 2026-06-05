<p align="center">
  <img src="assets/background.png" width="600" alt="CIOS" />
</p>

<h1 align="center">CIOS</h1>

<p align="center">
  <strong>Substituindo apps por intenção.<br>Você fala. O computador faz.</strong>
</p>

<p align="center">
  <a href="https://github.com/damnhalfling/cios/releases"><img src="https://img.shields.io/github/v/release/damnhalfling/cios" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/damnhalfling/cios" alt="License" /></a>
  <img src="https://img.shields.io/badge/tests-839%20passing-brightgreen" alt="Tests" />
</p>

<p align="center">
  <a href="https://github.com/damnhalfling/cios/releases/latest"><strong>⬇ Download .deb</strong></a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#english"><strong>English</strong></a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#português"><strong>Português</strong></a>
</p>

---

<a name="english"></a>

## The problem

Computers still work the same way they did decades ago:

- You open applications.
- You navigate menus.
- You manage windows.
- You search for things manually.

**This doesn't scale.**

## The shift

CIOS eliminates the traditional interface.

You don't use apps. **You express intent.**

## See it in action

```
"I want to work on the loyalty project"
→ opens editor → starts backend → launches frontend → opens browser
Done.
```

```
"free up space"
→ analyzes disk → finds unnecessary files
"Found 3.2 GB. Remove?"
```

```
"my computer is slow"
→ analyzes CPU and memory
"Chrome is using too much memory. Close it?"
```

```
"connect to wifi"
→ scans networks → connects to known
"Connected to Starlink (192.168.1.42)"
```

No terminal. No menus. No jargon. Just results.

## What changed

| Traditional model | CIOS |
|---|---|
| Open apps | Declare intent |
| Navigate menus | Direct execution |
| Manage windows | Ignore windows |
| Search for files | Ask for the result |
| Read error messages | Get a suggestion |
| Configure manually | System learns from you |
| Repeat yourself | Once is enough — it remembers |
| Set up cron jobs | Say it in plain language |

## How it works

CIOS is built on four layers:

### MCP — Model Context Protocol

Live system state. Always current.

Wi-Fi · Volume · CPU · Open apps · Disk · Battery · Networks

Reactive watchers + adaptive polling. The system knows itself before you ask.

### MCO — Model Context Orchestrator

The decision layer.

- Enough context → executes immediately
- Ambiguous → asks a clarification question
- Unknown → guides you

No wasted steps. No wrong guesses.

### Skills

Real system execution. 46 skills, zero abstraction.

Wi-Fi (nmcli) · Audio (pactl) · Files · Processes · Packages (apt) · Windows (compositor IPC) · Clipboard (wl-clipboard) · Battery · Brightness · Dev environments · Disk analysis · Auto-learning · File search · Workflow start · Explore system · Gallery management · Favorites & albums · Duplicate detection · Face clustering · Screen capture · Image editing · Spreadsheets (CSV/XLSX) · Theming · Notifications · Scheduler · Automount · VPN · Firewall · Keyring · Trash · Display settings · Night light · Printer · Backup · Locale · Google Workspace (Gmail, Drive, Calendar, Chat)

**No LLM for critical actions.** Pattern matching handles 80%+ of intents. Hybrid classifier (regex → cache → LLM) ensures natural language works while keeping latency low.

### Intelligence — Memory & Learning (paid)

The layer that makes CIOS smarter over time.

- **Cognitive memory** — cross-session recall, semantic search over past conversations
- **User modeling** — learns preferences, routines, and project context progressively
- **Self-improving skills** — complex solutions become reusable shortcuts automatically
- **Scheduled automations** — natural language cron ("every morning, check updates")
- **Persistence nudges** — proactively suggests saving knowledge after complex sessions

Local auto-learning (regex pattern detection) works offline. Intelligence adds deep memory and reasoning on top.

## Voice-first, offline

- Speech-to-text: whisper.cpp (local)
- Text-to-speech: piper (local)
- Never reads commands or technical output
- Short, useful responses

```
"3 duplicate files found. Remove?"
```

Your voice stays on your machine. Always.

## A real system, not an app

- Custom Wayland compositor (cios-shell) — replaces your desktop
- Server-side decorations: titlebar with close/minimize/maximize buttons
- Single-surface interface: prompt at bottom, results above, system status on the right
- Background task execution: long operations (apt install) run without blocking the prompt
- No sidebar, no menus, no page navigation — just intent
- Minimal top bar (clock, battery, wifi, volume, CPU)
- Processing spinner appears only when the system is thinking
- Multi-monitor support (secondary screen shows system context)
- Global hotkey (Ctrl+Space)
- VT switching (Ctrl+Alt+F1-F12) for TTY access
- Boot splash with seamless transition to main interface
- XWayland support for legacy X11 apps (browser, editor, terminal)
- foot terminal (Wayland-native) as default terminal
- Onboarding wizard on first login

**No GNOME. No KDE. No X11. Just intent.**

```
Boot → Plymouth → greetd (login) → cios-shell (Wayland) → Ready
```

## Conversational by design

3-turn context. Clarification questions. Pronoun resolution. Post-action validation.

```
You: connect to wifi
CIOS: Which network?
  Starlink — 85%
  Vizinho — 40%
You: Starlink
CIOS: Connected to Starlink (192.168.1.42)
```

Every error includes a recovery suggestion. **Zero dead-ends.**

## CIOS Intelligence (paid)

CIOS Intelligence is the cloud layer that makes CIOS smarter over time. It handles tasks that benefit from large models, persistent memory, and cross-device continuity.

**What it does:**

- **Cognitive memory** — remembers past conversations, learns your patterns, recalls context across sessions
- **User modeling** — builds a progressive profile (preferences, projects, routines) without manual config
- **Semantic search** — "how did I fix that server issue last week?" finds the answer from history
- **Complex reasoning** — summarizing, translating, generating text, answering knowledge questions
- **Cross-device sync** — same memory, same context between OS, web, and mobile
- **OS command generation** — Intelligence understands your intent and sends executable commands back to the OS

**What stays local:**

- All system actions (Wi-Fi, volume, files, packages) — always local, always instant
- Pattern matching (80%+ of intents) — works offline, zero latency
- Intent cache — previously seen inputs never need the cloud again
- Voice (STT/TTS) — whisper.cpp + piper, fully on-device

```
You: "what happened in the world today?"
CIOS: "Consulting CIOS Intelligence..."
→ Returns a summary from multiple sources

You: "how did I set up the nginx last time?"
CIOS: "Found it. Last Tuesday you ran these 4 commands..."
→ Cognitive memory retrieves the session
```

Intelligence is a paid service. The OS works fully offline for system tasks — Intelligence adds memory, reasoning, and cross-device continuity on top.

## Cross-device continuity

Conversations and actions flow between OS, web, and mobile — same user, same memory, same context.

```
Phone: "check the AWS costs spreadsheet, how much did we spend?"
→ OS finds the file, reads the value
→ "R$ 1.500 last month"

Phone: "correct it to 1.750"
→ OS updates the spreadsheet
→ Next time you open it, the value is already there
```

The OS polls for remote commands every 5 seconds. When another device (mobile, web) needs something executed locally, it happens automatically.

## What you can say

| Input | What happens |
|---|---|
| `connect to wifi` | Scans networks, auto-connects to known |
| `turn up the volume` | Increases volume by 10% |
| `mute` | Mutes audio |
| `firefox` | Launches Firefox (bare app names work) |
| `open chrome` | Launches Google Chrome |
| `my computer is slow` | Diagnoses CPU, memory, disk — suggests actions |
| `free space` | Finds space hogs, suggests cleanup |
| `organize my downloads` | Sorts files by type into folders |
| `install htop` | Installs via apt (masked password + confirmation) |
| `start my backend` | Detects project, installs deps, starts server |
| `search for squirrels` | Opens browser with Google search |
| `pesquise sobre esquilos` | Abre browser com busca no Google |
| `tile window left` | Tiles active window to left half |
| `clipboard history` | Shows clipboard history with smart detection |
| `shutdown` | Shuts down (asks confirmation) |
| `what can you do` | Lists all 14 capability categories |
| `I want to work on project X` | Opens editor + backend + browser for the project |
| `close the project` | Kills server, closes editor and browser windows |
| `where is the contract?` | Searches files by name and content |
| `check spreadsheet costs` | Reads and searches spreadsheet files |
| `update value in spreadsheet` | Edits cell values in CSV/XLSX files |
| `I want to watch a video` | Opens the right media player |
| `update cios` | Checks for updates and installs |
| `favoritar` | Adds current photo to favorites |
| `fotos de ontem` | Shows photos from yesterday |
| `fotos duplicadas` | Finds duplicate images (pHash + MD5) |
| `fotos do João` | Shows photos of a named person |
| `criar álbum viagem` | Creates a photo album |
| `print screen` | Takes a screenshot |
| `gravar tela` | Starts screen recording |
| `parar gravação` | Stops screen recording |
| `girar foto` | Rotates current image 90° |
| `info da foto` | Shows EXIF metadata |
| `how did I fix the server last time?` | Intelligence searches past sessions, shows the commands |
| `every morning check for updates` | Creates a scheduled automation (cron) |
| `prepare my work environment` | Parallel: opens editor, starts backend, checks git, opens browser |

All commands work in **English** and **Portuguese**.

## Install

```bash
# Download the .deb from releases
wget https://github.com/damnhalfling/CIOS/releases/latest/download/cios_3.0.0-rc6_amd64.deb
sudo apt install ./cios_3.0.0-rc6_amd64.deb
sudo reboot
```

CIOS **replaces** the desktop. There is no "session alongside GNOME" mode.
After install, CIOS is the system. Revert with `sudo apt remove cios && sudo reboot`.

The installer:
- Compiles and installs the Wayland compositor (cios-shell)
- Installs Ollama + Mistral (local LLM)
- Installs Whisper (STT) + Piper (TTS)
- Configures greetd (login manager)
- Sets up Plymouth boot splash
- Requires internet during install (~6GB downloads)

## Test without leaving your desktop

```bash
# Run compositor nested inside your current session (Wayland or X11)
WLR_BACKENDS=wayland cios-shell --log-level debug
# Or via X11 backend:
WLR_BACKENDS=x11 cios-shell --log-level debug
```

## Execution modes

```bash
cios              # GUI (default)
cios --cli        # Terminal (Rich + prompt_toolkit)
cios --daemon     # Background daemon (Unix socket)
cios --overlay    # Hotkey overlay (Ctrl+Space)
cios --topbar     # System status bar
cios --setup      # Re-run onboarding wizard
```

## LLM provider

CIOS uses **Ollama** as its local LLM provider. Ollama runs entirely on your machine — free, private, no cloud dependency.

Ollama handles:
- Intent classification for unknown patterns
- Local AI optimization for cloud requests (optional)
- Local AI tasks that don't need cloud processing

Ollama is auto-installed during setup.

### Fallback chain (when Ollama is unavailable)

If Ollama (or any configured LLM) is unreachable, CIOS degrades gracefully:

1. **Pattern matching (regex)** — handles 80%+ of intents with zero LLM dependency
2. **Intent cache (SQLite)** — previously classified inputs are reused instantly
3. **Fuzzy cache match** — similar inputs hit cached results via word-overlap similarity
4. **LLM classification** — lightweight prompt to classify intent (~200-500ms)
5. **Full LLM resolve** — generates a plan for complex/unknown intents
6. **Graceful error** — "Não entendi o que você quer" with recovery suggestion

In practice: if no LLM is available, all regex-matched intents (the vast majority) work normally. Only truly unknown inputs that have never been cached will fail — and even then, the user gets a helpful error message, never a crash.

## Status

- ✅ Custom Wayland compositor (wlroots 0.18) — running on real hardware
- ✅ Server-side decorations (titlebar + close/minimize/maximize)
- ✅ Background task queue — prompt stays free during long operations
- ✅ 46 skills — Wi-Fi, audio, files, packages, windows, clipboard, dev environments, self-update, file search, workflow start, gallery management, duplicates, face clustering, screen capture, spreadsheets, monitor config, theming, notifications, scheduler, automount, VPN, firewall, keyring, trash, display settings, night light, printer, backup, locale, Google Workspace (Gmail, Drive, Calendar, Chat)
- ✅ Hybrid intent classifier — regex + LLM cache with stemming + auto-learning
- ✅ Voice offline — STT + TTS, fully local
- ✅ Multi-monitor — secondary screen as full interaction surface
- ✅ Auto-learning engine
- ✅ .deb installable package (full replacement, no fallbacks)
- ✅ Plymouth boot splash (logo on boot, no text)
- ✅ 839 tests passing (including property-based tests)
- ✅ Onboarding wizard
- ✅ Conversational UX with 3-turn context
- ✅ Project auto-creation ("work on project X" creates it if not found)
- ✅ Media gallery — favorites, albums, duplicates, face clustering, date/text search, editing
- ✅ Screen capture — screenshot (full/window/region) + screen recording
- ✅ XDG user directories — auto-created on login
- ✅ XWayland — full support for X11 apps (browser, editor, terminal)
- ✅ VT switching (Ctrl+Alt+Fn) for TTY access
- ✅ greetd bundled (no dependency on external repos)
- ✅ CIOS Intelligence — cloud cognitive layer (auth, streaming, memory, cross-device sync)
- ✅ Notifications system — events, apps, timers, progress
- ✅ Scheduled tasks — natural language cron ("every morning, check updates")
- ✅ Theming — dark/light mode via intent
- ✅ Automount — USB, SD card, external drives
- ✅ VPN — WireGuard + OpenVPN via intent
- ✅ Firewall — ufw via intent
- ✅ Keyring / secrets management
- ✅ Trash / recycle bin (XDG Trash spec)
- ✅ Display settings — resolution, scaling, refresh rate, monitor arrangement
- ✅ Google Workspace integration — Gmail, Drive, Calendar, Chat via intent

**This is not a prototype. It runs on real hardware.**

## Roadmap

- ✅ ~~CIOS Intelligence integration~~ — done (cloud API, auth, streaming)
- ✅ ~~Wayland compositor~~ — done (wlroots 0.18, XWayland, layer-shell)
- ✅ ~~Custom Debian-based distribution~~ — done (greetd, Plymouth, ISO)
- ✅ ~~Notifications system~~ — done (events, apps, timers)
- ✅ ~~Natural language cron~~ — done (scheduler skill)
- ✅ ~~Theming~~ — done (dark/light via intent)
- ✅ ~~VPN + Firewall~~ — done (WireGuard, OpenVPN, ufw)
- ✅ ~~Google Workspace~~ — done (Gmail, Drive, Calendar, Chat)
- ⏳ Voice module (STT/TTS as alternative I/O)
- ⏳ Cognitive memory advanced (intent graph, semantic indexing) — via Intelligence
- ⏳ Self-improving skills — skills that refine themselves from usage patterns
- ⏳ Project context files (`.cios.yml`) — declarative project config for instant workflow start
- ⏳ Parallel task delegation — split complex intents into concurrent sub-tasks
- ⏳ Persistence nudges — proactive suggestions to save knowledge after complex sessions

## Architecture (for contributors)

```
User Input → Intent Parser → Classifier → MCO → Planner → Executor → Humanizer → UI
                  │              │          │       │          │            │
            201 Patterns     Cache +      MCP     46 Skills   Shell      Translates
            (PT/EN)         LLM +       (live    + Auto-     Control    to human
                           Stemming     state)   Learner      │        language
                                                   │        Memory
                                                   │          │
                                                Scheduler  TaskQueue
                                                (cron)   (background ops)
                                                   │
                                              Intelligence
                                          (cognitive memory +
                                           user model + skills
                                            self-improvement)
```

<details>
<summary><strong>Core components</strong></summary>

- **Intent Parser** — 201 regex patterns (PT/EN), hybrid LLM classifier with cache + stemming for natural language
- **Intent Classifier** — SQLite-cached LLM classifications, fuzzy matching with light PT stemming, auto-learning from successful executions
- **Task Queue** — Background execution for long operations (apt install, upgrades). Tasks grouped by context, sequential within context, parallel across contexts. Prompt stays free.
- **MCP** — Live system state with reactive watchers (nmcli monitor, pactl subscribe) + adaptive polling (1s/5s/15s)
- **MCO** — Decision layer: resolves from MCP state instantly when possible
- **Planner** — Handlers with context-aware execution and `_resilient_call()` retry
- **Executor** — Safe shell execution with timeout, blocked command list, background processes
- **Humanizer** — 260+ translations PT/EN, all technical output becomes plain language
- **Intelligence** — Cloud cognitive layer: memory across sessions, user modeling, semantic search, skill self-improvement
- **Model Router** — Ollama (local, default) with fallback support, 8s timeout
- **Memory** — SQLite store of intents, commands, and outcomes
- **Error Recovery** — 19 error types classified with actionable suggestions (PT/EN)
- **Bridge** — 3-turn conversation context, clarification, pronoun resolution, post-action validation, background task dispatch
- **Gallery Store** — SQLite persistence for favorites, albums, trash, face embeddings, duplicate cache
- **Voice** — STT (whisper.cpp) + TTS (piper), both local and offline
- **Daemon** — Unix socket server for IPC
- **Auto-Learning** — Detects repeated patterns, saves shortcuts, reuses them
- **Compositor** — cios-shell (C/wlroots 0.18): SSD, VT switch, Alt+Tab, layer-shell, XWayland, splash

</details>

<details>
<summary><strong>Project structure</strong></summary>

```
cios-os/
├── cios/
│   ├── main.py                 # Entry point (6 modes)
│   ├── core/
│   │   ├── bridge.py           # UI ↔ backend (sync + streaming + conversation)
│   │   ├── intent_parser.py    # 201 regex patterns PT/EN
│   │   ├── intent_classifier.py # Hybrid LLM classifier + cache + stemming
│   │   ├── planner.py          # 43 handlers + MCO + _resilient_call()
│   │   ├── task_queue.py       # Background task execution (TaskManager + TaskThread)
│   │   ├── thread_manager.py   # Conversation thread state + classification
│   │   ├── intelligence.py     # Cloud cognitive layer (memory, user model, commands)
│   │   ├── scheduler.py        # Natural language cron (planned)
│   │   ├── handlers/           # Intent handlers (gallery, media, screen, etc.)
│   │   ├── mcp.py              # Live system state (watchers + adaptive polling)
│   │   ├── executor.py         # Safe shell execution
│   │   ├── humanizer.py        # Technical → human translation (260+ PT/EN)
│   │   ├── model_router.py     # LLM routing (Ollama default, full fallback chain)
│   │   ├── config.py           # Persistent settings (~/.cios/) + XDG dirs
│   │   ├── memory.py           # SQLite history
│   │   └── error_recovery.py   # 19 error types + actionable suggestions
│   ├── skills/                 # 46 system skills
│   │   ├── package_manager.py  # apt install/remove/search (background-capable)
│   │   ├── app_launcher.py     # .desktop scan + aliases (foot, chrome, etc.)
│   │   ├── gallery_store.py    # Favorites, albums, trash (SQLite)
│   │   ├── gallery_search.py   # Date + text/CLIP search
│   │   ├── duplicates.py       # pHash + MD5 duplicate detection
│   │   ├── face_cluster.py     # Face detection + DBSCAN clustering
│   │   ├── image_edit.py       # Rotate, flip, crop, brightness, EXIF, share
│   │   ├── screen_capture.py   # Screenshot + screen recording
│   │   └── ...                 # network, audio, bluetooth, etc.
│   ├── ui/                     # GUI, CLI, hotkey, topbar, splash, gallery, viewer
│   └── infra/                  # Daemon, voice, multi-monitor, scheduler
├── shell/                      # Wayland compositor (C, wlroots 0.18)
│   ├── src/
│   │   ├── main.c, server.c, output.c, input.c
│   │   ├── hotkeys.c           # Ctrl+Space, Alt+Tab, Super, VT switch
│   │   ├── decorations.c       # Server-side decorations (titlebar + buttons)
│   │   ├── xwayland.c, xdg_shell.c, layer_shell.c
│   │   ├── process.c           # Runtime lifecycle + circuit breaker
│   │   └── ipc.c              # Unix socket JSON protocol
│   └── meson.build
├── session/                    # Wayland session config
├── tests/                      # 839 tests
├── .github/workflows/          # CI: lint → test → build compositor → build .deb → release
├── build-deb.sh                # .deb builder (mandatory compositor, no fallbacks)
└── pyproject.toml
```

</details>

## Quick start (development)

```bash
cd cios-os
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/cios              # GUI
.venv/bin/pytest tests/ -v      # 839 tests
```

**Requirements:** Python 3.10+ · Linux (Ubuntu/Debian) · Optional: Ollama, wl-clipboard, brightnessctl

## Open source

Contributions are welcome — especially in:

- Conversational UX ✅
- New skills
- Performance optimization

## Design principles

1. **No jargon** — everything passes through the humanizer
2. **Single surface** — one input, one feed, one result
3. **Pattern match first** — LLM only when regex can't handle it
4. **Deterministic skills** — system actions execute directly, no AI guessing
5. **Context-aware** — MCP knows the state, MCO decides before every action
6. **Always feel fast** — feedback in <50ms
7. **Confirm destructive actions** — asks before shutdown, installs, file moves
8. **Resilient** — retry + fallback chain + circuit breaker
9. **Voice-first ready** — speak results, never read commands
10. **Zero dead-ends** — every error includes a recovery suggestion
11. **Learn from use** — repeated patterns become shortcuts, complex solutions become skills
12. **Remember everything** — Intelligence retains context across sessions and devices
13. **Anticipate, don't wait** — proactive suggestions based on time, context, and history

---

<a name="português"></a>

## Português

### O problema

Computadores ainda funcionam da mesma forma há décadas: você abre aplicativos, navega menus, gerencia janelas, procura coisas manualmente. **Isso não escala.**

### A mudança

CIOS elimina a interface tradicional. Você não usa apps. **Você expressa intenção.**

### Veja funcionando

```
"quero trabalhar no projeto fidelidade"
→ abre editor → sobe backend → inicia frontend → abre navegador
Pronto.
```

```
"libera espaço"
→ analisa disco → encontra arquivos desnecessários
"Encontrei 3.2 GB. Deseja remover?"
```

```
"meu pc tá lento"
→ analisa CPU e memória
"Chrome está consumindo muita memória. Quer fechar?"
```

### O que mudou

| Modelo tradicional | CIOS |
|---|---|
| Abrir apps | Declarar intenção |
| Navegar menus | Execução direta |
| Gerenciar janelas | Ignorar janelas |
| Procurar arquivos | Pedir o resultado |
| Configurar manualmente | O sistema aprende com você |
| Se repetir | Uma vez basta — ele lembra |
| Configurar cron jobs | Dizer em linguagem natural |

### CIOS Intelligence (pago)

CIOS Intelligence é a camada cloud que torna o CIOS mais inteligente com o tempo. Lida com tarefas que se beneficiam de modelos grandes, memória persistente e continuidade entre dispositivos.

**O que faz:**

- **Memória cognitiva** — lembra conversas passadas, aprende seus padrões, recupera contexto entre sessões
- **Modelagem de usuário** — constrói um perfil progressivo (preferências, projetos, rotinas) sem configuração manual
- **Busca semântica** — "como eu resolvi aquele problema do servidor semana passada?" encontra a resposta no histórico
- **Raciocínio complexo** — resumir, traduzir, gerar texto, responder perguntas de conhecimento
- **Sync cross-device** — mesma memória, mesmo contexto entre OS, web e mobile
- **Geração de comandos** — Intelligence entende sua intenção e envia comandos executáveis de volta ao OS

**O que permanece local:**

- Todas as ações de sistema (Wi-Fi, volume, arquivos, pacotes) — sempre local, sempre instantâneo
- Pattern matching (80%+ dos intents) — funciona offline, zero latência
- Cache de intents — inputs já vistos nunca precisam do cloud novamente
- Voz (STT/TTS) — whisper.cpp + piper, totalmente no dispositivo

```
Você: "o que aconteceu hoje no mundo?"
CIOS: "Consultando CIOS Intelligence..."
→ Retorna um resumo de múltiplas fontes

Você: "como eu configurei o nginx da última vez?"
CIOS: "Achei. Na terça passada você rodou esses 4 comandos..."
→ Memória cognitiva recupera a sessão
```

Intelligence é um serviço pago. O OS funciona totalmente offline para tarefas de sistema — Intelligence adiciona memória, raciocínio e continuidade cross-device por cima.

### O que você pode dizer

| Comando | O que acontece |
|---|---|
| `conectar no wifi` | Escaneia redes, conecta na conhecida |
| `aumentar volume` | Aumenta volume em 10% |
| `silenciar` | Muta o áudio |
| `firefox` | Abre o Firefox (nome do app direto funciona) |
| `abre o chrome` | Abre o Google Chrome |
| `meu computador tá lento` | Diagnóstico com sugestões |
| `libera espaço` | Encontra o que ocupa espaço |
| `organizar meus downloads` | Organiza arquivos por tipo |
| `instalar htop` | Instala via apt (senha mascarada + confirmação) |
| `pesquise sobre esquilos` | Abre browser com busca no Google |
| `desligar` | Desliga (pede confirmação) |
| `quanta bateria` | Mostra status da bateria |
| `aumentar brilho` | Aumenta brilho da tela |
| `o que posso fazer` | Lista todas as capacidades |
| `quero trabalhar no projeto X` | Abre editor + backend + browser |
| `onde está o contrato?` | Busca arquivos por nome e conteúdo |
| `quero assistir um vídeo` | Abre o player de vídeo |
| `atualizar cios` | Verifica e instala atualizações |
| `como eu resolvi o problema do servidor?` | Intelligence busca nas sessões passadas, mostra os comandos |
| `toda manhã verifica atualizações` | Cria uma automação agendada (cron) |
| `prepara meu ambiente de trabalho` | Paralelo: abre editor, sobe backend, checa git, abre browser |

### UX Conversacional

```
Você: conectar no wifi
CIOS: Qual rede?
  Starlink — 85%
  Vizinho — 40%
Você: Starlink
CIOS: Conectado na Starlink (192.168.1.42)
```

### Instalação

```bash
# Baixe o .deb da release
wget https://github.com/damnhalfling/CIOS/releases/latest/download/cios_3.0.0-rc6_amd64.deb
sudo apt install ./cios_3.0.0-rc6_amd64.deb
sudo reboot
```

CIOS **substitui** o desktop. Não existe modo "sessão ao lado do GNOME".
Reverter: `sudo apt remove cios && sudo reboot`.

O instalador requer internet (~6GB de downloads: Ollama, Mistral, Whisper, Piper).

### Configuração de IA

No primeiro boot, o **Onboarding Wizard** guia a configuração:
- **Ollama** (padrão) — local, gratuito, privado. Auto-instalado.

### Modos de execução

```bash
cios              # GUI (padrão)
cios --cli        # Terminal
cios --daemon     # Daemon (socket Unix)
cios --overlay    # Overlay (Ctrl+Space)
cios --topbar     # Barra de status
cios --setup      # Re-executar setup
```

---

> **Interfaces foram criadas porque computadores não entendiam você.**
> **CIOS existe porque agora eles entendem.**

---

*CIOS v3.0.0-rc6 — June 2026*
