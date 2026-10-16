"""Evacuation History page for the City Admin; removes Situation Reports from the sidebar."""
s = open('main.py').read()
if 'import history' not in s:
    s += '\nimport history\napp.include_router(history.router)\n'
    open('main.py', 'w').write(s)
print('main.py ready')
a = open('static/app/app.js').read()
old = "      ['report', 'Situation Reports', null],\n"
if old in a:
    a = a.replace(old, "      ['report', 'Evacuation History', 'history.html'],\n", 1)
    print('app.js: Situation Reports removed, Evacuation History added')
elif 'history.html' in a:
    print('app.js: already done')
else:
    print('app.js: Situation Reports line NOT FOUND')
open('static/app/app.js', 'w').write(a)
c = open('static/app/city.html').read()
old = '<h2>Evacuation history</h2>'
if old in c:
    c = c.replace(old, '<h2><a class="h-link" href="history.html">Evacuation history <span>&rarr;</span></a></h2>', 1)
    open('static/app/city.html', 'w').write(c)
    print('city.html: title linked')
else:
    print('city.html: title NOT FOUND (maybe already linked)')
