<p align="center">
  <img src="assets/background.png" width="600" alt="Harmoni OS" />
</p>

<h1 align="center">Harmoni</h1>

<p align="center">
  <strong>Substituindo apps por intenção.<br>Você fala. O computador faz.</strong>
</p>

<p align="center">
  <a href="https://github.com/damnhalfling/harmoni/releases"><img src="https://img.shields.io/github/v/release/damnhalfling/harmoni" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/damnhalfling/harmoni" alt="License" /></a>
  <img src="https://img.shields.io/badge/tests-468%20passing-brightgreen" alt="Tests" />
</p>

<p align="center">
  <a href="https://github.com/damnhalfling/harmoni/releases/latest"><strong>⬇ Download .deb</strong></a>&nbsp;&nbsp;·&nbsp;&nbsp;
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

Harmoni OS eliminates the traditional interface.

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

| Traditional model | Harmoni OS |
|---|---|
| Open apps | Declare intent |
| Navigate menus | Direct execution |
| Manage windows | Ignore windows |
| Search for files | Ask for the result |
| Read error messages | Get a suggestion |

## How it works

Harmoni OS is built on three layers:

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

Real system execution. 21 skills, zero abstraction.

Wi-Fi (nmcli) · Audio (pactl) · Files · Processes · Packages (apt) · Windows (EWMH) · Clipboard · Battery · Brightness · Dev environments · Disk analysis · Auto-learning · File search · Workflow start · Explore system

**No LLM for critical actions.** Pattern matching handles 80%+ of intents. Hybrid classifier (regex → cache → LLM) ensures natural language works while keeping latency low.

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

- Independent X session — replaces your desktop
- Single-surface interface: prompt at bottom, results above, system status on the right
- No sidebar, no menus, no page navigation — just intent
- Minimal top bar (clock, battery, wifi, volume, CPU)
- Processing spinner appears only when the system is thinking
- Multi-monitor support (secondary screen shows system context)
- Global hotkey (Ctrl+Space)
- Boot splash with seamless transition to main interface
- Onboarding wizard on first login

**No GNOME. No KDE. Just intent.**

```
Boot → Display Manager → "Harmoni OS" → Splash → Ready
```

## Conversational by design

3-turn context. Clarification questions. Pronoun resolution. Post-action validation.

```
You: connect to wifi
Harmoni: Which network?
  Starlink — 85%
  Vizinho — 40%
You: Starlink
Harmoni: Connected to Starlink (192.168.1.42)
```

Every error includes a recovery suggestion. **Zero dead-ends.**

## Harmoni Intelligence (optional)

For tasks that need cloud AI — like summarizing news, generating text, or translating — Harmoni OS can connect to **Harmoni Intelligence**, an optional cloud service.

The OS uses Ollama locally to compress your input before sending, keeping token usage minimal. Authentication is via Google login.

```
You: "what happened in the world today?"
Harmoni: "I can look that up with Harmoni Intelligence."
         [Activate] [No thanks]
```

Everything local stays local. Intelligence is opt-in.

## What you can say

| Input | What happens |
|---|---|
| `connect to wifi` | Scans networks, auto-connects to known |
| `turn up the volume` | Increases volume by 10% |
| `mute` | Mutes audio |
| `open chrome` | Launches Google Chrome |
| `my computer is slow` | Diagnoses CPU, memory, disk — suggests actions |
| `free space` | Finds space hogs, suggests cleanup |
| `organize my downloads` | Sorts files by type into folders |
| `install htop` | Installs via apt (asks confirmation) |
| `start my backend` | Detects project, installs deps, starts server |
| `tile window left` | Tiles active window to left half |
| `clipboard history` | Shows clipboard history with smart detection |
| `shutdown` | Shuts down (asks confirmation) |
| `what can you do` | Lists all 14 capability categories |
| `I want to work on project X` | Opens editor + backend + browser for the project |
| `where is the contract?` | Searches files by name and content |
| `I want to watch a video` | Opens the right media player |
| `update harmoni` | Checks for updates and installs |

All commands work in **English** and **Portuguese**.

## Install

```bash
# One-line install
curl -sL https://raw.githubusercontent.com/damnhalfling/harmoni/main/install-harmoni.sh | sudo bash
```

```bash
# Or manual
sudo apt install ./harmoni_0.12.0_amd64.deb
sudo reboot
```

Select **Harmoni OS** at the login screen. That's it.

The installer offers two modes:
1. **Session only** — adds Harmoni alongside GNOME/KDE
2. **Full replacement** — switches to LightDM with Harmoni theme

