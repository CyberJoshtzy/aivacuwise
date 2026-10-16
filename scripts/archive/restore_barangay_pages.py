"""Gives barangay officials back their own pages (from the last git commit), so the City Hall
changes only affect the City Admin. City Admin pages are not touched.

- evacuees.html, centers.html, barangays.html  ->  copied from git as brgy-evacuees.html, brgy-centers.html, brgy-barangays.html
  and the Barangay Official sidebar points to these copies
- signin.html (barangay sign-in) is restored from git
"""
import subprocess, re, sys

def git_show(path):
    try:
        return subprocess.run(['git', 'show', 'HEAD:' + path], capture_output=True, text=True, check=True).stdout
    except Exception:
        return None

head = subprocess.run(['git', 'log', '-1', '--format=%ad  %s', '--date=format:%b %d %Y %H:%M'], capture_output=True, text=True).stdout.strip()
if not head:
    sys.exit('No git history found. Send the output of "git log --oneline | head" to Claude.')
print('Restoring from last commit:', head)

a = open('static/app/app.js').read()
nav_start = a.index("barangay_official: [")
nav_end = a.index("\n    ]", nav_start)
nav = a[nav_start:nav_end]
done = []
for page in ('evacuees.html', 'centers.html', 'barangays.html'):
    old = git_show('static/app/' + page)
    if not old:
        print(page + ': not in git, kept as is'); continue
    old = re.sub(r'app\.js(\?v=\d+)?"', 'app.js?v=41"', old)
    old = old.replace("BL.renderSidebar(me, '" + page + "'", "BL.renderSidebar(me, 'brgy-" + page + "'")
    open('static/app/brgy-' + page, 'w').write(old)
    nav = nav.replace("'" + page + "']", "'brgy-" + page + "']")
    done.append(page[:-5])
    print(page + ': barangay officials now use their original version (brgy-' + page + ')')
a = a[:nav_start] + nav + a[nav_end:]
# a barangay official who opens a City Admin version is sent to their own copy
if done and 'brgy-redirect' not in a:
    a = a.replace("    if (opts.role && me.role !== opts.role) {",
                  "    /* brgy-redirect */ if (me.role !== 'city_admin' && /^(" + '|'.join(done) + ")\\.html/.test(here)) { location.href = 'brgy-' + here; return new Promise(() => {}); }\n    if (opts.role && me.role !== opts.role) {", 1)
open('static/app/app.js', 'w').write(a)
print('app.js: Barangay Official sidebar updated')

old = git_show('static/app/signin.html')
if old:
    old = re.sub(r'app\.js(\?v=\d+)?"', 'app.js?v=41"', old)
    open('static/app/signin.html', 'w').write(old)
    print('signin.html: restored')
