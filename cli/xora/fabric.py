"""Fabric: your devices cooperate. V1 = trusted devices + remote jobs.

Transport is SSH (works over LAN, WireGuard or Tailscale). Each paired device has
explicit capabilities (build, run) and can be revoked at any time.

    xora fabric pair office-pc pafra@192.168.1.20 --can build,run
    xora fabric ls
    xora fabric run --on office-pc -- flutter build apk     # sync Space, run there, bring results back
    xora fabric run --on auto --get build/ -- make -j16
    xora fabric revoke office-pc

Failure policy for `run` (--fallback): local (default) | queue | fail
"""
import os
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .util import (DEVICES_FILE, STATE, bold, cyan, die, dim, err, green, have, info, load_json, load_yaml, ok, out,
                   red, run, save_json, save_yaml, warn, yellow, confirm)

QUEUE = STATE / "fabric-queue.json"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=15"]


EXPOSURE = "/usr/lib/xora/hooks/exposure"


def expose(action):
    """Open or close what other devices need (SSH, pairing, discovery) via XORA's stealth helper.
    XORA answers nothing on the network by default; this asks for the admin password when needed."""
    if not Path(EXPOSURE).exists():
        return True                     # not on XORA (development machine): nothing to do
    import sys
    if os.geteuid() == 0:
        argv = [EXPOSURE, action]
    elif sys.stdin.isatty() and have("sudo"):
        argv = ["sudo", EXPOSURE, action]
    else:
        argv = ["pkexec", EXPOSURE, action]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        warn(f"couldn't change network visibility ({action}); linked devices may not reach this one")
    return r.returncode == 0


def _places():
    from .places import sync
    try:
        sync()
    except Exception:  # the Files sidebar is a convenience; never fail pairing over it
        pass


def _devices():
    return load_yaml(DEVICES_FILE, {}) or {}


def _save(devs):
    save_yaml(DEVICES_FILE, devs)


def _probe(host):
    """Return dict with online, cpus, load, mem_free_mb, arch, or online False."""
    script = "uname -m; nproc; cut -d' ' -f1 /proc/loadavg; awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; df -Pm ~ | awk 'NR==2{print $4}'; awk '/MemTotal/{print int($2/1024)}' /proc/meminfo"
    t = time.time()
    r = subprocess.run(["ssh", *SSH_OPTS, host, script], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return {"online": False, "error": (r.stderr.strip().splitlines() or ["unreachable"])[-1]}
    try:
        f = r.stdout.split()
        arch, cpus, load, mem, disk = f[:5]
        return {"online": True, "arch": arch, "cpus": int(cpus), "load": float(load), "mem_free_mb": int(mem),
                "disk_free_mb": int(disk), "mem_total_mb": int(f[5]) if len(f) > 5 else None,
                "rtt_ms": int((time.time() - t) * 1000)}
    except ValueError:
        return {"online": False, "error": "unexpected reply"}


def _local():
    cpus = os.cpu_count() or 1
    load = os.getloadavg()[0]
    mem = total = 0
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            mem = int(line.split()[1]) // 1024
        elif line.startswith("MemTotal"):
            total = int(line.split()[1]) // 1024
    return {"online": True, "arch": os.uname().machine, "cpus": cpus, "load": load, "mem_free_mb": mem,
            "mem_total_mb": total, "rtt_ms": 0}


def _score(p):
    """Higher = better place to run a heavy job: free cores, then free memory."""
    free_cores = max(0.0, p["cpus"] - p["load"])
    return free_cores + p["mem_free_mb"] / 4096 - p.get("rtt_ms", 0) / 200


# ---------------------------------------------------------------- commands

def cmd_pair(a):
    if not have("ssh"):
        die("ssh is not installed")
    name, host = a.name, a.host
    devs = _devices()
    if name in devs and not a.force:
        die(f"'{name}' is already paired. Use --force to re-pair.")
    info(f"checking {host} …")
    p = _probe(host)
    if not p["online"]:
        warn(f"can't log in to {host} without a password ({p['error']}).")
        key = Path.home() / ".ssh/id_ed25519"
        if not key.exists() and confirm("Create an SSH key for this computer?", True):
            run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key), "-C", f"xora@{os.uname().nodename}"])
        if confirm(f"Copy this computer's key to {host}? (you'll type its password once)", True):
            run(["ssh-copy-id", "-i", str(key) + ".pub", host])
            p = _probe(host)
        if not p["online"]:
            die(f"pairing failed: {p.get('error')}")
    caps = [c.strip() for c in a.can.split(",") if c.strip()]
    devs[name] = {"host": host, "arch": p["arch"], "cpus": p["cpus"], "can": caps, "paired": time.strftime("%Y-%m-%d")}
    _save(devs)
    _places()
    ok(f"Paired {bold(name)} ({host}): {p['cpus']} cores, {p['arch']}, {p['mem_free_mb']} MB free. Allowed: {', '.join(caps)}")
    info(f"Revoke any time with: xora fabric revoke {name}")


