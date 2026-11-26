"""System features: privacy panel, metered data & update schedule, resilience, boot, welcome."""
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from .util import (CONFIG, STATE, bold, cyan, die, dim, err, green, have, human, info, load_yaml, ok, out, red, run,
                   save_yaml, say, warn, yellow, confirm)

SETTINGS = CONFIG / "settings.yaml"


def settings():
    s = {"resilience": {"checkpoint_minutes": 30, "low_battery": 15, "critical_battery": 7}}
    s.update(load_yaml(SETTINGS, {}) or {})
    return s


# ================================================================ privacy: who is using what, right now

def _proc_name(pid):
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
        name = Path(exe).name
        cg = Path(f"/proc/{pid}/cgroup").read_text()
        m = re.search(r"app-flatpak-([\w.]+)-\d+\.scope", cg)
        return (m.group(1), True) if m else (name, False)
    except OSError:
        return (None, False)


def _users_of(devglob):
    users = defaultdict(set)
    devs = {str(p) for p in Path("/dev").glob(devglob)}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                try:
                    if os.readlink(f"/proc/{pid}/fd/{fd}") in devs:
                        name, _ = _proc_name(pid)
                        if name:
                            users[name].add(int(pid))
                except OSError:
                    pass
        except OSError:
            pass
    return users


def _mic_users():
    users = defaultdict(set)
    if not have("pactl"):
        return users
    try:
        data = json.loads(out(["pactl", "-f", "json", "list", "source-outputs"]) or "[]")
    except json.JSONDecodeError:
        return users
    for so in data:
        p = so.get("properties", {})
        name = p.get("application.name") or p.get("application.process.binary") or "?"
        users[name].add(int(p.get("application.process.id", 0) or 0))
    return users


def _net_users():
    users = defaultdict(lambda: [0, set()])
    for line in out(["ss", "-tunpH", "state", "established"]).splitlines():
        m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        if m:
            remote = line.split()[4] if len(line.split()) > 4 else ""
            name, _ = _proc_name(m.group(2))
            u = users[name or m.group(1)]
            u[0] += 1
            u[1].add(remote.rsplit(":", 1)[0])
    return users


def cmd_privacy(a):
    if a.revoke:
        return _revoke(a.revoke, a.what)
    cam = _users_of("video*")
    mic = _mic_users()
    print(bold("Right now"))
    print(f"  {'Camera':12} " + (", ".join(red(n) for n in cam) if cam else green("nobody")))
    print(f"  {'Microphone':12} " + (", ".join(red(n) for n in mic) if mic else green("nobody")))
    geo = out(["busctl", "--system", "--list", "--no-pager"]) if have("busctl") else ""
    gc = "geoclue" in geo and out(["pgrep", "-a", "geoclue"])
    print(f"  {'Location':12} " + (yellow("geoclue is active") if gc else green("nobody")))
    print(bold("\nNetwork connections"))
    net = sorted(_net_users().items(), key=lambda kv: -kv[1][0])
    for name, (n, hosts) in net[:12]:
        print(f"  {name:28} {n:3} connection(s)  {dim(', '.join(sorted(hosts))[:60])}")
    if not net:
        print(dim("  no open connections"))
    if have("flatpak"):
        print(bold("\nApp permissions (Flatpak)"))
        apps = out(["flatpak", "list", "--app", "--columns=application"]).splitlines()
        for app in apps[:25]:
            perms = out(["flatpak", "info", "--show-permissions", app], timeout=5)
            flags = []
            if re.search(r"devices=.*(all|webcam)", perms): flags.append("camera")
            if "pulseaudio" in perms: flags.append("audio/mic")
            if re.search(r"filesystems=.*(host|home)", perms): flags.append(yellow("your files"))
            if "network" in perms: flags.append("network")
            print(f"  {app:40} {', '.join(flags) or dim('nothing sensitive')}")
        print(dim("\n  Revoke with: xora privacy --revoke <app> --what camera|mic|files|network"))


