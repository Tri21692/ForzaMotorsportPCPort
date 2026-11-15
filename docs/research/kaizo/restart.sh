#!/bin/bash
# track_lap.sh <track ordinal> <out folder> [laps] [speed m/s] [class rights] [car rights]
# An Arcade race on that track (XBRT_QR_TEST sets every arcade event's track), the player's car on the runtime's
# autopilot along the AI line (XBRT_AUTODRIVE), the AI field racing; a picture each second (present, after the
# post effects), the player's position (pos.trace), the frame trace; muted, windowed; a copy of the save disk.
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; T=$1; O=$2; LAPS=${3:-1}; SPD=${4:-28}; H=$S/hdd_lap
XBE="C:\\Users\\maste\\Downloads\\extract-xiso-win32-release\\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\\default.xbe"
if tasklist | grep -qi forza; then echo "game running"; exit 1; fi
rm -rf "$O" "$H" && mkdir -p "$O" && cp -r "$G/run/hdd_test" "$H" && : > "$O/input.txt" && cp "$G/run/forza.ini" "$O/forza.ini"
( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=${MODS:-mods_track} XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_NO_PROJ_SHADOWS=${NOPROJ:-VancouverLoop,VancouverLoopReverse} XBRT_INPUT_LIVE="$O/input.txt" XBRT_SETTINGS="$O/forza.ini" \
    XBRT_ACHIEVEMENTS="$O/ach.txt" XBRT_PRIZEMATCH="$O/pm.txt" XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x960 \
    XBRT_PRESENT_SHOT="$O/p" XBRT_PRESENT_SHOT_MS=1000 XBRT_POS_TRACE="$O/pos.trace" XBRT_STATS=1 XBRT_FRAME_TRACE="$O/frames.trace" \
    $EXTRA XBRT_QR_ALWAYS=1 \
    XBRT_QR_TEST=3072/3073/3074/3179/3181/3182/3183/3184/3186/3187/3188/3189/3191/3192/3193/3195/3897/3898/3899/3900/3901/3902/3903/3904/3905/3906/3907/3908/3909/3910/3911,$T,$LAPS \
    "$G/runtime/${EXE:-forza-test.exe}" "$XBE" > "$O/live.log" 2>&1 & )
p() { echo "$1 0.1" >> "$O/input.txt"; sleep "${2:-1.5}"; }
until [ -f "$O/p_025.ppm" ]; do sleep 2; done
p A 4; p A 5; p A 6; p A 6                        # title, profile, Arcade Race, the event
for k in $(seq ${5:-0}); do p RIGHT 1.2; done; p A 6
for k in $(seq ${6:-0}); do p RIGHT 1.2; done; p A 8
p A 6
for k in $(seq ${LINE_OFF:-0}); do p ${LINE_KEY:-LEFT} 1.2; done     # (the Assists box, on Suggested Line: LEFT turns it off)
p A 6; p A 8                               # on to the grid's Start Race
for k in $(seq ${VIEW:-0}); do p BLACK 0.6; done        # the camera view (BLACK: far chase, bumper, hood)
sleep ${START_WAIT:-8}; echo "RT ${HOLD:-25}" >> "$O/input.txt"               # (the race clock starts once the car moves: then the autopilot takes it)
sleep 25; p UP 1.5; p A 3; p A 16; echo "RT 4" >> "$O/input.txt"; sleep 12
taskkill //F //IM ${EXE:-forza-test.exe} > /dev/null 2>&1; sleep 3
echo "done: $(ls $O/p_*.ppm | wc -l) pictures"
