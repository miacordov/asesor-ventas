"""Pruebas de la interfaz con el probador oficial de Streamlit (AppTest).

AppTest ejecuta app.py sin abrir un navegador. Cada ejecución corre en un hilo
distinto, así que estas pruebas también verifican que PySwip funciona bajo el
modelo de hilos de Streamlit.
"""

import shutil
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parent.parent
APP = str(RAIZ / "app.py")
TIEMPO = 60


def abrir(pagina=None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIEMPO).run()
    if pagina:
        at.sidebar.radio[0].set_value(pagina).run()
    return at


def sin_excepciones(at):
    return [e.value for e in at.exception] == []


def textos(elementos):
    return [e.value for e in elementos]


# =====================================================================
# Arranque y navegación
# =====================================================================
def test_la_app_inicia_sin_errores():
    at = abrir()
    assert sin_excepciones(at)
    assert at.error == []
    assert textos(at.header) == ["Agenda de hoy"]


def test_la_barra_lateral_ofrece_las_cuatro_paginas():
    at = abrir()
    assert list(at.sidebar.radio[0].options) == ["Agenda de hoy", "Arma mi pedido", "Clientes", "Resumen"]
    assert at.sidebar.date_input[0].value == date(2026, 10, 5)


@pytest.mark.parametrize(
    ("pagina", "titulo"),
    [
        ("Agenda de hoy", "Agenda de hoy"),
        ("Arma mi pedido", "Arma mi pedido"),
        ("Clientes", "Clientes"),
        ("Resumen", "Resumen de ventas"),
    ],
)
def test_cada_pagina_se_muestra_sin_errores(pagina, titulo):
    at = abrir(pagina)
    assert sin_excepciones(at)
    assert textos(at.header) == [titulo]


def test_varias_ejecuciones_seguidas_no_fallan():
    """Cada ejecución corre en un hilo distinto: PySwip debe aguantarlo."""
    at = abrir()
    for pagina in ("Arma mi pedido", "Agenda de hoy", "Resumen", "Agenda de hoy", "Clientes", "Agenda de hoy"):
        at.sidebar.radio[0].set_value(pagina).run()
        assert sin_excepciones(at), pagina
    assert len(at.subheader) == 7


# =====================================================================
# Agenda
# =====================================================================
def test_agenda_muestra_los_siete_contactos_en_orden():
    at = abrir()
    assert textos(at.subheader) == [
        "1. Juan Pérez · Reactivar cliente",
        "2. Pedro Salas · Reactivar cliente",
        "3. María Torres · Fidelizar cliente",
        "4. Ana Ríos · Fidelizar cliente",
        "5. Lucía Mendoza · Fidelizar cliente",
        "6. Carlos Ruiz · Ofrecer productos complementarios",
        "7. Luis Vega · Ofrecer productos complementarios",
    ]


def test_agenda_no_incluye_a_rosa_sin_compras():
    at = abrir()
    assert not any("Rosa" in s for s in textos(at.subheader))


def test_cada_tarjeta_tiene_su_boton_de_whatsapp_con_el_texto_del_mensaje():
    at = abrir()
    botones = at.get("link_button")
    assert len(botones) == 7
    for boton in botones:
        assert boton.proto.label == "Abrir en WhatsApp"
        url = urlparse(boton.proto.url)
        assert url.netloc == "wa.me" and url.path[1:].isdigit()
        assert parse_qs(url.query)["text"][0].startswith("Hola ")
    primer_texto = parse_qs(urlparse(botones[0].proto.url).query)["text"][0]
    assert "Juan" in primer_texto and "S/ 607.50" in primer_texto


def test_el_motivo_de_cada_tarjeta_es_visible():
    at = abrir()
    contenido = textos(at.markdown)
    assert "Compró 3 veces, lleva 40 días sin comprar" in contenido
    assert "Compró 5 veces, su última compra fue hace 4 días" in contenido


def test_cada_tarjeta_tiene_sus_tres_secciones():
    at = abrir()
    etiquetas = [e.label for e in at.expander]
    assert etiquetas.count("¿Por qué?") == 7
    assert etiquetas.count("Mensaje para WhatsApp") == 7
    assert sum(e.startswith("Pedido sugerido") for e in etiquetas) == 7
    assert "Pedido sugerido · S/ 607.50" in etiquetas


def test_la_tarjeta_explica_las_reglas_y_los_umbrales():
    at = abrir()
    contenido = textos(at.markdown)
    assert any("`frecuente`" in t and "`inactivo`" in t for t in contenido)
    assert any("desde 3 compras" in c and "más de 30 días" in c for c in textos(at.caption))


def test_la_agenda_cambia_con_la_fecha_de_referencia():
    at = abrir()
    at.sidebar.date_input[0].set_value(date(2026, 10, 20)).run()
    assert sin_excepciones(at)
    # Ana (última compra el 10-sep) pasa a inactiva: 40 días, tercer lugar entre los "reactivar".
    assert "3. Ana Ríos · Reactivar cliente" in textos(at.subheader)


