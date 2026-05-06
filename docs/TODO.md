# Harmoni OS — TODO

> Escopo TRAVADO. NÃO adicionar features. Fechar o loop.
> Atualizado: Maio 2026 — v0.14.0

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
| Media player inline (fotos, vídeo, áudio) — sem abrir app externo | Próxima fase |
| Installer modes (full replacement, clean install) | ✅ v0.14.1 |
| Logo Harmoni na tela de login do LightDM | ✅ v0.14.2 |
| Integração com Maestro API (login Google OAuth + Intelligence) | Após P3 |
| Demo voz (wake word, confirmação, 3 fluxos) | Após Intelligence |
| Distribuição (1-liner, AppImage, ISO) | Quando tiver impacto |

---

## 🟢 PRÓXIMO — Media Player Inline (~3-5 dias)

Galeria de fotos + player de vídeo/áudio embutido no Harmoni. Sem abrir VLC ou outro software.

| # | Task | Esforço |
|---|------|---------|
| 200 | Galeria de fotos (Tkinter + Pillow): scan, thumbnails, ampliar, voltar | 1.5 dia |
| 201 | Detecção de pendrives/mídias montadas | 0.5 dia |
| 202 | Player de vídeo inline (python-mpv embedded no Tk) | 1.5 dia |
| 203 | Extração de thumbnails de vídeo (ffmpeg) | 0.5 dia |
| 204 | Player de áudio (play/pause, barra de progresso) | 0.5 dia |
| 205 | Intents: "mostre fotos", "mostre vídeos", "toque música" | 0.5 dia |
| 206 | Fluxo guiado: "encontrei em X e Y, qual?" | 0.5 dia |

**Deps .deb:** ffmpeg, mpv, python3-pil, python3-pil.imagetk, gstreamer1.0-libav, gstreamer1.0-plugins-good/ugly
**Deps pip:** Pillow, python-mpv

**UX:**
```
"mostre as fotos do pendrive"
→ Grid de thumbnails → clique amplia → Esc volta

"mostre meus vídeos"
→ "Encontrei vídeos em ~/Vídeos e no pendrive Kingston. Qual?"
→ Grid de thumbnails → clique reproduz inline → Esc volta
```

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
