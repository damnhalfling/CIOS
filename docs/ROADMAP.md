# CIOS — Roadmap

> Substituindo apps por intenção.
> Atualizado: Maio 2026 — v2.0.0-rc17

---

## Onde estamos

Protótipo → sistema funcional → **polimento + narrativa + impacto**.

Escopo TRAVADO. NÃO adicionar features. Fechar o loop.

---

## Fases concluídas

| Fase | Objetivo | Status |
|------|----------|--------|
| 1 | Sessão X funcional + skills core | ✅ |
| 2 | Pacote .deb + login customizado | ✅ |
| 3 | Camada cognitiva (MCP/MCO) + desktop completo | ✅ |
| 4 | Desktop features (daemon, topbar, hotkey, EWMH, clipboard) | ✅ |
| 5 | Polimento: boot, latência, confiabilidade, UX conversacional | ✅ |
| 5.5 | Intenção > App: intent abstrato, workflow, file search, explore | ✅ |
| 5.6 | Intent híbrido: regex + cache LLM + stemming + aprendizado | ✅ |
| 5.7 | UI intent-first: prompt bottom, resultado acima, sem sidebar/menus | ✅ |

---

## Fase atual: Produto percebido ✅

### P0 — Killer workflow perfeito ✅
O momento wow: **"quero trabalhar no projeto X"** → ambiente completo pronto.

- ✅ Dev Start 100% confiável (stale deps detection, polling port wait, editor+browser launch)
- ✅ Memória contextual ("continuar projeto X" → reabre como estava via SessionContext)
- ✅ Feedback perfeito (<3s, streaming progress, humanizer completo)
- ✅ Projeto não encontrado → cria automaticamente e abre no editor

### P1 — Confiabilidade core ✅
Se não for 100% confiável → fluxo guiado. Se for confiável → automático.

- ✅ Test matrix real (Ubuntu clean, Debian clean, VM sem GPU)
- ✅ Fluxos guiados multi-step (GuidedFlowStep + GuidedFlow)
- ✅ Degradação graciosa de dependências (nmcli, pactl, bluetoothctl, etc.)
- ✅ Confirmação com senha integrada (sudo antes de confirmar, não depois)

### P2 — Polimento invisível ✅
"Ok" não compete com macOS. Precisa de sensação de "OS novo".

- ✅ Boot: fade transition (300ms alpha animation)
- ✅ Feedback visual consistente (audit 21 handlers, zero leak técnico)
- ✅ Zero tela técnica visível ao usuário (output audit test)
- ✅ UI intent-first: prompt fixo no bottom, resultado persiste acima
- ✅ Removida sidebar/navegação por páginas — superfície única
- ✅ Removida GUI Web — produto é desktop nativo
- ✅ Design tokens centralizados (theme.py)
- ✅ Spinner animado (arco girando + dot pulsante) só quando processa
- ✅ Hotkey overlay com mesma identidade visual
- ✅ Splash com transição contínua para GUI
- ✅ Multi-monitor: janela principal no primário, tela secundária interativa
- ✅ Plymouth boot splash (logo CIOS, sem texto de boot)
- ✅ Installer com opção de substituição completa (LightDM + Plymouth)
- ✅ Modal de confirmação com focus correto (Enter confirma, não reenvia)

### P3 — Demo ✅
- ✅ Gravação manual em máquina real

---

## Fase atual: Hardening + Intelligence + UX Conversacional ✅

### P3.5 — Hardening IA local ✅
- ✅ Ollama auto-start no boot (ollama_manager.py)
- ✅ Indicador de IA no topbar (🧠 verde/amarelo/vermelho)
- ✅ Diagnóstico de conectividade Ollama no boot

### Media Player Inline ✅
- ✅ Skill media_player.py (scan, thumbnails, playback via mpv)
- ✅ Intents PT/EN: "mostre fotos", "mostre vídeos", "tocar música", "parar"
- ✅ Detecção automática de pendrives/mídias montadas
- ✅ Thumbnails com cache (Pillow + ffmpeg)
- ✅ Graceful degradation (sem mpv → informa, sem Pillow → sem thumbnails)

---

