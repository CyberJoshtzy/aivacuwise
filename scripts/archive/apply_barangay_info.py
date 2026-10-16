s = open('main.py').read()
if 'import barangay_info' not in s:
    s += '\nimport barangay_info\napp.include_router(barangay_info.router)\n'
    open('main.py', 'w').write(s)
print('main.py ready')
