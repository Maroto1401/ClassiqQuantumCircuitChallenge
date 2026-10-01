"""Exact/near-exact reversible-pebbling scheduler via CP-SAT (Google
OR-Tools), instead of a hand-rolled heuristic. Rationale: this session's
hand-rolled schedulers for the same problem (see aig_synth.py's
_BeladyScheduler) hit 11 distinct subtle bugs before being stopped as
untrustworthy -- correctness here comes from the SOLVER being sound by
construction (it either proves a schedule respects every constraint, or
reports infeasible/unknown), not from scheduling logic written by hand.

MODEL (standard reversible-pebbling formulation):
  - Boolean P[n][t]: is node n's value materialized ("pebbled") in some
    ancilla at time step t, for internal node n and t in [0, T].
  - P[n][0] = 0 for all n (start empty); P[n][T] = 0 for all n (fully
    uncomputed by the end).
  - sum_n P[n][t] <= ancillas for every t (the actual resource constraint).
  - At most one node's pebble state may change per time step (keeps the
    move->gate mapping simple; a general-purpose transpiler handles finding
    parallelism in the resulting gate sequence afterward, same as every
    other lowering in this codebase).
  - If node n's state changes at step t (placed OR removed -- REVERSIBLE
    pebbling requires fanins live for BOTH, unlike irreversible "black
    pebbling" where removal is free), every one of n's fanins must be
    available (pebbled, or a primary input) at t-1.
  - The output node must be pebbled at some t (so a Z gate can be applied
    there).
This is a FEASIBILITY search (find any valid schedule within a fixed
horizon T), not full makespan optimization -- optimizing T directly is a
much harder search; feasibility at a generously-chosen T is enough to
produce a correct circuit, and Qiskit's own transpiler already handles
compacting the resulting gate sequence for depth.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model
from qiskit import QuantumCircuit
from qiskit.circuit.library import RCCXGate


@dataclass
class PebbleSchedule:
    moves: list[tuple[str, bool]]  # (node_name, True=placed/False=removed), in time order


def solve_pebbling(nodes: dict, output: str, input_names: set[str], ancillas: int,
                    horizon: int, time_limit_s: float = 120.0) -> PebbleSchedule | None:
    """`nodes`: dict[name -> object with a `.fanins` tuple of 2 names]. Returns
    None if no schedule was found within `horizon` steps and `time_limit_s`
    (either genuinely infeasible at this horizon, or the solver ran out of
    time before deciding -- these are NOT distinguished here; caller should
    retry with a larger horizon on None, and treat repeated failure at large
    horizons as evidence of infeasibility, not proof).
    """
    internal = [n for n in nodes if n not in input_names]
    idx = {n: i for i, n in enumerate(internal)}
    T = horizon

    model = cp_model.CpModel()
    P = {n: [model.NewBoolVar(f"P_{n}_{t}") for t in range(T + 1)] for n in internal}

    for n in internal:
        model.Add(P[n][0] == 0)
        model.Add(P[n][T] == 0)

    for t in range(T + 1):
        model.Add(sum(P[n][t] for n in internal) <= ancillas)

    change = {}
    for n in internal:
        for t in range(1, T + 1):
            c = model.NewBoolVar(f"chg_{n}_{t}")
            model.Add(P[n][t] != P[n][t - 1]).OnlyEnforceIf(c)
            model.Add(P[n][t] == P[n][t - 1]).OnlyEnforceIf(c.Not())
            change[(n, t)] = c

    for t in range(1, T + 1):
        model.Add(sum(change[(n, t)] for n in internal) <= 1)

    for n in internal:
        f0, f1 = nodes[n].fanins
        for t in range(1, T + 1):
            for f in (f0, f1):
                if f in input_names:
                    continue  # primary inputs are always available
                model.AddImplication(change[(n, t)], P[f][t - 1])

    model.AddBoolOr([P[output][t] for t in range(1, T + 1)])

    # There must be SOME point where output is live and isolated (nothing
    # else pebbled) -- needed by callers that hand output off to be used
    # alongside a second, concurrently-built sub-AIG sharing the same
    # ancilla pool (gf2_cpsat_hybrid.py's u_i/v_i pair: v_i's own schedule
    # assumes a fixed number of free ancilla, which breaks if u_i leaves
    # more than just output live at the handoff -- confirmed as a real
    # integration bug, see notes/DECISIONS.md 2026-09-14).
    #
    # NOTE this must NOT be "isolated at the SAME instant output is first
    # placed" -- that directly contradicts the dependency rule (computing
    # output requires its OWN fanins pebbled at that same step), which is
    # exactly the bug in the first version of this constraint (confirmed:
    # instant, unanimous infeasibility across all 20 factors, 0.0-0.1s each
    # -- too fast to be a real search, a sure sign of a direct logical
    # contradiction rather than a hard instance). The fix: let the solver
    # choose ANY later timestep as the "isolated" one, giving it room to
    # free output's fanins in the steps between placing output and
    # reaching isolation.
    isolated = []
    for t in range(1, T + 1):
        lit = model.NewBoolVar(f"isolated_{t}")
        others = [P[n][t] for n in internal if n != output]
        model.AddBoolAnd([P[output][t]] + [o.Not() for o in others]).OnlyEnforceIf(lit)
        model.AddBoolOr([P[output][t].Not()] + others).OnlyEnforceIf(lit.Not())
        isolated.append(lit)
    model.AddBoolOr(isolated)

    model.Minimize(sum(change[(n, t)] for n in internal for t in range(1, T + 1)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    moves: list[tuple[str, bool]] = []
    for t in range(1, T + 1):
        for n in internal:
            if solver.Value(change[(n, t)]):
                moves.append((n, bool(solver.Value(P[n][t]))))
    return PebbleSchedule(moves=moves)


@dataclass
class PebbleCircuitResult:
    result_qubit: int
    invert: bool
    _remaining_moves: list[tuple[str, bool]] = field(default_factory=list)
    _live: dict[str, int] = field(default_factory=dict)
    _free: list[int] = field(default_factory=list)
    _emit: object = None  # the closure, reused for uncompute

    @property
    def live_qubits(self) -> set[int]:
        """ALL qubits currently holding a live value -- not just
        `result_qubit`. The schedule stops right after output's first
        placement, but other nodes of the SAME sub-AIG (e.g. output's own
        fanins) can still be live at that instant; the CP-SAT model only
        guarantees eventual cleanup, not "free everything possible
        immediately". A caller reusing the surrounding ancilla pool for
        something else (e.g. a second sub-AIG sharing the same physical
        qubits) MUST exclude every qubit in this set, not just
        `result_qubit` -- confirmed necessary: excluding only
        `result_qubit` let a second build's scratch allocator silently
        reuse a qubit that still held a first build's intermediate value,
        corrupting it (see notes/DECISIONS.md 2026-09-14)."""
        return set(self._live.values())


def build_from_schedule(qc: QuantumCircuit, nodes: dict, output: str, input_qubit: dict[str, int],
                         ancilla_qubits: list[int], schedule: PebbleSchedule,
                         relative_phase: bool = True) -> PebbleCircuitResult:
    """Realize a CP-SAT-verified-feasible `PebbleSchedule` as actual gates,
    UP TO AND INCLUDING output's first placement (its own schedule then
    uncomputes it again by construction -- P[n][T]=0 for every n including
    output -- so this function stops right after placing it, leaving it
    live for the caller to USE (e.g. a CZ against a paired factor), and
    returns a handle for `uncompute_from_schedule` to run the REMAINING
    moves afterward). Since the solver already proved the full schedule
    respects the ancilla budget and every dependency at every step, this is
    pure bookkeeping (which physical qubit currently holds which node) --
    no scheduling decisions are made here, only executed. Folds each
    node's own `invert_output` into consumers' polarity (never a physical
    post-gate X -- that breaks RCCX's self-inverse cancellation, see
    aig_synth.py's module docstring). The output's own inversion, if any,
    is reported via `.invert` for the caller to correct if this result
    feeds further AND logic (e.g. a GF(2)-factor CZ) rather than only a
    final global phase.
    """
    live: dict[str, int] = {}
    free = list(ancilla_qubits)

    # AND nodes: fold a fanin's own invert_output into THIS node's polarity
    # (never a physical post-gate X -- breaks RCCX's self-inverse
    # cancellation, see aig_synth.py's module docstring).
    # XOR nodes: fold into THIS node's own invert flag instead -- safe here
    # (verified: [CX(a,t);CX(b,t);X(t)] reapplied twice restores t=0
    # exactly; XOR has no RCCX-style relative phase to break) and simpler,
    # since XOR(NOT(a),b) = NOT(XOR(a,b)) toggles the OUTPUT directly,
    # unlike AND where an inverted fanin changes which VALUE the fanin must
    # match (polarity), not whether the whole node flips.
    effective_polarity: dict[str, tuple[int, int]] = {}
    effective_invert: dict[str, bool] = {}
    for name, node in nodes.items():
        f0, f1 = node.fanins
        if node.is_xor:
            toggle = node.invert_output
            if nodes.get(f0) and nodes[f0].invert_output:
                toggle = not toggle
            if nodes.get(f1) and nodes[f1].invert_output:
                toggle = not toggle
            effective_invert[name] = toggle
        else:
            p0, p1 = node.polarity
            if nodes.get(f0) and nodes[f0].invert_output:
                p0 ^= 1
            if nodes.get(f1) and nodes[f1].invert_output:
                p1 ^= 1
            effective_polarity[name] = (p0, p1)

    def emit(name: str, target: int) -> None:
        node = nodes[name]
        f0, f1 = node.fanins
        q0 = live.get(f0, input_qubit.get(f0))
        q1 = live.get(f1, input_qubit.get(f1))
        if node.is_xor:
            qc.cx(q0, target)
            qc.cx(q1, target)
            if effective_invert[name]:
                qc.x(target)
            return
        p0, p1 = effective_polarity[name]
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

    # Stop at the first point where output is live AND isolated (nothing
    # else live) -- NOT simply output's first placement. The CP-SAT model
    # only guarantees an isolated point exists somewhere at or after
    # output's placement (it CAN'T guarantee isolation AT the placement
    # instant -- that directly contradicts needing output's fanins live at
    # that same step to compute it). Stopping too early would hand the
    # caller a qubit set that still has other live values mixed in.
    moves = schedule.moves
    result_qubit = None
    i = 0
    for i, (name, placed) in enumerate(moves):
        if placed:
            q = free.pop()
            emit(name, q)
            live[name] = q
        else:
            q = live.pop(name)
            emit(name, q)
            free.append(q)
        if output in live and len(live) == 1:
            result_qubit = live[output]
            i += 1
            break
    assert result_qubit is not None, "schedule never reached an output-isolated state"

    # For an AND-type output, invert_output was never folded anywhere (it
    # has no consumer WITHIN this sub-AIG to fold into), so it must be
    # corrected here. For an XOR-type output, `emit()` already applied the
    # correction internally via `effective_invert` (folding in any of
    # output's OWN fanins' inversions too) -- applying it AGAIN here would
    # double it (net no-op), silently leaving the wrong value on
    # result_qubit whenever output itself has no inverted fanins (so the
    # two corrections aren't accidentally identical).
    invert = False if nodes[output].is_xor else nodes[output].invert_output
    if invert:
        qc.x(result_qubit)

    return PebbleCircuitResult(result_qubit=result_qubit, invert=invert,
                                _remaining_moves=moves[i:], _live=live, _free=free, _emit=emit)


def uncompute_from_schedule(qc: QuantumCircuit, result: PebbleCircuitResult) -> None:
    """Runs the rest of the schedule (everything after output's first
    placement), returning every ancilla -- including output's own qubit --
    to |0>."""
    if result.invert:
        qc.x(result.result_qubit)  # undo the corrective X, FIRST
    live, free, emit = result._live, result._free, result._emit
    for name, placed in result._remaining_moves:
        if placed:
            q = free.pop()
            emit(name, q)
            live[name] = q
        else:
            q = live.pop(name)
            emit(name, q)
            free.append(q)
