from datetime import date

import pytest

from ventas.combos import Combo, lineas_combo, total_combo, ventas_del_combo
from ventas.modelos import Producto, Venta
from ventas.ofertas import Oferta

HOY = date(2026, 10, 5)
PRODUCTOS = (
    Producto("p001", "Mouse", "perifericos", 45.0),
    Producto("p002", "Hub", "accesorios", 60.0),
)
OFERTA_MOUSE = Oferta("p001", 20, date(2026, 10, 1), date(2026, 10, 31))  # 45 -> 36
COMBO = Combo("cb001", "c001", ("p001", "p002"), HOY)


def test_mientras_la_oferta_esta_vigente_el_combo_la_muestra():
    lineas = lineas_combo(COMBO, PRODUCTOS, {"p001": OFERTA_MOUSE})
    assert [(linea.producto.nombre, linea.precio, linea.oferta) for linea in lineas] == [
        ("Mouse", 36.0, OFERTA_MOUSE),
        ("Hub", 60.0, None),
    ]
    assert total_combo(lineas) == 96.0


def test_sin_oferta_vigente_vuelve_al_precio_normal():
    assert total_combo(lineas_combo(COMBO, PRODUCTOS, {})) == 105.0


def test_registrar_genera_una_venta_por_producto_al_precio_del_dia():
    lineas = lineas_combo(COMBO, PRODUCTOS, {"p001": OFERTA_MOUSE})
    assert ventas_del_combo(COMBO, lineas, ["v031", "v032"], HOY) == (
        Venta("v031", "c001", "p001", 1, 36.0, HOY),
        Venta("v032", "c001", "p002", 1, 60.0, HOY),
    )


def test_un_combo_registrado_no_se_registra_otra_vez():
    registrado = Combo("cb001", "c001", ("p001", "p002"), HOY, ("v031", "v032"))
    assert not registrado.pendiente
    with pytest.raises(ValueError, match="ya se registró"):
        ventas_del_combo(registrado, lineas_combo(registrado, PRODUCTOS, {}), ["v033", "v034"], HOY)


def test_combo_con_un_producto_borrado_no_se_registra():
    lineas = lineas_combo(COMBO, PRODUCTOS[:1], {})
    with pytest.raises(ValueError, match="ya no están en el catálogo"):
        ventas_del_combo(COMBO, lineas, ["v031"], HOY)


