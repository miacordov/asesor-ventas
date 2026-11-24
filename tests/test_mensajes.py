from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from ventas.agenda import construir_agenda
from ventas.cargador import cargar_todo
from ventas.funcional import PerfilCliente
from ventas.logico import PuenteProlog
from ventas.mensajes import (
    Mensaje,
    dias_texto,
    dinero,
    enlace_whatsapp,
    enumerar,
    frase_oferta,
    mensajes_para_agenda,
    primer_nombre,
    redactar_mensaje,
    validar_telefono,
)
from ventas.modelos import ClienteFrecuente, ClienteRegular

DATOS = Path(__file__).resolve().parent / "datos"
HOY = date(2026, 10, 5)


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


@pytest.fixture
def motor():
    puente = PuenteProlog()
    puente.cargar_compras([])
    puente.cargar_perfiles([])
    puente.cargar_catalogo([])
    return puente


@pytest.fixture
def mensajes(datos, motor):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    return mensajes_para_agenda(agenda, datos.clientes, datos.productos, motor)


def texto_del_enlace(enlace):
    return parse_qs(urlparse(enlace).query)["text"][0]


# =====================================================================
# Funciones puras de formato
# =====================================================================
@pytest.mark.parametrize(
    ("items", "esperado"),
    [([], ""), (["a"], "a"), (["a", "b"], "a y b"), (["a", "b", "c"], "a, b y c"), (["a", "b", "c", "d"], "a, b, c y d")],
)
def test_enumerar(items, esperado):
    assert enumerar(items) == esperado


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [(675, "S/ 675.00"), (607.5, "S/ 607.50"), (1234.5, "S/ 1,234.50"), (0, "S/ 0.00"), (0.1 + 0.2, "S/ 0.30")],
)
def test_dinero(monto, esperado):
    assert dinero(monto) == esperado


@pytest.mark.parametrize(("dias", "esperado"), [(0, "0 días"), (1, "1 día"), (2, "2 días"), (40, "40 días")])
def test_dias_texto(dias, esperado):
    assert dias_texto(dias) == esperado


def test_primer_nombre():
    assert primer_nombre("María Torres") == "María"
    assert primer_nombre("Ana") == "Ana"
    assert primer_nombre("  Luis   Vega ") == "Luis"


# =====================================================================
# Teléfono y enlace
# =====================================================================
@pytest.mark.parametrize("tel", ["51900000001", "12125550123", "12345678", "123456789012345"])
def test_telefonos_validos(tel):
    assert validar_telefono(tel) == tel


@pytest.mark.parametrize(
    "tel", ["", "abc", "+51900000001", "051900000001", "1234567", "1234567890123456", "51 900 000 001", "5190000000a", None, 51900000001]
)
def test_telefonos_invalidos(tel):
    with pytest.raises(ValueError):
        validar_telefono(tel)


def test_enlace_tiene_el_formato_de_whatsapp():
    enlace = enlace_whatsapp("51900000001", "Hola Juan")
    assert enlace == "https://wa.me/51900000001?text=Hola%20Juan"


@pytest.mark.parametrize(
    "texto",
    [
        "Hola María, ¿cómo estás? ¡Te esperamos!",
        "Ana & Co: 50% de descuento #1",
        "Precio: S/ 1,234.50 (con 10 %)",
        "Línea uno\nLínea dos",
        "ñandú 🙂 café",
        "a=b&c=d?e/f+g",
    ],
)
def test_enlace_conserva_el_texto_exacto(texto):
    enlace = enlace_whatsapp("51900000001", texto)
    assert texto_del_enlace(enlace) == texto
    assert " " not in enlace and "\n" not in enlace and "&" not in enlace.split("?text=")[1]
    assert unquote(enlace.split("?text=")[1]) == texto


