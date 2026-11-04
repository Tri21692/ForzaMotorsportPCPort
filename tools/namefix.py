"""The doubled car names in the mods' event texts ("the Ferrari Enzo Ferrari"), fixed in place: addcar.car_name put
the make before models whose own name has it ('Enzo Ferrari'); the series tools wrote those into their descriptions
(Time Trials', the Opens' prizes, Catch-Up's). Every language's EventStrings.str in the mods folder: each text with a
doubled name gets the model's name alone; ids, series and ordinals untouched. Idempotent.

  python tools/namefix.py <disc> <mods folder>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def one(text, o):
    """The string at UTF-16 offset o, to its NUL (replace_strings's edits put texts out of id order: the next id's
    offset is not this one's end)."""
    k = o * 2
    while k + 1 < len(text) and text[k:k + 2] != b'\0\0': k += 2
    return text[o * 2:k].decode('utf-16-le', 'replace')


def doubled(disc, mods):
    """{'Ferrari Enzo Ferrari': 'Enzo Ferrari', ...}: every car whose model's name has its make."""
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    m = mega.files[B.join(('forzadb', 'cardb', 'model.dat'))]
    mk = mega.files[B.join(('forzadb', 'cardb', 'make.dat'))]
    p = os.path.join(mods, 'media', 'Loc', 'en', 'CarDataStrings.str')
    e1, text, _, _ = addcar.read_strings(open(p if os.path.exists(p) else addcar.disc_file(disc, 'media', 'Loc', 'en', 'CarDataStrings.str'), 'rb').read())
    s = {i: text[o * 2:o2 * 2].decode('utf-16-le').rstrip('\0') for (i, o), (_, o2) in zip(e1, e1[1:])}
    makes = {struct.unpack_from('<I', mk, i)[0]: struct.unpack_from('<H', mk, i + 8)[0] for i in range(0, len(mk), 28)}
    out = {}
    for r in range(len(m) // 104):
        make, model = makes.get(struct.unpack_from('<I', m, r * 104 + 4)[0]), struct.unpack_from('<H', m, r * 104 + 12)[0]
        if make not in s or model not in s: continue
        if s[make].lower() in s[model].lower().split(): out['%s %s' % (s[make], s[model])] = s[model]
    return out


def main(disc, mods):
    fix = doubled(disc, mods)
    print('doubled names:', ', '.join(sorted(fix)) or 'none')
    loc = os.path.join(mods, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()  # (read before the file is opened to write: that empties it)
        e1, text, _, _ = addcar.read_strings(d)
        changes = {}
        for i, o in e1[:-1]:
            t = one(text, o)
            n = t
            for a, b in fix.items(): n = n.replace(a, b)
            if n != t: changes[i] = n
        if changes:
            open(mp, 'wb').write(addcar.replace_strings(d, changes))
        print(lang, '%d texts fixed' % len(changes))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
