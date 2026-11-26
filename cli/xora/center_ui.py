"""GTK 4 interface for XORA Center. Data and actions live in center.py and the xora modules."""
import datetime as dt
import shlex
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import center as C  # noqa: E402
from .util import STATE, have, load_yaml, tilde  # noqa: E402

CSS = Path(__file__).with_name("center.css")


# ================================================================ small helpers

def L(text="", *cls, x=0.0, wrap=False, markup=False, sel=False):
    w = Gtk.Label()
    (w.set_markup if markup else w.set_text)(text)
    w.set_xalign(x)
    if wrap:
        w.set_wrap(True)
        w.set_natural_wrap_mode(Gtk.NaturalWrapMode.WORD)
    w.set_selectable(sel)
    for c in cls:
        w.add_css_class(c)
    return w


def B(vertical=True, spacing=0, *cls, **kw):
    w = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)
    for c in cls:
        w.add_css_class(c)
    for k, v in kw.items():
        getattr(w, "set_" + k)(v)
    return w


def btn(label, cb, *cls):
    b = Gtk.Button(label=label)
    for c in cls:
        b.add_css_class(c)
    if cb:
        b.connect("clicked", lambda *_: cb())
    return b


def pad(w, t=0, r=0, b=0, l=0):
    w.set_margin_top(t)
    w.set_margin_end(r)
    w.set_margin_bottom(b)
    w.set_margin_start(l)
    return w


def clear(box):
    c = box.get_first_child()
    while c:
        nxt = c.get_next_sibling()
        box.remove(c)
        c = nxt


def spacer(h=True):
    w = Gtk.Box()
    w.set_hexpand(h)
    w.set_vexpand(not h)
    return w


def bg(fn, done=None, *args):
    """Run fn(*args) on a worker thread, then done(result_or_exception) on the UI thread."""
    def work():
        try:
            r = fn(*args)
        except Exception as e:  # shown in the UI, never a crash
            r = e
        if done:
            GLib.idle_add(lambda: done(r) and False)
    threading.Thread(target=work, daemon=True).start()


def logo(dark, w=92, h=30):
    p = C.LOGO_DARK if dark else C.LOGO_LIGHT
    if not Path(p).exists():  # running from source
        p = str(Path(__file__).resolve().parents[2] / "os/files" / p.lstrip("/"))
    from gi.repository import GdkPixbuf
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(p, w, h, True)
    except GLib.Error:
        return L("XORA", "h-sec")
    pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
    pic.set_can_shrink(False)
    pic.set_halign(Gtk.Align.START)
    pic.set_valign(Gtk.Align.CENTER)
    return pic


def text_window(parent, title, text, dark=True):
    win = Gtk.Window(title=title, transient_for=parent, modal=True, default_width=820, default_height=560)
    win.add_css_class("xora")
    win.add_css_class("dark" if dark else "light")
    tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    tv.add_css_class("diff")
    pad(tv, 14, 14, 14, 14)
    buf = tv.get_buffer()
    buf.set_text(text)
    if text.startswith("---") or "\n@@" in text:  # colour a unified diff
        plus = buf.create_tag(None, foreground="#9FE6B5")
        minus = buf.create_tag(None, foreground="#F59A9A")
        hunk = buf.create_tag(None, foreground="#7FB8FF")
        for i, line in enumerate(text.splitlines()):
            tag = hunk if line.startswith("@@") else plus if line.startswith("+") else minus if line.startswith("-") else None
            if tag:
                s = buf.get_iter_at_line(i)[1]
                e = s.copy()
                e.forward_to_line_end()
                buf.apply_tag(tag, s, e)
    sw = Gtk.ScrolledWindow(child=tv)
    win.set_child(sw)
    win.present()
    return win


def ask_window(parent, title, fields, on_ok, ok_label="Add"):
    """Small dark form: fields = [(key, label, placeholder)]."""
    win = Gtk.Window(title=title, transient_for=parent, modal=True, default_width=440)
    win.add_css_class("xora")
    win.add_css_class("dark")
    box = pad(B(True, 10), 22, 22, 22, 22)
    box.append(L(title, "h-sec"))
    entries = {}
    for k, label, ph in fields:
        box.append(L(label, "muted", "small"))
        e = Gtk.Entry(placeholder_text=ph)
        entries[k] = e
        box.append(e)
    row = B(False, 8)
    row.append(spacer())
    row.append(btn("Cancel", win.close, "btn", "flat"))

    def ok():
        vals = {k: e.get_text().strip() for k, e in entries.items()}
        if all(vals.values()):
            win.close()
            on_ok(vals)
    row.append(btn(ok_label, ok, "btn", "primary"))
    box.append(pad(row, 8))
    win.set_child(box)
    win.present()


# ================================================================ Home (light)

