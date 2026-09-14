"""Cover strategies: OracleSpec -> PhaseIR. The expensive, cached half."""
from __future__ import annotations

from typing import Callable, Protocol

from ..ir import PhaseIR
from ..spec import OracleSpec

_REGISTRY: dict[str, "CoverStrategy"] = {}


class CoverStrategy(Protocol):
    name: str

    def __call__(self, spec: OracleSpec, **params) -> PhaseIR: ...


def register(name: str) -> Callable:
    def deco(fn):
        fn.name = name
        _REGISTRY[name] = fn
        return fn
    return deco


def get(name: str) -> "CoverStrategy":
    if name not in _REGISTRY:
        raise KeyError(f"unknown cover '{name}'. available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def available() -> list[str]:
    return sorted(_REGISTRY)


from . import minterm, pprm, esop_abc  # noqa: E402,F401