def cmd_revoke(a):
    devs = _devices()
    if a.name not in devs:
        die(f"no device '{a.name}'")
    d = devs.pop(a.name)
    _save(devs)
    _places()
    ok(f"Removed {a.name} from Fabric.")
    if not devs and expose("fabric-off"):
        info("No linked devices left: this computer is invisible on the network again (SSH off).")
    pub = Path.home() / ".ssh/id_ed25519.pub"
    if pub.exists() and confirm(f"Also remove this computer's key from {d['host']} so it can't log in any more?", True):
        key = pub.read_text().split()[1]
        r = run(["ssh", *SSH_OPTS, d["host"], f"sed -i.bak '\\#{key}#d' ~/.ssh/authorized_keys"], capture=True)
        ok("key removed on the other device") if r.returncode == 0 else warn("couldn't reach it; remove the key there manually")


def cmd_ls(a):
    devs = _devices()
    loc = _local()
    print(f"{green('●')} {'this computer':16} {dim('local'):24} {loc['cpus']:>3} cores  load {loc['load']:.1f}  {loc['mem_free_mb']:>6} MB free  {cyan('(here)')}")
    if not devs:
        info("No other devices yet. Pair one with: xora fabric pair <name> <user@host>")
        return
    with ThreadPoolExecutor(8) as ex:
        probes = dict(zip(devs, ex.map(lambda n: _probe(devs[n]["host"]), devs)))
    for n, d in devs.items():
        p = probes[n]
        if p["online"]:
            print(f"{green('●')} {n:16} {dim(d['host']):24} {p['cpus']:>3} cores  load {p['load']:.1f}  {p['mem_free_mb']:>6} MB free  {dim(','.join(d.get('can', [])))}  {dim(str(p['rtt_ms']) + 'ms')}")
        else:
            print(f"{dim('○')} {n:16} {dim(d['host']):24} {red('offline')}  {dim(p.get('error', ''))}")


def _pick(devs, cap):
    cands = {n: d for n, d in devs.items() if cap in d.get("can", [])}
    with ThreadPoolExecutor(8) as ex:
        probes = dict(zip(cands, ex.map(lambda n: _probe(cands[n]["host"]), cands)))
    best, best_score = None, _score(_local())
    for n, p in probes.items():
        if p["online"] and p["arch"] == os.uname().machine and _score(p) > best_score:
            best, best_score = n, _score(p)
    return best


