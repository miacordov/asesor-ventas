from datetime import date

import pytest

from ventas.contactos import (
    RESULTADOS,
    Contacto,
    conversion,
    nuevo_contacto,
    pospuestos,
    ultimo_contacto,
)
from ventas.modelos import Venta

HOY = date(2026, 11, 24)


def venta(n, cliente, dia, mes=11):
    return Venta(f"v{n:03d}", cliente, "p001", 1, 10.0, date(2026, mes, dia))


def test_cada_resultado_propone_cuando_volver():
    assert {clave: dias for clave, (_, dias) in RESULTADOS.items()} == {
        "propuesta_enviada": 3,
        "interesado": 3,
        "no_responde": 7,
        "no_interesado": 30,
    }


def test_nuevo_contacto_calcula_la_fecha_para_volver():
    assert nuevo_contacto("c001", HOY, "no_responde") == Contacto("c001", HOY, "no_responde", date(2026, 12, 1))
    assert nuevo_contacto("c001", HOY, "no_responde", dias=0).volver_el == HOY


@pytest.mark.parametrize(
    ("resultado", "dias", "mensaje"),
    [("enojado", 3, "Resultado desconocido"), ("interesado", -1, "días"), ("interesado", 400, "días")],
)
def test_contacto_invalido(resultado, dias, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        nuevo_contacto("c001", HOY, resultado, dias=dias)


def test_el_ultimo_contacto_es_el_mas_reciente():
    viejo = nuevo_contacto("c001", date(2026, 11, 1), "no_responde")
    nuevo = nuevo_contacto("c001", date(2026, 11, 20), "interesado")
    otro = nuevo_contacto("c002", date(2026, 11, 22), "interesado")
    assert ultimo_contacto([nuevo, otro, viejo], "c001") == nuevo
    assert ultimo_contacto([otro], "c001") is None


def test_pospuestos_hasta_la_fecha_para_volver():
    contactos = [
        nuevo_contacto("c001", date(2026, 11, 20), "no_responde"),  # vuelve el 27/11
        nuevo_contacto("c002", date(2026, 11, 20), "interesado"),  # vuelve el 23/11: ya pasó
        nuevo_contacto("c003", date(2026, 11, 1), "no_interesado"),  # vuelve el 01/12
        nuevo_contacto("c003", date(2026, 11, 21), "interesado", dias=0),  # el último manda: hoy ya vuelve
    ]
    assert pospuestos(contactos, HOY) == {"c001"}


def test_conversion_cuenta_quien_compro_en_los_15_dias_siguientes():
    contactos = [
        nuevo_contacto("c001", date(2026, 11, 1), "propuesta_enviada"),  # compró el 10/11: sí
        nuevo_contacto("c002", date(2026, 11, 1), "interesado"),  # compró el 20/11: fuera de los 15 días
        nuevo_contacto("c003", date(2026, 11, 1), "no_responde"),  # compró el mismo día del contacto: no cuenta
        nuevo_contacto("c004", date(2026, 11, 20), "interesado"),  # sin compras
        nuevo_contacto("c005", date(2026, 11, 25), "interesado"),  # posterior a hoy: no cuenta
    ]
    ventas = [venta(1, "c001", 10), venta(2, "c002", 20), venta(3, "c003", 1)]
    resultado = conversion(contactos, ventas, HOY)
    assert (resultado.contactos, resultado.compraron) == (4, 1)
    assert resultado.tasa == 0.25


def test_conversion_sin_contactos():
    resultado = conversion([], [], HOY)
    assert (resultado.contactos, resultado.compraron, resultado.tasa) == (0, 0, None)
