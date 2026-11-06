#!/bin/bash
# Reconverts every add-on car (newcars.py convert), six at a time.
cd /e/xbrt_scr/newcars
keys=$(python -c "
import importlib.util,sys; sys.argv=['x']; s=importlib.util.spec_from_file_location('nc','newcars.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(' '.join(m.CARS))")
echo $keys | tr ' ' '\n' | xargs -P 6 -I{} sh -c 'python newcars.py convert {} > conv_{}.log 2>&1; tail -1 conv_{}.log'
