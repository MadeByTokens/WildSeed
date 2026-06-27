"""Seeded procedural terrain synthesis: reproducibility, presets, sanity.

Reproducibility is asserted on the read-back DEM array (not file bytes): GDAL can
embed library/version tags that vary, which would make a byte-compare flaky.
Relief is asserted on the synthesizer's own array (not the meshed output): the
terrain pipeline applies its own gaussian_filter to every DEM, so the meshed
z-extent is slightly less than amplitude_m.
"""

import numpy as np
import pytest

from forest3d.config.schema import TerrainGenConfig, PRESET_NAMES
from forest3d.core.terraingen import TerrainSynthesizer, PRESETS, GDAL_AVAILABLE


def _synth(**kw):
    cfg = TerrainGenConfig(resolution=96, **kw)
    return TerrainSynthesizer(cfg).synthesize()


def test_seed_reproducible_array():
    a, _ = _synth(preset="hilly", seed=42)
    b, _ = _synth(preset="hilly", seed=42)
    assert np.array_equal(a, b)


def test_different_seed_differs():
    a, _ = _synth(preset="hilly", seed=1)
    b, _ = _synth(preset="hilly", seed=2)
    assert not np.array_equal(a, b)


def test_min_is_zero_and_finite():
    H, _ = _synth(preset="mountainous", seed=5)
    assert np.isfinite(H).all()
    assert float(H.min()) == pytest.approx(0.0, abs=1e-4)
    assert float(H.max()) > 0.0


def test_amplitude_drives_relief():
    small, _ = _synth(preset="hilly", seed=3, amplitude_m=10.0,
                      n_peaks=0, n_basins=0, n_creeks=0)
    big, _ = _synth(preset="hilly", seed=3, amplitude_m=60.0,
                    n_peaks=0, n_basins=0, n_creeks=0)
    assert np.ptp(big) > np.ptp(small) * 3


def test_preset_registry_matches_schema():
    assert set(PRESET_NAMES) == set(PRESETS.keys())


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_every_preset_synthesizes(preset):
    H, lakes = _synth(preset=preset, seed=7)
    assert np.isfinite(H).all()
    assert float(H.min()) == pytest.approx(0.0, abs=1e-4)
    if preset == "lakeland":
        assert len(lakes) >= 1


def test_lakeland_emits_lake_levels():
    _, lakes = _synth(preset="lakeland", seed=11)
    assert lakes
    for lk in lakes:
        assert lk["suggested_water_level"] > lk["floor_z"]
        assert "center_xy_m" in lk and "radius_m" in lk


def test_basin_carves_depression():
    flat, _ = _synth(preset="hilly", seed=9, amplitude_m=20.0, n_basins=0)
    pit, lakes = _synth(preset="hilly", seed=9, amplitude_m=20.0, n_basins=1)
    # a basin should create a local minimum near a recorded center
    assert lakes
    ci, ri = lakes[0]["center_px"]
    assert pit[ri, ci] < np.median(pit)


@pytest.mark.skipif(not GDAL_AVAILABLE, reason="GDAL not installed")
def test_geotiff_roundtrip(tmp_path):
    from osgeo import gdal
    cfg = TerrainGenConfig(resolution=96, preset="hilly", seed=4)
    synth = TerrainSynthesizer(cfg)
    H, lakes = synth.synthesize()
    out = tmp_path / "synth.tif"
    synth.write_geotiff(H, out, lakes)
    assert out.exists()
    ds = gdal.Open(str(out))
    assert ds.RasterXSize == 96 and ds.RasterYSize == 96
    gt = ds.GetGeoTransform()
    assert abs(gt[1]) == pytest.approx(2.5)
    back = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    assert np.allclose(back, H, atol=1e-4)


@pytest.mark.skipif(not GDAL_AVAILABLE, reason="GDAL not installed")
def test_geotiff_seed_reproducible(tmp_path):
    from osgeo import gdal

    def write(seed, name):
        cfg = TerrainGenConfig(resolution=96, preset="lakeland", seed=seed)
        s = TerrainSynthesizer(cfg)
        H, lakes = s.synthesize()
        p = tmp_path / name
        s.write_geotiff(H, p, lakes)
        ds = gdal.Open(str(p))
        arr = ds.GetRasterBand(1).ReadAsArray()
        ds = None
        return arr

    assert np.array_equal(write(7, "a.tif"), write(7, "b.tif"))
    assert not np.array_equal(write(7, "c.tif"), write(8, "d.tif"))
