"""Sección de asesoría: ofertas de temporada.

Muestra cómo se vende cada producto en la temporada elegida para que la
persona decida qué poner en oferta, y lista las ofertas registradas.
"""

import math

import pandas as pd
import streamlit as st

from interfaz import comun, estilo
from interfaz.comun import dinero, nombre_categoria
from ventas import administracion as admin
from ventas.ofertas import (
    PORCENTAJE_MAXIMO,
    PORCENTAJE_MINIMO,
    TEMPORADAS,
    DesempenoTemporada,
    desempeno_en_temporada,
    temporada_proxima,
)

SUGERENCIAS = {
    "pico": "Pico de temporada: oferta gancho",
    "baja_rotacion": "Baja rotación: oferta para mover stock",
    "estable": "Estable",
    "sin_ventas": "Sin ventas registradas",
}
TODAS = "Todas"


def pagina_ofertas() -> None:
    comun.mostrar_aviso()
    estilo.hero(
        "Asesoría",
        "Ofertas de temporada",
        "Mira cómo se vende cada producto en la temporada y elige cuáles poner en oferta. "
        "Las ofertas vigentes se sugieren primero en «Arma mi pedido».",
        "ofertas",
    )
    datos, hoy = comun.datos(), comun.fecha_referencia()
    if not datos.productos:
        st.info("No hay productos registrados. Agrégalos en Administración › Productos.", icon=":material/info:")
        return

    claves = list(TEMPORADAS)
    filtros = st.columns([2, 1])
    clave = filtros[0].selectbox(
        "Temporada de ventas",
        claves,
        index=claves.index(temporada_proxima(hoy).clave),
        format_func=lambda c: TEMPORADAS[c].nombre,
        key="temporada_oferta",
    )
    categorias = sorted({p.categoria for p in datos.productos})
    categoria = filtros[1].selectbox(
        "Categoría", [TODAS, *categorias], format_func=lambda c: c if c == TODAS else nombre_categoria(c), key="categoria_oferta"
    )
    temporada = TEMPORADAS[clave]
    productos = [p for p in datos.productos if categoria == TODAS or p.categoria == categoria]
    desempeno = desempeno_en_temporada(productos, datos.ventas, temporada)
    ofertas = {o.id_producto: o for o in comun.ofertas()}

    tabla, formulario = st.columns([3, 2], gap="large")
    with tabla:
        st.subheader("Cómo se vende en la temporada")
        if not datos.ventas:
            st.info("Aún no hay ventas: sin historial no se puede medir la temporada.", icon=":material/info:")
        tabla_desempeno(desempeno, ofertas)
        st.caption(
            "**Índice:** cuánto se vende por mes en la temporada frente al resto del año "
            "(2.0 = el doble). Un pico sirve como oferta gancho; la baja rotación, para mover stock."
        )
    with formulario:
        formulario_oferta(desempeno, temporada.fechas(hoy))
    st.divider()
    ofertas_registradas(datos, ofertas, hoy)


def tabla_desempeno(desempeno: tuple[DesempenoTemporada, ...], ofertas: dict) -> None:
    filas = [
        {
            "Producto": d.producto.nombre,
            "Categoría": nombre_categoria(d.producto.categoria),
            "Precio": d.producto.precio,
            "Unidades en temporada": d.unidades_temporada,
            "Por mes (temporada)": d.promedio_temporada,
            "Por mes (resto)": d.promedio_resto,
            "Índice": None if math.isinf(d.indice) else d.indice,
            "Sugerencia": SUGERENCIAS[d.sugerencia],
            "Oferta": f"-{ofertas[d.producto.id_producto].porcentaje} %" if d.producto.id_producto in ofertas else "",
        }
        for d in desempeno
    ]
    st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        key="tabla_temporada",
        column_config={
            "Precio": st.column_config.NumberColumn(format="S/ %.2f"),
            "Índice": st.column_config.NumberColumn(format="%.2f", help="Vacío: solo se vende en esta temporada."),
        },
    )


