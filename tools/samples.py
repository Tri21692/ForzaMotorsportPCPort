"""Summarises tools/sample.sh output for the threads whose stacks contain
a given function (device_main by default): the innermost runtime frame of
each sample (with its line), and the functions that appear anywhere.

    python tools/samples.py samples.txt [function]
"""
import collections
import re
import sys

SYSTEM = ('ntdll', 'KERNEL', '??', 'igx', 'SetEvent', 'WaitFor', 'Release', 'msvcrt', 'do_sema', 'pthread_cond',
          '_pthread', 'pthread_getevent')

path = sys.argv[1]
want = sys.argv[2] if len(sys.argv) > 2 else 'device_main'
text = open(path, encoding='utf-8', errors='replace').read()
inner, lines, anywhere = collections.Counter(), collections.Counter(), collections.Counter()
n = 0
for sample in text.split('====='):
    for thread in re.split(r'\nThread ', sample):
        frames = re.findall(r'#\d+\s+(?:0x[0-9a-f]+ in )?(\S+) \((?:[^\n]*? at \S+?:(\d+))?', thread)
        if want not in [f for f, _ in frames]:
            continue
        n += 1
        own = [(f, l) for f, l in frames if not f.startswith(SYSTEM)] or frames
        inner[own[0][0]] += 1
        lines['%s:%s' % own[0]] += 1
        for f in set(f for f, _ in own):
            anywhere[f] += 1
print('%d stacks with %s' % (n, want))
print('\ninnermost:')
for f, c in inner.most_common(20):
    print('%4d %s' % (c, f))
print('\nby line:')
for f, c in lines.most_common(20):
    print('%4d %s' % (c, f))
print('\nanywhere:')
for f, c in anywhere.most_common(30):
    print('%4d %s' % (c, f))
