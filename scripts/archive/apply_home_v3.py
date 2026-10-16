"""Home page: two role cards. Clicking a card shows Sign In / Sign Up for that role."""
p = 'static/app/index.html'
s = open(p).read()
if 'id="rolePick"' in s:
    print('Already applied.'); raise SystemExit
rep = [
    ('<div class="role-cards">', '<div id="rolePick" class="role-cards">'),
    ('<div class="role-card brgy">', '<button type="button" class="role-card brgy" data-role="brgy">'),
    ('<div class="role-card city">', '<button type="button" class="role-card city" data-role="city">'),
    ('            <div class="role-btns"><a class="rb fill" href="signin.html">Sign In</a><a class="rb line" href="register.html">Sign Up</a></div>\n          </div>',
     '            <span class="go">Continue &rarr;</span>\n          </button>'),
    ('            <div class="role-btns"><a class="rb fill" href="admin-signin.html">Sign In</a><a class="rb line" href="admin-register.html">Sign Up</a></div>\n          </div>\n        </div>',
     '''            <span class="go">Continue &rarr;</span>
          </button>
        </div>
        <div id="roleNext" class="role-next" hidden>
          <button type="button" class="role-back" id="roleBack">&larr; Change role</button>
          <div class="role-head"><span class="ico" id="rnIco"></span><div><strong id="rnTitle"></strong><span class="d" id="rnSub"></span></div></div>
          <a class="rb fill big" id="rnIn" href="#"><span>Sign In</span><small>I already have an account</small></a>
          <a class="rb line big" id="rnUp" href="#"><span>Sign Up</span><small id="rnUpSub"></small></a>
        </div>'''),
]
for a, b in rep:
    if a not in s:
        print('Could not find part of the cards. Send index.html to Claude.'); raise SystemExit(1)
    s = s.replace(a, b, 1)
css = '''.role-card { font: inherit; text-align: left; cursor: pointer; }
.role-card .go { margin-top: auto; padding-top: 4px; font-size: 14px; font-weight: 800; color: var(--navy); }
.role-card.brgy .go { color: #C2410C; }
.role-card:focus-visible { outline: 3px solid rgba(245,158,11,.45); outline-offset: 2px; }
.role-next { display: flex; flex-direction: column; gap: 12px; padding: 22px; border-radius: 14px; border: 2px solid #E3E8F2; background: #FFFFFF; animation: pop .25s ease-out; }
.role-next[hidden] { display: none; }
.role-back { align-self: flex-start; background: none; border: none; padding: 0; font: inherit; font-size: 14px; font-weight: 700; color: var(--navy); cursor: pointer; }
.role-head { display: flex; gap: 14px; align-items: center; margin-bottom: 4px; }
.role-head strong { display: block; font-size: 18px; color: var(--navy); }
.role-head .d { font-size: 13px; color: var(--muted); }
.role-head .ico { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; flex-shrink: 0; }
.role-head .ico svg { width: 24px; height: 24px; fill: none; stroke: #FFFFFF; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.rb.big { min-height: 64px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 2px; font-size: 16px; }
.rb.big small { font-size: 12px; font-weight: 600; opacity: .85; }
.role-next.brgy .rb { border-color: var(--orange); }
.role-next.brgy .rb.fill { background: var(--orange); color: var(--navy); }
.role-next.brgy .rb.line { color: #C2410C; }
'''
s = s.replace('</style>\n</head>', css + '</style>\n</head>', 1)
js = '''<script>
(function () {
  var pick = document.getElementById('rolePick'), next = document.getElementById('roleNext');
  var R = {
    brgy: { title: 'Barangay Official', sub: 'Captain, kagawad, secretary or BDRRMC staff', inn: 'signin.html', up: 'register.html', upSub: 'Register my barangay' },
    city: { title: 'City Hall Administrator', sub: 'Mayor, CDRRMO, CSWDO, CHO or MIS personnel', inn: 'admin-signin.html', up: 'admin-register.html', upSub: 'Request City Hall access' }
  };
  pick.querySelectorAll('.role-card').forEach(function (c) {
    c.addEventListener('click', function () {
      var r = R[c.dataset.role];
      document.getElementById('rnIco').innerHTML = c.querySelector('.ico').innerHTML;
      document.getElementById('rnIco').style.background = getComputedStyle(c.querySelector('.ico')).backgroundColor;
      document.getElementById('rnTitle').textContent = r.title;
      document.getElementById('rnSub').textContent = r.sub;
      document.getElementById('rnIn').href = r.inn;
      document.getElementById('rnUp').href = r.up;
      document.getElementById('rnUpSub').textContent = r.upSub;
      next.className = 'role-next ' + c.dataset.role;
      pick.hidden = true; pick.style.display = 'none'; next.hidden = false;
      document.getElementById('rnIn').focus();
    });
  });
  document.getElementById('roleBack').addEventListener('click', function () {
    next.hidden = true; pick.hidden = false; pick.style.display = '';
  });
})();
</script>
</body>'''
s = s.replace('</body>', js, 1)
open(p, 'w').write(s)
print('index.html updated')
