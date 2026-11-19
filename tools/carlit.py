"""A Forza car drawn lit in Blender (3.3, headless), close to how the game shades it, to check a converted car
offline before anyone drives it:

  blender -b --python tools/carlit.py -- <car.carbin> <atlas png> <out prefix> [paint r,g,b]

The atlas is the cab's livery0hi.xpr as PNG with its alpha (forzaxpr.dxt). Drawn: the stock parts (each shop
slot's plain or 'a' variant, no wing, no race parts or driver), the finest detail level, the carbin's own
normals and shading bytes, Body as paint times the texel where the atlas is clear (alpha 0), glass see-through.
Writes <out prefix>_<view>.png for the views front, rear, left, fside.

Env: VIEWS=front,rear,...  (also lclose, rclose, fclose, rtop, cabin, rearc)  ALL=1 every part
     ICON=1 the car-select tile's view (icon: a front three-quarter, no ground, a clear background, 512 x 256)
     PARTS=1 a flat colour a part (the names printed)   ONLYP=<regex> only those parts   PICK=<name,...> add these
     SLOTS=bumperF:b,skirtL:b,hood:e,wing:c  those shop variants instead of the stock ones
     BACKRED=1 back faces (by the carbin's winding) red   LEVEL=<n> that detail level instead of the finest

It found the Celica GT-Four still on its template's body, the Underground 2 decals as black boxes and the MX-5's
squashed cabin (1 Nov), none of which the unlit preview (carobj.py) showed plainly."""
import math
import os
import re
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carbin

argv = sys.argv[sys.argv.index('--') + 1:]
path, atlas, out = argv[0], argv[1], argv[2]
paint = tuple(float(x) for x in argv[3].split(',')) if len(argv) > 3 else (0.75, 0.08, 0.06)
car = carbin.read(open(path, 'rb').read())
names = {p['name'] for p in car['parts']}


FAM = {}
for n in names:  # a slot's variants: the plain one first, then a, b, ...
    m = re.match(r'(.*?(?:bumperF|bumperR|hood|skirtL|skirtR|wing|exhaust|mirrorL|mirrorR|taillightL|taillightR|glassLHL|glassRHL|glassLTL|glassRTL))(race[A-C]?|[a-z]?p?)_LOD1$', n)
    if m: FAM.setdefault(m.group(1), []).append((m.group(2), n))
PICK = set(os.environ.get('PICK', '').split(','))


SLOTS = dict(kv.split(':') for kv in os.environ.get('SLOTS', '').split(',') if ':' in kv)  # SLOTS=bumperF:b,hood:e: that shop variant drawn for the slot


def stock(n):
    if os.environ.get('ALL') or n in PICK: return True
    for f, vs in FAM.items():  # (a shop variant asked for: drawn in its slot's place, wings too)
        key = next((k for k in SLOTS if f.endswith(k)), None)
        if key and any(v[1] == n for v in vs) and any(v[0] == SLOTS[key] for v in vs):
            return any(v[0] == SLOTS[key] and v[1] == n for v in vs)
    if n.startswith(('driver', 'Head', 'Chest', 'Abdomen', 'Left_', 'Right_', 'cagerace', 'nocage', 'aaa_')): return False
    for f, vs in FAM.items():
        if any(v[1] == n for v in vs):
            if f.endswith('wing'): return False  # no wing on a stock car
            ok = sorted(v for v in vs if not v[0].startswith('race'))
            return bool(ok) and ok[0][1] == n
    return True


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
img = bpy.data.images.load(atlas)
mats = {}


