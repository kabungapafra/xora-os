"""Shared helpers: paths, Kali-style output, running commands, YAML."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "xora"
DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "xora"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "xora"
SPACES_DIR = CONFIG / "spaces"
TIMELINE_DIR = DATA / "timeline"
DEVICES_FILE = CONFIG / "devices.yaml"
FIX_FILE = STATE / "fix"          # last suggested fix; the zsh F2 key reads this
ACTIVE_FILE = STATE / "active-space"

for d in (CONFIG, DATA, STATE, SPACES_DIR, TIMELINE_DIR):
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:  # e.g. no writable home (image builds, system services): commands that need it will say so
        pass

sys.stdout.reconfigure(line_buffering=True)
_tty = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
def _c(code):
    return (lambda s: f"\033[{code}m{s}\033[0m") if _tty else (lambda s: str(s))

green, red, yellow, blue, cyan, dim, bold = (_c("32"), _c("31"), _c("33"), _c("34"), _c("36"), _c("2"), _c("1"))


def ok(msg): print(f"{green('[+]')} {msg}")
def info(msg): print(f"{blue('[*]')} {msg}")
def warn(msg): print(f"{yellow('[!]')} {msg}")
def err(msg):
    sys.stdout.flush()
    print(f"{red('[-]')} {msg}", file=sys.stderr, flush=True)
def say(msg): print(f"{cyan('[xora]')} {msg}")


def die(msg, code=1):
    err(msg)
    sys.exit(code)


def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, check=False, capture=False, cwd=None, env=None, quiet=False, timeout=None):
    """Run a command (list). Returns CompletedProcess."""
    if not quiet and not capture:
        print(dim("$ " + " ".join(str(c) for c in cmd)))
    try:
        return subprocess.run([str(c) for c in cmd], check=check, cwd=cwd, env=env, timeout=timeout,
                              text=True, capture_output=capture)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: command not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timed out")


def out(cmd, cwd=None, timeout=10):
    r = run(cmd, capture=True, cwd=cwd, timeout=timeout)
    return r.stdout.strip() if r.returncode == 0 else ""


def load_yaml(path, default=None):
    try:
        with open(path) as f:
            return yaml.safe_load(f) or default
    except FileNotFoundError:
        return default


def save_yaml(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    tmp.replace(path)


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def set_fix(cmd):
    """Remember a suggested fix so the terminal's F2 key can run it."""
    if cmd:
        FIX_FILE.write_text(cmd + "\n")
        print(f"{cyan('[xora explain]')} Press {bold('F2')} to run: {green(cmd)}")
    elif FIX_FILE.exists():
        FIX_FILE.unlink()


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def ago(ts):
    s = int(time.time() - ts)
    if s < 60: return f"{s}s ago"
    if s < 3600: return f"{s // 60} min ago"
    if s < 86400: return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"


def confirm(question, default=False):
    if not sys.stdin.isatty():
        return default
    a = input(f"{yellow('[?]')} {question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not a else a.startswith("y")


def tilde(path):
    """/home/me/x or /var/home/me/x → ~/x. Only a real home prefix is shortened (on XORA /home is a link to /var/home)."""
    p = str(path)
    for h in {str(Path.home()), str(Path.home().resolve())}:
        if p == h:
            return "~"
        if p.startswith(h + "/"):
            return "~" + p[len(h):]
    return p
