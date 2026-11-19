#!/bin/bash
# A muted Mayhem test race (7 Nov): an Arcade race on track $1 made Mayhem (XBRT_MAYHEM_TEST), 1 lap, the throttle held,
# the given runtime ($2, default forza-test.exe); its log and a shot every 2 s in E:/xbrt_scr/mrace/<track>.
# On a copy of the save disk; the user's never written.   bash mrace.sh <track> [exe] [seconds racing]
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; H=$S/hdd_mrace; R=$S/mrace
XBE="C:\\Users\\maste\\Downloads\\extract-xiso-win32-release\\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\\default.xbe"
if tasklist | grep -qi "forza"; then echo "forza is running: not started"; exit 1; fi
t=$1; EXE=${2:-forza-test.exe}; SECS=${3:-90}
rm -rf "$H" && cp -r "$G/run/hdd_test" "$H"
L="$R/$t"; rm -rf "$L"; mkdir -p "$L"; : > "$L/input.txt"
cp "$G/run/forza.ini" "$L/forza.ini" 2>/dev/null
p() { echo "$1 0.1" >> "$L/input.txt"; sleep "${2:-1.5}"; }
( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_track XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
    XBRT_NO_PROJ_SHADOWS=VancouverLoop,VancouverLoopReverse XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" \
    XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x720 \
    XBRT_PRESENT_SHOT="$L/s" XBRT_PRESENT_SHOT_MS=2000 $MRACE_ENV \
    XBRT_MAYHEM_TEST=1 XBRT_QR_TEST=3072/3073/3074/3179/3181/3182/3183/3184/3186/3187/3188/3189/3191/3192/3193/3195/3897/3898/3899/3900/3901/3902/3903/3904/3905/3906/3907/3908/3909/3910/3911,$t,1 \
    "$G/runtime/$EXE" "$XBE" > "$L/live.log" 2>&1 & )
sleep 55
p A 4; p A 5; p A 6; p A 6          # title, profile, Arcade Race, the event
p A 6; p A 8                        # the class, the car
p A 6; p A 6; p A 8                 # on to the grid's Start Race
echo "RT $SECS" >> "$L/input.txt"   # the throttle held
sleep $SECS
taskkill //F //IM "$EXE" > /dev/null 2>&1; sleep 3
grep -a "mayhem\|camera\|big field\|takedown\|moment\|not a number" "$L/live.log" | head -60