class HomePage(Gtk.ScrolledWindow):
    dark = False

    def __init__(self, app):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.app = app
        root = pad(B(True, 0), 18, 40, 30, 40)
        self.set_child(root)

        top = B(False, 18)
        top.append(logo(False, 150, 40))
        self.clock = L("", "muted", x=0.5)
        self.clock.set_hexpand(True)
        top.append(self.clock)
        self.status = B(False, 18)
        top.append(self.status)
        root.append(top)

        cols = pad(B(False, 28), 26)
        root.append(cols)
        left = B(True, 0)
        left.set_hexpand(True)
        cols.append(left)

        self.hello = L("", "h-hero")
        left.append(self.hello)
        self.summary = pad(L("", "lead", "muted", wrap=True), 6)
        left.append(self.summary)

        search = pad(B(False, 10, "search"), 18)
        search.append(pad(Gtk.Image.new_from_icon_name("system-search-symbolic"), 0, 0, 0, 16))
        self.entry = Gtk.Entry(placeholder_text="Open a Space, find a file, or ask XORA why something is slow")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", lambda e: self.on_search(e.get_text().strip()))
        search.append(self.entry)
        search.append(pad(L("Alt + Space", "kbd"), 0, 14, 0, 0))
        search.get_last_child().set_valign(Gtk.Align.CENTER)
        left.append(search)
        self.chips = pad(B(False, 8), 14)
        left.append(self.chips)
        self.explain = pad(B(True, 10), 0)
        left.append(self.explain)

        hdr = pad(B(False), 26, 0, 12)
        hdr.append(L("Your Spaces", "h-sec"))
        hdr.append(spacer())
        hdr.append(btn("New Space", self.new_space, "link"))
        left.append(hdr)
        self.spaces = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, row_spacing=14, column_spacing=14,
                                  max_children_per_line=4, min_children_per_line=1, homogeneous=True)
        left.append(self.spaces)

        hdr = pad(B(False), 28, 0, 12)
        hdr.append(L("Your devices, working as one", "h-sec"))
        hdr.append(spacer())
        hdr.append(btn("Add a device", lambda: app.show("pair"), "link"))
        left.append(hdr)
        self.devs = B(False, 0)
        left.append(self.devs)

        tl = pad(B(True, 0, "card"), 0, 0, 0, 0)
        tl.set_size_request(340, -1)
        tl.set_valign(Gtk.Align.START)
        inner = pad(B(True, 0), 22, 20, 20, 20)
        tl.append(inner)
        inner.append(L("Timeline", "h-sec"))
        inner.append(pad(L("Everything you can go back to. Restoring never deletes newer work.", "muted", "small", wrap=True), 4, 0, 10))
        self.tl = B(True, 2)
        inner.append(self.tl)
        inner.append(pad(btn("Open full Timeline", lambda: app.show("timeline"), "btn"), 18))
        cols.append(tl)

        self.devices = []
        GLib.timeout_add_seconds(30, self.tick)
        self.tick()

    # ---------------------------------------------------------------- refresh
    def tick(self):
        self.clock.set_text(dt.datetime.now().strftime("%A %-d %B · %H:%M"))
        return True

    def refresh(self):
        name = C.first_name()
        self.hello.set_text(f"{C.greeting()}{', ' + name if name else ''}")
        bg(lambda: (C.spaces_info(), C.events(), C.status_bar(), C.devices_info(probe=False)), self.fill)
        bg(lambda: C.devices_info(probe=True), self.fill_devices)
        from . import cards
        bg(lambda: cards.cards(slow=False), self.fill_explain)

    def fill(self, r):
        if isinstance(r, Exception):
            self.summary.set_text(f"Couldn't read your Spaces: {r}")
            return
        spaces, evs, st, devs = r
        self.spaces_data, self.evs = spaces, evs
        if not self.devices:
            self.fill_devices(devs)
        self.fill_status(st, devs)
        self.fill_spaces(spaces)
        self.fill_timeline(evs)
        self.fill_summary()

    def fill_explain(self, found):
        """Explain cards (same as the desktop notifications), so they're here even after a notification is closed."""
        from . import cards
        clear(self.explain)
        if isinstance(found, Exception):
            return
        sn = C.load_json(cards.SNOOZE_FILE, {})
        for card in found:
            if sn.get(card.key, 0) > time.time():
                continue
            box = pad(B(True, 6, "explain-card", card.level), 18)
            box.append(L(f"Explain · {card.title}", "h-card"))
            body = L(card.body, "small", wrap=True, markup=True)
            box.append(body)
            row = pad(B(False, 8), 6)
            for act in card.actions[:2]:
                row.append(btn(act[1], lambda card=card, act=act, body=body: self.explain_action(card, act, body), "btn"))
            row.append(btn("Ignore", lambda card=card: (cards.snooze(card.key, 24 * 3600), self.refresh()), "btn", "flat"))
            box.append(row)
            self.explain.append(box)

    def explain_action(self, card, act, body):
        from . import cards
        body.set_text(f"{act[1]}…")
        def done(msg):
            body.set_text(str(msg) if isinstance(msg, Exception) else (msg or f"{act[1]}: opened."))
            GLib.timeout_add_seconds(5, lambda: self.refresh() and False)   # let the result be read first
        bg(lambda: cards.run_action(card, act[0]), done)

    def fill_status(self, st, devs):
        clear(self.status)
        n = len(devs)
        self.status.append(L(f"{n} device{'s' if n != 1 else ''} linked" if n > 1 else "Only this device", "muted", "small"))
        if st["updates"]:
            self.status.append(L(st["updates"], "muted", "small"))
        if st["battery"] is not None:
            self.status.append(L(f"{st['battery']}%" + (" ⚡" if st["charging"] else ""), "muted", "small"))

    def fill_summary(self):
        spaces = getattr(self, "spaces_data", [])
        bits = []
        changed = [s for s in spaces if s["changes"]]
        if changed:
            bits.append(f"{len(changed)} Space{'s have' if len(changed) != 1 else ' has'} uncommitted changes.")
        elif spaces:
            bits.append(f"You have {len(spaces)} Space{'s' if len(spaces) != 1 else ''}. Everything is committed.")
        else:
            bits.append("Make a Space from a project folder and XORA can bring the whole project back in one go.")
        fb = C.free_builder(self.devices) if self.devices else None
        if fb:
            bits.append(f"Your {fb['name']} is free for builds.")
        self.summary.set_text(" ".join(bits))
        clear(self.chips)
        for label, act in C.suggestions(spaces, self.devices, getattr(self, "evs", [])):
            b = btn(label, lambda act=act: self.do(act), "chip")
            self.chips.append(b)

    def fill_spaces(self, spaces):
        clear_flow(self.spaces)
        if not spaces:
            card = pad(B(True, 8, "card"), 0)
            inner = pad(B(True, 8), 18, 18, 18, 18)
            inner.append(L("No Spaces yet", "h-card"))
            inner.append(L("A Space remembers a project's code, tools, databases, terminals and windows.", "muted", wrap=True))
            inner.append(pad(btn("Make a Space from a folder", self.new_space, "btn"), 6))
            card.append(inner)
            self.spaces.append(card)
            return
        for s in spaces[:8]:
            self.spaces.append(self.space_card(s))

    def space_card(self, s):
        card = B(True, 0, "card")
        inner = pad(B(True, 3), 16, 16, 16, 16)
        card.append(inner)
        head = B(False, 6)
        head.append(L(s["name"], "h-card"))
        head.append(spacer())
        text, cls = C.space_state(s)
        head.append(L(text, "pill", cls))
        head.get_last_child().set_valign(Gtk.Align.CENTER)
        inner.append(head)
        inner.append(pad(L(s["stack"], "small", wrap=True), 6))
        if s["branch"]:
            inner.append(L(f"Branch {s['branch']}" + (f" · {s['changes']} change{'s' if s['changes'] != 1 else ''}" if s["changes"] else ""), "small"))
        else:
            inner.append(L(f"Last opened {C.when(s['opened'])}", "small"))
        inner.append(pad(L("On this computer" if s["exists"] else "Folder not on this computer yet", "muted", "small"), 8))
        if s["active"]:
            b = btn("Return to Space", lambda n=s["name"]: C.in_terminal(["space", "open", n]), "btn", "current")
        else:
            b = btn("Open", lambda n=s["name"]: C.in_terminal(["space", "open", n]), "btn")
        inner.append(pad(b, 10))
        return card

    def fill_devices(self, devs):
        if isinstance(devs, Exception):
            return
        self.devices = devs
        clear(self.devs)
        for i, d in enumerate(devs[:4]):
            if i:
                w = B(True, 0, "wire")
                w.set_size_request(24, 2)
                w.set_valign(Gtk.Align.CENTER)
                self.devs.append(w)
            card = B(True, 4, "card")
            card.set_hexpand(True)
            inner = pad(B(True, 6), 14, 16, 16, 16)
            card.append(inner)
            head = B(False)
            head.append(L(d["name"], "h-card"))
            head.append(spacer())
            text, cls = C.device_status(d)
            head.append(L(text, "small", "muted" if not cls else "status-ok"))
            inner.append(head)
            if d.get("mem_total"):
                inner.append(L(f"Memory {d['mem_used']:.1f} of {d['mem_total']:.0f} GB", "small"))
                bar = Gtk.ProgressBar(fraction=min(1.0, d["mem_used"] / d["mem_total"]))
                if d["mem_used"] / d["mem_total"] > 0.8:
                    bar.add_css_class("hot")
                inner.append(pad(bar, 4))
            else:
                inner.append(L(d.get("host", ""), "small", "muted"))
            self.devs.append(card)
        if hasattr(self, "spaces_data"):
            self.fill_summary()

    def fill_timeline(self, evs):
        clear(self.tl)
        if not evs:
            self.tl.append(L("Nothing yet. XORA saves a snapshot before anything is deleted, and checkpoints open Spaces every 30 minutes.",
                             "muted", "small", wrap=True))
            return
        day = None
        for i, e in enumerate(evs[:6]):
            dl = C.day_label(e["at"])
            if dl != day:
                day = dl
                self.tl.append(pad(L(dl, "cap"), 8 if i else 0, 0, 4))
            row = B(False, 14, "tl-row")
            if i == 0:
                row.add_css_class("first")
            row.append(L(time.strftime("%H:%M", time.localtime(e["at"])), "tl-time"))
            col = B(True, 1)
            col.append(L(e["title"], "h-card", "small"))
            col.append(L(e["sub"], "small", "muted"))
            col.get_last_child().set_ellipsize(3)
            col.set_hexpand(True)
            row.append(col)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, e=e: self.app.show("timeline", select=e))
            row.add_controller(click)
            self.tl.append(row)

    # ---------------------------------------------------------------- actions
    def do(self, act):
        k = act[0]
        if k == "open":
            C.in_terminal(["space", "open", act[1]])
        elif k == "build":
            s = next((s for s in self.spaces_data if s["name"] == act[1]), None)
            m = load_yaml(Path.home() / ".config/xora/spaces" / f"{act[1]}.yaml") or {}
            cmd = m.get("build_cmd")
            if cmd and s:
                C.in_terminal(["fabric", "run", "--on", act[2], "--build", "--", *shlex.split(cmd)], cwd=s["dir"])
            else:
                text_window(self.get_root(), "Build on another device",
                            f"Add a build command to the Space so XORA knows what to run, for example:\n\n"
                            f"  xora space edit {act[1]}\n\n  build_cmd: flutter build apk\n\n"
                            f"Then this button runs it on {act[2]} and brings the results back.", dark=False)
        elif k == "timeline-path":
            self.app.show("timeline", path=act[1])
        elif k == "timeline":
            self.app.show("timeline")
        elif k == "ask":
            self.ask(act[1])

    def ask(self, q):
        win = text_window(self.get_root(), "XORA explains", "Measuring…", dark=False)
        bg(lambda: C.run_xora("ask", q, timeout=90),
           lambda r: win.get_child().get_child().get_buffer().set_text(str(r)) or False)

    def on_search(self, q):
        if not q:
            return
        names = [s["name"] for s in getattr(self, "spaces_data", [])]
        hit = next((n for n in names if n == q.lower()), None) or next((n for n in names if n.startswith(q.lower())), None)
        if hit:
            C.in_terminal(["space", "open", hit])
        elif q.endswith("?") or q.lower().split()[0] in ("why", "what", "how", "is", "which", "who"):
            self.ask(q)
        elif not C.krunner(q):
            self.ask(q)
        self.entry.set_text("")

    def new_space(self):
        dlg = Gtk.FileDialog(title="Choose the project folder for the new Space")
        projects = Path.home() / "Projects"
        if projects.is_dir():
            dlg.set_initial_folder(Gio.File.new_for_path(str(projects)))

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except GLib.Error:
                return
            if f:
                C.in_terminal(["space", "create", "--dir", f.get_path()])
        dlg.select_folder(self.get_root(), None, done)


