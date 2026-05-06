# Harmoni OS — Roadmap

> Substituindo apps por intenção.
> Atualizado: Maio 2026 — v0.14.0

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
- ✅ Plymouth boot splash (logo Harmoni, sem texto de boot)
- ✅ Installer com opção de substituição completa (LightDM + Plymouth)
- ✅ Modal de confirmação com focus correto (Enter confirma, não reenvia)

### P3 — Demo
- ⏳ Gravação manual em máquina real (celular)

---

## Fases futuras

| Fase | Objetivo | Quando |
|------|----------|--------|
| Harmoni Intelligence | IA cloud opcional (news, explain, write, translate) | Após P0-P3 |
| Demo voz | Wake word, confirmação por voz, 3 fluxos matadores | Após Intelligence |
| Wayland compositor | Compositor próprio (wlroots-based) | Antes de distribuição |
| Distribuição | 1-liner, AppImage, distro própria | Quando tiver impacto |

---

## Nota: Migração X11 → Wayland

**Decisão:** manter X11 agora, migrar quando for hora de distribuir.

**Por que migrar (eventualmente):**
- Harmoni roda apps reais (editor, browser) — isolamento de segurança faz sentido
- Compositor próprio = controle total sobre window placement, hotkeys, segurança
- Distros estão convergindo pra Wayland como padrão

**O que muda:**
- Openbox → compositor wlroots-based próprio (Harmoni É o compositor)
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

## Números (v0.14.0)

| Métrica | Valor |
|---------|-------|
| Skills | 21 |
| Intent patterns | 155+ (PT/EN) |
| Traduções humanizer | 220+ (PT/EN) |
| Tipos de erro | 19 |
| Testes | 468+ |
| Property tests (Hypothesis) | 13 |
| Modos de execução | 6 |
| Itens concluídos | 150+ |

---

## Regra #0: Latência + Previsibilidade

> Se Wi-Fi falhar 1x, volume não responder instantâneo, ou o sistema "pensar demais" → usuário volta pro GNOME em 2 minutos.

Skills de sistema = execução direta, sem LLM:
- Wi-Fi → nmcli · Volume → pactl · Apps → .desktop · Sessão → systemctl
- Pacotes → apt · Janelas → wmctrl · Clipboard → xclip · Bateria → psutil

LLM só para intents desconhecidos. Pattern matching resolve 80%+.

---

*Atualizado: Maio 2026 — v0.13.0*
