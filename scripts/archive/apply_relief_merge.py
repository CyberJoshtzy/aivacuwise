"""City Overview: remove three helper texts, merge the two relief panels into one compact panel,
and give the City Admin a 'Relief & Medicine' sidebar item that opens the full log (read-only)."""
import re
c = open('static/app/city.html').read()

# 1. remove helper texts
for t in ['<p style="font-size:13px;color:var(--muted);margin:0">Most unaccounted first. Click a row to filter the centers below.</p>',
          '<p style="font-size:13px;color:var(--muted);margin:0">Click a barangay to see every item given.</p>']:
    print('removed text' if t in c else 'text not found (ok if already gone)')
    c = c.replace(t, '')
c = c.replace("""      $('accSum').innerHTML = '<span class="chip" style="background:#E8F7EE;color:#15803D">' + brgys.length + ' barangay' + (brgys.length === 1 ? '' : 's') + ' with an account</span>' +
        (none.length""", """      $('accSum').innerHTML = (none.length""", 1)

# 2. remove the two old relief panels (HTML)
c = re.sub(r'    <section class="panel">\n      <div class="panel-head"><h2>Relief &amp; medicine per barangay</h2>.*?</section>\n\n', '', c, count=1, flags=re.S)
c = re.sub(r'    <section class="panel">\n      <div class="panel-head"><h2>Relief &amp; medicine distribution log</h2>.*?</section>\n\n', '', c, count=1, flags=re.S)
# and their scripts
c = re.sub(r'\n  // Relief and medicine per barangay\n.*?\n  loadRelief\(\);\n', '\n', c, count=1, flags=re.S)
c = re.sub(r'\n  // Relief and medicine distribution log.*?\n  loadRlog\(\);\n', '\n', c, count=1, flags=re.S)
c = c.replace('BL.connectLive(() => { load(); loadRelief(); loadRlog(); }', 'BL.connectLive(() => { load(); loadReliefBox(); }', 1)
c = c.replace('BL.connectLive(() => { load(); loadRelief(); }', 'BL.connectLive(() => { load(); loadReliefBox(); }', 1)

# 3. one merged panel
if 'id="reliefBox"' not in c:
    panel = '''    <section class="panel">
      <div class="panel-head"><h2><a class="h-link" href="relief.html">Relief &amp; medicine <span aria-hidden="true">&rarr;</span></a></h2><span class="note" id="reliefNote"></span></div>
      <div class="table-wrap"><table class="data"><thead><tr><th scope="col" style="width:200px">Barangay</th><th scope="col">Items given (total)</th><th scope="col" style="width:130px">Persons served</th><th scope="col" style="width:170px">Last given</th></tr></thead><tbody id="reliefBox"></tbody></table></div>
    </section>

'''
    anchor = '    <section class="panel">\n      <div class="panel-head"><h2>'
    i = c.find('Evacuation centers', c.find('<section class="panel">\n      <div class="panel-head"><h2>', c.find('id="alerts"')))
    j = c.rfind('    <section class="panel">', 0, i)
    assert j != -1, 'centers panel not found'
    c = c[:j] + panel + c[j:]
    js = '''
  // Relief and medicine: one compact panel (full log on the Relief & Medicine page)
  async function loadReliefBox() {
    let rs = [];
    try { rs = await BL.api('/relief/summary') || []; } catch (e) { rs = []; }
    const names = {}; ((data && data.summary && data.summary.barangays) || []).forEach((b) => { names[b.id] = b.name; });
    const COL = { Food: ['#FFF4E5', '#B45309'], Water: ['#E0F2FE', '#0369A1'], Medicine: ['#FDECEC', '#B91C1C'], Hygiene: ['#E8F7EE', '#15803D'], Other: ['#EEF2FF', '#142C6E'] };
    const chip = (i) => { const k = COL[i.category] || COL.Other; return '<span style="display:inline-block;margin:2px 4px 2px 0;font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px;background:' + k[0] + ';color:' + k[1] + '">' + BL.esc(i.item) + ' ' + Number(i.quantity).toLocaleString() + ' ' + BL.esc(i.unit) + '</span>'; };
    rs.sort((a, b) => String(names[a.barangay_id] || '').localeCompare(String(names[b.barangay_id] || ''), undefined, { numeric: true }));
    const served = rs.reduce((s, r) => s + (r.recipients || 0), 0);
    document.getElementById('reliefNote').textContent = rs.length ? rs.length + ' barangay' + (rs.length === 1 ? '' : 's') + ', ' + served + ' persons served' : '';
    document.getElementById('reliefBox').innerHTML = rs.map((r) => '<tr><td><strong style="color:var(--navy)">' + BL.esc(names[r.barangay_id] || 'Barangay #' + r.barangay_id) + '</strong></td>' +
      '<td>' + r.items.slice(0, 6).map(chip).join('') + (r.items.length > 6 ? '<a href="relief.html" style="font-size:12px;font-weight:700">+' + (r.items.length - 6) + ' more</a>' : '') + '</td>' +
      '<td>' + (r.recipients || '-') + '</td><td style="font-size:13px;white-space:nowrap">' + (r.last_given ? BL.dateTime(r.last_given) : '-') + '</td></tr>').join('') ||
      '<tr><td colspan="4"><div class="empty">No relief or medicine recorded yet.</div></td></tr>';
  }
  loadReliefBox();
'''
    a2 = '  BL.connectLive('
    k = c.rfind(a2)
    c = c[:k] + js.lstrip('\n') + c[k:]
