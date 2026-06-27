# Forest3D integration spike — briefing for the spike agent

You are running a **time-boxed, throwaway spike** (target: a few hours, not days). The
goal is to **de-risk** adopting [Forest3D](https://github.com/unitsSpaceLab/Forest3D) as a
procedural off-road world generator for a separate ROS 2 robotics project, **without
touching that project's repo**. You work only here in `~/GitStuff/Forest3D` (this clone)
and a scratch output dir. Your deliverable is a **written findings report**, not
production code.

Forest3D is already cloned here (`main`, commit `5c3d331`). Branches of note:
`feature/terrain-types-refactor` (terrain textures) and `IFIT-2026` (terramechanics).

---

## 1. The consuming project (context you need, but must NOT modify)

A sensor-fusion / GPS-denied-localization portfolio project ("AutonomyTests") at
`~/GitStuff/AutonomyTests` (also bind-mounted at `~/backup/GitStuff/AutonomyTests`).
**Treat it as READ-ONLY reference.** Relevant facts:

- **Stack:** ROS 2 **Jazzy** + Gazebo **Harmonic** (gz-sim 8.x, the REP-2001 pairing),
  all in Docker. A Clearpath **Husky A200** (skid-steer UGV) is spawned via `clearpath_gz`
  into a world called `pipeline`. Sensors on the robot: stereo OAK-D-Lite camera, Ouster
  OS1 lidar, Microstrain IMU, SwiftNav GPS.
- **What it needs from a world:** it runs **stereo VIO** (OpenVINS), will run **lidar
  odometry** (KISS-ICP) next, and a **GPS-denied** experiment that depends on a working
  `NavSat`/GPS — so the world must carry the right gz **system plugins** and
  `<spherical_coordinates>` (see §4). A bare terrain mesh is **not** enough.
- **Why Forest3D:** the current single hand-made `pipeline` world is unrealistic for
  off-road. We want **procedural, randomizable** off-road terrain (forests, rocks, slopes)
  to test VIO/lidar/GPS robustness across many worlds — ideally **seeded** so a failure
  reproduces.

Reference files in AutonomyTests you may READ (do not edit):
- `docker/Dockerfile.sim` — how they build the sim image; **contains the EGL fix in §5**.
- `docs/sim-debugging-notes.md` "#8" — the headless-render blank-camera saga (read it).
- `edge_sensor_fusion_project_PLAN.md` §17.2 — documented Gazebo/ros_gz walls.
- `scripts/deploy.sh` (`m3-smoke`) — their render/feature regression gate idea.

---

## 2. Spike goal & success criteria

**One sentence:** prove (or disprove) that Forest3D can generate an off-road world that
loads in **gz Harmonic headless on this machine** and can host a robot with **working
camera + lidar + GPS**, and surface every integration cost before the team commits.

Tiered deliverables — get as far down as time allows, **report what you reach**:

1. **MUST — does it even run?** Build/install Forest3D (Docker path preferred, see README
   §Quick Start), and generate **one** world end-to-end (`terrain` → `convert` → `generate`).
   Capture: build time, image size, commands that worked, every error + fix.
2. **MUST — load in gz Harmonic headless** and confirm it **renders on the GPU** (a camera
   sensor in the world returns a **non-blank** frame). This is where the EGL gotcha (§5)
   will bite — apply the fix proactively.
3. **SHOULD — the "world-shell" merge (§4).** Get the generated terrain+vegetation into a
   world that also has the required gz system plugins + `<spherical_coordinates>`, load it,
   and confirm a `gpu_lidar` gets returns off the terrain/trees and a `navsat` sensor emits
   a fix. (You can use a minimal standalone robot/sensor SDF — you do NOT need the Husky.)
4. **STRETCH — answer the open questions (§3)** with evidence.

You do **not** need to spawn the actual Husky or wire ROS 2 fusion. A minimal gz sensor
test (camera + lidar + navsat in the generated world) is enough to prove host-ability.

---

## 3. Open questions to settle (these are the decision inputs — answer with evidence)

| # | Question | Why it matters | How to check |
|---|----------|----------------|--------------|
| Q1 | **Is there a SEED** for reproducible placement? If not, how hard to add (it uses clustering / `np.random`)? | "Reproducibility is the product" — randomized worlds are useless for debugging if a failure can't be reproduced. | grep `src/forest3d` for `seed`/`random`/`np.random`; try generating twice — identical output? |
| Q2 | **License truth.** Repo metadata says **AGPL-3.0**; README badge says **MIT**. Which is in the `LICENSE` file? | AGPL on *offline world-gen tooling* is lower-risk than in a runtime spine, but it must be known before depending on it. | read `LICENSE`; note any per-file headers; note asset licenses too. |
| Q3 | **Footprint.** Docker image size + size of one generated world (terrain mesh + glTF models). | The consuming project has a ~60 GB disk-frugal policy; worlds may need generate→use→prune. | `docker images`, `du -sh` the output world dir. |
| Q4 | **Assets.** `Blender-Assets/{tree,rock,bush,grass,soil}` are empty `.gitkeep`. Does `generate` work with **no** assets (terrain only)? What CC0 assets slot in cleanly? | Forest3D is BYO-assets — a real adoption cost. Need to know the minimum viable path. | try generate with bundled DEM only; try one free CC0 tree `.blend`. |
| Q5 | **gz version match.** Does Forest3D's Docker use the **same gz Harmonic (gz-sim 8.x)** as Jazzy? A mismatch = SDF/plugin incompatibility. | The world's plugin `filename=`s (`libgz-sim-*-system.so`) are version-bound. | `gz sim --version` in their image; check the Dockerfile base. |
| Q6 | **Output format.** Exact `.world` structure: SDF version, does it emit `<scene>`/`<plugin>`/physics, or just terrain+models? | Determines the merge strategy in §4 (graft-into-shell vs include-into-shell). | inspect the generated `worlds/*.world`. |
| Q7 | **Texture randomization.** `texture_blend` knob + the `feature/terrain-types-refactor` branch — can terrain/material textures be varied? | The team explicitly wants texture randomization too. | read the config schema + that branch's README/diff. |

---

## 4. The world-shell (the critical integration artifact)

A Forest3D `.world` will almost certainly be terrain + vegetation **only**. To host the
consuming project's robot, the world MUST also contain these gz system plugins,
`<spherical_coordinates>`, scene, light, and physics — copied verbatim from their working
`pipeline` world (gz Harmonic / Jazzy). **This block is the "shell"**; the spike should get
Forest3D's terrain+models *into* a world that has it (either graft Forest3D's `<model>`s
into this shell, or `<include>` them):

