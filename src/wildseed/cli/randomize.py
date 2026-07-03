"""Texture domain-randomization CLI subcommand."""

import click
from pathlib import Path

from rich.table import Table


@click.command()
@click.option("--models", "-m", "models_root", type=click.Path(exists=True),
              default="./models", help="Models root directory. Default: ./models")
@click.option("--categories", "-c", default="tree,bush,rock,grass",
              help="Comma-separated categories to randomize. Default: tree,bush,rock,grass")
@click.option("--variants", "-n", type=click.IntRange(1, 20), default=2,
              help="Recoloured variants per model. Default: 2")
@click.option("--seed", type=int, default=0,
              help="Master seed (same seed -> identical variants).")
@click.option("--strength", type=click.FloatRange(0.0, 1.0), default=0.5,
              help="HSV shift strength (hsv mode). Default: 0.5")
@click.option("--mode", type=click.Choice(["hsv", "wild"]), default="hsv",
              help="hsv = global hue/sat/value shift; wild = unrealistic random "
                   "duotone recolour (structure kept, colours arbitrary).")
@click.pass_context
def randomize(ctx, models_root, categories, variants, seed, strength, mode):
    """Create recoloured texture variants of converted models (domain randomization).

    Rewrites the base-colour textures embedded in each model's visual .glb and
    stamps out sibling model dirs named ``<model>_dr<k>``. The placement engine
    (``wildseed generate``) then treats every variant as one more species —
    randomized scenes without touching the source assets. Normal/roughness maps
    and foliage alpha cutouts are left untouched.

    \b
    Examples:
        wildseed randomize --variants 3 --seed 7
        wildseed randomize -c tree --mode wild --seed 42
    """
    console = ctx.obj["console"]
    from wildseed.core.texrand import randomize_models

    cats = [c.strip() for c in categories.split(",") if c.strip()]
    made = randomize_models(Path(models_root), cats, variants,
                            seed=seed, strength=strength, mode=mode)
    if not made:
        raise click.ClickException("No models found to randomize.")

    table = Table(title=f"Texture variants ({mode}, seed={seed})", show_header=True)
    table.add_column("Variant", style="cyan")
    for d in made:
        table.add_row(str(d.relative_to(Path(models_root))))
    console.print(table)
    console.print(f"[green]Success![/green] {len(made)} variant model(s) created.")
