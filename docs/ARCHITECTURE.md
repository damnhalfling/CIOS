# CIOS — Arquitetura

> v3.0.1-beta — Junho 2026

---

## Filosofia Cognitiva

O CIOS não usa LLM como sistema principal. Usa **arquitetura cognitiva**.

```
Paradigma da indústria:          Paradigma CIOS:

  User Input                       User Input
      ↓                                ↓
    LLM (70B)                    Intent Parser (regex, <1ms)
      ↓                                ↓
   Response                      Thought Layer (estado, memória, contexto)
                                       ↓
                                  LLM (1-7B, só quando necessário)
                                       ↓
                                  Executor (ação no sistema)
```

**Princípio Doom:** A indústria tenta GPUs maiores pra renderizar tudo.
O CIOS pergunta: "O que nem precisa passar pelo modelo?"

### A separação fundamental

```
Cognição ≠ Geração de linguagem
```

| Responsabilidade | Quem resolve | Custo |
|-----------------|--------------|-------|
| Identificar intenção | Regex (257 patterns) | 0 tokens, <1ms |
| Decidir como executar | MCO + Orchestrator | 0 tokens, <5ms |
| Manter estado/memória | Thought Layer (Python) | 0 tokens |
| Selecionar contexto | Memory Engine (RAG) | ~100 tokens |
| Gerar texto natural | LLM (Ollama/Bedrock) | ~500 tokens |
| Executar no sistema | Skills (47 módulos) | 0 tokens |

**Resultado:** 80%+ das interações funcionam com 0 tokens. O LLM é chamado
apenas para geração de texto (explicações, opiniões, conversas abertas).

### Hierarquia de resolução

```
[1] Regex patterns (257)     → 80% dos intents → <1ms, offline, 0 tokens
[2] Intent cache (SQLite)    → 10% (frases já vistas) → <5ms, offline
[3] Keyword + scoring        → 5% (variações próximas) → <10ms, offline
[4] LLM classify (Ollama 3B) → 4% (ambiguidades entre 2-3 opções)
[5] LLM full (Bedrock)       → 1% (conversas abertas, explicações)
```

Cada camada reduz a necessidade da próxima. O sistema fica mais inteligente
**sem** aumentar inferência — porque aprende novos patterns e cacheia.

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
User Input → Parser (257 patterns) → Classifier (regex → cache → Ollama)
  → MCO (decision layer) → Planner (47 handlers) → Executor
  → Humanizer (260+ translations) → UI (streaming GTK4)
```

### Thought Layer (camada cognitiva pré-LLM)

O Thought Layer é o que torna possível usar LLMs pequenos (ou nenhum).
Ele assume funções que normalmente seriam empurradas para dentro do modelo:

```
┌─────────────────────────────────────────────────┐
│  THOUGHT LAYER (Python, determinístico)          │
│                                                   │
│  Intent Parser ── identifica O QUE              │
│  Memory Engine ── sabe QUEM/QUANDO (RAG)        │
│  MCP Context   ── percebe ONDE (sistema)        │
│  Orchestrator  ── decide COMO (context-aware)   │
│  State Manager ── mantém estado entre requests   │
│  Planner       ── resolve SEM modelo quando pode │
│                                                   │
│  ↓ Só chama LLM quando precisa gerar texto ↓     │
└─────────────────────────────────────────────────┘
```

**O que isso elimina do LLM:**
- Memória (o modelo não precisa "lembrar" — a memória é externa)
- Planejamento (o Planner decide a rota, não o LLM)
- Estado (mantido entre requests, não recalculado)
- Identidade (fixa no config, não emergida dos parâmetros)
- Contexto do sistema (MCP provê, não precisa estar no prompt)

**Hipótese central:** 70B parâmetros ≈ 7B + Thought Layer bem construído.
O CIOS já opera com essa premissa — 80% dos intents resolvem sem modelo nenhum.

### Disambiguation (quando há ambiguidade)

```
Regex identifica 2-3 intents possíveis
    ↓
Contexto resolve? (media_state, active_apps, etc.)
    ├── Sim → Executa o mais provável
    └── Não →
        ├── 2-3 opções → LLM pequeno escolhe
        └── 4+ opções → OS mostra botões ao user
                         (comandos pré-formatados, executa local)
```

Exemplo de disambiguation response:
```json
{
  "type": "disambiguation",
  "text": "Parar o quê?",
  "options": [
    {"label": "Parar a música", "intent": "media_control", "params": {"action": "stop"}},
    {"label": "Desligar o PC", "intent": "session", "params": {"action": "shutdown"}}
  ]
}
```
User clica → OS executa direto. Zero round-trip ao server.

### MCP — Model Context Protocol
Live system state. Sempre atualizado.

- Wi-Fi, Volume, CPU, Apps, Disk, Battery, Bluetooth, Networks
- Media state (now playing, mode, playlist)
- Reactive watchers (nmcli monitor, pactl subscribe)
- Adaptive polling (1s/5s/15s conforme atividade)

### MCO — Model Context Orchestrator
Camada de decisão context-aware:
- User trabalhando + pede música → sidebar PIP
- Nada aberto + pede música → sidebar (sempre não-intrusivo)
- Media tocando + "para" → media_control (não shutdown)
- Instala pacote → background, notifica quando pronto
- Operação destrutiva → pede confirmação

### Fallback chain (quando Ollama indisponível)
1. Pattern matching (regex) — 80%+ dos intents
2. Intent cache (SQLite)
3. Fuzzy cache match (word-overlap similarity)
4. LLM classification (~200-500ms)
5. Full LLM resolve (intents complexos)
6. Graceful error

---

## Media Pipeline v2

```
User: "toca techno"
    ↓
