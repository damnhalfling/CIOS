# CIOS Live ISO

Bootable live ISO image with CIOS pre-installed.

## Boot Chain

```
Power On → GRUB (0s, invisible) → Plymouth (CIOS logo) → greetd (login) → CIOS Desktop
```

- **GRUB**: Hidden, 0s timeout, dark background (#0a0a0f). Only shows on boot failure (2s).
- **Plymouth**: CIOS logo animation, same dark background. Starts instantly via KMS in initramfs.
- **greetd**: Wayland-native display manager. Launches cios-shell with GTK4 greeter.
- **CIOS Desktop**: Full Wayland compositor with intent-first interface.

## Build

### Prerequisites

```bash
sudo apt install live-build debootstrap dpkg-dev meson ninja-build \
  pkg-config libwayland-dev wayland-protocols libxkbcommon-dev \
  libinput-dev libpixman-1-dev libdrm-dev libseat-dev patchelf
```

### Build ISO

```bash
sudo ./build-iso.sh 1.1.0-rc16
```

Takes 15-30 minutes. Output: `cios-1.1.0-rc16-amd64.iso`

### Test in QEMU

```bash
qemu-system-x86_64 -cdrom cios-1.1.0-rc16-amd64.iso -m 4G -enable-kvm \
  -device virtio-vga -display gtk \
  -net nic -net user,hostfwd=tcp::2222-:22
```

### Write to USB

```bash
sudo dd if=cios-1.1.0-rc16-amd64.iso of=/dev/sdX bs=4M status=progress
```

## Live Session

- **User**: `cios`
- **Password**: `cios`
- **Sudo**: passwordless (NOPASSWD)
- **SSH**: enabled on port 22

## Structure

```
live-build/
├── auto/config              # lb config parameters (Debian trixie, hybrid ISO)
├── build-iso.sh             # Main build orchestrator
├── config/
│   ├── hooks/live/          # Chroot hooks (run during build)
│   │   ├── 0100-install-cios-deb    # Install .deb + verify
│   │   ├── 0200-configure-user      # Create cios user + groups
│   │   ├── 0300-configure-autologin # greetd + seatd + getty mask
│   │   ├── 0400-configure-boot      # GRUB + Plymouth + initramfs + KMS
│   │   └── 0500-generate-manifest   # Package list for reproducibility
│   ├── includes.chroot/     # Files copied into the live filesystem
│   └── package-lists/       # Packages to install
│       └── cios.list.chroot
└── README.md
```

## CI/CD

Push a tag `v*-iso` to trigger automatic ISO build:

```bash
git tag v1.1.0-rc16-iso
git push origin v1.1.0-rc16-iso
```

The GitHub Actions workflow builds the ISO and uploads it as a release asset.
