"""Pruebas del sistema de diseño: paleta, accesibilidad, imágenes en línea y escape de HTML."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import tomllib

from interfaz import estilo
from ventas.cargador import cargar_todo

RAIZ = Path(__file__).resolve().parent.parent
P = estilo.PALETA


def luminancia(color: str) -> float:
    r, g, b = (int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    canal = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(a: str, b: str) -> float:
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


# =====================================================================
# Accesibilidad: contraste WCAG
# =====================================================================
@pytest.mark.parametrize(
    ("texto", "fondo", "minimo"),
    [
        ("texto", "crema", 7.0),  # texto principal sobre el fondo: AAA
        ("texto", "superficie", 7.0),  # sobre las tarjetas: AAA
        ("texto_2", "crema", 4.5),  # texto secundario: AA
        ("texto_2", "superficie", 4.5),
        ("crema", "navy_900", 7.0),  # barra lateral y banner
        ("crema", "navy_700", 7.0),  # botones primarios
        ("oro_claro", "navy_900", 4.5),  # etiqueta dorada del banner
    ],
)
def test_contraste_de_la_paleta(texto, fondo, minimo):
    assert contraste(P[texto], P[fondo]) >= minimo


@pytest.mark.parametrize("tono", sorted(estilo.TONOS_ETIQUETA))
def test_contraste_de_cada_etiqueta(tono):
    fondo, texto = estilo.TONOS_ETIQUETA[tono]
    assert contraste(texto, fondo) >= 4.5


def test_la_calculadora_de_contraste_es_correcta():
    assert contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contraste("#777777", "#777777") == pytest.approx(1.0)


def test_los_colores_de_las_etiquetas_estan_en_el_css():
    for tono, (fondo, texto) in estilo.TONOS_ETIQUETA.items():
        assert f".chip-{tono}{{background:{fondo};color:{texto}}}" in estilo.CSS


# =====================================================================
# Configuración del tema
# =====================================================================
@pytest.fixture(scope="module")
def config():
    return tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


def test_el_tema_usa_la_paleta_crema_y_navy(config):
    tema = config["theme"]
    assert tema["backgroundColor"] == P["crema"]
    assert tema["primaryColor"] == P["navy_700"]
    assert tema["textColor"] == P["texto"]
    assert tema["borderColor"] == P["linea"]
    assert tema["base"] == "light"


def test_la_barra_lateral_es_navy_con_texto_crema(config):
    lateral = config["theme"]["sidebar"]
    assert lateral["backgroundColor"] == P["navy_900"]
    assert contraste(lateral["textColor"], lateral["backgroundColor"]) >= 7.0


def test_las_fuentes_del_tema_existen_en_el_proyecto(config):
    assert config["server"]["enableStaticServing"] is True
    fuentes = config["theme"]["fontFaces"]
    assert {f["weight"] for f in fuentes} == {600, 700}
    for fuente in fuentes:
        assert fuente["url"].startswith("app/static/")
        archivo = RAIZ / "static" / fuente["url"].removeprefix("app/static/")
        assert archivo.is_file() and archivo.stat().st_size > 10_000, archivo
    assert (RAIZ / "static" / "fuentes" / "LICENSE-Playfair-Display.txt").is_file()


def test_los_titulos_usan_la_fuente_serif_con_respaldo(config):
    assert config["theme"]["headingFont"].startswith("Playfair Display")
    assert "serif" in config["theme"]["headingFont"]


# =====================================================================
# Imágenes en línea: SVG escritos en el código, sin descargas ni internet
# =====================================================================
TODAS = {**estilo.ILUSTRACIONES, "logo": estilo.LOGO_SVG}


@pytest.mark.parametrize("nombre", sorted(TODAS))
def test_las_imagenes_son_svg_validos(nombre):
    raiz = ET.fromstring(TODAS[nombre])
    assert raiz.tag.endswith("svg")
    assert "viewBox" in raiz.attrib


@pytest.mark.parametrize("nombre", sorted(TODAS))
def test_las_imagenes_no_dependen_de_internet(nombre):
    svg = TODAS[nombre].replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http" not in svg and "href" not in svg and "url(" not in svg


def test_hay_una_ilustracion_por_pantalla():
    assert set(estilo.ILUSTRACIONES) == {"agenda", "pedido", "resumen", "clientes", "productos", "ventas"}


def test_cada_categoria_del_catalogo_tiene_su_icono_propio():
    generico = estilo.icono_categoria("categoria_que_no_existe")
    categorias = {p.categoria for p in cargar_todo(RAIZ / "datos").productos}
    assert categorias
    for categoria in categorias:
        assert estilo.icono_categoria(categoria) != generico, categoria


def test_una_categoria_nueva_usa_el_icono_generico():
    assert estilo.icono_categoria("impresion_3d") == estilo.icono_categoria("otra")
    ET.fromstring(estilo.icono_categoria("impresion_3d"))


# =====================================================================
# Componentes HTML: escape de lo que escribe la persona
# =====================================================================
def test_el_nombre_de_un_producto_se_escapa():
    html = estilo.fila_producto("Mouse <Pro> & Cía", "perifericos", "S/ 45.00")
    assert "Mouse &lt;Pro&gt; &amp; Cía" in html
    assert "<Pro>" not in html


def test_un_nombre_con_script_queda_inofensivo():
    html = estilo.fila_producto("<script>alert(1)</script>", "audio", "S/ 1.00", "<img src=x onerror=alert(1)>")
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html


def test_la_etiqueta_escapa_su_texto():
    assert estilo.chip("A & <b>B</b>", "ok") == '<span class="chip chip-ok">A &amp; &lt;b&gt;B&lt;/b&gt;</span>'


def test_etiqueta_con_tono_desconocido():
    with pytest.raises(ValueError, match="Tono"):
        estilo.chip("x", "fucsia")


def test_total_con_y_sin_descuento():
    con = estilo.total("Total", "S/ 607.50", tachado="S/ 675.00", nota="Ahorras S/ 67.50")
    assert '<s>S/ 675.00</s>S/ 607.50' in con and "Ahorras S/ 67.50" in con
    sin = estilo.total("Total", "S/ 110.00")
    assert "<s>" not in sin and "nota" not in sin


def test_los_componentes_no_tienen_lineas_en_blanco_ni_sangria():
    """Markdown rompe un bloque HTML con una línea en blanco o 4 espacios de sangría."""
    piezas = [
        estilo.fila_producto("Hub USB-C", "accesorios", "S/ 60.00", "Accesorios"),
        estilo.total("Total", "S/ 1.00", tachado="S/ 2.00", nota="n"),
        estilo.chip("x"),
    ]
    for pieza in piezas:
        assert "\n\n" not in pieza and "\n    " not in pieza
