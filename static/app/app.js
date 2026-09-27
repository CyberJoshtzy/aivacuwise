/* BilisLikas 2.0 shared frontend logic.
   Talks to the FastAPI backend on the same host (served from /static/app/). */
const BL = (() => {
  const TOKEN = 'bl_token';
  const ME = 'bl_me';
  const PRIVACY = 'bl_privacy_ok';

  function store() {
    return localStorage.getItem(TOKEN) ? localStorage : sessionStorage;
  }
  function token() {
    return localStorage.getItem(TOKEN) || sessionStorage.getItem(TOKEN);
  }
  function cachedMe() {
    try { return JSON.parse(store().getItem(ME) || 'null'); } catch (e) { return null; }
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    const t = token();
    if (t) headers['Authorization'] = 'Bearer ' + t;
    if (opts.json !== undefined) {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.json);
    }
    let res;
    try {
      res = await fetch(path, { method: opts.method || 'GET', headers, body: opts.body });
    } catch (e) {
      throw new Error('Cannot reach the BilisLikas server. Check that the laptop server is running.');
    }
    if (res.status === 401 && !opts.allow401) {
      logout();
      throw new Error('Your session has ended. Please sign in again.');
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
    if (!res.ok) {
      let msg = (data && data.detail) ? data.detail : ('Request failed (' + res.status + ')');
      if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(', ');
      throw new Error(msg);
    }
    return data;
  }

  async function login(identifier, password, remember) {
    const body = new URLSearchParams();
    body.set('username', identifier.trim());
    body.set('password', password);
    const res = await fetch('/login', { method: 'POST', body });
    if (!res.ok) {
      if (res.status === 401 || res.status === 400) throw new Error('Incorrect email or password.');
      throw new Error('Sign in failed (' + res.status + '). Check that the server is running.');
    }
    const data = await res.json();
    localStorage.removeItem(TOKEN); sessionStorage.removeItem(TOKEN);
    localStorage.removeItem(ME); sessionStorage.removeItem(ME);
    sessionStorage.removeItem(PRIVACY);
    const s = remember ? localStorage : sessionStorage;
    s.setItem(TOKEN, data.access_token);
    const me = await api('/users/me');
    s.setItem(ME, JSON.stringify(me));
    return me;
  }

  function logout() {
    [localStorage, sessionStorage].forEach((s) => { s.removeItem(TOKEN); s.removeItem(ME); });
    sessionStorage.removeItem(PRIVACY);
    location.href = 'signin.html';
  }

  function homeFor(me) {
    return me && me.role === 'city_admin' ? 'city.html' : 'dashboard.html';
  }

  async function requireAuth(opts = {}) {
    if (!token()) { location.href = 'signin.html'; return new Promise(() => {}); }
    let me;
    try { me = await api('/users/me'); } catch (e) { location.href = 'signin.html'; return new Promise(() => {}); }
    store().setItem(ME, JSON.stringify(me));
    if (!opts.skipPrivacy && sessionStorage.getItem(PRIVACY) !== '1') {
      location.href = 'privacy.html'; return new Promise(() => {});
    }
    if (opts.role && me.role !== opts.role) {
      location.href = homeFor(me); return new Promise(() => {});
    }
    return me;
  }

  function acceptPrivacy() { sessionStorage.setItem(PRIVACY, '1'); }

  const ICONS = {
    live: '<path d="M7 18v-6a5 5 0 0 1 10 0v6"/><path d="M4 18h16v3H4z"/><path d="M12 3v2"/><path d="M4.5 6.5l1.4 1.4"/><path d="M19.5 6.5l-1.4 1.4"/>',
    dash: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c1-3.5 3.5-5.5 6.5-5.5s5.5 2 6.5 5.5"/><circle cx="17" cy="9" r="2.5"/><path d="M17 14.5c2.3 0 4 1.5 4.7 4"/>',
    face: '<path d="M4 8V5a1 1 0 0 1 1-1h3"/><path d="M16 4h3a1 1 0 0 1 1 1v3"/><path d="M20 16v3a1 1 0 0 1-1 1h-3"/><path d="M8 20H5a1 1 0 0 1-1-1v-3"/><circle cx="12" cy="11" r="3"/><path d="M7.5 17c1-2 2.6-3 4.5-3s3.5 1 4.5 3"/>',
    center: '<path d="M3 21h18"/><path d="M5 21V10l7-5 7 5v11"/><path d="M10 21v-6h4v6"/>',
    transfer: '<path d="M4 7h13"/><path d="M14 4l3 3-3 3"/><path d="M20 17H7"/><path d="M10 14l-3 3 3 3"/>',
    tracker: '<circle cx="12" cy="12" r="2"/><path d="M8 8a5.6 5.6 0 0 0 0 8"/><path d="M16 8a5.6 5.6 0 0 1 0 8"/><path d="M5 5a10 10 0 0 0 0 14"/><path d="M19 5a10 10 0 0 1 0 14"/>',
    pin: '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18"/><path d="M12 3a14 14 0 0 0 0 18"/>',
    report: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 13h7"/><path d="M9 17h5"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c1-3.5 3.5-5.5 6.5-5.5s5.5 2 6.5 5.5"/><path d="M17 8v6"/><path d="M14 11h6"/>',
    out: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l-5-5 5-5"/><path d="M5 12h11"/>'
  };
  const svg = (k) => '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[k] + '</svg>';

  // Pages that exist now link normally; the rest show "Soon" until the next batch.
  const NAV = {
    barangay_official: [
      ['live', 'Live Evacuation', 'live.html'],
      ['dash', 'Dashboard', 'dashboard.html'],
      ['people', 'Evacuees', 'evacuees.html'],
      ['face', 'Pre-Registration', 'preregister.html'],
      ['center', 'Evacuation Centers', 'centers.html'],
      ['transfer', 'Transfers', 'transfers.html'],
      ['tracker', 'Trackers', 'trackers.html'],
      ['pin', 'Barangays', 'barangays.html']
    ],
    city_admin: [
      ['globe', 'City Overview', 'city.html'],
      ['center', 'Evacuation Centers', 'centers.html'],
      ['people', 'Evacuees', 'evacuees.html'],
      ['face', 'Pre-Registration', 'preregister.html'],
      ['transfer', 'Transfers', 'transfers.html'],
      ['live', 'Live Evacuation', 'live.html'],
      ['tracker', 'Trackers', 'trackers.html'],
      ['pin', 'Barangays', 'barangays.html'],
      ['report', 'Situation Reports', null],
      ['users', 'User Accounts', null]
    ]
  };

  function renderSidebar(me, active, barangayName) {
    const el = document.getElementById('sidebar');
    if (!el) return;
    const city = me.role === 'city_admin';
    el.className = 'sidebar' + (city ? ' city' : '');
    const items = (NAV[me.role] || NAV.barangay_official).map(([ic, label, href]) => {
      if (!href) return '<span class="soon" aria-disabled="true">' + svg(ic) + label + '<em>Soon</em></span>';
      const cur = href === active ? ' aria-current="page"' : '';
      return '<a href="' + href + '"' + cur + '>' + svg(ic) + label + '</a>';
    }).join('');
    const badge = city
      ? '<div class="role-badge"><div class="kind">Super user</div><div class="who">City Admin</div><div class="sub">' + esc(me.email || me.username) + '</div></div>'
      : '<div class="role-badge"><div class="kind">Signed in</div><div class="who">' + esc(barangayName || 'Barangay') + '</div><div class="sub">' + esc(me.email || me.username) + '</div></div>';
    el.innerHTML =
      '<div class="logo-tile"><img src="/static/logo.png" alt="BilisLikas 2.0"></div>' + badge +
      '<nav class="nav" aria-label="Main">' + items + '</nav>' +
      '<nav class="nav signout" aria-label="Account"><a href="#" id="signout">' + svg('out') + 'Sign Out</a></nav>';
    document.getElementById('signout').addEventListener('click', (e) => { e.preventDefault(); logout(); });
  }

  let toastTimer;
  function toast(msg) {
    let t = document.querySelector('.toast');
    if (t) t.remove();
    t = document.createElement('div');
    t.className = 'toast';
    t.setAttribute('role', 'status');
    t.textContent = msg;
    document.body.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.remove(), 3000);
  }

  // Live updates: the server sends a small "something changed" signal; pages re-fetch.
  function connectLive(onChange, badgeEl) {
    let ws, retry;
    const setBadge = (state) => {
      if (!badgeEl) return;
      badgeEl.className = 'live-badge ' + (state === 'on' ? 'on' : 'off');
      badgeEl.querySelector('.txt').textContent = state === 'on' ? 'Live' : 'Offline, reconnecting';
    };
    const open = () => {
      const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
      ws = new WebSocket(proto + location.host + '/ws/dashboard?token=' + encodeURIComponent(token()));
      ws.onopen = () => setBadge('on');
      ws.onmessage = (ev) => { let m = null; try { m = JSON.parse(ev.data); } catch (e) {} onChange(m); };
      ws.onclose = () => { setBadge('off'); clearTimeout(retry); retry = setTimeout(open, 3000); };
      ws.onerror = () => ws.close();
    };
    open();
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function age(birthdate) {
    if (!birthdate) return null;
    const b = new Date(birthdate);
    if (isNaN(b)) return null;
    const t = new Date();
    let a = t.getFullYear() - b.getFullYear();
    if (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate())) a--;
    return a;
  }
  function parseT(d) {
    if (typeof d === 'string' && /T\d/.test(d) && !/(Z|[+-]\d\d:?\d\d)$/.test(d)) return new Date(d + 'Z');
    return new Date(d);
  }
  function ago(d) {
    const s = Math.max(0, Math.round((Date.now() - parseT(d).getTime()) / 1000));
    if (s < 60) return 'just now';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' hr ago';
    return Math.round(s / 86400) + ' day(s) ago';
  }
  function time(d) {
    const x = d ? parseT(d) : new Date();
    return x.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  }
  function dateTime(d) {
    const x = parseT(d);
    return x.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' + time(x);
  }
  function tone(p) { return p >= 0.95 ? 'red' : p >= 0.8 ? 'amber' : 'green'; }
  const TONE_HEX = { red: '#B91C1C', amber: '#B45309', green: '#15803D' };

  function eyeToggle(input, btn) {
    const openEye = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4A5368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
    const shutEye = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#142C6E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2"/><path d="M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.8 9.8 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
    const set = (shown) => {
      input.type = shown ? 'text' : 'password';
      btn.innerHTML = shown ? shutEye : openEye;
      btn.setAttribute('aria-label', shown ? 'Hide password' : 'Show password');
    };
    set(false);
    btn.addEventListener('click', () => set(input.type === 'password'));
  }

  // Modal dialog. Returns { el, close }. Closes on Escape or scrim click.
  function modal(html, width) {
    const scrim = document.createElement('div');
    scrim.className = 'scrim';
    scrim.innerHTML = '<section class="dialog" role="dialog" aria-modal="true" style="width:min(' + (width || 760) + 'px,100%)">' + html + '</section>';
    const last = document.activeElement;
    const close = () => { scrim.remove(); document.removeEventListener('keydown', onKey); if (last && last.focus) last.focus(); };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) close(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(scrim);
    scrim.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', close));
    const first = scrim.querySelector('input, select, textarea, button');
    if (first) first.focus();
    return { el: scrim, close };
  }

  function confirmBox(opts) {
    return new Promise((resolve) => {
      const m = modal(
        '<div style="padding:28px 30px;display:flex;flex-direction:column;gap:14px">' +
        '<h2 style="font-size:21px;font-weight:800;color:var(--text)">' + esc(opts.title) + '</h2>' +
        '<p style="font-size:15px;line-height:1.6;color:#3D4659">' + esc(opts.text) + '</p>' +
        '<div class="form-error" hidden></div>' +
        '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:6px">' +
        '<button type="button" class="btn btn-ghost" data-close>Cancel</button>' +
        '<button type="button" class="btn ' + (opts.danger ? 'btn-danger' : 'btn-primary') + '" data-ok>' + esc(opts.ok || 'Confirm') + '</button></div></div>', 500);
      const okBtn = m.el.querySelector('[data-ok]');
      const errBox = m.el.querySelector('.form-error');
      m.el.querySelector('[data-close]').addEventListener('click', () => resolve(false));
      okBtn.addEventListener('click', async () => {
        if (!opts.action) { m.close(); resolve(true); return; }
        okBtn.disabled = true;
        try { await opts.action(); m.close(); resolve(true); }
        catch (e) { errBox.textContent = e.message; errBox.hidden = false; okBtn.disabled = false; }
      });
    });
  }

  return { parseT, ago, modal, confirmBox, api, login, logout, requireAuth, acceptPrivacy, homeFor, cachedMe, token, renderSidebar, toast, connectLive, esc, age, time, dateTime, tone, TONE_HEX, eyeToggle };
})();