def cmd_run(a):
    from .spaces import active, load, project_dir
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        die("usage: xora fabric run --on <device|auto> -- <command>")
    devs = _devices()
    target = a.on
    if target == "auto":
        target = _pick(devs, "run" if not a.build else "build")
        if not target:
            info("this computer is the best place for this job; running here")
            return subprocess.call(cmd)
    if target not in devs:
        die(f"no device '{target}'. See: xora fabric ls")
    dev = devs[target]
    if "run" not in dev.get("can", []) and "build" not in dev.get("can", []):
        die(f"{target} is not allowed to run jobs. Re-pair with --can run")

    space = active()
    root = project_dir(load(space)) if space else Path.cwd()
    rel = os.path.relpath(Path.cwd(), root) if Path.cwd().is_relative_to(root) else "."
    remote_root = f".xora/fabric/{space or root.name}"
    host = dev["host"]

    p = _probe(host)
    if not p["online"]:
        return _fallback(a, cmd, f"{target} is offline ({p.get('error')})")

    info(f"Syncing {bold(str(root))} to {target} …")
    excludes = []
    for f in (".gitignore",):
        if (root / f).exists():
            excludes += ["--filter", f":- {f}"]
    r = run(["rsync", "-az", "--delete", "--info=stats1", "-e", "ssh " + " ".join(SSH_OPTS), *excludes,
             "--exclude", ".git/", f"{root}/", f"{host}:{remote_root}/"], capture=True)
    if r.returncode != 0:
        return _fallback(a, cmd, f"sync failed: {r.stderr.strip()[-200:]}")
    ok("synced")
    remote_cmd = f"cd {shlex.quote(remote_root)}/{shlex.quote(rel)} && {' '.join(shlex.quote(c) for c in cmd)}"
    print(f"{cyan('[fabric]')} running on {bold(target)}: {' '.join(cmd)}")
    t = time.time()
    code = subprocess.call(["ssh", "-t" if os.isatty(0) else "-T", *SSH_OPTS[2:], host, "bash -lc " + shlex.quote(remote_cmd)])
    took = time.time() - t
    if code == 255:
        return _fallback(a, cmd, f"lost connection to {target}")
    gets = a.get or []
    for g in gets:
        src = f"{host}:{remote_root}/{rel}/{g}".replace("/./", "/")
        dst = (Path.cwd() / g)
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = run(["rsync", "-az", "-e", "ssh " + " ".join(SSH_OPTS), src, str(dst.parent) + "/"], capture=True)
        ok(f"brought back {g}") if r.returncode == 0 else warn(f"couldn't bring back {g}: {r.stderr.strip()[-120:]}")
    (ok if code == 0 else err)(f"job on {target} finished with exit code {code} in {took:.0f}s")
    return code


def _fallback(a, cmd, why):
    warn(why)
    if a.fallback == "local":
        info("running it here instead (--fallback local)")
        return subprocess.call(cmd)
    if a.fallback == "queue":
        q = load_json(QUEUE, [])
        q.append({"cmd": cmd, "on": a.on, "cwd": str(Path.cwd()), "at": time.time(), "get": a.get or []})
        save_json(QUEUE, q)
        ok(f"queued; run `xora fabric queue --run` when {a.on} is back")
        return 0
    return 1


def cmd_queue(a):
    q = load_json(QUEUE, [])
    if not q:
        info("queue is empty")
        return
    if not a.run:
        for i, j in enumerate(q):
            print(f"{i + 1}. on {j['on']}: {' '.join(j['cmd'])}  {dim(j['cwd'])}")
        return
    rest = []
    for j in q:
        os.chdir(j["cwd"])
        ns = type("A", (), {"cmd": j["cmd"], "on": j["on"], "get": j["get"], "fallback": "fail", "build": False})
        if cmd_run(ns) != 0:
            rest.append(j)
    save_json(QUEUE, rest)


# ---------------------------------------------------------------- QR / code pairing
# Device A: `xora fabric invite`  → shows a QR + code, listens once on the LAN.
# Device B: `xora fabric join <code>` → both sides exchange SSH keys and add each other,
#           each with the capabilities its owner chose. Code expires after 10 minutes.

import base64
import hashlib
import hmac
import http.server
import json as _json
import secrets as _secrets
import socket
import threading
import urllib.error
import urllib.request

PAIR_PORT = 47821
INVITE_TTL = 300            # seconds a pairing code stays valid
MAX_BAD_TRIES = 5           # a 6-digit code is short: close the invite after a few wrong guesses


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _ensure_key():
    key = Path.home() / ".ssh/id_ed25519"
    if not key.exists():
        key.parent.mkdir(mode=0o700, exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), "-C", f"xora@{os.uname().nodename}"], check=True)
    return (key.with_suffix(".pub")).read_text().strip()


def _authorize(pubkey, label):
    ak = Path.home() / ".ssh/authorized_keys"
    ak.parent.mkdir(mode=0o700, exist_ok=True)
    existing = ak.read_text() if ak.exists() else ""
    if pubkey.split()[1] not in existing:
        with open(ak, "a") as f:
            f.write(f"{pubkey.split()[0]} {pubkey.split()[1]} xora-fabric:{label}\n")
        os.chmod(ak, 0o600)


def _me():
    mem = 0
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                mem = int(line.split()[1]) // 1024
    except OSError:
        pass
    return {"name": os.uname().nodename, "user": os.environ.get("USER", "user"), "ip": _lan_ip(),
            "pubkey": _ensure_key(), "arch": os.uname().machine, "cpus": os.cpu_count(), "mem_mb": mem}


def _sig(token, body):
    return hmac.new(token.encode(), body, hashlib.sha256).hexdigest()


