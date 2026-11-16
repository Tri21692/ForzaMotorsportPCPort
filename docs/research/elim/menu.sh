#!/bin/bash
# The muted test game (forza-test.exe, mods_next, a copy of the save) to Career > Go Race, left running:
# press.sh <keys...> presses on and saves the latest picture as E:/xbrt_scr/elim/cur.jpg.
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; L=$S/elim/menu; H=$S/hdd_elim
XBE="C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\default.xbe"
tasklist | grep -qi forza && { echo "forza is running: not started"; exit 1; }
rm -rf "$H" && cp -r "$G/run/hdd_test" "$H"; rm -rf $L; mkdir -p $L; : > $L/input.txt; cp "$G/run/forza.ini" $L/forza.ini
( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_next XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" \
    XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x960 XBRT_PRESENT_SHOT="$L/present" XBRT_PRESENT_SHOT_MS=1000 XBRT_KAIZO=0 $EXTRA \
    "$G/runtime/forza-test.exe" "$XBE" > $L/live.log 2>&1 & )
until [ -f $L/present_040.ppm ]; do sleep 2; done
p() { echo "$1 0.1" >> $L/input.txt; sleep ${2:-2}; }
p A 4; p A 4; p A 4; p DOWN 3; p A 4; p A 6
bash $S/elim/press.sh
