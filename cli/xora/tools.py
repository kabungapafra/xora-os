"""Security and DevOps toolkits.

    xora tools                    what's built in, by category (✓ installed)
    xora tools kali [--full]      the complete Kali toolset (Metasploit, Burp, sqlmap, nikto, …) in a container
    xora tools run CMD ARGS...    run a Kali tool, e.g. xora tools run msfconsole
    xora tools add NAME           tools that aren't part of the base system: zap, signal, vscodium, httpx,
                                  volatility, seclists (installed for you only; nothing in the OS changes)

The base system stays small and stable; the big, fast-changing offensive toolset lives in its own
container (Distrobox), shares your home folder and network, and can be deleted without touching XORA.
"""
import os
import shlex
import subprocess
from pathlib import Path

from .util import bold, cyan, die, dim, err, green, have, info, ok, out, run, warn

KALI = "kali"
KALI_IMAGE = "docker.io/kalilinux/kali-rolling:latest"

TOOLKIT = [
    ("Privacy", [("xora anon", "all traffic through Tor with a kill switch"), ("torsocks", "one program through Tor"),
                 ("nyx", "watch Tor"), ("mat2", "strip metadata from files"), ("macchanger", "change the MAC address"),
                 ("firejail", "run an app in a sandbox"), ("usbguard", "allow or block USB devices"),
                 ("keepassxc", "password manager"), ("tor", "the Tor network daemon")]),
    ("Recon & network", [("nmap", "port and service scanner"), ("masscan", "very fast port scanner"),
                         ("wireshark", "packet analyser"), ("tcpdump", "packet capture"), ("hping3", "packet crafting"),
                         ("mtr", "traceroute and ping"), ("ncat", "network Swiss-army knife"), ("socat", "relay anything"),
                         ("dig", "DNS lookups"), ("whois", "domain owners"), ("dsniff", "network auditing")]),
    ("Web", [("gobuster", "find hidden paths and subdomains"), ("ffuf", "web fuzzer"), ("httpie", "HTTP client")]),
    ("Passwords & wireless", [("john", "password cracker"), ("hashcat", "GPU password cracker"),
                              ("hydra", "online login brute force"), ("aircrack-ng", "Wi-Fi security")]),
    ("Reverse engineering & forensics", [("radare2", "disassembler and debugger"), ("binwalk", "firmware analysis"),
                                         ("yara", "malware pattern matching")]),
    ("Defence & hardening", [("lynis", "security audit of this system"), ("rkhunter", "rootkit scanner"),
                             ("chkrootkit", "rootkit scanner"), ("clamscan", "antivirus scanner"),
                             ("trivy", "find vulnerabilities in containers and code")]),
    ("DevOps", [("podman", "containers"), ("buildah", "build images"), ("skopeo", "copy and inspect images"),
                ("podman-compose", "compose files"), ("kubectl", "Kubernetes"), ("helm", "Kubernetes packages"),
                ("k9s", "Kubernetes in the terminal"), ("tofu", "OpenTofu: infrastructure as code"),
                ("ansible", "configuration management"), ("ansible-playbook", "run Ansible playbooks"), ("aws", "AWS CLI"), ("gh", "GitHub CLI"),
                ("git-lfs", "large files in Git"), ("jq", "JSON on the command line"), ("yq", "YAML on the command line"),
                ("git", "version control"), ("distrobox", "any Linux distribution in a container")]),
]

# In the app grid too; installed with `xora tools kali`, run with `xora tools run <tool>`
KALI_TOOLS = [("msfconsole", "Metasploit exploitation framework"), ("burpsuite", "web application testing"),
              ("sqlmap", "SQL injection testing"), ("nikto", "web server scanner"), ("wpscan", "WordPress scanner"),
              ("searchsploit", "Exploit Database, offline"), ("responder", "LLMNR/NBT-NS poisoner"),
              ("netexec", "Windows and Active Directory testing"), ("enum4linux", "Windows/Samba enumeration"),
              ("theHarvester", "emails, names and subdomains"), ("bettercap", "network attacks and monitoring"),
              ("wfuzz", "web fuzzer"), ("dirb", "hidden web content"), ("setoolkit", "social engineering tests"),
              ("hashid", "identify hash types"), ("wifite", "automated Wi-Fi auditing"),
              ("ghidra", "reverse engineering suite"), ("autopsy", "digital forensics")]