def clear_flow(fb):
    c = fb.get_first_child()
    while c:
        nxt = c.get_next_sibling()
        fb.remove(c)
        c = nxt


# ================================================================ Devices / pairing (dark)

class PairPage(Gtk.ScrolledWindow):
    dark = True

    def __init__(self, app, setup=None):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.app, self.setup = app, setup
        self.inv = None
        self.inv_error = None
        self.found = []
        self.selected = None
        self.message = ""
        self.request_seen = None
        root = pad(B(True, 0), 34, 120, 30, 120)
        self.set_child(root)

        top = B(False, 10)
        top.append(logo(True, 130, 36))
        if setup:
            top.append(L("setup", "muted"))
            top.append(spacer())
            top.append(setup.step_bars(3))
        else:
            top.append(spacer())
        root.append(top)

        root.append(pad(L("Add your other devices", "h-big"), 34))
        lead = L("Linked devices can share builds, projects and storage. You choose exactly what each one can do, "
                 "and you can unlink it any time.", "lead", "muted", wrap=True)
        lead.set_max_width_chars(80)
        root.append(pad(lead, 10, 0, 28))

        grid = B(False, 28)
        root.append(grid)

        qr = B(True, 8, "card")
        qr.set_size_request(400, -1)
        qin = pad(B(True, 8), 26, 26, 26, 26)
        qr.append(qin)
        wrap = B(True, 0, "qr-wrap")
        wrap.set_halign(Gtk.Align.CENTER)
        wrap.set_valign(Gtk.Align.START)
        wrap.set_vexpand(False)
        self.qr = Gtk.Image(pixel_size=228)   # fixed size: a Picture grows with the card's width
        wrap.append(self.qr)
        qin.append(wrap)
        self.qr_title = pad(L("Link another XORA device", "h-card", x=0.5), 14)
        qin.append(self.qr_title)
        self.qr_text = L("", "small", "muted", x=0.5, markup=True)
        self.qr_text.set_justify(Gtk.Justification.CENTER)
        qin.append(self.qr_text)
        self.expiry = pad(L("", "small", "muted", x=0.5), 10)
        qin.append(self.expiry)
        self.new_code = btn("New code", self.start_invite, "btn", "small")
        self.new_code.set_halign(Gtk.Align.CENTER)
        self.new_code.set_visible(False)
        qin.append(self.new_code)
        grid.append(qr)

        right = B(True, 20)
        right.set_hexpand(True)
        grid.append(right)
        found = B(True, 0, "card")
        fin = pad(B(True, 10), 20, 22, 22, 22)
        found.append(fin)
        hdr = B(False)
        hdr.append(L("Found on this network", "h-card"))
        hdr.append(spacer())
        self.searching = L("Searching…", "small", "muted")
        hdr.append(self.searching)
        fin.append(hdr)
        self.rows = B(True, 10)
        fin.append(self.rows)
        self.msg = L("", "small", wrap=True)
        fin.append(self.msg)
        right.append(found)

        caps = B(True, 0, "card")
        cin = pad(B(True, 12), 20, 22, 22, 22)
        caps.append(cin)
        self.caps_title = L("", "h-card")
        cin.append(self.caps_title)
        self.caps_grid = Gtk.Grid(row_spacing=10, column_spacing=10, column_homogeneous=True)
        cin.append(self.caps_grid)
        self.checks = {}
        for i, (key, title, sub) in enumerate(C.CAPS):
            cb = Gtk.CheckButton()
            row = B(False, 12, "sub")
            row.append(pad(cb, 12, 0, 12, 14))
            col = pad(B(True, 1), 10, 10, 10)
            col.append(L(title, "h-card", "small"))
            col.append(L(sub, "small", "muted"))
            row.append(col)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, cb=cb: cb.set_active(not cb.get_active()))
            col.add_controller(click)
            cb.connect("toggled", lambda _cb, key=key: self.cap_toggled(key))
            self.checks[key] = cb
            self.caps_grid.attach(row, i % 2, i // 2, 1, 1)
        self.caps_note = L("", "small", "muted", wrap=True)
        cin.append(self.caps_note)
        right.append(caps)

        if setup:
            bot = pad(B(False, 10), 34)
            bot.append(btn("Skip for now", setup.next, "btn", "flat"))
            bot.append(spacer())
            bot.append(btn("Continue", setup.next, "btn", "primary"))
            root.append(bot)

        self._updating = False
        GLib.timeout_add_seconds(1, self.tick)
        GLib.timeout_add_seconds(15, self.rediscover)

    # ---------------------------------------------------------------- invite
    def refresh(self):
        if not self.inv or self.inv.closed or not self.inv.remaining():
            self.start_invite()
        self.render()
        self.rediscover()

    def start_invite(self):
        from .fabric import Invite
        if self.inv:
            self.inv.close()
        self.request_seen = None
        try:
            self.inv = Invite()
            self.inv_error = None
        except OSError as e:
            self.inv, self.inv_error = None, str(e)
        self.new_code.set_visible(False)
        if self.inv and have("qrencode"):
            f = Path(tempfile.gettempdir()) / f"xora-pair-{self.inv.digits}.png"
            subprocess.run(["qrencode", "-t", "PNG", "-s", "8", "-m", "1", "-o", str(f), f"xora-pair:{self.inv.code}"])
            from gi.repository import GdkPixbuf
            try:  # exactly 228 px, sharp pixels: GTK then sizes the card by it
                pb = GdkPixbuf.Pixbuf.new_from_file(str(f)).scale_simple(228, 228, GdkPixbuf.InterpType.NEAREST)
                self.qr.set_from_paintable(Gdk.Texture.new_for_pixbuf(pb))
            except GLib.Error:
                self.qr.set_from_file(str(f))
            f.unlink(missing_ok=True)
        if self.inv:
            self.qr_text.set_markup(f"On the other device open <b>XORA Center › Devices</b>,\npress <b>Link</b> next to "
                                    f"{GLib.markup_escape_text(self.inv.me['name'])} and enter\n"
                                    f"<span size='large' weight='heavy'>{self.inv.pretty}</span>\n"
                                    f"<small>or run: xora fabric join {self.inv.digits}</small>")
        else:
            self.qr_text.set_markup(f"Pairing isn't available right now: {GLib.markup_escape_text(self.inv_error or '')}")
        self.tick()

    def tick(self):
        if self.inv:
            r = self.inv.remaining()
            if self.inv.closed and not self.inv.peer:
                self.expiry.set_text("Too many wrong codes. Make a new one.")
                self.new_code.set_visible(True)
            elif not r and not self.inv.peer:
                self.expiry.set_text("Code expired")
                self.inv.close()
                self.new_code.set_visible(True)
            elif not self.inv.peer:
                self.expiry.set_text(f"Code expires in {r // 60}:{r % 60:02d}")
            if self.inv.peer and self.request_seen is not self.inv.peer:
                self.request_seen = self.inv.peer
                self.expiry.set_text(f"{self.inv.peer['name']} wants to link")
                self.render()
        return True

    def rediscover(self):
        from .fabric import discover
        self.searching.set_text("Searching…")
        bg(discover, self.found_done)
        return True

    def found_done(self, r):
        self.found = [] if isinstance(r, Exception) else r
        self.searching.set_text(f"{len(self.found)} found" if self.found else "No other XORA devices yet")
        self.render()

    # ---------------------------------------------------------------- rows
    def render(self):
        from .fabric import _devices
        devs = _devices()
        clear(self.rows)
        peer = self.inv.peer if self.inv and self.inv.peer and not self.inv.closed else None
        if peer:
            row = B(False, 10, "row", "selected")
            col = B(True, 1)
            col.append(L(f"{peer['name']} wants to link", "h-card"))
            col.append(L(f"{peer.get('cpus', '?')} cores · {peer['ip']} · it knew this device's code", "small", "muted"))
            col.set_hexpand(True)
            row.append(col)
            row.append(btn("Decline", self.decline, "btn", "small", "flat"))
            row.append(btn("Allow", self.allow, "btn", "small", "primary"))
            self.rows.append(row)
        for name, d in devs.items():
            row = B(False, 10, "row")
            if name == self.selected:
                row.add_css_class("selected")
            col = B(True, 1)
            col.append(L(name, "h-card"))
            mem = f"{d['mem_mb'] // 1024} GB · " if d.get("mem_mb") else ""
            col.append(L(f"{mem}{d.get('cpus') or '?'} cores · {d['host']}", "small", "muted"))
            col.set_hexpand(True)
            row.append(col)
            row.append(L("✓ Linked", "linked", "small"))
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, n=name: self.select(n))
            row.add_controller(click)
            self.rows.append(row)
        for f in self.found:
            if f["paired_as"]:
                continue
            row = B(False, 10, "row")
            col = B(True, 1)
            col.append(L(f["name"], "h-card"))
            col.append(L(f"XORA · {f['ip']}", "small", "muted"))
            col.set_hexpand(True)
            row.append(col)
            row.append(self.link_button(f))
            self.rows.append(row)
        row = B(False, 10, "row")
        col = B(True, 1)
        col.append(L("Add a server or VPS", "h-card"))
        col.append(L("Connect over the internet with a secure key", "small", "muted"))
        col.set_hexpand(True)
        row.append(col)
        row.append(btn("Add", self.add_server, "btn", "small"))
        self.rows.append(row)
        self.msg.set_text(self.message)
        if self.selected not in devs:
            self.selected = next(iter(devs), None)
            if self.selected:
                return self.render()
        self.render_caps(devs)

    def link_button(self, f):
        mb = Gtk.MenuButton(label="Link")
        mb.add_css_class("btn")
        mb.add_css_class("small")
        mb.add_css_class("primary")
        pop = Gtk.Popover()
        box = pad(B(True, 8), 12, 12, 12, 12)
        box.append(L(f"Enter the code shown on {f['name']}", "small"))
        e = Gtk.Entry(placeholder_text="123 456", max_length=7, width_chars=10)
        box.append(e)

        def go(*_):
            pop.popdown()
            self.message = f"Linking with {f['name']}…"
            self.msg.set_text(self.message)
            from .fabric import PAIR_PORT, join
            bg(join, self.joined, f["ip"], PAIR_PORT, e.get_text().replace(" ", ""), ["build", "run", "spaces"], f["name"])
        e.connect("activate", go)
        box.append(btn("Link", go, "btn", "small", "primary"))
        pop.set_child(box)
        mb.set_popover(pop)
        return mb

    def joined(self, r):
        self.message = f"Couldn't link: {r}" if isinstance(r, Exception) else f"Linked with {r}."
        if not isinstance(r, Exception):
            self.selected = r
        self.render()
        self.rediscover()

    def allow(self):
        caps = ["build", "run", "spaces"]
        try:
            name = self.inv.accept(caps)
            self.message = f"Linked with {name}. Choose below what it can do."
            self.selected = name
        except Exception as e:
            self.message = f"Couldn't link: {e}"
        self.start_invite()
        self.render()

    def decline(self):
        self.message = f"Declined {self.inv.peer['name']}."
        self.start_invite()
        self.render()

    def add_server(self):
        def ok(v):
            C.in_terminal(["fabric", "pair", v["name"], v["host"], "--can", "build,run"])
            self.message = f"Finish adding {v['name']} in the terminal (you'll type its password once)."
            self.render()
        ask_window(self.get_root(), "Add a server or VPS",
                   [("name", "Name", "contabo-vps"), ("host", "Login", "user@203.0.113.7")], ok)

    def select(self, name):
        self.selected = name
        self.render()

    # ---------------------------------------------------------------- capabilities
    def render_caps(self, devs):
        d = devs.get(self.selected)
        self._updating = True
        self.caps_grid.set_sensitive(bool(d))
        if d:
            self.caps_title.set_text(f"What can {self.selected} do?")
            can = set(d.get("can") or [])
            if "run" in can:              # the terminal's "run" and Center's "Run my builds" are one permission
                can.add("build")
            for key, cb in self.checks.items():
                cb.set_active(key in can)
            self.caps_note.set_text("Changes are saved straight away. Unlink with: xora fabric revoke " + self.selected)
        else:
            self.caps_title.set_text("What can a linked device do?")
            for cb in self.checks.values():
                cb.set_active(False)
            self.caps_note.set_text("Link a device to choose what it's allowed to do.")
        self._updating = False

    def cap_toggled(self, key):
        if self._updating or not self.selected:
            return
        from .fabric import _devices, set_caps
        d = _devices().get(self.selected)
        if not d:
            return
        can = set(d.get("can") or [])
        group = {"build": {"build", "run"}}.get(key, {key})
        can = can | group if self.checks[key].get_active() else can - group
        set_caps(self.selected, sorted(can))

    def stop(self):
        if self.inv:
            self.inv.close()


