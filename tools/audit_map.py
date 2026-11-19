"""A map of the whole circuit for reading: tools/blender_export.py's scenery rendered from above in
Blender, tools/collision_audit.py's findings laid over it (reachable ground green, walls white where
something drawn stands, red where nothing does, open edges yellow) and numbered markers.

  blender -b --python tools/audit_map.py -- <obj> <audit folder> <out.png> [markers.json] [px]

markers.json: [[label, x, z], ...] in game coordinates.
"""
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
obj_path, audit, out = argv[0], argv[1], argv[2]
marks = json.load(open(argv[3])) if len(argv) > 3 else []
px = int(argv[4]) if len(argv) > 4 else 3000

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.obj(filepath=obj_path, axis_forward='-Z', axis_up='Y')
B = lambda x, y, z: Vector((-x, -z, y))
for o in list(bpy.context.scene.objects):
    if o.name.startswith('collision') or o.name == 'loop': o.hide_render = True
for mat in bpy.data.materials:  # unlit, as blender_render.py's
    nt = mat.node_tree
    img = next((nd for nd in nt.nodes if nd.type == 'TEX_IMAGE'), None)
    out_ = next(nd for nd in nt.nodes if nd.type == 'OUTPUT_MATERIAL')
    for nd in list(nt.nodes):
        if nd not in (img, out_): nt.nodes.remove(nd)
    em = nt.nodes.new('ShaderNodeEmission')
    if img:
        img.extension = 'REPEAT'
        tr, mix = nt.nodes.new('ShaderNodeBsdfTransparent'), nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(img.outputs['Color'], em.inputs['Color']); nt.links.new(img.outputs['Alpha'], mix.inputs['Fac'])
        nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out_.inputs['Surface'])
        mat.blend_method = 'CLIP'
    else:
        em.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1); nt.links.new(em.outputs[0], out_.inputs['Surface'])
    mat.use_backface_culling = False

# the audit as a plane over everything, its colours where something was found (the void stays clear)
d = np.load(audit + '/audit.npz')
img, lo = d['img'].astype(float) / 255, d['lo']
H, W = img.shape[:2]
CELL = 0.5
alpha = np.zeros((H, W))
col = img[..., :3]
is_ = lambda c: np.all(np.abs(col - np.array(c) / 255) < 0.02, -1)
alpha[is_((40, 110, 40))] = 0.35                                         # reachable
for c in ((200, 200, 200), (255, 30, 30), (255, 220, 0)): alpha[is_(c)] = 1.0  # walls, invisible, open
# the lines a cell thick: widened for the map (red and yellow over white)
def widen(m):
    g = m.copy()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1): g |= np.roll(np.roll(m, dr, 0), dc, 1)
    return g
rgba = np.dstack([col, alpha])
for c, a in (((200, 200, 200), 1), ((255, 30, 30), 1), ((255, 220, 0), 1)):
    m = widen(is_(c))
    rgba[m, :3] = np.array(c) / 255; rgba[m, 3] = a
im = bpy.data.images.new('audit', W, H, alpha=True)
im.pixels = rgba.ravel().tolist()  # rows from the bottom: row 0 the grid's lowest z
x0, z0 = lo[0], lo[1]
x1, z1 = lo[0] + W * CELL, lo[1] + H * CELL
me = bpy.data.meshes.new('audit')
me.from_pydata([B(x0, 60, z0), B(x1, 60, z0), B(x1, 60, z1), B(x0, 60, z1)], [], [(0, 1, 2, 3)])
uv = me.uv_layers.new()
for k, (u, v) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))): uv.data[k].uv = (u, v)
ob = bpy.data.objects.new('audit', me); bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new('audit'); mat.use_nodes = True; nt = mat.node_tree
for nd in list(nt.nodes):
    if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
out_ = nt.nodes['Material Output']
tex, em, tr, mix = (nt.nodes.new(t) for t in ('ShaderNodeTexImage', 'ShaderNodeEmission', 'ShaderNodeBsdfTransparent', 'ShaderNodeMixShader'))
tex.image, tex.interpolation = im, 'Closest'
nt.links.new(tex.outputs['Color'], em.inputs['Color']); nt.links.new(tex.outputs['Alpha'], mix.inputs['Fac'])
nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out_.inputs['Surface'])
mat.blend_method = 'BLEND'
me.materials.append(mat)

# numbered markers: a ring and its number, white on black
def marker(label, x, z):
    bpy.ops.mesh.primitive_torus_add(major_radius=7, minor_radius=1.2, location=B(x, 70, z))
    t = bpy.context.object
    bpy.ops.object.text_add(location=B(x, 71, z) + Vector((-9, 4, 0)))
    tx = bpy.context.object
    tx.data.body, tx.data.size = str(label), 12
    tx.rotation_euler = (0, 0, math.pi)  # upright under the camera, turned for north up
    for o, c in ((t, (1, 1, 1, 1)), (tx, (1, 1, 1, 1))):
        m = bpy.data.materials.new('mark'); m.use_nodes = True
        n = m.node_tree; [n.nodes.remove(q) for q in list(n.nodes) if q.type != 'OUTPUT_MATERIAL']
        e = n.nodes.new('ShaderNodeEmission'); e.inputs['Color'].default_value = c
        n.links.new(e.outputs[0], n.nodes['Material Output'].inputs['Surface'])
        o.data.materials.append(m)
for label, x, z in marks: marker(label, x, z)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.world = bpy.data.worlds.new('w'); sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.02, 0.02, 0.02, 1)
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = sc.render.resolution_y = px
sc.render.film_transparent = False
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.clip_end = 1000
size = max(x1 - x0, z1 - z0)
cam.ortho_scale = size
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
co.location = B((x0 + x1) / 2, 300, (z0 + z1) / 2)
co.rotation_euler = (0, 0, math.pi)  # north (+z) up, the game's own way round
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print('map', out)
