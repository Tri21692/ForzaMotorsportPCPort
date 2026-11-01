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

# (the disc's car, the new car, its name)
CARS = [('NissanSilvia', 'NissanSilviaDSpec', 'Silvia S15 D-Spec'),
        ('Nissan240SX', 'Nissan240SXDSpec', '240SX D-Spec'),
        ('MazdaRX72', 'MazdaRX7DSpec', 'RX-7 D-Spec'),
        ('ToyotaTrueno', 'ToyotaTruenoDSpec', 'Trueno D-Spec')]
TUNE = ['--shift', 'drivetraindiff:LimittedSlipTorqueAccel=600', '--shift', 'drivetraindiff:LimittedSlipTorqueDecel=300',
        '--scale', 'tiremod:RearFrictionScale=0.86', '--scale', 'tiremod:FrontFrictionScale=1.05',
        '--scale', 'nonupgradedata.xml:MaxAngle=1.5714']


def ordinals(disc, mods):
    xml = addcar.Archive(disc, mods, 'Mega.ca2').files['cars' + chr(92) + 'carlist.xml'].decode('latin-1')
    return {new: addcar.ordinal_of(xml, new) for _, new, _ in CARS if re.search(r'<car name="%s"' % new, xml)}


def install(disc, mods):
    here = os.path.dirname(os.path.abspath(__file__))
    have = ordinals(disc, mods)
    for src, new, name in CARS:
        if new in have:
            print('%s: there already (%d)' % (new, have[new]))
            continue
        subprocess.run([sys.executable, os.path.join(here, 'addcar.py'), disc, mods, src, new, '--name', name, '--short', name], check=True)
        subprocess.run([sys.executable, os.path.join(here, 'tunecar.py'), disc, mods, new] + TUNE, check=True)
    for new, o in sorted(ordinals(disc, mods).items(), key=lambda kv: kv[1]): print('%s: ordinal %d' % (new, o))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2])
