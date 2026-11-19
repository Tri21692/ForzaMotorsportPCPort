"""A car as the career's Race Type icons draw their objects: light grey with white highlights and soft
shade, a black outline, on a clear background (Blender 3.3, headless), for drifticon.py.

  blender -b --python tools/caricon.py -- <car.carbin> <out.png> [width height] [yaw pitch]

The stock body at its finest detail; the glass dark grey. The wheels (another archive's) are drawn as
plain tyres at the axles, found from the body's length. yaw turns the car from side-on (degrees; 35 is
a front three-quarter view), pitch is the camera's height (degrees)."""
import math
import os
import re
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carbin

argv = sys.argv[sys.argv.index('--') + 1:]
path, out = argv[0], argv[1]
W, H = (int(argv[2]), int(argv[3])) if len(argv) > 3 else (840, 468)
yaw, pitch = (float(argv[4]), float(argv[5])) if len(argv) > 5 else (35.0, 14.0)
car = carbin.read(open(path, 'rb').read())

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def flat(name, grey, rough=0.6, spec=0.3):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (grey, grey, grey, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Specular'].default_value = spec
    return m


BODY, GLASS, DARK, RIM = flat('body', 0.62, 0.35, 0.6), flat('glass', 0.06, 0.2, 0.5), flat('dark', 0.03), flat('rim', 0.45, 0.3, 0.6)
GLASS_IDS = (2, 6, 16, 28, 30)

FAM = {}
for n in {p['name'] for p in car['parts']}:
    m = re.match(r'(.*?(?:bumperF|bumperR|hood|skirtL|skirtR|wing|exhaust|mirrorL|mirrorR|taillightL|taillightR|glassLHL|glassRHL|glassLTL|glassRTL))(race[A-C]?|[a-z]?p?)_LOD1$', n)
    if m: FAM.setdefault(m.group(1), []).append((m.group(2), n))


def stock(n):
    if not n.endswith('_LOD1') and '_LOD' in n: return False
    if n.startswith(('driver', 'Head', 'Chest', 'Abdomen', 'Left_', 'Right_', 'cagerace', 'nocage', 'aaa_')): return False
    for f, vs in FAM.items():
        if any(v[1] == n for v in vs):
            if f.endswith('wing'): return False
            ok = sorted(v for v in vs if not v[0].startswith('race'))
            return bool(ok) and ok[0][1] == n
    return True


S = 1 / 4096 / 1.6
objs = []
for p in car['parts']:
    V = p['verts']
    if not V or not stock(p['name']) or re.search('interior|cabin|dash|seat|steer', p['name'], re.I): continue
    faces, fmat = [], []
    for sp in p['subparts']:
        if sp['id'] != 1: continue
        ix = sp['indices']
        for k in range(len(ix) - 2):
            a, b, c = (ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
            if len({a, b, c}) < 3: continue
            faces.append((a, b, c)), fmat.append(1 if sp['material'] in GLASS_IDS else 0)
    if not faces: continue
    me = bpy.data.meshes.new(p['name'])
    me.from_pydata([(v[2] * S, -v[0] * S, v[1] * S) for v in V], [], faces)
    me.materials.append(BODY), me.materials.append(GLASS)
    for f, mi in zip(me.polygons, fmat): f.material_index = mi
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    me.use_auto_smooth = True
    me.normals_split_custom_set_from_vertices([(lambda n: (n[2], -n[0], n[1]))([c / 32767 for c in v[3:6]]) for v in V])
    o = bpy.data.objects.new(p['name'], me)
    scene.collection.objects.link(o)
    objs.append(o)

# the body's extent: x along the car (front +), y across, z up
pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
x0, x1 = min(p.x for p in pts), max(p.x for p in pts)
y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
z0, z1 = min(p.z for p in pts), max(p.z for p in pts)
L, Wd = x1 - x0, y1 - y0
r = 0.075 * L  # a tyre's radius (0.31 m on a 4.2 m car)
for ax in (x1 - 0.205 * L, x0 + 0.215 * L):
    for side in (-1, 1):
        y = (y0 + y1) / 2 + side * (Wd / 2 - 0.11 * Wd)
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=0.2 * Wd, location=(ax, y, z0 + r * 0.92), rotation=(math.pi / 2, 0, 0), vertices=40)
        t = bpy.context.object
        t.data.materials.append(DARK)
        bpy.ops.mesh.primitive_cylinder_add(radius=r * 0.62, depth=0.2 * Wd + 0.02, location=(ax, y, z0 + r * 0.92), rotation=(math.pi / 2, 0, 0), vertices=40)
        bpy.context.object.data.materials.append(RIM)

# light: a key from above front, a fill, a grey world (soft shade, white highlights)
for rot, e in (((math.radians(35), 0, math.radians(-40)), 3.2), ((math.radians(70), 0, math.radians(150)), 1.0)):
    s = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    s.data.energy = e
    s.rotation_euler = rot
    scene.collection.objects.link(s)
scene.world = bpy.data.worlds.new('w')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value = 0.55
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.use_gtao = True
scene.view_settings.view_transform = 'Standard'
scene.render.film_transparent = True
scene.render.resolution_x, scene.render.resolution_y = W, H
# the outline (Freestyle): silhouettes and borders thick, creases thin, black
scene.render.use_freestyle = True
scene.render.line_thickness_mode = 'ABSOLUTE'
vl = scene.view_layers[0]
ls = vl.freestyle_settings.linesets.active if vl.freestyle_settings.linesets else vl.freestyle_settings.linesets.new('lines')
ls.select_by_visibility = True
ls.select_silhouette, ls.select_border, ls.select_crease, ls.select_external_contour = True, True, True, True
if ls.linestyle is None: ls.linestyle = bpy.data.linestyles.new('lines')  # (a new line set has none)
ls.linestyle.color = (0, 0, 0)
ls.linestyle.thickness = max(2.0, W / 220)
vl.freestyle_settings.crease_angle = math.radians(120)

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = 'ORTHO'
centre = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2 - 0.1))
a, e = math.radians(yaw), math.radians(pitch)
d = Vector((math.cos(a) * math.cos(e), -math.sin(a) * math.cos(e), math.sin(e)))
cam.location = centre + d * 20
cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
cam.data.ortho_scale = L * 1.12
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
