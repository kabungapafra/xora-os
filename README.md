# XORA OS

**Your devices. Your projects. One connected workspace.**

XORA is a real, bootable, image-based operating system. It builds on **Fedora Atomic (bootc) with KDE Plasma** and adds XORA's own identity and features:

## Install

**Hardware:** 64-bit Intel/AMD (x86_64) or ARM64 · 4 GB RAM (8 GB recommended) · 40 GB disk · UEFI.
Secure Boot works out of the box. NVIDIA cards run on the open driver; a `xora-os-nvidia` image with the
proprietary driver (for gaming and CUDA) is planned.

**New machine:** download the ISO (GitHub › Actions › *iso*, or the project's download mirror), write it to a
USB stick (`sudo dd if=xora-os-latest-x86_64.iso of=/dev/sdX bs=4M status=progress`, or Fedora Media Writer /
balenaEtcher) and boot from it. The installer asks for language, disk and your user.

**Already on Fedora Atomic** (Silverblue, Kinoite, Bazzite, Aurora, …): switch in place, keep your files:

```bash
sudo bootc switch ghcr.io/<owner>/xora-os:latest     # or: sudo rpm-ostree rebase ostree-image-signed:docker://ghcr.io/<owner>/xora-os:latest
systemctl reboot
```

**Updates** come by themselves: every night at 2 am (never on metered data) XORA downloads only what changed
in `ghcr.io/<owner>/xora-os:latest`. The previous version stays on disk; if a new one fails to boot three
times it's rolled back automatically, and `xora timeline system --rollback` goes back by hand.
Images are built by GitHub Actions for x86_64 and ARM64 on every change and every week, and signed with
Sigstore: see [SECURITY.md](SECURITY.md) to verify one.

## Licence

GPL-3.0-or-later ([LICENSE](LICENSE)): use it, study it, change it, share it; if you distribute a changed
version, share your changes too. Fedora, KDE and the other included software keep their own licences.
The XORA name and logo are the project's trademarks: forks are welcome under their own name.
Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

What XORA does, and where each part stands:

| Feature | In XORA | How it works |
|---|---|---|
| **Fabric**: devices work as one | ✅ | Link devices with a QR / 6-digit code (XORA Center › Devices). `on office-pc flutter build apk` or `xora fabric run --on auto` sends heavy jobs to the least busy device and brings results back. Linked devices appear in Files like drives (`sftp://`) |
| Device permissions you control | ✅ | Per device: run builds, open Spaces, store backups, share downloads. Change any time in XORA Center, revoke with `xora fabric revoke` |
| **Project Spaces** | ✅ | One command (`xora space open`) brings back code, tools, databases/containers (secrets from the keyring), terminals and windows. `xora space handoff NAME --to DEV` moves it to another device (checkpoint, clean stop, copy code + database volumes, start there; seconds of downtime, not live). `xora space share NAME --with DEV` |
| **Timeline for everything** | ✅ | Files, folders and Spaces are snapshotted; the system keeps its previous version. A restore shows exactly what changes first (line counts, Compare) and never deletes newer work: the current state is saved before any restore |
| **Explain** | ✅ | Desktop cards name the cause from measurements (memory, disk, battery, CPU, network, failed services, data budgets) with buttons that only run when you press them. Failed terminal commands: F2 explains them |
| Terminal with a safety net | ✅ | `rm` snapshots first, `undo` brings files back. After a failed command, F2 re-runs it under Explain. `on <device> <cmd>` runs anything on another device. Terminal: Ptyxis (header bar, tabs, search) |
| Real-world conditions | ✅ | Survives power cuts (checkpoints, clean database stop, hibernate). Per-app data budgets (`xora data --budget firefox 500MB`, blocked at the limit until midnight, "Allow 100 MB more" card). Updates at night, never on metered data. `xora fabric update-cache on`: the office downloads each update once (only linked devices are trusted as caches) |
| Updates can't break it | ✅ | Image-based OS with the previous version kept. greenboot health checks after every update; 3 failed boots roll back automatically (offline boots never count as failures) |
| Apps from everywhere | ✅ | `xora install FILE|NAME` or double-click: Flatpak/Flathub, `.deb` (Ubuntu container), `.rpm` (Fedora container), AppImage, `.apk` (Android/Waydroid), `.exe`/`.msi` (Bottles/Wine). Windows apps Wine can't run: `xora apps windows-vm` runs real Windows 11 in a VM and opens its apps as windows on the XORA desktop (needs KVM, 4 GB RAM and a Windows licence). Not possible on any Linux: games with kernel anti-cheat |
| Files that know where they live | ✅ | Right-click › Where is this file?: device, Space, copies on linked devices (checked live), Timeline versions, Git status. Git status overlays in Files |
| **Privacy** | ✅ | Anon mode (`xora anon on` or the top-bar chip): all traffic through Tor with a kill switch. VPNs: WireGuard, OpenVPN, OpenConnect, L2TP/IPsec, vpnc; `xora vpn import`, always-on, VPN kill switch. **Stealth by default**: every unsolicited packet is dropped (ping included), nothing announces the computer on the network (no mDNS, no KDE Connect broadcasts), SSH is off until you link a Fabric device and then reachable from the local network only, keys only; the pairing port opens only while a code is on screen. No calls home: no connectivity check, no download counter, time from authenticated NTS servers, no Wi-Fi geolocation. Random MAC per network, hostname and stable DHCP IDs not sent, encrypted DNS (DoT), Firefox telemetry off + strict tracking protection, metadata cleaner (mat2), app sandbox (firejail), USBGuard, KeePassXC, Tor Browser, OnionShare, zuluCrypt (encrypted folders and USB sticks, opens VeraCrypt volumes), Signal (`xora tools add signal`). Bluetooth uses a random, changing address |
| Security toolkit | ✅ | Built in, each with its own icon in the app grid: nmap, masscan, Wireshark, tcpdump, hping3, mtr, ncat, socat, dig, whois, dsniff, gobuster, ffuf, john, hashcat, hydra, aircrack-ng, radare2, binwalk, yara, lynis, rkhunter, chkrootkit, ClamAV, trivy. Kali toolset (also in the grid; installed into an isolated container with `xora tools kali`): Metasploit, Burp Suite, sqlmap, nikto, WPScan, SearchSploit, Responder, NetExec, enum4linux, theHarvester, Bettercap, wfuzz, DIRB, SET, hashID, Wifite, Ghidra, Autopsy, plus the rest of Kali with `--full`. Also built in: nuclei, subfinder, dnsx, Sleuth Kit, Kismet. Installed on first click (`xora tools add NAME`): OWASP ZAP, httpx, katana, Volatility 3, SecLists. Full list: `xora tools` |
| DevOps toolkit | ✅ | Podman, buildah, skopeo, podman-compose, kubectl, helm, k9s, OpenTofu, ansible, AWS CLI, gh, jq/yq |
| Local AI | ✅ opt-in | `xora ai enable` (Ollama in a container, localhost only). The model only rephrases measured facts |
| Live migration of running containers | v2 | Handoff is a fast stop-copy-start today; live (CRIU) needs root on both sides |
| Same OS on phones | not planned yet | Needs a Plasma Mobile build for specific phone hardware |
| Independent security audit | not done | Anon mode and the kill switches were tested against the real kernel firewall, but haven't been audited. Don't rely on them where your safety is at stake until they are |

## Layout

```
os/Containerfile        the OS image (FROM fedora-kinoite)
os/files/               files laid over the system: theme, wallpaper, Plymouth, Konsole, zsh, units
os/iso.toml             installer settings (os/iso-vm-test.toml: unattended, for test VMs only)
.github/workflows/      GitHub builds: image for x86_64 + ARM64 (build.yml), installer ISO (iso.yml)
cli/xora/               the `xora` command (Python): spaces, timeline, fabric, explain, secrets
cli/xora/center*.py     XORA Center, the GTK 4 app (Home, Devices, Timeline, first-boot setup)
cli/xora.sh             run xora from source (works on Ubuntu/Fedora today)
build.sh                build the OS image
build-iso.sh            make a bootable installer ISO (needs sudo)
assets/                 logos
prototype/              the earlier browser mock-up of the desktop
```

## Build the OS

```bash
./build.sh                         # → localhost/xora-os:latest  (rootless podman)
./build-iso.sh                     # → output/bootiso/install.iso (asks for sudo)
TYPE=qcow2 ./build-iso.sh          # → a VM disk image instead
```

Write the ISO to a USB stick (`sudo dd if=output/xora-os-0.1-x86_64.iso of=/dev/sdX bs=4M status=progress`, or with Fedora Media Writer / Ventoy / balenaEtcher) and boot from it, or open it in a VM (GNOME Boxes, virt-manager, VirtualBox with EFI on).

### How a machine installed from the ISO gets updates

1. Change the code and `git push` to GitHub.
2. GitHub Actions builds the new image (x86_64 and ARM64), signs it and publishes it as `ghcr.io/<owner>/xora-os:latest` (about 30–40 minutes).
3. Every installed XORA machine checks that image at night (2 am, never on metered data), downloads only the layers that changed, and switches to it on the next restart. The previous version stays on disk for rollback.

There's nothing to set up: `build.sh` writes the repository's GitHub image into the OS as its update source, and on first boot the installed machine switches to it (`xora-image-origin.service`). To update right away instead of waiting for the night: `sudo bootc upgrade && systemctl reboot`. To see where updates come from: `sudo bootc status`. For a private registry, build with `XORA_IMAGE=registry.example.com/xora-os:latest ./build.sh`.

## Use `xora` today, before installing the OS

```bash
ln -s "$PWD/cli/xora.sh" ~/.local/bin/xora     # needs python3 + pyyaml

cd ~/code/attndi && xora space create          # detects git, tools, compose services
xora secret set attndi/postgres_password       # secrets go to your keyring, never the manifest
xora space open attndi                         # repo + tools + containers + terminals + windows
xora up / xora down / xora services
xora rm -rf build/ && xora undo
xora explain -- pytest -q
xora center                                    # the app: Home, Devices, Timeline
xora fabric invite                             # on the office PC: shows a QR + 6-digit code
xora fabric join 123 456                       # on your laptop (same network)
xora fabric run --on auto --get build/ -- flutter build apk
xora privacy · xora data · xora resilience · xora boot
```

### Space manifest (`~/.config/xora/spaces/<name>.yaml`)

```yaml
space: attndi-backend
version: 1
dir: ~/Spaces/attndi-backend
repo: git@github.com:digiflect/attndi.git
branch: main
tools:
  - python: "3.12"
  - flutter: "3.24"
services:
  - name: db
    image: postgres:16
    volume: attndi-db                          # data lives in a named volume
    ports: ["5432:5432"]
    secrets:
      - {env: POSTGRES_PASSWORD, ref: "keyring:attndi-backend/db_password"}
  - name: api
    build: ./backend
    command: uvicorn app.main:app --reload --host 0.0.0.0
    ports: ["8000:8000"]
terminals:
  - {cwd: ./backend, title: backend}
  - {cwd: ./mobile}
layout:
  windows: [code, "http://localhost:8000/docs"]
checkpoints: timeline://attndi-backend
build_cmd: flutter build apk                   # XORA Center's "Build on <device>" runs this via Fabric
share: true                                    # devices allowed to "open my Spaces" get this Space
```

Services run in Podman on a private network per Space, so they reach each other by name (`db:5432`). If `mise` is installed, XORA installs the listed tool versions itself.

## Release-critical checks before calling v1 done

- [ ] ISO installs and boots on real hardware and in a VM
- [ ] `bootc upgrade` followed by `bootc rollback` works
- [ ] A Space comes back after a reboot, and `space open` recovers from an interrupted setup
- [ ] Timeline restores without touching unrelated or newer files
- [ ] Fabric pairing and revoking work, and a remote build falls back cleanly when the device drops
- [ ] Core features work offline
- [ ] Memory and boot time are measured on a 4 GB machine
