#!/bin/bash
# lapaudit.sh <track> <seconds> [speed m/s]: a muted Arcade lap of a track on the line-following autopilot
# (vid/run.sh), a picture a second and the position trace, for the Pacific Shipyards Circuit audit (17 Nov).
# Then the game closed; the pictures in vid/lap_<track>/p_*.ppm, the trace vid/lap_<track>/pos.trace.
S=/e/xbrt_scr/vid; T=$1; N=$2; O=$S/lap_$T
tasklist | grep -qi forza && { echo "forza is running: not started"; exit 1; }
SHOT_MS=1000 EXTRA="XBRT_INPUT_ONLY=1 XBRT_RIVAL=0" bash $S/run.sh $T $O 2 ${3:-22} 0 0 > $S/lapaudit.out 2>&1
sleep $N
taskkill //F //IM forza-test.exe > /dev/null 2>&1
ls $O/p_*.ppm | wc -l; ls -la $O/pos.trace 2>/dev/null
grep -a -i "not a number\|fell\|scoreboards:\|indirect call\|assert" $O/live.log | head -8
grep -a "quick race: lap\|lap [0-9]" $O/live.log | tail -3 | cut -c1-140
