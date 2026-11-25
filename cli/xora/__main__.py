"""xora — the XORA OS command.

    xora space create|open|close|list|status|show|edit|rm   Project Spaces
    xora space handoff NAME --to DEV | share NAME --with DEV move a Space to another device, or share it
    xora up | down | services | logs <svc>                   this Space's services
    xora rm [-rf] <paths>                                    delete with a Timeline snapshot first
    xora undo [id]                                           bring back the last deletion
    xora timeline [list|snap|show|restore|prune|system]     history
    xora fabric invite|join|discover|pair|ls|run|revoke      your devices working together
    xora fabric mirror|recover|image-push                    copies on nearby devices; share downloads over LAN
    xora explain [-- cmd] [--cards] [--watch]                why something is wrong, in plain words
    xora ask "question"                                      ask in plain words (also: lines starting with # in the terminal)
    xora secret set|rm <space/key>                           secrets for Spaces (kept in your keyring)
    xora privacy [--revoke app --what camera|mic|files|network]   who uses camera, mic, network
    xora anon on|off|status|check                            all traffic through Tor, with a kill switch
    xora vpn [import F|on|off|always N|killswitch on|off]    VPNs, always-on, no leaks if it drops
    xora speed                                               internet speed, latency, DNS: what's slowing it down
    xora where FILE                                          device, Space, copies, versions and Git of a file
    xora install FILE|NAME                                   install any app (.exe .apk .deb .rpm .AppImage, app store)
    xora apps [android|windows|windows-vm|ubuntu|…]          apps from everywhere
    xora tools [kali [--full] | run CMD]                     security and DevOps toolkits; full Kali in a container
    xora data [--metered on|off] [--updates night|now|off]   expensive internet: metered mode, night updates
    xora resilience [watch|checkpoint|onbattery]             power cuts and UPS
    xora boot                                                what slows startup
    xora ai [enable|disable]                                 opt-in local AI (never leaves the machine)
    xora center [home|pair|timeline] [--setup]               the XORA Center app (Home, Devices, Timeline)
    xora info                                                about this system
"""
import argparse
import os
import platform
import sys

from . import __version__


