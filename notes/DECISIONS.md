# Decision log

Condensed record: each entry is a **decision** and the **reason** it was taken.
2026-09-14 → 2026-09-30. The full day-by-day narrative is preserved in this file's git
history (`git log -p notes/DECISIONS.md`, commit `b20b3b0`).

Metric throughout: `depth / cx` after transpile to `u3`+`cx`. Depth is scored, CX is the
tiebreak. Correctness is a gate, not a score — every figure below comes from a circuit that
passed an exact 4096-state check including ancilla restoration.

---

## Shipped — the decisions that moved the score

**5329 → 4316 · share repeated predicates.** The 18 raster rectangles have only 10 unique
x-ranges (disc rasterisation is vertically symmetric). Compute each x-condition once and
reuse it for the 1–2 y-sub-ranges under it. *Reason: a purely mechanical dedup, no new
synthesis idea, −19% depth.*

**9620 → 2769 · change the MCX decomposition, not the cover.** Rebuilt the identical
57-cube ESOP with `synth_mcx_2_clean_kg24` (Khattar–Gidney 2024, 2 clean ancillas) instead
of Qiskit's ancilla-free default. *Reason: kg24 is ~8.5× shallower at k=9 and nearly flat in
control count. The route had been dismissed at 9620 — a figure produced by an ancilla-free
decomposition using zero of the 6 available ancillas. The measurement was an artifact of the
implementation, not of the approach.* Note the linear-depth ancilla-free method
(`noaux_v24`, arXiv 2203.11882) is *worse* than Qiskit's default at k≥8 — the win comes from
spending ancillas, not from a better ancilla-free construction.

**2769 → 2422 · optimise the cube order.** All cubes are diagonal, hence commuting, so order
is a free parameter. *Reason: measured spread across orderings is 2431–2929 (17%) and random
orderings are the worst case — this cannot be left to chance.* 2-opt on a control-overlap
proxy, then direct measurement of transpiled depth.

**2422 → 1927 → 1358 · non-linear change of variables.** `diag(f) = U†·diag(f∘P)·U` for any
basis permutation `P`, so search for a cheap `P` whose composed function has a smaller cover
and pay only for `U` twice. Basin-hopping over short CX/Toffoli circuits found a 13-gate `P`
cutting the cover 57 → 38 cubes. *Reason: the LINEAR version is provably blocked — max ANF
degree is 12 and ANF degree is invariant under invertible GF(2) maps, so every linear basis
retains a full-support 12-literal cube (confirmed: 6 random bases gave cube counts 79–169,
strictly worse). Toffolis are non-linear and break that invariant.* The search objective is
the **measured** per-cube cost `Σ COST[n_literals]`, not cube count, because cost is strongly
non-uniform (27 at k≤8 vs 66 at k=12).

**1775 → 1438 · 6-ancilla balanced RCCX AND-tree MCZ.** AND the controls pairwise into
ancillas; because those pairs are disjoint the RCCXs run concurrently, giving a log-depth
tree where kg24 is serial. The build picks the better of tree/kg24 per cube from a measured
per-k table (`research/mcz_best_table.json`). *Reason: −25…50% MCZ depth for ~2% more CX,
and we were using only 14 of 18 qubits. Depth is scored and CX is only the tiebreak, so this
trade is always correct here.*

**1358 → 1332 · relative-phase Toffolis inside the conjugating permutation.** `RCCX = Λ·CCX`
with `Λ` diagonal, so writing `U = Λ_tot·P`: `U†DU = P†Λ†DΛP = P†DP`. *Reason: diagonals
commute, so the relative phases cancel identically — the resulting unitary is bit-for-bit
the full-Toffoli one, at depth 7 / 3 CX instead of 11 / 6. Free.* RCCX is not self-inverse
(CCX is), so the reversed pass must emit `RCCX†`.

---

## Rejected outputs

