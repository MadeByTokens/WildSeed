"""Build the 6 Forest3D demo scenarios end-to-end and render galleries.

Runs inside forest3d:egl with --gpus all. For each scenario:
  terraingen -> terrain -> ground (patchy biome [+auto-water]) -> generate (seeded)
  -> terrain_scene (graft placed models + cameras) -> render hero + oblique + top.

SPECIES are constrained per scenario from the per-biome palettes in
assets/manifest.yaml. `generate` picks a random variant per slot from whatever is in
models/<cat>/, so for each scenario we stash every model NOT in that biome's palette
(across tree/bush/rock/grass), generate, then restore. Density (the tree/rock/bush/
grass counts) is the user-tunable knob: edit it here, or override per run with
`forest3d generate --density '{"tree":80,...}'`.

Output: frames/scn_<name>_{hero,oblique,top}.npy and:
  tools/scenarios_gallery.png   (hero, human-scale)
  tools/scenarios_overview.png  (oblique, aerial)
"""
import json
import os
import shutil
import subprocess

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

CLI = ["python3", "-m", "forest3d.cli.main"]
WS = "/workspace"
MODELS = os.path.join(WS, "models")
CATS = ["tree", "bush", "rock", "grass"]
STASH = os.path.join(MODELS, "_demo_stash")

BIOMES = yaml.safe_load(open(os.path.join(WS, "assets/manifest.yaml")))["biomes"]

# name, terraingen flags, biome(palette+ground), density, water, blurb
SCN = [
    # Phase A (DEMO_REALISM_V2): terrain at robot/human scale. `detail` is dropped hard
    # (kills sub-2 m fBm sponginess that aliases for LIO), `smooth` raised (anti-facet),
    # `feature` set as the "tens of metres" rolling lever (independent of world size).
    # `pixel` is now an explicit per-scene realism knob (held at 1.6 in A; the
    # pixel/density decoupling happens in Phase C where density rises). alpine keeps
    # real relief (higher detail/amplitude); temperate/coastal/savanna read smooth.
    # Phase C: densities raised for populated, varied scenes (the headline coverage gap).
    # Trees kept moderate (each canopy tree is ~0.5 M tris -> tri budget) but scaled UP
    # via SCALE_RANGES; understory (bush/grass) and rocks raised hard since they're light
    # and they spread discrete features across the frame (coverage + LIO structure).
    dict(name="temperate_hills", biome="temperate", pixel=1.6,
         tg=["--preset", "hilly", "--seed", "7", "--amplitude", "26", "--feature", "110",
             "--detail", "0.12", "--smooth", "1.6"],
         density={"tree": 120, "rock": 45, "bush": 150, "grass": 300}, water=False,
         blurb="Rolling green hills, broadleaf forest + understory"),
    # Phase D: savanna was the one weak frame (fast/MP ~2900, tilePk 0.37) -- two drags:
    # ~40% dead sky and an empty, sand-ripple-tiling foreground. Coupled fix: HERO_DOWN
    # raises the eye so the hero cam tilts DOWN (cuts sky, pushes the tiling sand low) AND
    # near-field understory (grass/bush up hard) fills the reclaimed foreground with
    # discrete scrub -> features + coverage + breaks the ripple's periodic dominance.
    dict(name="savanna_flats", biome="savanna", pixel=1.6,
         tg=["--preset", "hilly", "--seed", "3", "--amplitude", "12", "--feature", "140",
             "--detail", "0.10", "--smooth", "1.8"],
         density={"tree": 60, "rock": 42, "bush": 200, "grass": 380}, water=False,
         env={"HERO_DOWN": 3.0},
         blurb="Arid flats, quiver trees + scrub + dry bloom"),
    dict(name="lakeland_wetland", biome="wetland", pixel=1.6,
         tg=["--preset", "lakeland", "--seed", "7", "--feature", "130",
             "--detail", "0.12", "--smooth", "1.6"],
         density={"tree": 100, "rock": 38, "bush": 160, "grass": 240}, water=True,
         blurb="Basins holding water, reeds/ferns along the shores"),
    dict(name="alpine_snow", biome="alpine", pixel=1.6,
         tg=["--preset", "mountainous", "--seed", "7", "--ridged", "0.3",
             "--amplitude", "80", "--feature", "90", "--detail", "0.30", "--smooth", "1.2"],
         density={"tree": 70, "rock": 75, "bush": 55, "grass": 120}, water=False,
         blurb="SNOW - rugged massif, conifers + boulders"),
    dict(name="winter_forest", biome="winter", pixel=1.6,
         tg=["--preset", "valley", "--seed", "5", "--feature", "100",
             "--detail", "0.18", "--smooth", "1.5"],
         density={"tree": 115, "rock": 42, "bush": 0, "grass": 140}, water=False,
         blurb="SNOW - snowy valley, conifers + dead trunks"),
    dict(name="coastal_dune", biome="coastal", pixel=1.6,
         tg=["--preset", "hilly", "--seed", "11", "--amplitude", "7", "--feature", "150",
             "--detail", "0.10", "--smooth", "2.0"],
         density={"tree": 45, "rock": 30, "bush": 130, "grass": 220}, water=False,
         blurb="Coastal dune, marram grass + dune shrubs + coast rocks"),
]

