# ClassiqQCC — working notes for Claude Code


## !! SUBMISSION-CRITICAL (2026-09-28): BQSKIT OUTPUT IS INVALID !!
The notebook's own acceptance test (Step 6) uses a **1e-10** threshold on the
statevector. Our `verify.py` uses atol=**1e-8**, which is LOOSER -- so circuits
can pass our check and still be rejected. Measured, all artifacts:

| circuit family | max deviation | passes 1e-10 |
|---|---|---|
| every BQSKit-processed circuit | 1.4e-09 .. 4.6e-09 | **NO** |
| every non-BQSKit circuit | ~3e-16 | yes |

BQSKit's per-block numerical error accumulates and is **NOT** controlled by
`synthesis_epsilon`: 1e-12 -> 1.4e-09, 1e-14 -> 1.19e-09, 1e-16 -> 1.33e-09.
The older note in this file claiming "always use 1e-12 and it's fine" is WRONG.
**Do not submit a BQSKit-processed circuit. Do not trust `verify.py` alone --
always run the notebook's 1e-10 statevector test before submitting.**

**VALID BEST / SUBMIT THIS:
`data/artifacts/lower/esop_hybrid_tree3_rccx/oracle.qasm` (copied to
`submission.qasm`) -- depth 1332, cx 1317, width 18. Officially verified
(notebook Step 6): max error 3.8e-16, ancilla 6.7e-17, norm 2.2e-14.**
(The older 1358/1336 `esop_hybrid_tree3` is the same circuit with full
Toffolis in the transform; superseded, see RCCX note below.)

## RCCX IS FREE INSIDE ANY CONJUGATING PERMUTATION (2026-09-30) — user's insight
Our oracle has the form `U^dag . D . U` with D diagonal. Write U as a product
of CX and RCCX: each RCCX = `Lambda . CCX` with Lambda diagonal, and
conjugating a diagonal by a permutation stays diagonal, so `U = Lambda_tot . P`
for a permutation P. Then
`U^dag D U = P^dag Lambda^dag D Lambda P = P^dag D P`
because diagonals commute. **The relative phases cancel identically — the
result is bit-for-bit the same unitary as with full Toffolis.** So RCCX
(depth 7 / 3 cx) may replace CCX (depth 11 / 6 cx) everywhere inside U, not
just inside pebbling. Emit `RCCXGate()` forward and `RCCXGate().inverse()` in
the reversed pass (RCCX is not self-inverse; CCX is).
Measured, same cover and same cube order, only that swap: **1358/1336 ->
1332/1317**, verified 0/4096 wrong at 1e-10.
**Consequence for search:** the transform search priced Toffolis at
`D_TOF=22.0` (= 2 x CCX depth 11). The correct price is **14.0** (2 x RCCX
depth 7) — it had been over-penalizing Toffolis by 36% the whole time.
Re-run at the correct price (120 hops): **no improvement, seed returned
unchanged** (38 cubes / cube_cost 1450). The cost model was not the limit;
38/1450 is a real local optimum of this architecture. Don't re-run.

## Submission artifacts (2026-09-28) — BOTH FILES READY
| file | what it is |
|---|---|
| `submission.qasm` | **the scored artifact.** 18 qubits, 1317 cx + 1622 u3 |
| `submission.qmod` | native Qmod source, same circuit gate-for-gate |
| `submission.synthesis_options.json` | written by `write_qmod`; DEPTH / max_width=18 |
| `submission_model.py` | Python Qmod that regenerates the `.qmod` |

Ran the notebook's **Step 6 verbatim** (Classiq simulator, 3 random product
states) against `submission.qasm`:
`Successfully verified loaded QASM with score 1332` — max error **3.8e-16**,
ancilla error **6.7e-17**, normalization error **2.2e-14** (all bars 1e-10).
The notebook's own `qasm_metrics()` reads width=18, depth=1332, cx=1317.

**Two traps found while producing the qmod, both avoided:**
1. `qasm_to_qmod()` (server decompiler) and `write_qmod()` BOTH round angles to
   **4 decimals** by default (`decimal_precision=4`): it emits `U(3.1416,...)`
   for `pi`. That is a 7.3e-6 error against a 1e-10 bar — the decompiled qmod is
   WRONG. Always pass `decimal_precision=17`. The circuit also contains genuinely
   irrational fused Euler angles (e.g. `0.8332521844832049`) from 1q-gate fusion,
   so this is not fixable by substituting `pi` symbols.
2. Scoring does **not** re-transpile: `qasm_metrics()` computes depth by its own
   per-qubit layering **directly on the submitted file**, and Step 6 "reads
   `submission.qasm` directly and never simulates the earlier Qmod model." So the
   QASM file as written is the score; the qmod is reproducibility only.

`submission.qmod` was checked by parsing it back to a gate list and asserting
**exact float equality** with `submission.qasm` — 2939/2939 ops identical.
NOTE: `gen_model.py` must read `submission.qasm`; it originally hardcoded the
now-deleted `SUBMISSION_oracle.qasm` and silently regenerated the qmod from a
STALE circuit. The bit-equality check is what caught it — always re-run it
after changing the QASM.
Known limitation: `synthesize()` on this model uploads a 3.8 MB serialized
payload and dies with `httpx.WriteTimeout` (2980 literal gate statements at
~1.3 KB of JSON each). Does not affect scoring, since the QASM is authoritative.

