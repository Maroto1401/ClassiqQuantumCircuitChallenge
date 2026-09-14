"""Command line. Every stage is separately invocable -- that is what makes
re-scoring free."""
from __future__ import annotations

import json
from pathlib import Path

import click

from . import cover as cover_mod
from . import lower as lower_mod
from .io import load_target, synthetic_target
from .leaderboard import render
from .metrics import BASES, DEFAULT_BASIS
from .pipeline import Pipeline
from .store import Store


def _spec(target: str | None):
    return synthetic_target() if target in (None, "synthetic") else load_target(target)


@click.group()
@click.option("--store", default="data/artifacts", help="artifact root")
@click.option("--target", default=None, help="path to target image, or 'synthetic'")
@click.pass_context
def cli(ctx, store, target):
    ctx.obj = Pipeline(spec=_spec(target), store=Store(Path(store)))
    click.echo(f"# spec: {ctx.obj.spec}", err=True)


@cli.command()
@click.option("--force", is_flag=True)
@click.pass_obj
def diag(pipe, force):
    """Phase 1 diagnostics: density, symmetry, GF(2) rank, ANF."""
    click.echo(json.dumps(pipe.diagnostics(force=force), indent=2, default=str))


@cli.command("covers")
def list_covers():
    """List registered cover and lowering strategies."""
    click.echo(f"covers:    {cover_mod.available()}")
    click.echo(f"lowerings: {lower_mod.available()}")
    click.echo(f"bases:     {sorted(BASES)}")


@cli.command()
@click.option("--cover", default="pprm")
@click.option("--lowering", default="serial_mcz")
@click.option("--params", default="{}", help="JSON dict of cover params")
@click.option("--basis", default=DEFAULT_BASIS)
@click.pass_obj
def run(pipe, cover, lowering, params, basis):
    """Full pipeline for one (cover, lowering) pair."""
    res = pipe.run(cover, lowering, cover_params=json.loads(params), bases=[basis])
    click.echo(json.dumps(res, indent=2, default=str))


@cli.command()
@click.option("--basis", default=DEFAULT_BASIS)
@click.option("--opt-level", default=3)
@click.pass_obj
def score(pipe, basis, opt_level):
    """Re-score EVERY stored circuit. No re-synthesis. This is the point."""
    for key in pipe.store.all_circuits():
        pipe.score_circuit(key, bases=[basis], opt_level=opt_level)
    click.echo(render(pipe.store, basis))


@cli.command()
@click.option("--basis", default=DEFAULT_BASIS)
@click.pass_obj
def leaderboard(pipe, basis):
    """Ranked table from stored artifacts."""
    click.echo(render(pipe.store, basis))


if __name__ == "__main__":
    cli()
