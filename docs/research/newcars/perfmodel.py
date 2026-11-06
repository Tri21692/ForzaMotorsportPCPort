"""The game's performance figure (gamecars.dat 120 on the disc, the listed class from it), as forza.exe's
f_0016CFF0 works it out:  round3( 0.25 (1 - (lbs - 1200) / 4100) + 0.025 (ft-lb - 90) / 910 + 0.125 (G - 0.15) / 0.29
+ 0.55 (hp - 100) / 1000 + 0.05 E^2 / 9 ) + model.dat's float at 100; the class from the table at 0x52ca00 (upper
bounds D4 .. S1)."""
import struct, sys, re, collections
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar
B = chr(92)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = r'E:\Forza Motorsport Remastered\run\mods_track'
BOUNDS = [0.239, 0.25, 0.261, 0.271, 0.274, 0.277, 0.281, 0.286, 0.293, 0.302, 0.315, 0.333, 0.348, 0.363, 0.391, 0.419, 0.475, 0.555, 0.645, float('inf')]
SUBS = ['D4', 'D3', 'D2', 'D1', 'C4', 'C3', 'C2', 'C1', 'B4', 'B3', 'B2', 'B1', 'A4', 'A3', 'A2', 'A1', 'S4', 'S3', 'S2', 'S1']
def subclass(p):
    return next(i + 1 for i, b in enumerate(BOUNDS) if p <= b)
def base(hp, ftlb, lbs):
    return 0.25 * (1 - (lbs - 1200) / 4100) + 0.025 * (ftlb - 90) / 910 + 0.55 * (hp - 100) / 1000
