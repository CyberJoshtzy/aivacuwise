"""Replaces the single Sign In button on index.html with two choices:
Barangay Official and City Hall Administrator."""
import re
p = 'static/app/index.html'
s = open(p).read()
if 'role-cards' in s:
    print('Already applied.'); raise SystemExit
css = '''<style>
.role-title { font-size: 14px; font-weight: 800; color: var(--navy); margin: 0 0 10px; }
.role-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.role-card { display: flex; flex-direction: column; gap: 10px; padding: 18px; border-radius: 14px; border: 2px solid #E3E8F2; background: #FFFFFF; text-decoration: none; color: inherit; transition: border-color .15s, transform .15s, box-shadow .15s; }
.role-card:hover, .role-card:focus-visible { border-color: var(--orange); transform: translateY(-2px); box-shadow: 0 8px 20px rgba(11,31,77,.10); outline: none; }
.role-card .ico { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; }
.role-card .ico svg { width: 24px; height: 24px; fill: none; stroke: #FFFFFF; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.role-card.brgy .ico { background: var(--orange); }
.role-card.city .ico { background: var(--navy); }
.role-card strong { font-size: 16px; color: var(--navy); }
.role-card span.d { font-size: 13px; color: var(--muted); line-height: 1.45; }
.role-card .go { margin-top: auto; font-size: 14px; font-weight: 800; color: var(--navy); }
.role-card.brgy .go { color: #C2410C; }
@media (max-width: 700px) { .role-cards { grid-template-columns: 1fr; } }
</style>
</head>'''
cards = '''<div>
        <p class="role-title">Sign in as</p>
        <div class="role-cards">
          <a class="role-card brgy" href="signin.html">
            <span class="ico"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21h18"/><path d="M5 21V10l7-5 7 5v11"/><path d="M10 21v-6h4v6"/></svg></span>
            <strong>Barangay Official</strong>
            <span class="d">Barangay captain, kagawad, secretary or BDRRMC staff managing one barangay.</span>
            <span class="go">Barangay Sign In &rarr;</span>
          </a>
          <a class="role-card city" href="admin-signin.html">
            <span class="ico"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21h18"/><path d="M4 21V9h16v12"/><path d="M2 9l10-6 10 6"/><path d="M8 13v4M12 13v4M16 13v4"/></svg></span>
            <strong>City Hall Administrator</strong>
            <span class="d">City Mayor, CDRRMO, CSWDO, CHO and MIS personnel viewing all barangays.</span>
            <span class="go">City Hall Sign In &rarr;</span>
          </a>
        </div>
        <p style="font-size:13px;color:var(--muted);margin:10px 0 0">City Hall personnel without an account can <a href="admin-register.html" style="font-weight:700">request access here</a>.</p>
      </div>'''
m = re.search(r'<a\b[^>]*href="signin\.html"[^>]*>\s*Sign In\s*</a>', s)
if not m:
    m = re.search(r'<(a|button)\b[^>]*>\s*Sign In\s*</\1>', s)
if not m:
    print('Could not find the Sign In button. Send index.html to Claude.'); raise SystemExit(1)
s = s[:m.start()] + cards + s[m.end():]
s = s.replace('</head>', css, 1)
open(p, 'w').write(s)
print('index.html updated')
