# Harmoni OS — TODO

> Escopo TRAVADO. NÃO adicionar features. Fechar o loop.
> Atualizado: Maio 2026 — v0.13.0

---

## ✅ CONCLUÍDO — Produto percebido

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

### P3 — Demo
| # | Task | Status |
|---|------|--------|
| 170 | Gravação manual em máquina real | ⏳ Pendente |

---

## 🟡 DEPOIS — Intelligence (OS side)

Só APÓS P0-P3 estarem fechados.

| # | Task | Esforço |
|---|------|---------|
| 140 | Token Optimizer (Ollama comprime input) | 2 dias |
| 141 | Intelligence Client (HTTP + JWT) | 1 dia |
| 142 | Intents Intelligence no parser | 1 dia |
| 143 | Handlers Intelligence no planner | 1 dia |
| 144 | UX de ativação | 0.5 dia |
| 145 | Humanizer Intelligence | 0.5 dia |
| 146 | Auth flow (Google OAuth) | 1 dia |

---

## ⚪ FUTURO

| Bloco | Quando |
|-------|--------|
| Installer modes (full replacement, clean install) | Próxima release |
| Demo voz (wake word, confirmação, 3 fluxos) | Após Intelligence |
| Distribuição (1-liner, AppImage, ISO) | Quando tiver impacto |

---

## Ordem

```
AGORA  → P0: Killer workflow perfeito
AGORA  → P1: Confiabilidade core
AGORA  → P2: Polimento invisível
AGORA  → P3: Demo
DEPOIS → Intelligence OS side
FUTURO → Demo voz + Distribuição
```

---

*Atualizado: Maio 2026 — v0.13.0*
