#!/bin/bash
# pass_m.sh <mods folder name> [last]: the dealer's DLC Cars list walked on forza-test.exe with that mods folder
# (17 Nov, the wheel trials): start_big_m.sh, the menu path of the 16 Nov audit, then pass3n.sh; the earlier
# pictures kept as cars_prev. The game closed at the end.
cd /e/xbrt_scr/store
tasklist | grep -qi forza && { echo "forza is running: not started"; exit 1; }
rm -rf cars_prev; [ -d cars ] && mv cars cars_prev
MODS=$1 bash start_big_m.sh
p() { echo "$1 0.1" >> input.txt; sleep "${2:-1.5}"; }
sleep 60
p START 4; p A 5; p A 6
p DOWN 1.5; p A 7; p DOWN 1; p DOWN 1; p A 7; p LEFT 1.5; p A 7; p DOWN 1; p DOWN 1
for i in $(seq 12); do p RIGHT 1; done; p LEFT 1.5
p A 8
LAST=${2:-46} bash pass3n.sh
taskkill //F //IM forza-test.exe > /dev/null 2>&1
ls cars | wc -l
