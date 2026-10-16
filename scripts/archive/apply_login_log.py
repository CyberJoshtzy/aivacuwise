"""Records every sign-in attempt and adds a Sign-in history section to User Accounts."""
s = open('main.py').read()
if 'login_log.record' not in s:
    old_sig = 'def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):'
    assert old_sig in s, 'login function not found in main.py'
    s = s.replace(old_sig, 'def login(request: _LLRequest, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):', 1)
    s = s.replace('@app.post("/login", response_model=schemas.Token)', 'from fastapi import Request as _LLRequest\nimport login_log\n\n\n@app.post("/login", response_model=schemas.Token)', 1)
    a = '        raise HTTPException(status_code=401, detail="Incorrect username or password")'
    assert a in s, 'wrong-password line not found'
    s = s.replace(a, '        login_log.record(db, request, user, form_data.username, "failed", "Wrong email or password")\n' + a, 1)
    a = '    if status == "pending":\n'
    if a in s:
        s = s.replace(a, a + '        login_log.record(db, request, user, form_data.username, "blocked", "Waiting for approval")\n', 1)
    a = '    if status in ("rejected", "disabled"):\n'
    if a in s:
        s = s.replace(a, a + '        login_log.record(db, request, user, form_data.username, "blocked", "Account " + status)\n', 1)
    a = '    access_token = auth.create_access_token(data={"sub": user.username})'
    assert a in s, 'token line not found'
    s = s.replace(a, '    login_log.record(db, request, user, form_data.username, "success")\n' + a, 1)
    s += '\napp.include_router(login_log.router)\n'
    open('main.py', 'w').write(s)
    print('main.py: sign-ins are now recorded')
else:
    print('main.py: already done')

h = open('static/app/accounts.html').read()
if 'id="logRows"' not in h:
    panel = '''    <section class="panel" id="logPanel">
      <div class="panel-head"><h2>Sign-in history</h2>
        <div class="tools">
          <div class="search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
            <input id="lq" class="input" type="search" placeholder="Search name or email" aria-label="Search sign-in history"></div>
          <select id="lR" class="input" style="font-size:14px" aria-label="Filter by result"><option value="">All results</option><option value="success">Signed in</option><option value="failed">Wrong password</option><option value="blocked">Blocked</option></select>
          <select id="lD" class="input" style="font-size:14px" aria-label="Filter by date"><option value="">All dates</option><option value="1">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
        </div></div>
      <div class="table-wrap" style="max-height:520px;overflow-y:auto"><table class="data"><thead><tr><th>Date and time</th><th>Name</th><th>Barangay / Office</th><th>Result</th><th>Device</th><th>IP address</th></tr></thead><tbody id="logRows"></tbody></table></div>
    </section>
'''
    h = h.replace('  </main>', panel + '  </main>', 1)
    js = '''
  // ---- sign-in history ----
  let logs = [];
  const RES = { success: ['Signed in', '#E8F7EE', '#15803D'], failed: ['Wrong password', '#FDECEC', '#B91C1C'], blocked: ['Blocked', '#FFF7ED', '#B45309'] };
  async function loadLogs() {
    try { logs = await BL.api('/admin/login_logs') || []; } catch (e) { logs = []; }
    drawLogs();
  }
  function drawLogs() {
    const q = $('lq').value.trim().toLowerCase(), r = $('lR').value, d = Number($('lD').value) || 0;
    const since = d ? (() => { const x = new Date(); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - (d - 1)); return x.getTime(); })() : 0;
    const list = logs.filter((l) => (!r || l.result === r) && (!since || BL.parseT(l.time).getTime() >= since) && (!q || (String(l.name || '') + ' ' + String(l.email || '')).toLowerCase().includes(q)));
    $('logRows').innerHTML = list.map((l) => { const k = RES[l.result] || [l.result, '#EEF1F6', '#6B7280'], t = BL.parseT(l.time);
      return '<tr><td style="white-space:nowrap"><strong>' + t.toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' }) + '</strong><div style="font-size:12px;color:var(--muted)">' + t.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit', second: '2-digit' }) + '</div></td>' +
        '<td><strong style="color:var(--navy)">' + BL.esc(l.name || '-') + '</strong><div style="font-size:12px;color:var(--muted)">' + BL.esc(l.email || '') + '</div></td>' +
        '<td>' + BL.esc(l.where) + '<div style="font-size:12px;color:var(--muted)">' + BL.esc(l.position) + '</div></td>' +
        '<td><span class="st" style="background:' + k[1] + ';color:' + k[2] + '">' + k[0] + '</span>' + (l.detail && l.result !== 'success' ? '<div style="font-size:12px;color:var(--muted)">' + BL.esc(l.detail) + '</div>' : '') + '</td>' +
        '<td style="font-size:13px">' + BL.esc(l.device || '-') + '</td><td style="font-size:13px">' + BL.esc(l.ip || '-') + '</td></tr>'; }).join('')
      || '<tr><td colspan="6"><div class="empty">No sign-ins recorded yet.</div></td></tr>';
  }
  ['lq', 'lR', 'lD'].forEach((id) => $(id).addEventListener(id === 'lq' ? 'input' : 'change', drawLogs));
  loadLogs();
'''
    a = '  await load();'
    i = h.rfind(a)
    assert i != -1, 'load call not found in accounts.html'
    h = h[:i] + js + h[i:]
    h = h.replace("document.querySelector('section.panel').hidden = true;", "document.querySelectorAll('section.panel').forEach((x) => { x.hidden = true; });", 1)
    open('static/app/accounts.html', 'w').write(h)
    print('accounts.html: Sign-in history added')
else:
    print('accounts.html: already done')
