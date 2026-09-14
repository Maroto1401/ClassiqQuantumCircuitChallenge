import numpy as np
import pytest

from qoracle.io import synthetic_target
from qoracle.spec import DIM, OracleSpec, index_to_xy, xy_to_index
from qoracle.gf2 import rank, factor
from qoracle import cover as cover_mod
from qoracle.lower.serial_mcz import lower as serial_lower
from qoracle.verify import verify, verify_ir


@pytest.fixture(scope="module")
def spec():
    return synthetic_target()


def test_index_roundtrip():
    for i in (0, 1, 63, 64, 4095):
        assert xy_to_index(*index_to_xy(i)) == i


def test_gf2_factor_exact():
    rng = np.random.default_rng(0)
    M = (rng.random((64, 64)) < 0.3).astype(np.uint8)
    U, V, _ = factor(M)
    assert np.array_equal((U @ V) % 2, M)
    assert V.shape[0] == rank(M)


@pytest.mark.parametrize("name", ["minterm", "pprm"])
def test_cover_is_exact(spec, name):
    ir = cover_mod.get(name)(spec)
    assert verify_ir(ir, spec)["ok"], f"{name} does not reproduce the truth table"


def test_small_circuit_verifies():
    """End-to-end on a tiny target: cover -> lower -> exact statevector check."""
    truth = np.zeros(DIM, dtype=np.uint8)
    for i in (0, 5, 1023, 4095):
        truth[i] = 1
    s = OracleSpec(truth=truth, name="tiny")
    ir = cover_mod.get("minterm")(s)
    qc = serial_lower(ir)
    assert verify(qc, s)["ok"]


def test_verifier_rejects_wrong_circuit():
    truth = np.zeros(DIM, dtype=np.uint8)
    truth[7] = 1
    s = OracleSpec(truth=truth, name="tiny2")
    bad = OracleSpec(truth=np.roll(truth, 1), name="tiny3")
    qc = serial_lower(cover_mod.get("minterm")(bad))
    assert not verify(qc, s)["ok"]
