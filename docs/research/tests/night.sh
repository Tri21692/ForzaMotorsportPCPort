#!/bin/bash
# night.sh <track> <out> <pilot seconds> [env for the tool...]: the night tracks' data re-installed (tools/fujiminight.py,
# the scenery only with SCENERY=1), then a muted Arcade race there on the pad pilot against one rival, stopped after
# that many seconds of driving; three pictures side by side as vid/night.jpg.
T=$1; O=$2; N=$3; shift 3
G="/e/Forza Motorsport Remastered"; S=/e/xbrt_scr/vid
DISC="C:/Users/maste/Downloads/extract-xiso-win32-release/Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso"
tasklist | grep -qi forza && { echo "forza is running"; exit 1; }
( cd "$G" && env NIGHT_SCENERY=${SCENERY:-0} "$@" python tools/fujiminight.py "$DISC" run/mods_next tracks 2>&1 | grep -v "SyntaxWarning\|^  " | tail -2 )
SHOT_MS=1000 EXTRA="XBRT_PILOT=${SPEED:-28} XBRT_QR_FIELD=1 $RUN_ENV" bash $S/run.sh $T $O 1 0 ${CLASS:-0} ${CAR:-3} > /dev/null 2>&1
for i in $(seq 100); do
  [ "$(grep -a -c 'pilot:' $O/live.log)" -ge $N ] && break
  tasklist | grep -qi forza-test || break
  grep -a -q "fatal error" $O/live.log && { echo FATAL; break; }
  sleep 3
done
[ -n "$KEEP" ] || taskkill //F //IM forza-test.exe > /dev/null 2>&1
grep -a -i "fatal\|catch-up:" $O/live.log | cut -c1-160 | head -5
python - "$O" <<'EOF'
import sys, glob, os
from PIL import Image
fs = sorted(glob.glob(sys.argv[1] + '/p_*.ppm'), key=os.path.getmtime)
pick = [fs[-1], fs[-4], fs[-8]] if len(fs) > 8 else fs[-1:]
ims = [Image.open(f).convert('RGB') for f in pick]
w, h = ims[0].size
o = Image.new('RGB', (w * len(ims) // 2, h // 2))
for i, im in enumerate(ims): o.paste(im.resize((w // 2, h // 2)), (i * w // 2, 0))
o.save('E:/xbrt_scr/vid/night.jpg', quality=88)
ims[0].save('E:/xbrt_scr/vid/cur.jpg', quality=88)
print(pick[0])
EOF
