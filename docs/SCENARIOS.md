# Forest3D demo scenarios

Five complete, reproducible outdoor scenarios built entirely from the seeded
pipeline (`terraingen → terrain → ground → generate`) and CC0 assets. Two are
snow scenes. Every command below is copy-pasteable inside the `forest3d:egl`
container (prefix with the Docker wrapper from `docs/TUTORIAL.md`).

Rebuild all five + the gallery in one go:

```bash
python3 spike/build_scenarios.py    # writes spike/scenarios_gallery.png
```

Gallery: `spike/scenarios_gallery.png`. Each scenario uses seed 7 for ground; the
terrain/placement seeds are listed per scenario. Change any seed for a fresh world.

Asset species are constrained per scenario (the builder temporarily keeps only the
intended tree variants in `models/tree/`, since `generate` picks variants at random):
broadleaf **island_tree_01** for temperate/savanna/wetland, **fir_sapling** +
**dead_tree_trunk_02** for the snow scenes. Rocks (boulder_01, namaqualand_boulder_04,
namaqualand_rocks_01) are used throughout. All assets are CC0 — see
`spike/ASSET_REGISTRY.md` for full credits.

---

## 1. Temperate hills  🌳
Rolling green hills, broadleaf forest with scattered boulders.

```bash
forest3d terraingen --preset hilly --seed 7 --detail 0.5 -o dem/synth.tif
forest3d terrain    --dem dem/synth.tif
forest3d ground     --mode patchy --biome grassland --seed 7
forest3d generate   --density '{"tree":45,"rock":14,"bush":0}' --seed 7
```

## 2. Savanna flats  🏜️
Arid sandy terrain, sparse acacia and lots of rock — a dry savanna / semi-desert.

```bash
forest3d terraingen --preset hilly --seed 3 --amplitude 14 --detail 0.4 -o dem/synth.tif
forest3d terrain    --dem dem/synth.tif
forest3d ground     --mode patchy --biome desert --seed 7
forest3d generate   --density '{"tree":6,"rock":24,"bush":0}' --seed 7
```

## 3. Lakeland wetland  💧
Basins that hold water at their own levels (per-basin planes), trees along the shores.

```bash
forest3d terraingen --preset lakeland --seed 7 -o dem/synth.tif
forest3d terrain    --dem dem/synth.tif
forest3d ground     --mode patchy --biome grassland --seed 7
forest3d ground     --mode patchy --biome grassland --seed 7 --auto-water --dem dem/synth.tif
forest3d generate   --density '{"tree":32,"rock":12,"bush":0}' --seed 7
```
(The second `ground` call adds one water plane per basin; see `docs/TUTORIAL.md` §4.)

## 4. Alpine snow  ❄️  *(snow)*
Rugged snowy massif, conifers and many boulders — high-relief alpine.

```bash
forest3d terraingen --preset mountainous --seed 7 --ridged 0.2 --detail 0.6 -o dem/synth.tif
forest3d terrain    --dem dem/synth.tif
forest3d ground     --mode patchy --biome snow --seed 7
forest3d generate   --density '{"tree":16,"rock":28,"bush":0}' --seed 7
```
(Snow scenes keep only `fir_sapling` + `dead_tree_trunk_02` in `models/tree/`.)

## 5. Winter forest  ❄️  *(snow)*
A snowy valley with conifers and dead trunks.

```bash
forest3d terraingen --preset valley --seed 5 --detail 0.6 -o dem/synth.tif
forest3d terrain    --dem dem/synth.tif
forest3d ground     --mode patchy --biome snow --seed 7
forest3d generate   --density '{"tree":38,"rock":12,"bush":0}' --seed 7
```

---

### Notes
- Render any scenario with the harness in `docs/TUTORIAL.md` §2 (`FOREST=1
  python3 spike/terrain_scene.py` then `gz sim ...`). Add `WATER=1` for lakeland.
- To make a *batch* of randomized variants of any scenario, loop the same recipe
  over different `--seed` values (see `docs/TUTORIAL.md` §3).
- Heights/relief, surface smoothness, biome, and density are all independent knobs —
  mix freely to derive new scenarios.
