"""User Accounts page for the City Admin: sidebar item opens accounts.html, and the
'User accounts' title on City Overview links to it."""
a = open('static/app/app.js').read()
old = "['users', 'User Accounts', null]"
print('app.js: sidebar item opened' if old in a else 'app.js: sidebar item NOT FOUND (maybe already done)')
a = a.replace(old, "['users', 'User Accounts', 'accounts.html']", 1)
open('static/app/app.js', 'w').write(a)
c = open('static/app/city.html').read()
old = '<h2>User accounts</h2>'
print('city.html: title linked' if old in c else 'city.html: title NOT FOUND (maybe already done)')
c = c.replace(old, '<h2><a class="h-link" href="accounts.html">User accounts <span aria-hidden="true">&rarr;</span></a></h2>', 1)
open('static/app/city.html', 'w').write(c)
