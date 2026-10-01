"""Manually-scheduled ancilla-batched lowering for `cover='rect_groups'`.

WHY THIS EXISTS. `classiq_native/rectangles_grouped.py` builds the identical
logical structure (compute an x-range flag once, reuse it for 1-2 y-sub-range
branches -- which turned out to BE the exact mirror-symmetry of the logo, see
that module's docstring) but hands it to Classiq's `control()` + AUTO_OPTIMIZE
and trusts the black-box scheduler to parallelize across the 10 independent
groups under the 6-ancilla budget. Measured result: 4316 depth / 2630 cx,
i.e. only 0.61 gates per depth layer -- the leaderboard leader manages 3.92.
Since gate COUNT is only 4.7x the leader's (not 30x, matching the depth gap),
the gap looks like a SCHEDULING problem, not a missing-structure problem.
This lowering removes the black box: WE choose the batching and gate order.

SCHEME. `ancillas // 2` groups are "live" at once (one x-flag ancilla + one
y-flag ancilla per live group). Batch the `n_groups` x-range groups into
chunks of that size. Per batch: compute all x-flags (into distinct ancillas,
via the group's ESOP cubes), then for each "round" r (0 or 1 -- a group has
1 or 2 y-sub-ranges) compute the round-r y-flag for every group that has one,
CZ it against that group's x-flag, and uncompute the y-flag before the next
round. Finally uncompute all x-flags. All CZs within a round act on disjoint
ancilla pairs (depth-1 in principle); x-flag computes for different groups
target disjoint ancillas so the transpiler can interleave them even though
they read the same x register.
"""
from __future__ import annotations

from qiskit import QuantumCircuit

from . import register
from .gf2_ancilla import _emit_indicator
from ..ir import PhaseIR
from ..spec import N_DATA, N_X, N_Y


@register("rect_ancilla")
def lower(ir: PhaseIR, width: int | None = None, ancillas: int = 6, **params) -> QuantumCircuit:
    if not ir.pre.is_identity:
        raise NotImplementedError("non-identity AffinePre lowering not implemented yet")
    groups = ir.provenance.get("groups")
    if not groups:
        raise ValueError(
            "rect_ancilla requires a PhaseIR from cover='rect_groups' "
            "(missing provenance['groups'])"
        )
    pairs = max(1, ancillas // 2)
    if width is not None and N_DATA + 2 * pairs > width:
        pairs = max(1, (width - N_DATA) // 2)

    n_anc = 2 * pairs
    qc = QuantumCircuit(N_DATA + n_anc, name="oracle_rect_ancilla")
    x_qubits = list(range(N_X))
    y_qubits = list(range(N_X, N_DATA))

    for batch_start in range(0, len(groups), pairs):
        batch = groups[batch_start: batch_start + pairs]
        x_anc = [N_DATA + 2 * i for i in range(len(batch))]
        y_anc = [N_DATA + 2 * i + 1 for i in range(len(batch))]

        for g, xa in zip(batch, x_anc):
            _emit_indicator(qc, g["x_cubes"], x_qubits, xa, relative_phase=True)

        max_rounds = max(len(g["y_ranges_cubes"]) for g in batch)
        for r in range(max_rounds):
            for g, xa, ya in zip(batch, x_anc, y_anc):
                if r >= len(g["y_ranges_cubes"]):
                    continue
                y_cubes = g["y_ranges_cubes"][r]
                _emit_indicator(qc, y_cubes, y_qubits, ya, relative_phase=True)
                qc.cz(xa, ya)
                _emit_indicator(qc, y_cubes, y_qubits, ya, relative_phase=True, reverse=True)

        for g, xa in zip(batch, x_anc):
            _emit_indicator(qc, g["x_cubes"], x_qubits, xa, relative_phase=True, reverse=True)

    return qc
