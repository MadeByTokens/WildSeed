"""Texture domain randomization: GLB recolour variants + ground modes."""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from wildseed.core.texrand import (
    read_glb, write_glb, randomize_glb, randomize_model_dir, randomize_models,
)


# --------------------------------------------------------------------------- #
# fixtures: a minimal GLB with an RGBA basecolor + an RGB normal map embedded
# --------------------------------------------------------------------------- #
def _png(arr, mode):
    buf = BytesIO()
    Image.fromarray(arr, mode).save(buf, format="PNG")
    return buf.getvalue()


def _basecolor_png():
    arr = np.zeros((8, 8, 4), np.uint8)
    arr[..., 0] = 200  # red-ish
    arr[..., 1] = 60
    arr[..., 2] = 30
    arr[..., 3] = np.tile([255, 0], (8, 4))  # leaf-cutout-like alpha pattern
    return _png(arr, "RGBA")


def _normal_png():
    arr = np.full((8, 8, 3), [128, 128, 255], np.uint8)
    return _png(arr, "RGB")


def _minimal_glb(path):
    p1, p2 = _basecolor_png(), _normal_png()
    pad = b"\x00" * (-len(p1) % 4)
    binary = p1 + pad + p2
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(p1)},
            {"buffer": 0, "byteOffset": len(p1) + len(pad), "byteLength": len(p2)},
        ],
        "images": [{"bufferView": 0, "mimeType": "image/png"},
                   {"bufferView": 1, "mimeType": "image/png"}],
        "textures": [{"source": 0}, {"source": 1}],
        "materials": [{
            "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}},
            "normalTexture": {"index": 1},
        }],
    }
    write_glb(path, gltf, binary)
    return path


def _decode_image(glb_path, image_idx):
    gltf, binary = read_glb(glb_path)
    view = gltf["bufferViews"][gltf["images"][image_idx]["bufferView"]]
    off = view.get("byteOffset", 0)
    raw = binary[off:off + view["byteLength"]]
    return np.asarray(Image.open(BytesIO(raw)))


def test_glb_roundtrip(tmp_path):
    src = _minimal_glb(tmp_path / "a.glb")
    gltf, binary = read_glb(src)
    out = tmp_path / "b.glb"
    write_glb(out, gltf, binary)
    gltf2, binary2 = read_glb(out)
    assert gltf2 == gltf and binary2[:len(binary)] == binary


def test_randomize_glb_recolours_basecolor_keeps_alpha_and_normal(tmp_path):
    src = _minimal_glb(tmp_path / "a.glb")
    before_base = _decode_image(src, 0)
    before_normal = _decode_image(src, 1)
    out = tmp_path / "b.glb"
    n = randomize_glb(src, out, np.random.default_rng(7), strength=0.9)
    assert n == 1  # only the basecolor image
    after_base = _decode_image(out, 0)
    after_normal = _decode_image(out, 1)
    assert not np.array_equal(after_base[..., :3], before_base[..., :3])
    np.testing.assert_array_equal(after_base[..., 3], before_base[..., 3])  # alpha intact
    np.testing.assert_array_equal(after_normal, before_normal)  # normal untouched


def test_randomize_glb_deterministic(tmp_path):
    src = _minimal_glb(tmp_path / "a.glb")
    o1, o2, o3 = (tmp_path / f"{n}.glb" for n in "123")
    randomize_glb(src, o1, np.random.default_rng(7))
    randomize_glb(src, o2, np.random.default_rng(7))
    randomize_glb(src, o3, np.random.default_rng(8))
    assert o1.read_bytes() == o2.read_bytes()
    assert o1.read_bytes() != o3.read_bytes()


def test_randomize_glb_wild_mode(tmp_path):
    src = _minimal_glb(tmp_path / "a.glb")
    out = tmp_path / "w.glb"
    randomize_glb(src, out, np.random.default_rng(3), mode="wild")
    after = _decode_image(out, 0)
    assert not np.array_equal(after[..., :3], _decode_image(src, 0)[..., :3])
    np.testing.assert_array_equal(after[..., 3], _decode_image(src, 0)[..., 3])


