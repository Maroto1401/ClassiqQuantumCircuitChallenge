# Low-depth diagonal phase oracle for the Classiq logo

A submission to the **Classiq Quantum Circuit Challenge** (September 2026): compile a
64×64 binary image into an exact quantum phase oracle, minimising circuit **depth**.

**Final result: depth 1332, CX 1317, width 18** — exact to 3.3×10⁻¹⁶, verified against the
organisers' own acceptance test. The winning entry was depth 95. This repository contains
the circuit, the full synthesis pipeline, and an honest account of the 14× gap: what closed
it from 5329 → 1332, what the winners did differently, and the two process errors that cost
the most.

---

## 1. The problem

Encode a rasterised 64×64 Classiq logo as a diagonal phase oracle

```
|x, y⟩  ⟼  (−1)^f(x,y) |x, y⟩
```

where `f(x,y) = 1` on the 1097 black pixels. The image is the union of two axis-aligned
rectangles and two discs:

```python
f(x, y) =  (2 <= x <= 26 and 29 <= y <= 53)        # tall rectangle
        or (26 <= x <= 49 and 39 <= y <= 43)       # horizontal bar
        or (x-55)**2 + (y-41)**2 <= 42             # small disc
        or (x-40)**2 + (y-19)**2 <= 72             # large disc
```

**Constraints**

| | |
|---|---|
| Data qubits | 12 — `x` on `q[0:6]`, `y` on `q[6:12]`, little-endian |
| Ancillas | up to 6 **clean** (start `|0⟩`, must be restored to `|0⟩`) |
| Total width | 18 |
| Gate set | `u3` + `cx` only |
| **Primary metric** | **circuit depth** |
| Tiebreak | CX count |
| Correctness | exact — statevector error < 10⁻¹⁰ on random product states |

Correctness is a gate, not a score: a fidelity of 0.999 is a *wrong answer*, which rules out
every variational or approximate method. Depth is computed by the organisers' own
per-qubit layering **directly on the submitted QASM text** — there is no re-transpilation at
scoring time, so the file as written *is* the score.

---

## 2. Final approach, in detail

The oracle is built as a **conjugated ESOP cover**:

```
          ┌───────────────────────── U† ─────────────────────────┐
|x,y⟩ ──► │ 13 cheap CX / RCCX gates (change of variables)       │
          └──────────────────────────────────────────────────────┘
          ┌───────────── D = diag((−1)^g) ───────────────────────┐
          │ 38 multi-controlled-Z gates, one per ESOP cube       │
          │ each MCZ synthesised by whichever of two methods is  │
          │ measurably shallower at its control count            │
          └──────────────────────────────────────────────────────┘
          ┌───────────────────────── U ──────────────────────────┐
          │ the same 13 gates, reversed and inverted             │
          └──────────────────────────────────────────────────────┘
```

Six ideas compose multiplicatively here. None is a new circuit construction; each is a
better choice inside a structure that was already correct.

### 2.1 ESOP cover — the function as an XOR of product terms

`f` is minimised into an **XOR-sum-of-products** (ESOP) by EXORCISM (via Berkeley `abc`):
57 cubes over the 12 variables. Each cube is an AND of literals, so it lowers to one
multi-controlled Z, and `(−1)^f` is the product of those MCZs.

The cube count has a hard floor: every cube factorises as `c_x(x) ∧ c_y(y)`, i.e. a rank-1
matrix over GF(2), so **any** ESOP needs at least `rank₂(image) = 10` cubes. An exact CP-SAT
search over an enriched cube pool (2,614 candidates, 244k LP relaxations) could not beat
EXORCISM's 57 — so the heuristic is at or near its practical optimum.

### 2.2 Non-linear change of variables — 57 → 38 cubes

Because `D` is diagonal, for any basis permutation `P` realised by a circuit `U`:

```
diag(f)  =  U† · diag(f ∘ P) · U
```

So we may *search* for a cheap `P` whose composed function has a smaller cover, and pay only
for `U` twice. A basin-hopping search over short CX/Toffoli circuits found a **13-gate** `P`
taking the cover from 57 cubes to **38**.

