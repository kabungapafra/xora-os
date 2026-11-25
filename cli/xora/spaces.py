"""Project Spaces: one manifest describes how to rebuild a whole project.

Manifest: ~/.config/xora/spaces/<name>.yaml

    space: attndi-backend
    version: 1
    dir: ~/Spaces/attndi-backend
    repo: git@github.com:digiflect/attndi.git
    branch: main
    tools:
      - python: "3.12"
    services:
      - name: db
        image: postgres:16
        volume: attndi-db                      # named volume, data never in the manifest
        ports: ["5432:5432"]
        env: {POSTGRES_DB: attndi}
        secrets:
          - {env: POSTGRES_PASSWORD, ref: "keyring:attndi/db_password"}
      - name: api
        build: ./backend
        command: uvicorn app.main:app --reload --host 0.0.0.0
        ports: ["8000:8000"]
    terminals:
      - {cwd: ./backend, title: backend}
      - {cwd: ./mobile}
    layout:
      windows: [code, "http://localhost:8000/docs"]
    checkpoints: timeline://attndi-backend
"""
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from . import vault as sec
from .util import (ACTIVE_FILE, SPACES_DIR, STATE, load_json, save_json, tilde, blue, bold, cyan, die, dim, err, green, have, info, load_yaml,
                   ok, out, red, run, save_yaml, warn, yellow)

MANIFEST_VERSION = 1
OPENED_FILE = STATE / "opened.json"     # when each Space was last opened

# Where well-known images keep their data, so `volume: name` is enough.
DATA_PATHS = {
    "postgres": "/var/lib/postgresql/data", "postgis": "/var/lib/postgresql/data",
    "mysql": "/var/lib/mysql", "mariadb": "/var/lib/mysql", "mongo": "/data/db",
    "redis": "/data", "valkey": "/data", "minio": "/data", "rabbitmq": "/var/lib/rabbitmq",
}

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


# ---------------------------------------------------------------- manifest

def path_of(name):
    return SPACES_DIR / f"{name}.yaml"


def all_names():
    return sorted(p.stem for p in SPACES_DIR.glob("*.yaml"))


def load(name):
    m = load_yaml(path_of(name))
    if not m:
        known = all_names()
        die(f"no Space called '{name}'." + (f" Known: {', '.join(known)}" if known else " Create one with: xora space create"))
    return validate(m, name)


def validate(m, name="?"):
    problems = []
    if not isinstance(m, dict):
        die(f"{path_of(name)}: manifest must be a mapping")
    if m.get("version", 1) > MANIFEST_VERSION:
        problems.append(f"manifest version {m['version']} is newer than this xora ({MANIFEST_VERSION}); update xora")
    if not NAME_RE.match(str(m.get("space", ""))):
        problems.append("'space' must be lowercase letters, digits, . _ -")
    seen = set()
    for s in m.get("services") or []:
        if not s.get("name"):
            problems.append("every service needs a name")
        elif s["name"] in seen:
            problems.append(f"service '{s['name']}' is listed twice")
        seen.add(s.get("name"))
        if not (s.get("image") or s.get("build")):
            problems.append(f"service '{s.get('name')}' needs 'image' or 'build'")
        for k, v in (s.get("env") or {}).items():
            if re.search(r"(PASSWORD|SECRET|TOKEN|API_KEY)", k, re.I) and v:
                problems.append(f"service '{s.get('name')}': {k} looks like a secret — move it to 'secrets' as a reference")
    if problems:
        die(f"{path_of(name)} has problems:\n    " + "\n    ".join(problems))
    m.setdefault("version", MANIFEST_VERSION)
    return m


def project_dir(m):
    return Path(os.path.expanduser(m.get("dir") or f"~/Spaces/{m['space']}"))


