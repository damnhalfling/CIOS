# CIOS — TODO

> Atualizado: Maio 2026 — v2.0.0-rc17

---

## ✅ CONCLUÍDO

### P0 — Killer workflow perfeito ✅
| # | Task | Status |
|---|------|--------|
| 150 | Dev Start 100% confiável (stale deps, polling port, editor+browser) | ✅ |
| 151 | Memória contextual ("continuar projeto X") | ✅ |
| 152 | Feedback perfeito (humanizer, streaming, topbar transitions) | ✅ |

### P1 — Confiabilidade core ✅
| # | Task | Status |
|---|------|--------|
| 102 | Test matrix real (Ubuntu, Debian, VM sem GPU) | ✅ |
| 103 | Fluxos guiados (GuidedFlow multi-step) | ✅ |
| 104 | Degradação graciosa de dependências | ✅ |

### P2 — Polimento invisível ✅
| # | Task | Status |
|---|------|--------|
| 160 | Boot: fade transition (300ms alpha) | ✅ |
| 161 | Feedback visual consistente (audit 21 handlers) | ✅ |
| 162 | Audit de outputs (zero tela técnica) | ✅ |

### P3 — Demo ✅
| # | Task | Status |
|---|------|--------|
| 170 | Gravação manual em máquina real | ✅ |

### P3.5 — Hardening IA local ✅
| # | Task | Status |
|---|------|--------|
| 175 | Ollama auto-start no boot (ollama_manager.py) | ✅ |
| 176 | Indicador de IA no topbar (🧠 status) | ✅ |
| 177 | Diagnóstico de conectividade Ollama | ✅ |

### Media Player Inline ✅
| # | Task | Status |
|---|------|--------|
| 200 | Skill media_player.py (scan, thumbnails, playback) | ✅ |
| 201 | Intents: "mostre fotos/vídeos/músicas", "tocar", "parar" | ✅ |
| 202 | Detecção de pendrives/mídias montadas | ✅ |
| 203 | Handler no planner (gallery, play, stop) | ✅ |
| 204 | Thumbnails via Pillow + ffmpeg (com cache) | ✅ |
| 205 | Reprodução via mpv (graceful degradation se ausente) | ✅ |

### Conversation Threads ✅
| # | Task | Status |
|---|------|--------|
| 210 | ThreadManager + ThreadClassifier + ThreadStore | ✅ |
| 211 | ThreadPanel GUI (substitui recents, expand/collapse) | ✅ |
| 212 | Cloud sync de threads (payload sanitizado, daemon thread) | ✅ |
| 213 | Bridge refactor: delega estado conversacional ao ThreadManager | ✅ |
| 214 | 9 property tests + 140 novos testes (unitários + integração) | ✅ |

### P6.5 — Media Gallery: Gestão Completa ✅
| # | Task | Status |
|---|------|--------|
| 240 | Deletar individual (✕ no cell, confirmação, lixeira XDG) | ✅ |
| 241 | Seleção múltipla (checkboxes, toolbar: Deletar/Favoritar/Todos) | ✅ |
| 242 | Deletar em grupo (move seleção para lixeira) | ✅ |
| 243 | Detector de duplicadas (pHash + MD5, cache SQLite) | ✅ |
| 244 | UI duplicadas ("mostre fotos repetidas" → grid agrupado) | ✅ |
| 245 | Intents duplicadas (PT/EN) | ✅ |
| 246 | Face detection (face_recognition/dlib, local) | ✅ |
| 247 | Face clustering (DBSCAN manual, embeddings 128-d) | ✅ |
| 248 | UI pessoas ("mostre fotos por pessoa", nomear) | ✅ |
| 249 | Busca por pessoa ("fotos do João") | ✅ |
| 250 | Cache de embeddings (SQLite ~/.cios/faces.db, incremental) | ✅ |
| 251 | Favoritos (★ toggle no cell/viewer, "mostre favoritas") | ✅ |
| 252 | Álbuns (criar, renomear, adicionar, "mostre álbum X") | ✅ |
| 253 | Persistência (SQLite ~/.cios/gallery.db) | ✅ |
| 254 | Busca por data ("fotos de ontem", "fotos de janeiro 2024") | ✅ |
| 255 | Busca por texto/IA (CLIP quando disponível, filename fallback) | ✅ |
| 256 | Intents busca (PT/EN) | ✅ |
| 257 | Info/metadata (EXIF: data, câmera, GPS) no ImageViewer | ✅ |
| 258 | Edição básica (rotate, flip, crop, brightness/contrast) | ✅ |
| 259 | Compartilhar (xdg-email/xdg-open) | ✅ |
| 260 | Organizar por data (busca retorna ordenado por mtime) | ✅ |