## The task
12 qubits (x:6, y:6), up to 6 clean ancillas (18 qubits total). Build a diagonal
phase oracle `|x,y> -> (-1)^f(x,y)|x,y>` for the 64x64 Classiq-logo image, 1097
marked pixels (`io.logo_pixel`: 2 axis-aligned rectangles + 2 discs).
**Ranked by circuit DEPTH after transpile to u3/cx. CX count is the tiebreak.**
Leader as of 2026-09-15: Boopathi R., depth=129, cx=614, width=18. Full
top-10 (2026-09-15/16 snapshot) splits cleanly into two cx/depth-ratio
clusters — ~2.0-2.4 (Gabriele M. 166/348, Vyom P. 175/343, Satwik S. 175/352,
Jayachandiran U. 181/426, Daksh S. 188/451) and ~4.1-4.8 (Boopathi R. 129/614,
Mateusz P. 137/561, SOURABH N. 170/802, Hyun-Jung K. 178/782, Monit S.
185/854), nothing in between. Our best (1332/1317) ratio is **0.989** — still
below both clusters, meaning our schedule averages under 1 CX per depth-layer
while leaders pack 2-5x that. `lower/fanout.py` (the lever this once pointed
to) was subsequently tested directly and confirmed DEAD — see "Live work"
below; the ratio gap remains unexplained, not a live lead.

**CURRENT BEST (VALID): 1332 / 1317 at width 18.** The 1330/1321 figure
sometimes cited below is BQSKit-processed and FAILS the official 1e-10 test
-- see the submission-critical warning at the top of this file. Reached
2026-09-26/30 from 3194/2467 — a **58% depth reduction** — via SEVEN
compounding levers, none of them a new circuit construction:
1. **MCX synthesis method** (`synth_mcx_2_clean_kg24`, 2 clean ancillas):
   9620 → 2769 on the previously-written-off `esop_abc` route, with NO
   change to the cover. Biggest single lever in the project. See MCX table.
2. **Cube ordering** (cubes are diagonal ⇒ commute ⇒ order is free):
   2769 → 2422. Worth ~13%; random orderings are ~17% worse than optimized.
3. **Non-linear change of variables** (10 cheap CX/Toffoli gates, found by
   basin-hopping): ESOP 57 → 40 cubes, 2422 → 1775. The LINEAR version of
   this is provably blocked (ANF-degree invariant); non-linear breaks it.
4. **6-ancilla AND-tree MCZ** (uses the FULL 18-qubit budget): partial ANDs on
   disjoint control pairs run concurrently, giving 25-50% shallower MCZ than
   kg24 for k=4..10 at only ~2% more CX. 1775 → 1438. Deliberately trades CX
   for depth — depth is scored, CX is only the tiebreak.
5. **Cost-model-driven transform search**: re-ran lever 3 against the MEASURED
   per-size MCZ cost table (k<=8:27, k=9:36, k=10:55, k=11:64, k=12:66) instead
   of raw cube count, since cost is very non-uniform. 38 cubes. 1438 → 1358.
6. ~~BQSKit~~ — INVALID, see warning at top. Valid chain stops at 1358.
7. **RCCX inside the conjugating permutation** (2026-09-30): `U^dag D U` with
   D diagonal means RCCX's relative phases cancel identically, so RCCX (7/3)
   replaces CCX (11/6) in the transform for free. 1358 → **1332**. See the
   RCCX section at the top of this file for the derivation.

**PLATEAUED at 1332 (valid).** Every refinement after lever 7 bought nothing:
transform search improved cube_cost 1496→1465 with no real depth change; the
per-k MCZ optimum (measured, incl. reserve tuning) changed depth 0 and CX -5;
BQSKit gives ~2% and is INVALID; and re-running the transform search at the
CORRECTED Toffoli price (D_TOF 22→14, 120 hops) returned the seed UNCHANGED.
38 cubes / cube_cost 1450 is a real local optimum of this architecture, not a
cost-model artifact. Further effort here is not productive — the ceiling is
the architecture. See the 2026-09-30 post-mortem in notes/DECISIONS.md for the
structure (fused single comparison, verified 0/4096) that would have been
needed instead.

Session history: paused 2026-09-22 by user decision at 3194/2467; resumed
2026-09-25 (change-of-basis + SVD/QR, both closed negative) and 2026-09-26/28
(the four levers above). ELEVEN circuit-construction leads are closed out
with hard evidence (see "Live work"); the gap to the leader (129) is ~10.3x
and remains blocked by the serialization limit documented below. If
resuming: read "Live work" first, and note the process lesson from
2026-09-26 — **a route written off on an old measurement may be an artifact
of its implementation, not its approach.**

Submission = Classiq `.qmod` source + OpenQASM circuit
(`classiq-challenge-baseline.ipynb` is the reference notebook/scorer).

## Two synthesis tracks — current standings (2026-09-14, basis cx_u3/u3+cx)

