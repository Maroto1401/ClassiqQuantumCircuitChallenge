"""Ancilla-parallel lowering for GF(2)-factored PhaseIRs.

Requires a PhaseIR built by `cover='gf2_factor'` (needs `provenance['factors']`,
the per-factor u_k(y)/v_k(x) cube recipe -- the flattened `ir.terms` list alone
does not preserve which cubes belong to which factor).

IDEA. Each factor k contributes u_k(y) & v_k(x) to the XOR sum. u_k only
touches y-qubits, v_k only touches x-qubits -- disjoint registers -- so:

    1. compute u_k(y) into a fresh y-side ancilla (XOR-accumulate its ESOP
       cubes via MCX, X-conjugated for negated literals -- same pattern as
       `serial_mcz.emit_cube`, but targeting an ancilla instead of a data MCZ)
    2. compute v_k(x) into a fresh x-side ancilla, same way
    3. CZ the two ancillas together
    4. uncompute both (re-run steps 1-2: each is a self-inverse XOR toggle)

All CZs across a batch act on disjoint ancilla pairs, so they collapse to a
single depth layer, and step 1/2 run on disjoint qubit sets (y vs x) so they
overlap in time too. With `ancillas` clean ancillas available, `ancillas // 2`
factors are live at once; factors are processed in that many batches.
"""
from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.circuit.library import RCCXGate

from . import register
from ..ir import PhaseIR
from ..spec import N_DATA, N_X, N_Y


def _emit_indicator(qc: QuantumCircuit, cubes: list, qubits: list[int], target: int,
                     dirty: list[int] = (), relative_phase: bool = False,
                     reverse: bool = False) -> None:
    """XOR-accumulate an ESOP (list of (mask, value)) onto `target` via MCX.

    `dirty`: qubits NOT among `qubits`/`target` that are free to borrow as
    scratch for the multi-controlled-X decomposition (any state, restored
    exactly). Qiskit's ancilla-free MCX synthesis is very expensive (a
    6-control Toffoli: 124 CX); with even one borrowed dirty qubit it drops
    to 64 CX -- confirmed empirically, 2026-09-14. When computing an x-only
    indicator the y register is completely unused (and vice versa), so it's
    free scratch here at zero extra qubit cost.

    `relative_phase`: use RCCX (3 CX) instead of CCX (6 CX) for 2-literal
    cubes. Verified exact (full Operator comparison, not approximate) for
    this XOR-accumulate pattern -- BUT ONLY when the uncompute call
    processes cubes in REVERSED order (`reverse=True`): RCCX introduces
    relative phases that cancel correctly under reversed-order reapplication
    but NOT under same-order reapplication (confirmed broken: exact
    Operator diff of 2.0 -- see notes/DECISIONS.md 2026-09-14). Reversing
    cube order is always safe for the non-relative-phase gates too (plain
    XOR-accumulation is order-independent), so callers should pass
    `reverse=True` on every uncompute call regardless of `relative_phase`.
    Only applied to the 2-control case here; 3+ control cubes still use the
    (unverified-for-relative-phase) generic `mcx` path.
    """
    ordered = list(reversed(cubes)) if reverse else cubes
    for mask, value in ordered:
        lits = [i for i in range(len(qubits)) if (mask >> i) & 1]
        if not lits:
            qc.x(target)  # constant-1 cube: unconditional toggle
            continue
        negs = [i for i in lits if not ((value >> i) & 1)]
        for i in negs:
            qc.x(qubits[i])
        ctrl = [qubits[i] for i in lits]
        if len(ctrl) == 1:
            qc.cx(ctrl[0], target)
        elif len(ctrl) == 2:
            if relative_phase:
                qc.append(RCCXGate(), [ctrl[0], ctrl[1], target])
            else:
                qc.ccx(ctrl[0], ctrl[1], target)
        elif dirty:
            qc.mcx(ctrl, target, ancilla_qubits=list(dirty), mode="recursion")
        else:
            qc.mcx(ctrl, target)
        for i in negs:
            qc.x(qubits[i])


@register("gf2_ancilla")
def lower(ir: PhaseIR, width: int | None = None, ancillas: int = 6, **params) -> QuantumCircuit:
    if not ir.pre.is_identity:
        raise NotImplementedError("non-identity AffinePre lowering not implemented yet")
    factors = ir.provenance.get("factors")
    if not factors:
        raise ValueError(
            "gf2_ancilla requires a PhaseIR from cover='gf2_factor' "
            "(missing provenance['factors'])"
        )
    pairs = max(1, ancillas // 2)
    if width is not None and N_DATA + 2 * pairs > width:
        pairs = max(1, (width - N_DATA) // 2)

    n_anc = 2 * pairs
    qc = QuantumCircuit(N_DATA + n_anc, name="oracle_gf2_ancilla")
    x_qubits = list(range(N_X))
    y_qubits = list(range(N_X, N_DATA))

    for batch_start in range(0, len(factors), pairs):
        batch = factors[batch_start: batch_start + pairs]
        u_anc = [N_DATA + 2 * i for i in range(len(batch))]
        v_anc = [N_DATA + 2 * i + 1 for i in range(len(batch))]

        for f, ua, va in zip(batch, u_anc, v_anc):
            _emit_indicator(qc, f["u_cubes"], y_qubits, ua, relative_phase=True)
            _emit_indicator(qc, f["v_cubes"], x_qubits, va, relative_phase=True)

        for ua, va in zip(u_anc, v_anc):
            qc.cz(ua, va)

        for f, ua, va in zip(batch, u_anc, v_anc):
            _emit_indicator(qc, f["u_cubes"], y_qubits, ua, relative_phase=True, reverse=True)
            _emit_indicator(qc, f["v_cubes"], x_qubits, va, relative_phase=True, reverse=True)

    return qc
