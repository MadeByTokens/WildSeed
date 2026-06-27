# Procedural Terrain Generator — execution plan (fresh-session handoff)

**Read this top-to-bottom before starting.** It is written to be executed in a clean
context with no memory of the prior sessions. Everything you need is here or in the
files it points to.

---

## 0. Mission

Add a **seeded procedural terrain generator** to Forest3D so we can synthesize varied
landforms — **hills, mounts, valleys, flatlands, basins→mini-lakes, creeks** — instead
of only meshing the one bundled DEM. This is the last missing piece of the
"randomize a whole scenario for VIO/lidar testing" goal: the same `--seed` must give the
same landform, a new seed a new one. It must flow through the *existing, proven*
terrain→ground→placement pipeline **unchanged**.

**Lowest-risk approach (do this): synthesize a GeoTIFF DEM**, then feed it to the
existing `forest3d terrain --dem <synth.tif>`. Nothing downstream changes — the mesh,
UVs, ground compositor, water plane, and seeded placement all already work on any DEM.

---

## 1. Where things stand (context you can trust)

- **Repo:** `/home/ricardodeazambuja/backup/GitStuff/Forest3D`, git remote `origin =
  github.com/ricardodeazambuja/Forest3D` (a fork). **DO NOT push or open PRs.**
- **Branch:** `feature/realism-convert-fork` (keep working here). Latest commit ~`45fc8d4`.
- **Docker image:** `forest3d:egl` (built from `docker/Dockerfile.egl`): Forest3D +
  Blender 4.2.3 + gz Harmonic 8.x + NVIDIA EGL ICD + `numpy<2` (GDAL ABI) + Pillow.
- **GPU render is proven.** Host has an NVIDIA RTX 2070. Always run the container with
  `--gpus all -e NVIDIA_DRIVER_CAPABILITIES=all`. **Verify GL is real**, not llvmpipe:
  `grep -i GL_VENDOR ~/.gz/rendering/ogre2.log` → must say `NVIDIA`.
