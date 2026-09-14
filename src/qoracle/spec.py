"""Problem instance: the target image as a 12-bit Boolean function.

CONVENTION (single source of truth -- confirm against the scorer before submitting):

    index = (y << N_X) | x              # 12-bit basis-state label
    qubit q[0..5]   = x_0 .. x_5        # x register, LSB first
    qubit q[6..11]  = y_0 .. y_5        # y register, LSB first
    qubits q[12..]  = ancillas (must be returned to |0>)

Everything downstream imports these helpers. Never hand-roll bit order elsewhere.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

N_X = 6
N_Y = 6
N_DATA = N_X + N_Y
DIM = 1 << N_DATA

X_QUBITS = tuple(range(0, N_X))
Y_QUBITS = tuple(range(N_X, N_DATA))


@dataclass(frozen=True)
class OracleSpec:
    """A phase oracle target. Immutable, content-addressed."""

    truth: np.ndarray  # uint8, shape (DIM,), 1 = marked pixel (phase flip)
    name: str = "target"
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.truth.shape != (DIM,):
            raise ValueError(f"truth must have shape ({DIM},), got {self.truth.shape}")
        if self.truth.dtype != np.uint8:
            raise ValueError("truth must be uint8")
        if not np.isin(self.truth, (0, 1)).all():
            raise ValueError("truth must be binary")

    @classmethod
    def from_image(cls, img: np.ndarray, name: str = "target") -> "OracleSpec":
        """img[y, x] != 0 marks a pixel."""
        img = np.asarray(img)
        if img.shape != (1 << N_Y, 1 << N_X):
            raise ValueError(f"expected ({1 << N_Y},{1 << N_X}) image, got {img.shape}")
        return cls(truth=(img.reshape(-1) != 0).astype(np.uint8), name=name)

    def to_image(self) -> np.ndarray:
        return self.truth.reshape(1 << N_Y, 1 << N_X)

    @property
    def spec_hash(self) -> str:
        h = hashlib.sha256()
        h.update(b"qoracle-spec-v1")
        h.update(self.truth.tobytes())
        return h.hexdigest()[:16]

    @property
    def n_marked(self) -> int:
        return int(self.truth.sum())

    def __repr__(self) -> str:
        return f"OracleSpec({self.name}, marked={self.n_marked}/{DIM}, hash={self.spec_hash})"


def xy_to_index(x: int, y: int) -> int:
    return (y << N_X) | x


def index_to_xy(idx: int) -> tuple[int, int]:
    return idx & ((1 << N_X) - 1), idx >> N_X


def index_to_bits(idx: int) -> tuple[int, ...]:
    """LSB-first bit tuple aligned with qubit order q[0..11]."""
    return tuple((idx >> i) & 1 for i in range(N_DATA))