# --------------------------------------------------------------------------- #
# model-dir variants
# --------------------------------------------------------------------------- #
def _fake_model(models_root, cat, name):
    mdir = models_root / cat / name
    (mdir / "mesh").mkdir(parents=True)
    _minimal_glb(mdir / "mesh" / f"{name}.glb")
    (mdir / "mesh" / f"{name}_collision.glb").write_bytes(
        (mdir / "mesh" / f"{name}.glb").read_bytes())
    (mdir / "model.sdf").write_text(
        f'<model name="{name}"><uri>mesh/{name}.glb</uri>'
        f'<uri>mesh/{name}_collision.glb</uri></model>')
    (mdir / "model.config").write_text(f"<model><name>{name}</name></model>")
    return mdir


def test_randomize_model_dir_renames_everything(tmp_path):
    mdir = _fake_model(tmp_path / "models", "tree", "oak")
    out = randomize_model_dir(mdir, "oak_dr0", np.random.default_rng(1))
    assert (out / "mesh" / "oak_dr0.glb").exists()
    assert (out / "mesh" / "oak_dr0_collision.glb").exists()
    assert not (out / "mesh" / "oak.glb").exists()
    sdf = (out / "model.sdf").read_text()
    assert "mesh/oak_dr0.glb" in sdf and "mesh/oak.glb" not in sdf
    assert "oak_dr0" in (out / "model.config").read_text()


def test_randomize_models_walks_categories_and_is_deterministic(tmp_path):
    root = tmp_path / "models"
    _fake_model(root, "tree", "oak")
    _fake_model(root, "rock", "r1")
    made = randomize_models(root, ["tree", "rock"], variants=2, seed=5)
    assert {d.name for d in made} == {"oak_dr0", "oak_dr1", "r1_dr0", "r1_dr1"}
    b1 = (root / "tree" / "oak_dr0" / "mesh" / "oak_dr0.glb").read_bytes()
    # re-run: variants regenerate identically, and _dr dirs are not re-sourced
    made2 = randomize_models(root, ["tree", "rock"], variants=2, seed=5)
    assert len(made2) == 4
    assert (root / "tree" / "oak_dr0" / "mesh" / "oak_dr0.glb").read_bytes() == b1


# --------------------------------------------------------------------------- #
# ground: hsv jitter + wild mode
# --------------------------------------------------------------------------- #
@pytest.fixture
def terrain_dir(tmp_path):
    gdir = tmp_path / "ground"
    (gdir / "mesh").mkdir(parents=True)
    (gdir / "mesh" / "terrain.obj").write_text(
        "v -40 -40 0\nv 40 -40 0\nv 40 40 0\nv -40 40 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1/1 2/2 3/3 4/4\n")
    return gdir


def _fake_texture_root(tmp_path):
    troot = tmp_path / "soil"
    troot.mkdir()
    rng = np.random.default_rng(0)
    arr = (rng.random((16, 16, 3)) * 255).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(troot / "FakeMat_Color.png")
    return troot


def test_uniform_hsv_jitter_changes_albedo(tmp_path, terrain_dir):
    from wildseed.config.schema import GroundConfig
    from wildseed.core.ground import GroundCompositor
    troot = _fake_texture_root(tmp_path)

    def bake(jitter):
        cfg = GroundConfig(mode="uniform", base_material="FakeMat",
                           hsv_jitter=jitter, seed=3)
        GroundCompositor(terrain_dir, troot, cfg).generate()
        return (terrain_dir / "texture" / "ground_Color.png").read_bytes()

    plain = bake(0.0)
    shifted = bake(0.9)
    assert plain != shifted
    assert bake(0.9) == shifted  # seeded -> reproducible


def test_wild_mode_needs_no_texture_packs(tmp_path, terrain_dir):
    from wildseed.config.schema import GroundConfig
    from wildseed.core.ground import GroundCompositor
    empty = tmp_path / "nowhere"

    def bake(seed):
        cfg = GroundConfig(mode="wild", seed=seed, resolution=512)
        info = GroundCompositor(terrain_dir, empty, cfg).generate()
        assert info["mode"] == "wild"
        return (terrain_dir / "texture" / "ground_Color.png").read_bytes()

    a = bake(1)
    assert bake(1) == a       # deterministic
    assert bake(2) != a       # new seed, new ground
    assert (terrain_dir / "model.sdf").exists()


def test_schema_accepts_wild_and_jitter():
    from wildseed.config.schema import GroundConfig
    g = GroundConfig(mode="wild", hsv_jitter=0.5)
    assert g.mode == "wild" and g.hsv_jitter == 0.5
    with pytest.raises(ValueError):
        GroundConfig(hsv_jitter=1.5)


def test_cli_registers_randomize():
    from wildseed.cli.main import main as cli_main
    assert "randomize" in cli_main.commands
