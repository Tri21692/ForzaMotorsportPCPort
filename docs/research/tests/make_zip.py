"""The audited mods as one zip (the user's, 11 Nov: "audit as many mods as you can and put them to a zip"):
run/mods_next without its backup files, runtime/forza-next.exe, the launcher and a readme, paths as in the project."""
import os, sys, zipfile, time
G = r'E:\Forza Motorsport Remastered'
OUT = os.path.join(G, 'Forza mods 2026-11-12.zip')
SKIP = ('.bak_', '.before_')
README = open(r'E:\xbrt_scr\zip_readme.txt', encoding='utf-8').read()
n = size = 0
t = time.time()
with zipfile.ZipFile(OUT + '.part', 'w', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
    z.writestr('README.txt', README)
    z.write(os.path.join(G, 'Play Forza (New mods).bat'), 'Play Forza (New mods).bat')
    z.write(os.path.join(G, 'runtime', 'forza-next.exe'), 'runtime/forza-next.exe')
    root = os.path.join(G, 'run', 'mods_next')
    for d, _, fs in os.walk(root):
        for f in fs:
            if any(k in f for k in SKIP): continue
            p = os.path.join(d, f)
            z.write(p, 'run/mods_next/' + os.path.relpath(p, root).replace(os.sep, '/'))
            n += 1; size += os.path.getsize(p)
with zipfile.ZipFile(OUT + '.part') as z:
    bad = z.testzip()
if os.path.exists(OUT): os.remove(OUT)
os.rename(OUT + '.part', OUT)
print('%s: %d files, %.2f GB in, %.2f GB zip, bad: %s, %.0f s' % (OUT, n, size / 2**30, os.path.getsize(OUT) / 2**30, bad, time.time() - t))
