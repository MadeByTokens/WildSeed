"""Build the 5 Forest3D demo scenarios end-to-end and render a gallery.

Runs inside forest3d:egl with --gpus all. For each scenario:
  terraingen -> terrain -> ground (patchy biome [+auto-water]) -> generate (seeded)
  -> terrain_scene (graft placed models + cameras) -> render oblique [+ top].

Tree SPECIES are constrained per scenario (generate picks a random variant per
slot, so we temporarily stash the tree variants a scenario shouldn't use):
broadleaf island_tree for temperate/savanna/wetland; fir + dead trunk for snow.

Output: frames/scn_<name>_{oblique,top}.npy and spike/scenarios_gallery.png.
"""
import json
import os
import shutil
import subprocess
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CLI = ["python3", "-m", "forest3d.cli.main"]
MODELS = "/workspace/models"
TREE = os.path.join(MODELS, "tree")
STASH = os.path.join(MODELS, "_tree_stash")

# name, terraingen flags, biome, density, trees (allowed variants), water(bool), blurb
SCN = [
    dict(name="temperate_hills",
         tg=["--preset", "hilly", "--seed", "7", "--detail", "0.5"],
         biome="grassland", density={"tree": 45, "rock": 14, "bush": 0},
         trees=["island_tree_01"], water=False,
         blurb="Rolling green hills, broadleaf forest"),
    dict(name="savanna_flats",
         tg=["--preset", "hilly", "--seed", "3", "--amplitude", "14", "--detail", "0.4"],
         biome="desert", density={"tree": 6, "rock": 24, "bush": 0},
         trees=["island_tree_01"], water=False,
         blurb="Arid sandy flats, sparse acacia + boulders"),
    dict(name="lakeland_wetland",
         tg=["--preset", "lakeland", "--seed", "7"],
         biome="grassland", density={"tree": 32, "rock": 12, "bush": 0},
         trees=["island_tree_01"], water=True,
         blurb="Basins holding water (per-basin levels), trees around the shores"),
    dict(name="alpine_snow",
         tg=["--preset", "mountainous", "--seed", "7", "--ridged", "0.2", "--detail", "0.6"],
         biome="snow", density={"tree": 16, "rock": 28, "bush": 0},
         trees=["fir_sapling", "dead_tree_trunk_02"], water=False,
         blurb="SNOW — rugged snowy massif, conifers + boulders"),
    dict(name="winter_forest",
         tg=["--preset", "valley", "--seed", "5", "--detail", "0.6"],
         biome="snow", density={"tree": 38, "rock": 12, "bush": 0},
         trees=["fir_sapling", "dead_tree_trunk_02"], water=False,
         blurb="SNOW — snowy valley, conifers + dead trunks"),
]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def render(cams, tag, water):
    env = dict(os.environ, FOREST="1")
    if water:
        env["WATER"] = "1"
    run(["python3", "/workspace/spike/terrain_scene.py"], env=env)
    g = subprocess.Popen(["gz", "sim", "-s", "-r", "--headless-rendering",
                          "/workspace/worlds/terrain_scene.world"],
                         stdout=open(f"/workspace/frames/gz_{tag}.log", "w"),
                         stderr=subprocess.STDOUT)
    try:
        run(["python3", "/workspace/spike/capture_cams.py", ",".join(cams)], timeout=90)
    finally:
        g.terminate()
        try:
            g.wait(timeout=10)
        except subprocess.TimeoutExpired:
            g.kill()
    for c in cams:
        f = f"/workspace/frames/{c}.npy"
        if os.path.exists(f):
            shutil.copy(f, f"/workspace/frames/scn_{tag}_{c}.npy")


def constrain_trees(allowed):
    os.makedirs(STASH, exist_ok=True)
    # move back anything stashed
    for d in os.listdir(STASH):
        shutil.move(os.path.join(STASH, d), os.path.join(TREE, d))
    # stash disallowed
    for d in os.listdir(TREE):
        if os.path.isdir(os.path.join(TREE, d)) and d not in allowed:
            shutil.move(os.path.join(TREE, d), os.path.join(STASH, d))


for s in SCN:
    name = s["name"]
    print(f"=== {name} ===", flush=True)
    run(CLI + ["terraingen"] + s["tg"] + ["--size", "192", "-o", "dem/synth.tif"])
    run(CLI + ["terrain", "--dem", "dem/synth.tif"])
    run(CLI + ["ground", "--mode", "patchy", "--biome", s["biome"], "--seed", "7", "--res", "4096"])
    # clear any prior water models, then per-basin water for lakeland
    for d in os.listdir(MODELS):
        if d.startswith("water"):
            shutil.rmtree(os.path.join(MODELS, d), ignore_errors=True)
    if s["water"]:
        run(CLI + ["ground", "--mode", "patchy", "--biome", s["biome"], "--seed", "7",
                   "--res", "256", "--auto-water", "--dem", "dem/synth.tif"])
        # re-bake full-res ground (the auto-water call above used low res for speed)
        run(CLI + ["ground", "--mode", "patchy", "--biome", s["biome"], "--seed", "7", "--res", "4096"])
    constrain_trees(s["trees"])
    run(CLI + ["generate", "--density", json.dumps(s["density"]), "--seed", "7"])
    cams = ["cam_hero", "cam_oblique", "cam_top"]
    render(cams, name, s["water"])
    print(f"  rendered {name}", flush=True)

# restore all stashed tree variants
if os.path.isdir(STASH):
    for d in os.listdir(STASH):
        shutil.move(os.path.join(STASH, d), os.path.join(TREE, d))
    os.rmdir(STASH)

# ---- gallery (5 oblique panels, 2 cols) ----
def lab(img, t):
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except Exception:
        f = ImageFont.load_default()
    d.rectangle([8, 8, 18 + d.textlength(t, font=f), 44], fill=(0, 0, 0))
    d.text((13, 11), t, fill=(255, 255, 255), font=f)
    return img


def fit(a, w, h):
    im = Image.fromarray(a).convert("RGB")
    im.thumbnail((w, h))
    c = Image.new("RGB", (w, h), (222, 233, 244))
    c.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return c


def make_gallery(cam, outfile, PW=720, PH=420):
    cols, rows = 2, 3
    G = Image.new("RGB", (cols * PW, rows * PH), (240, 244, 248))
    for i, s in enumerate(SCN):
        f = f"/workspace/frames/scn_{s['name']}_{cam}.npy"
        if not os.path.exists(f):
            continue
        r, c = divmod(i, cols)
        G.paste(lab(fit(np.load(f), PW, PH), f"{i+1}. {s['name']}"), (c * PW, r * PH))
    G.save(outfile)
    print("wrote", outfile, flush=True)


make_gallery("cam_hero", "/workspace/spike/scenarios_gallery.png")        # human-scale hero shots
make_gallery("cam_oblique", "/workspace/spike/scenarios_overview.png")     # aerial overviews
