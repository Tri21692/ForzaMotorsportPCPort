#!/bin/bash
# (7 Nov) The whole store pass in one: start.sh's muted game on a copy of the test disk, pressed to Buy Cars >
# Advanced Search > Class: DLC Cars, then pass3.sh (each add-on 30 s, its shots in cars/<n>/), then the game closed.
cd /e/xbrt_scr/store
rm -rf cars; mkdir -p cars
bash start.sh || exit 1
sleep 60
p() { echo "$1 0.1" >> input.txt; sleep "${2:-1.5}"; }
p START 4; p A 5; p A 6                 # title, profile
p DOWN 1.5; p A 7                       # Career Mode
p DOWN 1.5; p DOWN 1.5; p A 8           # Buy Cars
p LEFT 1.5; p A 4                       # Advanced Search
for k in 1 2 3 4 5 6 7 8 9; do p RIGHT 1; done
p A 8                                   # Class: DLC Cars (nine on since Class F)
bash pass3.sh
taskkill //F //IM forza.exe > /dev/null 2>&1
echo "store pass done: $(ls cars | wc -l) cars"
