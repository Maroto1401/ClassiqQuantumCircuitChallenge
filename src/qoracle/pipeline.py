"""Orchestration. Each stage checks the cache, runs only if needed, and records
timing + provenance so a result can always be traced back to what produced it."""
from __future__ import annotations

import time
from dataclasses import dataclass

from qiskit import QuantumCircuit

from . import cover as cover_mod
from . import lower as lower_mod
from . import diagnostics, metrics as metrics_mod
from .ir import PhaseIR
from .spec import OracleSpec
from .store import Store, circuit_key, ir_key
from .verify import verify, verify_ir


@dataclass
class Pipeline:
    spec: OracleSpec
    store: Store

    # -- stage 1 -----------------------------------------------------------
    def diagnostics(self, force: bool = False) -> dict:
        cached = None if force else self.store.load_diag(self.spec.spec_hash)
        if cached:
            return cached
        t0 = time.time()
        data = diagnostics.run_all(self.spec)
        data["elapsed_s"] = time.time() - t0
        self.store.save_diag(self.spec.spec_hash, data)
        return data

    # -- stage 2: expensive, cached ---------------------------------------
    def build_ir(self, cover: str, params: dict | None = None,
                 force: bool = False) -> tuple[str, PhaseIR]:
        params = params or {}
        key = ir_key(self.spec.spec_hash, cover, params)
        if self.store.has_ir(key) and not force:
            return key, self.store.load_ir(key)
        fn = cover_mod.get(cover)
        t0 = time.time()
        ir = fn(self.spec, **params)
        elapsed = time.time() - t0
        chk = verify_ir(ir, self.spec)
        if not chk["ok"]:
            raise AssertionError(f"cover '{cover}' is WRONG on {chk['n_wrong']} states")
        self.store.save_ir(key, ir, {
            "cover": cover, "params": params, "spec_hash": self.spec.spec_hash,
            "elapsed_s": elapsed, "ir_verified": True,
        })
        return key, ir

    # -- stage 3: cheap, re-runnable --------------------------------------
    def build_circuit(self, ir_k: str, lowering: str, params: dict | None = None,
                      force: bool = False) -> tuple[str, QuantumCircuit]:
        params = params or {}
        ir = self.store.load_ir(ir_k)
        key = circuit_key(ir.ir_hash, lowering, params)
        if self.store.has_circuit(key) and not force:
            return key, self.store.load_circuit(key)
        fn = lower_mod.get(lowering)
        t0 = time.time()
        qc = fn(ir, **params)
        elapsed = time.time() - t0
        self.store.save_circuit(key, qc, {
            "lowering": lowering, "params": params, "ir_key": ir_k,
            "ir_hash": ir.ir_hash, "spec_hash": self.spec.spec_hash,
            "elapsed_s": elapsed, "ir_summary": ir.summary(),
        })
        return key, qc

    # -- stage 4: verification (cached per circuit) -----------------------
    def verify_circuit(self, circ_k: str, force: bool = False) -> dict:
        cached = None if force else self.store.read_side(circ_k, "verify.json")
        if cached:
            return cached
        qc = self.store.load_circuit(circ_k)
        res = verify(qc, self.spec)
        self.store.write_side(circ_k, "verify.json", res)
        return res

    # -- stage 5: metrics, ALWAYS recomputable ----------------------------
    def score_circuit(self, circ_k: str, bases: list[str] | None = None,
                      opt_level: int = 3) -> dict:
        qc = self.store.load_circuit(circ_k)
        res = metrics_mod.score_all(qc, bases=bases, opt_level=opt_level)
        self.store.write_side(circ_k, "metrics.json", res)
        return res

    # -- convenience -------------------------------------------------------
    def run(self, cover: str, lowering: str, cover_params: dict | None = None,
            lower_params: dict | None = None, bases: list[str] | None = None) -> dict:
        ir_k, ir = self.build_ir(cover, cover_params)
        circ_k, _ = self.build_circuit(ir_k, lowering, lower_params)
        ver = self.verify_circuit(circ_k)
        met = self.score_circuit(circ_k, bases=bases) if ver["ok"] else {}
        return {
            "cover": cover, "lowering": lowering, "ir_key": ir_k, "circuit_key": circ_k,
            "ir": ir.summary(), "verified": ver["ok"], "verify": ver, "metrics": met,
        }
