"""Runs exactly ONE classiq_native model, in its own process (see `run()` in
`__init__.py` for why: Classiq's qfunc/type-inference machinery keeps global
state keyed by function name ("main", "logo_phase_oracle", ...), so decorating
two same-named qfuncs -- e.g. `rectangles.main` and `rectangles_grouped.main`
-- in one process corrupts it, no matter which module they're each defined
in. Confirmed empirically 2026-09-14: identical model code that builds fine
alone raises `TypeError: issubclass() arg 1 must be a class` deep in
`declaration_inferrer.is_qvar` once a second same-named qfunc has been
decorated in the same interpreter.

Invoked as `python -m qoracle.classiq_native._run_one <model_name>`, never
called directly -- see `run()`.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from qiskit import qasm2

from ..io import logo_target
from ..verify import verify

MODEL_MODULES = ("rectangles", "rectangles_grouped", "rectangles_nested", "primitives")


def main(name: str, store_dir: str) -> dict:
    import classiq
    from classiq import (
        Constraints,
        OptimizationParameter,
        Preferences,
        TargetLanguage,
        TranspilationConfig,
        TranspilationOption,
        create_model,
        export,
        quantum_program_from_qasm,
        synthesize,
    )
    from classiq.interface.generator.hardware.hardware_data import CustomHardwareSettings

    if name not in MODEL_MODULES:
        raise KeyError(f"unknown classiq_native model '{name}'. available: {list(MODEL_MODULES)}")
    mod = importlib.import_module(f".{name}", __package__)
    qmod_main = mod.main

    constraints = Constraints(optimization_parameter=OptimizationParameter.DEPTH, max_width=18)
    model = create_model(qmod_main, constraints=constraints)
    qprog = synthesize(model)

    raw_qasm = export(qprog, TargetLanguage.QASM2)
    raw_lines = raw_qasm.splitlines()
    prep_idx = {
        i for i, l in enumerate(raw_lines)
        if l.lstrip().startswith("hadamard_transform_") and "q[" in l
    }
    if len(prep_idx) != 2:
        raise RuntimeError(f"expected 2 Hadamard-prep lines to strip, found {len(prep_idx)}")
    candidate_qasm = "\n".join(l for i, l in enumerate(raw_lines) if i not in prep_idx)
    candidate_qprog = quantum_program_from_qasm(candidate_qasm)

    transpiled = classiq.transpile(
        candidate_qprog,
        preferences=Preferences(
            transpilation_option=TranspilationOption.AUTO_OPTIMIZE,
            custom_hardware_settings=CustomHardwareSettings(basis_gates=["u3", "cx"]),
        ),
    )
    m = classiq.get_transpiled_circuit_metrics(transpiled)
    submission_qasm = export(
        transpiled, TargetLanguage.QASM2,
        transpilation_config=TranspilationConfig(basis_gates=["u3", "cx"]),
    )

    qc = qasm2.loads(submission_qasm)
    ver = verify(qc, logo_target())

    result = {
        "name": name, "width": m.width, "depth": m.depth,
        "cx": m.count_ops.get("cx", 0), "count_ops": dict(m.count_ops),
        "verified": ver["ok"], "verify": ver,
    }

    out = Path(store_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "oracle.qasm").write_text(submission_qasm)
    (out / "metrics.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    name, store_dir = sys.argv[1], sys.argv[2]
    res = main(name, store_dir)
    print(json.dumps(res))
