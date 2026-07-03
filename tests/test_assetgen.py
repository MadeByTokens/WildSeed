"""Procedural asset generation: spec plumbing (Blender-side runs are gated)."""

import json

import pytest

from wildseed.core.assetgen import (
    KINDS, KIND_CATEGORY, _BLENDER_SCRIPT, converter_config, generate_blends,
)
from wildseed.core.converter import find_blender

BLENDER = find_blender()


def test_every_kind_maps_to_a_placement_category():
    assert set(KIND_CATEGORY.values()) <= {"rock", "tree", "bush", "grass"}
    assert {"rock", "boulder", "tree", "conifer", "bush", "grass"} == set(KINDS)


def test_blender_script_has_a_builder_per_kind():
    for kind in KINDS:
        assert f'"{kind}"' in _BLENDER_SCRIPT


def test_unknown_kind_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown kind"):
        generate_blends("/usr/bin/false", tmp_path, "cactus", 1)


def test_converter_config_keeps_full_visual_detail():
    cfg = converter_config()
    for cat in ("rock", "tree", "bush", "grass"):
        assert cfg.resolve_category(cat).visual_decimation == 1.0
    assert cfg.resolve_category("rock").collision_strategy == "convex_hull"
    assert cfg.resolve_category("tree").collision_strategy == "trunk_cylinder"
    # generated grass/bush inherit the passable + laser_retro defaults
    assert cfg.resolve_category("grass").passable is True
    assert cfg.resolve_category("grass").laser_retro == 4.0


def test_child_seeds_are_extensible(tmp_path, monkeypatch):
    """count=5 must reuse the count=3 child seeds for the first 3 assets."""
    captured = []

    def fake_run(cmd, **kw):
        script = open(cmd[cmd.index("--python") + 1]).read()
        specs = json.loads(script.split('json.loads("""')[1].split('""")')[0])
        captured.append(specs)
        for s in specs:
            open(s["out"], "w").write("stub")
        class R:
            stdout = stderr = ""
        return R()

    import wildseed.core.assetgen as ag
    monkeypatch.setattr(ag.subprocess, "run", fake_run)
    generate_blends("blender", tmp_path / "a", "rock", 3, seed=7)
    generate_blends("blender", tmp_path / "b", "rock", 5, seed=7)
    seeds3 = [s["seed"] for s in captured[0]]
    seeds5 = [s["seed"] for s in captured[1]]
    assert seeds5[:3] == seeds3
    assert len(set(seeds5)) == 5


def test_cli_registers_assetgen():
    from wildseed.cli.main import main as cli_main
    assert "assetgen" in cli_main.commands


@pytest.mark.skipif(BLENDER is None, reason="Blender not installed")
def test_full_generation_smoke(tmp_path):
    blends = generate_blends(BLENDER, tmp_path, "rock", 1, seed=1)
    assert blends[0].exists() and blends[0].stat().st_size > 0
