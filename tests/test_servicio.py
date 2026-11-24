from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from ventas.cargador import cargar_todo
from ventas.logico import PuenteProlog
from ventas.modelos import ClienteFrecuente, ClienteRegular
from ventas.ofertas import Oferta
from ventas.propuestas import LineaPropuesta, Propuesta
from ventas.servicio import clientes_con_perfil, construir_tarjetas, resumen_ventas

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
def tarjetas(datos, motor):
    return construir_tarjetas(datos, HOY, motor)


# =====================================================================
# Tarjetas de la agenda
# =====================================================================
def test_orden_de_las_tarjetas(tarjetas):
    assert [t.cliente.id_cliente for t in tarjetas] == ["c001", "c007", "c004", "c002", "c008", "c003"]


def test_clientes_clasificados(tarjetas):
    tipos = {t.cliente.id_cliente: type(t.cliente) for t in tarjetas}
    assert tipos["c001"] is ClienteFrecuente
    assert tipos["c003"] is ClienteRegular
    assert "c005" not in tipos  # Luis no tiene clientes similares: no hay nada que ofrecerle


def test_clientes_similares_calculados_a_mano(tarjetas):
    # Similares: 2 o más productos en común. Juan: c002, c003, c004, c007 (c008 solo
    # comparte p002). Pedro: c001, c002, c003, c004, c008 (Luis solo comparte p009).
    similares = {t.cliente.id_cliente: t.clientes_similares for t in tarjetas}
    assert similares["c001"] == 4
    assert similares["c007"] == 5


def test_confianza_es_soporte_sobre_similares(tarjetas):
    for t in tarjetas:
        for r in t.recomendaciones:
            assert r.soporte / t.clientes_similares == pytest.approx(r.confianza)


def test_recomendaciones_completas_de_juan(tarjetas):
    juan = tarjetas[0]
    assert [r.id_producto for r in juan.recomendaciones] == ["p009", "p005", "p004", "p006", "p010"]


def test_pedidos_de_juan(tarjetas):
    (pedido,) = tarjetas[0].pedidos
    assert pedido.pedido.ids == ("p004", "p005", "p009")
    assert pedido.pedido.subtotal == 675.0
    assert pedido.total_con_descuento == 607.5


def test_pedido_de_maria_en_su_tarjeta(tarjetas):
    maria = next(t for t in tarjetas if t.cliente.id_cliente == "c002")
    assert [p.pedido.ids for p in maria.pedidos] == [("p006", "p007", "p010")]


def test_limite_de_pedidos(datos, motor):
    uno = construir_tarjetas(datos, HOY, motor, max_pedidos=1)
    assert len(uno[0].pedidos) == 1
    assert all(len(t.pedidos) <= 1 for t in uno)
    assert all(t.pedidos == () for t in construir_tarjetas(datos, HOY, motor, max_pedidos=0))


def test_el_mensaje_coincide_con_el_primer_pedido(tarjetas):
    for t in (t for t in tarjetas if t.pedidos):
        assert t.mensaje.id_cliente == t.cliente.id_cliente
        for producto in t.pedidos[0].pedido.productos:
            assert producto.nombre in t.mensaje.texto


def test_los_clientes_sin_combinacion_no_tienen_pedido_pero_si_enlace(tarjetas):
    sin_pedido = {t.cliente.id_cliente for t in tarjetas if not t.pedidos}
    assert sin_pedido == {"c003", "c004", "c008"}
    assert all(len(p.pedido.productos) >= 2 for t in tarjetas for p in t.pedidos)
    assert all(t.mensaje.enlace for t in tarjetas)


def test_sin_ventas_no_hay_tarjetas(datos, motor):
    sin_ventas = type(datos)(datos.clientes, datos.productos, ())
    assert construir_tarjetas(sin_ventas, HOY, motor) == ()


def test_fecha_anterior_a_las_ventas(datos, motor):
    with pytest.raises(ValueError, match="anterior"):
        construir_tarjetas(datos, date(2026, 5, 1), motor)


def test_tarjetas_son_deterministas(datos, motor):
    assert construir_tarjetas(datos, HOY, motor) == construir_tarjetas(datos, HOY, motor)


