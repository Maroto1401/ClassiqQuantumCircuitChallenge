# ClassiqQuantumCircuitChallenge

Minimal reference implementation for a logo-image quantum circuit depth challenge.

- `build_naive_logo_circuit(...)` builds the circuit with sequential gate scheduling.
- `build_optimized_logo_circuit(...)` applies depth-aware scheduling to lower circuit depth.

Run tests:

```bash
python -m unittest tests/test_quantum_logo_circuit.py -v
```
