with open('main.py') as f:
    content = f.read()

changed = False

if 'from fastapi.staticfiles import StaticFiles' not in content:
    content = 'from fastapi.staticfiles import StaticFiles\n' + content
    changed = True
    print('main.py: StaticFiles import added')
else:
    print('main.py: StaticFiles import already present, skipped')

if 'app.mount("/static"' not in content and "app.mount('/static'" not in content:
    content += '\n\napp.mount("/static", StaticFiles(directory="static"), name="static")\n'
    changed = True
    print('main.py: /static mount added')
else:
    print('main.py: /static mount already present, skipped')

if changed:
    with open('main.py', 'w') as f:
        f.write(content)
    print('main.py: saved')
else:
    print('main.py: no changes needed')
