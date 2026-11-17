#!/bin/bash
# rv.sh <track> <seconds> [env...]: a muted race on the pad pilot with the matched rival forced on (XBRT_RIVAL_TEST),
# its CarInits logged (17 Nov). Then the game closed and the log's lines that matter.
S=/e/xbrt_scr/vid; O=$S/rv; T=$1; N=$2; shift 2
tasklist | grep -qi forza && { echo "forza is running: not started"; exit 1; }
SHOT_MS=500 EXTRA="XBRT_PILOT=${TOP:-60} XBRT_PILOT_ONCE=1 XBRT_RIVAL=${RIVAL:-log} XBRT_RIVAL_TEST=1 $*" bash $S/run.sh $T $O 2 0 0 0 > $S/rv.out 2>&1
sleep $N
taskkill //F //IM forza-test.exe > /dev/null 2>&1
grep -a -A9 "matched rival\|rival pace" $O/live.log | cut -c1-300 | head -${LINES_OUT:-120}
grep -a -c "pilot:" $O/live.log
