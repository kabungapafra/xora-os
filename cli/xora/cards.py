"""Explain cards: the desktop tells you why, with buttons that fix it.

A small user service (`xora explain --watch`, started at login) measures the computer about once a
minute. When a problem lasts (two checks in a row, so a short spike doesn't bother you) it shows a
desktop notification like the design's:

    Explain · Your laptop is low on memory
    Chrome is using 5.8 GB and only 1.1 GB is free. safepick's containers are running but you're
    not in that Space: stopping them frees 1.4 GB.
    [Stop safepick]  [Show processes]  [Ignore]

Every sentence comes from a measurement. Buttons only run what they say. Ignore snoozes that card
for a day. When the problem goes away the card is withdrawn.

    xora explain --cards      what would be shown now (no notifications)
    xora explain --watch      the background service
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .util import STATE, have, human, load_json, out, save_json

SNOOZE_FILE = STATE / "explain-snooze.json"
CHECK_EVERY = 60          # seconds
SLOW_EVERY = 5            # network and services: every 5th round
REMIND_AFTER = 2 * 3600   # a dismissed card can come back after this, if the problem is still there

NICE = {"chrome": "Chrome", "chromium": "Chromium", "chromium-browse": "Chromium", "firefox": "Firefox",
        "Isolated Web Co": "Firefox", "Web Content": "Firefox", "code": "VS Code", "java": "Java",
        "studio": "Android Studio", "qemu-system-x86": "a virtual machine", "postgres": "Postgres",
        "mongod": "MongoDB", "node": "Node.js", "python3": "Python", "dart": "Dart", "gradle": "Gradle",
        "plasmashell": "the desktop", "kwin_wayland": "the window manager", "electron": "an Electron app",
        "slack": "Slack", "discord": "Discord", "Discord": "Discord", "teams": "Teams", "zoom": "Zoom",
        "telegram-deskto": "Telegram", "spotify": "Spotify", "baloo_file": "file indexing"}
BROWSERS = {"Chrome", "Chromium", "Firefox"}


def nice(name):
    return NICE.get(name, name[:1].upper() + name[1:])


class Card:
    """key: stable id ("memory"); level: warn|bad; actions: [(id, label, kind, arg)].
    kind: xora (run in background) · term (in the XORA terminal) · app (start a program) · center (XORA Center page)"""

    def __init__(self, key, level, title, body, actions=(), confirm=2):
        self.key, self.level, self.title, self.body = key, level, title, body
        self.actions = list(actions)
        self.confirm = confirm

    def sig(self):
        return f"{self.level}:{self.title}"

    def as_dict(self):
        return {"key": self.key, "level": self.level, "title": self.title, "body": self.body,
                "actions": [{"id": a[0], "label": a[1]} for a in self.actions]}


# ================================================================ measurements → cards

def _space_containers():
    """{space: [(container, mem_bytes)]} for running XORA Space containers."""
    if not have("podman"):
        return {}
    res = {}
    for line in out(["podman", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"], timeout=15).splitlines():
        try:
            name, mem = line.split("\t")
        except ValueError:
            continue
        if not name.startswith("xora-"):
            continue
        used = mem.split("/")[0].strip()
        try:
            num = float(used.rstrip("kKMGTiBb"))
            unit = used.lstrip("0123456789.").upper()
            mult = {"B": 1, "KB": 1e3, "KIB": 1024, "MB": 1e6, "MIB": 1 << 20, "GB": 1e9, "GIB": 1 << 30}.get(unit, 1)
            b = int(num * mult)
        except ValueError:
            b = 0
        from .spaces import all_names
        for n in sorted(all_names(), key=len, reverse=True):
            if name.startswith(f"xora-{n}-"):
                res.setdefault(n, []).append((name[len(f"xora-{n}-"):], b))
                break
    return res


def memory_card():
    from .explain import _meminfo, _top_procs
    m = _meminfo()
    total, avail = m["MemTotal"], m["MemAvailable"]
    if avail / total >= 0.15:
        return None
    level = "bad" if avail / total < 0.08 else "warn"
    top = _top_procs(3)
    kind = "laptop" if any(Path("/sys/class/power_supply").glob("BAT*")) else "computer"
    body = []
    if top:
        rss, name, n = top[0]
        body.append(f"<b>{nice(name)}</b> is using {human(rss)} and only {human(avail)} is free.")
    else:
        body.append(f"Only {human(avail)} of {human(total)} is free.")
    actions = []
    active = (STATE / "active-space").read_text().strip() if (STATE / "active-space").exists() else None
    idle = {s: c for s, c in _space_containers().items() if s != active}
    if idle:
        s, conts = max(idle.items(), key=lambda kv: sum(b for _, b in kv[1]))
        freed = sum(b for _, b in conts)
        body.append(f"<b>{s}</b>'s containers are running but you're not in that Space: stopping them frees "
                    f"{human(freed) if freed else 'memory'}. Its data is kept.")
        actions.append(("stop", f"Stop {s}", "xora", ["space", "close", s]))
    elif top and nice(top[0][1]) in BROWSERS:
        body.append("Closing tabs you aren't using frees the most.")
    elif len(top) > 1:
        body.append("Next biggest: " + ", ".join(f"{nice(nm)} {human(r)}" for r, nm, _ in top[1:]) + ".")
    actions.append(("procs", "Show processes", "app", ["plasma-systemmonitor"]))
    return Card("memory", level, f"Your {kind} is low on memory", " ".join(body), actions)


def disk_card():
    from .timeline import _index
    st = os.statvfs(str(Path.home()))
    total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
    if free >= 5 << 30 and (not total or free / total >= 0.08):
        return None
    level = "bad" if free < 2 << 30 else "warn"
    body = [f"Only {human(free)} is left. When a disk fills up, databases stop and downloads break."]
    actions = []
    idx = _index()
    old = [e for e in idx if e["at"] < time.time() - 30 * 86400]
    if old:
        body.append(f"{len(old)} Timeline snapshot{'s' if len(old) != 1 else ''} older than 30 days use "
                    f"{human(sum(e['size'] for e in old))}.")
        actions.append(("prune", "Clean old snapshots", "term", ["timeline", "prune", "--days", "30"]))
    if have("podman"):
        rec = out(["podman", "system", "df", "--format", "{{.Type}}\t{{.Reclaimable}}"], timeout=15)
        for line in rec.splitlines():
            t, r = (line.split("\t") + [""])[:2]
            if t == "Images" and r and not r.startswith("0"):
                body.append(f"Unused container images: {r.split('(')[0].strip()} can be freed with podman image prune.")
    actions.append(("look", "See what's using space", "app", ["filelight", str(Path.home())]))
    return Card("disk", level, "Your disk is almost full", " ".join(body), actions)


def battery_card():
    for b in Path("/sys/class/power_supply").glob("BAT*"):
        try:
            cap = int((b / "capacity").read_text())
            status = (b / "status").read_text().strip()
        except OSError:
            continue
        if status != "Discharging" or cap > 15:
            return None
        return Card("battery", "bad" if cap <= 8 else "warn", f"Battery at {cap}%",
                    "XORA checkpoints your open Spaces and stops their databases cleanly at 15%, then hibernates at 7%, "
                    "so nothing is lost. Plug in to keep working.",
                    [("save", "Save my Spaces now", "xora", ["resilience", "checkpoint"])], confirm=1)
    return None


def network_card():
    from .explain import check_network
    r = check_network()
    if not r or r[0] == "ok":
        return None
    level, head, detail, fix = r
    actions = []
    if fix and "dns" in fix:
        actions.append(("fixdns", "Fix DNS", "sh", fix))
    elif fix:
        actions.append(("fix", "Turn Wi-Fi on", "sh", fix))
    actions.append(("details", "Details", "term", ["explain"]))
    return Card("network", level, head.rstrip("."), detail or "", actions)


SYSTEMD_NOISE = re.compile(r"Consumed .* CPU time|Failed with result|Control process exited|Main process exited|"
                           r"^Failed to start|^Starting |^Started |Scheduled restart|Deactivated successfully|"
                           r"^Stopped |^Stopping |start request repeated too quickly")
ERRORISH = re.compile(r"error|fail|denied|not found|no such|cannot|can't|unable|refused|invalid|missing", re.I)


def _why(unit, user=False):
    """The unit's own last error line, skipping systemd's bookkeeping."""
    lines = out(["journalctl", *(["--user"] if user else []), "-u", unit, "-n", "40", "-o", "cat", "--no-pager"],
                timeout=10).splitlines()
    own = [l.strip() for l in lines if l.strip() and not SYSTEMD_NOISE.search(l)]
    errs = [l for l in own if ERRORISH.search(l)]
    line = (errs or own or [""])[-1]
    return re.sub(r"^[\w.@-]+(\.sh|\.service)?: ", "", line)[:160]


def services_card():
    failed = out(["systemctl", "--failed", "--plain", "--no-legend"]).splitlines()
    ufailed = out(["systemctl", "--user", "--failed", "--plain", "--no-legend"]).splitlines()
    items = [(l.split()[0], False) for l in failed if l.strip()] + [(l.split()[0], True) for l in ufailed if l.strip()]
    if not items:
        return None
    name, user = items[0]
    why = _why(name, user)
    body = f"<b>{name}</b> stopped with an error" + (f": “{why[:140]}”" if why else ".")
    if len(items) > 1:
        body += f" ({len(items) - 1} more failed too.)"
    actions = [("why", "Show why", "app", ["xora-term", "--hold", "--", "journalctl", *(["--user"] if user else []),
                                           "-u", name, "-n", "40", "--no-pager"])]
    if user:
        actions.insert(0, ("restart", "Restart it", "sh", f"systemctl --user restart {name}"))
    return Card("services:" + name, "warn", f"{len(items)} background service{'s' if len(items) != 1 else ''} failed",
                body, actions)


def cpu_card():
    load = os.getloadavg()[1]           # 5-minute average: sustained, not a spike
    cpus = os.cpu_count() or 1
    if load < cpus * 1.5:
        return None
    top = out(["ps", "-eo", "comm,%cpu", "--sort=-%cpu", "--no-headers"]).splitlines()[:2]
    names = [(" ".join(t.split()[:-1]), t.split()[-1]) for t in top if t.split()]
    body = f"For the last 5 minutes your CPU has had {load:.1f} jobs for {cpus} cores."
    if names:
        body += " Busiest: " + ", ".join(f"<b>{nice(n)}</b> {p}%" for n, p in names) + "."
    actions = []
    try:
        from .center import devices_info, free_builder
        fb = free_builder(devices_info(probe=True))
    except Exception:
        fb = None
    if fb:
        body += f" {fb['name']} is free: builds can run there with <i>xora fabric run --on {fb['name']}</i>."
    actions.append(("procs", "Show processes", "app", ["plasma-systemmonitor"]))
    return Card("cpu", "warn", "Your computer is working very hard", body, actions)


def budget_cards():
    from .system import app_budgets
    res = []
    for appid, x in app_budgets().items():
        if not x.get("limit"):
            continue
        if x.get("blocked"):
            res.append(Card(f"budget:{appid}", "warn", f"{x['name'].capitalize()} used its data for today",
                            f"<b>{x['name'].capitalize()}</b> has used {human(x['used'])} of its {human(x['budget'])} daily budget, "
                            "so it's offline until midnight. Everything else still works.",
                            [("more", "Allow 100 MB more", "xora", ["data", "--allow", x["name"], "100MB"])], confirm=1))
        elif x["used"] >= 0.9 * x["limit"]:
            res.append(Card(f"budget:{appid}", "warn", f"{x['name'].capitalize()} is near its data budget",
                            f"{human(x['used'])} of {human(x['limit'])} used today.", [], confirm=1))
    return res


def budget_card():
    cs = budget_cards()
    return cs[0] if cs else None


FAST = [memory_card, disk_card, battery_card, cpu_card, budget_card]
SLOW = [network_card, services_card]


def cards(slow=True):
    res = []
    for fn in FAST + (SLOW if slow else []):
        try:
            c = fn()
        except Exception:  # one broken measurement must not hide the others
            c = None
        if c:
            res.append(c)
    return res


# ================================================================ acting on a button

def run_action(card, action_id, notify=None):
    """Run one of the card's buttons. Returns a short result sentence (or None)."""
    from .center import _detach, in_terminal
    act = next((a for a in card.actions if a[0] == action_id), None)
    if not act:
        return None
    _, label, kind, arg = act
    if kind == "xora":
        xora = shutil.which("xora") or "xora"
        r = subprocess.run([xora, *arg], capture_output=True, text=True, timeout=300, env={**os.environ, "NO_COLOR": "1"})
        return f"{label}: done." if r.returncode == 0 else f"{label} didn't work: {(r.stderr or r.stdout).strip()[-160:]}"
    if kind == "term":
        in_terminal(arg)
    elif kind == "app":
        if not (have(arg[0]) and _detach(arg)):
            in_terminal(["explain"])
    elif kind == "sh":
        r = subprocess.run(["sh", "-c", arg], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return f"{label} didn't work: {r.stderr.strip()[-160:]}"
        return f"{label}: done."
    elif kind == "center":
        _detach([shutil.which("xora") or "xora", "center", *arg])
    return None


# ================================================================ the background service

class Watcher:
    BUS, PATH, IFACE = "org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications"

    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.shown = {}       # key → {"id", "sig", "at", "card", "dismissed"}
        self.seen = {}        # key → consecutive rounds the problem was there
        self.round = 0
        self.busy = False
        self.bus.signal_subscribe(self.BUS, self.IFACE, None, self.PATH, None, Gio.DBusSignalFlags.NONE, self.on_signal, None)

    # -------------------------------------------------------- notifications over D-Bus
    def notify(self, card, replaces=0, body=None, actions=True):
        G = self.GLib
        acts = []
        if actions:
            acts = ["default", "Open XORA Center"]
            for a in card.actions[:2]:
                acts += [a[0], a[1]]
            acts += ["ignore", "Ignore"]
        hints = {"desktop-entry": G.Variant("s", "org.xora.Center"),
                 "urgency": G.Variant("y", 2 if card.level == "bad" else 1),
                 "category": G.Variant("s", "device")}
        r = self.bus.call_sync(self.BUS, self.PATH, self.IFACE, "Notify",
                               G.Variant("(susssasa{sv}i)", ("XORA Explain", replaces, "xora-logo", f"Explain · {card.title}",
                                                              body if body is not None else card.body, acts, hints,
                                                              0 if card.level == "bad" else 30000)),
                               G.VariantType("(u)"), self.Gio.DBusCallFlags.NONE, 5000, None)
        return r.unpack()[0]

    def close(self, nid):
        try:
            self.bus.call_sync(self.BUS, self.PATH, self.IFACE, "CloseNotification", self.GLib.Variant("(u)", (nid,)),
                               None, self.Gio.DBusCallFlags.NONE, 5000, None)
        except Exception:
            pass

    def by_id(self, nid):
        return next((k for k, v in self.shown.items() if v["id"] == nid), None)

    def on_signal(self, conn, sender, path, iface, signal, params, *_user_data):
        p = params.unpack()
        key = self.by_id(p[0])
        if not key:
            return
        s = self.shown[key]
        if signal == "ActionInvoked":
            action = p[1]
            if action == "ignore":
                snooze(key, 24 * 3600)
                self.close(s["id"])
                del self.shown[key]
            elif action == "default":
                from .center import _detach
                _detach([shutil.which("xora") or "xora", "center"])
            else:
                card = s["card"]

                def work():
                    msg = run_action(card, action)
                    if msg:
                        self.GLib.idle_add(lambda: self.result(key, card, msg) and False)
                threading.Thread(target=work, daemon=True).start()
        elif signal == "NotificationClosed":
            if p[1] == 2:          # closed by the user: don't repeat for a while
                s["dismissed"] = time.time()

    def result(self, key, card, msg):
        s = self.shown.get(key)
        try:
            nid = self.notify(card, s["id"] if s else 0, body=msg, actions=False)
            if s:
                s["id"] = nid
        except Exception:
            pass

    # -------------------------------------------------------- the loop
    def tick(self):
        if self.busy:
            return True
        self.busy = True
        slow = self.round % SLOW_EVERY == 0
        self.round += 1

        def work():
            found = cards(slow=slow)
            self.GLib.idle_add(lambda: self.apply(found, slow) and False)
        threading.Thread(target=work, daemon=True).start()
        return True

    def apply(self, found, slow):
        self.busy = False
        now = time.time()
        sn = load_json(SNOOZE_FILE, {})
        keys = {c.key for c in found}
        slow_keys = ("network", "services:")
        for c in found:
            self.seen[c.key] = self.seen.get(c.key, 0) + 1
            if self.seen[c.key] < c.confirm or sn.get(c.key, 0) > now:
                continue
            s = self.shown.get(c.key)
            if s and s["sig"] == c.sig():
                if not s.get("dismissed") or now - s["dismissed"] < REMIND_AFTER:
                    s["card"] = c          # keep the buttons current, don't re-pop the same card
                    continue
            try:
                nid = self.notify(c, s["id"] if s else 0)
            except Exception:
                continue
            self.shown[c.key] = {"id": nid, "sig": c.sig(), "at": now, "card": c, "dismissed": None}
        for k in list(self.seen):
            if k not in keys and (slow or not k.startswith(slow_keys)):
                self.seen.pop(k)
                s = self.shown.pop(k, None)
                if s:
                    self.close(s["id"])     # the problem went away: withdraw its card
        return False

    def run(self):
        loop = self.GLib.MainLoop()
        self.GLib.timeout_add_seconds(CHECK_EVERY, self.tick)
        self.GLib.timeout_add_seconds(20, lambda: self.tick() and False)   # first look shortly after login
        loop.run()


def snooze(key, seconds):
    sn = {k: v for k, v in load_json(SNOOZE_FILE, {}).items() if v > time.time()}
    sn[key] = time.time() + seconds
    save_json(SNOOZE_FILE, sn)


def cmd_cards(a):
    found = cards(slow=True)
    if getattr(a, "json", False):
        print(json.dumps([c.as_dict() for c in found], indent=1))
        return
    from .util import bold, dim, red, yellow, ok
    import re
    if not found:
        ok("Nothing to explain: memory, disk, battery, CPU, network and services are fine.")
    for c in found:
        print(f"{(red if c.level == 'bad' else yellow)('[!]')} {bold(c.title)}")
        print("    " + re.sub(r"<[^>]+>", "", c.body))
        if c.actions:
            print(dim("    buttons: " + " · ".join(a[1] for a in c.actions) + " · Ignore"))


def cmd_watch(a):
    try:
        import gi  # noqa: F401
        from gi.repository import Gio  # noqa: F401
    except ImportError:
        from .util import die
        die("the Explain watcher needs python3-gobject")
    Watcher().run()
