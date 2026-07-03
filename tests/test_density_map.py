"""Grayscale density-map placement: pixel intensity steers where models go."""

import numpy as np
import pytest
from PIL import Image

from wildseed.core.forest import WorldPopulator


@pytest.fixture
def tiny_world(tmp_path):
    """Minimal base_path: a flat 2-triangle terrain + empty model dirs."""
    from stl import mesh as stl_mesh
    ground_mesh = tmp_path / "models" / "ground" / "mesh"
    ground_mesh.mkdir(parents=True)
    data = np.zeros(2, dtype=stl_mesh.Mesh.dtype)
    s = 40.0  # 80x80 m flat square at z=0
    data["vectors"][0] = [[-s, -s, 0], [s, -s, 0], [s, s, 0]]
    data["vectors"][1] = [[-s, -s, 0], [s, s, 0], [-s, s, 0]]
    stl_mesh.Mesh(data).save(str(ground_mesh / "terrain.stl"))
    for cat, models in {"tree": ["oak"], "grass": ["g1"]}.items():
        for m in models:
            (tmp_path / "models" / cat / m).mkdir(parents=True)
    (tmp_path / "worlds").mkdir()
    return tmp_path


def _map_png(path, arr):
    Image.fromarray(arr.astype(np.uint8), mode="L").save(path)
    return path


def _placed_xy(populator, category):
    return [(x, y) for x, y, _, _ in populator.placed_models[category]]


def test_half_black_map_confines_placement(tiny_world, tmp_path):
    """Left half black, right half white -> every instance lands at x >= 0."""
    arr = np.zeros((64, 64))
    arr[:, 32:] = 255
    mp = _map_png(tmp_path / "east.png", arr)
    pop = WorldPopulator(base_path=tiny_world, seed=7,
                         density_maps={"grass": mp})
    pop.create_forest_world({"grass": 40, "tree": 0})
    xy = _placed_xy(pop, "grass")
    assert len(xy) >= 30  # dense white half: nearly all should place
    assert all(x >= 0.0 for x, _ in xy)


def test_north_up_orientation(tiny_world, tmp_path):
    """Row 0 of the image is the +Y edge: white top half -> placements y >= 0."""
    arr = np.zeros((64, 64))
    arr[:32, :] = 255  # top half white
    mp = _map_png(tmp_path / "north.png", arr)
    pop = WorldPopulator(base_path=tiny_world, seed=7,
                         density_maps={"grass": mp})
    pop.create_forest_world({"grass": 30, "tree": 0})
    assert all(y >= 0.0 for _, y in _placed_xy(pop, "grass"))


def test_star_fallback_applies_to_unmapped_categories(tiny_world, tmp_path):
    arr = np.zeros((32, 32))
    arr[:, 16:] = 255
    mp = _map_png(tmp_path / "east.png", arr)
    pop = WorldPopulator(base_path=tiny_world, seed=3,
                         density_maps={"*": mp})
    pop.create_forest_world({"grass": 20, "tree": 5})
    for cat in ("grass", "tree"):
        assert all(x >= 0.0 for x, _ in _placed_xy(pop, cat)), cat


def test_seeded_map_placement_is_reproducible(tiny_world, tmp_path):
    arr = (np.linspace(0, 255, 64)[None, :] * np.ones((64, 1)))
    mp = _map_png(tmp_path / "grad.png", arr)

    def build():
        pop = WorldPopulator(base_path=tiny_world, seed=11,
                             density_maps={"grass": mp, "tree": mp})
        return pop.create_forest_world({"grass": 25, "tree": 6}).read_text()

    assert build() == build()


def test_gradient_map_biases_density(tiny_world, tmp_path):
    """Linear west->east ramp: mean x of placements must be clearly east."""
    arr = (np.linspace(0, 255, 64)[None, :] * np.ones((64, 1)))
    mp = _map_png(tmp_path / "grad.png", arr)
    pop = WorldPopulator(base_path=tiny_world, seed=5,
                         density_maps={"grass": mp})
    pop.create_forest_world({"grass": 60, "tree": 0})
    xs = [x for x, _ in _placed_xy(pop, "grass")]
    # ramp weighting puts the expectation at +1/6 of the extent (~13 m of 80)
    assert np.mean(xs) > 5.0


def test_all_black_map_rejected(tiny_world, tmp_path):
    mp = _map_png(tmp_path / "black.png", np.zeros((16, 16)))
    with pytest.raises(ValueError, match="all black"):
        WorldPopulator(base_path=tiny_world, seed=1, density_maps={"grass": mp})


def test_generate_cli_exposes_density_maps():
    from wildseed.cli.generate import generate
    names = {p.name for p in generate.params}
    assert "density_maps" in names
