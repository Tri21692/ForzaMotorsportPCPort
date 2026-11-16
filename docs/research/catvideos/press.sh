#!/bin/bash
# press.sh <out> [key ...]: each key pressed 1.5 s apart in the running test game, then the latest picture to vid/cur.jpg
L=$1; shift
for k in "$@"; do echo "$k 0.1" >> $L/input.txt; sleep 1.5; done
sleep 2
f=$(ls -t $L/p_*.ppm | head -1)
python -c "
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB'); im.thumbnail((800, 600)); im.save('E:/xbrt_scr/vid/cur.jpg', quality=85)" "$f"
echo $f
