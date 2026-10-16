s = open('main.py').read()
if 'import barangay_delete' not in s:
    s += '\nimport barangay_delete\napp.include_router(barangay_delete.router)\n'
    open('main.py', 'w').write(s)
print('main.py ready')
p = 'static/app/barangays.html'
h = open(p).read()
i = h.find('  function del(b) {')
j = h.find("  $('add').addEventListener('click'", i)
if i == -1 or j == -1:
    print('barangays.html: delete code NOT FOUND')
else:
    h = h[:i] + '''  async function del(b) {
    let u = null;
    try { u = await BL.api('/barangays/' + b.id + '/usage'); } catch (e) { BL.toast(e.message); return; }
    if (u.active) {
      BL.confirmBox({ title: 'Cannot delete ' + b.name + ' yet', text: 'An evacuation is still running in this barangay. Finish it first in Live Evacuation.', ok: 'OK' });
      return;
    }
    const parts = [];
    const add = (n, one, many) => { if (n) parts.push(n + ' ' + (n === 1 ? one : many)); };
    add(u.residents, 'registered resident', 'registered residents');
    add(u.households, 'family', 'families');
    add(u.centers, 'evacuation center', 'evacuation centers');
    add(u.accounts, 'official account', 'official accounts');
    add(u.evacuations, 'evacuation record', 'evacuation records');
    BL.confirmBox({
      title: 'Are you sure you want to delete ' + b.name + '?',
      text: parts.length ? 'There are still ' + parts.join(', ') + ' linked to this barangay. Deleting it will also remove all of these from the system. This cannot be undone.'
        : 'This barangay will be removed from the list. This cannot be undone.',
      ok: 'Yes, Delete', danger: true,
      action: () => BL.api('/barangays/' + b.id + '/force', { method: 'DELETE' })
    }).then((ok) => { if (ok) { BL.toast(b.name + ' was deleted.'); load(); } });
  }

''' + h[j:]
    open(p, 'w').write(h)
    print('barangays.html: new confirmation added')
