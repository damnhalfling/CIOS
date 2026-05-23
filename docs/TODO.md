# CIOS — TODO

> v2.0.0-rc18 — Maio 2026

---

## 🟡 Em andamento

### UX Conversacional — Sprint 3

| Task | Status |
|------|--------|
| Artifact panel GTK4 (split view, copy, close) | ✅ |
| Cognitive indicator no bubble (🧠 memória, ⚖️ honesty) | ✅ |
| Histórico unificado (sync web ↔ OS, timeline única) | 🟡 |
| Sanitização de sync (local_only marks, sem credenciais) | 🟡 |
| Busca em histórico (Ctrl+K ou intent "busca conversa sobre X") | 🟡 |

### Intelligence Client

| Task | Status |
|------|--------|
| Intelligence Client (core/intelligence.py) | ✅ |
| Auth flow | ✅ |
| Cloud API integration | ✅ |
| Topbar: indicador de uso | ✅ |

---

## 📋 Próximo (Fase 1 — Fechar o loop)

| # | Task | Tipo |
|---|------|------|
| 310 | Memória operacional básica (últimos projetos, padrões, hábitos) | Runtime |
| 312 | "Continua o que eu fazia ontem" → restaura estado completo | UX |
| 320 | Sandbox de execução (ações destrutivas isoladas) | Segurança |
| 321 | Rollback de ações (undo operacional) | Confiabilidade |
| 322 | Audit trail (log semântico de tudo que o sistema fez) | Observabilidade |
| 325 | Failure semantics (preservar contexto + alternativa na falha) | UX |
| 353 | Terminal output como contexto (erros → sugestões) | Runtime |
| 381 | Confirmação semântica para ações destrutivas | UX |

---

## 🔮 Backlog (Fase 2+)

### Scheduler cognitivo
| # | Task |
|---|------|
| 400 | Foreground/background intent separation |
| 401 | Interruption control (não quebrar coding flow) |
| 402 | Attention routing (resultado sem roubar foco) |
| 403 | Estado operacional explícito (coding mode, writing mode) |
| 405 | Agrupamento de notificações por contexto/projeto |
| 406 | Focus protection |

### Intent arbitration
| # | Task |
|---|------|
| 410 | Priority model entre intents concorrentes |
| 411 | Intent cancellation (nova intenção cancela anterior) |
| 412 | Execution preemption |
| 413 | Conflict resolution (intents contraditórios) |
| 414 | Background intent queue |

### Multi-channel intent
| # | Task |
|---|------|
| 420 | Voz como side-channel paralelo (pesquisar enquanto coda) |
| 421 | Background intent execution (resolver sem interromper foreground) |
| 422 | Resultado contextual sem interrupção (overlay sutil) |
| 424 | Side-channel results (resumo silencioso de pesquisa/docs) |

### Voz (STT/TTS)
| # | Task |
|---|------|
| 330 | STT local (whisper.cpp) |
| 331 | TTS local (piper) |
| 333 | Modo silencioso (texto puro) como padrão |

### Compositor intent-native
| # | Task |
|---|------|
| 300 | Window focus/layout por intenção |
| 304 | Multitasking por objetivo |
| 361 | Window placement por intenção |
| 362 | Overlays nativos |
| 365 | Focus gerido por contexto/projeto ativo |

### Memória cognitiva
| # | Task |
|---|------|
| 311 | Context graph avançado |
| 313 | Semantic indexing de atividade |
| 370 | Graph de intents (frequência, padrões, relações) |
| 371 | Graph de projetos (pessoas, arquivos, ferramentas) |
| 374 | Intent memory compression |

### Post-app computing
| # | Task |
|---|------|
| 302 | File system semântico |
| 390 | Antecipação de intenção |
| 391 | Zero-click workflows |
| 392 | Redução progressiva de UI |

---

## 🚫 Decisões (não fazer)

- **Tema Jarvis/sci-fi** — diferencial é intenção, não estética futurista
- **Marketplace/plugins** — complexidade sem retorno nesta fase
- **Agent swarm / multi-agent** — hype sem substância para o caso de uso
- **Cloud dependency** — execução sempre local
- **Autonomia máxima** — execução supervisionada, determinística
- **Distro pública massiva** — foco em profundidade vertical
- **Suporte Nvidia** — só Intel/AMD (mesa drivers)

---

## Distribuição — itens menores pendentes

| Task | Prioridade |
|------|-----------|
| Recovery mode no GRUB | Baixa |
| Esconder terminal do usuário comum | Baixa |
