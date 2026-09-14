import unittest

from quantum_logo_circuit import (
    build_logo_gates,
    build_naive_logo_circuit,
    build_optimized_logo_circuit,
)


class QuantumLogoCircuitTests(unittest.TestCase):
    def test_build_logo_gates_for_empty_image(self):
        qubits, gates = build_logo_gates([])
        self.assertEqual(qubits, 0)
        self.assertEqual(gates, [])

    def test_naive_depth_matches_gate_count(self):
        pixels = [
            [1, 1],
            [1, 0],
        ]

        circuit = build_naive_logo_circuit(pixels)
        self.assertEqual(circuit.depth, len(circuit.gates))

    def test_optimized_circuit_reduces_depth_for_sparse_logo(self):
        pixels = [
            [1, 0, 1],
            [0, 0, 0],
            [1, 0, 1],
        ]

        naive = build_naive_logo_circuit(pixels)
        optimized = build_optimized_logo_circuit(pixels)

        self.assertLess(optimized.depth, naive.depth)

    def test_optimized_schedule_avoids_qubit_conflicts_in_same_layer(self):
        pixels = [
            [1, 1],
            [1, 1],
        ]

        optimized = build_optimized_logo_circuit(pixels)

        by_layer = {}
        for scheduled in optimized.gates:
            by_layer.setdefault(scheduled.layer, set())
            qubits = set(scheduled.gate.qubits)
            self.assertTrue(qubits.isdisjoint(by_layer[scheduled.layer]))
            by_layer[scheduled.layer].update(qubits)


if __name__ == "__main__":
    unittest.main()
