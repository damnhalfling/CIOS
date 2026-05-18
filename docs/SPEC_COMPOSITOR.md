# CIOS Compositor — Spec

> Compositor Wayland próprio para substituir Openbox/X11.
> Branch: `feat/wayland-compositor`

---

## 1. Objetivo

Substituir a stack X11 + Openbox por um compositor Wayland mínimo e purpose-built para o CIOS. O compositor não é um WM genérico — é a camada de display do sistema operacional intent-first.

**O que muda para o usuário:** Nada visível. Mesma experiência. Mais seguro, mais rápido, mais moderno.

**O que muda para o sistema:** Elimina X11, Openbox, wmctrl, xdotool. Controle total sobre rendering, input, e segurança.

---

## 2. Escopo

### Faz

- Renderiza a janela CIOS fullscreen (Tkinter via XWayland ou migração futura)
- Renderiza apps externos (browser, editor, terminal) via XWayland
- Hotkey global (Ctrl+Space → overlay)
- Topbar como layer-shell surface
- Multi-monitor (primário = CIOS, secundário = apps)
- Cursor management
- Session lifecycle (start, crash recovery, logout)
- Boot splash integrado (sem transição entre processos)

### NÃO faz

- Tiling / stacking configurável
- Menus de contexto / dock / taskbar
- Drag & drop entre apps (fase futura se necessário)
- Configuração por arquivo (rc.xml, etc.) — comportamento é hardcoded

---

## 3. Decisões técnicas

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Linguagem | **C** | wlroots é C puro, bindings em outras linguagens são imaturos |
| Biblioteca | **wlroots 0.18+** | Abstrai DRM/KMS, input, XWayland. Padrão da indústria |
| Build system | **Meson** | Padrão do ecossistema wlroots |
| XWayland | **Sim** | Tkinter e muitos apps ainda são X11 |
| Protocolo topbar | **wlr-layer-shell** | Permite surfaces fixas (topbar, overlay) |
| Protocolo hotkey | **wlr-foreign-toplevel** + grab | Captura Ctrl+Space globalmente |
| Rendering | **wlroots scene graph API** | Simplifica composição sem EGL manual |
| Session | **logind / seatd** | Gerencia permissões de GPU/input sem root |

---

## 4. Requisitos funcionais

### 4.1 Boot

```
LightDM → cios-compositor (Exec no .desktop)
  → seta background #0a0a0f
  → renderiza splash (imagem estática ou animação simples)
  → inicia CIOS runtime (Python) como child process
  → quando CIOS sinaliza ready → remove splash
```

### 4.2 Window management

| Cenário | Comportamento |
|---------|--------------|
| CIOS GUI (Tkinter) | Fullscreen, sem decoração, sempre visível |
| App externo (browser) | Maximizado, sem decoração, atrás do CIOS |
| Overlay (Ctrl+Space) | Layer surface acima de tudo |
| Topbar | Layer surface no topo, 32px, sempre visível |
| Diálogo/popup | Centralizado, flutuante, acima do CIOS |

### 4.3 Input

- Teclado: forwarded para surface focada
- Ctrl+Space: interceptado pelo compositor → sinaliza overlay
- Alt+Tab: switch entre CIOS e apps externos
- Alt+F4: fecha app externo (nunca fecha CIOS)
- Super: foca CIOS

### 4.4 Multi-monitor

- Monitor primário: CIOS fullscreen
- Monitor secundário: apps externos (browser, editor)
- Hotplug: detecta conexão/desconexão sem crash

### 4.5 XWayland

- Obrigatório na v1 (Tkinter é X11)
- Apps X11 renderizam via XWayland transparentemente
- Futuro: migrar GUI para toolkit Wayland-nativo (GTK4, ou custom)

### 4.6 Crash recovery

- Se CIOS (Python) crashar → compositor reinicia o processo (como o session script faz hoje)
- Se compositor crashar → logind detecta, LightDM reaparece
- Nunca tela preta permanente

---

## 5. Arquitetura

```
┌─────────────────────────────────────────────────┐
│  cios-compositor (C, ~3000 linhas)               │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ wlroots  │  │ XWayland │  │ layer-shell  │  │
│  │ backend  │  │ server   │  │ (topbar/ovl) │  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │               │          │
│  ┌────▼──────────────▼───────────────▼───────┐  │
│  │           Scene Graph (wlroots)            │  │
│  │  ┌─────────┐ ┌────────┐ ┌──────────────┐  │  │
│  │  │ CIOS    │ │ Apps   │ │ Topbar/Ovl   │  │  │
│  │  │ (full)  │ │ (max)  │ │ (layer)      │  │  │
│  │  └─────────┘ └────────┘ └──────────────┘  │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Input handling (libinput via wlroots)     │  │
│  │  Hotkeys: Ctrl+Space, Alt+Tab, Alt+F4     │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Process manager                           │  │
│  │  - Spawns CIOS Python runtime              │  │
│  │  - Crash recovery (restart on exit != 0)   │  │
│  │  - Splash lifecycle                        │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │
         ▼ DRM/KMS (GPU)
    ┌──────────┐
    │  Display │
    └──────────┘
```

---

## 6. Fases de implementação

### Fase 1 — Compositor mínimo (3-5 dias)

- [ ] Setup projeto C + Meson + dependências wlroots
- [ ] Backend (DRM ou headless para testes)
- [ ] Uma surface fullscreen (cor sólida)
- [ ] Input básico (teclado + mouse forwarded)
- [ ] XWayland funcional (Tkinter abre)
- [ ] Testar: `cios-compositor` inicia, abre xterm dentro

