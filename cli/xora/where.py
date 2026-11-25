"""Files that know where they live.

    xora where FILE [--gui]

Answers: which device it's on, which Space it belongs to, where its copies are (linked devices that
keep copies, checked live), its versions in the Timeline, and its Git status. --gui shows the same in
a window (Files › right-click › Where is this file?).
"""
import os
import shlex
import subprocess
import time
from pathlib import Path

from .util import ago, bold, die, dim, green, have, human, out, tilde, yellow


def facts(path):
    from .fabric import SSH_OPTS, _devices
    from .spaces import all_names, load_yaml, path_of, project_dir
    from .timeline import _index
    p = Path(path).absolute()
    if not p.exists() and not p.is_symlink():
        die(f"{path} doesn't exist")
    st = p.lstat()
    f = {"path": tilde(p), "device": os.uname().nodename, "size": st.st_size if p.is_file() else None,
         "modified": st.st_mtime, "space": None, "rel": None, "copies": [], "versions": [], "git": None}

    # Space
    real = p.resolve()
    for n in all_names():
        d = project_dir({"space": n, **(load_yaml(path_of(n)) or {})}).resolve()
        if real == d or d in real.parents:
            f["space"], f["rel"] = n, str(real.relative_to(d))
            break

    # copies on linked devices (Fabric mirror keeps Spaces on devices allowed to 'store')
    if f["space"]:
        for name, dev in _devices().items():
            if "store" not in dev.get("can", []):
                continue
            remote = f".xora/mirror/{os.uname().nodename}/{f['space']}/{f['rel']}"
            try:
                r = subprocess.run(["ssh", *SSH_OPTS, "-o", "ConnectTimeout=3", dev["host"],
                                    f"stat -c %Y {shlex.quote(remote)} 2>/dev/null || echo missing"],
                                   capture_output=True, text=True, timeout=8)
                v = r.stdout.strip()
                state = "offline" if r.returncode not in (0,) and not v else \
                        "no copy yet" if v == "missing" else \
                        ("up to date" if float(v) >= st.st_mtime - 1 else f"copy from {ago(float(v))}")
            except (subprocess.TimeoutExpired, ValueError):
                state = "offline"
            f["copies"].append({"device": name, "state": state})

    # Timeline versions: snapshots of this path or of a folder containing it
    for e in _index():
        sp = Path(e["path"])
        if sp == p or sp in p.parents:
            f["versions"].append({"id": e["id"], "at": e["at"], "reason": e.get("reason", ""), "restored": e.get("restored")})

    # Git
    d = p if p.is_dir() else p.parent
    top = out(["git", "-C", str(d), "rev-parse", "--show-toplevel"], timeout=5) if have("git") else ""
    if top:
        st_line = out(["git", "-C", top, "status", "--porcelain", "--", str(real)], timeout=5)
        last = out(["git", "-C", top, "log", "-1", "--format=%h %ar · %s", "--", str(real)], timeout=5)
        branch = out(["git", "-C", top, "rev-parse", "--abbrev-ref", "HEAD"], timeout=5)
        code = st_line[:2].strip() if st_line else ""
        f["git"] = {"branch": branch, "last": last or "never committed",
                    "state": {"": "committed, no changes", "M": "changed since last commit", "A": "added, not committed",
                              "??": "not tracked by Git", "D": "deleted"}.get(code, f"git: {code}")}
    return f


def render(f):
    lines = [f"{f['path']}",
             f"On this device: {f['device']}" + (f" · {human(f['size'])}" if f["size"] is not None else "") +
             f" · changed {ago(f['modified'])}"]
    lines.append(f"Space: {f['space']}" if f["space"] else "Not in a Space (no automatic copies on other devices)")
    if f["copies"]:
        lines.append("Copies: " + ", ".join(f"{c['device']} ({c['state']})" for c in f["copies"]))
    elif f["space"]:
        lines.append("Copies: none yet. Allow a linked device to 'Store backups' in XORA Center › Devices")
    if f["versions"]:
        v = f["versions"]
        lines.append(f"Versions: {len(v)} in the Timeline, latest {ago(v[0]['at'])} ({v[0]['reason'][:40]})")
    else:
        lines.append("Versions: none yet (a snapshot is taken before it's deleted, and Spaces are checkpointed)")
    if f["git"]:
        g = f["git"]
        lines.append(f"Git: {g['state']} · branch {g['branch']} · last commit {g['last']}")
    return lines


def cmd_where(a):
    f = facts(a.path)
    lines = render(f)
    if a.gui and have("kdialog"):
        subprocess.Popen(["kdialog", "--title", "Where is this file?", "--msgbox", "\n\n".join(lines)])
        return
    print(bold(lines[0]))
    for line in lines[1:]:
        k, _, v = line.partition(": ")
        print(f"  {green(k + ':') if v else dim(line)} {v}" if v else f"  {dim(line)}")
