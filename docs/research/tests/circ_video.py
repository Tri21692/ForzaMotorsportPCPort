"""The Pacific Shipyards Circuit's track list entries: Video = their own folder's Flythrough.bik (in place)."""
import sys, re
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar
m = addcar.Archive(sys.argv[1], sys.argv[2], 'Mega.ca2')
k = next(k for k in m.files if k.lower().endswith('tracklist.xml'))
t = m.files[k].decode('latin-1')
BS = chr(92)
old = 'Video="d:' + BS + 'media' + BS + 'tracks' + BS + 'Vancouver' + BS + 'Flythrough.bik"'
for n in ('VancouverLoop', 'VancouverLoopReverse'):
    mm = re.search(r'<track\s[^>]*name="%s".*?/>' % n, t, re.S)
    e = mm.group(0)
    assert old in e, n
    new = 'Video="d:' + BS + 'media' + BS + 'tracks' + BS + n + BS + 'Flythrough.bik"'
    t = t[:mm.start()] + e.replace(old, new) + t[mm.end():]
assert '\t\t' not in new and chr(9) not in new
m.files[k] = t.encode('latin-1')
m.check()
m.write()
print([repr(x) for x in re.findall(r'Video="[^"]*Loop[^"]*"', t)])
