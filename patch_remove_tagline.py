with open('static/kiosk.html') as f:
    content = f.read()

target = '<p class="tagline">Kasama mo sa Paglikas.</p>\n      '
count = content.count(target)
if count > 0:
    content = content.replace(target, '')
    with open('static/kiosk.html', 'w') as f:
        f.write(content)
    print('Removed tagline paragraph,', count, 'occurrence(s)')
else:
    print('WARNING: tagline paragraph not found, no changes made')
