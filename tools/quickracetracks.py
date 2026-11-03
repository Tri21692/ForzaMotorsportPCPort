"""quickracetracks.py <disc> <mods>: the tracks Quick Race offers (hle_quickrace.c), as <mods>/quickrace.txt, a line
each, "ordinal name": every track of forzadb/tracklist.xml (the mods folder's Mega.ca2 if it has one) that its AI
can race (aiReady="true"), by its RosettaName, in the list's order."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    k = next(k for k in mega.files if k.lower().endswith('tracklist.xml'))
    x = bytes(mega.files[k]).decode('utf-8', 'replace')
    out = []
    for t in re.finditer(r'<track\b(.*?)/>', x, re.S):
        a = dict(re.findall(r'(\w+)="([^"]*)"', t.group(1)))
        if a.get('aiReady', '').lower() == 'true' and 'Ordinal' in a:
            out.append('%s %s' % (a['Ordinal'], a.get('RosettaName') or a.get('name')))
    open(os.path.join(mods, 'quickrace.txt'), 'w').write('\n'.join(out) + '\n')
    print('quickrace.txt: %d tracks' % len(out))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
