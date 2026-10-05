from collections import defaultdict
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from pathlib import Path

import pytest

from ventas.agenda import (
    Accion,
    Cruzar,
    Fidelizar,
    Reactivar,
    _mejor_por_cliente,
    construir_agenda,
    crear_accion,
)
from ventas.cargador import cargar_todo
from ventas.funcional import perfil_cliente, perfiles
from ventas.logico import MotorLogico, PuenteProlog
from ventas.modelos import Venta

DATOS = Path(__file__).resolve().parent.parent / "datos"
HOY = date(2026, 10, 5)


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


@pytest.fixture
def motor():
    # SWI-Prolog es un único motor por proceso: se limpia en cada prueba.
    puente = PuenteProlog()
    puente.cargar_compras([])
    puente.cargar_perfiles([])
    return puente


def cargar(motor, datos, hoy=HOY, **umbrales):
    motor.cargar_compras(datos.ventas)
    motor.cargar_perfiles(perfiles(datos.clientes, datos.ventas, datos.productos, hoy), **umbrales)
    return motor


def compras_sinteticas(cliente, ultimo_dia, n=3, producto="p001"):
    """n compras en días distintos (cada 10 días), la última en `ultimo_dia`."""
    return [
        Venta(f"v{cliente}{i}", cliente, producto, 1, 10.0, ultimo_dia - timedelta(days=10 * i))
        for i in range(n)
    ]


def tipo_de(motor, cliente):
    return {c: t for c, t, _ in motor.acciones()}.get(cliente)


def oraculo_acciones(ps, ventas, umbral, dias):
    """Verdad independiente: las mismas reglas en Python puro."""
    compras = defaultdict(set)
    for v in ventas:
        compras[v.id_cliente].add(v.id_producto)

    def tiene_recomendacion(c):
        propios = compras[c]
        similares = {o for o, otros in compras.items() if o != c and otros & propios}
        return any(compras[o] - propios for o in similares)

    resultado = {}
    for p in ps:
        if p.n_compras >= umbral:
            resultado[p.id_cliente] = "reactivar" if p.dias_sin_comprar > dias else "fidelizar"
        elif p.n_compras >= 1 and tiene_recomendacion(p.id_cliente):
            resultado[p.id_cliente] = "cruzar"
    return resultado


# =====================================================================
# Reglas Prolog de la agenda
# =====================================================================
def test_acciones_del_dataset_calculadas_a_mano(motor, datos):
    cargar(motor, datos)
    assert {(c, t) for c, t, _ in motor.acciones()} == {
        ("c001", "reactivar"),
        ("c007", "reactivar"),
        ("c002", "fidelizar"),
        ("c004", "fidelizar"),
        ("c008", "fidelizar"),
        ("c003", "cruzar"),
        ("c005", "cruzar"),
    }


def test_motivos_exactos(motor, datos):
    cargar(motor, datos)
    motivos = {c: m for c, _, m in motor.acciones()}
    assert motivos["c001"] == ("frecuente", "inactivo")
    assert motivos["c002"] == ("frecuente", "reciente")
    assert motivos["c003"] == ("no_frecuente", "similares")


def test_cliente_sin_compras_no_tiene_acciones(motor, datos):
    cargar(motor, datos)
    assert tipo_de(motor, "c006") is None


def test_sin_perfiles_cargados_no_hay_acciones(motor, datos):
    motor.cargar_compras(datos.ventas)
    assert motor.acciones() == ()


@pytest.mark.parametrize(
    ("umbral", "dias"), [(3, 30), (5, 30), (3, 45), (3, 10), (1, 30), (10, 30), (3, 200)]
)
def test_acciones_coinciden_con_el_oraculo(motor, datos, umbral, dias):
    cargar(motor, datos, umbral_frecuente=umbral, dias_inactividad=dias)
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    esperado = oraculo_acciones(ps, datos.ventas, umbral, dias)
    assert {c: t for c, t, _ in motor.acciones()} == esperado


# ---------- los límites exactos ----------
@pytest.mark.parametrize(("dias_sin_comprar", "esperado"), [(29, "fidelizar"), (30, "fidelizar"),
                                                              (31, "reactivar")])
