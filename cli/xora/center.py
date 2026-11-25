"""XORA Center: the desktop app for Home, Devices (pairing) and Timeline (restore preview).

    xora center                 Home
    xora center pair            Devices: QR / 6-digit code, devices on this network, what each may do
    xora center timeline [--space NAME | --path PATH]
    xora center --setup         first-boot setup (Welcome · Updates & data · Devices · First Space)

GTK 4 (already part of Fedora Kinoite, so it costs no extra download). Everything shown is
read from the same code the `xora` command uses; nothing here is sample data.
"""
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .util import ACTIVE_FILE, STATE, have, human, load_json, out, tilde

LOGO_LIGHT = "/usr/share/xora/xora-logo-light.svg"
LOGO_DARK = "/usr/share/xora/xora-logo-dark.svg"
CAPS = [("build", "Run my builds", "Flutter, Docker and compile jobs"),
        ("spaces", "Open my Spaces", "Only Spaces you mark share: true"),
        ("store", "Store backups", "Keeps copies of your Spaces"),
        ("net", "Share downloads", "Container images download once for both")]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ================================================================ data (no GTK here, so it can be tested alone)

def first_name():
    import pwd
    try:
        g = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except KeyError:
        g = ""
    name = (g or os.environ.get("USER", "")).split()
    return name[0].capitalize() if name else ""


def greeting(now=None):
    h = (now or dt.datetime.now()).hour
    return "Good morning" if 5 <= h < 12 else "Good afternoon" if h < 18 else "Good evening"


def _git(d, *args):
    return out(["git", "-C", str(d), *args], timeout=5)


def spaces_info():
    from .spaces import OPENED_FILE, all_names, load_yaml, path_of, project_dir, _running_containers
    running = _running_containers()
    opened = load_json(OPENED_FILE, {})
    act = ACTIVE_FILE.read_text().strip() if ACTIVE_FILE.exists() else None
    res = []
    for n in all_names():
        m = load_yaml(path_of(n)) or {}
        d = project_dir({"space": n, **m})
        svcs = m.get("services") or []
        live = [s.get("name") for s in svcs if f"xora-{n}-{s.get('name')}" in running]
        parts = []
        for s in svcs:
            img = (s.get("image") or "").split("/")[-1].split(":")[0]
            if img:
                parts.append(img.capitalize())
        for t in m.get("tools") or []:
            k = next(iter(t)) if isinstance(t, dict) else str(t)
            parts.append(k.capitalize())
        info = {"name": n, "dir": str(d), "exists": d.exists(), "stack": " · ".join(dict.fromkeys(parts)) or "Project folder",
                "services": len(svcs), "running": len(live), "active": n == act, "opened": opened.get(n),
                "branch": None, "changes": 0}
        if (d / ".git").exists():
            info["branch"] = _git(d, "rev-parse", "--abbrev-ref", "HEAD") or None
            st = _git(d, "status", "--porcelain")
            info["changes"] = len(st.splitlines()) if st else 0
        res.append(info)
    # open/running first, then most recently opened
    res.sort(key=lambda s: (not (s["active"] or s["running"]), -(s["opened"] or 0)))
    return res


def space_state(s):
    if not s["exists"]:
        return "Folder missing", "missing"
    if s["active"] or s["running"]:
        return "Running", "running"
    return "Paused", "paused"


def when(ts, now=None):
    if not ts:
        return "never"
    now = now or time.time()
    d0 = dt.date.fromtimestamp(now)
    d = dt.date.fromtimestamp(ts)
    days = (d0 - d).days
    if days == 0:
        return "today " + time.strftime("%H:%M", time.localtime(ts))
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return time.strftime("%-d %b", time.localtime(ts))