### Screen Capture ✅
| # | Task | Status |
|---|------|--------|
| 270 | Screenshot (full/window/region via maim/scrot) | ✅ |
| 271 | Gravação de tela (ffmpeg x11grab + áudio PulseAudio) | ✅ |
| 272 | Intents: "print screen", "gravar tela", "parar gravação" | ✅ |
| 273 | Salva em ~/Pictures/Screenshots e ~/Videos/Recordings | ✅ |

### XDG User Directories ✅
| # | Task | Status |
|---|------|--------|
| 280 | Criação automática no login (session script) | ✅ |
| 281 | Criação via ensure_dirs() no boot do CIOS | ✅ |
| 282 | user-dirs.dirs config (freedesktop spec) | ✅ |

---

## 🟡 EM ANDAMENTO — Distribuição (Distro Boot)

### Stack de sessão ✅
| # | Task | Status |
|---|------|--------|
| 500 | Compositor Wayland (cios-shell, wlroots 0.18) | ✅ |
| 501 | greetd como display manager (Wayland-native) | ✅ |
| 502 | Plymouth boot splash (tema CIOS) | ✅ |
| 503 | GRUB invisível (0s timeout, silent boot) | ✅ |
| 504 | Libs bundled via ldd + ldconfig (sem conflito sistema) | ✅ |
| 505 | seatd para acesso DRM/input | ✅ |
| 506 | Instalação .deb sem downloads pesados | ✅ |
| 507 | cios-setup-ai (Ollama/Mistral/Whisper pós-login) | ✅ |
| 508 | Greeter GTK4 visual (login screen Wayland-native) | ✅ |
| 509 | Sessão estável pós-login (getty masked, seat handoff) | ✅ |
| 510 | Password dialog mascarado para sudo | ✅ |
| 511 | /etc/os-release customizado ("CIOS") | ✅ |

### Pendente
| # | Task | Prioridade |
|---|------|-----------|
| 510 | ~~Greeter gráfico (trocar agreety por Wayland visual)~~ | ✅ CONCLUÍDO |
| 511 | /etc/os-release customizado ("CIOS" não "Debian") | ✅ CONCLUÍDO |
| 512 | First-boot wizard ("Bem-vindo ao CIOS") | ✅ CONCLUÍDO |
| 513 | Update mechanism na UI | ✅ CONCLUÍDO |
| 514 | ISO de instalação própria (live-build) | ✅ CONCLUÍDO |
| 515 | Recovery mode no GRUB | Baixa |
| 516 | Esconder terminal do usuário comum | Baixa |

---

## 🟡 EM ANDAMENTO — Intelligence Client (P4)

API em produção: `https://api.cios-ia.com/` (Maestro v2.33.0).

**Implementado:**
- ✅ Token Optimizer (Ollama comprime input)
- ✅ Intelligence Client (`core/intelligence.py`)
- ✅ Intents no parser (news, explain, write, translate, summarize)
- ✅ Handler no planner
- ✅ Auth flow (Google → browser → localhost:7778 → JWT)
- ✅ Sidebar Intelligence no bottom da sidebar
- ✅ Download foto Google → ~/.face (avatar LightDM)
- ✅ Maestro OAuth atualizado (v2.33.0 deployed)
- ✅ Topbar: mostra plano + uso ("🧠 Free 3/5")
- ✅ Humanizer: traduções PT pra erros Intelligence
- ✅ Refresh sidebar automático após cada query

**Pendente:**

| # | Task | Esforço |
|---|------|---------|
| 151 | Verificar redirect URI no Google Console | — (config) |

