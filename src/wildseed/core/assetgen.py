"""Procedural Blender asset generation (rocks, boulders, trees, bushes, grass).

Instead of fetching artist-made CC0 assets, synthesize them: every asset is a
seeded parametric build (displaced icospheres, tapered cones, hand-built blade
meshes) with solid-colour Principled BSDF materials — no textures and no alpha
foliage, which sidesteps the glTF MASK pipeline entirely and keeps meshes
light. Same (kind, seed) -> same .blend content, so generated asset sets are
reproducible like everything else in WildSeed.

Two stages, mirroring the existing pipeline:
1. :func:`generate_blends` runs ONE headless Blender process that builds and
   saves N .blend files (origin at the trunk base / ground plane, real-world
   metres, transforms applied — i.e. already "normalized").
2. :func:`convert_assets` feeds them to the existing
   :class:`~wildseed.core.converter.AssetExporter` (visual decimation off —
   the meshes are born low-poly) with per-category collision strategies.

Combined with ``wildseed randomize`` (texture DR) this gives fully synthetic,
infinitely variable scene content for domain randomization.
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("wildseed.assetgen")

# kind -> WildSeed placement category
KIND_CATEGORY: Dict[str, str] = {
    "rock": "rock",
    "boulder": "rock",
    "tree": "tree",
    "conifer": "tree",
    "bush": "bush",
    "grass": "grass",
}
KINDS = tuple(KIND_CATEGORY)


# --------------------------------------------------------------------------- #
# The Blender-side script. %%SPECS%% is replaced by a JSON list of
# {kind, seed, out} build orders; one headless Blender run builds them all.
# Determinism: geometry uses random.Random(seed) + mathutils.noise (Perlin,
# a pure function of position) sampled at seeded offsets.
# --------------------------------------------------------------------------- #
_BLENDER_SCRIPT = r'''
import colorsys
import json
import math
import random

import bpy
from mathutils import Matrix, Vector, noise

SPECS = json.loads("""%%SPECS%%""")


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material(name, h, s, v, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(s, 1.0)), max(0.0, min(v, 1.0)))
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def fractal(p, off, octaves=3):
    n, amp, freq, tot = 0.0, 1.0, 1.0, 0.0
    for _ in range(octaves):
        n += amp * noise.noise(p * freq + off)
        tot += amp
        amp *= 0.5
        freq *= 2.0
    return n / tot


def blob(rng, radius, roughness, subdiv=3, aniso=(1, 1, 1), location=(0, 0, 0)):
    """Noise-displaced icosphere: the workhorse for rocks and canopies."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=radius)
    obj = bpy.context.object
    off = Vector((rng.uniform(-100, 100) for _ in range(3)))
    for vtx in obj.data.vertices:
        p = vtx.co.copy()
        vtx.co = p * (1.0 + roughness * fractal(p * (1.5 / radius), off))
    obj.scale = aniso
    obj.location = location
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def drop_to_ground(objs, bury=0.0):
    """Shift everything so the lowest vertex sits at z = -bury."""
    zmin = min((o.matrix_world @ v.co).z for o in objs for v in o.data.vertices)
    for o in objs:
        o.location.z -= zmin + bury
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def build_rock(rng, big=False):
    size = rng.uniform(1.5, 3.5) if big else rng.uniform(0.3, 1.0)
    aniso = (rng.uniform(0.7, 1.5), rng.uniform(0.7, 1.5), rng.uniform(0.55, 1.1))
    obj = blob(rng, size / 2.0, rng.uniform(0.25, 0.5), subdiv=3, aniso=aniso)
    mat = make_material("rock", rng.uniform(0.04, 0.13), rng.uniform(0.03, 0.3),
                        rng.uniform(0.18, 0.55), rng.uniform(0.85, 1.0))
    assign(obj, mat)
    drop_to_ground([obj], bury=0.12 * size)


def _tapered_trunk(rng, h, r0, mat):
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=r0, radius2=r0 * 0.35,
                                    depth=h, location=(0, 0, h / 2.0))
    trunk = bpy.context.object
    assign(trunk, mat)
    return trunk


