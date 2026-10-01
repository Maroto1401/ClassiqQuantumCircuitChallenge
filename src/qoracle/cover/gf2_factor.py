"""GF(2)-rank factorisation cover: f(x,y) = XOR_k u_k(y) . v_k(x).

`gf2.factor` writes the image (rows = y, cols = x) as M = U @ V (mod 2) with V
a subset of the image's OWN rows -- see `gf2.factor` docstring for why.  Each
factor k contributes one AND term u_k(y) & v_k(x); u_k and v_k are 6-bit
functions, individually minimised via the same ABC/EXORCISM route as
`esop_abc` (cheap: 6-variable ESOP, not 12), then cross-multiplied into
12-variable cubes (x-literals and y-literals never overlap within one cube,
so the cross product is a plain mask/value union).

r = gf2 rank sets how many independent (u, v) pairs exist. On the real logo
r=10 (see diagnostics), so this is the cover the low-rank diagnostic verdict
("pursue") points at.

This only changes the COVER -- the resulting PhaseIR is a normal flat list of
Cubes, so any existing lowering (serial_mcz, fanout) already knows how to
consume it. The real depth win beyond that (computing each u_k/v_k into a
shared ancilla and applying disjoint depth-1 CZs) is a LOWERING strategy, not
implemented here -- that is the natural next step once this cover is in use.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import register
from ..gf2 import factor
from ..ir import Cube, PhaseIR
from ..spec import N_X, N_Y, OracleSpec


def _esop_cubes(bits: np.ndarray, n: int, quality: int = 4) -> list[tuple[int, int]]:
    """Minimal ESOP (mask, value) pairs for an n-bit 0/1 function, via ABC."""
    marked = np.flatnonzero(bits)
    if marked.size == 0:
        return []
    if marked.size == (1 << n):
        return [(0, 0)]  # constant 1: mask=0 cube (free global phase upstream)
    if shutil.which("abc") is None:
        raise RuntimeError("abc binary not found on PATH")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        pla, out = tdp / "f.pla", tdp / "f_esop.pla"
        lines = [f".i {n}", ".o 1", f".p {marked.size}", ".type fr"]
        for i in marked:
            row = "".join(str((int(i) >> b) & 1) for b in range(n))
            lines.append(f"{row} 1")
        lines.append(".e")
        pla.write_text("\n".join(lines))
        script = f"read_pla {pla}; &get; &exorcism -Q {quality} {out}; "
        subprocess.run(["abc", "-q", script], check=True, capture_output=True, timeout=600)
        cubes: list[tuple[int, int]] = []
        for line in out.read_text().splitlines():
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
            cubes.append((mask, value))
        return cubes


@register("gf2_factor")
def cover(spec: OracleSpec, quality: int = 4, **params) -> PhaseIR:
    img = spec.to_image()  # (1<<N_Y, 1<<N_X): rows=y, cols=x
    U, V, basis_rows = factor(img)
    r = V.shape[0]

    terms: list[Cube] = []
    factors: list[dict] = []
    for k in range(r):
        v_cubes = _esop_cubes(V[k], N_X, quality=quality)       # x-only, bits [0..N_X)
        u_cubes = _esop_cubes(U[:, k], N_Y, quality=quality)    # y-only, bits [0..N_Y)
        factors.append({"u_cubes": u_cubes, "v_cubes": v_cubes})
        for vm, vv in v_cubes:
            for um, uv in u_cubes:
                mask = vm | (um << N_X)
                value = vv | (uv << N_X)
                terms.append(Cube(mask, value))

    return PhaseIR(
        terms,
        provenance={
            "cover": "gf2_factor", "quality": quality, "rank": r, "basis_rows": basis_rows,
            # per-factor recipe (local x/y bit positions), consumed by lower/gf2_ancilla.py
            # to exploit u_k(y)/v_k(x) independence instead of the flattened cube list.
            "factors": factors,
        },
    )
