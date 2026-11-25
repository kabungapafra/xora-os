# XORA OS

A working build of the XORA OS desktop concept: boot screen, first-boot setup, desktop with Spaces, dock, launcher, window manager, a Kali-style terminal, Files, Timeline, Fabric and Settings.

## Run it

Open `index.html` in Chrome or Firefox (no server or build step needed). Add `?fast` to the URL to skip the boot animation.

Everything you do is saved in the browser (localStorage). Settings → Reset XORA starts over from first-boot setup.

## Keys

| Key | Action |
|---|---|
| Ctrl+Alt+T | New terminal |
| Ctrl+Space | Launcher (apps, Spaces, files, commands, questions) |
| F2 | Run the fix XORA suggested in the terminal |
| Tab / ↑ ↓ | Complete / history in the terminal |
| Delete | Delete the selected item in Files (saved to Timeline first) |

## Terminal demo

```
pytest                    # fails, [xora explain] says why → press F2
rm -rf build/             # 1,284 files, snapshot saved first
xora undo                 # brings them back
# why is the api slow?    # ask in plain words
xora fabric run flutter build apk --on office-pc
sudo su                   # Kali root look (red user, #)
neofetch
```

## Layout

```
index.html        screens: boot, setup, desktop
css/xora.css      theme (navy #0F0E1E, cyan #1EC8F0, logo gradient #1ED4F2 → #0A7CF0)
js/logo.js        logo path data (from XORA_logo_v2.svg)
js/kernel.js      state, virtual file system, Spaces, Timeline snapshots, Fabric jobs
js/wm.js          window manager
js/terminal.js    terminal
js/apps.js        Home, Files, Timeline, Fabric, Settings
js/boot.js        boot, setup, top bar, dock, launcher
assets/           logo SVG/PNG files
```

## Path to a real, bootable OS

1. Base on Debian (like Kali), built with `live-build` into an ISO.
2. Run this shell full-screen as the desktop session (a Tauri or Electron kiosk app started by a Wayland compositor such as `cage`).
3. Swap the simulated parts for real ones: terminal → real shell through a PTY (xterm.js + node-pty), virtual file system → real files, Timeline → Btrfs snapshots, Fabric → SSH or a small agent on each device, `# questions` → the local AI model (`xora ai`).
