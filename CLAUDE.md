# ClassiqQCC — working notes for Claude Code

## The task
12 qubits (x:6, y:6). Build a diagonal phase oracle `|x,y> -> (-1)^f(x,y)|x,y>`
for a 64x64 binary image with 1097 marked pixels.
**Ranked by circuit DEPTH. CX count is the tiebreak. Nothing else scores.**

Submission = Classiq `.qmod` source + OpenQASM circuit.

## Architecture — do not violate this
The pipeline is cut at `PhaseIR` (`src/qoracle/ir.py`): a list of XOR-ed product
terms (cubes) plus an optional affine pre-map.

```
spec --diagnostics--> report
  +--> COVER --> PhaseIR --> LOWER --> circuit(QPY) --> VERIFY --> METRICS --> QASM
       expensive  cached      cheap     canonical        cached    derived     view
       cached                 cached
```

Rules that follow, and that keep the repo cheap to iterate in:

1. **Metrics are DERIVED, never stored as truth.** Redefining a metric or
   changing the gate set must cost `qo score` and zero re-synthesis.
2. **Canonical stored circuit is QPY at the HIGH level** (multi-controlled gates
   intact), not QASM. Re-scoring re-transpiles from structured form, which beats
   re-transpiling an already-decomposed circuit. QASM lives in `export.py` as a view.
3. **Adding a lowering must never invalidate a cover.** That is the entire point
   of the cut. `COVER_VERSION` and `LOWER_VERSION` in `version.py` are separate
   so one stage's cache can be invalidated without the other.
4. **Nothing is a candidate until `verify.py` passes.** It checks the CIRCUIT
   (not the IR), including that ancillas return to |0>. 4096 states is cheap.
5. **Bit conventions live ONLY in `spec.py`.** Never hand-roll bit order elsewhere.

## Confirmed dead — do not propose these again
- **Complementing the image.** `(-1)^~f = -(-1)^f`. Global phase. Zero gain.
- **Variable reordering to improve ESOP.** Permutation + complementation of
  variables preserve min-ESOP cost EXACTLY. Morton order helps BDD size only,
  so it matters only on a BDD-synthesis route.
- **Variational / learned oracle.** Must be exact on all 4096 states; fidelity
  < 1 is a wrong answer, not a worse score.
- **General (non-affine) pixel permutation.** Costs more than the oracle it optimises.

## Live work, in priority order
1. `lower/fanout.py` — ancilla fanout of control bits so independent cubes run
   concurrently instead of queueing on 12 wires. **Main depth lever.** Blocked on
   the width cap (it sets `copies`).
2. `cover/esop_abc.py` — EXORCISM with best-of-N random restarts, weighted by
   LITERAL count not cube count (a 12-literal cube is a 12-controlled Z).
3. Relative-phase Toffolis inside every compute/uncompute pair; log-depth MCX
   with clean ancillas (Gidney; conditionally-clean-ancilla results).
4. Phase-gadget scheduling (PyZX). Commuting-gadget scheduling *is* the depth problem.
5. Symmetry fold if diagnostics find one: removes a VARIABLE for ~5 CX, which
   beats any downstream optimisation because it halves the domain before minimisation.
6. GF(2) factorisation if rank is low: `f = XOR_i u_i(y) v_i(x)` becomes r
   disjoint CZs = one depth-1 layer. `gf2.factor` picks V from real image rows
   on purpose; they synthesise more cheaply than RREF basis vectors.

## Blocking unknowns — ask before guessing
1. Max qubit width (sets fanout `copies`).
2. Scored gate set (`metrics.BASES` has candidates; depth differs ~2x across bases).
3. The scorer's bit-order convention (see `spec.py` docstring).
4. The real image and the baseline `.qmod`.

## Commands
```bash
qo diag                                     # Phase-1 diagnostics
qo run --cover pprm --lowering serial_mcz   # full pipeline
qo score --basis cx_u                       # re-score all stored circuits
qo leaderboard
pytest -q
```

## Working style
- Always hold a verified best-so-far. Never break the working submission.
- No measured, verified improvement in ~4h -> shelve the branch, log it, don't delete.
- Diagnostics before optimisation.
- Prefer variance (restarts, seeds) over cleverness when time is short.
- Reductions compose multiplicatively:
  fewer variables -> fewer terms -> fewer literals -> shorter schedule.