def build_tree(rng):
    h = rng.uniform(4.0, 9.0)
    r0 = h * rng.uniform(0.018, 0.035)
    bark = make_material("bark", rng.uniform(0.05, 0.1), rng.uniform(0.3, 0.6),
                         rng.uniform(0.12, 0.3), 0.95)
    leaf = make_material("canopy", rng.uniform(0.2, 0.36), rng.uniform(0.45, 0.8),
                         rng.uniform(0.15, 0.45), 0.9)
    objs = [_tapered_trunk(rng, h, r0, bark)]
    tips = [Vector((0, 0, h * 0.98))]
    for _ in range(rng.randint(2, 5)):
        length = h * rng.uniform(0.25, 0.45)
        zb = h * rng.uniform(0.55, 0.85)
        yaw = rng.uniform(0, 2 * math.pi)
        pitch = rng.uniform(math.radians(35), math.radians(70))
        rot = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(pitch, 4, 'Y')
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=r0 * 0.45,
                                        radius2=r0 * 0.15, depth=length)
        br = bpy.context.object
        br.matrix_world = (Matrix.Translation((0, 0, zb)) @ rot
                           @ Matrix.Translation((0, 0, length / 2.0)))
        assign(br, bark)
        objs.append(br)
        tips.append(Matrix.Translation((0, 0, zb)) @ rot @ Vector((0, 0, length)))
    # crown: a blob per branch tip PLUS a cluster hugging the upper trunk,
    # so the canopy reads full rather than a bare pole with pompoms.
    canopy = h * rng.uniform(0.13, 0.2)
    for _ in range(rng.randint(2, 4)):
        ang = rng.uniform(0, 2 * math.pi)
        rad = canopy * rng.uniform(0.0, 0.7)
        tips.append(Vector((rad * math.cos(ang), rad * math.sin(ang),
                            h * rng.uniform(0.72, 0.95))))
    for tip in tips:
        r = canopy * rng.uniform(0.8, 1.4)
        objs.append(blob(rng, r, rng.uniform(0.3, 0.5), subdiv=2,
                         aniso=(1, 1, rng.uniform(0.65, 0.9)),
                         location=(tip.x, tip.y, tip.z)))
        assign(objs[-1], leaf)
    drop_to_ground(objs)


def build_conifer(rng):
    h = rng.uniform(5.0, 12.0)
    r0 = h * rng.uniform(0.022, 0.04)
    bark = make_material("bark", rng.uniform(0.04, 0.09), rng.uniform(0.3, 0.6),
                         rng.uniform(0.1, 0.25), 0.95)
    needle = make_material("needles", rng.uniform(0.28, 0.42), rng.uniform(0.4, 0.75),
                           rng.uniform(0.08, 0.3), 0.92)
    objs = [_tapered_trunk(rng, h, r0, bark)]
    n = rng.randint(3, 6)
    base_r = h * rng.uniform(0.14, 0.22)
    z0 = h * rng.uniform(0.18, 0.3)
    spacing = (h * 0.95 - z0) / max(n - 1, 1)
    for i in range(n):
        t = i / max(n - 1, 1)
        r = base_r * (1.0 - 0.75 * t)
        # each tier must overlap the next: depth > spacing, or daylight shows
        # between the cones (seen in the first contact-sheet render)
        depth = spacing * rng.uniform(1.4, 1.8)
        z = z0 + (h * 0.95 - z0) * t
        bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=r, radius2=r * 0.06,
                                        depth=depth, location=(0, 0, z + depth / 2.0))
        cone = bpy.context.object
        assign(cone, needle)
        objs.append(cone)
    drop_to_ground(objs)


def build_bush(rng):
    leaf = make_material("bush", rng.uniform(0.16, 0.34), rng.uniform(0.35, 0.75),
                         rng.uniform(0.12, 0.4), 0.9)
    size = rng.uniform(0.5, 1.2)
    objs = []
    for _ in range(rng.randint(3, 6)):
        r = size * rng.uniform(0.25, 0.5)
        loc = (rng.uniform(-0.3, 0.3) * size, rng.uniform(-0.3, 0.3) * size,
               r * rng.uniform(0.6, 0.9))
        objs.append(blob(rng, r, rng.uniform(0.3, 0.55), subdiv=2,
                         aniso=(1, 1, rng.uniform(0.7, 1.0)), location=loc))
        assign(objs[-1], leaf)
    drop_to_ground(objs)