def devices_info(probe=True):
    from .fabric import _devices, _local, _probe, _score
    loc = _local()
    laptop = any(Path("/sys/class/power_supply").glob("BAT*"))
    res = [{"name": "This laptop" if laptop else "This computer",
            "here": True, "online": True, "mem_used": (loc["mem_total_mb"] - loc["mem_free_mb"]) / 1024,
            "mem_total": loc["mem_total_mb"] / 1024, "score": _score(loc), "cpus": loc["cpus"], "can": []}]
    devs = _devices()

    def one(item):
        name, d = item
        p = _probe(d["host"]) if probe else {"online": None}
        r = {"name": name, "host": d["host"], "here": False, "online": p.get("online"), "can": d.get("can", []),
             "cpus": p.get("cpus") or d.get("cpus"), "arch": d.get("arch")}
        if p.get("online"):
            tot = (p.get("mem_total_mb") or d.get("mem_mb") or 0) / 1024
            r.update(mem_total=tot, mem_used=max(0.0, tot - p["mem_free_mb"] / 1024) if tot else None, score=_score(p),
                     load=p["load"])
        return r

    with ThreadPoolExecutor(max_workers=8) as ex:
        res += list(ex.map(one, devs.items()))
    return res


def device_status(d):
    if d["here"]:
        return "You're here", ""
    if d["online"] is None:
        return "Checking…", ""
    if not d["online"]:
        return "Offline", ""
    if "build" in d["can"] and d.get("load", 99) < max(1, (d.get("cpus") or 1) * 0.25):
        return "Free for builds", "ok"
    return "Online", ""


def free_builder(devs):
    cands = [d for d in devs if not d["here"] and d.get("online") and "build" in d["can"]]
    cands.sort(key=lambda d: -d.get("score", 0))
    return cands[0] if cands and device_status(cands[0])[0] == "Free for builds" else None


def events(space=None, path=None, kinds=("files", "system", "apps")):
    """Everything you can go back to, newest first: [{kind, at, title, sub, tone, entry}]."""
    from . import timeline as tl
    res = []
    scope_dirs = []
    if space:
        from .spaces import load_yaml, path_of, project_dir
        scope_dirs.append(str(project_dir({"space": space, **(load_yaml(path_of(space)) or {})})))
    if path:
        scope_dirs.append(str(Path(path).absolute()))
    if "files" in kinds:
        for e in tl._index():
            if scope_dirs and not (e.get("space") == space and space) and \
                    not any(e["path"] == d or e["path"].startswith(d + "/") or d.startswith(e["path"] + "/") for d in scope_dirs):
                continue
            reason = e.get("reason") or "Snapshot"
            low = reason.lower()
            tone = "power" if any(w in low for w in ("power", "battery", "ups")) else "files"
            title = ("Power cut handled" if tone == "power" else
                     "Saved before a restore" if low.startswith("before restoring") else
                     "Space checkpoint" if "checkpoint" in low else
                     "Deleted " + Path(e["path"]).name if low.startswith("rm") or "delete" in low else reason[:1].upper() + reason[1:])
            where = tilde(e["path"])
            sub = f"{where} · {e['files']:,} file{'s' if e['files'] != 1 else ''}" + (" · restored" if e.get("restored") else "")
            if tone == "power":
                sub = "Work saved before battery ran low · " + sub
            res.append({"kind": "files", "at": e["at"], "title": title, "sub": sub, "tone": tone, "entry": e})
    if "system" in kinds and not path:
        for d in tl.system_history():
            if not d["at"]:
                continue
            res.append({"kind": "system", "at": d["at"], "title": f"XORA {d['version']} installed" if d["version"] else "System update",
                        "sub": "Running now" if d["booted"] else "Ready after restart" if d["staged"] else "Previous version kept for rollback",
                        "tone": "system", "entry": d})
    if "apps" in kinds and not path and not space:
        for a in tl.app_history():
            if a["at"]:
                res.append({"kind": "apps", "at": a["at"], "title": f"{a['app'].split('.')[-1]} {a['change']}",
                            "sub": a["app"], "tone": "apps", "entry": a})
    res.sort(key=lambda e: -e["at"])
    return res


