"""Slightly larger logo in the resident dashboard top bar, and the resident sign-in side panel
uses the same layout as the City Hall sign-in (green colors kept)."""
p = 'static/app/resident.html'
s = open(p).read()
if 'logo-v3' not in s:
    s = s.replace('</style>', '/* logo-v3 */ .top img { height: 58px !important; } .brand b { font-size: 17px !important; }\n</style>', 1)
    open(p, 'w').write(s); print('resident.html: logo enlarged')
p = 'static/app/resident-signin.html'
s = open(p).read()
if 'side-v2' not in s:
    css = '''<style id="side-v2">
.signin aside { justify-content: center !important; align-items: center; text-align: center; gap: 24px !important; position: relative; padding: 48px 56px !important;
  background: radial-gradient(circle at 20% 15%, rgba(245,158,11,.15), transparent 40%), radial-gradient(circle at 85% 90%, rgba(52,211,153,.22), transparent 45%), linear-gradient(160deg, #0F5132, #198754) !important; }
.signin aside .tile { align-self: center !important; padding: 18px 22px !important; border-radius: 22px !important; box-shadow: 0 18px 40px rgba(0,0,0,.25); }
.signin aside .tile img { width: 240px !important; }
.signin aside h2 { margin: 0; }
.signin aside > div:not(.tile):not(.foot) { display: flex; flex-direction: column; align-items: center; gap: 6px; max-width: 440px; width: 100%; }
.points { margin-top: 18px !important; gap: 10px !important; width: 100%; }
.points div { align-items: center !important; text-align: left; padding: 12px 16px; border-radius: 14px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); }
.points b { width: 30px; height: 30px; border-radius: 10px; display: grid; place-items: center; background: rgba(255,209,102,.18); flex-shrink: 0; }
.signin aside .foot { position: absolute; left: 0; right: 0; bottom: 26px; text-align: center; font-size: 12px !important; }
</style>
</head>'''
    s = s.replace('</head>', css, 1)
    s = s.replace('<h2>Para sa mga residente</h2>', '<span style="display:inline-block;padding:6px 14px;border-radius:999px;background:var(--orange);color:#FFFFFF;font-size:12px;font-weight:800;letter-spacing:.08em;margin-bottom:8px">RESIDENT PORTAL</span>\n      <h2>Para sa mga residente</h2>', 1)
    open(p, 'w').write(s); print('resident-signin.html: side panel matches City Hall layout')