**Linear maps provably cannot do this.** The maximum ANF degree of `f` is 12, and ANF degree
is invariant under any invertible GF(2) linear map — so every linear basis still contains a
full-support 12-literal cube. Measured on six random linear bases, the cube count instead
*rose* to 79–169. Toffoli gates are non-linear and break that invariant; that distinction is
what makes this lever work at all, and it was worth ~27% depth.

The search minimises the **measured** cost `Σ_cubes COST[n_literals]`, not the cube count —
per-cube cost is strongly non-uniform (27 at k ≤ 8 vs 66 at k = 12), so a cover with a fat
11/12-literal tail is far worse than its count suggests.

### 2.3 MCZ synthesis — a measured per-size choice

Multi-controlled-Z dominates the circuit, and the decomposition matters enormously. Measured
depth/CX in the `u3`+`cx` basis:

| controls | Qiskit default (0 anc) | `noaux_v24` | **`kg24`, 2 clean anc** |
|---|---|---|---|
| 6 | 191 / 124 | 192 / 140 | **54 / 30** |
| 9 | 513 / 332 | 703 / 444 | **60 / 48** |
| 12 | 1130 / 716 | 1499 / 900 | **73 / 66** |

Khattar–Gidney (2024) with 2 clean ancillas is ~8.5× shallower at k = 9 and nearly *flat* in
control count. Notably the linear-depth ancilla-free method is *worse* than Qiskit's default
here — the win comes from **spending ancillas**, not from a cleverer ancilla-free circuit.

But `kg24` uses only 2 of our 6 ancillas. Using all six, a **balanced RCCX AND-tree** does
better: controls are AND-ed pairwise into ancillas, and because those pairs are *disjoint*
the RCCXs execute concurrently, giving a log-depth tree where `kg24` is serial.

| k | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|
| `kg24` | **10** | 22 | 36 | 27 | 54 | 54 | 56 | 60 | **64** | 73 |
| AND-tree | 15 | **15** | **27** | **25** | **27** | **27** | **36** | **55** | 66 | **66** |

The tree wins for k = 4…10 and k = 12 — up to −50% depth for ~2% more CX. The build picks
the better method **per cube** from this measured table. This is a deliberate CX-for-depth
trade: depth is scored, CX is only the tiebreak.

### 2.4 Cube order is a free parameter — worth ~13%

All 38 cubes are diagonal, hence mutually commuting, so their order is unconstrained.
Measured spread across orderings: **2431–2929** depth at the 57-cube stage — 17%. Random
orderings are the worst case, so this must not be left to chance. The shipped order comes
from 2-opt on a control-overlap proxy, then direct measurement of transpiled depth.

### 2.5 Relative-phase Toffolis are free inside `U`

An RCCX (Margolus gate) is a Toffoli up to basis-state-dependent phases: `RCCX = Λ·CCX` with
`Λ` diagonal. It costs **depth 7 / 3 CX** against CCX's **11 / 6**.

Conjugating a diagonal by a permutation stays diagonal, so writing `U = Λ_tot · P`:

```
U† · D · U  =  P† Λ† D Λ P  =  P† D P        (diagonals commute)
```

The relative phases cancel **identically** — not approximately. So RCCX substitutes for CCX
everywhere inside `U`, and the resulting unitary is bit-for-bit the one the full-Toffoli
circuit implements. One subtlety: RCCX is *not* self-inverse (CCX is), so the reversed pass
must emit `RCCX†`. Worth 1358 → **1332**.

### 2.6 Exact verification at every step

Nothing counts as a candidate until it passes a full 4096-state check that also confirms the
ancillas return to `|0⟩` — this catches lowering bugs, phase leakage and convention
mismatches that a spot check would miss. The shipped circuit was then put through the
organisers' own Step 6 (Classiq simulator, random product states):

```
Successfully verified loaded QASM with score 1332
width = 18   depth = 1332   CX count = 1317
max error = 3.8e-16   ancilla error = 6.7e-17   normalization error = 2.2e-14
```

All three thresholds are 10⁻¹⁰; the circuit is ~6 orders of magnitude inside every one.

---

## 3. Progress: baseline → final

Every row is independently verified exact (0/4096 wrong). Depth is the scored metric.

