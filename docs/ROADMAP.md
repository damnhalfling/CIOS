# CIOS — Roadmap

> Substituindo apps por intenção.
> Atualizado: Maio 2026 — v1.0.0-rc.1.1

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
| Wayland compositor | Compositor próprio (wlroots-based) | Antes de distribuição |
| Distribuição | 1-liner, AppImage, distro própria | Quando tiver impacto |

---

## Nota: Migração X11 → Wayland

**Decisão:** manter X11 agora, migrar quando for hora de distribuir.

**Por que migrar (eventualmente):**
- CIOS roda apps reais (editor, browser) — isolamento de segurança faz sentido
- Compositor próprio = controle total sobre window placement, hotkeys, segurança
- Distros estão convergindo pra Wayland como padrão

**O que muda:**
- Openbox → compositor wlroots-based próprio (CIOS É o compositor)
- `wmctrl` → protocolos Wayland nativos (controle direto, sem hack)
- `xclip` → `wl-copy`/`wl-paste`
- Hotkey global → layer-shell protocol
- Tkinter → continua via XWayland (ou migra pra widget toolkit nativo)

**O que NÃO muda (zero impacto):**
- Skills core (nmcli, pactl, apt, bluetoothctl, psutil)
- MCP, planner, intent parser, humanizer, memory
- Toda a camada cognitiva

**Estimativa:** ~2-4 semanas de trabalho focado. Acoplamento X11 é localizado (UI + 3 skills).

---

## Números (v1.0.0-rc.1.1)

| Métrica | Valor |
|---------|-------|
| Skills | 26 |
| Intent patterns | 171 (PT/EN) |
| Traduções humanizer | 230+ (PT/EN) |
| Tipos de erro | 19 |
| Testes | 398 |
| Property tests (Hypothesis) | 22 |
| Modos de execução | 6 |
| Itens concluídos | 175+ |

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

*Atualizado: Maio 2026 — v1.0.0-rc.1.1*
