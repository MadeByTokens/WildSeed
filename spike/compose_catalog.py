"""Compose frames/catalog/*.png into a labeled grid grouped by category.

  python3 spike/compose_catalog.py   ->  spike/asset_catalog.png
"""
import glob
import os
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

SRC = "/workspace/frames/catalog"
OUT = "/workspace/spike/asset_catalog.png"
TW, TH = 360, 440
COLS = 5
PAD = 6
HDR = 40
CAT_ORDER = ["tree", "bush", "grass", "rock"]

try:
    F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    FB = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
except Exception:
    F = FB = ImageFont.load_default()

by_cat = defaultdict(list)
for p in sorted(glob.glob(f"{SRC}/*.png")):
    cat = os.path.basename(p).split("__")[0]
    by_cat[cat].append(p)

# layout: per category a header row then rows of tiles
rows_plan = []  # ("header", cat, count) or ("tiles", [paths])
for cat in CAT_ORDER + [c for c in by_cat if c not in CAT_ORDER]:
    items = by_cat.get(cat, [])
    if not items:
        continue
    rows_plan.append(("header", cat, len(items)))
    for i in range(0, len(items), COLS):
        rows_plan.append(("tiles", items[i:i + COLS]))

width = COLS * (TW + PAD) + PAD
y = PAD
heights = []
for kind, *rest in rows_plan:
    heights.append(HDR if kind == "header" else TH + PAD)
height = sum(heights) + PAD

canvas = Image.new("RGB", (width, height), (238, 242, 247))
draw = ImageDraw.Draw(canvas)
y = PAD
for (kind, *rest), h in zip(rows_plan, heights):
    if kind == "header":
        cat, n = rest
        draw.rectangle([PAD, y, width - PAD, y + HDR - 6], fill=(30, 40, 55))
        draw.text((PAD + 10, y + 6), f"{cat.upper()}  ({n})", fill=(255, 255, 255), font=FB)
    else:
        paths = rest[0]
        x = PAD
        for p in paths:
            try:
                im = Image.open(p).convert("RGB").resize((TW, TH))
            except Exception:
                im = Image.new("RGB", (TW, TH), (200, 200, 200))
            canvas.paste(im, (x, y))
            name = os.path.basename(p).split("__", 1)[1][:-4]
            draw.rectangle([x, y + TH - 28, x + TW, y + TH], fill=(0, 0, 0))
            draw.text((x + 6, y + TH - 26), name, fill=(255, 255, 255), font=F)
            x += TW + PAD
    y += h

canvas.save(OUT)
print("wrote", OUT, canvas.size)