def add_device(name, peer, can):
    devs = _devices()
    devs[name] = {"host": f"{peer['user']}@{peer['ip']}", "arch": peer.get("arch"), "cpus": peer.get("cpus"),
                  "mem_mb": peer.get("mem_mb"), "can": list(can), "paired": time.strftime("%Y-%m-%d")}
    _save(devs)
    _places()
    expose("fabric-on")                 # the linked device reaches this one over SSH (local network, keys only)


def set_caps(name, can):
    devs = _devices()
    if name in devs:
        devs[name]["can"] = list(can)
        _save(devs)


class Invite:
    """One pairing invitation: a 6-digit code (also inside a QR code) that one other device can use once.

    The code is the HMAC key for the exchange, so a device that doesn't know it can't take part,
    and the invite closes after MAX_BAD_TRIES wrong attempts. Nothing is trusted until `accept()`.
    """

    def __init__(self, ttl=INVITE_TTL):
        self.digits = f"{_secrets.randbelow(10**6):06d}"
        self.me = _me()
        self.expires = time.time() + ttl
        self.peer = None
        self.closed = False
        self.arrived = threading.Event()
        self._bad = 0
        inv = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *x):
                pass

            def do_POST(self):
                body = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 65536))
                if inv.peer or inv.closed or time.time() > inv.expires or \
                        not hmac.compare_digest(self.headers.get("X-Xora-Sig", ""), _sig(inv.digits, body)):
                    inv._bad += 1
                    if inv._bad >= MAX_BAD_TRIES:
                        inv.closed = True
                    self.send_response(403)
                    self.end_headers()
                    return
                try:
                    peer = _json.loads(body)
                    assert all(k in peer for k in ("name", "user", "ip", "pubkey"))
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return
                peer["ip"] = self.client_address[0]     # trust the address it came from, not what it says
                reply = _json.dumps(inv.me).encode()
                self.send_response(200)
                self.send_header("X-Xora-Sig", _sig(inv.digits, reply))
                self.end_headers()
                self.wfile.write(reply)
                inv.peer = peer
                inv.arrived.set()

        self._srv = http.server.HTTPServer(("0.0.0.0", PAIR_PORT), H)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        expose("pair-open")             # port 47821 for 5 minutes (closes itself), local network only

    @property
    def code(self):
        """Long form for the QR code and copy-paste: includes this device's address."""
        return base64.urlsafe_b64encode(f"{self.me['ip']}:{PAIR_PORT}:{self.digits}".encode()).decode().rstrip("=")

    @property
    def pretty(self):
        return f"{self.digits[:3]} {self.digits[3:]}"

    def remaining(self):
        return max(0, int(self.expires - time.time()))

    def wait(self, timeout=None):
        return self.arrived.wait(timeout)

    def accept(self, can, name=None):
        name = name or self.peer["name"]
        _authorize(self.peer["pubkey"], name)
        add_device(name, self.peer, can)
        self.close()
        return name

    def close(self):
        if not getattr(self, "_closed_net", False):
            self._closed_net = True
            expose("pair-close")
        self.closed = True
        try:
            self._srv.shutdown()
            self._srv.server_close()
        except Exception:
            pass


def parse_code(text):
    """→ (ip or None, port, digits). Accepts the long code, the QR text, or just the 6 digits."""
    raw = text.strip().replace("xora-pair:", "")
    digits = raw.replace(" ", "").replace("-", "")
    if digits.isdigit() and len(digits) == 6:
        return None, PAIR_PORT, digits
    try:
        ip, port, token = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode().split(":")
        return ip, int(port), token
    except Exception:
        raise ValueError("that code isn't valid")


def join(ip, port, digits, can, name=None):
    """Send our details to the inviting device; returns the name it was saved under. Raises on failure."""
    me = _me()
    body = _json.dumps(me).encode()
    req = urllib.request.Request(f"http://{ip}:{port}/", data=body, headers={"X-Xora-Sig": _sig(digits, body)})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError("the code didn't match (or it expired). Check the 6 digits on the other device")
        raise RuntimeError(f"the other device refused ({e.code})")
    except Exception as e:
        raise RuntimeError(f"couldn't reach the other device ({getattr(e, 'reason', e)})")
    reply = resp.read()
    if not hmac.compare_digest(resp.headers.get("X-Xora-Sig", ""), _sig(digits, reply)):
        raise RuntimeError("the other device's answer wasn't signed with the code, so pairing stopped")
    peer = _json.loads(reply)
    peer["ip"] = ip
    name = name or peer["name"]
    _authorize(peer["pubkey"], name)
    add_device(name, peer, can)
    return name