def formulario_oferta(desempeno: tuple[DesempenoTemporada, ...], fechas) -> None:
    clave = f"of_{comun.version('oferta')}"
    with st.container(border=True, key="panel_oferta"):
        st.subheader("Poner en oferta")
        if not desempeno:
            st.caption("No hay productos en esta categoría.")
            return
        por_id = {d.producto.id_producto: d for d in desempeno}
        st.selectbox(
            "Producto",
            list(por_id),
            format_func=lambda i: f"{por_id[i].producto.nombre} · {SUGERENCIAS[por_id[i].sugerencia]}",
            key=f"{clave}_producto",
        )
        st.number_input(
            "Descuento (%)", min_value=PORCENTAJE_MINIMO, max_value=PORCENTAJE_MAXIMO, value=10, step=1, key=f"{clave}_porcentaje"
        )
        st.date_input("Vigencia", value=fechas, format="DD/MM/YYYY", key=f"{clave}_vigencia")
        elegido = por_id[st.session_state[f"{clave}_producto"]].producto
        porcentaje = st.session_state[f"{clave}_porcentaje"]
        st.caption(
            f"{elegido.nombre}: {dinero(elegido.precio)} → "
            f"{dinero(max(round(elegido.precio * (100 - porcentaje) / 100, 2), 0.01))}"
        )
        st.button("Guardar oferta", type="primary", icon=":material/sell:", on_click=_guardar_oferta, key="guardar_oferta")


def _guardar_oferta() -> None:
    clave = f"of_{comun.version('oferta')}"
    vigencia = st.session_state[f"{clave}_vigencia"]
    if len(vigencia) != 2:
        comun.avisar("error", "Elige la fecha de inicio y la de fin de la oferta.")
        return
    try:
        oferta = admin.poner_oferta(
            comun.repositorio(), st.session_state[f"{clave}_producto"], st.session_state[f"{clave}_porcentaje"], *vigencia
        )
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        nombre = next(p.nombre for p in comun.datos().productos if p.id_producto == oferta.id_producto)
        comun.avisar("exito", f"Oferta guardada: {nombre} con {oferta.porcentaje} % de descuento.")
        comun.reiniciar("oferta")


def _quitar_oferta(id_producto: str, nombre: str) -> None:
    try:
        admin.quitar_oferta(comun.repositorio(), id_producto)
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Oferta de {nombre} quitada.")


def estado(oferta, hoy) -> tuple[str, str]:
    if oferta.vigente(hoy):
        return "Vigente", "ok"
    return ("Programada", "media") if hoy < oferta.desde else ("Vencida", "neutro")


def ofertas_registradas(datos, ofertas: dict, hoy) -> None:
    st.subheader("Ofertas registradas")
    if not ofertas:
        st.info("Todavía no hay ofertas. Elige un producto y guárdala arriba.", icon=":material/sell:")
        return
    por_id = {p.id_producto: p for p in datos.productos}
    for oferta in sorted(ofertas.values(), key=lambda o: (o.desde, o.id_producto)):
        producto = por_id[oferta.id_producto]
        texto, tono = estado(oferta, hoy)
        with st.container(border=True, key=f"oferta_{oferta.id_producto}"):
            info, boton = st.columns([5, 1], vertical_alignment="center")
            info.markdown(
                estilo.fila_producto(
                    producto.nombre,
                    producto.categoria,
                    dinero(oferta.precio(producto.precio)),
                    f"{dinero(producto.precio)} · -{oferta.porcentaje} % · del {oferta.desde:%d/%m/%Y} al {oferta.hasta:%d/%m/%Y}",
                )
                + estilo.chip(texto, tono),
                unsafe_allow_html=True,
            )
            boton.button(
                "Quitar",
                key=f"quitar_oferta_{oferta.id_producto}",
                on_click=_quitar_oferta,
                args=(oferta.id_producto, producto.nombre),
                width="stretch",
            )
