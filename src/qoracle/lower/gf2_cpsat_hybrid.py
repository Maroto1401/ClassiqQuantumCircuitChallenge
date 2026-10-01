"""Per-factor AIG+RCCX lowering for `cover='gf2_factor'`, scheduled via
CP-SAT (pebble_cpsat.py) instead of the hand-rolled `_BeladyScheduler` in
aig_synth.py. That heuristic scheduler broke on integration (11th bug of
the session: a "hole" in the available-qubit list corrupted a v_i build)
and only found feasible schedules for 15/20 of the real logo's GF(2)-factor
sub-functions at scratch=5.

CP-SAT, with the correct model (see pebble_cpsat.py -- an "output isolated"
requirement was needed for THIS integration specifically, since one
sub-AIG's result must sit alone in the shared ancilla pool before a second
sub-AIG starts using it; the naive version of that constraint was itself a
real modeling bug, fixed and documented there), solves 17/20 at ancillas=5.
The remaining 3 (factor 6/7/8's v_i) are genuinely, quickly infeasible at
that budget -- not slow searches, confirmed infeasible in 1-2s each -- and
fall back to the existing, independently-verified ESOP-cube approach
(`gf2_ancilla._emit_indicator`), which needs no separate scratch pool at
all (XOR-accumulates directly into one target ancilla, using the data
qubits as controls).

Schedules are solved ONCE and cached to disk (next to this file) since each
CP-SAT solve costs up to ~45s -- without caching, every pipeline run would
re-pay that cost.

SEQUENTIAL: one factor at a time, using all 6 ancilla for whichever factor
is current (5 scratch for whichever sub-AIG is actively building via
CP-SAT, 1 reserved for the other side's already-computed result; the ESOP
fallback needs only its own 1 target ancilla, no scratch).
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit

from . import register
from .gf2_ancilla import _emit_indicator
from ..aig_synth import synthesize_small_aig_blif, parse_blif
from ..ir import PhaseIR
from ..pebble_cpsat import solve_pebbling, build_from_schedule, uncompute_from_schedule
from ..spec import N_DATA, N_X, N_Y

_CACHE_PATH = Path(__file__).parent / "_gf2_cpsat_schedule_cache.pkl"


def _cubes_to_truth(cubes: list, n: int) -> np.ndarray:
    truth = np.zeros(1 << n, dtype=np.uint8)
    for x in range(1 << n):
        val = 0
        for mask, value in cubes:
            if all(((x >> i) & 1) == ((value >> i) & 1) for i in range(n) if (mask >> i) & 1):
                val ^= 1
        truth[x] = val
    return truth


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        with open(_CACHE_PATH, "rb") as fh:
            return pickle.load(fh)
    return {}


def _save_cache(cache: dict) -> None:
    with open(_CACHE_PATH, "wb") as fh:
        pickle.dump(cache, fh)


def _get_aig_and_schedule(truth: np.ndarray, n: int, ancillas: int, cache_key: tuple,
                           cache: dict, horizon: int = 100, time_limit_s: float = 45.0):
    if cache_key in cache:
        return cache[cache_key]
    blif = synthesize_small_aig_blif(truth, n)
    if blif is None:
        result = ("constant0", None, None, None)
    else:
        inputs, output, nodes = parse_blif(blif)
        if not nodes:
            result = ("degenerate", inputs, output, nodes)
        else:
            sched = solve_pebbling(nodes, output, set(inputs), ancillas=ancillas,
                                    horizon=horizon, time_limit_s=time_limit_s)
            if sched is None:
                result = ("infeasible", inputs, output, nodes)
            else:
                result = ("scheduled", inputs, output, nodes, sched)
    cache[cache_key] = result
    _save_cache(cache)
    return result


@register("gf2_cpsat_hybrid")
def lower(ir: PhaseIR, width: int | None = None, ancillas: int = 6, **params) -> QuantumCircuit:
    if not ir.pre.is_identity:
        raise NotImplementedError("non-identity AffinePre lowering not implemented yet")
    factors = ir.provenance.get("factors")
    if not factors:
        raise ValueError(
            "gf2_cpsat_hybrid requires a PhaseIR from cover='gf2_factor' "
            "(missing provenance['factors'])"
        )
    if ancillas < 2:
        raise ValueError("gf2_cpsat_hybrid needs at least 2 ancillas")

    x_qubits = list(range(N_X))
    y_qubits = list(range(N_X, N_DATA))
    all_anc = list(range(N_DATA, N_DATA + ancillas))

    cache = _load_cache()
    qc = QuantumCircuit(N_DATA + ancillas, name="oracle_gf2_cpsat_hybrid")

    for fi, f in enumerate(factors):
        u_truth = _cubes_to_truth(f["u_cubes"], N_Y)
        v_truth = _cubes_to_truth(f["v_cubes"], N_X)

        u_truth_key = tuple(u_truth.tolist())
        v_truth_key = tuple(v_truth.tolist())

        # Whichever side is computed FIRST gets the full `ancillas` budget
        # (nothing else alive yet to compete for it); the second side is
        # capped at ancillas-1 (1 qubit is held by the first side's result).
        # u_i is confirmed feasible at ancillas-1 for every factor, but v_i
        # is not (a few factors are only solvable if v_i itself goes first
        # with the full budget) -- and even where BOTH orderings work,
        # CP-SAT's move-minimizing objective can land on a cheaper total
        # either way, not always u-first (confirmed 2026-09-16: mixed
        # results across factors, u-first cheaper for some, v-first for
        # others, ties for the rest). So actually solve both candidate
        # schedules for whichever sides are cheap to check from cache and
        # use whichever ordering has the smaller total move count -- or
        # whichever is even feasible, if only one is.
        u6_info = _get_aig_and_schedule(u_truth, N_Y, ancillas, ("u6", fi, u_truth_key), cache)
        v5_info = _get_aig_and_schedule(v_truth, N_X, ancillas - 1, ("v", fi, v_truth_key), cache)
        u_first_total = None
        if u6_info[0] == "scheduled" and v5_info[0] == "scheduled":
            u_first_total = len(u6_info[4].moves) + len(v5_info[4].moves)

        v6_entry = cache.get(("v6", fi, v_truth_key)) or cache.get(("ancilla6", ("v", fi, v_truth_key)))
        u5_info = _get_aig_and_schedule(u_truth, N_Y, ancillas - 1, ("u", fi, u_truth_key), cache)
        v_first_total = None
        if v6_entry is not None and v6_entry[0] == "scheduled" and u5_info[0] == "scheduled":
            v_first_total = len(v6_entry[4].moves) + len(u5_info[4].moves)

        use_v_first = v_first_total is not None and (u_first_total is None or v_first_total < u_first_total)

        if use_v_first:
            _, v_inputs, v_output, v_nodes, v_sched = v6_entry
            v_input_qubit = {name: x_qubits[i] for i, name in enumerate(v_inputs)}
            v_res = build_from_schedule(qc, v_nodes, v_output, v_input_qubit, all_anc, v_sched,
                                         relative_phase=True)
            qv = v_res.result_qubit

            u_pool = [a for a in all_anc if a not in v_res.live_qubits]
            u_info = u5_info
            if u_info[0] == "scheduled":
                _, u_inputs, u_output, u_nodes, u_sched = u_info
                u_input_qubit = {name: y_qubits[i] for i, name in enumerate(u_inputs)}
                u_res = build_from_schedule(qc, u_nodes, u_output, u_input_qubit, u_pool, u_sched,
                                             relative_phase=True)
                qu = u_res.result_qubit
            elif u_info[0] == "degenerate":
                u_res = None
                _, u_inputs, u_output, _ = u_info
                u_input_qubit = {name: y_qubits[i] for i, name in enumerate(u_inputs)}
                qu = u_input_qubit[u_output]
            else:  # constant0 or infeasible -- not observed for any factor's u_i, but handle safely
                u_res = None
                if u_info[0] == "constant0":
                    uncompute_from_schedule(qc, v_res)
                    continue
                qu = u_pool[0]
                _emit_indicator(qc, f["u_cubes"], y_qubits, qu, relative_phase=True)

            qc.cz(qu, qv)

            if u_res is not None:
                uncompute_from_schedule(qc, u_res)
            elif u_info[0] == "infeasible":
                _emit_indicator(qc, f["u_cubes"], y_qubits, qu, relative_phase=True, reverse=True)
            uncompute_from_schedule(qc, v_res)
            continue

        # u-first ordering (either the only feasible one, or the cheaper of
        # the two): u_i gets the full ancillas budget since nothing else is
        # alive yet; v_i gets the remaining ancillas-1 afterward.
        u_info = u6_info
        u_res = None
        if u_info[0] == "scheduled":
            _, u_inputs, u_output, u_nodes, u_sched = u_info
            u_input_qubit = {name: y_qubits[i] for i, name in enumerate(u_inputs)}
            u_scratch = all_anc[:ancillas]
            u_res = build_from_schedule(qc, u_nodes, u_output, u_input_qubit, u_scratch, u_sched,
                                         relative_phase=True)
            qu = u_res.result_qubit
        elif u_info[0] == "degenerate":
            _, u_inputs, u_output, _ = u_info
            u_input_qubit = {name: y_qubits[i] for i, name in enumerate(u_inputs)}
            qu = u_input_qubit[u_output]
        elif u_info[0] == "constant0":
            continue  # entire factor contributes nothing
        else:  # infeasible -- ESOP-cube fallback, no scratch pool needed
            qu = all_anc[0]
            _emit_indicator(qc, f["u_cubes"], y_qubits, qu, relative_phase=True)

        # Exclude EVERY qubit still live from u_i's build, not just qu -- the
        # CP-SAT "isolated" constraint guarantees this is just {qu}, but the
        # ESOP fallback also only ever occupies the single qu qubit, so this
        # is correct either way.
        u_still_live = u_res.live_qubits if u_res is not None else {qu}
        v_pool = [a for a in all_anc if a not in u_still_live]

        v_info = v5_info
        v_res = None
        if v_info[0] == "scheduled":
            _, v_inputs, v_output, v_nodes, v_sched = v_info
            v_input_qubit = {name: x_qubits[i] for i, name in enumerate(v_inputs)}
            v_res = build_from_schedule(qc, v_nodes, v_output, v_input_qubit, v_pool, v_sched,
                                         relative_phase=True)
            qv = v_res.result_qubit
        elif v_info[0] == "degenerate":
            _, v_inputs, v_output, _ = v_info
            v_input_qubit = {name: x_qubits[i] for i, name in enumerate(v_inputs)}
            qv = v_input_qubit[v_output]
        elif v_info[0] == "constant0":
            if u_res is not None:
                uncompute_from_schedule(qc, u_res)
            elif u_info[0] != "degenerate":
                _emit_indicator(qc, f["u_cubes"], y_qubits, qu, relative_phase=True, reverse=True)
            continue
        else:  # infeasible -- ESOP-cube fallback
            qv = v_pool[0]
            _emit_indicator(qc, f["v_cubes"], x_qubits, qv, relative_phase=True)

        qc.cz(qu, qv)

        if v_res is not None:
            uncompute_from_schedule(qc, v_res)
        elif v_info[0] == "infeasible":
            _emit_indicator(qc, f["v_cubes"], x_qubits, qv, relative_phase=True, reverse=True)

        if u_res is not None:
            uncompute_from_schedule(qc, u_res)
        elif u_info[0] == "infeasible":
            _emit_indicator(qc, f["u_cubes"], y_qubits, qu, relative_phase=True, reverse=True)

    return qc
