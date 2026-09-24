with open('main.py') as f:
    main_content = f.read()

if 'FileResponse' not in main_content:
    main_content = main_content.replace(
        'from database import get_db',
        'from database import get_db\nfrom fastapi.responses import FileResponse',
        1,
    )
    print('main.py: FileResponse import added')
else:
    print('main.py: FileResponse import already present, skipped')

if '@app.get("/dashboard")' not in main_content:
    main_content += '''

@app.get("/dashboard")
def dashboard_page():
    return FileResponse("static/dashboard.html")
'''
    print('main.py: /dashboard route added')
else:
    print('main.py: /dashboard route already present, skipped')

with open('main.py', 'w') as f:
    f.write(main_content)

print('DONE')
