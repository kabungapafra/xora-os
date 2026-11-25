/* XORA window manager */
(function () {
  const X = window.XORA;
  const apps = {};          // id -> {name, icon, open(body, win, args), w, h, single}
  const wins = [];          // open windows
  let z = 10, offset = 0;

  X.registerApp = (id, def) => { apps[id] = Object.assign({ id, w: 760, h: 480 }, def); };
  X.apps = apps;
  X.windows = wins;

  X.openApp = function (id, args) {
    const app = apps[id];
    if (!app) return null;
    if (app.single) {
      const w = wins.find(w => w.app === id);
      if (w) { w.el.classList.remove('min'); focus(w); w.onArgs && w.onArgs(args); return w; }
    }
    const host = document.getElementById('windows');
    const el = document.createElement('div');
    el.className = 'win';
    const W = Math.min(app.w, innerWidth - 40), H = Math.min(app.h, innerHeight - 140);
    el.style.width = W + 'px';
    el.style.height = H + 'px';
    el.style.left = Math.max(10, (innerWidth - W) / 2 + offset) + 'px';
    el.style.top = Math.max(46, (innerHeight - H) / 2 - 30 + offset) + 'px';
    offset = (offset + 28) % 140;
    el.innerHTML = `<div class="win-title"><div class="win-ctrl"><button class="c" title="Close"></button><button class="m" title="Minimise"></button><button class="x" title="Maximise"></button></div><div class="t"></div><div style="width:53px"></div></div><div class="win-body"></div><div class="win-resize"></div>`;
    el.querySelector('.t').textContent = app.name;
    host.appendChild(el);
    const win = { id: 'w' + Date.now() + Math.random(), app: id, el, body: el.querySelector('.win-body'),
      setTitle(t) { el.querySelector('.t').textContent = t; }, close() { close(win); } };
    wins.push(win);

    el.addEventListener('mousedown', () => focus(win), true);
    el.querySelector('.c').onclick = () => close(win);
    el.querySelector('.m').onclick = () => { el.classList.add('min'); X.emit('wm'); };
    el.querySelector('.x').onclick = () => el.classList.toggle('max');
    el.querySelector('.win-title').ondblclick = e => { if (!e.target.closest('button')) el.classList.toggle('max'); };
    drag(el, el.querySelector('.win-title'));
    resize(el, el.querySelector('.win-resize'));

    focus(win);
    app.open(win.body, win, args);
    X.emit('wm');
    return win;
  };

  function focus(win) {
    wins.forEach(w => w.el.classList.toggle('inactive', w !== win));
    win.el.style.zIndex = ++z;
    X.focused = win;
    win.onFocus && win.onFocus();
  }
  function close(win) {
    win.onClose && win.onClose();
    win.el.remove();
    wins.splice(wins.indexOf(win), 1);
    X.emit('wm');
  }
  X.toggleApp = function (id) {
    const open = wins.filter(w => w.app === id);
    if (!open.length) return X.openApp(id);
    const w = open[open.length - 1];
    if (w.el.classList.contains('min')) { w.el.classList.remove('min'); focus(w); }
    else if (X.focused === w) w.el.classList.add('min');
    else focus(w);
    X.emit('wm');
  };

  function drag(el, handle) {
    handle.addEventListener('mousedown', e => {
      if (e.target.closest('button') || e.button !== 0) return;
      if (el.classList.contains('max')) return;
      const sx = e.clientX - el.offsetLeft, sy = e.clientY - el.offsetTop;
      const mv = ev => {
        el.style.left = Math.min(innerWidth - 80, Math.max(-el.offsetWidth + 80, ev.clientX - sx)) + 'px';
        el.style.top = Math.min(innerHeight - 60, Math.max(36, ev.clientY - sy)) + 'px';
      };
      const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
      e.preventDefault();
    });
  }
  function resize(el, handle) {
    handle.addEventListener('mousedown', e => {
      const sx = e.clientX, sy = e.clientY, w = el.offsetWidth, h = el.offsetHeight;
      const mv = ev => { el.style.width = Math.max(340, w + ev.clientX - sx) + 'px'; el.style.height = Math.max(220, h + ev.clientY - sy) + 'px'; };
      const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
      e.preventDefault(); e.stopPropagation();
    });
  }
})();
