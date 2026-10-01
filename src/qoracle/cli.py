"""Command line. Every stage is separately invocable -- that is what makes
re-scoring free."""
from __future__ import annotations

import json
from pathlib import Path

import click

from . import cover as cover_mod
from . import lower as lower_mod
from .io import load_target, logo_target, synthetic_target
from .leaderboard import render
from .metrics import BASES, DEFAULT_BASIS
from .pipeline import Pipeline
from .store import Store


def _spec(target: str | None):
    if target in (None, "logo"):
        return logo_target()
    if target == "synthetic":
        return synthetic_target()
    return load_target(target)


@click.group()
@click.option("--store", default="data/artifacts", help="artifact root")
@click.option("--target", default=None, help="path to target image, 'logo' (default), or 'synthetic'")
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


@cli.command("classiq-score")
@click.option("--circuit-key", required=True, help="circuit key, e.g. from `qo run`")
@click.option("--basis", default=DEFAULT_BASIS)
@click.pass_obj
def classiq_score_cmd(pipe, circuit_key, basis):
    """Score ONE stored circuit with Classiq's own AUTO_OPTIMIZE compiler.

    Authoritative vs. metrics.py's Qiskit proxy, but needs `pip install -e
    ".[classiq]"` and a prior `classiq.authenticate()` on this machine.
    """
    from . import classiq_score as cq
    qc = pipe.store.load_circuit(circuit_key)
    res = cq.score(qc, basis=basis).as_dict()
    pipe.store.write_side(circuit_key, "metrics_classiq.json", res)
    click.echo(json.dumps(res, indent=2))


@cli.command("native-run")
@click.option("--name", required=True, help="registered classiq_native model, e.g. 'rectangles'")
@click.pass_context
def native_run(ctx, name):
    """Track B: build+synthesize+score a Classiq-native qmod model (bypasses PhaseIR).

    Needs `pip install -e ".[classiq]"` and a prior `classiq.authenticate()`.
    """
    from . import classiq_native as cn
    res = cn.run(name)
    click.echo(json.dumps(res, indent=2))


@cli.command("native-list")
def native_list():
    """List registered Track B (classiq_native) models."""
    from . import classiq_native as cn
    click.echo(f"classiq_native models: {cn.available()}")


if __name__ == "__main__":
    cli()
