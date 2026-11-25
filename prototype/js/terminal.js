/* XORA Terminal — Kali-style look, XORA features (explain, fabric, timeline undo, Spaces, # questions). */
(function () {
  const X = window.XORA, S = X.state, esc = X.esc;
  S.dbs = S.dbs || [];

  const COMMANDS = ['help', 'clear', 'ls', 'cd', 'pwd', 'cat', 'echo', 'mkdir', 'touch', 'rm', 'whoami', 'hostname', 'uname',
    'date', 'history', 'neofetch', 'python', 'python3', 'git', 'pytest', 'createdb', 'flutter', 'xora', 'sudo', 'open', 'exit', 'tree'];

  X.registerApp('terminal', {
    name: 'Terminal', icon: '🖥️', w: 860, h: 540,
    open(body, win, args) { new Term(body, win, args); },
  });

  class Term {
    constructor(body, win, args) {
      this.win = win;
      this.zoom = 13.5;
      body.innerHTML = `<div class="term">
        <div class="term-menu"><span data-m="file">File</span><span data-m="actions">Actions</span><span data-m="edit">Edit</span><span data-m="view">View</span><span data-m="help">Help</span></div>
        <div class="term-tabs"></div>
        <div class="term-out" tabindex="0"></div>
      </div>`;
      this.root = body.querySelector('.term');
      this.tabsEl = body.querySelector('.term-tabs');
      this.out = body.querySelector('.term-out');
      this.tabs = [];
      this.newTab((args && args.space) || S.activeSpace, args && args.cwd);

      this.root.querySelector('.term-menu').onclick = e => this.menu(e.target.dataset.m);
      this.out.addEventListener('mouseup', () => { if (!getSelection().toString()) this.focusInput(); });
      win.onFocus = () => setTimeout(() => this.focusInput(), 0);
      win.onArgs = a => { if (a) this.newTab(a.space || S.activeSpace, a.cwd); };
      this.onSpace = id => { if (this.tab && this.tab.space !== id) { const t = this.tabs.find(t => t.space === id); t ? this.switchTab(t) : this.newTab(id); } };
      X.on('space', this.onSpace);
    }

    /* ---------- tabs ---------- */
    newTab(spaceId, cwd) {
      const sp = X.space(spaceId);
      const tab = { space: sp.id, cwd: cwd || X.resolve(sp.dir, X.home()), frag: document.createDocumentFragment(), hist: [], hi: 0, code: 0, fix: null, busy: null };
      if (!X.node(tab.cwd)) tab.cwd = X.home();
      this.tabs.push(tab);
      this.switchTab(tab);
      this.print(`<span class="k-dim">XORA OS 0.1 (Dawn) · Space </span><span class="k-space">${esc(sp.name)}</span><span class="k-dim"> · type </span>help<span class="k-dim"> to get started, or start a line with </span>#<span class="k-dim"> to ask in plain words.</span>`);
      this.prompt();
    }
    switchTab(tab) {
      if (this.tab) { this.tab.frag = document.createDocumentFragment(); while (this.out.firstChild) this.tab.frag.appendChild(this.out.firstChild); }
      this.tab = tab;
      this.out.appendChild(tab.frag);
      this.renderTabs();
      if (tab.needPrompt) { tab.needPrompt = false; this.prompt(); }
      this.win.setTitle(`${S.user.login}@${S.host}: ${X.pretty(tab.cwd)}`);
      if (S.activeSpace !== tab.space) X.setSpace(tab.space);
      this.scroll(); this.focusInput();
    }
    closeTab(tab) {
      const i = this.tabs.indexOf(tab);
      this.tabs.splice(i, 1);
      if (!this.tabs.length) return this.win.close();
      if (tab === this.tab) { this.tab = null; this.out.innerHTML = ''; this.switchTab(this.tabs[Math.max(0, i - 1)]); }
      else this.renderTabs();
    }
    renderTabs() {
      this.tabsEl.innerHTML = '';
      this.tabs.forEach(t => {
        const el = document.createElement('div');
        el.className = 'term-tab' + (t === this.tab ? ' on' : '');
        el.innerHTML = `<span>${esc(X.space(t.space).name)}</span><span class="x">✕</span>`;
        el.onclick = e => e.target.classList.contains('x') ? this.closeTab(t) : this.switchTab(t);
        this.tabsEl.appendChild(el);
      });
      const add = document.createElement('div');
      add.className = 'term-tab add'; add.textContent = '+'; add.title = 'New tab in another Space';
      add.onclick = () => { const used = this.tabs.map(t => t.space); const next = S.spaces.find(s => !used.includes(s.id)) || X.space(); this.newTab(next.id); };
      this.tabsEl.appendChild(add);
    }

    menu(m) {
      if (m === 'file') this.newTab(S.activeSpace);
      if (m === 'actions') { this.out.innerHTML = ''; this.prompt(); }
      if (m === 'edit') { const s = getSelection().toString(); if (s) navigator.clipboard?.writeText(s); X.toast('Edit', s ? 'Copied selection' : 'Select text to copy'); }
      if (m === 'view') { this.zoom = this.zoom >= 17 ? 12 : this.zoom + 1.5; this.root.style.fontSize = this.zoom + 'px'; }
      if (m === 'help') this.run('help');
    }

    /* ---------- output ---------- */
    print(html, cls) {
      const d = document.createElement('div');
      d.className = 'term-line' + (cls ? ' ' + cls : '');
      d.innerHTML = html;
      (this.pending || this.out).appendChild(d);
      this.scroll();
      return d;
    }
    text(s, cls) { return this.print(esc(s), cls); }
    scroll() { this.out.scrollTop = this.out.scrollHeight; }
    focusInput() { const i = this.out.querySelector('.term-input'); i && i.focus({ preventScroll: true }); }

    promptHTML() {
      const t = this.tab, sp = X.space(t.space);
      const _r = this.isRoot;
      const code = t.code ? `<span class="k-frame">-[</span><span class="k-bad">${t.code}</span><span class="k-frame">]</span>` : '';
      const git = this.gitBranch(t.cwd) ? ` <span class="k-dim">git:</span><span class="k-ok">${esc(sp.branch)}</span>` : '';
      const lang = sp.lang && t.cwd.startsWith(X.resolve(sp.dir, X.home())) ? ` <span class="k-dim">${esc(sp.lang)}</span>` : '';
      return `<span class="k-frame">┌──(</span><span class="k-user">${_r ? 'root' : esc(S.user.login)}㉿${esc(S.host)}</span><span class="k-frame">)-[</span><span class="k-path">${esc(X.pretty(t.cwd))}</span><span class="k-frame">]</span>${code} <span class="k-space">⟨${esc(sp.name)}⟩</span>${git}${lang}`;
    }
    prompt() {
      const root = this.isRoot;
      this.print(this.promptHTML(), root ? 'root' : '');
      const line = document.createElement('div');
      line.className = 'term-line term-input-line' + (root ? ' root' : '');
      line.innerHTML = `<span class="k-frame">└─</span><span class="k-dollar">${root ? '#' : '$'}</span>&nbsp;<input class="term-input" spellcheck="false" autocomplete="off">`;
      this.out.appendChild(line);
      const inp = line.querySelector('input');
      inp.addEventListener('keydown', e => this.key(e, inp));
      this.scroll();
      inp.focus({ preventScroll: true });
    }

    key(e, inp) {
      const t = this.tab;
      if (e.key === 'Enter') {
        const v = inp.value;
        const line = inp.parentElement;
        line.innerHTML = `<span class="k-frame">└─</span><span class="k-dollar">${line.classList.contains('root') ? '#' : '$'}</span> ${esc(v)}`;
        line.classList.remove('term-input-line');
        if (v.trim()) { t.hist.push(v); t.hi = t.hist.length; }
        this.exec(v);
      } else if (e.key === 'ArrowUp') {
        if (t.hi > 0) inp.value = t.hist[--t.hi]; e.preventDefault();
      } else if (e.key === 'ArrowDown') {
        if (t.hi < t.hist.length) inp.value = t.hist[++t.hi] || ''; e.preventDefault();
      } else if (e.key === 'Tab') {
        e.preventDefault(); this.complete(inp);
      } else if (e.key === 'F2') {
        e.preventDefault();
        if (t.fix) { inp.value = t.fix; inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' })); }
      } else if (e.key === 'l' && e.ctrlKey) {
        e.preventDefault(); this.out.innerHTML = ''; this.prompt(); this.focusInput();
        const ni = this.out.querySelector('.term-input'); ni.value = inp.value;
      } else if (e.key === 'c' && e.ctrlKey && !getSelection().toString()) {
        e.preventDefault();
        inp.parentElement.innerHTML += '<span class="k-dim">^C</span>';
        inp.remove(); this.prompt();
      }
    }

    complete(inp) {
      const v = inp.value, parts = v.split(/\s+/), last = parts[parts.length - 1];
      let options;
      if (parts.length === 1) options = COMMANDS.filter(c => c.startsWith(last));
      else {
        const slash = last.lastIndexOf('/');
        const base = slash >= 0 ? last.slice(0, slash + 1) : '';
        const d = X.node(X.resolve(base || '.', this.tab.cwd));
        if (!d || d.t !== 'd') return;
        options = Object.keys(d.k).filter(n => n.startsWith(last.slice(slash + 1))).map(n => base + n + (d.k[n].t === 'd' ? '/' : ''));
      }
      if (options.length === 1) { parts[parts.length - 1] = options[0] + (parts.length === 1 ? ' ' : ''); inp.value = parts.join(' '); }
      else if (options.length > 1) {
        const pre = options.reduce((a, b) => { let i = 0; while (i < a.length && a[i] === b[i]) i++; return a.slice(0, i); });
        if (pre.length > last.length) { parts[parts.length - 1] = pre; inp.value = parts.join(' '); }
        else {
          const line = inp.parentElement;
          const d = document.createElement('div'); d.className = 'term-line'; d.textContent = options.join('   ');
          line.before(d);
        }
      }
    }

    /* ---------- execution ---------- */
    run(cmd) { const i = this.out.querySelector('.term-input'); if (i) { i.value = cmd; i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' })); } }

    async exec(raw) {
      const t = this.tab;
      const line = raw.trim();
      this.isRoot = !!t.rootShell;
      if (!line) { t.code = 0; return this.prompt(); }
      let code = 0;
      try {
        if (line.startsWith('#')) code = await this.ask(line.slice(1).trim());
        else {
          // simple support for `a && b` and `a ; b`
          const chain = line.split(/\s*(&&|;)\s*/);
          for (let i = 0; i < chain.length; i += 2) {
            if (i > 0 && chain[i - 1] === '&&' && code !== 0) break;
            code = await this.one(chain[i]);
          }
        }
      } catch (err) {
        this.text(err.message, 'k-bad'); code = 1;
      }
      t.code = code;
      this.isRoot = !!t.rootShell;
      this.win.setTitle(`${S.user.login}@${S.host}: ${X.pretty(t.cwd)}`);
      if (this.tab === t) this.prompt(); else t.needPrompt = true;
    }

    parse(s) {
      const out = []; let cur = '', q = null, has = false;
      for (const ch of s) {
        if (q) { if (ch === q) q = null; else cur += ch; }
        else if (ch === '"' || ch === "'") { q = ch; has = true; }
        else if (/\s/.test(ch)) { if (cur || has) out.push(cur); cur = ''; has = false; }
        else cur += ch;
      }
      if (cur || has) out.push(cur);
      return out;
    }

    async one(s) {
      let redirect = null;
      const m = s.match(/^(.*?)\s*(>>?)\s*(\S+)\s*$/);
      if (m && !/^\s*xora|^\s*#/.test(s)) { s = m[1]; redirect = { append: m[2] === '>>', path: m[3] }; }
      const argv = this.parse(s);
      const cmd = argv.shift();
      const fn = this['c_' + cmd.replace(/[^a-z0-9]/gi, '_')];
      if (redirect) {
        const buf = []; const realText = this.text;
        this.text = (x) => { buf.push(x); return { textContent: '' }; };
        let code;
        try { code = fn ? await fn.call(this, argv) : this.notFound(cmd); }
        finally { this.text = realText; }
        X.write(X.resolve(redirect.path, this.tab.cwd), buf.join('\n') + '\n', redirect.append);
        return code;
      }
      if (!fn) return this.notFound(cmd);
      return (await fn.call(this, argv)) || 0;
    }
    notFound(cmd) {
      this.print(`<span class="k-bad">zsh: command not found: ${esc(cmd)}</span>`);
      const near = COMMANDS.find(c => lev(c, cmd) <= 2);
      if (near) this.xexplain(`Did you mean <b>${near}</b>?`, near);
      return 127;
    }

    xexplain(html, fix) {
      this.print(`<span class="k-xora">[xora explain]</span> ${html}`);
      this.tab.fix = fix || null;
      if (fix) this.print(`<span class="k-xora">[xora explain]</span> Press <b>F2</b> to run: <span class="k-link" data-fix>${esc(fix)}</span>`)
        .querySelector('[data-fix]').onclick = () => this.run(fix);
    }

    /* ---------- builtins ---------- */
    c_help() {
      const rows = [
        ['ls, cd, pwd, cat, tree', 'look around the file system'],
        ['mkdir, touch, echo > file', 'create things'],
        ['rm [-rf]', 'delete — a Timeline snapshot is saved first'],
        ['git, python, pytest, createdb, flutter', 'project tools (demo)'],
        ['xora undo', 'bring back the last thing you deleted'],
        ['xora timeline', 'list snapshots'],
        ['xora fabric ls | run <cmd> --on <device> | back', 'run work on your other devices'],
        ['xora up | down | services', 'start/stop this Space\'s services'],
        ['xora space <name>', 'switch Space'],
        ['open <app>', 'open files, timeline, fabric, settings, home'],
        ['# <question>', 'ask in plain words, e.g. # why is the api slow?'],
        ['F2', 'run the fix XORA suggested'],
      ];
      this.print('<span class="k-info">[*]</span> XORA Terminal commands');
      rows.forEach(([a, b]) => this.print(`    <span class="k-ok">${esc(a.padEnd(46))}</span><span class="k-dim">${esc(b)}</span>`));
    }
    c_clear() { this.out.innerHTML = ''; }
    c_pwd() { this.text(this.tab.cwd); }
    c_whoami() { this.text(this.isRoot ? 'root' : S.user.login); }
    c_hostname() { this.text(S.host); }
    c_date() { this.text(new Date().toString()); }
    c_uname(a) { this.text(a.includes('-a') ? `Linux ${S.host} 6.12.0-xora #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux` : 'Linux'); }
    c_history() { this.tab.hist.forEach((h, i) => this.text(String(i + 1).padStart(5) + '  ' + h)); }
    c_echo(a) { this.text(a.join(' ')); }
    c_exit() { if (this.tab.rootShell) { this.tab.rootShell = false; this.isRoot = false; return; } setTimeout(() => this.closeTab(this.tab)); }
    c_open(a) {
      const id = (a[0] || '').toLowerCase();
      if (!X.apps[id]) { this.text(`open: unknown app '${a[0] || ''}'. Try: ${Object.keys(X.apps).join(', ')}`, 'k-bad'); return 1; }
      X.openApp(id);
    }
    async c_sudo(a) {
      if (!a.length) { this.text('usage: sudo <command>'); return 1; }
      this.print(`<span class="k-dim">[sudo] password for ${esc(S.user.login)}: ••••••••</span>`);
      await sleep(400);
      this.isRoot = true;
      if (a[0] === 'su' || a[0] === '-i' || a[0] === '-s') { this.tab.rootShell = true; return 0; }
      return this.one(a.join(' '));
    }

    c_cd(a) {
      const p = X.resolve(a[0] || '~', this.tab.cwd);
      const n = X.node(p);
      if (!n) { this.text(`cd: no such file or directory: ${a[0]}`, 'k-bad'); return 1; }
      if (n.t !== 'd') { this.text(`cd: not a directory: ${a[0]}`, 'k-bad'); return 1; }
      this.tab.cwd = p;
    }
    c_ls(a) {
      const flags = a.filter(x => x.startsWith('-')).join('');
      const targets = a.filter(x => !x.startsWith('-'));
      const p = X.resolve(targets[0] || '.', this.tab.cwd);
      const n = X.node(p);
      if (!n) { this.text(`ls: cannot access '${targets[0]}': No such file or directory`, 'k-bad'); return 2; }
      if (n.t === 'f') { this.text(targets[0]); return; }
      let names = Object.keys(n.k).sort();
      if (!flags.includes('a')) names = names.filter(x => !x.startsWith('.'));
      const fmt = name => {
        const c = n.k[name];
        return c.t === 'd' ? `<span class="k-dir">${esc(name)}</span>` : /\.(sh|py)$/.test(name) ? `<span class="k-exe">${esc(name)}</span>` : esc(name);
      };
      if (flags.includes('l')) {
        this.text(`total ${names.length * 4}`);
        names.forEach(name => {
          const c = n.k[name];
          const size = c.t === 'd' ? 4096 : (c.c || '').length;
          const d = new Date(c.m || Date.now());
          const when = d.toLocaleString('en', { month: 'short' }) + ' ' + String(d.getDate()).padStart(2) + ' ' + d.toTimeString().slice(0, 5);
          this.print(`${c.t === 'd' ? 'drwxr-xr-x' : '-rw-r--r--'} 1 ${esc(S.user.login)} ${esc(S.user.login)} ${String(size).padStart(6)} ${when} ${fmt(name)}`);
        });
      } else if (names.length) this.print(names.map(fmt).join('  '));
    }
    c_tree(a) {
      const p = X.resolve(a[0] || '.', this.tab.cwd), root = X.node(p);
      if (!root || root.t !== 'd') { this.text('tree: not a directory', 'k-bad'); return 1; }
      let dirs = 0, files = 0;
      const walk = (n, pre, depth) => {
        const names = Object.keys(n.k).filter(x => !x.startsWith('.')).sort();
        names.forEach((name, i) => {
          const c = n.k[name], last = i === names.length - 1;
          this.print(esc(pre + (last ? '└── ' : '├── ')) + (c.t === 'd' ? `<span class="k-dir">${esc(name)}</span>` : esc(name)));
          if (c.t === 'd') { dirs++; if (depth < 3) walk(c, pre + (last ? '    ' : '│   '), depth + 1); } else files++;
        });
      };
      this.print(`<span class="k-dir">${esc(a[0] || '.')}</span>`); walk(root, '', 0);
      this.text(`\n${dirs} directories, ${files} files`);
    }
    c_cat(a) {
      if (!a.length) { this.text('cat: missing file operand', 'k-bad'); return 1; }
      for (const f of a) {
        const n = X.node(X.resolve(f, this.tab.cwd));
        if (!n) { this.text(`cat: ${f}: No such file or directory`, 'k-bad'); return 1; }
        if (n.t === 'd') { this.text(`cat: ${f}: Is a directory`, 'k-bad'); return 1; }
        this.text(n.c.replace(/\n$/, ''));
      }
    }
    c_mkdir(a) {
      const p = a.includes('-p'); const names = a.filter(x => x !== '-p');
      if (!names.length) { this.text('mkdir: missing operand', 'k-bad'); return 1; }
      for (const n of names) {
        try { X.mkdir(X.resolve(n, this.tab.cwd), p); }
        catch (e) { this.text(`mkdir: cannot create directory '${n}': ${e.message}`, 'k-bad'); return 1; }
      }
    }
    c_touch(a) {
      for (const f of a) { const p = X.resolve(f, this.tab.cwd); if (!X.node(p)) X.write(p, ''); else X.node(p).m = Date.now(); }
    }
    c_rm(a) {
      const flags = a.filter(x => x.startsWith('-')).join('');
      const targets = a.filter(x => !x.startsWith('-'));
      const rec = /r/i.test(flags);
      if (!targets.length) { this.text('rm: missing operand', 'k-bad'); return 1; }
      for (const f of targets) {
        const p = X.resolve(f, this.tab.cwd), n = X.node(p);
        if (!n) { if (flags.includes('f')) continue; this.text(`rm: cannot remove '${f}': No such file or directory`, 'k-bad'); return 1; }
        if (n.t === 'd' && !rec) { this.text(`rm: cannot remove '${f}': Is a directory`, 'k-bad'); return 1; }
        if (p === '/' || p === X.home()) { this.text(`rm: refusing to remove '${f}'`, 'k-bad'); return 1; }
        const snap = X.remove(p, `rm ${a.join(' ')}`);
        if (n.t === 'd' || snap.count > 1) {
          this.print(`<span class="k-xora">[xora timeline]</span> Snapshot saved before deleting <b>${snap.count.toLocaleString()}</b> files in ${esc(X.pretty(p))}/ · <span class="k-link" data-u>xora undo</span> to bring them back`)
            .querySelector('[data-u]').onclick = () => this.run('xora undo');
        }
      }
    }

    /* ---------- dev tools (demo) ---------- */
    gitBranch(cwd) {
      let p = cwd;
      while (p && p !== '/') { if (X.node(p + '/.git')) return X.space(this.tab.space).branch; p = p.slice(0, p.lastIndexOf('/')) || '/'; }
      return null;
    }
    c_git(a) {
      const br = this.gitBranch(this.tab.cwd);
      if (!br) { this.text('fatal: not a git repository (or any of the parent directories): .git', 'k-bad'); return 128; }
      const sub = a[0];
      if (sub === 'status') {
        this.text(`On branch ${br}\nChanges not staged for commit:`);
        this.print('        <span class="k-bad">modified:   app/routes/checkin.py</span>');
        this.text('\nno changes added to commit (use "git add" and/or "git commit -a")');
      } else if (sub === 'branch') this.print(`* <span class="k-ok">${esc(br)}</span>\n  main`);
      else if (sub === 'log') this.print(`<span class="k-warn">commit 8f2c1e4</span> (HEAD -> <span class="k-ok">${esc(br)}</span>)\nAuthor: ${esc(S.user.name)}\n\n    Add check-in endpoint\n\n<span class="k-warn">commit 1a9b0d2</span> (main)\n\n    Initial FastAPI app`);
      else this.text('usage: git status | branch | log');
    }
    c_python(a) { if (a[0] === '--version' || a[0] === '-V') this.text('Python 3.12.7'); else { this.text('Python 3.12.7 (main) [GCC 13.2.0] on linux\n(interactive Python is not available in this demo)'); } }
    c_python3(a) { return this.c_python(a); }
    async c_pytest() {
      if (!X.node(this.tab.cwd + '/tests')) { this.text('no tests ran in 0.01s', 'k-warn'); return 5; }
      this.print('<span class="k-bold">============================= test session starts ==============================</span>');
      this.text('platform linux -- Python 3.12.7, pytest-8.3.3\nrootdir: ' + X.pretty(this.tab.cwd) + '\ncollected 1 item\n');
      await sleep(700);
      if (S.dbs.includes('attndi_test')) {
        this.print('tests/test_checkin.py <span class="k-ok">.</span>                                                  [100%]');
        this.print('<span class="k-ok">============================== 1 passed in 0.42s ===============================</span>');
        return 0;
      }
      this.print('tests/test_checkin.py <span class="k-bad">E</span>                                                  [100%]');
      this.print('<span class="k-bad">E   psycopg.OperationalError: connection failed: FATAL:  database "attndi_test" does not exist</span>');
      this.print('<span class="k-bad">=============================== 1 error in 0.38s ===============================</span>');
      this.xexplain('The tests need a database called <b>attndi_test</b>, and it doesn\'t exist yet. Create it once and the tests can connect.', 'createdb attndi_test');
      return 1;
    }
    c_createdb(a) {
      if (!a[0]) { this.text('createdb: missing database name', 'k-bad'); return 1; }
      if (S.dbs.includes(a[0])) { this.text(`createdb: error: database creation failed: ERROR:  database "${a[0]}" already exists`, 'k-bad'); return 1; }
      S.dbs.push(a[0]); X.save();
      this.print(`<span class="k-ok">[+]</span> Created database ${esc(a[0])}`);
      this.tab.fix = null;
    }
    async c_flutter(a) {
      if (a[0] === '--version') { this.text('Flutter 3.24.3 • channel stable'); return; }
      if (a[0] !== 'build') { this.text('usage: flutter build apk'); return 1; }
      if (!X.node(this.tab.cwd + '/pubspec.yaml')) { this.text('Error: No pubspec.yaml file found.', 'k-bad'); return 1; }
      return this.progress('flutter build apk', 'laptop', 160);
    }

    async progress(cmd, deviceId, speed) {
      const dev = X.device(deviceId);
      const line = this.print('');
      let p = 0, cancel = false;
      const stopper = e => { if (e.key === 'c' && e.ctrlKey) cancel = true; };
      addEventListener('keydown', stopper);
      const where = dev.here ? '' : ` <span class="k-dim">on</span> <span class="k-xora">${esc(dev.name)}</span>`;
      let job = null;
      if (!dev.here) job = X.startJob(cmd, deviceId);
      while (p < 100 && !cancel) {
        await sleep(speed);
        p = job ? job.progress : Math.min(100, p + 2 + Math.random() * 4);
        const n = Math.round(p / 4);
        const at = job ? X.device(job.device) : dev;
        line.innerHTML = `<span class="k-info">[*]</span> ${esc(cmd)}${at.here ? '' : ` <span class="k-dim">on</span> <span class="k-xora">${esc(at.name)}</span>`} [<span class="k-ok">${'#'.repeat(n)}</span>${'.'.repeat(25 - n)}] ${Math.floor(p)}%`;
        this.scroll();
      }
      removeEventListener('keydown', stopper);
      if (job && cancel) job.state = 'cancelled';
      if (cancel) { this.print('<span class="k-dim">^C</span>'); return 130; }
      this.print(`<span class="k-ok">[+]</span> Built build/app/outputs/flutter-apk/app-release.apk (21.4MB)${where ? ' · copied back to this laptop' : ''}`);
      X.toast('Build finished', cmd + (where ? ' · ' + dev.name : ''));
      return 0;
    }

    /* ---------- xora ---------- */
    async c_xora(a) {
      const sub = a.shift();
      if (!sub || sub === 'help') return this.c_help();
      if (sub === 'undo') {
        try {
          const s = X.restore(a[0]);
          this.print(`<span class="k-ok">[+]</span> Restored ${esc(X.pretty(s.path))} (${s.count.toLocaleString()} files) from snapshot ${s.id}`);
        } catch (e) { this.text('xora undo: ' + e.message, 'k-bad'); return 1; }
        return;
      }
      if (sub === 'timeline') {
        if (!S.timeline.length) { this.text('No snapshots yet. XORA saves one automatically before anything is deleted.'); return; }
        S.timeline.slice(0, 15).forEach(s => this.print(`<span class="k-warn">${s.id}</span>  ${esc(X.ago(s.at).padEnd(10))} ${esc(X.pretty(s.path).padEnd(28))} ${String(s.count).padStart(6)} files  ${s.restored ? '<span class="k-dim">restored</span>' : '<span class="k-ok">available</span>'}`));
        return;
      }
      if (sub === 'fabric') {
        const op = a.shift();
        if (!op || op === 'ls') {
          S.devices.forEach(d => this.print(`${d.online ? '<span class="k-ok">●</span>' : '<span class="k-dim">○</span>'} ${esc(d.name.padEnd(14))} <span class="k-dim">${d.id.padEnd(10)}</span> ${d.online ? `cpu ${String(d.cpu).padStart(3)}%` : 'offline'}${d.here ? '  <span class="k-xora">(here)</span>' : ''}`));
          return;
        }
        if (op === 'run') {
          const i = a.indexOf('--on');
          const devId = i >= 0 ? a[i + 1] : 'office-pc';
          const cmd = a.filter((_, j) => i < 0 || (j !== i && j !== i + 1)).join(' ');
          const dev = X.device(devId);
          if (!dev) { this.text(`xora fabric: unknown device '${devId}'. Try: xora fabric ls`, 'k-bad'); return 1; }
          if (!dev.online) { this.text(`xora fabric: ${dev.name} is offline`, 'k-bad'); return 1; }
          if (!cmd) { this.text('usage: xora fabric run <command> --on <device>'); return 1; }
          this.print(`<span class="k-info">[*]</span> Sending Space <span class="k-space">${esc(X.space().name)}</span> to ${esc(dev.name)}… synced 214 files`);
          return this.progress(cmd, devId, 300);
        }
        if (op === 'back') {
          const j = S.jobs.find(j => j.state === 'running' && j.device !== 'laptop');
          if (!j) { this.text('Nothing running on other devices.'); return; }
          X.bringBack(j.id); this.print(`<span class="k-ok">[+]</span> ${esc(j.cmd)} moved back to this laptop`); return;
        }
        this.text('usage: xora fabric ls | run <cmd> --on <device> | back'); return 1;
      }
      if (sub === 'up' || sub === 'down') {
        const sp = X.space();
        if (!sp.services.length) { this.text(`Space '${sp.name}' has no services.`); return; }
        for (const s of sp.services) {
          await sleep(180);
          X.setService(sp.id, s.n, sub === 'up' ? 'running' : 'stopped');
          this.print(`${sub === 'up' ? '<span class="k-ok">[+]</span> started' : '<span class="k-warn">[-]</span> stopped'} ${esc(s.n)}`);
        }
        return;
      }
      if (sub === 'services') {
        const sp = X.space();
        if (!sp.services.length) this.text('No services in this Space.');
        sp.services.forEach(s => this.print(`${s.s === 'running' ? '<span class="k-ok">●</span>' : '<span class="k-bad">●</span>'} ${esc(s.n.padEnd(10))} ${s.s}`));
        return;
      }
      if (sub === 'space') {
        const q = a.join(' ').toLowerCase();
        if (!q) { S.spaces.forEach(s => this.print(`${s.id === S.activeSpace ? '<span class="k-ok">*</span>' : ' '} ${esc(s.id.padEnd(10))} ${esc(s.name)}`)); return; }
        const sp = S.spaces.find(s => s.id === q || s.name.toLowerCase().includes(q));
        if (!sp) { this.text(`xora space: no Space matches '${q}'`, 'k-bad'); return 1; }
        this.tab.space = sp.id; const d = X.resolve(sp.dir, X.home()); if (X.node(d)) this.tab.cwd = d;
        X.setSpace(sp.id); this.renderTabs(); return;
      }
      if (sub === 'explain') {
        if (this.tab.fix) this.xexplain('The last suggestion is still waiting.', this.tab.fix);
        else this.text('Nothing to explain — the last command went fine.');
        return;
      }
      this.text(`xora: unknown command '${sub}'. Try: xora help`, 'k-bad'); return 1;
    }
    c_neofetch() {
      const sp = X.space();
      const art = ['     ▄▄▄       ▄▄▄', '      ▀██▄   ▄██▀ ', '        ▀██▄██▀   ', '         ▄███▄    ', '       ▄██▀ ▀██▄  ', '     ▄██▀     ▀██▄'];
      const info = [
        `<span class="k-user">${esc(S.user.login)}</span>@<span class="k-user">${esc(S.host)}</span>`,
        '-----------',
        `<span class="k-xora">OS</span>: XORA OS 0.1 (Dawn) x86_64`,
        `<span class="k-xora">Kernel</span>: 6.12.0-xora`,
        `<span class="k-xora">Shell</span>: zsh 5.9`,
        `<span class="k-xora">Space</span>: ${esc(sp.name)}`,
        `<span class="k-xora">Devices</span>: ${S.devices.filter(d => d.online).length} online`,
      ];
      for (let i = 0; i < Math.max(art.length, info.length); i++)
        this.print(`<span class="k-xora">${esc((art[i] || '').padEnd(22))}</span>${info[i] || ''}`);
    }

    /* ---------- # plain-words questions ---------- */
    async ask(q) {
      if (!q) { this.text('Ask something after the #, like: # why is the api slow?'); return 0; }
      this.print('<span class="k-xora">[xora]</span> <span class="k-dim">thinking…</span>');
      await sleep(500);
      const t = q.toLowerCase(), sp = X.space();
      const say = s => this.print(`<span class="k-xora">[xora]</span> ${s}`);
      if (/slow|lag|perf/.test(t) && /api/.test(t)) {
        const worker = sp.services.find(s => s.n === 'worker');
        say('The api is answering in about <b>1.8 s</b> per request (normal is under 200 ms).');
        if (worker && worker.s !== 'running') { say('The <b>worker</b> service is stopped, so the api is doing background jobs itself on every check-in.'); this.xexplain('Starting the worker should bring response times back down.', 'xora up'); }
        else say('All services are running. The slowest query is <b>SELECT * FROM checkins</b> with no index on user_id.');
        return 0;
      }
      if (/test|pytest/.test(t)) {
        if (S.dbs.includes('attndi_test')) say('Tests should pass now — the attndi_test database exists. Run <b>pytest</b>.');
        else this.xexplain('Tests fail because the database <b>attndi_test</b> is missing.', 'createdb attndi_test');
        return 0;
      }
      if (/undo|deleted|restore|get back/.test(t)) {
        const s = S.timeline.find(s => !s.restored);
        if (s) this.xexplain(`Your last deletion was <b>${esc(X.pretty(s.path))}</b> (${s.count.toLocaleString()} files), ${X.ago(s.at)}.`, 'xora undo');
        else say('There is nothing deleted that can be restored right now.');
        return 0;
      }
      if (/build|apk|faster/.test(t)) { this.xexplain('Your <b>Office PC</b> is idle and has 3× the CPU. Send the build there.', 'xora fabric run flutter build apk --on office-pc'); return 0; }
      if (/where am i|what space|which space/.test(t)) { say(`You're in Space <span class="k-space">${esc(sp.name)}</span>, folder ${esc(X.pretty(this.tab.cwd))}.`); return 0; }
      if (/disk|space left|storage/.test(t)) { say('You have <b>182 GB</b> free of 512 GB. The biggest folder is ~/attndi/mobile/build (6.1 GB).'); return 0; }
      say('I can answer questions about this Space, its services, tests, builds, devices and deleted files. Try <b># why is the api slow?</b>');
      return 0;
    }
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function lev(a, b) {
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return d[a.length][b.length];
  }
})();
