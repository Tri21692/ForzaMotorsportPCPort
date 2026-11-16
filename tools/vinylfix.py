"""The vinyl editor's layout put right on the converted cars already installed (the vinyl audit, 16 Nov).

A vinyl is a flat picture drawn into a view's rectangle of the car's 1024 livery atlas (<car>.liveries.bin: left,
right, top, front, back, each a place and a mask), and the body shows it right only where a painted triangle's
texture coordinates are that view's flat projection of it. The converter (nfsu2forza.py) copied the template's
triangle maps onto another shape instead and kept the template's masks: every converted car's vinyls came out
stretched or on the wrong panel, and the 25 built on a template without a wing view had the paint shop's
`detail` written 140 bytes late. Here each such car is repaired as it stands, with no conversion run again:

  car.carbin        the painted triangles (Body material, on the template's old layout) given the projection of
                    the view they face (nfsu2forza.project_layout: the template's own scale and offset a view,
                    made to hold the whole body; a triangle that does not fit its view, or would land on
                    another part's texture, goes to its next view, and failing all to one clear paint texel)
  livery0*.xpr      the texels the body now takes made plain paint in the three atlases (livery0hi; livery0nc
                    and livery0's clean slice; their damaged slices only where the clean one held other art).
                    Only the blocks touched are encoded again: the lamps', badges' and cabin's texels (every
                    triangle not moved, eight texels round) stay as they are, where they are
  <car>.liveries.bin  each view's mask drawn again as the body's own outline in it, and `detail` made again
                    from the new atlas at the right place (nfsu2forza.paint_shop)

  python tools/vinylfix.py <disc folder> <mods folder> <out folder> [car ...]     (no cars: every car_*.cab)

Reads the mods folder, writes only under the out folder, laid out as the mods folder (media\\cabs\\car_<car>.cab,
media\\cars\\<car>.liveries.bin; copy them over the mods folder's to install) with vinylfix.json (what was done to
each car, the projections used) beside them. Left alone, and said so: a car with no liveries.bin (a race
template: no views), a disc car's own body (the D-Spec copies), a car not on its template's layout (a Most
Wanted vinyl canvas: the M3 GTR), and one whose paint mostly finds no room (--max-clear, over 25% of its area).
Liveries already painted on a repaired car keep their vinyls' texels, which now lie elsewhere on the body.
"""
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import carbin
import forzacab
import forzaxpr as fx
import nfsu2forza as n2

B = '\\'
ATLASES = ('livery0nc.xpr', 'livery0.xpr', 'livery0hi.xpr')
EDGE, FLAT_EDGE = 8, 3   # texels round another part's texture, and round a single texel one, that stay as they are
WHITE = np.array([255, 255, 255, 0], np.uint8)


def unpack_bin(path):
    return bytearray(zlib.decompress(open(path, 'rb').read()))


def views_key(d):
    """What tells one car's views from another's: their places and the side and top masks."""
    h = hashlib.md5()
    for name, (x, y, w, h_, pitch, at) in sorted(n2.shop_views(d).items()):
        h.update(('%s %d %d %d %d' % (name, x, y, w, h_)).encode())
        if name in ('left', 'right', 'top'): h.update(bytes(d[at:at + pitch * h_]))
    return h.hexdigest()


def disc_templates(disc):
    """{views_key: the disc car}: whose liveries.bin a converted car's began as."""
    folder = addcar.disc_file(disc, 'media', 'cars')
    out = {}
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith('.liveries.bin'):
            out.setdefault(views_key(unpack_bin(os.path.join(folder, f))), f[:-len('.liveries.bin')])
    return out


def cab_get(files, suffix):
    return next((k for k in files if k.lower().endswith(suffix.lower())), None)


def detail_of(d):
    """detail's alpha (1024 x 1024) as the file's header places it, and as paint_shop's old slip left it (its
    header taken as 1136 bytes on a 996-byte one: indices and palette 140 bytes late), each with its colours."""
    head = struct.unpack_from('<I', d, 4)[0]
    for k in range(struct.unpack_from('<I', d, 12)[0]):
        e = 0x10 + 0x8c * k
        if d[e:e + 44].split(b'\0')[0].lower() == b'detail.tga':
            i_at = head + struct.unpack_from('<I', d, e + 0x68)[0]; p_at = head + struct.unpack_from('<I', d, e + 0x7c)[0]
            out = []
            for slip in (0, 140):
                idx = np.frombuffer(bytes(d[i_at + slip:i_at + slip + (1 << 20)]), np.uint8)
                if len(idx) < 1 << 20: break
                pal = np.frombuffer(bytes(d[p_at + slip:p_at + slip + 1024]), np.uint8).reshape(256, 4)
                out.append(pal[idx.reshape(1024, 1024)])  # BGRA
            return head, out
    return head, []