def test_la_fecha_cambia_la_agenda(datos, motor):
    tarjetas = construir_tarjetas(datos, date(2026, 10, 20), motor)
    tipos = {t.cliente.id_cliente: t.entrada.accion.tipo for t in tarjetas}
    assert tipos["c004"] == "reactivar"


def test_tarjeta_inmutable(tarjetas):
    with pytest.raises(FrozenInstanceError):
        tarjetas[0].mensaje = None


# =====================================================================
# Clientes con perfil
# =====================================================================
def test_clientes_con_perfil(datos):
    pares = clientes_con_perfil(datos, HOY)
    assert len(pares) == 8
    assert [c.id_cliente for c, _ in pares] == [c.id_cliente for c in datos.clientes]
    assert all(c.id_cliente == p.id_cliente for c, p in pares)
    tipos = {c.id_cliente: type(c) for c, _ in pares}
    assert tipos["c006"] is ClienteRegular and tipos["c002"] is ClienteFrecuente


def test_perfil_de_juan_en_la_tabla(datos):
    cliente, perfil = clientes_con_perfil(datos, HOY)[0]
    assert (perfil.n_compras, perfil.dias_sin_comprar, perfil.ticket_promedio) == (3, 40, 883.33)


# =====================================================================
# Resumen de ventas
# =====================================================================
def test_resumen_calculado_a_mano(datos):
    r = resumen_ventas(datos)
    assert r.total == 8455.0
    assert r.promedio_por_linea == 281.83
    assert (r.n_ventas, r.n_clientes) == (30, 8)


def test_resumen_por_mes_y_categoria(datos):
    r = resumen_ventas(datos)
    assert r.por_mes[0] == ("2026-06", 810.0)
    assert r.por_mes[-1] == ("2026-10", 260.0)
    assert dict(r.por_categoria)["computo"] == 4750.0
    assert sum(m for _, m in r.por_mes) == pytest.approx(r.total)
    assert sum(m for _, m in r.por_categoria) == pytest.approx(r.total)


def test_resumen_top_productos_con_nombres(datos):
    r = resumen_ventas(datos)
    assert r.top_productos[:2] == (("Mouse inalámbrico", 7), ("Hub USB-C", 7))
    assert len(r.top_productos) == 5


def test_resumen_sin_ventas(datos):
    vacio = type(datos)(datos.clientes, datos.productos, ())
    r = resumen_ventas(vacio)
    assert (r.total, r.promedio_por_linea, r.n_ventas) == (0.0, 0.0, 0)
    assert r.por_mes == () and r.por_categoria == () and r.top_productos == ()


# =====================================================================
# Efecto de un cambio sobre la agenda
# =====================================================================
def test_acciones_por_cliente(datos, motor):
    from ventas.servicio import acciones_por_cliente

    assert acciones_por_cliente(datos, HOY, motor) == {
        "c001": "reactivar",
        "c007": "reactivar",
        "c004": "reactivar",
        "c002": "fidelizar",
        "c008": "fidelizar",
        "c003": "cruzar",
    }


def test_acciones_por_cliente_cambia_al_agregar_una_venta(datos, motor):
    from ventas.modelos import Venta
    from ventas.servicio import acciones_por_cliente

    nueva = Venta("v031", "c001", "p002", 1, 45.0, HOY)
    con_venta = type(datos)(datos.clientes, datos.productos, (*datos.ventas, nueva))
    assert acciones_por_cliente(datos, HOY, motor)["c001"] == "reactivar"
    assert acciones_por_cliente(con_venta, HOY, motor)["c001"] == "fidelizar"


@pytest.mark.parametrize(
    ("antes", "despues", "esperado"),
    [
        ("reactivar", "fidelizar", "Juan Pérez pasó de «Reactivar» a «Fidelizar» en la agenda."),
        ("cruzar", "fidelizar", "Juan Pérez pasó de «Complementar» a «Fidelizar» en la agenda."),
        (None, "cruzar", "Juan Pérez ahora aparece en la agenda como «Complementar»."),
        ("fidelizar", None, "Juan Pérez ya no aparece en la agenda."),
        ("fidelizar", "fidelizar", "Juan Pérez sigue en la agenda como «Fidelizar»."),
        (None, None, "Juan Pérez sigue sin aparecer en la agenda."),
    ],
)
def test_describir_cambio_agenda(antes, despues, esperado):
    from ventas.servicio import describir_cambio_agenda

    assert describir_cambio_agenda("Juan Pérez", antes, despues) == esperado


