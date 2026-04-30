# Harmoni OS — TODO

> Tarefas pendentes do sistema open source.
> Atualizado: Maio 2026 — v0.12.0

---

## 🔴 Prioridade Alta

### Harmoni Intelligence — OS side
| # | Task | Esforço |
|---|------|---------|
| 140 | Token Optimizer (Ollama comprime input antes de enviar ao cloud) | 2 dias |
| 141 | Intelligence Client (cliente HTTP com auth JWT) | 1 dia |
| 142 | Intents Intelligence no parser (NEWS, EXPLAIN, WRITE, SUMMARIZE, TRANSLATE) | 1 dia |
| 143 | Handlers Intelligence no planner | 1 dia |
| 144 | UX de ativação ("Posso resolver com Harmoni Intelligence. [Ativar]") | 0.5 dia |
| 145 | Humanizer Intelligence (traduções PT/EN para respostas cloud) | 0.5 dia |
| 146 | Auth flow (Google OAuth → browser → callback → JWT → salva local) | 1 dia |

### Confiabilidade
| # | Task | Esforço |
|---|------|---------|
| 102 | Test matrix real (Ubuntu clean, Debian clean, VM sem GPU) | 2 dias |

---

## 🟡 Prioridade Média

### Demo Voz
| # | Task | Esforço |
|---|------|---------|
| 84 | Wake word / push-to-talk contínuo | 2 dias |
| 85 | Confirmação por voz — "sim"/"não"/"cancela" | 1 dia |
| 86 | Navegação por voz — "configurações"/"volta" | 1 dia |
| 87-91 | 3 fluxos matadores + momento mágico + roteiro 60s | 4.5 dias |

### Distribuição
| # | Task | Esforço |
|---|------|---------|
| 109 | Install script 1-liner (detecta distro) | 1 dia |
| 110 | AppImage portable | 2 dias |
| 111 | Distro própria base Debian (ISO) — Harmoni OS | 1 semana+ |

---

## Ordem de execução

```
AGORA  → Intelligence OS side (#140-146)
DEPOIS → Confiabilidade (#102)
DEPOIS → Demo voz (#84-91)
DEPOIS → Distribuição (#109-111)
```

---

*Atualizado: Maio 2026 — v0.12.0*