def build_grass(rng):
    verts, faces = [], []
    for _ in range(rng.randint(10, 25)):
        ang = rng.uniform(0, 2 * math.pi)
        base = Vector((rng.uniform(0, 0.22) * math.cos(ang),
                       rng.uniform(0, 0.22) * math.sin(ang), 0))
        height = rng.uniform(0.15, 0.5)
        width = rng.uniform(0.012, 0.03)
        lean_dir = Vector((math.cos(rng.uniform(0, 2 * math.pi)),
                           math.sin(rng.uniform(0, 2 * math.pi)), 0))
        bend = height * rng.uniform(0.15, 0.5)
        perp = Vector((-lean_dir.y, lean_dir.x, 0))
        segs = 3
        i0 = len(verts)
        for s in range(segs + 1):
            t = s / segs
            centre = base + lean_dir * bend * t * t + Vector((0, 0, height * t))
            if s == segs:
                verts.append(centre)  # apex
            else:
                wh = width * (1.0 - 0.8 * t) / 2.0
                verts.append(centre - perp * wh)
                verts.append(centre + perp * wh)
        for s in range(segs - 1):
            a = i0 + 2 * s
            faces.append((a, a + 1, a + 3, a + 2))
        a = i0 + 2 * (segs - 1)
        faces.append((a, a + 1, a + 2))
    me = bpy.data.meshes.new("grass")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    obj = bpy.data.objects.new("grass", me)
    bpy.context.collection.objects.link(obj)
    mat = make_material("blade", rng.uniform(0.18, 0.3), rng.uniform(0.45, 0.85),
                        rng.uniform(0.2, 0.55), 0.85)
    mat.use_backface_culling = False  # glTF doubleSided: blades visible both ways
    assign(obj, mat)


BUILDERS = {
    "rock": lambda rng: build_rock(rng, big=False),
    "boulder": lambda rng: build_rock(rng, big=True),
    "tree": build_tree,
    "conifer": build_conifer,
    "bush": build_bush,
    "grass": build_grass,
}

for spec in SPECS:
    reset_scene()
    rng = random.Random(spec["seed"])
    BUILDERS[spec["kind"]](rng)
    bpy.ops.wm.save_as_mainfile(filepath=spec["out"])
    print("ASSETGEN_SAVED:", spec["out"])
'''


def generate_blends(
    blender_path: Path,
    out_dir: Path,
    kind: str,
    count: int,
    seed: int = 0,
    timeout: int = 600,
) -> List[Path]:
    """Build ``count`` seeded .blend assets of one kind in a single Blender run.

    Asset i gets its own child seed (seed*1000 + i namespaced by kind via
    hashing the kind string) so sets are extensible: asking for count=5 later
    reproduces the first 3 of a count=3 run byte-for-content.
    """
    if kind not in KIND_CATEGORY:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = []
    for i in range(count):
        name = f"gen_{kind}_s{seed}_{i:02d}"
        # stable child seed: arithmetic namespaced by the kind's index (python's
        # hash() is salted per-process, so it can't be used for this).
        child_seed = int(seed) * 1000 + KINDS.index(kind) * 101 + i
        specs.append({"kind": kind, "seed": child_seed,
                      "out": str(out_dir / f"{name}.blend")})

    script = _BLENDER_SCRIPT.replace("%%SPECS%%", json.dumps(specs))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name
    try:
        result = subprocess.run(
            [str(blender_path), "--background", "--python", script_path],
            capture_output=True, text=True, timeout=timeout,
        )
        made = [Path(s["out"]) for s in specs]
        missing = [p for p in made if not p.exists()]
        if missing:
            logger.error(f"assetgen stdout tail: {result.stdout[-2000:]}")
            logger.error(f"assetgen stderr tail: {result.stderr[-2000:]}")
            raise RuntimeError(f"Blender did not produce: {[str(p) for p in missing]}")
    finally:
        os.unlink(script_path)
    logger.info(f"generated {len(made)} {kind} blend(s) -> {out_dir}")
    return made


def converter_config():
    """Conversion parameters for generated assets: keep full (already low-poly)
    visual detail; primitive collisions per category."""
    from wildseed.config.schema import BlenderConfig, CategoryConfig
    return BlenderConfig(
        visual_decimation=1.0,
        categories={
            "rock": CategoryConfig(visual_decimation=1.0, collision_strategy="convex_hull"),
            "tree": CategoryConfig(visual_decimation=1.0, collision_strategy="trunk_cylinder"),
            "bush": CategoryConfig(visual_decimation=1.0, collision_strategy="trunk_cylinder"),
            "grass": CategoryConfig(visual_decimation=1.0, collision_strategy="box"),
        },
    )


def convert_assets(blender_path: Path, blends: List[Path], kind: str,
                   models_dir: Path) -> List[Path]:
    """Convert generated .blend files to Gazebo models via the standard exporter."""
    from wildseed.core.converter import AssetExporter
    category = KIND_CATEGORY[kind]
    exporter = AssetExporter(blender_path=blender_path, output_path=Path(models_dir),
                             config=converter_config())
    out = []
    for blend in blends:
        out.append(exporter.process_asset(Path(blend), category))
    return out
