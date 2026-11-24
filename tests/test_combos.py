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
