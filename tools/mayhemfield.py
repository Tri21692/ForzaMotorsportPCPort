"""The Mayhem Tour's races with a big field (the user's, 5 Nov: "20-30 opponents ... evenly spaced out" with a head
start; 12, the user's "we'll do 12 for now": the game's field holds 16 AI cars, but in the tests 17 racers crashed at
Start Race and 14 to 16 never got the start lights; 13 raced): each event's <AIField NumAICars="7" .../> made NumAICars="12" random="true"
duplicates="true", in place in events\\Mayhem\\Ser00001.xml (the series' own field of 8 cars a difficulty is kept: the
picker, 0x22ABA0, draws 12 from those at random, duplicates allowed; without random it stops at the 8 there are).
The grid (over 8 racers: the in-order grid, the rivals spread round the lap) is the runtime's (hle_career.c, big field).
Idempotent. N=7 puts the disc's 7 back.

  python tools/mayhemfield.py <disc> <mods folder> [N]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def main(disc, mods, n=12):
    if not 1 <= n <= 12: raise SystemExit('1 to 12 AI cars (more never started or crashed in the tests), not %d' % n)
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    key = next(k for k in mega.files if k.lower() == ('events' + B + 'mayhem' + B + 'ser00001.xml'))
    x = mega.files[key].decode('latin-1')
    big = n > 7
    new = '<AIField NumAICars="%d" random="%s" byclass="false" duplicates="%s" />' % (n, 'true' if big else 'false', 'true' if big else 'false')
    events = re.findall(r'<event\b.*?</event>', x, re.S)
    out, changed = x, 0
    for e in events:
        m = re.findall(r'<AIField NumAICars="\d+"[^>]*/>', e)
        if len(m) != 1: raise SystemExit('an event without one AIField line: %s' % e[:120])
        if m[0] != new:
            out = out.replace(e, e.replace(m[0], new), 1)
            changed += 1
    if changed:
        mega.files[key] = out.encode('latin-1')
        mega.check(); mega.write()
    print('%s: %d of %d events set to %s' % (key, changed, len(events), new))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) == 4 else 12)
