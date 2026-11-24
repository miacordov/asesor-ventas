"""Pruebas de la interfaz con el probador oficial de Streamlit (AppTest).

AppTest ejecuta la aplicación sin abrir un navegador. Cada ejecución corre en un
hilo distinto, igual que en Streamlit real, así que estas pruebas también
verifican que PySwip y SQLite funcionan bajo ese modelo de hilos.

Cada prueba usa una base de datos en memoria nueva (se llena con los datos de
ejemplo), de modo que nada depende del orden ni toca la base real.
"""

import re
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
PAGINAS = ["agenda", "pedido", "ofertas", "propuesta", "resumen", "clientes", "productos", "registro_ventas"]


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    monkeypatch.setenv("ASESOR_DB", ":memory:")
    monkeypatch.setenv("ASESOR_FECHA", "2026-10-05")  # fecha fija: los valores esperados dependen de ella
    # Datos fijos de prueba: los valores esperados se calcularon a mano sobre ellos.
    monkeypatch.setattr("interfaz.comun.CARPETA_CSV", RAIZ / "tests" / "datos")
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def abrir(pagina: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIEMPO).run()
    if pagina:
        at.switch_page(f"paginas/{pagina}.py").run()
    return at


def banner(at: AppTest) -> str:
    """Título del banner de la pantalla (el <h1> del encabezado)."""
    html = next(m.value for m in at.markdown if 'class="hero"' in m.value)
    return re.search(r"<h1>(.*?)</h1>", html).group(1)


def filas_de_producto(html: str) -> list[tuple[str, str]]:
    """[(nombre, precio)] de las filas de producto de un bloque HTML."""
    patron = r'<span class="nom">(.*?)<small>.*?</small></span><span class="pre">(.*?)</span>'
    return re.findall(patron, html)


def totales(at: AppTest) -> list[tuple[str, str]]:
    """[(precio tachado o '', total)] de cada bloque de total de las tarjetas."""
    html = " ".join(m.value for m in at.markdown if 'class="total"' in m.value)
    return re.findall(r'<span class="val">(?:<s>(.*?)</s>)?(.*?)</span>', html)


def ok(at: AppTest) -> bool:
    return [e.value for e in at.exception] == []


def boton(at: AppTest, etiqueta: str):
    return next(b for b in at.button if b.label == etiqueta)


def tarjetas(at: AppTest) -> list[str]:
    return [m.value[5:] for m in at.markdown if m.value.startswith("#### ")]


