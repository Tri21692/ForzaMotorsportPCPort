#!/bin/sh
# Samples the stacks of every thread in a running forza.exe with gdb.
#
#   tools/sample.sh <samples> <out.txt>
#
# Each sample attaches, prints "thread apply all bt 40" and detaches (about
# a second each); samples are separated by "=====" lines. Host frames
# named f_XXXXXXXX are guest functions. To see where the device thread
# spends its time, count the innermost runtime frame of the stacks that
# contain device_main (see docs/NIGHTLY.md).
export PATH="/c/Users/maste/Downloads/w64devkit/bin:$PATH"
pid=$(tasklist //FI "IMAGENAME eq forza.exe" //FO CSV //NH | head -1 | cut -d, -f2 | tr -d '"')
[ -n "$pid" ] || { echo "forza.exe is not running" >&2; exit 1; }
: > "$2"
i=0
while [ "$i" -lt "$1" ]; do
  gdb -q -batch -p "$pid" -ex "thread apply all bt 40" >> "$2" 2>/dev/null
  echo "=====" >> "$2"
  i=$((i + 1))
done
