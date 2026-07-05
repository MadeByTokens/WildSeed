#!/usr/bin/env python3
"""Option (d2) — gz <heightmap> ground with cm–dm surface relief on a flat, drivable macro.

The mesh path (`terraingen` + `terrain`, option d1) is Nyquist-limited to ≳1.2 m relief, so to
make surface texture it must raise amplitude → slope (un-drivable). A gz `<heightmap>` (Ogre2
Terra: GPU-tessellated + LOD'd render, one static collision surface) carries **cm–dm roughness
on an otherwise-flat surface** — VIO/LIO texture without touching the macro slope — at one-mesh
cost (RTF 1.0 measured at 1025²; see docs/GROUND_CLUTTER.md).

This writes a hi-res heightmap PNG (multi-octave value noise with the LOW frequencies removed,
so there is no macro tilt — pure roughness) + a gz world skinned with the ground texture, then
injects the sensor rig. Measure it with the existing gates:
  python3 tools/heightmap_relief.py --out-world worlds/heightmap_d2.world
  python3 tools/rtf_bench.py    --world heightmap_d2 --tag d2   # RTF (V2)
  python3 tools/lidar_spread.py --world heightmap_d2 --tag d2   # LIO roughness (V3)
  python3 tools/vio_bench.py --heightmap dem/hm_d2.png,60,0.35 --tag d2 --agl 2 --pitch 0.35 \
      --step 2.0 --region full --viz                            # camera VIO (V1)
Run inside wildseed:egl from /workspace.
"""
import argparse
import os
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

WS = os.environ.get("WS", "/workspace")


def fractal(n, seed):
    """Multi-octave value noise, macro-FLAT (low frequencies skipped), normalized 0..1."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((n, n), np.float64)
    total = 0.0
    amp = 1.0
    # start at ~n/64 features (skip the low freqs that would tilt the surface) down to a few px.
    for div in (64, 32, 16, 8, 4):
        f = max(n // div, 2)
        coarse = rng.random((f + 1, f + 1))
        img = np.asarray(Image.fromarray((coarse * 255).astype(np.uint8)).resize(
            (n, n), Image.BICUBIC), np.float64) / 255.0
        acc += amp * img
        total += amp
        amp *= 0.6
    acc /= total
    acc -= acc.min()
    acc /= acc.max()
    return acc


def main():
    ap = argparse.ArgumentParser(description="Option d2: hi-res heightmap relief ground.")
    ap.add_argument("--res", type=int, default=1025, help="Heightmap side (must be 2^n+1).")
    ap.add_argument("--extent", type=float, default=60.0, help="Patch side length, m.")
    ap.add_argument("--relief", type=float, default=0.35, help="Max relief height, m.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out-png", default=f"{WS}/dem/hm_d2.png")
    ap.add_argument("--out-world", default=f"{WS}/worlds/heightmap_d2.world")
    ap.add_argument("--rig-z", type=float, default=2.0, help="Rig height AGL, m.")
    ap.add_argument("--no-rig", action="store_true", help="Skip rig injection (bare world).")
    args = ap.parse_args()

    if (args.res - 1) & (args.res - 2) != 0 and bin(args.res - 1).count("1") != 1:
        print(f"warning: --res {args.res} is not 2^n+1; gz heightmaps require 2^n+1", flush=True)

    os.makedirs(os.path.dirname(args.out_png), exist_ok=True)
    h = fractal(args.res, args.seed)
    Image.fromarray((h * 255).astype(np.uint8), mode="L").save(args.out_png)

    dz = h * args.relief
    px = args.extent / (args.res - 1)
    gy, gx = np.gradient(dz, px)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    print(f"heightmap {args.res}x{args.res} over {args.extent} m ({px*100:.1f} cm/px), "
          f"relief {dz.ptp():.3f} m, mean_slope {slope.mean():.1f} deg, "
          f"p95 {np.percentile(slope,95):.1f} deg", flush=True)

    color = f"file://{WS}/models/ground/texture/ground_Color.png"
    normal = f"file://{WS}/models/ground/texture/ground_NormalGL.png"
    sdf = ET.Element("sdf", version="1.9")
    world = ET.SubElement(sdf, "world", name=os.path.splitext(os.path.basename(args.out_world))[0])
    phys = ET.SubElement(world, "physics", name="1ms", type="ignored")
    dart = ET.SubElement(phys, "dart")
    ET.SubElement(dart, "collision_detector").text = "bullet"  # heightmaps prefer bullet
    ET.SubElement(phys, "max_step_size").text = "0.003"
    ET.SubElement(phys, "real_time_factor").text = "1.0"
    sun = ET.SubElement(world, "light", type="directional", name="sun")
    ET.SubElement(sun, "cast_shadows").text = "true"
    ET.SubElement(sun, "pose").text = "0 0 10 0 0 0"
    ET.SubElement(sun, "diffuse").text = "0.9 0.9 0.9 1"
    ET.SubElement(sun, "specular").text = "0.3 0.3 0.3 1"
    ET.SubElement(sun, "direction").text = "0.4 0.3 -0.86"
    scene = ET.SubElement(world, "scene")
    ET.SubElement(scene, "ambient").text = "0.35 0.37 0.4 1"
    ET.SubElement(scene, "background").text = "0.7 0.8 0.9 1"
    ET.SubElement(scene, "sky")

    model = ET.SubElement(world, "model", name="heightmap_terrain")
    ET.SubElement(model, "static").text = "true"
    link = ET.SubElement(model, "link", name="link")
    for kind in ("collision", "visual"):
        el = ET.SubElement(link, kind, name=kind)
        hm = ET.SubElement(ET.SubElement(el, "geometry"), "heightmap")
        ET.SubElement(hm, "uri").text = f"file://{args.out_png}"
        ET.SubElement(hm, "size").text = f"{args.extent} {args.extent} {args.relief}"
        ET.SubElement(hm, "pos").text = "0 0 0"
        if kind == "visual":
            tex = ET.SubElement(hm, "texture")
            ET.SubElement(tex, "size").text = "2"
            ET.SubElement(tex, "diffuse").text = color
            ET.SubElement(tex, "normal").text = normal
            ET.SubElement(hm, "sampling").text = "2"

    ET.indent(sdf, space="  ")
    ET.ElementTree(sdf).write(args.out_world, encoding="unicode", xml_declaration=True)
    print(f"wrote {args.out_world}", flush=True)

    if not args.no_rig:
        from pathlib import Path
        from wildseed.core.rig import RigConfig, inject_rig_into_world
        inject_rig_into_world(Path(args.out_world), RigConfig(), Path(f"{WS}/models"),
                              rig_pose=(0.0, 0.0, args.rig_z, 0.0, 0.0, 0.0))
        print(f"rig injected at 0,0,{args.rig_z}", flush=True)


if __name__ == "__main__":
    main()
