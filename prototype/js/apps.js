/* XORA apps: Home, Files, Timeline, Fabric, Settings */
(function () {
  const X = window.XORA, S = X.state, esc = X.esc;

  /* live re-render helper: re-run render on events, unsubscribe-free (closed windows are skipped) */
  function live(win, events, render) {
    render();
    events.forEach(ev => X.on(ev, () => { if (win.el.isConnected) render(); }));
  }

  /* ---------- Home (light) ---------- */
  X.registerApp('home', {
    name: 'Home', icon: '🏠', w: 820, h: 540, single: true,
    open(body, win) {
      live(win, ['space', 'jobs', 'timeline', 'services'], () => {
        const hour = new Date().getHours();
        const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
        const running = S.jobs.filter(j => j.state === 'running');
        const lastSnap = S.timeline[0];
        body.innerHTML = `<div class="home">
          <div class="hl" data-logo="full" data-ora="#011429"></div>
          <h1>${greet}, ${esc(S.user.name)}</h1>
          <div class="sub">You're in <b class="acc">${esc(X.space().name)}</b>. ${running.length ? running.length + ' job running on your devices.' : 'Nothing running in the background.'}</div>
          <div class="cards">
            ${S.spaces.map(s => `<div class="card" data-space="${s.id}"><div class="ci">🗂️</div><b>${esc(s.name)}</b><span>${s.services.filter(x => x.s === 'running').length}/${s.services.length} services running · ${esc(s.branch)}</span></div>`).join('')}
            <div class="card" data-app="terminal"><div class="ci">🖥️</div><b>Terminal</b><span>Open in ${esc(X.space().name)}</span></div>
            <div class="card" data-app="timeline"><div class="ci">🕓</div><b>Timeline</b><span>${lastSnap ? 'Last snapshot ' + X.ago(lastSnap.at) : 'No snapshots yet'}</span></div>
            <div class="card" data-app="fabric"><div class="ci">🛰️</div><b>Fabric</b><span>${S.devices.filter(d => d.online).length} devices online</span></div>
          </div>
        </div>`;
        X.paintLogos(body);
        body.querySelectorAll('[data-space]').forEach(c => c.onclick = () => X.setSpace(c.dataset.space));
        body.querySelectorAll('[data-app]').forEach(c => c.onclick = () => X.openApp(c.dataset.app));
      });
    },
  });

  /* ---------- Files ---------- */
  const ICONS = { md: '📝', txt: '📄', py: '🐍', dart: '🎯', json: '🧾', yaml: '⚙️', svg: '🖼️', png: '🖼️', js: '📜', html: '🌐', css: '🎨' };
  X.registerApp('files', {
    name: 'Files', icon: '📁', w: 820, h: 520,
    open(body, win, args) {
      let cwd = (args && args.path) || X.home();
      let viewing = null;
      const places = () => [['🏠', 'Home', X.home()], ['📄', 'Documents', X.home() + '/Documents'], ['⬇️', 'Downloads', X.home() + '/Downloads'], ['🖼️', 'Pictures', X.home() + '/Pictures']];
      live(win, ['fs', 'space'], render);
      document.addEventListener('keydown', function del(e) {
        if (!win.el.isConnected) return document.removeEventListener('keydown', del);
        if (X.focused !== win || e.key !== 'Delete') return;
        const sel = body.querySelector('.file.sel'); if (!sel) return;
        const snap = X.remove(cwd + '/' + sel.dataset.name, 'Deleted in Files');
        X.toast('Deleted — saved to Timeline', `${sel.dataset.name} · ${snap.count} file(s) · restore it from Timeline`);
      });
      function render() {
        if (!X.node(cwd)) cwd = X.home();
        const n = X.node(cwd);
        const parts = cwd.split('/').filter(Boolean);
        win.setTitle('Files — ' + X.pretty(cwd));
        body.innerHTML = `<div class="app-side">
          <div class="side">
            <h4>Places</h4>${places().map(([i, l, p]) => `<div class="side-item ${p === cwd ? 'on' : ''}" data-go="${esc(p)}">${i} ${l}</div>`).join('')}
            <h4>Spaces</h4>${S.spaces.map(s => { const p = X.resolve(s.dir, X.home()); return `<div class="side-item ${p === cwd ? 'on' : ''}" data-go="${esc(p)}">🗂️ ${esc(s.name)}</div>`; }).join('')}
          </div>
          <div class="main">
            <div class="crumbs"><span data-go="/">/</span>${parts.map((p, i) => `<span data-go="/${esc(parts.slice(0, i + 1).join('/'))}">${esc(p)}</span>`).join(' › ')}
              <div style="margin-left:auto;display:flex;gap:6px"><button class="btn" data-act="mkdir">New folder</button><button class="btn" data-act="term">Open terminal here</button></div></div>
            ${viewing ? `<div style="margin-bottom:10px"><button class="btn" data-act="back">← Back</button> <b style="margin-left:8px">${esc(viewing)}</b></div><div class="viewer"></div>` :
              `<div class="grid">${Object.keys(n.k).filter(x => !x.startsWith('.')).sort((a, b) => (n.k[b].t === 'd') - (n.k[a].t === 'd') || a.localeCompare(b)).map(name => {
                const c = n.k[name], ext = name.split('.').pop();
                return `<div class="file" data-name="${esc(name)}"><div class="ic">${c.t === 'd' ? '📁' : ICONS[ext] || '📄'}</div>${esc(name)}</div>`;
              }).join('') || '<div class="empty">This folder is empty</div>'}</div>`}
          </div></div>`;
        if (viewing) body.querySelector('.viewer').textContent = X.node(cwd + '/' + viewing)?.c ?? '';
        body.querySelectorAll('[data-go]').forEach(e => e.onclick = () => { cwd = e.dataset.go; viewing = null; render(); });
        body.querySelectorAll('.file').forEach(e => {
          e.onclick = () => { body.querySelectorAll('.file').forEach(f => f.classList.remove('sel')); e.classList.add('sel'); };
          e.ondblclick = () => {
            const name = e.dataset.name, c = n.k[name];
            if (c.t === 'd') cwd = (cwd === '/' ? '' : cwd) + '/' + name; else viewing = name;
            render();
          };
        });
        const act = body.querySelectorAll('[data-act]');
        act.forEach(b => b.onclick = () => {
          if (b.dataset.act === 'back') { viewing = null; render(); }
          if (b.dataset.act === 'term') X.openApp('terminal', { cwd });
          if (b.dataset.act === 'mkdir') {
            let i = 1, name = 'New folder'; while (n.k[name]) name = 'New folder ' + (++i);
            X.mkdir(cwd + '/' + name);
          }
        });
      }
    },
  });

  /* ---------- Timeline ---------- */
  X.registerApp('timeline', {
    name: 'Timeline', icon: '🕓', w: 640, h: 520, single: true,
    open(body, win) {
      live(win, ['timeline'], () => {
        body.innerHTML = `<div class="main"><h2>Timeline</h2><div class="sub">XORA saves a snapshot before anything is deleted, so every mistake can be undone.</div>
          ${S.timeline.length ? `<div class="tl">${S.timeline.map(s => `<div class="tl-item ${s.restored ? 'restored' : ''}">
            <div class="h"><b>${esc(X.pretty(s.path))}</b>${s.restored ? '<span class="sub" style="margin:0">Restored</span>' : `<button class="btn acc" data-r="${s.id}">Restore</button>`}</div>
            <div class="meta">${s.count.toLocaleString()} files · ${esc(s.reason)} · ${X.ago(s.at)} · ${esc(X.space(s.space).name)}</div></div>`).join('')}</div>`
          : '<div class="empty">No snapshots yet.<br>Try <code>rm -rf build/</code> in the Terminal.</div>'}</div>`;
        body.querySelectorAll('[data-r]').forEach(b => b.onclick = () => {
          try { const s = X.restore(b.dataset.r); X.toast('Restored', X.pretty(s.path)); }
          catch (e) { X.toast('Could not restore', e.message); }
        });
      });
    },
  });

  /* ---------- Fabric ---------- */
  X.registerApp('fabric', {
    name: 'Fabric', icon: '🛰️', w: 720, h: 500, single: true,
    open(body, win) {
      live(win, ['jobs'], () => {
        body.innerHTML = `<div class="main"><h2>Fabric</h2><div class="sub">All your devices act like one computer. Send heavy work to whichever one is free.</div>
          <div class="devices">${S.devices.map(d => `<div class="device"><div class="n">${d.kind} ${esc(d.name)} <span class="dot ${d.online ? 'ok' : ''}" style="margin-left:auto"></span></div>
            <div class="m">${d.online ? (d.here ? 'This device' : 'Online') : 'Offline'}</div>
            ${d.online ? `<small>CPU ${d.cpu}%</small><div class="bar"><i style="width:${d.cpu}%"></i></div>` : ''}</div>`).join('')}</div>
          <h4 style="margin:24px 0 10px;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em">Jobs</h4>
          ${S.jobs.length ? S.jobs.slice(0, 8).map(j => `<div class="tl-item" style="margin-left:0"><div class="h"><b><code>${esc(j.cmd)}</code></b>
            ${j.state === 'running' && j.device !== 'laptop' ? `<button class="btn" data-back="${j.id}">Bring back here</button>` : ''}</div>
            <div class="meta">${esc(X.device(j.device)?.name || j.device)} · ${j.state} · ${Math.floor(j.progress)}%</div>
            ${j.state === 'running' ? `<div class="bar"><i style="width:${j.progress}%"></i></div>` : ''}</div>`).join('')
          : '<div class="empty">No jobs yet. In the Terminal try:<br><code>xora fabric run flutter build apk --on office-pc</code></div>'}</div>`;
        body.querySelectorAll('[data-back]').forEach(b => b.onclick = () => { X.bringBack(b.dataset.back); X.toast('Fabric', 'Job moved back to this laptop'); });
      });
    },
  });

  /* ---------- Settings ---------- */
  const ACCENTS = ['#1EC8F0', '#0A84F5', '#7C5CFF', '#3DDC97', '#FF8A3D', '#FF5C7A'];
  X.ACCENTS = ACCENTS;
  X.registerApp('settings', {
    name: 'Settings', icon: '⚙️', w: 620, h: 560, single: true,
    open(body, win) {
      const render = () => {
        body.innerHTML = `<div class="main"><h2>Settings</h2><div class="sub">XORA OS 0.1 (Dawn) · ${esc(S.user.name)}</div>
          <div class="row"><div class="l">Highlight colour<small>Used for buttons, selections and the active Space</small></div>
            <div class="swatches" style="margin:0">${ACCENTS.map(c => `<button class="swatch ${c === S.accent ? 'on' : ''}" style="background:${c};width:26px;height:26px" data-acc="${c}"></button>`).join('')}</div></div>
          <div class="row"><div class="l">Wallpaper glow<small>The glowing X in the middle of the desktop</small></div><button class="toggle ${S.glow ? 'on' : ''}" data-t="glow"></button></div>
          <div class="row"><div class="l">Terminal frame colour<small>The ┌──( lines in the prompt</small></div><input type="color" data-c="termFrame" value="${S.termFrame}"></div>
          <div class="row"><div class="l">Terminal user colour<small>Set it to red for Kali's root look</small></div><input type="color" data-c="termUser" value="${S.termUser}">
            <button class="btn" data-root>Root red</button><button class="btn" data-kali>Kali blue</button></div>
          <div class="row"><div class="l">Name<small>Shown on Home</small></div><input data-name value="${esc(S.user.name)}" style="padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:rgba(0,0,0,.25);color:var(--text)"></div>
          <div class="row" style="border:0"><div class="l">Reset XORA<small>Erase everything and run first-boot setup again</small></div><button class="btn" data-reset style="color:var(--bad)">Reset…</button></div>
        </div>`;
        body.querySelectorAll('[data-acc]').forEach(b => b.onclick = () => { S.accent = b.dataset.acc; apply(); });
        body.querySelector('[data-t=glow]').onclick = () => { S.glow = !S.glow; apply(); };
        body.querySelectorAll('[data-c]').forEach(i => i.oninput = () => { S[i.dataset.c] = i.value; X.applyTheme(); X.save(); });
        body.querySelector('[data-root]').onclick = () => { S.termUser = '#FF3B3B'; S.termFrame = '#3D7EFF'; apply(); };
        body.querySelector('[data-kali]').onclick = () => { S.termUser = '#3D7EFF'; S.termFrame = '#2FD15A'; apply(); };
        body.querySelector('[data-name]').onchange = e => { S.user.name = e.target.value || S.user.name; X.save(); X.emit('space'); };
        const reset = body.querySelector('[data-reset]');
        reset.onclick = () => { if (reset.dataset.armed) X.reset(); reset.dataset.armed = 1; reset.textContent = 'Click again to erase'; };
      };
      const apply = () => { X.applyTheme(); X.save(); render(); };
      render();
    },
  });
})();
