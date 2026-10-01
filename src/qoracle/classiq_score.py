"""Scoring against Classiq's OWN compiler, not Qiskit's.

`metrics.py` transpiles with Qiskit (`transpile(..., optimization_level=3)`) as
a cheap local proxy. That is NOT the compiler that actually scores a
submission -- the challenge notebook scores via
`classiq.transpile(..., transpilation_option=AUTO_OPTIMIZE)`. The two
optimizers can and do disagree, so this is the authoritative number close to
submission time; treat `metrics.py` numbers as a fast local proxy in between.

Requires `pip install -e ".[classiq]"` and a one-time interactive
`classiq.authenticate()` (browser device-auth flow) on this machine -- neither
of which this module can do for you. Everything here fails loud and early if
either precondition is missing, rather than silently falling back to Qiskit.
"""
from __future__ import annotations

from dataclasses import dataclass

from qiskit import QuantumCircuit

from .export import to_qasm2
from .metrics import DEFAULT_BASIS


@dataclass(frozen=True)
class ClassiqMetrics:
    depth: int
    cx: int
    width: int
    count_ops: dict

    def key(self) -> tuple[int, int]:
        return (self.depth, self.cx)

    def as_dict(self) -> dict:
        return {"depth": self.depth, "cx": self.cx, "width": self.width,
                "count_ops": self.count_ops, "engine": "classiq"}


def classiq_available() -> bool:
    try:
        import classiq  # noqa: F401
        return True
    except ImportError:
        return False


def score(qc: QuantumCircuit, basis: str = DEFAULT_BASIS, opt_level: int = 3,
          seed: int = 0) -> ClassiqMetrics:
    """Transpile through Classiq's own AUTO_OPTIMIZE pipeline, u3/cx basis.

    Round-trips through the same Qiskit-transpiled QASM2 used for submission
    (`export.to_qasm2`), so this scores exactly what you would actually upload.
    """
    try:
        import classiq
        from classiq import (
            Preferences,
            TranspilationConfig,
            TranspilationOption,
            quantum_program_from_qasm,
        )
        from classiq.interface.generator.hardware.hardware_data import CustomHardwareSettings
    except ImportError as e:
        raise RuntimeError(
            "classiq SDK not installed. `pip install -e '.[classiq]'`"
        ) from e

    qasm = to_qasm2(qc, basis=basis, opt_level=opt_level, seed=seed)
    try:
        qprog = quantum_program_from_qasm(qasm)
        transpiled = classiq.transpile(
            qprog,
            preferences=Preferences(
                transpilation_option=TranspilationOption.AUTO_OPTIMIZE,
                custom_hardware_settings=CustomHardwareSettings(basis_gates=["u3", "cx"]),
            ),
        )
        m = classiq.get_transpiled_circuit_metrics(transpiled)
    except Exception as e:
        raise RuntimeError(
            "Classiq call failed -- most likely not authenticated on this machine. "
            "Run `classiq.authenticate()` once (interactive browser login), then retry."
        ) from e

    return ClassiqMetrics(
        depth=m.depth, cx=m.count_ops.get("cx", 0), width=m.width,
        count_ops=dict(m.count_ops),
    )