---

---

## 🚫 DECISÕES DE DESIGN (não fazer)

### Visual: Sem tema "Jarvis" oficial

**Decisão:** Não implementar tema sci-fi/Jarvis como identidade ou feature oficial.

**Motivo:** O diferencial do CIOS é computação por intenção, não estética futurista. Um "tema Jarvis" ancora a percepção pública em "brinquedo sci-fi" e mata credibilidade.

**O que o sistema já faz naturalmente (e é suficiente):**
- Topbar com 🧠 status
- Streaming response
- Overlay via Ctrl+Space
- Feedback contextual
- Transições suaves

**Referências visuais corretas (cinematic minimalism):**
- Nothing OS
- HUDs militares limpos
- Interfaces diegéticas de filmes modernos
- Ambient computing / dashboards silenciosos

**Diretrizes visuais para médio prazo:**
- Motion: transições 200-300ms com easing suave
- Translucência: overlay 85-90% opacidade, sutil
- Micro-feedback: pulse no 🧠 quando processa, fade-in nos resultados
- Tipografia: mono para output, sans-serif para UI, contraste alto
- Cor: monocromático + um accent color, sem gradientes

**O que NUNCA fazer:**
- Animações decorativas (partículas, ondas, glitch)
- Fontes estilizadas/futuristas
- Bordas brilhantes ou glow
- Qualquer coisa que pareça "dashboard de filme"
- Hologramas fake, excesso de neon, visual gamer

**Princípio:** O melhor elogio não é "parece Jarvis". É "esqueci que estava usando um computador".

---

## 🔮 VISÃO — O que falta para virar SO do futuro

> O salto: de "desktop Linux avançado com camada cognitiva" para "novo modelo de sistema operacional".
> Princípio: Linux vira infraestrutura. CIOS vira o sistema principal.
> Eixo central: **gerenciamento computacional de intenção e atenção humana**.
> O que NÃO fazer: marketplace, plugin ecosystem, agent swarm, multi-agent hype, cloud dependency, "AI everything", autonomia máxima, distro pública massiva.

### 1. Intent-native all the way down

**Status:** Parcialmente feito (intent execution, contextual continuation, orchestration).

**O salto:** Window manager, notifications, files, focus, sessions, workspace state, multitasking — tudo gerido por intenção.

| # | Task | Camada | Fase |
|---|------|--------|------|
| 300 | Window focus/layout gerido por intenção (não só wmctrl) | Compositor | 3 |
| 301 | Notificações contextuais (filtradas por intent/projeto ativo) | Runtime | 2 |
| 302 | File system semântico (acesso por contexto, não por path) | Runtime | 5 |
| 303 | Sessions/workspaces como unidades de intenção | Runtime | 2 |
| 304 | Multitasking por objetivo (não por janela) | Runtime | 3 |

### 2. Contexto persistente real (estado operacional)

**Status:** Memória básica existe (SQLite, SessionContext, "continuar projeto X").

**O salto:** Continuidade temporal completa — o sistema entende arquivos, tabs, intenção, ambiente, prioridade, ferramentas, estado mental operacional.

| # | Task | Fase |
|---|------|------|
| 310 | Memória operacional básica gratuita (últimos projetos, padrões, hábitos) | 1 |
| 311 | Context graph avançado (relações, objetivos, temporalidade, cross-session) | 4 |
| 312 | "Continua o que eu estava fazendo ontem" → restaura estado completo | 1 |
| 313 | Semantic indexing de atividade (não só intents, mas fluxos) | 4 |
| 314 | Temporal model: deferred intents ("depois da reunião", "amanhã cedo") | 2 |
| 315 | Timeline operacional (scheduling semântico de intenções) | 2 |

**Nota:** Sem memória mínima, o sistema parece "chat stateless com automação". Memória operacional básica é parte do paradigma.

### 3. Runtime agêntico confiável

**Status:** Separação parser/planner/executor/humanizer já existe. Base forte.

**O salto:** Determinismo, rollback, sandbox, observabilidade, permissionamento, recovery, replay, audit trail. SO precisa ser confiável, não "criativo".

