# Contributing to XORA OS

Thanks for helping. XORA is GPL-3.0-or-later: your contributions are shared under the same licence.

## Run it

```bash
./cli/xora.sh help                 # the xora command runs from source on any Linux (python3 + pyyaml)
./build.sh                         # build the OS image (podman)
TYPE=anaconda-iso ./build-iso.sh   # installer ISO (needs sudo)
```

## Layout

- `cli/xora/` – the `xora` command and XORA Center (Python, GTK 4)
- `os/Containerfile` – the OS image (Fedora Atomic / bootc + KDE Plasma)
- `os/files/` – files laid over the system: theme, widgets, services, privacy and performance settings

## Rules of thumb

- **Measure, don't guess.** Explain cards and `xora ask` state facts the system measured; the optional AI only rephrases them.
- **Never lose work.** Anything that deletes or overwrites saves a Timeline snapshot first.
- **Nothing runs without consent.** Fixes are offered as buttons; privacy-relevant changes ask for the password.
- **Works offline and on expensive data.** No feature may require the internet to keep the machine usable.
- **Keep the base small.** Big or fast-changing tools go in containers (`xora tools`, `xora apps`).

## Before a pull request

```bash
python3 -m py_compile cli/xora/*.py
for c in "" space fabric timeline explain data anon vpn tools apps install speed where; do ./cli/xora.sh $c --help >/dev/null; done
```

The GitHub build runs these checks and builds the image for x86_64 and ARM64.

The XORA name and logo are trademarks of the project: forks are welcome under a different name.