def _revoke(app, what):
    flag = {"camera": "--nodevice=all", "mic": "--nosocket=pulseaudio", "files": "--nofilesystem=home",
            "network": "--unshare=network"}.get(what)
    if not flag:
        die("--what must be camera, mic, files or network")
    if "." in app and have("flatpak"):
        if run(["flatpak", "override", "--user", flag, app]).returncode == 0:
            if what == "files":
                run(["flatpak", "override", "--user", "--nofilesystem=host", app], quiet=True)
            ok(f"{app} can no longer use {what}. Undo with: flatpak override --user --reset {app}")
        return
    pids = out(["pgrep", "-x", app]).split()
    if pids and confirm(f"{app} isn't a sandboxed app, so its access can't be removed — stop it now?"):
        run(["kill"] + pids)


# ================================================================ data: metered mode, usage, night-time updates

UPDATE_OVERRIDE = Path("/etc/systemd/system/bootc-fetch-apply-updates.timer.d/xora.conf")


def _active_conn():
    return out(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"]).splitlines()[:1]


NETBUDGET = "/usr/lib/xora/hooks/netbudget"
NETBUDGET_STATUS = Path("/run/xora/netbudget.json")


def parse_size(text):
    m = re.fullmatch(r"\s*([\d.]+)\s*([kmgt]?)i?b?\s*", text.lower())
    if not m:
        die(f"'{text}' isn't a size (try 500MB or 2GB)")
    return int(float(m.group(1)) * {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30, "t": 1 << 40}[m.group(2)])


def _root(argv):
    if os.geteuid() == 0:
        return run(argv).returncode
    if sys.stdin.isatty() and have("sudo"):
        return run(["sudo", *argv]).returncode
    return run(["pkexec", *argv]).returncode


def app_budgets():
    """Per-app data today from the budget service: {app: {name, used, budget, limit, blocked}}."""
    try:
        j = json.loads(NETBUDGET_STATUS.read_text())
    except (OSError, ValueError):
        return {}
    return j.get("apps", {}) if j.get("day") == time.strftime("%F") else {}


def cmd_data(a):
    if a.budget or a.allow:
        if not Path(NETBUDGET).exists():
            die("per-app budgets need XORA OS (the budget service isn't installed here)")
        app, size = a.budget or a.allow
        n = parse_size(size)
        rc = _root([NETBUDGET, "set" if a.budget else "allow", app.lower(), str(n)])
        if rc == 0:
            ok(f"{app}: " + (f"{human(n)} per day" if a.budget and n else "no budget" if a.budget else f"{human(n)} more today"))
        return rc
    conn = _active_conn()
    if a.metered is not None:
        if not conn:
            die("no active network connection")
        val = "yes" if a.metered == "on" else "no"
        run(["nmcli", "connection", "modify", conn[0], "connection.metered", val])
        ok(f"'{conn[0]}' is {'metered: updates and big background downloads wait' if val == 'yes' else 'not metered'}")
        return
    if a.updates:
        return _schedule_updates(a.updates)
    # status
    if conn:
        m = out(["nmcli", "-g", "connection.metered", "connection", "show", conn[0]])
        print(f"{bold('Connection')}  {conn[0]}  " + (yellow("metered") if m in ("yes", "guess-yes") else dim("not metered")))
    if have("vnstat"):
        print(bold("\nData used"))
        print(out(["vnstat", "--oneline", "b"]) and out(["vnstat", "-m"]) or dim("  vnstat is still collecting"))
    else:
        rx = tx = 0
        for dev in Path("/sys/class/net").iterdir():
            if dev.name == "lo":
                continue
            try:
                rx += int((dev / "statistics/rx_bytes").read_text())
                tx += int((dev / "statistics/tx_bytes").read_text())
            except OSError:
                pass
        print(f"{bold('Since boot')}  ↓ {human(rx)}  ↑ {human(tx)}")
    apps = app_budgets()
    if apps:
        print(bold("\nData per app today"))
        for appid, x in sorted(apps.items(), key=lambda kv: -kv[1]["used"])[:12]:
            lim = f" of {human(x['limit'])}" if x.get("limit") else ""
            tag = red("  BLOCKED: budget reached") if x.get("blocked") else ""
            print(f"  {x['name']:22} {human(x['used']):>9}{lim}{tag}")
    print(bold("\nWho is using the network now"))
    net = sorted(_net_users().items(), key=lambda kv: -kv[1][0])[:8]
    for name, (n, _) in net:
        print(f"  {name:28} {n} connection(s)")
    print(dim("\nxora data --metered on|off · --updates night|now|off · --budget APP 500MB · --allow APP 100MB"))


def _schedule_updates(mode):
    if mode == "now":
        os.execvp("sudo", ["sudo", "bootc", "upgrade"])
    if mode == "off":
        content = None
    else:
        content = ("[Timer]\nOnBootSec=\nOnUnitInactiveSec=\nOnCalendar=\nOnCalendar=*-*-* 02:00:00\nRandomizedDelaySec=45min\nPersistent=true\n")
    script = (f"mkdir -p {UPDATE_OVERRIDE.parent} && " +
              (f"printf '%s' {json.dumps(content)} > {UPDATE_OVERRIDE}" if content else f"rm -f {UPDATE_OVERRIDE} && systemctl disable --now bootc-fetch-apply-updates.timer") +
              " && systemctl daemon-reload" + (" && systemctl enable --now bootc-fetch-apply-updates.timer" if content else ""))
    if run(["sudo", "sh", "-c", script]).returncode == 0:
        ok("updates download at night (around 2 am), and never on metered connections" if content else "automatic updates are off")


# ================================================================ resilience: power cuts and UPS

def _battery():
    for b in Path("/sys/class/power_supply").glob("BAT*"):
        try:
            return int((b / "capacity").read_text()), (b / "status").read_text().strip()
        except OSError:
            pass
    return None, None


def checkpoint_all(reason):
    """Save every open Space: snapshot files, then stop databases cleanly so they recover safely."""
    from .spaces import ACTIVE_FILE, all_names, load, project_dir, _running_containers
    from .timeline import snapshot
    running = _running_containers()
    saved = 0
    for n in all_names():
        m = load(n)
        live = [s for s in m.get("services") or [] if f"xora-{n}-{s['name']}" in running]
        is_active = ACTIVE_FILE.exists() and ACTIVE_FILE.read_text().strip() == n
        if not live and not is_active:
            continue
        d = project_dir(m)
        if d.exists():
            try:
                snapshot(d, reason, n)
                saved += 1
            except Exception as e:
                err(f"{n}: {e}")
        for s in live:
            # databases flush and close files on a clean stop; a power cut mid-write is what corrupts them
            run(["podman", "stop", "-t", "20", f"xora-{n}-{s['name']}"], capture=True)
    return saved


def cmd_resilience(a):
    s = settings()["resilience"]
    if a.action == "checkpoint":
        n = checkpoint_all(a.reason or "resilience checkpoint")
        ok(f"checkpointed {n} Space(s)")
        return
    if a.action == "watch":
        return _watch(s)
    if a.action == "onbattery":     # called by NUT's upsmon NOTIFYCMD or UPower
        say("Power cut detected: saving your Spaces now, while there's still power.")
        n = checkpoint_all("power cut")
        run(["notify-send", "-u", "critical", "XORA: running on backup power", f"Saved {n} Space(s). Save your other work."], capture=True)
        return
    cap, st = _battery()
    print(bold("Resilience"))
    print("  power        " + (f"battery {cap}% ({st.lower()})" if cap is not None else "mains (no battery)"))
    ups = out(["upsc", "-l"]) if have("upsc") else ""
    print("  UPS          " + (green(ups) if ups else dim("none configured (install a UPS and run: sudo nut-scanner)")))
    timer = out(["systemctl", "--user", "is-active", "xora-resilience.service"])
    print("  watcher      " + (green("running") if timer == "active" else yellow("off — systemctl --user enable --now xora-resilience")))
    print(f"  checkpoints  every {s['checkpoint_minutes']} min while a Space is open; at {s['low_battery']}% battery all Spaces are saved "
          f"and databases stopped cleanly; at {s['critical_battery']}% the computer hibernates")


def _watch(s):
    """Long-running user service: periodic checkpoints + low-battery actions."""
    last_ck = 0
    acted_low = acted_crit = False
    info("resilience watcher started")
    while True:
        cap, st = _battery()
        now = time.time()
        if now - last_ck > s["checkpoint_minutes"] * 60:
            from .spaces import ACTIVE_FILE
            if ACTIVE_FILE.exists():
                from .timeline import snapshot
                from .spaces import load, project_dir
                try:
                    n = ACTIVE_FILE.read_text().strip()
                    snapshot(project_dir(load(n)), "automatic checkpoint", n)
                except (Exception, SystemExit):
                    pass
            last_ck = now
        if cap is not None and st == "Discharging":
            if cap <= s["low_battery"] and not acted_low:
                checkpoint_all(f"battery {cap}%")
                run(["notify-send", "-u", "critical", "XORA: battery low", f"{cap}% left. Your Spaces are saved."], capture=True)
                acted_low = True
            if cap <= s["critical_battery"] and not acted_crit:
                acted_crit = True
                if run(["systemctl", "hibernate"], capture=True).returncode != 0:
                    run(["systemctl", "suspend"], capture=True)  # no swap for hibernation: suspend instead
        else:
            acted_low = acted_crit = False
        time.sleep(60)


# ================================================================ boot (RapidBoot report)

def cmd_boot(a):
    print(out(["systemd-analyze"]) or "systemd-analyze unavailable")
    print(bold("\nSlowest to start"))
    for line in out(["systemd-analyze", "blame", "--no-pager"]).splitlines()[:8]:
        print("  " + line.strip())
    if out(["systemctl", "is-enabled", "NetworkManager-wait-online.service"]) == "enabled":
        warn("NetworkManager-wait-online makes boot wait for the network; XORA disables it")


# ================================================================ first-boot welcome

def cmd_welcome(a):
    marker = STATE / "welcomed"
    if a.once and marker.exists():
        return
    marker.write_text(time.strftime("%F %T"))
    print(cyan("""
        ▄▄▄▄          ▄▄▄
         ▀███▄      ▄██▀       Welcome to XORA OS
           ▀███▄  ▄██▀
             ▀█████▀           Your devices. Your projects.
            ▄██▀▀███▄          One connected workspace.
          ▄██▀    ▀███▄
        ▄██▀       ▀████▄
"""))
    print(bold("Add your other devices") + " — laptops and PCs that join your Fabric can share builds and keep copies of your work.")
    if confirm("Pair a device now?", False):
        from .fabric import cmd_invite
        cmd_invite(type("A", (), {"can": "build,run,store", "name": None}))
    print(f"""
{bold('Get started')}
  {green('xora space create')}            inside a project folder — XORA remembers how to bring it all back
  {green('xora space open <name>')}       repo, tools, containers, terminals and windows in one go
  {green('rm -rf something')} → {green('undo')}       every delete is saved to the Timeline first
  {green('# why is my pc slow?')}         ask in plain words, right in the terminal
  {green('xora privacy')}                 who is using your camera, mic and network
  {green('xora data --metered on')}       on expensive internet: updates wait
  {green('xora help')}                    everything else
""")
    if a.once:
        input(dim("Press Enter to close… "))


# ================================================================ local AI (opt-in)

AI_CONTAINER = "xora-ai"
AI_MODEL = "qwen2.5:1.5b"     # ~1 GB, runs on CPU with 4 GB RAM


def cmd_ai(a):
    if a.action == "enable":
        model = a.model or AI_MODEL
        print(f"This downloads the Ollama runtime (~1.5 GB) and the {model} model (~1 GB).")
        print("It runs only on this computer (bound to 127.0.0.1); your questions never leave the machine.")
        if not confirm("Continue?", False):
            return
        if run(["podman", "container", "exists", AI_CONTAINER], capture=True).returncode != 0:
            r = run(["podman", "run", "-d", "--name", AI_CONTAINER, "--restart", "unless-stopped",
                     "-p", "127.0.0.1:11434:11434", "-v", "xora-ai:/root/.ollama", "docker.io/ollama/ollama:latest"])
            if r.returncode != 0:
                die("couldn't start the AI service")
        else:
            run(["podman", "start", AI_CONTAINER], capture=True)
        if run(["podman", "exec", AI_CONTAINER, "ollama", "pull", model]).returncode == 0:
            ok("local AI is on. Try in the terminal:  # why is my computer slow?")
        return
    if a.action == "disable":
        run(["podman", "stop", AI_CONTAINER], capture=True)
        ok("local AI is off (models kept; `xora ai remove` deletes them)")
        return
    if a.action == "remove":
        if confirm("Delete the AI service and its downloaded models?", False):
            run(["podman", "rm", "-f", AI_CONTAINER], capture=True)
            run(["podman", "volume", "rm", "xora-ai"], capture=True)
            ok("removed")
        return
    st = out(["podman", "ps", "--filter", f"name={AI_CONTAINER}", "--format", "{{.Status}}"]) if have("podman") else ""
    print(f"local AI: {green('on — ' + st) if st else dim('off (enable with: xora ai enable)')}")


# ================================================================ status for the desktop widgets (fast, JSON)

def cmd_status(a):
    from .spaces import active, all_names, load_yaml, path_of, _running_containers
    from .fabric import _devices, QUEUE
    from .util import load_json
    running = _running_containers()
    spaces = []
    for n in all_names():
        m = load_yaml(path_of(n)) or {}
        svcs = m.get("services") or []
        spaces.append({"name": n, "dir": m.get("dir", ""),
                       "running": sum(1 for s in svcs if f"xora-{n}-{s.get('name')}" in running), "services": len(svcs)})
    devs = _devices()
    conn = _active_conn() if have("nmcli") else []
    metered = False
    if conn:
        metered = out(["nmcli", "-g", "connection.metered", "connection", "show", conn[0]]) in ("yes", "guess-yes")
    today, label = None, "today"
    if have("vnstat"):
        try:
            j = json.loads(out(["vnstat", "--json", "d", "1"]) or "{}")
            days = [d for i in j.get("interfaces", []) for d in i.get("traffic", {}).get("day", [])]
            today = sum(d.get("rx", 0) + d.get("tx", 0) for d in days) or None
        except (json.JSONDecodeError, TypeError):
            pass
    try:   # internet only (the budget service skips LAN / Fabric traffic, which costs no data)
        nb = json.loads(NETBUDGET_STATUS.read_text())
        if nb.get("day") == time.strftime("%F") and "internet" in nb:
            today, label = nb["internet"], "today"
    except (OSError, ValueError):
        pass
    if today is None:
        today, label = 0, "since boot"
        for dev in Path("/sys/class/net").iterdir():
            if dev.name != "lo":
                try:
                    today += int((dev / "statistics/rx_bytes").read_text()) + int((dev / "statistics/tx_bytes").read_text())
                except OSError:
                    pass
    cap, st = _battery()
    data = {"space": active(), "spaces": spaces, "devices": len(devs) + 1, "paired": list(devs),
            "queued_jobs": len(load_json(QUEUE, [])), "metered": metered, "data_today": today,
            "data_today_h": human(today), "data_label": label, "battery": cap, "battery_status": st,
            "anon": anon_on(), **_vpn_state()}
    print(json.dumps(data))


# ================================================================ Anon mode: all traffic through Tor, with a kill switch

ANON_HOOK = "/usr/lib/xora/hooks/anon"


def _vpn_state():
    try:
        from .vpn import active, killswitch_on
        on = active() if have("nmcli") else []
        return {"vpn": on[0][0] if on else None, "vpn_killswitch": killswitch_on()}
    except Exception:
        return {"vpn": None, "vpn_killswitch": False}


def anon_on():
    """True when Anon mode is on (the Tor instance runs; the routing rules need root to read)."""
    return have("systemctl") and out(["systemctl", "is-active", "xora-anon-tor.service"]) == "active"


def cmd_anon(a):
    action = a.action or "status"
    if action in ("on", "off"):
        if not Path(ANON_HOOK).exists() or not have("tor"):
            die("Anon mode needs XORA OS (Tor and the anon helper aren't installed here)")
        if os.geteuid() == 0:
            argv = [ANON_HOOK, action]
        elif sys.stdin.isatty() and have("sudo"):
            argv = ["sudo", ANON_HOOK, action]
        else:
            argv = ["pkexec", ANON_HOOK, action]      # desktop password prompt
        r = run(argv)
        if r.returncode == 0 and action == "on":
            info("Check it: xora anon check")
        return r.returncode
    if action == "check":
        import urllib.request
        try:
            with urllib.request.urlopen("https://check.torproject.org/api/ip", timeout=30) as resp:
                j = json.loads(resp.read())
        except Exception as e:
            die(f"couldn't reach the Tor check service: {e}")
        if j.get("IsTor"):
            ok(f"Your traffic leaves through Tor (exit address {j.get('IP')}). Websites can't see your real address.")
        else:
            warn(f"NOT going through Tor: websites see {j.get('IP')}. Turn it on with: xora anon on")
        return
    if anon_on():
        ok("Anon mode is ON: all traffic goes through Tor, and the kill switch blocks anything else.")
    else:
        info("Anon mode is off. Turn it on with: xora anon on")
