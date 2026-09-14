"""Metrics are DERIVED, never stored as truth.

Every number here is recomputed from the stored QASM on demand, so redefining a
metric or changing the target gate set costs one `qo score` pass and zero
re-synthesis. That is the property the whole repo is organised around.

The scored basis is still UNKNOWN -- confirm with the organisers. Comparing depth
across bases is meaningless (easily 2x), so `qo score` always records the basis
used alongside the numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from qiskit import QuantumCircuit, transpile

# Candidate bases. `clifford_t` and `ibm_native` are guesses until confirmed.
BASES: dict[str, list[str]] = {
    "cx_u": ["cx", "u"],
    "cx_u3": ["cx", "u3"],
    "clifford_t": ["cx", "h", "s", "sdg", "t", "tdg", "x", "z"],
    "ibm_native": ["cz", "rz", "sx", "x"],
}
DEFAULT_BASIS = "cx_u"


@dataclass(frozen=True)
class Metrics:
    basis: str
    depth: int
    cx: int
    two_qubit_depth: int
    two_qubit_gates: int
    t_count: int
    total_gates: int
    width: int
    opt_level: int

    def key(self) -> tuple[int, int]:
        """Competition ranking key: depth first, CX as tiebreak."""
        return (self.depth, self.cx)

    def as_dict(self) -> dict:
        return asdict(self)


TWO_Q = {"cx", "cz", "ecr", "cp", "cy", "ch", "swap", "iswap", "rzz", "rxx", "ryy"}


def score(qc: QuantumCircuit, basis: str = DEFAULT_BASIS, opt_level: int = 3,
          seed: int = 0) -> Metrics:
    if basis not in BASES:
        raise KeyError(f"unknown basis '{basis}'. available: {sorted(BASES)}")
    tqc = transpile(qc, basis_gates=BASES[basis], optimization_level=opt_level,
                    seed_transpiler=seed)
    ops = tqc.count_ops()
    two_q = sum(v for k, v in ops.items() if k in TWO_Q)
    return Metrics(
        basis=basis,
        depth=tqc.depth(),
        cx=int(ops.get("cx", 0) + ops.get("cz", 0)),
        two_qubit_depth=tqc.depth(lambda inst: inst.operation.num_qubits == 2),
        two_qubit_gates=two_q,
        t_count=int(ops.get("t", 0) + ops.get("tdg", 0)),
        total_gates=sum(ops.values()),
        width=tqc.num_qubits,
        opt_level=opt_level,
    )


def score_all(qc: QuantumCircuit, bases: list[str] | None = None, **kw) -> dict[str, dict]:
    return {b: score(qc, basis=b, **kw).as_dict() for b in (bases or list(BASES))}
