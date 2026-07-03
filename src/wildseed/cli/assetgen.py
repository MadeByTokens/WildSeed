"""Procedural asset generation CLI subcommand."""

import click
from pathlib import Path

from wildseed.core.assetgen import KINDS, KIND_CATEGORY, generate_blends, convert_assets


@click.command()
@click.option("--kind", "-k", type=click.Choice(list(KINDS) + ["all"]), default="all",
              help="Asset kind to generate (boulder/conifer are big-rock/pine "
                   "variants of rock/tree). Default: all")
@click.option("--count", "-n", type=click.IntRange(1, 100), default=3,
              help="Assets per kind. Default: 3")
@click.option("--seed", type=int, default=0,
              help="Master seed (same seed -> same assets; count is extensible).")
@click.option("--out", "out_dir", type=click.Path(), default="./Blender-Assets/generated",
              help="Where .blend files are written. Default: ./Blender-Assets/generated")
@click.option("--models", "models_dir", type=click.Path(), default="./models",
              help="Models root for conversion. Default: ./models")
@click.option("--convert/--no-convert", default=True,
              help="Also convert to Gazebo models (default: convert).")
@click.pass_context
def assetgen(ctx, kind, count, seed, out_dir, models_dir, convert):
    """Generate parametric assets in Blender (no downloads, no artists).

    Seeded procedural rocks, boulders, trees, conifers, bushes and grass
    clumps: noise-displaced icospheres, tapered cones and hand-built blade
    meshes with solid-colour PBR materials (no textures, no alpha foliage).
    Combined with `wildseed randomize` this yields fully synthetic scene
    content for domain randomization.

    \b
    Examples:
        wildseed assetgen --kind rock -n 5 --seed 42
        wildseed assetgen --kind all -n 3       # 3 of each kind
        wildseed assetgen -k conifer -n 4 --no-convert
    """
    console = ctx.obj["console"]
    config = None
    try:
        from wildseed.config.loader import load_config
        config = load_config(ctx.obj.get("config_path"))
    except Exception:
        pass

    blender = (config.blender.path if config and config.blender.path else None)
    if blender is None:
        from wildseed.core.converter import find_blender
        blender = find_blender()
    if blender is None:
        raise click.ClickException(
            "Blender not found (install it, set blender.path in config, or run "
            "inside the wildseed:egl image).")

    kinds = list(KINDS) if kind == "all" else [kind]
    total = 0
    for k in kinds:
        console.print(f"[bold]assetgen[/bold] kind=[cyan]{k}[/cyan] count={count} seed={seed}")
        blends = generate_blends(Path(blender), Path(out_dir), k, count, seed=seed)
        for b in blends:
            console.print(f"  blend -> [dim]{b}[/dim]")
        if convert:
            dirs = convert_assets(Path(blender), blends, k, Path(models_dir))
            for d in dirs:
                console.print(f"  model -> [cyan]{d}[/cyan]")
            total += len(dirs)
        else:
            total += len(blends)
    console.print(f"[green]Success![/green] {total} asset(s) "
                  f"({'converted' if convert else 'blend only'}).")
    if convert:
        console.print("[dim]They join placement like any other model "
                      "(categories: " +
                      ", ".join(sorted(set(KIND_CATEGORY[k] for k in kinds))) + ").[/dim]")
