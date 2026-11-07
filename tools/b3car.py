"""Read Burnout 3: Takedown (Xbox) vehicle models (.bgv, and traffic .btv) and export OBJ + PNG.

Usage:
  python tools/b3car.py <CarN.bgv> <out folder> [--lod N] [--parts] [--wheel 0|1|2]
      writes <name>.obj / .mtl, <name>.png (+ <name>_opaque.png), <name>_wheels.txt
      default: the intact body (one group per material) + 4 placed wheels;
      --parts: body and panels separately (panels unplaced, local frames), raw wheel
      meshes and the two extra meshes as well.
  .hwd / .lwd next to a .bgv are not graphics: RenderWare Audio wave dictionaries
  (u32 0x809, names "high"/"low") of engine/exhaust samples (eng_2873, ex_4395, turbine,
  dump ...): the high- and low-quality engine sound sets.
  python tools/b3car.py --info <CarN.bgv>      print the layout found

Format as found (Xbox build, file version 0x17; little-endian; no compression; all
"absolute" offsets are file offsets).  Partly from the community notes (AcuteSyntax's BGV
gist, Edness's fmt_Burnout3LRD.py Noesis plugin, which reads the texture only), the rest
reverse-engineered from the HSPC/Car21 data.

Header
  0x00 u32  version 0x17 (0x14 demo, 0x1D/0x1F Revenge, 0x25 Revenge X360 zlib)
  0x0C u8   body-part count (detachable panels; 6 max in 0x17)   0x0D u8 wheel count
  0x0E u16  min LOD   0x10 u16 max LOD (0, 3)
  0x4C..0x58 u32 x4   LOD blocks, lowest detail first (0x58 = highest); 0x5C unused
  0x60 u32  texture header (one texture per car)
  0x64, 0x68 u32      two extra one-strip meshes (header like a part, see below) that use
                      the highest LOD's vertex buffer: inner door-side panels on Car21
                      (probably shown when a door is torn off); may be 0
  0x70..0x570         20 4x4 float matrices (row-major, D3D row-vector convention,
                      translation in row 3): the damage-deformation "bones" (body frame,
                      bumper ends, door hinges, bonnet/boot hinges ...)
  0x570..0xA70        the 20 inverse matrices
  0xB80..0xC70        4 wheel matrices (Car21 order FR, FL, RR, RL): the 3x3 holds the
                      mirror (180 deg about y) for the left side and a width scale on x
                      (Car21: 0.84 front, 1.0 rear); row 3 = hub centre (y = 0 here).
                      The wheel mesh's hub face is on its -x side (outboard on the right).
                      6-wheel trucks (HEVY Car7/8/10) probably have more: not checked.
  0xD30..0xE80        point frames (exhaust / light / camera points?) - not decoded
  0xE70..             bounding boxes: model max xyz + min xyz + radius, then per part max/min
  0x1050..0x16F0      deformation/crash parameters, plane list, ... - not decoded

LOD block (LOD = offset of the block; every offset inside is relative to its own field's
owner as noted)
  +0x00 u32 x12  part offsets (relative to LOD): 0 = body, 1..6 = detachable panels
                 (Car21: 1/2 doors, 3/4 bumpers, 5 bonnet, 6 boot), then the wheel meshes
                 (Car21: 7 = modelled 5-spoke wheel, 8 = tyre with a flat spoke-picture
                 disc, 9 = tyre with a blurred disc: speed variants; --wheel 0/1/2).
                 Panels are in their own local frame (placed by the deformation bones,
                 not decoded); wheels are centred on the hub, axle along x.
  +0x48 u32 1, u32 vertex-buffer offset (relative to LOD), u32 0
  +0x54 u32 1, u32 blend-stream offset (relative to LOD), u32 0
  +0x60 u8 nstrips, u8 n, u16 0, u32 r: an "intact car" strip list (the body with all panels
        merged in model space) at LOD + r + 0x60; its extra vertices follow the parts' ones
        in the vertex buffer.  This is what the exporter uses for the body by default.
  vertex buffer: stride 0x18 = float3 position, u32 NORMPACKED3 normal (11:11:10 signed),
        float2 uv.  Vertex count = (blend offset - vb offset) / 0x18.
  blend stream: 8 bytes per vertex of the parts (not the intact-only extra vertices):
        u16 bone0, u16 bone1, u16 w0, u16 w1 (w0 + w1 = 255): bones = header matrices
Part (and the extra meshes)
  +0x00 u8 strip count, u8 (count of opaque strips or 0xFF), u16 0, u32 0x10, 8 bytes 0
  +0x10 strips, 0x1C bytes each:
        u32 0, f32 a, f32 b, u32 index offset (relative to the strip entry), u32 index
        count, u32 0, u32 flags.  Indices are u16 into the LOD's whole vertex buffer,
        a D3D triangle strip (degenerate triangles join pieces).
        a, b = 1.0, 0.0 for opaque strips and 0.216, 0.216 for glass.
        flags = the material slot (see MATERIALS); several strips per part.
Texture (Xbox, Edness's layout): +0x04 u32 bitmap offset (relative to the texture header),
  +0x14 u32 palette header offset (rel.), +0x34 u32 format (0x0B = P8, 0x0C DXT1,
  0x0E DXT3, 0x0F DXT5, 0x3A A8R8G8B8), +0x38 width, +0x3C height, +0x40 bits,
  +0x48 name, +0x69 u8 palette count.  P8 bitmaps are swizzled (Morton order); palette
  header "01 00 03 00" + u32 data offset (rel. to the texture header): 256 x BGRA.
  The palette alpha is not transparency on the body (it varies over paint): probably a
  reflection/specular mask.

Coordinates: metres, +y up, +z forward (headlights at +z, front axle z > 0), and the data
is right-handed as stored: +x = the car's LEFT (decal text reads correctly only without a
mirror; triangle strips are counter-clockwise facing the vertex normals, 100% consistent
on Car21 with the usual parity flip on odd triangles).  The OBJ keeps the coordinates
as they are (Blender: import with forward -Z, up Y; the car then faces -Y).
"""
import os, struct, sys, zlib
import numpy as np

