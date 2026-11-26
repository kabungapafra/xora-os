"""Timeline: history you can scrub back through.

History providers (shown together, restored separately):
  files    — snapshots XORA takes before deleting, on `xora rm`, and on demand.
             Uses copy-on-write reflinks (instant and free on Btrfs, a normal copy elsewhere).
  system   — OS deployments from bootc / rpm-ostree (roll back with `xora timeline system --rollback`).
  apps     — Flatpak install/update history.
  git      — the Space's recent commits.

Rule: a restore never silently overwrites newer files. If the original path exists,
the snapshot is restored next to it as <name>.restored-<id>.
"""
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .util import (TIMELINE_DIR, bold, cyan, die, dim, green, have, human, info, load_json, ok, out, red, run,
                   save_json, warn, yellow, ago, confirm, tilde)

INDEX = TIMELINE_DIR / "index.json"


def _index():
    return load_json(INDEX, [])


def _save(idx):
    save_json(INDEX, idx)


def _count(p):
    p = Path(p)
    if p.is_symlink() or p.is_file():
        return 1, p.lstat().st_size
    files = size = 0
    for root, dirs, fs in os.walk(p):
        for f in fs:
            files += 1
            try:
                size += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return files, size


def snapshot(path, reason, space=None, batch=None):
    """Copy `path` into the timeline store. Returns the entry."""
    src = Path(path).absolute()
    if not src.exists() and not src.is_symlink():
        raise FileNotFoundError(str(path))
    sid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    dest = TIMELINE_DIR / sid
    dest.mkdir(parents=True)
    target = dest / "data"
    # cp --reflink=auto: instant copy-on-write on Btrfs/XFS, ordinary copy elsewhere
    r = subprocess.run(["cp", "-a", "--reflink=auto", str(src), str(target)], capture_output=True, text=True)
    if r.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"could not snapshot {src}: {r.stderr.strip()}")
    files, size = _count(target)
    entry = {"id": sid, "path": str(src), "reason": reason, "at": time.time(), "files": files,
             "size": size, "kind": "dir" if src.is_dir() and not src.is_symlink() else "file",
             "space": space, "restored": False, "batch": batch}
    idx = _index()
    idx.insert(0, entry)
    _save(idx)
    return entry


