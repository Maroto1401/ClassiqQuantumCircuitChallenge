from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


Grid = Sequence[Sequence[int]]


@dataclass(frozen=True)
class Gate:
    """A logical quantum gate over one or two qubits."""

    name: str
    qubits: Tuple[int, ...]


@dataclass(frozen=True)
class ScheduledGate:
    """A gate scheduled at a specific circuit layer."""

    gate: Gate
    layer: int


@dataclass(frozen=True)
class Circuit:
    """A lightweight circuit representation focused on depth accounting."""

    qubit_count: int
    gates: Tuple[ScheduledGate, ...]

    @property
    def depth(self) -> int:
        if not self.gates:
            return 0
        return max(g.layer for g in self.gates) + 1


def _active_pixels(pixels: Grid) -> List[Tuple[int, int]]:
    active: List[Tuple[int, int]] = []
    for row_index, row in enumerate(pixels):
        for col_index, value in enumerate(row):
            if value:
                active.append((row_index, col_index))
    return active


def _flatten_index(row: int, col: int, width: int) -> int:
    return row * width + col


def build_logo_gates(pixels: Grid) -> Tuple[int, List[Gate]]:
    """Build logical gates for an image-based quantum logo encoding."""

    if not pixels or not pixels[0]:
        return 0, []

    height = len(pixels)
    width = len(pixels[0])
    qubit_count = height * width

    active = set(_active_pixels(pixels))
    gates: List[Gate] = []

    for row, col in sorted(active):
        gates.append(Gate("H", (_flatten_index(row, col, width),)))

    for row, col in sorted(active):
        right = (row, col + 1)
        down = (row + 1, col)

        if right in active:
            control = _flatten_index(row, col, width)
            target = _flatten_index(row, col + 1, width)
            gates.append(Gate("CX", (control, target)))

        if down in active:
            control = _flatten_index(row, col, width)
            target = _flatten_index(row + 1, col, width)
            gates.append(Gate("CX", (control, target)))

    return qubit_count, gates


def _schedule_sequential(gates: Iterable[Gate]) -> Tuple[ScheduledGate, ...]:
    return tuple(ScheduledGate(gate=gate, layer=index) for index, gate in enumerate(gates))


def _schedule_depth_optimized(gates: Iterable[Gate]) -> Tuple[ScheduledGate, ...]:
    scheduled: List[ScheduledGate] = []
    layer_usage: List[set[int]] = []

    for gate in gates:
        layer = 0
        qubit_set = set(gate.qubits)

        while True:
            if layer == len(layer_usage):
                layer_usage.append(set())

            if qubit_set.isdisjoint(layer_usage[layer]):
                layer_usage[layer].update(qubit_set)
                scheduled.append(ScheduledGate(gate=gate, layer=layer))
                break

            layer += 1

    return tuple(scheduled)


def build_naive_logo_circuit(pixels: Grid) -> Circuit:
    qubit_count, gates = build_logo_gates(pixels)
    return Circuit(qubit_count=qubit_count, gates=_schedule_sequential(gates))


def build_optimized_logo_circuit(pixels: Grid) -> Circuit:
    qubit_count, gates = build_logo_gates(pixels)
    return Circuit(qubit_count=qubit_count, gates=_schedule_depth_optimized(gates))
