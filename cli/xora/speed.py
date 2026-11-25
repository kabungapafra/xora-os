"""How fast is the internet right now, and is XORA's tuning active?

    xora speed            latency, DNS, download speed (about 10 MB of data; 2 MB on metered connections)
    xora speed --no-download

Reports facts, then says what's slowing things down: the Wi-Fi/router, the provider, DNS, or a VPN/Tor.
"""
import socket
import subprocess
import time
from pathlib import Path

from .util import bold, cyan, dim, green, have, info, ok, out, red, warn, yellow


def _read(p):
    try:
        return Path(p).read_text().strip()
    except OSError:
        return "?"


def _tcp_ms(host, port=443, tries=3):
    best = None
    for _ in range(tries):
        t = time.perf_counter()
        try:
            socket.create_connection((host, port), timeout=4).close()
        except OSError:
            continue
        ms = (time.perf_counter() - t) * 1000
        best = ms if best is None else min(best, ms)
    return best


def _dns_ms(name, limit=3.0):
    """Lookup time in ms, or None if there's no answer within `limit` seconds."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TO
    def look():
        t = time.perf_counter()
        socket.getaddrinfo(name, 443, proto=socket.IPPROTO_TCP)
        return (time.perf_counter() - t) * 1000
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(look).result(timeout=limit)
    except (_TO, OSError):
        return None
    finally:
        ex.shutdown(wait=False)


def _gateway():
    r = out(["ip", "route", "show", "default"])
    parts = r.split()
    return parts[parts.index("via") + 1] if "via" in parts else None


def _ping_ms(host):
    r = subprocess.run(["ping", "-c", "3", "-i", "0.3", "-W", "2", host], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "min/avg" in line:
            return float(line.split("=")[1].split("/")[1])
    return None


def cmd_speed(a):
    from .system import _active_conn, anon_on
    cc = _read("/proc/sys/net/ipv4/tcp_congestion_control")
    qd = _read("/proc/sys/net/core/default_qdisc")
    tuned = cc == "bbr"
    print(bold("Tuning") + f"  congestion control {green(cc) if tuned else yellow(cc)} · queue {qd}" +
          ("" if tuned else dim("  (XORA uses bbr; this machine isn't running XORA's settings)")))

    gw = _gateway()
    gw_ms = _ping_ms(gw) if gw else None
    net_ms = _tcp_ms("1.1.1.1")
    dns_cold = _dns_ms(f"xora-{int(time.time())}.example.com")       # a name nobody has looked up: real DNS time
    dns_ms = _dns_ms("wikipedia.org")
    dns_warm = _dns_ms("wikipedia.org")                                  # second time: from the cache
    fmt = lambda v: f"{v:.0f} ms" if v is not None else red("no answer")
    print(bold("Latency") + f"  router {fmt(gw_ms)} · internet {fmt(net_ms)}")
    print(bold("DNS") + f"      lookup {fmt(dns_ms)} · cached {fmt(dns_warm)}" + dim(f"  (unknown name: {fmt(dns_cold)})"))

    mbps = None
    if not a.no_download and net_ms is not None:
        metered = False
        conn = _active_conn() if have("nmcli") else []
        if conn:
            metered = out(["nmcli", "-g", "connection.metered", "connection", "show", conn[0]]) in ("yes", "guess-yes")
        size = 2_000_000 if metered else 10_000_000
        info(f"downloading {size // 1_000_000} MB to measure speed" + (" (metered connection: small test)" if metered else "") + "…")
        # several well-known test servers: the first one that answers is used; 10 s is enough even if it doesn't finish
        sources = [f"https://speed.cloudflare.com/__down?bytes={size}", "https://proof.ovh.net/files/10Mb.dat",
                   "http://speedtest.tele2.net/10MB.zip", "https://ash-speed.hetzner.com/100MB.bin"]
        deadline = time.monotonic() + 25          # the whole test stays short, even on a bad line
        for url in sources:
            left = deadline - time.monotonic()
            if left < 3:
                break
            r = subprocess.run(["curl", "-s", "-L", "-o", "/dev/null", "--max-time", str(int(min(10, left))), "--max-filesize", str(size * 11),
                                "-r", f"0-{size - 1}", "-w", "%{speed_download} %{size_download}", url],
                               capture_output=True, text=True)
            try:
                bps, got = (float(x) for x in r.stdout.split())
            except ValueError:
                continue
            if got > 200_000:
                mbps = bps * 8 / 1e6
                break
        print(bold("Download") + f" {green(f'{mbps:.1f} Mbit/s') if mbps else red('failed')}")

    # what's slowing it down, from the numbers above
    notes = []
    if gw_ms and gw_ms > 30:
        notes.append(f"Your Wi-Fi to the router is slow ({gw_ms:.0f} ms; good is under 10). Move closer, or use 5 GHz / a cable.")
    if gw_ms and net_ms and net_ms - gw_ms > 150:
        notes.append("The delay is beyond your router: the provider's line is congested or far away.")
    if dns_ms is None and net_ms is not None:
        notes.append("DNS isn't answering: the internet works, but names (websites) don't resolve. That makes everything "
                     "feel slow or broken. `xora explain --only network` can switch to a working DNS server.")
    elif dns_ms and dns_ms > 250:
        notes.append(f"DNS is slow ({dns_ms:.0f} ms). It's cached after the first lookup; a different network or `xora data` won't help, but "
                     "turning off a slow VPN might.")
    if anon_on():
        notes.append("Anon mode is on: Tor routes through 3 relays, so expect it to be slower. That's the price of anonymity.")
    if mbps is not None and mbps < 2:
        notes.append("Under 2 Mbit/s: big downloads will crawl. Data saver (`xora data --metered on`) keeps updates from competing.")
    for n in notes:
        print(yellow("[!] ") + n)
    if not a.no_download and net_ms is not None and mbps is None:
        notes.append("The download test got no data from any test server: the connection is up but very slow or filtered.")
    if not notes and net_ms is not None:
        ok("Nothing is slowing the connection down on this side.")