```xml
<?xml version='1.0' encoding='ASCII'?>
<sdf version='1.4'>
  <world name='forest_spike'>
    <physics type='ode'>
      <max_step_size>0.003</max_step_size>
      <real_time_factor>1.0</real_time_factor>
      <real_time_update_rate>1000</real_time_update_rate>
      <gravity>0 0 -9.8</gravity>
    </physics>
    <!-- REQUIRED system plugins (filenames are gz-sim 8.x / Harmonic-bound) -->
    <plugin name='gz::sim::systems::Physics'         filename='libgz-sim-physics-system.so'/>
    <plugin name='gz::sim::systems::UserCommands'    filename='libgz-sim-user-commands-system.so'/>
    <plugin name='gz::sim::systems::SceneBroadcaster' filename='libgz-sim-scene-broadcaster-system.so'/>
    <plugin name="gz::sim::systems::Sensors"         filename="libgz-sim-sensors-system.so">
      <render_engine>ogre2</render_engine>   <!-- cameras/lidar need this -->
    </plugin>
    <plugin name="gz::sim::systems::Imu"    filename="libgz-sim-imu-system.so"/>
    <plugin name="gz::sim::systems::NavSat" filename="libgz-sim-navsat-system.so"/>

    <scene>
      <ambient>1 1 1 1</ambient>
      <background>0.3 0.7 0.9 1</background>
      <grid>false</grid>
      <sky><clouds><speed>12</speed></clouds></sky>
      <shadows>0</shadows>
    </scene>
    <light name='sun' type='directional'>
      <cast_shadows>0</cast_shadows>
      <pose>0 0 10 0 -0 0</pose>
      <diffuse>1.0 1.0 1.0 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.5 -1.0</direction>
    </light>

    <!-- REQUIRED for GPS/NavSat: sets the world's lat/lon origin -->
    <spherical_coordinates>
      <latitude_deg>57.0271155</latitude_deg>
      <longitude_deg>-115.426770</longitude_deg>
      <elevation>600</elevation>
      <heading_deg>0</heading_deg>
    </spherical_coordinates>

    <!-- >>> Forest3D's generated terrain + placed models go HERE (graft or <include>) <<< -->

  </world>
</sdf>
```

