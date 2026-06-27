"""Generate simple procedural CC0 vegetation .blend assets for Forest3D.
Run in the Forest3D container's Blender:
  blender --background --python make_assets.py -- <which>
where <which> is 'tree', 'all', or a comma list (tree,rock,bush).
Each asset: fresh empty scene -> meshes with Principled-BSDF Base Color (glTF reads
the node, NOT diffuse_color) -> saved .blend under /workspace/Blender-Assets/<cat>/.
Z-up is preserved by the converter (export_yup=False) so assets stand upright.
"""
import sys
import bpy

BASE = "/workspace/Blender-Assets"


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)  # no default cube rides along


def mat(name, rgb, rough=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = rough
    return m


def assign(obj, m):
    obj.data.materials.clear()
    obj.data.materials.append(m)


def save(cat, name):
    import os
    d = f"{BASE}/{cat}"
    os.makedirs(d, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=f"{d}/{name}.blend")
    print(f"SAVED {d}/{name}.blend")


def tree(name, trunk_h=4.0, trunk_r=0.3, foliage_r=2.2, foliage_h=6.0,
         green=(0.10, 0.40, 0.08), tiers=2):
    reset()
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=trunk_r, depth=trunk_h,
                                        location=(0, 0, trunk_h / 2))
    trunk = bpy.context.active_object
    assign(trunk, mat(f"{name}_bark", (0.25, 0.13, 0.05)))
    gmat = mat(f"{name}_leaf", green)
    # stacked cones -> conifer silhouette, survives heavy decimation
    z = trunk_h
    for i in range(tiers):
        r = foliage_r * (1.0 - 0.28 * i)
        h = foliage_h / tiers * 1.5
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=r, radius2=0.0, depth=h,
                                        location=(0, 0, z + h / 2 - 0.4))
        assign(bpy.context.active_object, gmat)
        z += h * 0.55
    save("tree", name)


def rock(name, r=1.2, seed=1):
    reset()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=(0, 0, r * 0.5))
    o = bpy.context.active_object
    # lumpy: jitter verts deterministically (no RNG import needed)
    for i, v in enumerate(o.data.vertices):
        f = 1.0 + 0.18 * (((i * 37 + seed * 91) % 11) / 11.0 - 0.5)
        v.co *= f
    o.scale = (1.0, 0.8, 0.6)
    assign(o, mat(f"{name}_rock", (0.42, 0.40, 0.38)))
    save("rock", name)


def bush(name, r=0.9, green=(0.12, 0.34, 0.10)):
    reset()
    gmat = mat(f"{name}_bush", green)
    for dx, dy, dz, s in [(0, 0, 0.5, 1.0), (0.6, 0.3, 0.4, 0.7),
                          (-0.5, 0.4, 0.4, 0.7), (0.2, -0.5, 0.4, 0.6)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r * s,
                                              location=(dx, dy, dz))
        assign(bpy.context.active_object, gmat)
    save("bush", name)


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["tree"]
which = argv[0] if argv else "tree"
sel = ["tree", "rock", "bush"] if which == "all" else which.split(",")

if "tree" in sel:
    tree("tree1")
    tree("tree2", trunk_h=5.0, foliage_r=2.6, green=(0.14, 0.45, 0.10), tiers=3)
    tree("tree3", trunk_h=3.0, foliage_r=1.7, green=(0.20, 0.42, 0.12), tiers=2)
if "rock" in sel:
    rock("rock1", r=1.4, seed=3)
    rock("rock2", r=0.9, seed=7)
if "bush" in sel:
    bush("bush1")
    bush("bush2", r=1.1, green=(0.16, 0.38, 0.12))
print("DONE assets:", sel)