# FOREST_SCN=name1,name2 renders only those scenarios (fast iteration).
_only = os.environ.get("FOREST_SCN")
if _only:
    SCN = [s for s in SCN if s["name"] in _only.split(",")]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def render(cams, tag, water, extra_env=None):
    env = dict(os.environ, FOREST="1")
    if water:
        env["WATER"] = "1"
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    ts = run(["python3", f"{WS}/tools/terrain_scene.py"], env=env)
    for ln in ts.stdout.splitlines():
        if "hero cam frames boulder" in ln or "extent" in ln:
            print(f"  [{tag}] {ln}", flush=True)
    g = subprocess.Popen(["gz", "sim", "-s", "-r", "--headless-rendering",
                          f"{WS}/worlds/terrain_scene.world"],
                         stdout=open(f"{WS}/frames/gz_{tag}.log", "w"),
                         stderr=subprocess.STDOUT)
    try:
        run(["python3", f"{WS}/tools/capture_cams.py", ",".join(cams)], timeout=120)
    finally:
        g.terminate()
        try:
            g.wait(timeout=10)
        except subprocess.TimeoutExpired:
            g.kill()
    for c in cams:
        f = f"{WS}/frames/{c}.npy"
        if os.path.exists(f):
            shutil.copy(f, f"{WS}/frames/scn_{tag}_{c}.npy")


def constrain(palette):
    """Stash every model NOT in this biome's palette, across all categories.

    palette: {trees:[...], bushes:[...], grasses:[...], rocks:[...]}.
    Restores anything previously stashed first, so scenarios don't leak into each other.
    """
    key = {"tree": "trees", "bush": "bushes", "rock": "rocks", "grass": "grasses"}
    os.makedirs(STASH, exist_ok=True)
    # restore all stashed first
    for cat in CATS:
        st = os.path.join(STASH, cat)
        if os.path.isdir(st):
            for d in os.listdir(st):
                shutil.move(os.path.join(st, d), os.path.join(MODELS, cat, d))
    # stash disallowed per category
    for cat in CATS:
        allowed = set(palette.get(key[cat], []))
        catdir = os.path.join(MODELS, cat)
        if not os.path.isdir(catdir):
            continue
        st = os.path.join(STASH, cat)
        os.makedirs(st, exist_ok=True)
        for d in os.listdir(catdir):
            if os.path.isdir(os.path.join(catdir, d)) and d not in allowed:
                shutil.move(os.path.join(catdir, d), os.path.join(st, d))


def restore_all():
    for cat in CATS:
        st = os.path.join(STASH, cat)
        if os.path.isdir(st):
            for d in os.listdir(st):
                shutil.move(os.path.join(st, d), os.path.join(MODELS, cat, d))
    shutil.rmtree(STASH, ignore_errors=True)


for s in SCN:
    name, biome = s["name"], s["biome"]
    pal = BIOMES[biome]
    ground = pal.get("ground", "grassland")
    print(f"=== {name} (biome={biome}, ground={ground}) ===", flush=True)
    # pixel is a per-scene realism knob (Phase A); 1.6 -> ~307 m world at size 192.
    # Terrain SHAPE (rolling scale, smoothness) is set via feature/detail/smooth in
    # s["tg"]; density (Phase C) is decoupled from world size.
    run(CLI + ["terraingen"] + s["tg"] + ["--size", "192",
               "--pixel", str(s.get("pixel", 1.6)), "-o", "dem/synth.tif"])
    run(CLI + ["terrain", "--dem", "dem/synth.tif"])
    _tw = os.environ.get("FOREST_TILE_WARP")  # e.g. 0 renders the no-warp (tiled) baseline
    _twarg = ["--tile-warp", _tw] if _tw is not None else []
    run(CLI + ["ground", "--mode", "patchy", "--biome", ground, "--seed", "7", "--res", "4096"] + _twarg)
    for d in os.listdir(MODELS):
        if d.startswith("water"):
            shutil.rmtree(os.path.join(MODELS, d), ignore_errors=True)
    if s["water"]:
        run(CLI + ["ground", "--mode", "patchy", "--biome", ground, "--seed", "7",
                   "--res", "256", "--auto-water", "--dem", "dem/synth.tif"])
        run(CLI + ["ground", "--mode", "patchy", "--biome", ground, "--seed", "7", "--res", "4096"])
    constrain(pal)
    run(CLI + ["generate", "--density", json.dumps(s["density"]), "--seed", "7"])
    render(["cam_hero", "cam_oblique", "cam_top"], name, s["water"], s.get("env"))
    print(f"  rendered {name}", flush=True)

restore_all()


# ---- galleries (6 panels, 2 cols x 3 rows) ----
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
        f = f"{WS}/frames/scn_{s['name']}_{cam}.npy"
        if not os.path.exists(f):
            continue
        r, c = divmod(i, cols)
        G.paste(lab(fit(np.load(f), PW, PH), f"{i+1}. {s['name']}"), (c * PW, r * PH))
    G.save(outfile)
    print("wrote", outfile, flush=True)


make_gallery("cam_hero", f"{WS}/tools/scenarios_gallery.png")
make_gallery("cam_oblique", f"{WS}/tools/scenarios_overview.png")