def discover(timeout=6):
    """XORA devices announcing themselves on this network: [{name, ip, paired_as}]."""
    if not have("avahi-browse"):
        return []
    if not (Path("/var/lib/xora/exposure") / "fabric").exists():
        expose("seek")                  # let discovery answers in for a minute
    r = run(["avahi-browse", "-rtp", "_xora._tcp"], capture=True, timeout=timeout)
    me = os.uname().nodename
    by_ip = {d["host"].split("@")[-1]: n for n, d in _devices().items()}
    found = {}
    for line in (r.stdout or "").splitlines():
        p = line.split(";")
        if p[0] == "=" and len(p) > 8 and p[2] == "IPv4" and p[3] != me:
            found[p[3]] = {"name": p[3], "ip": p[7], "paired_as": by_ip.get(p[7])}
    return list(found.values())


def cmd_invite(a):
    if not Path("/usr/sbin/sshd").exists() and not have("sshd"):
        warn("this device has no SSH server, so others can't run jobs on it (they can still be used from here)")
    try:
        inv = Invite()
    except OSError as e:
        die(f"can't listen for pairing on port {PAIR_PORT}: {e}")
    print(bold("\n  Add a device to your XORA Fabric\n"))
    if have("qrencode"):
        subprocess.run(["qrencode", "-t", "ansiutf8", "-m", "2", f"xora-pair:{inv.code}"])
    print(f"  On the other device enter   {bold(green(inv.pretty))}")
    print(f"  or run:   {green('xora fabric join ' + inv.code)}")
    print(dim(f"  (this device: {inv.me['name']} at {inv.me['ip']} · code expires in {inv.remaining() // 60} minutes)\n"))
    while not inv.wait(1):
        if inv.closed or not inv.remaining():
            inv.close()
            die("too many wrong codes, invite closed" if inv.closed and inv.remaining() else "pairing code expired")
    peer = inv.peer
    print(f"  {bold(peer['name'])} ({peer['user']}@{peer['ip']}, {peer.get('cpus')} cores) wants to join.")
    if not confirm(f"Allow it? It will be able to: {a.can}", True):
        inv.close()
        die("pairing refused")
    name = inv.accept([c for c in a.can.split(",") if c], a.name)
    ok(f"Paired with {peer['name']}. Revoke any time: xora fabric revoke {name}")


def cmd_join(a):
    try:
        ip, port, digits = parse_code(" ".join(a.code))
    except ValueError as e:
        die(str(e))
    targets = [ip] if ip else [d["ip"] for d in discover() if not d["paired_as"]]
    if not targets:
        die("no XORA device is inviting on this network. Use the long code from `xora fabric invite`.")
    info("contacting " + ", ".join(targets) + " …")
    last = None
    for t in targets:
        try:
            name = join(t, port, digits, [c for c in a.can.split(",") if c], a.name)
            ok(f"Linked with {name}. It can see this device once it presses Allow. Try: xora fabric ls")
            return
        except RuntimeError as e:
            last = e
    die(str(last))


def cmd_discover(a):
    """Find XORA devices on the local network (Avahi/mDNS)."""
    if not have("avahi-browse"):
        die("avahi-browse is not installed")
    found = discover()
    if not found:
        info("no other XORA devices found on this network")
    for d in found:
        tag = green(f"paired as {d['paired_as']}") if d["paired_as"] else dim("not paired: run `xora fabric invite` on one of them")
        print(f"  {bold(d['name']):30} {d['ip']:16} {tag}")


# ---------------------------------------------------------------- nothing is lost: mirror Spaces to paired devices

def shared_spaces(device):
    """Spaces this device may open: manifests with `share: true` or `share: [device, ...]`."""
    from .spaces import all_names, load_yaml, path_of
    res = []
    for n in all_names():
        sh = (load_yaml(path_of(n)) or {}).get("share")
        if sh is True or (isinstance(sh, list) and (device in sh or "*" in sh)):
            res.append(n)
    return res