### Conversation Threads ✅
- ✅ ThreadManager: coordena estado de conversa com lock único (thread-safe)
- ✅ ThreadClassifier: classificação determinística (pronomes PT/EN, frases de continuação, proximidade temporal, intent)
- ✅ ThreadStore: persistência SQLite (50 threads, enforce limit, filtros por data/intent)
- ✅ Bridge refactor: delega _conversation e _pending_question ao ThreadManager
- ✅ ThreadPanel GUI: substitui recents, expand/collapse, indicadores de pending/timeout
- ✅ Cloud sync: payload sanitizado (sem params/credentials), daemon thread, 10s timeout
- ✅ 9 property tests (Hypothesis) + testes unitários + integração (140 novos testes)

---

### Background Task Queue ✅ (v2.0.0-rc14)
- ✅ TaskQueue: operações longas (apt install, upgrade) rodam em background threads

### Hardening rc17 ✅ (v2.0.0-rc17)
- ✅ IPC nativo `get_outputs` no compositor (elimina dependência xdpyinfo)
- ✅ Protocolo IPC corrigido (surface_id, correlation id, response normalization)
- ✅ `window_control.py` reescrito: 100% IPC nativo, zero código X11
- ✅ `clipboard.py` reescrito: Wayland-only (wl-copy/wl-paste), sem fallback X11
- ✅ deps.py: Wayland-only. Core: foot, wl-clipboard, ollama, nmcli. Sem X11
- ✅ Ollama/Mistral como dependência crítica (sistema não funciona sem)
- ✅ Teste E2E Intelligence Client (18 testes: auth, query, streaming, rate limit, continuity)
- ✅ Mypy efetivo no CI (sem `|| true`, erros bloqueiam build)
- ✅ Bug fix: `state.bluetooth_powered` → `state.bluetooth.powered` no planner
- ✅ Bug fix: `WAYLAND_DISPLAY` ausente no app_launcher → foot não aparecia
- ✅ Bug fix: Ollama timeout 8s → 30s (hardware lento dava circuit breaker)
- ✅ Bug fix: Parser não reconhecia "meu disco com X% de uso" (5 patterns novos)
- ✅ Bug fix: "analise o volume" ambíguo → clarificação ("áudio ou disco?")
- ✅ Coverage threshold: 30% → 45%
- ✅ 635 testes passando

### UX Conversacional ✅ (v2.0.0-rc17)
- ✅ Chat feed GTK4 (MessageBubble, scroll, greeting)
- ✅ Message bubbles (user/assistant, timestamps, metadata cognitiva)
- ✅ Streaming token-by-token (start_streaming, append_token, finish)
- ✅ Progress inline para skills (add_progress_message, update_progress)
- ✅ Tom conversacional (conversational_tone: 30+ regras PT/EN, curto e natural)
- ✅ Follow-up automático (install→abrir, disco→liberar, erro→retry, organizar→ver)
- ✅ Artifact panel GTK4 (split view, copy, close, auto-detect >400 chars)
- ✅ Timing humano (250ms delay antes de responder)
- ✅ Prompt livre: usuário continua digitando enquanto tasks executam
- ✅ Tasks agrupadas por contexto (package, network, files)
- ✅ Execução sequencial dentro do mesmo contexto, paralela entre contextos
- ✅ Progress polling (2s) com atualização visual na UI
- ✅ Notificação de conclusão (sucesso/erro)
- ✅ Bridge: `get_active_tasks()`, `get_task_result()` para UI consultar

### Compositor Hardening ✅ (v2.0.0-rc8→rc14)
- ✅ Server-side decorations: titlebar 28px com close/minimize/maximize
- ✅ VT switching (Ctrl+Alt+F1-F12) via ioctl
- ✅ Alt+Tab: raise_to_top + suporte XDG/XWayland
- ✅ Focus: surfaces hidden são reveladas ao receber foco
- ✅ greetd bundlado no .deb (não depende de repos)
- ✅ PAM config para greetd
- ✅ Plymouth timeout (15s) — não trava boot
- ✅ greetd crash limit (3x em 30s → para)
- ✅ sudo como dependência + usuários no grupo sudo
- ✅ foot (terminal Wayland) como dependência
- ✅ Conflicts: lightdm, gdm3, sddm — sem X11 DMs
- ✅ Build aborta se compositor não compila (sem .deb quebrado)
- ✅ LLM timeout reduzido (15s → 8s) para resposta mais rápida

---

## Fases futuras

