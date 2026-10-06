"""Asesor comercial: punto de entrada de la aplicación web.

Ejecutar desde la carpeta del proyecto:  streamlit run app.py

Dos secciones: Asesoría (agenda y modo mostrador) y Administración (resumen,
clientes, productos y ventas). Las pantallas viven en paginas/ y se dibujan con
el código de interfaz/; la lógica de negocio está en ventas/.
"""

import sqlite3

import streamlit as st

st.set_page_config(page_title="Asesor comercial", page_icon=":material/storefront:", layout="wide")

try:
    from interfaz import comun, estilo
except Exception as error:  # p. ej. SWI-Prolog no instalado: pyswip falla al importarse
    st.error(
        "No se pudo iniciar el motor lógico. Verifica que SWI-Prolog esté instalado "
        "(https://www.swi-prolog.org) con la misma arquitectura que Python, y que ejecutaste "
        "`streamlit run app.py` desde la carpeta del proyecto."
    )
    st.caption(f"Detalle técnico: {type(error).__name__}: {error}")
    st.stop()

try:
    comun.datos()  # abre la base de datos
except (ValueError, sqlite3.Error, OSError) as error:
    st.error(f"No se pudieron cargar los datos: {error}")
    st.info("Revisa la carpeta de datos y vuelve a abrir la aplicación.")
    st.stop()

estilo.aplicar()
st.logo(estilo.LOGO_SVG, size="large")

st.sidebar.date_input(
    "Fecha de referencia",
    value=comun.FECHA_DEMO,
    key="fecha_referencia",
    format="DD/MM/YYYY",
    help="Los días sin comprar se cuentan hasta esta fecha.",
)


navegacion = st.navigation(
    {
        "Asesoría": [
            st.Page("paginas/agenda.py", title="Agenda de hoy", icon=":material/event_note:", default=True),
            st.Page("paginas/pedido.py", title="Arma mi pedido", icon=":material/shopping_cart:", url_path="pedido"),
        ],
        "Administración": [
            st.Page("paginas/resumen.py", title="Resumen", icon=":material/dashboard:", url_path="resumen"),
            st.Page("paginas/clientes.py", title="Clientes", icon=":material/groups:", url_path="clientes"),
            st.Page("paginas/productos.py", title="Productos", icon=":material/inventory_2:", url_path="productos"),
            st.Page("paginas/registro_ventas.py", title="Ventas", icon=":material/receipt_long:", url_path="ventas"),
        ],
    }
)
navegacion.run()
estilo.pie()
