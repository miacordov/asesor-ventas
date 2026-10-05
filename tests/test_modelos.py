from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from ventas.modelos import (
    Cliente,
    ClienteFrecuente,
    ClienteRegular,
    Producto,
    Recomendacion,
    Venta,
)


# ---------- Cliente (herencia y polimorfismo) ----------
def test_cliente_es_abstracto():
    with pytest.raises(TypeError):
        Cliente("c001", "Juan")


def test_descuento_polimorfico():
    regular = ClienteRegular("c001", "Juan")
    frecuente = ClienteFrecuente("c002", "Ana")
    assert regular.descuento() == 0.0
    assert frecuente.descuento() == 0.10


def test_cliente_telefono_opcional():
    assert ClienteRegular("c001", "Juan").telefono == ""


@pytest.mark.parametrize("id_malo", ["Juan", "c 001", "1abc", "", "c-001", "Ñandú"])
def test_cliente_id_invalido(id_malo):
    with pytest.raises(ValueError):
        ClienteRegular(id_malo, "Juan")


@pytest.mark.parametrize("nombre", ["", "   "])
def test_cliente_nombre_vacio(nombre):
    with pytest.raises(ValueError):
        ClienteRegular("c001", nombre)


def test_cliente_inmutable():
    c = ClienteRegular("c001", "Juan")
    with pytest.raises(FrozenInstanceError):
        c.nombre = "Otro"


# ---------- Producto ----------
def test_producto_valido():
    p = Producto("p001", "Mouse inalámbrico", "perifericos", 35.5)
    assert p.precio == 35.5


@pytest.mark.parametrize("precio", [0, -1, "10", None])
def test_producto_precio_invalido(precio):
    with pytest.raises(ValueError):
        Producto("p001", "Mouse", "perifericos", precio)


def test_producto_categoria_debe_ser_atomo():
    with pytest.raises(ValueError):
        Producto("p001", "Mouse", "Periféricos", 10)


# ---------- Venta ----------
def _venta(**cambios):
    datos = {
        "id_venta": "v001",
        "id_cliente": "c001",
        "id_producto": "p001",
        "cantidad": 2,
        "precio_unitario": 35.5,
        "fecha": date(2026, 9, 1),
    }
    datos.update(cambios)
    return Venta(**datos)


def test_venta_monto():
    assert _venta().monto == 71.0


def test_venta_monto_redondea():
    assert _venta(cantidad=3, precio_unitario=0.1).monto == 0.3


@pytest.mark.parametrize("cantidad", [0, -2, 1.5, "2"])
def test_venta_cantidad_invalida(cantidad):
    with pytest.raises(ValueError):
        _venta(cantidad=cantidad)


def test_venta_precio_invalido():
    with pytest.raises(ValueError):
        _venta(precio_unitario=0)


def test_venta_fecha_debe_ser_date():
    with pytest.raises(ValueError):
        _venta(fecha="2026-09-01")


def test_venta_ids_invalidos():
    with pytest.raises(ValueError):
        _venta(id_cliente="Juan Perez")


def test_venta_iguales_son_iguales_y_hashables():
    assert _venta() == _venta()
    assert len({_venta(), _venta()}) == 1


# ---------- Recomendacion ----------
def test_recomendacion_valida():
    r = Recomendacion("c001", "p002", soporte=2, confianza=0.67)
    assert r.soporte == 2


@pytest.mark.parametrize("confianza", [-0.1, 1.1])
def test_recomendacion_confianza_fuera_de_rango(confianza):
    with pytest.raises(ValueError):
        Recomendacion("c001", "p002", soporte=1, confianza=confianza)


def test_recomendacion_soporte_minimo():
    with pytest.raises(ValueError):
        Recomendacion("c001", "p002", soporte=0, confianza=0.5)
