"""AIG-based synthesis: build f's phase oracle from a SHARED 2-input AND
network (an And-Inverter Graph, via `abc`'s own logic optimization: `strash;
dc2; dc2; dch`), not from a flat list of independently-computed ESOP cubes.

WHY. `esop_abc`/`gf2_factor`/`rect_groups` each compute their terms/factors/
groups INDEPENDENTLY -- no sharing of common sub-results across terms. `abc`'s
own AIG optimizer finds a much more compact SHARED representation: for the
real logo, 57 ESOP cubes (up to 12 literals each) collapse to a 218-node,
14-LEVEL 2-input AND graph -- i.e. the function's true "circuit depth" in
purely classical terms is 14 AND-gates, not 12 literals' worth of series
control. This is the XOR-AND-Inverter-Graph idea from Meuli/Soeken/De Micheli
("Xor-And-Inverter Graphs for Quantum Compilation", npj Quantum Information
2022), and mapping it to a reversible circuit under a fixed ancilla budget is
their "reversible pebbling game" -- an NP-hard scheduling problem in general.

RELATIVE-PHASE TOFFOLI (RCCX / Margolus gate, 3 CX instead of 6). Every AIG
node is a plain 2-input AND -- exactly the case RCCX handles. Verified exact
(full Operator comparison, not approximate) for the compute/use/uncompute
pattern used throughout this module, PROVIDED: (a) uncompute happens in
strict LIFO order (reversed node order -- this module already does that),
and (b) no node's own `invert_output` is applied as a physical post-gate X
(that breaks the cancellation -- confirmed: 3725/4096 wrong before this fix).
Instead `invert_output` is folded into the POLARITY used by whatever
consumes that node as a fanin; the output node's own inversion, if any,
surfaces only as a global phase (free per the problem spec). With this fix,
relative_phase=True roughly HALVES cx/depth: unlimited-ancilla ceiling went
from 1679/2616 to 853/1307 -- see notes/DECISIONS.md 2026-09-14.

STATUS: `peak_width()` measures the minimum simultaneously-live node count a
naive schedule needs (24-28 across many orderings -- a real structural
property of this graph, not fixable by reordering alone). `build_circuit()`
is the ancilla-constrained scheduler: Belady's algorithm (evict whichever
live node has the furthest-in-the-future next use, computed from a fixed
processing order) rather than the earlier recursive "protect list" design,
which grew unboundedly with recursion depth and deadlocked around 6-10
ancillas. Belady needs no such list -- a node about to be reused has a
near-term next-use distance and is naturally never chosen for eviction.
"""
from __future__ import annotations

import subprocess
import tempfile
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import RCCXGate

from .spec import N_DATA, OracleSpec


@dataclass
class AigNode:
    fanins: tuple[str, str]
    polarity: tuple[int, int]
    invert_output: bool = False
    is_xor: bool = False
    """True for a genuine XOR/XNOR node (`invert_output` distinguishes
    them: XOR if False, XNOR if True). `polarity` is unused when this is
    set. ABC's `if -K 2` LUT mapping does NOT only produce single-product
    (AND-with-polarity) 2-input nodes -- a 2-row `.names` block ("01 1" +
    "10 1", or "00 1" + "11 1") is XOR/XNOR, and treating it as AND-only
    (reading just the first row) silently drops half the function.
    Confirmed as a real, live bug: one of the real logo's GF(2)-factor
    sub-AIGs synthesized an XOR node, and the single-row assumption gave a
    wrong circuit for exactly the 2 inputs that only the dropped row
    covered (see notes/DECISIONS.md 2026-09-14). XOR needs no relative-
    phase machinery at all -- two plain CNOTs into the target, trivially
    self-inverse and order-independent (CNOTs on different controls always
    commute), unlike AND/RCCX which needed careful compute/uncompute
    ordering throughout this module."""


def write_pla_truth(truth: np.ndarray, n: int, path: Path) -> None:
    marked = np.flatnonzero(truth)
    lines = [f".i {n}", ".o 1", f".p {len(marked)}", ".type fr"]
    for i in marked:
        bits = "".join(str((int(i) >> b) & 1) for b in range(n))
        lines.append(f"{bits} 1")
    lines.append(".e")
    path.write_text("\n".join(lines))


