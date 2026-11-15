#!/bin/bash
# A career race (type $1, series $2) on the autopilot with Kaizo on, to its end and through the results (kaizo/c1):
# the credits added logged (XBRT_KAIZO_TEST=1: nothing ends the race, the finish counts as clean).
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; L=$S/kaizo/${OUT:-c1}; H=$S/hdd_kz
XBE="C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\default.xbe"
tasklist | grep -i forza | grep -vqi forza-test && { echo "the user's game is running"; exit 1; }
taskkill //F //IM forza-test.exe > /dev/null 2>&1; sleep 2
rm -rf "$H" && cp -r "$G/run/hdd_test" "$H"; rm -rf $L; mkdir -p $L; : > $L/input.txt; cp "$G/run/forza.ini" $L/forza.ini
( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_next XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" \
    XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x960 XBRT_PRESENT_SHOT="$L/present" XBRT_PRESENT_SHOT_MS=2000 \
    XBRT_KAIZO=1 XBRT_KAIZO_TEST=${KTEST:-1} $EXTRA \
    "$G/runtime/forza-test.exe" "$XBE" > "$L/live.log" 2>&1 & )
until [ -f $L/present_025.ppm ]; do sleep 2; done
p() { echo "$1 0.1" >> $L/input.txt; sleep ${2:-2}; }
p A 4; p A 4; p A 4; p DOWN 3; p A 4; p A 5
for i in $(seq ${1:-0}); do p RIGHT 1.5; done
p A 6
for i in $(seq ${2:-0}); do p RIGHT 1.5; done
p A 5; p A 6; p A 8; p A 8; p A 8
echo "RT ${HOLD:-3}" >> $L/input.txt
for i in $(seq ${WAIT:-60}); do sleep 5; grep -a -q "kaizo: a clean finish\|kaizo: the race over" $L/live.log && break; done
sleep 12; for i in 1 2 3 4 5 6; do p A 5; done
taskkill //F //IM forza-test.exe > /dev/null 2>&1
grep -a -i "kaizo\|race.s event ordinal" $L/live.log | sort | uniq -c | sort -rn | head -30
