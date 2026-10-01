"""Cover built from the logo's own rectangle decomposition, grouped by shared
x-range -- the SAME structure as `classiq_native/rectangles_grouped.py`
(which turned out to be exactly the "reflect the symmetric half" idea: every
2-member x-range group pairs two rows that are EXACT mirror images, about
y=19 for the disc2 band or y=41 for the rect1/rect2/disc1 band -- verified
0 defect pixels both times, 2026-09-14).

This module exists to feed `lower/rect_ancilla.py`: unlike
`classiq_native/rectangles_grouped.py` (which hands the grouped structure to
Classiq's `control()` and trusts `AUTO_OPTIMIZE` to schedule/parallelize it),
this cover preserves the group structure explicitly in provenance so we can
hand-schedule the ancilla batching ourselves -- see `lower/rect_ancilla.py`
docstring for why that's worth trying (measured depth/cx is 6.4x less
"gates per depth layer" than the competition leader; that gap is either
Classiq's scheduler or ours to close).

Each x-range's indicator (a plain 6-bit contiguous interval) and each
y-sub-range's indicator are individually ESOP-minimised via the same
ABC/EXORCISM route as `gf2_factor._esop_cubes` (reused directly, not
reimplemented).
"""
from __future__ import annotations

from collections import defaultdict

from . import register
from .gf2_factor import _esop_cubes
from ..io import logo_rectangles
from ..ir import Cube, PhaseIR
from ..spec import N_X, N_Y, OracleSpec


def _range_bits(lo: int, hi: int, n: int) -> list[int]:
    return [1 if lo <= v <= hi else 0 for v in range(1 << n)]


@register("rect_groups")
def cover(spec: OracleSpec, quality: int = 4, **params) -> PhaseIR:
    import numpy as np

    rects = logo_rectangles()
    by_x: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for x_min, x_max, y_min, y_max in rects:
        by_x[(x_min, x_max)].append((y_min, y_max))

    terms: list[Cube] = []
    groups: list[dict] = []
    for (x_min, x_max), y_ranges in sorted(by_x.items()):
        x_cubes = _esop_cubes(np.array(_range_bits(x_min, x_max, N_X)), N_X, quality=quality)
        y_ranges_cubes = []
        for y_min, y_max in y_ranges:
            y_cubes = _esop_cubes(np.array(_range_bits(y_min, y_max, N_Y)), N_Y, quality=quality)
            y_ranges_cubes.append(y_cubes)
            for xm, xv in x_cubes:
                for ym, yv in y_cubes:
                    terms.append(Cube(xm | (ym << N_X), xv | (yv << N_X)))
        groups.append({"x_range": (x_min, x_max), "x_cubes": x_cubes,
                        "y_ranges": y_ranges, "y_ranges_cubes": y_ranges_cubes})

    return PhaseIR(
        terms,
        provenance={"cover": "rect_groups", "quality": quality, "n_groups": len(groups),
                    "groups": groups},
    )