| # | Task | Tipo | Fase |
|---|------|------|------|
| 320 | Sandbox de execução (ações destrutivas isoladas) | Segurança | 1 |
| 321 | Rollback de ações (undo operacional) | Confiabilidade | 1 |
| 322 | Audit trail (log semântico de tudo que o sistema fez) | Observabilidade | 1 |
| 323 | Replay de workflows (reproduzir sequência de ações) | Automação | 4 |
| 324 | Recovery automático (falha → estado anterior) | Confiabilidade | 2 |
| 325 | Failure semantics: preservar contexto + preparar alternativa na falha | UX | 1 |

**Princípio:** O futuro NÃO é "LLM controlando tudo livremente". É execução híbrida, determinística, supervisionada, contextual.

### 4. Voz como I/O opcional (não obrigatório)

**Status:** Spec existe (whisper.cpp + piper, offline). Não implementado.

**O salto:** Extensão natural da intenção — hands-free, multitasking, ambient computing, accessibility. Sempre offline. Uso principal: side-channel paralelo (não conversar o tempo inteiro com o computador).

| # | Task | Tipo | Fase |
|---|------|------|------|
| 330 | STT local (whisper.cpp) | Input | 2 |
| 331 | TTS local (piper) | Output | 2 |
| 332 | Ativação por wake word (opcional) | UX | 4 |
| 333 | Modo silencioso (texto puro, sem voz) como padrão | UX | 2 |

**Princípio:** Muita gente pensa mais rápido digitando. Voz é extensão, não substituição. Computação multimodal adaptativa.

### 5. Recursos computacionais semânticos

**Status:** Não implementado.

**O salto:** Usuário pensa em tarefa/objetivo/contexto. SO pensa em processo/arquivo/path. Alinhar os dois.

| # | Task | Tipo | Fase |
|---|------|------|------|
| 340 | Acesso por contexto ("documentos da reunião do cliente X") | Semântico | 5 |
| 341 | Agrupamento por objetivo (não por app/janela) | UX | 3 |
| 342 | Priorização por relevância temporal | Runtime | 5 |
| 343 | Relações semânticas entre recursos (arquivo ↔ projeto ↔ pessoa) | Graph | 4 |

### 6. Multi-modalidade real

**Status:** Parcial (media, screenshots, threads, intent execution).

**O salto:** Texto, voz, imagem, vídeo, tela, clipboard, câmera, apps, browser, terminal — um único espaço contextual. Sem silos.

| # | Task | Tipo | Fase |
|---|------|------|------|
| 350 | Clipboard universal semântico (entende o que foi copiado) | Runtime | 2 |
| 351 | Screenshot → contexto (OCR + entendimento) | IA | 4 |
| 352 | Browser state como contexto (tabs abertas = intenção) | Runtime | 5 |
| 353 | Terminal output como contexto (erros → sugestões) | Runtime | 1 |

### 7. Compositor próprio (wlroots-based)

**Status:** Planejado. Não iniciado. Mais difícil e mais importante estruturalmente.

**O salto:** CIOS deixa de "usar o desktop" e passa a DEFINIR o desktop. Filosofia vira infraestrutura.

| # | Task | Tipo | Fase |
|---|------|------|------|
| 360 | Compositor wlroots-based mínimo | Infra | ✅ |
| 361 | Window placement por intenção (não por drag) | UX | 3 |
| 362 | Overlays nativos (sem hack X11) | UI | 3 |
| 363 | Transições controladas pelo sistema (não pelo WM) | UX | 3 |
| 364 | Layer-shell para hotkey/topbar | Infra | 3 |
| 365 | Focus gerido por contexto/projeto ativo | UX | 3 |

**Nota:** Quase ninguém pequeno chega nessa etapa. É brutal. Mas é onde a categoria muda.

### 8. Intent graph / memory graph (kernel cognitivo)

**Status:** Não implementado. Será o verdadeiro diferencial do CIOS.

**O salto:** Grafo operacional pessoal — relações, frequência, hábitos, objetivos, projetos, pessoas, workflows, temporalidade. Não banco vetorial genérico.

