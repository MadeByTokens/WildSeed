"""Master-seed scenario resolution: deterministic, seed-sensitive, well-formed."""

import pytest

from forest3d.core.scenario import (BIOME_NAMES, BIOME_SPACE, SCENARIO_FORMAT,
                                    palette_from_manifest, resolve_scenario)


def test_same_seed_same_spec():
    a = resolve_scenario(42)
    b = resolve_scenario(42)
    assert a == b


def test_different_seed_different_spec():
    a = resolve_scenario(42)
    b = resolve_scenario(43)
    assert a != b
    # the stage seeds must differ too (not just the drawn params)
    assert a["stage_seeds"] != b["stage_seeds"]


def test_stage_seeds_are_independent():
    seeds = resolve_scenario(7)["stage_seeds"]
    assert len(set(seeds.values())) == 3, "spawned stage seeds must not collide"


def test_biome_override_keeps_format_and_knob_envelope():
    spec = resolve_scenario(7, biome="alpine")
    assert spec["biome"] == "alpine"
    assert spec["scenario_format"] == SCENARIO_FORMAT
    space = BIOME_SPACE["alpine"]
    for knob, (lo, hi) in space["knobs"].items():
        assert lo <= spec["terrain_knobs"][knob] <= hi
    assert spec["preset"] in space["presets"]


def test_explicit_preset_override_wins():
    spec = resolve_scenario(7, biome="temperate", preset="flat")
    assert spec["preset"] == "flat"


def test_density_scale_scales_counts():
    base = resolve_scenario(7, biome="temperate")
    double = resolve_scenario(7, biome="temperate", density_scale=2.0)
    for cat, count in base["density"].items():
        assert double["density"][cat] == pytest.approx(count * 2, abs=1)


def test_all_biomes_resolve():
    for biome in BIOME_NAMES:
        spec = resolve_scenario(1, biome=biome)
        assert spec["ground_biome"] in ("grassland", "desert", "gravel", "snow")
        assert all(v >= 0 for v in spec["density"].values())


def test_unknown_biome_raises():
    with pytest.raises(ValueError):
        resolve_scenario(1, biome="lunar")


def test_scenario_cli_registered():
    from forest3d.cli.main import main
    assert "scenario" in main.commands


def test_palette_from_manifest_covers_dod(tmp_path=None):
    """Every biome palette must give placement >=3 tree + >=2 understory species
    (the variety floor that breaks repeated-model VIO feature aliasing)."""
    from pathlib import Path
    manifest = Path(__file__).parent.parent / "assets" / "manifest.yaml"
    if not manifest.exists():
        pytest.skip("assets/manifest.yaml not present")
    for biome in BIOME_NAMES:
        pal = palette_from_manifest(manifest, biome)
        assert len(pal["tree"]) >= 3, f"{biome}: <3 tree species"
        assert len(pal["bush"]) + len(pal["grass"]) >= 2, f"{biome}: <2 understory species"
