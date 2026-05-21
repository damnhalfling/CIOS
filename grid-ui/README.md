# CIOS Shell — The Grid Interface

Wayland shell overlay inspirado em TRON: Legacy para o CIOS OS.

## Conceito

Interface intent-first onde não existem janelas tradicionais. Elementos visuais emergem como formas geométricas de luz que comunicam estado do sistema.

### Elementos Visuais

| Elemento | Função |
|----------|--------|
| Identity Disc | Estado do runtime (idle/listening/cloud/error) |
| Grid Background | Plano infinito com linhas de dados pulsantes |
| Rez-in | Materialização de elementos (scan-line bottom-up) |
| Derezz | Dissolução em partículas geométricas |

### Paleta de Cores

| Cor | Hex | Significado |
|-----|-----|-------------|
| Ciano | `#00E5FF` | Local/idle/seguro |
| Laranja | `#FF6D00` | Cloud intelligence ativa |
| Vermelho | `#FF1744` | Erro/alerta de segurança |
| Fundo | `#00050D` | Espaço digital profundo |

## Build

```bash
# Dependências (Ubuntu/Debian)
sudo apt install libwayland-dev libvulkan-dev libxkbcommon-dev wayland-protocols pkg-config

# Compilar
cargo build --release

# Rodar (precisa de compositor Wayland com layer-shell)
RUST_LOG=info ./target/release/cios-shell
```

## .deb

O `.deb` é gerado automaticamente via GitHub Actions em push para `main` ou em tags `v*`.

Para instalar o artefato:
```bash
sudo dpkg -i cios-shell_0.1.0_amd64.deb
```

## Requisitos

- Compositor Wayland com suporte a `wlr-layer-shell` (Sway, Hyprland, etc.)
- GPU com drivers Vulkan
- Linux x86_64

## Arquitetura

```
src/
├── main.rs           # Entry point
├── compositor.rs     # Wayland client (layer-shell)
├── renderer.rs       # wgpu render pipeline
├── state.rs          # State machine (Idle/Listening/Cloud/Error)
├── animation.rs      # Easing, transitions, timing
├── identity_disc.rs  # Disc uniforms
├── grid.rs           # Grid background uniforms
├── transitions.rs    # Rez-in/Derezz uniforms
└── shaders/
    ├── mod.rs        # Shader module loader
    ├── grid.wgsl     # Background grid shader
    ├── disc.wgsl     # Identity disc shader
    └── derezz.wgsl   # Transition effects shader
```

## Roadmap

- [ ] wgpu rendering integrado com wayland surface
- [ ] Keyboard shortcuts para alternar estados (demo)
- [ ] Input de voz → transição de estado
- [ ] Fluxos de execução vetoriais (nós de task)
- [ ] Integração com CIOS runtime (D-Bus/socket)
