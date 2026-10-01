"""Notebook Step 6, verbatim, against submission.qasm."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import re, warnings
from pathlib import Path
import numpy as np
import classiq
from classiq import *
from classiq.execution import ExecutionSession
from classiq import TranspilationOption

GRID_SIZE, COORD_BITS = 64, 6
def logo_pixel(x, y):
    return ((2 <= x <= 26 and 29 <= y <= 53) or (26 <= x <= 49 and 39 <= y <= 43)
            or (x - 55) ** 2 + (y - 41) ** 2 <= 42 or (x - 40) ** 2 + (y - 19) ** 2 <= 72)

STATE_ERROR_THRESHOLD = 1e-10
NORMALIZATION_ERROR_THRESHOLD = 1e-10

def qasm_metrics(source):
    statements = [s.strip() for s in re.sub(r"//[^\n]*", "", source).split(";") if s.strip()]
    if statements[:2] != ["OPENQASM 2.0", 'include "qelib1.inc"']:
        raise ValueError("Expected an OpenQASM 2.0 file using qelib1.inc")
    qm = re.fullmatch(r"qreg\s+q\s*\[\s*(\d+)\s*\]", statements[2]) if len(statements) >= 3 else None
    if qm is None: raise ValueError("Expected exactly one register named q")
    width = int(qm.group(1))
    if not 12 <= width <= 18: raise ValueError(f"bad width {width}")
    qd, cx_count = [0]*width, 0
    for st in statements[3:]:
        u3m = re.fullmatch(r"u3\s*\([^,]+,[^,]+,[^,]+\)\s+q\s*\[\s*(\d+)\s*\]", st)
        cxm = re.fullmatch(r"cx\s+q\s*\[\s*(\d+)\s*\]\s*,\s*q\s*\[\s*(\d+)\s*\]", st)
        if u3m: qubits = (int(u3m.group(1)),)
        elif cxm: qubits = tuple(map(int, cxm.groups())); cx_count += 1
        else: raise ValueError(f"Unsupported QASM statement: {st}")
        if any(q >= width for q in qubits): raise ValueError(f"out of range: {st}")
        if len(set(qubits)) != len(qubits): raise ValueError(f"dup operands: {st}")
        layer = max(qd[q] for q in qubits) + 1
        for q in qubits: qd[q] = layer
    return width, max(qd, default=0), cx_count

def dense_classiq_statevector(frame, width):
    sv = np.zeros(1 << width, dtype=np.complex128); seen = set()
    for row in frame.itertuples(index=False):
        bs = str(row.bitstring).replace(" ", "")
        if len(bs) != width or set(bs) - {"0","1"}: raise ValueError(f"bad bitstring {row.bitstring}")
        bi = int(bs, 2)
        if bi in seen: raise ValueError(f"dup basis {bs}")
        amp = complex(row.amplitude)
        if not np.isfinite(amp.real) or not np.isfinite(amp.imag): raise ValueError("non-finite")
        seen.add(bi); sv[bi] = amp
    if not seen: raise ValueError("empty statevector")
    ne = abs(np.vdot(sv, sv).real - 1)
    if ne >= NORMALIZATION_ERROR_THRESHOLD: raise ValueError(f"not normalized: {ne:.3e}")
    return sv, ne

QASM_PATH = Path("submission.qasm")
submission_source = QASM_PATH.read_text(encoding="utf-8")
submission_width, depth, cx_count = qasm_metrics(submission_source)
print(f"metrics: width={submission_width} depth={depth} cx={cx_count}", flush=True)

logical_size = GRID_SIZE**2
rng = np.random.default_rng()
random_phases = rng.uniform(-np.pi, np.pi, size=(3, 2*COORD_BITS))
target_phases = np.array([-1 if logo_pixel(x,y) else 1
                          for y in range(GRID_SIZE) for x in range(GRID_SIZE)], dtype=np.complex128)
swc = re.sub(r"//[^\n]*", lambda m: " "*len(m.group()), submission_source)
qm = list(re.finditer(rf"\bqreg\s+q\s*\[\s*{submission_width}\s*\]\s*;", swc))
if len(qm) != 1: raise ValueError("QASM must contain exactly one matching q register")
insertion_index = qm[0].end()
basis = np.arange(logical_size, dtype=np.uint16)
max_error = ancilla_error = normalization_error = 0.0
shared_global_phase = 1 + 0j

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Non-zero amplitudes were detected in states with non-zero auxiliary values.*")
    for test_index, phases in enumerate(random_phases):
        prep = [f"u3(pi/2,{p:.17g},0) q[{q}];" for q, p in enumerate(phases)]
        test_qasm = submission_source[:insertion_index] + "\n" + "\n".join(prep) + submission_source[insertion_index:]
        print(f"  running state {test_index+1}/3 ...", flush=True)
        with ExecutionSession(test_qasm, backend="classiq/simulator",
                              transpilation_option=TranspilationOption.DECOMPOSE) as session:
            frame = session.calculate_state_vector(amplitude_threshold=0.0)
        sv, ne = dense_classiq_statevector(frame, submission_width)
        normalization_error = max(normalization_error, ne)
        ancilla_error = max(ancilla_error, np.max(np.abs(sv[logical_size:]), initial=0.0))
        bp = np.zeros(logical_size)
        for q, p in enumerate(phases): bp += ((basis >> q) & 1) * p
        exp = np.zeros(1 << submission_width, dtype=np.complex128)
        exp[:logical_size] = np.exp(1j*bp)/np.sqrt(logical_size)*target_phases
        if test_index == 0:
            ov = np.vdot(exp, sv)
            if abs(ov) <= 1e-12: raise ValueError("cannot determine global phase")
            shared_global_phase = ov/abs(ov)
        max_error = max(max_error, np.max(np.abs(sv - shared_global_phase*exp)))

if ancilla_error >= STATE_ERROR_THRESHOLD: raise ValueError(f"dirty ancillas: {ancilla_error:.3e}")
if max_error >= STATE_ERROR_THRESHOLD: raise ValueError(f"verification failed: {max_error:.3e}")
print(f"\nSuccessfully verified loaded QASM with score {depth}:\n"
      f"random states = {len(random_phases)}\nwidth = {submission_width}\ndepth = {depth}\n"
      f"CX count = {cx_count}\nmax error = {max_error:.1e}\nancilla error = {ancilla_error:.1e}\n"
      f"normalization error = {normalization_error:.1e}")