def material(mid):
    if mid in mats: return mats[mid]
    m = bpy.data.materials.new('m%d' % mid)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img; tex.interpolation = 'Closest' if mid == 1 else 'Linear'
    vc = nt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'shade'
    mul = nt.nodes.new('ShaderNodeMixRGB'); mul.blend_type = 'MULTIPLY'; mul.inputs[0].default_value = 1
    col = tex.outputs['Color']
    if mid == 1:  # Body: paint where the texel is clear, times the texel
        pm = nt.nodes.new('ShaderNodeMixRGB'); pm.blend_type = 'MULTIPLY'; pm.inputs[0].default_value = 1
        pm.inputs[2].default_value = (*paint, 1)
        nt.links.new(col, pm.inputs[1])
        sel = nt.nodes.new('ShaderNodeMixRGB')
        nt.links.new(tex.outputs['Alpha'], sel.inputs[0])
        nt.links.new(pm.outputs[0], sel.inputs[1])
        nt.links.new(col, sel.inputs[2])
        col = sel.outputs[0]
        bsdf.inputs['Roughness'].default_value = 0.25
        bsdf.inputs['Clearcoat'].default_value = 0.6
    nt.links.new(col, mul.inputs[1])
    nt.links.new(vc.outputs['Color'], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs['Base Color'])
    if mid in (2, 6, 16, 28, 30):  # glass
        bsdf.inputs['Alpha'].default_value = 0.35 if mid == 2 else 0.5
        bsdf.inputs['Roughness'].default_value = 0.05
        m.blend_method = 'BLEND'
    if mid == 7:
        bsdf.inputs['Metallic'].default_value = 1; bsdf.inputs['Roughness'].default_value = 0.15
    if os.environ.get('BACKRED'):
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        em = nt.nodes.new('ShaderNodeEmission'); em.inputs[0].default_value = (1, 0, 0, 1)
        mix = nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(geo.outputs['Backfacing'], mix.inputs[0])
        nt.links.new(bsdf.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], nt.nodes['Material Output'].inputs[0])
    m.use_backface_culling = False
    mats[mid] = m
    return m


S = 1 / 4096 / 1.6
PAL = [(0.9, 0.1, 0.1), (0.1, 0.7, 0.1), (0.1, 0.3, 0.95), (0.95, 0.85, 0.1), (0.8, 0.2, 0.9), (0.1, 0.9, 0.9),
       (1.0, 0.5, 0.0), (0.5, 0.5, 0.5), (0.45, 0.25, 0.05), (1, 1, 1), (0.05, 0.05, 0.05), (0.6, 0.9, 0.4)]
shown = []
for p in car['parts']:
    V = p['verts']
    if not V or not stock(p['name']): continue
    if os.environ.get('ONLYP') and not re.search(os.environ['ONLYP'], p['name']): continue
    shown.append(p['name'])
    faces, fmat, order = [], [], []
    for sp in p['subparts']:
        if sp['id'] != int(os.environ.get('LEVEL', '1')): continue  # (LEVEL=2..4: a far detail level, tools/carlods.py's)
        if sp['material'] not in order: order.append(sp['material'])
        ix = sp['indices']
        for k in range(len(ix) - 2):
            a, b, c = (ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
            if len({a, b, c}) < 3: continue
            faces.append((a, b, c) if not os.environ.get('FLIPW') else (a, c, b)); fmat.append(order.index(sp['material']))
    if not faces: continue
    me = bpy.data.meshes.new(p['name'])
    me.from_pydata([(v[2] * S, -v[0] * S, v[1] * S) for v in V], [], faces)
    if os.environ.get('PARTS'):  # a flat colour a part
        pm = bpy.data.materials.new(p['name']); c = PAL[len(shown) % len(PAL)]
        pm.diffuse_color = (*c, 1); pm.use_nodes = True; pm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*c, 1)
        print('PART', c, p['name'], len(V))
        order = [order[0]] * 0 + [None]; fmat = [0] * len(fmat); me.materials.append(pm)
    for mid in order:
        if mid is not None: me.materials.append(material(mid))
    for f, mi in zip(me.polygons, fmat): f.material_index = mi
    uv = me.uv_layers.new(name='uv')
    vcl = me.vertex_colors.new(name='shade')
    for loop in me.loops:
        v = V[loop.vertex_index]
        uv.data[loop.index].uv = (v[10] / 32768 % 1, 1 - v[11] / 32768 % 1)
        vcl.data[loop.index].color = (0.35 + 0.65 * v[6] / 255,) * 3 + (1,)  # the first shading byte: occlusion (the second, the reflection's, is not drawn)
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    me.use_auto_smooth = True
    me.normals_split_custom_set_from_vertices([(lambda n: (n[2], -n[0], n[1]))([c / 32767 for c in v[3:6]]) for v in V])
    o = bpy.data.objects.new(p['name'], me)
    scene.collection.objects.link(o)