**BQSKit excluded from the submission despite being faster.** Numerical resynthesis reached
1330/1321 (~2% better than shipped). *Reason: every BQSKit-processed circuit leaves
1.4e-09…4.6e-09 residual error. It passes our local 1e-8 check and FAILS the official 1e-10
one, and this is not fixable via `synthesis_epsilon` (1e-12 → 1.4e-09, 1e-14 → 1.19e-09,
1e-16 → 1.33e-09). Those circuits would have scored zero.* Lesson: run the actual acceptance
test of record early, not a local approximation — we optimised for two weeks against a
checker 100× looser than the real one.

**Qmod written at `decimal_precision=17`, not the default 4.** *Reason: both
`qasm_to_qmod()` and `write_qmod()` default to 4 decimals, emitting `U(3.1416,…)` where the
circuit needs π — 7.3e-6 per gate against a 1e-10 bar. Not fixable with symbolic π either:
single-qubit gate fusion leaves genuinely irrational Euler angles across 63 distinct
triples.* Guarded by parsing the `.qmod` back to a gate list and asserting exact float
equality with the `.qasm` (`tools/check_final.py`).

---

## Closed — and the specific reason

Do not re-propose these without a genuinely new angle on the stated failure mode.

| route | why it died |
|---|---|
| **Complementing the image** | `(−1)^¬f = −(−1)^f`. Global phase. Zero gain. |
| **Variable permutation / reordering for ESOP** | Permutation and complementation preserve min-ESOP cost exactly. |
| **Variational / learned oracle** | Must be exact on all 4096 states; fidelity < 1 is a wrong answer, not a worse score. |
| **Pure phase-polynomial (Gray-code) synthesis** | Ruled out by computation, not experiment: all 4096 Walsh coefficients are nonzero and the spectrum is not concentrated, so a parity-based construction needs ~4096 Rz terms. The ANF degree histogram (avg 6.75/12, only 4 of 886 terms at degree ≤2) says the same for AND-monomials. |
| **GF(2)-linear change of basis to cut rank** | Rank 9 *is* reachable (vs baseline 10, reproducible across restarts) but costs **more**: total AIG nodes 169 → 247 (+46%), because mixing x and y bits destroys the axis-aligned interval structure that makes the standard basis cheap. **Rank counts factors; cost lives in the sub-functions** — rank was a proxy, and an anti-correlated one. |
| **SVD / QR of the image matrix** | Real SVD rank is 11 only because there are 11 distinct row patterns — the same structure already exploited, seen in a linear-algebra basis. Each factor would need real-valued QROM lookups on x and y plus a multiplication; that pattern measured 4615–7073 depth for one disc. Also: rank 11 is the *Schmidt* rank, so the **state** is easy; we need the **operator**, correct on all 4096 inputs with ancillas restored. |
| **Splitting the image into regions and OR-merging** | Tried three partitions (disc/rest, y-bands, true geometric primitives with overlap-correct merge). All ~2× worse, even with unlimited ancillas. ESOP/rank minimisation is global; any split destroys the cross-primitive redundancy it finds. Per-piece ranks summed to exactly the whole-image rank every time — there was never any slack. |
| **Full quadratic disc predicates** `(x−a)²+(y−b)²≤r²` | Needs ~43 qubits for one disc's sum-of-squares intermediates, against an 18-qubit cap. |
| **Shared-distance / lookup-table disc predicate** | Math verified exact (compute `w=LUT(y)` once, test `|x−cx|≤w` once); hand-built in Qiskit after two reproducible Classiq compiler bugs. Costs 4615/3118 for ONE disc, and *worse* (7073/6314) after the "obvious" optimisation — the bottleneck is ~9 branches serialising on one shared register, not the gate type per branch. |
| **Rectangle-XOR decomposition** | Real structure (one rectangle converged to the exact true geometry under optimisation) but the discs need 30+ terms each; disc2 alone measured 2910/2275, more than half the whole budget for one disc. |
| **Carry-lookahead (parallel-prefix) comparator** | Genuinely 69 depth for one threshold test vs ripple's 261 per rectangle — but its internal state must stay live between compute and uncompute, so it never settles to just the result qubit. A rectangle needs two comparators alive at once; independent CP-SAT search confirms infeasible at every ancilla count 2–5. |
| **QFT-based comparator** | Real, verified 2× reduction in QFT-op count; still ~35% worse than ripple. Structural, not a tuning gap: each threshold test needs a QFT+IQFT round trip to extract a borrow bit, O(n²) phase gates vs ripple's O(n). Also only ever helped the already-dead rectangle-XOR route. |
| **Ancilla fanout / concurrent scheduling** | CP-SAT feasibility sweep over all 20 real sub-functions at 3 ancillas: 100% infeasible, every one a fast fail rather than a timeout. These AIGs need close to the full 5–6 ancillas to be pebbled *at all*, so there is no slack to split into two concurrent pools. |
| **Nested `control()` predicates (Classiq track)** | Logically correct (verified 0/4096 in plain Python first) but rejected on width: nesting to depth *d* requires *d* simultaneously-live condition qubits. The full chain needs ≥26 qubits; even the shallowest 3-deep case needs ≥20. Cost is convex in nesting depth, not linear. |
| **`gmeuli/caterpillar` (academic pebbling tooling)** | Built from source and tested on our real AIGs. Its SAT pebbler matches our CP-SAT's schedule *size* (not better) and emits full Toffolis (2× our RCCX cost). Its level-parallel strategy needs ~1 ancilla **per AIG node** — an unconstrained-ancilla regime, incompatible with a 6-ancilla cap. |
| **PyZX `full_reduce`** | Verified correct but worse (6962/5641 vs 4316/2630). Its extraction targets T-count in Clifford+T; our basis is `u3`/`cx` with no discrete T to save, so extraction overhead dominates with nothing to offset it. |
| **Exact CP-SAT ESOP minimisation** | 2,614-candidate enriched cube pool, 244k LP relaxations: no improvement on EXORCISM's 57 cubes / 507 literals. Third independent method agreeing there is no hidden cancellation in the ESOP representation. Scoped to ESOP — says nothing about arithmetic representations. |
| **Hand-rolled Belady pebbling scheduler** | Abandoned after 11 distinct bugs, several surfacing only after the previous fix had verified. Replaced by CP-SAT (exact, correct by construction). A wrong circuit is disqualification rather than a worse score, so a bug-discovery rate with no sign of convergence is not an acceptable stopping point. |
| **Dirty ancilla borrowed from the other data register** | Real 2× per-gate win in isolation (6-ctrl MCX 124→64 CX) but regressed every integration (3 variants, +18…45% depth) — it serialises the x-side/y-side work that was running concurrently on disjoint qubits. |
| **Symmetry folding** (y@19, y@41, x@40) | The mirrors are exact but **band-local**. Implemented as reversible sign-magnitude folds, every variant makes the cover worse (38 cubes/1450 → 52–69 cubes/2165–2987) *before* paying the ~200 depth to implement the fold. Folding globally destroys the axis-aligned structure outside the band, where most cubes live. |
| **Minimising how many qubits `f∘Π` depends on** | Vacuous by parity: 1097 marked pixels is **odd**, so if `f∘Π` depended on k<12 qubits the domain would split into blocks of size 2^(12−k) ≥ 2 with `f` constant on each, making the count even. The answer is 12 for every in-place permutation Π. (Does not apply to ancilla-assisted forms, which are the ordinary compute-flag-Z-uncompute architecture — separately measured with a ~600 cx floor.) |
| **Re-running the transform search at the corrected Toffoli price** | After the RCCX result the search's `D_TOF=22.0` was wrong (correct: 14.0 — a 36% over-penalty). Re-ran 120 hops: returned the seed **unchanged**. The cost model was not the limiting factor; 38 cubes / cost 1450 is a genuine local optimum of this architecture. |

