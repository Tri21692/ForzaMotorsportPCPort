#!/bin/bash
# drtest.sh <seconds> <track> <class presses> <car rights> <env...>: a drift tuning run (pictures 500 ms apart) for
# that many seconds of driving, then the game closed and the slides counted: seconds by the slide's angle, the
# stops (a spin or a wall), the mean speed.
N=$1; T=$2; C=$3; K=$4; shift 4
S=/e/xbrt_scr/vid; O=$S/p2
SHOT_MS=500 EXTRA="XBRT_PILOT_ONCE=1 XBRT_QR_FIELD=0 $*" bash $S/run.sh $T $O 1 0 $C $K > /dev/null || exit 1
until [ "$(grep -a -c 'pilot:' $O/live.log)" -ge $((N + 10)) ] || grep -a -q "lap 1 of 1" $O/live.log || ! tasklist | grep -qi forza-test; do sleep 3; done
taskkill //F //IM forza-test.exe > /dev/null 2>&1
grep -a "pilot:" $O/live.log | tr -d ',()' | awk 'NR>10 {s=$10; if (s<0) s=-s; v+=$5; n++; if ($5<4) st++; if (s<8) a++; else if (s<18) b++; else if (s<45) c++; else if (s<70) d++; else e++}
  END {printf "seconds: straight %d, 8-18 deg %d, 18-45 deg %d, 45-70 deg %d, over 70 %d; stopped %d; mean %.1f m/s\n", a, b, c, d, e, st, v/n}'
