"""Measure whether symmetry folding (y about 19/41, x about 40) shrinks the cover.
Benefit first: only worth decomposing into gates if the cover actually improves."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys, json, numpy as np
sys.path.insert(0, str(ROOT / "src"))
from collections import Counter
from qoracle import io
from qoracle.spec import OracleSpec
from qoracle.cover.esop_abc import cover as esop_cover

COST = {0:0,1:1,2:2,3:10,4:15,5:27,6:25,7:27,8:27,9:36,10:55,11:64,12:66}
spec = io.logo_target()
truth = np.asarray(spec.truth, dtype=np.uint8) & 1
ZS = np.arange(4096, dtype=np.int64)

def fold_field(v, center, bits=6):
    """Reversible sign-magnitude fold of a `bits`-wide field about `center`."""
    M = (1 << bits) - 1
    t = (v - center) & M
    s = (t >> (bits-1)) & 1
    u = t & ((1 << (bits-1)) - 1)
    u2 = np.where(s == 1, (-u) & ((1 << (bits-1)) - 1), u)
    return (s << (bits-1)) | u2

def apply_perm(z, fy=None, fx=None):
    x = z & 63; y = (z >> 6) & 63
    if fx is not None: x = fold_field(x, fx)
    if fy is not None: y = fold_field(y, fy)
    return (y << 6) | x

def evaluate(name, z):
    assert len(set(z.tolist())) == 4096, f"{name}: NOT a bijection"
    sp = OracleSpec(truth=np.asarray(truth[z], dtype=np.uint8), name=f"fold_{abs(hash(name))%10**9}")
    terms = esop_cover(sp).terms
    cc = sum(COST[bin(t.mask).count("1")] for t in terms)
    dist = dict(sorted(Counter(bin(t.mask).count("1") for t in terms).items()))
    print(f"{name:34s} cubes={len(terms):3d} cube_cost={cc:5d}  {dist}", flush=True)
    return cc, len(terms)

print("baseline (no transform):")
evaluate("identity", ZS.copy())
GATES = [tuple(g) for g in json.load(open("data/artifacts/lower/esop_hybrid_tree3/metrics.json"))["transform_gates"]]
z = ZS.copy()
for g in GATES:
    if g[0] == "tof":
        _, c1, c2, t = g; f = ((z >> c1) & 1) & ((z >> c2) & 1)
    else:
        _, c1, t = g; f = (z >> c1) & 1
    z = z ^ (f.astype(np.int64) << t)
evaluate("current 13-gate transform", z)

print("\nsymmetry folds (user's suggestion):")
for fy, fx, name in [(19,None,"fold y@19"), (41,None,"fold y@41"), (None,40,"fold x@40"),
                     (19,40,"fold y@19 + x@40"), (41,40,"fold y@41 + x@40")]:
    evaluate(name, apply_perm(ZS.copy(), fy, fx))

print("\nfold composed AFTER the 13-gate transform:")
for fy, fx, name in [(19,None,"13g + fold y@19"), (41,None,"13g + fold y@41"), (None,40,"13g + fold x@40"),
                     (19,40,"13g + fold y@19 + x@40")]:
    evaluate(name, apply_perm(z.copy(), fy, fx))