def build():
    from . import apps, explain, install, fabric, handoff, places, spaces, system, speed, timeline, tools, vault, vpn, where

    p = argparse.ArgumentParser(prog="xora", description="XORA OS: your devices, your projects, one connected workspace.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 2)[2])
    p.add_argument("--version", action="version", version=f"xora {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    # ---- space
    sp = sub.add_parser("space", help="Project Spaces").add_subparsers(dest="sub", metavar="<action>", required=True)
    c = sp.add_parser("create", help="make a Space from a project folder (detects git, tools, compose services)")
    c.add_argument("name", nargs="?")
    c.add_argument("--dir", help="project folder (default: current folder)")
    c.add_argument("--repo", help="git URL to clone when opening")
    c.add_argument("--branch")
    c.add_argument("--force", action="store_true")
    c.set_defaults(fn=spaces.cmd_create)
    for name, fn, hlp in (("open", spaces.cmd_open, "bring the whole project up: files, tools, services, terminals, windows"),
                          ("close", spaces.cmd_close, "stop the Space's services"),
                          ("status", spaces.cmd_status, "git and services status"),
                          ("show", spaces.cmd_show, "print the manifest"),
                          ("edit", spaces.cmd_edit, "edit the manifest"),
                          ("rm", spaces.cmd_rm, "forget a Space (keeps project files)")):
        x = sp.add_parser(name, help=hlp)
        x.add_argument("name", nargs="?" if name not in ("open", "rm") else None)
        if name == "open":
            x.add_argument("--no-gui", action="store_true", help="don't open terminals or windows")
        x.set_defaults(fn=fn)
    sp.add_parser("list", aliases=["ls"], help="list Spaces").set_defaults(fn=spaces.cmd_list)
    x = sp.add_parser("handoff", help="move a Space to another device (checkpoint, clean stop, copy, start there)")
    x.add_argument("name")
    x.add_argument("--to", required=True, help="linked device")
    x.add_argument("--with-secrets", action="store_true", help="also copy its secrets into that device's keyring")
    x.set_defaults(fn=handoff.cmd_handoff)
    x = sp.add_parser("share", help="let a linked device open this Space")
    x.add_argument("name")
    x.add_argument("--with", dest="with_", required=True)
    x.set_defaults(fn=handoff.cmd_share)
    x = sp.add_parser("unshare", help="stop sharing a Space with a device")
    x.add_argument("name")
    x.add_argument("--with", dest="with_", required=True)
    x.set_defaults(fn=handoff.cmd_unshare)

    for name, fn, hlp in (("up", spaces.cmd_up, "start this Space's services"),
                          ("down", spaces.cmd_down, "stop this Space's services"),
                          ("services", spaces.cmd_services, "show this Space's services")):
        x = sub.add_parser(name, help=hlp)
        x.add_argument("--space")
        x.set_defaults(fn=fn)
    x = sub.add_parser("logs", help="follow a service's logs")
    x.add_argument("service")
    x.add_argument("--space")
    x.set_defaults(fn=spaces.cmd_logs)

    # ---- timeline
    x = sub.add_parser("undo", help="restore the last deletion (or a snapshot id)")
    x.add_argument("id", nargs="?")
    x.set_defaults(fn=timeline.cmd_undo)
    tl = sub.add_parser("timeline", help="history: snapshots, system deployments, apps")
    tl.add_argument("--path")
    tl.add_argument("--limit", type=int, default=25)
    tl.add_argument("--all", action="store_true", help="also show system and app history")
    tl.set_defaults(fn=timeline.cmd_list)
    ts = tl.add_subparsers(dest="sub", metavar="<action>")
    x = ts.add_parser("list")
    x.add_argument("--path")
    x.add_argument("--limit", type=int, default=25)
    x.add_argument("--all", action="store_true")
    x.set_defaults(fn=timeline.cmd_list)
    x = ts.add_parser("snap", help="snapshot a path (default: this Space)")
    x.add_argument("path", nargs="?")
    x.add_argument("-m", "--message")
    x.set_defaults(fn=timeline.cmd_snap)
    x = ts.add_parser("show", help="what a snapshot contains and what restoring will do")
    x.add_argument("id")
    x.add_argument("--limit", type=int, default=40)
    x.set_defaults(fn=timeline.cmd_show)
    x = ts.add_parser("restore", help="restore a snapshot (never overwrites newer files)")
    x.add_argument("id")
    x.add_argument("--to")
    x.add_argument("--merge", action="store_true",
                   help="put it back in place: changed/deleted files return, files made since are kept (current state is saved first)")
    x.set_defaults(fn=timeline.cmd_restore)
    x = ts.add_parser("prune", help="delete old snapshots")
    x.add_argument("--keep", type=int)
    x.add_argument("--days", type=int)
    x.add_argument("-y", "--yes", action="store_true")
    x.set_defaults(fn=timeline.cmd_prune)
    x = ts.add_parser("system", help="OS deployment history; --rollback to go back")
    x.add_argument("--rollback", action="store_true")
    x.set_defaults(fn=timeline.cmd_system)

    # ---- fabric
    fb = sub.add_parser("fabric", help="your devices working together").add_subparsers(dest="sub", metavar="<action>", required=True)
    x = fb.add_parser("pair", help="add a trusted device")
    x.add_argument("name")
    x.add_argument("host", help="user@host (LAN, WireGuard or Tailscale address)")
    x.add_argument("--can", default="build,run", help="capabilities to allow (build,run)")
    x.add_argument("--force", action="store_true")
    x.set_defaults(fn=fabric.cmd_pair)
    fb.add_parser("ls", aliases=["devices"], help="devices and how busy they are").set_defaults(fn=fabric.cmd_ls)
    x = fb.add_parser("revoke", help="remove a device and its access")
    x.add_argument("name")
    x.set_defaults(fn=fabric.cmd_revoke)
    x = fb.add_parser("run", help="run a command on another device: xora fabric run --on pc -- make")
    x.add_argument("--on", default="auto")
    x.add_argument("--get", action="append", help="path to bring back afterwards (repeatable)")
    x.add_argument("--fallback", choices=["local", "queue", "fail"], default="local")
    x.add_argument("--build", action="store_true", help="needs the 'build' capability")
    x.add_argument("cmd", nargs=argparse.REMAINDER)
    x.set_defaults(fn=fabric.cmd_run)
    x = fb.add_parser("invite", help="show a QR code / pairing code for another device to join")
    x.add_argument("--name", help="what to call the joining device")
    x.add_argument("--can", default="build,run,store", help="what the joining device may do here")
    x.set_defaults(fn=fabric.cmd_invite)
    x = fb.add_parser("join", help="join another device's Fabric with its pairing code (6 digits or long code)")
    x.add_argument("code", nargs="+")
    x.add_argument("--name")
    x.add_argument("--can", default="build,run,store")
    x.set_defaults(fn=fabric.cmd_join)
    fb.add_parser("discover", help="find XORA devices on this network").set_defaults(fn=fabric.cmd_discover)
    x = fb.add_parser("mirror", help="copy your Spaces to devices allowed to 'store' (nothing is lost)")
    x.add_argument("--space")
    x.set_defaults(fn=fabric.cmd_mirror)
    x = fb.add_parser("recover", help="get a Space back from a device's copy")
    x.add_argument("space")
    x.add_argument("--device", required=True)
    x.add_argument("--from-host", help="name of the computer the copy came from (default: this one)")
    x.add_argument("--to")
    x.set_defaults(fn=fabric.cmd_recover)
    x = fb.add_parser("image-push", help="send a container image to a device over the LAN, not the internet")
    x.add_argument("image")
    x.add_argument("--to", default="all")
    x.set_defaults(fn=fabric.cmd_image_push)
    x = fb.add_parser("update-cache", help="keep OS updates for the other XORA devices here, so the office downloads them once")
    x.add_argument("action", nargs="?", choices=["on", "off", "status"])
    x.add_argument("--registry", help="registry to cache (default: the one this system updates from)")
    x.set_defaults(fn=fabric.cmd_update_cache)
    x = fb.add_parser("send", help="send files to a device's Received folder over the LAN")
    x.add_argument("paths", nargs="+")
    x.add_argument("--to")
    x.set_defaults(fn=fabric.cmd_send)
    x = fb.add_parser("queue", help="jobs waiting for a device")
    x.add_argument("--run", action="store_true")
    x.set_defaults(fn=fabric.cmd_queue)

    # ---- explain / ask
    x = sub.add_parser("explain", help="health check, or run a command and explain its failure")
    x.add_argument("--only", help="memory,disk,cpu,power,network,services")
    x.add_argument("--cards", action="store_true", help="the Explain cards the desktop would show now")
    x.add_argument("--json", action="store_true", help="with --cards: as JSON")
    x.add_argument("--watch", action="store_true", help="background service: show Explain cards as desktop notifications")
    x.add_argument("cmd", nargs=argparse.REMAINDER)
    x.set_defaults(fn=explain.cmd_explain)
    x = sub.add_parser("apps", help="apps from everywhere: Android, Windows, Ubuntu/Debian/Arch, Flatpak")
    x.add_argument("what", nargs="?", choices=["android", "windows", "windows-vm", "ubuntu", "debian", "arch", "fedora", "export"])
    x.add_argument("args", nargs=argparse.REMAINDER)
    x.set_defaults(fn=apps.cmd_apps)
    x = sub.add_parser("install", help="install any app: .exe .msi .apk .deb .rpm .AppImage, or a name from the app store")
    x.add_argument("target")
    x.set_defaults(fn=install.cmd_install)
    x = sub.add_parser("tools", help="security and DevOps toolkits; the full Kali toolset in a container")
    x.add_argument("action", nargs="?", choices=["kali", "run"])
    x.add_argument("--full", action="store_true", help="with kali: the full desktop toolset (kali-linux-default)")
    x.add_argument("cmd", nargs=argparse.REMAINDER)
    x.set_defaults(fn=tools.cmd_tools)
    x = sub.add_parser("vpn", help="VPNs: import, connect, always-on, kill switch")
    x.add_argument("action", nargs="?", choices=["import", "on", "off", "always", "killswitch", "status"])
    x.add_argument("args", nargs="*")
    x.add_argument("--name")
    x.set_defaults(fn=vpn.cmd_vpn)
    x = sub.add_parser("speed", help="internet speed, latency and DNS, and what's slowing it down")
    x.add_argument("--no-download", action="store_true")
    x.set_defaults(fn=speed.cmd_speed)
    x = sub.add_parser("where", help="where a file lives: device, Space, copies, versions, Git")
    x.add_argument("path")
    x.add_argument("--gui", action="store_true")
    x.set_defaults(fn=where.cmd_where)
    x = sub.add_parser("anon", help="Anon mode: all traffic through Tor, with a kill switch")
    x.add_argument("action", nargs="?", choices=["on", "off", "status", "check"])
    x.set_defaults(fn=system.cmd_anon)
    x = sub.add_parser("ask", help="ask in plain words")
    x.add_argument("--no-ai", action="store_true")
    x.add_argument("question", nargs=argparse.REMAINDER)
    x.set_defaults(fn=explain.cmd_ask)

    # ---- secrets
    se = sub.add_parser("secret", help="secrets for Spaces").add_subparsers(dest="sub", metavar="<action>", required=True)
    x = se.add_parser("set")
    x.add_argument("key", help="e.g. attndi/db_password")
    x.set_defaults(fn=vault.cmd_set)
    x = se.add_parser("rm")
    x.add_argument("key")
    x.set_defaults(fn=vault.cmd_rm)

    x = sub.add_parser("privacy", help="who is using the camera, mic and network; revoke app access")
    x.add_argument("--revoke", metavar="APP")
    x.add_argument("--what", choices=["camera", "mic", "files", "network"])
    x.set_defaults(fn=system.cmd_privacy)
    x = sub.add_parser("data", help="data usage, metered mode, night-time updates")
    x.add_argument("--metered", choices=["on", "off"])
    x.add_argument("--updates", choices=["night", "now", "off"])
    x.add_argument("--budget", nargs=2, metavar=("APP", "SIZE"), help="daily data budget for an app, e.g. --budget firefox 500MB (0 removes it)")
    x.add_argument("--allow", nargs=2, metavar=("APP", "SIZE"), help="extra data for an app today, e.g. --allow firefox 100MB")
    x.set_defaults(fn=system.cmd_data)
    x = sub.add_parser("resilience", help="power cuts and UPS: checkpoints and safe shutdown")
    x.add_argument("action", nargs="?", choices=["status", "watch", "checkpoint", "onbattery"], default="status")
    x.add_argument("--reason")
    x.set_defaults(fn=system.cmd_resilience)
    sub.add_parser("boot", help="what slows startup").set_defaults(fn=system.cmd_boot)
    x = sub.add_parser("status", help="state for the desktop widgets")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=system.cmd_status)
    x = sub.add_parser("ai", help="opt-in local AI for plain-words answers (runs only on this computer)")
    x.add_argument("action", nargs="?", choices=["status", "enable", "disable", "remove"], default="status")
    x.add_argument("--model")
    x.set_defaults(fn=system.cmd_ai)
    x = sub.add_parser("welcome", help="first-login welcome")
    x.add_argument("--once", action="store_true")
    x.set_defaults(fn=system.cmd_welcome)
    x = sub.add_parser("places", help="keep Projects, Spaces and devices in the Files sidebar")
    x.add_argument("action", nargs="?", choices=["sync"], default="sync")
    x.set_defaults(fn=places.cmd_sync)
    sub.add_parser("help", help="this help").set_defaults(fn=lambda a: build().print_help())
    sub.add_parser("info", help="about this system").set_defaults(fn=cmd_info)
    sub.add_parser("fix", help="print the last suggested fix (the F2 key runs it)").set_defaults(fn=cmd_fix)
    sub.add_parser("rm", help="delete with a Timeline snapshot first (accepts -r -f)", add_help=False)
    sub.add_parser("center", help="XORA Center app: Home, Devices (pairing), Timeline; --setup for first boot", add_help=False)
    return p


def cmd_rm(argv):
    from .timeline import cmd_rm as rm
    flags = [a for a in argv if a.startswith("-") and a != "--"]
    paths = [a for a in argv if not a.startswith("-") or a == "--"]
    if "--" in argv:
        i = argv.index("--")
        flags = [a for a in argv[:i] if a.startswith("-")]
        paths = [a for a in argv[:i] if not a.startswith("-")] + argv[i + 1:]
    if not paths:
        print("rm: missing operand")
        return 1
    ns = argparse.Namespace(paths=paths, flags=[f for f in flags if not f.startswith("--")],
                            recursive="--recursive" in flags, force="--force" in flags, raw=argv)
    return rm(ns)


def cmd_info(a):
    from .util import blue, bold, cyan, green, out
    from .spaces import active, all_names
    from .fabric import _devices
    osr = {}
    try:
        for l in open("/etc/os-release"):
            if "=" in l:
                k, v = l.rstrip().split("=", 1)
                osr[k] = v.strip('"')
    except OSError:
        pass
    art = [
        "  ▄▄▄▄          ▄▄▄",
        "   ▀███▄      ▄██▀ ",
        "     ▀███▄  ▄██▀   ",
        "       ▀█████▀     ",
        "      ▄██▀▀███▄    ",
        "    ▄██▀    ▀███▄  ",
        "  ▄██▀       ▀████▄",
    ]
    mem = out(["free", "-h", "--si"]).splitlines()
    mem = mem[1].split()[2] + " / " + mem[1].split()[1] if len(mem) > 1 else "?"
    lines = [
        f"{bold(blue(os.environ.get('USER', 'user')))}@{bold(blue(platform.node()))}",
        "─" * 22,
        f"{cyan('OS')}       {osr.get('PRETTY_NAME', platform.system())}",
        f"{cyan('Kernel')}   {platform.release()}",
        f"{cyan('Shell')}    {os.path.basename(os.environ.get('SHELL', '?'))}",
        f"{cyan('Memory')}   {mem}",
        f"{cyan('Space')}    {active() or '-'}  ({len(all_names())} total)",
        f"{cyan('Fabric')}   {len(_devices())} paired device(s)",
        f"{cyan('xora')}     {__version__}",
    ]
    for i in range(max(len(art), len(lines))):
        print(f"{cyan(art[i]) if i < len(art) else ' ' * 19}   {lines[i] if i < len(lines) else ''}")


def cmd_fix(a):
    from .util import FIX_FILE
    if FIX_FILE.exists():
        print(FIX_FILE.read_text().strip())
    else:
        return 1


def main(argv=None):
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet exit when piped into head/less
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["rm"]:
            return cmd_rm(argv[1:]) or 0
        if argv[:1] == ["center"]:
            from . import center
            return center.main(argv[1:]) or 0
        p = build()
        if not argv:
            p.print_help()
            return 0
        a = p.parse_args(argv)
        if not hasattr(a, "fn"):
            p.parse_args(argv + ["--help"])
        return a.fn(a) or 0
    except KeyboardInterrupt:
        print()
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
