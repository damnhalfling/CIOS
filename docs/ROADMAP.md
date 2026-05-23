# CIOS — Roadmap

> Substituindo apps por intenção.
> v2.0.0-rc18 — Maio 2026

---

## Onde estamos

```
✅ Protótipo
✅ Sistema funcional
✅ Polimento + narrativa + impacto
✅ Produto percebido
🟡 Hardening final + distribuição
```

Escopo TRAVADO. NÃO adicionar features. Fechar o loop.

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

---

## Visão futura

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
> Quebrar o modelo single-focus. Aqui o CIOS começa a parecer "o futuro".

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
> Compositor muda de categoria. CIOS define o desktop.

- Window focus/layout gerido por intenção
- Multitasking por objetivo (não por janela)
- Window placement por intenção (não por drag)
- Overlays nativos (sem hack)
- Transições controladas pelo sistema
- Focus gerido por contexto/projeto ativo
- Foreground/background cognitive separation no compositor

### FASE 4 — Memória cognitiva
> CIOS como sistema contínuo.

- Intent graph (frequência, padrões, relações)
- Context graph avançado (relações, objetivos, temporalidade)
- Semantic indexing de atividade
- Replay de workflows
- Intent memory compression (sumarização, pruning, relevance decay)
- Screenshot → contexto (OCR + entendimento)

### FASE 5 — Post-app computing
> Substituir abstrações antigas. Paradigma novo completo.

- File system semântico (acesso por contexto, não por path)
- Antecipação de intenção (sugestão antes do input)
- Zero-click workflows (sistema age sem pedir quando confiança > threshold)
- Redução progressiva de UI (menos elementos conforme confiança cresce)
- Inferência de hábitos (sugestões proativas)
- Browser state como contexto (tabs abertas = intenção)
- Cross-device sync do graph

---

## Princípios de evolução

- **Determinismo > Criatividade.** SO precisa ser confiável, não "criativo".
- **Execução híbrida.** Pattern matching (80%) + LLM (20%), não LLM-first.
- **Atenção humana.** O CIOS gerencia atenção computacional, não só executa.
- **Invisibilidade.** Menos UI, mais fluxo. iPhone venceu por fluidez, não features.
- **Local-first.** Privacidade, offline, determinismo. Cloud é extensão, não dependência.