| Fase | Objetivo | Quando |
|------|----------|--------|
| Intelligence Client (P4) | Client no OS que consome api.harmoni-ia.com | AGORA |
| Módulo de Voz (P6) | STT/TTS como I/O agnóstico (mic → texto → pipeline → TTS) | Após P4 |
| ~~Wayland compositor~~ | ~~Compositor próprio (wlroots-based)~~ | ✅ CONCLUÍDO |
| ~~Distribuição base~~ | ~~greetd + Plymouth + .deb funcional~~ | ✅ CONCLUÍDO |
| ~~Greeter gráfico~~ | ~~GTK4 Wayland-native login screen~~ | ✅ CONCLUÍDO |
| ~~ISO própria~~ | ~~Live-build com instalador CIOS~~ | ✅ CONCLUÍDO |
| ~~First-boot wizard~~ | ~~"Bem-vindo ao CIOS" + config inicial~~ | ✅ CONCLUÍDO |
| ~~Update mechanism~~ | ~~"CIOS 1.2 disponível" na UI~~ | ✅ CONCLUÍDO |
| ~~Background Tasks~~ | ~~Operações longas em background, prompt livre~~ | ✅ CONCLUÍDO |
| ~~Server-side decorations~~ | ~~Titlebar com close/minimize/maximize~~ | ✅ CONCLUÍDO |

---

## Nota: Migração X11 → Wayland ✅ CONCLUÍDA

**Status:** Compositor Wayland próprio (cios-shell) implementado e funcional.

**O que foi feito:**
- Openbox → **cios-shell** (compositor wlroots 0.18, C puro)
- `wmctrl` → IPC via Unix socket (JSON protocol)
- `xclip` → `wl-copy`/`wl-paste` (com fallback X11)
- Hotkey global → layer-shell protocol
- Tkinter → continua via XWayland
- XWayland habilitado para apps legados (browser, editor, terminal)
- LightDM → **greetd** (display manager Wayland-native)
- **Greeter GTK4** visual com login mascarado (substitui agreety)
- Libs bundled em `/usr/lib/cios/` via ldconfig (sem conflito com sistema)
- Plymouth boot splash funcional
- Instalação limpa via .deb (sem downloads pesados)
- Componentes de IA deferidos para pós-login (`sudo cios-setup-ai`)
- Sessão estável (getty@tty1 masked, seat handoff correto)
- Password dialog mascarado para operações sudo

**Stack de sessão:**
```
GRUB (0s) → Plymouth → greetd (login) → cios-session → cios-shell (Wayland)
```

**O que NÃO mudou (zero impacto):**
- Skills core (nmcli, pactl, apt, bluetoothctl, psutil)
- MCP, planner, intent parser, humanizer, memory
- Toda a camada cognitiva

---

## Números (v2.0.0-rc17)

| Métrica | Valor |
|---------|-------|
| Skills | 26 |
| Intent patterns | 176 (PT/EN) |
| Traduções humanizer | 260+ (PT/EN) |
| Conversational tone rules | 30+ (PT/EN) |
| Tipos de erro | 19 |
| Testes | 635 |
| Property tests (Hypothesis) | 22 |
| Modos de execução | 6 |
| Itens concluídos | 210+ |
| Compositor | cios-shell (wlroots 0.18, C) + SSD |
| Display Manager | greetd (bundlado) |
| Boot splash | Plymouth (tema custom, 15s timeout) |
| UI | GTK4 Wayland-native (chat feed + streaming) |
| Background tasks | TaskQueue (por contexto) |
| Terminal | foot (Wayland-native) |
| Ollama timeout | 30s (tolerante a hardware lento) |
| X11 code | zero (removido) |

---

## Regra #0: Latência + Previsibilidade

> Se Wi-Fi falhar 1x, volume não responder instantâneo, ou o sistema "pensar demais" → usuário volta pro GNOME em 2 minutos.

Skills de sistema = execução direta, sem LLM:
- Wi-Fi → nmcli · Volume → wpctl · Apps → .desktop · Sessão → systemctl
- Pacotes → apt · Janelas → compositor IPC · Clipboard → wl-clipboard · Bateria → psutil

LLM só para intents desconhecidos. Pattern matching resolve 80%+.

---

---

## Branching & Release

- **main** — versão estável, release semanal (domingo)
- **dev** — desenvolvimento diário, RC
- **feat/*** — features isoladas (ex: `feat/wayland-compositor`)

Ver `docs/BRANCHING.md` para detalhes.

---

*Atualizado: Maio 2026 — v2.0.0-rc17*