| # | approach | track | depth | cx | width | verified |
|---|---|---|---|---|---|---|
| 1 | **13-gate transform w/ RCCX + 38-cube ESOP + 6-anc AND-tree MCZ + order** — **VALID, SUBMIT THIS** | A | **1332** | **1317** | 18 | Y (3.2e-16) |
| 1b | same, full CCX in the transform (superseded) | A | 1358 | 1336 | 18 | Y (4.8e-16) |
| 2 | 10-gate transform, 40 cubes, tree MCZ | A | 1438 | 1425 | 18 | Y (3.1e-16) |
| 3 | 10-gate transform, 40 cubes, kg24 MCZ only | A | 1775 | 1359 | 14 | Y (3.5e-16) |
| 4 | 8-gate transform / 42 cubes | A | 1798 | 1358 | 14 | Y (2.3e-16) |
| 5 | 5-gate transform / 46 cubes | A | 1927 | 1418 | 14 | Y (2.5e-16) |
| 6 | `esop_abc` 57 cubes + kg24 MCZ + optimized order (no transform) | A | 2422 | 1827 | 14 | Y (2.9e-16) |
| 7 | same, original (unoptimized) cube order | A | 2769 | 2136 | 14 | Y (5.8e-16) |
| 8 | `gf2_factor` + `gf2_cpsat_hybrid` v4 | A | 3335 | 2490 | 18 | Y (7.9e-16) |
| 9 | `classiq_native.rectangles_grouped` | B | 4316 | 2630 | 18 | Y |
| 10 | `classiq_native.rectangles` | B | 5329 | 3502 | 18 | Y |
| 11 | `rect_groups` + `rect_ancilla` | A | 6233 | 3564 | 18 | Y |
| 12 | `gf2_factor` + `gf2_ancilla` | A | 6337 | 3609 | 18 | Y |
| 13 | `esop_abc` + `serial_mcz` (SAME cover as row 1 — gap is purely MCX decomposition + ancillas) | A | 9620 | 6496 | 12 | Y |
| 14 | `pprm` + `serial_mcz` | A | 55741 | 35679 | 12 | Y |

**ALL BQSKit-PROCESSED RESULTS REMOVED FROM THIS TABLE — THEY ARE INVALID.**
For the record they were: 1330/1321, 1409/1410, 1759/1358, 1779/1356,
2399/1825, 3194/2467, 3230/2474, 3960/2436. Every one fails the official
1e-10 statevector test (1.4e-09 .. 4.6e-09). See the warning at the top.

**BQSKit is unusable for this competition.** Its numerical resynthesis leaves
~1e-09 residual regardless of `synthesis_epsilon` (1e-12 -> 1.4e-09,
1e-14 -> 1.19e-09, 1e-16 -> 1.33e-09), and the official bar is 1e-10. It bought
~2% depth and would have cost the entire submission. Every depth figure in this
file dated 2026-09-18..28 that mentions BQSKit is INVALID.

**`max_synthesis_size` (default 3) is a real, underused lever, found
2026-09-18.** BQSKit partitions the circuit into blocks of at most this many
qubits and NUMERICALLY RESYNTHESIZES each block's unitary from scratch
(not just peephole-optimizes the existing gates) — bigger blocks let it find
non-obvious arrangements peephole passes can't, at real (roughly exponential)
time cost per BQSKit's own docs. Row 1 above used `max_synthesis_size=4`
(~450-600s wall-clock) and beat the prior `=3` default (row 1b) by another
~1.1% depth on top of the original BQSKit win. Non-deterministic across runs
(two separate `=4` runs gave 3197/2469 and 3194/2467) — the search has real
randomness, worth a few repeats at a fixed size rather than trusting one run.
`=5` untested as of this writing (running, multi-minute+). Don't assume `=4`
is the ceiling; this hasn't been pushed to its own limit yet.

**MCX SYNTHESIS METHOD IS THE SINGLE BIGGEST LEVER FOUND (2026-09-26).**
Qiskit 2.5's `synth_mcx_2_clean_kg24` (Khattar-Gidney 2024, needs exactly 2
clean ancillas) is dramatically better than the ancilla-free decomposition,
and its depth is nearly FLAT in the number of controls:

| n controls | qiskit default (0 anc) | `noaux_v24` | **`2_clean_kg24`** |
|---|---|---|---|
| 6  | 191 / 124  | 192 / 140  | **54 / 30** |
| 9  | 513 / 332  | 703 / 444  | **60 / 48** |
| 12 | 1130 / 716 | 1499 / 900 | **73 / 66** |

(depth/cx, transpiled u3+cx). That is 8.5x depth at n=9, 15x at n=12. Note
`noaux_v24` (the da Silva-Park linear-depth ancilla-free method) is WORSE
than Qiskit's own default here — the win comes from spending 2 ancillas,
not from a better ancilla-free construction. `n_clean_m15` (v-chain) is
worse than kg24 at every size AND needs n-2 ancillas, so kg24-2-clean is
simply the best available choice for us at every control count.