def indicadores(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def tabla(at: AppTest, indice: int = 0):
    return at.dataframe[indice].value


def exito(at: AppTest) -> list[str]:
    return [s.value for s in at.success]


def errores(at: AppTest) -> list[str]:
    return [e.value for e in at.error]


# =====================================================================
# Arranque y navegación
# =====================================================================
def test_la_app_inicia_en_la_agenda_sin_errores():
    at = abrir()
    assert ok(at) and errores(at) == []
    assert banner(at) == "Agenda de fidelización"


@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_se_muestra_sin_errores(pagina):
    at = abrir(pagina)
    assert ok(at), pagina
    assert errores(at) == []


def test_navegar_muchas_veces_no_falla():
    """Cada ejecución corre en un hilo distinto: PySwip y SQLite deben aguantarlo."""
    at = abrir()
    for pagina in ("pedido", "agenda", "resumen", "agenda", "clientes", "registro_ventas", "agenda"):
        at.switch_page(f"paginas/{pagina}.py").run()
        assert ok(at), pagina
    assert len(tarjetas(at)) == 7


def test_la_fecha_de_referencia_se_puede_fijar_con_asesor_fecha():
    at = abrir()
    assert at.sidebar.date_input[0].value == date(2026, 10, 5)


def test_sin_asesor_fecha_la_referencia_es_hoy(monkeypatch):
    monkeypatch.delenv("ASESOR_FECHA")
    at = abrir()
    assert at.sidebar.date_input[0].value == date.today()


def test_asesor_fecha_invalida_usa_hoy(monkeypatch):
    monkeypatch.setenv("ASESOR_FECHA", "mañana")
    assert abrir().sidebar.date_input[0].value == date.today()


def test_el_servidor_solo_escucha_en_esta_computadora():
    import tomllib

    config = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["address"] == "localhost"


def test_datos_de_ejemplo_invalidos_muestran_un_mensaje_claro(tmp_path, monkeypatch):
    for nombre in ("clientes.csv", "productos.csv"):
        shutil.copy(RAIZ / "tests" / "datos" / nombre, tmp_path / nombre)
    (tmp_path / "ventas.csv").write_text(
        "id_venta,id_cliente,id_producto,cantidad,precio_unitario,fecha\nv001,c001,p001,dos,10,2026-09-01\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("interfaz.comun.CARPETA_CSV", tmp_path)
    at = abrir()
    assert ok(at)
    assert len(errores(at)) == 1
    assert "No se pudieron cargar los datos" in errores(at)[0] and "ventas.csv, fila 2" in errores(at)[0]


def test_los_datos_persisten_al_reiniciar_la_aplicacion(tmp_path, monkeypatch):
    monkeypatch.setenv("ASESOR_DB", str(tmp_path / "negocio.db"))
    at = abrir("clientes")
    at.text_input(key="nc_nombre_0").set_value("Ana Torres").run()
    boton(at, "Registrar cliente").click().run()
    assert any("c009" in t for t in exito(at))
    st.cache_resource.clear()  # simula cerrar y volver a abrir la aplicación
    reabierta = abrir("clientes")
    assert "Ana Torres" in list(tabla(reabierta)["Cliente"])
    assert len(tabla(reabierta)) == 9


# =====================================================================
# Agenda
# =====================================================================
def test_agenda_muestra_los_siete_contactos_en_orden():
    assert tarjetas(abrir()) == [
        "1. Juan Pérez",
        "2. Pedro Salas",
        "3. María Torres",
        "4. Ana Ríos",
        "5. Lucía Mendoza",
        "6. Carlos Ruiz",
        "7. Luis Vega",
    ]


def test_agenda_indicadores_calculados_a_mano():
    assert indicadores(abrir()) == {
        "Contactos": "7",
        "Por reactivar": "2",
        "Por fidelizar": "3",
        "Complementar": "2",
        "Valor en pedidos sugeridos": "S/ 1,476.00",  # 607.50+261+382.50+225 (Ana, Lucía y Carlos sin combinación)
    }


def test_agenda_no_incluye_a_rosa_sin_compras():
    assert not any("Rosa" in t for t in tarjetas(abrir()))


def test_cada_tarjeta_tiene_su_boton_de_whatsapp_con_el_mensaje():
    botones = abrir().get("link_button")
    assert len(botones) == 7
    for b in botones:
        url = urlparse(b.proto.url)
        assert url.netloc == "wa.me" and url.path[1:].isdigit()
        assert parse_qs(url.query)["text"][0].startswith("Hola ")
    assert "S/ 607.50" in parse_qs(urlparse(botones[0].proto.url).query)["text"][0]


def test_la_tarjeta_muestra_motivo_y_pedido_con_descuento():
    at = abrir()
    assert "Compró 3 veces, lleva 40 días sin comprar" in [m.value for m in at.markdown]
    assert ("S/ 675.00", "S/ 607.50") in totales(at)  # Juan: precio tachado y total con descuento
    assert ("", "S/ 225.00") in totales(at)  # Luis es regular: sin descuento
    assert any("Ahorras S/ 67.50 (10 % de descuento)" in m.value for m in at.markdown)


def test_cada_tarjeta_tiene_porque_y_mensaje():
    etiquetas = [p.proto.popover.label for p in abrir().get("popover")]
    assert etiquetas.count("¿Por qué?") == 7 and etiquetas.count("Mensaje") == 7


def test_filtrar_la_agenda_por_tipo_de_accion():
    at = abrir()
    at.get("button_group")[0].set_value("Reactivar").run()
    assert ok(at)
    assert tarjetas(at) == ["1. Juan Pérez", "2. Pedro Salas"]
    at.get("button_group")[0].set_value("Complementar").run()
    assert tarjetas(at) == ["6. Carlos Ruiz", "7. Luis Vega"]  # conservan su posición en la agenda


def test_la_agenda_cambia_con_la_fecha_de_referencia():
    at = abrir()
    at.sidebar.date_input[0].set_value(date(2026, 10, 20)).run()
    assert ok(at)
    assert indicadores(at)["Por reactivar"] == "3"  # Ana (última compra el 10-sep) ya está inactiva
    assert "3. Ana Ríos" in tarjetas(at)


@pytest.mark.parametrize("pagina", ["agenda", "clientes", "registro_ventas"])
def test_fecha_anterior_a_las_ventas_muestra_un_error_claro(pagina):
    at = abrir(pagina)
    at.sidebar.date_input[0].set_value(date(2026, 5, 1)).run()
    assert ok(at)
    assert len(errores(at)) == 1 and "anterior a la última venta" in errores(at)[0] and "03/10/2026" in errores(at)[0]
    assert tarjetas(at) == []


# =====================================================================
# Arma mi pedido
# =====================================================================
def test_pedido_por_defecto_calculado_a_mano():
    at = abrir("pedido")
    opciones = [m.value for m in at.markdown if m.value.startswith("**Opción")]
    assert opciones == [
        "**Opción 1 · S/ 195.00** · sobran S/ 5.00",
        "**Opción 2 · S/ 180.00** · sobran S/ 20.00",
        "**Opción 3 · S/ 170.00** · sobran S/ 30.00",
        "**Opción 4 · S/ 130.00** · sobran S/ 70.00",
        "**Opción 5 · S/ 105.00** · sobran S/ 95.00",
    ]
    assert "5 combinaciones" in [s.value for s in at.subheader]


def test_pedido_la_mejor_opcion_es_webcam_y_mochila():
    filas = [m.value for m in abrir("pedido").markdown if 'class="prod"' in m.value]
    assert filas_de_producto(filas[0]) == [("Webcam HD", "S/ 110.00"), ("Mochila para laptop", "S/ 85.00")]


@pytest.mark.parametrize(("presupuesto", "combinaciones"), [(105.0, 1), (104.0, 0), (130.0, 2), (200.0, 5)])
def test_el_presupuesto_limita_las_combinaciones(presupuesto, combinaciones):
    at = abrir("pedido")
    at.number_input(key="presupuesto_pedido").set_value(presupuesto).run()
    assert ok(at)
    assert len([m for m in at.markdown if m.value.startswith("**Opción")]) == combinaciones
    assert len(at.warning) == (1 if combinaciones == 0 else 0)


def test_si_solo_alcanza_un_producto_no_muestra_combinaciones():
    # Audio tiene un único producto (S/ 95): sin pareja no hay combinación.
    at = abrir("pedido")
    at.get("button_group")[0].set_value(["audio"]).run()
    assert ok(at)
    assert not [m for m in at.markdown if m.value.startswith("**Opción")]
    assert "al menos 2 productos" in at.warning[0].value


def test_una_sola_categoria_combina_dos_productos_de_ella():
    at = abrir("pedido")
    at.get("button_group")[0].set_value(["perifericos"]).run()
    opciones = [m.value for m in at.markdown if m.value.startswith("**Opción")]
    assert opciones == ["**Opción 1 · S/ 165.00** · sobran S/ 35.00", "**Opción 2 · S/ 155.00** · sobran S/ 45.00"]


def ofertar(id_producto: str, porcentaje: int) -> None:
    """Registra una oferta vigente el 05/10/2026 en la base que usa la aplicación."""
    from interfaz import comun
    from ventas.ofertas import Oferta

    comun.repositorio().guardar_oferta(Oferta(id_producto, porcentaje, date(2026, 10, 1), date(2026, 10, 31)))


def test_la_agenda_propone_las_ofertas_a_sus_clientes():
    abrir()
    ofertar("p005", 20)  # auriculares: 95 -> 76, hasta el 31/10/2026
    at = abrir()
    assert ok(at)
    html = " ".join(m.value for m in at.markdown)
    assert "Oferta para este cliente" in html
    assert "Oferta -20 % hasta el 31/10/2026" in html
    assert ("Auriculares con micrófono", "S/ 76.00") in filas_de_producto(html)
    textos = [parse_qs(urlparse(b.proto.url).query)["text"][0] for b in at.get("link_button")]
    assert any("Auriculares con micrófono con 20 % de descuento hasta el 31/10/2026" in t for t in textos)


def test_las_ofertas_vigentes_se_sugieren_primero_en_el_pedido():
    abrir("pedido")
    ofertar("p002", 50)  # mouse: 45 -> 22.50
    at = abrir("pedido")
    opciones = [m.value for m in at.markdown if m.value.startswith("**Opción")]
    assert opciones[:2] == ["**Opción 1 · S/ 107.50** · sobran S/ 92.50", "**Opción 2 · S/ 82.50** · sobran S/ 117.50"]
    filas = [m.value for m in at.markdown if 'class="prod"' in m.value]
    assert filas_de_producto(filas[0]) == [("Mouse inalámbrico", "S/ 22.50"), ("Mochila para laptop", "S/ 85.00")]
    assert "Oferta -50 % · antes S/ 45.00" in filas[0]
    assert any("En oferta" in m.value and "Ahorras S/ 22.50" in m.value for m in at.markdown)


def test_una_oferta_vencida_no_cambia_el_pedido():
    from interfaz import comun
    from ventas.ofertas import Oferta

    abrir("pedido")
    comun.repositorio().guardar_oferta(Oferta("p002", 50, date(2026, 9, 1), date(2026, 9, 30)))
    opciones = [m.value for m in abrir("pedido").markdown if m.value.startswith("**Opción")]
    assert opciones[0] == "**Opción 1 · S/ 195.00** · sobran S/ 5.00"


def test_ofertas_de_otras_categorias_se_sugieren():
    abrir("pedido")
    ofertar("p005", 20)  # auriculares (audio), no elegida por defecto
    at = abrir("pedido")
    assert any("Auriculares con micrófono (-20 %)" in i.value for i in at.info)


def test_guardar_combinacion_pide_elegir_el_cliente():
    at = abrir("pedido")
    assert at.button(key="guardar_combo_1").disabled
    at.selectbox(key="combo_cliente").set_value("c001").run()
    assert not at.button(key="guardar_combo_1").disabled


def guardar_combinacion(id_cliente: str = "c001", opcion: int = 1) -> AppTest:
    at = abrir("pedido")
    at.selectbox(key="combo_cliente").set_value(id_cliente).run()
    return at.button(key=f"guardar_combo_{opcion}").click().run()


def test_guardar_combinacion_la_lleva_a_ventas_con_su_id():
    at = guardar_combinacion()
    assert ok(at)
    assert "Combinación cb001 guardada para Juan Pérez." in exito(at)[0]
    at.switch_page("paginas/registro_ventas.py").run()
    assert any(t.label == "Combos por registrar (1)" for t in at.tabs)
    titulos = [m.value for m in at.markdown if m.value.startswith("**Combo ")]
    assert titulos == ["**Combo cb001 · Juan Pérez** · guardado el 05/10/2026"]
    html = " ".join(m.value for m in at.markdown if 'class="prod"' in m.value)
    assert filas_de_producto(html) == [("Webcam HD", "S/ 110.00"), ("Mochila para laptop", "S/ 85.00")]


def test_el_combo_muestra_la_oferta_mientras_esta_vigente_y_se_vende_con_ella():
    abrir("pedido")
    ofertar("p002", 50)  # mouse: 45 -> 22.50 hasta el 31/10/2026; su combinación va primero
    at = guardar_combinacion()
    at.switch_page("paginas/registro_ventas.py").run()
    html = " ".join(m.value for m in at.markdown if 'class="prod"' in m.value)
    assert "Oferta -50 % hasta el 31/10/2026 · antes S/ 45.00" in html
    assert ("S/ 130.00", "S/ 107.50") in totales(at)

    at.button(key="registrar_combo_cb001").click().run()
    assert ok(at)
    assert exito(at)[0].startswith("Combo cb001 registrado para Juan Pérez por S/ 107.50: ventas v031, v032.")
    assert any(t.label == "Combos por registrar (0)" for t in at.tabs)
    t = tabla(at)
    registradas = t[t["combo"] == "cb001"]
    assert sorted(zip(registradas["producto"], registradas["precio_unitario"])) == [
        ("Mochila para laptop", 85.0),
        ("Mouse inalámbrico", 22.5),
    ]


def test_descartar_un_combo_pendiente():
    at = guardar_combinacion()
    at.switch_page("paginas/registro_ventas.py").run()
    at.button(key="descartar_combo_cb001").click().run()
    assert ok(at) and "Combo cb001 descartado." in exito(at)
    assert any("No hay combos por registrar" in i.value for i in at.info)


def test_combo_para_un_cliente_no_registrado():
    at = abrir("pedido")
    at.get("button_group")[1].set_value("No registrado").run()  # [0] son las categorías
    assert at.button(key="guardar_combo_1").disabled
    at.text_input(key="combo_nombre").set_value("  Pedro   Gómez ").run()
    at.button(key="guardar_combo_1").click().run()
    assert ok(at) and "Combinación cb001 guardada para Pedro Gómez (no registrado)." in exito(at)[0]

    at.switch_page("paginas/registro_ventas.py").run()
    assert "**Combo cb001 · Pedro Gómez (no registrado)** · guardado el 05/10/2026" in [m.value for m in at.markdown]
    at.button(key="registrar_combo_cb001").click().run()
    assert ok(at)
    assert "Cliente nuevo registrado: Pedro Gómez (c009)." in exito(at)[0]
    at.switch_page("paginas/clientes.py").run()
    assert "Pedro Gómez" in list(tabla(at)["Cliente"])


def test_sin_categorias_pide_elegir_al_menos_una():
    at = abrir("pedido")
    at.get("button_group")[0].set_value([]).run()
    assert ok(at)
    assert any("Elige al menos una categoría" in i.value for i in at.info)


# =====================================================================
# Asesoría: ofertas de temporada
# =====================================================================
def poner_oferta(at: AppTest, id_producto: str, porcentaje: int) -> AppTest:
    at.selectbox(key="of_0_producto").set_value(id_producto).run()
    at.number_input(key="of_0_porcentaje").set_value(porcentaje).run()
    return boton(at, "Guardar oferta").click().run()


def test_ofertas_proponen_la_temporada_que_viene():
    at = abrir("ofertas")
    assert at.selectbox(key="temporada_oferta").value == "fin_de_anio"  # referencia: 05/10/2026
    assert len(tabla(at)) == 10
    assert any("Todavía no hay ofertas" in i.value for i in at.info)


def test_la_tabla_de_temporada_sugiere_que_ofertar():
    at = abrir("ofertas")
    at.selectbox(key="temporada_oferta").set_value("fiestas_patrias").run()
    sugerencias = set(tabla(at)["Sugerencia"])
    assert sugerencias <= {
        "Pico de temporada: oferta gancho",
        "Baja rotación: oferta para mover stock",
        "Estable",
        "Sin ventas registradas",
    }
    assert "Pico de temporada: oferta gancho" in sugerencias


def test_filtrar_la_temporada_por_categoria():
    at = abrir("ofertas")
    at.selectbox(key="categoria_oferta").set_value("perifericos").run()
    assert sorted(tabla(at)["Producto"]) == ["Mouse inalámbrico", "Teclado mecánico", "Webcam HD"]


def test_guardar_una_oferta_y_verla_registrada():
    at = poner_oferta(abrir("ofertas"), "p002", 20)
    assert ok(at) and "Oferta guardada: Mouse inalámbrico con 20 % de descuento." in exito(at)
    html = " ".join(m.value for m in at.markdown if 'class="prod"' in m.value)
    assert ("Mouse inalámbrico", "S/ 36.00") in filas_de_producto(html)  # 45 - 20 %
    assert "Programada" in html  # empieza el 01/11/2026
    assert "-20 %" in list(tabla(at)["Oferta"])


def test_quitar_una_oferta():
    at = poner_oferta(abrir("ofertas"), "p002", 20)
    boton(at, "Quitar").click().run()
    assert ok(at) and "Oferta de Mouse inalámbrico quitada." in exito(at)
    assert any("Todavía no hay ofertas" in i.value for i in at.info)


# =====================================================================
# Asesoría: propuesta personalizada
# =====================================================================
def armar_propuesta_para(at: AppTest, id_cliente: str, productos: list[str], descuento: int) -> AppTest:
    at.selectbox(key="propuesta_cliente").set_value(id_cliente).run()
    at.multiselect(key=f"pp_{id_cliente}_0_productos").set_value(productos).run()
    at.number_input(key=f"pp_{id_cliente}_0_descuento").set_value(descuento).run()
    return at


def test_personalizar_desde_la_agenda_abre_la_propuesta_del_cliente():
    at = abrir()
    at.button(key="personalizar_c001").click().run()
    assert ok(at) and banner(at) == "Propuesta personalizada"
    assert at.selectbox(key="propuesta_cliente").value == "c001"


def test_la_propuesta_sugiere_el_descuento_del_cliente_frecuente():
    at = abrir("propuesta")
    at.selectbox(key="propuesta_cliente").set_value("c001").run()  # Juan es frecuente
    assert at.number_input(key="pp_c001_0_descuento").value == 10


def test_guardar_una_propuesta_la_lleva_a_la_agenda():
    abrir("propuesta")
    ofertar("p005", 20)  # auriculares: 95 -> 76
    at = armar_propuesta_para(abrir("propuesta"), "c001", ["p005", "p009"], 5)
    boton(at, "Guardar en la agenda").click().run()
    assert ok(at) and "Propuesta para Juan Pérez guardada en la agenda." in exito(at)
    esperado = (
        "Hola Juan, te preparamos una propuesta especial: Auriculares con micrófono (en oferta) y Hub USB-C "
        "por S/ 136.00, y con tu 5 % de descuento te queda en S/ 129.20. ¡Escríbenos si te interesa!"
    )
    enlaces = [parse_qs(urlparse(b.proto.url).query)["text"][0] for b in at.get("link_button")]
    assert esperado in enlaces  # en la lista de propuestas guardadas

    at.switch_page("paginas/agenda.py").run()
    html = " ".join(m.value for m in at.markdown)
    assert "Propuesta lista para enviar" in html and "Propuesta guardada el 05/10/2026" in html
    assert ("", "S/ 136.00") not in totales(at) and ("S/ 136.00", "S/ 129.20") in totales(at)
    enlaces = [parse_qs(urlparse(b.proto.url).query)["text"][0] for b in at.get("link_button")]
    assert esperado in enlaces


def test_un_solo_producto_no_se_puede_guardar():
    at = abrir("propuesta")
    at.selectbox(key="propuesta_cliente").set_value("c001").run()
    at.multiselect(key="pp_c001_0_productos").set_value(["p005"]).run()
    assert ok(at)
    assert not [b for b in at.button if b.label == "Guardar en la agenda"]
    assert any("al menos 2 productos" in c.value for c in at.caption)


def test_quitar_una_propuesta_guardada():
    at = armar_propuesta_para(abrir("propuesta"), "c001", ["p005", "p009"], 0)
    boton(at, "Guardar en la agenda").click().run()
    boton(at, "Quitar").click().run()
    assert ok(at) and "Propuesta de Juan Pérez quitada de la agenda." in exito(at)
    assert any("Todavía no guardaste propuestas" in i.value for i in at.info)


# =====================================================================
# Administración: resumen
# =====================================================================
def test_resumen_indicadores_calculados_a_mano():
    # 22 compras (días distintos por cliente); 8455 / 22 = 384.32; top 3 = (3235+2650+1195)/8455 = 83.7 %
    assert indicadores(abrir("resumen")) == {
        "Ventas totales": "S/ 8,455",
        "Compras": "22",
        "Ticket promedio": "S/ 384",
        "Clientes con compras": "7",
        "Top 3 clientes": "84 %",
    }


def test_resumen_tablas():
    at = abrir("resumen")
    por_mes, por_categoria, segmentos = tabla(at, 0), tabla(at, 1), tabla(at, 2)
    assert list(por_mes["mes"]) == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert por_mes["variacion_pct"].iloc[0] == "—" and por_mes["variacion_pct"].iloc[1] == "+278.4 %"
    assert por_categoria["categoria"].iloc[0] == "Cómputo" and por_categoria["ventas"].iloc[0] == 4750.0
    assert list(segmentos["segmento"]) == ["Alto", "Medio", "Bajo", "Sin compras"]
    assert list(segmentos["clientes"]) == [3, 2, 2, 1]


def test_resumen_ofrece_descargar_las_ventas():
    assert len(abrir("resumen").get("download_button")) == 1


def test_restablecer_los_datos_de_ejemplo_descarta_los_cambios():
    at = abrir("registro_ventas")
    boton(at, "Registrar venta").click().run()
    at.switch_page("paginas/resumen.py").run()
    assert indicadores(at)["Ventas totales"] == "S/ 10,855"
    at.checkbox(key="confirmar_restablecer").check().run()
    boton(at, "Restablecer datos de ejemplo").click().run()
    assert "Datos de ejemplo restablecidos." in exito(at)
    assert indicadores(at)["Ventas totales"] == "S/ 8,455"


def test_restablecer_exige_confirmacion():
    assert boton(abrir("resumen"), "Restablecer datos de ejemplo").disabled


# =====================================================================
# Administración: clientes
# =====================================================================
def test_lista_de_clientes():
    t = tabla(abrir("clientes"))
    assert len(t) == 8
    juan = t[t["Cliente"] == "Juan Pérez"].iloc[0]
    assert (juan["Tipo"], juan["Segmento"], juan["Compras"], juan["Días sin comprar"]) == ("Frecuente", "Alto", 3, "40")
    rosa = t[t["Cliente"] == "Rosa Chávez"].iloc[0]
    assert (rosa["Segmento"], rosa["Días sin comprar"], rosa["Categorías habituales"]) == ("Sin compras", "—", "—")


def test_buscar_clientes_por_nombre():
    at = abrir("clientes")
    at.text_input(key="buscar_cliente").set_value("ana").run()
    assert list(tabla(at)["Cliente"]) == ["Ana Ríos"]


def test_registrar_un_cliente_nuevo():
    at = abrir("clientes")
    at.text_input(key="nc_nombre_0").set_value("  Ana   Torres ").run()
    at.text_input(key="nc_tel_0").set_value("900 000 009").run()
    boton(at, "Registrar cliente").click().run()
    assert ok(at) and "Cliente Ana Torres registrado (c009)." in exito(at)
    t = tabla(at)
    assert len(t) == 9
    nueva = t[t["Cliente"] == "Ana Torres"].iloc[0]
    assert (nueva["Tipo"], nueva["Segmento"], nueva["Teléfono"]) == ("Regular", "Sin compras", "51900000009")
    assert at.text_input(key="nc_nombre_1").value == ""  # el formulario quedó limpio


def test_registrar_cliente_sin_nombre_muestra_el_error_y_conserva_lo_escrito():
    at = abrir("clientes")
    at.text_input(key="nc_tel_0").set_value("900000009").run()
    boton(at, "Registrar cliente").click().run()
    assert errores(at) == ["El nombre no puede estar vacío."]
    assert at.text_input(key="nc_tel_0").value == "900000009"
    assert len(tabla(at)) == 8


def test_registrar_cliente_con_telefono_invalido():
    at = abrir("clientes")
    at.text_input(key="nc_nombre_0").set_value("Ana Torres").run()
    at.text_input(key="nc_tel_0").set_value("abc123").run()
    boton(at, "Registrar cliente").click().run()
    assert len(errores(at)) == 1 and "Teléfono inválido" in errores(at)[0]
    assert len(tabla(at)) == 8


def test_editar_un_cliente():
    at = abrir("clientes")
    at.selectbox(key="editar_cliente_sel").select("c003").run()
    at.text_input(key="ec_nombre_c003_0").set_value("Carlos Ruiz Díaz").run()
    at.text_input(key="ec_tel_c003_0").set_value("").run()
    boton(at, "Guardar cambios").click().run()
    assert ok(at) and "Datos de Carlos Ruiz Díaz actualizados." in exito(at)
    carlos = tabla(at)[tabla(at)["Cliente"] == "Carlos Ruiz Díaz"].iloc[0]
    assert carlos["Teléfono"] == "—" and carlos["Compras"] == 2  # sus compras siguen asociadas


def test_eliminar_un_cliente_sin_ventas():
    at = abrir("clientes")
    at.text_input(key="nc_nombre_0").set_value("Ana Torres").run()
    boton(at, "Registrar cliente").click().run()
    at.selectbox(key="editar_cliente_sel").select("c009").run()
    assert boton(at, "Eliminar cliente").disabled
    at.checkbox(key="conf_del_cliente_c009").check().run()
    boton(at, "Eliminar cliente").click().run()
    assert ok(at) and "Cliente Ana Torres eliminado." in exito(at)
    assert len(tabla(at)) == 8


def test_no_se_puede_eliminar_un_cliente_con_ventas():
    at = abrir("clientes")
    at.checkbox(key="conf_del_cliente_c001").check().run()
    boton(at, "Eliminar cliente").click().run()
    assert errores(at) == ["No se puede eliminar el cliente c001: tiene 4 ventas registradas."]
    assert len(tabla(at)) == 8


# =====================================================================
# Administración: productos
# =====================================================================
def test_lista_de_productos():
    t = tabla(abrir("productos"))
    assert len(t) == 10
    laptop = t[t["Producto"] == "Laptop 14 pulgadas"].iloc[0]
    assert (laptop["Categoría"], laptop["Precio actual"], laptop["Unidades vendidas"], laptop["Ingresos"]) == (
        "Cómputo",
        2400.0,
        2,
        4750.0,
    )


def test_el_catalogo_muestra_la_oferta_vigente_hasta_su_vencimiento():
    abrir("productos")
    ofertar("p002", 20)  # vigente del 01/10 al 31/10/2026; referencia: 05/10/2026
    t = tabla(abrir("productos"))
    mouse = t[t["Producto"] == "Mouse inalámbrico"].iloc[0]
    assert (mouse["Oferta"], mouse["Precio con oferta"]) == ("-20 % hasta el 31/10/2026", 36.0)
    laptop = t[t["Producto"] == "Laptop 14 pulgadas"].iloc[0]
    assert laptop["Oferta"] == "" and laptop["Precio con oferta"] == 2400.0


def test_el_catalogo_no_muestra_ofertas_vencidas():
    from interfaz import comun
    from ventas.ofertas import Oferta

    abrir("productos")
    comun.repositorio().guardar_oferta(Oferta("p002", 20, date(2026, 9, 1), date(2026, 9, 30)))
    t = tabla(abrir("productos"))
    assert t[t["Producto"] == "Mouse inalámbrico"].iloc[0]["Oferta"] == ""


def test_registrar_un_producto_en_una_categoria_existente():
    at = abrir("productos")
    at.text_input(key="np_0_nombre").set_value("Cable HDMI").run()
    at.selectbox(key="np_0_cat").select("accesorios").run()
    at.number_input(key="np_0_precio").set_value(25.0).run()
    boton(at, "Registrar producto").click().run()
    assert ok(at) and "Producto Cable HDMI registrado (p011)." in exito(at)
    nuevo = tabla(at)[tabla(at)["Producto"] == "Cable HDMI"].iloc[0]
    assert (nuevo["Categoría"], nuevo["Precio actual"], nuevo["Unidades vendidas"]) == ("Accesorios", 25.0, 0)


def test_registrar_un_producto_con_una_categoria_nueva():
    at = abrir("productos")
    at.text_input(key="np_0_nombre").set_value("Impresora láser").run()
    at.selectbox(key="np_0_cat").select("Nueva categoría…").run()
    at.text_input(key="np_0_cat_nueva").set_value("Impresión 3D").run()
    boton(at, "Registrar producto").click().run()
    assert ok(at) and "Producto Impresora láser registrado (p011)." in exito(at)
    assert tabla(at)[tabla(at)["Producto"] == "Impresora láser"].iloc[0]["Categoría"] == "Impresion 3d"
    at.switch_page("paginas/pedido.py").run()  # la categoría nueva ya se puede usar al armar pedidos
    assert "Impresion 3d" in at.get("button_group")[0].options


def test_registrar_producto_sin_nombre():
    at = abrir("productos")
    boton(at, "Registrar producto").click().run()
    assert errores(at) == ["El nombre no puede estar vacío."]


def test_cambiar_el_precio_de_un_producto_no_altera_las_ventas_pasadas():
    at = abrir("productos")
    at.selectbox(key="editar_producto_sel").select("p001").run()
    at.number_input(key="ep_p001_0_precio").set_value(2500.0).run()
    boton(at, "Guardar cambios").click().run()
    assert ok(at) and "Producto Laptop 14 pulgadas actualizado." in exito(at)
    laptop = tabla(at)[tabla(at)["Producto"] == "Laptop 14 pulgadas"].iloc[0]
    assert laptop["Precio actual"] == 2500.0 and laptop["Ingresos"] == 4750.0
    at.switch_page("paginas/resumen.py").run()
    assert indicadores(at)["Ventas totales"] == "S/ 8,455"


def test_no_se_puede_eliminar_un_producto_con_ventas_pero_si_uno_nuevo():
    at = abrir("productos")
    at.checkbox(key="conf_del_producto_p001").check().run()
    boton(at, "Eliminar producto").click().run()
    assert len(errores(at)) == 1 and "tiene 2 ventas registradas" in errores(at)[0]
    at.text_input(key="np_0_nombre").set_value("Cable HDMI").run()
    boton(at, "Registrar producto").click().run()
    at.selectbox(key="editar_producto_sel").select("p011").run()
    at.checkbox(key="conf_del_producto_p011").check().run()
    boton(at, "Eliminar producto").click().run()
    assert "Producto Cable HDMI eliminado." in exito(at) and len(tabla(at)) == 10


# =====================================================================
# Administración: ventas
# =====================================================================
def test_registrar_una_venta_muestra_como_cambia_la_agenda():
    at = abrir("registro_ventas")
    boton(at, "Registrar venta").click().run()  # Juan Pérez, laptop, hoy
    assert ok(at)
    assert exito(at) == ["Venta v031 registrada por S/ 2,400.00. Juan Pérez pasó de «Reactivar» a «Fidelizar» en la agenda."]


def test_la_venta_registrada_cambia_la_agenda():
    at = abrir("registro_ventas")
    boton(at, "Registrar venta").click().run()
    at.switch_page("paginas/agenda.py").run()
    assert ok(at)
    assert (indicadores(at)["Por reactivar"], indicadores(at)["Por fidelizar"]) == ("1", "4")
    assert tarjetas(at)[:2] == ["1. Pedro Salas", "2. Juan Pérez"]


def test_el_total_de_la_venta_se_calcula_al_cambiar_la_cantidad():
    at = abrir("registro_ventas")
    at.number_input(key="venta_cantidad_0").set_value(3).run()
    assert "**Total de la venta: S/ 7,200.00**" in [m.value for m in at.markdown]


def test_el_precio_se_sugiere_segun_el_producto_elegido():
    at = abrir("registro_ventas")
    at.selectbox(key="venta_producto_0").select("p002").run()
    assert at.number_input(key="venta_precio_0_p002").value == 45.0


def test_registrar_una_venta_con_precio_distinto_al_del_producto():
    at = abrir("registro_ventas")
    at.selectbox(key="venta_cliente_0").select("c003").run()
    at.selectbox(key="venta_producto_0").select("p002").run()
    at.number_input(key="venta_precio_0_p002").set_value(40.0).run()
    boton(at, "Registrar venta").click().run()
    assert any("Venta v031 registrada por S/ 40.00" in t for t in exito(at))
    ultima = tabla(at).iloc[0]  # el historial muestra primero la más reciente
    assert (ultima["id_venta"], ultima["precio_unitario"], ultima["monto"]) == ("v031", 40.0, 40.0)


def test_historial_ordenado_por_fecha_y_filtrable():
    at = abrir("registro_ventas")
    t = tabla(at)
    assert len(t) == 30 and str(t["fecha"].iloc[0])[:10] == "2026-10-03"
    at.selectbox(key="filtro_venta_cliente").select("Juan Pérez").run()
    assert len(tabla(at)) == 4
    at.selectbox(key="filtro_venta_categoria").select("perifericos").run()
    assert len(tabla(at)) == 2  # mouse y teclado


def test_anular_una_venta():
    at = abrir("registro_ventas")
    assert boton(at, "Anular venta").disabled
    at.checkbox(key="conf_anular_venta").check().run()
    boton(at, "Anular venta").click().run()  # la más reciente: v030
    assert ok(at) and "Venta v030 anulada." in exito(at)
    assert len(tabla(at)) == 29


def test_sin_ventas_la_agenda_y_el_resumen_explican_que_falta():
    from interfaz import comun

    at = abrir("resumen")
    repo = comun.repositorio()  # la misma base que usa la aplicación
    for venta in repo.cargar_todo().ventas:
        repo.eliminar_venta(venta.id_venta)
    at.switch_page("paginas/agenda.py").run()
    assert ok(at) and tarjetas(at) == []
    assert any("Todavía no hay clientes para contactar" in i.value for i in at.info)
    at.switch_page("paginas/resumen.py").run()
    assert ok(at) and any("Aún no hay ventas" in i.value for i in at.info)


# =====================================================================
# Diseño: banner, etiquetas, íconos y pie de página
# =====================================================================
@pytest.mark.parametrize(
    ("pagina", "seccion", "titulo"),
    [
        ("agenda", "Asesoría", "Agenda de fidelización"),
        ("pedido", "Asesoría · modo mostrador", "Arma mi pedido"),
        ("ofertas", "Asesoría", "Ofertas de temporada"),
        ("propuesta", "Asesoría", "Propuesta personalizada"),
        ("resumen", "Administración", "Resumen del negocio"),
        ("clientes", "Administración", "Clientes"),
        ("productos", "Administración", "Productos"),
        ("registro_ventas", "Administración", "Ventas"),
    ],
)
def test_cada_pantalla_tiene_su_banner_con_ilustracion(pagina, seccion, titulo):
    html = next(m.value for m in abrir(pagina).markdown if 'class="hero"' in m.value)
    assert f'<div class="eyebrow">{seccion}</div>' in html
    assert f"<h1>{titulo}</h1>" in html
    assert "<svg" in html


def test_las_etiquetas_de_la_agenda_usan_el_tono_de_su_prioridad():
    html = " ".join(m.value for m in abrir().markdown if "chip" in m.value)
    assert 'chip-alta">Reactivar cliente' in html
    assert 'chip-media">Fidelizar cliente' in html
    assert 'chip-baja">Ofrecer productos complementarios' in html
    assert 'chip-neutro">Cliente frecuente' in html


def test_cada_producto_del_pedido_lleva_su_icono():
    filas = [m.value for m in abrir("pedido").markdown if 'class="prod"' in m.value]
    assert filas
    assert all(f.count("<svg") == f.count('class="prod"') for f in filas)


@pytest.mark.parametrize("pagina", PAGINAS)
def test_toda_pantalla_termina_con_el_pie_de_pagina(pagina):
    assert any('class="pie"' in m.value for m in abrir(pagina).markdown)


def test_un_producto_con_simbolos_no_rompe_el_diseno():
    at = abrir("productos")
    at.text_input(key="np_0_nombre").set_value("Mouse <Pro> & Cía").run()
    at.selectbox(key="np_0_cat").select("perifericos").run()
    at.number_input(key="np_0_precio").set_value(10.0).run()
    boton(at, "Registrar producto").click().run()
    assert ok(at)
    at.switch_page("paginas/pedido.py").run()
    at.number_input(key="presupuesto_pedido").set_value(100.0).run()
    filas = " ".join(m.value for m in at.markdown if 'class="prod"' in m.value)
    assert "Mouse &lt;Pro&gt; &amp; Cía" in filas
    assert "<Pro>" not in filas