**Entregável:** compositor que roda e aceita janelas X11.

### Fase 2 — CIOS integrado (3-5 dias)

- [ ] Spawn CIOS Python como child process
- [ ] CIOS GUI (Tkinter) aparece fullscreen via XWayland
- [ ] Crash recovery (reinicia Python se exit != 0)
- [ ] Background color #0a0a0f no boot
- [ ] Splash image antes do CIOS carregar

**Entregável:** CIOS roda dentro do compositor como roda hoje no Openbox.

### Fase 3 — Hotkeys + Layer shell (2-3 dias)

- [ ] Ctrl+Space interceptado → sinaliza overlay
- [ ] Alt+Tab → switch focus entre surfaces
- [ ] Alt+F4 → fecha surface focada (exceto CIOS)
- [ ] Super → foca CIOS
- [ ] Layer shell protocol → topbar como surface fixa no topo

**Entregável:** hotkeys funcionam, topbar aparece.

### Fase 4 — Multi-window (3-5 dias)

- [ ] Apps externos (browser, editor) abrem maximizados
- [ ] CIOS fica "atrás" quando app externo tem foco
- [ ] Fechar app externo → CIOS volta ao foco
- [ ] Popups/diálogos flutuam centralizados

**Entregável:** workflow dev_start funciona (abre editor + browser).

### Fase 5 — Multi-monitor (2-3 dias)

- [ ] Detectar outputs via wlroots
- [ ] CIOS no primário, apps no secundário
- [ ] Hotplug (conectar/desconectar monitor)

**Entregável:** multi-monitor funcional.

### Fase 6 — Polimento (3-5 dias)

- [ ] Transição splash → CIOS (fade)
- [ ] Cursor theme
- [ ] Animações de focus (opcional)
- [ ] Session .desktop atualizado
- [ ] Remover dependências X11 do .deb (xorg, openbox, wmctrl, xdotool)
- [ ] Testes em hardware real

**Entregável:** pronto para merge na main.

---

## 7. Integração com o runtime

### O que muda no Python

| Componente | Antes (X11) | Depois (Wayland) |
|-----------|-------------|------------------|
| GUI (Tkinter) | Nativo X11 | XWayland (transparente) |
| wmctrl | Usado em skills | Substituir por IPC com compositor |
| xdotool | Usado em skills | Substituir por IPC com compositor |
| xclip | Clipboard | wl-copy / wl-paste |
| Topbar | Tkinter window | Layer-shell surface (ou manter Tkinter via XWayland) |
| Hotkey overlay | xbindkeys | Compositor intercepta direto |

### IPC compositor ↔ runtime

Protocolo simples via Unix socket ou arquivo:

```
compositor → runtime: {"event": "hotkey", "key": "ctrl+space"}
runtime → compositor: {"command": "focus", "target": "cios"}
runtime → compositor: {"command": "launch", "app": "firefox"}
```

Isso substitui wmctrl/xdotool com controle direto.

### Migração gradual

1. **Fase 1-2:** Tudo via XWayland. Zero mudança no Python.
2. **Fase 3-4:** Adicionar IPC. Skills que usam wmctrl ganham fallback Wayland.
3. **Fase 6:** Remover dependências X11 do .deb.

---

## 8. Dependências de build

```
# Debian/Ubuntu
sudo apt install \
  meson ninja-build \
  libwlroots-dev \
  libwayland-dev \
  libxkbcommon-dev \
  libinput-dev \
  libpixman-1-dev \
  xwayland \
  seatd
```

---

## 9. Estrutura de arquivos

```
cios-os/
├── compositor/              # ← NOVO
│   ├── meson.build          # Build system
│   ├── src/
│   │   ├── main.c           # Entry point + session lifecycle
│   │   ├── server.c         # Compositor core (wlroots setup)
│   │   ├── server.h
│   │   ├── output.c         # Monitor/output management
│   │   ├── input.c          # Keyboard + pointer handling
│   │   ├── xwayland.c       # XWayland integration
│   │   ├── layer_shell.c    # Topbar + overlay surfaces
│   │   ├── hotkeys.c        # Ctrl+Space, Alt+Tab, etc.
│   │   ├── process.c        # Spawn + manage CIOS Python
│   │   └── ipc.c            # Unix socket IPC with runtime
│   └── README.md
├── cios/                    # Runtime Python (sem mudanças iniciais)
├── session/                 # Atualizar .desktop para cios-compositor
└── ...
```

---

## 10. Critérios de merge

A branch `feat/wayland-compositor` só mergeia na main quando:

1. ✅ CIOS GUI funciona fullscreen (via XWayland)
2. ✅ Apps externos abrem e fecham corretamente
3. ✅ Hotkeys funcionam (Ctrl+Space, Alt+Tab, Alt+F4)
4. ✅ Topbar visível
5. ✅ Crash recovery funciona (Python crashar não mata sessão)
6. ✅ Multi-monitor funciona
7. ✅ Testado em hardware real (não só headless)
8. ✅ .deb buildável com compositor incluído

---

## 11. Riscos

| Risco | Mitigação |
|-------|-----------|
| wlroots API muda entre versões | Pinnar versão no meson.build |
| Tkinter não funciona via XWayland | Testar cedo (Fase 1) — se falhar, avaliar alternativa |
| Hardware antigo sem DRM/KMS | Fallback para Openbox (manter como opção) |
| Tempo de desenvolvimento excede estimativa | Fases incrementais — cada fase é funcional sozinha |
| Debugging difícil (crash = tela preta) | Modo headless para testes + logging agressivo |

---

*Spec criada: Maio 2026 — CIOS v1.0.0*
