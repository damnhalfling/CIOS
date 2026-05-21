---
inclusion: auto
---

# CIOS Design System — Shared Visual Language

## Princípio

O CIOS OS e o Maestro (intelligence-ui) compartilham a mesma linguagem visual.
A experiência deve ser indistinguível entre o desktop e a web — mesmas cores,
mesmas animações, mesma tipografia, mesma sensação.

## O que é exclusivo do OS (NÃO vai para a web)

- Compositor Wayland / layer-shell
- System metrics (CPU, RAM, Disk) no sidebar
- Plymouth boot theme
- greetd / greeter login
- Voice input/output (Whisper/Piper)
- Hotkey overlay (Ctrl+Space)
- Integração com Ollama local

## O que é compartilhado (DEVE ser igual nos dois)

- Paleta de cores (tokens abaixo)
- Tipografia (Inter + JetBrains Mono)
- Animações (fade-in, slide-up, shimmer, glow-pulse)
- Chat/prompt UX (input no bottom, mensagens acima)
- Artifact panel (conteúdo longo abre em painel lateral)
- Scrollbar styling (5px, accent translúcido)
- Focus ring (1px accent 40% opacity)
- Glass effect (backdrop-filter blur)
- Code blocks (fundo escuro, border accent sutil)

## Paleta de Cores — Single Source of Truth

| Token | Hex | RGB | Uso |
|-------|-----|-----|-----|
| bg | #00050d | 0,5,13 | Fundo principal (espaço digital profundo) |
| bg-secondary | #000a14 | 0,10,20 | Painéis, sidebar |
| bg-tertiary | #001020 | 0,16,32 | Cards, inputs |
| bg-hover | #001a30 | 0,26,48 | Hover states |
| border | #002040 | 0,32,64 | Bordas sutis |
| border-focus | #003060 | 0,48,96 | Bordas em foco |
| fg | #e0f4ff | 224,244,255 | Texto principal |
| fg-secondary | #7eb8d8 | 126,184,216 | Texto secundário |
| fg-dim | #3a6080 | 58,96,128 | Texto terciário/desabilitado |
| accent | #00e5ff | 0,229,255 | Accent principal (cyan TRON) |
| accent-light | #40f0ff | 64,240,255 | Accent hover/destaque |
| accent-dark | #009db8 | 0,157,184 | Accent pressed/sutil |
| accent-glow | rgba(0,229,255,0.25) | — | Glow/shadow |
| success | #00e676 | 0,230,118 | Sucesso |
| warning/cloud | #ff6d00 | 255,109,0 | Cloud/warning (laranja TRON) |
| error | #ff1744 | 255,23,68 | Erro (vermelho laser) |

## Mapeamento OS ↔ Web

### Python (theme.py)
```python
BG = "#00050d"
ACCENT = "#00e5ff"
ERROR = "#ff1744"
WARNING = "#ff6d00"  # também usado como RING_CLOUD
```

### CSS (globals.css / tailwind)
```css
:root {
  --color-bg: 0 5 13;
  --color-accent: 0 229 255;
  --color-error: 255 23 68;
  --color-warning: 255 109 0;
}
```

### Tailwind (tailwind.config.ts)
```typescript
colors: {
  cios: {
    500: "#00e5ff",  // accent
    600: "#00b8d4",  // accent-dark
    400: "#40f0ff",  // accent-light
  },
  "surface-dark": {
    0: "#00050d",    // bg
    1: "#000a14",    // bg-secondary
    2: "#001020",    // bg-tertiary
    3: "#001a30",    // bg-hover
  }
}
```

## Animações Compartilhadas

| Nome | Duração | Easing | Uso |
|------|---------|--------|-----|
| fade-in | 250ms | ease-out | Elementos aparecendo |
| slide-up | 300ms | cubic-bezier(0.16,1,0.3,1) | Modais, painéis |
| glow-pulse | 4s | ease-in-out infinite | Indicador AI idle |
| shimmer | 3s | ease-in-out infinite | Loading states |

## Regras de Consistência

1. **Nunca hardcodar cores** — sempre usar tokens (theme.py no OS, CSS vars na web)
2. **Mesma hierarquia visual** — bg < bg-secondary < bg-tertiary para elevação
3. **Accent = interativo** — tudo clicável usa accent como indicador
4. **Glow = estado ativo** — box-shadow com accent indica processamento
5. **Sem bordas sólidas visíveis** — bordas são sempre translúcidas ou accent sutil
6. **Transições em tudo** — nada "snaps", tudo faz transition (mínimo 150ms)
7. **Fundo nunca é preto puro** — sempre tem um toque de azul (#00050d)