def test_enlace_rechaza_telefono_o_texto_invalidos():
    with pytest.raises(ValueError):
        enlace_whatsapp("abc", "Hola")
    with pytest.raises(ValueError):
        enlace_whatsapp("51900000001", "")
    with pytest.raises(ValueError):
        enlace_whatsapp("51900000001", "   ")


# =====================================================================
# Objeto Mensaje
# =====================================================================
def test_mensaje_valido_y_enlace():
    m = Mensaje("c001", "Juan Pérez", "51900000001", "reactivar", "Hola Juan")
    assert m.enlace == "https://wa.me/51900000001?text=Hola%20Juan"


def test_mensaje_sin_telefono_no_tiene_enlace():
    assert Mensaje("c001", "Juan", "", "reactivar", "Hola").enlace is None


@pytest.mark.parametrize(
    "campos",
    [
        ("Juan Perez", "Juan", "51900000001", "reactivar", "Hola"),  # id con espacio
        ("c001", "", "51900000001", "reactivar", "Hola"),  # nombre vacío
        ("c001", "Juan", "51900000001", "reactivar", ""),  # texto vacío
        ("c001", "Juan", "telefono", "reactivar", "Hola"),  # teléfono inválido
    ],
)
def test_mensaje_invalido(campos):
    with pytest.raises(ValueError):
        Mensaje(*campos)


def test_mensaje_es_inmutable():
    m = Mensaje("c001", "Juan", "51900000001", "reactivar", "Hola")
    with pytest.raises(FrozenInstanceError):
        m.texto = "otro"


# =====================================================================
# Redacción (funciones puras)
# =====================================================================
PERFIL = PerfilCliente("c001", 3, date(2026, 8, 26), 40, 2650.0, 883.33, ("perifericos",))


def test_redactar_sin_oferta():
    cliente = ClienteFrecuente("c001", "Juan Pérez")
    assert redactar_mensaje("reactivar", cliente, PERFIL, None) == (
        "Hola Juan, hace 40 días que no nos visitas y queremos saber cómo estás. ¡Te esperamos!"
    )
    assert redactar_mensaje("fidelizar", cliente, PERFIL, None) == (
        "Hola Juan, gracias por seguir eligiéndonos. ¡Gracias por tu confianza!"
    )


def test_redactar_solo_con_recomendaciones():
    cliente = ClienteRegular("c003", "Carlos Ruiz")
    texto = redactar_mensaje("cruzar", cliente, PERFIL, None, ["Webcam HD", "Hub USB-C"])
    assert "Creemos que te pueden interesar: Webcam HD y Hub USB-C." in texto
    assert "propuesta" not in texto


def test_redactar_un_dia_sin_comprar_va_en_singular():
    perfil = PerfilCliente("c001", 3, date(2026, 10, 4), 1, 10.0, 10.0, ())
    assert "hace 1 día que" in redactar_mensaje("reactivar", ClienteRegular("c001", "Juan"), perfil, None)


def test_redactar_tipo_desconocido():
    with pytest.raises(ValueError, match="plantilla"):
        redactar_mensaje("vender", ClienteRegular("c001", "Juan"), PERFIL, None)


def test_frase_oferta_sin_nada():
    assert frase_oferta(ClienteRegular("c001", "Juan"), None, []) == ""


# =====================================================================
# Mensajes de la agenda completa (calculados a mano sobre el dataset)
# =====================================================================
def test_un_mensaje_por_entrada_y_en_el_mismo_orden(datos, motor, mensajes):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    assert [m.id_cliente for m in mensajes] == [e.accion.id_cliente for e in agenda]
    assert [m.id_cliente for m in mensajes] == ["c001", "c007", "c004", "c002", "c008", "c003"]


def test_mensaje_de_juan_reactivar_con_descuento(mensajes):
    assert mensajes[0].texto == (
        "Hola Juan, hace 40 días que no nos visitas y queremos saber cómo estás. "
        "Te armamos esta propuesta: Monitor 24 pulgadas, Auriculares con micrófono y Hub USB-C "
        "por S/ 675.00 (S/ 607.50 con tu descuento del 10 %). ¡Te esperamos!"
    )


