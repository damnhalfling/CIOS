# CIOS — Desenvolvimento

> v3.0.0-rc14 — Junho 2026

---

## Branching & Release

| Branch | Propósito | Merge |
|--------|-----------|-------|
| `main` | Versão estável. Só recebe merges aos domingos. | Tag `vX.Y.Z` |
| `dev` | Desenvolvimento diário. RC (release candidate). | → main (domingo) |
| `feat/*` | Features isoladas. | → dev |

### Fluxo

```
feat/xyz → dev (diário)
dev → main (domingo, após validação)
main → tag vX.Y.Z → .deb release
```

### Versionamento

- MAJOR: mudança de paradigma
- MINOR: nova feature ou mudança significativa
- PATCH: bugfix ou polimento

### Regra de horário (Git Schedule)

| Horário | Repo público | Local |
|---------|-------------|-------|
| Antes 19h | ❌ Sem push/commit | ✅ Livre |
| Após 19h | ✅ Livre | ✅ Livre |

---

## CI/CD

Pipeline (`.github/workflows/build-deb.yml`):

```
Tag push → Lint (ruff + mypy) → Test (pytest) → Build compositor → Build .deb → GitHub Release
```

| Trigger | Release |
|---------|---------|
| Tag `v1.2.0` na `main` | Stable (limpa releases anteriores) |
| Tag `v1.2.0-rc1` na `dev` | Pre-release (limpa RCs anteriores) |

### Lint
- `ruff check cios/ tests/` — E/F/W/I/UP/B/SIM rules, 100-char line
- `ruff format --check cios/ tests/`
- `mypy cios/core/` — exclui intent_parser, mcp, intelligence, bridge

### Testes
- `pytest --cov=cios` — threshold 45%
- 839 testes, property-based (Hypothesis)
- Timeout: 30s por teste

---

## Módulos recentes (Sprint 3)

### History Sync (`core/thread_manager.py`)
- `ThreadStore.full_sync()` — bidirecional (push + pull)
- `ThreadStore._merge_cloud_thread()` — importa threads do web
- `ThreadStore._contains_sensitive_content()` — auto-marca local_only
- Periodic sync: daemon thread no bridge (5 min interval)
- DB migration automática (`_migrate()`) para colunas novas

### Search Overlay (`ui/gtk/search_overlay.py`)
- Ctrl+K via compositor IPC ou GTK EventControllerKey (fallback)
- Debounce 300ms, resultados live, Escape para fechar
- Integra com `ThreadStore.search()` (LIKE match)

### IPC Events
- `ipc_listener.py` agora despacha: `ctrl+space`, `ctrl+k`, `logout_requested`
- Compositor envia `key_intercepted` com key name

---

## Manutenção da distribuição

### O que o Debian faz (não manter)
- Kernel, drivers GPU, firmware, glibc, openssl, systemd
- NetworkManager, PipeWire, Python 3.x, pacotes base

### O que NÓS mantemos

| Componente | Frequência |
|-----------|-----------|
| cios-shell | A cada release wlroots |
| Libs bundled | Junto com cios-shell |
| CIOS runtime | Contínuo |
| greetd config | A cada major Debian |
| Plymouth tema | Raro |
| build-deb.sh | A cada major Debian |
| CI/CD | Contínuo |

### Riscos conhecidos

| Risco | Mitigação |
|-------|-----------|
| wlroots API break (0.18 → 0.19) | Travar na 0.18, libs bundled isolam |
| Nvidia | Não suportado. Só Intel/AMD (mesa) |
| Python version bump | postinst recria venv |
| greetd removido dos repos | Bundlado no .deb |
| CVE em libs bundled | Monitorar, rebuildar quando necessário |

### Debian major release (13 → 14, ~2027)
1. Rebuildar cios-shell contra novas libs
2. Testar venv Python
3. Verificar greetd/seatd
4. Atualizar CI base image
5. Testar instalação limpa

---

## Dependências

### Runtime
```
prompt_toolkit==3.0.48, rich==13.9.4, psutil==6.1.1
Pillow>=10.0.0, qrcode>=7.4, requests>=2.31
beautifulsoup4>=4.12, pymupdf>=1.23
```

### Sistema (core)
```
foot (terminal), wl-clipboard, ollama, nmcli, sudo
python3-gi, gir1.2-gtk-4.0, greetd, seatd, plymouth-themes
```

### Dev
```
ruff==0.8.6, pre-commit==4.0.1, mypy==1.14.1
pytest==8.3.4, pytest-cov==6.0.0, pytest-timeout==2.3.1, hypothesis==6.100.0
```

---

## Comandos úteis

```bash
# Rodar testes
pytest tests/ -q --timeout=30

# Lint
ruff check cios/ tests/
ruff format --check cios/ tests/

# Type check (como CI)
mypy cios/core/ --ignore-missing-imports --exclude "(intent_parser|mcp|intelligence|bridge)\.py"

# Build .deb
bash build-deb.sh 3.0.0-rc14

# Testar em VM (QEMU)
qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm \
  -drive file=~/cios-test.qcow2,format=qcow2 \
  -device virtio-vga-gl -display gtk,gl=on \
  -net nic -net user,hostfwd=tcp::2222-:22

# Instalar na VM
ssh -p 2222 user@localhost
sudo apt install ./cios_3.0.0-rc14_amd64.deb

# Instalar componentes de IA
sudo cios-setup-ai
```
