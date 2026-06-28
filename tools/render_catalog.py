"""Blender: render a framed thumbnail of every converted model in models/<cat>/.

  blender -b --python tools/render_catalog.py

Imports each models/<cat>/<id>/mesh/<id>.glb fresh, frames it 3/4, lights it, and
renders frames/catalog/<cat>__<id>.png (EEVEE-Next, GPU). Compose with
tools/compose_catalog.py. Shows asset shape + texture + MASK foliage so quality and
count are visible at a glance.
"""
import glob
import math
import os
import bpy
from mathutils import Vector

OUT = "/workspace/frames/catalog"
os.makedirs(OUT, exist_ok=True)
W, H = 360, 440

models = sorted(glob.glob("/workspace/models/*/*/mesh/*.glb"))
models = [m for m in models if "_collision" not in m]


def frame_and_render(glb, out_png):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        return False
    # combined world bounds
    mn = Vector((1e18, 1e18, 1e18)); mx = Vector((-1e18, -1e18, -1e18))
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector((min(mn[i], w[i]) for i in range(3)))
            mx = Vector((max(mx[i], w[i]) for i in range(3)))
    center = (mn + mx) / 2.0
    diag = (mx - mn).length or 1.0

    # camera at a 3/4 elevated angle
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    d = diag * 1.25
    cam.location = center + Vector((d * 0.7, -d * 0.9, d * 0.55))
    direction = (center - cam.location).normalized()
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    # light: sun + bright world ambient
    sun_data = bpy.data.lights.new("sun", "SUN"); sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(55), math.radians(15), math.radians(40))
    bpy.context.scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.90, 0.95, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.1
    bpy.context.scene.world = world

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x = W; sc.render.resolution_y = H
    sc.render.film_transparent = False
    sc.render.filepath = out_png
    sc.eevee.taa_render_samples = 16
    bpy.ops.render.render(write_still=True)
    return True


for glb in models:
    aid = os.path.basename(glb)[:-4]
    cat = glb.split("/models/")[1].split("/")[0]
    out = os.path.join(OUT, f"{cat}__{aid}.png")
    try:
        if frame_and_render(glb, out):
            print("CATALOG_OK", cat, aid, flush=True)
    except Exception as e:
        print("CATALOG_FAIL", cat, aid, e, flush=True)
