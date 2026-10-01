"""Geometric-primitive model: 2 rectangles + 2 REAL quadratic disc predicates
`(x-a)^2+(y-b)^2 <= r^2`, instead of the 18-rectangle raster decomposition.

STATUS: blocked, kept for reference. `run("primitives")` will raise from
Classiq with "Model requires at least 43 qubits, but max width constraint is
18." Evaluating one quadratic form in reversible arithmetic at 6-bit precision
(signed subtract -> square -> add -> compare) needs wide intermediate
registers that don't fit the 6-ancilla budget, even though only one such
predicate is "live" at a time. Confirmed empirically, 2026-09-14 -- see
`classiq_native/__init__.py` module docstring for the sibling result.

Correctness note if this is revisited: the 4 raw primitives are NOT pairwise
disjoint (rect1 & rect2 overlap 5 pixels, rect2 & disc1 overlap 5 pixels, no
triple overlaps) -- unlike `logo_rectangles()`'s output, which is a disjoint
partition by construction. A naive per-primitive `control(P, phase(pi))` loop
double-flips those 10 pixels back to +1. The fix is inclusion-exclusion via
phase parity: flip once per primitive AND once more per pairwise-overlapping
PAIR (`rect1 & rect2`, `rect2 & disc1`); verified exactly against the true
mask (0 mismatches over all 4096 states) before ever touching Classiq.

Future direction if the width blocker gets solved (e.g. narrower fixed-point
arithmetic, or a cheaper radius-comparison trick than a full sum-of-squares):
this halves the "control block" count vs. `rectangles.py` (6 vs 18), which is
the more promising lever toward the 142/557 leader than further squeezing the
raster decomposition.
"""
from classiq import Const, Output, QNum, allocate, control, hadamard_transform, phase, qfunc, qperm
from classiq.qmod.symbolic import pi

from ..spec import N_X

COORD_BITS = N_X


@qperm
def logo_phase_oracle(x: Const[QNum], y: Const[QNum]) -> None:
    rect1 = (x >= 2) & (x <= 26) & (y >= 29) & (y <= 53)
    rect2 = (x >= 26) & (x <= 49) & (y >= 39) & (y <= 43)
    disc1 = (x - 55) ** 2 + (y - 41) ** 2 <= 42
    disc2 = (x - 40) ** 2 + (y - 19) ** 2 <= 72
    control(rect1, lambda: phase(pi))
    control(rect2, lambda: phase(pi))
    control(disc1, lambda: phase(pi))
    control(disc2, lambda: phase(pi))
    control(rect1 & rect2, lambda: phase(pi))  # inclusion-exclusion correction
    control(rect2 & disc1, lambda: phase(pi))  # inclusion-exclusion correction


@qfunc
def main(x: Output[QNum[COORD_BITS]], y: Output[QNum[COORD_BITS]]) -> None:
    allocate(x)
    allocate(y)
    hadamard_transform(x)
    hadamard_transform(y)
    logo_phase_oracle(x, y)
