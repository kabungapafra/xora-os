"""Apps from everywhere: Linux (Flatpak), other distros (Ubuntu, Debian, Arch), Windows and Android.

    xora apps                        what's set up
    xora apps android                set up Android apps (Waydroid); then double-click any .apk
    xora apps android install X.apk
    xora apps windows                set up Windows apps (Bottles, a Wine manager); then double-click any .exe
    xora apps ubuntu|debian|arch|fedora     a container of that distro; `xora apps export <distro> <app>` puts its app in your menu
    xora apps windows-vm [run "C:\\path\\app.exe" | desktop | stop]
                                     real Windows 11 in a VM for apps Wine can't run (Office 365, Adobe, …);
                                     its apps open in their own windows on the XORA desktop

Each one is set up only when you ask, so the OS stays small. Nothing here changes the base system.
"""
import shutil
import subprocess

from .util import bold, cyan, die, dim, green, have, info, ok, out, run, warn

DISTROS = {"ubuntu": "docker.io/library/ubuntu:24.04", "debian": "docker.io/library/debian:stable",
           "arch": "docker.io/library/archlinux:latest", "fedora": "registry.fedoraproject.org/fedora-toolbox:44"}
BOTTLES = "com.usebottles.bottles"


def _boxes():
    if not have("distrobox"):
        return set()
    return {line.split("|")[1].strip() for line in out(["distrobox", "list", "--no-color"], timeout=30).splitlines()[1:]
            if line.count("|") >= 2}


def _waydroid_ready():
    return have("waydroid") and "Session" in out(["waydroid", "status"], timeout=10) and \
        "not initialized" not in out(["waydroid", "status"], timeout=10).lower()


def _bottles():
    return have("flatpak") and BOTTLES in out(["flatpak", "list", "--app", "--columns=application"], timeout=30)


def cmd_apps(a):
    what = a.what
    if what == "android":
        if a.args and a.args[0] == "install":
            if len(a.args) < 2:
                die("usage: xora apps android install app.apk")
            return run(["waydroid", "app", "install", a.args[1]]).returncode
        return _android()
    if what == "windows":
        return _windows(a.args)
    if what == "windows-vm":
        return _windows_vm(a.args)
    if what in DISTROS:
        return _distro(what)
    if what == "export":
        if len(a.args) < 2:
            die("usage: xora apps export <distro> <app>   (e.g. xora apps export ubuntu gimp)")
        box, app = a.args[0], a.args[1]
        return run(["distrobox", "enter", box, "--", "distrobox-export", "--app", app]).returncode
    boxes = _boxes()
    rows = [("Linux (Flatpak)", have("flatpak"), "Discover, or: flatpak install flathub <app>"),
            ("Android", _waydroid_ready(), "xora apps android"),
            ("Windows", _bottles(), "xora apps windows")]
    rows += [(d.capitalize(), d in boxes, f"xora apps {d}") for d in DISTROS]
    for name, ready, how in rows:
        print(f"  {green('✓') if ready else dim('·')} {name:18} {dim('ready' if ready else 'set up with: ' + how)}")


def _as_root(argv):
    import sys
    if sys.stdin.isatty() and shutil.which("sudo"):
        return run(["sudo", *argv]).returncode
    return run(["pkexec", *argv]).returncode      # desktop password prompt


def _android():
    if not have("waydroid"):
        die("Waydroid isn't installed")
    if not _waydroid_ready():
        info("Setting up Android (downloads the Android system image once, about 1 GB)…")
        if _as_root(["waydroid", "init"]) != 0:
            die("Android setup didn't finish; run `xora apps android` again to continue")
        _as_root(["systemctl", "enable", "--now", "waydroid-container.service"])
    ok("Android apps are ready. Double-click an .apk to install it, or: xora apps android install app.apk")
    info("Android apps appear in your app menu once installed. Full Android screen: waydroid show-full-ui")


def _windows(args):
    if not have("flatpak"):
        die("Flatpak isn't installed")
    if not _bottles():
        info("Installing Bottles (runs Windows programs with Wine, each in its own sandbox)…")
        r = run(["flatpak", "install", "--user", "-y", "flathub", BOTTLES])
        if r.returncode != 0:
            die("couldn't install Bottles from Flathub; check the internet connection and try again")
    if args:
        return run(["flatpak", "run", BOTTLES, *args]).returncode
    ok("Windows apps are ready. Double-click an .exe or .msi to run it, or open Bottles from the app menu.")