# =====================================================================
# Ofertas en la agenda
# =====================================================================
AURICULARES_OCTUBRE = {"p005": Oferta("p005", 20, date(2026, 10, 1), date(2026, 10, 31))}  # 95 -> 76


def test_las_tarjetas_traen_las_ofertas_de_cada_cliente(datos, motor):
    tarjetas = construir_tarjetas(datos, HOY, motor, vigentes=AURICULARES_OCTUBRE)
    compraron = {v.id_cliente for v in datos.ventas if v.id_producto == "p005"}
    for t in tarjetas:
        ids = [o.id_producto for o in t.ofertas]
        if isinstance(t.cliente, ClienteFrecuente) and t.cliente.id_cliente not in compraron:
            assert ids == ["p005"] and "cliente_frecuente" in t.ofertas[0].motivos
        if t.cliente.id_cliente in compraron:
            assert ids == []


def test_el_pedido_y_el_mensaje_priorizan_la_oferta(datos, motor):
    tarjetas = construir_tarjetas(datos, HOY, motor, vigentes=AURICULARES_OCTUBRE)
    con_oferta = [t for t in tarjetas if t.pedidos and t.pedidos[0].ofertas_incluidas]
    assert con_oferta
    for t in con_oferta:
        auriculares = next(p for p in t.pedidos[0].pedido.productos if p.id_producto == "p005")
        assert auriculares.precio == 76.0
        assert "Auriculares con micrófono con 20 % de descuento hasta el 31/10/2026" in t.mensaje.texto


def test_sin_ofertas_la_agenda_no_cambia(datos, motor, tarjetas):
    assert construir_tarjetas(datos, HOY, motor, vigentes={}) == tarjetas


def test_la_propuesta_guardada_reemplaza_el_mensaje_automatico(datos, motor, tarjetas):
    guardada = Propuesta(
        "c001", (LineaPropuesta("p005", 95.0, 76.0), LineaPropuesta("p009", 60.0, 60.0)), 5, HOY
    )
    nuevas = construir_tarjetas(datos, HOY, motor, propuestas=[guardada])
    juan = next(t for t in nuevas if t.cliente.id_cliente == "c001")
    assert juan.propuesta == guardada
    assert juan.mensaje.texto == (
        "Hola Juan, te preparamos una propuesta especial: Auriculares con micrófono (en oferta) y Hub USB-C "
        "por S/ 136.00, y con tu 5 % de descuento te queda en S/ 129.20. ¡Escríbenos si te interesa!"
    )
    # Los demás clientes no cambian.
    assert [t for t in nuevas if t.cliente.id_cliente != "c001"] == [t for t in tarjetas if t.cliente.id_cliente != "c001"]


def test_cada_cliente_se_calcula_una_sola_vez(datos, motor, monkeypatch):
    llamadas = {"recomendar": 0, "armar_pedidos": 0}
    for nombre in llamadas:
        original = getattr(motor, nombre)

        def contar(*args, _original=original, _nombre=nombre, **kwargs):
            llamadas[_nombre] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(motor, nombre, contar)
    sin_duplicar = construir_tarjetas(datos, HOY, motor)
    recomendar_por_tarjeta, pedidos_por_tarjeta = dict(llamadas).values()
    # Lo mismo que antes, pero la tarjeta y el mensaje comparten las cuentas.
    assert recomendar_por_tarjeta == len(sin_duplicar)
    llamadas.update(recomendar=0, armar_pedidos=0)
    construir_tarjetas(datos, HOY, motor, max_pedidos=1)
    assert llamadas["armar_pedidos"] == pedidos_por_tarjeta  # el mensaje no vuelve a armar pedidos


def test_la_tarjeta_trae_los_complementos_de_lo_que_compro(tarjetas):
    # Juan compró cómputo, periféricos y accesorios: le faltan almacenamiento,
    # audio, mobiliario y monitores (el catálogo de prueba no tiene RAM).
    juan = tarjetas[0]
    assert [p.id_producto for p in juan.complementos] == ["p008", "p005", "p010", "p004"]
