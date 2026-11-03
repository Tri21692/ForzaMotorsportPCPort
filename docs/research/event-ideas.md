# Event type ideas (2 Nov, for the user to pick; nothing built)

Each one is something the runtime can already see or change: racers' places and progress, lap
counts, the race clock, penalties (off-track), car speed and slide angle, and a HUD panel like the
drift and Catch-Up ones. Rough effort in brackets.

1. **Elimination.** 8 cars; at the end of each lap the last car is knocked out (its run ended, as
   the Catch-Up hook already does). Last car standing wins. [small]
2. **Overtake Rush.** Start last of 8 on a short race; points for every place gained, lost again
   for every place given back; targets for 1st, 2nd and 3rd like drift events. [small]
3. **Checkpoint Rush.** An arcade countdown: 30 s on the clock, each lap (or sector) adds time;
   keep it above zero for as many laps as possible. Medals by laps reached. [medium]
4. **Clean Racer.** A normal race, but every off-track penalty or hard hit costs a place at the
   finish (or ends the run on "Hardcore"). Rewards tidy driving. [small]
5. **Speed Trap.** The speed through 3 fixed points on the lap is added up; best total wins.
   Good on Fuji's straight and Le Mans-style tracks. [small]
6. **Slipstream Challenge.** Points for every second spent close behind another car (drafting),
   doubled when you then pass it. [medium]
7. **Reverse Grid Handicap.** The faster your car's class, the further back and the more laps
   you give; the AI field gets a head start in seconds. [small]
8. **Pace Car.** Stay within 20 m of an AI pace car for a whole lap without passing it; the pace
   car speeds up each lap. Fails if you drop back or overtake. [medium]
9. **Drift Zones.** Drift events where only marked sectors score (the hairpin, the Dunlop loop),
   with a multiplier for linking zones. Builds on the drift scorer. [medium]
10. **King of the Hill (time attack ladder).** Five AI "rivals" with set lap times; beat each in
    turn to unlock the next, the last one's car as the prize. [medium]
11. **Bounty Duel.** One-on-one against a named rival in their car; win and their car is yours
    (works with the Catch-Up duel code). [small, needs prizes]
12. **Endurance Lite.** A 15-minute timed race (not laps); most laps when the clock runs out wins,
    with a pit stop required once. [medium-large: pit stop detection]
13. **Crash Course (later, with takedowns).** Burnout-style: points for taking AI cars out,
    a timer, respawns. Depends on the Quick Race takedown modifier working first. [large]
