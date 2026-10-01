# Decisions log

## 2026-09-17 (cont'd) — nested-predicate Track B experiment: correct, blocked on qubit count
User pushed back on the session's run of dead ends and asked to re-read the
baseline notebook's own hints directly rather than trust prior summaries.
Re-read `classiq-challenge-baseline.ipynb` in full. Two of its three hints
turned out to already be correctly implemented: the Hadamard-harness
synthesis trick (Step 3-5: synthesize `allocate+hadamard_transform+oracle`
together, strip the two `hadamard_transform_` blocks from the QASM by name
afterward) is exactly what `classiq_native/_run_one.py` already does, and
`rectangles.py` is a literal copy of the notebook's own baseline model — not
gaps.

The third hint ("predicate sharing" / "consolidation") led somewhere real.
Pulled the actual 18-rectangle data (`io.logo_rectangles()`) and found disc2's
5 unique x-ranges are a STRICT NESTING CHAIN (`[38,42]⊂[36,44]⊂[34,46]⊂
[33,47]⊂[32,48]`, rings around its widest row) and disc1's 3 are too
(`[53,57]⊂[51,59]⊂[50,60]`) — `rectangles_grouped` treats all 10 unique
x-ranges as flat, unrelated siblings and never uses this. Checked exact-value
endpoint sharing too (the OTHER specific extension CLAUDE.md had flagged as
untried): only one exists across all 10 ranges (rect1 and the middle bar both
start at x=2) — that lead is thin, confirmed by inspection rather than assumed.

Built `classiq_native/rectangles_nested.py`: nests `control()` blocks to match
the real containment chains (widest ring's x-condition computed first, its
own y-rows applied, then INSIDE that scope the next-narrower ring's
x-condition, recursively), keeping rect1/middle-bar flat since they're
numerically wide but geometrically unrelated to either ring family. First
chain-builder attempt had a real bug (picked the NARROWEST contained
candidate as "next link", fragmenting each 5/3-chain into disconnected
pairs+singletons instead of one telescoping chain) — caught by simulating the
nested-control logic in plain Python against `io.logo_pixel` before spending
a real synthesis run (0/4096 wrong once fixed to pick the WIDEST contained
candidate at each step).

Ran it through real Classiq synthesis: **rejected outright, "Model requires
at least 26 qubits, but max width constraint is 18."** Not a depth problem —
a hard qubit-count wall. Tested the minimal case to see if ANY nesting could
fit: isolated just disc1's 3-level chain (everything else flat) — still
**"requires at least 20 qubits"**, 2 over budget even at the shallowest
depth tried. Cost is convex in nesting depth, not linear (flat~18,
3-deep=20, 5-deep=26) — going deeper costs progressively more, not a fixed
per-level increment.

Mechanism, and why this connects to everything else closed out this
session: `control(A, lambda: control(B, ...))` requires A's condition qubit
to stay live for B's entire evaluation — nesting to depth d needs d
simultaneously-live condition qubits, where the flat sibling version
(`rectangles_grouped`) only ever needs one at a time (compute, use,
uncompute, move to the next). This is the identical ancilla-scarcity
constraint that killed `lower/fanout.py` and the carry-lookahead comparator,
reached this time from Track B (Classiq-native qmod) instead of Track A
(our own AIG/CP-SAT pipeline) — six independent techniques now, from two
completely different synthesis tracks, have hit the same wall: our 6 spare
qubits are not enough to hold more than one non-trivial intermediate result
alive at a time, for essentially anything tried. Logged dead in CLAUDE.md;
`rectangles_nested.py` kept (like `primitives.py`) as a correct, verified,
blocked reference — don't revisit without either a fundamentally cheaper
"N simultaneous conditions" encoding or a relaxed qubit budget.

## 2026-09-28 (cont'd, 5) — SUBMISSION-CRITICAL: every BQSKit circuit fails the official 1e-10 test
With one day left, ran the notebook's OWN acceptance checks rather than only
our `verify.py`. Two findings, the second nearly cost the submission.

1. **Format validator: clean.** Replicated the notebook's `qasm_metrics()`
   verbatim on our artifact -- correct header, single `qreg q`, width 18 in
   [12,18], 0 unsupported statements, and THEIR depth metric returns exactly
   the same numbers we report.

2. **Statevector test: our best circuits FAIL.** The notebook checks against a
   **1e-10** threshold; our `verify.py` uses atol **1e-8**, i.e. LOOSER. So we
   had been passing a weaker test all along. Measured across every artifact:

| family | max deviation | passes 1e-10 |
|---|---|---|
| every BQSKit-processed circuit | 1.4e-09 .. 4.6e-09 | **NO** |
| every non-BQSKit circuit | ~3e-16 | yes |

   Cause is BQSKit's numerical resynthesis, and it is **not** fixable by
   tightening `synthesis_epsilon`: 1e-12 -> 1.4e-09, 1e-14 -> 1.19e-09,
   1e-16 -> 1.33e-09. The error floor is inherent. **The earlier claim in
   CLAUDE.md that 1e-12 clears the bar is WRONG** -- it was written from the
   1e-8 default failing, and never re-checked against the real 1e-10 test.

**Consequence:** every "best" recorded on 2026-09-18 through 2026-09-28
(3230, 3194, 2732, 2399, 1779, 1759, 1409, 1330) was BQSKit-processed and
would have scored ZERO. **Valid best is `esop_hybrid_tree3`: depth 1358,
cx 1336, width 18, deviation 4.82e-16**, saved as `SUBMISSION_oracle.qasm`.
Cost of dropping BQSKit is only ~2%.

**Process lesson:** we optimised for months against a proxy checker that was
100x looser than the real one. Always run the ACTUAL acceptance test of record
early, not a local approximation of it -- and re-run it before trusting any
new tool in the pipeline.

## 2026-09-28 (cont'd, 4) — ring form doesn't fit either; annealing prototype stalls. Two negative results that narrow things sharply.
**Ring form does NOT solve the ancilla problem.** `phase = XOR_i ([x in R_i]
AND [L1>=i])` with tiny rings measured **184 AIG nodes** (vs 169 for the
current route), and the terms still need 4-5 scratch, several infeasible even
at 5. Completes a striking pattern -- every decomposition tried lands in the
same regime:

| decomposition | AIG nodes | scratch/term |
|---|---|---|
| full intervals (`gf2_factor`) | 169 | 4-5 |
| incremental deltas | 190 | 4-5 |
| level-code encoders | 149 | 4-5 |
| ring form | 184 | 4-5 |

**~150-190 nodes and 4-5 scratch every single time** -- that looks like a real
invariant of this function's 6-bit sub-components, not an artifact of any one
slicing. With 12 data + 6 ancillas only one such evaluation fits at a time,
which forces the compute/uncompute serialisation costing us ~10x.

**Floor for the whole structural family:** ~10 sub-functions x ~10 nodes x
3 cx x 2 (compute+uncompute) ~= **600 cx even with perfect, recomputation-free
pebbling**. The leader is at 269 -- BELOW that floor. So their circuit is
almost certainly not built from AIG-synthesised predicates at all.

