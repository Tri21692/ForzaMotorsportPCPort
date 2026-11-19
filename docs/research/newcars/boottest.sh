#!/bin/bash
# A muted, windowed boot on a copy of the save disk: title, profile, Arcade Race, an event, the class and car screens
# (screenshots every 2 s), to see the game take the new cars' list.
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr/newcars; H=$S/hdd_boot; L=$S/boot_run
XBE="C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\default.xbe"
if tasklist | grep -qi "forza"; then echo "game running"; exit 1; fi
rm -rf "$H" "$L" && cp -r "$G/run/hdd_test" "$H" && mkdir -p "$L/present"
: > "$L/input.txt"; cp "$G/run/forza.ini" "$L/forza.ini"
p() { echo "$1 0.1" >> "$L/input.txt"; sleep "${2:-1.5}"; }
( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_track XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" \
    XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x960 XBRT_PRESENT_SHOT="$L/present/s" XBRT_PRESENT_SHOT_MS=2000 \
    "$G/runtime/forza.exe" "$XBE" > "$L/live.log" 2>&1 & )
sleep 55
p A 4; p A 5; p A 6; p A 6
p A 6; for k in 1 2 3 4; do p RIGHT 2; done; p A 8
for k in $(seq 30); do p RIGHT 2.5; done
sleep 3; taskkill //F //IM forza.exe > /dev/null 2>&1; sleep 3
echo "shots: $(ls $L/present | wc -l)"; grep -i -E "error|assert|crash|exception|fatal" "$L/live.log" | head
