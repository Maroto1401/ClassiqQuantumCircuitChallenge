"""GF(2) linear algebra helpers (rank / factorisation diagnostics)."""
from __future__ import annotations

import numpy as np


def rref(M: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Row-reduced echelon form over GF(2). Returns (R, pivot_columns)."""
    R = (np.asarray(M) & 1).astype(np.uint8).copy()
    rows, cols = R.shape
    piv: list[int] = []
    r = 0
    for c in range(cols):
        sel = None
        for rr in range(r, rows):
            if R[rr, c]:
                sel = rr
                break
        if sel is None:
            continue
        R[[r, sel]] = R[[sel, r]]
        hits = np.flatnonzero(R[:, c])
        for rr in hits:
            if rr != r:
                R[rr] ^= R[r]
        piv.append(c)
        r += 1
        if r == rows:
            break
    return R, piv


def rank(M: np.ndarray) -> int:
    return len(rref(M)[1])


def factor(M: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Factor M = U @ V (mod 2) with V a subset of ACTUAL ROWS of M.

    Real image rows synthesise far more cheaply than random GF(2) vectors, which
    is why we deliberately pick V from M rather than from the RREF basis.
    Returns (U, V, row_indices_used).
    """
    M = (np.asarray(M) & 1).astype(np.uint8)
    basis_rows: list[int] = []
    red: list[np.ndarray] = []  # reduced basis vectors, echelon by leading col
    lead: list[int] = []
    for i, row in enumerate(M):
        cur = row.copy()
        for b, l in zip(red, lead):
            if cur[l]:
                cur ^= b
        nz = np.flatnonzero(cur)
        if nz.size:
            basis_rows.append(i)
            red.append(cur)
            lead.append(int(nz[0]))
    V = M[basis_rows]
    # solve U: for each row of M, express in terms of V
    r = len(basis_rows)
    U = np.zeros((M.shape[0], r), dtype=np.uint8)
    for i, row in enumerate(M):
        cur = row.copy()
        coef = np.zeros(r, dtype=np.uint8)
        # greedy elimination against reduced basis, tracking combination
        combos = [np.eye(r, dtype=np.uint8)[j] for j in range(r)]
        red2: list[np.ndarray] = []
        # rebuild reduction with combination tracking
        work = [(V[j].copy(), combos[j]) for j in range(r)]
        for j in range(r):
            vec, cmb = work[j]
            for k in range(j):
                vk, ck = work[k]
                lk = int(np.flatnonzero(vk)[0])
                if vec[lk]:
                    vec ^= vk
                    cmb ^= ck
            work[j] = (vec, cmb)
        for vec, cmb in work:
            nz = np.flatnonzero(vec)
            if nz.size and cur[int(nz[0])]:
                cur ^= vec
                coef ^= cmb
        assert not cur.any(), "factorisation failed -- basis incomplete"
        U[i] = coef
    return U, V, basis_rows
