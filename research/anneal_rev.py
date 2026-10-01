"""CPU prototype of the reversible-circuit annealing the top solutions reportedly use.

Target form:  oracle = U . Z(flag) . U^dagger, so depth = 2*depth(U)+1 and we only
need U to COMPUTE f into a flag qubit (ancillas need not be restored -- U^dag does it).
For 97 total depth we need depth(U) ~ 48. Search over {X, CX, CCX} on 18 qubits.

Vectorised: simulate all 4096 inputs at once as bit-planes.
"""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys
sys.path.insert(0, str(ROOT / "src"))
import random, numpy as np
from qoracle import io

NQ, NDATA = 18, 12
FLAG = 12                      # ancilla holding f; 13..17 are workspace
spec = io.logo_target()
F = (np.asarray(spec.truth, dtype=np.int64) & 1).astype(np.uint8)   # index = x|(y<<6)
XS = np.arange(4096, dtype=np.int64)
INIT = np.zeros((NQ, 4096), dtype=np.uint8)
for b in range(NDATA):
    INIT[b] = ((XS >> b) & 1).astype(np.uint8)

def simulate(gates):
    s = INIT.copy()
    for g in gates:
        if g[0] == 0: s[g[1]] ^= 1
        elif g[0] == 1: s[g[2]] ^= s[g[1]]
        else: s[g[3]] ^= s[g[1]] & s[g[2]]
    return s

def wrong(gates):
    return int((simulate(gates)[FLAG] != F).sum())

def depth(gates):
    """exact layered depth over the qubits each gate touches"""
    t = [0]*NQ
    for g in gates:
        q = [g[1]] if g[0]==0 else ([g[1],g[2]] if g[0]==1 else [g[1],g[2],g[3]])
        d = max(t[i] for i in q)+1
        for i in q: t[i] = d
    return max(t) if t else 0

def rnd_gate(r):
    k = r.random()
    if k < 0.15:
        return (0, r.randrange(NQ))
    if k < 0.55:
        a, b = r.sample(range(NQ), 2); return (1, a, b)
    a, b, c = r.sample(range(NQ), 3); return (2, a, b, c)

# ---- seed: build a correct U from the ESOP cubes via CCX ladders ----
from qoracle.cover.esop_abc import cover as esop_cover
cubes = [(c.mask, c.value) for c in esop_cover(spec).terms]
WS = [13,14,15,16,17]

def and_into(g, lits, target, scr):
    """g += gates computing target ^= AND(lits); scr restored to |0>."""
    k = len(lits)
    if k == 1: g.append((1, lits[0], target)); return
    if k == 2: g.append((2, lits[0], lits[1], target)); return
    if k - 2 <= len(scr):
        w = scr[:k-2]
        g.append((2, lits[0], lits[1], w[0]))
        for i in range(1, k-2): g.append((2, w[i-1], lits[i+1], w[i]))
        g.append((2, w[k-3], lits[k-1], target))
        for i in range(k-3, 0, -1): g.append((2, w[i-1], lits[i+1], w[i]))
        g.append((2, lits[0], lits[1], w[0]))
        return
    h = k // 2
    a, b, rest = scr[0], scr[1], scr[2:]
    and_into(g, lits[:h], a, rest); and_into(g, lits[h:], b, rest)
    g.append((2, a, b, target))
    and_into(g, lits[h:], b, rest); and_into(g, lits[:h], a, rest)

seed = []
for mask, val in cubes:
    lits = [i for i in range(NDATA) if (mask >> i) & 1]
    flips = [i for i in lits if not ((val >> i) & 1)]
    for b in flips: seed.append((0, b))
    and_into(seed, lits, FLAG, WS)
    for b in flips: seed.append((0, b))

w0, d0 = wrong(seed), depth(seed)
print(f"seed circuit U: gates={len(seed)} wrong={w0} depth(U)={d0} -> oracle depth ~{2*d0+1}")
if w0 != 0:
    print("seed incorrect, aborting"); sys.exit(1)

def cost(g, lam=1.0):
    return 400.0*wrong(g) + lam*depth(g)

rng = random.Random(0)
cur = list(seed); cc = cost(cur)
best, bc = list(cur), cc
T0, T1, STEPS = 30.0, 0.5, 4000
import time; t0=time.time()
for s in range(STEPS):
    T = T0*((T1/T0)**(s/(STEPS-1)))
    g = list(cur); r = rng.random()
    if g and r < 0.45: g.pop(rng.randrange(len(g)))
    elif g and r < 0.75: g[rng.randrange(len(g))] = rnd_gate(rng)
    else: g.insert(rng.randrange(len(g)+1), rnd_gate(rng))
    c = cost(g)
    if c <= cc or rng.random() < pow(2.718281828, -(c-cc)/T):
        cur, cc = g, c
        if c < bc and wrong(g) == 0:
            best, bc = list(g), c
            print(f"  step {s:4d}: gates={len(g):4} depth(U)={depth(g):4} -> oracle ~{2*depth(g)+1}", flush=True)
print(f"\n{STEPS} steps in {time.time()-t0:.0f}s")
print(f"BEST correct U: gates={len(best)} depth(U)={depth(best)} -> oracle depth ~{2*depth(best)+1}, wrong={wrong(best)}")
print(f"(seed was oracle ~{2*d0+1};  our built best = 1330;  leader = 97)")
