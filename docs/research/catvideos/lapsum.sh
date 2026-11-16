#!/bin/bash
# lapsum.sh <out> [laps]: waits for the run's last lap (or the game's end), then the pilot's log in short:
# point, speed/allowed, slip, steer, throttle, brake; the worst slides; the lap clock.
O=$1; L=${2:-1}
until grep -a -q "lap $L of $L" "$O/live.log" || ! tasklist | grep -qi forza-test; do sleep 3; done
grep -a "pilot:" "$O/live.log" | tr -d ',()' | awk '{printf "%4s %2s/%-2s sl%-4s st%-5s t%-4s b%-4s| ", $4, $5, $8, $10, $15, $17, $19; if (NR%4==0) print ""}'
echo
echo "slides over 15 deg: $(grep -a 'pilot:' "$O/live.log" | tr -d ',()' | awk '{s=$10; if (s<0) s=-s; if (s>15) n++} END {print n+0}') of $(grep -a -c 'pilot:' "$O/live.log") seconds; stopped: $(grep -a 'pilot:' "$O/live.log" | awk '$5==0' | wc -l)"
grep -a "quick race: lap" "$O/live.log" | tail -2