def synthesize_small_aig_blif(truth: np.ndarray, n: int, effort: str = "strash; dc2; dc2; dch") -> str | None:
    """BLIF for an arbitrary n-bit truth table (not tied to N_DATA=12) --
    used for the small per-factor AIGs in `build_gf2_factor_circuit`.
    Returns None for the constant-0 function (empty marked set; `abc`
    can't/needn't synthesize anything for it -- caller should treat the
    result as identically 0)."""
    if not truth.any():
        return None
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        pla, blif = tdp / "f.pla", tdp / "f.blif"
        write_pla_truth(truth, n, pla)
        script = f"read_pla {pla}; {effort}; if -K 2; write_blif {blif};"
        subprocess.run(["abc", "-q", script], check=True, capture_output=True, timeout=600)
        return blif.read_text()


def write_pla(spec: OracleSpec, path: Path) -> None:
    write_pla_truth(spec.truth, N_DATA, path)


def synthesize_aig_blif(spec: OracleSpec, effort: str = "strash; dc2; dc2; dch") -> str:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        pla, blif = tdp / "f.pla", tdp / "f.blif"
        write_pla(spec, pla)
        script = f"read_pla {pla}; {effort}; if -K 2; write_blif {blif};"
        subprocess.run(["abc", "-q", script], check=True, capture_output=True, timeout=600)
        return blif.read_text()


def parse_blif(text: str) -> tuple[list[str], str, dict[str, AigNode]]:
    lines = text.splitlines()
    inputs: list[str] = []
    output: str | None = None
    nodes: dict[str, AigNode] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(".inputs"):
            inputs = line.split()[1:]
        elif line.startswith(".outputs"):
            output = line.split()[1]
        elif line.startswith(".names"):
            names = line.split()[1:]
            assert len(names) == 3, f"expected a 2-input node, got: {line}"
            in0, in1, out = names
            rows: list[tuple[str, str]] = []
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith("."):
                i += 1
                pattern, val = lines[i].strip().split()
                rows.append((pattern, val))
            assert rows, f"'.names {in0} {in1} {out}' has no rows"
            assert len({v for _, v in rows}) == 1, \
                f"'.names {in0} {in1} {out}' mixes on-set and off-set rows: {rows} -- unhandled BLIF form"
            val = rows[0][1]
            patterns = {p for p, _ in rows}
            if len(rows) == 1:
                pattern = rows[0][0]
                nodes[out] = AigNode(fanins=(in0, in1), polarity=(int(pattern[0]), int(pattern[1])),
                                      invert_output=(val == "0"))
            elif len(rows) == 2 and patterns == {"01", "10"}:
                # XOR(in0, in1) if val=="1", else XNOR (the complement)
                nodes[out] = AigNode(fanins=(in0, in1), polarity=(0, 0), is_xor=True,
                                      invert_output=(val == "0"))
            elif len(rows) == 2 and patterns == {"00", "11"}:
                # XNOR(in0, in1) if val=="1", else XOR
                nodes[out] = AigNode(fanins=(in0, in1), polarity=(0, 0), is_xor=True,
                                      invert_output=(val == "1"))
            else:
                raise NotImplementedError(
                    f"'.names {in0} {in1} {out}' has an unhandled 2-input pattern set {patterns} "
                    f"(val={val}) -- only single-row (AND-with-polarity) and the two XOR/XNOR "
                    f"2-row forms are implemented"
                )
        i += 1
    assert output is not None and inputs
    return inputs, output, nodes


