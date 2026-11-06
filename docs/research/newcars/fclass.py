"""Class F, above S (the user's, 6 Nov: "a new rating for the hyper cars like the Bugatti ... call it F, a darker red
than S ... an option for it in the store search"). Into the mods folder only:
  Mega.ca2     performanceclass.dat: class 7 "F" (its name string, its badges' slot 7: the large tiles keep the
               keys at 6); performancesubclass.dat: subclass 24 "F" of class 7 (its label at slot 23, after P1)
  MegaXPR.ca2  the badge strips grown (fclassart.py's art): sym_classlabel slot 23, sym_classlabel-trial 24,
               ico_class / -med / _border slots 6 (R's, a filler) and 7, every language's ico_class-lg slot 7
  media/Loc/*/CarDataStrings.str  "Class F" twice (IDS_PerformanceSubclass_24_Name, IDS_PerformanceClass_7_Name)
The game's own class formula gives it through the runtime (hle_fclass.c: S1 past F_BOUND becomes 24), and
classfix.py lists the cars it fits.  python fclass.py [--dry]"""
import sys, os, struct, shutil
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
sys.path.insert(0, r'E:\xbrt_scr\newcars')
import numpy as np
from PIL import Image
import addcar, addmake, fclassart
B = chr(92)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = r'E:\Forza Motorsport Remastered\run\mods_track'
CLASS_ID, SUB_ID, CLASS_ICON, SUB_ICON = 7, 24, 7, 23


def grow(d, slots, slot_h):
    """An XPR0 linear A8R8G8B8 strip with these RGBA slots (each slot_h high, its width) added at the bottom."""
    hdr = struct.unpack_from('<I', d, 8)[0]
    fmt = (struct.unpack_from('<I', d, 24)[0] >> 8) & 0xFF
    assert fmt == 0x12, 'not linear A8R8G8B8: %02x' % fmt
    w, h, pitch = addmake.strip_size(d)
    assert h % slot_h == 0, (w, h, slot_h)
    data = bytearray(d[hdr:hdr + pitch * h])
    for im in slots:
        a = np.asarray(im.convert('RGBA'), np.uint8)
        assert a.shape[:2] == (slot_h, w), (a.shape, slot_h, w)
        sl = bytearray(pitch * slot_h)
        for y in range(slot_h):
            sl[y * pitch:y * pitch + w * 4] = a[y][:, [2, 1, 0, 3]].tobytes()  # BGRA
        data += sl
    nh = h + slot_h * len(slots)
    assert nh <= 4096
    data += bytes(-len(data) % 2048)
    head = bytearray(d[:hdr])
    size = struct.unpack_from('<I', head, 28)[0]
    struct.pack_into('<I', head, 28, (size & ~(0xFFF << 12)) | ((nh - 1) << 12))
    struct.pack_into('<I', head, 4, len(head) + len(data))
    return bytes(head) + bytes(data), h // slot_h


def strip_slot(d, i, slot_h):
    hdr = struct.unpack_from('<I', d, 8)[0]
    w, h, pitch = addmake.strip_size(d)
    px = np.frombuffer(d[hdr:hdr + pitch * h], np.uint8).reshape(h, pitch)[:, :w * 4].reshape(h, w, 4)[..., [2, 1, 0, 3]]
    return Image.fromarray(px[i * slot_h:(i + 1) * slot_h].copy(), 'RGBA')


def main(dry):
    art = fclassart.make()
    mega = addcar.Archive(DISC, MODS, 'Mega.ca2')
    xpr = addcar.Archive(DISC, MODS, 'MegaXPR.ca2')
    ck, sk = B.join(('forzadb', 'cardb', 'performanceclass.dat')), B.join(('forzadb', 'cardb', 'performancesubclass.dat'))
    cls, sub = bytes(mega.files[ck]), bytes(mega.files[sk])
    if any(struct.unpack_from('<I', cls, o)[0] == CLASS_ID for o in range(0, len(cls), 24)):
        raise SystemExit('class F is in already')
    # strings, every language alike (each holds the same ids: they gain the same two)
    loc = os.path.join(MODS, 'media', 'Loc')
    langs = sorted(os.listdir(loc))
    new = {}
    for lang in langs:
        p = os.path.join(loc, lang, 'CarDataStrings.str')
        d = open(p, 'rb').read()
        e1 = addcar.read_strings(d)[0]
        nid = max(i for i, _ in e1[:-1]) + 1
        new[lang] = (p, addcar.write_strings(d, [('IDS_PerformanceSubclass_%d_Name' % SUB_ID, 'Class F'), ('IDS_PerformanceClass_%d_Name' % CLASS_ID, 'Class F')]), nid)
    ids = {v[2] for v in new.values()}
    assert len(ids) == 1, ids
    sid = ids.pop()  # the subclass's name; the class's sid + 1
    print('strings: Class F as %d (subclass) and %d (class), %d languages' % (sid, sid + 1, len(new)))
    # the tables
    cls += struct.pack('<IHH', CLASS_ID, sid + 1, CLASS_ICON) + b'F'.ljust(16, b'\0')
    sub += struct.pack('<IIHH', SUB_ID, CLASS_ID, sid, SUB_ICON) + b'F'.ljust(16, b'\0')
    mega.files[ck], mega.files[sk] = cls, sub
    print('performanceclass.dat: %d rows; performancesubclass.dat: %d rows' % (len(cls) // 24, len(sub) // 28))
    # the badges
    fe = 'frontend' + B
    def put(name, slots, slot_h):
        k = next(x for x in xpr.files if x.lower() == (fe + name).lower())
        xpr.files[k], first = grow(bytes(xpr.files[k]), slots, slot_h)
        print('  %-28s slots %d.. added %d' % (name, first, len(slots)))
    put('sym_classlabel.xpr', [art['sym_classlabel']], 32)
    put('sym_classlabel-trial.xpr', [art['sym_classlabel-trial']], 32)
    for name, h in (('ico_class.xpr', 15), ('ico_class-med.xpr', 18), ('ico_class_border.xpr', 60)):
        k = next(x for x in xpr.files if x.lower() == (fe + name).lower())
        filler = strip_slot(bytes(xpr.files[k]), 5, h)  # (slot 6: R's again, as the large tiles' keys are there)
        put(name, [filler, art[name[:-4]]], h)
    for lang in ('', 'de', 'en', 'es', 'fr', 'it', 'ja', 'ko', 'zh'):
        put((lang + B if lang else '') + 'ico_class-lg.xpr', [art[(lang + '_' if lang else '') + 'ico_class-lg']], 60)
    if dry: raise SystemExit('dry run: nothing written')
    for a in (mega, xpr): a.check()
    for a in (mega, xpr): a.write()
    for lang, (p, d, _) in new.items(): open(p, 'wb').write(d)
    print('written')


if __name__ == '__main__':
    main('--dry' in sys.argv)
