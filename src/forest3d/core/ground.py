"""Procedural ground material compositor for Forest3D terrain.

Generates the terrain's PBR ground material (albedo / normal / roughness) either as
a crisp tiled single texture (``uniform``) or as a seeded baked composite
(``patchy``) that blends a base with overlay layers -- organic patches of
sand/gravel/pebbles/rock and trails (explicit waypoints or seeded random walk).

This is a superset of the original Forest3D terrain texturing (single PBR material
from a soil.blend): same render path, plus controllable, *reproducible* variation
for randomized VIO / lidar test scenarios. Everything is driven by a seed, so the
same seed yields the same ground and a new seed yields a new scenario.

Output is one ``<pbr><metal>`` material written into ``<ground>/texture/`` with the
terrain UVs rewritten accordingly, plus an optional flat water model.
"""

import glob
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.ndimage import gaussian_filter, zoom

logger = logging.getLogger("forest3d.ground")


# --------------------------------------------------------------------------- #
# Biome presets. Each maps logical roles to material *keys* (a substring that
# identifies a texture pack under the texture root, e.g. an ambientCG id). A
# layer is a patch (organic noise blobs) or a trail (path).
# --------------------------------------------------------------------------- #
BIOMES: Dict[str, dict] = {
    "grassland": {
        "base": "Grass004", "base_tile_m": 4.0,
        "layers": [
            {"material": "Ground027", "kind": "patch", "coverage": 0.08, "scale_m": 28.0, "tile_m": 3.0},  # sand
            {"material": "Gravel023", "kind": "patch", "coverage": 0.05, "scale_m": 16.0, "tile_m": 2.0},  # gravel
            {"material": "Rocks023",  "kind": "patch", "coverage": 0.04, "scale_m": 9.0,  "tile_m": 2.0},  # pebbles
            {"material": "Ground054", "kind": "trail", "width_m": 2.5, "count": 2, "tile_m": 3.0},          # dirt
        ],
    },
    "desert": {
        "base": "Ground027", "base_tile_m": 4.0,
        "layers": [
            {"material": "Gravel023", "kind": "patch", "coverage": 0.12, "scale_m": 22.0, "tile_m": 2.0},
            {"material": "Rocks023",  "kind": "patch", "coverage": 0.07, "scale_m": 9.0,  "tile_m": 2.0},
            {"material": "Ground054", "kind": "trail", "width_m": 3.0, "count": 1, "tile_m": 3.0},
        ],
    },
    "gravel": {
        "base": "Gravel023", "base_tile_m": 2.0,
        "layers": [
            {"material": "Ground027", "kind": "patch", "coverage": 0.10, "scale_m": 20.0, "tile_m": 3.0},
            {"material": "Rocks023",  "kind": "patch", "coverage": 0.10, "scale_m": 8.0,  "tile_m": 2.0},
            {"material": "Ground054", "kind": "trail", "width_m": 2.5, "count": 1, "tile_m": 3.0},
        ],
    },
    "snow": {
        "base": "Snow", "base_tile_m": 5.0,
        "layers": [
            {"material": "Rocks023",  "kind": "patch", "coverage": 0.07, "scale_m": 14.0, "tile_m": 2.0},  # exposed rock
            {"material": "Ground037", "kind": "patch", "coverage": 0.04, "scale_m": 10.0, "tile_m": 3.0},  # bare ground
            {"material": "Ground054", "kind": "trail", "width_m": 2.0, "count": 1, "tile_m": 3.0},          # tracked path
        ],
    },
}

# Map -> (color, normal, roughness) filename substrings tried in order.
_COLOR = ("color", "diff", "albedo", "basecolor", "base_color")
_NORMAL = ("normalgl", "nor_gl", "normal_gl", "normaldx", "normal", "_nor")
_ROUGH = ("roughness", "rough")


