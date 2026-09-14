"""Content-addressed artifact store.

Layout:
    data/artifacts/ir/<ir_key>/{ir.json, manifest.json}
    data/artifacts/circuit/<circ_key>/{circuit.qpy, manifest.json, metrics.json, verify.json}

The CANONICAL stored circuit is QPY at the HIGH level (multi-controlled gates
intact), not QASM. This matters: re-scoring under a new basis then re-transpiles
from the structured form, which is strictly better than re-transpiling an
already-decomposed circuit. QASM is an EXPORT, produced on demand by
`qoracle.export`, never the source of truth.
    data/artifacts/diag/<spec_hash>.json

Keys are hashes of (inputs + params + stage code version). Bumping COVER_VERSION
invalidates covers WITHOUT touching lowerings, and vice versa -- that is why the
two versions are separate constants.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from qiskit import QuantumCircuit, qpy

from .ir import PhaseIR
from .version import COVER_VERSION, LOWER_VERSION, DIAG_VERSION


def _key(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode())
        h.update(b"|")
    return h.hexdigest()[:16]


def ir_key(spec_hash: str, cover: str, params: dict) -> str:
    return _key("ir", spec_hash, cover, params, COVER_VERSION)


def circuit_key(ir_hash: str, lowering: str, params: dict) -> str:
    return _key("circ", ir_hash, lowering, params, LOWER_VERSION)


@dataclass
class Store:
    root: Path = Path("data/artifacts")

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        for sub in ("ir", "circuit", "diag"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- diagnostics -------------------------------------------------------
    def diag_path(self, spec_hash: str) -> Path:
        return self.root / "diag" / f"{spec_hash}-{DIAG_VERSION}.json"

    def save_diag(self, spec_hash: str, data: dict) -> Path:
        p = self.diag_path(spec_hash)
        p.write_text(json.dumps(data, indent=2, default=str))
        return p

    def load_diag(self, spec_hash: str) -> dict | None:
        p = self.diag_path(spec_hash)
        return json.loads(p.read_text()) if p.exists() else None

    # -- IR ----------------------------------------------------------------
    def ir_dir(self, key: str) -> Path:
        return self.root / "ir" / key

    def has_ir(self, key: str) -> bool:
        return (self.ir_dir(key) / "ir.json").exists()

    def save_ir(self, key: str, ir: PhaseIR, manifest: dict) -> Path:
        d = self.ir_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        (d / "ir.json").write_text(ir.to_json())
        manifest = {**manifest, "saved_at": time.time(), "summary": ir.summary()}
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        return d

    def load_ir(self, key: str) -> PhaseIR:
        return PhaseIR.from_json((self.ir_dir(key) / "ir.json").read_text())

    # -- circuits ----------------------------------------------------------
    def circ_dir(self, key: str) -> Path:
        return self.root / "circuit" / key

    def has_circuit(self, key: str) -> bool:
        return (self.circ_dir(key) / "circuit.qpy").exists()

    def save_circuit(self, key: str, qc: QuantumCircuit, manifest: dict) -> Path:
        d = self.circ_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "circuit.qpy", "wb") as fh:
            qpy.dump(qc, fh)
        (d / "manifest.json").write_text(
            json.dumps({**manifest, "saved_at": time.time()}, indent=2, default=str)
        )
        return d

    def load_circuit(self, key: str) -> QuantumCircuit:
        with open(self.circ_dir(key) / "circuit.qpy", "rb") as fh:
            return qpy.load(fh)[0]

    def write_side(self, key: str, name: str, data: dict) -> None:
        (self.circ_dir(key) / name).write_text(json.dumps(data, indent=2, default=str))

    def read_side(self, key: str, name: str) -> dict | None:
        p = self.circ_dir(key) / name
        return json.loads(p.read_text()) if p.exists() else None

    def all_circuits(self) -> list[str]:
        return sorted(p.name for p in (self.root / "circuit").iterdir() if p.is_dir())
