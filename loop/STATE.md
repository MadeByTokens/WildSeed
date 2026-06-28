# Overnight autonomous session — STATE

Started Sat 2026-06-27 21:45 EDT. User away until ~morning. Work autonomously,
commit every increment, keep this file current so any crash resumes statelessly.
Branch `feature/realism-convert-fork`. DO NOT push.

## Goal (verbatim intent)
1. Document + commit current state.
2. Per-basin water levels (lakeland: each basin holds water at its own level).
3. Enough assets (trees/rocks/...) to build **5 demo scenarios**, realistic,
   **≥2 with snow**. Collect images, document everything, write an easy tutorial
   (how to use + how to randomize). Licenses: don't care for use (repo will be
   FOSS) but **save credit info** for the docs.

## Plan / progress
- [ ] PHASE 1 — docs/TERRAIN_GENERATOR.md + this STATE + commit
- [ ] PHASE 2 — per-basin water: extend write_water_model (name/center/size),
      `forest3d ground --auto-water` reads dem/<name>.lakes.json, places one plane
      per basin at its own suggested level. Test + render lakeland. Commit.
- [ ] PHASE 3a — acquire realistic CC0 assets (time-box ~2.5h): 2 rocks (easy,
      single-material like namaqualand), attempt 1-2 trees incl a conifer for snow,
      attempt 1 shrub. Convert via `forest3d convert` + normalize_island_tree.py
      pattern. Record source+license in spike/ASSET_REGISTRY.md for credits.
      FALLBACK if foliage conversion fails: use island_tree_01 everywhere + snow
      ground for snow scenes. Curate models/ to realistic-only (move primitives to
      models/_primitives_aside/ so generate doesn't place them).
- [ ] PHASE 3b — 5 scenarios (terrain preset + biome + seeded placement + cameras):
      e.g. (1) temperate rolling forest (hilly+grassland), (2) arid (flat/valley+
      desert), (3) lakeland wetland (lakeland+grassland+per-basin water),
      (4) ALPINE SNOW (mountainous+snow), (5) WINTER forest (hilly/valley+snow).
      Render hero image(s) each. Compose gallery.
- [ ] PHASE 3c — docs/SCENARIOS.md + docs/TUTORIAL.md (install/docker, pipeline,
      randomization via --seed, per-scenario recipes). Update ASSET_REGISTRY credits.
- [ ] PHASE 3d — send gallery + tutorial to user.

## Key facts / gotchas (so recovery needs no re-derivation)
- Render recipe: docker run --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all
  -e PYTHONPATH=/workspace/src -e GZ_SIM_RESOURCE_PATH=/workspace/models
  -v "$PWD:/workspace" --entrypoint bash forest3d:egl -c '...'. Verify GL_VENDOR
  NVIDIA in ~/.gz/rendering/ogre2.log.
- Pipeline: forest3d terraingen -> terrain --dem -> ground --mode patchy|uniform
  --biome -> generate --density '{...}' --seed. terrain overwrites models/ground.
- generate picks RANDOM variant per category from models/<cat>/* subdirs -> keep
  only realistic variants in models/ for realistic scenes.
- Scene builder: spike/terrain_scene.py (FOREST=1 grafts worlds/forest_world.world
  includes; skips ground/water dup). Cameras: looking DOWN = +pitch.
- terraingen sidecar dem/<name>.lakes.json: [{center_px,center_xy_m,radius_m,
  floor_z,suggested_water_level}]. min==0 metre frame; water plane at absolute Z.
- pytest: pip3 install --quiet pytest; python3 -m pytest tests/ -q -o addopts="".
- models/, worlds/, frames/, dem/synth* are gitignored. spike/*.png + docs/ tracked.

## Done log
(append commit hashes as phases complete)
