"""Seeded rig flight CLI subcommand (docs/SENSOR_RIG_PLAN.md Phase 2)."""

from pathlib import Path

import click

from wildseed.core.fly import (PATTERNS, TerrainSampler, play_trajectory,
                               synthesize, write_trajectory)


@click.command()
@click.option("--pattern", "-p", type=click.Choice(PATTERNS), default="orbit",
              help="Flight pattern. Default: orbit")
@click.option("--seed", type=int, default=0,
              help="Trajectory seed (same seed -> byte-identical trajectory).")
@click.option("--speed", type=float, default=5.0, help="Target speed, m/s.")
@click.option("--agl", type=float, default=12.0,
              help="Height above ground (terrain-following), metres.")
@click.option("--rate", type=float, default=30.0, help="Samples per second.")
@click.option("--margin", type=float, default=15.0,
              help="Keep-out border from the terrain edge, metres.")
@click.option("--center", type=str, default=None,
              help="Pattern centre 'x,y' (default: terrain centre).")
@click.option("--radius", type=float, default=None,
              help="Orbit radius, metres (default: 30%% of terrain span).")
@click.option("--base-path", "-b", type=click.Path(exists=True), default=".",
              help="Project base (models/ + worlds/). Default: cwd")
@click.option("--out", "-o", type=click.Path(), default=None,
              help="Trajectory JSON path. Default: "
                   "worlds/trajectory_<pattern>_<seed>.json")
@click.option("--play", is_flag=True,
              help="Also fly it: drive the rig via /world/<world>/set_pose, "
                   "paced by sim time (needs a running gz server + gz python).")
@click.option("--world", default="forest_world",
              help="World name for --play. Default: forest_world")
@click.option("--model", default="sensor_rig",
              help="Model to move for --play. Default: sensor_rig")
@click.pass_context
def fly(ctx, pattern, seed, speed, agl, rate, margin, center, radius,
        base_path, out, play, world, model):
    """Synthesize (and optionally fly) a seeded rig trajectory.

    The trajectory is written to disk BEFORE any playback: the seed defines
    the file, the file defines the flight. Kinematic playback is for camera
    work — IMU data during set_pose flight is meaningless by construction
    (that is Phase 4's dynamic mode).

    \b
    Examples:
        wildseed fly --pattern orbit --seed 7
        wildseed fly -p flythrough --agl 8 --speed 6 --play
    """
    console = ctx.obj["console"]
    base = Path(base_path)

    stl = base / "models" / "ground" / "mesh" / "terrain.stl"
    if not stl.exists():
        raise click.ClickException(
            f"terrain mesh not found: {stl}\nGenerate terrain first "
            "(wildseed terrain/terraingen) — the flight follows its heights.")

    center_xy = None
    if center:
        try:
            cx, cy = (float(v) for v in center.split(","))
            center_xy = (cx, cy)
        except ValueError:
            raise click.ClickException("--center must be 'x,y'")

    console.print(f"[bold]fly[/bold] pattern=[cyan]{pattern}[/cyan] seed={seed} "
                  f"speed={speed} agl={agl}")
    terrain = TerrainSampler(stl)
    traj = synthesize(pattern, seed, terrain, speed=speed, agl=agl, rate=rate,
                      margin=margin, center=center_xy, radius=radius)

    out_path = Path(out) if out else (
        base / "worlds" / f"trajectory_{pattern}_{seed}.json")
    write_trajectory(traj, out_path)
    console.print(f"[green]trajectory[/green] {traj['count']} poses, "
                  f"{traj['duration']:.1f}s -> [cyan]{out_path}[/cyan]")

    if play:
        try:
            calls = play_trajectory(traj, world=world, model=model)
        except ImportError as e:
            raise click.ClickException(
                f"gz python bindings unavailable ({e}); run --play inside the "
                "wildseed/wildseed:egl containers next to a running server.")
        except RuntimeError as e:
            raise click.ClickException(str(e))
        console.print(f"[green]flight complete[/green] ({calls} pose updates)")