def test_limite_de_inactividad(motor, datos, dias_sin_comprar, esperado):
    ventas = compras_sinteticas("c001", HOY - timedelta(days=dias_sin_comprar), n=3)
    motor.cargar_compras(ventas)
    motor.cargar_perfiles([perfil_cliente("c001", ventas, datos.productos, HOY)])
    assert tipo_de(motor, "c001") == esperado


@pytest.mark.parametrize(("compras", "es_frecuente"), [(2, False), (3, True), (4, True)])
def test_limite_de_cliente_frecuente(motor, datos, compras, es_frecuente):
    ventas = compras_sinteticas("c001", HOY - timedelta(days=5), n=compras)
    motor.cargar_compras(ventas)
    motor.cargar_perfiles([perfil_cliente("c001", ventas, datos.productos, HOY)])
    assert (tipo_de(motor, "c001") == "fidelizar") is es_frecuente


# ---------- carga de perfiles ----------
@pytest.mark.parametrize("malo", [-1, 3.5, "30", None, True])
def test_umbrales_invalidos(motor, malo):
    with pytest.raises(ValueError):
        motor.cargar_perfiles([], umbral_frecuente=malo)
    with pytest.raises(ValueError):
        motor.cargar_perfiles([], dias_inactividad=malo)


def test_cargar_perfiles_reemplaza_los_anteriores(motor, datos):
    cargar(motor, datos, hoy=HOY)
    assert tipo_de(motor, "c004") == "fidelizar"  # 25 días
    cargar(motor, datos, hoy=date(2026, 10, 20))
    assert tipo_de(motor, "c004") == "reactivar"  # 40 días


# =====================================================================
# Jerarquía de acciones (POO)
# =====================================================================
def test_accion_es_abstracta():
    with pytest.raises(TypeError):
        Accion("c001", ("frecuente",))


def test_polimorfismo_de_las_acciones():
    acciones = [Reactivar("c001", ("a",)), Fidelizar("c001", ("a",)), Cruzar("c001", ("a",))]
    assert [a.prioridad for a in acciones] == ["alta", "media", "baja"]
    assert [a.peso for a in acciones] == [3, 2, 1]
    assert len({a.titulo() for a in acciones}) == 3


def test_crear_accion_devuelve_la_clase_correcta():
    assert isinstance(crear_accion("reactivar", "c001", ["frecuente"]), Reactivar)
    assert isinstance(crear_accion("fidelizar", "c001", ["frecuente"]), Fidelizar)
    assert isinstance(crear_accion("cruzar", "c001", ["similares"]), Cruzar)


def test_crear_accion_tipo_desconocido():
    with pytest.raises(ValueError, match="desconocido"):
        crear_accion("vender", "c001", ["frecuente"])


def test_accion_sin_motivos():
    with pytest.raises(ValueError):
        Reactivar("c001", ())


def test_accion_con_id_invalido():
    with pytest.raises(ValueError):
        Reactivar("Juan Perez", ("frecuente",))


def test_accion_es_inmutable():
    with pytest.raises(FrozenInstanceError):
        Reactivar("c001", ("frecuente",)).id_cliente = "c002"


def test_explicar_con_motivo_desconocido(datos):
    perfil = perfil_cliente("c001", datos.ventas, datos.productos, HOY)
    with pytest.raises(ValueError, match="Motivo desconocido"):
        Reactivar("c001", ("inventado",)).explicar(perfil)


def test_explicar_redacta_la_frase(datos):
    p1 = perfil_cliente("c001", datos.ventas, datos.productos, HOY)
    p2 = perfil_cliente("c002", datos.ventas, datos.productos, HOY)
    assert Reactivar("c001", ("frecuente", "inactivo")).explicar(p1) == (
        "Compró 3 veces, lleva 40 días sin comprar"
    )
    assert Fidelizar("c002", ("frecuente", "reciente")).explicar(p2) == (
        "Compró 5 veces, su última compra fue hace 4 días"
    )


def test_mejor_por_cliente_se_queda_con_la_mas_urgente():
    acciones = [Cruzar("c001", ("a",)), Reactivar("c001", ("a",)), Fidelizar("c001", ("a",)),
                Cruzar("c002", ("a",))]
    elegidas = {a.id_cliente: type(a) for a in _mejor_por_cliente(acciones)}
    assert elegidas == {"c001": Reactivar, "c002": Cruzar}


