# qoracle — low-depth phase oracle for a 64×64 binary image

12 qubits (x:6, y:6), 1097 marked pixels. Build a diagonal oracle
`|x,y> -> (-1)^f(x,y) |x,y>`. **Ranked by circuit depth, CX count as tiebreak.**

## The one architectural idea

The pipeline is cut at **`PhaseIR`** — a synthesis-independent list of XOR-ed
product terms (cubes) plus an optional affine pre-map.

```
spec ──diagnostics──► (report)
  │
  └─► COVER ──► PhaseIR ──► LOWER ──► circuit(QPY) ──► VERIFY ──► METRICS ──► QASM export
      expensive   cached     cheap      canonical       cached     derived      view
      cached                 cached
```

Everything **above** the cut is expensive and cached (ESOP minimisation, basis
search, factorisation). Everything **below** is cheap and re-runnable
(decomposition, scheduling, transpilation, metrics, export).

Consequences, which is the whole point:

| you change | you re-run | you do NOT re-run |
|---|---|---|
| metric definition / gate set | `qo score` | anything |
| lowering / scheduling idea | `qo run --lowering X` | cover minimisation |
| cover strategy | that cover only | other covers |

Two separate version stamps (`COVER_VERSION`, `LOWER_VERSION`) let you invalidate
one stage's cache without touching the other.

**Canonical artifact is QPY at the high level** (multi-controlled gates intact),
not QASM. Re-scoring then re-transpiles from structured form, which beats
re-transpiling an already-decomposed circuit. QASM is an export view.

## Quickstart

```bash
pip install -e ".[dev]"
pytest -q
qo diag                                    # Phase-1 diagnostics
qo run --cover pprm --lowering serial_mcz  # full pipeline
qo score --basis cx_u                      # re-score everything, no re-synthesis
qo leaderboard
```

Works today on a built-in synthetic target with the right shape and density, so
the machinery is exercised before the real logo arrives. Swap it with
`--target data/raw/logo.npy`.

## Status

Proven end-to-end (synthetic target, opt_level 1, placeholder numbers):

| cover | terms | literals | depth | cx | verified |
|---|---|---|---|---|---|
| pprm | 1482 | 9708 | 90630 | 56559 | ✅ |
| minterm | 1097 | 13164 | 943442 | 618708 | ✅ |

## Layout

```
src/qoracle/
  spec.py          bit conventions — SINGLE SOURCE OF TRUTH
  ir.py            PhaseIR: Cube, AffinePre — the cut point
  diagnostics.py   density, symmetry, GF(2) rank, ANF
  gf2.py           rank / factorisation (M = U·V with V real image rows)
  cover/           spec -> PhaseIR   [minterm, pprm, esop_abc]
  lower/           PhaseIR -> circuit [serial_mcz, fanout(stub)]
  verify.py        exact 4096-state check + ancilla-restoration check
  metrics.py       derived, never stored as truth
  export.py        QASM submission view
  store.py         content-addressed artifacts
  pipeline.py      orchestration + caching
  leaderboard.py   ranked table (depth, then cx)
```

## Blocking unknowns

1. **Max qubit width** — sets `copies` in the fanout lowering, the main depth lever.
2. **Scored gate set** — depth differs ~2× across bases; `metrics.BASES` has candidates.
3. **Bit-order convention** of the scorer — see the docstring in `spec.py`.
4. The real image, and the baseline `.qmod`.

See `notes/DECISIONS.md`.