# Not packaged for the base system: installed per user on first use, from each project's official source.
#   kind: flatpak (Flathub app id) · go (module, binary goes to ~/.local/bin) · venv (pip package, command) · git (repo, folder)
ADDONS = {
    "zap": ("flatpak", "org.zaproxy.ZAP", "OWASP ZAP: web application security scanner (free Burp alternative)"),
    "signal": ("flatpak", "org.signal.Signal", "Signal: end-to-end encrypted messenger"),
    "vscodium": ("flatpak", "com.vscodium.codium", "VSCodium: VS Code without Microsoft's telemetry"),
    "httpx": ("go", "github.com/projectdiscovery/httpx/cmd/httpx@latest", "probe which web servers are alive"),
    "katana": ("go", "github.com/projectdiscovery/katana/cmd/katana@latest", "web crawler for recon"),
    "volatility": ("venv", ("volatility3", "vol"), "memory forensics (Volatility 3)"),
    "seclists": ("git", ("https://github.com/danielmiessler/SecLists.git", "wordlists/SecLists"),
                 "SecLists wordlists, rockyou included (about 1 GB)"),
}
LOCAL_BIN = Path.home() / ".local/bin"


def _addon_installed(name):
    kind, what, _ = ADDONS[name]
    if kind == "flatpak":
        return have("flatpak") and subprocess.run(["flatpak", "info", what], capture_output=True).returncode == 0
    if kind == "go":
        return (LOCAL_BIN / name).exists()
    if kind == "venv":
        return (LOCAL_BIN / what[1]).exists()
    return (Path.home() / what[1]).is_dir()


def _hide_grid_stub(name):
    """Once the real app is installed it has its own icon: hide XORA's 'install me' icon for this user."""
    d = Path.home() / ".local/share/applications"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"xora-tool-{name}.desktop").write_text("[Desktop Entry]\nType=Application\nName=" + name + "\nHidden=true\n")


def add_tool(name):
    if name not in ADDONS:
        die(f"unknown tool '{name}'. Available: {', '.join(ADDONS)}")
    kind, what, desc = ADDONS[name]
    if _addon_installed(name):
        ok(f"{name} is already installed")
        return 0
    info(f"installing {bold(name)}: {desc}")
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    if kind == "flatpak":
        if not have("flatpak"):
            die("Flatpak isn't installed")
        run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
             "https://dl.flathub.org/repo/flathub.flatpakrepo"], capture=True)
        r = run(["flatpak", "install", "--user", "-y", "flathub", what])
        if r.returncode == 0:
            _hide_grid_stub(name)
    elif kind == "go":
        if not have("go"):
            die("Go isn't installed")
        env = dict(os.environ, GOBIN=str(LOCAL_BIN))
        r = subprocess.run(["go", "install", what], env=env)
    elif kind == "venv":
        pkg, cmd = what
        venv = Path.home() / ".local/share/xora/venvs" / pkg
        r = run(["python3", "-m", "venv", str(venv)])
        if r.returncode == 0:
            r = run([str(venv / "bin/pip"), "install", "-q", "--upgrade", pkg])
        if r.returncode == 0:
            link = LOCAL_BIN / cmd
            link.unlink(missing_ok=True)
            link.symlink_to(venv / "bin" / cmd)
    else:
        url, folder = what
        dest = Path.home() / folder
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = run(["git", "clone", "--depth", "1", url, str(dest)])
    if r.returncode:
        err(f"{name} didn't install (see the messages above); run `xora tools add {name}` again to retry")
        return r.returncode
    ok(f"{name} installed" + (f" in ~/{what[1]}" if kind == "git" else ""))
    return 0


