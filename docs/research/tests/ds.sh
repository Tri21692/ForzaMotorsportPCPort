#!/bin/bash
# ds.sh <track> <seconds> <keep>: a muted Arcade race on the pad pilot held in a drift (XBRT_PILOT_DRIFT), any car
# taken for a D-Spec (XBRT_DSPEC_TEST), the slide's speed hold at <keep> (17 Nov). Prints the pilot's mean speed,
# how far along the line it got and the hold's own lines.
S=/e/xbrt_scr/vid; O=$S/ds_$3; T=$1; N=$2
tasklist | grep -qi forza && { echo "forza is running: not started"; exit 1; }
SHOT_MS=1000 EXTRA="XBRT_PILOT=${TOP:-60} XBRT_PILOT_ONCE=1 XBRT_PILOT_DRIFT=${DRIFT:-25} XBRT_RIVAL=0 XBRT_DSPEC_TEST=1 XBRT_DSPEC_KEEP=$3" bash $S/run.sh $T $O 2 0 0 0 > $S/ds.out 2>&1
sleep $N
taskkill //F //IM forza-test.exe > /dev/null 2>&1
echo "keep $3: $(grep -a 'pilot:' $O/live.log | tr -d ',' | awk '$5 > 3 {n++; s += $5; a = $10; if (a < 0) a = -a; sl += a; if (a > 10) d++} END {printf "%d lines moving, mean %.1f m/s, mean slip %.1f deg, %d lines over 10 deg", n, s / n, sl / n, d}'); last $(grep -a 'pilot:' $O/live.log | tail -1 | cut -c1-40)"
grep -a "d-spec:" $O/live.log | cut -c1-160 | tail -8