# ================================================================ Timeline (dark)

TONE = {"files": (0.36, 0.35, 0.47), "power": (0.96, 0.72, 0.18), "system": (0.65, 0.55, 0.98), "apps": (0.30, 0.78, 0.94)}


class TimelinePage(Gtk.ScrolledWindow):
    dark = True

    def __init__(self, app):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.app = app
        self.space = self.path = None
        self.kind = "all"
        self.evs = []
        self.sel = None
        self.prev = None
        root = pad(B(True, 0), 22, 40, 30, 40)
        self.set_child(root)

        top = B(False)
        tcol = B(True, 2)
        tcol.append(L("Timeline", "muted", "small"))
        self.title = L("", "h-big")
        tcol.append(self.title)
        top.append(tcol)
        top.append(spacer())
        seg = B(False, 2, "seg")
        seg.set_valign(Gtk.Align.CENTER)
        first = None
        for key, label in (("all", "All"), ("files", "Files"), ("apps", "Apps"), ("system", "System")):
            tb = Gtk.ToggleButton(label=label, active=key == "all")
            if first:
                tb.set_group(first)
            first = first or tb
            tb.connect("toggled", lambda b, k=key: b.get_active() and self.set_kind(k))
            seg.append(tb)
        top.append(seg)
        root.append(top)

        scrub = pad(B(True, 8, "card"), 22)
        self.area = Gtk.DrawingArea(content_height=80)
        self.area.set_draw_func(self.draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_scrub)
        self.area.add_controller(click)
        scrub.append(pad(self.area, 16, 22, 0, 22))
        legend = pad(B(False, 16), 0, 22, 14, 22)
        for name, tone in (("Snapshot", "files"), ("Power cut", "power"), ("OS update", "system"), ("App change", "apps")):
            item = B(False, 6)
            sw = Gtk.DrawingArea(content_width=10, content_height=10)
            sw.set_valign(Gtk.Align.CENTER)
            sw.set_draw_func(lambda a, cr, w, h, t=tone: (cr.set_source_rgb(*TONE[t]), cr.rectangle(0, 0, w, h), cr.fill()))
            item.append(sw)
            item.append(L(name, "small", "muted"))
            legend.append(item)
        legend.append(L("○ Selected", "small", "muted"))
        scrub.append(legend)
        root.append(scrub)

        cols = pad(B(False, 22), 22)
        cols.set_vexpand(True)
        root.append(cols)
        left = B(True, 0, "card")
        left.set_size_request(420, -1)
        lsw = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        lsw.set_min_content_height(420)
        self.list = pad(B(True, 4), 18, 16, 18, 16)
        lsw.set_child(self.list)
        left.append(lsw)
        cols.append(left)
        self.right = B(True, 0, "card")
        self.right.set_hexpand(True)
        self.pv = pad(B(True, 12), 22, 24, 22, 24)
        self.pv.set_vexpand(True)
        self.right.append(self.pv)
        cols.append(self.right)

    # ---------------------------------------------------------------- data
    def configure(self, space=None, path=None, select=None):
        self.space, self.path = space, path
        self.want = select

    def refresh(self):
        scope = self.space or (Path(self.path).name if self.path else None)
        if not scope:
            scope = "Everything"
        self.title.set_text(scope)
        kinds = ("files", "system", "apps") if self.kind == "all" else (self.kind,)
        bg(lambda: C.events(self.space, self.path, kinds), self.loaded)

    def set_kind(self, k):
        self.kind = k
        self.refresh()

    def loaded(self, evs):
        if isinstance(evs, Exception):
            evs = []
        self.evs = evs
        want = getattr(self, "want", None)
        self.want = None
        pick = None
        if want:
            pick = next((e for e in evs if e["kind"] == want["kind"] and e["at"] == want["at"]), None)
        if not pick and self.sel:
            pick = next((e for e in evs if e["kind"] == self.sel["kind"] and e["at"] == self.sel["at"]), None)
        self.select(pick or (evs[0] if evs else None))

    def select(self, e):
        self.sel = e
        self.render_list()
        self.area.queue_draw()
        self.render_preview()

    # ---------------------------------------------------------------- scrubber
    def span(self):
        now = time.time()
        start_today = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
        lo = start_today - 2 * 86400
        if self.sel and self.sel["at"] < lo:
            lo = dt.datetime.combine(dt.date.fromtimestamp(self.sel["at"]), dt.time()).timestamp()
        return lo, max(now, start_today + 86400 * 0.999)

    def xpos(self, ts, w):
        lo, hi = self.span()
        return 10 + (w - 20) * (ts - lo) / (hi - lo)

    def draw(self, area, cr, w, h):
        lo, hi = self.span()
        y = 50
        cr.set_source_rgb(0.23, 0.22, 0.32)
        cr.set_line_width(1.5)
        cr.move_to(10, y)
        cr.line_to(w - 10, y)
        cr.stroke()
        cr.select_font_face("Noto Sans")
        cr.set_font_size(12)
        d = dt.date.fromtimestamp(lo)
        days = []
        while dt.datetime.combine(d, dt.time()).timestamp() < hi:
            days.append(d)
            d += dt.timedelta(days=1)
        for i, d in enumerate(days):
            t = dt.datetime.combine(d, dt.time()).timestamp()
            label = "Today" if d == dt.date.today() else d.strftime("%a %-d")
            x = self.xpos(max(t, lo), w)
            ext = cr.text_extents(label)
            if i == len(days) - 1 and len(days) > 1:
                x = w - 10 - ext.width
            elif i:
                x -= ext.width / 2
            cr.set_source_rgb(0.92, 0.92, 0.96) if label == "Today" else cr.set_source_rgb(0.60, 0.60, 0.69)
            cr.move_to(max(10, x), 14)
            cr.show_text(label)
        for e in self.evs:
            if e["at"] < lo:
                continue
            x = self.xpos(e["at"], w)
            cr.set_source_rgb(*TONE.get(e["tone"], TONE["files"]))
            cr.set_line_width(3 if e["tone"] != "files" else 2)
            cr.move_to(x, y - 11)
            cr.line_to(x, y + 11)
            cr.stroke()
        if self.sel and self.sel["at"] >= lo:
            x = self.xpos(self.sel["at"], w)
            cr.set_source_rgb(0.93, 0.94, 0.98)
            cr.arc(x, y, 11, 0, 6.2832)
            cr.fill()

    def on_scrub(self, g, n, x, y):
        w = self.area.get_width()
        lo, _ = self.span()
        cands = [e for e in self.evs if e["at"] >= lo]
        if cands:
            self.select(min(cands, key=lambda e: abs(self.xpos(e["at"], w) - x)))

    # ---------------------------------------------------------------- list
    def render_list(self):
        clear(self.list)
        if not self.evs:
            self.list.append(L("Nothing to go back to yet.\n\nXORA saves a snapshot before anything is deleted with rm, "
                               "checkpoints open Spaces every 30 minutes, and keeps the previous system after each update.",
                               "muted", wrap=True))
            return
        day = None
        for e in self.evs[:200]:
            dl = C.day_label(e["at"])
            if dl != day:
                day = dl
                self.list.append(pad(L(dl, "cap"), 4 if day is None else 12, 0, 4, 8))
            row = B(False, 14, "tl-row")
            if e is self.sel:
                row.add_css_class("selected")
            row.append(L(time.strftime("%H:%M", time.localtime(e["at"])), "tl-time", "tone-" + e["tone"]))
            col = B(True, 1)
            col.set_hexpand(True)
            col.append(L(e["title"], "h-card"))
            sub = L(e["sub"], "small", "muted")
            sub.set_ellipsize(3)
            col.append(sub)
            row.append(col)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, e=e: self.select(e))
            row.add_controller(click)
            self.list.append(row)

    # ---------------------------------------------------------------- preview
    def header(self, title, note="Nothing changes until you confirm"):
        h = B(False)
        h.append(L(title, "h-sec"))
        h.append(spacer())
        h.append(L(note, "small", "muted"))
        self.pv.append(h)

    def render_preview(self):
        clear(self.pv)
        e = self.sel
        if not e:
            self.pv.append(L("Choose a moment on the left to see what restoring it would do.", "muted"))
            return
        stamp = (C.when(e["at"]) if C.when(e["at"]).startswith("today") else
                 time.strftime("%a %-d %b %H:%M", time.localtime(e["at"])))
        if e["kind"] == "system":
            d = e["entry"]
            self.header(f"System · {stamp}", "")
            self.pv.append(L(f"{e['title']}\n{d.get('image', '')}", "lead", wrap=True))
            if d["booted"]:
                self.pv.append(L("This is the version running now.", "good"))
            else:
                self.pv.append(L("Restarting into this version swaps back to it. The version you have now is kept, so you can "
                                 "switch again.", "muted", wrap=True))
                self.pv.append(spacer(False))
                row = B(False, 10)
                row.append(spacer())
                row.append(btn("Roll back to this version", lambda: C.in_terminal(["timeline", "system", "--rollback"]),
                               "btn", "primary"))
                self.pv.append(row)
            return
        if e["kind"] == "apps":
            a = e["entry"]
            self.header(f"App change · {stamp}", "")
            self.pv.append(L(f"{a['app']} — {a['change']}\n{a['when']}", "lead", wrap=True))
            self.pv.append(L("Shown so you can see what changed. To go back to an earlier app version use "
                             "flatpak's own history (flatpak remote-info --log).", "muted", wrap=True))
            return
        self.header(f"Restore preview · {stamp}")
        self.pv.append(L("Comparing with now…", "muted"))
        ent = e["entry"]
        from . import timeline as tl
        bg(tl.preview, lambda p, e=e: self.sel is e and self.show_preview(e, p), ent)

    def show_preview(self, e, p):
        clear(self.pv)
        ent = e["entry"]
        stamp = time.strftime("%H:%M", time.localtime(e["at"]))
        self.header(f"Restore preview · {C.when(e['at']) if C.when(e['at']).startswith('today') else time.strftime('%a %-d %b %H:%M', time.localtime(e['at']))}")
        if isinstance(p, Exception) or p.get("error"):
            self.pv.append(L(f"Can't preview this snapshot: {p if isinstance(p, Exception) else p['error']}", "bad", wrap=True))
            return
        name = Path(ent["path"]).name
        boxes = B(False, 14)
        boxes.set_homogeneous(True)
        rest = pad(B(True, 6, "sub"), 0)
        ri = pad(B(True, 6), 14, 14, 14, 14)
        rest.append(ri)
        ri.append(L("Will be restored", "h-card", "small"))
        nch, nmi = len(p["changed"]), len(p["missing"])
        if nch:
            ri.append(L(f"✓ {nch} changed file{'s' if nch != 1 else ''} go back to how they were", "small", wrap=True))
        if nmi:
            ri.append(L(f"✓ {nmi} deleted file{'s' if nmi != 1 else ''} come back", "small"))
        if not nch and not nmi:
            ri.append(L(f"Nothing: {name} is the same as it was at {stamp}", "small", "muted", wrap=True))
        whole = self.is_space_root(ent)
        if whole and (nch or nmi):
            ri.append(L(f"✓ The whole {ent['space']} project folder", "small", wrap=True))
        boxes.append(rest)
        keep = B(True, 6, "keep")
        ki = pad(B(True, 6), 14, 14, 14, 14)
        keep.append(ki)
        ki.append(L("Kept as they are now", "keep-title", "small"))
        if p["extra"]:
            n = len(p["extra"])
            ki.append(L(f"{n}{'+' if n >= 200 else ''} newer file{'s' if n != 1 else ''} you made after {stamp}", "small"))
        if p["git"]:
            ki.append(L("Your Git commits", "small"))
        ki.append(L(f"Files outside {name}", "small"))
        ki.append(L("What you have now is saved first, so this restore can be undone", "small", wrap=True))
        boxes.append(keep)
        self.pv.append(boxes)

        items = [("changed", c) for c in p["changed"]] + [("missing", m) for m in p["missing"]]
        self.file_rows = items
        if items:
            self.pv.append(pad(L("Changed files", "h-card", "small"), 6))
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            lb.add_css_class("files")
            self.lb = lb
            self.show_all = getattr(self, "show_all", False) and self.show_all == ent["id"]
            shown = items if self.show_all else items[:6]
            for kind, it in shown:
                r = B(False, 10, "file-row")
                r.append(L(it["path"], "mono"))
                r.append(spacer())
                if kind == "missing":
                    r.append(L("deleted", "mono", "plus"))
                elif it.get("plus") is not None:
                    r.append(L(f"+{it['plus']}", "mono", "plus"))
                    r.append(L(f"−{it['minus']}", "mono", "minus"))
                else:
                    r.append(L("binary", "mono", "muted"))
                lb.append(r)
            if len(items) > 6 and not self.show_all:
                r = B(False, 10, "file-row")
                r.append(L(f"and {len(items) - 6} more", "mono", "muted"))
                r.append(spacer())
                sa = btn("Show all", lambda: (setattr(self, "show_all", ent["id"]), self.show_preview(e, p)), "btn", "small", "flat")
                r.append(sa)
                lb.append(r)
            lb.connect("row-activated", lambda _lb, row: self.compare(e, row.get_index()))
            self.pv.append(lb)

        self.pv.append(spacer(False))
        self.result = L("", "small", "good", wrap=True)
        self.pv.append(self.result)
        row = B(False, 10)
        row.append(spacer())
        cmp_btn = btn("Compare", lambda: self.compare(e, None), "btn")
        cmp_btn.set_sensitive(bool(p["changed"]))
        row.append(cmp_btn)
        row.append(btn("Restore as a copy", lambda: self.restore(e, copy=True), "btn"))
        r = btn("Restore Space" if whole else "Restore", lambda: self.restore(e, copy=False), "btn", "primary")
        r.set_sensitive(bool(items))
        row.append(r)
        self.pv.append(row)

    @staticmethod
    def is_space_root(ent):
        if not ent.get("space"):
            return False
        from .spaces import load_yaml, path_of, project_dir
        m = load_yaml(path_of(ent["space"])) or {}
        return str(project_dir({"space": ent["space"], **m})) == ent["path"]

    def compare(self, e, idx):
        from . import timeline as tl
        rows = self.file_rows
        if idx is None:
            row = self.lb.get_selected_row() if hasattr(self, "lb") else None
            idx = row.get_index() if row else 0
        if idx >= len(rows):
            return
        kind, it = rows[idx]
        if kind == "missing":
            text_window(self.get_root(), it["path"], f"{it['path']} was deleted after this snapshot. Restoring brings it back.")
            return
        text_window(self.get_root(), f"{it['path']}: now → {time.strftime('%H:%M', time.localtime(e['at']))}",
                    tl.diff(e["entry"], it["path"]) or "No differences.")

    def restore(self, e, copy):
        from . import timeline as tl
        ent = e["entry"]
        self.result.set_text("Restoring…")

        def work():
            if copy:
                dest = tl.restore(ent, Path(ent["path"]).with_name(Path(ent["path"]).name + f".restored-{ent['id']}"))
                return f"Restored a copy to {tilde(dest)}. Nothing else was changed."
            backup, n, kept = tl.restore_merge(ent)
            return (f"Restored {n} file{'s' if n != 1 else ''}; kept {kept} newer. "
                    + (f"Your state from just before is in the Timeline ({backup['id']})." if backup else ""))

        def done(r):
            self.refresh()
            GLib.timeout_add(400, lambda: (hasattr(self, "result") and self.result.set_text(
                f"Couldn't restore: {r}" if isinstance(r, Exception) else r)) and False)
        bg(work, done)


