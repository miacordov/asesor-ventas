from pathlib import Path
import streamlit as st
from pyswip import Prolog

@st.cache_resource
def motor():
    p = Prolog()
    p.consult(str(Path(__file__).parent / "prolog" / "reglas.pl"))
    for c, prod in [("c001", "p001"), ("c002", "p001"), ("c002", "p002")]:
        p.assertz(f"compro({c}, {prod})")
    return p

st.title("Prueba pyswip + Streamlit")
cliente = st.selectbox("Cliente", ["c001", "c002"])
if st.button("Consultar"):
    resultado = [s["P"] for s in motor().query(f"recomendar({cliente}, P)")]
    st.write(resultado)