| # | approach | depth | CX | width |
|---|---|---|---|---|
| 0 | **Organisers' baseline** — one `control()` per raster rectangle (18 of them) | 5329 | 3502 | 18 |
| 1 | Predicate sharing — the 18 rectangles have only 10 unique x-ranges; compute each once | 4316 | 2630 | 18 |
| 2 | GF(2) rank-10 factorisation + CP-SAT reversible-pebbling scheduler | 3335 | 2490 | 18 |
| 3 | ESOP cover + ancilla-free MCZ *(the route later written off — see §5)* | 9620 | 6496 | 12 |
| 4 | …same cover, `kg24` 2-clean-ancilla MCZ | 2769 | 2136 | 14 |
| 5 | …+ optimised cube order | 2422 | 1827 | 14 |
| 6 | …+ non-linear change of variables (5 gates → 46 cubes) | 1927 | 1418 | 14 |
| 7 | …+ 6-ancilla AND-tree MCZ (full width budget) | 1438 | 1425 | 18 |
| 8 | …+ cost-model-driven transform search (13 gates → 38 cubes) | 1358 | 1336 | 18 |
| 9 | **…+ RCCX inside the conjugating permutation — SHIPPED** | **1332** | **1317** | **18** |

**4.0× depth reduction from the organisers' baseline**, and 7.2× from row 3 — with *no new
circuit construction*. Every gain came from a better choice inside an existing structure: the
MCX decomposition, the gate order, the variable basis, the ancilla budget, the cost model,
and the Toffoli variant.

One result is deliberately absent. BQSKit numerical resynthesis reached 1330/1321, but every
BQSKit-processed circuit leaves ~10⁻⁹ residual error — it passes a 10⁻⁸ check and **fails the
official 10⁻¹⁰ one**, and this is not fixable via `synthesis_epsilon` (1e-12 → 1.4e-09,
1e-16 → 1.33e-09). Those circuits would have scored zero. Dropping BQSKit costs ~2%.

---

## 4. Suitability for real quantum hardware

The submitted circuit is a hardware-shaped artifact rather than a simulator-only one:

- **Native gate set.** `u3` + `cx` exclusively — the single- and two-qubit primitives real
  superconducting and trapped-ion stacks actually execute. No high-level or synthetic gates
  survive into the submitted file; it is fully decomposed.
- **Fixed, small width.** Exactly 18 qubits, known statically.
- **Clean ancillas, provably restored.** All 6 ancillas return to `|0⟩` to 6.7×10⁻¹⁷. This is
  what makes the oracle *composable*: it can be called repeatedly inside Grover or a quantum
  feature map without leaking entanglement into scratch space, and the ancillas are reusable
  by the surrounding algorithm. An oracle that leaves dirty ancillas is unusable as a
  subroutine regardless of its depth.
- **Exact, not variational.** Error 3.3×10⁻¹⁶. An approximate oracle's error compounds across
  Grover iterations; this one contributes none.
- **Depth-first, CX-second by design.** The AND-tree spends ~2% extra CX to cut MCZ depth by
  up to 50%, which is the correct trade on hardware where the limit is decoherence *time*,
  not gate count.
- **Relative-phase Toffolis where they are provably safe.** RCCX at half the CX of a full
  Toffoli, justified by the conjugation argument in §2.5 rather than by tolerance.

**Honest caveat.** The circuit assumes **all-to-all connectivity** — no SWAP routing is
included, per the challenge's stated scoring model. On a fixed-coupling device it would need
a well-connected 18-qubit sub-lattice and would grow in depth under routing. At 1332 depth it
is also beyond what current NISQ coherence windows comfortably support. It is a correct,
hardware-native *compile target*, not a run-today experiment.

---

## 5. The gap: what the winners did

Final standings put the winner at **depth 95 / 272 CX**, with 2nd–7th clustered tightly at
**107–111** despite very different CX counts (373–558) — several independent teams converging
on the natural depth of some construction. Our 1332 is **14×** off.

### 5.1 The structure we found, verified, and then failed to build

The image has exactly **11 distinct row patterns**, and they form a **width-2 containment
poset** — two chains:

```
chain 1 (7 levels):  {} ⊂ [38,42] ⊂ [36,44] ⊂ [34,46] ⊂ [33,47] ⊂ [32,48] ⊂ [2,61]
chain 2 (5 levels):  {} ⊂ [2,26] ⊂ +[53,57] ⊂ +[51,59] ⊂ +[50,60]
```

Let `u(y)` = which chain row `y` belongs to, `l(y)` = its level in that chain, and
`a_u(x)` = the least level of chain `u` containing column `x`. Then, **verified 0 wrong of
4096** (`research/fused2.py`):

```
f(x,y)  =  [ a_u(x) ≤ l(y) ]          — ONE comparison
        =  [ l(y) + mu(x,u) ≥ 7 ]     — a threshold on a sum,  mu(x,u) = 7 − a_u(x)
```

The whole oracle is therefore: a 3-bit **level code of the rows**, a 3-bit **level code of
the columns**, and a single comparison. The row code is a 6→3-bit function (**64 points**);
the column code takes `x` *plus the chain bit* `u`, so it is 7→3 bits (**128 points**). That
extra input is the part we misread for days — we read the published hint as "get the class
count below 8 per side", measured 11, and treated it as a wall. The chain choice does not
consume code bits at all; it is a separate *input* to the column code.

The remaining obstacle is sharper than "nearly there": the fused form needs
`l(3) + u(1) + mu(3) = 7` ancillas live simultaneously and we have **6**. The two-pass XOR
form fits 6 (each pass needs `l_u(3) + a_u(3)`, with `u` implicit in which pass is running),
so fusing buys depth but costs an ancilla. The way in is probably that the code bits need not
live on dedicated wires — only on some set of wires whose GF(2) *span* contains them — but
that is unconfirmed.

### 5.2 The method we were missing: decompose, then brute-force the small piece

The winners did not *synthesise* those codes. They **searched** for them: many thousands of
annealing chains per code, each first finding a correct circuit and then annealing it toward
minimum depth against an exact model of final `u3`/`cx` depth.

A 6→3-bit function is 64 points. That is small enough to search directly — and the GPU scale
they used is not the part that mattered. Our own annealing prototype
(`research/anneal_rev.py`) failed because it annealed the **whole 18-qubit oracle**, where
every single-gate mutation changes the computed function and is rejected on correctness, so
the chain never leaves its seed. The correct ordering is **decompose first, brute-force the
small piece second**.

### 5.3 The two process errors that cost the most

**We never budgeted backwards from the public target.** 95 depth / 272 CX is ~90 RCCX total,
~45 per half, so ~25–30 depth per component. Our interval-indicator primitive measured **136
depth by itself** (`research/interval_prim.py`). That one division rules out the entire
"materialise predicates into ancillas, CZ, uncompute" architecture — and it was performed on
day 14 of a 16-day project, after weeks had gone into that architecture. The signal was
public far earlier: a competitor was already at 128 depth by 17 September, while this project
sat at ~4000.

**We closed the winning route on a measurement of the wrong thing.** Having found the exact
decomposition, we synthesised the encoder bit-functions as AIGs (16, 13, 15 nodes), measured
them infeasible to pebble within the available scratch, and concluded "unbuildable in 6
ancillas." That measured **AIG-synthesis-then-pebble** — a method already committed to — and
not the cost of the function. The project's own notes had recorded exactly this check two days
earlier, in bold, after an identical mistake on the ESOP route (which had been written off at
9620 depth and became the winning route at 2769 once the MCX decomposition was fixed —
row 3 → row 4 above). Writing the lesson down did not prevent repeating it, because it was
filed as a fact about one route instead of as a check to run before closing *any* route.

A third, smaller one: the anti-stuck rule rewarded *any* measured improvement, which kept
effort inside one valley — 17% from scheduler tuning, 14 hours of compute for 0.4%. A better
rule is that **while the gap is >5×, an improvement that does not change the order of
magnitude is not progress.**

---

## 6. Repository layout

