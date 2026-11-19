#!/bin/bash
# record.sh <track> <out> <laps> <speed> <class presses> <car rights> [replay seconds]: run.sh's race on the autopilot,
# pictures 66 ms apart; when the race is done, View Replay, recorded for the seconds given; then the game closed.
# The replay's first picture is noted in <out>/replay_from.txt.
S=/e/xbrt_scr/vid; O=$2; RS=${7:-120}
SHOT_MS=66 bash $S/run.sh "$1" "$O" "$3" "$4" "$5" "$6" || exit 1
for i in $(seq 200); do sleep 3; grep -a -q "quick race: lap $3 of $3" "$O/live.log" && break; done
sleep 14
p() { echo "$1 0.1" >> "$O/input.txt"; sleep "${2:-1.5}"; }
p UP; p UP; p UP
ls "$O" | grep -c "^p_" > "$O/replay_from.txt"
p A
sleep $RS
taskkill //F //IM forza-test.exe > /dev/null 2>&1; sleep 3
echo "$O: $(ls $O | grep -c '^p_') pictures, the replay from $(cat $O/replay_from.txt)"