| # | Task | Fase |
|---|------|------|
| 370 | Graph de intents (frequência, padrões, relações) | 4 |
| 371 | Graph de projetos (pessoas, arquivos, ferramentas, estado) | 4 |
| 372 | Inferência de hábitos (sugestões proativas) | 5 |
| 373 | Cross-device sync do graph | 5 |
| 374 | Intent memory compression (sumarização, pruning, relevance decay) | 4 |

**Diferencial futuro:** continuidade computacional.

### 9. Segurança intent-native

**Status:** Não implementado. Quase não existe no mercado.

**O salto:** Permissões por intenção, não por recurso técnico.

| # | Task | Tipo | Fase |
|---|------|------|------|
| 380 | Permissões por intenção ("pode enviar email", "pode deletar") | Segurança | 2 |
| 381 | Confirmação semântica para ações destrutivas | UX | 1 |
| 382 | Níveis de autonomia configuráveis (supervisão → automático) | Segurança | 2 |
| 383 | Audit de ações autônomas (o que o sistema fez sozinho) | Observabilidade | 2 |

### 10. Invisibilidade (UX e fluidez)

**Status:** Parcial (intent-first, single surface, zero jargon).

**O salto:** Menos navegação, menos fricção, menos gerenciamento manual, menos UI. Mais fluxo, continuidade, execução, antecipação, contexto.

| # | Task | Tipo | Fase |
|---|------|------|------|
| 390 | Antecipação de intenção (sugestão antes do input) | UX/IA | 5 |
| 391 | Zero-click workflows (sistema age sem pedir quando confiança > threshold) | UX | 5 |
| 392 | Redução progressiva de UI (menos elementos conforme confiança cresce) | UX | 5 |
| 393 | Continuidade cross-session sem fricção | UX | 2 |

**Princípio:** iPhone venceu por fluidez, touch, resposta imediata — não por features.

---

### 11. Scheduler cognitivo (NOVO)

**Status:** Não implementado. Maior gap estrutural atual.

**O que é:** O sistema precisa entender quando interromper, quando sugerir, quando silenciar, quando agrupar. Não basta executar intenção — precisa gerenciar atenção computacional.

| # | Task | Tipo | Fase |
|---|------|------|------|
| 400 | Foreground/background intent separation | Runtime | 2 |
| 401 | Interruption control (não quebrar coding flow) | UX | 2 |
| 402 | Attention routing (resultado aparece sem roubar foco) | UX | 2 |
| 403 | Estado operacional explícito: coding mode, writing mode, research mode | Runtime | 2 |
| 404 | Modo altera: notificações, layout, contexto, prioridade, ferramentas | Runtime | 2 |
| 405 | Agrupamento de notificações por contexto/projeto | UX | 2 |
| 406 | "Não interromper durante coding flow" (focus protection) | UX | 2 |

**Princípio:** Hoje sistemas operacionais são attention-hostile. O CIOS precisa ser attention-aware.

---

### 12. Intent arbitration (NOVO)

**Status:** Não implementado. Obrigatório antes de computação paralela funcionar.

**O que é:** Quando múltiplas intenções entram em conflito (automação quer agir, usuário mudou de contexto, workflow antigo ativo, outro canal dispara) — quem decide?

| # | Task | Tipo | Fase |
|---|------|------|------|
| 410 | Priority model entre intents concorrentes | Runtime | 2 |
| 411 | Intent cancellation (nova intenção cancela anterior) | Runtime | 2 |
| 412 | Execution preemption (interromper execução em andamento) | Runtime | 3 |
| 413 | Conflict resolution (intents contraditórios) | Runtime | 3 |
| 414 | Background intent queue (fila de intenções secundárias) | Runtime | 2 |

**Princípio:** Sem arbitration, computação paralela vira caos. Isso é coisa de SO real.

---

### 13. Multi-channel intent — Computação paralela humana (NOVO)

**Status:** Não implementado. **Eixo central da tese do CIOS.**

**O que é:** Quebrar o modelo single-focus da GUI. O usuário pode estar codando (foreground) enquanto fala com o PC para pesquisar algo (background). Resultado aparece contextualizado sem roubar foco. Dois sentidos diferentes operando no computador simultaneamente.

