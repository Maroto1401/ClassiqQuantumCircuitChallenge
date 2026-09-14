"""Depth-oriented lowering: ancilla fanout of control bits.

IDEA. The oracle is diagonal, so the data qubits stay diagonal throughout and a
control bit may be CX-copied into ancillas. Independent cubes then drive several
MCZs CONCURRENTLY instead of queueing on the same 12 wires. With `c` copies the
MCZ layer count drops by roughly `c`, bounded by the width cap.

STATUS: scaffold. Partitioning + copy/uncopy scheduling is roadmap Phase 3 (B1).
Kept here with a real signature so the runner, store and leaderboard can already
address it and so switching it on costs no plumbing.
"""
from __future__ import annotations

from qiskit import QuantumCircuit

from . import register
from ..ir import PhaseIR


@register("fanout")
def lower(ir: PhaseIR, width: int | None = None, copies: int = 2, **params) -> QuantumCircuit:
    raise NotImplementedError(
        "fanout lowering pending: needs the width cap from the organisers "
        "(it sets `copies`) -- see roadmap Phase 3 / Track B1"
    )
