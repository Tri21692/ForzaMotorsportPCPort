#!/bin/bash
# mtest.sh: the modded game on a copy of the save disk, muted, windowed, the pad from E:/xbrt_scr/mtest/input.txt,
# a picture every 2 s in E:/xbrt_scr/mtest/present*, the log in E:/xbrt_scr/mtest/live.log (Mayhem's career check)
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; L=$S/mtest; H=$S/hdd_mtest
XBE="C:\\Users\\maste\\Downloads\\extract-xiso-win32-release\\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\\default.xbe"
if tasklist | grep -qi "forza"; then echo "game running"; exit 1; fi
rm -rf "$H" "$L" && cp -r "$G/run/hdd_test" "$H" && mkdir -p "$L" && : > "$L/input.txt"
cp "$G/run/forza.ini" "$L/forza.ini"
cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_track XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
  XBRT_NO_PROJ_SHADOWS=VancouverLoop,VancouverLoopReverse XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" \
  XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x960 \
  XBRT_PRESENT_SHOT="$L/present" XBRT_PRESENT_SHOT_MS=2000 \
  "$G/runtime/forza-test.exe" "$XBE" > "$L/live.log" 2>&1
