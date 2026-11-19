#!/bin/bash
# td17.sh <track> <seconds> [env...]: a muted Mayhem race on the pad pilot, the takedown camera staged every 10 s with
# the player's car knocked 45 degrees across as it leaves (XBRT_TD_KICK), for the takedown pilot's hold on the road
# and the car's hold on the ground (17 Nov). Then the game closed and the log's lines that matter.
S=/e/xbrt_scr/vid; O=$S/td17; T=$1; N=$2; shift 2
tasklist | grep -qi forza && { echo "forza is running: not started"; exit 1; }
SHOT_MS=500 EXTRA="XBRT_PILOT=${TOP:-60} XBRT_PILOT_ONCE=1 XBRT_MAYHEM_TEST=1 XBRT_TD_TEST=14 XBRT_TD_REPEAT=${REPEAT:-14} XBRT_TD_KICK=${KICK:-45} XBRT_CHAOS=1 $*" bash $S/run.sh $T $O 2 0 0 0 > $S/td17.out 2>&1
sleep $N
taskkill //F //IM forza-test.exe > /dev/null 2>&1
grep -a "td test: the\|td test: over\|set on the line\|kept on the road\|chaos\|on a wall\|respawned\|taken down\|takedown [0-9]" $O/live.log | cut -c1-200 | tail -60
echo "pilot lines: $(grep -a -c 'pilot:' $O/live.log); stopped (under 4 m/s): $(grep -a 'pilot:' $O/live.log | tr -d ',' | awk '$5 < 4' | wc -l); over 30 deg across: $(grep -a 'pilot:' $O/live.log | tr -d ',' | awk '{s=$10; if (s<0) s=-s; if (s>30) n++} END {print n+0}')"
