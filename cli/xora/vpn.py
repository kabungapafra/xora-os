"""VPNs: connect safely on any network.

    xora vpn                          which VPN is on, and whether the kill switch is on
    xora vpn import FILE [--name N]   add a VPN from your provider or company: WireGuard .conf or OpenVPN .ovpn
    xora vpn on [NAME] | off          connect / disconnect
    xora vpn always NAME              connect it automatically on every Wi-Fi and cable network
    xora vpn killswitch on|off        while on, nothing leaves except through the VPN (no leaks if it drops)

VPN vs Anon mode: a VPN hides your traffic from the local network and your internet provider (good on
public Wi-Fi), but the VPN company can see it. Anon mode (Tor) is for anonymity: no single party knows
both who you are and where you go. Both can be on: Tor then runs inside the VPN.
Also in the network menu (top bar): WireGuard, OpenVPN, OpenConnect (Cisco/Palo Alto/Fortinet), L2TP/IPsec.
"""
import os
import re
import socket
import sys
from pathlib import Path

from .util import bold, die, dim, green, have, info, ok, out, red, run, warn, yellow

KS_HOOK = "/usr/lib/xora/hooks/vpn-killswitch"
KS_MARK = Path("/run/xora/vpn-killswitch")
VPN_TYPES = ("vpn", "wireguard")


def _cons():
    """[(name, uuid, type, device or '')] of VPN connections."""
    res = []
    for line in out(["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show"], timeout=10).splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) >= 4 and parts[2] in VPN_TYPES:
            res.append((parts[0].replace("\\:", ":"), parts[1], parts[2], parts[3]))
    return res


def active():
    act = set(out(["nmcli", "-t", "-f", "UUID", "connection", "show", "--active"], timeout=10).split())
    return [c for c in _cons() if c[1] in act]


def killswitch_on():
    return KS_MARK.exists()


def _root(argv):
    if os.geteuid() == 0:
        return run(argv).returncode
    if sys.stdin.isatty() and have("sudo"):
        return run(["sudo", *argv]).returncode
    return run(["pkexec", *argv]).returncode


def _servers():
    """IP addresses of every configured VPN server, so the kill switch lets the VPN (re)connect."""
    hosts = set()
    for name, uuid, typ, _ in _cons():
        if typ == "wireguard":
            for line in out(["nmcli", "--show-secrets", "-g", "wireguard.peers", "connection", "show", uuid], timeout=10).split(","):
                m = re.search(r"endpoint=([^\s;]+)", line)
                if m:
                    hosts.add(m.group(1).rsplit(":", 1)[0].strip("[]"))
            for line in out(["wg", "showconf", name], timeout=5).splitlines() if have("wg") else []:
                if line.lower().startswith("endpoint"):
                    hosts.add(line.split("=", 1)[1].strip().rsplit(":", 1)[0].strip("[]"))
        else:
            data = out(["nmcli", "-g", "vpn.data", "connection", "show", uuid], timeout=10)
            for key in ("remote", "gateway"):
                m = re.search(rf"\b{key}\s*=\s*([^,\s]+)", data)
                if m:
                    hosts.add(m.group(1).split(":")[0])
    ips = set()
    for h in hosts:
        try:
            for ai in socket.getaddrinfo(h, None, socket.AF_INET):
                ips.add(ai[4][0])
        except OSError:
            pass
    return sorted(ips)


def cmd_vpn(a):
    if not have("nmcli"):
        die("NetworkManager (nmcli) is needed for VPNs")
    act = a.action
    if act == "import":
        if not a.args:
            die("usage: xora vpn import FILE.conf|FILE.ovpn [--name NAME]")
        f = Path(a.args[0]).expanduser()
        if not f.exists():
            die(f"{f} doesn't exist")
        typ = "wireguard" if f.suffix == ".conf" else "openvpn" if f.suffix in (".ovpn", ".conf_ovpn") else None
        if not typ:
            die("use a WireGuard .conf or an OpenVPN .ovpn file (other VPN types: the network menu › Add VPN)")
        r = run(["nmcli", "connection", "import", "type", typ, "file", str(f)], capture=True)
        if r.returncode != 0:
            die(f"couldn't import: {r.stderr.strip()[-200:]}")
        m = re.search(r"'(.+?)' \(([0-9a-f-]{36})\)", r.stdout)
        if m and a.name:
            run(["nmcli", "connection", "modify", m.group(2), "connection.id", a.name], capture=True)
        ok(f"added VPN {a.name or (m.group(1) if m else f.stem)}. Connect with: xora vpn on" +
           ("" if not killswitch_on() else "  (kill switch updated)"))
        if killswitch_on():
            _root([KS_HOOK, "on", *_servers()])
        return
    if act == "on":
        cons = _cons()
        if not cons:
            die("no VPN set up yet. Add one: xora vpn import FILE (or the network menu › Add VPN)")
        name = a.args[0] if a.args else cons[0][0]
        r = run(["nmcli", "connection", "up", "id", name])
        return r.returncode
    if act == "off":
        for name, uuid, _, _ in active():
            run(["nmcli", "connection", "down", "uuid", uuid])
        if killswitch_on():
            warn("the kill switch is on, so the internet is blocked until a VPN connects (xora vpn killswitch off)")
        return
    if act == "always":
        if not a.args:
            die("usage: xora vpn always NAME")
        vpn = next((c for c in _cons() if c[0] == a.args[0]), None)
        if not vpn:
            die(f"no VPN called {a.args[0]}")
        n = 0
        for line in out(["nmcli", "-t", "-f", "UUID,TYPE", "connection", "show"], timeout=10).splitlines():
            uuid, _, typ = line.partition(":")
            if typ in ("802-11-wireless", "802-3-ethernet"):
                run(["nmcli", "connection", "modify", uuid, "connection.secondaries", vpn[1]], capture=True)
                n += 1
        ok(f"{vpn[0]} now connects automatically on {n} network(s). New networks: run this again after joining them.")
        return
    if act == "killswitch":
        mode = (a.args or ["status"])[0]
        if mode == "on":
            servers = _servers()
            if not _cons():
                warn("no VPN is set up yet: with the kill switch on, the internet stays blocked until one connects")
            return _root([KS_HOOK, "on", *servers])
        if mode == "off":
            return _root([KS_HOOK, "off"])
        print(green("on") if killswitch_on() else dim("off"))
        return
    # status
    on = active()
    if on:
        for name, _, typ, dev in on:
            ok(f"VPN on: {bold(name)} ({'WireGuard' if typ == 'wireguard' else 'VPN'}{', ' + dev if dev else ''})")
    else:
        info("No VPN connected." + (" Set one up: xora vpn import FILE" if not _cons() else " Connect: xora vpn on"))
    print(f"  kill switch: {green('on: nothing leaves outside the VPN') if killswitch_on() else dim('off')}")
    others = [c[0] for c in _cons() if c not in on]
    if others:
        print(dim("  other VPNs: " + ", ".join(others)))
