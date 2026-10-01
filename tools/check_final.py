"""Parse the shipped .qmod back to a circuit; prove it is bit-identical to the .qasm."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import re, sys, math, pathlib
import numpy as np
sys.path.insert(0, str(ROOT / "src"))
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qoracle import io
from qoracle.verify import verify
from qoracle.spec import DIM, N_DATA

ROOT = pathlib.Path(".")

# ---------- parse .qmod ----------
txt = (ROOT / "submission.qmod").read_text()
wrappers = {}
for m in re.finditer(r"qfunc\s+(\w+)\(q_0:\s*qbit\)\s*\{\s*U\(([^)]*)\)\s*;\s*\}", txt):
    args = [a.strip() for a in m.group(2).split(",")]
    assert len(args) == 5 and args[4] == "q_0", args
    t, p, l, g = (float(a) for a in args[:4])
    assert g == 0.0, f"nonzero global phase in {m.group(1)}"
    wrappers[m.group(1)] = (t, p, l)

mm = re.search(r"qfunc\s+main\(output\s+q:\s*qbit\[(\d+)\]\)\s*\{(.*)\}", txt, re.S)
nq = int(mm.group(1))
qmod_ops = []
for line in mm.group(2).splitlines():
    line = line.strip()
    if not line or line == "allocate(q);":
        continue
    c = re.fullmatch(r"CX\(q\[(\d+)\],\s*q\[(\d+)\]\);", line)
    if c:
        qmod_ops.append(("cx", int(c.group(1)), int(c.group(2))))
        continue
    u = re.fullmatch(r"(\w+)\(q\[(\d+)\]\);", line)
    if u and u.group(1) in wrappers:
        qmod_ops.append(("u3", int(u.group(2))) + wrappers[u.group(1)])
        continue
    raise SystemExit(f"UNPARSED qmod line: {line!r}")

# ---------- parse .qasm ----------
NS = {"pi": math.pi}
qasm_ops = []
for raw in (ROOT / "submission.qasm").read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith(("OPENQASM", "include", "qreg", "creg", "//")):
        continue
    c = re.fullmatch(r"cx q\[(\d+)\],q\[(\d+)\];", line)
    if c:
        qasm_ops.append(("cx", int(c.group(1)), int(c.group(2))))
        continue
    u = re.fullmatch(r"u3\(([^)]*)\) q\[(\d+)\];", line)
    if u:
        t, p, l = (float(eval(a, {"__builtins__": {}}, NS)) for a in u.group(1).split(","))
        qasm_ops.append(("u3", int(u.group(2)), t, p, l))
        continue
    raise SystemExit(f"UNPARSED qasm line: {line!r}")

print(f"qmod ops = {len(qmod_ops)}   qasm ops = {len(qasm_ops)}   qubits = {nq}")
if qmod_ops == qasm_ops:
    print("IDENTITY: .qmod and .qasm are BIT-IDENTICAL gate sequences (exact float equality).")
else:
    diffs = [i for i, (a, b) in enumerate(zip(qmod_ops, qasm_ops)) if a != b]
    print(f"MISMATCH at {len(diffs)} positions; first 3: {[(qmod_ops[i], qasm_ops[i]) for i in diffs[:3]]}")
    raise SystemExit(1)

# ---------- build circuit from the QMOD and verify ----------
qc = QuantumCircuit(nq)
for op in qmod_ops:
    if op[0] == "cx":
        qc.cx(op[1], op[2])
    else:
        qc.u(op[2], op[3], op[4], op[1])

spec = io.logo_target()
res = verify(qc, spec, atol=1e-10)
print(f"VERIFY (atol=1e-10): {res}")

# notebook-style deviation
prep = QuantumCircuit(nq)
for q in range(N_DATA):
    prep.h(q)
sv = Statevector.from_instruction(prep.compose(qc)).data
expected = np.where(spec.truth == 1, -1.0, 1.0) / np.sqrt(DIM)
full = np.zeros(1 << nq, dtype=complex)
full[:DIM] = expected
gp = sv[np.argmax(np.abs(sv))] / full[np.argmax(np.abs(sv))]
dev = float(np.abs(sv - full * gp).max())
print(f"max statevector deviation = {dev:.3e}   (notebook bar 1e-10) -> {'PASS' if dev < 1e-10 else 'FAIL'}")