MATERIALS = {
    0x1: 'paint', 0x2: 'trim', 0x10002: 'under', 0x4: 'headlight', 0x8: 'brakelight',
    0x10: 'taillight', 0x20: 'indicator_l', 0x40: 'indicator_r', 0x80: 'reverselight',
    0x20100: 'glass', 0x0: 'extra',
}
# names guessed from the geometry of Car21 (lights by position: 4 front, 8/0x10/0x80 rear;
# 0x20 mostly on +x = left, 0x40 on -x = right); 0x10002 is dark underside/grille/arches


def wheel_name(M):
    return ('F' if M[3, 2] > 0 else 'R') + ('L' if M[3, 0] > 0 else 'R')


def png(path, rgba):
    h, w, c = rgba.shape
    raw = b''.join(b'\0' + rgba[r].tobytes() for r in range(h))
    ch = lambda t, b: struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6 if c == 4 else 2, 0, 0, 0))
                           + ch(b'IDAT', zlib.compress(raw, 6)) + ch(b'IEND', b''))


def morton_index(w, h):
    """Linear offset of texel (y, x) in an Xbox swizzled (Morton, x bit first) 2D texture."""
    ys, xs = np.meshgrid(np.arange(h), np.arange(w), indexing='ij')
    idx = np.zeros((h, w), np.int64)
    bit, s = 0, 1
    while s < w or s < h:
        if s < w: idx |= ((xs & s) != 0).astype(np.int64) << bit; bit += 1
        if s < h: idx |= ((ys & s) != 0).astype(np.int64) << bit; bit += 1
        s <<= 1
    return idx


def unpack_normal(v):
    v = int(v); x = v & 0x7FF; y = (v >> 11) & 0x7FF; z = v >> 22
    x = x - 0x800 if x >= 0x400 else x
    y = y - 0x800 if y >= 0x400 else y
    z = z - 0x400 if z >= 0x200 else z
    n = np.array([x / 1023.0, y / 1023.0, z / 511.0])
    l = np.linalg.norm(n)
    return n / l if l > 1e-6 else np.array([0, 1.0, 0])


