#!/bin/bash
# vid/run.sh <track> <out> [laps] [speed m/s] [class rights] [car rights]: track_lap2.sh's Arcade race on the autopilot,
# left running (no kill): vid/press.sh <out> <keys...> presses on and shows the latest picture as vid/cur.jpg.
# SHOT_MS (1000), WIN (800x600), EXTRA, MODS (mods_next), VIEW, LINE_OFF/LINE_KEY as track_lap2.sh's.
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; T=$1; O=$2; LAPS=${3:-1}; SPD=${4:-28}; H=$S/hdd_vid
XBE="C:\\Users\\maste\\Downloads\\extract-xiso-win32-release\\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\\default.xbe"
if tasklist | grep -qi forza; then echo "game running"; exit 1; fi
rm -rf "$O" "$H" && mkdir -p "$O" && cp -r "$G/run/hdd_test" "$H" && : > "$O/input.txt" && cp "$G/run/forza.ini" "$O/forza.ini" && sed -i "s/^show_fps = .*/show_fps = 0/" "$O/forza.ini"
( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=${MODS:-mods_next} XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_NO_PROJ_SHADOWS=VancouverLoop,VancouverLoopReverse XBRT_INPUT_LIVE="$O/input.txt" XBRT_SETTINGS="$O/forza.ini" \
    XBRT_ACHIEVEMENTS="$O/ach.txt" XBRT_PRIZEMATCH="$O/pm.txt" XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=${WIN:-800x600} XBRT_KAIZO=0 \
    XBRT_PRESENT_SHOT="$O/p" XBRT_PRESENT_SHOT_MS=${SHOT_MS:-1000} XBRT_POS_TRACE="$O/pos.trace" \
    $EXTRA XBRT_QR_ALWAYS=1 XBRT_AUTODRIVE=$SPD \
    XBRT_QR_TEST=3072/3073/3074/3179/3181/3182/3183/3184/3186/3187/3188/3189/3191/3192/3193/3195/3897/3898/3899/3900/3901/3902/3903/3904/3905/3906/3907/3908/3909/3910/3911,$T,$LAPS \
    "$G/runtime/${EXE:-forza-test.exe}" "$XBE" > "$O/live.log" 2>&1 & ) > /dev/null 2>&1
p() { echo "$1 0.1" >> "$O/input.txt"; sleep "${2:-1.5}"; }
until [ -f "$O/p_$(( 25000 / ${SHOT_MS:-1000} )).ppm" ] || [ -f "$O/p_0$(( 25000 / ${SHOT_MS:-1000} )).ppm" ]; do sleep 2; done
p A 4; p A 5; p A 6; p A 6
for k in $(seq ${5:-0}); do p ${CLASS_KEY:-RIGHT} 1.2; done; p A 6
for k in $(seq ${6:-0}); do p RIGHT 1.2; done; p A 8
for k in $ASSIST_KEYS; do p $k 1.0; done   # (the assists menu: e.g. "RIGHT DOWN RIGHT DOWN RIGHT" = the line, STM and TCS switched)
p A 6
for k in $(seq ${LINE_OFF:-0}); do p ${LINE_KEY:-LEFT} 1.2; done
p A 6; p A 8
for k in $(seq ${VIEW:-0}); do p BLACK 0.6; done
sleep ${START_WAIT:-8}; echo "RT 3" >> "$O/input.txt"
echo started
