"""Download a Poly Haven model bundle (gltf or native blend + textures) into a dir.

All Poly Haven assets are CC0 (credential-free public API -> reproducible). Usage:
    python3 spike/fetch_polyhaven.py <asset_id> <res> <out_dir> [fmt=gltf|blend]
e.g. python3 spike/fetch_polyhaven.py fir_sapling 1k Blender-Assets/tree/_raw_fir_sapling
     python3 spike/fetch_polyhaven.py shrub_01 2k Blender-Assets/bush/_raw_shrub_01 blend

Prefer `blend` for foliage: Poly Haven's glTF omits the foliage alpha map (leaves
re-export OPAQUE), but the native .blend wires opacity in the material, so the
normalizer's alpha->MASK pattern triggers automatically. See ASSET_REGISTRY.md.

Prints `MAIN_GLTF <path>` (gltf) or `MAIN_BLEND <path>` (blend) for the caller.
"""
import json
import os
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Forest3D asset fetch; CC0)"}


def _get(url, dest=None, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
    return data


asset, res, out = sys.argv[1], sys.argv[2], sys.argv[3]
fmt = sys.argv[4] if len(sys.argv) > 4 else "gltf"
api = f"https://api.polyhaven.com/files/{asset}"
files = json.loads(_get(api))

# Pick the requested format, falling back to the highest available <= requested res.
fmt_files = files[fmt]
res_use = res if res in fmt_files else sorted(fmt_files.keys())[0]
node = fmt_files[res_use][fmt]
os.makedirs(out, exist_ok=True)
main_name = node["url"].split("/")[-1]
jobs = [(node["url"], os.path.join(out, main_name))]
for rel, info in node.get("include", {}).items():
    jobs.append((info["url"], os.path.join(out, rel)))

for url, dest in jobs:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("skip", dest); continue
    print("get", dest)
    _get(url, dest)

tag = "MAIN_BLEND" if fmt == "blend" else "MAIN_GLTF"
print(tag, os.path.join(out, main_name))
