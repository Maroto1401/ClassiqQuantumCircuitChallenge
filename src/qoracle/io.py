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
    Superseded by `logo_target()` now that the real logo formula is known --
    kept only so old cached artifacts and tests stay reproducible."""
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


def logo_pixel(x: int, y: int) -> bool:
    """Exact black-pixel predicate for the Classiq logo, ported verbatim from
    `classiq-challenge-baseline.ipynb` (cell 4). Two axis-aligned rectangles
    unioned with two discs; 1097 True pixels over the 64x64 grid."""
    return (
        (2 <= x <= 26 and 29 <= y <= 53)
        or (26 <= x <= 49 and 39 <= y <= 43)
        or (x - 55) ** 2 + (y - 41) ** 2 <= 42
        or (x - 40) ** 2 + (y - 19) ** 2 <= 72
    )


def _intervals_for_row(grid: int, y: int) -> tuple[tuple[int, int], ...]:
    xs = [x for x in range(grid) if logo_pixel(x, y)]
    if not xs:
        return ()
    intervals: list[tuple[int, int]] = []
    start = end = xs[0]
    for x in xs[1:]:
        if x == end + 1:
            end = x
        else:
            intervals.append((start, end))
            start = end = x
    intervals.append((start, end))
    return tuple(intervals)


def logo_rectangles(grid: int = 1 << N_X) -> tuple[tuple[int, int, int, int], ...]:
    """Disjoint (x_min, x_max, y_min, y_max) rectangle cover of the logo, ported
    from the baseline's `merge_equal_intervals()`. This is the baseline's own
    (unoptimized) cover strategy -- useful as a reference/upper bound, not
    something our cover stage must reuse."""
    active: dict[tuple[int, int], int] = {}
    rectangles: list[tuple[int, int, int, int]] = []
    for y in range(grid + 1):
        intervals = set(_intervals_for_row(grid, y)) if y < grid else set()
        for interval, y_min in tuple(active.items()):
            if interval not in intervals:
                rectangles.append((*interval, y_min, y - 1))
                del active[interval]
        for interval in intervals:
            active.setdefault(interval, y)
    return tuple(sorted(rectangles, key=lambda block: (block[2], block[0])))


def logo_target() -> OracleSpec:
    """The real challenge target: the Classiq logo, 1097/4096 marked pixels."""
    h, w = 1 << N_Y, 1 << N_X
    img = np.array([[logo_pixel(x, y) for x in range(w)] for y in range(h)], dtype=np.uint8)
    if img.sum() != 1097:
        raise RuntimeError(f"logo_target must have 1097 marked pixels, got {img.sum()}")
    return OracleSpec.from_image(img, name="logo")
