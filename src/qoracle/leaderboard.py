"""Aggregate every stored circuit into a ranked table.

Reads ONLY from the artifact store, so `qo leaderboard` after `qo score --basis X`
re-ranks everything under a new basis without re-synthesising anything.
"""
from __future__ import annotations

from .metrics import DEFAULT_BASIS
from .store import Store


def rows(store: Store, basis: str = DEFAULT_BASIS) -> list[dict]:
    out = []
    for key in store.all_circuits():
        man = store.read_side(key, "manifest.json") or {}
        met = (store.read_side(key, "metrics.json") or {}).get(basis)
        ver = store.read_side(key, "verify.json") or {}
        out.append({
            "key": key,
            "cover": (man.get("ir_summary", {}).get("provenance", {}) or {}).get("cover", "?"),
            "lowering": man.get("lowering", "?"),
            "terms": man.get("ir_summary", {}).get("n_terms"),
            "literals": man.get("ir_summary", {}).get("n_literals"),
            "verified": ver.get("ok"),
            "depth": (met or {}).get("depth"),
            "cx": (met or {}).get("cx"),
            "width": (met or {}).get("width"),
            "basis": basis,
        })
    ok = [r for r in out if r["verified"] and r["depth"] is not None]
    rest = [r for r in out if r not in ok]
    ok.sort(key=lambda r: (r["depth"], r["cx"]))
    return ok + rest


def render(store: Store, basis: str = DEFAULT_BASIS) -> str:
    rs = rows(store, basis)
    if not rs:
        return "(no artifacts yet)"
    hdr = f"{'#':<3} {'cover':<10} {'lowering':<12} {'terms':>6} {'lits':>6} {'depth':>7} {'cx':>7} {'w':>3} {'ok':>3}"
    lines = [f"basis = {basis}   (rank: depth, then cx)", hdr, "-" * len(hdr)]
    for i, r in enumerate(rs, 1):
        lines.append(
            f"{i:<3} {str(r['cover']):<10} {str(r['lowering']):<12} "
            f"{str(r['terms']):>6} {str(r['literals']):>6} {str(r['depth']):>7} "
            f"{str(r['cx']):>7} {str(r['width']):>3} {'Y' if r['verified'] else 'N':>3}"
        )
    return "\n".join(lines)
