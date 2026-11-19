"""The 3 Nov audit's fixes to series already installed, in place: each series file edited where it is, its
seriesordinal, event ordinals, strings and logo kept (the series tools, run again, gave the re-added series new
ordinals, and the career keeps a series' results by its ordinal). Idempotent: an edit made already is skipped.

  - Forced Induction Cup (club): its field named car ordinals, not AI models (100 + ordinal): six of eight were no
    AI model at all; now Class B turbo and supercharged cars (RS6, Stealth, Evo MR, Supra, C32, 22B, 911 Turbo, R34);
  - Sunday Stroll (club): Class C and D only (a B4 Integra could enter against a D field), and two of its field
    (the RSX Type S and Celica GTS, family none) swapped for a VW R32 and a Peugeot 206, cars of its families;
  - Japanese Showdown (club): Class A and below (S and race cars could enter against a B/C field);
  - Nordschleife Endurance (spec): the AI's pit thresholds 0.35 tyres, 0.25 fuel (1.0 had them pit every lap).

  python tools/auditfix.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def series_file(mega, name):
    for k, v in mega.files.items():
        if k.lower().startswith('events' + B) and ('displayname="%s"' % name).encode() in v[:400]:
            return k
    raise SystemExit('no series named %s' % name)


def add_to_ors(x, extra):
    """Each <or> alternative given the extra restrictions (all of an <or>'s hold), once."""
    add = ''.join('\t\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n' % r for r in extra)
    def one(m):
        body = m.group(0)
        return body if add.strip().splitlines()[0].strip() in body else body.replace('\t\t</or>', add + '\t\t</or>')
    return re.sub(r'\t\t<or>\r?\n.*?\t\t</or>', one, x, flags=re.S)


def add_top(x, extra):
    """Restrictions added at the top level (all of them hold), once."""
    for r in extra:
        line = '<Restriction Attrib="%s" Func="%s" Value="%s" />' % r
        if line not in x: x = x.replace('\t</Restrictions>', '\t\t' + line + '\r\n\t</Restrictions>', 1)
    return x


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    descs = {}
    # Forced Induction Cup's field
    k = series_file(mega, 'Forced Induction Cup')
    x = mega.files[k].decode('latin-1')
    swap = dict(zip(('116', '63', '201', '13', '60', '80', '88', '92'), ('216', '163', '301', '113', '160', '180', '188', '192')))
    x = re.sub(r'(<AIField>.*?</AIField>)', lambda m: re.sub(r'aicarmodelid="(\d+)"', lambda g: 'aicarmodelid="%s"' % swap.get(g.group(1), g.group(1)), m.group(1)), x, count=1, flags=re.S)
    mega.files[k] = x.encode('latin-1')
    print(k, 'Forced Induction Cup: the field as AI models')
    # Sunday Stroll: Class C and D, two field cars swapped
    k = series_file(mega, 'Sunday Stroll')
    x = mega.files[k].decode('latin-1')
    x = add_to_ors(x, [('perfclass', '<>', c) for c in ('B', 'A', 'S', 'R')])
    x = re.sub(r'(<AIField>.*?</AIField>)', lambda m: m.group(1).replace('aicarmodelid="110"', 'aicarmodelid="120"').replace('aicarmodelid="114"', 'aicarmodelid="125"'), x, count=1, flags=re.S)
    descs[int(re.search(r'seriesdescid="(\d+)"', x).group(1))] = 'Open to Class C and D tuner and compact cars: hatchbacks, Integras and Eclipses.'
    mega.files[k] = x.encode('latin-1')
    print(k, 'Sunday Stroll: Class C and D, its field')
    # Japanese Showdown: Class A and below
    k = series_file(mega, 'Japanese Showdown')
    x = add_top(mega.files[k].decode('latin-1'), [('perfclass', '<>', 'S'), ('perfclass', '<>', 'R')])
    descs[int(re.search(r'seriesdescid="(\d+)"', x).group(1))] = 'Open to Class A and below cars originating from Japan.'
    mega.files[k] = x.encode('latin-1')
    print(k, 'Japanese Showdown: Class A and below')
    # Nordschleife Endurance's pitting
    k = series_file(mega, 'Nordschleife Endurance')
    x = mega.files[k].decode('latin-1').replace('tire="1.0" fuel="1.0"', 'tire="0.35" fuel="0.25"')
    mega.files[k] = x.encode('latin-1')
    print(k, 'Nordschleife Endurance: pit thresholds')
    mega.check(); mega.write()
    # the descriptions, in every language (EventStrings, in place by id)
    loc = addcar.disc_file(disc, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(mods, 'media', 'Loc', lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = addcar.replace_strings(open(mp, 'rb').read(), descs)  # (read before the file is opened to write: that empties it)
        open(mp, 'wb').write(d)
    print('descriptions:', ', '.join(str(i) for i in descs))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
