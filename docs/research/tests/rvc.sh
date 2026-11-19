#!/bin/bash
# rvc.sh start | press <key[:wait]>... | stop: the New mods game (forza-test.exe) on a copy of the save disk, muted,
# pressed through the career by hand (17 Nov, the matched rival in the Touge's own events); after the presses the
# latest picture is E:/xbrt_scr/vid/rvc_cur.jpg. The log: E:/xbrt_scr/vid/rvc/live.log.
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; L=$S/vid/rvc; H=$S/hdd_rvc
XBE="C:\\Users\\maste\\Downloads\\extract-xiso-win32-release\\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\\default.xbe"
pic() { python -c "
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB'); im.thumbnail((800, 600)); im.save('E:/xbrt_scr/vid/rvc_cur.jpg', quality=80)" "$(ls -t $L/present_*.ppm | head -1)"; }
case $1 in
start)
  if tasklist | grep -qi "forza"; then echo "game running"; exit 1; fi
  rm -rf "$H" "$L" && cp -r "$G/run/hdd_test" "$H" && mkdir -p "$L" && : > "$L/input.txt" && cp "$G/run/forza.ini" "$L/forza.ini"
  ( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_next XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_NO_PROJ_SHADOWS=VancouverLoop,VancouverLoopReverse XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" \
    XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=800x600 XBRT_KAIZO=0 \
    XBRT_PRESENT_SHOT="$L/present" XBRT_PRESENT_SHOT_MS=1000 XBRT_RIVAL=log XBRT_PILOT=45 XBRT_PILOT_ONCE=1 XBRT_QR_ALWAYS=1 $RVC_ENV \
    "$G/runtime/forza-test.exe" "$XBE" > "$L/live.log" 2>&1 & ) > /dev/null 2>&1
  sleep 55; pic ;;
press)
  shift
  for k in "$@"; do echo "${k%%:*} 0.1" >> "$L/input.txt"; w=${k#*:}; [ "$w" = "$k" ] && w=1.5; sleep $w; done
  sleep 1.5; pic ;;
stop) taskkill //F //IM forza-test.exe > /dev/null 2>&1 ;;
esac