**Hoje:** Computadores são single-attention systems. Teclado focado, mouse focado, janela focada. O humano multitarefa — o computador não permite.

**O salto:** Multi-channel intent interaction. Foreground cognition (o que você faz ativamente) + Background cognition (sistema resolvendo intenções secundárias sem quebrar fluxo).

| # | Task | Tipo | Fase |
|---|------|------|------|
| 420 | Voz como side-channel paralelo (pesquisar enquanto coda) | Input | 2 |
| 421 | Background intent execution (resolver sem interromper foreground) | Runtime | 2 |
| 422 | Resultado contextual sem interrupção (overlay sutil, não modal) | UI | 2 |
| 423 | Foreground/background cognitive separation no compositor | UX | 3 |
| 424 | Side-channel results: resumo silencioso de pesquisa/docs | UX | 2 |
| 425 | Ambient response: resultado aparece quando relevante, não quando pronto | UX | 4 |

**Exemplo concreto:**
```
Você: codando (teclado, editor, foco total)
Voz: "pesquisa como fazer X em Python"
Sistema: resolve em background
Resultado: aparece como overlay sutil no canto, sem roubar foco
Você: continua codando, consulta quando quiser
```

**Princípio:** GUI tradicional pressupõe um operador central focando uma ferramenta por vez. Intenção permite canais paralelos, execução assíncrona, atenção distribuída, computação periférica. Isso é praticamente gerenciamento computacional de atenção humana.

---

## Fases de evolução

### FASE 1 — Fechar o loop (curto prazo)
> CIOS confiável e inevitável no uso diário.

| # | Task |
|---|------|
| 148 | Teste e2e Intelligence (login → query → resposta) |
| 151 | Verificar redirect URI no Google Console |
| 310 | Memória operacional básica |
| 312 | "Continua o que eu fazia ontem" → estado completo |
| 320 | Sandbox de execução |
| 321 | Rollback de ações |
| 322 | Audit trail |
| 325 | Failure semantics |
| 353 | Terminal output como contexto (erros → sugestões) |
| 381 | Confirmação semântica para ações destrutivas |

### FASE 2 — Computação paralela
> Quebrar o modelo single-focus. Aqui o CIOS começa a parecer "o futuro".

| # | Task |
|---|------|
| 301 | Notificações contextuais |
| 303 | Sessions/workspaces por intenção |
| 314 | Temporal model: deferred intents |
| 315 | Timeline operacional |
| 324 | Recovery automático |
| 330 | STT local (whisper.cpp) |
| 331 | TTS local (piper) |
| 333 | Modo silencioso como padrão |
| 350 | Clipboard universal semântico |
| 380 | Permissões por intenção |
| 382 | Níveis de autonomia configuráveis |
| 383 | Audit de ações autônomas |
| 393 | Continuidade cross-session |
| 400 | Foreground/background intent separation |
| 401 | Interruption control |
| 402 | Attention routing |
| 403 | Estado operacional explícito (modos) |
| 404 | Modo altera contexto/prioridade/ferramentas |
| 405 | Agrupamento de notificações por contexto |
| 406 | Focus protection |
| 410 | Priority model entre intents |
| 411 | Intent cancellation |
| 414 | Background intent queue |
| 420 | Voz como side-channel paralelo |
| 421 | Background intent execution |
| 422 | Resultado contextual sem interrupção |
| 424 | Side-channel results |

### FASE 3 — Intent-native core
> Parar de depender do desktop tradicional. Compositor muda de categoria.

| # | Task |
|---|------|
| 300 | Window focus/layout por intenção |
| 304 | Multitasking por objetivo |
| 341 | Agrupamento por objetivo |
| 360 | Compositor wlroots-based mínimo |
| 361 | Window placement por intenção |
| 362 | Overlays nativos |
| 363 | Transições controladas pelo sistema |
| 364 | Layer-shell para hotkey/topbar |
| 365 | Focus gerido por contexto |
| 412 | Execution preemption |
| 413 | Conflict resolution |
| 423 | Foreground/background cognitive separation no compositor |

### FASE 4 — Memória cognitiva
> CIOS como sistema contínuo.