@pytest.mark.parametrize(
    ("ids", "mensaje"),
    [(("p001",), "al menos 2"), (("p001", "p001"), "repite"), (("p001", "P 2"), "id_producto")],
)
def test_combo_invalido(ids, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        Combo("cb001", "c001", ids, HOY)


# ---------------------------------------------------------------------
# Clientes no registrados
# ---------------------------------------------------------------------
def test_combo_de_cliente_no_registrado():
    combo = Combo("cb001", None, ("p001", "p002"), HOY, nombre_cliente="Pedro Gómez")
    assert not combo.registrado and combo.pendiente


@pytest.mark.parametrize(
    ("id_cliente", "nombre", "mensaje"),
    [(None, "", "nombre del cliente no registrado"), (None, "   ", "nombre del cliente no registrado"), ("c001", "Pedro", "no de ambos")],
)
def test_combo_sin_cliente_o_con_ambos(id_cliente, nombre, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        Combo("cb001", id_cliente, ("p001", "p002"), HOY, nombre_cliente=nombre)


def test_las_ventas_del_no_registrado_van_al_cliente_que_se_crea():
    combo = Combo("cb001", None, ("p001", "p002"), HOY, nombre_cliente="Pedro Gómez")
    lineas = lineas_combo(combo, PRODUCTOS, {})
    with pytest.raises(ValueError, match="falta crear su cliente"):
        ventas_del_combo(combo, lineas, ["v031", "v032"], HOY)
    assert {v.id_cliente for v in ventas_del_combo(combo, lineas, ["v031", "v032"], HOY, "c009")} == {"c009"}


# ---------------------------------------------------------------------
# Pedido unificado: estados y una sola regla de precio
# ---------------------------------------------------------------------
from ventas.combos import congelar, descuento_de, total_combo_con_descuento  # noqa: E402
from ventas.modelos import ClienteFrecuente, ClienteRegular  # noqa: E402

FRECUENTE = ClienteFrecuente("c001", "Juan", "")
REGULAR = ClienteRegular("c001", "Juan", "")


def test_el_estado_se_deduce_de_lo_que_tiene_el_pedido():
    borrador = Combo("cb001", "c001", ("p001", "p002"), HOY)
    enviado = Combo("cb001", "c001", ("p001", "p002"), HOY, precios=(36.0, 60.0), descuento=10)
    vendido = Combo("cb001", "c001", ("p001", "p002"), HOY, ("v031", "v032"), precios=(36.0, 60.0), descuento=10)
    descartado = Combo("cb001", "c001", ("p001", "p002"), HOY, descartado=True)
    assert [c.estado for c in (borrador, enviado, vendido, descartado)] == ["borrador", "enviado", "vendido", "descartado"]
    assert [c.pendiente for c in (borrador, enviado, vendido, descartado)] == [True, True, False, False]


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"precios": (36.0,)}, "un precio por producto"),
        ({"precios": (36.0, 0.0)}, "precio"),
        ({"descuento": 91}, "descuento"),
        ({"descuento": -1}, "descuento"),
        ({"descuento": 5.5}, "descuento"),
        ({"descartado": True, "ids_ventas": ("v031", "v032")}, "vendido"),
    ],
)
def test_pedido_invalido(cambios, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        Combo("cb001", "c001", ("p001", "p002"), HOY, **cambios)


def test_el_descuento_es_el_manual_o_el_del_cliente():
    assert descuento_de(COMBO, FRECUENTE) == 10
    assert descuento_de(COMBO, REGULAR) == 0
    assert descuento_de(COMBO, None) == 0  # cliente no registrado
    assert descuento_de(Combo("cb001", "c001", ("p001", "p002"), HOY, descuento=15), FRECUENTE) == 15
    assert descuento_de(Combo("cb001", "c001", ("p001", "p002"), HOY, descuento=0), FRECUENTE) == 0


def test_total_con_la_oferta_y_el_descuento():
    lineas = lineas_combo(COMBO, PRODUCTOS, {"p001": OFERTA_MOUSE})  # 36 + 60 = 96
    assert total_combo_con_descuento(lineas, 10) == 86.4


def test_al_enviarlo_los_precios_y_el_descuento_quedan_fijos():
    lineas = lineas_combo(COMBO, PRODUCTOS, {"p001": OFERTA_MOUSE})
    enviado = congelar(COMBO, lineas, 10)
    assert (enviado.estado, enviado.precios, enviado.descuento) == ("enviado", (36.0, 60.0), 10)
    # aunque la oferta venza, se cobra lo que se prometió
    fijas = lineas_combo(enviado, PRODUCTOS, {})
    assert [linea.precio for linea in fijas] == [36.0, 60.0]
    assert total_combo_con_descuento(fijas, enviado.descuento) == 86.4


def test_las_ventas_reparten_el_descuento_y_suman_el_total_exacto():
    combo = Combo("cb001", "c001", ("p001", "p002", "p003"), HOY)
    productos = PRODUCTOS + (Producto("p003", "Cable", "accesorios", 10.0),)
    lineas = lineas_combo(combo, productos, {})  # 45 + 60 + 10 = 115; -15 % = 97,75
    ventas = ventas_del_combo(combo, lineas, ["v031", "v032", "v033"], HOY, descuento=15)
    assert [v.precio_unitario for v in ventas] == [38.25, 51.0, 8.5]
    assert round(sum(v.monto for v in ventas), 2) == 97.75


def test_el_redondeo_lo_absorbe_la_ultima_linea():
    combo = Combo("cb001", "c001", ("p001", "p002", "p003"), HOY)
    productos = (
        Producto("p001", "A", "a", 10.01),
        Producto("p002", "B", "b", 10.01),
        Producto("p003", "C", "c", 10.01),
    )
    lineas = lineas_combo(combo, productos, {})  # 30,03 con 10 % = 27,03 (27,027)
    ventas = ventas_del_combo(combo, lineas, ["v031", "v032", "v033"], HOY, descuento=10)
    assert round(sum(v.monto for v in ventas), 2) == total_combo_con_descuento(lineas, 10) == 27.03


def test_no_se_vende_un_pedido_descartado():
    descartado = Combo("cb001", "c001", ("p001", "p002"), HOY, descartado=True)
    with pytest.raises(ValueError, match="descartado"):
        ventas_del_combo(descartado, lineas_combo(descartado, PRODUCTOS, {}), ["v031", "v032"], HOY)