# =====================================================================
# La agenda completa (los tres paradigmas juntos)
# =====================================================================
def test_agenda_ordenada_calculada_a_mano(motor, datos):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    # Primero la acción más urgente; a igual urgencia, el que más gastó:
    # reactivar: c001 (2650), c007 (1195) | fidelizar: c002 (3235), c004 (455),
    # c008 (310) | cruzar: c003 (320), c005 (290)
    assert [e.accion.id_cliente for e in agenda] == [
        "c001", "c007", "c002", "c004", "c008", "c003", "c005",
    ]
    assert [e.accion.tipo for e in agenda] == [
        "reactivar", "reactivar", "fidelizar", "fidelizar", "fidelizar", "cruzar", "cruzar",
    ]


def test_agenda_no_incluye_clientes_sin_compras(motor, datos):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    assert "c006" not in {e.accion.id_cliente for e in agenda}


def test_agenda_una_entrada_por_cliente(motor, datos):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    ids = [e.accion.id_cliente for e in agenda]
    assert len(ids) == len(set(ids))


def test_cada_entrada_trae_motivo_perfil_y_recomendaciones(motor, datos):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    juan = agenda[0]
    assert juan.motivo == "Compró 3 veces, lleva 40 días sin comprar"
    assert juan.perfil.ticket_promedio == 883.33
    assert [r.id_producto for r in juan.recomendaciones] == ["p009", "p005", "p004"]


@pytest.mark.parametrize(("maximo", "cantidad"), [(1, 1), (2, 2), (0, 0), (-1, 0)])
def test_agenda_limita_las_recomendaciones(motor, datos, maximo, cantidad):
    agenda = construir_agenda(
        datos.clientes, datos.ventas, datos.productos, HOY, motor, max_recomendaciones=maximo
    )
    assert len(agenda[0].recomendaciones) == cantidad


def test_agenda_es_determinista(motor, datos):
    a = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    b = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    assert a == b


def test_agenda_cambia_con_la_fecha_de_referencia(motor, datos):
    agenda = construir_agenda(
        datos.clientes, datos.ventas, datos.productos, date(2026, 10, 20), motor
    )
    # c004 (última compra el 10-sep) pasa a inactivo; c002 y c008 siguen activos.
    assert [e.accion.id_cliente for e in agenda] == [
        "c001", "c007", "c004", "c002", "c008", "c003", "c005",
    ]
    assert {e.accion.id_cliente: e.accion.tipo for e in agenda}["c004"] == "reactivar"


def test_agenda_sin_clientes(motor, datos):
    assert construir_agenda((), datos.ventas, datos.productos, HOY, motor) == ()


def test_agenda_sin_ventas(motor, datos):
    assert construir_agenda(datos.clientes, (), datos.productos, HOY, motor) == ()


def test_agenda_con_fecha_anterior_a_las_ventas(motor, datos):
    with pytest.raises(ValueError, match="anterior"):
        construir_agenda(datos.clientes, datos.ventas, datos.productos, date(2026, 5, 1), motor)


def test_agenda_acepta_generadores(motor, datos):
    agenda = construir_agenda(
        iter(datos.clientes), iter(datos.ventas), iter(datos.productos), HOY, motor
    )
    assert len(agenda) == 7


def test_entrada_de_agenda_es_inmutable(motor, datos):
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, motor)
    with pytest.raises(FrozenInstanceError):
        agenda[0].motivo = "otro"


def test_agenda_depende_de_la_abstraccion_no_de_prolog(datos):
    """Cualquier MotorLogico sirve: aquí uno falso que siempre dice 'fidelizar'."""

    class MotorFalso(MotorLogico):
        def cargar_compras(self, ventas):
            pass

        def cargar_perfiles(self, perfiles, umbral_frecuente=3, dias_inactividad=30):
            pass

        def recomendar(self, id_cliente):
            return ()

        def respaldo(self, id_cliente, id_producto):
            return ()

        def acciones(self):
            return (("c002", "fidelizar", ("frecuente", "reciente")),)

    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, HOY, MotorFalso())
    assert [e.accion.id_cliente for e in agenda] == ["c002"]
    assert agenda[0].motivo == "Compró 5 veces, su última compra fue hace 4 días"
