# CIOS Live ISO Build System

Produces a bootable hybrid ISO image based on Debian bookworm using `live-build`. The ISO boots directly into the CIOS desktop with zero user interaction.

## Prerequisites

- **OS**: Debian/Ubuntu (live-build is Debian-specific)
- **Packages**: `live-build`, `debootstrap`, `dpkg-dev`
- **Privileges**: Root access (chroot operations require root)
- **Disk space**: At least 10 GB free
- **Network**: Required for downloading packages during build

Install dependencies:

```bash
sudo apt install live-build debootstrap dpkg-dev
```

## Building Locally

```bash
sudo ./live-build/build-iso.sh
```

Or with a specific version:

```bash
sudo ./live-build/build-iso.sh 1.1.0
```

The script will:
1. Build the CIOS `.deb` package via `build-deb.sh`
2. Configure live-build via `auto/config`
3. Build the ISO (~15-30 minutes)
4. Output `cios-{version}-amd64.iso`

## CI/CD (GitHub Actions)

The ISO is built automatically when a tag matching `v*.*.*-iso` is pushed:

```bash
git tag -a v1.1.0-iso -m "Live ISO release"
git push origin v1.1.0-iso
```

The workflow builds the ISO and uploads it as a GitHub Release artifact.

## Testing with QEMU

```bash
qemu-system-x86_64 \
    -cdrom cios-1.1.0-amd64.iso \
    -m 2G \
    -enable-kvm \
    -boot d
```

## Writing to USB

```bash
sudo dd if=cios-1.1.0-amd64.iso of=/dev/sdX bs=4M status=progress
sync
```

⚠️ Replace `/dev/sdX` with your actual USB device. Double-check with `lsblk`.

## Directory Structure

```
live-build/
├── README.md                    # This file
├── build-iso.sh                 # Build orchestrator (entry point)
├── .gitignore                   # Ignores build artifacts
├── auto/
│   └── config                   # live-build auto-configuration
└── config/
    ├── package-lists/
    │   └── cios.list.chroot     # Packages to install
    ├── hooks/
    │   └── live/
    │       ├── 0100-install-cios-deb.hook.chroot   # Install CIOS .deb
    │       ├── 0200-configure-user.hook.chroot     # Create live user
    │       ├── 0300-configure-autologin.hook.chroot # LightDM autologin
    │       ├── 0400-configure-boot.hook.chroot     # Silent boot chain
    │       └── 0500-generate-manifest.hook.chroot  # Package manifest
    └── includes.chroot/
        └── usr/local/bin/
            └── install-cios     # Permanent installer
```

## Boot Chain

```
BIOS/UEFI → GRUB (hidden) → Kernel (silent) → Plymouth (CIOS logo) → LightDM (autologin) → CIOS Desktop
```

## Compatibility

- ✅ UEFI boot (Secure Boot disabled)
- ✅ Legacy BIOS boot
- ✅ USB media (via `dd`)
- ✅ DVD media (via optical drive)

## Troubleshooting

**Build fails with "lb: command not found"**
→ Install `live-build`: `sudo apt install live-build`

**Build fails with permission errors**
→ Must run as root: `sudo ./live-build/build-iso.sh`

**ISO too large (>1.5 GB)**
→ Check package list for unnecessary packages. The `--apt-recommends false` flag should keep size minimal.

**Build logs**
→ Check `live-build/.build/` directory for detailed logs on failure.
