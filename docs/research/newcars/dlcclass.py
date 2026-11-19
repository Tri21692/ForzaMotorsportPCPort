"""A "DLC Cars" entry in the store's Advanced Search (the user's, 6 Nov): the search's class list is "Any" and one
entry a row of performanceclass.dat (f_0017B790), so a class row 8, "DLC Cars", gives the entry; no car is of
class 8, so no class picker shows it. The runtime (hle_unlock.c) turns that entry's condition into the add-on
cars. Mega.ca2's performanceclass.dat and every language's CarDataStrings.str, in the mods folder.
python dlcclass.py [--dry]"""
import sys, os, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar
B = chr(92)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = r'E:\Forza Motorsport Remastered\run\mods_track'
CLASS_ID, ICON = 8, 7  # (F's badges: nothing shows a class with no cars)


def main(dry):
    mega = addcar.Archive(DISC, MODS, 'Mega.ca2')
    ck = B.join(('forzadb', 'cardb', 'performanceclass.dat'))
    cls = bytes(mega.files[ck])
    if any(struct.unpack_from('<I', cls, o)[0] == CLASS_ID for o in range(0, len(cls), 24)): raise SystemExit('in already')
    loc = os.path.join(MODS, 'media', 'Loc')
    new = {}
    for lang in sorted(os.listdir(loc)):
        p = os.path.join(loc, lang, 'CarDataStrings.str')
        d = open(p, 'rb').read()
        nid = max(i for i, _ in addcar.read_strings(d)[0][:-1]) + 1
        new[lang] = (p, addcar.write_strings(d, [('IDS_PerformanceClass_%d_Name' % CLASS_ID, 'DLC Cars')]), nid)
    ids = {v[2] for v in new.values()}
    assert len(ids) == 1, ids
    sid = ids.pop()
    cls += struct.pack('<IHH', CLASS_ID, sid, ICON) + b'DLC'.ljust(16, b'\0')
    mega.files[ck] = cls
    print('class %d "DLC Cars" (string %d), performanceclass.dat %d rows' % (CLASS_ID, sid, len(cls) // 24))
    if dry: raise SystemExit('dry run')
    mega.check(); mega.write()
    for p, d, _ in new.values(): open(p, 'wb').write(d)
    print('written')


if __name__ == '__main__':
    main('--dry' in sys.argv)
