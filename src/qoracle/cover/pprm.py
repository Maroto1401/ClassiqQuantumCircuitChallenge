"""Positive-polarity Reed-Muller cover via the Moebius transform.

Zero external dependencies, always correct, and a genuinely reasonable ESOP for
structured functions. This is the baseline every fancier cover must beat, and it
unblocks the whole pipeline while ABC/Classiq access is pending.
"""
from __future__ import annotations

import numpy as np

from . import register
from ..diagnostics import anf
from ..ir import Cube, PhaseIR
from ..spec import OracleSpec


@register("pprm")
def cover(spec: OracleSpec, **params) -> PhaseIR:
    a = anf(spec.truth)
    terms = [Cube(int(m), int(m)) for m in np.flatnonzero(a)]  # positive literals only
    return PhaseIR(terms, provenance={"cover": "pprm"})
