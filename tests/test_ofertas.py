import math
from datetime import date

import pytest

from ventas.modelos import Producto, Venta
from ventas.ofertas import (
    TEMPORADAS,
    Oferta,
    Temporada,
    aplicar_ofertas,
    desempeno_en_temporada,
    meses_del_historial,
    ofertas_vigentes,
    temporada_proxima,
)

NAVIDAD = Temporada("navidad", "Navidad", (12,))
GRAFICA = Producto("p001", "Gráfica", "graficas", 1000.0)
USB = Producto("p002", "USB", "memorias", 30.0)
MOUSE = Producto("p003", "Mouse", "perifericos", 50.0)
SILLA = Producto("p004", "Silla", "mobiliario", 400.0)


def venta(n, producto, cantidad, anio, mes):
    return Venta(f"v{n:03d}", "c001", producto, cantidad, 10.0, date(anio, mes, 10))


# Historial de enero a diciembre de 2025 (12 meses: 1 de temporada y 11 fuera).
VENTAS = (
    venta(1, "p001", 1, 2025, 1),
    venta(2, "p001", 6, 2025, 12),  # gráfica: 6 en diciembre, 1 en el resto -> pico
    venta(3, "p002", 11, 2025, 3),  # USB: 0 en diciembre, 11 en el resto -> baja rotación
    venta(4, "p003", 1, 2025, 12),
    venta(5, "p003", 11, 2025, 6),  # mouse: 1 por mes en ambos casos -> estable
)


# ---------------------------------------------------------------------
# Oferta
# ---------------------------------------------------------------------
def test_precio_con_la_oferta():
    assert Oferta("p001", 15, date(2026, 11, 1), date(2026, 11, 30)).precio(200.0) == 170.0
    assert Oferta("p001", 33, date(2026, 11, 1), date(2026, 11, 30)).precio(99.99) == 66.99


def test_el_precio_con_oferta_nunca_llega_a_cero():
    assert Oferta("p001", 90, date(2026, 11, 1), date(2026, 11, 30)).precio(0.01) == 0.01


def test_la_oferta_rige_entre_sus_fechas_incluidas():
    oferta = Oferta("p001", 10, date(2026, 11, 1), date(2026, 11, 30))
    assert [oferta.vigente(date(2026, 11, d)) for d in (1, 15, 30)] == [True, True, True]
    assert not oferta.vigente(date(2026, 10, 31)) and not oferta.vigente(date(2026, 12, 1))


@pytest.mark.parametrize("porcentaje", [0, 91, -5, 12.5, True, "10"])
def test_porcentaje_invalido(porcentaje):
    with pytest.raises(ValueError, match="entre 1 y 90"):
        Oferta("p001", porcentaje, date(2026, 11, 1), date(2026, 11, 30))


def test_la_oferta_no_termina_antes_de_empezar():
    with pytest.raises(ValueError, match="antes de empezar"):
        Oferta("p001", 10, date(2026, 11, 30), date(2026, 11, 1))


def test_identificador_invalido():
    with pytest.raises(ValueError, match="id_producto"):
        Oferta("P 1", 10, date(2026, 11, 1), date(2026, 11, 30))


# ---------------------------------------------------------------------
# Temporadas
# ---------------------------------------------------------------------
def test_temporadas_predefinidas():
    assert TEMPORADAS["escolar"].meses == (2, 3)
    assert TEMPORADAS["fin_de_anio"].meses == (11, 12)
    assert TEMPORADAS["fiestas_patrias"].incluye(date(2026, 7, 28))


def test_temporada_con_meses_invalidos():
    with pytest.raises(ValueError, match="meses"):
        Temporada("x", "X", (13,))


def test_meses_del_historial_cruza_el_anio():
    ventas = [venta(1, "p001", 1, 2025, 11), venta(2, "p001", 1, 2026, 2)]
    assert meses_del_historial(ventas) == ((2025, 11), (2025, 12), (2026, 1), (2026, 2))
    assert meses_del_historial([]) == ()


# ---------------------------------------------------------------------
# Desempeño en temporada (calculado a mano)
# ---------------------------------------------------------------------
def test_desempeno_calculado_a_mano():
    resultado = desempeno_en_temporada([USB, MOUSE, GRAFICA, SILLA], VENTAS, NAVIDAD)
    filas = [(d.producto.id_producto, d.unidades_temporada, d.promedio_temporada, d.promedio_resto, d.indice) for d in resultado]
    assert filas == [
        ("p001", 6, 6.0, 0.09, 66.0),  # 6 / (1/11) = 66
        ("p003", 1, 1.0, 1.0, 1.0),
        ("p002", 0, 0.0, 1.0, 0.0),
        ("p004", 0, 0.0, 0.0, 0.0),
    ]
    assert [d.sugerencia for d in resultado] == ["pico", "estable", "baja_rotacion", "sin_ventas"]


def test_producto_que_solo_vende_en_temporada():
    (d,) = desempeno_en_temporada([GRAFICA], [venta(1, "p001", 2, 2025, 12), venta(2, "p003", 1, 2025, 1)], NAVIDAD)
    assert math.isinf(d.indice) and d.sugerencia == "pico"


def test_sin_ventas_no_falla():
    (d,) = desempeno_en_temporada([GRAFICA], [], NAVIDAD)
    assert d.sugerencia == "sin_ventas" and d.unidades_temporada == 0


# ---------------------------------------------------------------------
# Ofertas vigentes y precios
# ---------------------------------------------------------------------
def test_solo_cuentan_las_ofertas_vigentes():
    noviembre = Oferta("p001", 10, date(2026, 11, 1), date(2026, 11, 30))
    diciembre = Oferta("p002", 20, date(2026, 12, 1), date(2026, 12, 31))
    assert ofertas_vigentes([noviembre, diciembre], date(2026, 11, 15)) == {"p001": noviembre}
    assert ofertas_vigentes([noviembre, diciembre], date(2027, 1, 1)) == {}


def test_aplicar_ofertas_cambia_solo_los_productos_ofertados():
    vigentes = {"p001": Oferta("p001", 25, date(2026, 11, 1), date(2026, 11, 30))}
    grafica, usb = aplicar_ofertas([GRAFICA, USB], vigentes)
    assert grafica.precio == 750.0 and grafica.nombre == "Gráfica"
    assert usb == USB


# ---------------------------------------------------------------------
# Fechas de temporada
# ---------------------------------------------------------------------
def test_fechas_de_la_proxima_temporada():
    fin_de_anio = TEMPORADAS["fin_de_anio"]
    assert fin_de_anio.fechas(date(2026, 10, 5)) == (date(2026, 11, 1), date(2026, 12, 31))
    # Ya empezó: la oferta arranca hoy.
    assert fin_de_anio.fechas(date(2026, 11, 20)) == (date(2026, 11, 20), date(2026, 12, 31))
    # Ya pasó este año: la del año siguiente (febrero bisiesto incluido).
    assert TEMPORADAS["escolar"].fechas(date(2027, 4, 1)) == (date(2028, 2, 1), date(2028, 3, 31))


@pytest.mark.parametrize(
    ("hoy", "clave"),
    [
        (date(2026, 10, 5), "fin_de_anio"),
        (date(2026, 12, 15), "fin_de_anio"),
        (date(2027, 1, 10), "escolar"),
        (date(2026, 4, 1), "dia_de_la_madre"),
        (date(2026, 6, 30), "fiestas_patrias"),
    ],
)
def test_temporada_proxima(hoy, clave):
    assert temporada_proxima(hoy).clave == clave
