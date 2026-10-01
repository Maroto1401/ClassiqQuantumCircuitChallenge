"""Custom multi-controlled Z using a BALANCED AND-TREE over all 6 ancillas.

kg24 uses only 2 ancillas. With 6 we can compute partial ANDs on DISJOINT
control pairs concurrently -> log-depth tree instead of a serial chain.
Spends more CX to buy depth; CX is only the tiebreak, depth is scored.
RCCX (relative-phase Toffoli, 3 CX) is safe for the tree: the relative phases
cancel exactly against the uncompute, since only a diagonal gate sits between.
"""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys
sys.path.insert(0, str(ROOT / "src"))
import warnings
warnings.filterwarnings("ignore")
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import RCCXGate, MCXGate
from qiskit.quantum_info import Statevector
from qiskit.synthesis import synth_mcx_2_clean_kg24


def mcz_tree(qc, controls, ancillas):
    """Apply -1 phase iff all `controls` are 1, using a balanced AND tree."""
    level = list(controls)
    free = list(ancillas)
    undo = []
    while len(level) > 2 and len(free) >= 1:
        nxt, i = [], 0
        while i + 1 < len(level) and free:
            a = free.pop(0)
            qc.append(RCCXGate(), [level[i], level[i + 1], a])
            undo.append((a, level[i], level[i + 1]))
            nxt.append(a)
            i += 2
        nxt.extend(level[i:])
        if len(nxt) == len(level):
            break
        level = nxt
    if len(level) == 1:
        qc.z(level[0])
    elif len(level) == 2:
        qc.cz(level[0], level[1])
    else:
        blk = synth_mcx_2_clean_kg24(len(level) - 1)
        need = blk.num_qubits - len(level)
        if need <= len(free):
            qc.h(level[-1])
            qc.compose(blk, qubits=list(level[:-1]) + [level[-1]] + free[:need], inplace=True)
            qc.h(level[-1])
        else:
            import math as _m
            qc.mcp(_m.pi, list(level[:-1]), level[-1])
    for a, x, y in reversed(undo):
        qc.append(RCCXGate().inverse(), [x, y, a])


def verify_mcz(k, n_anc):
    """Check the tree MCZ applies -1 exactly on the all-ones control state."""
    qc = QuantumCircuit(k + n_anc)
    for i in range(k):
        qc.h(i)
    mcz_tree(qc, list(range(k)), list(range(k, k + n_anc)))
    sv = Statevector.from_instruction(qc).data
    amp = 2 ** (-k / 2)
    bad = 0
    for s in range(1 << k):
        exp = -amp if s == (1 << k) - 1 else amp
        if abs(sv[s] - exp) > 1e-9:
            bad += 1
    leak = sum(1 for i in range(1 << (k + n_anc)) if (i >> k) != 0 and abs(sv[i]) > 1e-9)
    return bad, leak


def cost_tree(k, n_anc):
    qc = QuantumCircuit(k + n_anc)
    mcz_tree(qc, list(range(k)), list(range(k, k + n_anc)))
    t = transpile(qc, basis_gates=["u3", "cx"], optimization_level=3)
    return t.depth(), t.count_ops().get("cx", 0)


def cost_kg24(k):
    blk = synth_mcx_2_clean_kg24(k - 1)
    n_anc = blk.num_qubits - k
    qc = QuantumCircuit(k + max(0, n_anc))
    qc.h(k - 1)
    qc.compose(blk, qubits=list(range(k - 1)) + [k - 1] + list(range(k, k + n_anc)), inplace=True)
    qc.h(k - 1)
    t = transpile(qc, basis_gates=["u3", "cx"], optimization_level=3)
    return t.depth(), t.count_ops().get("cx", 0)


print("correctness of tree MCZ (bad_amplitudes, ancilla_leak):")
for k in (3, 5, 8, 9):
    print(f"  k={k}, 6 anc -> {verify_mcz(k, 6)}")

print(f"\n{'k':>3} {'kg24 (2 anc)':>16} {'tree (6 anc)':>16}  {'depth change':>14}")
for k in range(3, 13):
    dk, ck = cost_kg24(k)
    dt, ct = cost_tree(k, 6)
    print(f"{k:>3} {f'{dk}/{ck}':>16} {f'{dt}/{ct}':>16}  {100*(dt-dk)/dk:>+12.0f}%")