```
submission.qasm                  the scored artifact — 18 qubits, 1317 cx + 1622 u3
submission.qmod                  Classiq Qmod source, gate-for-gate identical
submission_model.py              Python Qmod that regenerates the .qmod
submission.synthesis_options.json

src/qoracle/
  spec.py           bit conventions — single source of truth
  ir.py             PhaseIR: the cover/lower cut point (XOR-ed cubes + affine pre-map)
  io.py             the real logo; rectangle decomposition
  diagnostics.py    density, symmetry, GF(2) rank, ANF degree spectrum
  gf2.py            rank / factorisation
  cover/            spec → PhaseIR     [minterm, pprm, esop_abc, gf2_factor, rect_groups]
  lower/            PhaseIR → circuit  [serial_mcz, gf2_ancilla, rect_ancilla, gf2_cpsat_hybrid]
  aig_synth.py      AND-inverter-graph synthesis via `abc`
  pebble_cpsat.py   exact CP-SAT reversible-pebbling scheduler
  classiq_native/   Qmod models synthesised by Classiq itself (the alternative track)
  verify.py         exact 4096-state check + ancilla restoration
  metrics.py        derived, never stored as truth
  classiq_score.py  scoring through Classiq's own AUTO_OPTIMIZE compiler

research/           the experiments behind the result
  build_final.py            rebuilds submission.qasm exactly (and shows the CCX/RCCX test)
  final_build_params.json   frozen parameters of the shipped circuit
  build_hybrid3.py          the full architecture incl. cube-order search
  mcz_variants.py           AND-tree vs kg24, the measured per-k table
  nl_costmodel.py           non-linear change-of-variables search
  fused2.py                 verifies the single-comparison level-code form (§5.1)
  interval_prim.py          the per-primitive cost measurement that should have come first
  fold_test.py              symmetry folding — a measured negative result
  anneal_rev.py             the annealing prototype, and why it stalled

tools/              submission + verification toolchain
  gen_model.py              QASM → exact-angle Python Qmod
  emit_submission_qmod.py   write_qmod at full precision
  check_final.py            proves .qmod and .qasm are bit-identical, then verifies
  nb_metrics.py             the organisers' qasm_metrics(), verbatim
  step6.py                  the organisers' Step 6 acceptance test, verbatim

notes/DECISIONS.md  condensed decision log: what was tried, and why it was kept or killed
CLAUDE.md           working brief the project was actually run from (conventions,
                    live standings, dead ends) — kept as a record of process
```

### Architecture note

The pipeline is cut at **`PhaseIR`** — a synthesis-independent list of XOR-ed cubes.
Everything above the cut is expensive and cached (ESOP minimisation, factorisation, basis
search); everything below is cheap and re-runnable (decomposition, scheduling, transpilation,
metrics, export). Separate `COVER_VERSION` / `LOWER_VERSION` stamps let one stage's cache be
invalidated without touching the other, so changing a metric costs `qo score` and zero
re-synthesis. The canonical stored circuit is QPY at the *high* level with multi-controlled
gates intact — re-scoring re-transpiles from structured form, which beats re-transpiling an
already-decomposed circuit.

---

## 7. Reproducing

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest -q                   # 6 tests

# rebuild the submitted circuit from frozen parameters (byte-identical)
python research/build_final.py

# score and verify it exactly as the organisers do
python tools/nb_metrics.py                 # width / depth / CX off the QASM text
python tools/check_final.py                # .qmod == .qasm, then 4096-state exact check
python tools/step6.py                      # official acceptance test (needs Classiq auth)
```

`abc` (Berkeley) must be on `PATH` for the ESOP and AIG covers. The Classiq SDK needs a
one-time interactive `classiq.authenticate()`.

### A trap worth knowing, if you generate Qmod

Both `qasm_to_qmod()` and `write_qmod()` default to `decimal_precision=4`. They emit
`U(3.1416, …)` where the circuit needs `π` — a 7.3×10⁻⁶ error per gate against a 10⁻¹⁰
correctness bar. Pass `decimal_precision=17`. Substituting symbolic `π` is *not* a fix:
single-qubit gate fusion leaves genuinely irrational Euler angles (`0.8332521844832049`, …)
across 63 distinct angle triples. `tools/check_final.py` guards against this by parsing the
`.qmod` back to a gate list and asserting exact float equality with the `.qasm`.