def open_tool(name):
    """From the app grid: install on first use, then start it."""
    if name not in ADDONS:
        die(f"unknown tool '{name}'")
    if not _addon_installed(name) and add_tool(name):
        input("\nPress Enter to close")
        return 1
    kind, what, desc = ADDONS[name]
    if kind == "flatpak":
        subprocess.Popen(["flatpak", "run", what], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    if kind == "git":
        os.chdir(Path.home() / what[1])
        print(bold(cyan(name)) + "  " + desc + "\n")
        subprocess.run(["ls", "--color=auto", "-p"])
        print(dim(f"\nYou're in ~/{what[1]}. Passwords/Leaked-Databases has rockyou.txt.tar.gz\n"))
        shell = os.environ.get("SHELL", "/bin/zsh")
        os.execvp(shell, [shell, "-i"])
    exe = name if kind == "go" else what[1]
    os.execvp("/usr/lib/xora/hooks/tool-shell", ["tool-shell", exe, desc])


def _kali_exists():
    return have("distrobox") and KALI in out(["distrobox", "list", "--no-color"], timeout=30)


def cmd_tools(a):
    action = a.action
    if action == "kali":
        return _kali(a.full)
    if action == "add":
        if not a.cmd:
            die("usage: xora tools add NAME   (" + ", ".join(ADDONS) + ")")
        return max(add_tool(n) for n in a.cmd)
    if action == "open":
        return open_tool(a.cmd[0]) if a.cmd else die("usage: xora tools open NAME")
    if action == "run":
        if not a.cmd:
            die("usage: xora tools run CMD ARGS...   (e.g. xora tools run msfconsole)")
        if not _kali_exists():
            die("the Kali toolset isn't set up yet. Run: xora tools kali")
        return run(["distrobox", "enter", KALI, "--", *a.cmd]).returncode
    variant = Path("/usr/lib/xora/variant")
    if variant.exists() and variant.read_text().strip() == "base":
        staged = Path("/var/lib/xora/toolkit/staged").exists()
        warn("the XORA toolkit is " + ("downloaded: restart to finish installing it" if staged else
             "still to come: it downloads by itself after installing (or: sudo systemctl start xora-toolkit)"))
        print()
    for cat, tools in TOOLKIT:
        print(bold(cyan(cat)))
        for name, what in tools:
            exe = name.split()[0] if name != "xora anon" else "xora"
            mark = green("✓") if have(exe) else dim("·")
            print(f"  {mark} {name:16} {dim(what)}")
        print()
    print(bold(cyan("Install on first use")) + dim("  (xora tools add NAME, or click it in the app grid)"))
    for name, (kind, what, desc) in ADDONS.items():
        print(f"  {green('✓') if _addon_installed(name) else dim('·')} {name:16} {dim(desc)}")
    print()
    kali = _kali_exists()
    print(bold(cyan("Kali toolset")) + dim("  (" + ("installed: xora tools run <tool>" if kali else "not installed yet: xora tools kali") + ")"))
    for name, what in KALI_TOOLS:
        print(f"  {green('✓') if kali else dim('·')} {name:16} {dim(what)}")
    print(dim("  …and the other 600+ Kali tools (xora tools kali --full)\n"))
    if kali:
        ok("Kali toolset installed: xora tools run <tool>   (e.g. msfconsole, sqlmap, nikto, burpsuite)")
    else:
        info("Everything else from Kali (Metasploit, Burp, sqlmap, nikto, …): xora tools kali")


def _kali(full):
    if not have("distrobox"):
        die("distrobox is not installed")
    meta = "kali-linux-default" if full else "kali-linux-headless"
    if not _kali_exists():
        info(f"Creating the Kali container from {KALI_IMAGE} (shares your home folder; the OS stays untouched)…")
        r = run(["distrobox", "create", "--yes", "--name", KALI, "--image", KALI_IMAGE])
        if r.returncode != 0:
            die("couldn't create the Kali container")
    info(f"Installing {meta} inside it (several GB; on metered data, wait for Wi-Fi)…")
    script = f"sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {shlex.quote(meta)}"
    r = run(["distrobox", "enter", KALI, "--", "bash", "-lc", script])
    if r.returncode == 0:
        ok("Kali toolset ready. Use it with: xora tools run msfconsole   (or: distrobox enter kali)")
    else:
        warn("the install stopped; run `xora tools kali` again to continue where it left off")
    return r.returncode