After install, say **"update harmoni"** anytime to get the latest version automatically.

## Test without leaving your desktop

```bash
sudo apt install xserver-xephyr openbox wmctrl xdotool
Xephyr :2 -screen 1280x720 &
DISPLAY=:2 openbox &
DISPLAY=:2 .venv/bin/harmoni
```

## Execution modes

```bash
harmoni              # GUI (default)
harmoni --cli        # Terminal (Rich + prompt_toolkit)
harmoni --daemon     # Background daemon (Unix socket)
harmoni --overlay    # Hotkey overlay (Ctrl+Space)
harmoni --topbar     # System status bar
harmoni --setup      # Re-run onboarding wizard
```

## LLM provider

Harmoni OS uses **Ollama** as its local LLM provider. Ollama runs entirely on your machine — free, private, no cloud dependency.

Ollama handles:
- Intent classification for unknown patterns
- Token compression before sending to Harmoni Intelligence (optional)
- Local AI tasks that don't need cloud processing

Ollama is auto-installed during setup.

## Status

- ✅ Independent X session — running on real hardware
- ✅ 21 skills — Wi-Fi, audio, files, packages, windows, clipboard, dev environments, self-update, file search, workflow start
- ✅ Hybrid intent classifier — regex + LLM cache with stemming + auto-learning
- ✅ Voice offline — STT + TTS, fully local
- ✅ Multi-monitor
- ✅ Auto-learning engine
- ✅ .deb installable package
- ✅ 468 tests passing (including 13 property-based tests)
- ✅ Onboarding wizard
- ✅ Conversational UX with 3-turn context

**This is not a prototype. It runs.**

## Roadmap

- ⏳ Harmoni Intelligence integration (optional cloud AI)
- ⏳ Boot optimization (<100ms core actions)
- ⏳ Refined conversational UX
- ⏳ Smarter skills with deeper context
- ⏳ Custom Debian-based distribution

## Architecture (for contributors)

```
User Input → Intent Parser → Classifier → MCO → Planner → Executor → Humanizer → UI
                  │              │          │       │          │            │
            148+ Patterns    Cache +      MCP     21 Skills   Shell      Translates
            (PT/EN)         LLM +       (live    + Auto-     Control    to human
                           Stemming     state)   Learner      │        language
                                                            Memory
```

<details>
<summary><strong>Core components</strong></summary>

- **Intent Parser** — 148+ regex patterns (PT/EN), hybrid LLM classifier with cache + stemming for natural language
- **Intent Classifier** — SQLite-cached LLM classifications, fuzzy matching with light PT stemming, auto-learning from successful executions
- **MCP** — Live system state with reactive watchers (nmcli monitor, pactl subscribe) + adaptive polling (1s/5s/15s)
- **MCO** — Decision layer: resolves from MCP state instantly when possible
- **Planner** — 28 handlers with context-aware execution and `_resilient_call()` retry
- **Executor** — Safe shell execution with timeout, blocked command list, background processes
- **Humanizer** — 220+ translations PT/EN, all technical output becomes plain language
- **Model Router** — Ollama (local, default) with fallback support
- **Memory** — SQLite store of intents, commands, and outcomes
- **Error Recovery** — 17 error types classified with actionable suggestions (PT/EN)
- **Bridge** — 3-turn conversation context, clarification, pronoun resolution, post-action validation
- **Voice** — STT (whisper.cpp) + TTS (piper), both local and offline
- **Daemon** — Unix socket server for IPC
- **Auto-Learning** — Detects repeated patterns, saves shortcuts, reuses them

</details>

<details>
<summary><strong>Project structure</strong></summary>

```
harmoni-os/
├── harmoni/
│   ├── main.py                 # Entry point (6 modes)
│   ├── core/
│   │   ├── bridge.py           # UI ↔ backend (sync + streaming + conversation)
│   │   ├── intent_parser.py    # 148+ regex patterns PT/EN
│   │   ├── intent_classifier.py # Hybrid LLM classifier + cache + stemming
│   │   ├── planner.py          # 25 handlers + MCO + _resilient_call()
│   │   ├── mcp.py              # Live system state (watchers + adaptive polling)
│   │   ├── executor.py         # Safe shell execution
│   │   ├── humanizer.py        # Technical → human translation (185+ PT/EN)
│   │   ├── model_router.py     # LLM routing (Ollama default)
│   │   ├── config.py           # Persistent settings (~/.harmoni/)
│   │   ├── memory.py           # SQLite history
│   │   └── error_recovery.py   # 17 error types + actionable suggestions
│   ├── skills/                 # 21 system skills
│   ├── ui/                     # GUI, CLI, hotkey, topbar, splash, theme
│   └── infra/                  # Daemon, voice, multi-monitor
├── session/                    # X session config (Openbox)
├── tests/                      # 323 tests
├── .github/workflows/          # CI: test → build → release
├── build-deb.sh                # .deb package builder
├── install-harmoni.sh          # One-line installer
└── pyproject.toml
```