**Annealing prototype (`scratchpad/anneal_rev.py`): built, works, stalls.**
Searches U over {X,CX,CCX} on 18 qubits with oracle = U.Z(flag).U^dag (so
ancillas need not be restored and depth = 2*depth(U)+1; 97 total => depth(U)
~48). Vectorised over all 4096 inputs. Seeded from a verified-correct
ESOP-derived circuit (fixed a real bug first: the CCX ladder wrapped around
and reused workspace qubits still holding live values -- recursive split-AND
fixes it). 4000 steps in 27s: **2873 -> 2871**, i.e. frozen.
**Why:** any single-gate insert/delete/replace changes the computed function,
so nearly every move is rejected on the wrongness penalty and the chain never
leaves the seed. **Naive annealing over raw gate sequences is not viable.**
Re-reading the source hint ("each chain FIRST finds a correct circuit, THEN
anneals it towards smallest depth") -- the annealing must move through
CORRECTNESS-PRESERVING REWRITES (circuit identities, commutations, peephole
substitutions), which is a rewrite-rule engine, not a gate-mutation sampler.
That, plus GPU-scale parallelism, is the actual missing machinery.

## 2026-09-28 (cont'd, 3) — THE EXACT DECOMPOSITION, verified 0/4096. Build this next.
Pushed the level-code finding to its exact form. The 11 distinct row patterns
form a **width-2 poset** -- exactly two containment chains:

```
chain 1 (7 levels): 0/ {}  1/ [38,42]  2/ [36,44]  3/ [34,46]
                    4/ [33,47]  5/ [32,48]  6/ [2,61]
chain 2 (5 levels): 0/ {}  1/ [2,26]  2/ [2,26]u[53,57]
                    3/ [2,26]u[51,59]  4/ [2,26]u[50,60]
```

Define, for x:  a1(x) = least level j with x in chain1[j] (else 7)
                a2(x) = least level j with x in chain2[j] (else 7)
       for y:  L1(y) = level of row y if its pattern is in chain 1, else 0
               L2(y) = level of row y if its pattern is in chain 2, else 0

Then, **verified exactly, 0 wrong of 4096**:

```
f(x,y)  =  [ a1(x) <= L1(y) ]   XOR   [ a2(x) <= L2(y) ]
```

Ranges: a1 in {1..7}, L1 in {0..6}, a2 in {1,2,3,4,7}, L2 in {0..4} -- every
one fits in **3 bits**. The two terms are never simultaneously true (checked:
0 such (x,y)), so the XOR cannot double-cancel. The chain-1 and chain-2 y-rows
are disjoint, so the two comparisons can be **two passes sharing the same 6
ancillas**: 3 bits for the x-code + 3 for the y-code + one comparison each.
That is exactly the "3-bit level code of the rows and one of the columns,
single comparison constraint" description of the top solutions, and it explains
why the ancilla budget is 6.

**Why this should be much cheaper than anything we have built.** The x-encoder
reads only the x-register and the y-encoder only the y-register -- DISJOINT
supports, so they run concurrently (depth = max, not sum). And a single 3-bit
comparison replaces the 10 separate CZ terms of the GF(2) route. Contrast the
ESOP route, which has 0 of 1596 disjoint cube pairs and therefore cannot
parallelize at all.

**The open obstacle (do not skip this).** The 12 encoder bit-functions total
**149 AIG nodes** (a1: 19/11/8, L1: 16/13/11, a2: 9/17/13, L2: 15/10/7) --
comparable to the GF(2) route's 169. But materializing both 3-bit codes
consumes all 6 ancillas, leaving **zero scratch** to evaluate those AIGs, and
this session measured repeatedly that these 6-bit AIGs need 5-6 scratch to
pebble at all. Computing an encoder bit with 0-2 scratch means ancilla-free
MCX per ANF term (10-33 terms per bit) -- catastrophic. So the construction is
exact and the right target, but the ancilla schedule is unsolved.

Promising ways in, in order:
 (a) **Ring form.** Since chain 1 is nested, with R_i = chain1[i] \ chain1[i-1]
     one gets `phase = XOR_i ( [x in R_i] AND [L1(y) >= i] )`. The rings R_i
     are TINY (2-5 elements each: R_1=[38,42], R_2=[36,37]u[43,44], ...), so
     their indicators should have far smaller AIGs than the full intervals we
     currently synthesize, and `[L1>=i]` is a cheap threshold on 3 bits. This
     keeps the concurrency and may dodge the scratch problem.
 (b) Materialize only ONE code (e.g. L1, 3 ancillas) and apply the phase
     conditioned on (raw x-register, L1), leaving 3 ancillas as scratch.
 (c) Search for a cheap reversible transform minimizing the number of distinct
     row/column classes (target <=8 per side). NOTE this is a completely
     different objective from the ESOP-cube-count one we have been using --
     our current 13-gate transform makes this metric WORSE (11/11 -> 17/13),
     i.e. we have been optimizing the wrong quantity for this route.

Also learned: the top solutions reportedly use **massive GPU simulated
annealing over reversible circuits**, tens of thousands of chains, annealing
against an exact model of the final u3/cx depth. So part of the gap is raw
search scale, not only structure.

## 2026-09-28 (cont'd, 2) — STRUCTURAL KEY FOUND: f factors as g(Lx(x), Ly(y)) via level codes
Literature/leaderboard search surfaced two concrete descriptions of what the
top solutions do:
1. Massive GPU simulated annealing over REVERSIBLE CIRCUITS directly -- tens of
   thousands of parallel chains, each first finding a correct circuit then
   annealing it against an EXACT model of final u3/cx depth. Brute force at
   scale, not a clever analytic construction.
2. "The oracle needs only two small circuits: a 3-bit LEVEL CODE of the rows
   and one of the columns", plus "a single comparison constraint".

**Tested (2) directly and it is EXACTLY TRUE for our image:**
`f(x,y) = g(Lx(x), Ly(y))` factors with **zero error**, where
- the image has exactly **11 distinct ROW patterns** and **11 distinct COLUMN
  patterns** (consistent with the earlier real-SVD rank of 11 -- same fact
  seen from a different angle), and
- g is an arbitrary small function on the two class indices.

So the whole oracle is: encode x to a class, encode y to a class, apply one
small function of the two codes. This is the structure the leaders exploit,
and it explains why 6 ancillas is the stated budget (3 + 3 level-code bits).

**Where we stand vs it.** 11 classes needs ceil(log2 11)=4 bits per side, so
4+4=8 ancillas -- OVER the 6-ancilla budget. The hint's 3+3 implies they got
the class count down to <=8 per side. Two ways in:
 (a) find a cheap reversible transform that reduces distinct row/column
     classes to <=8 each -- note this is a COMPLETELY DIFFERENT search
     objective from the one we have been using. Our existing 13-gate
     transform, optimized for ESOP cube count, makes this metric WORSE
     (11/11 -> 17/13). We have been optimizing the wrong quantity.
 (b) encode only ONE side: Ly needs just 4 ancillas, leaving 2 free, and the
     phase is then applied conditioned on (raw x-register, Ly). Fits the
     budget immediately, no transform needed.

Also measured this round, both ruling things out:
- **Generic diagonal-unitary synthesis** (Qiskit `Diagonal` on the full 4096
  diagonal): 8170 depth / 4094 cx, verified -- exactly the textbook 2^n-2 CNOT,
  2^(n+1)-3 depth result. Parallelizing it across 6 ancilla accumulators would
  give ~1360, i.e. a tie with our 1330. Not the answer.
- **The interval-indicator primitive**, measured in isolation and gated on an
  exact 64-input check: **~103 cx / ~136 depth per 6-bit interval** (5 scratch;
  at 4 scratch most are infeasible). The leader's ENTIRE circuit is 269 cx /
  97 depth, so ONE of our range tests costs more depth than their whole
  circuit. Even assuming perfect recomputation-free pebbling (AIGs are only
  5-9 nodes, ~54 cx compute+uncompute), 20 tests = ~1080 cx, still 4x their
  total. **This rules out the entire "materialize predicates into ancillas,
  CZ, uncompute" architecture arithmetically.**

**Next step, clearly identified:** build the level-code oracle (route (b) first
since it fits the budget today), and re-run the transform search against the
NEW objective of minimizing distinct row/column class counts rather than ESOP
cube count. Best remains 1330/1321.

## 2026-09-28 (cont'd) — leader at 97/269; phase-polynomial RULED OUT; incremental-accumulator GF(2) blocked on ancillas
New leaderboard datapoint from user: **97 depth / 269 CX**. Our 1330/1321 is
13.7x on depth, 4.9x on CX. Their ratio 2.77 vs our 0.99 -- they use ~5x fewer
gates AND pack them ~2.8x denser.

**Phase polynomial / Walsh: RULED OUT, and an old note here was WRONG.** 269 CX
looks exactly like a Gray-coded phase polynomial (~1 CNOT per parity term), so
this was worth checking properly. Computed the full Walsh-Hadamard spectrum of
f: **all 4096 coefficients are nonzero**, and it is not remotely concentrated
(2123 terms for even 90% of L1 mass; by weight |S| the counts are exactly the
binomials C(12,k)). So any parity-based construction needs ~4096 Rz terms.
DEAD. **Correction to the record:** an earlier entry claimed the WHT was
"genuinely concentrated (unlike ANF)" -- that is false, as measured here. Note
also the older dismissal of phase polynomials cited the ANF degree histogram,
which is the wrong transform for this question (ANF = AND-monomials, phase
polynomials need Walsh/parities), and claimed "additive decomposition can't
become multiplicative", which is also wrong -- sums in an exponent DO factor
into products of unitaries. The conclusion (dead) happens to be right, but the
stated reasons were not; it is settled now on correct evidence.

**What 269 CX probably is.** 10 terms (the proven GF(2) rank floor) x ~27 CX
= 270. That points back at our own rank-10 factorization, implemented ~10x
more cheaply than `gf2_cpsat_hybrid` does (886 RCCX ~ 2658 CX).

**Where our 10x overhead lives (measured).** Printed the structure of all 20
sub-functions: every one is a union of 1-2 CONTIGUOUS INTERVALS (v_k are
x-ranges like [38,42]; u_k are symmetric y-ring pairs like [11,11]u[27,27],
and the u_k are mutually DISJOINT). We synthesize them as opaque truth tables
via AIG (169 nodes total -- actually fine) and then pay a **5.2x pebbling
recomputation penalty** (886 RCCX emitted for 169 nodes) because CP-SAT must
recompute constantly to fit 5-6 ancillas.

**Incremental-accumulator idea (correct, and it would have worked).** Keep ONE
accumulator per side and apply only the delta between consecutive factors:
`U ^= u_k^u_{k-1}`, `V ^= v_k^v_{k-1}`, then `CZ(U,V)`; a final delta walks both
back to 0, so there is no separate uncompute pass at all. Delta AIGs total 190
nodes vs the 886 RCCX currently emitted -- a 4.7x reduction -- and the v-side
(x-register) and u-side (y-register) have DISJOINT support, so they run
concurrently, which the ESOP route structurally cannot do (0/1596 disjoint
cube pairs). Built it and verified correct (n_wrong=0).

**Blocked on ancillas, measured precisely.** The construction needs 2 qubits
held permanently (one accumulator per side) plus scratch to pebble each delta
AIG, leaving only 4 scratch. Built the full 11x11 transition cost matrix over
factor orderings (factor order is FREE -- all 10 CZ terms commute): **104 of
110 transitions are unschedulable at 4 ancillas.** Exact Held-Karp over the
orderings confirms no feasible tour exists. So reordering cannot rescue it;
the approach needs 7-8 ancillas and we have 6. A partial build using only the
schedulable subset reached 925 depth / 699 CX before falling back -- i.e. the
cost profile is excellent WHEN it fits, which is what makes this frustrating
rather than merely negative. Forcing the unschedulable deltas through an
ancilla-free Reed-Muller fallback works (verified correct) but costs
4958/3404, far worse than doing nothing.

**CORRECTION (same day, diagnostic run) -- the ancilla diagnosis above was
WRONG.** User asked for an out-of-budget trial purely to isolate the variable.
Ran the incremental construction at 2 accumulators + S scratch:

| scratch | total qubits | depth | cx | unschedulable deltas | valid |
|---|---|---|---|---|---|
| 4 | 18 | 1043 | 778 | 13 | NO |
| 5 | 19 | 2665 | 2005 | 4 | NO |
| 6 | **20** | **3599** | **2824** | 0 | **YES** |

The only CORRECT version costs **3599/2824 -- ~2.7x worse than the legal
1330/1321**. More ancillas do not rescue it; the construction is simply
expensive once completed. **So the 6-ancilla budget is NOT the binding
constraint here**, contrary to what was written above.

**Methodological lesson, recorded because it was made twice in one session:**
the cheap-looking 1043/778 and 2665/2005 rows are cheap ONLY because 13 and 4
deltas were silently skipped as unschedulable -- they are not valid circuits.
The earlier "partial build reached 925/699, so the cost profile is excellent"
claim in this same entry was the identical error. **An incomplete or
unverified circuit's depth/CX is meaningless -- never quote it as evidence,
and never let it seed a diagnosis.** Always gate cost measurements on
`verify.py` passing first.

This also weakens the broader "one 6-ancilla wall explains every failure"
narrative that had been forming across fanout / nested predicates /
carry-lookahead / this. Those each failed; the shared-cause story is not
established. Best remains **1330/1321**.

## 2026-09-28 — 6-ancilla AND-tree MCZ + cost-model transform search: 1759 -> 1330 (final; plateaued)
User raised three points that turned out to compose into one experiment:
(a) we were using only 14 of 18 qubits, (b) we should trade CX for depth since
CX is only the tiebreak, (c) keep reducing variables/literals.

**6-ancilla balanced AND-tree MCZ.** kg24 uses exactly 2 ancillas; we had 6
idle. Build a balanced tree of RCCX partial-ANDs -- pairs of controls ANDed
into ancillas -- and because those pairs are DISJOINT the RCCXs run
concurrently, giving a log-depth tree where kg24 is serial. RCCX is safe here:
its relative phases cancel exactly against the uncompute since only a diagonal
gate sits between (same argument the AIG pebbling already relies on). Verified
directly (0 bad amplitudes, 0 ancilla leak) at k=3,5,8,9.
Measured per-k optimum, `reserve` = ancillas held back for a kg24 residual:

| k | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|
| kg24 | **10** | 22 | 36 | 27 | 54 | 54 | 56 | 60 | **64** | 73 |
| tree | 15 | **15** | **27** | **25**(r3) | **27** | **27** | **36** | **55** | 66 | **66**(r2) |

Tree wins k=4..10 and k=12, up to -50% depth, for ~2% more CX. Reserving
ancillas matters at the top end: without it the residual falls back to
Qiskit's ancilla-free `mcp`, which is why a naive tree measured 90 at k=11
(vs kg24's 64). Table: `scratchpad/mcz_best_table.json`.
**1775 -> 1438**, width 14 -> 18 (full budget).

**Cost-model-driven transform search.** With the table above, per-cube cost is
very non-uniform (k<=8:27, k=9:36, k=10:55, k=11:64, k=12:66), so minimizing
CUBE COUNT is wrong -- a cover with a fat 11/12-literal tail is far worse than
its count suggests. Re-ran the non-linear basin-hopping against
`sum(COST[n_literals])` instead: 40 cubes/cube_cost 1614 -> 38 cubes/1496.
**1438 -> 1358**, then BQSKit -> **1330 / 1321 at width 18, verified.**

**PLATEAUED.** Three further refinements each bought ~nothing: a 70-hop deeper
transform search (cube_cost 1496 -> 1465) produced no real depth change; the
measured per-k MCZ optimum incl. reserve tuning changed depth by 0 and CX by
-5; BQSKit gives ~2%. Stop optimizing this architecture.

**Cumulative 2026-09-26/28: 3194/2467 -> 1330/1321, a 58% depth reduction**,
from six compounding levers, NONE of them a new circuit construction: MCX
synthesis method, cube ordering, non-linear change of variables, 6-ancilla
AND-tree MCZ, cost-model-driven search, BQSKit. Gap to leader 25x -> 10.3x.

**What still blocks 129 (unchanged and structural).** 0 of 1596 cube pairs
have disjoint support, so no two MCZ gates can ever run concurrently. Every
lever above reduced WORK; none created PARALLELISM, because this architecture
forbids it. Note the cx/depth ratio has now risen from 0.77 to 0.993 purely
because the tree spends CX to buy depth -- still far below the leaders' 2-5,
which remains the real signature of the gap.

## 2026-09-26 (cont'd) — NON-LINEAR change of variables: 57 -> 46 cubes, new best 1927/1418
User's idea, and it broke a wall that the LINEAR version provably could not.

**Why linear was blocked (proved + measured).** Max ANF degree of our function
is 12, and ANF degree is INVARIANT under any invertible linear map. A degree-d
ANF monomial requires some ESOP cube with >= d literals, so EVERY linear basis
contains a 12-literal full-support cube. Measured on 6 random linear bases:
max cube size was 12 in all six, mean support stayed 8.3-9.2 (baseline 8.89),
disjoint cube pairs stayed ~0 -- and cube count BLEW UP from 57 to 79-169.
Linear basis change is strictly harmful here.

**Non-linear breaks the invariant.** Toffoli gates are non-linear, so f∘P has
a different ANF degree profile. General permutations are exponentially
expensive (already on the dead list, "costs more than the oracle it
optimises"), but a permutation built from a HANDFUL of Toffoli/CX gates is
cheap enough to pay for itself, since depth ~ n_cubes x ~48 and each gate
costs only ~4-22 depth both-directions. That middle ground was never tested.

Annealed over short Toffoli+CX circuits, objective = n_cubes*48 + gate cost
(ESOP eval via `abc` is only ~0.11s, so thousands of evaluations are cheap).
Found with just **5 gates** (`cx 11->10, cx 2->3, cx 2->1, tof(10,5)->8,
tof(10,9)->7`): **57 cubes/507 literals -> 46 cubes/401 literals.**

**Construction.** `diag(f) = U . diag(g) . U^dagger` where `g(z)=f(P(z))` and
U is the 5-gate circuit. Emit U^dagger, then g's ESOP oracle (kg24 MCZ +
optimized cube order), then U. Verified `n_wrong=0`.
**Result: 1927 depth / 1418 CX at width 14** (was 2399/1825).
Artifact: `data/artifacts/lower/esop_nonlinear/`.

**Cumulative for 2026-09-26: 3194/2467 -> 1927/1418, a 40% depth reduction**,
from three compounding levers, none of which was a new circuit construction:
MCX synthesis method (kg24, 2 clean ancillas), cube ordering (free parameter,
cubes commute), and a cheap non-linear change of variables.

## 2026-09-26 — BREAKTHROUGH: MCX synthesis method. New best 2732/2136 at width 14 (was 3194/2467 at width 18)
User supplied two papers to check. The second (arXiv 2203.11882, da Silva &
Park, "Linear-depth quantum circuits for multiqubit controlled gates") did
not itself help -- but asking "is our multi-controlled-gate decomposition any
good?" did, and the answer was that we had been leaving a ~8.5x factor on the
table in a route we had already written off.

**First: confirmed the question does NOT apply to the then-best circuit.**
`gf2_cpsat_hybrid` pre-transpile gate composition is `{x: 1884, rccx: 886,
cx: 16, cz: 10}` -- RCCX is 2-control, so there are no large multi-controlled
gates for a better MCX decomposition to improve. Track A was immune.

**Where it DID apply: the ESOP route.** `esop_abc`+`serial_mcz` (row 8,
9620/6496) is built entirely from per-cube multi-controlled Z gates (57
cubes, avg 8.9 controls, max 12) and ran at **width 12 -- using ZERO of our
6 available ancillas.** Benchmarked every MCX synthesis method in Qiskit 2.5
(depth/cx, transpiled u3+cx):

| n | qiskit default | noaux_v24 | noaux_hp24 | 1_clean_kg24 | 2_clean_kg24 |
|---|---|---|---|---|---|
| 6  | 191/124  | 192/140  | 191/124  | 57/30 | **54/30** |
| 9  | 513/332  | 703/444  | 513/332  | 89/48 | **60/48** |
| 12 | 1130/716 | 1499/900 | 1130/716 | 117/66| **73/66** |

Khattar-Gidney 2024 with 2 clean ancillas wins at every size. Notably the
da Silva-Park method (`noaux_v24`) is WORSE than Qiskit's own default at
n>=8 -- the gain is from SPENDING ANCILLAS, not from a better ancilla-free
construction. `n_clean_m15` (v-chain) is worse than kg24 at every size and
needs n-2 ancillas (>6 for n>=9), so kg24-2-clean is strictly the right
choice for us everywhere.

**Result: rebuilt the identical ESOP cover with kg24-2-clean MCZ.**
No change to the cover -- same 57 cubes, same 507 literals, same math.
- 9620/6496 @ width 12  ->  **2769/2136 @ width 14** (3.5x depth)
- +BQSKit (`max_synthesis_size=4, optimization_level=2, eps=1e-12`, 252s)
  -> **2732/2136 @ width 14**
Both verified `n_wrong=0, global_phase_flip=false` via `verify.py`.
Beats the previous best (3194/2467 @ width 18) by **14.5% depth, 13.4% cx,
and 4 fewer qubits.** Artifacts: `data/artifacts/lower/esop_kg24/` and
`.../esop_kg24_bqskit/`.

**Process lesson, worth generalizing.** The ESOP route was written off early
as hopeless (9620, row 8 of 9) and never revisited. But that number was an
artifact of the IMPLEMENTATION (ancilla-free MCX, zero ancillas used), not of
the APPROACH. Once the width cap was known to be 18 and 6 ancillas were
available, every route measured at width 12 should have been re-measured --
it never was. **Before writing off a route, check whether the measurement is
an artifact of implementation rather than approach.** Eight
circuit-construction leads were closed this session on carefully-argued
evidence; this one reversal came from re-examining a measurement, not from a
new construction.

**Follow-up: the right ESOP objective changed.** kg24 depth is nearly flat in
control count (36 at n=4 -> 73 at n=11), so total depth ~ n_cubes x ~48 and
is driven by CUBE COUNT, not literal count. The 2026-09-17 exact CP-SAT search
minimized LITERALS -- the wrong objective under this cost model. Re-ran it
with a cube-count objective (2614-candidate enriched pool, 600s, 8 workers):
still 57 cubes, no improvement. But the proven lower bound is only **19**, so
57 is NOT proven optimal, and the pool was limited to generalizations of
EXORCISM's own cubes. **A genuinely smaller cube cover is now the single most
valuable open target** -- every cube removed is worth ~48 depth directly.
Also checked and rejected: cube reordering to cancel polarity X gates (all
cubes are diagonal so they commute freely, but 57 x ~48 = ~2740 already
accounts for essentially all of the 2769, so the 920 X gates cost ~nothing);
and using the 4 still-idle ancillas for shared sub-products (depth is flat in
n, so reducing control counts buys almost nothing).

## 2026-09-25 — change-of-basis search RESOLVED (closes the thread left in progress 2026-09-14 cont'd 9): rank 9 is real, and it costs MORE
User re-raised the linear-transformation idea (their own idea originally,
first logged 2026-09-14 cont'd 9). Checking the log revealed that thread was
never finished: a single annealing run had found **GF(2) rank 9** vs the
baseline 10, a multi-restart search was launched to push further, the entry
said "see next entry for the result" -- and no such entry was ever written.
The session went off into caterpillar/rectangle-XOR/QFT and never returned.
It was NOT in the dead list and NOT among the eight closed-out leads. Now
resolved.

**Setup.** `f(x,y)` with `z=(x,y)`, 12 bits. For invertible `A` over GF(2),
`g(z) = f(Az)`, and `diag(f) = L_A · diag(g) · L_A^-1` where `L_A` is a CNOT
network (~40 CNOTs for a 12x12 GF(2) matrix, so ~30-60 depth for both
networks -- cheap relative to a ~330-depth factor block). Annealed over
GL(12,2) via elementary row ops (which preserve invertibility by
construction), objective = GF(2) rank of the 64x64 matrix `M[y'][x']` in the
new basis. 8 restarts x 4000 steps, geometric cooling.
Script: `/tmp/.../scratchpad/basis_search.py`.

**Result 1 -- rank 9 confirmed, reproducible, and apparently the floor.**
5 of 8 restarts reached rank 9 (seeds 0,1,2,3,7); the other 3 stalled at 10.
Nothing ever went below 9. So the original single-run finding was real, not
a lucky draw, and 9 looks like this method's floor.

**Result 2 -- and it is STRICTLY WORSE, which settles it.** Measured what
actually drives cost (total AIG nodes across all factors' u_k/v_k
sub-functions, the same quantity the CP-SAT pebbler schedules):
- baseline (identity basis): rank 10, 20 sub-functions, **169 AIG nodes**;
  per-sub-function 4-15 nodes, average ~8.5.
- best rank-9 basis: 9 factors, 18 sub-functions, **247 AIG nodes** (+78,
  +46%); per-sub-function 7-25 nodes, average ~13.7.
Dropping one factor saves ~2 sub-functions (~17 nodes at baseline rates),
but every remaining sub-function got ~60% fatter. Net strongly negative.

**Mechanism, and why this generalizes.** The standard basis IS the good
basis, because the target's geometry is axis-aligned: conditions like
`x in [2,26]` are compact in standard binary encoding. Any A that mixes x
and y bits destroys that interval structure, leaving generic 6-bit functions
with bigger AIGs. **Rank counts FACTORS; cost lives in the SUB-FUNCTIONS.**
Minimizing rank is therefore the wrong objective -- it was a proxy, and this
measurement shows the proxy is anti-correlated with true cost here.
Secondary risk, unmeasured but real: several transformed factors have 22-25
node AIGs, well above the baseline max of 15, and the 2026-09-17 ancilla
sweep showed even 4-15 node AIGs need close to all 6 ancillas -- some of
these might not schedule at all, forcing ESOP fallback and making it worse
still. Didn't need to test that; the +46% node count already decides it.

Rough depth projection: 169 nodes -> ~3335 pre-BQSKit, so 247 scales to
~4900, plus CNOT overhead. ~46% worse than what we have.

**Closed.** Do not re-propose GF(2)-linear change of basis for rank
reduction. The one variant NOT tested: annealing directly on AIG node count
instead of rank (the correct objective). Not pursued -- each evaluation
needs ~18-20 `abc` syntheses (~0.5-1s/step vs ~2ms for rank), so ~1h per
restart, and the prior is now poor: identity gives 169, the annealed
rank-9 basis gives 247, and mixing demonstrably destroys the geometric
structure that makes the standard basis cheap. Consistent with the earlier
finding that 42 different FACTORIZATION bases all cost exactly 169 (a
different invariance, same conclusion: this basis is hard to beat).

**Also settled in the same exchange -- SVD / QR (user's question).** Real
SVD of the +/-1 sign matrix has rank exactly **11**, and the reason is
mundane: the image has exactly 11 distinct ROW PATTERNS (10 nonzero + the
all-zero row); real rank of the 0/1 image is 10, and `M = J - 2B` adds one
for the all-ones matrix. That is the SAME structure `rectangles_grouped`
already exploits (10 unique x-ranges), just seen in a linear-algebra basis
instead of a geometric one. Low-rank approximations get SIGNS right well
before they are exact (rank-5: 4092/4096 correct, only 4 wrong pixels;
rank-8: exact).
Why it does not yield a cheaper circuit: the additive SVD DOES factor into
composable unitaries (`diag(e^{-i*pi*M/2}) = prod_k diag(e^{-i(pi*sigma_k/2)
u_k(y) v_k(x)})` -- sums in an exponent become products), but each factor
then needs a real-valued QROM lookup on y, another on x, a real
MULTIPLICATION, and a rotation proportional to the product. That is the
lookup+arithmetic pattern measured at 4615-7073 depth for ONE instance
(2026-09-17 cont'd 3) with only integer tables and a comparison -- 8-11 of
them with real multiplies is an order of magnitude above 3194. GF(2) needs
only boolean AND + controlled-Z. Both capture the same rank-~10 structure;
boolean wins because a phase oracle is fundamentally a boolean object.
QR specifically does not map onto this problem at all: the target unitary is
already diagonal (the trivial endpoint of a Givens/QR decomposition), and
the 64x64 sign matrix's Q/R factors are not operations the oracle needs.
Worth keeping straight: rank 11 is the SCHMIDT rank of the state
`sum (-1)^f |x>|y>`, so that STATE is genuinely easy (~4 ancillas via
Schmidt decomposition). We need the OPERATOR, correct on all 4096 basis
inputs with ancillas restored. Low-rank structure of one output state does
not transfer to the cost of the unitary -- this is likely the root of the
recurring intuition that low rank "should" help here.

## 2026-09-18/22 — BQSKit `max_synthesis_size` tuning: real gains found; session paused by user decision
After the shared-distance disc predicate (below) confirmed hand-crafted
circuit structures were exhausted on both tracks, user pushed back hard on
"no vast cancellation exists" (fair pushback -- that finding was scoped to
Track A/ESOP specifically, not arithmetic representations). Rather than
invent another new circuit structure, tried pushing harder on a tool
already proven to work: BQSKit, previously used only at its DEFAULT
`max_synthesis_size=3` for a light final polish.

**Real, verified, repeatable win.** `max_synthesis_size` controls how large
a unitary block BQSKit will NUMERICALLY RESYNTHESIZE FROM SCRATCH (not just
peephole-clean) during its automatic partitioning -- bigger blocks find
non-obvious arrangements peephole passes structurally can't, at real
(roughly exponential per BQSKit's own docs) time cost.
- `=4`, `optimization_level=2`: ~420-600s wall-clock. Multiple runs:
  unseeded gave 3197/2469 and 3194/2467 (real non-determinism in the
  search); two EXPLICITLY SEEDED runs (seed=101, seed=202) both converged
  to exactly 3194/2467, confirming this is a stable local optimum, not a
  lucky draw. **New verified best: 3194/2467**, saved and confirmed via
  `verify.py` (n_wrong=0). Beats the prior 3230/2474 (`=3`) by ~1.1% depth.
- `=5`, `optimization_level=2`: 51,181s (14.2 HOURS). Verified correct,
  3182/2461 -- a further real improvement, but the circuit itself was
  never persisted (script only printed metrics; regenerating it costs
  another ~14h). Not banked -- user judged the reproduction cost not
  worth it for a further ~0.4% depth. Known-achievable, not shipped.
- `=6`: not attempted. Extrapolating the `=4`->`=5` scaling (~100x time for
  one step), `=6` would plausibly take on the order of weeks. Correctly
  not pursued.
- `optimization_level=3` at `=4` (same block size, different overall
  workflow depth): run for over 2 DAYS with no completion and no visible
  progress signal (BQSKit logs no per-block progress, only benign
  `linregress` sample-size warnings from its internal LEAP synthesis
  passes) -- killed, inconclusive. Unlike `=5`, this one never produced a
  result at all; don't assume it would have been better, there's no
  evidence either way.
- Applying the SAME `=4` tuning to Track B's `rectangles_grouped` circuit
  (a structurally different, arithmetic/comparator-based circuit, not
  AIG-based) made it WORSE (4008/2444 vs its existing default-settings
  3960/2436) -- confirms the size=4 win is not a free, universal transfer;
  it's specific to what BQSKit's partitioner finds in THIS circuit's
  structure, re-tune per circuit, don't assume.

Process hygiene note for future sessions: running multiple `bqskit.compile()`
calls in parallel on one machine FAILS (its runtime server binds a fixed
port, `Address already in use` / `Connection reset by peer` on all but one
concurrent caller) -- run BQSKit compiles sequentially, not in parallel,
unless a port override is set up first.

**Session paused here, by explicit user decision ("we give up here" /
"do not rerun anything"), 2026-09-22.** Final state: verified best
3194/2467 (`gf2_factor`+`gf2_cpsat_hybrid` v4 +BQSKit `max_synthesis_size=4`),
saved at `data/artifacts/lower/gf2_cpsat_hybrid_bqskit/`. Gap to leaderboard
(129-188 depth) remains large and unresolved -- eight substantial
circuit-construction leads were closed out this session (see 2026-09-16 and
2026-09-17 entries) with hard, specific evidence for each; none beat the
CP-SAT-scheduler-tuning + BQSKit-parameter-tuning combination that actually
moved the score. If resumed later, do not re-litigate anything logged as
closed without a genuinely new angle on its specific documented failure mode.

## 2026-09-17 (cont'd, 3) — shared-distance/lookup-table disc predicate: real math, hand-built in Qiskit after Classiq compiler bugs, still loses badly
User challenged the "no vast cancellation" framing directly: leaders hit
depth 129-188, so SOME vast simplification must exist. Correct pushback --
my prior conclusion only ruled out the ESOP/XOR-of-cubes representation
(Track A); it said nothing about arithmetic/comparator representations
(Track B), which is almost certainly what leaders actually use. Re-derived
fresh cx/depth-ratio evidence (see cont'd entry below) already pointed at
Track B needing the same parallelism leaders show, not Track A specifically.

**The math, verified first:** instead of testing 9 independent x-ranges for
disc2 (one per row-width, what `rectangles_grouped` does), compute a SINGLE
`w = LUT(y)` (a ~9-entry lookup: e=y-19, w=floor(sqrt(72-e^2))) then test
`|x-40|<=w` ONCE, with w now a genuinely quantum-derived threshold, not a
classical per-row constant. Verified exactly (0/4096 wrong) in plain Python
before any circuit work, for both discs.

**Classiq qmod attempt: two real, reproducible compiler bugs, not usage
mistakes.** `abs()` on a QNum expression throws an unrecoverable internal
server error ("Internal error ... error 122001"). Workaround (`max(y-cy,
cy-y)`) synthesizes but needs 23 qubits (avoidable -- traced to computing
BOTH signed subtractions as separate registers). Avoiding both via a
raw-signed-subtraction + range-guard reformulation (verified 0/4096 wrong
in Python first) hit a SECOND bug: "Control condition 'False' must be a
qubit... but is bool" -- confirmed via local trace-time instrumentation that
my Python-level condition construction is completely valid (every group
produces a real `SymbolicExpr`, `model created OK`); the failure is
server-side, during Classiq's own internal expansion (`disc_oracle_expanded
___0` in the trace), and persists identically whether using `|`/`&` or the
explicit `logical_or`/`logical_and` functions. Not a fixable usage error on
our side without visibility into Classiq's synthesis internals.

**Hand-built in Qiskit instead** (`/tmp/.../scratchpad/disc_full_qiskit.py`),
reusing this session's QFT-arithmetic machinery, extended with TWO new
verified primitives: `qft_reg_add` (Draper 2-register QFT adder -- first
attempt used the wrong angle formula, `2π/2^(j-k+1)`, a RELATIVE bit-shift;
correct formula is `2π/2^(n-j-k)`, depending on the ABSOLUTE register width
`n`, verified exhaustively at 3 size combinations after the fix) and
`lt_mixed_comparator` (compares a register against `const ± other_register`
in one QFT bracket -- first attempt wrongly wrapped `qft_reg_add`, which
already does its own internal QFT/IQFT, in ANOTHER external QFT/IQFT pair,
silently double-transforming; fixed by removing the redundant wrap, verified
exhaustively at 3 sizes incl. both actual disc use-case signs).

Built the full disc2 oracle end-to-end at 19 qubits (1 over budget, accepted
deliberately to validate the ARCHITECTURE before fighting the last qubit):
w-lookup, y-range validity guard, two register-mixed comparators for the
x-side, final phase via 2-controlled `mcp`, full LIFO uncompute. **Verified
exactly correct (n_wrong=0, n_leak=0) on the first complete end-to-end test**
against real disc2 geometry.

Cost, however, is decisively worse than what we have, and got WORSE not
better under the "obvious" optimization:
- Naive lookup (17 exact-value multi-controlled-X branches): 4615 depth /
  3118 cx, for ONE disc alone (whole-image current best is 3230/2474).
- "Optimized" lookup (9 range-grouped branches using this session's cheap,
  verified QFT range comparators instead of expensive 6-controlled-X):
  7073 depth / 6314 cx -- WORSE. Diagnosed why: each QFT comparator costs
  100-300 depth on its own (consistent with earlier findings this session),
  and the lookup needs ~9 of them in sequence, all contending for exclusive
  access to the same 6-qubit y-register. The bottleneck is register
  SERIALIZATION, not the specific gate type used to build each branch --
  swapping cheaper per-branch gates for a shallower comparator style doesn't
  help when the branch COUNT and the shared-register contention are the
  real cost driver.

**Conclusion:** the underlying math (shared distance + lookup + one
comparison) is real and correct, but realizing "compute once, compare once"
costs MORE in gates than "test N times directly" with every technique tried
this session (multi-controlled-X, QFT arithmetic). Distinct from, but
consistent with, the QFT-comparator finding (2026-09-17 cont'd) and the
nested-predicate finding: every genuinely different construction tried so
far pays a steep per-operation cost that swamps its structural elegance.
This is the third Track-B-side idea (after nested predicates) and the
fourth overall this session to verify correct and still lose badly.

## 2026-09-17 (cont'd, 2) — exact CP-SAT ESOP search: no improvement over heuristic EXORCISM, third independent method confirming no hidden cancellation
User's explicit "last attempt": push CP-SAT itself (not the AIG scheduler this
time -- ESOP/predicate minimization directly) as hard as possible on the
hypothesis that a smarter combination of XOR-cancelling predicates could
"vastly reduce" the problem below what's been found.

Worth being precise about what was and wasn't already ruled out. GF(2)
rank=10 is a PROVEN hard floor specifically for representations of the form
`XOR_k u_k(y) AND v_k(x)` -- and it's actually a hard floor for ANY ESOP
whatsoever: every cube (AND of literals over the 12 variables) is trivially
separable as `c_x(x) AND c_y(y)`, i.e. a rank-1 matrix over GF(2), so an ESOP
with T cubes gives T rank-1 matrices XOR-summing to the target, meaning
T >= rank always. What rank does NOT bound is CIRCUIT COST when u_k/v_k are
allowed to be genuinely complex (multi-cube) functions realized via AIG
sharing rather than literal cube expansion -- our actual 10-term GF2
decomposition expands to ~101 raw ESOP cubes if flattened, realized instead
as 169 total AIG nodes. So "is there a cost-cheaper combination of terms"
was genuinely still open, not closed by the rank argument alone.

Built an exact ESOP-minimization CP-SAT model
(`/tmp/.../scratchpad/cpsat_esop.py`): took `cover/esop_abc.py`'s own
heuristic output (EXORCISM via `abc`, 57 cubes / 507 literals -- verified
0/4096 wrong against the real target first) as a guaranteed-feasible seed,
enriched the candidate pool with every 1- and 2-literal generalization of
each base cube (2,614 candidates total), and modeled selection as boolean
variables with `AddBoolXOr` parity constraints (one per truth-table entry,
target=1 needs odd parity among covering cubes, target=0 needs even --
encoded via an extra always-true literal) and objective = total literal
count. Seeded the solver with the 57-cube baseline as a hint.

Ran 480s wall-clock, 8 parallel workers: 243,930 LP relaxations explored
across subsolvers (core/default_lp/max_lp/quick_restart/reduced_costs/LNS
variants), real, substantial search. **Result: FEASIBLE at 507 literals --
identical to the seeded baseline, zero improvement found.** Did not reach
OPTIMAL (no matching lower bound proven), so this isn't a mathematical
proof, but it's the third independent method this session pointing the same
direction: rank-10 is a hard floor (proof), 42 different valid bases all
cost identically (exhaustive-among-alternatives search), and now a genuinely
general (non-bilinear-restricted) exact-solver search over a rich enriched
cube space also can't beat the heuristic. The function has real, deep
complexity -- not a disguised-simple one waiting for the right decomposition.

## 2026-09-17 — QFT-comparator dead end (real but insufficient); ancilla-fanout dead end (confirmed, decisive); fresh leaderboard analysis
Two more threads closed out, no change to the verified best (3230/2474).

**QFT-based comparator: real algorithmic wins, still loses on absolute cost.**
User's own suggestion (interference-based/QFT techniques) prompted testing
Yuan-Wang-Wang-Chen-Dou-Wu-Guo's 1-ancilla QFT comparator (arXiv 2305.09106)
as a possible replacement for ripple's comparator inside the (already
rectangle-XOR-shaped) decomposition. Built incrementally in
`/tmp/.../scratchpad/qft_comparator{,2,3}.py` -> `qft_rectangle{,2,3,4}.py`:
- Single comparator (n=6, `QFTGate`-based, Qiskit's library not hand-rolled
  after a hand-rolled version failed for a!=0): verified OK across 15
  constants incl. real thresholds. 149 depth, 138 cx, 1 ancilla.
- Full rectangle, x-side and y-side on DISJOINT ancilla (3 each, 6 total,
  full 18-qubit budget): verified exact against real rect1 geometry
  (n_wrong=0, n_leak=0). First version: 453 depth/765 cx -- confirmed the
  transpiler genuinely captures x||y concurrency (409+409 serial-equivalent
  collapsing to 453, not ~818), a real, measured result, not assumed.
- Algebraic improvement: `range_flag_toggle_fast` in `qft_rectangle4.py`
  tests `x>=lo` then continues DIRECTLY on the shifted register (testing
  `(x-lo)<width`) instead of restoring x and re-deriving a fresh offset for
  an independent second comparator -- cuts QFT-op count exactly 2x (64->32,
  confirmed via raw gate counts). Verified correct across 8 range cases incl.
  edges (lo=hi=0, lo=hi=63, full 0-63). Result: 353 depth / 625 cx per
  rectangle, down from 453/765.
- Still ~35% worse than ripple's established 261/rectangle floor. Diagnosed
  as structural, not a tuning gap: every threshold test needs a QFT+IQFT
  round trip to extract a borrow bit into a controllable ancilla (can't read
  a computational-basis bit while still in Fourier domain) -- O(n^2)
  phase-gate cost per test vs ripple's O(n). A range test needs 2 such tests,
  4 QFT-ops per compute pass, 8 per compute+uncompute toggle -- already near
  this construction's floor.
- Even a hypothetical win here wouldn't reach the pipeline that's actually
  winning: this only ever helps the rectangle-XOR decomposition, already
  dead (2026-09-16) for unrelated reasons (discs need ~30+ terms each). QFT
  arithmetic has no natural construction for a generic 6-bit truth table
  (what `gf2_cpsat_hybrid`'s factors actually are), only constant-comparisons.
  Logged dead; see CLAUDE.md Live Work.

**Ancilla fanout: confirmed dead, decisively, not just "didn't help."**
Fresh top-10 leaderboard snapshot (2026-09-15/16) showed a clean 5-5 split by
cx/depth ratio (~2.0-2.4 cluster: Gabriele 166/348, Vyom 175/343, Satwik
175/352, Jayachandiran 181/426, Daksh 188/451; ~4.1-4.8 cluster: Boopathi
129/614, Mateusz 137/561, SOURABH 170/802, Hyun-Jung 178/782, Monit 185/854),
nothing in between -- strong evidence of two distinct circuit families among
leaders. Our own ratio (2474/3230=0.766) sits BELOW both clusters: our
schedule averages under 1 CX per depth-layer, vs leaders' 2-5x that. This
re-surfaced and quantified an earlier-session observation (0.61 vs a prior
leader snapshot's 3.92) with fresh numbers, and motivated re-testing ancilla
fanout directly rather than relying on the earlier session's memory of why it
failed.

Ran a direct CP-SAT feasibility sweep (`/tmp/.../scratchpad/test_uv_split.py`)
against the REAL current factor data (`cover.gf2_factor` on the real logo,
10 factors, u_i/v_i AIGs of 4-15 nodes each, 20 sub-functions total): tried
scheduling EVERY one at ancillas=3, horizon=200, 25s time limit each. Result:
**100% infeasible, all 20, every single one, all fast fails (0.4-2.5s wall,
nowhere near the 25s cap)**. This directly kills any concurrency scheme
needing two disjoint 3-ancilla (or smaller) pools running simultaneously --
both within-factor (u_i computed concurrently with v_i, each on its own
data-register + disjoint ancilla, mirroring the QFT rectangle's confirmed
x||y concurrency) and cross-factor pairing (two different factors' whole
computations concurrent). Also spot-checked ancillas=4 for each side
independently: feasible for about a third of the 20 (all took ~25s, i.e.
right at the cap -- hard to find, not fast to confirm), but a real concurrent
build needs two DISJOINT pools summing to <=6, and no factor had both u_i AND
v_i feasible at a combination that sums to <=6 (4+4=8 is over budget; a 4+2
split needs the weaker side feasible at just 2 ancilla, and the ancilla=3
result makes that very unlikely, not tested further).

Root cause: these AIGs generically need close to the full 5-6 ancilla to be
pebbled AT ALL (consistent with the existing pipeline's own u/v-at-
ancillas-1-or-6 pattern) -- there's no slack to share concurrently,
regardless of scheduling cleverness. A fully joint/interleaved CP-SAT model
(one shared schedule across all 20 sub-functions instead of a fixed spatial
split) is the only theoretical escape left, but the UNIFORMITY and SPEED of
the ancilla=3 failures suggests these schedules run near-peak ancilla usage
for most of their length rather than peaky-with-slack -- inference, not
directly tested, logged as a strong prior against that much extra
engineering paying off. `lower/fanout.py` moved from "unimplemented,
promising" to confirmed dead in CLAUDE.md.

## 2026-09-16 — caterpillar dead end; rectangle-XOR dead end; carry-lookahead dead end; new verified best 3230/2474 from tuning the CP-SAT scheduler itself
Continuing from cont'd-11's caterpillar research and 3913/2677 best. Four
substantial threads this session, three negative (with hard evidence, not
just "didn't pan out") and one that delivered a real, compounding win.

**caterpillar/tweedledum: matches our own CP-SAT, doesn't beat it.** Built
the real academic tool from source (`gmeuli/caterpillar`, bundles
`mockturtle`/`tweedledum` as submodules, sidesteps tweedledum's broken PyPI
packaging). Its `bsat_pebble_solver` (SAT-based, exact) found a schedule for
one of our real per-factor AIGs in 5ms vs our CP-SAT's up to 45s -- but the
schedule itself was the same SIZE (43 moves vs our ~39), and it emits literal
Toffolis (6 CX) not RCCX (3 CX), so its raw output is worse than ours despite
the faster search. Its `xag_low_depth_mapping_strategy` (the strategy tied to
real "parallel copies" ancilla-fanout support -- the one thing on our own
Live-Work list we'd never built) turned out to need ~1 dedicated ancilla PER
AIG NODE (12-13 for our 12-13-node factors) -- an unconstrained-ancilla
regime incompatible with our 6-ancilla cap, not a "spend a few extra"
middle ground. Confirmed via a real 3-bit-sorter smoke test plus direct
testing on our own factor data.

**Rectangle-XOR decomposition: real structure, wrong economics.** The user's
own Classiq experiment (a hand-built circuit using `arith_eng` GE/LE
comparators + `r1tof` relative-phase Toffolis) was NOT exact (489/4096
wrong) but wasn't noise either: isolating each of its 4 `mark_rect` gates
showed each is a genuinely clean axis-aligned rectangle, and coordinate-
descent optimization of their 16 boundary parameters converged rect1 to
EXACTLY our true geometry (`[2,26,29,53]`, pixel-perfect) -- strong evidence
the whole image factors as XOR of a small number of overlapping rectangles.
Residual after fixing rect1/rect2 exact = precisely the 2 discs (362px),
confirmed via connected-component analysis with zero stray pixels elsewhere.
Measured the real per-rectangle cost from the `r1tof` construction directly:
**261 depth for one full 4-condition rectangle** (GE_x+LE_x+GE_y+LE_y+
compose+uncompute), which set a hard floor. Launched a multi-day CP-SAT
minimum-XOR-rectangle-cover search for the 2 discs (still running,
`/tmp/min_xor_rect_cover.py`, disc2 at 31 rectangles as of this writing) --
but even a good outcome doesn't help: measured the ACTUAL cost of building
disc2's then-current 33-rectangle solution via x-range-grouped comparators
(same sharing trick as `rectangles_grouped`) at **2910 depth / 2275 CX for
disc2 ALONE** -- more than half our entire current best, before rect1/rect2/
disc1 are even added. The XOR-decomposition idea is real; this image's
discs just need too many terms to represent that way, sharing or not.

**Carry-lookahead (parallel-prefix) comparator: real 69-depth win, unusable.**
Researched why the leaderboard might hit ~140-190 depth when our best
comparator technique (ripple, `r1tof`-style) costs 261 for one rectangle
alone. Found the real, citable, well-established technique: Draper-Kutin-
Rains-Svore's logarithmic-depth quantum carry-lookahead adder (arXiv
quant-ph/0406142) -- O(log n) depth via an associative generate/propagate
merge over doubling intervals, O(n) ancilla. Adapted it for OUR simpler case
(comparison against a classical constant, not two variable registers --
collapses the leaf-level propagate/generate values to free wire references,
no gates). Hand-built and EXHAUSTIVELY VERIFIED (all 64 constants x all 64
inputs, later independently re-verified via a from-scratch AigNode
translation) a working version: **69 depth / 78 CX for one exact threshold
comparator**, fitting exactly 6 ancilla. But it doesn't compose: the tree's
internal state (D, C, the final g/p pair) has to stay live the ENTIRE time
between compute and uncompute -- it never settles to holding just the
result the way `build_from_schedule`/`uncompute_from_schedule` does for the
GF(2) factors. A rectangle needs 2+ such comparators alive together (to AND
GE and LE); there's no ancilla left for a second one. Confirmed via
independent CP-SAT search on the tree's own AigNode translation: infeasible,
FAST (not slow-search) failures at ancillas=2,3,4,5 for essentially every
non-degenerate threshold constant -- this is the tree's real dependency
structure, not a scheduling artifact. A genuinely different (lower-ancilla-
floor) graph might fix this; not attempted.

**What actually worked: tuning the CP-SAT scheduler's own resource
allocation, three times, each verified and shipped before the next.**
1. Wired in a fix that had been found earlier but never applied: 3 factors
   (6/7/8's v_i) are infeasible at ancillas-1 ONLY because u_i (computed
   first by convention) permanently holds 1 of the 6 ancilla while v_i
   tries to build -- not because v_i's own AIG is hard. Confirmed those
   same v_i schedule fine given the FULL 6-ancilla budget. Swapped order
   for exactly those 3 (v_i first with all 6, u_i second with the
   remaining 5) -- eliminates the ESOP-cube fallback entirely, 20/20
   factors now go through CP-SAT+RCCX. Verified: **3529/2585** (pre-
   BQSKit, was 4020/2704), **3418/2577** post-BQSKit (was 3913/2677).
2. Noticed u_i is ALWAYS computed first (by default) with nothing else
   competing for ancilla, yet was capped at ancillas-1 (5) instead of the
   full 6 for no real reason. Since CP-SAT's objective directly minimizes
   move count, more budget can only find an equal-or-cheaper schedule,
   never worse -- re-solved all 10 u_k at ancillas=6 under a new cache
   tag (`"u6"`), confirmed real per-factor drops (e.g. factor 5: 78->70
   moves). Verified: **3380/2504** pre-BQSKit, **3279/2488** post-BQSKit.
3. Generalized: rather than assuming u-first is always right, actually
   solved v-first-at-6 for the other 7 factors too and compared TOTAL
   move count against the existing u-first total. Mixed results (1 factor
   improved, 3 ties, 3 u-first-still-better) -- only factor 0 flipped
   (52 vs 56 moves) -- but wired in the general "pick whichever ordering
   is cheaper, per factor" rule anyway since the comparison data was
   already computed and the code delta was small. Verified: **3335/2490**
   pre-BQSKit, **3230/2474** post-BQSKit -- current best, ~17.4% depth
   below this session's 3913 starting point, entirely from resource-
   allocation tuning of a scheduler that was already correct, not from
   any new circuit-construction idea.

Net read: three genuinely different architectural ideas (an established
academic tool, a geometric decomposition validated down to exact-pixel
precision, a textbook asymptotically-superior comparator) all failed to
beat what we already had, for three DIFFERENT concrete reasons -- yet
methodically re-examining the resource allocation of the technique we
ALREADY trust (CP-SAT pebbling) bought a real, compounding 17% with no new
architecture at all. The gap to the leaderboard (137-190) is still large
(~17-23x on depth) and none of this session's research explains how that's
closed; logged here so the SAME three dead ends aren't re-attempted without
a genuinely new angle on their specific failure mode.

## 2026-09-14 (cont'd, 11) — CP-SAT scheduler replaces hand-rolled Belady; new verified best 3913/2677; caterpillar/tweedledum research started
**Doc hygiene note**: this entry, and the CLAUDE.md standings/live-work update
alongside it, were written in a later session picking up after a context
compaction. The code and artifacts below were already on disk (verified by
timestamp and by re-reading each `metrics.json`) but neither this file nor
CLAUDE.md had been updated to match — anyone (or any session) reading only
the docs between then and now was seeing a stale picture (best=4316/2630,
live work = "fix gf2_aig_hybrid"). If you're a future session and something
about the docs vs. the code doesn't add up, check `git log`/mtimes over
trusting either source blindly — that's exactly what happened here.

**BLIF XOR-parsing bug (real correctness bug, not a scheduling issue).**
`aig_synth.parse_blif` only ever read the first row after a `.names`
directive. ABC emits a genuine 2-row SOP block for XOR/XNOR gates (e.g.
`01 1` + `10 1`); reading only the first row silently dropped half the truth
table for every XOR node ABC happened to synthesize. Found via a localized
64/4096-wrong-state pattern (all sharing `y in {38,39}`), confirmed by
direct BLIF inspection. Fixed by extending `AigNode` with `is_xor: bool` and
having `parse_blif` read all rows of a block, classifying the 2-row
`{"01","10"}` / `{"00","11"}` patterns as XOR/XNOR (anything else unhandled
raises `NotImplementedError` rather than silently mis-parsing). XOR nodes
get plain CNOTs, not RCCX — verified by hand that `[CX(a,t);CX(b,t);X(t)]`
applied twice restores `t=0` exactly, so XOR has none of RCCX's
phase-fragility/ordering constraints. This fix corrected the unlimited-
ancilla AIG ceiling from the 1679/2616 reported in (cont'd, 10) down to
**853/1307**, verified exact (0/4096 wrong) — same graph, previously
mis-costed because some AND-shaped emulation of XOR was being emitted
instead of 2 CNOTs.

**`gf2_aig_hybrid.py` (per-factor Belady-scheduler hybrid): built, found
broken, abandoned rather than debugged further.** Pivoted from
"schedule the whole 218-node graph at once" (dead per cont'd-10) to
per-factor: GF(2) rank-10 decomposition gives 20 independent 6-bit
sub-functions (`u_k(y)`, `v_k(x)`, k=0..9), each small enough (~10-30 AIG
nodes) that a 5-6 qubit scratch pool is plausible. Routed through the
existing (already-verified-for-standalone-use) `_BeladyScheduler`/
`_pebble_build`/`_pebble_uncompute` machinery. Found and fixed one real bug
this way (a custom refcounted allocator that freed a qubit on refcount-zero
*without* uncomputing it first — silently corrupting reused qubits) by
routing everything through the correct pebble_build/uncompute pair instead.
Then hit a second bug specific to chaining two per-factor builds on a
*non-contiguous* shared scratch pool: excluding only the `u_i` result qubit
(not all of `u_i`'s live qubits) from the pool handed to `v_i`'s build let
`v_i` corrupt `u_i`'s still-live intermediates. Reproduced in isolation
(factor 9, exact scratch assignment `[12,13,14,16,17]` — note the missing
`15`). This was the *11th* distinct scheduler bug found across this whole
AIG effort (see cont'd-10 for the first ten). Rather than debug an 11th
heuristic-scheduler bug, the file was marked `NOT VERIFIED CORRECT -- DO NOT
USE FOR A SUBMISSION` in its own docstring and kept only for reference. The
underlying insight (per-factor decomposition makes ancilla-constrained
scheduling tractable) was correct; the hand-rolled Belady scheduler was not
the right tool to exploit it.

**Pivot: CP-SAT (OR-Tools) as a correctness-by-construction scheduler,
replacing the hand-rolled heuristic entirely.** New module
`src/qoracle/pebble_cpsat.py`. Model: boolean `P[node][t]` ("node is pebbled
at step t"), ancilla-budget constraint, at-most-one-move-per-step,
dependency constraints (can't pebble a node before its fanins), an
existential "output isolated at some step" constraint, `Minimize(sum of all
pebble changes)`. Two real modeling bugs on the way to a working version:
(1) the first isolation formulation required the output to be isolated *at
the exact instant of its own placement* — directly contradicts needing both
fanins live at that same step, so every one of the 20 factors came back
UNSAT in under 0.1s (the suspiciously fast infeasibility, not a slow search,
is what gave this away as a modeling bug rather than genuine infeasibility).
Fixed with a proper existential formulation over reified booleans (isolated
at SOME later timestep). (2) `build_from_schedule` originally stopped
realizing gates at the output's *first* placement rather than its isolated
point, which let `live_qubits` include more than just the result qubit —
the exact same non-contiguous-pool failure mode as `gf2_aig_hybrid`,
recurring even with an exact solver, because the bug was in the *circuit
realization* step, not the scheduling step. Fixed by adding the isolation
constraint to the model itself (see above) and changing the stop condition
to `output in live and len(live) == 1`.

**Result: `src/qoracle/lower/gf2_cpsat_hybrid.py`, verified end-to-end.**
17/20 GF(2) factors scheduled via CP-SAT at ancillas=5 (1 of the 6 reserved
for the other side's result); the remaining 3 (factors 6/7/8's `v_i`) are
genuinely infeasible at that budget (fast ~1-2s UNSAT, not a timeout) and
fall back to the ESOP-cube lowering for just that sub-function. Full
pipeline: **depth=4020, cx=2704**, verify.py exact (0/4096 wrong) —
saved at `data/artifacts/lower/gf2_cpsat_hybrid/`. Post-processed with
BQSKit (`optimization_level=2, synthesis_epsilon=1e-12` — the default
`1e-8` leaves ~1.16e-06 residual leaked amplitude, which fails this
competition's strict 1e-10 exactness bar) to **depth=3913, cx=2677**,
re-verified exact — saved at `data/artifacts/lower/gf2_cpsat_hybrid_bqskit/`.
**This is the current best, beating the session-start baseline
(4316/2630, `classiq_native.rectangles_grouped`) by ~9% depth.** (For
reference, plain BQSKit applied directly to that original baseline, with no
CP-SAT/AIG work at all, only gets to 3960/2436 —
`data/artifacts/classiq_native/rectangles_grouped_bqskit/` — worse on depth
than the CP-SAT route despite a lower cx; an earlier, looser-settings BQSKit
attempt against the same baseline is the transient `/tmp/bqskit_run_l2_tight.log`,
4155/2559, superseded one save later by the 3960/2436 artifact.)

Also established along the way: Classiq's `Preferences(optimization_level=
...)` doesn't move this particular qmod model (already at its synthesis
optimum) — a distinct knob from `Constraints(optimization_parameter=...)`,
don't conflate them. And `sym.abs()` on a `QNum` expression triggers a
server-side `ClassiqAPIError` (122001) even for a bare, unused assignment —
reproduced under several phrasings, concluded to be a genuine SDK
limitation, not a rephrasing problem; closes off a disc-distance-transform
idea via qmod specifically (the geometric insight itself — discs' rows are
symmetric ranges — is still valid via hand-rolled arithmetic if ever
revisited).

**Still ~20-25x off the leaderboard's depth range (137-190)** despite all of
the above. User's reaction: not satisfied with a 9% win at that gap, asked
for deep research into academic tooling/papers that exploit this exact
problem shape rather than more incremental tuning.

**Research finding: this is a known, named academic problem with existing
tooling.** "Reversible pebbling" for ancilla-constrained reversible circuit
synthesis is literally the subject of published work by Meuli/Soeken/De
Micheli (the same group behind `mockturtle`/`tweedledum`), implemented in
`gmeuli/caterpillar` (header-only C++17, MIT-licensed, bundles `mockturtle`
and `tweedledum` as git submodules — sidesteps `tweedledum`'s broken PyPI
packaging, which failed to build standalone via pip with a
`pyproject.toml` "must contain ['version']" error across two versions, with
and without build isolation). Its `pebbling_mapping_strategy` +
`bsat_pebble_solver<Ntk>` is a genuine SAT-based EXACT solver for the same
problem `pebble_cpsat.py` solves heuristically-but-correctly with CP-SAT:
given a `pebble_limit`, it incrementally searches over schedule length
(`add_step()` + re-solve, `search_timeout` default 30s per pebble-limit
attempt) for a feasible compute/uncompute schedule. Read
`caterpillar/synthesis/lhrs.hpp` in full: critically, it also has a
DIFFERENT, more advanced strategy family (`compute_level_with_copies` /
`uncompute_level`, driving `xag_mapping_strategy` and friends, not yet
read in detail) that spends *extra* ancilla deliberately to copy shared
fanin values so multiple same-level AIG nodes can be computed **in
parallel** instead of serially — i.e. real support for exactly the
"ancilla fanout so independent cubes run concurrently" idea that's been on
our own Live-Work list, unimplemented, this whole time. Its plain
`compute_and` emits full Toffolis (`gate::mcx`, 2 controls -> literal `ccx`
in the QASM writer) rather than our RCCX — 2x the CX of our approach per
AND node in isolation — but the *schedule/structure* it finds is the
actually-uncertain, actually-interesting part; gate-level cost can be
swapped for our own RCCX afterward if the schedule itself is better than
what we get on our own.

Built and validated the C++ toolchain end-to-end before writing any driver
against our real problem: `git clone --recursive gmeuli/caterpillar` into
`/tmp/caterpillar` (submodules `mockturtle`, `tweedledum`, `kitty`,
`lorina`, `percy` (+ bundled `abcsat`, a real compiled SAT-solver library
percy links against), `bill`, `fmt`, `json`, `rang`, `sparsepp`, `ez`,
`easy` all present and header-only except abcsat). Configured with
`-DCATERPILLAR_TEST=OFF -DCATERPILLAR_EXAMPLES=ON` (skip the catch2 test
suite, build only files dropped into `examples/`) — this built clean
(warnings only, from `sparsepp`'s use of deprecated `std::iterator`) and
linked in a few minutes, confirming CMake correctly wires up every
submodule's include paths and the abcsat native build. Ran the test
suite's own 3-bit-sorter example (6-gate AIG, `pebble_limit=3`, no Z3):
timed out at the 30s default `search_timeout` with no solution found for
that (small!) graph — inconclusive on its own (could be genuine
infeasibility at 3 pebbles for that particular graph, or just a slow SAT
search), not yet a verdict on the tool. **Next step, in progress when this
entry was written**: code-generate a C++ `xag_network` construction
(`create_pi`/`create_and`/`create_xor`/`!signal` for polarity, 1:1 from our
already-parsed, already-verified `AigNode` graph — `fanins`, `polarity`,
`is_xor`, `invert_output` — rather than round-tripping through BLIF/lorina)
for one of our REAL per-factor sub-AIGs (one we already have a known-good
CP-SAT schedule for, from the 17/20 that succeeded), and run caterpillar's
`bsat_pebble_solver` on it at the same ancilla budget our CP-SAT used, as a
direct apples-to-apples comparison before considering the full 218-node
graph or the level-parallel strategies.

## 2026-09-14 (cont'd, 10) — RCCX/AIG deep-dive: real 2x ceiling found, ancilla-constrained scheduling stopped after 11 bugs
User raised the stakes explicitly: this is winner-take-all ($20k), not a
context where "meaningfully better than baseline" has any value short of
being competitive. Recalibrated risk tolerance accordingly and pushed much
harder into the AIG/pebbling direction than the earlier (correct, for a
normal-stakes context) decision to deprioritize it.

**Real, verified result: relative-phase Toffoli (RCCX / Margolus gate,
3 CX instead of 6) roughly HALVES the AIG's cost.** Every AIG node is a
plain 2-input AND -- exactly RCCX's use case. Confirmed safe via exhaustive
Operator comparison for the actual patterns used (compute/use/uncompute,
multi-term XOR-accumulate, chained AND, fan-out>1) -- PROVIDED (a) uncompute
happens in strict LIFO order (same-order reapplication is exact-verified
BROKEN, Operator diff=2.0, not a rounding issue), and (b) a node's own
`invert_output` is folded into consumers' polarity rather than applied as a
physical post-gate X (physical X breaks the cancellation -- confirmed
3725/4096 wrong before this fix). With both fixes: unlimited-ancilla AIG
ceiling improved from 1679/2616 to **853/1307** -- exact, verified against
the full 4096-state truth table. Also applied to `gf2_ancilla`/
`rect_ancilla`'s existing 2-literal cubes (the only case it currently
covers): small but real, fully verified improvement (~1%) -- most of their
cubes are 3-6 literals and untouched by this specific fix.

**Ancilla-constrained scheduling (fitting the AIG into 6 real ancilla):
genuinely NP-hard-flavored, confirmed empirically, not just asserted from
literature.** Built and abandoned, in order:
  1. Recursive demand-driven scheduler with an accumulated "protect list"
     (grows with recursion depth) -- deadlocks around 6-10 ancillas
     ("nothing evictable").
  2. Belady's algorithm (evict furthest-next-use, from a FIXED processing
     order) instead -- eliminates the protect-list, but required finding
     and fixing, in sequence: (a) target_pos must be a single GLOBAL clock
     advanced by the driving loop, not threaded per-call (threading it gave
     every intermediate node's Belady distance measured against the wrong
     reference point); (b) proactive release-on-last-use is logically
     correct but causes EXPONENTIAL recompute-for-uncompute blowup on
     deep/shared graphs (2000+ ensure() calls by clock=34 with zero
     eviction pressure) -- removed entirely, rely on purely reactive
     eviction; (c) `_teardown` must pop from `live` BEFORE its own fanins'
     `ensure()` calls, not after -- otherwise a nested eviction can
     re-select the node whose teardown is already in progress (confirmed
     root cause of runaway recursion); (d) sibling protection (the ORIGINAL
     protect-list idea) turns out to still be NECESSARY, just LOCAL (only
     the current node's own 2 fanins, not the full ancestor chain) --
     without it, securing one fanin can evict the other, freshly-secured
     one, since Belady's next-use metric has no way to know a
     just-recomputed value is needed imminently.
  3. With all of (a)-(d) fixed, the scheduler is CORRECT when it succeeds,
     but its actual resource requirement is much higher than the
     theoretical peak_width() and NON-MONOTONIC in ancilla count: works at
     ancillas=218, FAILS at ancillas=100, works again at 218. This is the
     empirical signature of genuine combinatorial (NP-hard) difficulty --
     recomputation cascades compound, they don't scale down smoothly with
     more resources.

**Pivot: apply AIG+RCCX to the small 6-variable u_i(y)/v_i(x) GF(2)-rank-10
factors instead of the full 218-node 12-variable graph.** Measured
peak_width across all 20 small AIGs (10 factors x u,v): 3-5, comfortably
small. Built `lower/gf2_aig_hybrid.py`: AIG+RCCX (reusing the SAME,
by-then-debugged Belady scheduler) where a factor's sub-function fits in
5 scratch qubits, ESOP-cube fallback (`_emit_indicator`) otherwise --
15/20 fit. Individually, ALL 20 sub-functions verified EXACTLY correct in
isolation (0 wrong, 0 leak each). **Integrated (10 factors, sequential,
sharing one 6-qubit ancilla pool): BROKEN.** Factor 9 (both halves
AIG-eligible) produces a leaked, non-+-1 phase (1j -- a literal half-applied
RCCX relative phase) specifically when its v_i build uses a
NON-CONTIGUOUS scratch pool (excludes wherever u_i's result landed, e.g.
[12,13,14,16,17] with 15 missing) -- reproduced in isolation with the exact
qubit assignment, so it's a real scheduler bug triggered by a "hole" in the
available-qubit list, not a sequential-history artifact. Root cause NOT
found. This is the 11th distinct bug in this scheduler-design effort.

**Stopped here, deliberately, given the stakes.** A wrong circuit is
disqualification, not a lower score; the bug-discovery rate (11 in one
session, several only surfacing after the previous one was fixed and
verified) means "one more fix" cannot be trusted as a stopping point without
another full exhaustive-verification pass, and this pattern shows no sign of
convergence. `lower/gf2_aig_hybrid.py` is marked NOT VERIFIED / DO NOT USE in
its own docstring. **`rectangles_grouped` (4316/2630, Track B) remains the
verified submission candidate, untouched throughout this entire effort.**

**What a future session should do with this:** the 853/1307 unlimited-
ancilla ceiling and the 15/20-factors-fit-at-scratch-5 result are both real
and worth building on. The `_BeladyScheduler` in `aig_synth.py` is correct
for a SINGLE, standalone small AIG with a clean contiguous scratch list
(verified exhaustively) -- the remaining bug is specifically about REUSING
it across multiple sequential builds sharing one pool with gaps in it.
Suspect areas: `_pebble_build`/`_pebble_uncompute`'s interaction with a
`scratch` list that isn't `range(a,b)`, or state in `_BeladyScheduler` that
implicitly assumes qubit values correlate with allocation order. Before
trusting any fix, re-run the exact repro in this entry (factor 9 of
`gf2_factor` on the real logo, u_scratch=[12,13,14,15,16],
v_pool=[12,13,14,16,17], input x0=16) and confirm it passes, THEN re-run the
full 4096-state exhaustive check on the integrated 10-factor circuit before
considering it a candidate.

## 2026-09-14 (cont'd, 9) — PyZX full_reduce: tried, negative; change-of-basis search: promising, ongoing
Re-read the full baseline notebook cell-by-cell on user request (previously
only skimmed/summarized). Confirms: exact shape formulas match our
`io.logo_pixel` and the user's independently-derived boundaries exactly; the
notebook's own "Optimization Directions" hints (repartition-for-sharing,
boolean decomposition, comparison-sharing, symmetry, ancilla/recompute
tradeoff) have ALL been explored this session, with the ancilla/recompute
one (AIG pebbling) being the one that hit a real wall rather than a clean
win. Also clarified the actual root goal for future reference: it's circuit
DEPTH (cx tiebreak), not predicate/term count -- the tell is that the
leader's cx is only ~4.7x ours while their depth is ~8x ours (was ~30x pre-
session), meaning parallelism-per-depth-layer, not raw logical complexity,
is where most of the remaining gap lives. Every real win this session
(`gf2_ancilla`, `rectangles_grouped`) came from trading gate count for
parallelism, never from fewer terms alone.

**PyZX (`full_reduce` + `extract_circuit`) on `rectangles_grouped`'s QASM:**
loaded correctly (2630 CX confirmed), ran full_reduce (140s) + extraction
(25s), re-transpiled the result through our own Qiskit opt_level=3 pipeline.
Verified CORRECT (0/4096 wrong) but WORSE: depth 6962 / cx 5641 vs baseline
4316/2630. Root cause: PyZX's extraction algorithm targets T-count reduction
in Clifford+T circuits; ours is u3/cx (continuous rotations, no discrete
T-gates to save), so extraction overhead dominates with nothing to offset
it. **Confirmed dead: PyZX full_reduce on our circuit representation, via
this direct QASM-in/QASM-out pipeline.** (Not ruling out ZX-calculus ideas
entirely -- just this specific default pipeline on this specific gate set.)

**Change-of-basis search (user's idea, genuinely new, not covered by the
already-dead "variable permutation" finding):** does a GF(2)-LINEAR mix of
the 12 input bits (not just permutation/complementation -- a vastly larger
transformation group) reduce the function's structural complexity? Random
search (300-500 trials, both small near-identity and wide random invertible
matrices) found nothing below rank 10. Simulated-annealing hill-climb (2000
steps, single run) found **rank 9** -- a real, verified improvement over the
baseline rank-10 structure. Multi-restart annealing search (8 restarts x
4000 steps) launched to see how far this goes before deciding whether the
resulting rank reduction (if any) is worth the ~80-100 CX overhead of the
CNOT-network change-of-basis (apply L, phase in new basis, apply L^-1).
Status: IN PROGRESS as of this entry -- see next entry for the result.

## 2026-09-14 (cont'd, 8) — true-primitives split+merge: built for real, still loses (definitive)
User asked to actually test split+merge empirically rather than trust the
rank argument alone. Built it: ESOP-minimized each of the 4 true primitives
(rect1: 20 cubes/152 lits, rect2: 8/66, disc_small: 17/160, disc_big:
21/198) over all 12 variables, computed each into its own ancilla, OR'd them
together via a proper reversible OR-tree (3x `CCX;CX;CX` triples, exactly
invertible), applied Z, uncomputed everything in reverse -- correct
inclusion-exclusion, not a naive concatenation (these primitives genuinely
overlap by 10 pixels). Used UNLIMITED scratch ancilla (7 extra, width=19)
specifically to find the best-case ceiling before considering whether a
real ancilla-constrained version is worth building (same diagnostic
discipline as the AIG unlimited-ancilla check). Verified exactly correct via
a from-scratch classical simulator (0/4096 wrong, 0 leak). Result: **depth
10812 / cx 7560** -- worse than baseline (4316/2630) by 2.5x/2.9x, using
MORE qubits than budget even in the unconstrained case.
**Conclusively closes image-splitting.** Three different partitions now
empirically tested (disc1/rest, 4 y-band regions, true geometric
primitives with real overlap-correct merge) -- all lose, all for the same
underlying reason (global minimization beats any partition). Do not
attempt a 4th partition or a tighter-ancilla version of this specific
build; the unconstrained ceiling already loses badly enough that a
constrained version can only be worse.

## 2026-09-14 (cont'd, 7) — user independently re-derived the true 4 primitives; rank confirms splitting still loses
User visually decomposed the logo into 4 shapes by eye (bounding boxes) --
turned out to match `io.logo_pixel`'s literal source EXACTLY: rect1
(2<=x<=26, 29<=y<=53), rect2 (26<=x<=49, 39<=y<=43), disc_small
(center=(55,41), r=sqrt(42)), disc_big (center=(40,19), r=sqrt(72))). This is
precisely the decomposition `classiq_native/primitives.py` already used
(blocked on ~43 qubits for the quadratic arithmetic, see CLAUDE.md) -- but
that attempt never got as far as comparing GF(2) ranks. Did that now:
  rect1=1, rect2=1 (both trivially separable, as expected for axis-aligned
  rectangles), disc_small=4, disc_big=5. **Sum of ranks = 11, HIGHER than the
  unified image's rank of 10.** So even in a hypothetical world with zero
  merge-overhead, this decomposition doesn't beat unified synthesis on pure
  structural grounds -- confirms (a third time, different partition each
  time: disc1/rest, 4 arbitrary y-band regions, now the TRUE geometric
  primitives) that global minimization over the full truth table finds
  cross-primitive redundancy that any split destroys. Combined with the
  qubit-budget block already known for `primitives.py`, this decomposition
  is dead for two independent reasons now, not just one.
**Confirmed dead, reinforced: splitting the image into regions (by pixel
band OR by true geometric primitive) and merging, full stop.**

## 2026-09-14 (cont'd, 6) — ANF degree distribution: rules out pure Gray-code/phase-polynomial synthesis, mathematically
Before building anything, computed the exact ANF (Zhegalkin/PPRM) degree
histogram of the real logo via a fast Mobius/Zeta transform (O(n*2^n), no
circuit synthesis needed) to check the PRECONDITION for Amy-Maslov-Mosca-style
Gray-code CNOT-ladder phase-polynomial synthesis: that technique realizes
LINEAR phase functions (phases on XOR-parities) with pure CNOT+phase gates,
zero ancilla -- it only helps when a function's ANF mass concentrates at low
degree. Result: **886 terms total (matches `pprm` cover exactly, a good cross-
check), average degree 6.75/12, only 4 terms at degree<=2, 87% of terms at
degree 5-9.** There is essentially no low-degree structure to exploit --
confirmed mathematically, not experimentally.

**Conclusion: pure Gray-code/phase-polynomial synthesis does not apply to
this function.** Any correct circuit must compute genuine high-arity AND
terms somehow (direct multi-controlled gates, or ancilla-based AND/XAG
decomposition) -- which is exactly the AIG-sharing problem already explored
and correctly deprioritized (NP-hard ancilla-constrained scheduling, still
~12x off leader even with unlimited ancilla). This closes the "maybe the
leader is using a fundamentally different linear-algebraic trick" hypothesis
for real: they're either solving the SAME hard scheduling problem we
shelved (successfully, with more sophisticated tooling), or using a
technique outside anything in the phase-polynomial/AIG/region-decomposition
family entirely. Don't re-attempt pure phase-polynomial synthesis without
new evidence the function's structure has changed (it hasn't -- this is
exact, not approximate).

## 2026-09-14 (cont'd, 5) — split-and-merge (2 variants): both lose to unified minimization
User proposed splitting the logo into independently-optimized pieces, twice:
(1) disc1 vs "rest of image", (2) all 4 geometric primitives separately
(disc2, disc1, big_rect, small_rect -- the leftover bucket turned out to be
EXACTLY 0 pixels, confirming disc1's definition correctly absorbs the
rect/disc transition zones). Measured GF(2) rank per piece both times:
  - disc1=1, rest=9 (sum=10, matches full)
  - disc2=5, disc1=4, big_rect=1, small_rect=0 (sum=10, matches full)
Built and scored each piece's oracle independently (esop_abc+serial_mcz) and
summed:
  - disc1+rest split: 8826 depth / 5926 cx (vs baseline 4316/2630)
  - 4-region split: 8469 depth / 5654 cx (vs baseline 4316/2630)
**Both LOSE by ~2x, before even adding OR-merge overhead.** Root cause:
ESOP/rank minimization is a GLOBAL optimization over the whole truth table;
splitting the table loses that global view even though each piece is
individually "simpler" (lower rank) -- the pieces' minimized circuits don't
compose additively cheaper than minimizing the whole. Rank summing to
EXACTLY the full-image rank both times (no redundancy across pieces) is the
tell: there was never slack to exploit this way.
**Confirmed dead: splitting the image into independently-synthesized regions
and OR/merging them, in any partition.** Don't retry with a different cut --
the mechanism (loss of global minimization) doesn't depend on where the cut
is made.

## 2026-09-14 (cont'd, 4) — comparator-efficiency lever: 3 clean negative results, stopped
Diagnosed WHY our comparators cost ~94 CX avg: of 60 range-indicator cubes
across the 10 `rect_groups`, 23 need the full 6 literals (6-controlled
Toffoli-equivalent, ~124 CX via Qiskit's default no-ancilla synthesis) --
confirms the theory from the previous entry, wide cubes are the real driver.

Tried THREE variants of "give Qiskit's `mcx(..., mode='recursion')` a dirty
ancilla to cut the per-gate cost" (confirmed in isolation: 6-ctrl MCX
124->64 CX with 1 borrowed qubit):
  1. dirty = other data register (x borrowed during y-side compute): depth
     6233->9068, cx 3564->5372. REGRESSED.
  2. dirty = same group's own already-computed x_flag ancilla (natural
     existing dependency, seemed safe): depth 6233->7742, cx 3564->4615.
     REGRESSED.
  3. dirty = genuinely idle ancilla (forced fully-serial group processing,
     sacrificing cross-group parallelism entirely, so 4 of 6 ancilla are
     ALWAYS idle and safe to lend): depth 6233->8761, cx 3564->5372.
     REGRESSED even with zero parallelism to destroy.

All three verified correct, all three worse. Variant 3 disproves the
"destroys parallelism" explanation for variants 1-2 (no parallelism existed
to destroy) -- the real cause is more likely that Qiskit's `opt_level=3`
transpiler has strong peephole/cancellation rules tuned to its STANDARD
(no-ancilla) MCX decomposition's regular gate pattern, and the `'recursion'`
dirty-ancilla pattern doesn't benefit from those passes anywhere near as
much, so the pre-transpile gate-count win gets more than erased post-transpile.

**Conclusion: don't retry `qc.mcx(..., ancilla_qubits=..., mode=...)` variants
here -- 3 consistent failures, not noise.** The remaining untested option is
writing a comparator's CX/Toffoli sequence by hand (bypassing Qiskit's
decomposition-mode selection entirely), which carries similar "might still
lose after transpile" uncertainty and real design/verification effort --
correctly deferred rather than attempted as a 4th variant this session.
**`rectangles_grouped` (4316/2630, Track B, verified) remains the best
result and the submission candidate.**

## 2026-09-14 (cont'd, 3) — AIG-sharing explored and correctly abandoned; dirty-ancilla MCX trick backfired
Researched state-of-the-art for exactly this problem class (Boolean phase
oracle synthesis under an ancilla budget): XOR-AND-Inverter Graphs + the
"reversible pebbling game" (Meuli/Soeken/De Micheli, npj Quantum Information
2022 + companion paper). Built `aig_synth.py`: use `abc` (`strash;dc2;dc2;dch`)
to get a SHARED 218-node/14-level 2-input AND graph for f (vs. 507-893
literals with zero sharing in our flat ESOP/GF2 approaches). With unlimited
scratch ancilla this gives depth=1679/cx=2616, verified exactly correct via a
from-scratch classical simulator (full Statevector sim isn't feasible at
230 qubits) -- already ~2.6x better depth than our best. BUT fitting this
into 6 real ancillas needs a genuine ancilla-constrained scheduler (the
"pebbling game," NP-hard in general); a hand-rolled greedy
evict-and-recompute scheduler hit repeated subtle bugs (the
eviction-protection chain during recursive `ensure()` calls needs the
sibling fanin protected too, not just the node being evicted -- fixed twice,
still failed at 6-10 ancillas). **Correctly abandoned mid-implementation**:
user pointed out that even the BEST-CASE unlimited-ancilla number (1679) is
still ~12x off the leader (142), so a hard scheduler that might still lose
wasn't the right time investment. Lesson: verify the ceiling of an approach
before investing in its hardest remaining piece.

Pivoted to a much better-targeted, concrete lever: measured that our
existing comparators cost ~94 CX each vs. ~10-20 CX for a hand-optimal 6-bit
range comparator -- a 5-9x overhead sitting entirely inside generic MCX
synthesis, and consistent with the leader's ~20 CX/comparator on a
similarly-sized (~28) comparator structure. Confirmed in isolation that
Qiskit's ancilla-free multi-controlled-X is expensive (6-ctrl: 124 CX) and
providing even 1 "dirty" (borrowed, exactly-restored) ancilla roughly halves
it (64 CX). **Tried wiring the OTHER data register in as dirty scratch
(x-register borrowed during a y-side computation, vice versa) -- this
REGRESSED both `rect_ancilla` (6233->9068 depth) and `gf2_ancilla`
(6337->7438 depth), reverted.** Root cause: the whole point of these
lowerings is that x-side and y-side sub-computations are on DISJOINT qubits
and can run concurrently; borrowing the other register as scratch creates a
data dependency between them and serializes what used to be parallel work.
The per-gate CX savings measured in isolation don't survive in context.
**The comparator-efficiency lever is still real and worth pursuing** -- just
needs dirty ancilla sourced from something genuinely idle (e.g. a batch's
own not-yet-live ancilla slots), not the other register.

## 2026-09-14 (cont'd, 2) — symmetry confirmed exact (per-band); manual scheduling tested, LOST to Classiq
User visually spotted band-local symmetry in the logo ("ball" ~y=11-27,
middle band ~y=29-53). Checked exactly against the pixel data: **disc2 band
symmetric about y=19 (0 defect pixels, both axes), middle band symmetric
about y=41 (0 defects)** — both exact, not approximate. Cross-checked against
`rectangles_grouped`: every one of its 2-member x-range groups already pairs
rows that are exact mirror images about one of these two axes. So the
symmetry is real, and was already fully captured (the "grouped by x-range"
dedup IS the reflection trick, just not labeled as such) — this doesn't leave
further headroom on its own.

Ran the cheap experiment agreed as step (1) before reaching for algebraic
methods: built `cover/rect_groups.py` + `lower/rect_ancilla.py`, a
hand-scheduled ancilla-batched version of the exact same group structure
`rectangles_grouped.py` uses, to test whether Classiq's `AUTO_OPTIMIZE` was
leaving parallelism on the table (depth/cx ratio was 0.61 vs leader's 3.92,
suggesting a scheduling deficit). Result: **6233/3564, verified correct, but
WORSE than Classiq's own scheduling of the identical logical structure
(4316/2630)**. Conclusion: our naive manual batching (Qiskit's generic MCX
decomposition + strict batch-boundary uncompute) is not simply unlocking
free parallelism Classiq was missing — if anything Classiq's own comparator
synthesis and/or scheduler is already better than our hand-rolled version.
This is informative, not wasted: it says the remaining ~30x gap is unlikely
to close via "control the scheduling ourselves" on this circuit shape. Next:
step (2), investigate whether the leader is using a fundamentally different
technique (algebraic/Gray-code phase-polynomial synthesis of the Boolean
function directly, rather than region-detection at all).

## 2026-09-14 (cont'd) — literature check + rectangles_grouped (4316/2630)
Searched for state-of-the-art technique before hand-rolling further (this is
a global challenge; assume competitors are reading the same papers). Most
relevant: "Low Depth Phase Oracle Using a Parallel Piecewise Circuit"
(arxiv 2409.04587) — general technique is per-segment ancilla flags computed
in parallel, O(log n + log S) depth for S segments, but needs ~1 ancilla per
segment (18 for our rectangles) against our 6-ancilla budget, so not directly
applicable at full width; validates the DIRECTION (shared/parallel
sub-predicate computation) that `gf2_ancilla` already used, not a drop-in.
Also checked comparator-synthesis literature (optimal CNOT-depth comparators,
QFT-based comparators) — relevant if hand-rolling comparators ever beats
Classiq's own arithmetic synthesis; not pursued yet.

Applied the general principle directly to Track B: `io.logo_rectangles()`'s
18 rectangles only have **10 unique x-ranges** (disc rasterization is
top-bottom symmetric). Built `classiq_native/rectangles_grouped.py`: nests
`control()` so the x-condition is computed once per unique x-range and reused
for its 1-2 y-sub-branches, instead of recomputing per rectangle. Verified
correct, **4316/2630** — new best, beating `rectangles.py` (5329/3502) by
19%/25% depth/cx from a single, purely mechanical dedup, no new synthesis
idea. Suggests there's more to gain from the same principle (grouping more
aggressively, or finding a smaller shared-comparator basis than raw x-range
identity).

Hit and fixed two real Classiq SDK bugs while building the second model —
documented in `CLAUDE.md` ("Classiq SDK gotcha") so they aren't rediscovered:
(1) `from __future__ import annotations` breaks `@qfunc` type introspection
(turns hints into strings; Classiq's inferrer expects real classes); (2)
two same-named qfuncs decorated in one process corrupt global inference
state regardless of which module defines them — fixed by running each
`classiq_native` model in its own subprocess (`_run_one.py`).

## 2026-09-14 — two tracks discovered/built; Track B currently leads
The baseline notebook (`classiq-challenge-baseline.ipynb`) revealed the real
image (Classiq logo: 2 rects + 2 discs, `io.logo_pixel`), the width cap (18 =
12 data + 6 ancilla), the scored basis (u3/cx via Classiq's own
`AUTO_OPTIMIZE`), and confirmed our bit convention already matched. Everything
run before this against `io.synthetic_target()` is stale (see below).

Built a second track (`classiq_native/`) alongside the existing PhaseIR
pipeline (`cover/`+`lower/`, now called Track A): qmod models synthesized
directly by Classiq, exploiting the image's geometric structure instead of
treating it as an opaque truth table. `classiq_native.rectangles` (the
notebook's own "unoptimized" baseline, just run through Classiq's DEPTH
constraint) scored **5329/3502**, beating Track A's best custom pipeline
(`gf2_factor`+`gf2_ancilla`: 6337/3609). Full standings in `CLAUDE.md`.

Both tracks are still ~37x off the leader (142/557) — neither is "done."

## Confirmed dead — do not revisit
- **Complementing the image.** `(-1)^¬f = -(-1)^f`. Global phase. Zero gain.
  (Encoded as a note in `diagnostics.density_report`.)
- **Variable reordering to improve ESOP.** Permutation + complementation of
  variables preserve min-ESOP cost exactly. Morton order helps BDD size only —
  so it matters only on a BDD-synthesis route.
- **Variational / learned oracle.** Must be exact on all 4096 states; fidelity
  < 1 is a wrong answer, not a worse score.
- **General (non-affine) pixel permutation.** Costs more than the oracle it optimises.
- **Full quadratic-arithmetic disc predicates** (`classiq_native/primitives.py`)
  within the 18-qubit cap — needs ~43 qubits for one disc's sum-of-squares
  intermediates. A cheaper "inside this disc" encoding is still worth finding.
- **Mirror/transpose symmetry on the REAL logo.** Checked via `qo diag`:
  agreement 0.6-0.9 on every axis, none exact. Dead for this image (was
  gated/unresolved when diagnostics only ran on the synthetic placeholder).

## Live
- **Track B: cut Track B's 18 rectangles further without exceeding the qubit
  budget** (e.g. share one comparator ancilla across rectangles with a common
  x- or y-range, mirroring `gf2_ancilla`'s reuse idea). Best lever right now.
- ESOP via EXORCISM + best-of-N restarts, weighted by **literal** count.
- Ancilla fanout (`lower/fanout.py`) — width cap is now known (18/6), so this
  is unblocked; likely secondary to the Track B lever above.
- Relative-phase Toffolis inside `within_apply`; log-depth MCX with clean ancillas.
- Phase-gadget scheduling (PyZX) — commuting-gadget scheduling *is* the depth problem.

## Resolved (were gated on diagnostics)
- **GF(2) rank** on the real logo = 10/64 → pursued. `gf2_factor` cover +
  `gf2_ancilla` lowering (ancilla-parallel, batched depth-1 CZ layers) built
  and verified: 6337/3609, Track A's current best. `gf2.factor` deliberately
  picks V from real image rows, which synthesise more cheaply than RREF basis
  vectors — confirmed working as designed.
- **Mirror symmetry**: see "Confirmed dead" above — none exists on the real image.

## Anti-stuck rules
1. No measured, verified improvement in 4h → shelve the branch (log, don't delete).
2. Always hold a verified best-so-far. Never break the working submission.
3. Diagnostics before optimisation.
4. Prefer variance (restarts, seeds) over cleverness when time is short.
5. fewer variables → fewer terms → fewer literals → shorter schedule.
   Reductions compose multiplicatively; earlier ones are worth more.

## 2026-09-28 (cont'd 6) — submission artifacts: .qmod + .qasm produced and verified

Produced the two deliverables the challenge asks for. `submission.qasm` (the
scored artifact) and `submission.qmod` (the reproducibility source), plus
`submission.synthesis_options.json` and `submission_model.py`.

**What the notebook actually scores.** Read Steps 4-6 properly for the first
time. Two things that change how this must be done:
- `qasm_metrics()` computes depth by its own per-qubit layering **directly on
  the submitted QASM text**. There is no re-transpile at scoring time. The file
  as written *is* the score.
- Step 6 "reads `submission.qasm` directly and **never simulates the earlier
  Qmod model**". The markdown for Step 4 says the qmod "is saved for
  reproducibility, but the transpiled QASM circuit ... is the authoritative
  artifact for verification and scoring."
So the qmod does not have to synthesize; it has to faithfully represent the
circuit. Good, because ours cannot synthesize (see limitation below).

**Trap 1 — angle rounding, would have been fatal.** Both `qasm_to_qmod()` (the
server-side decompiler) and `write_qmod()` default to `decimal_precision=4`.
The decompiled qmod contains `U(3.1416, 0.0, 3.1416, 0.0, q_0)` where the
circuit needs `pi`. That is a 7.3e-6 per-gate error against a 1e-10 exactness
bar. Not fixable by substituting symbolic `pi` either: 1q-gate fusion in the
Qiskit transpile leaves genuinely irrational Euler angles in the circuit
(`0.8332521844832049`, `2.323947607757091`, ... — 61 distinct triples, of which
many are non-symbolic). Fix: generate `submission_model.py` from the QASM with
Python `repr()` floats (bit-identical doubles) and pass `decimal_precision=17`.

**Trap 2 — don't trust a decompiler round-trip as verification.** Checked the
shipped qmod by parsing it back to a gate list and asserting *exact float
equality* against the QASM parsed the same way: 2980/2980 ops identical
(1336 cx + 1644 u3). Then built a Qiskit circuit *from the qmod* and ran
`verify()` at atol=1e-10: 0 wrong of 4096, deviation 3.33e-16.

**Authoritative check.** Ran the notebook's Step 6 verbatim (Classiq
`ExecutionSession`, `classiq/simulator`, 3 random product states) on
`submission.qasm`:
```
Successfully verified loaded QASM with score 1358:
width = 18   depth = 1358   CX count = 1336
max error = 4.0e-16   ancilla error = 7.1e-17   normalization error = 2.2e-14
```
All three bars are 1e-10; we are ~6 orders inside all of them.

**No free win from Classiq's compiler.** Ran cell 14's
`quantum_program_from_qasm` + `classiq.transpile(AUTO_OPTIMIZE, u3/cx)` on our
QASM: returns depth=1358, cx=1336, u3=1644 — identical. Our circuit is already
at Classiq's own fixed point, so the file needs no further processing.

**Known limitation (harmless).** `synthesize(main)` on the gate-literal model
fails with `httpx.WriteTimeout`: `create_model` serializes 2980 literal gate
statements into a 3.8 MB JSON payload (~1.3 KB/statement) and the upload is
rejected. There is no native-qmod ingestion endpoint in the SDK (only
`qasm_to_qmod` the other direction), so this cannot be worked around from
Python. It does not affect scoring or verification, both of which are
QASM-driven. The 56 KB native `.qmod` text itself is well-formed and is what
the IDE consumes.

Deleted the server-decompiled `SUBMISSION_oracle.py` — it carried the
4-decimal angles and would produce a wrong circuit if anyone ran it.

## 2026-09-30 — RCCX is free inside the conjugating permutation: 1358/1336 -> 1332/1317 (VALID). Symmetry folding and variable-count minimization both closed.

User's last-attempt proposal, three parts. One correct and shipped, two closed.

**(1) SHIPPED — RCCX everywhere inside U, not just in pebbling.** The oracle is
`U^dag . D . U` with D diagonal. Every RCCX = `Lambda . CCX` with Lambda
diagonal; conjugating a diagonal by a permutation stays diagonal, so
`U = Lambda_tot . P` for a permutation P, and
`U^dag D U = P^dag Lambda^dag D Lambda P = P^dag D P`
since diagonals commute. The relative phases cancel **identically** — not
approximately — so the circuit is bit-for-bit the same unitary as the
full-Toffoli version. RCCX is depth 7 / 3 cx vs CCX's 11 / 6.

`emit_perm` in `build_hybrid3.py` was emitting `qc.ccx(...)` for all three
transform Toffolis (the AND-tree MCZ already used RCCX; the transform did not).
Swapped, with `RCCXGate()` forward and `RCCXGate().inverse()` in the reversed
pass — RCCX is NOT self-inverse, CCX is, and `emit_perm` relied on that.
Controlled test, same cover and same cube order, only that swap:
- CCX control: depth 1358, cx 1336  (reproduces the stored artifact exactly)
- RCCX:        depth **1332**, cx **1317**, verify 1e-10 n_wrong=0
Official Step 6: `Successfully verified loaded QASM with score 1332`,
max error 3.8e-16, ancilla 6.7e-17, norm 2.2e-14. Shipped to `submission.*`.
Artifact: `data/artifacts/lower/esop_hybrid_tree3_rccx/`.

**Knock-on: the transform search had the wrong cost model all along.**
`nl_costmodel.py` used `D_TOF=22.0` (2 x CCX depth 11). Correct price is
**14.0** (2 x RCCX depth 7) — Toffolis were over-penalized by 36%, so the
basin-hopping search was biased against exactly the gates that break the ANF
degree invariant. Re-ran it seeded from the 13-gate best with D_TOF=14.0 and
the corrected measured COST entries (k=6 -> 25 not 27, k=12 -> 66 not 73).
**RESULT (2026-09-30, 120 hops): NO IMPROVEMENT.** Returned the seed unchanged
-- the identical 13 gates, 38 cubes, cube_cost 1450. So the inflated Toffoli
price was NOT what limited that search, and the hypothesis that it biased the
search against ANF-degree-breaking gates is refuted. 38 cubes / 1450 is a
genuine local optimum of this cover+transform architecture, not a cost-model
artifact. Don't re-run this search with another reweighting.

**(2) CLOSED BY PROOF — "minimize how many qubits f∘Pi depends on".** Vacuous:
the answer is 12 for every Pi. The image has **1097** marked pixels, which is
ODD. If f∘Pi depended on only k < 12 data qubits, the domain would partition
into blocks of size 2^(12-k) >= 2 with f constant on each, so |f^-1(1)| would
be a multiple of 2^(12-k), hence even. It is 1097. Any in-place permutation of
the 12 data qubits preserves that count, so no reversible relabelling can ever
shrink D's support. (This does NOT apply to ancilla-assisted forms, where the
image of the encoding is a 2^12 subset of 2^18 and g may be chosen to depend on
fewer variables — that is just the ordinary compute-flag-Z-uncompute
architecture, already measured with a ~600 cx floor.)

**(3) CLOSED BY MEASUREMENT — symmetry folding.** Tested the exact band-local
mirrors (y about 19, y about 41, x about 40) as reversible sign-magnitude folds
(bijections by construction, asserted). Benefit measured BEFORE any gate
decomposition — every variant makes the cover WORSE:

| transform | cubes | cube_cost |
|---|---|---|
| identity | 57 | 2461 |
| current 13-gate | **38** | **1450** |
| fold y@19 | 57 | 2578 |
| fold y@41 | 69 | 2987 |
| fold x@40 | 64 | 2656 |
| 13g + fold y@19 | 52 | 2165 |
| 13g + fold x@40 | 56 | 2205 |

Mechanism, and it is the same one that killed the GF(2)-linear basis change:
those mirrors are **band-local** (exact only within the disc2 band about y=19
and the middle bar about y=41), not global. Folding globally destroys the
axis-aligned interval structure everywhere OUTSIDE the band, which is where
most cubes live. Cost ~200+ depth to implement and it is negative before you
spend any of it. Note CLAUDE.md already recorded "no exact GLOBAL mirror
symmetry"; this closes the band-local version too.

**Process note:** measuring the benefit of a transform (one `abc` call on the
permuted truth table) before building its circuit turned a ~3h implementation
into a ~1min test. Do that ordering for any future change-of-variables idea.

**Also fixed:** `gen_model.py` hardcoded `SUBMISSION_oracle.qasm`, so after
updating the QASM it regenerated the qmod from the STALE circuit. Caught by the
qmod-vs-qasm exact-float-equality check (2980 vs 2939 ops). Path now points at
`submission.qasm` and the stale file is deleted. Keep running that check after
every QASM change — it is the only thing that catches this.

## 2026-09-30 (cont'd) — POST-MORTEM: the fused single-comparison form VERIFIED (0/4096). Where the project actually went wrong.

User surfaced a published competitor approach (QBlackBit). Its central claim is
checkable, and I checked it rather than taking it on trust. **It is exactly
right for our image.**

**The architecture: ONE comparison, not an XOR of two.**
```
[a1(x) <= L1(y)] XOR [a2(x) <= L2(y)]   wrong = 0/4096   (ours, 2026-09-28)
[ a_u(x) <= l(y) ]          (single)    wrong = 0/4096
[ l(y) + mu(x,u) >= 7 ]     (sum)       wrong = 0/4096
```
where u(y) = which of the two chains row y belongs to, l(y) = its level in that
chain, and `mu(x,u) = 7 - a_u(x)`. Our XOR form was the SAME structure unfused;
fusing it is arithmetic, not new geometry.

**The "128 points" detail confirms the reading.** The row code is 6 bits of y
-> 3 bits = **64 points**. The column code is 6 bits of x PLUS the chain bit u
-> 3 bits = **128 points**. That extra input is why the published description
says 128 and not 64, and it is why "11 row classes > 8" was never the real
obstacle: the chain choice does not consume code bits, it is a separate input
to the column code. We read the hint as "get to <=8 classes per side" and got
stuck on 11 — wrong reading.
Verified in `scratchpad/fused2.py`; the two chains are confirmed to partition
all 11 patterns (sharing only the empty one), each strictly increasing.

**The real remaining obstacle is ANCILLA COUNT, and it is sharper than "one
step away".** The fused form needs `l(3) + u(1) + mu(3) = 7` materialized at
once; we have 6. The two-pass XOR form is the one that fits 6 (each pass needs
`l_u(3) + a_u(3)`, with u implicit in which pass you are in). So fusing buys
depth but costs an ancilla. Unsolved here. The likely way in is the relaxation
visible in their verifier — it checks membership in a GF(2) SPAN by
elimination, i.e. it does not require the code bits on dedicated wires, only
some set of wires whose linear span contains them. Not confirmed.

**THE PROCESS ERROR, stated plainly.** On 2026-09-28 I found the exact
decomposition and then closed the route MYSELF: I synthesized the encoder bit
functions as AIGs (L1 bit0 = 16 nodes, bit1 = 13, L2 bit0 = 15), measured them
infeasible to pebble at 5 scratch, and concluded "unbuildable in 6 ancillas."
That measured the cost of **AIG-synthesis-then-pebble** — a method already
committed to — NOT the cost of the function. A 6->3-bit function is only 64
points: small enough to SEARCH for a circuit directly, which is what the
competitor does (tens of thousands of annealing chains per code, each first
finding a correct circuit then annealing toward minimum depth against an exact
u3/cx depth model). Decompose first, brute-force the small piece second. The
GPU is not the part that mattered — our own `anneal_rev.py` failed because it
annealed the whole 18-qubit oracle instead of a 64- or 128-point piece.

**This is the SAME error this log recorded in bold two days earlier**
(2026-09-26, ESOP route): "before writing off a route, check whether the
measurement is an artifact of implementation rather than approach." Written
down on the 26th, repeated on the 28th, on the most important route in the
project. Recording the lesson did not prevent recurrence because it was filed
as a fact about the ESOP route, not as a check to run before closing ANY route.

**Three other process failures, in order of cost:**
1. **Geometry was never done first.** The two chains and 11 row classes are
   computable from `io.logo_pixel` in minutes. Found on 2026-09-28, two days
   from the deadline. 2026-09-14 through -26 went entirely to the
   "opaque boolean function" family (ESOP, GF(2) rank, AIG, pebbling, BQSKit) —
   a family whose own floor I later computed at ~600 cx, above the leader's 269.
2. **Never budgeted backwards from the leaderboard before building.** 95 depth
   / 272 cx is ~90 RCCX total, ~45 per half, so ~25-30 depth per piece. Our
   interval indicator measured 136 depth BY ITSELF. Doing that division on
   2026-09-14 rules out the whole materialize-predicates architecture before
   weeks go into it. The public signal was already there: Daksh S. at 128 on
   2026-09-17 while our generic route was at ~4000.
3. **Tuned at a 10x gap.** The anti-stuck rule ("no measured improvement in 4h
   -> shelve") rewards any positive delta and kept the project in one valley:
   +17% from CP-SAT tuning, 14 HOURS of BQSKit for 0.4%. **Better rule: while
   the gap to the leader is >5x, an improvement that does not change the order
   of magnitude does not count as progress.**

Also noted: 2nd-7th place all landed at depth 107-111 with wildly different cx
(373-558), which suggests several independent teams converging on some natural
depth of a construction none of this project found. The published approach's
own estimate (both codes at depth ~33 -> whole oracle ~120) does not reach the
top-5 cut of 109 either.
