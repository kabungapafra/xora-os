"""Secret references. Manifests only ever hold references like `keyring:attndi/db_password`;
the value lives in the desktop keyring (KWallet / GNOME Keyring through secret-tool).

Reference schemes:
    keyring:<space>/<key>   desktop keyring (secret-tool)      ← default
    vault:<space>/<key>     same as keyring (name from the design docs)
    env:<NAME>              environment variable of the shell running xora
    file:<path>             first line of a file (e.g. a mounted secret)
"""
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

from .util import DATA, die, have, ok, warn

FALLBACK = DATA / "secrets"   # used only when no keyring is available, mode 0600


def _split(ref):
    if isinstance(ref, dict):
        return ref.get("env"), ref["ref"]
    # bare string: env var name comes from the last part, e.g. attndi/db_password → DB_PASSWORD
    return None, ref


def _env_name(ref):
    tail = re.split(r"[:/]", ref)[-1]
    return re.sub(r"[^A-Z0-9_]", "_", tail.upper())


def resolve(ref):
    """Return (ENV_NAME, value). Raises RuntimeError with a helpful message if missing."""
    env, r = _split(ref)
    env = env or _env_name(r)
    scheme, _, rest = r.partition(":")
    if scheme in ("keyring", "vault"):
        val = _keyring_get(rest)
    elif scheme == "env":
        val = os.environ.get(rest)
    elif scheme == "file":
        p = Path(os.path.expanduser(rest))
        val = p.read_text().splitlines()[0] if p.exists() else None
    else:
        raise RuntimeError(f"unknown secret reference '{r}' (use keyring:, env: or file:)")
    if val is None:
        raise RuntimeError(f"secret {r} is not set. Set it with: xora secret set {rest}")
    return env, val


def _keyring_get(key):
    if have("secret-tool"):
        r = subprocess.run(["secret-tool", "lookup", "xora", key], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.rstrip("\n")
    f = FALLBACK / key.replace("/", "__")
    return f.read_text().rstrip("\n") if f.exists() else None


def cmd_set(a):
    key = a.key.split(":", 1)[-1]
    val = sys.stdin.read().rstrip("\n") if not sys.stdin.isatty() else getpass.getpass(f"Value for {key}: ")
    if not val:
        die("empty value, nothing saved")
    if have("secret-tool"):
        r = subprocess.run(["secret-tool", "store", "--label", f"XORA {key}", "xora", key], input=val, text=True)
        if r.returncode == 0:
            ok(f"saved {key} in your keyring")
            return
        warn("keyring is not available, saving to a private file instead")
    FALLBACK.mkdir(parents=True, exist_ok=True)
    os.chmod(FALLBACK, 0o700)
    f = FALLBACK / key.replace("/", "__")
    f.write_text(val + "\n")
    os.chmod(f, 0o600)
    ok(f"saved {key} in {f} (readable only by you)")


def cmd_rm(a):
    key = a.key.split(":", 1)[-1]
    if have("secret-tool"):
        subprocess.run(["secret-tool", "clear", "xora", key])
    f = FALLBACK / key.replace("/", "__")
    if f.exists():
        f.unlink()
    ok(f"removed {key}")