def topo_order(inputs: list[str], output: str, nodes: dict[str, AigNode]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set(inputs)
    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        for f in nodes[name].fanins:
            visit(f)
        order.append(name)
    visit(output)
    return order


def best_order(inputs: list[str], output: str, nodes: dict[str, AigNode],
                trials: int = 300, seed: int = 7) -> list[str]:
    """Random DFS restarts (shuffle which fanin is visited first), keep the
    ordering with lowest peak simultaneous-live-node count. Peak width stays
    in the 24-29 range across strategies tried (2026-09-14) -- a structural
    property of this graph -- but a lower one still reduces how much
    recomputation the ancilla-constrained scheduler needs to do."""
    import random
    rng = random.Random(seed)
    best, best_pw = None, None
    for _ in range(trials):
        seen = set(inputs)
        order: list[str] = []
        def visit(name: str) -> None:
            if name in seen:
                return
            seen.add(name)
            pair = list(nodes[name].fanins)
            rng.shuffle(pair)
            for f in pair:
                visit(f)
            order.append(name)
        visit(output)
        pw = peak_width(order, nodes, output)
        if best_pw is None or pw < best_pw:
            best, best_pw = order, pw
    return best


def peak_width(order: list[str], nodes: dict[str, AigNode], output: str) -> int:
    refcount = {n: 0 for n in nodes}
    for n in nodes.values():
        for f in n.fanins:
            if f in refcount:
                refcount[f] += 1
    refcount[output] = refcount.get(output, 0) + 1
    remaining = dict(refcount)
    live: set[str] = set()
    peak = 0
    for name in order:
        live.add(name)
        peak = max(peak, len(live))
        for f in nodes[name].fanins:
            if f in remaining:
                remaining[f] -= 1
                if remaining[f] == 0:
                    live.discard(f)
    return peak


def build_circuit_unlimited_ancilla(spec: OracleSpec, relative_phase: bool = False) -> QuantumCircuit:
    """One fresh scratch qubit per AIG node, never reused. NOT a valid
    submission (width = 12 + n_nodes, way over the 18-qubit cap) -- purely to
    measure whether the shared-AIG representation is worth pursuing before
    building the real ancilla-constrained pebbling scheduler.

    `relative_phase`: use RCCX (Margolus gate, 3 CX) instead of CCX (6 CX)
    for every node's AND. See module docstring for why this is safe here.
    """
    blif = synthesize_aig_blif(spec)
    inputs, output, nodes = parse_blif(blif)
    order = topo_order(inputs, output, nodes)

    effective_polarity: dict[str, tuple[int, int]] = {}
    for name in order:
        node = nodes[name]
        f0, f1 = node.fanins
        p0, p1 = node.polarity
        if nodes.get(f0) and nodes[f0].invert_output:
            p0 ^= 1
        if nodes.get(f1) and nodes[f1].invert_output:
            p1 ^= 1
        effective_polarity[name] = (p0, p1)

    qc = QuantumCircuit(N_DATA + len(order), name="oracle_aig_unlimited")
    qubit = {name: i for i, name in enumerate(inputs)}
    next_free = N_DATA

    def emit(name: str, target: int) -> None:
        f0, f1 = nodes[name].fanins
        p0, p1 = effective_polarity[name]
        q0, q1 = qubit[f0], qubit[f1]
        if p0 == 0:
            qc.x(q0)
        if p1 == 0:
            qc.x(q1)
        if relative_phase:
            qc.append(RCCXGate(), [q0, q1, target])
        else:
            qc.ccx(q0, q1, target)
        if p0 == 0:
            qc.x(q0)
        if p1 == 0:
            qc.x(q1)

    for name in order:
        q = next_free
        next_free += 1
        emit(name, q)
        qubit[name] = q

    qc.z(qubit[output])  # output's own invert_output, if any, is a free global phase

    for name in reversed(order):
        emit(name, qubit[name])

    return qc


@dataclass
class _BeladyScheduler:
    """Ancilla-constrained scheduler using Belady's optimal offline caching
    rule: when a free slot is needed, evict whichever currently-live node
    has the FURTHEST-in-the-future next use (computed from a fixed node
    order), never an explicit "protect list". A node about to be reused has
    a near-term next-use distance and is therefore never a good eviction
    candidate -- this is what makes the earlier recursive "protect list"
    design (which grew with recursion depth and deadlocked around 6-10
    ancillas) unnecessary here.
    """
    nodes: dict[str, AigNode]
    input_qubit: dict[str, int]
    consumption: dict[str, list[int]]  # node -> sorted positions where it's used as a fanin
    order_index: dict[str, int]
    ancillas: list[int]
    qc: QuantumCircuit
    relative_phase: bool
    free: list[int] = field(default_factory=list)
    live: dict[str, int] = field(default_factory=dict)
    clock: int = 0
    """A SINGLE, globally-consistent notion of "how far we've progressed" --
    NOT a per-call parameter. Threading a `target_pos`/`pos` argument through
    the recursion instead (tried first) is WRONG: `_teardown`, when it
    re-`ensure`s a evicted node's own fanins mid-cascade, used to pass that
    node's static creation position, which could be far EARLIER than where
    the schedule has actually progressed to -- making Belady decisions
    inside that cascade think we were "back" at an earlier point, evicting
    things that were still genuinely needed later. The driving loop below
    advances `clock` once per fixed-order step; every recursive call, no
    matter how deep, reads the same current value. Confirmed broken without
    this (None qubit index / infinite-recompute cycling even at ancillas=30,
    well above the measured peak width of ~26) -- see notes/DECISIONS.md
    2026-09-14.
    """

    def __post_init__(self):
        self.free = list(self.ancillas)

    def _emit(self, name: str, target: int) -> None:
        node = self.nodes[name]
        f0, f1 = node.fanins
        p0, p1 = node.polarity
        q0 = self.live.get(f0, self.input_qubit.get(f0))
        q1 = self.live.get(f1, self.input_qubit.get(f1))
        if p0 == 0:
            self.qc.x(q0)
        if p1 == 0:
            self.qc.x(q1)
        if self.relative_phase:
            self.qc.append(RCCXGate(), [q0, q1, target])
        else:
            self.qc.ccx(q0, q1, target)
        if p0 == 0:
            self.qc.x(q0)
        if p1 == 0:
            self.qc.x(q1)

    def _next_use(self, name: str) -> float:
        positions = self.consumption.get(name, [])
        i = bisect_right(positions, self.clock - 1)
        return positions[i] if i < len(positions) else float("inf")

    def ensure(self, name: str, protect: frozenset = frozenset()) -> int:
        if name in self.input_qubit:
            return self.input_qubit[name]
        if name in self.live:
            return self.live[name]
        f0, f1 = self.nodes[name].fanins
        self.ensure(f0, protect | {f1})
        self.ensure(f1, protect | {f0})
        if not self.free:
            self._evict(protect | {f0, f1})
        q = self.free.pop()
        self._emit(name, q)
        self.live[name] = q
        # NO proactive release here, deliberately -- see history in
        # notes/DECISIONS.md 2026-09-14 for why (release-on-last-use is
        # logically correct but causes exponential recompute-for-uncompute
        # blowup for deep/shared chains). Rely purely on REACTIVE eviction.
        #
        # `protect`: f0 and f1 must not be evicted while securing EACH
        # OTHER (Belady's structural next-use metric has no way to know a
        # freshly-recomputed fanin is needed imminently for the pending
        # gate -- its own recorded consumption positions are typically long
        # past by the time a teardown cascade recomputes it far later than
        # its original slot. Confirmed root cause of a persistent "None
        # qubit" bug: securing f1 evicted the JUST-secured f0). This is
        # LOCAL protection (just the current node's own 2 fanins, inherited
        # by whatever it recurses into) -- not the unboundedly-accumulating
        # ancestor-chain protection that deadlocked an earlier design; here
        # it is bounded by how many gates are simultaneously "pending
        # completion" along the live recursion path.
        assert len(self.live) <= len(self.ancillas), \
            f"live set ({len(self.live)}) exceeds ancilla budget ({len(self.ancillas)})"
        return q

    def _evict(self, protect: frozenset = frozenset()) -> None:
        worst_name, worst_dist = None, -1.0
        for name in self.live:
            if name in protect:
                continue
            dist = self._next_use(name)
            if dist > worst_dist:
                worst_name, worst_dist = name, dist
        if worst_name is None:
            raise RuntimeError(f"nothing evictable -- all {len(self.live)} live nodes protected")
        self._teardown(worst_name, protect)

    def _teardown(self, name: str, protect: frozenset = frozenset()) -> None:
        f0, f1 = self.nodes[name].fanins
        # Pop from `live` FIRST, before the fanins' own `ensure()` calls can
        # run. Doing it after (tried first) is a genuine re-entrancy bug: if
        # securing f0/f1 triggers a NESTED eviction, Belady sees `name`
        # still marked live and can pick it as ITS OWN victim, recursively
        # tearing down the very node whose teardown is already in progress
        # -- confirmed root cause of runaway/infinite recursion even at
        # ancillas=30 with zero real need for it (peak_width()==26). The
        # qubit `q` is deliberately held out of BOTH `live` and `free`
        # during this window: not live (so it can't be re-selected), not
        # free (so nothing else can claim it before this uncompute gate
        # actually runs).
        q = self.live.pop(name)
        self.ensure(f0, protect | {f1})
        self.ensure(f1, protect | {f0})
        self._emit(name, q)  # self-inverse: restores q to |0>
        self.free.append(q)
        assert len(self.live) <= len(self.ancillas), \
            f"live set ({len(self.live)}) exceeds ancilla budget ({len(self.ancillas)})"


def _pebble_build(qc: QuantumCircuit, nodes: dict[str, AigNode], output: str, inputs: list[str],
                   input_qubit: dict[str, int], ancilla_qubits: list[int], relative_phase: bool,
                   order_trials: int) -> tuple[_BeladyScheduler, list[str]]:
    """Compute `output` using the Belady-eviction ancilla-constrained
    scheduler, leaving it live in the returned scheduler's `.live[output]`.
    Caller must eventually call `_pebble_uncompute` to return everything
    (including the output) to |0>. Factored out of `build_circuit` so the
    same, now-carefully-debugged machinery (see module docstring history)
    can also drive the small per-factor AIGs in
    `build_gf2_factor_circuit` -- NOT a second, independently-written
    allocator (an earlier from-scratch one for the small-AIG case had its
    own bug: freeing a qubit on refcount-zero without first UNCOMPUTING it,
    silently corrupting reused qubits -- see notes/DECISIONS.md 2026-09-14).
    """
    order = best_order(inputs, output, nodes, trials=order_trials)
    order_index = {name: i for i, name in enumerate(order)}

    consumption: dict[str, list[int]] = {n: [] for n in nodes}
    for name in order:
        for f in nodes[name].fanins:
            if f in consumption:
                consumption[f].append(order_index[name])
    consumption.setdefault(output, []).append(len(order))  # the final external use

    sched = _BeladyScheduler(nodes=nodes, input_qubit=input_qubit, consumption=consumption,
                              order_index=order_index, ancillas=ancilla_qubits, qc=qc,
                              relative_phase=relative_phase)

    # Drive through the FIXED order step by step, advancing sched.clock so it
    # reflects genuine schedule progress (a single top-level `ensure(output)`
    # call was tried and is WRONG: every intermediate node's Belady "next
    # use" would be measured against the final position, making everything
    # look infinitely far away / safe to evict long before it's actually
    # done being used).
    for i, name in enumerate(order):
        sched.clock = i
        sched.ensure(name)
    return sched, order


def _pebble_uncompute(sched: _BeladyScheduler, order: list[str]) -> None:
    sched.clock = len(order)  # past every real use; only cleanup remains
    for name in reversed(order):
        if name in sched.live:
            sched._teardown(name)


def build_circuit(spec: OracleSpec, ancillas: int = 6, relative_phase: bool = True,
                   order_trials: int = 300) -> QuantumCircuit:
    blif = synthesize_aig_blif(spec)
    inputs, output, nodes = parse_blif(blif)
    assert len(inputs) == N_DATA

    qc = QuantumCircuit(N_DATA + ancillas, name="oracle_aig_pebbled")
    input_qubit = {name: i for i, name in enumerate(inputs)}
    anc = list(range(N_DATA, N_DATA + ancillas))

    sched, order = _pebble_build(qc, nodes, output, inputs, input_qubit, anc, relative_phase, order_trials)
    out_q = sched.live[output]
    qc.z(out_q)
    _pebble_uncompute(sched, order)
    return qc


# ---------------------------------------------------------------------------
# Per-factor small AIGs (GF(2) rank decomposition), instead of one AIG for
# the full 12-variable function.
#
# WHY. The full-function AIG (218 nodes) genuinely needs ~20-28 simultaneous
# live values no matter how it's scheduled or reordered (peak_width(), tried
# across bare strash up to full dc2/dc2/dch) -- fitting that into 6 ancilla
# needs real recomputation, and recomputation cascades COMPOUND (confirmed:
# the Belady scheduler above works at ancillas=218 but FAILS at
# ancillas=100 -- non-monotonic behavior is the signature of genuine NP-hard
# pebbling difficulty, not a remaining implementation bug).
#
# Applying AIG+RCCX to the 6-VARIABLE u_i(y)/v_i(x) factors from the
# rank-10 `gf2_factor` decomposition instead is a completely different
# regime: measured peak_width across all 20 small AIGs (10 factors x 2) is
# 3-5, comfortably under budget. This reuses `_pebble_build`/
# `_pebble_uncompute` (the SAME Belady scheduler as the full-AIG path) --
# NOT a separately-written allocator. An earlier from-scratch attempt here
# had its own bug (freeing a qubit on refcount-zero WITHOUT first
# uncomputing it, silently corrupting reused qubits -- confirmed via an
# exhaustive test that caught 8-39 wrong results per factor before this
# fix), which is exactly the class of bug the Belady scheduler already
# handles correctly via its `_teardown` (uncompute-then-free). At this tiny
# scale (peak_width 3-5, depth 3-4), the sibling-protection set the Belady
# scheduler threads through recursion stays small -- none of the deep-chain
# compounding that made the full 218-node graph infeasible applies here.
# ---------------------------------------------------------------------------

@dataclass
class _SmallAigResult:
    result_qubit: int | None  # None means "constant 0" (no qubit holds it)
    sched: _BeladyScheduler | None = None
    order: list[str] = field(default_factory=list)
    invert: bool = False
    degenerate_qubit: int | None = None  # set when output IS a primary input, no AIG needed


def build_small_aig(qc: QuantumCircuit, truth: np.ndarray, n: int, input_qubits: list[int],
                     scratch: list[int], relative_phase: bool = True,
                     order_trials: int = 50) -> _SmallAigResult:
    """Compute an n-bit truth table's value into one of `scratch`'s qubits.
    `len(scratch)` MUST be >= this function's peak_width (measured 3-5 for
    all 20 of our GF(2)-factor sub-functions -- check via `peak_width()` on
    the same BLIF for any other use). Returns the qubit holding the result
    (not freed -- caller uses it, e.g. a CZ, then must call
    `uncompute_small_aig` to return everything including the result qubit
    to |0>).
    """
    blif = synthesize_small_aig_blif(truth, n)
    if blif is None:
        return _SmallAigResult(result_qubit=None)

    inputs, output, nodes = parse_blif(blif)
    assert len(inputs) == n
    input_qubit = {name: input_qubits[i] for i, name in enumerate(inputs)}

    if not nodes:
        # Degenerate: output is a primary input directly (shouldn't happen
        # for our factors in practice -- ESOP already handles literal-only
        # functions cheaply -- but handle it rather than assume it can't).
        assert output in input_qubit
        return _SmallAigResult(result_qubit=input_qubit[output], degenerate_qubit=input_qubit[output])

    sched, order = _pebble_build(qc, nodes, output, inputs, input_qubit, list(scratch),
                                  relative_phase, order_trials)
    result_qubit = sched.live[output]
    invert = nodes[output].invert_output
    if invert:
        # Unlike the top-level oracle (where the analogous inversion is a
        # harmless GLOBAL phase, since that result only ever feeds a final
        # Z), this result feeds further AND logic downstream (e.g. CZ with
        # a v_i factor) -- NOT(u_i) AND v_i != NOT(u_i AND v_i) in general,
        # so it must be corrected here, not left as a "free" inversion.
        qc.x(result_qubit)
    return _SmallAigResult(result_qubit=result_qubit, sched=sched, order=order, invert=invert)


def uncompute_small_aig(qc: QuantumCircuit, result: _SmallAigResult) -> None:
    """Exact inverse of `build_small_aig`."""
    if result.result_qubit is None or result.degenerate_qubit is not None:
        return  # constant-0, or output was a bare primary input -- nothing was computed
    if result.invert:
        qc.x(result.result_qubit)  # undo the corrective X, FIRST (mirrors build's order reversed)
    _pebble_uncompute(result.sched, result.order)