open('static/app/city.html', 'w').write(c)
print('city.html: relief merged into one panel')

# 4. sidebar item for City Admin, page allowed again (read-only log)
a = open('static/app/app.js').read()
a = a.replace('|relief)', ')', 1)
if "['report', 'Relief & Medicine', 'relief.html'],\n      ['report', 'Situation Reports', null]" not in a:
    a = a.replace("      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Situation Reports', null],",
                  "      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Relief & Medicine', 'relief.html'],\n      ['report', 'Situation Reports', null],", 1)
open('static/app/app.js', 'w').write(a)
print('app.js: Relief & Medicine added for City Admin')

r = open('static/app/relief.html').read()
if 'cityLogOnly' not in r:
    r = r.replace("  if (city) {\n    $('brgyWrap').hidden = false;", """  if (city) { /* cityLogOnly: City Admin sees the log only */
    document.querySelector('.grid2 > section.panel').style.display = 'none';
    document.querySelector('.grid2').style.gridTemplateColumns = '1fr';
    document.querySelector('h1').textContent = 'Relief & Medicine Log';
    document.querySelectorAll('#rows').forEach(() => {});
  }
  if (city) {
    $('brgyWrap').hidden = false;""", 1)
    r = r.replace("'<td style=\"text-align:right\"><button type=\"button\" class=\"btn btn-del btn-sm\" data-del=\"' + r.id + '\">Remove</button></td></tr>'",
                  "'<td style=\"text-align:right\">' + (city ? '<span style=\"font-size:12px;color:var(--muted)\">' + BL.esc(r.recorded_by || '') + '</span>' : '<button type=\"button\" class=\"btn btn-del btn-sm\" data-del=\"' + r.id + '\">Remove</button>') + '</td></tr>'", 1)
    open('static/app/relief.html', 'w').write(r)
    print('relief.html: City Admin sees the log only')

# 5. City Overview panels: show a few rows, scroll for the rest (full lists on each page)
c = open('static/app/city.html').read()
if 'panel scroll limits' not in c:
    c = c.replace('</style>', '''/* panel scroll limits */
main .panel .table-wrap { max-height: 340px; overflow-y: auto; }
main .panel .table-wrap thead th { position: sticky; top: 0; z-index: 1; background: var(--bg, #F4F6FA); }
#alerts { max-height: 340px; overflow-y: auto; }
</style>''', 1)
    open('static/app/city.html', 'w').write(c)
print('city.html: long lists now scroll inside their panels')
