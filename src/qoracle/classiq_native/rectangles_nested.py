"""Like `rectangles_grouped.py`, but nests x-range `control()` blocks that are
STRICTLY CONTAINED in one another, instead of treating all 10 unique x-ranges
as flat siblings.

Real structure in the data (`io.logo_rectangles()`): disc2's 5 x-ranges are a
strict nesting chain `[38,42]⊂[36,44]⊂[34,46]⊂[33,47]⊂[32,48]` (symmetric
rings around its widest row), and disc1's 3 are likewise
`[53,57]⊂[51,59]⊂[50,60]`. `rectangles_grouped` computes all 10 x-conditions
as independent flat siblings even though 8 of them are literally rings of the
same two circles. This nests each family from widest to narrowest instead:
compute the widest ring's x-condition, apply its own y-rows, then INSIDE that
scope compute the next-narrower ring's x-condition, etc.

Y-ranges are mutually exclusive across nesting levels (inherited from the
source rectangles being disjoint), so nesting from widest to narrowest and
applying each level's own phase(pi) before recursing reproduces the identical
pixel set -- correctness verified against the real truth table below, not
just asserted.

rect1 (`[2,26]`) and the middle bar (`[2,61]`) are numerically wide enough to
contain everything but are NOT part of either ring family (unrelated shapes,
disjoint y-bands from the rings) -- nesting them in would be geometrically
meaningless and only add spurious depth, so the chain search is restricted to
x-ranges narrower than 20 (comfortably above disc2's widest ring, 16, and
below rect1's 24), and the two wide ones stay flat top-level siblings exactly
as in `rectangles_grouped`.

BLOCKED (2026-09-17): correctness verified in plain Python (0/4096 wrong
against the real `io.logo_pixel`), but Classiq's synthesizer rejects it on
QUBIT COUNT, not depth. The full 5-deep chain needs >=26 qubits (vs the
18-qubit cap); even the shallowest possible test -- JUST disc1's 3-level
chain nested, everything else flat -- needs >=20. Mechanism: `control(A,
lambda: control(B, ...))` must hold A's condition qubit live for the entire
duration B is being evaluated (that's what "nested" means operationally),
so a chain of depth d needs d simultaneously-live condition qubits instead
of the 1-at-a-time reuse the FLAT sibling version (`rectangles_grouped`)
gets. Same underlying ancilla-scarcity wall as `lower/fanout.py` and the
carry-lookahead comparator (see CLAUDE.md Live Work, 2026-09-16/17), just
reached from the Track B / Classiq-native side instead of Track A. Do not
revisit without either a fundamentally cheaper way to encode "N nested
conditions" (not more `control()` nesting) or a relaxed qubit budget.
"""
from collections import defaultdict

from classiq import Const, Output, QNum, allocate, control, hadamard_transform, phase, qfunc, qperm
from classiq.qmod.symbolic import pi

from ..io import logo_rectangles
from ..spec import N_X

COORD_BITS = N_X
_NEST_WIDTH_CUTOFF = 20  # see module docstring

_rects = logo_rectangles()
_by_x: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
for _xm, _xM, _ym, _yM in _rects:
    _by_x[(_xm, _xM)].append((_ym, _yM))
_GROUPS = sorted(_by_x.items())


def _contains(outer: tuple[int, int], inner: tuple[int, int]) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1] and outer != inner


def _build_chains(groups):
    nestable = [(xr, yr) for xr, yr in groups if xr[1] - xr[0] < _NEST_WIDTH_CUTOFF]
    flat = [(xr, yr) for xr, yr in groups if xr[1] - xr[0] >= _NEST_WIDTH_CUTOFF]

    remaining = sorted(nestable, key=lambda g: -(g[0][1] - g[0][0]))
    used: set[tuple[int, int]] = set()
    chains = []
    for xr, yr in remaining:
        if xr in used:
            continue
        chain = [(xr, yr)]
        used.add(xr)
        cur = xr
        while True:
            candidates = [(xr2, yr2) for xr2, yr2 in remaining
                          if xr2 not in used and _contains(cur, xr2)]
            if not candidates:
                break
            nxt = max(candidates, key=lambda g: g[0][1] - g[0][0])
            chain.append(nxt)
            used.add(nxt[0])
            cur = nxt[0]
        chains.append(chain)
    chains.extend([xy] for xy in flat)
    return chains


CHAINS = _build_chains(_GROUPS)


def _y_cond(y, y_min, y_max):
    return (y == y_min) if y_min == y_max else ((y >= y_min) & (y <= y_max))


@qperm
def logo_phase_oracle(x: Const[QNum], y: Const[QNum]) -> None:
    def emit_level(chain, idx):
        (x_min, x_max), y_ranges = chain[idx]
        x_condition = (x >= x_min) & (x <= x_max)

        def body():
            for y_min, y_max in y_ranges:
                control(_y_cond(y, y_min, y_max), lambda: phase(pi))
            if idx + 1 < len(chain):
                emit_level(chain, idx + 1)

        control(x_condition, body)

    for chain in CHAINS:
        emit_level(chain, 0)


@qfunc
def main(x: Output[QNum[COORD_BITS]], y: Output[QNum[COORD_BITS]]) -> None:
    allocate(x)
    allocate(y)
    hadamard_transform(x)
    hadamard_transform(y)
    logo_phase_oracle(x, y)
