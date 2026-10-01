"""The notebook's OWN qasm_metrics(), verbatim, run on submission.qasm."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import re, pathlib

def qasm_metrics(source: str) -> tuple[int, int, int]:
    statements = [s.strip() for s in re.sub(r"//[^\n]*", "", source).split(";") if s.strip()]
    if statements[:2] != ["OPENQASM 2.0", 'include "qelib1.inc"']:
        raise ValueError("Expected an OpenQASM 2.0 file using qelib1.inc")
    qreg_match = (re.fullmatch(r"qreg\s+q\s*\[\s*(\d+)\s*\]", statements[2])
                  if len(statements) >= 3 else None)
    if qreg_match is None:
        raise ValueError("Expected exactly one register named q")
    width = int(qreg_match.group(1))
    if not 12 <= width <= 18:
        raise ValueError(f"QASM width must be between 12 and 18, got {width}")
    qubit_depths = [0] * width
    cx_count = 0
    for statement in statements[3:]:
        u3_match = re.fullmatch(r"u3\s*\([^,]+,[^,]+,[^,]+\)\s+q\s*\[\s*(\d+)\s*\]", statement)
        cx_match = re.fullmatch(r"cx\s+q\s*\[\s*(\d+)\s*\]\s*,\s*q\s*\[\s*(\d+)\s*\]", statement)
        if u3_match:
            qubits = (int(u3_match.group(1)),)
        elif cx_match:
            qubits = tuple(map(int, cx_match.groups()))
            cx_count += 1
        else:
            raise ValueError(f"Unsupported QASM statement: {statement}")
        if any(q >= width for q in qubits):
            raise ValueError(f"Qubit index outside range: {statement}")
        if len(set(qubits)) != len(qubits):
            raise ValueError(f"Gate operands must be distinct: {statement}")
        layer = max(qubit_depths[q] for q in qubits) + 1
        for q in qubits:
            qubit_depths[q] = layer
    return width, max(qubit_depths, default=0), cx_count

src = pathlib.Path("submission.qasm").read_text(encoding="utf-8")
w, d, cx = qasm_metrics(src)
print(f"OFFICIAL qasm_metrics(submission.qasm):  width={w}  depth={d}  cx={cx}")
print(f"SCORE (depth, tiebreak cx) = ({d}, {cx})")
