"""Adds the relief and medicine log: model in models.py (synced to the cloud hub), router in main.py,
and a 'Relief & Medicine' item in the sidebar for barangay officials and the City Admin."""
m = open('models.py').read()
if 'class ReliefRecord' not in m:
    model = '''class ReliefRecord(Base):
    __tablename__ = "relief_records"
    id = Column(Integer, primary_key=True)
    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=False, index=True)
    evacuation_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=True)
    category = Column(String, nullable=False)
    item = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    recipients = Column(Integer, nullable=True)
    given_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(String, nullable=True)


'''
    i = m.index('SYNCED_MODELS = [')
    m = m[:i] + model + m[i:]
    m = m.replace('Transfer, Tracker, TrackerPing, GpsPing, Incident]', 'Transfer, Tracker, TrackerPing, GpsPing, Incident, ReliefRecord]', 1)
    assert 'Incident, ReliefRecord]' in m, 'SYNCED_MODELS list not found'
    open('models.py', 'w').write(m)
    print('models.py updated')

s = open('main.py').read()
if 'import relief' not in s:
    s += '\nimport relief\napp.include_router(relief.router)\n'
    open('main.py', 'w').write(s)
    print('main.py updated')

a = open('static/app/app.js').read()
if 'relief.html' not in a:
    a = a.replace("      ['pin', 'Barangays', 'barangays.html']\n    ],", "      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Relief & Medicine', 'relief.html']\n    ],", 1)
    a = a.replace("      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Situation Reports', null],", "      ['pin', 'Barangays', 'barangays.html'],\n      ['report', 'Relief & Medicine', 'relief.html'],\n      ['report', 'Situation Reports', null],", 1)
    open('static/app/app.js', 'w').write(a)
    print('app.js updated (' + str(a.count('relief.html')) + ' menus)')

# ---- City Overview: relief and medicine per barangay ----
c = open('static/app/city.html').read()
if 'id="relief"' not in c:
    panel = '''    <section class="panel">
      <div class="panel-head"><h2>Relief &amp; medicine per barangay</h2><a class="note no-print" href="relief.html">Open full log</a></div>
      <p style="font-size:13px;color:var(--muted);margin:0">Click a barangay to see every item given.</p>
      <div class="table-wrap"><table class="data"><thead><tr><th scope="col">Barangay</th><th scope="col">Food</th><th scope="col">Water</th><th scope="col">Medicine</th><th scope="col">Hygiene</th><th scope="col">Other</th><th scope="col">Persons served</th><th scope="col">Last given</th></tr></thead><tbody id="relief"></tbody></table></div>
    </section>

'''
    anchor = '''    <section class="panel">
      <div class="panel-head"><h2>Evacuation centers</h2>'''
    assert anchor in c, 'centers panel not found in city.html'
    c = c.replace(anchor, panel + anchor, 1)
    js = '''
  // Relief and medicine per barangay
  let reliefData = [];
  async function loadRelief() {
    try { reliefData = await BL.api('/relief/summary') || []; } catch (e) { reliefData = []; }
    const names = {}; ((data && data.summary && data.summary.barangays) || []).forEach((b) => { names[b.id] = b.name; });
    const cats = ['Food', 'Water', 'Medicine', 'Hygiene', 'Other'];
    const top = (r, cat) => r.items.filter((i) => i.category === cat).slice(0, 2).map((i) => BL.esc(i.item) + ' <strong>' + Number(i.quantity).toLocaleString() + '</strong> ' + BL.esc(i.unit)).join('<br>') || '<span style="color:var(--muted)">-</span>';
    const list = reliefData.slice().sort((a, b) => String(names[a.barangay_id] || '').localeCompare(String(names[b.barangay_id] || ''), undefined, { numeric: true }));
    document.getElementById('relief').innerHTML = list.map((r) => '<tr class="clickable" data-rb="' + r.barangay_id + '"><td><strong style="color:var(--navy)">' + BL.esc(names[r.barangay_id] || 'Barangay #' + r.barangay_id) + '</strong></td>' +
      cats.map((k) => '<td style="font-size:13px">' + top(r, k) + '</td>').join('') +
      '<td>' + (r.recipients || '-') + '</td><td style="white-space:nowrap;font-size:13px">' + (r.last_given ? BL.dateTime(r.last_given) : '-') + '</td></tr>').join('') ||
      '<tr><td colspan="8"><div class="empty">No relief or medicine recorded yet. Barangay officials record them on the Relief &amp; Medicine page.</div></td></tr>';
    document.querySelectorAll('#relief tr[data-rb]').forEach((tr) => tr.addEventListener('click', () => {
      const r = reliefData.find((x) => x.barangay_id === Number(tr.dataset.rb)); if (!r) return;
      BL.modal('<div class="dialog-head"><h2>' + BL.esc(names[r.barangay_id] || 'Barangay') + ': relief &amp; medicine</h2><button type="button" class="btn btn-ghost" data-close>Close</button></div>' +
        '<div class="dialog-body"><table class="data"><thead><tr><th>Category</th><th>Item</th><th>Total given</th></tr></thead><tbody>' +
        r.items.map((i) => '<tr><td>' + BL.esc(i.category) + '</td><td><strong>' + BL.esc(i.item) + '</strong></td><td>' + Number(i.quantity).toLocaleString() + ' ' + BL.esc(i.unit) + '</td></tr>').join('') +
        '</tbody></table><p style="font-size:13px;color:var(--muted);margin-top:10px">' + r.records + ' records, ' + (r.recipients || 0) + ' persons served.</p></div>', 720);
    }));
  }
'''
    anchor2 = '  BL.connectLive(() => load(), '
    assert anchor2 in c, 'connectLive line not found in city.html'
    c = c.replace(anchor2, js + '  loadRelief();\n  BL.connectLive(() => { load(); loadRelief(); }, //', 1)
    c = c.replace("  BL.connectLive(() => { load(); loadRelief(); }, //$('live'));", "  BL.connectLive(() => { load(); loadRelief(); }, $('live'));", 1)
    c = c.replace("  BL.connectLive(() => { load(); loadRelief(); }, //null);", "  BL.connectLive(() => { load(); loadRelief(); }, null);", 1)
    open('static/app/city.html', 'w').write(c)
    print('city.html updated')
