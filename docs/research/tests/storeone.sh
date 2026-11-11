#!/bin/bash
# storeone.sh <n>: as storepass2.sh, but only the n-th DLC car (0-based), 32 s of shots into one/<n>/
cd /e/xbrt_scr/store
N=$1; rm -rf one/$N; mkdir -p one/$N
bash start2.sh || exit 1
sleep 60
p() { echo "$1 0.1" >> input.txt; sleep "${2:-1.5}"; }
p START 4; p A 5; p A 6
p DOWN 1.5; p A 7
p DOWN 1.5; p DOWN 1.5; p A 8
sleep 3; p LEFT 2; p A 4
p DOWN 1.2; p DOWN 1.2
for k in 1 2 3 4 5 6 7 8; do p RIGHT 1; done
p A 8
p RIGHT 1.5; p LEFT 1
for k in $(seq 1 $N); do p RIGHT 1; done
rm -f shots/*; sleep 32; mv shots/* one/$N/
taskkill //F //IM forza-test.exe > /dev/null 2>&1
echo "done: $(ls one/$N | wc -l) shots"
