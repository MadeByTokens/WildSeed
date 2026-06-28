"""Download a Poly Haven model's glTF bundle (gltf + bin + textures) into a dir.

All Poly Haven assets are CC0. Usage:
    python3 spike/fetch_polyhaven.py <asset_id> <res> <out_dir>
e.g. python3 spike/fetch_polyhaven.py fir_sapling 1k Blender-Assets/tree/_raw_fir_sapling
"""
import json
import os
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Forest3D asset fetch; CC0)"}


def _get(url, dest=None, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
    return data


asset, res, out = sys.argv[1], sys.argv[2], sys.argv[3]
api = f"https://api.polyhaven.com/files/{asset}"
files = json.loads(_get(api))

node = files["gltf"][res]["gltf"]
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

print("MAIN_GLTF", os.path.join(out, main_name))