**BUT kg24 uses only 2 ancillas — a 6-ancilla AND-TREE beats it (2026-09-28).**
Build a balanced tree of RCCX partial-ANDs: pairs of controls are ANDed into
ancillas, and because those pairs are DISJOINT the RCCXs run concurrently, so
the tree is log-depth where kg24 is serial. Measured per-k optimum (tree with
`reserve` ancillas held back for a kg24 residual; `mcz_variants.py`):

| k | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|
| kg24 | **10** | 22 | 36 | 27 | 54 | 54 | 56 | 60 | **64** | 73 |
| best tree | 15 | **15** | **27** | **25**(r3) | **27** | **27** | **36** | **55** | 66 | **66**(r2) |

Tree wins k=4..10 and k=12 (up to −50% depth) for only ~2% more CX; kg24 wins
at k=3 and k=11. Table stored in `scratchpad/mcz_best_table.json`. **This is
the CX-for-depth trade: always take it, depth is scored and CX is only the
tiebreak.** Consequence: the right ESOP objective is neither cube count nor
literal count but `sum over cubes of COST[n_literals]` using the table above —
costs are very non-uniform (k<=8:27 vs k=11:64), so a cover with a fat 11/12
tail is much worse than its cube count suggests.

**Consequence: `esop_abc` went from 9620 (row 8, written off) to 2732 (row 1,
new best) with NO change to the cover** — same 57 cubes, same 507 literals.
The route had been dismissed on a measurement that was an artifact of a bad
MCX decomposition plus using zero of our 6 available ancillas. Lesson worth
generalizing: **before writing off a route, check whether its measurement is
an artifact of the implementation rather than the approach.**

Because kg24 depth is nearly flat in n, the right ESOP objective is **cube
COUNT, not literal count** (total depth ~ n_cubes x ~48). Re-ran the exact
CP-SAT search with a cube-count objective: still 57, no improvement found,
but the proven lower bound is only 19 — so 57 is NOT proven optimal, and a
genuinely smaller cube cover remains the most valuable open target. The
search pool was limited to generalizations of EXORCISM's own cubes.

**Cube ORDER is a free parameter worth ~13%.** All 57 cubes are diagonal,
hence mutually commuting, so they can be emitted in any order. Measured
spread across orderings: **2431-2929 depth** (17%). Greedy max-overlap gives
2495; 2-opt on an overlap proxy gives 2431; a direct search on transpiled
depth gives 2422; +BQSKit = 2399. Random orderings are the worst — do not
leave this to chance. Optimized order is stored in the artifact's
`metrics.json` under `"order"`.

**Why this route cannot be parallelized (measured, definitive).** Cube
support sizes are {3:2, 5:4, 6:3, 7:4, 8:5, 9:14, 10:11, 11:9, 12:5}, mean
8.89 of 12 data qubits. **Exactly 0 of 1596 cube pairs have disjoint
support** — so no two MCZ gates can ever run concurrently, under any
ordering. That is the whole explanation for our ~11% packing efficiency vs
the leader's ~53%. Qubit PERMUTATION cannot fix it (preserves all sizes and
intersections). GF(2)-LINEAR basis change cannot either: max ANF degree is
12 and degree is invariant under invertible linear maps, so every basis
contains a 12-literal full-support cube — confirmed empirically, 6 random
bases all gave maxsize=12, mean support 8.3-9.2, ~0 disjoint pairs, AND
blew cube count up from 57 to 79-169. See DECISIONS.md 2026-09-26.

