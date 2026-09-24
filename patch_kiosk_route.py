with open('main.py') as f:
    content = f.read()

if '"/kiosk"' in content or "'/kiosk'" in content:
    print('main.py: /kiosk route already present, skipped')
else:
    addition = (
        '\n\n@app.get("/kiosk")\n'
        'async def kiosk():\n'
        '    return FileResponse("static/kiosk.html")\n'
    )
    content += addition
    with open('main.py', 'w') as f:
        f.write(content)
    print('main.py: /kiosk route added')