Intent Parser → media_play {query: "techno"}
    ↓
mpv_controller.play_search("techno", mode="sidebar")
    ↓
mpv --input-ipc-server=~/.cios/mpv.sock ytdl://ytsearch10:techno
    ↓
┌─────────────────────────────────────┐
│  mpv (sidebar PIP, 480p, on-top)    │
│  ← JSON IPC → MpvController        │
│  ← State poll 2s → .media_state    │
│  ← Topbar reads → ♫ Track (▶)      │
└─────────────────────────────────────┘
```

**Controles via IPC (não xdotool):**
- `toggle_pause()`, `next_track()`, `prev_track()`
- `toggle_fullscreen()`, `set_volume(n)`, `quit()`
- Playlist: `loadfile <url> append-play`

**Decisões automáticas:**
- Sempre sidebar PIP (música não interrompe trabalho)
- 480p cap (performance em hardware limitado)
- Stop seletivo (não mata mpv de outros contextos)

---

## Execution Orchestrator (Maestro)

Quando `client=os` e o intent requer execução complexa:

```
User: "instala docker"
    ↓
Maestro Pipeline:
  [1] Regex detect → intent: package, params: {package: "docker"}
  [2] Orchestrator planeja multi-step:
      Step 1: Adiciona repositório Docker
      Step 2: apt update
      Step 3: Instala docker-ce
      Step 4: Adiciona user ao grupo
  [3] Retorna step 1 → OS executa → reporta → Maestro envia step 2...
  [4] Error? → _attempt_recovery (fix_dpkg, add_sudo, retry_network)
  [5] User input needed? → type: "question" → OS mostra → user responde → continua
```

**Session State:** Maestro mantém estado entre requests (media, apps, projeto ativo).
Persiste em DB com TTL 1h. Restaura no boot.

---

## Conversation Threading & History Sync

### Thread Manager
```
User Input → ThreadManager.route_input()
  → ThreadClassifier (pronoun, continuation, intent, temporal signals)
  → RoutingDecision: answer_pending | continue_thread | new_thread
```

### History Sync (Web ↔ OS)
Bidirectional, periódico (5min), com sanitização automática de dados sensíveis.

---

## Compositor (cios-shell)

Compositor Wayland purpose-built. Não é WM genérico.

| Spec | Valor |
|------|-------|
| Linguagem | C |
| Biblioteca | wlroots 0.18.1 |
| Build | Meson |
| Linhas | ~4500 |

**Funcionalidades:**
- XWayland para apps legados
- Layer-shell (topbar, overlay)
- Server-side decorations
- IPC via Unix socket (JSON protocol)
- Multi-monitor, hotplug
- Crash recovery (reinicia runtime se exit != 0)
- Window Manager: `move_to_sidebar()`, `move_to_foreground()`, `move_to_fullscreen()`

---

## Security boundary: OS vs Web

| Camada | Pode | Não pode |
|--------|------|----------|
| **Web (Intelligence)** | Conversar, gerar texto, ver histórico | Executar comandos, acessar filesystem |
| **OS (CIOS)** | Tudo da web + executar, instalar, configurar | — |
| **Sync** | Transferir texto de conversas | Transferir credenciais, comandos |

---

## Números

| Métrica | Valor |
|---------|-------|
| Intents (regex) | 257 patterns, 47 tipos |
| Skills | 47 módulos Python |
| Testes | 1079 (839 OS + 240 Maestro) |
| Boot → Desktop | <4s |
| Latência intent (regex) | <1ms |
| Latência LLM (Bedrock) | ~2s |
| RAM idle | ~180MB |
| Offline funcional | 80%+ |
| Compositor | 100% Wayland (zero X11 na UI) |

---

## Estrutura de código

```
cios-os/
├── cios/                    # Python runtime
│   ├── core/                # Engine cognitiva (Thought Layer)
│   │   ├── intent_parser.py # 257 regex patterns
│   │   ├── bridge.py        # UI ↔ backend + orchestration
│   │   ├── intelligence.py  # Cloud AI + system_context
│   │   ├── planner.py       # 47 handlers + MCO
│   │   ├── mcp.py           # Live system state
│   │   └── handlers/        # 19 handler modules
│   ├── skills/              # 47 system skills
│   │   ├── mpv_controller.py    # Media IPC control
│   │   ├── window_manager.py    # Sidebar/foreground/fullscreen
│   │   └── ...
│   ├── ui/gtk/              # GTK4 interface
│   └── infra/               # Daemon, voice, deps
├── shell/                   # Compositor C (wlroots 0.18)
├── tests/                   # 839 testes
└── pyproject.toml
```
