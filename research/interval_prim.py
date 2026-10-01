"""THE decisive primitive: cost of writing a 6-bit interval indicator into an
ancilla.  flag ^= [x in [a,b]].  Leader's TOTAL budget is 269 CX / 97 depth and
the geometry needs ~20 such tests, so ~13 CX each is the target.
Every number here is gated on an exact correctness check first."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys
sys.path.insert(0, str(ROOT / "src"))
import warnings, numpy as np
warnings.filterwarnings("ignore")
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector
from qoracle.aig_synth import synthesize_small_aig_blif, parse_blif
from qoracle.pebble_cpsat import solve_pebbling, build_from_schedule, uncompute_from_schedule

REAL = [(2,26),(32,48),(33,47),(34,46),(36,44),(38,42),(50,60),(51,59),(53,57),(2,61)]

def itruth(a,b):
    return np.array([1 if a<=x<=b else 0 for x in range(64)],dtype=np.uint8)

def build_flag(a,b,n_scratch):
    """Returns (qc, ok) computing flag ^= [x in [a,b]] on 6 data + 1 flag + scratch."""
    t=itruth(a,b)
    blif=synthesize_small_aig_blif(t,6)
    if blif is None: return None,0,False
    ins,out,nodes=parse_blif(blif)
    if not nodes: return None,0,False
    sched=None
    for hz,tl in ((200,20.0),(400,40.0)):
        sched=solve_pebbling(nodes,out,set(ins),ancillas=n_scratch,horizon=hz,time_limit_s=tl)
        if sched: break
    if sched is None: return None,len(nodes),False
    qc=QuantumCircuit(6+1+n_scratch)
    flag=6; scr=list(range(7,7+n_scratch))
    imap={nm:i for i,nm in enumerate(ins)}
    r=build_from_schedule(qc,nodes,out,imap,scr,sched,relative_phase=True)
    qc.cx(r.result_qubit,flag)
    uncompute_from_schedule(qc,r)
    return qc,len(nodes),True

def verify_flag(qc,a,b,n_scratch):
    """Exact check on all 64 inputs: flag set iff in range, scratch restored."""
    for x in range(64):
        c=QuantumCircuit(qc.num_qubits)
        for i in range(6):
            if (x>>i)&1: c.x(i)
        c.compose(qc,inplace=True)
        sv=Statevector.from_instruction(c).data
        want = x | ((1 if a<=x<=b else 0)<<6)
        k=int(np.argmax(np.abs(sv)))
        if k!=want or abs(abs(sv[k])-1)>1e-9: return False
    return True

print(f"{'interval':>12} {'aig':>4} " + " ".join(f"{'S=%d'%s:>14}" for s in (2,3,4,5)))
tot={s:[0,0,0] for s in (2,3,4,5)}
for (a,b) in REAL:
    row=[]
    nn=0
    for s in (2,3,4,5):
        qc,nn,ok=build_flag(a,b,s)
        if not ok:
            row.append("infeasible"); continue
        if not verify_flag(qc,a,b,s):
            row.append("WRONG"); continue
        t=transpile(qc,basis_gates=["u3","cx"],optimization_level=3)
        d,c=t.depth(),t.count_ops().get("cx",0)
        row.append(f"{d}/{c}")
        tot[s][0]+=d; tot[s][1]+=c; tot[s][2]+=1
    print(f"[{a:>2},{b:>2}]".rjust(12) + f" {nn:>4} " + " ".join(f"{x:>14}" for x in row), flush=True)

print("\nTOTALS over the intervals that verified:")
for s in (2,3,4,5):
    d,c,n=tot[s]
    if n: print(f"  scratch={s}: {n}/10 verified, sum depth={d} sum cx={c}, mean {d/n:.0f}/{c/n:.0f} per interval")
print("\ntarget for parity with leader: ~13 CX and ~5 depth per interval")
print("(leader total: 97 depth / 269 cx;  geometry needs ~20 such tests)")
