s = open('main.py').read()
if 'import center_delete' not in s:
    s += '\nimport center_delete\napp.include_router(center_delete.router)\n'
    open('main.py', 'w').write(s)
print('main.py ready')
