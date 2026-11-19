import sys
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import nfsu2forza
nfsu2forza.SMOOTH = True
nfsu2forza.main(['x'] + sys.argv[1:])
