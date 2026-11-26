"""Explain: the OS tells you why, in plain words.

Deterministic first: facts are gathered from the system and matched against known
causes. Nothing is changed without asking. An optional local model (Ollama) may only
re-phrase the collected facts; it never invents causes.

    xora explain                 # health check: memory, disk, CPU, network, power, failed services
    xora explain -- pytest -q    # run a command; if it fails, say why and suggest a fix (F2 runs it)
    xora ask "why is my pc slow?"
"""
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

from .util import (FIX_FILE, bold, cyan, dim, green, have, human, info, ok, out, red, say, set_fix, warn, yellow)


# ---------------------------------------------------------------- system facts

def _meminfo():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        m[k] = int(v.split()[0]) * 1024
    return m


def _top_procs(n=3):
    procs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/status") as f:
                st = dict(l.split(":", 1) for l in f if ":" in l)
            rss = int(st.get("VmRSS", "0 kB").split()[0]) * 1024
            procs.append((rss, st["Name"].strip(), int(pid)))
        except (OSError, KeyError, ValueError):
            pass
    # group by program name, so 40 chrome processes count as one "Chrome"
    groups = {}
    for rss, name, pid in procs:
        g = groups.setdefault(name, [0, 0])
        g[0] += rss
        g[1] += 1
    return sorted(((v[0], k, v[1]) for k, v in groups.items()), reverse=True)[:n]


def check_memory():
    m = _meminfo()
    total, avail = m["MemTotal"], m["MemAvailable"]
    pct = avail / total * 100
    swap_used = m.get("SwapTotal", 0) - m.get("SwapFree", 0)
    top = _top_procs()
    if pct < 10:
        name = top[0][1] if top else "?"
        return ("bad", f"Your computer is short on memory: only {human(avail)} of {human(total)} is free.",
                f"{bold(name)} is using {human(top[0][0])}" + (f" across {top[0][2]} processes" if top and top[0][2] > 1 else "") +
                ". Closing it (or some of its tabs/windows) will free the most.", None)
    if pct < 25:
        return ("warn", f"Memory is getting full: {human(avail)} free of {human(total)}.",
                "Biggest users: " + ", ".join(f"{n} {human(r)}" for r, n, _ in top), None)
    return ("ok", f"Memory is fine: {human(avail)} free of {human(total)}" + (f", {human(swap_used)} swap in use" if swap_used > 256 << 20 else "") + ".", None, None)


def check_disk():
    res = []
    seen = set()
    fstype = {}
    try:
        for line in open("/proc/self/mounts"):
            dev, mnt, typ = line.split()[:3]
            fstype[mnt] = typ
    except OSError:
        pass
    for mp in ("/", str(Path.home()), "/var", "/tmp"):
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        # XORA's / is the read-only system image (always "0 free"): nothing can fill it, so skip it
        if st.f_flag & os.ST_RDONLY or not st.f_blocks:
            continue
        key = (st.f_blocks, st.f_bfree)
        if key in seen:
            continue
        seen.add(key)
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        pct = free / total * 100 if total else 100
        in_ram = fstype.get(os.path.realpath(mp)) in ("tmpfs", "ramfs")
        # a RAM folder like /tmp is small by design: only its percentage matters
        if (pct < 5) if in_ram else (free < 2 << 30 or pct < 5):
            fix = "journalctl --user --vacuum-size=200M" if mp == "/var" else "xora timeline prune --days 30"
            res.append(("bad", f"The disk holding {mp} is almost full: {human(free)} left.",
                        "Programs fail in strange ways when the disk is full (databases stop, downloads break). "
                        "Old Timeline snapshots, caches and containers are the usual suspects: try `podman system df`.", fix))
        elif pct < 15:
            res.append(("warn", f"{mp}: {human(free)} free ({pct:.0f}%).", None, None))
    return res or [("ok", "Disk space is fine.", None, None)]


def check_cpu():
    load = os.getloadavg()[0]
    cpus = os.cpu_count() or 1
    if load > cpus * 1.5:
        top = out(["ps", "-eo", "comm,%cpu", "--sort=-%cpu", "--no-headers"]).splitlines()[:3]
        return ("warn", f"The CPU is overloaded (load {load:.1f} on {cpus} cores).",
                "Busiest: " + ", ".join(" ".join(t.split()) + "%" for t in top), None)
    return ("ok", f"CPU is fine (load {load:.1f} on {cpus} cores).", None, None)