def restore(entry, to=None):
    src = TIMELINE_DIR / entry["id"] / "data"
    if not src.exists() and not src.is_symlink():
        raise RuntimeError(f"snapshot {entry['id']} has no data (was it pruned?)")
    dest = Path(to) if to else Path(entry["path"])
    if dest.exists() or dest.is_symlink():
        dest = dest.with_name(dest.name + f".restored-{entry['id']}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["cp", "-a", "--reflink=auto", str(src), str(dest)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    idx = _index()
    for e in idx:
        if e["id"] == entry["id"]:
            e["restored"] = True
            e["restored_to"] = str(dest)
    _save(idx)
    return dest


def _walk_files(base):
    base = Path(base)
    if base.is_file() or base.is_symlink():
        yield ""
        return
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv")]
        for f in files:
            yield os.path.relpath(os.path.join(root, f), base)


def _lines(p):
    try:
        if p.stat().st_size > 2_000_000:
            return None
        b = p.read_bytes()
        if b"\0" in b[:4096]:
            return None
        return b.decode("utf-8", "replace").splitlines()
    except OSError:
        return None


def preview(entry, limit=200):
    """What restoring `entry` into place would do, without changing anything.

    changed:  files that differ from the snapshot and would be put back (+added/-removed lines vs now)
    missing:  files deleted since the snapshot that would come back
    extra:    files created after the snapshot: kept as they are now (so is .git, i.e. your commits)
    Before anything is put back, the current state is snapshotted, so a restore never loses work.
    """
    import difflib
    import filecmp
    snap = TIMELINE_DIR / entry["id"] / "data"
    cur = Path(entry["path"])
    res = {"changed": [], "missing": [], "extra": [], "same": 0, "git": (cur / ".git").exists()}
    if not snap.exists():
        res["error"] = "this snapshot's data was pruned"
        return res
    snap_files = set(_walk_files(snap))
    for rel in sorted(snap_files):
        s, c = (snap / rel) if rel else snap, (cur / rel) if rel else cur
        if not c.exists() and not c.is_symlink():
            res["missing"].append({"path": rel or cur.name})
            continue
        try:
            if c.is_file() and s.is_file() and filecmp.cmp(s, c, shallow=False):
                res["same"] += 1
                continue
        except OSError:
            continue
        a, b = _lines(c), _lines(s)
        plus = minus = None
        if a is not None and b is not None:
            plus = minus = 0
            for line in difflib.unified_diff(a, b, lineterm="", n=0):
                if line.startswith("+") and not line.startswith("+++"):
                    plus += 1
                elif line.startswith("-") and not line.startswith("---"):
                    minus += 1
        res["changed"].append({"path": rel or cur.name, "plus": plus, "minus": minus})
    if cur.is_dir():
        n = 0
        for rel in _walk_files(cur):
            if rel not in snap_files:
                res["extra"].append({"path": rel})
                n += 1
                if n >= limit:
                    break
    return res


def diff(entry, rel):
    """Unified diff: the file now → the file as it was in the snapshot."""
    import difflib
    snap = TIMELINE_DIR / entry["id"] / "data"
    s = (snap / rel) if (snap / rel).exists() else snap
    c = Path(entry["path"]) / rel if Path(entry["path"]).is_dir() else Path(entry["path"])
    a, b = _lines(c) if c.exists() else [], _lines(s)
    if a is None or b is None:
        return "(binary or very large file: no line comparison)"
    return "\n".join(difflib.unified_diff(a, b, f"now/{rel}", f"snapshot/{rel}", lineterm=""))


def restore_merge(entry):
    """Put the snapshot back into place without losing anything:
    1. snapshot the current state first (so this restore can itself be undone),
    2. bring back deleted files and files that changed *before* the snapshot,
    3. keep every file created since the snapshot, and the Git history.
    Returns (backup_entry, restored_count, kept_count)."""
    p = preview(entry)
    if p.get("error"):
        raise RuntimeError(p["error"])
    cur = Path(entry["path"])
    backup = snapshot(cur, f"before restoring {entry['id']}", entry.get("space")) if cur.exists() else None
    snap = TIMELINE_DIR / entry["id"] / "data"
    n = 0
    for item in p["changed"] + p["missing"]:
        rel = item["path"] if snap.is_dir() else ""
        src = (snap / rel) if rel else snap
        dst = (cur / rel) if rel else cur
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["cp", "-a", "--reflink=auto", "--remove-destination", str(src), str(dst)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        n += 1
    return backup, n, len(p["extra"])


def system_history():
    """OS deployments (bootc/rpm-ostree), newest first: [{version, at, booted, rollback, checksum}]."""
    if not have("rpm-ostree"):
        return []
    import json
    try:
        j = json.loads(out(["rpm-ostree", "status", "--json"], timeout=15) or "{}")
    except json.JSONDecodeError:
        return []
    res = []
    for d in j.get("deployments", []):
        res.append({"version": d.get("version") or d.get("checksum", "")[:10], "at": d.get("timestamp"),
                    "booted": bool(d.get("booted")), "staged": bool(d.get("staged")),
                    "image": d.get("container-image-reference", "")})
    return res


def app_history(limit=30):
    """Recent Flatpak installs/updates: [{at, change, app}]."""
    if not have("flatpak"):
        return []
    res = []
    for line in out(["flatpak", "history", "--columns=time,change,application"], timeout=20).splitlines()[-limit:]:
        p = line.split("\t")
        if len(p) >= 3 and p[2].strip():
            try:
                at = time.mktime(time.strptime(p[0].strip()[:19], "%b %d %H:%M:%S"))
            except ValueError:
                at = None
            res.append({"when": p[0].strip(), "at": at, "change": p[1].strip(), "app": p[2].strip()})
    return list(reversed(res))


def _find(sid):
    idx = _index()
    if not sid:
        for e in idx:
            if not e.get("restored"):
                return e
        die("nothing to undo — no unrestored snapshots")
    for e in idx:
        if e["id"] == sid or e["id"].endswith(sid) or e["id"].startswith(sid):
            return e
    die(f"no snapshot '{sid}'. See: xora timeline")


# ---------------------------------------------------------------- commands

def cmd_rm(a):
    """Safe rm: snapshot, then delete. Accepts the usual -r -f -i flags."""
    from .spaces import active
    space = active()
    flags = "".join(f.lstrip("-") for f in a.flags)
    recursive = any(c in flags for c in "rR") or a.recursive
    force = "f" in flags or a.force
    code = 0
    batch = uuid.uuid4().hex[:8]           # one rm = one undo, however many files and folders it names
    for p in a.paths:
        path = Path(p)
        if not path.exists() and not path.is_symlink():
            if not force:
                print(f"rm: cannot remove '{p}': No such file or directory")
                code = 1
            continue
        absolute = path.absolute()
        if absolute in (Path("/"), Path.home()) or str(absolute) in ("/usr", "/etc", "/var", "/boot"):
            print(f"rm: refusing to remove '{p}'")
            code = 1
            continue
        if path.is_dir() and not path.is_symlink() and not recursive:
            print(f"rm: cannot remove '{p}': Is a directory")
            code = 1
            continue
        try:
            e = snapshot(path, f"rm {' '.join(a.raw)}", space, batch)
        except Exception as ex:
            print(red(f"rm: '{p}': snapshot failed ({ex}); NOT deleting. Use /bin/rm to delete without a snapshot."))
            code = 1
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        if e["files"] > 1 or e["kind"] == "dir":
            n = f"{e['files']:,}"
            print(f"{cyan('[xora timeline]')} Snapshot saved before deleting {bold(n)} files "
                  f"({human(e['size'])}) in {p} · {green('xora undo')} to bring them back")
    return code


def cmd_undo(a):
    e = _find(a.id)
    group = [e]
    if not a.id and e.get("batch"):        # bring back everything the last rm deleted, not only its last item
        group = [x for x in _index() if x.get("batch") == e["batch"] and not x.get("restored")]
    for e in reversed(group):
        dest = restore(e)
        ok(f"Restored {tilde(str(dest))} ({e['files']:,} files) from snapshot {e['id']}")
        if str(dest) != e["path"]:
            warn(f"{e['path']} already exists, so the old version was put next to it instead of overwriting it")


def cmd_snap(a):
    from .spaces import active, load, project_dir
    path = a.path
    space = active()
    if not path:
        if not space:
            die("give a path, or run this inside a Space")
        path = project_dir(load(space))
    e = snapshot(path, a.message or "manual snapshot", space)
    ok(f"Snapshot {e['id']}: {e['path']} ({e['files']:,} files, {human(e['size'])})")


def cmd_list(a):
    idx = _index()
    if a.path:
        want = str(Path(a.path).absolute())
        idx = [e for e in idx if e["path"] == want or e["path"].startswith(want + "/")]
    if not idx:
        info("No file snapshots yet. XORA saves one automatically before anything is deleted with rm.")
    for e in idx[: a.limit]:
        st = dim("restored") if e.get("restored") else green("available")
        p = tilde(e["path"])
        print(f"{yellow(e['id'])}  {ago(e['at']):>10}  {p:40} {e['files']:>7,} files {human(e['size']):>9}  {st}  {dim(e['reason'][:40])}")
    if a.all:
        _system_history()
        _flatpak_history()


def cmd_show(a):
    e = _find(a.id)
    base = TIMELINE_DIR / e["id"] / "data"
    print(f"{bold(e['id'])}  {e['path']}  {ago(e['at'])}  {e['reason']}")
    if base.is_dir():
        n = 0
        for root, dirs, files in os.walk(base):
            for f in files:
                print("  " + os.path.relpath(os.path.join(root, f), base))
                n += 1
                if n >= a.limit:
                    print(dim(f"  … {e['files'] - n:,} more"))
                    return
    if not Path(e["path"]).exists():
        print(green(f"Restoring will recreate {e['path']}."))
        return
    # it exists now: show exactly what a merge restore would do (nothing newer is lost)
    p = preview(e)
    if p.get("error"):
        print(yellow(p["error"]))
        return
    print(bold("\nIf you restore this (xora timeline restore " + e["id"] + " --merge):"))
    for c in p["changed"]:
        delta = f"  (+{c['plus']} −{c['minus']} lines)" if c["plus"] is not None else ""
        print(f"  {yellow('put back')}  {c['path']}{dim(delta)}")
    for m in p["missing"]:
        print(f"  {green('bring back')} {m['path']}  {dim('(deleted since)')}")
    for x in p["extra"]:
        print(f"  {cyan('keep')}      {x['path']}  {dim('(created since: left as it is)')}")
    if not (p["changed"] or p["missing"]):
        print(dim("  nothing to restore: every file is the same as in this snapshot"))
    print(dim(f"  {p['same']} file(s) unchanged" + (" · Git history is kept" if p["git"] else "")
              + " · the current state is snapshotted first, so the restore can itself be undone"))
    print(dim(f"  Or restore beside it instead: xora timeline restore {e['id']}  (→ {Path(e['path']).name}.restored-{e['id']})"))


def cmd_restore(a):
    e = _find(a.id)
    if getattr(a, "merge", False):
        backup, n, kept = restore_merge(e)
        ok(f"Restored {n} file(s) into {e['path']}; kept {kept} file(s) created since then."
           + (f" Undo with: xora timeline restore {backup['id']} --merge" if backup else ""))
        return
    dest = restore(e, a.to)
    ok(f"Restored to {dest}")


def cmd_prune(a):
    idx = _index()
    keep, drop = [], []
    cutoff = time.time() - a.days * 86400 if a.days else None
    for i, e in enumerate(idx):
        if (a.keep is not None and i >= a.keep) or (cutoff and e["at"] < cutoff):
            drop.append(e)
        else:
            keep.append(e)
    if not drop:
        info("nothing to prune")
        return
    total = sum(e["size"] for e in drop)
    if not a.yes and not confirm(f"Delete {len(drop)} snapshot(s), {human(total)}? This can't be undone."):
        return
    for e in drop:
        shutil.rmtree(TIMELINE_DIR / e["id"], ignore_errors=True)
    _save(keep)
    ok(f"pruned {len(drop)} snapshot(s), freed up to {human(total)}")


def _system_history():
    print(bold("\nSystem deployments"))
    if have("bootc"):
        r = run(["bootc", "status", "--format", "humanreadable"], capture=True)
        print(r.stdout.strip() or dim("  bootc status needs root: sudo bootc status"))
    elif have("rpm-ostree"):
        print(out(["rpm-ostree", "status"]) or dim("  (unavailable)"))
    else:
        print(dim("  not an image-based system (no bootc / rpm-ostree)"))


def _flatpak_history():
    if not have("flatpak"):
        return
    print(bold("\nApp history (Flatpak)"))
    h = out(["flatpak", "history", "--columns=time,change,application,branch"], timeout=20)
    lines = h.splitlines()[-10:]
    print("\n".join("  " + l for l in lines) if lines else dim("  no app changes recorded"))


def cmd_system(a):
    if a.rollback:
        tool = "bootc" if have("bootc") else "rpm-ostree" if have("rpm-ostree") else None
        if not tool:
            die("this system has no image-based deployments to roll back")
        if confirm(f"Roll the whole OS back to the previous deployment with `sudo {tool} rollback`? Takes effect on reboot."):
            os.execvp("sudo", ["sudo", tool, "rollback"])
        return
    _system_history()
    _flatpak_history()
