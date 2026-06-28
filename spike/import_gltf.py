"""Blender: import a Poly Haven glTF, normalize, save a self-contained .blend
ready for `forest3d convert`.

  blender -b --python spike/import_gltf.py -- <gltf_path> <out_blend> [scale]

Normalize = join nothing (keep materials), apply transforms, recenter so the
model's footprint is at XY origin and its base sits at z=0 (so terrain placement
puts it ON the ground), optionally apply an extra uniform scale, pack textures.
"""
import sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
gltf_path, out_blend = argv[0], argv[1]
extra_scale = float(argv[2]) if len(argv) > 2 else 1.0
# optional: splice an EXTERNAL alpha map into foliage materials whose name contains
# alpha_substr (Poly Haven's glTF omits foliage alpha; pass twigs_alpha.png here).
alpha_map = argv[3] if len(argv) > 3 and argv[3] not in ("-", "") else None
alpha_substr = argv[4] if len(argv) > 4 else "twig"

# clean scene
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=gltf_path)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no mesh objects imported")

# apply all transforms so world coords are real
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# combined world-space bounds
mn = Vector((1e18, 1e18, 1e18))
mx = Vector((-1e18, -1e18, -1e18))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        mn = Vector((min(mn[i], w[i]) for i in range(3)))
        mx = Vector((max(mx[i], w[i]) for i in range(3)))
cx = (mn[0] + mx[0]) / 2.0
cy = (mn[1] + mx[1]) / 2.0
zmin = mn[2]

# recenter footprint to origin, base to z=0, then optional uniform scale about origin
for o in meshes:
    o.location.x -= cx
    o.location.y -= cy
    o.location.z -= zmin
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
if extra_scale != 1.0:
    for o in meshes:
        o.scale = (extra_scale, extra_scale, extra_scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

print(f"NORMALIZED size x={mx[0]-mn[0]:.2f} y={mx[1]-mn[1]:.2f} z={(mx[2]-zmin):.2f} m "
      f"(x{extra_scale}) materials={[m.name for m in bpy.data.materials]}")

# --- foliage alpha fix --------------------------------------------------------
# Blender 4.2's glTF exporter writes alphaMode from the NODE pattern, not
# blend_method (EEVEE-Next dropped CLIP). The glTF *importer* connects the alpha
# straight to BSDF.Alpha, so on re-export foliage comes out OPAQUE (solid white
# cards). For any material whose Alpha is driven, splice a Math:Greater-Than(0.5)
# node before BSDF.Alpha -> exporter detects alphaMode=MASK. Solid materials are
# left OPAQUE. (Same trick as spike/normalize_island_tree.py, generalized.)
for m in bpy.data.materials:
    if not m.use_nodes or not m.node_tree:
        continue
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        continue
    ain = bsdf.inputs["Alpha"]
    if not ain.is_linked and alpha_map and alpha_substr in m.name.lower():
        # wire the external alpha map (gltf had none for this foliage material)
        img = bpy.data.images.load(alpha_map, check_existing=True)
        img.colorspace_settings.name = "Non-Color"
        tnode = nt.nodes.new("ShaderNodeTexImage")
        tnode.image = img
        tnode.location = (bsdf.location.x - 700, bsdf.location.y - 300)
        nt.links.new(tnode.outputs["Color"], ain)
        print("EXTERNAL_ALPHA_LOADED:", m.name, alpha_map.split("/")[-1])
    if not ain.is_linked:
        m.blend_method = "OPAQUE"
        continue
    src = ain.links[0].from_socket
    if src.node.type == "MATH" and src.node.operation == "GREATER_THAN":
        pass  # already wired
    else:
        for lk in list(ain.links):
            nt.links.remove(lk)
        clip = nt.nodes.new("ShaderNodeMath")
        clip.operation = "GREATER_THAN"
        clip.inputs[1].default_value = 0.5
        clip.location = (src.node.location.x + 200, src.node.location.y - 150)
        nt.links.new(src, clip.inputs[0])
        nt.links.new(clip.outputs["Value"], ain)
    m.blend_method = "CLIP"
    m.alpha_threshold = 0.5
    m.use_backface_culling = False
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        pass
    print("ALPHA_MASK_WIRED:", m.name)

# self-contained
try:
    bpy.ops.file.pack_all()
except Exception as e:
    print("pack_all warn:", e)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("SAVED", out_blend)