def check_power():
    base = Path("/sys/class/power_supply")
    for b in base.glob("BAT*") if base.exists() else []:
        try:
            cap = int((b / "capacity").read_text())
            status = (b / "status").read_text().strip()
        except OSError:
            continue
        if status == "Discharging" and cap < 15:
            return ("bad", f"Battery is at {cap}% and discharging.", "Save your work; XORA will checkpoint Spaces and hibernate at 5%.", None)
        return ("ok", f"Battery {cap}% ({status.lower()}).", None, None)
    return None


def check_network():
    route = out(["ip", "route", "show", "default"])
    if not route:
        wifi = out(["nmcli", "-t", "-f", "WIFI", "general"]) if have("nmcli") else ""
        why = "Wi-Fi is switched off." if wifi == "disabled" else "You're not connected to any network (no Wi-Fi or cable)."
        return ("bad", why, "Connect to a network from the system tray.", "nmcli radio wifi on" if wifi == "disabled" else None)
    gw = re.search(r"via (\S+)", route)
    gw = gw.group(1) if gw else None
    if gw:
        r = subprocess.run(["ping", "-c", "1", "-W", "2", gw], capture_output=True)
        if r.returncode != 0:
            return ("bad", f"You're connected, but your router ({gw}) isn't answering.",
                    "Restart the router or reconnect to the Wi-Fi.", None)
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        internet = True
    except OSError:
        internet = False
    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname("fedoraproject.org")
        dns = True
    except OSError:
        dns = False
    if not internet:
        return ("bad", "Your router works but there's no internet behind it.",
                "The provider's line is down or your bundle/data has run out.", None)
    if not dns:
        return ("bad", "Internet works, but names (DNS) aren't resolving, so websites won't open.",
                "Your DNS server isn't answering. Switching to Cloudflare DNS usually fixes it.",
                "nmcli connection modify \"$(nmcli -t -f NAME connection show --active | head -1)\" ipv4.dns 1.1.1.1 && nmcli connection up \"$(nmcli -t -f NAME connection show --active | head -1)\"")
    return ("ok", "Network and internet are working.", None, None)


def check_services():
    failed = out(["systemctl", "--failed", "--plain", "--no-legend"]).splitlines()
    ufailed = out(["systemctl", "--user", "--failed", "--plain", "--no-legend"]).splitlines()
    items = [l.split()[0] for l in failed + ufailed if l.strip()]
    if items:
        return ("warn", f"{len(items)} background service(s) failed: {', '.join(items[:4])}.",
                f"See why with: journalctl -u {items[0]} -n 30", None)
    return ("ok", "All background services are running.", None, None)


CHECKS = [("memory", check_memory), ("disk", check_disk), ("cpu", check_cpu), ("power", check_power),
          ("network", check_network), ("services", check_services)]


def health(only=None):
    results = []
    for name, fn in CHECKS:
        if only and name not in only:
            continue
        try:
            r = fn()
        except Exception as e:  # a broken check must not hide the others
            r = ("warn", f"couldn't check {name}: {e}", None, None)
        if r is None:
            continue
        results += r if isinstance(r, list) else [r]
    return results


def print_results(results):
    fix = None
    for level, head, detail, f in results:
        mark = {"ok": green("[+]"), "warn": yellow("[!]"), "bad": red("[-]")}[level]
        print(f"{mark} {head}")
        if detail:
            print(f"    {dim(detail) if level == 'ok' else detail}")
        fix = fix or f
    set_fix(fix)


# ---------------------------------------------------------------- error explanations

PIP_NAMES = {"yaml": "pyyaml", "cv2": "opencv-python", "PIL": "pillow", "sklearn": "scikit-learn",
             "bs4": "beautifulsoup4", "dotenv": "python-dotenv", "jwt": "pyjwt", "psycopg2": "psycopg2-binary"}


def _pkg_install(cmd):
    osr = Path("/etc/os-release").read_text() if Path("/etc/os-release").exists() else ""
    if Path("/run/ostree-booted").exists():
        return (f"xora apps fedora && distrobox enter fedora -- sh -c 'sudo dnf install -y {cmd} && distrobox-export --bin \"$(command -v {cmd})\"'",
                "XORA's system is read-only, so tools go in its Fedora app container; F2 installs it there and makes "
                f"`{cmd}` work like a normal command. Apps with a window: `xora install {cmd}`.")
    if "fedora" in osr:
        return f"sudo dnf install -y {cmd}", None
    if re.search(r"ubuntu|debian", osr):
        return f"sudo apt install -y {cmd}", None
    return None, None