class GroundCompositor:
    """Compose a terrain ground PBR material set from tiling texture packs."""

    def __init__(
        self,
        ground_dir: Path,
        texture_root: Path,
        config=None,
    ):
        self.ground_dir = Path(ground_dir)
        self.obj = self.ground_dir / "mesh" / "terrain.obj"
        self.texdir = self.ground_dir / "texture"
        self.texture_root = Path(texture_root)
        self.config = config  # GroundConfig (duck-typed)
        self._cache: Dict[str, np.ndarray] = {}

    # ---- material loading ------------------------------------------------- #
    def _find(self, key: str, kinds: Tuple[str, ...]) -> Optional[str]:
        cands = glob.glob(os.path.join(self.texture_root, "**", f"*{key}*"), recursive=True)
        cands = [c for c in cands if c.lower().endswith((".png", ".jpg", ".jpeg"))]
        for k in kinds:
            for c in cands:
                if k in os.path.basename(c).lower():
                    return c
        return None

    def _load(self, path: str) -> np.ndarray:
        from PIL import Image
        if path not in self._cache:
            self._cache[path] = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
        return self._cache[path]

    def material(self, key: str) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
        """Return (albedo, normal, roughness) float arrays for a material key.

        Normal/roughness fall back to flat/mid-grey if the pack lacks them.
        """
        cpath = self._find(key, _COLOR)
        if cpath is None:
            raise FileNotFoundError(
                f"No color texture found for material '{key}' under {self.texture_root}. "
                f"Drop a CC0 pack (e.g. ambientCG {key}) there."
            )
        alb = self._load(cpath)
        npath = self._find(key, _NORMAL)
        nor = self._load(npath) if npath else None
        rpath = self._find(key, _ROUGH)
        rgh = self._load(rpath) if rpath else None
        return alb, nor, rgh

    # ---- geometry / extent ------------------------------------------------ #
    def terrain_extent(self) -> Tuple[float, float, float, float]:
        minx = miny = 1e18
        maxx = maxy = -1e18
        with open(self.obj) as f:
            for line in f:
                if line.startswith("v "):
                    p = line.split()
                    x, y = float(p[1]), float(p[2])
                    minx, maxx = min(minx, x), max(maxx, x)
                    miny, maxy = min(miny, y), max(maxy, y)
        return minx, maxx, miny, maxy

    def _extent_m(self) -> Tuple[float, float]:
        minx, maxx, miny, maxy = self.terrain_extent()
        return (maxx - minx, maxy - miny)

    # ---- sampling / blending --------------------------------------------- #
    @staticmethod
    def _tiled(tex: np.ndarray, res: int, extent_m: Tuple[float, float], tile_m: float) -> np.ndarray:
        h, w = tex.shape[:2]
        ex, ey = extent_m
        ux = ((np.arange(res) / res) * (ex / tile_m)) % 1.0
        uy = ((np.arange(res) / res) * (ey / tile_m)) % 1.0
        cols = (ux * w).astype(int) % w
        rows = (uy * h).astype(int) % h
        return tex[np.ix_(rows, cols)]

    @staticmethod
    def _blend_normal(a: np.ndarray, b: np.ndarray, m: np.ndarray) -> np.ndarray:
        da, db = a * 2.0 - 1.0, b * 2.0 - 1.0
        out = da * (1 - m[..., None]) + db * m[..., None]
        n = np.linalg.norm(out, axis=2, keepdims=True)
        n[n == 0] = 1
        return (out / n) * 0.5 + 0.5

    # ---- mask generators (the tuned, organic part) ------------------------ #
    @staticmethod
    def _fractal_noise(res: int, scale_px: float, rng: np.random.Generator, octaves: int = 4) -> np.ndarray:
        """Organic value noise in [0,1] via summed smoothed-random octaves.

        Computed at a coarse working resolution (capped) then bilinearly upscaled
        to `res` -- gaussian_filter on a full 4-8K grid per octave is far too slow
        for a CLI that must regenerate many seeded scenarios.
        """
        work = int(min(res, 768))
        s = scale_px * work / res  # keep feature size in output pixels
        out = np.zeros((work, work), np.float32)
        amp, total = 1.0, 0.0
        sigma = s
        for _ in range(octaves):
            n = gaussian_filter(rng.standard_normal((work, work)).astype(np.float32), sigma=max(sigma, 0.8))
            out += amp * n
            total += amp
            amp *= 0.5
            sigma *= 0.5
        out /= total
        out -= out.min()
        mx = out.max()
        out = out / mx if mx > 0 else out
        if work != res:
            out = zoom(out, res / work, order=1).astype(np.float32)
            out = out[:res, :res] if out.shape[0] >= res else np.pad(out, ((0, res - out.shape[0]), (0, res - out.shape[1])), mode="edge")
        return out

    def _patch_mask(self, res: int, coverage: float, scale_m: float, rng: np.random.Generator,
                    extent_m: Tuple[float, float], feather: float = 0.06) -> np.ndarray:
        """Organic patches covering ~`coverage` of the area, feature size ~`scale_m`."""
        scale_px = scale_m / ((extent_m[0] + extent_m[1]) / 2.0) * res
        noise = self._fractal_noise(res, max(scale_px, 2.0), rng)
        thr = float(np.quantile(noise, 1.0 - np.clip(coverage, 0.0, 1.0)))
        band = feather
        return np.clip((noise - (thr - band)) / (2 * band + 1e-6), 0, 1)

    def _trail_mask(self, res: int, waypoints_uv, width_m: float, extent_m: Tuple[float, float],
                    rng: np.random.Generator, feather: float = 0.5) -> np.ndarray:
        ex, ey = extent_m
        pts = np.array(waypoints_uv, dtype=np.float32) * res
        m = np.zeros((res, res), np.float32)
        yy, xx = np.mgrid[0:res, 0:res]
        wpx = width_m / ((ex + ey) / 2) * res / 2.0
        # slight width wobble for a natural, non-uniform path
        wobble = 0.75 + 0.5 * self._fractal_noise(res, res / 60, rng, octaves=2)
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            seg = q - p
            L2 = float((seg ** 2).sum()) or 1.0
            t = np.clip(((xx - p[0]) * seg[0] + (yy - p[1]) * seg[1]) / L2, 0, 1)
            px, py = p[0] + t * seg[0], p[1] + t * seg[1]
            dist = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
            local_w = wpx * wobble
            m = np.maximum(m, np.clip(1.0 - (dist - local_w) / (local_w * feather + 1e-3), 0, 1))
        return m

    @staticmethod
    def _random_walk_uv(rng: np.random.Generator, n: int = 6, margin: float = 0.08):
        horizontal = rng.random() < 0.5
        a = rng.uniform(margin, 1 - margin)
        pts = []
        for i in range(n):
            t = margin + (1 - 2 * margin) * i / (n - 1)
            a = float(np.clip(a + rng.uniform(-0.22, 0.22), margin, 1 - margin))
            pts.append((a, t) if horizontal else (t, a))
        return pts

    # ---- top-level generate ---------------------------------------------- #
    def generate(self) -> dict:
        cfg = self.config
        mode = getattr(cfg, "mode", "patchy")
        if mode == "uniform":
            return self._generate_uniform()
        return self._generate_patchy()

    def _generate_uniform(self) -> dict:
        cfg = self.config
        biome = BIOMES.get(getattr(cfg, "biome", "grassland"), BIOMES["grassland"])
        base = getattr(cfg, "base_material", None) or biome["base"]
        alb, nor, rgh = self.material(base)
        self._write_maps(self._to8(alb), self._to8(nor) if nor is not None else None,
                         self._to8(rgh) if rgh is not None else None)
        self.set_uv(getattr(cfg, "uniform_tile", 8.0))
        self.write_sdf(has_normal=nor is not None, has_rough=rgh is not None)
        logger.info(f"ground: uniform base={base} tile=x{getattr(cfg, 'uniform_tile', 8.0)}")
        return {"mode": "uniform", "base": base}

    def _generate_patchy(self) -> dict:
        cfg = self.config
        res = int(getattr(cfg, "resolution", 4096))
        seed = int(getattr(cfg, "seed", 0))
        rng = np.random.default_rng(seed)
        randomize = getattr(cfg, "randomize", True)
        biome_name = getattr(cfg, "biome", "grassland")
        biome = BIOMES.get(biome_name, BIOMES["grassland"])
        extent = self._extent_m()

        base_key = getattr(cfg, "base_material", None) or biome["base"]
        base_tile = biome.get("base_tile_m", 4.0)
        alb, nor, rgh = self.material(base_key)
        alb = self._tiled(alb, res, extent, base_tile)
        nor = self._tiled(nor, res, extent, base_tile) if nor is not None else np.full((res, res, 3), [0.5, 0.5, 1.0], np.float32)
        rgh = self._tiled(rgh, res, extent, base_tile) if rgh is not None else np.full((res, res, 3), 0.9, np.float32)

        layers = getattr(cfg, "layers", None) or biome["layers"]
        applied = []
        for spec in layers:
            spec = dict(spec) if not isinstance(spec, dict) else spec
            key = spec["material"]
            try:
                oa, on, orr = self.material(key)
            except FileNotFoundError as e:
                logger.warning(str(e))
                continue
            tile = spec.get("tile_m", 3.0)
            oa = self._tiled(oa, res, extent, tile)
            on = self._tiled(on, res, extent, tile) if on is not None else np.full((res, res, 3), [0.5, 0.5, 1.0], np.float32)
            orr = self._tiled(orr, res, extent, tile) if orr is not None else np.full((res, res, 3), 0.9, np.float32)

            if spec.get("kind") == "trail":
                count = int(spec.get("count", 1))
                width = float(spec.get("width_m", 2.5))
                wps = spec.get("waypoints")
                m = np.zeros((res, res), np.float32)
                for _ in range(count):
                    pts = wps if wps else self._random_walk_uv(rng)
                    m = np.maximum(m, self._trail_mask(res, pts, width, extent, rng))
                    wps = None  # only first uses explicit; extras random
            else:  # patch
                cov = float(spec.get("coverage", 0.08))
                scale = float(spec.get("scale_m", 15.0))
                if randomize:
                    cov *= float(rng.uniform(0.7, 1.3))
                    scale *= float(rng.uniform(0.8, 1.25))
                m = self._patch_mask(res, cov, scale, rng, extent)

            m3 = m[..., None]
            alb = alb * (1 - m3) + oa * m3
            rgh = rgh * (1 - m3) + orr * m3
            nor = self._blend_normal(nor, on, m)
            applied.append(f"{key}:{spec.get('kind')}")

        self._write_maps(self._to8(alb), self._to8(nor), self._to8(rgh))
        self.set_uv(None)
        self.write_sdf(has_normal=True, has_rough=True)
        logger.info(f"ground: patchy biome={biome_name} seed={seed} res={res} base={base_key} layers={applied}")
        return {"mode": "patchy", "biome": biome_name, "seed": seed, "res": res,
                "base": base_key, "layers": applied}

    # ---- io --------------------------------------------------------------- #
    @staticmethod
    def _to8(a):
        return (np.clip(a, 0, 1) * 255).astype(np.uint8)

    def _write_maps(self, alb, nor, rgh):
        from PIL import Image
        self.texdir.mkdir(parents=True, exist_ok=True)
        for f in glob.glob(os.path.join(self.texdir, "*.png")) + glob.glob(os.path.join(self.texdir, "*.jpg")):
            os.remove(f)
        Image.fromarray(alb).save(self.texdir / "ground_Color.png")
        if nor is not None:
            Image.fromarray(nor).save(self.texdir / "ground_NormalGL.png")
        if rgh is not None:
            Image.fromarray(rgh).save(self.texdir / "ground_Roughness.png")

    def set_uv(self, scale: Optional[float]):
        """Rewrite terrain.obj UVs. scale=None -> 0..1 (baked); else x scale (tiled)."""
        verts, lines = [], []
        with open(self.obj) as f:
            for line in f:
                lines.append(line)
                if line.startswith("v "):
                    p = line.split()
                    verts.append((float(p[1]), float(p[2])))
        vx = np.array([v[0] for v in verts]); vy = np.array([v[1] for v in verts])
        u = (vx - vx.min()) / (vx.max() - vx.min())
        v = (vy - vy.min()) / (vy.max() - vy.min())
        if scale is not None:
            u, v = u * scale, v * scale
        out, vi = [], 0
        for line in lines:
            if line.startswith("vt "):
                out.append(f"vt {u[vi]:.6f} {v[vi]:.6f}\n"); vi += 1
            else:
                out.append(line)
        with open(self.obj, "w") as f:
            f.writelines(out)

    def write_sdf(self, has_normal: bool = True, has_rough: bool = True):
        maps = ["                        <albedo_map>model://ground/texture/ground_Color.png</albedo_map>"]
        if has_normal:
            maps.append("                        <normal_map>model://ground/texture/ground_NormalGL.png</normal_map>")
        if has_rough:
            maps.append("                        <roughness_map>model://ground/texture/ground_Roughness.png</roughness_map>")
        maps_str = "\n".join(maps)
        sdf = f'''<?xml version="1.0" ?>
<sdf version="1.8">
    <model name="terrain">
        <static>true</static>
        <link name="link">
            <collision name="collision">
                <geometry><mesh><uri>model://ground/mesh/terrain.stl</uri></mesh></geometry>
            </collision>
            <visual name="visual">
                <geometry><mesh><uri>model://ground/mesh/terrain.obj</uri></mesh></geometry>
                <material>
                    <ambient>1.0 1.0 1.0 1</ambient>
                    <diffuse>1.0 1.0 1.0 1</diffuse>
                    <specular>0.1 0.1 0.1 1</specular>
                    <pbr><metal>
{maps_str}
                        <metalness>0.0</metalness>
                    </metal></pbr>
                </material>
            </visual>
        </link>
    </model>
</sdf>'''
        (self.ground_dir / "model.sdf").write_text(sdf)


