#!/bin/bash
# (7 Nov) mtest.sh's muted game (forza-test.exe, a copy of the save disk) pressed to Career > Go Race (the Race Type
# list); the latest picture to E:/xbrt_scr/store/cur.jpg. Leaves the game running: input.txt drives it on.
L=/e/xbrt_scr/mtest
if tasklist | grep -qi "forza"; then echo "forza is running: not started"; exit 1; fi
( bash /e/xbrt_scr/mtest.sh > /dev/null 2>&1 & )
sleep 60
p() { echo "$1 0.1" >> "$L/input.txt"; sleep "${2:-1.5}"; }
p START 4; p A 5; p A 6        # title, profile
p DOWN 1.5; p A 7; p A 8       # Career Mode, Go Race
python /e/xbrt_scr/store/cur.py "$(ls -t $L/present_*.ppm | head -1)"
grep -a "DEBUG race type\|career category" $L/live.log
