# CIOS — Roadmap

> Substituindo apps por intenção.
> Atualizado: Maio 2026 — v1.1.0-rc5

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

## Fase atual: Hardening + Intelligence

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

## Fases futuras

| Fase | Objetivo | Quando |
|------|----------|--------|
| Intelligence Client (P4) | Client no OS que consome api.harmoni-ia.com | AGORA |
| Módulo de Voz (P6) | STT/TTS como I/O agnóstico (mic → texto → pipeline → TTS) | Após P4 |
| ~~Wayland compositor~~ | ~~Compositor próprio (wlroots-based)~~ | ✅ CONCLUÍDO |
| ~~Distribuição base~~ | ~~greetd + Plymouth + .deb funcional~~ | ✅ CONCLUÍDO |
| Greeter gráfico | Trocar agreety por greeter Wayland visual | Próximo |
| ISO própria | Live-build com instalador CIOS | Após greeter |
| First-boot wizard | "Bem-vindo ao CIOS" + config inicial | Após ISO |
| Update mechanism | "CIOS 1.2 disponível" na UI | Após wizard |

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
- Libs bundled em `/usr/lib/cios/` via RPATH (sem conflito com sistema)
- Plymouth boot splash funcional
- Instalação limpa via .deb (sem downloads pesados)
- Componentes de IA deferidos para pós-login (`sudo cios-setup-ai`)

**Stack de sessão:**
```
GRUB (0s) → Plymouth → greetd (login) → cios-session → cios-shell (Wayland)
```

**O que NÃO mudou (zero impacto):**
- Skills core (nmcli, pactl, apt, bluetoothctl, psutil)
- MCP, planner, intent parser, humanizer, memory
- Toda a camada cognitiva

---

## Números (v1.1.0-rc5)

| Métrica | Valor |
|---------|-------|
| Skills | 26 |
| Intent patterns | 171 (PT/EN) |
| Traduções humanizer | 230+ (PT/EN) |
| Tipos de erro | 19 |
| Testes | 615 |
| Property tests (Hypothesis) | 22 |
| Modos de execução | 6 |
| Itens concluídos | 175+ |
| Compositor | cios-shell (wlroots 0.18, C) |
| Display Manager | greetd + agreety |
| Boot splash | Plymouth (tema custom) |
| Libs bundled | ~40 (via ldd, RPATH isolado) |

---

## Regra #0: Latência + Previsibilidade

> Se Wi-Fi falhar 1x, volume não responder instantâneo, ou o sistema "pensar demais" → usuário volta pro GNOME em 2 minutos.

Skills de sistema = execução direta, sem LLM:
- Wi-Fi → nmcli · Volume → pactl · Apps → .desktop · Sessão → systemctl
- Pacotes → apt · Janelas → wmctrl · Clipboard → xclip · Bateria → psutil

LLM só para intents desconhecidos. Pattern matching resolve 80%+.

---

---

## Branching & Release

- **main** — versão estável, release semanal (domingo)
- **dev** — desenvolvimento diário, RC
- **feat/*** — features isoladas (ex: `feat/wayland-compositor`)

Ver `docs/BRANCHING.md` para detalhes.

---

*Atualizado: Maio 2026 — v1.1.0-rc5*
