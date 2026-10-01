"""Find the BEST MCZ construction per control-count k, given 6 clean ancillas.

Variants: build a balanced RCCX AND-tree using (6 - r) ancillas, then finish the
residual with kg24 using the r reserved ones. r=0..3. Compare against plain kg24.
"""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys
sys.path.insert(0, str(ROOT / "src"))
import warnings, math, json
warnings.filterwarnings("ignore")
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import RCCXGate
from qiskit.quantum_info import Statevector
from qiskit.synthesis import synth_mcx_2_clean_kg24


def mcz(qc, controls, ancillas, reserve):
    tree_anc = list(ancillas[:len(ancillas) - reserve])
    res_anc = list(ancillas[len(ancillas) - reserve:])
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
        blk = synth_mcx_2_clean_kg24(len(level) - 1)
        need = blk.num_qubits - len(level)
        if need <= len(pool):
            qc.h(level[-1])
            qc.compose(blk, qubits=list(level[:-1]) + [level[-1]] + pool[:need], inplace=True)
            qc.h(level[-1])
        else:
            qc.mcp(math.pi, list(level[:-1]), level[-1])
    for a, x, y in reversed(undo):
        qc.append(RCCXGate().inverse(), [x, y, a])


def check(k, reserve, n_anc=6):
    qc = QuantumCircuit(k + n_anc)
    for i in range(k): qc.h(i)
    mcz(qc, list(range(k)), list(range(k, k + n_anc)), reserve)
    sv = Statevector.from_instruction(qc).data
    amp = 2 ** (-k / 2)
    bad = sum(1 for s in range(1 << k)
              if abs(sv[s] - (-amp if s == (1 << k) - 1 else amp)) > 1e-9)
    leak = sum(1 for i in range(1 << (k + n_anc)) if (i >> k) != 0 and abs(sv[i]) > 1e-9)
    return bad == 0 and leak == 0


def cost(k, reserve, n_anc=6):
    qc = QuantumCircuit(k + n_anc)
    mcz(qc, list(range(k)), list(range(k, k + n_anc)), reserve)
    t = transpile(qc, basis_gates=["u3", "cx"], optimization_level=3)
    return t.depth(), t.count_ops().get("cx", 0)


def kg_cost(k):
    blk = synth_mcx_2_clean_kg24(k - 1); na = blk.num_qubits - k
    qc = QuantumCircuit(k + max(0, na)); qc.h(k - 1)
    qc.compose(blk, qubits=list(range(k-1)) + [k-1] + list(range(k, k+na)), inplace=True)
    qc.h(k - 1)
    t = transpile(qc, basis_gates=["u3","cx"], optimization_level=3)
    return t.depth(), t.count_ops().get("cx", 0)


best_table = {}
print(f"{'k':>3} {'kg24':>10} " + " ".join(f"{'tree r=%d'%r:>10}" for r in range(4)) + "   BEST")
for k in range(3, 13):
    dk, ck = kg_cost(k)
    row = [f"{dk}/{ck}"]
    opts = [("kg24", dk, ck)]
    for r in range(4):
        d, c = cost(k, r)
        ok = check(k, r) if k <= 9 else True
        row.append(f"{d}/{c}" + ("" if ok else "!"))
        if ok: opts.append((f"tree{r}", d, c))
    nm, bd, bc = min(opts, key=lambda t: (t[1], t[2]))
    best_table[k] = {"method": nm, "depth": bd, "cx": bc}
    print(f"{k:>3} " + " ".join(f"{x:>10}" for x in row) + f"   {nm} {bd}/{bc}")

json.dump(best_table, open("research/mcz_best_table.json","w"), indent=2)
print("\nsaved per-k best table")
