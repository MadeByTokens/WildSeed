"""Seeded texture randomization of converted Gazebo models.

Domain randomization for perception training (Tobin et al. 2017): recolouring
asset textures — even unrealistically — makes models trained on the renders
transfer better. This module rewrites the base-colour textures EMBEDDED in a
model's visual .glb (pure Python: struct + json + PIL, no glTF library) and
stamps out variant model dirs (``<model>_dr<k>``) that the placement engine
picks up like any other model.

Only images referenced as ``baseColorTexture`` are touched: recolouring a
normal/roughness map would corrupt lighting rather than randomize appearance.
The alpha channel is preserved untouched — foliage leaf cards keep their
cutout masks (see the Blender MASK pipeline notes in docs/).
"""

import json
import logging
import shutil
import struct
import zlib
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("wildseed.texrand")

_GLB_MAGIC = 0x46546C67  # 'glTF'
_CHUNK_JSON = 0x4E4F534A  # 'JSON'
_CHUNK_BIN = 0x004E4942   # 'BIN\0'


# --------------------------------------------------------------------------- #
# GLB container
# --------------------------------------------------------------------------- #
def read_glb(path: Path) -> Tuple[dict, bytes]:
    """Parse a .glb into (gltf json dict, binary chunk bytes)."""
    data = Path(path).read_bytes()
    magic, version, _length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise ValueError(f"{path}: not a GLB file")
    if version != 2:
        raise ValueError(f"{path}: unsupported glTF version {version}")
    off = 12
    gltf, binary = None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8:off + 8 + clen]
        if ctype == _CHUNK_JSON:
            gltf = json.loads(chunk.decode("utf-8"))
        elif ctype == _CHUNK_BIN:
            binary = bytes(chunk)
        off += 8 + clen
    if gltf is None:
        raise ValueError(f"{path}: no JSON chunk")
    return gltf, binary


def write_glb(path: Path, gltf: dict, binary: bytes) -> None:
    """Serialize (gltf, binary) back into a valid .glb."""
    jbytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    jbytes += b" " * (-len(jbytes) % 4)  # JSON chunk padded with spaces
    binary = bytes(binary) + b"\x00" * (-len(binary) % 4)
    total = 12 + 8 + len(jbytes) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", _GLB_MAGIC, 2, total))
        f.write(struct.pack("<II", len(jbytes), _CHUNK_JSON))
        f.write(jbytes)
        f.write(struct.pack("<II", len(binary), _CHUNK_BIN))
        f.write(binary)


def _basecolor_image_indices(gltf: dict) -> List[int]:
    """Image indices used as baseColorTexture (the only safe ones to recolour)."""
    textures = gltf.get("textures", [])
    out = set()
    for mat in gltf.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        tex = pbr.get("baseColorTexture")
        if tex is not None:
            src = textures[tex["index"]].get("source")
            if src is not None:
                out.add(int(src))
    return sorted(out)


# --------------------------------------------------------------------------- #
# recolouring
# --------------------------------------------------------------------------- #
def _jitter_rgb(rgb: np.ndarray, rng: np.random.Generator, strength: float,
                mode: str) -> np.ndarray:
    """Recolour an HxWx3 uint8 array. 'hsv' = global HSV shift; 'wild' = duotone."""
    from PIL import Image
    if mode == "wild":
        # luminance through a random 2-colour ramp: structure kept, colours wild
        lum = rgb.astype(np.float32).mean(axis=2, keepdims=True) / 255.0
        c1 = rng.random(3).astype(np.float32) * 255.0
        c2 = rng.random(3).astype(np.float32) * 255.0
        out = c1[None, None, :] + (c2 - c1)[None, None, :] * lum
        return np.clip(out, 0, 255).astype(np.uint8)
    hsv = np.asarray(Image.fromarray(rgb, "RGB").convert("HSV"), dtype=np.float32)
    dh = rng.uniform(-0.5, 0.5) * strength * 255.0
    ds = 1.0 + rng.uniform(-0.6, 0.6) * strength
    dv = 1.0 + rng.uniform(-0.4, 0.4) * strength
    h = np.mod(hsv[..., 0] + dh, 256.0)
    s = np.clip(hsv[..., 1] * ds, 0, 255)
    v = np.clip(hsv[..., 2] * dv, 0, 255)
    out = Image.fromarray(np.stack([h, s, v], -1).astype(np.uint8), "HSV").convert("RGB")
    return np.asarray(out)