# ================================================================ first-boot setup (dark)

class SetupPage(Gtk.Stack):
    dark = True
    STEPS = 4

    def __init__(self, app):
        super().__init__(transition_type=Gtk.StackTransitionType.SLIDE_LEFT)
        self.app = app
        self.step = 1
        self.add_named(self.welcome(), "1")
        self.add_named(self.updates(), "2")
        self.pair = PairPage(app, setup=self)
        self.add_named(self.pair, "3")
        self.add_named(self.first_space(), "4")

    def step_bars(self, n):
        box = B(False, 6)
        for i in range(1, self.STEPS + 1):
            b = B(False, 0, "step-bar")
            if i <= n:
                b.add_css_class("on")
            b.set_valign(Gtk.Align.CENTER)
            box.append(b)
        box.append(pad(L(f"Step {n} of {self.STEPS}", "small", "muted"), 0, 0, 0, 8))
        return box

    def frame(self, n, title, lead):
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        root = pad(B(True, 0), 34, 120, 30, 120)
        sw.set_child(root)
        top = B(False, 10)
        top.append(logo(True, 130, 36))
        top.append(L("setup", "muted"))
        top.append(spacer())
        top.append(self.step_bars(n))
        root.append(top)
        root.append(pad(L(title, "h-big"), 34))
        ld = L(lead, "lead", "muted", wrap=True)
        ld.set_max_width_chars(80)
        root.append(pad(ld, 10, 0, 28))
        body = B(True, 14)
        body.set_vexpand(True)
        root.append(body)
        bot = pad(B(False, 10), 30)
        root.append(bot)
        return sw, body, bot

    def welcome(self):
        sw, body, bot = self.frame(1, "Welcome to XORA", "Your devices. Your projects. One connected workspace.")
        for t, s in (("Spaces", "A whole project — code, tools, databases, terminals and windows — comes back with one click."),
                     ("Timeline", "Everything you delete or change can be brought back. Restoring never deletes newer work."),
                     ("Fabric", "Your other computers lend their power and keep copies of your work."),
                     ("Explain", "When something is slow or fails, XORA tells you why, in plain words, from real measurements.")):
            row = B(True, 2, "row")
            row.append(L(t, "h-card"))
            row.append(L(s, "small", "muted", wrap=True))
            body.append(row)
        bot.append(spacer())
        bot.append(btn("Start", self.next, "btn", "primary"))
        return sw

    def updates(self):
        sw, body, bot = self.frame(2, "Updates and data",
                                   "XORA updates the whole system at once and keeps the previous version, so an update can always be undone.")
        self.night = Gtk.CheckButton(label="Install updates at night (around 2 am)", active=True)
        self.off = Gtk.CheckButton(label="Only when I say (xora data --updates now)", group=self.night)
        self.metered = Gtk.CheckButton(label="This internet connection is expensive (metered): updates and big downloads wait")
        for w in (self.night, self.off):
            body.append(pad(w, 0, 0, 0, 4))
        body.append(pad(self.metered, 14, 0, 0, 4))
        body.append(L("You can change these any time with xora data.", "small", "muted"))
        bot.append(btn("Back", self.back, "btn", "flat"))
        bot.append(spacer())
        bot.append(btn("Continue", self.apply_updates, "btn", "primary"))
        return sw

    def apply_updates(self):
        if self.metered.get_active():
            bg(lambda: C.run_xora("data", "--metered", "on"))
        if self.off.get_active():
            C.in_terminal(["data", "--updates", "off"])  # needs the admin password once
        self.next()

    def first_space(self):
        sw, body, bot = self.frame(4, "Make your first Space",
                                   "Pick a project folder. XORA looks at it — Git, languages, docker-compose services — and "
                                   "remembers how to bring the whole project back.")
        b = btn("Choose a project folder", lambda: self.app.pages["home"].new_space(), "btn")
        b.set_halign(Gtk.Align.START)
        body.append(b)
        body.append(L("You can also right-click any folder in Files and choose “Make this folder a Space”.", "small", "muted"))
        bot.append(btn("Back", self.back, "btn", "flat"))
        bot.append(spacer())
        bot.append(btn("Finish", self.finish, "btn", "primary"))
        return sw

    def refresh(self):
        if self.step == 3:
            self.pair.refresh()

    def next(self):
        if self.step < self.STEPS:
            self.step += 1
            self.set_visible_child_name(str(self.step))
            self.refresh()

    def back(self):
        if self.step > 1:
            self.step -= 1
            self.set_visible_child_name(str(self.step))
            self.refresh()

    def finish(self):
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "welcomed").write_text(time.strftime("%F %T"))
        self.pair.stop()
        self.app.end_setup()


