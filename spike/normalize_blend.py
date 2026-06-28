"""Blender: open a Poly Haven native .blend, normalize, save a self-contained
.blend ready for `forest3d convert`.

  blender -b <in.blend> --python spike/normalize_blend.py -- <out_blend> [scale] [variant]

Poly Haven kit .blends ship many variants (a,b,c,...) x several LODs; only the LOD0
objects are linked to the view layer. We keep a single LOD (the lowest-numbered LOD
present in the view layer) and a single variant (default the first; pass `variant` to
pick another, e.g. 'c') so each download yields one clean, scatter-ready model.

Same normalization as spike/import_gltf.py (recenter footprint to XY origin, base to
z=0, optional uniform scale, pack textures, alpha->MASK node wiring for the glTF
exporter) but the source is a native .blend whose foliage materials already wire
their opacity map -- so the alpha->MASK pattern triggers automatically and leaves
export with alphaMode=MASK (no separate alpha map to hunt for). See the foliage memory
note [[blender42-gltf-mask-foliage]] and ASSET_REGISTRY.md.
"""
import re
import sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
out_blend = argv[0]
extra_scale = float(argv[1]) if len(argv) > 1 else 1.0
want_variant = argv[2] if len(argv) > 2 and argv[2] not in ("-", "") else None
# Target LOD: an int (use that _LODn level), or "-"/absent = highest detail available.
want_lod = int(argv[3]) if len(argv) > 3 and argv[3] not in ("-", "") else None

scene_coll = bpy.context.scene.collection
# Consider ALL mesh objects in the file (Poly Haven links only one LOD set to the view
# layer, but ships LOD0..LOD3 in data); link any we may pick so view-layer ops work.
all_meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not all_meshes:
    raise SystemExit("no mesh objects in .blend")

# Keep a single LOD. Default = lowest-numbered _LODn present (highest detail);
# pass want_lod to trade quality for size (LOD1/2 are far lighter for trees).
lod_re = re.compile(r"_LOD(\d+)$")
lods = sorted({int(m.group(1)) for o in all_meshes if (m := lod_re.search(o.name))})
if lods:
    keep_lod = want_lod if (want_lod in lods) else lods[0]
    vl_meshes = [o for o in all_meshes
                 if (m := lod_re.search(o.name)) and int(m.group(1)) == keep_lod]
    print(f"LODS {lods} -> keeping LOD{keep_lod}")
else:
    vl_meshes = all_meshes
# Ensure the kept objects are linked into the active view layer (some LODs aren't).
for o in vl_meshes:
    if o.name not in bpy.context.view_layer.objects:
        try:
            scene_coll.objects.link(o)
        except RuntimeError:
            pass

# Keep a single variant for "kit" assets: names like <base>_<letter>_LOD<n>.
var_re = re.compile(r"_([a-z])_LOD\d+$")
variants = sorted({m.group(1) for o in vl_meshes if (m := var_re.search(o.name))})
if variants:
    pick = want_variant if (want_variant in variants) else variants[0]
    vl_meshes = [o for o in vl_meshes
                 if (m := var_re.search(o.name)) and m.group(1) == pick]
    print(f"KIT_VARIANTS {variants} -> picked {pick!r}")

keep = set(o.name for o in vl_meshes)
# Drop everything we are not keeping (other LODs, other variants, helper objects).
for o in list(bpy.data.objects):
    if o.name not in keep:
        bpy.data.objects.remove(o, do_unlink=True)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no mesh objects after LOD/variant selection")

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

# alpha->MASK wiring: for any material whose BSDF Alpha is linked (foliage opacity),
# splice Math:Greater-Than(0.5) before BSDF.Alpha so Blender 4.2's glTF exporter
# writes alphaMode=MASK. Materials with no alpha link are forced OPAQUE.
for m in bpy.data.materials:
    if not m.use_nodes or not m.node_tree:
        continue
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        continue
    ain = bsdf.inputs["Alpha"]
    if not ain.is_linked:
        m.blend_method = "OPAQUE"
        continue
    src = ain.links[0].from_socket
    if not (src.node.type == "MATH" and src.node.operation == "GREATER_THAN"):
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

try:
    bpy.ops.file.pack_all()
except Exception as e:
    print("pack_all warn:", e)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print("SAVED", out_blend)
