"""Lowering strategies: PhaseIR -> QuantumCircuit. The cheap, re-runnable half.

Adding a lowering NEVER invalidates a cover. That separation is the whole point
of the PhaseIR cut: a new depth idea costs one `qo lower` run, not a re-minimisation.
"""
from __future__ import annotations

from typing import Callable

_REGISTRY: dict[str, Callable] = {}


def register(name: str) -> Callable:
    def deco(fn):
        fn.name = name
        _REGISTRY[name] = fn
        return fn
    return deco


def get(name: str) -> Callable:
    if name not in _REGISTRY:
        raise KeyError(f"unknown lowering '{name}'. available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def available() -> list[str]:
    return sorted(_REGISTRY)


from . import serial_mcz, gf2_ancilla, rect_ancilla, gf2_cpsat_hybrid  # noqa: E402,F401
