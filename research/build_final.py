"""Rebuild the FINAL submitted circuit (depth 1332 / cx 1317, width 18).

Also serves as the controlled experiment that produced it: builds the identical
circuit twice -- same ESOP cover, same cube order -- changing ONLY whether the
change-of-variables permutation U uses full Toffolis or relative-phase ones.
Because the oracle is U^dag . D . U with D diagonal, U = Lambda . P and
U^dag D U = P^dag Lambda^dag D Lambda P = P^dag D P: the relative phases cancel
identically, so RCCX (depth 7 / 3 cx) is a free substitute for CCX (11 / 6).

    CCX  (control) -> depth 1358, cx 1336
    RCCX (shipped) -> depth 1332, cx 1317
U = Lambda.P for RCCX, so U^dag D U = P^dag Lambda^dag D Lambda P = P^dag D P -- same unitary."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys, json, pathlib, math, warnings, numpy as np
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")
from qiskit import QuantumCircuit, transpile, qasm2
from qiskit.circuit.library import RCCXGate
from qiskit.synthesis import synth_mcx_2_clean_kg24
from qoracle import io
from qoracle.spec import OracleSpec
from qoracle.cover.esop_abc import cover as esop_cover
from qoracle.verify import verify

N_DATA, N_ANC = 12, 6
spec = io.logo_target()
truth = np.asarray(spec.truth, dtype=np.uint8) & 1
M = json.load(open("research/final_build_params.json"))
GATES = [tuple(g) for g in M["transform_gates"]]
ORDER = list(M["cube_order"])
BEST_K = {int(k): tuple(v) for k, v in M["per_k_mcz_method"].items()}

z = np.arange(4096, dtype=np.int64)
for g in GATES:
    if g[0] == "tof":
        _, c1, c2, t = g; f = ((z >> c1) & 1) & ((z >> c2) & 1)
    else:
        _, c1, t = g; f = (z >> c1) & 1
    z = z ^ (f.astype(np.int64) << t)
gspec = OracleSpec(truth=np.asarray(truth[z], dtype=np.uint8), name="g")
cubes = [(c.mask, c.value) for c in esop_cover(gspec).terms]
print(f"cover reproduced: {len(cubes)} cubes (expect {M['n_cubes']})", flush=True)
anc = list(range(N_DATA, N_DATA + N_ANC)); _kg = {}

def mcz_tree(qc, controls, ancillas, reserve=0):
    tree_anc = list(ancillas[:len(ancillas)-reserve]); res_anc = list(ancillas[len(ancillas)-reserve:])
    level, free, undo = list(controls), tree_anc, []
    while len(level) > 2 and free:
        nxt, i = [], 0
        while i + 1 < len(level) and free:
            a = free.pop(0)
            qc.append(RCCXGate(), [level[i], level[i+1], a])
            undo.append((a, level[i], level[i+1])); nxt.append(a); i += 2
        nxt.extend(level[i:])
        if len(nxt) == len(level): break
        level = nxt
    pool = free + res_anc
    if len(level) == 1: qc.z(level[0])
    elif len(level) == 2: qc.cz(level[0], level[1])
    else:
        blk = synth_mcx_2_clean_kg24(len(level)-1); need = blk.num_qubits - len(level)
        if need <= len(pool):
            qc.h(level[-1]); qc.compose(blk, qubits=list(level[:-1])+[level[-1]]+pool[:need], inplace=True); qc.h(level[-1])
        else:
            qc.mcp(math.pi, list(level[:-1]), level[-1])
    for a, x, y in reversed(undo):
        qc.append(RCCXGate().inverse(), [x, y, a])

def mcz_kg(qc, lits):
    ctrls, tgt = lits[:-1], lits[-1]
    if len(ctrls) not in _kg: _kg[len(ctrls)] = synth_mcx_2_clean_kg24(len(ctrls))
    blk = _kg[len(ctrls)]; need = blk.num_qubits - len(lits)
    qc.h(tgt); qc.compose(blk, qubits=ctrls+[tgt]+anc[:need], inplace=True); qc.h(tgt)

def emit_perm(qc, rev, use_rccx):
    for g in (reversed(GATES) if rev else GATES):
        if g[0] == "tof":
            if use_rccx: qc.append(RCCXGate().inverse() if rev else RCCXGate(), [g[1], g[2], g[3]])
            else: qc.ccx(g[1], g[2], g[3])
        else: qc.cx(g[1], g[2])

def build(order, use_rccx):
    qc = QuantumCircuit(N_DATA + N_ANC)
    emit_perm(qc, True, use_rccx)
    for idx in order:
        mask, value = cubes[idx]
        lits = [i for i in range(N_DATA) if (mask >> i) & 1]
        if not lits: qc.global_phase += math.pi; continue
        flips = [i for i in lits if not ((value >> i) & 1)]
        for b in flips: qc.x(b)
        if len(lits) == 1: qc.z(lits[0])
        elif len(lits) == 2: qc.cz(lits[0], lits[1])
        else:
            meth, res = BEST_K.get(len(lits), ("kg", 0))
            if meth == "tree": mcz_tree(qc, lits, anc, res)
            else: mcz_kg(qc, lits)
        for b in flips: qc.x(b)
    emit_perm(qc, False, use_rccx)
    return qc

best_rccx = None
for use_rccx in (False, True):
    qc = build(ORDER, use_rccx)
    t = transpile(qc, basis_gates=["u3","cx"], optimization_level=3, seed_transpiler=0)
    d, c = t.depth(), t.count_ops().get("cx", 0)
    r8 = verify(t, spec, atol=1e-8); r10 = verify(t, spec, atol=1e-10)
    tag = "RCCX" if use_rccx else "CCX (control)"
    print(f"{tag:15s} depth={d:5d} cx={c:5d}  verify1e-10={r10['ok']} n_wrong={r10['n_wrong']}", flush=True)
    if use_rccx and r10["ok"]: best_rccx = (d, c, t)

if best_rccx:
    d, c, t = best_rccx
    out = "research/oracle_rebuilt.qasm"
    open(out, "w").write(qasm2.dumps(t))
    print(f"\nsaved -> {out}  (should match submission.qasm)")
    if pathlib.Path("submission.qasm").exists():
        same = open(out).read() == open("submission.qasm").read()
        print("byte-identical to submission.qasm:", same)
