"""Tests for the procedural ground config + compositor biome registry."""

import pytest

from forest3d.config.schema import GroundConfig, GroundLayerSpec, TerrainConfig


def test_ground_defaults():
    g = GroundConfig()
    assert g.mode == "uniform"
    assert g.biome == "grassland"
    assert g.seed == 0
    assert g.randomize is True


def test_mode_validation():
    GroundConfig(mode="patchy")
    with pytest.raises(ValueError):
        GroundConfig(mode="lava")


def test_layer_kind_validation():
    GroundLayerSpec(material="Gravel023", kind="patch")
    GroundLayerSpec(material="Ground054", kind="trail")
    with pytest.raises(ValueError):
        GroundLayerSpec(material="x", kind="river")


def test_terrain_config_has_optional_ground():
    t = TerrainConfig()
    assert t.ground is None
    t2 = TerrainConfig(ground=GroundConfig(mode="patchy", biome="snow", seed=7))
    assert t2.ground.biome == "snow" and t2.ground.seed == 7


def test_biomes_registry_well_formed():
    from forest3d.core.ground import BIOMES
    for name, b in BIOMES.items():
        assert "base" in b and "layers" in b
        for layer in b["layers"]:
            assert layer["kind"] in ("patch", "trail")
            assert "material" in layer


def test_seed_reproducible_random_walk():
    """Same seed -> identical seeded geometry (reproducible scenarios)."""
    import numpy as np
    from forest3d.core.ground import GroundCompositor
    a = GroundCompositor._random_walk_uv(np.random.default_rng(42))
    b = GroundCompositor._random_walk_uv(np.random.default_rng(42))
    c = GroundCompositor._random_walk_uv(np.random.default_rng(43))
    assert a == b
    assert a != c
