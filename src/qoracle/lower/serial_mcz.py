"""Baseline lowering: one multi-controlled Z per cube, executed in sequence.

Correct and simple. Serial on the 12 data qubits, so depth is roughly
sum over cubes of MCZ depth -- this is the number the fanout lowering exists to beat.
"""
from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.circuit.library import ZGate

from . import register
from ..ir import PhaseIR
from ..spec import N_DATA


def apply_pre(qc: QuantumCircuit, ir: PhaseIR) -> None:
    """Emit the affine pre-map as an X/CX network (identity -> nothing)."""
    if ir.pre.is_identity:
        return
    raise NotImplementedError(
        "non-identity AffinePre lowering not implemented yet "
        "(needs GF(2) CNOT-network synthesis; see roadmap Phase 4)"
    )


def emit_cube(qc: QuantumCircuit, mask: int, value: int, data: list[int]) -> None:
    """X-conjugated multi-controlled Z on the literals of one cube."""
    lits = [i for i in range(N_DATA) if (mask >> i) & 1]
    if not lits:
        return  # constant term = global phase, free
    negs = [i for i in lits if not ((value >> i) & 1)]
    for i in negs:
        qc.x(data[i])
    if len(lits) == 1:
        qc.z(data[lits[0]])
    else:
        ctrl = [data[i] for i in lits[:-1]]
        qc.append(ZGate().control(len(ctrl), annotated=False), ctrl + [data[lits[-1]]])
    for i in negs:
        qc.x(data[i])


@register("serial_mcz")
def lower(ir: PhaseIR, width: int | None = None, **params) -> QuantumCircuit:
    qc = QuantumCircuit(N_DATA, name="oracle_serial")
    data = list(range(N_DATA))
    apply_pre(qc, ir)
    for c in ir.terms:
        emit_cube(qc, c.mask, c.value, data)
    return qc
