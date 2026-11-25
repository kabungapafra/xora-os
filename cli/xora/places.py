"""Files sidebar: keep XORA's entries in Dolphin's Places (~/.local/share/user-places.xbel).

  Projects        ~/Projects
  each Space      its project folder (icon: folder-xora-space)
  each device     sftp://user@host/ for paired Fabric devices (Dolphin lists these under Remote)

Only entries XORA added (marked <XoraManaged/>) are ever changed or removed. If KDE hasn't
created the file yet, nothing is written; the login autostart runs `xora places sync` again.
"""
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from .util import info, ok

XBEL = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "user-places.xbel"
NS_BM = "http://www.freedesktop.org/standards/desktop-bookmarks"
NS_MIME = "http://www.freedesktop.org/standards/shared-mime-info"
ET.register_namespace("bookmark", NS_BM)
ET.register_namespace("mime", NS_MIME)
FD, KDE = "http://freedesktop.org", "http://www.kde.org"


def _wanted():
    from .fabric import _devices
    from .spaces import all_names, load_yaml, path_of, project_dir
    want = []
    projects = Path.home() / "Projects"
    if projects.is_dir():
        want.append(("Projects", projects.as_uri(), "folder-development"))
    for n in all_names():
        m = load_yaml(path_of(n)) or {}
        d = project_dir({"space": n, **m})
        want.append((n, d.as_uri(), "folder-xora-space"))
    for name, dev in _devices().items():
        host = dev["host"]
        user, _, h = host.rpartition("@")
        url = f"sftp://{quote(user) + '@' if user else ''}{h}/"
        want.append((name, url, "folder-remote"))
    return want


def _managed(bm):
    for md in bm.iter("metadata"):
        if md.get("owner") == KDE and md.find("XoraManaged") is not None:
            return True
    return False


def _bookmark(title, href, icon):
    bm = ET.Element("bookmark", {"href": href})
    ET.SubElement(bm, "title").text = title
    inf = ET.SubElement(bm, "info")
    fd = ET.SubElement(inf, "metadata", {"owner": FD})
    ET.SubElement(fd, f"{{{NS_BM}}}icon", {"name": icon})
    kde = ET.SubElement(inf, "metadata", {"owner": KDE})
    ET.SubElement(kde, "ID").text = f"{int(time.time())}/xora-{abs(hash(href)) % 10**8}"
    ET.SubElement(kde, "XoraManaged").text = "true"
    return bm


def sync(quiet=True):
    if not XBEL.exists():
        if not quiet:
            info("Dolphin hasn't created its Places list yet; XORA will add its entries at next login")
        return False
    tree = ET.parse(XBEL)
    root = tree.getroot()
    want = _wanted()
    want_hrefs = {h for _, h, _ in want}
    have = {}
    changed = False
    for bm in list(root.findall("bookmark")):
        href = bm.get("href")
        if _managed(bm):
            if href not in want_hrefs or href in have:
                root.remove(bm)
                changed = True
                continue
        have[href] = bm
    for title, href, icon in want:
        if href not in have:
            root.append(_bookmark(title, href, icon))
            changed = True
    if changed:
        ET.indent(tree, space=" ")
        body = ET.tostring(root, encoding="unicode")
        tmp = XBEL.with_suffix(".xora-tmp")
        tmp.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xbel>\n' + body + "\n")
        tmp.replace(XBEL)
    if not quiet:
        ok(f"Places: {len(want)} XORA entr{'y' if len(want) == 1 else 'ies'} (Projects, Spaces, devices)")
    return True


def cmd_sync(a):
    sync(quiet=False)