- **The package is pip-installed (copied) in the image, NOT editable.** To make your
  local `src/` edits take effect, run the CLI with `-e PYTHONPATH=/workspace/src` and
  mount the repo at `/workspace` (`-v "$PWD:/workspace"`). pytest isn't preinstalled:
  `pip3 install --quiet pytest` then `python3 -m pytest tests/ -q -o addopts=""`
  (the repo's pyproject sets `--cov` addopts that break ad-hoc runs).
- **Already shipped on this branch (don't redo):**
  - `core/converter.py` per-category foliage-aware decimation + primitive collision.
  - Hero tree (Poly Haven `island_tree_01`, CC0) + boulder (`namaqualand_boulder_04`).
  - `core/ground.py` + `forest3d ground` CLI: uniform/patchy ground, biomes
    (grassland/desert/gravel/snow), trails + sand/gravel/pebble patches, **water plane**
    (`write_water_model`), all seeded. `GroundConfig` in `config/schema.py`.
  - `forest3d generate --seed` (reproducible model placement; `WorldPopulator(seed=...)`).
  - Asset/texture provenance in `spike/ASSET_REGISTRY.md` (all CC0).
- **Memory files** (read for gotchas): under
  `~/.claude/projects/-home-ricardodeazambuja-backup-GitStuff-Forest3D/memory/` —
  `forest3d-terrain-texturing.md`, `blender42-gltf-mask-foliage.md`,
  `polyhaven-tree-asset-prep.md`.

### How the existing terrain pipeline consumes a DEM (so your synth DEM is compatible)
`src/forest3d/core/terrain.py` → `TerrainGenerator(tif_path, output_path, config)`:
- Opens the GeoTIFF with GDAL, reads band 1 as a float array, reads the geotransform
  **only for pixel size** (`pixel_width`, `pixel_height`).
- Builds a vertex grid: `world_x = col * pixel_width * scale_factor`,
  `world_y = row * pixel_height * scale_factor`, `world_z = elev * z_scale`; then
  **centers XY** and **shifts Z so min=0**. Writes `terrain.obj` (visual, with UVs) +
  `terrain.stl` (collision + height sampling for placement).
- Mesh resolution == DEM resolution. So **DEM pixel count = mesh density**.
- Projection/CRS is **not required** for meshing (the world's GPS origin comes from the
  sensor-shell `<spherical_coordinates>`, not the DEM). A bare geotransform is enough.

**Bundled DEM reference** (`dem/terrain.tif`): 87×88 px, 2.5 m pixels (~217 m square),
Float32, elevation 1610–1667 (~56 m relief), has a projection. Match this scale class:
e.g. 192×192 px @ 2.5 m ≈ 480 m, or keep ~88 px for the current ~217 m world. More
pixels = denser mesh (88² ≈ 15k faces; 256² ≈ 130k faces — still fine on the RTX 2070).

---

## 2. Deliverable

A new module + CLI that writes a synthetic DEM (and optionally drives the rest):

- `src/forest3d/core/terraingen.py` — `TerrainSynthesizer` producing a heightfield
  numpy array + writing it as a GeoTIFF via GDAL.
- `config/schema.py` — `TerrainGenConfig` (seed, size, resolution, preset, amplitude,
  feature params). Add as an optional field on `TerrainConfig` or standalone.
- `src/forest3d/cli/` — either a new `forest3d terraingen` subcommand **or** a
  `--procedural / --preset / --terrain-seed` set of flags on `forest3d terrain`.
  Recommendation: a dedicated `forest3d terraingen` that emits `dem/<name>.tif`, then the
  user runs the normal `terrain → ground → generate`. Keeps concerns separable and the
  existing `terrain` command untouched. (Optionally add a `--procedural` convenience flag
  to `terrain` that calls terraingen first.)
- `tests/test_terraingen.py` — seed reproducibility + preset registry + basin/lake sanity.

---

## 3. Heightfield synthesis design (numpy + scipy only; both in the image)

Work on a float array `H` of shape `(rows, cols)`, values in metres, seeded with
`rng = np.random.default_rng(seed)`. Reuse the **coarse-noise-then-upscale** trick from
`core/ground.py::GroundCompositor._fractal_noise` (full-res `gaussian_filter` is too slow):
generate noise at ≤256² then `scipy.ndimage.zoom` to the DEM resolution.

**Base layers / features (compose additively, then normalize to target relief):**

1. **fBm hills (base):** sum 4–6 octaves of smoothed Gaussian noise, halving amplitude &
   feature size each octave. Controls rolling hills. `amplitude_m` sets total relief.
2. **Flatlands:** multiply the noise by a low-frequency "flatness" mask, or simply use a
   small `amplitude_m` and `roughness`. A `flat` preset = low amplitude + gentle slope.
3. **Mounts/peaks:** add N Gaussian bumps at random centers
   (`H += peak_h * exp(-(d²)/(2σ²))`). Param: `n_peaks`, height range, radius range.
4. **Valleys:** subtract elongated troughs, or use **ridged** noise
   (`1 - |2*noise-1|`) blended in for sharper valley/ridge structure.
5. **Basins → mini-lakes:** carve closed depressions: `H -= basin_depth * exp(-(d²)/(2σ²))`
   at random centers (away from edges). Record each basin's floor Z and center — these
   are lake sites. After meshing, place the **water plane** at a level slightly above the
   basin floor (reuse `core/ground.py::write_water_model(models_dir, extent_m, level)`).
   For multiple independent lakes at different heights, you may need one water model per
   basin (extend `write_water_model` to accept a name/size/center, or write small per-lake
   plane models sized to each basin's footprint instead of one terrain-wide plane).
6. **Creeks:** generate a meandering path (reuse the random-walk / waypoint idea from
   `GroundCompositor._random_walk_uv` and `_trail_mask`), then **lower H along the path**
   by `creek_depth` within `creek_width` (distance-to-polyline carve, same math as the
   trail mask but applied to height, not texture). Optionally run the creek downhill by
   following the gradient for realism. Fill with a thin water ribbon: either a narrow
   water plane following the channel, or (simpler v1) just carve the channel and let the
   global water level / damp "mud" ground texture read as a creek bed. **v1: carve only;
   water ribbon is a stretch.**

**Smoothing & edges:** final `gaussian_filter(H, sigma=1)` to avoid faceting; optionally
taper the borders down so the terrain doesn't end on a cliff.

**Normalize:** rescale H so `max-min == amplitude_m` (+ optional base elevation).

### Presets (a registry dict, like `ground.py::BIOMES`)
- `hilly` — moderate fBm, no peaks, no basins.
- `mountainous` — high amplitude fBm + ridged + a few peaks.
- `flat` — low amplitude, gentle.
- `valley` — central trough / ridged valley.
- `lakeland` — fBm + 1–3 basins (lakes) + a creek connecting them.
Each preset = default feature params; CLI flags override; everything seeded.

### Writing the GeoTIFF (GDAL)
```python
from osgeo import gdal, osr
driver = gdal.GetDriverByName("GTiff")
ds = driver.Create(str(out_tif), cols, rows, 1, gdal.GDT_Float32)
ds.SetGeoTransform((0.0, pixel_m, 0.0, 0.0, 0.0, -pixel_m))  # origin arbitrary; pixel size matters
# projection optional; set a UTM SRS if you want georef parity with the bundled DEM
band = ds.GetRasterBand(1); band.WriteArray(H.astype("float32")); band.FlushCache()
ds = None
```
`pixel_m` default 2.5 (match bundled). `cols=rows=resolution`.

---

## 4. Integration & one-shot flow

After `terraingen` writes `dem/<name>.tif`, the existing chain just works:
```bash
forest3d terraingen --preset lakeland --seed 7 --size 256 --out dem/synth.tif   # NEW
forest3d terrain    --dem dem/synth.tif                                          # existing
forest3d ground     --mode patchy --biome grassland --seed 7                     # existing
# for lakeland, place water: forest3d ground ... --water-level <basin floor z>
forest3d generate   --density '{"tree":40,"rock":12,"bush":20}' --seed 7         # existing
```
For lakes, terraingen should **print/emit the basin floor Z(s)** so the caller knows the
water level (or write a sidecar JSON `dem/synth.lakes.json` with `[{center,floor_z,radius}]`
and have `forest3d ground --auto-water` read it). Wiring auto-water is a nice-to-have;
v1 can just print the recommended `--water-level`.

---

## 5. Verification (reuse the render harness — smallest-scene-first)

The committed capture scripts are `spike/capture_multi.py` (subscribes to named camera
topics, computes std/green%, saves `frames/<name>.npy`) and `spike/capture_cam.py`.
Ad-hoc per-camera capture scripts used earlier lived in the ephemeral scratchpad — just
recreate a tiny gz-transport subscriber if needed (pattern: subscribe
`gz.transport13.Node` to `gz.msgs10.image_pb2.Image` on the topic, save `m.data`).

**Render recipe (proven):**
```bash
docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all -e PYTHONPATH=/workspace/src \
  -e GZ_SIM_RESOURCE_PATH=/workspace/models -v "$PWD:/workspace" --entrypoint bash forest3d:egl -c '
  cd /workspace
  gz sim -s -r --headless-rendering worlds/<world>.world > frames/gz.log 2>&1 &
  GZ=$!; python3 <capture.py>; kill $GZ'
```
- Build a world by grafting the generated `worlds/forest_world.world` includes into a
  sensor shell + cameras — copy the pattern in `spike/hero_scene.py` / `spike/water_scene.py`
  (terrain + model includes + a camera model). For terrain shape, an **oblique overview**
  and a **top-down** camera read best. **Top-down camera looks DOWN with pitch `+1.5708`**
  (NOT `-1.5708`, which looks at the sky — this bit me once).
- Convert frames to PNG with Pillow (host has it via `condalocal`; container has Pillow):
  `Image.fromarray(np.load('frames/x.npy')).save('spike/x.png')`.

**Acceptance:**
1. `terraingen --seed N` twice → **identical** GeoTIFF (byte or array compare). Different
   seed → different. (Mirror `tests/test_seed.py`.)
2. Each preset renders on the GPU (GL_VENDOR NVIDIA) as the intended landform: hilly
   shows rolling hills; valley shows a trough; lakeland shows basin(s) that hold water
   when the water plane is placed; flat is gently sloped.
3. Mesh sane: no NaNs, finite Z range ≈ `amplitude_m`, placement (`generate`) still
   succeeds on the synth terrain (trees sit on the surface, not floating/buried).
4. Compose a **seeded gallery** (like `spike/biome_gallery.png`) of a few presets/seeds
   and save under `spike/`. Send it to the user.

---

## 6. Gotchas to remember (hard-won)

- `--gpus all -e NVIDIA_DRIVER_CAPABILITIES=all`; verify `GL_VENDOR = NVIDIA` in
  `~/.gz/rendering/ogre2.log` before trusting any frame.
- `-e PYTHONPATH=/workspace/src` to use local edits (image install is a copy).
- GDAL needs `numpy<2` (already pinned in `forest3d:egl`).
- Big `gaussian_filter` on full-res grids is slow → compute coarse + `zoom` upscale.
- gz top-down camera: pitch **+1.5708**.
- `models/`, `worlds/`, `Blender-Assets/**/*.blend`, raw texture/asset dirs, and
  `frames/` are **gitignored** — the registry + committed spike PNGs/scripts are the
  durable record. Synthetic DEMs go in `dem/` (check: `dem/terrain.tif` IS tracked, so
  decide whether to track synth DEMs or gitignore `dem/synth*`).
- The water plane (`write_water_model`) is a flat translucent plane — fine for ponds/
  flooding, not reflective-water perception.

---

## 7. Suggested build order (commit after each; never mention the assistant in messages)

1. `core/terraingen.py`: heightfield synth (fBm hills + normalize) + GeoTIFF writer +
   PRESETS registry with `hilly` only. Unit test: seed reproducibility. **Commit.**
2. CLI `forest3d terraingen` (seed/size/resolution/preset/amplitude/out). Smoke: emit a
   DEM, run `terrain` on it, render an oblique view on GPU. **Commit.**
3. Add features: peaks, valleys/ridged, flat preset. Render gallery. **Commit.**
4. Basins → lakes (carve + emit floor Z + place water plane; lakeland preset). Render a
   lake. **Commit.**
5. Creeks (carve channel; v1 no water ribbon). Render. **Commit.**
6. Update `spike/ASSET_REGISTRY.md` (note: terrain is synthesized, no external asset) and
   the terrain-texturing memory file. Final seeded gallery → send to user. **Commit.**

Keep each step small, render-verify on the GPU, and commit with a clear message
(end-state: `forest3d terraingen` produces seeded hills/valleys/flats/lakes/creeks that
flow through the existing terrain→ground→generate pipeline). Document learnings in the
memory dir as you go.
