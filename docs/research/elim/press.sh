#!/bin/bash
# press.sh [key ...]: each key pressed 1.5 s apart in the running test game, then the latest picture to cur.jpg
L=/e/xbrt_scr/elim/menu
for k in "$@"; do echo "$k 0.1" >> $L/input.txt; sleep 1.5; done
sleep 2
f=$(ls -t $L/present_*.ppm | head -1)
python -c "
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB'); im.thumbnail((960, 720)); im.save('E:/xbrt_scr/elim/cur.jpg', quality=85)" "$f"