def cmd_mirror(a):
    """Nothing is lost: copy Space folders to devices allowed to 'store', and hand the manifests of
    shared Spaces to devices allowed to open 'spaces' (they then appear in that device's Space list)."""
    from .spaces import all_names, load, path_of, project_dir
    all_devs = _devices()
    devs = {n: d for n, d in all_devs.items() if "store" in d.get("can", [])}
    sharers = {n: d for n, d in all_devs.items() if "spaces" in d.get("can", [])}
    if not devs and not sharers:
        info("No device is allowed to keep copies or open Spaces. Allow it in XORA Center › Devices.")
        return
    names = [a.space] if a.space else all_names()
    bad = 0
    online = {}
    for dn, d in {**devs, **sharers}.items():
        online[dn] = _probe(d["host"])["online"]
        if not online[dn]:
            warn(f"{dn} is offline; will copy next time")
    for dn, d in devs.items():
        if not online[dn]:
            continue
        for n in names:
            src = project_dir(load(n))
            if not src.exists():
                continue
            dest = f"{d['host']}:.xora/mirror/{os.uname().nodename}/{n}/"
            r = run(["rsync", "-az", "--delete", "-e", "ssh " + " ".join(SSH_OPTS), f"{src}/", dest], capture=True, timeout=3600)
            if r.returncode == 0:
                ok(f"{n} → {dn}")
            else:
                bad += 1
                err(f"{n} → {dn}: {r.stderr.strip()[-150:]}")
    for dn, d in sharers.items():
        if not online[dn]:
            continue
        share = [n for n in shared_spaces(dn) if n in names]
        if not share:
            continue
        files = [str(path_of(n)) for n in share]
        r = run(["rsync", "-a", "--mkpath", "-e", "ssh " + " ".join(SSH_OPTS), *files, f"{d['host']}:.config/xora/spaces/"],
                capture=True, timeout=120)
        if r.returncode == 0:
            ok(f"{dn} can now open: {', '.join(share)}")
        else:
            bad += 1
            err(f"sharing Spaces with {dn}: {r.stderr.strip()[-150:]}")
    return 1 if bad else 0


def cmd_recover(a):
    """Pull a Space back from a device's mirror (e.g. after a laptop died)."""
    devs = _devices()
    if a.device not in devs:
        die(f"no device '{a.device}'")
    host = devs[a.device]["host"]
    src_host = a.from_host or os.uname().nodename
    dest = Path(a.to or f"~/Spaces/{a.space}").expanduser()
    if dest.exists() and any(dest.iterdir()):
        die(f"{dest} is not empty; choose another folder with --to")
    dest.mkdir(parents=True, exist_ok=True)
    r = run(["rsync", "-az", "-e", "ssh " + " ".join(SSH_OPTS), f"{host}:.xora/mirror/{src_host}/{a.space}/", f"{dest}/"])
    (ok if r.returncode == 0 else err)(f"recovered {a.space} into {dest}" if r.returncode == 0 else "recovery failed")


# ---------------------------------------------------------------- shared downloads: move container images device-to-device

def cmd_image_push(a):
    """Download once, share over the LAN: only to devices allowed to share downloads ('net')."""
    devs = _devices()
    targets = [n for n, d in devs.items() if "net" in d.get("can", [])] if a.to == "all" else [a.to]
    if not targets:
        info("No device is allowed to share downloads. Tick 'Share its internet' in XORA Center › Devices.")
    for t in targets:
        if t not in devs:
            die(f"no device '{t}'")
        if "net" not in devs[t].get("can", []):
            die(f"{t} isn't allowed to share downloads. Allow it in XORA Center › Devices (or: it needs 'net').")
        info(f"sending {a.image} to {t} over the LAN (no internet used)")
        p1 = subprocess.Popen(["podman", "save", a.image], stdout=subprocess.PIPE)
        p2 = subprocess.run(["ssh", *SSH_OPTS, devs[t]["host"], "podman load"], stdin=p1.stdout, capture_output=True, text=True)
        p1.wait()
        (ok if p2.returncode == 0 else err)(f"{t}: " + (p2.stdout.strip().splitlines()[-1] if p2.returncode == 0 and p2.stdout.strip() else p2.stderr.strip()[-150:]))


# ---------------------------------------------------------------- send files to a device (Files › Send to a device)

