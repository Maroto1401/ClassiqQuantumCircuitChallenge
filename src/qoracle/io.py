"""Target loading. Accepts .npy / .txt / image files, plus a synthetic stand-in
so the whole pipeline is exercisable before the real logo arrives."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .spec import N_X, N_Y, OracleSpec


def load_target(path: str | Path, name: str | None = None) -> OracleSpec:
    p = Path(path)
    if p.suffix == ".npy":
        img = np.load(p)
    elif p.suffix in (".txt", ".csv"):
        img = np.loadtxt(p, dtype=int, delimiter="," if p.suffix == ".csv" else None)
    else:
        try:
            from PIL import Image  # optional dependency
        except ImportError as e:
            raise RuntimeError(f"install pillow to read {p.suffix} files") from e
        img = np.array(Image.open(p).convert("L"))
        img = (img < 128).astype(np.uint8)  # dark pixels = marked; CONFIRM polarity
    return OracleSpec.from_image(img, name=name or p.stem)


def synthetic_target(n_marked: int = 1097, seed: int = 0) -> OracleSpec:
    """Placeholder with the right shape, density AND mirror symmetry, so the
    diagnostics and covers get exercised on something structurally plausible.
    Replace with the real logo the moment it lands."""
    rng = np.random.default_rng(seed)
    h, w = 1 << N_Y, 1 << N_X
    img = np.zeros((h, w), dtype=np.uint8)
    img[10:54, 10:18] = 1          # strokes
    img[10:18, 10:54] = 1
    img[28:36, 18:46] = 1
    yy, xx = np.mgrid[0:h, 0:w]    # a ring
    r = np.hypot(yy - 32, xx - 32)
    img[(r > 20) & (r < 24)] = 1
    img = img | img[:, ::-1]       # force mirror-x symmetry
    cur = int(img.sum())
    idx = np.flatnonzero(img == 0) if cur < n_marked else np.flatnonzero(img == 1)
    pick = rng.choice(idx, size=abs(n_marked - cur), replace=False)
    flat = img.reshape(-1)
    flat[pick] ^= 1
    return OracleSpec.from_image(flat.reshape(h, w), name="synthetic")
