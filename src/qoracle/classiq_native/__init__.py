"""Track B: models built directly in Classiq's qmod language and synthesized by
Classiq's OWN compiler (not our PhaseIR pipeline in `cover/`, `lower/`).

WHY THIS TRACK EXISTS. `cover/` + `lower/` (Track A) treat the target as an
opaque 4096-entry Boolean truth table and minimise it (ESOP, GF(2) rank
factorisation). That throws away the fact that the logo is 4 simple geometric
primitives (2 rectangles + 2 discs). Classiq's `control()` on QNum arithmetic
conditions (`x >= lo`, quadratic disc predicates, ...) lets the SYNTHESIZER see
that geometry directly and its own depth-optimizing compiler exploit it -- this
beat Track A's best result (6337/3609) on the first, completely unoptimized
attempt (5329/3502, see `rectangles.py`). Confirmed empirically, 2026-09-14.

Each module here (`rectangles.py`, `rectangles_grouped.py`, `primitives.py`)
defines one qmod `main`. `run(name)` synthesizes it with Classiq
(Constraints(optimization_parameter=DEPTH, max_width=18)), transpiles through
Classiq's own AUTO_OPTIMIZE to u3/cx (the actual scoring compiler -- see
`..classiq_score`), verifies the result with our existing `verify.py` (reused
as-is: it only cares about a QASM-loadable QuantumCircuit, not where it came
from), and saves qasm + metrics under `data/artifacts/classiq_native/<name>/`.

EACH MODEL RUNS IN ITS OWN SUBPROCESS (`_run_one.py`). Not an aesthetic
choice: Classiq's qfunc/type-inference machinery keeps global state keyed by
function name ("main", "logo_phase_oracle"), so decorating two same-named
qfuncs in one process corrupts it -- confirmed empirically, one model builds
fine alone and raises deep inside `declaration_inferrer.is_qvar` the moment a
second same-named qfunc has been decorated anywhere in that interpreter, even
in a different module. Do not "fix" this by importing all model modules
eagerly at package level; that's what triggers it.

Requires `pip install -e ".[classiq]"` and a prior `classiq.authenticate()`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Deliberately NOT `from ._run_one import MODEL_MODULES`: importing `_run_one`
# here means it's already in sys.modules under this package's name by the
# time `python -m qoracle.classiq_native._run_one` re-executes it as
# `__main__`, which runpy warns about and which empirically corrupts
# Classiq's qfunc introspection (see module docstring). Duplicated as a
# plain tuple instead -- keep in sync with `_run_one.MODEL_MODULES`.
MODEL_MODULES = ("rectangles", "rectangles_grouped", "rectangles_nested", "primitives")


def available() -> list[str]:
    return list(MODEL_MODULES)


def run(name: str, store_dir: str | Path = "data/artifacts/classiq_native") -> dict:
    """Build, synthesize, transpile (Classiq AUTO_OPTIMIZE, u3/cx), verify, save.

    Spawns `python -m qoracle.classiq_native._run_one <name> <store_dir>` --
    see module docstring for why this must be a fresh process per model.
    """
    if name not in MODEL_MODULES:
        raise KeyError(f"unknown classiq_native model '{name}'. available: {available()}")
    proc = subprocess.run(
        [sys.executable, "-m", "qoracle.classiq_native._run_one", name, str(store_dir)],
        capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"classiq_native.run({name!r}) failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])