def active():
    """The Space for the current folder, else the last opened one."""
    cwd = Path.cwd().resolve()
    best = None
    for n in all_names():
        m = load_yaml(path_of(n)) or {}
        d = project_dir({"space": n, **m}).resolve()
        if cwd == d or d in cwd.parents:
            if best is None or len(str(d)) > len(str(best[1])):
                best = (n, d)
    if best:
        return best[0]
    if ACTIVE_FILE.exists():
        n = ACTIVE_FILE.read_text().strip()
        if path_of(n).exists():
            return n
    return None


def need_active(name=None):
    name = name or active()
    if not name:
        die("not inside a Space. Use: xora space open <name>   (or xora space list)")
    return load(name)


# ---------------------------------------------------------------- detection for `create`

def detect(dirpath, space="project"):
    d = Path(dirpath)
    m = {}
    if (d / ".git").exists():
        remote = out(["git", "-C", d, "remote", "get-url", "origin"])
        if remote:
            m["repo"] = remote
        br = out(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"])
        if br and br != "HEAD":
            m["branch"] = br
    tools = []
    if any((d / f).exists() for f in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile")) or \
            any((d / x / "requirements.txt").exists() for x in ("backend", "api", "server")):
        v = out(["python3", "-c", "import sys;print('%d.%d'%sys.version_info[:2])"])
        tools.append({"python": v or "3.12"})
    if any((d / x / "pubspec.yaml").exists() for x in (".", "mobile", "app", "flutter")):
        v = out(["flutter", "--version", "--machine"])
        mv = re.search(r'"frameworkVersion":\s*"(\d+\.\d+)', v or "")
        tools.append({"flutter": mv.group(1) if mv else "3.24"})
    if (d / "package.json").exists():
        v = out(["node", "--version"]).lstrip("v")
        tools.append({"node": ".".join(v.split(".")[:1]) or "22"})
    if (d / "go.mod").exists():
        tools.append({"go": out(["go", "env", "GOVERSION"]).replace("go", "")[:4] or "1.23"})
    if (d / "Cargo.toml").exists():
        tools.append({"rust": "stable"})
    if tools:
        m["tools"] = tools
    for compose in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
        c = load_yaml(d / compose)
        if c and isinstance(c.get("services"), dict):
            m["services"] = _from_compose(c["services"], space)
            break
    return m


def _from_compose(services, space):
    out_ = []
    for name, s in services.items():
        svc = {"name": name}
        if s.get("image"):
            svc["image"] = s["image"]
        if s.get("build"):
            b = s["build"]
            svc["build"] = b if isinstance(b, str) else b.get("context", ".")
        if s.get("command"):
            c = s["command"]
            svc["command"] = c if isinstance(c, str) else " ".join(c)
        if s.get("ports"):
            svc["ports"] = [str(p) for p in s["ports"]]
        env = s.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)
        clean, secrets = {}, []
        for k, v in env.items():
            if re.search(r"(PASSWORD|SECRET|TOKEN|API_KEY)", k, re.I):
                secrets.append({"env": k, "ref": f"keyring:{space}/{k.lower()}"})
            else:
                clean[k] = v
        if clean:
            svc["env"] = clean
        if secrets:
            svc["secrets"] = secrets
        for v in s.get("volumes") or []:
            if isinstance(v, str) and ":" in v and not v.startswith((".", "/", "~")):
                svc.setdefault("volumes", []).append(v)
        out_.append(svc)
    return out_


# ---------------------------------------------------------------- commands

def cmd_create(a):
    d = Path(a.dir or ".").expanduser().resolve()
    name = a.name or re.sub(r"[^a-z0-9._-]+", "-", d.name.lower()).strip("-")
    if not NAME_RE.match(name):
        die(f"'{name}' isn't a valid Space name (lowercase letters, digits, . _ -)")
    if path_of(name).exists() and not a.force:
        die(f"Space '{name}' already exists ({path_of(name)}). Use --force to replace it.")
    m = {"space": name, "version": MANIFEST_VERSION, "dir": tilde(d)}
    if a.repo:
        m["repo"] = a.repo
        if not d.exists() or not any(d.iterdir()):
            m["dir"] = f"~/Spaces/{name}" if not a.dir else m["dir"]
    m.update({k: v for k, v in detect(d, name).items() if k not in m})
    if a.branch:
        m["branch"] = a.branch
    m.setdefault("terminals", [{"cwd": "."}])
    m["checkpoints"] = f"timeline://{name}"
    save_yaml(path_of(name), m)
    launcher_entry(name)
    _places()
    ok(f"Created Space {bold(name)}  →  {path_of(name)}")
    for k in ("repo", "branch", "tools", "services"):
        if k in m:
            v = m[k]
            if k == "tools":
                v = ", ".join(f"{list(t)[0]} {list(t.values())[0]}" for t in v)
            if k == "services":
                v = ", ".join(s["name"] for s in v)
            print(f"    {dim(k + ':'):20} {v}")
    info(f"Edit it with: xora space edit {name}    Open it with: xora space open {name}")


def cmd_list(a):
    names = all_names()
    if not names:
        info("No Spaces yet. Create one inside a project folder with: xora space create")
        return
    cur = active()
    running = _running_containers()
    for n in names:
        m = load_yaml(path_of(n)) or {}
        svcs = m.get("services") or []
        up = sum(1 for s in svcs if f"xora-{n}-{s.get('name')}" in running)
        mark = green("●") if n == cur else " "
        print(f"{mark} {bold(n):30} {dim(m.get('dir', ''))}  {up}/{len(svcs)} services")


def cmd_show(a):
    p = path_of(a.name or need_active()["space"])
    if not p.exists():
        die(f"no Space '{a.name}'")
    print(p.read_text(), end="")


def cmd_edit(a):
    name = a.name or need_active()["space"]
    p = path_of(name)
    if not p.exists():
        die(f"no Space '{name}'")
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("nano" if have("nano") else "vi")
    subprocess.call(shlex.split(editor) + [str(p)])
    validate(load_yaml(p), name)
    ok("Manifest is valid")


def cmd_rm(a):
    p = path_of(a.name)
    if not p.exists():
        die(f"no Space '{a.name}'")
    m = load(a.name)
    _services_down(m, remove=True)
    p.unlink()
    launcher_entry(a.name, remove=True)
    _places()
    ok(f"Removed Space '{a.name}'. Project files in {project_dir(m)} were left alone.")


def cmd_open(a):
    m = load(a.name)
    name, d = m["space"], project_dir(m)
    print(f"{cyan('┌──(')}{bold(blue('xora'))}{cyan(')-[')}{bold('space ' + name)}{cyan(']')}")
    steps = [("Project files", lambda: _ensure_repo(m, d)),
             ("Tools", lambda: _check_tools(m, d)),
             ("Services", lambda: _services_up(m, d)),
             ("Terminals & windows", lambda: None if a.no_gui else _open_gui(m, d))]
    failed = False
    for title, fn in steps:
        print(f"{cyan('│')}")
        print(f"{cyan('├─')} {bold(title)}")
        try:
            if fn() is False:
                failed = True
        except KeyboardInterrupt:
            raise
        except Exception as e:  # keep going: a broken step must not leave the Space half-open silently
            err(f"{title} failed: {e}")
            failed = True
    print(f"{cyan('└─')}{bold('$')} ", end="")
    ACTIVE_FILE.write_text(name)
    opened = load_json(OPENED_FILE, {})
    opened[name] = time.time()
    save_json(OPENED_FILE, opened)
    if failed:
        print(yellow(f"Space '{name}' opened with problems (see above). Run: xora space status"))
        return 1
    print(green(f"Space '{name}' is ready.") + dim(f"  cd {d}"))


def cmd_close(a):
    m = load(a.name) if a.name else need_active()
    _services_down(m)
    if ACTIVE_FILE.exists() and ACTIVE_FILE.read_text().strip() == m["space"]:
        ACTIVE_FILE.unlink()
    ok(f"Closed Space '{m['space']}'. Files and volumes are kept.")


def cmd_status(a):
    m = load(a.name) if a.name else need_active()
    name, d = m["space"], project_dir(m)
    print(f"{bold(name)}  {dim(str(d))}")
    if (d / ".git").exists():
        br = out(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"])
        dirty = out(["git", "-C", d, "status", "--porcelain"])
        n = len(dirty.splitlines()) if dirty else 0
        print(f"  git     {green(br)}" + (yellow(f"  {n} changed file(s)") if n else dim("  clean")))
    elif not d.exists():
        print(f"  files   {red('missing')} — run: xora space open {name}")
    _services_status(m)


def cmd_up(a):
    m = need_active(a.space)
    return None if _services_up(m, project_dir(m)) is not False else 1


def cmd_down(a):
    _services_down(need_active(a.space))


def cmd_services(a):
    _services_status(need_active(a.space))


def cmd_logs(a):
    m = need_active(a.space)
    os.execvp("podman", ["podman", "logs", "-f", "--tail", "100", f"xora-{m['space']}-{a.service}"])


# ---------------------------------------------------------------- steps

def _ensure_repo(m, d):
    if d.exists() and any(d.iterdir()):
        if (d / ".git").exists():
            br = out(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"])
            want = m.get("branch")
            if want and br != want:
                dirty = out(["git", "-C", d, "status", "--porcelain"])
                if dirty:
                    warn(f"on branch {br}, manifest says {want}; not switching because you have uncommitted changes")
                else:
                    run(["git", "-C", d, "checkout", want])
                    br = want
            ok(f"{d}  {dim('git:')}{green(br)}")
        else:
            ok(str(d))
        return
    if not m.get("repo"):
        d.mkdir(parents=True, exist_ok=True)
        ok(f"created empty folder {d}")
        return
    cmd = ["git", "clone"] + (["-b", m["branch"]] if m.get("branch") else []) + [m["repo"], str(d)]
    if run(cmd).returncode != 0:
        err("git clone failed. Check your network and SSH key, then try again (nothing else was changed).")
        return False
    ok(f"cloned {m['repo']}")


TOOL_PROBES = {
    "python": (["python3", "--version"], r"(\d+\.\d+)"),
    "node": (["node", "--version"], r"v(\d+)"),
    "flutter": (["flutter", "--version"], r"Flutter (\d+\.\d+)"),
    "go": (["go", "version"], r"go(\d+\.\d+)"),
    "rust": (["rustc", "--version"], r"(\d+\.\d+)"),
    "java": (["java", "-version"], r'"(\d+)'),
}


def _check_tools(m, d):
    tools = m.get("tools") or []
    if not tools:
        info("no tools listed")
        return
    mise = have("mise")
    for t in tools:
        (tool, want), = t.items()
        want = str(want)
        if mise:
            r = run(["mise", "use", "--path", str(d / ".mise.toml"), f"{tool}@{want}"], capture=True, cwd=d, timeout=900)
            if r.returncode == 0:
                ok(f"{tool} {want} {dim('(mise)')}")
                continue
        probe = TOOL_PROBES.get(tool)
        if not probe:
            warn(f"{tool} {want}: don't know how to check it")
            continue
        r = run(probe[0], capture=True, timeout=30)
        mv = re.search(probe[1], (r.stdout or "") + (r.stderr or ""))
        have_v = mv.group(1) if mv else None
        if not have_v:
            warn(f"{tool} {want} is not installed" + ("" if mise else dim("  (install mise to let XORA install tools for you)")))
        elif want == "stable" or have_v == want or have_v.startswith(want + ".") or want.startswith(have_v):
            ok(f"{tool} {have_v}")
        else:
            warn(f"{tool}: want {want}, have {have_v}")


def _running_containers():
    if not have("podman"):
        return set()
    return set(out(["podman", "ps", "--format", "{{.Names}}"]).split())


def _all_containers():
    if not have("podman"):
        return set()
    return set(out(["podman", "ps", "-a", "--format", "{{.Names}}"]).split())


def qualify(image):
    """postgres:16 → docker.io/library/postgres:16, so it works without registry search config."""
    if not image:
        return image
    first = image.split("/")[0]
    if "/" in image and ("." in first or ":" in first or first == "localhost"):
        return image
    return "docker.io/" + (image if "/" in image else "library/" + image)


def _volume_args(s):
    args = []
    if s.get("volume"):
        img = (s.get("image") or "").split("/")[-1].split(":")[0]
        path = DATA_PATHS.get(img)
        if not path:
            raise RuntimeError(f"service '{s['name']}': don't know where {img or 'this image'} stores data; use volumes: [\"{s['volume']}:/path\"]")
        args += ["-v", f"{s['volume']}:{path}"]
    for v in s.get("volumes") or []:
        args += ["-v", v]
    return args


def _services_up(m, d):
    svcs = m.get("services") or []
    if not svcs:
        info("no services")
        return
    if not have("podman"):
        err("podman is not installed, so services can't start")
        return False
    name = m["space"]
    net = f"xora-{name}"
    if run(["podman", "network", "exists", net], capture=True).returncode != 0:
        run(["podman", "network", "create", net], capture=True)
    existing, running = _all_containers(), _running_containers()
    bad = False
    for s in svcs:
        cname = f"xora-{name}-{s['name']}"
        if cname in running:
            ok(f"{s['name']} {dim('already running')}")
            continue
        if cname in existing:
            r = run(["podman", "start", cname], capture=True)
            if r.returncode == 0:
                ok(f"{s['name']} started")
            else:
                err(f"{s['name']}: {r.stderr.strip()}")
                bad = True
            continue
        image = qualify(s.get("image"))
        if s.get("build"):
            image = f"localhost/xora-{name}-{s['name']}:latest"
            ctx = (d / s["build"]).resolve()
            if not ctx.exists():
                err(f"{s['name']}: build folder {ctx} does not exist")
                bad = True
                continue
            info(f"building {s['name']} from {ctx}")
            if run(["podman", "build", "-t", image, str(ctx)]).returncode != 0:
                err(f"{s['name']}: build failed")
                bad = True
                continue
        try:
            env_args = []
            for k, v in (s.get("env") or {}).items():
                env_args += ["-e", f"{k}={v}"]
            for ref in s.get("secrets") or []:
                key, val = sec.resolve(ref)
                env_args += ["-e", f"{key}={val}"]
            cmd = ["podman", "run", "-d", "--name", cname, "--network", net, "--network-alias", s["name"],
                   "--label", f"xora.space={name}", "--restart", "unless-stopped"]
            for p in s.get("ports") or []:
                cmd += ["-p", str(p)]
            cmd += _volume_args(s) + env_args + [image]
            if s.get("command"):
                cmd += shlex.split(s["command"])
        except RuntimeError as e:
            err(str(e))
            bad = True
            continue
        r = run(cmd, capture=True, timeout=900)
        if r.returncode == 0:
            ok(f"{s['name']} started {dim(image)}")
        else:
            err(f"{s['name']}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'podman run failed'}")
            bad = True
    return False if bad else None


def _services_down(m, remove=False):
    if not have("podman"):
        return
    existing = _all_containers()
    for s in m.get("services") or []:
        c = f"xora-{m['space']}-{s['name']}"
        if c in existing:
            run(["podman", "stop", "-t", "10", c], capture=True)
            if remove:
                run(["podman", "rm", c], capture=True)
            ok(f"{'removed' if remove else 'stopped'} {s['name']}")


def _services_status(m):
    svcs = m.get("services") or []
    if not svcs:
        print(dim("  no services"))
        return
    running = _running_containers()
    existing = _all_containers()
    for s in svcs:
        c = f"xora-{m['space']}-{s['name']}"
        st = green("● running") if c in running else (red("● stopped") if c in existing else dim("○ not created"))
        ports = ", ".join(s.get("ports") or [])
        print(f"  {s['name']:10} {st}  {dim(ports)}")


APPS_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "applications"


def _places():
    from .places import sync
    try:
        sync()
    except Exception:
        pass


def launcher_entry(name, remove=False):
    """Make every Space findable in the app launcher and KRunner (universal search)."""
    f = APPS_DIR / f"xora-space-{name}.desktop"
    if remove:
        f.unlink(missing_ok=True)
        return
    APPS_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(f"""[Desktop Entry]
Type=Application
Name={name}
GenericName=XORA Space
Comment=Open the {name} Space: files, tools, services, terminals and windows
Exec=xora space open {name}
Icon=xora-logo
Terminal=true
Categories=Development;
Keywords=space;project;xora;
Actions=close;status;

[Desktop Action close]
Name=Close Space
Exec=xora space close {name}

[Desktop Action status]
Name=Status
Exec=xora-term --hold -- xora space status {name}
""")


def _bus(*args):
    r = run(["busctl", "--user", "--json=short", "call", "org.kde.ActivityManager", "/ActivityManager/Activities",
             "org.kde.ActivityManager.Activities", *args], capture=True, timeout=5)
    if r.returncode != 0:
        return None
    if not r.stdout.strip():
        return True             # calls like SetActivityIcon return nothing: success
    import json
    try:
        data = json.loads(r.stdout).get("data") or [True]
    except ValueError:
        return None
    return data[0]


def _activity(name):
    """Each Space gets its own KDE Activity, so its windows stay together."""
    if not have("busctl"):
        return
    ids = _bus("ListActivities")
    if ids is None:
        return
    target = next((i for i in ids if _bus("ActivityName", "s", i) == name), None)
    if not target:
        target = _bus("AddActivity", "s", name)
        if target:
            _bus("SetActivityIcon", "ss", target, "xora-logo")
    if target and _bus("SetCurrentActivity", "s", target):
        ok(f"switched to the '{name}' Activity")


def _open_gui(m, d):
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        info("no graphical session; skipping terminals and windows")
        return
    _activity(m["space"])
    terms = m.get("terminals") or [{"cwd": "."}]
    if have("ptyxis") and have("xora-term"):
        for i, t in enumerate(terms):
            cwd = (d / t.get("cwd", ".")).resolve()
            argv = ["xora-term", *(["--tab"] if i else []), "--cwd", str(cwd)]
            if t.get("command"):
                argv += ["--", os.environ.get("SHELL", "/bin/bash"), "-c", f"{t['command']}; exec \"$SHELL\""]
            subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.8 if i == 0 else 0.2)   # tabs join the window the first call opened
        ok(f"opened {len(terms)} terminal tab(s)")
    elif have("konsole"):
        lines = []
        for t in terms:
            cwd = (d / t.get("cwd", ".")).resolve()
            line = f"title: {t.get('title', cwd.name)} ;; workdir: {cwd}"
            if t.get("command"):
                line += f" ;; command: {t['command']}"
            lines.append(line)
        f = tempfile.NamedTemporaryFile("w", suffix=".tabs", delete=False)
        f.write("\n".join(lines) + "\n")
        f.close()
        subprocess.Popen(["konsole", "--tabs-from-file", f.name], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok(f"opened {len(terms)} terminal tab(s) in Konsole")
    else:
        for t in terms:
            info(f"terminal: cd {(d / t.get('cwd', '.')).resolve()}")
    for w in (m.get("layout") or {}).get("windows") or []:
        target = str(w)
        if target.startswith("browser:"):
            target = target.split(":", 1)[1]
            if not target.startswith("http"):
                target = "http://" + target
        if re.match(r"^https?://", target):
            subprocess.Popen(["xdg-open", target], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok(f"opened {target}")
        elif have(target.split()[0]):
            subprocess.Popen(shlex.split(target) + ([str(d)] if target in ("code", "codium", "kate", "dolphin") else []),
                             cwd=d, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok(f"opened {target}")
        else:
            warn(f"window '{target}': app not installed")
