"""Submission export: high-level circuit -> OpenQASM in the scored basis.

Kept separate from the store because export is a VIEW, like metrics. Changing
the target basis re-exports; it never re-synthesises.
"""
from __future__ import annotations

from pathlib import Path

from qiskit import QuantumCircuit, qasm2, transpile

from .metrics import BASES, DEFAULT_BASIS

# gates qasm2.dumps can always emit against qelib1.inc
QASM2_SAFE = ["cx", "u3", "u2", "u1", "id", "x", "y", "z", "h", "s", "sdg", "t", "tdg", "rz", "rx", "ry"]


def to_qasm2(qc: QuantumCircuit, basis: str = DEFAULT_BASIS, opt_level: int = 3,
             seed: int = 0) -> str:
    gates = sorted(set(BASES[basis]) & set(QASM2_SAFE)) or ["cx", "u3"]
    if "u" in BASES[basis] and "u3" not in gates:
        gates.append("u3")
    tqc = transpile(qc, basis_gates=gates, optimization_level=opt_level, seed_transpiler=seed)
    return qasm2.dumps(tqc)


def write_submission(qc: QuantumCircuit, out_dir: str | Path, basis: str = DEFAULT_BASIS,
                     opt_level: int = 3) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "oracle.qasm"
    p.write_text(to_qasm2(qc, basis=basis, opt_level=opt_level))
    return p