---

## The structure that wins — found, verified, not built

The 11 distinct row patterns form a **width-2 containment poset** (two chains). With `u(y)` =
which chain row *y* belongs to, `l(y)` = its level in that chain, and `a_u(x)` = the least
level of chain *u* containing column *x*, all three forms below are **exact, 0 wrong of
4096** (`research/fused2.py`):

```
[a1(x) ≤ L1(y)] XOR [a2(x) ≤ L2(y)]      two comparisons  (what we had)
[ a_u(x) ≤ l(y) ]                        ONE comparison
[ l(y) + mu(x,u) ≥ 7 ]                   a threshold on a sum,  mu(x,u) = 7 − a_u(x)
```

So the oracle is a 3-bit level code of the rows (6→3 bits, **64 points**), a 3-bit level code
of the columns taking `x` **plus the chain bit** `u` (7→3 bits, **128 points**), and one
comparison. That extra input is the part we misread: we took the published hint as "get below
8 classes per side", measured 11, and treated it as a wall — but the chain choice is a
separate *input* to the column code, not a consumer of code bits.

**Remaining obstacle.** The fused form needs `l(3)+u(1)+mu(3) = 7` ancillas live at once; we
have 6. The two-pass XOR form is the one that fits 6 (`u` is implicit in which pass runs), so
fusing buys depth but costs an ancilla. Probable way in: the code bits need not occupy
dedicated wires, only wires whose GF(2) *span* contains them — unconfirmed.

