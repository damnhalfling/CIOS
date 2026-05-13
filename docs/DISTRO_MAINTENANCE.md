# CIOS — Manutenção da Distribuição

> CIOS como sistema operacional percebido (como Ubuntu ou iOS).
> O Debian é infraestrutura invisível. O usuário vê CIOS.
> Atualizado: Maio 2026 — v1.1.0-rc5

---

## Arquitetura atual

```
┌─────────────────────────────────────────────┐
│  CIOS (o que o usuário vê)                  │
│  ├── cios-shell (compositor Wayland/wlroots)│
│  ├── cios runtime (Python, intent engine)   │
│  ├── greetd + agreety (login)               │
│  ├── Plymouth (boot splash)                 │
│  └── cios-setup-ai (Ollama, Whisper, Piper) │
├─────────────────────────────────────────────┤
│  Debian (infraestrutura invisível)          │
│  ├── kernel Linux                           │
│  ├── systemd                                │
│  ├── apt/dpkg                               │
│  ├── glibc, drivers, firmware               │
│  └── security patches automáticos           │
└─────────────────────────────────────────────┘
```

---

## Stack de sessão

| Componente | Função | Pacote |
|-----------|--------|--------|
| GRUB | Bootloader (invisível, 0s timeout) | grub-efi / grub-pc |
| Plymouth | Boot splash (logo CIOS) | plymouth + tema custom |
| greetd | Display manager (Wayland-native) | greetd |
| agreety | Greeter (login texto, futuro: gráfico) | vem com greetd |
| seatd | Seat manager (acesso DRM/input) | seatd |
| cios-session | Script de sessão | /usr/local/bin/cios-session |
| cios-shell | Compositor Wayland (wlroots 0.18) | /usr/bin/cios-shell |
| CIOS runtime | Engine de intenção (Python) | /usr/share/cios/ |

---

## Libs bundled (/usr/lib/cios/)

O cios-shell depende de libs que não estão nos repos padrão do Debian.
São bundled no .deb e isoladas via RPATH (não poluem o sistema).

Capturadas automaticamente via `ldd` no build. Inclui:
- libwlroots-0.18.so
- libwayland-server/client 1.23
- libdisplay-info
- libliftoff
- libxcb-* (render-util, ewmh, etc.)
- libGLESv2, libEGL, libgbm

**Importante:** Essas libs NÃO usam ldconfig global. Só o cios-shell as vê (via RPATH).

---

## O que o Debian faz por nós (não manter)

- Kernel Linux (updates de segurança)
- Drivers GPU (i915, amdgpu, nouveau)
- Firmware (WiFi, Bluetooth)
- glibc, openssl, systemd
- NetworkManager, PipeWire
- Python 3.x runtime
- Pacotes base (coreutils, bash, etc.)

---

## O que NÓS mantemos

| Componente | Responsabilidade | Frequência |
|-----------|-----------------|-----------|
| cios-shell | Adaptar a novas APIs wlroots | A cada release wlroots |
| Libs bundled | Rebuildar quando wlroots atualiza | Junto com cios-shell |
| CIOS runtime | Features, bug fixes, skills | Contínuo |
| greetd config | Garantir que funciona após updates | A cada major Debian |
| Plymouth tema | Manter compatível | Raro |
| build-deb.sh | Adaptar a mudanças de paths/deps | A cada major Debian |
| CI/CD | Manter workflow funcional | Contínuo |

---

## Acompanhamento por release do Debian

### Point releases (13.4 → 13.5)

**Risco:** Baixo. Geralmente só security patches.

**Ação:**
1. Testar em VM com `apt upgrade`
2. Verificar se cios-shell ainda inicia
3. Se ok, nenhuma ação necessária

### Major releases (13 → 14)

**Risco:** Alto. Muda glibc, Python, libs de sistema.

**Ação obrigatória:**
1. Rebuildar cios-shell contra novas libs
2. Testar venv Python (versão pode mudar)
3. Verificar greetd/seatd (podem mudar de pacote)
4. Atualizar CI para nova base image
5. Testar instalação limpa do .deb
6. Lançar nova versão do CIOS para o novo Debian

**Timeline:** Debian major sai a cada ~2 anos. Próximo: Debian 14 (Forky) ~2027.

---

## Riscos e mitigações

### wlroots API break (0.18 → 0.19)

**Impacto:** cios-shell não compila.
**Mitigação:** Travar na versão 0.18 até decidir migrar. Libs bundled isolam do sistema.
**Ação:** Quando migrar, adaptar código C em shell/src/*.c.

### Nvidia

**Impacto:** Compositor não inicia (DRM/EGL incompatível).
**Decisão atual:** Não suportar Nvidia. Só Intel/AMD (mesa drivers).
**Futuro:** Se demanda crescer, testar com `nvidia-drm modeset=1`.

### Python version bump

**Impacto:** Venv pode quebrar, python3-tk pode mudar de pacote.
**Mitigação:** postinst recria venv a cada instalação. Resiliente.

### greetd removido dos repos

**Impacto:** Instalação falha (dependência não encontrada).
**Mitigação:** Bundlar greetd no .deb ou manter PPA próprio.

### Segurança das libs bundled

**Impacto:** Vulnerabilidade em libwayland/wlroots não é patchada automaticamente.
**Mitigação:** Monitorar CVEs de wlroots/wayland. Rebuildar quando necessário.
**Futuro:** PPA próprio com versões mantidas.

---

## Componentes de IA (opcionais, pós-login)

Instalados via `sudo cios-setup-ai`:

| Componente | Tamanho | Função |
|-----------|---------|--------|
| Ollama | ~500MB | Runtime de LLM local |
| Mistral | ~4GB | Modelo de linguagem |
| Whisper | ~1GB | Speech-to-text |
| Piper | ~100MB | Text-to-speech |

**Decisão:** Não bloquear instalação do OS. Instalar após primeiro login.
**Motivo:** Download de ~6GB durante dpkg trava a instalação.

---

## Para parecer um OS (não um pacote)

### Já implementado ✅
- Plymouth boot splash customizado
- GRUB invisível (0s timeout)
- Login via greetd (sem desktop environment visível)
- Compositor próprio (não usa GNOME/KDE/Openbox)
- Instalador com modo "substituição completa"

### Próximos passos
- [ ] Customizar /etc/os-release (mostrar "CIOS" não "Debian")
- [ ] Greeter gráfico (trocar agreety por greeter Wayland visual)
- [ ] Update mechanism na UI ("CIOS 1.2 disponível")
- [ ] ISO de instalação própria (live-build)
- [ ] First-boot wizard ("Bem-vindo ao CIOS")
- [ ] Recovery mode no GRUB ("CIOS Recovery")
- [ ] Esconder terminal do usuário comum (modo avançado)

---

## Comandos úteis de manutenção

```bash
# Rebuildar .deb
bash build-deb.sh 1.1.0-rc5

# Testar em VM (QEMU)
qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm \
  -drive file=~/cios-test.qcow2,format=qcow2 \
  -device virtio-vga-gl -display gtk,gl=on \
  -net nic -net user,hostfwd=tcp::2222-:22

# Instalar na VM via SSH
ssh -p 2222 user@localhost
sudo apt install ./cios_1.1.0-rc5_amd64.deb

# Verificar sessão
cat ~/.cios/session.log
systemctl status greetd

# Instalar componentes de IA
sudo cios-setup-ai
```

---

*Atualizado: Maio 2026 — v1.1.0-rc5*