def rgb565(c):
    r = (c >> 11) & 31; g = (c >> 5) & 63; b = c & 31
    return np.stack([r * 255 // 31, g * 255 // 63, b * 255 // 31], -1)


def dxt(data, w, h, kind):
    out = np.zeros((h, w, 4), np.uint8)
    bs = 8 if kind == 1 else 16
    o = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            blk = data[o:o + bs]; o += bs
            cb = blk[bs - 8:]
            c0, c1, bits = struct.unpack('<HHI', cb)
            p0, p1 = rgb565(np.array(c0)), rgb565(np.array(c1))
            if kind == 1 and c0 <= c1:
                pal = [p0, p1, (p0 + p1) // 2, np.zeros(3, int)]
                al = [255, 255, 255, 0]
            else:
                pal = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3]
                al = [255] * 4
            for i in range(16):
                y, x = by + i // 4, bx + i % 4
                k = (bits >> (2 * i)) & 3
                out[y, x, :3] = pal[k]; out[y, x, 3] = al[k]
            if kind == 3:
                a = int.from_bytes(blk[:8], 'little')
                for i in range(16):
                    out[by + i // 4, bx + i % 4, 3] = ((a >> (4 * i)) & 15) * 17
            elif kind == 5:
                a0, a1 = blk[0], blk[1]; ab = int.from_bytes(blk[2:8], 'little')
                ap = [a0, a1] + ([((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)] if a0 > a1 else
                                 [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255])
                for i in range(16):
                    out[by + i // 4, bx + i % 4, 3] = ap[(ab >> (3 * i)) & 7]
    return out


class Bgv:
    def __init__(self, path):
        self.path = path
        self.d = d = open(path, 'rb').read()
        if d[:2] == b'\x78\xDA':
            raise ValueError('zlib-compressed (Revenge X360) file: not handled')
        self.version = self.u32(0)
        self.nparts, self.nwheels = d[0xC], d[0xD]
        self.lod_min, self.lod_max = struct.unpack_from('<HH', d, 0xE)
        self.lods = [self.u32(0x4C + 4 * i) for i in range(4)]
        self.tex_off = self.u32(0x60)
        self.extra_offs = [self.u32(0x64), self.u32(0x68)]

    def u32(self, o):
        return struct.unpack_from('<I', self.d, o)[0]

    # ---- geometry ----
    def lod_info(self, k):
        lo = self.lods[k]
        vb = lo + self.u32(lo + 0x4C)
        bl = lo + self.u32(lo + 0x58)
        nv = (bl - vb) // 0x18
        parts = [lo + p if p else 0 for p in (self.u32(lo + 4 * i) for i in range(12))]
        intact_n = self.d[lo + 0x60]
        intact = lo + self.u32(lo + 0x64) + 0x60 if self.u32(lo + 0x64) else 0
        return dict(lod=lo, vb=vb, blend=bl, nv=nv, parts=parts, intact=intact, intact_n=intact_n)

    def vertices(self, info):
        a = np.frombuffer(self.d, np.uint8, info['nv'] * 0x18, info['vb']).reshape(-1, 0x18)
        pos = a[:, 0:12].copy().view('<f4').reshape(-1, 3).astype(float)
        nrm = np.array([unpack_normal(v) for v in a[:, 12:16].copy().view('<u4').ravel()])
        uv = a[:, 16:24].copy().view('<f4').reshape(-1, 2).astype(float)
        return pos, nrm, uv

    def strips_at(self, e, n):
        out = []
        for k in range(n):
            a, b, rel, cnt, _, fl = struct.unpack_from('<ffIIII', self.d, e + 4)
            idx = struct.unpack_from('<%dH' % cnt, self.d, e + rel)
            out.append(dict(a=a, b=b, flags=fl, idx=idx))
            e += 0x1C
        return out

    def part_strips(self, po):
        return self.strips_at(po + 0x10, self.d[po])

    def matrix(self, o):
        return np.array(struct.unpack_from('<16f', self.d, o)).reshape(4, 4)

    def wheels(self):
        """[(name, 4x4 matrix)]: hub frames, D3D row-vector convention."""
        ms = [self.matrix(0xB80 + 0x40 * i) for i in range(min(self.nwheels, 4))]
        return [(wheel_name(M), M) for M in ms]

    # ---- texture ----
    def texture(self):
        t = self.tex_off
        if not t:
            return None, None
        bmp = t + self.u32(t + 4)
        fmt, w, h, bits = struct.unpack_from('<IIII', self.d, t + 0x34)
        name = self.d[t + 0x48:t + 0x68].split(b'\0')[0].decode('latin-1')
        if fmt == 0xB:
            pal_hdr = t + self.u32(t + 0x14)
            assert self.d[pal_hdr:pal_hdr + 4] in (b'\x01\x00\x03\x00', b'\x01\x00\x03\xC0')
            pal = np.frombuffer(self.d, np.uint8, 1024, t + self.u32(pal_hdr + 4)).reshape(256, 4)
            pal = pal[:, [2, 1, 0, 3]]
            lin = np.frombuffer(self.d, np.uint8, w * h, bmp)
            img = pal[lin[morton_index(w, h)]]
        elif fmt == 0x3A:
            lin = np.frombuffer(self.d, np.uint8, w * h * 4, bmp).reshape(-1, 4)
            img = lin[morton_index(w, h)][..., [2, 1, 0, 3]]
        elif fmt in (0xC, 0xE, 0xF):
            kind = {0xC: 1, 0xE: 3, 0xF: 5}[fmt]
            img = dxt(self.d[bmp:bmp + (w * h // 2 if kind == 1 else w * h)], w, h, kind)
        else:
            raise ValueError('texture format 0x%X' % fmt)
        return name, np.ascontiguousarray(img)


def strip_tris(idx):
    out = []
    for i in range(len(idx) - 2):
        a, b, c = idx[i], idx[i + 1], idx[i + 2]
        if a == b or b == c or a == c:
            continue
        out.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return out


def orient(tris, pos, nrm):
    """Wind each triangle counter-clockwise facing its vertex normals.
    Returns (tris, how consistent the plain strip parity is with the normals, 0.5..1;
    Car21: 1.0 - even triangles a,b,c are already counter-clockwise, so nothing flips)."""
    if not tris:
        return tris, 1.0
    t = np.array(tris)
    p = pos[t]
    fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    vn = nrm[t].sum(1)
    s = (fn * vn).sum(1)
    # in the source left-handed frame, front faces are clockwise: cross product points away
    good = s > 0
    t[~good] = t[~good][:, [1, 0, 2]]
    return [tuple(x) for x in t], float(max(good.mean(), 1 - good.mean()))


def export(path, outdir, lod=None, parts_mode=False, wheel=0, log=print):
    car = Bgv(path)
    base = os.path.splitext(os.path.basename(path))[0]
    sub = os.path.basename(os.path.dirname(os.path.abspath(path)))
    name = '%s_%s' % (sub, base)
    os.makedirs(outdir, exist_ok=True)
    k = 3 if lod is None else lod
    while k > 0 and not car.lods[k]:
        k -= 1
    info = car.lod_info(k)
    pos, nrm, uv = car.vertices(info)
    texname, img = car.texture()
    if img is not None:
        png(os.path.join(outdir, name + '.png'), img)
        png(os.path.join(outdir, name + '_opaque.png'), np.ascontiguousarray(img[..., :3]))

    groups = []   # (group name, material, tris, transform or None)
    nparts = sum(1 for p in info['parts'] if p)
    wheel_parts = [i for i, p in enumerate(info['parts']) if p][1 + car.nparts:]
    wheels = car.wheels()

    seen = set()

    def add_strips(gname, strips, M=None):
        for s in strips:
            mat = MATERIALS.get(s['flags'], 'mat_%x' % s['flags'])
            g = '%s_%s' % (gname, mat)
            n = 2
            while g in seen:
                g = '%s_%s%d' % (gname, mat, n); n += 1
            seen.add(g)
            groups.append((g, mat, strip_tris(s['idx']), M))

    if parts_mode or not info['intact']:
        for i, po in enumerate(info['parts']):
            if po and i not in wheel_parts:
                add_strips('part%d' % i, car.part_strips(po))
    else:
        add_strips('body', car.strips_at(info['intact'], info['intact_n']))
    # wheels: the same mesh on all four hubs; which of the wheel meshes is the -wheel option
    wm = [i for i in wheel_parts]
    if wm:
        use = wm[min(wheel, len(wm) - 1)]
        for wn, M in wheels:
            add_strips('wheel_' + wn, car.part_strips(info['parts'][use]), M)
    if parts_mode:
        for i in wm:
            add_strips('wheelmesh%d' % i, car.part_strips(info['parts'][i]))
        for j, eo in enumerate(car.extra_offs):
            if eo:
                add_strips('extra%d' % j, car.part_strips(eo))

    # write OBJ (x negated -> right-handed)
    mats = sorted(set(g[1] for g in groups))
    with open(os.path.join(outdir, name + '.mtl'), 'w') as f:
        for m in mats:
            f.write('newmtl %s\nKd 1 1 1\n' % m)
            if m == 'glass':
                f.write('d 0.35\n')
            if img is not None:
                # the RGBA png's alpha is a mask (reflection?), not transparency
                f.write('map_Kd %s_opaque.png\n' % name)
            f.write('\n')
    lines = ['# %s  (Burnout 3 Takedown Xbox, LOD %d, texture %s)' % (path, k, texname),
             '# metres, +y up, +z forward, +x = car left (right-handed, as stored)', 'mtllib %s.mtl' % name]
    vbase = 1
    stats = []
    allp = []
    for gname, mat, tris, M in groups:
        tris, ok = orient(tris, pos, nrm)
        stats.append((gname, len(tris), ok))
        used = sorted(set(i for t in tris for i in t))
        remap = {v: j for j, v in enumerate(used)}
        P = pos[used]; N = nrm[used]
        if M is not None:
            P = P @ M[:3, :3] + M[3, :3]
            N = N @ M[:3, :3]
            N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
            if np.linalg.det(M[:3, :3]) < 0:
                tris = [(a, c, b) for a, b, c in tris]
        allp.append(P)
        lines.append('g %s\nusemtl %s' % (gname, mat))
        lines += ['v %.5f %.5f %.5f' % tuple(p) for p in P]
        lines += ['vt %.5f %.5f' % (t[0], 1 - t[1]) for t in uv[used]]
        lines += ['vn %.4f %.4f %.4f' % tuple(n) for n in N]
        for a, b, c in tris:
            a, b, c = (remap[x] + vbase for x in (a, b, c))
            lines.append('f %d/%d/%d %d/%d/%d %d/%d/%d' % (a, a, a, b, b, b, c, c, c))
        vbase += len(used)
    open(os.path.join(outdir, name + '.obj'), 'w').write('\n'.join(lines) + '\n')
    allp = np.concatenate(allp)
    lo, hi = allp.min(0), allp.max(0)
    with open(os.path.join(outdir, name + '_wheels.txt'), 'w') as f:
        f.write('# wheel hub centres, model/OBJ frame (+x = car left, y up, z forward), metres\n')
        for wn, M in wheels:
            f.write('%s  centre %.4f %.4f %.4f  width scale %.3f\n' % ((wn,) + tuple(M[3, :3]) + (abs(M[0, 0]),)))
        f.write('# bbox min %.3f %.3f %.3f  max %.3f %.3f %.3f  size %.3f x %.3f x %.3f (w h l)\n'
                % (tuple(lo) + tuple(hi) + tuple(hi - lo)))
    log('%s: LOD %d (%d verts), texture %s %s, %d groups, bbox %s .. %s' % (
        name, k, info['nv'], texname, None if img is None else img.shape[:2], len(groups), lo.round(3), hi.round(3)))
    for g, n, ok in stats:
        if ok < 0.9:
            log('  %s: %d tris, strip parity matched normals %.0f%%' % (g, n, ok * 100))
    return name


def info_dump(path):
    car = Bgv(path)
    print('version 0x%X parts %d wheels %d LOD %d..%d' % (car.version, car.nparts, car.nwheels, car.lod_min, car.lod_max))
    for k, lo in enumerate(car.lods):
        if not lo:
            continue
        inf = car.lod_info(k)
        print('LOD %d @%X: vb %X (%d verts) blend %X intact %X (%d strips)' % (k, lo, inf['vb'], inf['nv'], inf['blend'], inf['intact'], inf['intact_n']))
        for i, po in enumerate(inf['parts']):
            if po:
                st = car.part_strips(po)
                print('  part %d @%X: ' % (i, po) + ', '.join('%s %d' % (MATERIALS.get(s['flags'], hex(s['flags'])), len(s['idx'])) for s in st))
    for wn, M in car.wheels():
        print('wheel', wn, M[3, :3].round(4), 'scale', M[0, 0].round(3))
    print('texture', car.texture()[0])


if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--info':
        info_dump(a[1])
    else:
        lod = int(a[a.index('--lod') + 1]) if '--lod' in a else None
        wheel = int(a[a.index('--wheel') + 1]) if '--wheel' in a else 0
        export(a[0], a[1], lod, '--parts' in a, wheel)
