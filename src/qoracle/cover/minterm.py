"""Correctness floor: one 12-literal cube per marked pixel. Terrible, always right.

Exists so the pipeline can be exercised end-to-end and so every other cover has
a known-correct reference to diff against.
"""
from __future__ import annotations

import numpy as np

from . import register
from ..ir import Cube, PhaseIR
from ..spec import N_DATA, OracleSpec

FULL = (1 << N_DATA) - 1


@register("minterm")
def cover(spec: OracleSpec, **params) -> PhaseIR:
    terms = [Cube(FULL, int(i)) for i in np.flatnonzero(spec.truth)]
    return PhaseIR(terms, provenance={"cover": "minterm"})
