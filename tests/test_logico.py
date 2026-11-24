from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from ventas.cargador import cargar_todo
from ventas.logico import MotorLogico, PuenteProlog, pares_compra
from ventas.modelos import Venta

DATOS = Path(__file__).resolve().parent / "datos"
CLIENTES = ["c001", "c002", "c003", "c004", "c005", "c006", "c007", "c008"]


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


@pytest.fixture
def motor(datos):
    # SWI-Prolog es un único motor por proceso: se recarga en cada prueba.
    puente = PuenteProlog()
    puente.cargar_compras(datos.ventas)
    return puente


def venta(id_venta, cliente, producto):
    return Venta(id_venta, cliente, producto, 1, 10.0, date(2026, 9, 1))


def oraculo(ventas, cliente):
    """Verdad independiente: lo mismo, calculado en Python puro con conjuntos."""
    compras = defaultdict(set)
    for v in ventas:
        compras[v.id_cliente].add(v.id_producto)
    propios = compras[cliente]
    similares = {o for o, ps in compras.items() if o != cliente and ps & propios}
    if not similares:
        return {}
    candidatos = defaultdict(set)
    for otro in similares:
        for producto in compras[otro] - propios:
            candidatos[producto].add(otro)
    return {p: (len(s), len(s) / len(similares)) for p, s in candidatos.items()}


# ---------- contrato y función pura ----------
def test_motor_logico_es_abstracto():
    with pytest.raises(TypeError):
        MotorLogico()


def test_puente_cumple_el_contrato(motor):
    assert isinstance(motor, MotorLogico)


def test_pares_compra_sin_repetidos_y_ordenados():
    ventas = [venta("v1", "c002", "p002"), venta("v2", "c001", "p001"), venta("v3", "c001", "p001")]
    assert pares_compra(ventas) == (("c001", "p001"), ("c002", "p002"))


def test_pares_compra_vacio():
    assert pares_compra([]) == ()


# ---------- resultados calculados a mano para c001 ----------
def test_recomendaciones_de_c001_calculadas_a_mano(motor):
    # c001 compró p001, p002, p003, p007. Sus similares son c002, c003, c004,
    # c007 y c008 (c005 no comparte ningún producto con él): 5 clientes.
    esperado = [
        ("p009", 5, 1.0),
        ("p005", 4, 0.8),
        ("p004", 2, 0.4),
        ("p006", 2, 0.4),
        ("p010", 1, 0.2),
    ]
    obtenido = [(r.id_producto, r.soporte, r.confianza) for r in motor.recomendar("c001")]
    assert [(p, s) for p, s, _ in obtenido] == [(p, s) for p, s, _ in esperado]
    assert [c for _, _, c in obtenido] == pytest.approx([c for _, _, c in esperado])


def test_respaldo_explica_el_por_que(motor):
    assert motor.respaldo("c001", "p004") == ("c002", "c007")
    assert motor.respaldo("c001", "p010") == ("c007",)


# ---------- todos los clientes contra el oráculo ----------
@pytest.mark.parametrize("cliente", CLIENTES)
def test_coincide_con_el_oraculo(motor, datos, cliente):
    esperado = oraculo(datos.ventas, cliente)
    obtenido = {r.id_producto: (r.soporte, r.confianza) for r in motor.recomendar(cliente)}
    assert obtenido.keys() == esperado.keys()
    for producto, (soporte, confianza) in esperado.items():
        assert obtenido[producto][0] == soporte
        assert obtenido[producto][1] == pytest.approx(confianza)


@pytest.mark.parametrize("cliente", CLIENTES)
def test_nunca_recomienda_lo_que_ya_compro(motor, datos, cliente):
    propios = {v.id_producto for v in datos.ventas if v.id_cliente == cliente}
    recomendados = {r.id_producto for r in motor.recomendar(cliente)}
    assert not recomendados & propios


@pytest.mark.parametrize("cliente", CLIENTES)
def test_resultado_ordenado_y_confianza_valida(motor, cliente):
    recs = motor.recomendar(cliente)
    claves = [(-r.confianza, r.id_producto) for r in recs]
    assert claves == sorted(claves)
    assert all(0 < r.confianza <= 1 for r in recs)


# ---------- casos de borde ----------
def test_cliente_sin_compras(motor):
    assert motor.recomendar("c006") == ()


def test_cliente_inexistente_con_id_valido(motor):
    assert motor.recomendar("c999") == ()


def test_cliente_sin_clientes_similares():
    puente = PuenteProlog()
    puente.cargar_compras([venta("v1", "c001", "p001"), venta("v2", "c002", "p002")])
    assert puente.recomendar("c001") == ()


def test_cliente_que_ya_tiene_todo_lo_de_sus_similares():
    puente = PuenteProlog()
    puente.cargar_compras(
        [venta("v1", "c001", "p001"), venta("v2", "c001", "p002"), venta("v3", "c002", "p001")]
    )
    assert puente.recomendar("c001") == ()


def test_respaldo_de_producto_que_ya_tiene(motor):
    assert motor.respaldo("c001", "p001") == ()


def test_respaldo_de_producto_inexistente(motor):
    assert motor.respaldo("c001", "p999") == ()


def test_sin_ventas_no_hay_recomendaciones():
    puente = PuenteProlog()
    puente.cargar_compras([])
    assert puente.recomendar("c001") == ()


# ---------- carga de hechos ----------
def test_cargar_compras_reemplaza_los_hechos_anteriores(motor):
    motor.cargar_compras([venta("v1", "c001", "p001"), venta("v2", "c002", "p001"),
                          venta("v3", "c002", "p002")])
    recs = motor.recomendar("c001")
    assert [(r.id_producto, r.soporte) for r in recs] == [("p002", 1)]


def test_cargar_dos_veces_no_duplica(motor, datos):
    antes = motor.recomendar("c001")
    motor.cargar_compras(datos.ventas)
    assert motor.recomendar("c001") == antes


def test_ventas_repetidas_del_mismo_producto_no_inflan_el_soporte():
    puente = PuenteProlog()
    puente.cargar_compras([
        venta("v1", "c001", "p001"),
        venta("v2", "c002", "p001"),
        venta("v3", "c002", "p002"),
        venta("v4", "c002", "p002"),
    ])
    (rec,) = puente.recomendar("c001")
    assert rec.soporte == 1 and rec.confianza == 1.0


# ---------- seguridad: no se acepta código Prolog en los identificadores ----------
@pytest.mark.parametrize("malo", ["c001); halt(", "C001", "c 001", "", "c001, X"])
def test_recomendar_rechaza_ids_peligrosos(motor, malo):
    with pytest.raises(ValueError):
        motor.recomendar(malo)


def test_respaldo_rechaza_ids_peligrosos(motor):
    with pytest.raises(ValueError):
        motor.respaldo("c001", "p001); halt(")
