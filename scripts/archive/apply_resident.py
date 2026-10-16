"""Adds the resident portal: includes resident.py in main.py and adds a Resident card on the home page."""
s = open('main.py').read()
if 'import resident' not in s:
    s += '\nimport resident\napp.include_router(resident.router)\n'
    open('main.py', 'w').write(s)
    print('main.py updated')

p = 'static/app/index.html'
s = open(p).read()
if 'data-role="res"' in s:
    print('Home page already has the Resident card.'); raise SystemExit
card = '''          <button type="button" class="role-card res" data-role="res">
            <span class="ico"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c.8-3.5 3.2-5.5 6-5.5s5.2 2 6 5.5"/><path d="M15 15.2c.6-.2 1.3-.3 2-.3 2.2 0 3.9 1.5 4.5 4.6"/></svg></span>
            <strong>Resident / Evacuee</strong>
            <span class="d">Pre-registered residents checking their family's safety and records.</span>
            <span class="go">Continue &rarr;</span>
          </button>
        </div>
        <div id="roleNext"'''
old = '''          </button>
        </div>
        <div id="roleNext"'''
if old not in s:
    print('Could not find the role cards. Run apply_home_v3.py first, or send index.html to Claude.'); raise SystemExit(1)
s = s.replace(old, '          </button>\n' + card, 1)
s = s.replace("    city: { title: 'City Hall Administrator'",
              "    res: { title: 'Resident / Evacuee', sub: 'Pre-registered by your barangay', inn: 'resident-signin.html', up: '', upSub: '' },\n    city: { title: 'City Hall Administrator'", 1)
s = s.replace("      document.getElementById('rnUp').href = r.up;",
              "      document.getElementById('rnUp').href = r.up || '#';\n      document.getElementById('rnUp').style.display = r.up ? '' : 'none';", 1)
css = '''.role-cards { grid-template-columns: repeat(3, 1fr) !important; }
.role-card.res .ico { background: #198754; }
.role-card.res .go { color: #15803D; }
.role-next.res .rb { border-color: #198754; }
.role-next.res .rb.fill { background: #198754; color: #FFFFFF; }
@media (max-width: 1200px) { .role-cards { grid-template-columns: 1fr !important; } }
'''
s = s.replace('</style>\n</head>', css + '</style>\n</head>', 1)
open(p, 'w').write(s)
print('index.html updated')
