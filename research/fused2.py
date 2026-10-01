"""f(x,y) = [ l(y) + mu(x,u(y)) >= T ] -- ONE comparison, column code on 7 bits (128 points)."""
import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys; sys.path.insert(0, str(ROOT / "src"))
from qoracle import io
G=64
rows={y:frozenset(x for x in range(G) if io.logo_pixel(x,y)) for y in range(G)}
pats=sorted(set(rows.values()),key=len)
C1=[pats[i] for i in (0,1,2,3,4,5,10)]
C2=[pats[i] for i in (0,6,7,8,9)]
for nm,ch in (("chain1",C1),("chain2",C2)):
    assert all(ch[i] < ch[i+1] for i in range(len(ch)-1)), f"{nm} not a chain"
    print(f"{nm}: {len(ch)} levels, strictly increasing OK")
assert set(C1)|set(C2) == set(pats) and len(set(C1)&set(C2))==1
print("the two chains partition all 11 patterns (sharing only the empty one)")

CH=[C1,C2]
def code(y):
    p=rows[y]
    if len(p)==0: return 0,0
    for u,ch in enumerate(CH):
        if p in ch: return u,ch.index(p)
    raise AssertionError
U={y:code(y)[0] for y in range(G)}
L={y:code(y)[1] for y in range(G)}
BIG=7
def a(u,x):
    for j in range(1,len(CH[u])):
        if x in CH[u][j]: return j
    return BIG
MU={(x,u):BIG-a(u,x) for x in range(G) for u in (0,1)}

w_xor = sum(1 for y in range(G) for x in range(G)
            if ((a(0,x)<=(L[y] if U[y]==0 else 0)) ^ (a(1,x)<=(L[y] if U[y]==1 else 0)))
               != io.logo_pixel(x,y))
w_one = sum(1 for y in range(G) for x in range(G)
            if (a(U[y],x) <= L[y]) != io.logo_pixel(x,y))
w_sum = sum(1 for y in range(G) for x in range(G)
            if (L[y] + MU[(x,U[y])] >= BIG) != io.logo_pixel(x,y))
print(f"\n[a1<=L1] XOR [a2<=L2]            wrong = {w_xor:4d} / 4096")
print(f"[ a_u(x) <= l(y) ]  (single)     wrong = {w_one:4d} / 4096")
print(f"[ l(y) + mu(x,u) >= {BIG} ] (sum)   wrong = {w_sum:4d} / 4096")
print(f"\nl(y): 0..{max(L.values())} (3 bits)   u(y): 1 bit   mu: 0..{max(MU.values())} (3 bits)")
print(f"row code   : 6 bits y -> l(3)+u(1)      = {G} points")
print(f"column code: 6 bits x + 1 bit u -> 3    = {2*G} points   <-- the '128 points'")
print(f"ancillas to materialize simultaneously: l(3) + u(1) + mu(3) = 7")
