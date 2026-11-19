"""Forza's MLP data files (media\\AI\\DrivatarV2\\*.bin): a text header, then the fields' data
packed one after another in the header's order.

  MLPDataStart:
  <name>:<type>:<count>:<columns>:<offset, right-aligned in 9>
  ...
  MLPDataEnd:

types: float, int32, uint32, int8, char (count 1, columns the length). The data starts right after
the header, nothing aligned.

  python tools/mlp.py <file.bin>       prints the header and the first values of each field
"""
import sys

import numpy as np

TYPES = {'float': '<f4', 'int32': '<i4', 'uint32': '<u4', 'int8': '<i1'}


def read(d):
    """{name: array (or bytes for char)} and [(name, type, count, columns)] in the file's order."""
    end = d.index(b'MLPDataEnd:')
    fields, out = [], {}
    for line in d[:end].decode('latin-1').splitlines()[1:]:
        name, typ, n, cols, off = line.split(':')
        n, cols, off = int(n), int(cols), int(off)
        fields.append((name, typ, n, cols))
        if typ == 'char': out[name] = d[off:off + n * cols]
        else:
            a = np.frombuffer(d, TYPES[typ], count=n * cols, offset=off)
            out[name] = a.reshape(n, cols) if cols > 1 else a
    return out, fields


def write(fields):
    """fields: [(name, type, value)] (value an array, or bytes for char): the file's bytes."""
    datas, specs = [], []
    for name, typ, v in fields:
        if typ == 'char':
            b = bytes(v); n, cols = 1, len(b)
        else:
            a = np.asarray(v, TYPES[typ])
            n, cols = (a.shape[0], a.shape[1]) if a.ndim == 2 else (a.size, 1)
            b = a.tobytes()
        specs.append((name, typ, n, cols)); datas.append(b)
    # the header's length depends on itself only through the offsets' fixed width
    head = lambda offs: ('MLPDataStart:\n' + ''.join('%s:%s:%d:%d:%9d\n' % (s + (o,)) for s, o in zip(specs, offs)) + 'MLPDataEnd:\n').encode('latin-1')
    base = len(head([0] * len(specs)))
    offs, o = [], base
    for b in datas: offs.append(o); o += len(b)
    return head(offs) + b''.join(datas)


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    vals, fields = read(d)
    for name, typ, n, cols in fields:
        v = vals[name]
        print('%-24s %-6s %5d x %-3d %s' % (name, typ, n, cols, v[:40] if typ == 'char' else np.asarray(v).ravel()[:6]))
