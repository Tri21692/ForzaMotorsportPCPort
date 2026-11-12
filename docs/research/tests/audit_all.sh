#!/bin/bash
# audit_all.sh: the new mods folder (run/mods_next) checked working, on forza-test.exe, muted, on copies of the save disk
# (the user's, 11 Nov: "audit as many mods as you can ... make sure they're working and functional").
#  1. every track: an Arcade race, 1 lap on the autopilot (track_lap2.sh): the lap counted, no errors, the frame rate
#  2. the add-on cars: each 30 s in the dealer (store/storepass2.sh): its pictures
#  3. the career: each Race Type's first two series started from the menus: the race's event, a picture 20 s in
# Results: E:/xbrt_scr/audit_all/ (tracks.txt, career.txt, cars via store/cars). Stops if the user's game starts.
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr; O=$S/audit_all
XBE="C:\\Users\\maste\\Downloads\\extract-xiso-win32-release\\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso\\default.xbe"
mkdir -p $O
stop() { tasklist | grep -i "forza" | grep -vqi "forza-test" ; }

if [ -z "$SKIP_TRACKS" ]; then
: > $O/tracks.txt
for t in ${TRACKS:-84 82 83 1 2 3 5 6 8 9 10 16 17 18 19 20 21 25 26 27 81}; do
  if stop; then echo "the user's game is running: stopped before track $t" >> $O/tracks.txt; break; fi
  taskkill //F //IM forza-test.exe > /dev/null 2>&1
  R=$O/track_$t
  MODS=mods_next LOOKS=0 DRIVE_SECS=${SECS:-150} bash $S/track_lap2.sh $t $R 1 34 > /dev/null 2>&1
  laps=$(grep -a -c "quick race: lap 1 of 1" $R/live.log)
  name=$(grep -a -o "pit lane points for [A-Za-z0-9]*" $R/live.log | head -1 | sed 's/.*for //')
  err=$(grep -a -i "fatal\|not on the disc\|disc error\|exception\|crash" $R/live.log | grep -v -i "PinnedCubic\|TireSkids" | head -2 | cut -c1-120 | tr '\n' ' ')
  mem=$(grep -a -o "physical memory: [0-9]* MB" $R/live.log | sort -t: -k2 -n | tail -1)
  fps=$(cd $S && /c/Python313/python fps_log.py $R 2>/dev/null | tail -1 | cut -c1-40)
  n=$(ls $R/p_*.ppm 2>/dev/null | wc -l)
  echo "track $t ($name): lap done $laps, $n pictures, worst $fps, $mem; $err" >> $O/tracks.txt
  # keep a few pictures only
  /c/Python313/python - "$R" "$O/track_$t.jpg" <<'E'
import sys, glob, os
from PIL import Image
fs = sorted(glob.glob(sys.argv[1] + '/p_*.ppm'), key=lambda f: int(os.path.basename(f)[2:-4]))[50:]
if fs:
    pick = fs[::max(1, len(fs) // 8)][:8]
    s = Image.new('RGB', (2560, 960))
    for i, f in enumerate(pick): s.paste(Image.open(f).resize((640, 480)), (i % 4 * 640, i // 4 * 480))
    s.save(sys.argv[2], quality=80)
for f in glob.glob(sys.argv[1] + '/p_*.ppm'): os.remove(f)
E
done
fi

if [ -z "$SKIP_CARS" ] && ! stop; then
  taskkill //F //IM forza-test.exe > /dev/null 2>&1
  ( cd $S/store && bash storepass2.sh > $O/store.log 2>&1 )
  echo "cars: $(ls $S/store/cars 2>/dev/null | wc -l) add-ons shown in the dealer" > $O/cars.txt
fi

if [ -z "$SKIP_CAREER" ]; then
: > $O/career.txt
H=$S/hdd_m8
for ty in ${TYPES:-0 1 2 3 4 5 6 7 8 9}; do
 for k in ${SERIES:-0 1}; do
  if stop; then echo "the user's game is running: stopped" >> $O/career.txt; break 2; fi
  taskkill //F //IM forza-test.exe > /dev/null 2>&1; sleep 2
  rm -rf "$H" && cp -r "$G/run/hdd_test" "$H"
  L=$O/career_${ty}_$k; rm -rf $L; mkdir -p $L; : > $L/input.txt; cp "$G/run/forza.ini" $L/forza.ini
  ( cd "$G/run" && env XBRT_VOLUME=0 XBRT_GPU=gl XBRT_MODS=mods_next XBRT_HDD="$H" XBRT_ZONE_LEAD=1 XBRT_CAREER_TIMETRIAL=1 \
      XBRT_NO_PROJ_SHADOWS=VancouverLoop,VancouverLoopReverse XBRT_INPUT_LIVE="$L/input.txt" XBRT_SETTINGS="$L/forza.ini" \
      XBRT_ACHIEVEMENTS="$L/achievements.txt" XBRT_PRIZEMATCH="$L/prizematch.txt" XBRT_FULLSCREEN=0 XBRT_WINDOW_SIZE=1280x960 \
      XBRT_PRESENT_SHOT="$L/present" XBRT_PRESENT_SHOT_MS=2000 \
      "$G/runtime/forza-test.exe" "$XBE" > "$L/live.log" 2>&1 & )
  until [ -f $L/present_025.ppm ]; do sleep 2; done
  p() { echo "$1 0.1" >> $L/input.txt; sleep ${2:-2}; }
  p A 4; p A 4; p A 4; p DOWN 3; p A 4; p A 5                  # title, profile, Career, Go Race: the Race Type list
  for i in $(seq $ty); do p RIGHT 1.5; done
  p A 6                                                         # the type: its series
  for i in $(seq $k); do p RIGHT 1.5; done
  p A 5; p A 6; p A 8; p A 8; p A 8                             # the series, its race, the car, on to the start
  echo "RT 20" >> $L/input.txt
  sleep 24
  ev=$(grep -a -o "race.s event ordinal [0-9]*" $L/live.log | tail -1)
  mh=$(grep -a -c "mayhem: this race" $L/live.log)
  err=$(grep -a -i "fatal\|disc error\|exception" $L/live.log | grep -v -i "PinnedCubic" | head -1 | cut -c1-100)
  echo "type $ty series $k: ${ev:-no race started} (Mayhem $mh) $err" >> $O/career.txt
  taskkill //F //IM forza-test.exe > /dev/null 2>&1; sleep 3
  /c/Python313/python - "$L" "$O/career_${ty}_$k.jpg" <<'E'
import sys, glob, os
from PIL import Image
fs = sorted(glob.glob(sys.argv[1] + '/present_*.ppm'), key=lambda f: int(os.path.basename(f)[8:-4]))
if fs:
    pick = fs[-16::2][:8]
    s = Image.new('RGB', (2560, 960))
    for i, f in enumerate(pick): s.paste(Image.open(f).resize((640, 480)), (i % 4 * 640, i // 4 * 480))
    s.save(sys.argv[2], quality=80)
for f in fs: os.remove(f)
E
 done
done
fi
echo "AUDIT DONE" >> $O/tracks.txt