</details>

## Quick start (development)

```bash
cd harmoni-os
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/harmoni              # GUI
.venv/bin/pytest tests/ -v      # 323 tests
```

**Requirements:** Python 3.10+ · Linux (Ubuntu/Debian) · Optional: Ollama, xclip, xbindkeys, brightnessctl

## Open source

Contributions are welcome — especially in:

- Conversational UX
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

---

<a name="português"></a>

## Português

### O problema

Computadores ainda funcionam da mesma forma há décadas: você abre aplicativos, navega menus, gerencia janelas, procura coisas manualmente. **Isso não escala.**

### A mudança

Harmoni OS elimina a interface tradicional. Você não usa apps. **Você expressa intenção.**

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

| Modelo tradicional | Harmoni OS |
|---|---|
| Abrir apps | Declarar intenção |
| Navegar menus | Execução direta |
| Gerenciar janelas | Ignorar janelas |
| Procurar arquivos | Pedir o resultado |

### Harmoni Intelligence (opcional)

Para tarefas que precisam de IA cloud — como resumir notícias, gerar texto, ou traduzir — o Harmoni OS pode se conectar ao **Harmoni Intelligence**, um serviço cloud opcional.

O OS usa Ollama localmente para comprimir seu input antes de enviar, mantendo o uso de tokens mínimo. Autenticação via login Google.

```
Você: "o que aconteceu hoje no mundo?"
Harmoni: "Posso buscar isso com Harmoni Intelligence."
         [Ativar] [Não, obrigado]
```

Tudo local permanece local. Intelligence é opt-in.

### O que você pode dizer

| Comando | O que acontece |
|---|---|
| `conectar no wifi` | Escaneia redes, conecta na conhecida |
| `aumentar volume` | Aumenta volume em 10% |
| `silenciar` | Muta o áudio |
| `abre o chrome` | Abre o Google Chrome |
| `meu computador tá lento` | Diagnóstico com sugestões |
| `libera espaço` | Encontra o que ocupa espaço |
| `organizar meus downloads` | Organiza arquivos por tipo |
| `instalar htop` | Instala pacote via apt (pede confirmação) |
| `desligar` | Desliga (pede confirmação) |
| `quanta bateria` | Mostra status da bateria |
| `aumentar brilho` | Aumenta brilho da tela |
| `o que posso fazer` | Lista todas as capacidades |
| `quero trabalhar no projeto X` | Abre editor + backend + browser |
| `onde está o contrato?` | Busca arquivos por nome e conteúdo |
| `quero assistir um vídeo` | Abre o player de vídeo |
| `atualizar harmoni` | Verifica e instala atualizações |

### UX Conversacional

```
Você: conectar no wifi
Harmoni: Qual rede?
  Starlink — 85%
  Vizinho — 40%
Você: Starlink
Harmoni: Conectado na Starlink (192.168.1.42)
```

### Instalação

```bash
# Instalação automática
curl -sL https://raw.githubusercontent.com/damnhalfling/harmoni/main/install-harmoni.sh | sudo bash
```

```bash
# Ou manual
sudo apt install ./harmoni_0.12.0_amd64.deb
sudo reboot
```

Selecione **Harmoni OS** na tela de login.

Depois de instalado, diga **"atualizar harmoni"** a qualquer momento para atualizar automaticamente.

### Configuração de IA

No primeiro boot, o **Onboarding Wizard** guia a configuração:
- **Ollama** (padrão) — local, gratuito, privado. Auto-instalado.

### Modos de execução

```bash
harmoni              # GUI (padrão)
harmoni --cli        # Terminal
harmoni --daemon     # Daemon (socket Unix)
harmoni --overlay    # Overlay (Ctrl+Space)
harmoni --topbar     # Barra de status
harmoni --setup      # Re-executar setup
```

---

> **Interfaces foram criadas porque computadores não entendiam você.**
> **Harmoni OS existe porque agora eles entendem.**

---

*Harmoni OS v0.13.0 — May 2026*
