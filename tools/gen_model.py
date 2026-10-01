"""Generate an exact-angle Classiq qmod model from SUBMISSION_oracle.qasm."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import math, re, pathlib

ROOT = pathlib.Path(".")
qasm = (ROOT / "submission.qasm").read_text()

NS = {"pi": math.pi}
angles, idx, body = [], {}, []
ncx = nu3 = 0
for raw in qasm.splitlines():
    line = raw.strip()
    if not line or line.startswith(("OPENQASM", "include", "qreg", "creg", "//")):
        continue
    m = re.fullmatch(r"cx q\[(\d+)\],q\[(\d+)\];", line)
    if m:
        body.append(f"    CX(q[{m.group(1)}], q[{m.group(2)}])")
        ncx += 1
        continue
    m = re.fullmatch(r"u3\(([^)]*)\) q\[(\d+)\];", line)
    if m:
        parts = m.group(1).split(",")
        assert len(parts) == 3, line
        key = tuple(float(eval(p, {"__builtins__": {}}, NS)) for p in parts)
        if key not in idx:
            idx[key] = len(angles)
            angles.append(key)
        body.append(f"    u3_{idx[key]}(q[{m.group(2)}])")
        nu3 += 1
        continue
    raise SystemExit(f"UNPARSED LINE: {line!r}")

print(f"parsed: cx={ncx} u3={nu3} distinct_angles={len(angles)}")

out = ['"""Classiq QCC submission model - diagonal phase oracle for the 64x64 Classiq logo.',
       "",
       "|x,y> -> (-1)^f(x,y)|x,y>   with q[0:6]=x, q[6:12]=y, q[12:18]=clean ancillas",
       "(all ancillas returned to |0>).  Angles are written at full double precision:",
       "the u3 Euler angles produced by 1-qubit gate fusion are irrational, and the",
       "oracle must be exact to 1e-10 on all 4096 basis states.",
       '"""',
       "",
       "from classiq import CX, QArray, QBit, Output, U, allocate, qfunc", "", ""]
for i, (t, p, l) in enumerate(angles):
    out += [f"@qfunc",
            f"def u3_{i}(q_0: QBit) -> None:",
            f"    U(theta={t!r}, phi={p!r}, lam={l!r}, gam=0.0, target=q_0)",
            "", ""]
out += ["@qfunc", "def main(q: Output[QArray[QBit, 18]]) -> None:", "    allocate(q)"]
out += body
out += ["", ""]

dest = ROOT / "submission_model.py"
dest.write_text("\n".join(out))
print(f"wrote {dest}  ({len(out)} lines)")
