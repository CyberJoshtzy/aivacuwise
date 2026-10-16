"""Relief & Medicine: page only for barangay officials; City Admin sees the distribution log on City Overview."""
a = open('static/app/app.js').read()
old = "      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Relief & Medicine', 'relief.html'],\n      ['report', 'Situation Reports', null],"
if old in a:
    a = a.replace(old, "      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Situation Reports', null],", 1)
    print('app.js: removed from City Admin menu')
for pat in ("display|live)", "display)"):
    if pat in a and 'relief)' not in a:
        a = a.replace(pat, pat[:-1] + "|relief)", 1)
open('static/app/app.js', 'w').write(a)
print('app.js: relief.html blocked for City Admin' if '|relief)' in a else 'app.js: block NOT FOUND')

c = open('static/app/city.html').read()
if 'id="rlog"' not in c:
    c = c.replace('<a class="note no-print" href="relief.html">Open full log</a>', '<span class="note" id="reliefNote"></span>', 1)
    panel = '''    <section class="panel">
      <div class="panel-head"><h2>Relief &amp; medicine distribution log</h2>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <select id="rlB" class="input" style="width:200px;height:40px;font-size:14px" aria-label="Filter by barangay"><option value="">All barangays</option></select>
          <select id="rlC" class="input" style="width:170px;height:40px;font-size:14px" aria-label="Filter by category"><option value="">All categories</option><option>Food</option><option>Water</option><option>Medicine</option><option>Hygiene</option><option>Other</option></select>
        </div></div>
      <div class="table-wrap" style="max-height:480px;overflow-y:auto"><table class="data"><thead><tr><th scope="col">Date</th><th scope="col">Barangay</th><th scope="col">Item</th><th scope="col">Quantity</th><th scope="col">Evacuation center</th><th scope="col">Served</th><th scope="col">Recorded by</th></tr></thead><tbody id="rlog"></tbody></table></div>
    </section>

'''
    anchor = '''    <section class="panel">
      <div class="panel-head"><h2>Evacuation centers</h2>'''
    assert anchor in c, 'centers panel not found'
    c = c.replace(anchor, panel + anchor, 1)
    js = '''
  // Relief and medicine distribution log (recorded by barangay officials)
  let rlogRows = [];
  const RLC = { Food: ['#FFF4E5', '#B45309'], Water: ['#E0F2FE', '#0369A1'], Medicine: ['#FDECEC', '#B91C1C'], Hygiene: ['#E8F7EE', '#15803D'], Other: ['#EEF2FF', '#142C6E'] };
  function drawRlog() {
    const fb = Number(document.getElementById('rlB').value) || null, fc = document.getElementById('rlC').value;
    const shown = rlogRows.filter((r) => (!fb || r.barangay_id === fb) && (!fc || r.category === fc));
    document.getElementById('rlog').innerHTML = shown.map((r) => {
      const col = RLC[r.category] || RLC.Other;
      return '<tr><td style="white-space:nowrap;font-size:13px">' + BL.dateTime(r.given_at) + '</td><td><strong style="color:var(--navy)">' + BL.esc(r.barangay || '-') + '</strong></td>' +
        '<td><span style="font-size:11px;font-weight:800;padding:2px 8px;border-radius:999px;background:' + col[0] + ';color:' + col[1] + '">' + BL.esc(r.category) + '</span> <strong>' + BL.esc(r.item) + '</strong>' + (r.notes ? '<div style="font-size:12px;color:var(--muted)">' + BL.esc(r.notes) + '</div>' : '') + '</td>' +
        '<td style="white-space:nowrap"><strong>' + Number(r.quantity).toLocaleString() + '</strong> ' + BL.esc(r.unit) + '</td>' +
        '<td style="font-size:13px">' + BL.esc(r.center || 'House-to-house') + '</td><td>' + (r.recipients || '-') + '</td><td style="font-size:13px">' + BL.esc(r.recorded_by || '-') + '</td></tr>';
    }).join('') || '<tr><td colspan="7"><div class="empty">No relief or medicine recorded yet.</div></td></tr>';
  }
  async function loadRlog() {
    try { rlogRows = await BL.api('/relief') || []; } catch (e) { rlogRows = []; }
    const sel = document.getElementById('rlB'), keep = sel.value;
    const seen = {}; rlogRows.forEach((r) => { seen[r.barangay_id] = r.barangay; });
    sel.innerHTML = '<option value="">All barangays</option>' + Object.keys(seen).sort((x, y) => String(seen[x]).localeCompare(String(seen[y]), undefined, { numeric: true })).map((id) => '<option value="' + id + '">' + BL.esc(seen[id]) + '</option>').join('');
    sel.value = keep;
    drawRlog();
  }
  document.getElementById('rlB').addEventListener('change', drawRlog);
  document.getElementById('rlC').addEventListener('change', drawRlog);
  loadRlog();
'''
    anchor2 = '  loadRelief();\n'
    assert anchor2 in c, 'run apply_relief.py first'
    c = c.replace(anchor2, anchor2 + js, 1)
    c = c.replace('BL.connectLive(() => { load(); loadRelief(); }', 'BL.connectLive(() => { load(); loadRelief(); loadRlog(); }', 1)
    open('static/app/city.html', 'w').write(c)
    print('city.html: distribution log added')
