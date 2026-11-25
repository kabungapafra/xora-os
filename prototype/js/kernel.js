/* XORA kernel: state, virtual file system, Spaces, Timeline, Fabric, event bus. */
(function () {
  const KEY = 'xora.state.v1';
  const listeners = {};

  const X = window.XORA = {
    on(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); },
    emit(ev, data) { (listeners[ev] || []).forEach(fn => fn(data)); },
  };

  /* ---------- Logo ---------- */
  const L = window.XORA_LOGO;
  let gid = 0;
  X.logoSVG = function (kind = 'mark', oraColor = '#fff') {
    const id = 'xg' + (gid++);
    const grad = `<defs><linearGradient id="${id}" x1="157" y1="330" x2="752" y2="779" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#1ED4F2"/><stop offset="1" stop-color="#0A7CF0"/></linearGradient></defs>`;
    const mark = `<path d="${L.mark}" fill="url(#${id})"/>`;
    if (kind === 'mark') return `<svg class="logo" viewBox="150 325 610 460" preserveAspectRatio="xMidYMid meet">${grad}${mark}</svg>`;
    const ora = L.ora.map(p => `<path d="${p}" fill="${oraColor}"/>`).join('');
    return `<svg class="logo" viewBox="150 325 1145 460" preserveAspectRatio="xMinYMid meet">${grad}${mark}${ora}</svg>`;
  };
  X.paintLogos = function (root = document) {
    root.querySelectorAll('[data-logo]').forEach(el => {
      if (el.dataset.painted) return;
      el.innerHTML = X.logoSVG(el.dataset.logo, el.dataset.ora || '#fff');
      el.dataset.painted = 1;
    });
  };

  /* ---------- Default state ---------- */
  function file(content) { return { t: 'f', c: content, m: Date.now() }; }
  function dir(children = {}, bulk = 0) { return { t: 'd', k: children, bulk, m: Date.now() }; }

  function seedHome() {
    const build = {};
    ['app.js', 'app.js.map', 'index.html', 'styles.css', 'vendor.js', 'manifest.json'].forEach(n => build[n] = file('// build artefact'));
    build.assets = dir({ 'logo.png': file('[binary]'), 'fonts': dir({}, 312) }, 540);
    build.cache = dir({}, 425);
    return dir({
      attndi: dir({
        backend: dir({
          'README.md': file('# Attndi backend\n\nFastAPI service for attendance tracking.\n\nRun locally:\n    xora up\n    pytest\n'),
          'requirements.txt': file('fastapi==0.115\nuvicorn==0.32\nsqlalchemy==2.0\npsycopg==3.2\npytest==8.3\n'),
          '.git': dir({ HEAD: file('ref: refs/heads/feature/checkin\n') }),
          app: dir({
            'main.py': file('from fastapi import FastAPI\nfrom .routes import checkin\n\napp = FastAPI(title="Attndi")\napp.include_router(checkin.router)\n'),
            'db.py': file('import os\nDATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/attndi")\n'),
            routes: dir({ 'checkin.py': file('from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.post("/checkin")\ndef checkin(user_id: int):\n    return {"ok": True, "user": user_id}\n') }),
          }),
          tests: dir({
            'test_checkin.py': file('def test_checkin(client):\n    r = client.post("/checkin", params={"user_id": 1})\n    assert r.json()["ok"]\n'),
            'conftest.py': file('TEST_DB = "postgresql://localhost/attndi_test"\n'),
          }),
          build: dir(build),
        }),
        mobile: dir({
          'pubspec.yaml': file('name: attndi\nversion: 1.4.0\n'),
          lib: dir({ 'main.dart': file("import 'package:flutter/material.dart';\n\nvoid main() => runApp(const AttndiApp());\n") }),
        }),
      }),
      safepick: dir({ 'notes.md': file('# SafePick\n\n- driver verification flow\n- parent notifications\n') }),
      Documents: dir({ 'welcome.txt': file('Welcome to XORA OS.\n\nOpen the Terminal and type `help` to see what it can do.\nStart a line with # to ask a question in plain words.\n') }),
      Downloads: dir({}),
      Pictures: dir({ 'xora-mark.svg': file('[image]') }),
    });
  }

  function defaults() {
    return {
      setupDone: false,
      user: { name: 'Pafra', login: 'pafra' },
      accent: '#1EC8F0',
      termFrame: '#2FD15A',
      termUser: '#3D7EFF',
      glow: true,
      host: 'xora',
      fs: { t: 'd', k: { home: dir({}), etc: dir({ 'os-release': file('NAME="XORA OS"\nVERSION="0.1 (Dawn)"\nID=xora\nID_LIKE=debian\n') }), tmp: dir({}) } },
      spaces: [
        { id: 'backend', name: 'attndi · backend', dir: '~/attndi/backend', branch: 'feature/checkin', lang: 'py 3.12',
          services: [{ n: 'db', s: 'running' }, { n: 'api', s: 'running' }, { n: 'worker', s: 'stopped' }],
          saved: ['pytest -q', 'xora up', 'git status'] },
        { id: 'mobile', name: 'attndi · mobile', dir: '~/attndi/mobile', branch: 'main', lang: 'flutter 3.24',
          services: [{ n: 'emulator', s: 'stopped' }],
          saved: ['flutter build apk', 'xora fabric run flutter build apk --on office-pc'] },
        { id: 'safepick', name: 'safepick', dir: '~/safepick', branch: 'main', lang: '',
          services: [], saved: ['cat notes.md'] },
      ],
      activeSpace: 'backend',
      devices: [
        { id: 'laptop', name: 'This laptop', kind: '💻', online: true, cpu: 22, here: true },
        { id: 'office-pc', name: 'Office PC', kind: '🖥️', online: true, cpu: 8 },
        { id: 'phone', name: 'Pixel 8', kind: '📱', online: false, cpu: 0 },
      ],
      timeline: [],
      jobs: [],
    };
  }

  /* ---------- Persistence ---------- */
  let S;
  try { S = JSON.parse(localStorage.getItem(KEY)); } catch (e) { S = null; }
  if (!S) S = defaults();
  X.state = S;
  let saveT;
  X.save = function () { clearTimeout(saveT); saveT = setTimeout(() => localStorage.setItem(KEY, JSON.stringify(S)), 120); };
  X.reset = function () { localStorage.removeItem(KEY); location.reload(); };

  X.finishSetup = function ({ name, login, accent, space }) {
    S.user = { name, login };
    S.accent = accent;
    S.fs.k.home.k[login] = seedHome();
    if (space && space !== S.spaces[0].name) S.spaces[0].name = space;
    S.setupDone = true;
    X.save();
  };

  /* ---------- VFS ---------- */
  X.home = () => '/home/' + S.user.login;
  X.resolve = function (path, cwd) {
    if (!path) return cwd;
    if (path === '~' || path.startsWith('~/')) path = X.home() + path.slice(1);
    const parts = (path.startsWith('/') ? path : cwd + '/' + path).split('/');
    const out = [];
    for (const p of parts) {
      if (!p || p === '.') continue;
      if (p === '..') out.pop(); else out.push(p);
    }
    return '/' + out.join('/');
  };
  X.pretty = p => p === X.home() ? '~' : p.startsWith(X.home() + '/') ? '~' + p.slice(X.home().length) : p;
  X.node = function (abs) {
    let n = S.fs;
    for (const p of abs.split('/').filter(Boolean)) {
      if (!n || n.t !== 'd' || !n.k[p]) return null;
      n = n.k[p];
    }
    return n;
  };
  X.parent = function (abs) {
    const i = abs.lastIndexOf('/');
    return { dir: X.node(abs.slice(0, i) || '/'), name: abs.slice(i + 1) };
  };
  X.count = function (n) {
    if (!n) return 0;
    if (n.t === 'f') return 1;
    return Object.values(n.k).reduce((a, c) => a + X.count(c), n.bulk || 0);
  };
  X.write = function (abs, content, append) {
    const { dir: d, name } = X.parent(abs);
    if (!d || d.t !== 'd') throw new Error('No such file or directory');
    const cur = d.k[name];
    if (cur && cur.t === 'd') throw new Error('Is a directory');
    d.k[name] = file((append && cur ? cur.c : '') + content);
    X.save(); X.emit('fs');
  };
  X.mkdir = function (abs, parents) {
    const parts = abs.split('/').filter(Boolean);
    let n = S.fs;
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (!n.k[p]) {
        if (!parents && i < parts.length - 1) throw new Error('No such file or directory');
        n.k[p] = dir();
      } else if (n.k[p].t !== 'd') throw new Error('Not a directory');
      else if (!parents && i === parts.length - 1) throw new Error('File exists');
      n = n.k[p];
    }
    X.save(); X.emit('fs');
  };

  /* ---------- Timeline: snapshot before destructive actions ---------- */
  X.snapshot = function (abs, reason) {
    const n = X.node(abs);
    if (!n) return null;
    const snap = { id: 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), path: abs, reason,
      count: X.count(n), node: JSON.parse(JSON.stringify(n)), at: Date.now(), restored: false, space: S.activeSpace };
    S.timeline.unshift(snap);
    S.timeline = S.timeline.slice(0, 50);
    X.save(); X.emit('timeline');
    return snap;
  };
  X.remove = function (abs, reason) {
    const { dir: d, name } = X.parent(abs);
    if (!d || !d.k[name]) throw new Error('No such file or directory');
    const snap = X.snapshot(abs, reason);
    delete d.k[name];
    X.save(); X.emit('fs');
    return snap;
  };
  X.restore = function (id) {
    const snap = id ? S.timeline.find(s => s.id === id) : S.timeline.find(s => !s.restored);
    if (!snap) throw new Error('nothing to undo');
    const { dir: d, name } = X.parent(snap.path);
    if (!d) throw new Error('parent folder is gone: ' + X.pretty(snap.path));
    d.k[name] = JSON.parse(JSON.stringify(snap.node));
    snap.restored = true;
    X.save(); X.emit('fs'); X.emit('timeline');
    return snap;
  };

  /* ---------- Spaces ---------- */
  X.space = (id = S.activeSpace) => S.spaces.find(s => s.id === id) || S.spaces[0];
  X.setSpace = function (id) { S.activeSpace = id; X.save(); X.emit('space', id); };
  X.setService = function (spaceId, n, s) {
    const svc = X.space(spaceId).services.find(x => x.n === n);
    if (!svc) return false;
    svc.s = s; X.save(); X.emit('services'); return true;
  };

  /* ---------- Fabric jobs ---------- */
  X.device = id => S.devices.find(d => d.id === id);
  X.startJob = function (cmd, deviceId, onTick) {
    const job = { id: 'j' + Date.now().toString(36), cmd, device: deviceId, progress: 0, state: 'running', at: Date.now() };
    S.jobs.unshift(job); S.jobs = S.jobs.slice(0, 20);
    const dev = X.device(deviceId); if (dev) dev.cpu = 87;
    X.emit('jobs');
    const iv = setInterval(() => {
      if (job.state !== 'running') { clearInterval(iv); return; }
      job.progress = Math.min(100, job.progress + 4 + Math.random() * 9);
      if (job.progress >= 100) { job.state = 'done'; if (dev) dev.cpu = 8; clearInterval(iv); }
      X.save(); X.emit('jobs'); onTick && onTick(job);
    }, 450);
    return job;
  };
  X.bringBack = function (jobId) {
    const job = S.jobs.find(j => j.id === jobId);
    if (!job) return null;
    const old = X.device(job.device); if (old && !old.here) old.cpu = 8;
    job.device = 'laptop'; X.save(); X.emit('jobs'); return job;
  };

  /* ---------- Theme ---------- */
  X.applyTheme = function () {
    const r = document.documentElement.style;
    r.setProperty('--accent', S.accent);
    r.setProperty('--k-frame', S.termFrame);
    r.setProperty('--k-user', S.termUser);
    document.body.classList.toggle('no-glow', !S.glow);
  };

  /* ---------- Toasts ---------- */
  X.toast = function (title, msg, ms = 3800) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.innerHTML = `<b></b><span></span>`;
    t.querySelector('b').textContent = title;
    t.querySelector('span').textContent = msg || '';
    document.getElementById('toasts').appendChild(t);
    setTimeout(() => t.remove(), ms);
  };

  X.esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  X.ago = function (t) {
    const s = Math.round((Date.now() - t) / 1000);
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' h ago';
    return new Date(t).toLocaleDateString();
  };
})();
