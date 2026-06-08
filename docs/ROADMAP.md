# CIOS — Roadmap

> Substituindo apps por intenção.
> v3.0.0-rc15 — Junho 2026

---

## Onde estamos

```
✅ Protótipo
✅ Sistema funcional
✅ Polimento + narrativa + impacto
✅ Produto percebido
✅ Compositor Wayland estável (sem crash, apps legados via XWayland)
✅ Desktop completude para primeiro lançamento real
✅ Google Workspace MCP integration
✅ Desktop features (notifications, theming, automount, VPN, firewall, keyring, trash)
✅ Cross-device security (read-only + pending_confirmation)
🟡 Estabilização (notebooks) + demo video
```

**Milestone alcançado (Junho 2026):** Runtime v3 com 47 skills, 839 testes.
Desktop com cobertura ~85%. Google Workspace integrado. Puccini reescrito.
Media Pipeline v2 (mpv IPC + yt-dlp). Execution Orchestrator completo (OE1-OE12).

**Fase atual:** Estabilização final + demo video + cognição avançada (Fase 3).

**Visão de longo prazo:** Evolução contínua rumo a cognição extrema — o ambiente de trabalho
como extensão do ser. Independente de adesão comercial, o desenvolvimento continua.

---

## Fases concluídas

| Fase | Objetivo |
|------|----------|
| 1 | Sessão X funcional + skills core |
| 2 | Pacote .deb + login customizado |
| 3 | Camada cognitiva (MCP/MCO) + desktop completo |
| 4 | Desktop features (daemon, topbar, hotkey, clipboard) |
| 5 | Polimento: boot, latência, confiabilidade, UX conversacional |
| 5.5 | Intenção > App: intent abstrato, workflow, file search |
| 5.6 | Intent híbrido: regex + cache LLM + stemming + aprendizado |
| 5.7 | UI intent-first: prompt bottom, resultado acima, sem sidebar |
| P0 | Killer workflow perfeito (dev start, memória contextual, feedback) |
| P1 | Confiabilidade core (test matrix, fluxos guiados, degradação graciosa) |
| P2 | Polimento invisível (fade, audit, design tokens, multi-monitor) |
| P3 | Demo (gravação em máquina real) |
| P3.5 | Hardening IA local (Ollama auto-start, indicador topbar) |
| P4 | Intelligence Client (cloud API, auth, streaming) |
| P5 | Cross-Device (Command Poller, OS Orchestrator, spreadsheet) |
| — | Media Player Inline (scan, thumbnails, playback mpv) |
| — | Media Gallery Gestão Completa (duplicatas, faces, álbuns, busca, edição) |
| — | Screen Capture (screenshot, gravação, intents) |
| — | Conversation Threads (ThreadManager, ThreadPanel, cloud sync) |
| — | Background Task Queue (TaskManager, contexto, parallelism) |
| — | UX Conversacional (chat feed GTK4, streaming, tom, follow-up, artifact panel) |
| — | Compositor Hardening (SSD, VT switch, IPC nativo, Wayland-only) |
| — | Distribuição (greetd, Plymouth, greeter GTK4, ISO, first-boot wizard) |
| — | History Sync + Sanitization + Search (Sprint 3: sync bidirecional, local_only, Ctrl+K) |

---

## Visão futura

### ✅ FASE 0.5 — Primeiro Lançamento Real (Concluída)
> Desktop completo o suficiente para uso diário + bugs do Maestro/memória resolvidos.

**Contexto:** Compositor Wayland estável. Pipeline unificado v3 resolveu bugs do Maestro.
47 skills implementados. 839 testes passando. Google Workspace integrado.

**Concluído:**
- ✅ Resolver bugs do Maestro (pipeline conversacional) → pipeline unificado v3
- ✅ Resolver bugs da memória (persistência, retrieval) → synaptic reinforcement
- ✅ Garantir fluxo inicial sem quebras (boot → login → uso → shutdown)
- ✅ Google Workspace MCP Integration (Gmail, Drive, Chat, Calendar)
- ✅ Notifications system (eventos do sistema, apps, timers, progresso de tasks)
- ✅ Scheduled tasks / timers ("lembra-me às 17h", "backup toda noite")
- ✅ Automount (USB, SD card, drives externos — detectar e montar)
- ✅ Theming básico (dark/light mode via intent)
- ✅ Display settings via intent (resolução, scaling, refresh rate, arranjo de monitores)
- ✅ VPN via intent ("conecta VPN" → WireGuard/OpenVPN)
- ✅ Firewall via intent ("bloqueia porta 8080" → ufw)
- ✅ Keyring / secrets management (libsecret integration)
- ✅ Trash / recycle bin (XDG Trash spec)
- ✅ Printer support (CUPS integration)
- ✅ Timezone / locale config via intent
- ✅ Night light (gamma/color temperature)
- ✅ Backup/restore via intent