`rect_groups`+`rect_ancilla` is the SAME logical structure as
`rectangles_grouped` (hand-scheduled instead of left to Classiq's
`AUTO_OPTIMIZE`) — and it LOST, 6233/3564 vs 4316/2630. Manual ancilla
batching is not a free win here; see notes/DECISIONS.md 2026-09-14 (cont'd, 2).

**Track A now leads**, via AIG-sharing (GF(2)-rank factorization into 20
6-bit sub-functions, each XAG-synthesized with `abc` and scheduled onto a
5-6 qubit ancilla budget with a CP-SAT exact scheduler — see
`gf2_cpsat_hybrid` below and notes/DECISIONS.md 2026-09-14 (cont'd, 11) for
the full path, including two prior failed scheduler attempts). Gap to
leader (142/557) is still ~20-25x on depth — closing it is the open
problem. Currently researching whether `gmeuli/caterpillar`
(reversible-pebbling synthesis tooling from the academic literature) can
close more of it; see "Live work" below.

### Track A — `cover/` + `lower/` + `ir.py` (boolean minimisation)
Treats the target as an opaque 4096-entry truth table: minimise it (ESOP via
`abc`/EXORCISM, or GF(2)-rank factorisation), then lower the resulting
`PhaseIR` (list of XOR-ed cubes) to a Qiskit circuit. Architecture rules below
still apply IN FULL to this track.

```
spec --diagnostics--> report
  +--> COVER --> PhaseIR --> LOWER --> circuit(QPY) --> VERIFY --> METRICS --> QASM
       expensive  cached      cheap     canonical        cached    derived     view
       cached                 cached
```

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
   Reused as-is by Track B too (it only needs a QASM-loadable `QuantumCircuit`).
5. **Bit conventions live ONLY in `spec.py`.** Never hand-roll bit order elsewhere.
   Confirmed against the notebook's own scorer: `index=(y<<6)|x`, matches exactly.

### Track B — `classiq_native/` (Classiq-native qmod models)
Bypasses `PhaseIR` entirely: builds a `qfunc main` directly in Classiq's qmod
language using arithmetic `control()` conditions on the `x`/`y` `QNum`
registers, and lets **Classiq's own synthesizer** (not our cover/lower code)
exploit the geometry. This beat Track A's best result on the first,
literally-unoptimized attempt — see standings above. `run(name)` synthesizes
with `Constraints(optimization_parameter=DEPTH, max_width=18)`, transpiles
through Classiq's `AUTO_OPTIMIZE` (u3/cx — the actual scoring compiler),
verifies with `verify.py`, and saves to `data/artifacts/classiq_native/<name>/`.

- **`rectangles.py`**: one `control()` per disjoint rectangle from
  `io.logo_rectangles()` (18 rectangles, scanline-merged). This is literally
  the notebook's baseline model. 5329/3502.
- **`rectangles_grouped.py`** (current best, #1 above): the 18 rectangles only
  have **10 unique x-ranges** (disc rasterization is top-bottom symmetric).
  Nests `control()`: compute the x-condition ONCE per unique x-range, and
  inside that scope apply one `control(y_cond, phase(pi))` per y-sub-range
  that shares it (1 or 2, always disjoint). Classiq's `control()` uncomputes
  its own condition automatically, so this saves a whole x-range
  compute+uncompute per repeated range. 4316/2630 — a "don't recompute an
  identical sub-predicate" win, nothing fancier. **The natural next step is
  the same idea recursively / more aggressively**: group by y-range too where
  it helps, or find a smarter minimal set of shared comparators than raw
  x-range grouping.
- **`primitives.py`** (blocked, kept for reference): 2 rectangles + 2 REAL
  quadratic disc predicates `(x-a)^2+(y-b)^2<=r^2`, 6 `control()` blocks total
  instead of 18 (with inclusion-exclusion phase correction for the two
  overlapping primitive pairs — verified exactly against the truth table
  first). Fails synthesis: needs ~43 qubits for one quadratic form's
  arithmetic intermediates, way over the 18-qubit cap. The likely next lever
  toward 142 IS still "fewer, smarter primitives than 18 raster rectangles" —
  just not via full sum-of-squares arithmetic. See its module docstring.

**IMPORTANT for whichever track you push next:** the 30x gap to the leader
means neither track alone has found the real trick yet. Don't declare a track
"done" — both are mid-flight.

**Classiq SDK gotcha, will bite again on any new `classiq_native/*.py` model:**
1. Never put `from __future__ import annotations` in a file that defines a
   `@qfunc`/`@qperm`. It turns type hints into strings; Classiq's own
   `declaration_inferrer.is_qvar` calls `issubclass()` on them directly and
   crashes with `TypeError: issubclass() arg 1 must be a class`. The notebook
   doesn't use this import either — that's why.
2. Two same-named qfuncs (e.g. two files each with a `main`/
   `logo_phase_oracle`) decorated in the SAME process corrupt some global
   state in Classiq's type-inference machinery, even across different Python
   modules — the second one raises the identical error above. This is why
   `classiq_native/_run_one.py` exists: each model is synthesized in its own
   subprocess (`run()` in `classiq_native/__init__.py` shells out to
   `python -m qoracle.classiq_native._run_one <name>`). Don't "simplify" this
   back to in-process registry + eager imports.

## Confirmed dead — do not propose these again
- **Complementing the image.** `(-1)^~f = -(-1)^f`. Global phase. Zero gain.
- **Variable reordering to improve ESOP.** Permutation + complementation of
  variables preserve min-ESOP cost EXACTLY. Morton order helps BDD size only,
  so it matters only on a BDD-synthesis route.
- **Variational / learned oracle.** Must be exact on all 4096 states; fidelity
  < 1 is a wrong answer, not a worse score.
- **General (non-affine) pixel permutation.** Costs more than the oracle it optimises.
- **Full quadratic-arithmetic disc predicates within the 18-qubit cap.**
  `classiq_native/primitives.py` needs ~43 qubits for just one disc. A cheaper
  encoding of "inside this disc" would have to avoid a literal sum-of-squares.
- **AIG-sharing via a HAND-ROLLED (Belady-heuristic) ancilla pebbling
  scheduler**, specifically. NOT dead as an approach — it's the current
  best (see standings, row 1) once the scheduler was replaced with CP-SAT
  (exact, correctness-by-construction) instead of the heuristic. The
  hand-rolled `_BeladyScheduler` in `aig_synth.py` is real and correct for
  a single standalone build, but accumulated 11 distinct bugs (see
  notes/DECISIONS.md 2026-09-14 cont'd 10 and cont'd 11) trying to chain
  multiple builds over a shared, non-contiguous scratch pool, and was
  abandoned in favor of `pebble_cpsat.py`. Don't resurrect
  `_BeladyScheduler` for new ancilla-sharing work — use the CP-SAT
  scheduler, which solves the identical problem exactly.
- **Splitting the image into independently-synthesized regions and OR/merging
  them.** Tried twice (disc1 vs rest; all 4 geometric primitives separately).
  Both times each piece has genuinely lower GF(2) rank than the whole, but
  BOTH splits produce ~2x MORE total depth/cx than unified synthesis, before
  even adding OR-merge overhead (8826/5926 and 8469/5654 vs baseline
  4316/2630). ESOP/rank minimization is a global optimization; splitting the
  truth table loses that global view regardless of how sensible the cut is.
  Don't retry with a different partition.
- **Pure Gray-code/phase-polynomial (Amy-Maslov-Mosca) synthesis.** Ruled out
  MATHEMATICALLY, not experimentally: computed the exact ANF degree
  histogram (fast Mobius transform, no circuit built) -- average degree
  6.75/12, only 4 of 886 terms at degree<=2. That technique needs low-degree
  (near-linear) phase mass to avoid ancilla; ours has essentially none. Any
  correct circuit needs real high-arity AND computation, which routes back
  to the AIG-sharing problem above. See notes/DECISIONS.md 2026-09-14
  (cont'd, 6).
- **Dirty ancilla borrowed from the OTHER data register (x borrowed as scratch
  for a y-side computation, vice versa) to cheapen multi-controlled-X gates.**
  Real 2x per-gate win in isolation (6-ctrl MCX: 124->64 CX with 1 dirty
  qubit), but wiring it into `gf2_ancilla`/`rect_ancilla` REGRESSED both
  (depth +45%/+18%) by serializing the x-side/y-side work that used to run
  concurrently on disjoint qubits — the whole point of those lowerings. If
  revisited, the dirty source must be something genuinely idle (e.g. a
  batch's own not-yet-live ancilla), never the other register.
- **Track A on the SYNTHETIC placeholder image.** `io.synthetic_target()` is
  not the real logo; every diagnostic/cover run against it (old GF(2) rank=45
  "drop" verdict, old leaderboard entries at depth~26k) is stale. Real image
  loads via `io.logo_target()` (now the CLI default), real GF(2) rank=10.

## Live work, in priority order
Ten substantial leads have been closed out (2026-09-16, -17 and -25; see
notes/DECISIONS.md those dates for full detail, including exact numbers) —
don't re-attempt any of these without a genuinely new angle on their
specific failure mode:
- **`gmeuli/caterpillar`**: built from source, smoke-tested, tested on our
  real per-factor AIGs. `bsat_pebble_solver` matches our CP-SAT's schedule
  quality (not better) and emits literal Toffolis (2x our RCCX cost).
  `xag_low_depth_mapping_strategy` (the level-parallel "ancilla fanout"
  technique) needs ~1 ancilla PER AIG NODE — an unconstrained-ancilla
  regime, not compatible with our 6-ancilla cap at all.
- **Rectangle-XOR decomposition**: real (one rectangle converged to our
  exact true geometry under optimization), but the discs need ~30+ XOR
  terms each and the per-rectangle cost floor (261 depth via the cheapest
  comparator style found) makes even an optimal cover worse than what we
  already have. Measured disc2 alone at 2910/2275 for its 33-rectangle
  cover — more than half our whole current budget for one disc.
- **Carry-lookahead (parallel-prefix) comparator**: real, verified 69-depth
  single comparator (vs 261 for ripple's full rectangle) — but its
  internal state can't settle to just the result qubit before the next
  comparator needs to start, so nothing can be composed with it inside 18
  qubits. Confirmed via independent CP-SAT search: infeasible, fast, at
  every ancilla level from 2 to 5.
- **QFT-based comparator** (Draper-style phase arithmetic, 1 ancilla per
  threshold test): genuinely novel capability — confirmed real x∥y
  concurrency on disjoint qubits (measured, not assumed) and a real 2x
  reduction in QFT-op count via a shared-shift range-test merge. Best
  achieved, fully verified against real rect1 geometry: 353 depth / 625 cx
  for one rectangle, down from a naive 453/765 — but still ~35% worse than
  ripple's 261/rectangle floor, because each QFT threshold test costs
  O(n^2) phase gates vs ripple's O(n). Structural floor (2 QFT round trips
  per threshold test, non-negotiable to read out a borrow bit), not a
  tuning artifact. Also would only ever have helped the already-dead
  rectangle-XOR decomposition, not the GF2-factor pipeline that's actually
  winning — QFT arithmetic has no natural construction for a generic 6-bit
  truth table, only constant-comparisons.
- **Ancilla fanout / concurrent scheduling** (`lower/fanout.py`): tested
  directly via CP-SAT feasibility sweep, all 20 of the real GF2-factor
  sub-functions (u_i and v_i, 4-15 AIG nodes each), at ancillas=3 — 100%
  infeasible, every single one, all fast fails (0.4-2.5s, not timeouts).
  This kills ANY disjoint-pool concurrency scheme needing two simultaneous
  3-ancilla (or smaller) pools — within-factor (u_i ∥ v_i) and cross-factor
  pairing both die for the identical reason: these AIGs generically need
  close to the full 5-6 ancilla to be pebbled AT ALL, leaving no slack to
  share. A fully joint/interleaved CP-SAT scheduler (one shared model
  across all 20 sub-functions instead of a fixed spatial split) is the only
  theoretical escape left, but the uniform fast-infeasibility suggests
  these schedules run near-peak ancilla usage for most of their length, not
  peaky-with-slack — inference, not directly tested, but a strong prior
  against that much extra engineering paying off.
- **Nested `control()` predicates on Track B** (`classiq_native/
  rectangles_nested.py`): the real x-ranges in `io.logo_rectangles()` form
  two strict nesting chains (disc2's 5, `[38,42]⊂[36,44]⊂[34,46]⊂[33,47]⊂
  [32,48]`; disc1's 3, `[53,57]⊂[51,59]⊂[50,60]`) that `rectangles_grouped`
  treats as flat siblings. Nesting `control()` to match (compute the widest
  ring, apply its own y-rows, then INSIDE that scope compute the next-
  narrower ring) is logically correct — verified 0/4096 wrong in plain
  Python — but Classiq's synthesizer rejects it on QUBIT COUNT: the full
  5-deep chain needs >=26 qubits, and even the shallowest possible version
  (just disc1's 3-level chain nested, everything else flat) needs >=20,
  both over the 18-qubit cap. Mechanism: nesting requires every ancestor
  condition qubit to stay live for the whole inner scope, so a depth-d chain
  needs d simultaneous condition qubits instead of the 1-at-a-time reuse the
  flat sibling version gets — same ancilla-scarcity wall as fanout and
  carry-lookahead, reached from the Track B side this time.
- **Exact CP-SAT ESOP minimization**: built a real exact-solver ESOP search
  (not the heuristic `abc`/EXORCISM) — 57-cube EXORCISM baseline (507
  literals) enriched with every 1-/2-literal generalization (2,614
  candidates), `AddBoolXOr` parity constraints, minimize total literals, 8
  workers, 480s. 243,930 LP relaxations explored, zero improvement over the
  seeded 507-literal baseline. Doesn't prove 507 is minimal (no matching
  lower bound reached), but it's the THIRD independent method agreeing no
  hidden cancellation exists: GF(2) rank=10 is a proven hard floor for any
  ESOP (every cube is provably rank-1, so cube-count >= rank always,
  regardless of how cubes are chosen), 42 different valid rank-10 bases all
  cost identically (169 AIG nodes), and now a genuinely general
  (non-bilinear-restricted) exact search over a rich cube space also can't
  beat the heuristic. This function has real, deep complexity.
  **Scoping caveat, important:** this rules out cancellation in the
  ESOP/XOR-of-cubes representation (Track A) SPECIFICALLY, not in
  arithmetic/comparator representations (Track B) — a range condition like
  `x in [2,26]` isn't one cube, it costs many if flattened to ESOP. Don't
  cite this result as "no vast improvement exists anywhere."
- **Shared-distance/lookup-table disc predicate** (Track B side): real,
  verified math (compute `w=LUT(y)` once, test `|x-cx|<=w` once, instead of
  9 independent per-arow x-range tests) — 0/4096 wrong, both discs, checked
  before any circuit work. Classiq's qmod compiler hit two reproducible
  internal bugs on this pattern (`abs()` throws a server error; a
  register-derived-then-compared condition triggers "Control condition
  'False'" during Classiq's own internal expansion, confirmed via local
  trace instrumentation that the usage itself is valid). Hand-built in
  Qiskit instead (two new verified primitives: `qft_reg_add`, a corrected
  Draper 2-register QFT adder; `lt_mixed_comparator`, register-vs-`const±reg`
  comparison in one QFT bracket) — verified exactly correct end-to-end
  (n_wrong=0, n_leak=0) at 19 qubits. Cost: 4615/3118 for ONE disc with a
  naive lookup, and WORSE (7073/6314) after "optimizing" the lookup to use
  cheaper per-branch gates — the bottleneck is ~9 branches serializing on
  one shared register, not the specific gate type each branch uses. Whole
  current best (3230/2474) is for the ENTIRE image; this was for one disc.
- **GF(2)-linear change of basis** (conjugate the oracle by a CNOT network:
  `diag(f) = L_A · diag(f∘A) · L_A⁻¹`). Resolved 2026-09-25, closing a thread
  left IN PROGRESS since 2026-09-14. Rank 9 IS reachable and reproducible
  (5 of 8 annealing restarts, never below 9) vs baseline rank 10 — but it
  costs MORE: total AIG nodes 169 → **247 (+46%)** despite one fewer factor,
  because every sub-function gets ~60% fatter (4-15 nodes → 7-25). The
  standard basis IS the good basis: the geometry is axis-aligned, so
  `x in [2,26]`-style conditions are compact in standard binary, and any mix
  of x/y bits destroys that. **Rank counts FACTORS; cost lives in the
  SUB-FUNCTIONS** — minimizing rank is the wrong objective, and here it's
  anti-correlated with real cost. Untested variant: annealing directly on
  AIG node count (~1h/restart vs ~8s for rank); prior is poor, see
  DECISIONS.md.
- **SVD / QR of the image matrix** (2026-09-25). Real SVD rank of the ±1
  sign matrix is exactly 11 — but that's just "the image has 11 distinct row
  patterns," i.e. the SAME structure `rectangles_grouped` already exploits
  (10 unique x-ranges), in a linear-algebra basis. The additive SVD does
  factor into composable unitaries (sums in an exponent become products),
  but each factor then needs real-valued QROM lookups on x and y, a real
  MULTIPLICATION, and a proportional rotation — the exact lookup+arithmetic
  pattern already measured at 4615-7073 depth for ONE instance with only
  integer tables and a comparison. GF(2) needs just boolean AND +
  controlled-Z. QR doesn't map at all (the target unitary is already
  diagonal, the trivial endpoint of a Givens/QR decomposition). **Keep
  straight:** rank 11 is the SCHMIDT rank, so the STATE `Σ(-1)^f|x⟩|y⟩` is
  genuinely easy (~4 ancillas); we need the OPERATOR, correct on all 4096
  basis inputs with ancillas restored. That distinction is the root of the
  recurring "low rank should help" intuition.

**What's actually moved the score**, all three shipped, verified, and
compounding (see notes/DECISIONS.md 2026-09-16): none of them were new
circuit-construction ideas — all were tuning the CP-SAT scheduler's own
ancilla allocation across the 20 GF(2) factors (harder side gets the full
budget when it's actually the bottleneck; compare both orderings' real
move count per factor rather than assuming one default). Current best
**3230/2474**, down from the day's starting 3913/2677 (~17.4% depth), with
zero remaining ESOP-cube fallback (20/20 factors now via CP-SAT+RCCX).

Next candidates, roughly in order of expected value:
1. Extend the time_limit_s on CP-SAT solves that hit the current 45s cap
   without proving optimality (confirmed happening: factor 5's v6 solve
   took 67.8s wall-clock, factor 9's took 228.9s, both past the nominal
   45s solver budget due to model-construction overhead) — some factors'
   schedules may not yet be at their true minimum move count.
2. A genuinely different (lower-ancilla-floor) parallel-prefix comparator
   graph — the carry-lookahead idea's depth advantage was real; only ITS
   SPECIFIC 3-node-per-combine, 2-bit-per-node encoding forced the ~6-
   ancilla floor. Untried: does a 1-bit-per-node encoding, or a different
   associative merge, need less state per node? Calibrate expectations
   down given the fresh ancilla=3 uniform-infeasibility result above — our
   6-ancilla budget looks tight against essentially every technique tried
   so far, not just this one.
3. Symmetry fold: checked on the REAL logo, no exact mirror/transpose symmetry
   exists (agreement ~0.6-0.9, none =1.0). Dead for this image specifically.

`cover/esop_abc.py` restarts weighted by literal count — SUPERSEDED, not
just deprioritized: the exact CP-SAT ESOP search above IS this idea done
more rigorously (exact solver, not restarts; literal-count objective
directly, not a proxy) and found nothing. Don't redo the restart version.

## Resolved — previously blocking unknowns
1. Max qubit width: **18 total (12 data + up to 6 clean ancillas)**.
2. Scored gate set: **u3 + cx**, `AUTO_OPTIMIZE` via Classiq's own compiler
   (`metrics.BASES["cx_u3"]` for the Qiskit-proxy version; `classiq_score.py` /
   `classiq_native/` call the real one).
3. Bit-order convention: confirmed, matches `spec.py` exactly (`index=(y<<6)|x`).
4. Real image: `io.logo_target()` / `io.logo_pixel()`, ported verbatim from
   `classiq-challenge-baseline.ipynb`.

## Commands
```bash
# Track A (boolean minimisation, PhaseIR pipeline)
qo diag                                          # Phase-1 diagnostics, real logo
qo run --cover gf2_factor --lowering gf2_ancilla --basis cx_u3
qo score --basis cx_u3                           # re-score all stored circuits
qo leaderboard --basis cx_u3
qo classiq-score --circuit-key <key> --basis cx_u3   # authoritative (Classiq AUTO_OPTIMIZE) check

# Track B (Classiq-native qmod models)
qo native-list
qo native-run --name rectangles

pytest -q
```
`abc` binary lives at `abc/abc`, symlinked onto PATH (`/opt/homebrew/bin/abc`)
— needed by `cover/esop_abc.py` and `cover/gf2_factor.py`.
`classiq` SDK: `pip install -e ".[classiq]"`, then a one-time interactive
`classiq.authenticate()` per machine (cannot be scripted/automated).

## Working style
- Always hold a verified best-so-far. Never break the working submission.
- No measured, verified improvement in ~4h -> shelve the branch, log it, don't delete.
- Diagnostics before optimisation.
- Prefer variance (restarts, seeds) over cleverness when time is short.
- Reductions compose multiplicatively:
  fewer variables -> fewer terms -> fewer literals -> shorter schedule.
- Don't assume a track is exhausted just because it's currently behind —
  Track A's `gf2_factor` cover was worse than `esop_abc` under `serial_mcz`
  alone, but paired with the right lowering (`gf2_ancilla`) became the best
  Track A result. The (cover, lowering) or (model, synthesizer-constraint)
  PAIRING matters as much as either half alone.