def day_label(ts, now=None):
    d = dt.date.fromtimestamp(ts)
    today = dt.date.fromtimestamp(now or time.time())
    if d == today:
        return "TODAY"
    if (today - d).days == 1:
        return "YESTERDAY"
    return d.strftime("%A %-d %B").upper()


def status_bar():
    from .system import _active_conn, _battery
    metered = False
    if have("nmcli"):
        c = _active_conn()
        if c:
            metered = out(["nmcli", "-g", "connection.metered", "connection", "show", c[0]]) in ("yes", "guess-yes")
    upd = out(["systemctl", "is-enabled", "bootc-fetch-apply-updates.timer"]) if have("systemctl") else ""
    updates = ("Updates wait: metered" if metered else "Night updates on") if upd == "enabled" else \
              ("Updates off" if upd in ("disabled", "masked") else "")
    cap, st = _battery()
    return {"updates": updates, "metered": metered, "battery": cap, "charging": st == "Charging"}


def suggestions(spaces, devs, evs):
    res = []
    if spaces:
        s = spaces[0]
        res.append((f"Open {s['name']}", ("open", s["name"])))
    fb = free_builder(devs)
    if fb and spaces:
        res.append((f"Build {spaces[0]['name']} on {fb['name']}", ("build", spaces[0]["name"], fb["name"])))
    dl = Path.home() / "Downloads"
    if any(e["kind"] == "files" and e["entry"]["path"].startswith(str(dl)) for e in evs):
        res.append(("Rewind Downloads", ("timeline-path", str(dl))))
    elif any(e["kind"] == "files" for e in evs):
        res.append(("See what you can undo", ("timeline", None)))
    res.append(("Why is my computer slow?", ("ask", "why is my computer slow?")))
    return res


# ================================================================ desktop actions

def _detach(argv):
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except OSError:
        return False


def in_terminal(args, hold=True, cwd=None):
    """Run `xora <args>` in XORA's terminal, so anything that needs a password or shows progress works."""
    cmd = ["xora", *args]
    if have("xora-term"):
        return _detach(["xora-term", *(["--hold"] if hold else []), *(["--cwd", str(cwd)] if cwd else []), "--", *cmd])
    for t in ("ptyxis", "konsole", "x-terminal-emulator", "gnome-terminal", "xterm"):
        if have(t):
            if t == "ptyxis":
                return _detach([t, "--new-window", *(["-d", str(cwd)] if cwd else []), "--", *cmd])
            if t == "konsole":
                return _detach([t, *(["--workdir", str(cwd)] if cwd else []), *(["--hold"] if hold else []), "-e", *cmd])
            return _detach([t, "--", *cmd] if t == "gnome-terminal" else [t, "-e", " ".join(cmd)])
    return _detach(cmd)

def krunner(query):
    if have("gdbus"):
        return _detach(["gdbus", "call", "--session", "--dest", "org.kde.krunner", "--object-path", "/App",
                        "--method", "org.kde.krunner.App.query", query])
    return False


def run_xora(*args, timeout=60):
    """Run the xora command and return its text output without colour codes."""
    xora = shutil.which("xora") or "xora"
    try:
        r = subprocess.run([xora, *args], capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "NO_COLOR": "1"})
        return ANSI.sub("", (r.stdout + r.stderr).strip())
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"xora {' '.join(args)} failed: {e}"


# ================================================================ GTK app

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="xora center")
    ap.add_argument("page", nargs="?", default="home", choices=["home", "pair", "devices", "timeline"])
    ap.add_argument("--space")
    ap.add_argument("--path")
    ap.add_argument("--setup", action="store_true", help="first-boot setup")
    ap.add_argument("--once", action="store_true", help="with --setup: only if setup hasn't been done yet")
    a = ap.parse_args(argv)
    if a.setup and a.once and (STATE / "welcomed").exists():
        return 0
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # noqa: F401
    except (ImportError, ValueError):
        print("XORA Center needs GTK 4 for Python (python3-gobject, gtk4).", file=sys.stderr)
        return 1
    from . import center_ui
    return center_ui.run(a)
