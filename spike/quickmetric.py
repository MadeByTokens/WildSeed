"""Quick per-frame metrics for a single scene (reuses compare.py).

  python3 spike/quickmetric.py savanna_flats [hero|oblique|top] ...
Prints cov / fast-per-MP / tilePk for each named scene's cam_hero (and cam_top
tilePk), so a single-scene fix build can be judged without the full compare grid.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare import all_metrics, load_rgb, to_common, tiling_metrics  # noqa: E402

WS = os.environ.get("WS", os.getcwd())
names = sys.argv[1:] or ["savanna_flats", "alpine_snow", "coastal_dune"]
for name in names:
    hp = os.path.join(WS, "frames", f"scn_{name}_cam_hero.npy")
    tp = os.path.join(WS, "frames", f"scn_{name}_cam_top.npy")
    if not os.path.exists(hp):
        print(f"{name:<16} (no hero frame)")
        continue
    m = all_metrics(to_common(load_rgb(hp)))
    tt = tiling_metrics(to_common(load_rgb(tp)))["tiling_peak"] if os.path.exists(tp) else float("nan")
    print(f"{name:<16} hero: cov={m['coverage']:.2f} fast/MP={m['fast_pmp']:.0f} "
          f"tilePk={m['tiling_peak']:.3f}  top.tilePk={tt:.3f}")
