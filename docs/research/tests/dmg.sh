#!/bin/bash
# dmg.sh <out> <class presses> <car rights> [env...]: a muted Arcade race at Tsukuba on a wild pad pilot (it hits the
# walls), the player's car wrecked 20 s in (XBRT_DMGMAX), stopped after 45 s of driving; the last picture as <out>.jpg.
O=/e/xbrt_scr/vid/$1; C=$2; K=$3; shift 3
tasklist | grep -qi forza && { echo "forza is running"; exit 1; }
SHOT_MS=1000 WIN=1280x960 EXTRA="XBRT_PILOT=55 XBRT_PILOT_GRIP=30 XBRT_PILOT_BRAKE=3 XBRT_QR_FIELD=0 XBRT_DMGMAX=20 $*" bash /e/xbrt_scr/vid/run.sh 26 $O 3 0 $C $K > /dev/null 2>&1
for i in $(seq 80); do
  [ "$(grep -a -c 'pilot:' $O/live.log)" -ge 45 ] && break
  tasklist | grep -qi forza-test || break
  sleep 3
done
taskkill //F //IM forza-test.exe > /dev/null 2>&1
grep -a "dmg test\|fatal" $O/live.log | head -3
python - "$O" <<'EOF'
import sys, glob, os
from PIL import Image
fs = sorted(glob.glob(sys.argv[1] + '/p_*.ppm'), key=os.path.getmtime)
ims = [Image.open(f).convert('RGB') for f in (fs[-1], fs[-6], fs[-12])]
w, h = ims[0].size
o = Image.new('RGB', (w * 3 // 2, h // 2))
for i, im in enumerate(ims): o.paste(im.resize((w // 2, h // 2)), (i * w // 2, 0))
o.save(sys.argv[1] + '.jpg', quality=90)
EOF
