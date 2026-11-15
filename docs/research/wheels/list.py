"""Each add-on car's wheel model (tooldata's WheelStyle File) beside its maker, and the wheel styles the disc has.
  python list.py <disc> <mods>"""
import os, re, sys
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar
B = '\\'
disc, mods = sys.argv[1:3]
mega = addcar.Archive(disc, mods, 'Mega.ca2')
cars = addcar.Archive(disc, mods, 'Cars.ca2')
xml = bytes(mega.files[next(k for k in mega.files if k.lower() == 'cars\\carlist.xml')]).decode('latin-1')
dxml = bytes(mega.disc[next(k for k in mega.disc if k.lower() == 'cars\\carlist.xml')]).decode('latin-1')
dn = set(re.findall(r'<car name="([^"]*)"', dxml))
styles = sorted({k.split(B)[2] for k in mega.files if k.lower().startswith('tires\\art\\') and k.lower().endswith('tire.carbin')})
dstyles = {k.split(B)[2].lower() for k in mega.disc if k.lower().startswith('tires\\art\\')}
print('%d wheel models (%d the disc\'s)' % (len(styles), len(dstyles)))
ck = {k.lower(): k for k in cars.files}
for m in re.finditer(r'<car name="([^"]*)"[^>]*>', xml):
    n = m.group(1)
    if n in dn: continue
    t = bytes(cars.files[ck['cars\\%s\\tooldata.xml' % n.lower()]]).decode('latin-1')
    ws = re.search(r'<WheelStyle>(.*?)</WheelStyle>', t, re.S).group(1)
    fs = re.findall(r'<P(\d+) [^>]*File="([^"]*)"', ws)
    print('%-34s wheel %-22s %s (%d styles listed)' % (n, fs[0][1], 'OWN' if fs[0][1].lower() not in dstyles else '', len(fs)))
if '--styles' in sys.argv: print(' '.join(styles))
