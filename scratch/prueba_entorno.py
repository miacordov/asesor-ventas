from pathlib import Path
from pyswip import Prolog

p = Prolog()
p.consult(str(Path(__file__).parent / "prolog" / "reglas.pl"))
for c, prod in [("c001", "p001"), ("c002", "p001"), ("c002", "p002")]:
    p.assertz(f"compro({c}, {prod})")
print([s["P"] for s in p.query("recomendar(c001, P)")])
