"""Home page update: each choice card gets Sign In and Sign Up buttons.
Removes the 'Overview' label, 'Sign in as', the 'or' divider and the
'Is your barangay not yet in BilisLikas?' box."""
import re
from html.parser import HTMLParser

p = 'static/app/index.html'
s = open(p).read()
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr', 'path', 'circle', 'rect'}


def line_offsets(text):
    offs, n = [0], 0
    for line in text.splitlines(True):
        n += len(line); offs.append(n)
    return offs


class Spans(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.offs, self.stack, self.spans = line_offsets(text), [], []
    def pos(self):
        l, c = self.getpos(); return self.offs[l - 1] + c
    def handle_starttag(self, tag, attrs):
        if tag not in VOID: self.stack.append((tag, self.pos()))
    def handle_startendtag(self, tag, attrs): pass
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                t, st = self.stack.pop(i)
                end = s.index('>', self.pos()) + 1
                self.spans.append((st, end)); del self.stack[i:]; break


def spans():
    sp = Spans(s); sp.feed(s); return sp.spans


def plain(a, b):
    return ' '.join(re.sub(r'<[^>]+>', ' ', s[a:b]).split())


def remove_smallest(test, label, largest=False):
    global s
    hits = [(b - a, a, b) for a, b in spans() if test(plain(a, b), s[a:b])]
    if not hits:
        print('  not found (skipped):', label); return
    _, a, b = max(hits) if largest else min(hits)
    s = s[:a] + s[b:]
    print('  removed:', label)


remove_smallest(lambda t, h: t == 'Overview', "'Overview' label")
remove_smallest(lambda t, h: 'Is your barangay not yet in BilisLikas' in t and 'Register Barangay' in t, 'register barangay box')
remove_smallest(lambda t, h: t == 'or', "'or' divider", largest=True)

cards = '''<div class="role-cards">
          <div class="role-card brgy">
            <span class="ico"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21h18"/><path d="M5 21V10l7-5 7 5v11"/><path d="M10 21v-6h4v6"/></svg></span>
            <strong>Barangay Official</strong>
            <span class="d">Barangay captain, kagawad, secretary or BDRRMC staff managing one barangay.</span>
            <div class="role-btns"><a class="rb fill" href="signin.html">Sign In</a><a class="rb line" href="register.html">Sign Up</a></div>
          </div>
          <div class="role-card city">
            <span class="ico"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21h18"/><path d="M4 21V9h16v12"/><path d="M2 9l10-6 10 6"/><path d="M8 13v4M12 13v4M16 13v4"/></svg></span>
            <strong>City Hall Administrator</strong>
            <span class="d">City Mayor, CDRRMO, CSWDO, CHO and MIS personnel overseeing all barangays of Manila.</span>
            <div class="role-btns"><a class="rb fill" href="admin-signin.html">Sign In</a><a class="rb line" href="admin-register.html">Sign Up</a></div>
          </div>
        </div>'''
start = s.find('<p class="role-title">')
if start != -1:
    a = s.rfind('<div>', 0, start)
    hits = [(b - x, x, b) for x, b in spans() if x == a]
    a, b = hits[0][1], hits[0][2]
    s = s[:a] + cards + s[b:]
    print('  replaced choice cards')
else:
    m = re.search(r'<a\b[^>]*href="signin\.html"[^>]*>\s*Sign In\s*</a>', s)
    if not m:
        print('Could not find the Sign In area. Send index.html to Claude.'); raise SystemExit(1)
    s = s[:m.start()] + cards + s[m.end():]
    print('  replaced Sign In button')

css = '''.role-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.role-card { display: flex; flex-direction: column; gap: 10px; padding: 20px; border-radius: 14px; border: 2px solid #E3E8F2; background: #FFFFFF; transition: border-color .15s, transform .15s, box-shadow .15s; }
.role-card:hover { border-color: var(--orange); transform: translateY(-2px); box-shadow: 0 8px 20px rgba(11,31,77,.10); }
.role-card .ico { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; }
.role-card .ico svg { width: 24px; height: 24px; fill: none; stroke: #FFFFFF; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.role-card.brgy .ico { background: var(--orange); }
.role-card.city .ico { background: var(--navy); }
.role-card strong { font-size: 17px; color: var(--navy); }
.role-card span.d { font-size: 13px; color: var(--muted); line-height: 1.45; }
.role-btns { margin-top: auto; padding-top: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.rb { min-height: 44px; display: grid; place-items: center; border-radius: 10px; font-size: 14px; font-weight: 800; text-decoration: none; border: 2px solid var(--navy); }
.rb.fill { background: var(--navy); color: #FFFFFF; }
.rb.line { background: #FFFFFF; color: var(--navy); }
.brgy .rb { border-color: var(--orange); }
.brgy .rb.fill { background: var(--orange); color: var(--navy); }
.brgy .rb.line { color: #C2410C; }
.rb:hover, .rb:focus-visible { filter: brightness(.95); outline: 3px solid rgba(245,158,11,.35); outline-offset: 2px; }
@media (max-width: 700px) { .role-cards { grid-template-columns: 1fr; } }
'''
s = re.sub(r'<style>\s*\.role-title.*?</style>\s*', '', s, flags=re.S)
s = s.replace('</head>', '<style>\n' + css + '</style>\n</head>', 1)
open(p, 'w').write(s)
print('index.html updated')