def read_atlases(files, keys):
    nc, vol, hi = (fx.textures(files[keys[n]])[0] for n in ATLASES)
    W, H, D = nc['w'], nc['h'], nc['d']
    if (vol['w'], vol['h'], vol['d'], vol['format'], nc['format'], hi['format'], hi['w'], hi['h']) != (W, H, D, 0x0F, 0x06, 0x0F, 2 * W, 2 * H) or W != 512:
        return None
    sw = fx.unswizzle_index(W, H, D)
    raw = np.frombuffer(bytes(files[keys[ATLASES[0]]][nc['start']:nc['start'] + W * H * D * 4]), np.uint8).reshape(-1, 4).copy()
    nblk = (W // 4) * (H // 4)
    vblocks = np.frombuffer(bytes(files[keys[ATLASES[1]]][vol['start']:vol['start'] + nblk * D * 16]), np.uint8).reshape(nblk, D, 16).copy()
    return dict(nc=nc, vol=vol, hi=hi, W=W, H=H, D=D, sw=sw, raw=raw, vblocks=vblocks,
                ncimg=raw[sw][..., [2, 1, 0, 3]].copy(), volimg=np.stack([fx.dxt(vblocks[:, z].tobytes(), W, H, 5) for z in range(D)]).copy(),
                hiimg=fx.dxt(bytes(files[keys[ATLASES[2]]][hi['start']:]), 2 * W, 2 * H, 5).copy())


def encode_blocks(img, blocks):
    """The 4x4 blocks of img (h, w, 4) that blocks (h/4, w/4, bool) marks, as DXT5: their numbers (row by row)
    and 16 bytes each."""
    h, w = img.shape[:2]
    which = np.nonzero(blocks.reshape(-1))[0]
    if not len(which): return which, np.zeros((0, 16), np.uint8)
    px = img.reshape(h // 4, 4, w // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 4, 4, 4)[which]
    return which, np.frombuffer(fx.encode_dxt5(np.ascontiguousarray(px.reshape(-1, 4, 4))), np.uint8).reshape(-1, 16)


def write_atlases(files, keys, A, changed_lo, changed_hi):
    """The atlases back into files: livery0nc whole (it is not compressed: nothing else changes), of livery0 and
    of livery0hi's levels only the blocks holding a changed texel."""
    W, H, D = A['W'], A['H'], A['D']
    out = {n: bytearray(files[keys[n]]) for n in ATLASES}
    A['raw'][A['sw'].reshape(-1)] = A['ncimg'][..., [2, 1, 0, 3]].reshape(-1, 4)
    out[ATLASES[0]][A['nc']['start']:A['nc']['start'] + A['raw'].size] = A['raw'].tobytes()
    blocks = changed_lo.reshape(H // 4, 4, W // 4, 4).any((1, 3))
    for z in range(D):
        which, enc = encode_blocks(A['volimg'][z], blocks)
        A['vblocks'][which, z] = enc
    out[ATLASES[1]][A['vol']['start']:A['vol']['start'] + A['vblocks'].size] = A['vblocks'].tobytes()
    level, off, s, ch = A['hiimg'].astype(np.float32), A['hi']['start'], 2 * W, changed_hi
    for lv in range(A['hi']['mips']):
        bs = max(1, s // 4)
        if lv:
            level = level.reshape(s, 2, s, 2, 4).mean((1, 3))
            ch = ch.reshape(s, 2, s, 2).any((1, 3))
        img = np.clip(level + 0.5, 0, 255).astype(np.uint8)
        if s < 4: img = np.pad(img, ((0, 4 - s), (0, 4 - s), (0, 0)), mode='edge')
        which, enc = encode_blocks(img, ch.reshape(bs, s // bs, bs, s // bs).any((1, 3)))
        for b, e in zip(which.tolist(), enc):
            out[ATLASES[2]][off + 16 * b:off + 16 * b + 16] = e.tobytes()
        off += bs * bs * 16
        s = max(1, s // 2)
    for n in ATLASES: files[keys[n]] = bytes(out[n])


def same_body(car, tcar):
    """Whether the car is the template itself (a disc car under another name): every part's vertices in place."""
    mine = {p['name']: p for p in car['parts']}
    return all(p['name'] in mine and len(mine[p['name']]['verts']) == len(p['verts'])
               and all(a[:3] == b[:3] for a, b in zip(mine[p['name']]['verts'], p['verts'])) for p in tcar['parts'])


def whiten(A, mask, keep):
    """mask's texels (1024 x 1024) made plain paint in a set of atlases (read_atlases): livery0hi's; the half-size
    ones' clean slice wherever a texel of theirs holds one (but for the kept parts'), their damaged slices only
    where the clean one was not paint already (a badge, the template's dark art: left, a dented panel would blend
    to it; where it was paint the scratches stay). Returns the texels changed, half size and full."""
    W, H, hi = A['W'], A['H'], A['hiimg']
    lo = mask.reshape(H, 2, W, 2).any((1, 3)) & ~keep.reshape(H, 2, W, 2).any((1, 3))
    changed_hi = mask & (hi != WHITE).any(-1)
    hi[mask] = WHITE
    art = lo & ((A['ncimg'][0, ..., 3] > 0) | (A['ncimg'][0, ..., :3].min(-1) < 200))
    changed_lo = np.zeros((H, W), bool)
    for img in (A['ncimg'], A['volimg']):
        for z in range(A['D']):
            m = lo if z == 0 else art
            changed_lo |= m & (img[z] != WHITE).any(-1)
            img[z][m] = WHITE
    return changed_lo, changed_hi


def fix(name, mods, out, templates, disc, max_clear=0.25, cache={}):
    """One car: (what was done or why not, a record for vinylfix.json or None)."""
    cab_path = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % name)
    bin_path = os.path.join(mods, 'media', 'cars', '%s.liveries.bin' % name)
    if not os.path.exists(bin_path): return 'left: no liveries.bin (no vinyl views)', None
    d = unpack_bin(bin_path)
    tname = templates.get(views_key(d))
    if not tname: return 'left: its views are no disc car\'s', None
    if addcar.disc_file(disc, 'media', 'cabs', 'car_%s.cab' % name): return 'left: a disc car', None
    files, root = addcar.cab_files(open(cab_path, 'rb').read())
    ck = cab_get(files, 'car.carbin')
    keys = {n: cab_get(files, B + n) for n in ATLASES}
    if not ck or None in keys.values(): return 'left: no car.carbin or livery0 atlases in its cab', None
    # the template's other baked liveries (the Ford GT's stripes: livery1, 2..., which some of the car's paints name)
    more = {}
    for k in files:
        m = re.search(r'\\livery([1-9]\d*)(nc|hi|)\.xpr$', k.lower())
        if m: more.setdefault(int(m.group(1)), {})['livery0%s.xpr' % m.group(2)] = k
    if any(len(ks) != 3 for ks in more.values()): return 'left: a baked livery with an atlas missing', None
    if tname not in cache:
        cache.clear()  # (one template's worth kept)
        tfiles, _ = addcar.cab_files(open(addcar.disc_file(disc, 'media', 'cabs', 'car_%s.cab' % tname), 'rb').read())
        tcar = carbin.read(tfiles[cab_get(tfiles, 'car.carbin')])
        cache[tname] = (tcar, n2.view_fits(tcar), n2.grow_mask(n2.template_layout(tcar)[1], 2))
    tcar, fits, tcover = cache[tname]
    car = carbin.read(files[ck])
    if same_body(car, tcar): return 'left: the disc\'s %s under another name' % tname, None
    A = read_atlases(files, keys)
    A_more = {n: read_atlases(files, ks) for n, ks in more.items()}
    if A is None or None in A_more.values(): return 'left: its atlases are not the usual 512 / 512 / 1024', None
    rects = {v: r[:4] for v, r in n2.shop_views(d).items()}
    hi = A['hiimg']
    old = hi[..., :3].astype(float)
    plain = (hi[..., 3] == 0) & (hi[..., :3].min(-1) >= 200)  # paint as the atlas has it: clear and white
    # detail's alpha as it was meant (read 140 bytes on where that is nearer the atlas)
    head, readings = detail_of(d)
    if not readings: return 'left: no detail in its liveries.bin', None
    errs = [float(np.abs(r[..., [2, 1, 0]] - old).mean()) for r in readings]
    slipped = len(errs) == 2 and head != 1136 and errs[1] < 0.6 * errs[0]
    alpha = readings[1 if slipped else 0][..., 3]
    out_bin = os.path.join(out, 'media', 'cars', '%s.liveries.bin' % name)
    os.makedirs(os.path.join(out, 'media', 'cabs'), exist_ok=True)
    os.makedirs(os.path.dirname(out_bin), exist_ok=True)

    def shop(hi_xpr, **more_):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, 'livery0hi.xpr'), 'wb').write(hi_xpr)
            n2.paint_shop(bin_path, out_bin, tmp, [], alpha=alpha, **more_)

    def detail_only(why):
        """Left as it is, but for a detail written late: made again in its place from the atlas as it stands, the
        front view's mask (its first 140 bytes written over) the template's again."""
        if not slipped: return 'left: ' + why, None
        t = n2.shop_views(unpack_bin(addcar.disc_file(disc, 'media', 'cars', '%s.liveries.bin' % tname)))
        masks = {}
        if 'front' in t and 'front' in rects:
            x, y, w, h, pitch, at = t['front']
            dt = unpack_bin(addcar.disc_file(disc, 'media', 'cars', '%s.liveries.bin' % tname))
            m = np.zeros((1024, 1024), bool)
            m[y:y + h, x:x + w] = (np.frombuffer(bytes(dt[at:at + pitch * h]), np.uint8).reshape(h, pitch)[:, :w] > 0)[:1024 - y, :1024 - x]
            masks['front'] = m
        shop(files[keys[ATLASES[2]]], masks=masks)
        return 'left, but for its paint-shop detail (140 bytes late) made again in place: ' + why, dict(template=tname, detail_only=True, detail_slipped=True, detail_err_before=errs[1], detail_err_as_stored=errs[0], head=head)

    # The paint to move: Body triangles on the template's old layout (apply_layout kept them inside its
    # triangles); one held on a single texel only if that is paint (the black insides and cabins are Body too)
    old_paint, areas, probe = {}, [0.0, 0.0], {}
    for pi, p in enumerate(car['parts']):
        if not p['verts']: continue
        V = np.array(p['verts'], float)
        for si, sp in enumerate(p['subparts']):
            if sp['material'] != n2.BODY: continue
            t = np.array(n2.strip_tris(sp['indices']), int).reshape(-1, 3)
            if not len(t): continue
            q = V[t][:, :, 10:12] / 32
            lod1 = p['name'].endswith('_LOD1')  # (the shop's slots: what the converter makes)
            c = np.floor(q).astype(int)
            ok = (c >= 0).all((1, 2)) & (c < 1024).all((1, 2))
            c = np.clip(c, 0, 1023)
            ok &= tcover[c[..., 1], c[..., 0]].all(1)
            flat = np.ptp(q, axis=1).max(1) < 1.0
            paint = ~flat | plain[c[:, 0, 1], c[:, 0, 0]]
            ok &= paint & lod1
            probe[(pi, si)] = ok
            for j in np.nonzero(ok & flat)[0]:
                uv = tuple(int(x) for x in p['verts'][t[j, 0]][10:12])
                old_paint[uv] = old_paint.get(uv, 0) + 1
            if sp['id'] == 1 and lod1 and not p['name'].startswith(('wing', 'mirror')):
                P = V[t][:, :, :3] / 4096
                a = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
                areas[0] += float(a[ok].sum()); areas[1] += float(a[paint].sum())
    if areas[0] < 0.5 * max(areas[1], 1e-9):
        return detail_only('%.0f%% of its paint on the template\'s layout (a canvas of its own)' % (100 * areas[0] / max(areas[1], 1e-9)))
    spread, single, wide, moved, plain_parts = n2.footprints(car, probe, plain)
    keep = n2.grow_mask(spread, EDGE) | n2.grow_mask(single, FLAT_EDGE - 1)
    blocked = n2.grow_mask(spread, EDGE + 2) | n2.grow_mask(single, FLAT_EDGE)
    order = iter(sorted(probe))
    res = n2.project_layout(car, fits, rects, lambda p, V, t: probe[next(order)], blocked=blocked,
                            paint=max(old_paint, key=old_paint.get) if old_paint else None, plain=(hi == WHITE).all(-1))
    if res is None: return detail_only('no painted triangles on the template\'s layout')
    if os.environ.get('VINYLFIX_DEBUG'):  # (what it worked from, for a look: the kept texels, the old layout, each view's new texels)
        os.makedirs(os.environ['VINYLFIX_DEBUG'], exist_ok=True)
        np.savez_compressed(os.path.join(os.environ['VINYLFIX_DEBUG'], name + '.npz'), blocked=blocked, keep=keep, tcover=tcover,
                            **{'view_' + v: m for v, m in res['views'].items()})
    if res['share'][2] > max_clear:
        return detail_only('%.0f%% of its paint finds no room in the views beside the packed textures (it wants converting again)' % (100 * res['share'][2]))
    paintmask = n2.grow_mask(res['cover'], 4) & ~keep  # (four texels round: the old art left beside it would show in the smaller levels)
    others = 0
    if res['spare']:
        x, y, size = res['spare_box']
        paintmask[y:y + size, x:x + size] = True
        for p in car['parts']:  # the old paint texel's other users (chrome, glass, the insides held on it) to the new one
            for i, v in enumerate(p['verts']):
                if tuple(v[10:12]) in moved:
                    p['verts'][i] = tuple(v[:10]) + res['spare']; others += 1
        for pi, si in plain_parts:  # (parts outside the slots: project_layout left their vertices where they were)
            p = car['parts'][pi]
            for i in set(p['subparts'][si]['indices']):
                p['verts'][i] = tuple(p['verts'][i][:10]) + res['spare']; others += 1
    files[ck] = carbin.write(car)
    changed_lo, changed_hi = whiten(A, paintmask, keep)
    write_atlases(files, keys, A, changed_lo, changed_hi)
    for n, An in A_more.items():  # (a baked livery: only what the template's own paint did not hold, its stripes left)
        write_atlases(files, more[n], An, *whiten(An, paintmask & ~tcover, keep))
    open(os.path.join(out, 'media', 'cabs', 'car_%s.cab' % name), 'wb').write(forzacab.pack(files, root))
    # the paint shop's copy: each view's mask its own texels (one round, clear of the others' and of the kept parts')
    masks = {v: res['views'].get(v, np.zeros((1024, 1024), bool)) for v in rects if v in n2.VIEW_DIR}
    masks = {v: n2.grow_mask(m, 1) & ~keep & ~np.logical_or.reduce([o for w, o in res['views'].items() if w != v] + [np.zeros((1024, 1024), bool)]) for v, m in masks.items()}
    shop(files[keys[ATLASES[2]]], paint=paintmask, masks=masks)
    rec = dict(template=tname, fits=res['fits'], template_fits=fits, share=res['share'], spare=res['spare'], cover=int(res['cover'].sum()),
               whitened=int(changed_hi.sum()), kept_texels=int(keep.sum()), wrapped=wide, others_moved=others, detail_slipped=bool(slipped),
               detail_err_before=errs[1 if slipped else 0], detail_err_as_stored=errs[0], head=head, baked_liveries=sorted(more))
    return 'repaired on %s\'s views: %.1f%% of its paint by the view it faces, %.1f%% by another, %.1f%% on the clear texel; %d texels made paint%s%s' % (
        tname, 100 * res['share'][0], 100 * res['share'][1], 100 * res['share'][2], rec['whitened'], '; detail was 140 bytes late' if slipped else '',
        '; baked liver%s %s kept (new texels only made paint)' % ('ies' if len(more) > 1 else 'y', ', '.join(map(str, sorted(more)))) if more else ''), rec


def main(disc, mods, out, only=(), max_clear=0.25):
    templates = disc_templates(disc)
    cabs = os.path.join(mods, 'media', 'cabs')
    names = [f[4:-4] for f in sorted(os.listdir(cabs)) if f.lower().startswith('car_') and f.lower().endswith('.cab')]
    if only: names = [n for n in names if n.lower() in [o.lower() for o in only]]
    os.makedirs(out, exist_ok=True)
    log_path = os.path.join(out, 'vinylfix.json')
    log = json.load(open(log_path)) if os.path.exists(log_path) else {}
    for name in names:
        try:
            said, rec = fix(name, mods, out, templates, disc, max_clear)
        except Exception as e:  # (one car's trouble is not the others')
            import traceback
            traceback.print_exc()
            said, rec = 'left: not read (%r)' % (e,), None
        print('%s: %s' % (name, said), flush=True)
        log[name] = dict(result=said, **(rec or {}))
        json.dump(log, open(log_path, 'w'), indent=1)


if __name__ == '__main__':
    args = sys.argv[1:]
    max_clear = 0.25
    if '--max-clear' in args:
        i = args.index('--max-clear'); max_clear = float(args[i + 1]); del args[i:i + 2]
    if len(args) < 3: raise SystemExit(__doc__)
    disc, mods, out = args[:3]
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2', 'hdd_test') for part in os.path.abspath(out).split(os.sep)):
        raise SystemExit('%s: a save folder' % out)
    if os.path.abspath(out).lower() == os.path.abspath(mods).lower():
        raise SystemExit('the out folder must not be the mods folder (copy the files over yourself, after a backup)')
    main(disc, mods, out, args[3:], max_clear)
