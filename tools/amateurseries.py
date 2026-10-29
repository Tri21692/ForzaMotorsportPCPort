"""Four more Amateur (Club) series, through addseries.py (run again, each is replaced):

  - Sunday Stroll (any level): tuner and compact cars, the Hatch, Integra and Eclipse families
    and the other small coupes and saloons by car;
  - Beetle Face Off (level 5): Volkswagen Beetles only (carid 48), upgrades allowed; stock and
    upgraded Beetles against you;
  - Japanese Showdown (level 10): Japanese cars (location, the make's country);
  - Underdog Challenge (level 30): Class A or below (perfclass D, C, B or A), against the
    Class S Championship's field.

Restrictions are alternatives (each <or>) of conditions that all hold, as the disc's
(pro series 8: Viper and not R, or Corvette and not R). An AI car model id is 100 + the car's
ordinal stock, 1000 more a stage of upgrades (ai\\aicarmodellist.xml). Run after
careertimetrial.py: addseries.py numbers the series after the highest seriesordinal there is,
and the Time Trial's are fixed at 85-92. Event ordinals 371-384, after the Time Trial's.

  python tools/amateurseries.py <disc> <mods folder>
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addseries

EVENT_ORDINAL = 371
SERIES_ID = 229          # after the Forced Induction Cup's 228

# AI fields: eight cars, raced by the drivers given for Easy, Medium and Hard
TUNER_CARS = [107, 110, 114, 109, 124, 102, 208, 207]    # Civic Type R, RSX Type S, Celica GTS, Integra Type R, Eclipse GSX, Focus SVT, Mini Cooper S, Mazda 3
BEETLE_CARS = [148, 1148, 2148, 3148, 148, 1148, 2148, 3148]  # the Beetle at each upgrade stage
JAPAN_CARS = [192, 113, 106, 253, 116, 105, 127, 191]    # Skyline R34, Supra, RX-7, NSX-R, Evo VIII, WRX STi, 350Z, S2000
CLASS_S_CARS = [136, 173, 143, 199, 239, 137, 285, 202]  # the Class S Championship's: Enzo, Carrera GT, Zonda, Cerbera, ME412, F50, Tuscan R, S7

# who may enter: a list of alternatives, each a list of (attribute, func, value) that all hold
TUNER = ([[('family', '=', f)] for f in ('Hatch', 'Integra', 'Eclipse')] +
         # RSX, Celica GTS, Civic SI, Tiburon, Protege, Del Sol, Jetta, Talon, the 1.8 Celica, APR's Celica
         [[('carid', '=', o)] for o in (10, 14, 44, 47, 49, 52, 61, 127, 164, 226)])
BEETLE = [[('carid', '=', 48)]]
JAPAN = [[('location', '=', 'Japan')]]
CLASS_A_OR_BELOW = [[('perfclass', '=', c)] for c in 'DCBA']

# (name, level, description, icon (a disc series' logo), the car won (ordinal) and its name,
#  who may enter, the AI field, the drivers (Easy, Medium, Hard), duplicates, 1st place's xp,
#  events (track ordinal, laps))
SERIES = [
    ('Sunday Stroll', 0, 'An easy drive for tuner and compact cars: hatchbacks, small coupes and saloons.',
     27, 174, 'Mugen Civic Type R', TUNER, TUNER_CARS, (22, 36, 50), False, 3000,
     [(26, 3), (47, 3), (46, 2)]),                      # Tsukuba, Silverstone Club, Road Atlanta Club
    ('Beetle Face Off', 5, 'Volkswagen Beetles only. Upgrade yours as far as you like.',
     41, 203, 'Mugen S2000', BEETLE, BEETLE_CARS, (25, 36, 50), True, 5000,
     [(1, 2), (26, 3), (27, 2)]),                       # Laguna Seca, Tsukuba, Alpine Ring
    ('Japanese Showdown', 10, 'Japanese cars only.',
     4, 194, 'Mines Skyline GT-R R34', JAPAN, JAPAN_CARS, (21, 35, 49), False, 7000,
     [(3, 2), (26, 3), (4, 3), (6, 2)]),                # Fujimi Kaido, Tsukuba, Fujimi Kaido Short, Sunset Peninsula
    ('Underdog Challenge', 30, 'Class A cars at most, against a field of Class S supercars.',
     11, 40, 'Koenigsegg CC', CLASS_A_OR_BELOW, CLASS_S_CARS, (24, 35, 49), False, 18000,
     [(27, 2), (18, 2), (57, 2), (1, 3)]),              # Alpine Ring, New York, Maple Valley Reverse, Laguna Seca
]
PLACES = ((10, 1.0), (8, 0.7), (6, 0.5), (5, 0.4), (4, 0.3), (3, 0.2), (2, 0.1), (1, 0.0))   # points, share of 1st's xp


def restrictions(alternatives):
    if len(alternatives) == 1:
        return ''.join('\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n' % r for r in alternatives[0])
    return ''.join('\t\t<or>\r\n' + ''.join('\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n' % r for r in alt) + '\t\t</or>\r\n'
                   for alt in alternatives)


def series_xml(k, ordinal, name, level, icon, prize, allowed, field, drivers, duplicates, xp, events):
    ai = ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n'
                 % (car, driver, skill) for driver, skill in zip(drivers, ('Easy', 'Medium', 'Hard')) for car in field)
    x = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{SERIES_NAME_ID}" seriesdescid="{SERIES_DESC_ID}" '
         'seriesid="%d" seriesordinal="0" seriesorder="0" Icon="%d"%s>\r\n'
         '\t<Scoring>\r\n\t\t<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>\r\n' %
         (name, SERIES_ID + k, icon, ' Level="%d"' % level if level else '', prize, prize) +
         ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(2, 9)) +
         '\t</Scoring>\r\n\t<Restrictions>\r\n' + restrictions(allowed) + '\t</Restrictions>\r\n'
         '\t<AIField>\r\n' + ai + '\t</AIField>\r\n')
    for track, laps in events:
        x += ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{EVENT_NAME_ID}" eventdescid="{EVENT_DESC_ID}" '
              'type="Single" leaderboard="1450">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
              '\t\t<AIField NumAICars="7" random="false" byclass="false" duplicates="%s" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting aipitting tire="0.01" fuel="0.01" engine="0.5" transmission="0.5" suspension="0.5" spreadpercent="0" />\r\n'
              '\t\t</AIModeSettings>\r\n\t\t<Scoring>\r\n' % (ordinal, name, ordinal, track, laps, 'true' if duplicates else 'false') +
              ''.join('\t\t\t<score pos="%d" pts="%d" xp="%d"></score>\r\n' % (p + 1, pts, int(round(xp * share / 500)) * 500)
                      for p, (pts, share) in enumerate(PLACES)) +
              '\t\t</Scoring>\r\n\t</event>\r\n')
        ordinal += 1
    return x + '</series>\r\n', ordinal


def install(disc, mods):
    ordinal = EVENT_ORDINAL
    with tempfile.TemporaryDirectory() as tmp:
        for k, (name, level, desc, icon, prize, car, allowed, field, drivers, dup, xp, events) in enumerate(SERIES):
            x, ordinal = series_xml(k, ordinal, name, level, icon, prize, allowed, field, drivers, dup, xp, events)
            p = os.path.join(tmp, 'series%d.xml' % k)
            open(p, 'w', encoding='latin-1', newline='').write(x)
            addseries.main(disc, mods, 'club', p, name, '%s Win the series to win the %s.' % (desc, car), event_name=name)


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2])
