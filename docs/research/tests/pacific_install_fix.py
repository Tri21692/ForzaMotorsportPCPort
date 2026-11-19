"""install_fix.py <test mods folder> <target mods folder> [--write]

The Pacific Shipyards Circuit's rebuilt files (both layouts) from a test build into a mods folder that has the circuit
already (tools/shipyardcircuit.py installs nothing there: "... is in the track list already"). Without --write it only
lists what differs (reads both folders, writes nothing).

  the loose files: track\\<tag>\\ (collision cache, scenery, visibility, boxes, svb, stx) and media\\tracks\\<tag>\\
                   (QuickPreview1.col, AudioSpline.bin and the copies beside them), both tags, copied whole;
  Mega.ca2:        the members under ai\\drivatarv2\\ and tracks\\ named for the two tags (geometry, segmentation, the
                   level, interaction and segment profile files, audio xmls, quickpreview.xml and the rest of the data
                   folder), each put into the target's Mega.ca2 where its bytes differ; the AI track list, the track
                   list (ForzaDB) and everything else in the target's archive are left as they are;
  MegaXPR.ca2:     left alone (the map tiles: the loop's shape on the map is the same to a pixel or two).
"""
import os, shutil, sys, zlib
sys.path.insert(0, 'E:/Forza Motorsport Remastered/tools')
import addcar
DISC = 'C:/Users/maste/Downloads/extract-xiso-win32-release/Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
TAGS = ('VancouverLoop', 'VancouverLoopReverse')
src, dst = sys.argv[1], sys.argv[2]
write = '--write' in sys.argv
if write and any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(dst).split(os.sep)):
    raise SystemExit('%s: a save folder' % dst)
loose = []
for tag in TAGS:
    for top in (os.path.join('track', tag), os.path.join('media', 'tracks', tag)):
        for root, _, files in os.walk(os.path.join(src, top)):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), src)
                a = open(os.path.join(src, rel), 'rb').read()
                b = open(os.path.join(dst, rel), 'rb').read() if os.path.exists(os.path.join(dst, rel)) else None
                state = 'new' if b is None else 'same' if a == b else 'differs'
                loose.append((rel, len(a), state))
print('loose files:')
for rel, n, state in loose: print('  %-8s %10d  %s' % (state, n, rel))
ms, md = addcar.Archive(DISC, src, 'Mega.ca2'), addcar.Archive(DISC, dst, 'Mega.ca2')
B = chr(92)
def ours(k):
    kl = k.lower()
    if kl.startswith('tracks' + B): return kl.split(B)[1] in [t.lower() for t in TAGS]
    if kl.startswith('ai' + B + 'drivatarv2' + B): return any(('vancouverloop' in part) for part in kl.split(B)[2:])
    return False
members = []
for k in sorted(ms.files):
    if not ours(k): continue
    state = 'new' if k not in md.files else 'same' if md.files[k] == ms.files[k] else 'differs'
    members.append((k, state))
print('Mega.ca2 members:')
for k, state in members: print('  %-8s %8d  %s' % (state, len(ms.files[k]), k))
gone = [k for k in md.files if ours(k) and k not in ms.files]
if gone: print('in the target only (left):', gone)
if not write:
    print('nothing written (--write to install): %d loose files and %d archive members differ or are new' % (
        sum(s != 'same' for _, _, s in loose), sum(s != 'same' for _, s in members)))
    sys.exit()
for rel, n, state in loose:
    if state == 'same': continue
    os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
    shutil.copyfile(os.path.join(src, rel), os.path.join(dst, rel))
for k, state in members:
    if state != 'same': md.files[k] = ms.files[k]
md.check(); md.write()
print('installed into %s' % dst)
