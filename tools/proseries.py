"""Four more Professional (Spec list) series, the user's picks of 2026-11-01:

  Shipyard Grand Prix      Class R-GT, level 30: Pacific Shipyards Circuit and Circuit II, 4, 4 and 6 laps
  Rear-Engine Rebellion    Class S, rear- or mid-engined only, level 25, against such a field
  Rivals                   Class A, level 20: four one-on-one races against a Class S car's hard driver
  Nordschleife Endurance   Class R-GTS, level 40: one race of 3 laps of the Nurburgring, pit stops on

No prize cars yet (the user's: the four add-on cars of that night will be prizes somehow, sorted
later): first place pays only its credits, scaled to the level as the disc's series pay theirs.

Rivals' duels are two-car races, as the Catch-Up Challenge's: the runtime gives a head start only on
a Catch-Up track (by its racing line's length), so the duels keep off Laguna Seca, Road Atlanta,
Maple Valley and Silverstone.

  python tools/proseries.py <disc> <mods folder>
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import amateurseries as A

B = '\\'
KIND = 'spec'
EVENT_ORDINAL = 389      # after the Catch-Up Challenge's 385-388
SERIES_ID = 234          # after its 233
# rear- and mid-engined Class S cars, as AI car models (100 + ordinal): F50, Zonda, F40, XJ220, GT40 Mk II,
# Carrera GT, Enzo, Saleen S7
REAR_S_CARS = [137, 143, 168, 139, 138, 173, 136, 202]
REAR_S = '\t\t<Restriction Attrib="perfclass" Func="=" Value="S" />\r\n\t\t<or>\r\n' \
         '\t\t\t<Restriction Attrib="engineplacement" Func="=" Value="rear" />\r\n' \
         '\t\t\t<Restriction Attrib="engineplacement" Func="=" Value="mid" />\r\n\t\t</or>\r\n'

# (name, level, description, logo (art, captions; or an existing tile's number), who may enter (restrictions' XML), the AI field (a
#  disc Spec series' to copy, or car models with drivers), AI cars a race, events (track, laps, 1st's xp))
SERIES = [
    ('Shipyard Grand Prix', 30, 'Open to Class R-GT cars. Three races round the Pacific Shipyards Circuit, both ways.',
     (dict(tile=12, clear=[(80, 112)]), [('SHIPYARD GP', 84, 22, 'chrome')]),
     '\t\t<Restriction Attrib="perfsubclass" Func="=" Value="GT" />\r\n', ('spec', 18), 7,
     [(82, 4, 40000), (83, 4, 40000), (82, 6, 60000)]),
    ('Rear-Engine Rebellion', 25, 'Open to Class S cars with the engine behind the driver.',
     11,  # the Class S logo (the small strip's free tiles ran out after the Shipyard Grand Prix's)
     REAR_S, (REAR_S_CARS, (24, 35, 49)), 7,
     [(1, 3, 30000), (8, 3, 30000), (25, 3, 30000)]),
    ('Rivals', 20, 'Open to Class A cars. Four one-on-one races against a Class S rival.',
     10,  # the Class A logo
     '\t\t<Restriction Attrib="perfclass" Func="=" Value="A" />\r\n', (A.LOWER_S_CARS, (49, 49, 49)), 1,
     [(26, 2, 22000), (27, 2, 22000), (8, 2, 22000), (18, 2, 22000)]),
    ('Nordschleife Endurance', 40, 'Open to Class R-GTS cars. Three laps of the Nordschleife, pit stops and all.',
     13,  # the Class R-GTS logo
     '\t\t<Restriction Attrib="perfsubclass" Func="=" Value="GTS" />\r\n', ('spec', 19), 7,
     [(19, 3, 150000)]),
]
PLACES = A.PLACES


def ai_field(mega, field):
    """The <AIField> block: a disc Spec series' own, or the cars with each driver (Easy, Medium, Hard)."""
    if isinstance(field[0], str):
        kind, n = field
        x = next(v for k, v in mega.disc.items() if k.lower() == B.join(('events', kind, 'ser%05d.xml' % n))).decode('latin-1')
        return '\t' + re.search(r'<AIField>.*?</AIField>', x, re.S).group(0) + '\r\n'
    cars, drivers = field
    skills = ('Easy', 'Medium', 'Hard') if len(set(drivers)) > 1 else ('Hard', 'Hard', 'Hard')
    return '\t<AIField>\r\n' + ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n'
                                       % (car, driver, skill) for driver, skill in zip(drivers, skills) for car in cars) + '\t</AIField>\r\n'


def series_xml(mega, k, ordinal, name, level, allowed, field, n_ai, events):
    x = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{SERIES_NAME_ID}" seriesdescid="{SERIES_DESC_ID}" '
         'seriesid="%d" seriesordinal="0" seriesorder="0" Icon="{ICON}" Level="%d">\r\n'
         '\t<Scoring>\r\n' % (name, SERIES_ID + k, level) +
         ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(1, n_ai + 2)) +
         '\t</Scoring>\r\n\t<Restrictions>\r\n' + allowed + '\t</Restrictions>\r\n' + ai_field(mega, field))
    places = PLACES[:n_ai + 1] if n_ai > 1 else ((10, 1.0), (0, 0.0))
    for track, laps, xp in events:
        x += ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{EVENT_NAME_ID}" eventdescid="{EVENT_DESC_ID}" '
              'type="Single" leaderboard="1450">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
              '\t\t<AIField NumAICars="%d" random="%s" byclass="false" duplicates="false" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting aipitting tire="%s" fuel="%s" engine="0.5" transmission="0.5" suspension="0.5" spreadpercent="0" />\r\n'
              '\t\t</AIModeSettings>\r\n\t\t<Scoring>\r\n'
              % (ordinal, name, ordinal, track, laps, n_ai, 'true' if n_ai == 1 else 'false',
                 '1.0' if laps >= 3 and track == 19 else '0.01', '1.0' if laps >= 3 and track == 19 else '0.01') +
              ''.join('\t\t\t<score pos="%d" pts="%d" xp="%d"></score>\r\n' % (p + 1, pts, int(round(xp * share / 500)) * 500)
                      for p, (pts, share) in enumerate(places)) +
              '\t\t</Scoring>\r\n\t</event>\r\n')
        ordinal += 1
    return x + '</series>\r\n', ordinal


def install(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    ordinal = EVENT_ORDINAL
    with tempfile.TemporaryDirectory() as tmp:
        for k, (name, level, desc, spec, allowed, field, n_ai, events) in enumerate(SERIES):
            x, ordinal = series_xml(mega, k, ordinal, name, level, allowed, field, n_ai, events)
            if isinstance(spec, int): x = x.replace('{ICON}', str(spec))
            p = os.path.join(tmp, 'series%d.xml' % k)
            open(p, 'w', encoding='latin-1', newline='').write(x)
            png = None if isinstance(spec, int) else A.logo(disc, mods, *spec, tmp)
            addseries.main(disc, mods, KIND, p, name, desc, event_name=name, logo='%s,%s' % (png, png) if png else None)
            print('%s: events %d-%d' % (name, ordinal - len(events), ordinal - 1))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2])