# ================================================================ window

class Center(Gtk.Application):
    def __init__(self, a):
        super().__init__(application_id="org.xora.Center", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.a = a
        self.pages = {}

    def do_activate(self):
        prov = Gtk.CssProvider()
        prov.load_from_path(str(CSS))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.win = Gtk.ApplicationWindow(application=self, title="XORA Center", default_width=1400, default_height=900)
        self.win.add_css_class("xora")
        self.win.set_icon_name("xora-logo")
        hb = Gtk.HeaderBar()
        self.nav = B(False, 2, "nav")
        self.navb = {}
        first = None
        for key, label in (("home", "Home"), ("pair", "Devices"), ("timeline", "Timeline")):
            tb = Gtk.ToggleButton(label=label)
            if first:
                tb.set_group(first)
            first = first or tb
            tb.connect("toggled", lambda b, k=key: b.get_active() and self.show(k))
            self.nav.append(tb)
            self.navb[key] = tb
        hb.set_title_widget(self.nav)
        self.win.set_titlebar(hb)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pages = {"home": HomePage(self), "pair": PairPage(self), "timeline": TimelinePage(self)}
        for k, p in self.pages.items():
            self.stack.add_named(p, k)
        if self.a.setup:
            self.setup = SetupPage(self)
            self.stack.add_named(self.setup, "setup")
        self.pages["timeline"].configure(self.a.space, self.a.path)
        self.win.set_child(self.stack)
        self.win.connect("close-request", lambda *_: (self.pages["pair"].stop(), self.a.setup and self.setup.pair.stop()) and False)
        if self.a.setup:
            self.nav.set_visible(False)
            self._theme(True)
            self.stack.set_visible_child_name("setup")
        else:
            page = "pair" if self.a.page in ("pair", "devices") else self.a.page
            self.show(page)
        self.win.maximize()
        self.win.present()

    def _theme(self, dark):
        self.win.remove_css_class("light" if dark else "dark")
        self.win.add_css_class("dark" if dark else "light")
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", dark)

    def show(self, key, select=None, path=None):
        if getattr(self, "_switching", False):
            return
        page = self.pages[key]
        if key == "timeline" and (select or path):
            page.configure(None, path, select)
        if key != "pair" and self.pages["pair"].inv:
            self.pages["pair"].stop()          # stop listening for pairing when the page isn't open
            self.pages["pair"].inv = None
        self._theme(page.dark)
        self.stack.set_visible_child_name(key)
        self._switching = True
        self.navb[key].set_active(True)
        self._switching = False
        page.refresh()

    def end_setup(self):
        self.nav.set_visible(True)
        self.show("home")


def run(a):
    app = Center(a)
    return app.run([])