def write_water_model(models_dir: Path, extent_m: Tuple[float, float], level: float) -> Path:
    """Write a flat translucent water plane model at Z=level covering the terrain.

    A simple visual approximation (no waves/refraction) suitable for flooding low
    areas in a sim scenario.
    """
    wdir = Path(models_dir) / "water"
    wdir.mkdir(parents=True, exist_ok=True)
    sx, sy = extent_m[0] * 1.1, extent_m[1] * 1.1
    (wdir / "model.config").write_text(
        '<?xml version="1.0"?>\n<model>\n  <name>water</name>\n  <version>1.0</version>\n'
        '  <sdf version="1.8">model.sdf</sdf>\n  <description>Flat water plane</description>\n</model>\n'
    )
    (wdir / "model.sdf").write_text(f'''<?xml version="1.0" ?>
<sdf version="1.8">
    <model name="water">
        <static>true</static>
        <pose>0 0 {level:.3f} 0 0 0</pose>
        <link name="link">
            <visual name="visual">
                <geometry><plane><normal>0 0 1</normal><size>{sx:.2f} {sy:.2f}</size></plane></geometry>
                <material>
                    <ambient>0.10 0.22 0.34 1</ambient>
                    <diffuse>0.12 0.32 0.46 0.78</diffuse>
                    <specular>0.5 0.5 0.6 1</specular>
                    <pbr><metal><metalness>0.1</metalness><roughness>0.12</roughness></metal></pbr>
                </material>
            </visual>
        </link>
    </model>
</sdf>''')
    return wdir
