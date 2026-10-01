"""Like `rectangles.py`, but grouped by X-RANGE before lowering to `control()`.

The 18 disjoint rectangles from `io.logo_rectangles()` only have **10 unique
x-ranges** -- several rows/row-pairs of the raster share identical x-bounds
(expected: the two discs rasterize top-bottom symmetrically). `rectangles.py`
recomputes an independent x-condition per rectangle (18 x-comparator builds);
this groups by x-range and nests: compute the x-condition ONCE per group
(`control(x_cond, ...)`), then inside that scope apply one `control(y_cond_i,
phase(pi))` per y-sub-range belonging to that group (1 or 2 of them, always
mutually disjoint since the source rectangles are disjoint by construction).
Classiq's `control()` uncomputes its own condition automatically, so this
saves one whole x-range compute+uncompute per repeated x-range (8 rectangles
share an x-range with exactly one other rectangle here) versus 18 independent
computations -- a direct instance of the "compute shared sub-predicates once,
reuse across branches" principle from parallel/shared-ancilla oracle synthesis
literature (see notes/DECISIONS.md 2026-09-14 entry for the source search).
"""
from collections import defaultdict

from classiq import Const, Output, QNum, allocate, control, hadamard_transform, phase, qfunc, qperm
from classiq.qmod.symbolic import pi

from ..io import logo_rectangles
from ..spec import N_X

COORD_BITS = N_X

_rects = logo_rectangles()
_by_x: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
for _xm, _xM, _ym, _yM in _rects:
    _by_x[(_xm, _xM)].append((_ym, _yM))
GROUPED_RECTANGLES = tuple(sorted(_by_x.items()))


@qperm
def logo_phase_oracle(x: Const[QNum], y: Const[QNum]) -> None:
    for (x_min, x_max), y_ranges in GROUPED_RECTANGLES:
        x_condition = (x >= x_min) & (x <= x_max)

        if len(y_ranges) == 1:
            y_min, y_max = y_ranges[0]
            y_condition = (y == y_min) if y_min == y_max else ((y >= y_min) & (y <= y_max))
            control(x_condition & y_condition, lambda: phase(pi))
        else:
            def emit_y_branches():
                for y_min, y_max in y_ranges:
                    y_condition = (y == y_min) if y_min == y_max else ((y >= y_min) & (y <= y_max))
                    control(y_condition, lambda: phase(pi))

            control(x_condition, emit_y_branches)


@qfunc
def main(x: Output[QNum[COORD_BITS]], y: Output[QNum[COORD_BITS]]) -> None:
    allocate(x)
    allocate(y)
    hadamard_transform(x)
    hadamard_transform(y)
    logo_phase_oracle(x, y)