def cmd_send(a):
    devs = _devices()
    if not devs:
        die("no devices linked yet. Add one with: xora fabric invite")
    target = a.to
    if not target:
        if len(devs) == 1:
            target = next(iter(devs))
        elif have("kdialog") and (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
            items = [x for n in devs for x in (n, n)]
            r = subprocess.run(["kdialog", "--title", "Send to a device", "--menu", "Send to which device?", *items],
                               capture_output=True, text=True)
            target = r.stdout.strip()
            if not target:
                return 1
        else:
            die(f"which device? use --to ({', '.join(devs)})")
    if target not in devs:
        die(f"no device '{target}'")
    host = devs[target]["host"]
    paths = [str(Path(p).resolve()) for p in a.paths]
    info(f"sending {len(paths)} item(s) to {target}:~/Received/ over the local network …")
    r = run(["rsync", "-az", "--partial", "--info=progress2", "-e", "ssh " + " ".join(SSH_OPTS), *paths, f"{host}:Received/"])
    if r.returncode == 0:
        ok(f"sent to {target} (in its Received folder)")
        run(["notify-send", "-a", "XORA", "Sent to " + target, f"{len(paths)} item(s) are in Received on {target}"], capture=True)
    else:
        err(f"couldn't send to {target}; is it on?")
    return r.returncode


# ---------------------------------------------------------------- download OS updates once per office

CACHE_PORT = 5000
USER_UNITS = Path.home() / ".config/systemd/user"
QUADLETS = Path.home() / ".config/containers/systemd"


def _booted_registry():
    import json as _j
    try:
        j = _j.loads(subprocess.run(["bootc", "status", "--json"], capture_output=True, text=True, timeout=60).stdout)
        ref = j["status"]["booted"]["image"]["image"]["image"]
    except Exception:
        return None
    first = ref.split("/")[0]
    return first if ("." in first or ":" in first) and first != "localhost" else None


def cmd_update_cache(a):
    """This device keeps a copy of OS updates for the other XORA machines on the network.
    They use it automatically before their nightly update, but only if this device is linked in their Fabric."""
    action = a.action or "status"
    unit = "xora-update-cache.service"
    if action == "status":
        active = out(["systemctl", "--user", "is-active", unit]) == "active"
        print((green("on") if active else dim("off")) + f"  update cache on port {CACHE_PORT}")
        return
    if action == "off":
        run(["systemctl", "--user", "disable", "--now", unit, "xora-update-announce.service"], capture=True)
        expose("cache-off")
        ok("update cache stopped (its copy is kept in the podman volume xora-update-cache)")
        return
    reg = a.registry or _booted_registry()
    if not reg:
        die("this system wasn't installed from an online registry, so there's nothing to cache yet. "
            "Publish XORA to a registry (e.g. ghcr.io) and `sudo bootc switch` to it first, or pass --registry")
    QUADLETS.mkdir(parents=True, exist_ok=True)
    USER_UNITS.mkdir(parents=True, exist_ok=True)
    (QUADLETS / "xora-update-cache.container").write_text(f"""[Unit]
Description=XORA: OS update cache for this network (pull-through copy of {reg})

[Container]
Image=docker.io/library/registry:2
PublishPort={CACHE_PORT}:5000
Volume=xora-update-cache:/var/lib/registry
Environment=REGISTRY_PROXY_REMOTEURL=https://{reg}

[Service]
Restart=on-failure

[Install]
WantedBy=default.target
""")
    (USER_UNITS / "xora-update-announce.service").write_text(f"""[Unit]
Description=XORA: tell linked devices on this network about the update cache
After=xora-update-cache.service
BindsTo=xora-update-cache.service

[Service]
ExecStart=/usr/bin/avahi-publish -s "XORA updates on %H" _xora-updates._tcp {CACHE_PORT}
Restart=on-failure

[Install]
WantedBy=xora-update-cache.service
""")
    run(["systemctl", "--user", "daemon-reload"], capture=True)
    r = run(["systemctl", "--user", "start", "xora-update-cache.service"], capture=True)
    if r.returncode != 0:
        die(f"couldn't start the cache: {r.stderr.strip()[-200:]}")
    run(["systemctl", "--user", "enable", "--now", "xora-update-announce.service"], capture=True)
    expose("cache-on")
    ok(f"caching {reg} on port {CACHE_PORT}. Linked XORA devices on this network now update through this one.")
    info("It keeps running while you're logged in. Stop it with: xora fabric update-cache off")
