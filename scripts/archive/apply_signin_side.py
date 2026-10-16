"""Redesigns the blue side panel on the barangay and City Hall sign-in pages."""
css = '''<style id="side-v2">
.signin aside { justify-content: center !important; align-items: center; text-align: center; gap: 28px !important; position: relative; padding: 48px 56px !important;
  background: radial-gradient(circle at 20% 15%, rgba(245,158,11,.18), transparent 40%), radial-gradient(circle at 85% 90%, rgba(59,130,246,.25), transparent 45%), linear-gradient(160deg, #0B1F4D, #142C6E) !important; }
.signin aside .tile { align-self: center !important; padding: 18px 22px !important; border-radius: 22px !important; box-shadow: 0 18px 40px rgba(0,0,0,.25); }
.signin aside .tile img { width: 220px !important; }
.signin aside h2 { font-size: 30px !important; margin: 0; }
.signin aside > div:not(.tile):not(.foot) { display: flex; flex-direction: column; align-items: center; gap: 6px; max-width: 440px; }
.signin aside .points { margin-top: 18px !important; gap: 10px !important; width: 100%; }
.signin aside .points div { align-items: center !important; text-align: left; padding: 12px 16px; border-radius: 14px; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.10); color: #E3E9F7; font-size: 15px; }
.signin aside .points svg { width: 34px !important; height: 34px !important; padding: 7px; border-radius: 10px; background: rgba(245,158,11,.16); }
.signin aside .foot { position: absolute; left: 0; right: 0; bottom: 26px; text-align: center; font-size: 12px !important; }
@media (max-width: 900px) { .signin aside { padding: 28px 24px !important; } .signin aside .tile img { width: 180px !important; } }
</style>
</head>'''
for p in ('static/app/signin.html', 'static/app/admin-signin.html'):
    try:
        s = open(p).read()
    except FileNotFoundError:
        print(p + ': not found'); continue
    if 'id="side-v2"' in s:
        print(p + ': already done'); continue
    s = s.replace('</head>', css, 1)
    open(p, 'w').write(s)
    print(p + ': side panel redesigned')
