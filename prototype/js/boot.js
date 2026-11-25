/* XORA boot, first-boot setup and desktop shell */
(function () {
  const X = window.XORA, S = X.state, esc = X.esc;
  const $ = id => document.getElementById(id);

  X.applyTheme();
  X.paintLogos();

  /* ---------- Boot ---------- */
  const steps = ['Starting XORA kernel 6.12.0-xora', 'Mounting your files', 'Restoring Timeline', 'Connecting Fabric devices', 'Waking up Spaces', 'Ready'];
  let i = 0;
  const bar = document.querySelector('.boot-bar span');
  const fast = new URLSearchParams(location.search).has('fast');
  const tick = setInterval(() => {
    $('bootLog').textContent = steps[i];
    bar.style.width = ((i + 1) / steps.length * 100) + '%';
    if (++i >= steps.length) { clearInterval(tick); setTimeout(endBoot, fast ? 0 : 350); }
  }, fast ? 10 : 380);

  function endBoot() {
    $('boot').classList.add('fade');
    setTimeout(() => { $('boot').classList.add('hidden'); S.setupDone ? startDesktop() : startSetup(); }, fast ? 0 : 600);
  }

  /* ---------- Setup ---------- */
  function startSetup() {
    $('setup').classList.remove('hidden');
    let step = 0, accent = S.accent;
    const sw = $('setupSwatches');
    sw.innerHTML = X.ACCENTS.map(c => `<button class="swatch ${c === accent ? 'on' : ''}" style="background:${c}" data-c="${c}"></button>`).join('');
    sw.onclick = e => {
      const c = e.target.dataset.c; if (!c) return;
      accent = c; S.accent = c; X.applyTheme();
      sw.querySelectorAll('.swatch').forEach(s => s.classList.toggle('on', s.dataset.c === c));
    };
    const show = n => {
      document.querySelectorAll('.setup-step').forEach(s => s.classList.toggle('hidden', +s.dataset.step !== n));
      document.querySelectorAll('.setup-dots i').forEach((d, j) => d.classList.toggle('on', j === n));
      const inp = document.querySelector(`.setup-step[data-step="${n}"] input`); inp && inp.focus();
    };
    $('setupName').oninput = e => { $('setupUser').placeholder = (e.target.value || 'pafra').toLowerCase().replace(/[^a-z0-9]/g, '') || 'pafra'; };
    document.querySelectorAll('[data-next]').forEach(b => b.onclick = () => show(++step));
    document.querySelector('[data-finish]').onclick = finish;
    $('setup').addEventListener('keydown', e => { if (e.key === 'Enter') step < 2 ? show(++step) : finish(); });
    show(0);
    function finish() {
      const name = $('setupName').value.trim() || 'Pafra';
      const login = ($('setupUser').value.trim() || $('setupUser').placeholder).toLowerCase().replace(/[^a-z0-9_-]/g, '') || 'pafra';
      X.finishSetup({ name, login, accent, space: $('setupSpace').value.trim() });
      $('setup').classList.add('hidden');
      startDesktop(true);
    }
  }

  /* ---------- Desktop ---------- */
  function startDesktop(first) {
    $('desktop').classList.remove('hidden');
    X.paintLogos();
    renderSpaces(); renderDock(); renderFabric(); clock();
    setInterval(clock, 10000);
    X.on('space', renderSpaces);
    X.on('wm', renderDock);
    X.on('jobs', renderFabric);
    $('tbLaunch').onclick = openLauncher;
    $('tbFabric').onclick = () => X.openApp('fabric');
    addEventListener('keydown', e => {
      if ((e.key === ' ' && (e.ctrlKey || e.metaKey)) || (e.key === 'Meta' && !e.repeat)) { e.preventDefault(); toggleLauncher(); }
      if (e.key === 'Escape') closeLauncher();
      if (e.ctrlKey && e.altKey && e.key.toLowerCase() === 't') { e.preventDefault(); X.openApp('terminal'); }
    });
    if (first) {
      X.openApp('home');
      setTimeout(() => X.toast(`Welcome, ${S.user.name}`, 'Press Ctrl+Alt+T for the Terminal, or Ctrl+Space to search.', 6000), 400);
    } else X.openApp('terminal');
  }

  function renderSpaces() {
    $('tbSpaces').innerHTML = S.spaces.map(s => `<button class="tb-space ${s.id === S.activeSpace ? 'on' : ''}" data-s="${s.id}">${esc(s.name)}</button>`).join('');
    $('tbSpaces').querySelectorAll('[data-s]').forEach(b => b.onclick = () => X.setSpace(b.dataset.s));
  }
  function renderFabric() {
    const on = S.devices.filter(d => d.online).length;
    const run = S.jobs.filter(j => j.state === 'running').length;
    $('tbFabric').innerHTML = `<b>●</b> ${on} devices${run ? ` · ${run} job` : ''}`;
  }
  function clock() {
    const d = new Date();
    $('tbClock').textContent = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) + '  ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  const DOCK = ['home', 'terminal', 'files', 'timeline', 'fabric', 'settings'];
  function renderDock() {
    const dock = $('dock');
    dock.innerHTML = `<button class="dock-btn launch" data-launch><span class="tip">Launcher</span><div style="width:100%;height:100%" data-logo="mark"></div></button><div class="dock-sep"></div>` +
      DOCK.map(id => `<button class="dock-btn ${X.windows.some(w => w.app === id) ? 'running' : ''}" data-app="${id}"><span class="tip">${X.apps[id].name}</span>${X.apps[id].icon}</button>`).join('');
    X.paintLogos(dock);
    dock.querySelector('[data-launch]').onclick = toggleLauncher;
    dock.querySelectorAll('[data-app]').forEach(b => b.onclick = () => X.toggleApp(b.dataset.app));
  }

  /* ---------- Launcher ---------- */
  let sel = 0, results = [];
  function toggleLauncher() { $('launcher').classList.contains('hidden') ? openLauncher() : closeLauncher(); }
  function openLauncher() {
    $('launcher').classList.remove('hidden');
    const inp = $('launcherInput'); inp.value = ''; search(''); inp.focus();
  }
  function closeLauncher() { $('launcher').classList.add('hidden'); }
  $('launcher').onclick = e => { if (e.target.id === 'launcher') closeLauncher(); };
  $('launcherInput').oninput = e => search(e.target.value);
  $('launcherInput').onkeydown = e => {
    if (e.key === 'ArrowDown') { sel = Math.min(results.length - 1, sel + 1); draw(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    if (e.key === 'Enter' && results[sel]) { results[sel].go(); closeLauncher(); }
  };
  function search(q) {
    q = q.toLowerCase().trim();
    results = [];
    Object.values(X.apps).forEach(a => { if (!q || a.name.toLowerCase().includes(q)) results.push({ i: a.icon, t: a.name, s: 'App', go: () => X.openApp(a.id) }); });
    S.spaces.forEach(s => { if (!q || s.name.toLowerCase().includes(q)) results.push({ i: '🗂️', t: s.name, s: 'Space', go: () => X.setSpace(s.id) }); });
    if (q) {
      const walk = (n, path, depth) => {
        if (depth > 6 || results.length > 30) return;
        for (const [name, c] of Object.entries(n.k)) {
          if (name.startsWith('.')) continue;
          const p = path + '/' + name;
          if (name.toLowerCase().includes(q)) results.push({ i: c.t === 'd' ? '📁' : '📄', t: name, s: X.pretty(path), go: () => X.openApp('files', { path: c.t === 'd' ? p : path }) });
          if (c.t === 'd') walk(c, p, depth + 1);
        }
      };
      walk(X.node(X.home()), X.home(), 0);
      results.push({ i: '⌨️', t: `Run "${q}" in Terminal`, s: 'Command', go: () => runInTerminal(q) });
      if (q.length > 3) results.push({ i: '💬', t: `Ask XORA: ${q}`, s: 'Question', go: () => runInTerminal('# ' + q) });
    }
    sel = 0; draw();
  }
  function draw() {
    $('launcherResults').innerHTML = results.map((r, j) => `<div class="lr ${j === sel ? 'sel' : ''}" data-j="${j}"><span class="i">${r.i}</span>${esc(r.t)}<span class="s">${esc(r.s)}</span></div>`).join('');
    $('launcherResults').querySelectorAll('[data-j]').forEach(el => el.onclick = () => { results[+el.dataset.j].go(); closeLauncher(); });
  }
  function runInTerminal(cmd) {
    const w = X.openApp('terminal');
    setTimeout(() => {
      const inp = w.el.querySelector('.term-input');
      if (inp) { inp.value = cmd; inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' })); }
    }, 50);
  }
})();
