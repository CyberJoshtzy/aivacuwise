"""Connects the barangay official side to the City Hall changes.

1. Undoes restore_barangay_pages.py if it was run (barangay officials use the shared pages again).
2. Hides the 'Synced with cloud' badge and the green 'Live' badges for everyone.
3. Evacuation History for barangay officials: their own barangay only, view only.
"""
import os, re

a = open('static/app/app.js').read()
# 1. undo the restore
n = 0
for page in ('evacuees.html', 'centers.html', 'barangays.html'):
    if "'brgy-" + page + "'" in a:
        a = a.replace("'brgy-" + page + "'", "'" + page + "'"); n += 1
    if os.path.exists('static/app/brgy-' + page):
        os.remove('static/app/brgy-' + page)
a = re.sub(r"    /\* brgy-redirect \*/[^\n]*\n", '', a)
print('1. restore undone' if n else '1. restore was not run, nothing to undo')

# 2. hide sync badge and live badges
a = a.replace('    if (!city) startSyncBadge();', '    /* sync badge hidden */', 1)
a = a.replace('    startSyncBadge();\n', '    /* sync badge hidden */\n', 1)
if 'live-badge-hidden' not in a:
    a += """
/* live-badge-hidden: the green Live badges are hidden on every page */
(function () {
  if (/(display|entrance)\\.html$/.test(location.pathname)) return;
  var st = document.createElement('style');
  st.textContent = '.live-badge { display: none !important; }';
  document.head.appendChild(st);
})();
"""
print('2. sync badge and Live badges hidden')

# 3. evacuation history in the barangay official sidebar
start = a.index('barangay_official: [')
end = a.index('\n    ]', start)
nav = a[start:end]
if 'history.html' not in nav:
    nav = nav.rstrip() + ",\n      ['report', 'Evacuation History', 'history.html']"
    a = a[:start] + nav + a[end:]
open('static/app/app.js', 'w').write(a)

h = open('history.py').read()
if 'own barangay only' not in h:
    h = h.replace('''def _admin(user):
    if _role(user) != 'city_admin':
        raise HTTPException(status_code=403, detail='Only the City Admin can view the evacuation history.')''',
'''def _admin(user):  # own barangay only for officials (view), everything for the City Admin
    pass


def _city(user):
    if _role(user) != 'city_admin':
        raise HTTPException(status_code=403, detail='Only the City Admin can delete evacuation records.')''', 1)
    h = h.replace('''    if barangay_id:
        q = q.filter(I.barangay_id == barangay_id)''', '''    if _role(user) != 'city_admin':
        q = q.filter(I.barangay_id == user.barangay_id)
    elif barangay_id:
        q = q.filter(I.barangay_id == barangay_id)''', 1)
    h = h.replace('''        raise HTTPException(status_code=404, detail='Evacuation record not found.')
    names = _names(db)''', '''        raise HTTPException(status_code=404, detail='Evacuation record not found.')
    if _role(user) != 'city_admin' and i.barangay_id != user.barangay_id:
        raise HTTPException(status_code=403, detail='You can only view your own barangay.')
    names = _names(db)''', 1)
    h = h.replace('''def history_delete(iid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _admin(user)''', '''def history_delete(iid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _city(user)''', 1)
    open('history.py', 'w').write(h)
s = open('static/app/history.html').read()
if 'brgyView' not in s:
    s = s.replace("  const me = await BL.requireAuth({ role: 'city_admin' });\n  BL.renderSidebar(me, 'history.html');",
                  "  const me = await BL.requireAuth();\n  const city = me.role === 'city_admin'; /* brgyView */\n  BL.renderSidebar(me, 'history.html');\n  if (!city) { document.getElementById('fB').style.display = 'none'; }", 1)
    s = s.replace('''<button type="button" class="btn btn-del" data-del="' + i.id + '">Delete</button>''', '''' + (city ? '<button type="button" class="btn btn-del" data-del="' + i.id + '">Delete</button>' : '') + \'''', 1)
    open('static/app/history.html', 'w').write(s)
print('3. Evacuation History added for barangay officials (own barangay, view only)')
