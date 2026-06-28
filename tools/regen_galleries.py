"""Rebuild the 6-panel hero/oblique galleries from existing frames on disk.

Used when a single-scene fix build (FOREST_SCN=...) regenerated the galleries with
only that scene present. Reads all 6 scn_<name>_<cam>.npy and re-lays the 2x3 grids,
identical layout to build_scenarios.make_gallery, without re-rendering anything.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

WS = os.environ.get("WS", os.getcwd())
SCN = ["temperate_hills", "savanna_flats", "lakeland_wetland",
       "alpine_snow", "winter_forest", "coastal_dune"]


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
    for i, name in enumerate(SCN):
        f = f"{WS}/frames/scn_{name}_{cam}.npy"
        if not os.path.exists(f):
            print("MISSING", f)
            continue
        r, c = divmod(i, cols)
        a = np.load(f)[:, :, :3].astype("uint8")
        G.paste(lab(fit(a, PW, PH), f"{i+1}. {name}"), (c * PW, r * PH))
    G.save(outfile)
    print("wrote", outfile)


make_gallery("cam_hero", f"{WS}/tools/scenarios_gallery.png")
make_gallery("cam_oblique", f"{WS}/tools/scenarios_overview.png")
