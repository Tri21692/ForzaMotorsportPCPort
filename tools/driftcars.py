"""Drift-spec cars (the user's drift mode, 2026-11-01): copies of rear-wheel-drive cars as cars of their
own ("D-Spec"), set up to slide, every upgrade level alike:

  - the rear limited-slip differential locked much harder under power, and on lift too (its Accel
    torque +600, its Decel +300: the Trueno's is open, 0)
  - rear tyre grip x0.86, front x1.05: the tail steps out, the nose still bites
  - steering lock 35 degrees to 55, to hold a big angle

  python tools/driftcars.py <disc> <mods folder>

Prints each car's ordinal (the drift series' restriction names them, tools/driftseries.py). A car there
already is left as it is. Writes only into the mods folder, never the saves.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

# (the car, the new car, its name[, a rear-wheel-drive car whose drivetrain it takes]): the disc's, then
# the add-on cars (1 Nov), the front-driven Neon and the four-wheel-drive Celica made rear-driven as
# drift builds are (the Silvia's differential, its drive type in the menus)
CARS = [('NissanSilvia', 'NissanSilviaDSpec', 'Silvia S15 D-Spec'),
        ('Nissan240SX', 'Nissan240SXDSpec', '240SX D-Spec'),
        ('MazdaRX72', 'MazdaRX7DSpec', 'RX-7 D-Spec'),
        ('ToyotaTrueno', 'ToyotaTruenoDSpec', 'Trueno D-Spec'),
        ('NissanSilviaS15R', 'NissanSilviaS15RDSpec', 'Silvia Spec-R D-Spec'),
        ('DodgeNeonCoupe', 'DodgeNeonCoupeDSpec', 'Neon Coupe D-Spec', 'NissanSilvia'),
        ('ToyotaCelicaGT4', 'ToyotaCelicaGT4DSpec', 'Celica GT-Four D-Spec', 'NissanSilvia'),
        # (the user's, 16 Nov: "RX7 Spirit, Skyline R34, Miata, RX8, and the Impreza's"; the four-wheel-drive Skyline
        # and Imprezas rear-driven, as the Celica)
        ('Mazda_RX7', 'MazdaRX7SpiritDSpec', 'RX-7 Spirit R D-Spec'),
        ('NissanSkyline', 'NissanSkylineR34DSpec', 'Skyline R34 D-Spec', 'NissanSilvia'),
        ('MazdaMiata', 'MazdaMiataDSpec', 'Miata D-Spec'),
        ('MazdaRX8', 'MazdaRX8DSpec', 'RX-8 D-Spec'),
        ('WRX', 'SubaruWRXDSpec', 'Impreza WRX STi D-Spec', 'NissanSilvia'),
        ('Subaru22b', 'Subaru22bDSpec', 'Impreza 22B D-Spec', 'NissanSilvia')]
# (the MX-5 RADBUL's, MazdaMX5RadbulDSpec, taken out with the MX-5 RADBUL on 2 Nov: tools/removecar.py)
TUNE = ['--shift', 'drivetraindiff:LimittedSlipTorqueAccel=600', '--shift', 'drivetraindiff:LimittedSlipTorqueDecel=300',
        '--scale', 'tiremod:RearFrictionScale=0.86', '--scale', 'tiremod:FrontFrictionScale=1.05',
        '--scale', 'nonupgradedata.xml:MaxAngle=1.5714',
        # (the user's, 17 Nov: "up D-Spec Accel just a little bit": the final drive 7% shorter at every gearbox level,
        # more pull in every gear, the engine, class and price as they were. The thirteen there then were given it in
        # place, once, by tunecar.py; undone with =0.934579. The six of 16 Nov got their tiles' D-SPEC badge the same
        # day: tools/caricontile.py <disc> <mods> <ordinal>:badge)
        '--scale', 'transmission:FinalDriveRatio=1.07']


def ordinals(disc, mods):
    xml = addcar.Archive(disc, mods, 'Mega.ca2').files['cars' + chr(92) + 'carlist.xml'].decode('latin-1')
    return {c[1]: addcar.ordinal_of(xml, c[1]) for c in CARS if re.search(r'<car name="%s"' % c[1], xml)}


def install(disc, mods):
    here = os.path.dirname(os.path.abspath(__file__))
    have = ordinals(disc, mods)
    for src, new, name, *rwd in CARS:
        if new in have:
            print('%s: there already (%d)' % (new, have[new]))
            continue
        # (the first free ordinal past 279: 165, the removed MX-5 RADBUL D-Spec's, still has its strings and is refused)
        xml = addcar.Archive(disc, mods, 'Mega.ca2').files['cars' + chr(92) + 'carlist.xml'].decode('latin-1')
        taken = {int(o) for o in re.findall(r'Ordinal="(\d+)"', xml)}
        free = next(o for o in range(280, addcar.MAX_ORDINAL + 1) if o not in taken)
        subprocess.run([sys.executable, os.path.join(here, 'addcar.py'), disc, mods, src, new, '--name', name, '--short', name, '--ordinal', str(free)], check=True)
        drive = ['--physics-like', '%s:drivetraindiff' % rwd[0]] if rwd else []
        subprocess.run([sys.executable, os.path.join(here, 'tunecar.py'), disc, mods, new] + drive + TUNE, check=True)
    for new, o in sorted(ordinals(disc, mods).items(), key=lambda kv: kv[1]): print('%s: ordinal %d' % (new, o))


def restrict(disc, mods, extra=()):
    """The Drift Championship's entry in place (its series file's <Restrictions>: re-running the series' tool would
    number it anew): one <or> a D-Spec car there is, each with `extra` restrictions [(attribute, func, value)]."""
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    cars = sorted(ordinals(disc, mods).values())
    n = 0
    for k in list(mega.files):
        if not k.lower().startswith('events' + chr(92) + 'drift' + chr(92)): continue
        x = mega.files[k].decode('latin-1')
        body = ''.join('\t\t<or>\r\n' + ''.join('\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n' % r for r in [('carid', '=', c)] + list(extra)) + '\t\t</or>\r\n'
                       for c in cars)
        x2, m = re.subn(r'(<Restrictions>\r?\n).*?(\t</Restrictions>)', lambda q: q.group(1) + body + q.group(2), x, count=1, flags=re.S)
        if m: mega.files[k] = x2.encode('latin-1'); n += 1
    mega.check()
    mega.write()
    print('%d Drift series open to the D-Spec cars %s' % (n, cars))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    if len(sys.argv) == 4 and sys.argv[3] == 'restrict': restrict(sys.argv[1], sys.argv[2])
    else: install(sys.argv[1], sys.argv[2])
