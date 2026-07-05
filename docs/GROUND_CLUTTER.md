# Ground clutter / relief for VIO + LIO (ground vehicles)

Goal: make WildSeed terrain yield good, non-ambiguous features for a **ground vehicle**
running VIO (camera) and LIO (LIDAR) **without** dragging the sim's real-time factor (RTF)
down. Deliver switchable options — (c) steered scatter and (d) geometric relief — each judged
on **feature-gain per RTF-cost**.

Companion docs: `docs/VIO_BENCH.md` (data-association benchmark method), `tools/README.md`
(VIO tools table). Plan of record: `scratchpad/PLAN_ground_clutter.md`.

All renders run in the GPU container (`wildseed:egl`); helper: `scratchpad/dgpu.sh '<CMD>'`.

---

## Binding constraint — RTF

When RTF sags (trouble at ≲0.3), ROS 2 nodes advance internal timers on `sim_time` but DDS
delivery is wall-clock → desync → message-filter/TF timeouts → failures. **Keep RTF ≥ ~0.5.**
Every clutter/relief choice is judged by (VIO+LIDAR feature gain) / (RTF cost), measured under
load (sensors rendering + physics stepping), never assumed. Corollaries:
- Must be **real geometry**: LIDAR is blind to baked albedo/normal maps — texture-only clutter
  is out (fails for LIO).
- Instance **count** is the enemy; single-mesh geometry is cheap.
- Primary target = ground vehicle (~2 m eye); drone is secondary.

---

## P1 — Ground-vehicle failure baseline (DONE)

The benchmark (`tools/vio_bench.py`) renders the real rig camera (640×480, 57° FOV) along a
canonical translate-+X + yaw trajectory, matches ORB between consecutive frames and reports
`ratio_reject` (ambiguity), `inlier_ratio` (E-matrix RANSAC), `inliers/pair` (reliable
correspondences) and a verdict. Prior work (§2.6 of the plan) had never shown bare ground
*failing* at a ground-robot pose — every tested scene stayed GOOD, carried by landmarks or by
feature-rich hilly/patchy terrain.

**Result — a realistic ground-robot failure exists, and it is reached by removing the three
things that were secretly carrying VIO:** terrain relief (horizon parallax), ground texture
richness, and slow motion. Escalation gradient, all **bare** (`generate` with explicit zeros
`{"tree":0,"rock":0,"bush":0,"grass":0,"sand":0}`), camera at **2 m AGL**:

| scene | pose | verdict | inliers/pair | ratio_reject | inlier_ratio |
|---|---|---|---|---|---|
| hilly + patchy desert | pitch 0.5, step 0.6 m/fr | **GOOD** | 341 | 0.71 | 0.78 |
| flat + uniform grassland | pitch 0.35, step 1.2 m/fr | **MARGINAL** | 106 | 0.89 | 0.71 |
| **flat + uniform grassland** | **pitch 0.35, step 2.0 m/fr, yaw ±10°** | **ALIASING RISK** | **20** | **0.98** | **0.60** |

The last row is the **failure baseline** both options must beat: realistic fast driving
(2 m/frame ≈ brisk ground speed) over flat, smooth, landmark-free ground. `ratio_reject 0.98`
(near-total descriptor ambiguity) with only **20** surviving inliers/pair (< 40 = starvation).
Viz: matches cling to a thin near-field ground band; the smooth mid/far field is blank.

Reproduce (in container):
```
python3 -m wildseed.cli.main terraingen --preset flat --seed 3 --size 192 --pixel 1.6 -o dem/flat.tif
python3 -m wildseed.cli.main terrain --dem dem/flat.tif
python3 -m wildseed.cli.main ground --mode uniform --biome grassland --seed 7 --res 4096
python3 -m wildseed.cli.main generate --density '{"tree":0,"rock":0,"bush":0,"grass":0,"sand":0}' --seed 7
python3 tools/vio_bench.py --tag p1_flatunif_fast --agl 2 --pitch 0.35 --step 2.0 --yaw-amp-deg 10 --region full --viz
```
Outputs: `frames/vio_bench_p1_flatunif_fast.json`, `..._matches.png`.

**This flat + uniform-grassland scene is the fixed test bed for options (c) and (d):** flat
terrain is exactly where scatter and relief must prove their worth (no horizon to lean on).

---

## P2 — RTF-under-load harness (in progress)

`tools/vio_bench.py` renders one-shot (no RTF signal). P2 adds a real-time run: the rig
(camera 10 Hz + gpu_lidar 16 ch/360/10 Hz, from `core/rig.py`) in a world with clutter/relief
+ physics stepping, logging gz RTF. Output: RTF vs scene complexity — the cost gauge for
options (c)/(d).

_(numbers to follow)_
