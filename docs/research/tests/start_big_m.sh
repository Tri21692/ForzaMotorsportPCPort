#!/bin/bash
# A muted, windowed run of the modded game on a copy of the test disk (the saves untouched), its input from
# input.txt as lines are added, a screenshot a second in shots/.   bash start.sh
G="/e/Forza Motorsport Remastered"; L=/e/xbrt_scr/store
tasklist | grep -qi forza && { echo "forza is running"; exit 1; }
rm -rf $L/hdd $L/shots && mkdir -p $L/shots && cp -r "$G/run/hdd_test" $L/hdd && : > $L/input.txt
cp "$G/run/forza.ini" $L/forza.ini; cp "$G/run/achievements.txt" $L/ 2>/dev/null; cp "$G/run/prizematch.txt" $L/ 2>/dev/null
cd "$G/run"
env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=${MODS:-mods_next} XBRT_HDD=$L/hdd XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
  XBRT_INPUT_ONLY=1 XBRT_INPUT_LIVE=$L/input.txt XBRT_SETTINGS=$L/forza.ini XBRT_ACHIEVEMENTS=$L/achievements.txt XBRT_PRIZEMATCH=$L/prizematch.txt \
  XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1920x1080 XBRT_PRESENT_SHOT=$L/shots/s XBRT_PRESENT_SHOT_MS=1000 timeout 3600 \
  "$G/runtime/forza-test.exe" "C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\default.xbe" > $L/live.log 2>&1 &
