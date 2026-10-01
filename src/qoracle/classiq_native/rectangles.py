"""The challenge notebook's own (nominally "unoptimized") approach: one
arithmetic range-comparator control block per disjoint rectangle in the
scanline decomposition of the logo (`io.logo_rectangles`, 18 rectangles).

CURRENT BEST OVERALL (2026-09-14): width=18, depth=5329, cx=3502 -- beats
Track A's best (gf2_factor+gf2_ancilla: 6337/3609) despite being the
"unoptimized" starting point, purely because Classiq's synthesizer sees the
interval structure directly instead of a flattened truth table.

NOTE: `main`/`logo_phase_oracle` are defined at MODULE level, not nested in a
function -- Classiq's `@qfunc`/`@qperm` type introspection breaks on nested
qfuncs (confirmed empirically: `issubclass() arg 1 must be a class` deep in
`declaration_inferrer.is_qvar`). Mirrors the notebook's own top-level style.
"""
from classiq import Const, Output, QNum, allocate, control, hadamard_transform, phase, qfunc, qperm
from classiq.qmod.symbolic import pi

from ..io import logo_rectangles
from ..spec import N_X

COORD_BITS = N_X
ORACLE_RECTANGLES = logo_rectangles()


@qperm
def logo_phase_oracle(x: Const[QNum], y: Const[QNum]) -> None:
    for x_min, x_max, y_min, y_max in ORACLE_RECTANGLES:
        y_condition = (y == y_min) if y_min == y_max else ((y >= y_min) & (y <= y_max))
        rectangle_condition = (x >= x_min) & (x <= x_max) & y_condition
        control(rectangle_condition, lambda: phase(pi))


@qfunc
def main(x: Output[QNum[COORD_BITS]], y: Output[QNum[COORD_BITS]]) -> None:
    allocate(x)
    allocate(y)
    hadamard_transform(x)
    hadamard_transform(y)
    logo_phase_oracle(x, y)
