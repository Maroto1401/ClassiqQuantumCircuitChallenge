"""Full oracle: non-linear transform + per-cube MCZ chosen per control-count
(AND-tree on 6 ancillas where it wins, kg24 elsewhere) + optimized cube order.
Uses the FULL 18-qubit budget (12 data + 6 ancilla)."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys
sys.path.insert(0, str(ROOT / "src"))
import warnings, random, json, os, math, numpy as np
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
ZS = np.arange(4096, dtype=np.int64)
GATES = [tuple(g) for g in json.load(open("research/nonlinear_best6.json"))["gates"]]

z = ZS.copy()
for g in GATES:
    if g[0] == "tof":
        _, c1, c2, t = g; f = ((z >> c1) & 1) & ((z >> c2) & 1)
    else:
        _, c1, t = g; f = (z >> c1) & 1
    z = z ^ (f.astype(np.int64) << t)
gspec = OracleSpec(truth=np.asarray(truth[z], dtype=np.uint8), name="hybrid_g3")
cubes = [(c.mask, c.value) for c in esop_cover(gspec).terms]
from collections import Counter
sizes = Counter(bin(m).count("1") for m, v in cubes)
print(f"{len(cubes)} cubes; literal distribution: {dict(sorted(sizes.items()))}")

# measured per-k optimum: (method, reserve). kg24 for k=3,11; tree elsewhere.
BEST_K = {3:("kg",0), 4:("tree",0), 5:("tree",0), 6:("tree",3), 7:("tree",0),
          8:("tree",0), 9:("tree",0), 10:("tree",0), 11:("kg",0), 12:("tree",2)}
anc = list(range(N_DATA, N_DATA + N_ANC))
_kg = {}

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
            qc.h(level[-1])
            qc.compose(blk, qubits=list(level[:-1])+[level[-1]]+pool[:need], inplace=True)
            qc.h(level[-1])
        else:
            qc.mcp(math.pi, list(level[:-1]), level[-1])
    for a, x, y in reversed(undo):
        qc.append(RCCXGate().inverse(), [x, y, a])

def mcz_kg(qc, lits):
    ctrls, tgt = lits[:-1], lits[-1]
    if len(ctrls) not in _kg: _kg[len(ctrls)] = synth_mcx_2_clean_kg24(len(ctrls))
    blk = _kg[len(ctrls)]; need = blk.num_qubits - len(lits)
    qc.h(tgt); qc.compose(blk, qubits=ctrls+[tgt]+anc[:need], inplace=True); qc.h(tgt)

def emit_perm(qc, rev):
    for g in (reversed(GATES) if rev else GATES):
        if g[0] == "tof": qc.ccx(g[1], g[2], g[3])
        else: qc.cx(g[1], g[2])

def build(order):
    qc = QuantumCircuit(N_DATA + N_ANC)
    emit_perm(qc, True)
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
    emit_perm(qc, False)
    return qc

n = len(cubes)
def agree(i,j):
    mi,vi = cubes[i]; mj,vj = cubes[j]
    return bin(~(mi^mj) & ~(vi^vj) & 0xFFF).count("1") + bin(mi & mj).count("1")
PAIR=[[agree(i,j) for j in range(n)] for i in range(n)]
def proxy(o): return sum(PAIR[o[k]][o[k+1]] for k in range(len(o)-1))
rem=set(range(n)); cur=0; greedy=[cur]; rem.discard(cur)
while rem:
    nx=max(rem,key=lambda j:PAIR[cur][j]); greedy.append(nx); rem.discard(nx); cur=nx

cands={}
for seed in range(5):
    r=random.Random(seed); o = greedy[:] if seed==0 else r.sample(range(n),n); bs=proxy(o)
    for _ in range(50000):
        a,b=sorted(r.sample(range(n),2)); c2=o[:a]+o[a:b+1][::-1]+o[b+1:]; s=proxy(c2)
        if s>=bs: o,bs=c2,s
    cands[tuple(o)]=bs

best=None
for order,s in sorted(cands.items(), key=lambda kv:-kv[1])[:4]:
    qc=build(list(order)); t=transpile(qc,basis_gates=["u3","cx"],optimization_level=3)
    d,c=t.depth(),t.count_ops().get("cx",0); res=verify(t,spec)
    print(f"  proxy={s:5} -> depth={d:5} cx={c:5} verify={res['ok']}", flush=True)
    if res["ok"] and (best is None or (d,c)<(best[0],best[1])): best=(d,c,t,list(order))

d,c,t,order=best
print(f"\nHYBRID BEST: depth={d} cx={c} width={t.num_qubits}  (previous best 1759/1358 @ w14)")
out="data/artifacts/lower/esop_hybrid_tree3"
os.makedirs(out,exist_ok=True)
open(out+"/oracle.qasm","w").write(qasm2.dumps(t))
json.dump({"name":"esop_hybrid_tree3","width":t.num_qubits,"depth":d,"cx":c,"n_cubes":len(cubes),
  "transform_gates":[list(g) for g in GATES],"per_k_method":{str(k):v for k,v in BEST_K.items()},"order":order,
  "verified":True,"verify":verify(t,spec),
  "source":"non-linear transform (10 gates) + 40-cube ESOP; per-cube MCZ selected by control count: balanced RCCX AND-tree on 6 ancillas for k=4..10 (25-50% shallower than kg24), kg24 2-clean otherwise; optimized cube order. Uses full 18-qubit budget."},
  open(out+"/metrics.json","w"),indent=2)
print("saved ->",out)
