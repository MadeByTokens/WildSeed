"""Procedural ground material CLI subcommand."""

import click
from pathlib import Path

from forest3d.config.loader import load_config
from forest3d.config.schema import GroundConfig


@click.command()
@click.option("--ground-dir", "-g", type=click.Path(), default="./models/ground",
              help="Terrain model dir (must already contain mesh/terrain.obj). Default: ./models/ground")
@click.option("--texture-root", "-t", type=click.Path(), default="./Blender-Assets/soil",
              help="Directory of CC0 ground texture packs. Default: ./Blender-Assets/soil")
@click.option("--mode", type=click.Choice(["uniform", "patchy"]), default=None,
              help="uniform (crisp tiled) or patchy (seeded baked composite).")
@click.option("--biome", type=click.Choice(["grassland", "desert", "gravel", "snow"]), default=None,
              help="Biome preset.")
@click.option("--seed", type=int, default=None, help="RNG seed (same seed -> same ground).")
@click.option("--res", "resolution", type=int, default=None, help="Patchy bake resolution px (default 4096).")
@click.option("--base", "base_material", default=None, help="Override biome base material key.")
@click.option("--uniform-tile", type=float, default=None, help="Uniform-mode UV tiling.")
@click.option("--no-randomize", is_flag=True, default=False, help="Disable per-seed patch jitter.")
@click.option("--water-level", type=float, default=None, help="Add a flat water plane at this terrain-Z (m).")
@click.option("--models-dir", type=click.Path(), default="./models", help="Models root (for water). Default: ./models")
@click.pass_context
def ground(ctx, ground_dir, texture_root, mode, biome, seed, resolution, base_material,
           uniform_tile, no_randomize, water_level, models_dir):
    """Generate the terrain ground PBR material (uniform or patchy/seeded).

    Operates on an already-generated terrain (run `forest3d terrain` first).
    Reproducible: the same --seed yields the same ground, so randomized worlds
    for VIO/lidar testing can be regenerated exactly.

    \b
    Examples:
        # crisp uniform grass
        forest3d ground --mode uniform --biome grassland
        # seeded patchy scenario (trails + sand/gravel/pebble patches)
        forest3d ground --mode patchy --biome grassland --seed 42
        # a different random scenario, same biome
        forest3d ground --mode patchy --biome grassland --seed 99
        # snow biome with a flooded low area
        forest3d ground --mode patchy --biome snow --seed 7 --water-level 5.0
    """
    console = ctx.obj["console"]
    logger = ctx.obj["logger"]
    config = load_config(ctx.obj.get("config_path"))

    gc = config.terrain.ground or GroundConfig()
    if mode is not None:
        gc.mode = mode
    if biome is not None:
        gc.biome = biome
    if seed is not None:
        gc.seed = seed
    if resolution is not None:
        gc.resolution = resolution
    if base_material is not None:
        gc.base_material = base_material
    if uniform_tile is not None:
        gc.uniform_tile = uniform_tile
    if no_randomize:
        gc.randomize = False
    if water_level is not None:
        gc.water_level = water_level

    gdir = Path(ground_dir)
    if not (gdir / "mesh" / "terrain.obj").exists():
        raise click.ClickException(
            f"{gdir}/mesh/terrain.obj not found. Run `forest3d terrain --dem ...` first."
        )
    troot = Path(gc.texture_root) if gc.texture_root else Path(texture_root)
    if not troot.exists():
        raise click.ClickException(f"Texture root not found: {troot}")

    from forest3d.core.ground import GroundCompositor, write_water_model

    console.print(f"[bold]Ground material[/bold]  mode=[cyan]{gc.mode}[/cyan] biome=[cyan]{gc.biome}[/cyan] "
                  f"seed=[cyan]{gc.seed}[/cyan]")
    comp = GroundCompositor(ground_dir=gdir, texture_root=troot, config=gc)
    try:
        info = comp.generate()
    except FileNotFoundError as e:
        raise click.ClickException(str(e))

    if gc.water_level is not None:
        ex = comp._extent_m()
        wdir = write_water_model(Path(models_dir), ex, gc.water_level)
        console.print(f"  water plane @ z={gc.water_level} -> [cyan]{wdir}[/cyan] "
                      f"(add <include><uri>model://water</uri></include> to your world)")

    console.print(f"[green]Success![/green] {info}")
    console.print(f"[dim]Textures -> {gdir}/texture/ ; SDF updated.[/dim]")
