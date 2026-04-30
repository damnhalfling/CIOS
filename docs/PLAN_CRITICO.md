# Harmoni OS — Plano Técnico (Itens Críticos)

> De projeto para produto. Cada item aqui tem: problema, solução, arquivos afetados, e critério de "pronto".
> **Status: ✅ TODOS OS 16 ITENS IMPLEMENTADOS (v0.12.0)**

---

## Resumo de Implementação

| # | Item | Status | Implementação |
|---|------|--------|---------------|
| 62 | Splash screen | ✅ | `ui/splash.py` — logo pulsante, progress bar real, signal protocol |
| 63 | Transição suave | ✅ | `session/harmoni-session.sh` — splash antes do Openbox |
| 64 | Teste .deb em VM | ✅ | `tests/Vagrantfile` + `tests/test-vm-install.sh` (20+ checks) |
| 65 | Feedback instantâneo | ✅ | GUI: processing glow, icon spin, ripple. Web: processingPulse, <50ms |
| 66 | STT percepção | ✅ | Mic glow + waveform animada + "Escutando…" |
| 67 | Ação <1s percepção | ✅ | startProcessing() em <50ms, progress bar SSE, loading spinner |
| 68 | Watchers reativos | ✅ | `mcp.py` — nmcli monitor + pactl subscribe (threads daemon) |
| 69 | MCP polling adaptativo | ✅ | 1s ativo / 5s normal / 15s idle + notify_activity() + force_event() |
| 70 | Validação pós-ação | ✅ | force_update() após skills de estado + verificação de mudança |
| 71 | Erro → sugestão | ✅ | `error_recovery.py` — 19 tipos, classify_error(), suggest_recovery() PT/EN |
| 72 | Fallback gracioso | ✅ | _graceful_error() no bridge, JS global error handler na web |
| 73 | Retry inteligente | ✅ | _resilient_call() com is_retryable() em toda skill |
| 74 | Contexto de turno | ✅ | ConversationTurn, 3 turnos, _record_turn() no bridge |
| 75 | Perguntas de clarificação | ✅ | PendingQuestion, _needs_clarification(), _handle_answer() |
| 76 | Resolução de pronomes | ✅ | _resolve_pronouns() com _extract_object() (PT/EN) |

---

## Próximos Itens Críticos

### Harmoni Intelligence — OS side

| # | Item | Detalhe |
|---|------|---------|
| 140 | Token Optimizer | Ollama comprime input verboso → JSON limpo antes de enviar ao cloud |
| 141 | Intelligence Client | Cliente HTTP com auth JWT |
| 142 | Intents Intelligence | NEWS, EXPLAIN, WRITE, SUMMARIZE, TRANSLATE — patterns PT/EN |
| 143 | Handlers Intelligence | Roteiam para optimizer → client → humanizer |
| 144 | UX de ativação | "Posso resolver com Harmoni Intelligence. [Ativar]" |
| 145 | Humanizer Intelligence | Traduções PT/EN para respostas cloud |
| 146 | Auth flow | Browser → Google → callback → JWT → salva local |

---

*Atualizado: Maio 2026 — v0.12.0*
