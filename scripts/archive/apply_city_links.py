"""Undo the barangay page, then make City Overview titles link to their pages,
with a 'Back to City Overview' button on those pages (City Admin only)."""
import os
c = open('static/app/city.html').read()

# 1. undo apply_barangay_page.py
c = c.replace("      const pick = () => { location.href = 'barangay.html?id=' + tr.dataset.id; };",
              "      const pick = () => { const id = Number(tr.dataset.id); filter = filter === id ? null : id; render(); };", 1)
c = c.replace('Most unaccounted first. Click a barangay to open its full details.', 'Most unaccounted first. Click a row to filter the centers below.', 1)
c = c.replace("    document.querySelectorAll('#relief tr[data-rb]').forEach((tr) => tr.addEventListener('click', () => { location.href = 'barangay.html?id=' + tr.dataset.rb + '#relief'; }));\n    if (false) document", "    document", 1)
c = c.replace('<p style="font-size:13px;color:var(--muted);margin:0">Click a barangay to open its full details.</p>', '<p style="font-size:13px;color:var(--muted);margin:0">Click a barangay to see every item given.</p>', 1)
c = c.replace('#brgys tr.clickable, #relief tr.clickable { cursor: pointer; }\n#brgys tr.clickable:hover td, #relief tr.clickable:hover td { background: #F6F8FD; }\n', '', 1)
if os.path.exists('static/app/barangay.html'):
    os.remove('static/app/barangay.html')
for f in ('apply_barangay_page.py',):
    if os.path.exists(f):
        os.remove(f)
print('undo: barangay page removed')

# 2. section titles become links
n = 0
links = [
    ('<h2>Barangays</h2>', 'barangays.html', 'Barangays'),
    ('<h2>Evacuation centers</h2>', 'centers.html', 'Evacuation centers'),
    ('<h2>Priority evacuees still unaccounted</h2>', 'evacuees.html', 'Priority evacuees still unaccounted'),
    ('<div class="label">Barangays</div>', 'barangays.html', None),
    ('<div class="label">Accounted</div>', 'evacuees.html', None),
    ('<div class="label">Unaccounted</div>', 'evacuees.html', None),
    ('<div class="label">Evacuation centers</div>', 'centers.html', None),
    ('<div class="label">Trackers reporting</div>', 'trackers.html', None),
]
for old, href, title in links:
    if old in c:
        if title:
            new = '<h2><a class="h-link" href="' + href + '">' + title + ' <span aria-hidden="true">&rarr;</span></a></h2>'
        else:
            label = old[len('<div class="label">'):-len('</div>')]
            new = '<div class="label"><a class="h-link" href="' + href + '">' + label + ' <span aria-hidden="true">&rarr;</span></a></div>'
        c = c.replace(old, new, 1)
        n += 1
if '.h-link {' not in c:
    c = c.replace('</style>', '.h-link { color: inherit; text-decoration: none; }\n.h-link span { opacity: .45; transition: opacity .15s, margin .15s; }\n.h-link:hover { text-decoration: underline; color: var(--navy); }\n.h-link:hover span { opacity: 1; margin-left: 4px; }\n</style>', 1)
open('static/app/city.html', 'w').write(c)
print('city.html: %d titles linked' % n)

# 3. back button on the other City Admin pages
a = open('static/app/app.js').read()
anchor = "    document.getElementById('signout').addEventListener('click', (e) => { e.preventDefault(); logout(); });\n    startSyncBadge();"
if 'bl-back-city' not in a:
    assert anchor in a, 'sidebar code not found in app.js'
    a = a.replace(anchor, anchor + """
    if (city && active !== 'city.html' && !document.getElementById('bl-back-city')) {
      const main = document.querySelector('main');
      if (main) {
        const b = document.createElement('a');
        b.id = 'bl-back-city'; b.href = 'city.html'; b.className = 'no-print';
        b.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/></svg>Back to City Overview';
        b.style.cssText = 'align-self:flex-start;display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 14px;margin-bottom:4px;border-radius:10px;border:2px solid var(--navy);background:#FFFFFF;color:var(--navy);font-size:14px;font-weight:800;text-decoration:none;width:max-content';
        main.insertBefore(b, main.firstChild);
      }
    }""", 1)
    open('static/app/app.js', 'w').write(a)
print('app.js: back button ready')
