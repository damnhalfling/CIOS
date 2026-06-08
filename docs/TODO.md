# CIOS — TODO

> v3.0.0-rc15 — Junho 2026

---

## ✅ Concluído

### UX Conversacional — Sprint 3

| Task | Status |
|------|--------|
| Artifact panel GTK4 (split view, copy, close) | ✅ |
| Cognitive indicator no bubble (🧠 memória, ⚖️ honesty) | ✅ |
| Histórico unificado (sync web ↔ OS, timeline única) | ✅ |
| Sanitização de sync (local_only marks, sem credenciais) | ✅ |
| Busca em histórico (Ctrl+K ou intent "busca conversa sobre X") | ✅ |

### Intelligence Client

| Task | Status |
|------|--------|
| Intelligence Client (core/intelligence.py) | ✅ |
| Auth flow | ✅ |
| Cloud API integration | ✅ |
| Topbar: indicador de uso | ✅ |

---

## ✅ Concluído — Fase 0.5 (Google Workspace + Desktop Completude)

Todos os itens desta fase foram concluídos.

### Google Workspace MCP Integration (550-564) ✅
- OAuth scopes expandidos (Gmail, Drive, Chat, Calendar)
- Google refresh_token no banco + endpoint de token fresco
- Google MCP Client genérico (HTTP + OAuth)
- Skills: Gmail, Drive, Google Chat, Calendar
- Handlers: email, drive, gchat, calendar
- UI: EmailView, DriveView (GTK4 + artifact panel)
- Consent screen UX

### Desktop Features (500-509) ✅
- Notifications system + notification center
- Scheduled tasks / deferred intents
- Automount USB/SD/drives + notificação de device plugado
- Theming dark/light mode + via intent
- Display settings (resolução, scaling, arranjo de monitores)

### Networking + Segurança (510-514) ✅
- VPN via intent (WireGuard + OpenVPN)
- Firewall via intent (ufw)
- Keyring / secrets (libsecret)
- Trash / recycle bin (XDG Trash spec)
- Proxy config (nmcli)

### Polimento (520-527) ✅
- Printer support (CUPS)
- Timezone / locale config
- Night light (gamma/color temperature)
- Backup/restore via intent

---

## 📋 Próximo — Pendente

### Media Pipeline (mpv IPC)

| # | Task | Tipo | Skill/Módulo |
|---|------|------|--------------|
| — | mpv IPC socket (controle programático: pause, next, vol) | Skill | `skills/mpv_controller.py` |
| — | Media State Tracker (poll → ~/.cios/.media_state) | Skill | `skills/media_state.py` |
| — | yt-dlp pipeline (query → playlist → mpv, sem browser) | Skill | `skills/media_player.py` |
| — | Topbar "now playing" indicator | UI | `ui/gtk/topbar.py` |
| — | Refatorar handle_media_control para IPC | Handler | `handlers/media.py` |

### Polimento pendente

| # | Task | Tipo | Skill/Módulo |
|---|------|------|--------------|
| 523 | Do Not Disturb mode | Infra | notifications filter |
| 524 | Touchpad gestures no compositor | Shell | `shell/src/gestures.c` + libinput |
| 525 | App store integration (Flatpak/Snap via intent) | Skill | `skills/app_store.py` |
| 527 | Multi-user switching (fast user switch) | Session | greetd integration |

### ♿ Acessibilidade (obrigatório para público amplo)

| # | Task | Tipo | Skill/Módulo |
|---|------|------|--------------|
| 530 | Screen reader integration (Orca/AT-SPI) | Infra | GTK4 a11y + compositor |
| 531 | Zoom / magnifier | Shell | compositor shader |
| 532 | High contrast mode | UI | theming variant |
| 533 | Keyboard-only navigation completa | UI | focus management |
| 534 | Reduced motion mode | UI | animation toggle |

---

## 📋 Fase 1 — Fechar o loop

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
