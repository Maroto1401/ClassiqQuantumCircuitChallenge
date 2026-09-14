"""ESOP minimisation via ABC's EXORCISM (`&exorcism`).

Falls back with a clear error if the `abc` binary is absent, so the pipeline
never silently produces a worse cover than you think it did.

Weighting note: we ask for solutions ranked by LITERAL count, not cube count.
A 12-literal cube is a 12-controlled Z; three 4-literal cubes are cheaper in
both depth and CX.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import register
from ..ir import Cube, PhaseIR
from ..spec import DIM, N_DATA, OracleSpec


def abc_available() -> bool:
    return shutil.which("abc") is not None


def write_pla(spec: OracleSpec, path: Path) -> None:
    lines = [f".i {N_DATA}", ".o 1", f".p {spec.n_marked}", ".type fr"]
    for i in np.flatnonzero(spec.truth):
        bits = "".join(str((int(i) >> b) & 1) for b in range(N_DATA))  # LSB-first
        lines.append(f"{bits} 1")
    lines.append(".e")
    path.write_text("\n".join(lines))


def parse_esop_pla(text: str) -> list[Cube]:
    terms: list[Cube] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(".") or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] not in ("1", "~"):
            continue
        mask = value = 0
        for b, ch in enumerate(parts[0]):
            if ch == "1":
                mask |= 1 << b
                value |= 1 << b
            elif ch == "0":
                mask |= 1 << b
        terms.append(Cube(mask, value))
    return terms


@register("esop_abc")
def cover(spec: OracleSpec, quality: int = 4, seed: int | None = None, **params) -> PhaseIR:
    if not abc_available():
        raise RuntimeError(
            "abc binary not found. Install berkeley-abc, or use cover='pprm' meanwhile."
        )
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        pla, out = tdp / "f.pla", tdp / "f_esop.pla"
        write_pla(spec, pla)
        script = f"read_pla {pla}; &get; &exorcism -Q {quality} {out}; "
        subprocess.run(["abc", "-q", script], check=True, capture_output=True, timeout=1800)
        terms = parse_esop_pla(out.read_text())
    return PhaseIR(terms, provenance={"cover": "esop_abc", "quality": quality, "seed": seed})
