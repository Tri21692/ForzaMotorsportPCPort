"""A cab's cars\\<car>\\ files into a folder.   python excab.py <cab> <out folder>"""
import sys, os
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import forzacab
d, ver, es = forzacab.read(sys.argv[1])
n = 0
for e in es:
    parts = e['name'].lower().split(chr(92))
    if parts[0] != 'cars' or len(parts) < 3: continue
    p = os.path.join(sys.argv[2], *parts[2:]); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(forzacab.data(d, e)); n += 1
print(n, 'files to', sys.argv[2])