def _port_owner(port):
    o = out(["ss", "-ltnpH", f"sport = :{port}"])
    m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', o)
    return (m.group(1), m.group(2)) if m else (None, None)


def _space_db():
    try:
        from .spaces import active, load
        s = active()
        if not s:
            return None
        for svc in load(s).get("services") or []:
            if "postgres" in (svc.get("image") or "") or "postgis" in (svc.get("image") or ""):
                return f"xora-{s}-{svc['name']}"
    except SystemExit:
        return None
    return None


def explain_output(text, cmd):
    """Return (explanation, fix) for known failures, else (None, None)."""
    t = text
    m = re.search(r'database "([^"]+)" does not exist', t)
    if m:
        db = m.group(1)
        c = _space_db()
        fix = f"podman exec {c} createdb -U postgres {db}" if c else f"createdb {db}"
        return f"The program needs a database called {bold(db)}, and it doesn't exist yet. Create it once and it can connect.", fix
    m = re.search(r"connection (?:to server at|refused).*?(?:port )?(\d{4,5})|could not connect to server|Connection refused.*:(\d{4,5})", t, re.I)
    if m:
        port = next((g for g in m.groups() if g), None)
        what = {"5432": "PostgreSQL", "6379": "Redis", "3306": "MySQL", "27017": "MongoDB", "8000": "the API"}.get(port, "the server")
        return f"Nothing is listening{f' on port {port}' if port else ''}, so {what} isn't running.", "xora up"
    m = re.search(r"No module named '([\w.]+)'", t)
    if m:
        mod = m.group(1).split(".")[0]
        pkg = PIP_NAMES.get(mod, mod)
        venv = ".venv/bin/pip" if Path(".venv/bin/pip").exists() else "pip install --user" if not os.environ.get("VIRTUAL_ENV") else "pip"
        fix = f"{venv} install {pkg}" if venv.endswith("pip") else f"{venv} {pkg}"
        return f"Python can't find the package {bold(mod)}. It isn't installed in the Python you're using.", fix
    m = re.search(r"(?:command not found|not found): ?(\S+)|(\S+): command not found", t)
    if m:
        name = (m.group(1) or m.group(2)).strip(":")
        fix, note = _pkg_install(name)
        return f"The program {bold(name)} isn't installed." + (f" {note}" if note else ""), fix
    m = re.search(r"address already in use|EADDRINUSE|port is already allocated", t, re.I)
    if m:
        pm = re.search(r"(?:port|:)\s*(\d{2,5})\b", t[max(0, m.start() - 200):m.end() + 200])
        port = pm.group(1) if pm else next((c for c in (cmd or []) if re.fullmatch(r"\d{2,5}", str(c))), None)
        if not port:
            pm = re.search(r"(?:--port[= ]|-p ?|:)(\d{2,5})\b", " ".join(map(str, cmd or [])))
            port = pm.group(1) if pm else None
        name, pid = _port_owner(port) if port else (None, None)
        if pid:
            return f"Port {port} is already taken by {bold(name)} (pid {pid}).", f"kill {pid}"
        return "The port is already in use by another program.", None
    if re.search(r"No space left on device", t):
        return "The disk is full, so nothing more can be written.", "xora explain --only disk"
    if re.search(r"Permission denied \(publickey", t):
        return "The server doesn't recognise this computer's SSH key.", "ssh-keygen -t ed25519 && cat ~/.ssh/id_ed25519.pub"
    m = re.search(r"Could not resolve host:? ?(\S+)|Temporary failure in name resolution|getaddrinfo", t)
    if m:
        return "The computer can't look up website names (DNS).", "xora explain --only network"
    if re.search(r"not a git repository", t):
        return "This folder isn't a git project.", "git init"
    if re.search(r"Your branch is behind", t):
        return "Your branch is missing newer commits from the server.", "git pull --rebase"
    if re.search(r"CONFLICT \(content\)|Automatic merge failed", t):
        return "Git couldn't merge automatically: the same lines changed on both sides. Open the files marked CONFLICT and choose what to keep.", "git status"
    if re.search(r"npm ERR! Missing script: \"?(\w+)", t):
        return "package.json has no such script.", "npm run"
    if re.search(r"ENOENT.*package\.json", t):
        return "There's no package.json here; you're probably in the wrong folder.", None
    if re.search(r"No connected devices|No supported devices connected", t):
        return "Flutter can't see a phone or emulator.", "flutter emulators --launch $(flutter emulators | awk '/•/{print $1; exit}')"
    m = re.search(r"Permission denied", t)
    if m:
        return "You don't have permission for that file or folder.", None
    if re.search(r"Killed|Out of memory|MemoryError", t):
        return "The program ran out of memory and was stopped.", "xora explain --only memory"
    return None, None


