"""PhaseIR -- the cut point of the pipeline.

This is the single most important abstraction in the repo. Everything expensive
(ESOP minimisation, basis search, factorisation) happens ABOVE this line and is
cached. Everything cheap (decomposition, scheduling, transpilation, metrics)
happens BELOW it and is re-runnable for free.

Semantics of a PhaseIR:

    f(v) = XOR over terms t of [ v matches t ]         (v = 12 data bits, after `pre`)
    oracle |v> = (-1)^f(v) |v>

`pre` is an optional affine pre-map v -> A v XOR b applied by a CNOT/X network
before the terms are evaluated (symmetry folds, GL(12,2) basis changes). Terms
XOR together, so they commute and may be reordered freely by the scheduler --
that freedom is what the depth-oriented lowerings exploit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict

import numpy as np

from .spec import DIM, N_DATA


@dataclass(frozen=True)
class Cube:
    """A product term. `mask` selects fixed variables, `value` gives their required values.

    Literal count = popcount(mask). A cube with mask=0 is the constant 1 term
    (global phase, free).
    """

    mask: int
    value: int

    def __post_init__(self) -> None:
        if self.value & ~self.mask:
            raise ValueError("value has bits set outside mask")

    @property
    def n_literals(self) -> int:
        return bin(self.mask).count("1")

    @property
    def n_covered(self) -> int:
        return 1 << (N_DATA - self.n_literals)

    def matches(self, v: int) -> bool:
        return (v & self.mask) == self.value

    def as_tuple(self) -> tuple[int, int]:
        return (self.mask, self.value)


@dataclass(frozen=True)
class AffinePre:
    """v -> (A @ v) XOR b over GF(2). Identity by default. Cost: a CNOT+X network."""

    rows: tuple[int, ...] = tuple(1 << i for i in range(N_DATA))  # A as bitmask rows
    offset: int = 0

    @property
    def is_identity(self) -> bool:
        return self.offset == 0 and self.rows == tuple(1 << i for i in range(N_DATA))

    def apply(self, v: int) -> int:
        out = 0
        for i, r in enumerate(self.rows):
            out |= (bin(r & v).count("1") & 1) << i
        return out ^ self.offset


@dataclass
class PhaseIR:
    """A synthesis-independent description of the oracle's phase function."""

    terms: list[Cube]
    pre: AffinePre = field(default_factory=AffinePre)
    provenance: dict = field(default_factory=dict)

    # -- cost proxies (cheap, pre-lowering; used to rank covers) ------------
    @property
    def n_terms(self) -> int:
        return len(self.terms)

    @property
    def n_literals(self) -> int:
        return sum(c.n_literals for c in self.terms)

    @property
    def max_literals(self) -> int:
        return max((c.n_literals for c in self.terms), default=0)

    @property
    def literal_histogram(self) -> dict[int, int]:
        h: dict[int, int] = {}
        for c in self.terms:
            h[c.n_literals] = h.get(c.n_literals, 0) + 1
        return dict(sorted(h.items()))

    # -- exactness ---------------------------------------------------------
    def evaluate(self) -> np.ndarray:
        """Full 4096-entry truth table implied by this IR. Vectorised."""
        v = np.arange(DIM, dtype=np.uint16)
        w = self._apply_pre_vec(v)
        out = np.zeros(DIM, dtype=np.uint8)
        for c in self.terms:
            out ^= ((w & np.uint16(c.mask)) == np.uint16(c.value)).astype(np.uint8)
        return out

    def _apply_pre_vec(self, v: np.ndarray) -> np.ndarray:
        if self.pre.is_identity:
            return v
        out = np.zeros_like(v)
        for i, r in enumerate(self.pre.rows):
            par = np.zeros_like(v)
            rr = r
            bit = 0
            while rr:
                if rr & 1:
                    par ^= (v >> np.uint16(bit)) & np.uint16(1)
                rr >>= 1
                bit += 1
            out |= par << np.uint16(i)
        return out ^ np.uint16(self.pre.offset)

    @property
    def ir_hash(self) -> str:
        payload = {
            "terms": sorted(c.as_tuple() for c in self.terms),
            "rows": list(self.pre.rows),
            "offset": self.pre.offset,
        }
        h = hashlib.sha256(b"qoracle-ir-v1")
        h.update(json.dumps(payload, sort_keys=True).encode())
        return h.hexdigest()[:16]

    def summary(self) -> dict:
        return {
            "ir_hash": self.ir_hash,
            "n_terms": self.n_terms,
            "n_literals": self.n_literals,
            "max_literals": self.max_literals,
            "literal_histogram": self.literal_histogram,
            "pre_identity": self.pre.is_identity,
            "provenance": self.provenance,
        }

    def to_json(self) -> str:
        return json.dumps(
            {
                "terms": [c.as_tuple() for c in self.terms],
                "pre": asdict(self.pre),
                "provenance": self.provenance,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, s: str) -> "PhaseIR":
        d = json.loads(s)
        pre = AffinePre(rows=tuple(d["pre"]["rows"]), offset=d["pre"]["offset"])
        return cls([Cube(m, v) for m, v in d["terms"]], pre, d.get("provenance", {}))