**Decide & report which merge strategy is cleaner:** (a) graft Forest3D's `<model>` blocks
into this shell, or (b) keep Forest3D's models as separate model dirs and `<include>` them.
Note any path/`<uri>` rewrites needed (Forest3D may use absolute paths or a `model://` that
needs `GZ_SIM_RESOURCE_PATH` set).

---

## 5. Gotchas you will hit (saving you the rediscovery — these are hard-won)

1. **Headless gz cameras render BLACK/blank under EGL unless the NVIDIA EGL vendor ICD
   exists.** ogre2 silently falls back to **llvmpipe (software)** — `GL_RENDERER=llvmpipe`,
   "Texture memory budget exceeded", uniform-colour frames. `NVIDIA_DRIVER_CAPABILITIES=all`
   is necessary but **NOT sufficient**. The fix (do this in Forest3D's container too):
   ```bash
   mkdir -p /usr/share/glvnd/egl_vendor.d
   printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' \
     > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
   ```
   **Always verify `GL_RENDERER` is `NVIDIA...`, not `llvmpipe`, before trusting any frame.**
   Full saga: `~/GitStuff/AutonomyTests/docs/sim-debugging-notes.md` "#8". Run the container
   with `--gpus all` (or nvidia runtime) + `-e NVIDIA_DRIVER_CAPABILITIES=all`.
2. **A "blank camera" can masquerade as the world's fault.** If a frame is uniform-colour,
   check `GL_RENDERER` and the raw frame's pixel std-dev FIRST — don't assume the terrain is
   untextured. (This bit the consuming project for days.)
3. **gz `gpu_lidar` has no per-point timestamps** — irrelevant for the spike (you just need
   returns), but the consuming project's lidar odometry cares; just confirm the lidar gets
   **non-zero returns** off the terrain/trees.
4. **Plugin `filename=` is version-bound.** If Forest3D's gz ≠ gz-sim 8.x, the shell's
   `libgz-sim-*-system.so` names may differ → load errors. That's Q5; flag it loudly.
5. **Host machine:** hybrid-GPU laptop with an NVIDIA RTX (the project verified the full
   stack here). Use `mamba`, not `conda`, if you need a Python env (project convention).

---

## 6. Suggested sequence

1. Read this whole brief + skim AutonomyTests `sim-debugging-notes.md` #8.
2. Q2/Q4/Q6 are **free** (read `LICENSE`, the empty asset dirs, the configs) — do them first.
3. Build the Forest3D Docker image; record size + time (Q3, Q5).
4. Generate one world from the **bundled DEM** (`dem/terrain.tif`) — terrain-only first
   (Q4), then with one CC0 tree asset if time permits.
5. Inspect the output `.world` (Q6). Apply the EGL fix (§5). Load it headless in gz; prove
   a camera renders non-blank on the GPU and (stretch) a lidar returns hits.
6. Attempt the world-shell merge (§4); load the merged world the same way.
7. Settle Q1 (seed) + Q7 (textures) by reading source/branches.
8. Write the report (§7).

---

## 7. Report back (the deliverable)

Write `~/GitStuff/Forest3D/SPIKE_FINDINGS.md` (here, NOT in AutonomyTests) with:

- **Verdict:** can Forest3D realistically host the consuming project's robot in gz Harmonic?
  (yes / yes-with-work / no — and the single biggest blocker).
- **Each open question Q1–Q7 answered** with evidence (commands, sizes, file excerpts).
- **The merge recipe** that worked (or where it stuck), and which strategy (graft vs include).
- **Effort estimate** to turn this into a `worldgen/` capability in the consuming project
  (small / medium / large), and the top 3 risks.
- **Artifacts:** the commands you ran, the generated world path, any screenshots of a
  rendered frame proving GPU render + non-blank terrain.

Keep AutonomyTests pristine — all spike artifacts live under `~/GitStuff/Forest3D/`.