def _distro(name):
    if not have("distrobox"):
        die("distrobox isn't installed")
    if name not in _boxes():
        info(f"Creating a {name.capitalize()} container ({DISTROS[name]}); it shares your home folder…")
        r = run(["distrobox", "create", "--yes", "--name", name, "--image", DISTROS[name]])
        if r.returncode != 0:
            die(f"couldn't create the {name} container")
    ok(f"{name.capitalize()} is ready. Install apps inside it (distrobox enter {name}), then put one in your menu with:")
    print(f"    {cyan(f'xora apps export {name} <app>')}")



# ================================================================ real Windows, for apps Wine can't run

WIN_CT = "xora-windows"
WIN_IMAGE = "docker.io/dockurr/windows:latest"
WIN_USER = "xora"
WIN_SECRET = "windows-vm/password"


def _win_password():
    """The VM's password: generated once, kept in your keyring (never a default password)."""
    from .vault import resolve
    try:
        pw = resolve(f"keyring:{WIN_SECRET}")
    except RuntimeError:            # not created yet
        pw = None
    if not pw:
        import secrets as _s
        pw = _s.token_urlsafe(14)
        r = subprocess.run(["secret-tool", "store", "--label", "XORA Windows VM", "xora", WIN_SECRET], input=pw, text=True)
        if r.returncode:
            die("couldn't save the Windows VM password in your keyring")
    return pw


def _windows_vm(args):
    from pathlib import Path
    sub = args[0] if args else "start"
    if sub == "stop":
        return run(["podman", "stop", "-t", "120", WIN_CT]).returncode
    running = WIN_CT in out(["podman", "ps", "--format", "{{.Names}}"], timeout=30).split()
    if sub in ("start",) or not running:
        if not Path("/dev/kvm").exists():
            die("this computer's hardware virtualisation (KVM) is off, so Windows can't run in a VM. "
                "Turn on Intel VT-x / AMD-V in the BIOS (and make sure KVM isn't blacklisted)")
        if not have("podman"):
            die("podman isn't installed")
        pw = _win_password()
        oem = Path.home() / ".local/share/xora/windows-oem"
        oem.mkdir(parents=True, exist_ok=True)
        # runs once inside Windows after setup: allow apps to open as their own windows (RDP RemoteApp)
        (oem / "install.bat").write_text(
            '@echo off\r\n'
            'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Terminal Server\\TSAppAllowList" '
            '/v fDisabledAllowList /t REG_DWORD /d 1 /f\r\n'
            'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp" '
            '/v SecurityLayer /t REG_DWORD /d 2 /f\r\n')
        exists = WIN_CT in out(["podman", "ps", "-a", "--format", "{{.Names}}"], timeout=30).split()
        if not exists:
            info("Creating the Windows VM: Windows 11 downloads (~6 GB) and installs by itself, about 30-60 minutes the first time.")
            info("You need a Windows licence to keep using it after the evaluation period.")
            r = run(["podman", "run", "-d", "--name", WIN_CT, "--device", "/dev/kvm", "--device", "/dev/net/tun",
                     "--cap-add", "NET_ADMIN", "--stop-timeout", "120",
                     "-p", "127.0.0.1:8006:8006", "-p", "127.0.0.1:3389:3389/tcp", "-p", "127.0.0.1:3389:3389/udp",
                     "-v", "xora-windows:/storage", "-v", f"{oem}:/oem:Z",
                     "-e", "VERSION=11", "-e", "RAM_SIZE=4G", "-e", "CPU_CORES=2", "-e", "DISK_SIZE=64G",
                     "-e", f"USERNAME={WIN_USER}", "-e", f"PASSWORD={pw}", WIN_IMAGE])
        else:
            r = run(["podman", "start", WIN_CT])
        if r.returncode:
            die("couldn't start the Windows VM")
        ok("Windows VM is running. Watch it install at http://127.0.0.1:8006 (only this computer can reach it).")
        if sub == "start":
            info('Then run a Windows app: xora apps windows-vm run "C:\\Program Files\\...\\app.exe"   ·   whole desktop: xora apps windows-vm desktop')
            return
    pw = _win_password()
    rdp = shutil.which("xfreerdp") or shutil.which("sdl-freerdp") or shutil.which("wlfreerdp")
    if not rdp:
        die("FreeRDP isn't installed")
    base = [rdp, "/v:127.0.0.1", f"/u:{WIN_USER}", f"/p:{pw}", "/cert:ignore", "+clipboard", "/dynamic-resolution",
            f"/drive:home,{Path.home()}", "/sound"]
    if sub == "desktop":
        return subprocess.Popen(base, start_new_session=True) and 0
    if sub == "run":
        if len(args) < 2:
            die('usage: xora apps windows-vm run "C:\\path\\to\\app.exe"')
        return subprocess.Popen(base + [f"/app:program:{args[1]}"], start_new_session=True) and 0
    die("usage: xora apps windows-vm [start|run PATH|desktop|stop]")
