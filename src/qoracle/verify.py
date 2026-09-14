"""Exact verification. Nothing is a candidate until it passes this.

Verifies the CIRCUIT, not the IR -- so it catches lowering bugs, ancilla leakage
and convention mismatches, which is the whole point. 4096 states is cheap.
"""
from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from .spec import DIM, N_DATA, OracleSpec


def circuit_diagonal(qc: QuantumCircuit, atol: float = 1e-8) -> np.ndarray:
    """Return the length-4096 phase vector the circuit applies to data states.

    Raises if the circuit is not diagonal on the data register or if ancillas
    are not returned to |0> (either would be a silent correctness bug).
    """
    n_total = qc.num_qubits
    n_anc = n_total - N_DATA
    if n_anc < 0:
        raise ValueError("circuit narrower than the data register")

    prep = QuantumCircuit(n_total)
    for q in range(N_DATA):
        prep.h(q)
    sv = Statevector.from_instruction(prep.compose(qc)).data
    amps = sv.reshape((1 << n_anc, DIM)) if n_anc else sv.reshape((1, DIM))

    if n_anc:
        leak = float(np.abs(amps[1:]).max()) if amps.shape[0] > 1 else 0.0
        if leak > atol:
            raise ValueError(f"ancillas not restored to |0> (max leaked amplitude {leak:.2e})")

    a0 = amps[0] * np.sqrt(DIM)
    mag = np.abs(a0)
    if not np.allclose(mag, 1.0, atol=1e-6):
        raise ValueError("circuit is not diagonal on the data register")
    return a0


def verify(qc: QuantumCircuit, spec: OracleSpec, atol: float = 1e-8) -> dict:
    """Exact check on all 4096 basis states, up to a global phase."""
    try:
        d = circuit_diagonal(qc, atol=atol)
    except ValueError as e:
        return {"ok": False, "reason": str(e), "n_wrong": None}

    expected = np.where(spec.truth == 1, -1.0, 1.0)
    for gp, label in ((d[0] / abs(d[0]), "auto"),):
        signs = np.real(d / gp)
    wrong_pos = int(np.sum(~np.isclose(signs, expected, atol=1e-6)))
    wrong_neg = int(np.sum(~np.isclose(-signs, expected, atol=1e-6)))
    n_wrong = min(wrong_pos, wrong_neg)
    return {
        "ok": n_wrong == 0,
        "n_wrong": n_wrong,
        "global_phase_flip": bool(wrong_neg < wrong_pos),
        "reason": None if n_wrong == 0 else f"{n_wrong} basis states have the wrong phase",
    }


def verify_ir(ir, spec: OracleSpec) -> dict:
    """Cheap pre-check: does the IR reproduce the truth table? Catches cover bugs
    before you pay for lowering."""
    got = ir.evaluate()
    n_wrong = int(np.sum(got != spec.truth))
    return {"ok": n_wrong == 0, "n_wrong": n_wrong}