def test_fecha_anterior_a_las_ventas_muestra_un_error_claro():
    at = abrir()
    at.sidebar.date_input[0].set_value(date(2026, 5, 1)).run()
    assert sin_excepciones(at)
    assert len(at.error) == 1 and "anterior a la última venta" in at.error[0].value
    assert "03/10/2026" in at.error[0].value
    assert at.subheader == []


def test_el_error_de_fecha_tambien_aplica_a_clientes():
    at = abrir("Clientes")
    at.sidebar.date_input[0].set_value(date(2026, 5, 1)).run()
    assert sin_excepciones(at)
    assert len(at.error) == 1 and at.dataframe == []


# =====================================================================
# Arma mi pedido
# =====================================================================
def test_pedido_por_defecto_calculado_a_mano():
    at = abrir("Arma mi pedido")
    assert textos(at.markdown) == [
        "**Opción 1 · S/ 195.00** · sobran S/ 5.00",
        "**Opción 2 · S/ 180.00** · sobran S/ 20.00",
        "**Opción 3 · S/ 170.00** · sobran S/ 30.00",
        "**Opción 4 · S/ 130.00** · sobran S/ 70.00",
        "**Opción 5 · S/ 105.00** · sobran S/ 95.00",
    ]
    assert len(at.dataframe) == 5


def test_pedido_la_mejor_opcion_incluye_webcam_y_mochila():
    at = abrir("Arma mi pedido")
    productos = list(at.dataframe[0].value["Producto"])
    assert productos == ["Webcam HD", "Mochila para laptop"]


@pytest.mark.parametrize(("presupuesto", "combinaciones"), [(105.0, 1), (104.0, 0), (130.0, 2), (200.0, 5)])
def test_el_presupuesto_limita_las_combinaciones(presupuesto, combinaciones):
    at = abrir("Arma mi pedido")
    at.number_input[0].set_value(presupuesto).run()
    assert sin_excepciones(at)
    assert len(at.dataframe) == combinaciones
    assert len(at.warning) == (1 if combinaciones == 0 else 0)


def test_sin_categorias_pide_elegir_al_menos_una():
    at = abrir("Arma mi pedido")
    at.multiselect[0].set_value([]).run()
    assert sin_excepciones(at)
    assert "Elige al menos una categoría." in textos(at.info)
    assert at.dataframe == []


def test_las_categorias_se_muestran_con_tildes():
    at = abrir("Arma mi pedido")
    opciones = at.multiselect[0].options
    assert "Periféricos" in opciones and "Cómputo" in opciones


# =====================================================================
# Clientes y resumen
# =====================================================================
def test_clientes_muestra_los_ocho_con_su_tipo():
    at = abrir("Clientes")
    tabla = at.dataframe[0].value
    assert len(tabla) == 8
    tipos = dict(zip(tabla["Cliente"], tabla["Tipo"], strict=True))
    assert tipos["Juan Pérez"] == "Frecuente" and tipos["Carlos Ruiz"] == "Regular"
    juan = tabla[tabla["Cliente"] == "Juan Pérez"].iloc[0]
    assert (juan["Compras"], juan["Días sin comprar"], juan["Ticket promedio (S/)"]) == (3, 40, 883.33)


def test_clientes_no_expone_telefonos():
    at = abrir("Clientes")
    assert not any("tel" in c.lower() for c in at.dataframe[0].value.columns)


def test_resumen_muestra_los_indicadores_calculados_a_mano():
    at = abrir("Resumen")
    assert textos(at.metric) == ["S/ 8,455.00", "S/ 281.83", "30", "8"]
    assert textos(at.subheader) == ["Ventas por mes", "Ventas por categoría", "Productos más vendidos"]


# =====================================================================
# Errores de datos (se prueba con una copia de la app y datos dañados)
# =====================================================================
def test_datos_invalidos_muestran_un_mensaje_claro(tmp_path):
    copia = tmp_path / "app.py"
    shutil.copy(APP, copia)
    datos = tmp_path / "datos"
    datos.mkdir()
    for nombre in ("clientes.csv", "productos.csv", "ventas.csv"):
        shutil.copy(RAIZ / "datos" / nombre, datos / nombre)
    (datos / "ventas.csv").write_text(
        "id_venta,id_cliente,id_producto,cantidad,precio_unitario,fecha\n"
        "v001,c001,p001,dos,10,2026-09-01\n",
        encoding="utf-8",
    )
    st.cache_data.clear()
    try:
        at = AppTest.from_file(str(copia), default_timeout=TIEMPO).run()
        assert sin_excepciones(at)
        assert len(at.error) == 1
        assert "No se pudieron cargar los datos" in at.error[0].value
        assert "ventas.csv, fila 2" in at.error[0].value
    finally:
        st.cache_data.clear()
