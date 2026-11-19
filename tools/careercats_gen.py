"""python tools/careercats_gen.py: copy f_00184F30 and f_001856B0 from out/code_0023.c with the category table's address made a
variable, into runtime/hle_career_cats_gen.inc (included by hle_career_cats.c)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

src = open(os.path.join(ROOT, 'out', 'code_0023.c'), encoding='latin-1').read()


def func(name):
    i = src.index('XB_WEAK void %s(XbCtx *c) {' % name)
    j = src.index('\n}\n', i) + 3
    return src[i:j]


out = []
for name in ('f_00184F30', 'f_001856B0'):
    f = func(name).replace('XB_WEAK void %s' % name, 'void %s' % name)
    n0 = f.count('0x52E850u') + f.count('0x0052E850u') + f.count('0x52E988u')
    f = f.replace('0x0052E850u', 'cat_base()').replace('0x52E850u', 'cat_base()').replace('0x52E988u', 'cat_end()')
    # the list item's kind (+0x28): its icon's frame (cat_frame), the table keeps the kind
    k = f.count('/* 00185156  mov dword ptr [esi+0x28], edx */')
    if name == 'f_00184F30':
        a = f.index('/* 00185156  mov dword ptr [esi+0x28], edx */')
        b = f.index('\n', f.index('\n', a) + 1)
        line = f[f.index('\n', a) + 1:b]
        assert 'xb_wr32' in line and 'c->edx' in line, line
        f = f[:b] + '\n    xb_wr32((uint32_t)(c->esi + 0x28u), cat_frame(c->ebp, c->edx)); /* changed: the icon */' + f[b:]
        # the list on to Amateur once built: it opens on item 2 (the disc's Amateur), and the carousel keeps its own
        # place (the list told 4 still showed 2), so the D-pad is pressed on as far as the added categories moved it
        old = 'xb_call_indirect(c, t); }\n    /* 001851CB  pop edi */'
        assert f.count(old) == 1
        f = f.replace(old, 'xb_call_indirect(c, t); }\n    cat_opened(); /* changed: the list on to Amateur (the D-pad pressed, hle_input.c) */\n    /* 001851CB  pop edi */')
    out.append('/* %s: %d table addresses made cat_base()/cat_end()%s */\n' % (name, n0, ', the item kind its icon' if k else '') + f)
open(os.path.join(ROOT, 'runtime', 'hle_career_cats_gen.inc'), 'w', encoding='latin-1', newline='\n').write('\n'.join(out))
print([len(o) for o in out])