print('SHOWN', ' '.join(shown))
if os.environ.get('ICON') or os.environ.get('HUBS'):  # the tile's car stands on wheels: tyres and rims in its arches (the carbin has none), each arch
    # where the body's lower edge along its sides rises (the middle of each raised run), the tyre to its top
    import numpy as np
    P = np.array([tuple(o.matrix_world @ v.co) for o in scene.objects if o.type == 'MESH' for v in o.data.vertices])
    x0, x1, y0, y1, zlo = P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min()
    L, Wd = x1 - x0, y1 - y0
    side = P[np.abs(P[:, 1] - (y0 + y1) / 2) > 0.38 * Wd]
    bins = np.floor((side[:, 0] - x0) / (L / 80)).astype(int)
    low = np.full(80, np.nan)
    for b_ in range(80):
        z = side[bins == b_, 2]
        if len(z): low[b_] = z.min()
    sill = np.nanpercentile(low, 15)
    axles = []
    for half in (range(40, 80), range(0, 40)):  # front half (x up), rear half
        run = [b_ for b_ in half if np.isfinite(low[b_]) and low[b_] > sill + 0.06 * L / 4.2]
        if run:
            mid = (min(run) + max(run) + 1) / 2 * L / 80 + x0
            top = np.nanmax(low[min(run):max(run) + 1])
            axles.append((mid, top, (max(run) - min(run) + 1) * L / 80))
    rubber = bpy.data.materials.new('tyre'); rubber.use_nodes = True
    rubber.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.02, 0.02, 0.02, 1)
    rubber.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.8
    alloy = bpy.data.materials.new('rim'); alloy.use_nodes = True
    alloy.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.32, 0.33, 0.35, 1)
    alloy.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = 0.9
    alloy.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.25
    radii = [0.074 * L] * len(axles)  # (a 0.31 m tyre on a 4.2 m car)
    centres = [None] * len(axles)
    if os.environ.get('HUBS'):  # HUBS=hf,hr,ride_f,ride_r,dia_f,dia_r: the wheels where the game puts them (model units for the
        # hubs, metres for the rest: the template's physics and tyres), to check a car's arches against them
        hf_, hr_, rf_, rr_, df_, dr_ = (float(x) for x in os.environ['HUBS'].split(','))
        axles = [(hf_ * 4096 * S, 0, 0), (hr_ * 4096 * S, 0, 0)]
        radii = [df_ / 2, dr_ / 2]
        centres = [-rf_ + df_ / 2, -rr_ + dr_ / 2]
    if os.environ.get('TIRE'):  # TIRE=tire.carbin, TSCALE=front,rear, TRACK=front,rear (maxdata TrackOuter, m), TPOS=outer|centre:
        # the game's own tyre model at its draw scale, the tyre's outer face (or its middle) at half the track
        tc = carbin.read(open(os.environ['TIRE'], 'rb').read())
        tsf, tsr = (float(x) for x in os.environ.get('TSCALE', '1,1').split(','))
        tf_, tr_ = (float(x) for x in os.environ['TRACK'].split(','))
        cy = (y0 + y1) / 2
        for (ax, _, _), zc0, sc, trk in zip(axles, centres, (tsf, tsr), (tf_, tr_)):
            for q in tc['parts']:
                if not q['verts'] or not q['name'].endswith(('LOD1', '_LOD')): continue  # (an imported wheel's own model: wheel_LOD)
                TV = [(v[0] * S * 1.6 / 1.6, v[1] * S, v[2] * S) for v in q['verts']]
                xs_ = [v[0] for v in TV]; xmid = (min(xs_) + max(xs_)) / 2; half = (max(xs_) - min(xs_)) / 2 * sc
                for sgn in (-1, 1):
                    lat = trk / 2 - (half if os.environ.get('TPOS', 'outer') == 'outer' else 0)
                    tf_faces = []
                    for sp in q['subparts']:
                        if sp['id'] != 1: continue
                        ix = sp['indices']
                        for kk in range(len(ix) - 2):
                            a_, b_, c_ = (ix[kk], ix[kk + 1], ix[kk + 2]) if kk % 2 == 0 else (ix[kk + 1], ix[kk], ix[kk + 2])
                            if len({a_, b_, c_}) == 3: tf_faces.append((a_, b_, c_))
                    me_ = bpy.data.meshes.new('tyre')
                    me_.from_pydata([(ax + v[2] * sc, cy + sgn * (lat + (v[0] - xmid) * sc * sgn * -1), zc0 + v[1] * sc) for v in TV], [], tf_faces)
                    o_ = bpy.data.objects.new('tyre', me_); scene.collection.objects.link(o_); me_.materials.append(rubber)
        axles = []
    for (ax, top, width), r, zc0 in zip(axles, radii, centres):
        for sgn in (-1, 1):
            y = (y0 + y1) / 2 + sgn * (Wd / 2 - 0.14 * Wd)
            zc = sill + 0.3 * r if zc0 is None else zc0  # (from the sill: the arch liners hang low and hide the arch top)
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=0.15 * Wd, location=(ax, y, zc), rotation=(math.pi / 2, 0, 0), vertices=48)
            bpy.context.object.data.materials.append(rubber)
            bpy.ops.mesh.primitive_cylinder_add(radius=r * 0.64, depth=0.15 * Wd + 0.01, location=(ax, y, zc), rotation=(math.pi / 2, 0, 0), vertices=48)
            bpy.context.object.data.materials.append(alloy)
            if os.environ.get('DEALER'):  # close up: an alloy's look, a dark barrel, five spokes, a lip and a cap on the outer face
                if 'barrel' not in bpy.data.materials:
                    bm_ = bpy.data.materials.new('barrel'); bm_.use_nodes = True
                    bm_.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.04, 0.04, 0.045, 1)
                    bm_.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = 0.6
                bpy.context.object.data.materials[0] = bpy.data.materials['barrel']
                yo = y + sgn * (0.075 * Wd + 0.006)
                for s_ in range(5):
                    a_ = 2 * math.pi * s_ / 5 + 0.3
                    bpy.ops.mesh.primitive_cube_add(size=1, location=(ax + math.cos(a_) * r * 0.31, yo, zc + math.sin(a_) * r * 0.31), rotation=(0, -a_, 0))
                    sp_ = bpy.context.object; sp_.scale = (r * 0.62, 0.025, r * 0.13); sp_.data.materials.append(alloy)
                bpy.ops.mesh.primitive_torus_add(major_radius=r * 0.62, minor_radius=r * 0.035, location=(ax, yo, zc), rotation=(math.pi / 2, 0, 0))
                bpy.context.object.data.materials.append(alloy)
                bpy.ops.mesh.primitive_cylinder_add(radius=r * 0.12, depth=0.03, location=(ax, yo, zc), rotation=(math.pi / 2, 0, 0), vertices=24)
                bpy.context.object.data.materials.append(alloy)
    print('ICON axles', [(round(a, 2), round(t, 2), round(w, 2)) for a, t, w in axles])
