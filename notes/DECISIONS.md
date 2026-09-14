# Decisions log

## Confirmed dead — do not revisit
- **Complementing the image.** `(-1)^¬f = -(-1)^f`. Global phase. Zero gain.
  (Encoded as a note in `diagnostics.density_report`.)
- **Variable reordering to improve ESOP.** Permutation + complementation of
  variables preserve min-ESOP cost exactly. Morton order helps BDD size only —
  so it matters only on a BDD-synthesis route.
- **Variational / learned oracle.** Must be exact on all 4096 states; fidelity
  < 1 is a wrong answer, not a worse score.
- **General (non-affine) pixel permutation.** Costs more than the oracle it optimises.

## Live
- ESOP via EXORCISM + best-of-N restarts, weighted by **literal** count.
- Ancilla fanout (`lower/fanout.py`) — the main depth lever, blocked on width cap.
- Relative-phase Toffolis inside `within_apply`; log-depth MCX with clean ancillas.
- Phase-gadget scheduling (PyZX) — commuting-gadget scheduling *is* the depth problem.

## Gated on diagnostics
- **GF(2) rank** ≤16 → pursue factorisation (`f = ⊕ u_i(y)·v_i(x)` → r disjoint
  CZs → depth-1 layer). ≥32 → drop. `gf2.factor` deliberately picks V from real
  image rows, which synthesise more cheaply than RREF basis vectors.
- **Mirror symmetry** → fold a variable for ~5 CX. Worth more than any downstream
  optimisation because it halves the domain *before* minimisation.

## Anti-stuck rules
1. No measured, verified improvement in 4h → shelve the branch (log, don't delete).
2. Always hold a verified best-so-far. Never break the working submission.
3. Diagnostics before optimisation.
4. Prefer variance (restarts, seeds) over cleverness when time is short.
5. fewer variables → fewer terms → fewer literals → shorter schedule.
   Reductions compose multiplicatively; earlier ones are worth more.
