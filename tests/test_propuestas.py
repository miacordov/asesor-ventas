from datetime import date

import pytest

from ventas.mensajes import mensaje_propuesta
from ventas.modelos import ClienteFrecuente, Producto
from ventas.ofertas import Oferta
from ventas.propuestas import LineaPropuesta, Propuesta, armar_propuesta

HOY = date(2026, 10, 5)
PRODUCTOS = (
    Producto("p001", "Mouse", "perifericos", 45.0),
    Producto("p002", "Teclado", "perifericos", 120.0),
    Producto("p003", "Hub", "accesorios", 60.0),
)
VIGENTES = {"p002": Oferta("p002", 25, date(2026, 10, 1), date(2026, 10, 31))}  # 120 -> 90
NOMBRES = {p.id_producto: p.nombre for p in PRODUCTOS}


def test_armar_propuesta_con_precios_de_oferta_y_descuento_del_combo():
    propuesta = armar_propuesta("c001", ["p001", "p002"], 10, HOY, PRODUCTOS, VIGENTES)
    assert propuesta.lineas == (LineaPropuesta("p001", 45.0, 45.0), LineaPropuesta("p002", 120.0, 90.0))
    assert propuesta.subtotal == 135.0
    assert propuesta.total == 121.5  # 135 - 10 %


def test_un_solo_producto_no_es_una_propuesta():
    with pytest.raises(ValueError, match="al menos 2 productos"):
        armar_propuesta("c001", ["p001"], 0, HOY, PRODUCTOS, {})


def test_no_se_repiten_productos():
    with pytest.raises(ValueError, match="repite"):
        armar_propuesta("c001", ["p001", "p002", "p001"], 0, HOY, PRODUCTOS, {})


def test_producto_inexistente():
    with pytest.raises(ValueError, match="No existe el producto p999"):
        armar_propuesta("c001", ["p001", "p999"], 0, HOY, PRODUCTOS, {})


@pytest.mark.parametrize("descuento", [-1, 91, 5.5, True])
def test_descuento_del_combo_invalido(descuento):
    with pytest.raises(ValueError, match="entre 0 y 90"):
        armar_propuesta("c001", ["p001", "p002"], descuento, HOY, PRODUCTOS, {})


def test_linea_con_precio_mayor_al_normal_es_invalida():
    with pytest.raises(ValueError, match="Precio inválido"):
        LineaPropuesta("p001", 45.0, 50.0)


def test_mensaje_con_oferta_y_descuento():
    propuesta = armar_propuesta("c001", ["p001", "p002"], 10, HOY, PRODUCTOS, VIGENTES)
    assert mensaje_propuesta(ClienteFrecuente("c001", "Juan Pérez"), propuesta, NOMBRES) == (
        "Hola Juan, te preparamos una propuesta especial: Mouse y Teclado (en oferta) por S/ 135.00, "
        "y con tu 10 % de descuento te queda en S/ 121.50. ¡Escríbenos si te interesa!"
    )


def test_mensaje_sin_descuento():
    propuesta = Propuesta("c001", (LineaPropuesta("p001", 45.0, 45.0), LineaPropuesta("p003", 60.0, 60.0)), 0, HOY)
    assert mensaje_propuesta(ClienteFrecuente("c001", "Ana"), propuesta, NOMBRES) == (
        "Hola Ana, te preparamos una propuesta especial: Mouse y Hub por S/ 105.00. ¡Escríbenos si te interesa!"
    )