def cmd_explain(a):
    if getattr(a, "watch", False) or getattr(a, "cards", False):
        from . import cards
        return cards.cmd_watch(a) if a.watch else cards.cmd_cards(a)
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        only = a.only.split(",") if a.only else None
        print_results(health(only))
        return
    # run the command, streaming its output, then explain a failure
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    buf = []
    for line in proc.stdout:
        sys.stdout.write(line)
        buf.append(line)
        if len(buf) > 4000:
            buf = buf[-2000:]
    code = proc.wait()
    if code == 0:
        set_fix(None)
        return 0
    why, fix = explain_output("".join(buf), cmd)
    if why:
        print(f"{cyan('[xora explain]')} {why}")
        set_fix(fix)
    else:
        print(f"{cyan('[xora explain]')} {shlex.join(cmd)} failed with exit code {code}. I don't recognise this error yet.")
        set_fix(None)
    return code


# ---------------------------------------------------------------- plain-words questions

TOPICS = [
    (r"slow|lag|freez|hang|fan|hot|heavy", ["memory", "cpu", "disk"]),
    (r"internet|wifi|wi-fi|network|dns|website|online|connect", ["network"]),
    (r"disk|storage|space left|full", ["disk"]),
    (r"memory|ram", ["memory"]),
    (r"battery|power|charge", ["power"]),
    (r"service|crash|fail|broken", ["services"]),
]


def cmd_ask(a):
    q = " ".join(a.question).strip()
    if not q:
        say("Ask in plain words, e.g.  # why is my computer slow?")
        return
    ql = q.lower()
    if re.search(r"undo|deleted|get .* back|restore", ql):
        from .timeline import _index
        e = next((e for e in _index() if not e.get("restored")), None)
        if e:
            say(f"The last thing deleted was {bold(e['path'])} ({e['files']:,} files).")
            set_fix("xora undo")
        else:
            say("There's nothing deleted that can be restored.")
        return
    if re.search(r"space|project|which folder|where am i", ql):
        from .spaces import active
        s = active()
        say(f"You're in Space {bold(s)}." if s else "You're not inside a Space. List them with: xora space list")
        return
    topics = []
    for pat, t in TOPICS:
        if re.search(pat, ql):
            topics += [x for x in t if x not in topics]
    if not topics:
        topics = [n for n, _ in CHECKS]
    results = health(topics)
    phrased = _local_model(q, results) if not a.no_ai else None
    if phrased:
        say(phrased)
        set_fix(next((f for *_, f in results if f), None))
    else:
        print_results(results)


def _local_model(question, results):
    """Optional: let a local Ollama model phrase the facts. Never sends data off the machine."""
    if os.environ.get("XORA_AI", "auto") == "off":
        return None
    try:
        tags = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1))
        models = [m["name"] for m in tags.get("models", [])]
        if not models:
            return None
        model = os.environ.get("XORA_MODEL") or next((m for m in models if re.search(r"llama3|qwen|gemma|phi|mistral", m)), models[0])
        facts = "\n".join(f"- [{lvl}] {h}" + (f" {d}" if d else "") for lvl, h, d, _ in results)
        prompt = (f"You are XORA, the operating system. Answer the user's question in 1-3 short plain sentences, "
                  f"using ONLY these measured facts. Do not guess causes that aren't in the facts. If the facts show "
                  f"no problem, say so.\nFacts:\n{facts}\nQuestion: {question}")
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                     data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                                                      "options": {"temperature": 0.1}}).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=40))["response"].strip()
    except Exception:
        return None