def test_mensaje_de_ana_sin_combinacion_menciona_sus_recomendaciones(mensajes):
    # Con S/ 126 solo le cabe el teclado: un producto solo no es combinación.
    # Compra cada ~16 días y lleva 25 sin venir: el mensaje es de reactivación.
    ana = next(m for m in mensajes if m.id_cliente == "c004")
    assert ana.texto == (
        "Hola Ana, hace 25 días que no nos visitas y queremos saber cómo estás. "
        "Creemos que te pueden interesar: Teclado mecánico, Laptop 14 pulgadas y Monitor 24 pulgadas. "
        "¡Te esperamos!"
    )


def test_cliente_regular_no_menciona_descuento(mensajes):
    carlos = next(m for m in mensajes if m.id_cliente == "c003")
    assert carlos.texto == (
        "Hola Carlos, por lo que has comprado con nosotros, creemos que podemos ayudarte. "
        "Creemos que te pueden interesar: Laptop 14 pulgadas, Monitor 24 pulgadas y Webcam HD. "
        "¡Cuéntanos si te interesa!"
    )
    assert "descuento" not in carlos.texto


def test_todos_los_clientes_frecuentes_mencionan_su_descuento(datos, mensajes):
    # Ana (c004) y Lucía (c008) son frecuentes pero no tienen combinación que proponer.
    frecuentes = {"c001", "c002", "c007"}
    for m in mensajes:
        assert ("descuento del 10 %" in m.texto) is (m.id_cliente in frecuentes)


def test_todos_los_mensajes_tienen_enlace_que_reproduce_el_texto(mensajes):
    for m in mensajes:
        assert m.enlace.startswith(f"https://wa.me/{m.telefono}?text=")
        assert texto_del_enlace(m.enlace) == m.texto


def test_los_mensajes_no_exponen_identificadores_internos(mensajes):
    for m in mensajes:
        for interno in ("p00", "p01", "c00", "reactivar", "fidelizar", "cruzar"):
            assert interno not in m.texto


def test_cada_mensaje_nombra_a_su_cliente_y_usa_su_propio_telefono(datos, mensajes):
    por_id = {c.id_cliente: c for c in datos.clientes}
    for m in mensajes:
        cliente = por_id[m.id_cliente]
        assert m.texto.startswith(f"Hola {cliente.nombre.split()[0]},")
        assert m.telefono == cliente.telefono


def test_agenda_vacia_no_genera_mensajes(datos, motor):
    assert mensajes_para_agenda((), datos.clientes, datos.productos, motor) == ()


def test_cliente_sin_telefono_igual_recibe_mensaje_sin_enlace(datos, motor):
    sin_telefono = tuple(ClienteRegular(c.id_cliente, c.nombre, "") for c in datos.clientes)
    agenda = construir_agenda(sin_telefono, datos.ventas, datos.productos, HOY, motor)
    resultado = mensajes_para_agenda(agenda, sin_telefono, datos.productos, motor)
    assert len(resultado) == 6
    assert all(m.enlace is None and m.texto for m in resultado)


def test_los_mensajes_son_deterministas(datos, motor):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    a = mensajes_para_agenda(agenda, datos.clientes, datos.productos, motor)
    b = mensajes_para_agenda(agenda, datos.clientes, datos.productos, motor)
    assert a == b


def test_acepta_generadores(datos, motor):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    resultado = mensajes_para_agenda(iter(agenda), iter(datos.clientes), iter(datos.productos), motor)
    assert len(resultado) == 6


def test_el_mensaje_cambia_si_cambia_la_fecha(datos, motor):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, date(2026, 10, 20), motor)
    resultado = mensajes_para_agenda(agenda, datos.clientes, datos.productos, motor)
    ana = next(m for m in resultado if m.id_cliente == "c004")
    assert ana.tipo_accion == "reactivar" and "hace 40 días" in ana.texto