**Pendente (polimento):**
- Touchpad gestures no compositor
- App store integration (Flatpak/Snap via intent) — parcial (`app_store.py` existe)
- Do Not Disturb mode (silencia notificações)

**Acessibilidade (obrigatório para público amplo):**
- Screen reader integration (Orca)
- Zoom / magnifier
- High contrast mode
- Keyboard-only navigation completa

### FASE 1 — Fechar o loop
> CIOS confiável e inevitável no uso diário.

- Memória operacional básica (últimos projetos, padrões, hábitos)
- "Continua o que eu fazia ontem" → restaura estado completo
- Sandbox de execução (ações destrutivas isoladas)
- Rollback de ações (undo operacional)
- Audit trail (log semântico de tudo que o sistema fez)
- Failure semantics (preservar contexto + alternativa na falha)
- Terminal output como contexto (erros → sugestões)
- Confirmação semântica para ações destrutivas

### FASE 2 — Computação paralela
> Quebrar o modelo single-focus. O CIOS começa a operar como extensão cognitiva.

- Scheduler cognitivo (foreground/background, interruption control, attention routing)
- Intent arbitration (priority model, cancellation, background queue)
- Multi-channel intent (voz como side-channel paralelo)
- STT local (whisper.cpp) + TTS local (piper)
- Notificações contextuais (filtradas por projeto ativo)
- Sessions/workspaces por intenção
- Temporal model: deferred intents ("depois da reunião", "amanhã cedo")
- Permissões por intenção ("pode enviar email", "pode deletar")
- Continuidade cross-session sem fricção

### FASE 3 — Intent-native core
> Compositor muda de categoria. CIOS define o desktop cognitivo.

- Window focus/layout gerido por intenção
- Multitasking por objetivo (não por janela)
- Window placement por intenção (não por drag)
- Overlays nativos (sem hack)
- Transições controladas pelo sistema
- Focus gerido por contexto/projeto ativo
- Foreground/background cognitive separation no compositor

### FASE 4 — Memória cognitiva e awareness passivo
> CIOS como sistema contínuo que percebe e aprende.

- Awareness passivo: compositor rastreia foco, tempo, sequência de janelas
- Intent graph (frequência, padrões, relações)
- Context graph avançado (relações, objetivos, temporalidade)
- Semantic indexing de atividade
- Replay de workflows
- Intent memory compression (sumarização, pruning, relevance decay)
- Screenshot → contexto (OCR + entendimento)
- Sessão cognitiva: restaura não só janelas, mas contexto mental do trabalho anterior

### FASE 5 — Post-app computing (cognição extrema)
> Substituir abstrações antigas. O ambiente é extensão do ser.

- File system semântico (acesso por contexto, não por path)
- Antecipação de intenção (sugestão antes do input)
- Zero-click workflows (sistema age sem pedir quando confiança > threshold)
- Redução progressiva de UI (menos elementos conforme confiança cresce)
- Inferência de hábitos (sugestões proativas)
- Browser state como contexto (tabs abertas = intenção)
- Cross-device sync do graph
- Interfaces efêmeras (UI gerada pela IA sob demanda, destruída após uso)
- Streaming de intenção contínuo (sistema não espera input, pré-calcula próximos passos)

---

## Filosofia de desenvolvimento

O CIOS é um projeto de longo prazo. O objetivo final é construir o ambiente de trabalho
cognitivo do futuro — uma extensão real do pensamento do usuário, não apenas um assistente
que responde perguntas.

O desenvolvimento continua independente de adesão comercial ou tração de mercado.
Monetização é consequência, não pré-requisito.

---

## Princípios de evolução

- **Determinismo > Criatividade.** SO precisa ser confiável, não "criativo".
- **Execução híbrida.** Pattern matching (80%) + LLM (20%), não LLM-first.
- **Atenção humana.** O CIOS gerencia atenção computacional, não só executa.
- **Invisibilidade.** Menos UI, mais fluxo. iPhone venceu por fluidez, não features.
- **Local-first.** Privacidade, offline, determinismo. Cloud é extensão, não dependência.
- **Desktop-complete antes de futurista.** Gaps básicos (notifications, theming, automount) antes de features avançadas (intent graph, zero-click).
- **Acessibilidade não é opcional.** Screen reader, zoom, high contrast são requisitos, não nice-to-have.
- **Evolução natural.** Cada camada cognitiva é construída sobre a anterior. Sem saltos de fé.
- **Extensão do ser.** O destino final é um ambiente que pensa junto, não um assistente que responde.