# ground, light, world
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -0.02))
g = bpy.context.object; gm = bpy.data.materials.new('ground'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.35, 0.35, 0.37, 1); g.data.materials.append(gm)
zmin = min(o.bound_box[0][2] + 0 for o in scene.objects if o.type == 'MESH' and o != g)
g.location.z = min(v.co.z for o in scene.objects if o.type == 'MESH' and o != g for v in o.data.vertices) - 0.33
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(-30)); scene.collection.objects.link(sun)
scene.world = bpy.data.worlds.new('w'); scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs[0].default_value = (0.6, 0.65, 0.75, 1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value = 0.9
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.use_ssr = True; scene.eevee.use_gtao = True; scene.eevee.use_soft_shadows = True
scene.render.resolution_x, scene.render.resolution_y = 900, 600
if os.environ.get('ICON'):  # the car-select tile: the car alone on a clear background, wide
    g.hide_render = True
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = 512, 256
if os.environ.get('DEALER'):  # a maker's dealer background (addmake.py --dealer, the user's of 9 Nov): the car close up on
    # asphalt under a sky, as the disc's (418 x 480 of the 512 x 512, drawn here at twice that); the camera from CAMS
    scene.render.resolution_x, scene.render.resolution_y = 836, 960
    g.scale = (10, 10, 1)
    tyres_ = [o for o in scene.objects if o.type == 'MESH' and o.data.materials and o.data.materials[0].name.startswith('tyre')]
    if tyres_: g.location.z = min((o.matrix_world @ v.co).z for o in tyres_ for v in o.data.vertices) + 0.005  # (the car on its tyres)
    nt = gm.node_tree; bsdf = nt.nodes['Principled BSDF']
    tco = nt.nodes.new('ShaderNodeTexCoord')
    noise = nt.nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 400.0; noise.inputs['Detail'].default_value = 4.0
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.4, 0.6
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = (0.075, 0.075, 0.08, 1), (0.13, 0.13, 0.135, 1)
    nt.links.new(tco.outputs['Object'], noise.inputs['Vector'])
    nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac']); nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.95; bsdf.inputs['Specular'].default_value = 0.12
    # the sky: pale at the horizon to a soft blue above (the view's height, Generated z, through a ramp)
    wn = scene.world.node_tree; wtc = wn.nodes.new('ShaderNodeTexCoord'); sep = wn.nodes.new('ShaderNodeSeparateXYZ')
    wr = wn.nodes.new('ShaderNodeValToRGB')
    wr.color_ramp.elements[0].position, wr.color_ramp.elements[1].position = 0.0, 0.3
    wr.color_ramp.elements[0].color, wr.color_ramp.elements[1].color = (0.72, 0.78, 0.86, 1), (0.25, 0.4, 0.68, 1)
    wn.links.new(wtc.outputs['Generated'], sep.inputs[0]); wn.links.new(sep.outputs['Z'], wr.inputs['Fac'])
    wn.links.new(wr.outputs['Color'], wn.nodes['Background'].inputs['Color'])
    wn.nodes['Background'].inputs['Strength'].default_value = float(os.environ.get('SKY', '0.75'))
    sun.data.energy = 4.5; sun.data.angle = math.radians(4)
    c0 = os.environ.get('CAMS', '').split(';')[0].split(':')
    if len(c0) >= 7:  # the sun over the camera's shoulder: the side shown lit
        from mathutils import Vector
        to_cam = Vector((float(c0[1]) - float(c0[4]), float(c0[2]) - float(c0[5]), 0)).normalized()
        s_ = Vector((to_cam.x * math.cos(0.6) - to_cam.y * math.sin(0.6), to_cam.x * math.sin(0.6) + to_cam.y * math.cos(0.6), 1.1))
        sun.rotation_euler = (-s_).to_track_quat('-Z', 'Y').to_euler()
    scene.view_settings.view_transform = 'Standard'  # (Filmic washed the paint out: the disc's are saturated)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 45
views = {'icon': (6.4, -6.6, 2.2), 'front': (6.0, -4.2, 1.9), 'rear': (-6.0, 4.2, 2.1), 'left': (0.2, 8.0, 0.8), 'fside': (4.5, 5.5, 1.2), 'lclose': (0.3, 4.6, 0.6), 'rclose': (-2.2, 3.2, 1.0), 'fclose': (3.4, -1.6, 0.9), 'rtop': (-3.6, 1.8, 2.6), 'cabin': (0.6, 2.2, 2.4), 'rearc': (-4.6, 1.4, 0.9)}
if os.environ.get('CAMS'):  # CAMS=name:x:y:z:tx:ty:tz;...  cameras of one's own, each looking at its target (metres, Blender's axes)
    views = {}; targets = {}
    for c_ in os.environ['CAMS'].split(';'):
        n_, *xs_ = c_.split(':'); xs_ = [float(x) for x in xs_]
        views[n_] = tuple(xs_[:3]); targets[n_] = tuple(xs_[3:6])
elif os.environ.get('VIEWS'): views = {k: views[k] for k in os.environ['VIEWS'].split(',')}
elif os.environ.get('ICON'): views = {'icon': views['icon']}
elif 'icon' in views: del views['icon']
for name, (x, y, z) in views.items():
    cam.location = (x, y, z)
    cam.data.lens = 45 if 'close' not in name else 35
    if name == 'icon': cam.data.lens = 52
    from mathutils import Vector
    tgt = Vector(targets[name]) if os.environ.get('CAMS') else Vector((0, 0, 0))
    if os.environ.get('CAMS'): cam.data.lens = float(os.environ.get('LENS', '50'))
    cam.rotation_euler = (tgt - cam.location).normalized().to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = '%s_%s.png' % (out, name)
    bpy.ops.render.render(write_still=True)
