"""Frames a second in fixed windows of a race log (XBRT_STATS=1 output):

    python tools/fps_windows.py run/a.log run/b.log

Totals over a run depend on where the car ends up; windows compare like with like."""
import re, sys
for f in sys.argv[1:]:
    pts = [(float(t), int(fl), int(dr)) for t, fl, dr in re.findall(r'\[\s*([\d.]+)\] nv2a: \d+ vblanks, (\d+) flips, (\d+) draws', open(f, errors='replace').read())]
    def at(x): return min(pts, key=lambda p: abs(p[0] - x))
    out = []
    for a, b in ((170, 230), (230, 330), (330, 415)):
        p, q = at(a), at(b)
        out.append('%d-%ds: %.1f fps %d draws/flip' % (a, b, (q[1] - p[1]) / (q[0] - p[0]), (q[2] - p[2]) / max(1, q[1] - p[1])))
    print(f.ljust(10), ' | '.join(out))
