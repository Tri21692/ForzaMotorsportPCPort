"""Name the host stacks in a freeze's thread dump (runtime/thread.c, host_backtrace: each guest thread's
"  host: <offset> <offset> module!offset ..." line, offsets in the executable that ran). Each offset in the
executable becomes its function (f_000595E0, a game function as the recompiler named it, or the runtime's
own) by the executable's symbols (nm), plus how far in.

  python tools/hangstack.py <the executable> <log> [the dump's first line number]

The dump read is the last one in the log, or the one starting at that line. Use the very executable that
wrote the log: another build places every function elsewhere.
"""
import bisect
import subprocess
import sys

IMAGE_BASE = 0x140000000  # (objdump -p: ImageBase)


def symbols(exe):
    syms = []
    for line in subprocess.run(['nm', exe], capture_output=True, text=True, check=True).stdout.splitlines():
        w = line.split()
        if len(w) != 3 or w[1] not in 'tTwW': continue
        name = w[2][6:].rstrip('.') if w[2].startswith('.weak.') else w[2]  # (the game's functions are weak: W, or .weak.f_X.)
        if not name.startswith('.'): syms.append((int(w[0], 16), name.replace('.localalias', '')))
    syms.sort()
    return syms


def main(exe, log, start=None):
    syms = symbols(exe)
    addrs = [a for a, _ in syms]
    lines = open(log, errors='replace').read().splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith('---- ') and 'threads' in l]
    if not heads: raise SystemExit('%s: no thread dump' % log)
    first = int(start) - 1 if start else heads[-1]
    print(lines[first])
    thread = None
    for l in lines[first + 1:]:
        if l.startswith('---- ') or l.startswith('['): break
        if l.startswith('thread '): thread = l; continue
        if not l.startswith('  host:') or thread is None: continue
        print(thread)
        for f in l.split()[1:]:
            if '!' in f:
                print('    %s' % f)
                continue
            v = int(f, 16) + IMAGE_BASE
            i = bisect.bisect_right(addrs, v) - 1
            print('    %s+%x' % (syms[i][1], v - syms[i][0]) if i >= 0 else '    %s' % f)


if __name__ == '__main__':
    if len(sys.argv) < 3: raise SystemExit(__doc__)
    main(*sys.argv[1:4])
