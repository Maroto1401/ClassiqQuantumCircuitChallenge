"""Phase-1 diagnostics. Pure functions of the spec; cheap; gate whole tracks.

Run these BEFORE choosing a synthesis route. Each returns plain data so the
runner can cache and diff results across specs.
"""
from __future__ import annotations

import numpy as np

from .gf2 import rank, factor
from .spec import DIM, N_DATA, N_X, N_Y, OracleSpec


# -- ANF / Moebius ----------------------------------------------------------
def anf(truth: np.ndarray) -> np.ndarray:
    """Algebraic normal form coefficients via the Moebius transform (in place, O(n 2^n))."""
    a = truth.copy().astype(np.uint8)
    n = N_DATA
    for i in range(n):
        step = 1 << i
        idx = np.arange(DIM)
        hi = idx[(idx & step) != 0]
        a[hi] ^= a[hi ^ step]
    return a


def anf_stats(spec: OracleSpec) -> dict:
    a = anf(spec.truth)
    terms = np.flatnonzero(a)
    degs = np.array([bin(int(t)).count("1") for t in terms], dtype=int) if terms.size else np.array([], int)
    return {
        "n_anf_terms": int(terms.size),
        "max_degree": int(degs.max()) if degs.size else 0,
        "total_literals": int(degs.sum()),
        "degree_histogram": {int(d): int(c) for d, c in zip(*np.unique(degs, return_counts=True))} if degs.size else {},
    }


# -- symmetry ---------------------------------------------------------------
def symmetry_report(spec: OracleSpec) -> dict:
    """Test the cheap geometric symmetries. A hit here is worth more than any
    downstream optimisation: it removes a VARIABLE for ~5 CX."""
    img = spec.to_image()
    out = {
        "mirror_x": bool(np.array_equal(img, img[:, ::-1])),      # f(x,y)=f(~x,y)
        "mirror_y": bool(np.array_equal(img, img[::-1, :])),      # f(x,y)=f(x,~y)
        "transpose": bool(np.array_equal(img, img.T)),            # f(x,y)=f(y,x)
        "anti_transpose": bool(np.array_equal(img, img[::-1, ::-1].T)),
        "rot180": bool(np.array_equal(img, img[::-1, ::-1])),
    }
    # partial mirrors: agreement fraction, to spot near-symmetry worth exploiting
    out["mirror_x_agreement"] = float((img == img[:, ::-1]).mean())
    out["mirror_y_agreement"] = float((img == img[::-1, :]).mean())
    # XOR-shift invariances f(x^c, y) == f(x,y)
    xs = [c for c in range(1, 1 << N_X) if np.array_equal(img, img[:, np.arange(1 << N_X) ^ c])]
    ys = [c for c in range(1, 1 << N_Y) if np.array_equal(img, img[np.arange(1 << N_Y) ^ c, :])]
    out["xor_invariant_x"] = xs
    out["xor_invariant_y"] = ys
    return out


# -- GF(2) rank -------------------------------------------------------------
def rank_report(spec: OracleSpec) -> dict:
    """If rank r is small, f(x,y) = XOR_i u_i(y) v_i(x) and the oracle becomes
    r DISJOINT CZ gates -- a single depth-1 layer. This is the highest-upside
    diagnostic in the repo. Kill Track C if r is large."""
    M = spec.to_image().astype(np.uint8)
    r = rank(M)
    verdict = "pursue" if r <= 16 else ("marginal" if r <= 32 else "drop")
    return {"gf2_rank": int(r), "dim": int(M.shape[0]), "verdict": verdict}


def rank_factorisation(spec: OracleSpec) -> dict:
    M = spec.to_image().astype(np.uint8)
    U, V, rows = factor(M)
    ok = bool(np.array_equal((U @ V) % 2, M))
    return {"rank": int(V.shape[0]), "row_indices": rows, "verified": ok}


# -- density ----------------------------------------------------------------
def density_report(spec: OracleSpec) -> dict:
    return {
        "n_marked": spec.n_marked,
        "dim": DIM,
        "density": spec.n_marked / DIM,
        "note": "complementing is a global phase: (-1)^~f = -(-1)^f. Never a win.",
    }


def run_all(spec: OracleSpec) -> dict:
    return {
        "spec_hash": spec.spec_hash,
        "density": density_report(spec),
        "symmetry": symmetry_report(spec),
        "rank": rank_report(spec),
        "anf": anf_stats(spec),
    }
