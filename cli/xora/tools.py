"""Security and DevOps toolkits.

    xora tools                    what's built in, by category (✓ installed)
    xora tools kali [--full]      the complete Kali toolset (Metasploit, Burp, sqlmap, nikto, …) in a container
    xora tools run CMD ARGS...    run a Kali tool, e.g. xora tools run msfconsole

The base system stays small and stable; the big, fast-changing offensive toolset lives in its own
container (Distrobox), shares your home folder and network, and can be deleted without touching XORA.
"""
import shlex

from .util import bold, cyan, die, dim, green, have, info, ok, out, run, warn

KALI = "kali"
KALI_IMAGE = "docker.io/kalilinux/kali-rolling:latest"

TOOLKIT = [
    ("Privacy", [("xora anon", "all traffic through Tor with a kill switch"), ("torsocks", "one program through Tor"),
                 ("nyx", "watch Tor"), ("mat2", "strip metadata from files"), ("macchanger", "change the MAC address"),
                 ("firejail", "run an app in a sandbox"), ("usbguard", "allow or block USB devices"),
                 ("keepassxc", "password manager")]),
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
                ("ansible", "configuration management"), ("aws", "AWS CLI"), ("gh", "GitHub CLI"),
                ("git-lfs", "large files in Git"), ("jq", "JSON on the command line"), ("yq", "YAML on the command line")]),
]


def _kali_exists():
    return have("distrobox") and KALI in out(["distrobox", "list", "--no-color"], timeout=30)


def cmd_tools(a):
    action = a.action
    if action == "kali":
        return _kali(a.full)
    if action == "run":
        if not a.cmd:
            die("usage: xora tools run CMD ARGS...   (e.g. xora tools run msfconsole)")
        if not _kali_exists():
            die("the Kali toolset isn't set up yet. Run: xora tools kali")
        return run(["distrobox", "enter", KALI, "--", *a.cmd]).returncode
    for cat, tools in TOOLKIT:
        print(bold(cyan(cat)))
        for name, what in tools:
            exe = name.split()[0] if name != "xora anon" else "xora"
            mark = green("✓") if have(exe) else dim("·")
            print(f"  {mark} {name:16} {dim(what)}")
        print()
    if _kali_exists():
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
