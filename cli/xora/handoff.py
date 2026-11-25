"""Move a Space to another device, or share it.

    xora space handoff NAME --to DEVICE [--with-secrets] [--keep-running]
    xora space share NAME --with DEVICE      that device may open NAME (copied by the hourly mirror, or now)
    xora space unshare NAME --with DEVICE

Handoff is a fast, safe move, not a live migration: the Space is checkpointed (Timeline), its services
stopped cleanly (databases flush), then code, database volumes and the manifest are copied over SSH and
the Space is started on the other device. Downtime is the copy time; nothing is lost if the copy fails,
because the local copy is untouched and restarted.
"""
import os
import shlex
import subprocess

from .util import bold, confirm, die, info, ok, run, tilde, warn


def _dev(name, need):
    from .fabric import _devices, _probe
    devs = _devices()
    if name not in devs:
        die(f"no linked device '{name}'. Linked: {', '.join(devs) or 'none (XORA Center › Devices)'}")
    d = devs[name]
    if not set(need) & set(d.get("can", [])):
        die(f"{name} isn't allowed to {' or '.join(need)} for you. Allow it in XORA Center › Devices.")
    p = _probe(d["host"])
    if not p["online"]:
        die(f"{name} is offline ({p.get('error')})")
    return d


def _ssh(host, cmd, **kw):
    from .fabric import SSH_OPTS
    return subprocess.run(["ssh", *SSH_OPTS, host, cmd], capture_output=True, text=True, **kw)


def _volumes(m):
    """Named volumes this Space's services use (bind mounts live in the project folder and travel with it)."""
    vols = []
    for s in m.get("services") or []:
        if s.get("volume"):
            vols.append(s["volume"])
        for v in s.get("volumes") or []:
            src = v.split(":")[0]
            if src and not src.startswith((".", "/", "~")):
                vols.append(src)
    return list(dict.fromkeys(vols))


def cmd_handoff(a):
    from .fabric import SSH_OPTS
    from .spaces import ACTIVE_FILE, _services_down, _services_up, load, path_of, project_dir
    from .timeline import snapshot
    m = load(a.name)
    name, d = m["space"], project_dir(m)
    dev = _dev(a.to, ["spaces", "run", "build"])
    host = dev["host"]
    if _ssh(host, "command -v xora", timeout=20).returncode != 0:
        die(f"{a.to} doesn't have the xora command, so it can't run Spaces (is it a XORA device?)")
    secrets = [s for svc in m.get("services") or [] for s in svc.get("secrets") or []]
    if secrets and not a.with_secrets:
        warn(f"{len(secrets)} secret(s) stay on this device (pass --with-secrets to copy them into {a.to}'s keyring)")
    print(bold(f"Handing off {name} → {a.to}"))

    # 1. safety first: a checkpoint, then a clean stop so databases are consistent on disk
    if d.exists():
        e = snapshot(d, f"before handoff to {a.to}", name)
        ok(f"checkpoint {e['id']}")
    _services_down(m)

    failed = None
    try:
        # 2. project files (rsync only sends what changed)
        remote_dir = tilde(d)
        r = run(["rsync", "-az", "--delete", "--mkpath", "-e", "ssh " + " ".join(SSH_OPTS), f"{d}/", f"{host}:{remote_dir}/"],
                capture=True, timeout=7200)
        if r.returncode != 0:
            raise RuntimeError(f"copying files: {r.stderr.strip()[-200:]}")
        ok(f"files → {a.to}:{remote_dir}")
        # 3. database volumes
        for v in _volumes(m):
            exp = subprocess.Popen(["podman", "volume", "export", v], stdout=subprocess.PIPE)
            imp = subprocess.run(["ssh", *SSH_OPTS, host,
                                  f"podman volume exists {shlex.quote(v)} || podman volume create {shlex.quote(v)} >/dev/null; "
                                  f"podman volume import {shlex.quote(v)} -"],
                                 stdin=exp.stdout, capture_output=True, text=True, timeout=7200)
            exp.stdout.close()
            if exp.wait() != 0 or imp.returncode != 0:
                raise RuntimeError(f"copying volume {v}: {imp.stderr.strip()[-200:]}")
            ok(f"volume {v} → {a.to}")
        # 4. manifest
        r = run(["rsync", "-a", "--mkpath", "-e", "ssh " + " ".join(SSH_OPTS), str(path_of(name)),
                 f"{host}:.config/xora/spaces/"], capture=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"copying the manifest: {r.stderr.strip()[-200:]}")
        # 5. secrets (only when asked): straight into the other keyring, never written to disk
        if a.with_secrets:
            from .vault import resolve
            for sec in secrets:
                ref = sec["ref"]
                if not ref.startswith("keyring:"):
                    continue
                val = resolve(ref)
                if val is None:
                    continue
                key = ref.split(":", 1)[1]
                r = subprocess.run(["ssh", *SSH_OPTS, host, f"xora secret set {shlex.quote(key)}"],
                                   input=val, capture_output=True, text=True, timeout=60)
                (ok if r.returncode == 0 else warn)(f"secret {key} → {a.to}" + ("" if r.returncode == 0 else f": {r.stderr.strip()[-120:]}"))
        # 6. start it there
        r = _ssh(host, f"xora space open {shlex.quote(name)} --no-gui", timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"starting on {a.to}: {(r.stdout + r.stderr).strip()[-300:]}")
    except Exception as e:  # nothing is lost: the local copy is untouched; bring it back up here
        failed = str(e)

    if failed:
        warn(f"handoff stopped: {failed}")
        info("restarting the Space here, as it was")
        _services_up(m, d)
        return 1
    if ACTIVE_FILE.exists() and ACTIVE_FILE.read_text().strip() == name:
        ACTIVE_FILE.unlink()
    ok(f"{name} is now running on {a.to}. Its files here are kept as a copy.")
    info(f"Open it there: ssh {host}   ·   Bring it back: xora space handoff {name} --to <this device>")


def _share_list(name):
    from .spaces import load_yaml, path_of
    m = load_yaml(path_of(name)) or {}
    sh = m.get("share")
    return m, ([] if sh in (None, False) else sh if isinstance(sh, list) else ["*"])


def cmd_share(a):
    from .fabric import cmd_mirror
    from .spaces import path_of
    from .util import save_yaml
    m, lst = _share_list(a.name)
    if not m:
        die(f"no Space called '{a.name}'")
    _dev(a.with_, ["spaces"])
    if a.with_ not in lst and "*" not in lst:
        lst.append(a.with_)
    m["share"] = lst
    save_yaml(path_of(a.name), m)
    ok(f"{a.with_} may open {a.name}. Copying it there now…")
    return cmd_mirror(type("A", (), {"space": a.name})())


def cmd_unshare(a):
    from .spaces import path_of
    from .util import save_yaml
    m, lst = _share_list(a.name)
    if not m:
        die(f"no Space called '{a.name}'")
    m["share"] = [x for x in lst if x not in (a.with_, "*")] or False
    save_yaml(path_of(a.name), m)
    ok(f"{a.with_} won't receive {a.name} any more (copies already there stay until deleted on that device)")
