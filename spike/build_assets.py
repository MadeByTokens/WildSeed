"""Build the reproducible demo asset set from assets/manifest.yaml.

For each CC0 Poly Haven asset: fetch (native .blend, credential-free) -> normalize
(recenter/base-z0/scale/LOD+variant select/alpha->MASK) -> convert (Gazebo model).
Idempotent: skips any stage whose output already exists. Writes
assets/manifest.lock.yaml with each SOURCE Poly Haven .blend's sha256 (byte-stable
from their CDN) so a rebuild pulls the verifiably-same source assets (the "frozen"
guarantee). The normalized/converted outputs are not byte-reproducible because Blender
embeds timestamps/pointers, but they are deterministic in content.

Run INSIDE forest3d:egl (has Blender + forest3d + network):
  docker run --rm -v "$PWD:/workspace" --entrypoint bash forest3d:egl-v1 -c \
    'cd /workspace && python3 spike/build_assets.py'

Optional args: a space-separated list of asset ids to (re)build only those.
"""
import hashlib
import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
MANIFEST = "assets/manifest.yaml"
LOCK = "assets/manifest.lock.yaml"
CFG = "configs/realism.yaml"
CLI = ["python3", "-m", "forest3d.cli.main"]
ONLY = set(sys.argv[1:])


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        sys.stdout.write(p.stdout[-2000:])
        sys.stderr.write(p.stderr[-2000:])
    return p


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_ready(cat, aid):
    return os.path.exists(f"models/{cat}/{aid}/mesh/{aid}.glb")


def source_sha(cat, aid):
    """sha256 of the SOURCE Poly Haven .blend (byte-stable from their CDN).

    We hash the download, not the normalized/converted output: Blender embeds
    non-deterministic data (timestamps, pointers) so a re-normalized .blend is never
    byte-identical even from the same source. The source hash is the meaningful
    "frozen asset" guarantee.
    """
    raw_dir = f"Blender-Assets/{cat}/_raw_{aid}"
    if not os.path.isdir(raw_dir):
        return None
    blends = sorted(f for f in os.listdir(raw_dir) if f.endswith(".blend"))
    return sha256(os.path.join(raw_dir, blends[0])) if blends else None


def main():
    man = yaml.safe_load(open(MANIFEST))
    # Merge into any existing lock so a partial (filtered) run doesn't drop other
    # assets' checksums.
    lock = {}
    if os.path.exists(LOCK):
        prev = yaml.safe_load(open(LOCK)) or {}
        lock = prev.get("assets", {}) or {}
    ok, skip, fail = [], [], []
    for a in man["assets"]:
        aid, cat, res = a["id"], a["category"], a.get("res", "2k")
        scale = str(a.get("scale", 1.0))
        variant = str(a.get("variant", "-"))
        lod = str(a.get("lod", "-"))
        if ONLY and aid not in ONLY:
            continue
        raw_dir = f"Blender-Assets/{cat}/_raw_{aid}"
        norm = f"Blender-Assets/{cat}/{aid}.blend"
        print(f"=== {cat}/{aid} (res={res} lod={lod} variant={variant} scale={scale}) ===",
              flush=True)

        if model_ready(cat, aid) and os.path.exists(norm):
            print("  skip (model exists)", flush=True)
            lock[aid] = {"category": cat, "sha256": source_sha(cat, aid), "source": f"polyhaven:{aid}"}
            skip.append(aid)
            continue

        # 1. fetch native .blend (idempotent inside fetch script)
        if not os.path.exists(norm):
            r = run(["python3", "spike/fetch_polyhaven.py", aid, res, raw_dir, "blend"])
            if r.returncode != 0:
                print("  FETCH FAILED", flush=True); fail.append(aid); continue
            raws = [f for f in os.listdir(raw_dir) if f.endswith(".blend")]
            if not raws:
                print("  no .blend fetched", flush=True); fail.append(aid); continue
            src = os.path.join(raw_dir, raws[0])
            # 2. normalize
            r = run(["blender", "-b", src, "--python", "spike/normalize_blend.py",
                     "--", norm, scale, variant, lod])
            if r.returncode != 0 or not os.path.exists(norm):
                print("  NORMALIZE FAILED", flush=True); fail.append(aid); continue

        # 3. convert (stage the single .blend so only this asset is built)
        stage = f"Blender-Assets/_stage/{cat}"
        os.makedirs(stage, exist_ok=True)
        for f in os.listdir(stage):
            if f.endswith(".blend"):
                os.remove(os.path.join(stage, f))
        run(["cp", norm, os.path.join(stage, f"{aid}.blend")])
        r = run(CLI + ["-c", CFG, "convert", "-i", stage, "-o", "models", "-c", cat])
        if r.returncode != 0 or not model_ready(cat, aid):
            print("  CONVERT FAILED", flush=True); fail.append(aid); continue

        sz = os.path.getsize(f"models/{cat}/{aid}/mesh/{aid}.glb") / 1e6
        print(f"  OK -> models/{cat}/{aid} (visual {sz:.1f} MB)", flush=True)
        lock[aid] = {"category": cat, "sha256": source_sha(cat, aid), "source": f"polyhaven:{aid}",
                     "visual_mb": round(sz, 1)}
        ok.append(aid)

    with open(LOCK, "w") as f:
        yaml.safe_dump({"note": "sha256 of each SOURCE Poly Haven .blend download (CC0; byte-stable from their CDN)",
                        "assets": lock}, f, sort_keys=True)
    print(f"\nDONE ok={len(ok)} skip={len(skip)} fail={len(fail)}", flush=True)
    if fail:
        print("FAILED:", fail, flush=True)


if __name__ == "__main__":
    main()