**The method we lacked.** The winners **searched** for these codes rather than synthesising
them — many annealing chains per code, each first finding a correct circuit and then
annealing it toward minimum depth against an exact `u3`/`cx` depth model. A 6→3-bit function
is 64 points, small enough to search directly. Our own prototype
(`research/anneal_rev.py`) annealed the *whole 18-qubit oracle*, where every single-gate
mutation changes the computed function and is rejected on correctness, so the chain never
left its seed. **Decompose first, brute-force the small piece second.** The scale of compute
was not the differentiator; the piece size was.

---

## Process decisions worth keeping

**Nothing is a candidate until the exact verifier passes.** It checks the circuit, not the
IR, including ancilla restoration — which catches lowering bugs, phase leakage and
convention mismatches that a spot check misses. 4096 states is cheap.

**Never quote cost from an unverified or partial circuit.** Made twice. An
incremental-accumulator build silently skipped unschedulable sub-circuits and reported
"925/699" — about half the legitimate best — which then seeded an entirely wrong diagnosis.
The only *complete* version of that construction cost 3599/2824, ~2.7× worse than doing
nothing. Missing work always looks cheap. Gate every cost measurement on verification first.

**Measure a transform's benefit before building its circuit.** One `abc` call on the permuted
truth table decides it. This turned a ~3h implementation into a ~1min test for symmetry
folding, and would have for several other change-of-variables ideas.

**Budget backwards from the public target before building.** 95 depth / 272 CX is ~90 RCCX
total, ~45 per half, so ~25–30 depth per component. Our interval indicator measured 136 depth
by itself. That division, done on day 1 instead of day 14, rules out the entire
materialise-predicates architecture before weeks go into it.

**While the gap is >5×, an improvement that does not change the order of magnitude is not
progress.** The old anti-stuck rule ("no measured improvement in 4h → shelve the branch")
rewards any positive delta and kept effort inside one valley: +17% from scheduler tuning,
14 hours of compute for 0.4%.

**Before closing ANY route, ask whether the measurement reflects the approach or just the
implementation that was benchmarked.** Recorded in bold after the ESOP reversal (9620 → 2769
with no change to the cover) and then repeated two days later on the most important route in
the project: the level-code decomposition was closed on an AIG-pebbling measurement that said
nothing about the cost of the function itself. Filing a lesson as a fact about one route does
not prevent recurrence — it has to be a check that runs at the decision point.
