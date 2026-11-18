#!/bin/bash
# ovaudit.sh <out folder name>: every overlay of the port's captured from muted test windows (the audit of 18 Nov):
# F1's tabs (t0..t7, selections and the achievements scrolled), the Quick Race menu, Prize Match, the race HUD's pieces
# by XBRT_HUD_DEMO=9. Pictures in E:/xbrt_scr/vid/<name>/, sheets sheetA..E.jpg.
V=/e/xbrt_scr/vid; O=$V/$1; R=$V/rvc.sh; C=$V/rvc_cur.jpg
mkdir -p $O
RVC_ENV="XBRT_OVERLAY=1 XBRT_INPUT_ONLY=1" bash $R start
cp "/e/Forza Motorsport Remastered/run/achievements.txt" $V/rvc/achievements.txt
cp $C $O/t0.jpg
bash $R press RT:1 DOWN:0.5 DOWN:0.5 DOWN:0.5 > /dev/null; cp $C $O/t1.jpg
for i in 2 3 4 5; do bash $R press RT:1 > /dev/null; cp $C $O/t$i.jpg; done
bash $R press RT:1 > /dev/null; cp $C $O/t6.jpg
bash $R press DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 > /dev/null; cp $C $O/t6b.jpg
bash $R press DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 DOWN:0.4 > /dev/null; cp $C $O/t6c.jpg
bash $R press RT:1 > /dev/null; cp $C $O/t7.jpg
bash $R stop; sleep 3
RVC_ENV="XBRT_INPUT_ONLY=1" bash $R start
bash $R press A:4 A:5 A:6 A:6 X:2 DOWN:0.5 DOWN:0.5 > /dev/null; cp $C $O/qr.jpg
bash $R stop; sleep 3
RVC_ENV="XBRT_INPUT_ONLY=1" bash $R start
bash $R press START:4 A:5 A:6 DOWN:1.5 A:7 > /dev/null; cp $C $O/menu.jpg
bash $R press A:8 > /dev/null; cp $C $O/menu2.jpg
bash $R press WHITE:2 A:1 > /dev/null; cp $C $O/pm.jpg
bash $R stop; sleep 3
SHOT_MS=1000 EXTRA="XBRT_INPUT_ONLY=1 XBRT_RIVAL=0 XBRT_HUD_DEMO=9" bash $V/run.sh 26 $V/hud_t 2 22 0 0 > $V/hudtest.out 2>&1
sleep 40; taskkill //F //IM forza-test.exe > /dev/null 2>&1
python "E:/xbrt_scr/vid/ovsheets.py" "E:/xbrt_scr/vid/$1"
echo ovaudit done
