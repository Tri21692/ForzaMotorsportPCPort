"""Render tools/blender_export.py's OBJ from a game screenshot's camera, or a top-down view, in
Blender with no window (Eevee, textures unlit; where nothing is drawn, the void, magenta).

  blender -b --python tools/blender_render.py -- <obj> <out.png> <shot.cst | top:x,z,size> [what] [fov]
  blender -b --python tools/blender_render.py -- <obj> <out folder> cams:<cameras.json> [what] [fov]

With cams:, a level camera at each of a list ([name, position, forward], game coordinates), each
render's share of magenta below the horizon printed ("VOID <name> <share>").

The camera from the constants saved beside a screenshot (rows 166-169: up, forward, -, side and
the translation, as tools/shotpos.py reads them). `what`: scene (the scenery and the AI line; the
default), col (the collision: ground green, walls red), or all. `fov`: vertical, degrees (60).
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:]
obj_path, out, view = argv[0], argv[1], argv[2]
what = argv[3] if len(argv) > 3 else 'scene'
fov = float(argv[4]) if len(argv) > 4 else 60.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.obj(filepath=obj_path, axis_forward='-Z', axis_up='Y')  # the OBJ's (-x, y, z) -> Blender (-x, -z, y)
B = lambda p: Vector((-p[0], -p[2], p[1]))  # a game position or direction in Blender
for mat in bpy.data.materials:  # unlit: each texture as it is (repeating: the importer's did not, the
    nt = mat.node_tree             # road was its edge texels), cut out where its alpha is under half
    img = next((nd for nd in nt.nodes if nd.type == 'TEX_IMAGE'), None)
    colour = next((nd.inputs['Base Color'].default_value[:] for nd in nt.nodes if nd.type == 'BSDF_PRINCIPLED'), (0.6, 0.6, 0.6, 1))
    out_ = next(nd for nd in nt.nodes if nd.type == 'OUTPUT_MATERIAL')  # its own (a new one was not the active output)
    for nd in list(nt.nodes):
        if nd not in (img, out_): nt.nodes.remove(nd)
    em = nt.nodes.new('ShaderNodeEmission')
    if img:
        img.extension = 'REPEAT'
        tr, mix = nt.nodes.new('ShaderNodeBsdfTransparent'), nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(img.outputs['Color'], em.inputs['Color'])
        nt.links.new(img.outputs['Alpha'], mix.inputs['Fac'])
        nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out_.inputs['Surface'])
        mat.blend_method = 'CLIP'
    else:
        em.inputs['Color'].default_value = colour
        nt.links.new(em.outputs[0], out_.inputs['Surface'])
    mat.use_backface_culling = False
for o in bpy.context.scene.objects:
    col = o.name.startswith('collision')
    o.hide_render = (what == 'scene' and col) or (what == 'col' and o.name.startswith('scenery'))

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'  # (Workbench drew some meshes with another's texture)
sc.world = bpy.data.worlds.new('void')
sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs['Color'].default_value = (1.0, 0.0, 1.0, 1.0)
sc.render.resolution_x, sc.render.resolution_y = 1280, 960
sc.render.filepath = out
sc.view_settings.view_transform = 'Standard'

cam = bpy.data.cameras.new('cam')
cam.clip_start, cam.clip_end = 0.1, 3000.0
co = bpy.data.objects.new('cam', cam)
sc.collection.objects.link(co)
sc.camera = co
if view.startswith('cams:'):  # many cameras: out a folder, each [name, (x, y, z), forward (x, y, z)]
    import json
    os.makedirs(out, exist_ok=True)
    cam.sensor_fit, cam.angle_y = 'VERTICAL', math.radians(fov)
    for name, pos, fwd in json.load(open(view[5:])):
        z = -B(fwd).normalized()
        x = Vector((0, 0, 1)).cross(z).normalized()
        y = z.cross(x)
        co.matrix_world = Matrix(((x[0], y[0], z[0], 0), (x[1], y[1], z[1], 0), (x[2], y[2], z[2], 0), (0, 0, 0, 1)))
        co.location = B(pos)
        sc.render.filepath = os.path.join(out, name + '.png')
        bpy.ops.render.render(write_still=True)
        # the void: magenta below the horizon (the lower half, the camera level)
        im = bpy.data.images.load(sc.render.filepath)
        px = np.array(im.pixels[:]).reshape(im.size[1], im.size[0], 4)[:im.size[1] // 2]  # rows from the bottom
        void = (px[..., 0] > 0.9) & (px[..., 1] < 0.1) & (px[..., 2] > 0.9)
        print('VOID %s %.4f' % (name, void.mean()))
        bpy.data.images.remove(im)
    sys.exit(0)
if view.startswith('top:'):
    x, z, size = map(float, view[4:].split(','))
    cam.type, cam.ortho_scale = 'ORTHO', size
    co.location = B((x, 200.0, z))
    co.rotation_euler = (0, 0, 0)
else:
    m = np.frombuffer(open(view, 'rb').read(), '<f4').reshape(-1, 4).astype(float)[166:170]
    pos = np.linalg.solve(m[[0, 1, 3], :3], -m[[0, 1, 3], 3])
    up, fwd = B(m[0, :3]).normalized(), B(m[1, :3]).normalized()
    z = -fwd
    x = up.cross(z).normalized()
    y = z.cross(x)
    co.matrix_world = Matrix(((x[0], y[0], z[0], 0), (x[1], y[1], z[1], 0), (x[2], y[2], z[2], 0), (0, 0, 0, 1)))
    co.location = B(pos)
    cam.sensor_fit, cam.angle_y = 'VERTICAL', math.radians(fov)
    print('camera at', tuple(round(v, 1) for v in pos), 'looking', tuple(round(v, 2) for v in m[1, :3]))
bpy.ops.render.render(write_still=True)
print('rendered', out)