| # | Task |
|---|------|
| 311 | Context graph avançado |
| 313 | Semantic indexing de atividade |
| 323 | Replay de workflows |
| 332 | Wake word (opcional) |
| 343 | Relações semânticas entre recursos |
| 351 | Screenshot → contexto (OCR) |
| 370 | Graph de intents |
| 371 | Graph de projetos |
| 374 | Intent memory compression |
| 425 | Ambient response |

### FASE 5 — Post-app computing
> Substituir abstrações antigas. Paradigma novo completo.

| # | Task |
|---|------|
| 302 | File system semântico |
| 340 | Acesso por contexto |
| 342 | Priorização por relevância temporal |
| 352 | Browser state como contexto |
| 372 | Inferência de hábitos |
| 373 | Cross-device sync |
| 390 | Antecipação de intenção |
| 391 | Zero-click workflows |
| 392 | Redução progressiva de UI |

---

## Ordem resumida

```
✅ FEITO   → P0-P3: Produto percebido + Demo
✅ FEITO   → P3.5: Hardening IA local
✅ FEITO   → P5: Intelligence API (Maestro v2.33.0)
✅ FEITO   → P6.5: Media Gallery Gestão Completa
✅ FEITO   → Screen Capture + XDG Dirs
✅ FEITO   → Distribuição: compositor, greetd, Plymouth, .deb
✅ FEITO   → Background Task Queue + SSD + Compositor Hardening
✅ FEITO   → UX Conversacional (chat feed, streaming, tom natural, follow-up)
✅ FEITO   → Hardening rc17 (IPC nativo, Wayland-only, Ollama timeout, parser fixes)
🟡 AGORA   → UX Sprint 3 (histórico unificado, busca, sync)
FASE 1    → Fechar loop (memória, runtime, rollback, audit)
FASE 2    → Computação paralela (scheduler, arbitration, multi-channel, voz)
FASE 3    → Intent-native core (compositor, focus, placement, overlays)
FASE 4    → Memória cognitiva (graph, compression, semantic indexing)
FASE 5    → Post-app computing (filesystem semântico, antecipação, zero-click)
```

---

## 🟡 EM ANDAMENTO — UX Conversacional

> Objetivo: conversar com o CIOS como um humano. Fluido, natural, contínuo.
> Princípio: mesma voz em todo lugar (OS e Intelligence). Execução é local.
> Referência: Intelligence UI (web) define o padrão de UX. OS implementa com capacidade extra.

### Sprint 1 (fundação) ✅
| # | Task | Status |
|---|------|--------|
| 600 | Chat feed GTK4 (substituir label por feed de mensagens) | ✅ |
| 601 | Message bubbles (user/assistant, timestamps, metadata) | ✅ |
| 604 | Tom conversacional (conversational_tone — curto, natural, follow-up) | ✅ |

### Sprint 2 (fluidez) ✅
| # | Task | Status |
|---|------|--------|
| 602 | Streaming token-by-token (Intelligence + skills) | ✅ |
| 603 | Progress inline para skills (streaming de steps) | ✅ |
| 611 | Timing humano (250ms delay antes de streaming) | ✅ |
| 605 | Follow-up automático ("Quer que eu abra?", "Liberar espaço?") | ✅ |

### Sprint 3 (enriquecimento) — pendente
| # | Task | Status |
|---|------|--------|
| 606 | Artifact panel GTK4 (split view para conteúdo longo) | ✅ |
| 609 | Cognitive indicator no bubble (🧠 memória, ⚖️ honesty) | ✅ |
| 607 | Histórico unificado (sync web ↔ OS, timeline única) | 🟡 |
| 608 | Sanitização de sync (local_only marks, sem credenciais) | 🟡 |
| 610 | Busca em histórico (Ctrl+K ou intent "busca conversa sobre X") | 🟡 |

---

*Atualizado: Maio 2026 — v2.0.0-rc17*

---

## Branching & Release

- **main** — versão estável, release semanal (domingo)
- **dev** — desenvolvimento diário, RC
- **feat/*** — features isoladas

Ver `docs/BRANCHING.md` para detalhes.
