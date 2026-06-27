# Forest3D spike — execution plan

A thin, executable layer over `SPIKE_BRIEF.md`. **The brief stays the source of truth**
for context, success criteria, the world-shell (§4), and gotchas (§5). This file only
pins down the decisions and mechanics the brief left open, so the spike can run without
losing time on the predictable snags. Deliverable is still `SPIKE_FINDINGS.md`.

## Decisions locked
- **Build path: Docker** (README §Quick Start, `docker/Dockerfile`). Reproducible and answers Q5 directly.
- **Plan artifact:** this file (durable, committed).
- **No Husky / no ROS 2.** Minimal gz sensor SDF (camera + gpu_lidar + navsat) only.

## What orientation already settled (don't re-spend time here)
- **Q2 (license):** `LICENSE` = **AGPL-3.0** (verified). README MIT badge (line 11) is stale; README's own License section (line 321) says AGPL-3.0. → **Treat adoption as AGPL-3.0.** Still: note any per-file headers + asset licenses.
- **Q5 (gz version):** Dockerfile `FROM ubuntu:22.04` + installs `gz-harmonic` from OSRF (gz-sim **8.x** = Jazzy's Harmonic pairing). Plugin `.so` names should match the shell. → **Confirm in-image** with `gz sim --version` (expect 8.x); only then trust it.
- **CLI sequence:** `terrain → convert → generate → launch` (README lines 43–48). Real flags:
  - `forest3d terrain --dem ./dem/terrain.tif` → `models/ground/` + SDF
  - `forest3d convert -i ./Blender-Assets -o ./models` → per-category models (no-op while assets empty)
  - `forest3d generate --density '{...}'` → `worlds/forest_world.world`
  - `forest3d launch` → GUI gz (bypass for headless; see render harness)
- **Path gotchas to pre-empt:** repo dir is lowercase `dem/` (README says `./DEM/`); image hardcodes `GZ_SIM_RESOURCE_PATH=/workspace/models` (drives the §4 merge `<uri>` strategy).

## Render-verification harness (define once, reuse for tiers 2 & 3)
The `launch` subcommand is GUI; headless render proof is on us. Procedure inside the container (run with `--gpus all -e NVIDIA_DRIVER_CAPABILITIES=all`, EGL fix from brief §5 applied):
1. **GPU sanity first:** `glxinfo -B | grep -i renderer` (mesa-utils is in the image). Must read **NVIDIA…**, not `llvmpipe`. If llvmpipe → re-apply EGL ICD, re-check. Trust no frame until this passes.
2. **Run headless:** `gz sim -s -r --headless-rendering <world>` (server-only) with a camera sensor + `gz-sim-sensors` (ogre2) in the world.
3. **Grab a frame:** bridge/echo the camera image topic (`gz topic -e -t <cam_topic> -n 1`) or save via an image-saver; compute **pixel std-dev** in a tiny Python snippet (`condalocal` env). std-dev ≈ 0 → blank → fail. Non-trivial std-dev + NVIDIA renderer → **pass**.
4. **Lidar (tier 3):** echo the `gpu_lidar` scan topic; assert **non-zero/finite ranges** hitting terrain/trees.
5. **NavSat (tier 3):** echo the navsat topic; assert a fix is emitted (needs `<spherical_coordinates>` from the shell).

## Per-tier checkpoints, time-box, abort conditions
Total target: a few hours. Checkpoint = update `SPIKE_FINDINGS.md` + (optional) commit before moving on.

| Tier | Goal | Time-box | Abort / fallback |
|------|------|----------|------------------|
| 0 | Free reads: Q2, Q4 setup, Q6 prep; read AutonomyTests notes #8 | done / 20 min | — |
| 1 (MUST) | Docker build + generate **one** terrain-only world (Q3, Q4, Q5) | ~60 min | If build fails after one real fix attempt → record the wall, note local-mamba as fallback, still report. Don't rabbit-hole. |
| 2 (MUST) | Load headless, **GPU non-blank camera frame** (apply EGL fix) | ~60 min | If render stuck: confirm it's GL_RENDERER (llvmpipe) vs world fault per harness step 1 before blaming the world. Capture frame + std-dev either way. |
| 3 (SHOULD) | World-shell merge (§4) + lidar returns + navsat fix | ~45 min | If merge stuck, report **where** + which strategy (graft vs include) was closer. Partial is fine. |
| 4 (STRETCH) | Q1 (seed) + Q7 (texture) by reading `src/forest3d` + `feature/terrain-types-refactor` | leftover | Read-only; safe to truncate. |

## Artifacts (all under `~/GitStuff/Forest3D/`, AutonomyTests stays pristine)
- Generated world: `worlds/forest_world.world` (+ `models/`)
- Merged shell world: `worlds/forest_spike.world` (new)
- Render proof: saved frame PNG + std-dev number + `glxinfo` renderer line
- `SPIKE_FINDINGS.md` — the deliverable (verdict, Q1–Q7, merge recipe, effort estimate, top-3 risks)

## Top open risks going in
1. **EGL/llvmpipe** silent software fallback (brief §5 #1) — highest-probability time sink.
2. **`generate` with zero models** — does it tolerate empty `models/{tree,rock,...}` or hard-fail? (Q4) Decides whether terrain-only is even a path.
3. **Image size vs 60 GB policy** (Q3) — README claims ~2GB; Blender 4.2 + gz-harmonic likely 3–5GB. Measure, don't trust the README.