def _recolour_image_bytes(raw: bytes, rng: np.random.Generator, strength: float,
                          mode: str) -> bytes:
    """Recolour one embedded image, preserving any alpha channel exactly."""
    from PIL import Image
    img = Image.open(BytesIO(raw))
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        rgba = img.convert("RGBA")
        arr = np.asarray(rgba)
        rgb = _jitter_rgb(arr[..., :3].copy(), rng, strength, mode)
        out_arr = np.dstack([rgb, arr[..., 3]])
        out = Image.fromarray(out_arr, "RGBA")
    else:
        out = Image.fromarray(
            _jitter_rgb(np.asarray(img.convert("RGB")).copy(), rng, strength, mode), "RGB")
    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def randomize_glb(src: Path, dst: Path, rng: np.random.Generator,
                  strength: float = 0.5, mode: str = "hsv") -> int:
    """Write a copy of ``src`` with baseColor textures recoloured. Returns #images."""
    gltf, binary = read_glb(src)
    for buf in gltf.get("buffers", []):
        if "uri" in buf:
            raise ValueError(f"{src}: external buffer URIs unsupported (expected GLB-embedded)")
    targets = _basecolor_image_indices(gltf)
    images = gltf.get("images", [])
    views = gltf.get("bufferViews", [])

    replaced: Dict[int, bytes] = {}  # bufferView index -> new bytes
    for i in targets:
        img = images[i]
        bv = img.get("bufferView")
        if bv is None:
            continue  # external uri image; nothing embedded to rewrite
        view = views[bv]
        off = int(view.get("byteOffset", 0))
        raw = binary[off:off + int(view["byteLength"])]
        replaced[bv] = _recolour_image_bytes(raw, rng, strength, mode)
        img["mimeType"] = "image/png"

    # rebuild the binary buffer: every view re-packed in list order, 4-aligned
    new_bin = bytearray()
    for idx, view in enumerate(views):
        if idx in replaced:
            data = replaced[idx]
        else:
            off = int(view.get("byteOffset", 0))
            data = binary[off:off + int(view["byteLength"])]
        new_bin += b"\x00" * (-len(new_bin) % 4)
        view["byteOffset"] = len(new_bin)
        view["byteLength"] = len(data)
        new_bin += data
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(new_bin)

    write_glb(dst, gltf, bytes(new_bin))
    return len(replaced)


# --------------------------------------------------------------------------- #
# model-dir variants
# --------------------------------------------------------------------------- #
def randomize_model_dir(model_dir: Path, variant_name: str,
                        rng: np.random.Generator, strength: float = 0.5,
                        mode: str = "hsv") -> Path:
    """Stamp out one recoloured variant of a converted Gazebo model dir.

    Copies the dir to a sibling ``variant_name``, renames the meshes and
    rewrites every textual reference (model.sdf / model.config / test.world)
    from the old base name to the new one, then recolours the visual .glb.
    """
    model_dir = Path(model_dir)
    base = model_dir.name
    dst = model_dir.parent / variant_name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(model_dir, dst)

    mesh = dst / "mesh"
    visual_src = mesh / f"{base}.glb"
    if not visual_src.exists():
        raise FileNotFoundError(f"{visual_src} (is this a converted WildSeed model?)")
    n = randomize_glb(visual_src, mesh / f"{variant_name}.glb", rng, strength, mode)
    visual_src.unlink()
    coll = mesh / f"{base}_collision.glb"
    if coll.exists():
        coll.rename(mesh / f"{variant_name}_collision.glb")

    for fname in ("model.sdf", "model.config", "test.world"):
        f = dst / fname
        if f.exists():
            f.write_text(f.read_text().replace(base, variant_name))
    logger.info(f"variant {variant_name}: {n} texture(s) recoloured")
    return dst


def randomize_models(models_root: Path, categories: List[str], variants: int,
                     seed: int = 0, strength: float = 0.5, mode: str = "hsv",
                     ) -> List[Path]:
    """Create ``variants`` recoloured copies of every model in the categories.

    Deterministic: the RNG for (model, k) derives from
    (seed, crc32(category/model), k), so adding models or reordering dirs never
    changes another model's recolour, and re-runs overwrite identical variants.
    Existing ``*_dr<k>`` dirs are skipped as sources (no variant-of-variant).
    """
    models_root = Path(models_root)
    made = []
    for cat in categories:
        cat_dir = models_root / cat
        if not cat_dir.is_dir():
            logger.warning(f"no such category dir: {cat_dir}")
            continue
        for mdir in sorted(p for p in cat_dir.iterdir() if p.is_dir()):
            if "_dr" in mdir.name or mdir.name.startswith("."):
                continue
            key = zlib.crc32(f"{cat}/{mdir.name}".encode())
            for k in range(variants):
                rng = np.random.default_rng([seed, key, k])
                name = f"{mdir.name}_dr{k}"
                made.append(randomize_model_dir(mdir, name, rng, strength, mode))
    return made
