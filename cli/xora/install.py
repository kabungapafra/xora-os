"""Install any app: one command (or a double-click in Files) for every kind of app.

    xora install FILE         .exe .msi → Windows (Bottles/Wine) · .apk → Android · .deb → Ubuntu container
                              .rpm → Fedora container · .AppImage → your Apps folder · .flatpakref → Flatpak
    xora install NAME         looks it up in the app store (Flathub) and installs it

Apps installed into a container appear in the app menu like any other app. The base OS is never
modified, so an app can't break XORA, and removing one leaves nothing behind.
Windows apps that Wine can't run (Office 365, Adobe, some engineering software): xora apps windows-vm.
"""
import re
import shlex
import shutil
import stat
from pathlib import Path

from .util import bold, die, have, info, ok, out, run, warn

APPS_DIR = Path.home() / "Applications"
DESKTOP_DIR = Path.home() / ".local/share/applications"


def _ensure_box(distro):
    from .apps import _boxes, _distro
    if distro not in _boxes():
        if _distro(distro):
            die(f"couldn't set up the {distro} container")


def _export_new(box, before):
    """Put apps that a package added inside the container into the XORA app menu."""
    after = set(out(["distrobox", "enter", box, "--", "sh", "-c", "ls /usr/share/applications"], timeout=120).split())
    added = sorted(a for a in after - before if a.endswith(".desktop"))
    for d in added:
        run(["distrobox", "enter", box, "--", "distrobox-export", "--app", d[:-len(".desktop")]], capture=True)
    return added


def _appimage(f):
    APPS_DIR.mkdir(exist_ok=True)
    dest = APPS_DIR / f.name
    if f.resolve() != dest.resolve():
        shutil.copy2(f, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    name = re.sub(r"[-_.]?(x86_64|amd64|aarch64|linux|\d[\d.]*).*$", "", dest.stem, flags=re.I) or dest.stem
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    (DESKTOP_DIR / f"xora-appimage-{name.lower()}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\nExec=\"{dest}\" %U\nIcon=application-x-executable\n"
        f"Categories=Utility;\nComment=AppImage in ~/Applications\n")
    ok(f"{name} installed to ~/Applications and added to the app menu")


def cmd_install(a):
    target = a.target
    f = Path(target).expanduser()
    if f.exists():
        ext = "".join(f.suffixes[-1:]).lower()
        if ext in (".exe", ".msi", ".lnk"):
            from .apps import _windows
            return _windows([str(f)])
        if ext == ".apk":
            from .apps import _android
            _android()
            return run(["waydroid", "app", "install", str(f)]).returncode
        if ext == ".deb":
            _ensure_box("ubuntu")
            before = set(out(["distrobox", "enter", "ubuntu", "--", "sh", "-c", "ls /usr/share/applications"], timeout=300).split())
            info(f"installing {f.name} in the Ubuntu container…")
            r = run(["distrobox", "enter", "ubuntu", "--", "sh", "-c",
                     f"sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(str(f.resolve()))}"])
            if r.returncode:
                die("the .deb didn't install (see the messages above)")
            added = _export_new("ubuntu", before)
            ok(f"installed {f.name}" + (f"; in your app menu: {', '.join(x[:-8] for x in added)}" if added else
                                        " (it has no menu entry: run it with `distrobox enter ubuntu -- <command>`)"))
            return
        if ext == ".rpm":
            _ensure_box("fedora")
            before = set(out(["distrobox", "enter", "fedora", "--", "sh", "-c", "ls /usr/share/applications"], timeout=300).split())
            r = run(["distrobox", "enter", "fedora", "--", "sudo", "dnf", "-y", "install", str(f.resolve())])
            if r.returncode:
                die("the .rpm didn't install (see the messages above)")
            added = _export_new("fedora", before)
            ok(f"installed {f.name}" + (f"; in your app menu: {', '.join(x[:-8] for x in added)}" if added else ""))
            return
        if ext == ".appimage":
            return _appimage(f)
        if ext == ".flatpakref":
            return run(["flatpak", "install", "--user", "-y", "--from", str(f)]).returncode
        if ext == ".flatpak":
            return run(["flatpak", "install", "--user", "-y", str(f)]).returncode
        die(f"XORA doesn't know how to install {ext or 'this'} files. Supported: .exe .msi .apk .deb .rpm .AppImage .flatpakref")

    # a name: the app store first
    if not have("flatpak"):
        die("Flatpak isn't installed")
    hits = []
    for line in out(["flatpak", "search", "--columns=name,application", target], timeout=60).splitlines():
        name, _, appid = line.partition("\t")
        if appid.strip():
            hits.append((name.strip(), appid.strip()))
    if not hits:
        warn(f"'{target}' isn't in the app store (Flathub).")
        info(f"Other ways: a Windows installer (.exe) → xora install file.exe · Ubuntu package → "
             f"xora apps ubuntu, then: distrobox enter ubuntu -- sudo apt install {target}")
        return 1
    exact = [h for h in hits if h[0].lower() == target.lower()] or hits
    name, appid = exact[0]
    info(f"installing {bold(name)} ({appid}) from Flathub…")
    return run(["flatpak", "install", "--user", "-y", "flathub", appid]).returncode
