"""Non-linear transform search using the MEASURED per-cube depth cost table
(min of AND-tree / kg24 at each control count), not cube count.

Costs are very non-uniform: k<=8 -> 27, k=9 -> 36, k=10 -> 55, k=11 -> 64,
k=12 -> 73. So a cover with many 11/12-literal cubes is far worse than its
cube count suggests. Optimize what we actually pay."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys
sys.path.insert(0, str(ROOT / "src"))
import random, json, numpy as np
from collections import Counter
from qoracle import io
from qoracle.spec import OracleSpec
from qoracle.cover.esop_abc import cover as esop_cover

COST = {0:0, 1:1, 2:2, 3:10, 4:15, 5:27, 6:27, 7:27, 8:27, 9:36, 10:55, 11:64, 12:73}
D_TOF, D_CX, MAXG = 22.0, 4.0, 40

spec = io.logo_target()
truth = np.asarray(spec.truth, dtype=np.uint8) & 1
ZS = np.arange(4096, dtype=np.int64)

def perm(gates):
    z = ZS.copy()
    for g in gates:
        if g[0] == "tof":
            _, c1, c2, t = g; f = ((z >> c1) & 1) & ((z >> c2) & 1)
        else:
            _, c1, t = g; f = (z >> c1) & 1
        z = z ^ (f.astype(np.int64) << t)
    return z

_ev = {}
def cube_cost(gates):
    k = tuple(gates)
    if k in _ev: return _ev[k]
    sp = OracleSpec(truth=np.asarray(truth[perm(gates)], dtype=np.uint8), name=f"nlcm_{abs(hash(k))%10**9}")
    try:
        cubes = esop_cover(sp).terms
        c = sum(COST[bin(t.mask).count("1")] for t in cubes)
        info = (c, len(cubes))
    except Exception:
        info = (99999, 999)
    _ev[k] = info
    return info

def cost(g):
    return cube_cost(g)[0] + sum(D_TOF if x[0]=="tof" else D_CX for x in g)

def rnd_gate(r):
    qs = r.sample(range(12), 3)
    return ("tof", qs[0], qs[1], qs[2]) if r.random() < 0.55 else ("cx", qs[0], qs[1])

seed_gates = [tuple(g) for g in json.load(open("research/nonlinear_best4.json"))["gates"]]
bc, bn = cube_cost([])
print(f"identity:        cubes={bn} cube_cost={bc}")
sc, sn = cube_cost(seed_gates)
print(f"current 10-gate: cubes={sn} cube_cost={sc} total={cost(seed_gates):.0f}", flush=True)

best_g, best_c = list(seed_gates), cost(seed_gates)
rng = random.Random(31337)
for hop in range(30):
    cur = list(best_g)
    for _ in range(rng.randint(1, 4)):
        if cur and rng.random() < 0.35: cur.pop(rng.randrange(len(cur)))
        else: cur.insert(rng.randrange(len(cur)+1), rnd_gate(rng))
    cur_c = cost(cur); loc_g, loc_c = list(cur), cur_c
    T0, T1, STEPS = 50.0, 1.0, 700
    for s in range(STEPS):
        T = T0 * ((T1/T0) ** (s/(STEPS-1)))
        g = list(cur); r = rng.random()
        if g and r < 0.28: g.pop(rng.randrange(len(g)))
        elif g and r < 0.48: g[rng.randrange(len(g))] = rnd_gate(rng)
        else: g.insert(rng.randrange(len(g)+1), rnd_gate(rng))
        if len(g) > MAXG: continue
        c = cost(g)
        if c <= cur_c or rng.random() < pow(2.718281828, -(c-cur_c)/T):
            cur, cur_c = g, c
            if c < loc_c: loc_g, loc_c = list(g), c
    if loc_c < best_c:
        best_g, best_c = list(loc_g), loc_c
        cc, nn = cube_cost(best_g)
        print(f"  hop {hop:2d}: cubes={nn} cube_cost={cc} gates={len(best_g)} total={best_c:.0f}  <-- NEW BEST", flush=True)

cc, nn = cube_cost(best_g)
sp = OracleSpec(truth=np.asarray(truth[perm(best_g)],dtype=np.uint8), name="nlcm_final")
dist = Counter(bin(t.mask).count("1") for t in esop_cover(sp).terms)
print(f"\nBEST: cubes={nn} cube_cost={cc} gates={len(best_g)} total={best_c:.0f}")
print("literal distribution:", dict(sorted(dist.items())))
print("gates:", best_g)
json.dump({"gates":[list(g) for g in best_g],"cubes":nn,"cube_cost":cc},
          open("research/nonlinear_best5.json","w"))
