from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ventas.cargador import cargar_todo
from ventas.funcional import (
    UMBRAL_FRECUENTE,
    PerfilCliente,
    clasificar_cliente,
    clasificar_clientes,
    componer,
    de_categoria,
    de_cliente,
    entre_fechas,
    filtrar,
    monto_entre,
    perfil_cliente,
    perfiles,
    precio_con_descuento,
    promedio_ventas,
    ranking_productos,
    todos,
    total_del_cliente,
    total_ventas,
    ventas_por_categoria,
    ventas_por_mes,
)
from ventas.modelos import ClienteFrecuente, ClienteRegular, Venta

DATOS = Path(__file__).resolve().parent / "datos"
HOY = date(2026, 10, 5)


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


def venta(id_venta="v001", cliente="c001", producto="p001", cantidad=1, precio=10.0, dia=1):
    return Venta(id_venta, cliente, producto, cantidad, precio, date(2026, 9, dia))


@pytest.fixture
def df(datos):
    """Segunda verdad independiente: las mismas ventas en un DataFrame."""
    return pd.DataFrame(
        {
            "cliente": [v.id_cliente for v in datos.ventas],
            "producto": [v.id_producto for v in datos.ventas],
            "cantidad": [v.cantidad for v in datos.ventas],
            "monto": [v.monto for v in datos.ventas],
            "mes": [v.fecha.strftime("%Y-%m") for v in datos.ventas],
        }
    )


# ---------- métricas ----------
def test_total_y_promedio_calculados_a_mano(datos):
    assert total_ventas(datos.ventas) == 8455.0
    assert promedio_ventas(datos.ventas) == 281.83  # 8455 / 30


def test_metricas_con_lista_vacia():
    assert total_ventas([]) == 0.0
    assert promedio_ventas([]) == 0.0


def test_metricas_aceptan_cualquier_iterable(datos):
    assert total_ventas(iter(datos.ventas)) == 8455.0


def test_total_coincide_con_pandas(datos, df):
    assert total_ventas(datos.ventas) == pytest.approx(df["monto"].sum())


def test_por_categoria_calculado_a_mano(datos):
    resultado = dict(ventas_por_categoria(datos.ventas, datos.productos))
    assert resultado["computo"] == 4750.0  # laptops a 2400 y a 2350
    assert resultado["almacenamiento"] == 230.0
    assert sum(resultado.values()) == pytest.approx(8455.0)


def test_por_categoria_esta_ordenada_de_mayor_a_menor(datos):
    montos = [m for _, m in ventas_por_categoria(datos.ventas, datos.productos)]
    assert montos == sorted(montos, reverse=True)


def test_por_mes_calculado_a_mano(datos):
    esperado = (
        ("2026-06", 810.0),
        ("2026-07", 3065.0),
        ("2026-08", 3425.0),
        ("2026-09", 895.0),
        ("2026-10", 260.0),
    )
    assert ventas_por_mes(datos.ventas) == esperado


def test_por_mes_coincide_con_pandas(datos, df):
    esperado = df.groupby("mes")["monto"].sum()
    obtenido = dict(ventas_por_mes(datos.ventas))
    assert obtenido.keys() == set(esperado.index)
    for mes, monto in obtenido.items():
        assert monto == pytest.approx(esperado[mes])


def test_ranking_coincide_con_pandas_y_desempata_por_id(datos, df):
    esperado = df.groupby("producto")["cantidad"].sum()
    for producto, unidades in ranking_productos(datos.ventas, n=100):
        assert unidades == esperado[producto]
    assert ranking_productos(datos.ventas, n=3) == (("p002", 7), ("p009", 7), ("p003", 4))


@pytest.mark.parametrize("n", [0, -1])
def test_ranking_con_n_no_positivo(datos, n):
    assert ranking_productos(datos.ventas, n=n) == ()


# ---------- filtros y predicados ----------
def test_filtrar_por_cliente(datos):
    juan = filtrar(datos.ventas, de_cliente("c001"))
    assert len(juan) == 4
    assert total_ventas(juan) == 2650.0


def test_filtrar_por_monto(datos):
    caras = filtrar(datos.ventas, monto_entre(minimo=1000))
    assert {v.id_venta for v in caras} == {"v001", "v004"}


def test_filtrar_por_fechas_incluye_los_extremos(datos):
    septiembre = filtrar(datos.ventas, entre_fechas(date(2026, 9, 1), date(2026, 9, 30)))
    assert all(date(2026, 9, 1) <= v.fecha <= date(2026, 9, 30) for v in septiembre)
    assert any(v.fecha == date(2026, 9, 1) for v in septiembre)


def test_filtrar_por_categoria(datos):
    audio = filtrar(datos.ventas, de_categoria("audio", datos.productos))
    assert {v.id_producto for v in audio} == {"p005"}
    assert len(audio) == 4


def test_combinar_predicados(datos):
    combinado = todos(de_cliente("c002"), monto_entre(minimo=500))
    assert {v.id_venta for v in filtrar(datos.ventas, combinado)} == {"v004", "v005"}


def test_todos_sin_predicados_acepta_todo(datos):
    assert filtrar(datos.ventas, todos()) == datos.ventas


def test_filtrar_sin_resultados(datos):
    assert filtrar(datos.ventas, de_cliente("c006")) == ()


def test_filtrar_no_modifica_la_entrada(datos):
    antes = tuple(datos.ventas)
    filtrar(datos.ventas, de_cliente("c001"))
    assert datos.ventas == antes


# ---------- composición ----------
def test_componer_aplica_de_derecha_a_izquierda():
    assert componer(str, abs, int)("-3") == "3"


def test_componer_sin_funciones():
    with pytest.raises(ValueError):
        componer()


def test_total_del_cliente_es_una_funcion_nueva(datos):
    total_de_maria = total_del_cliente("c002")
    assert total_de_maria(datos.ventas) == 3235.0
    assert total_del_cliente("c006")(datos.ventas) == 0.0


# ---------- perfil del cliente ----------
def test_perfil_de_juan_calculado_a_mano(datos):
    perfil = perfil_cliente("c001", datos.ventas, datos.productos, HOY)
    assert perfil.n_compras == 3  # 20-jul, 10-ago, 26-ago (dos líneas el mismo día)
    assert perfil.ultima_compra == date(2026, 8, 26)
    assert perfil.dias_sin_comprar == 40
    assert perfil.total_gastado == 2650.0
    assert perfil.ticket_promedio == 883.33
    assert perfil.categorias_habituales == ("perifericos", "accesorios", "computo")


@pytest.mark.parametrize(
    ("cliente", "compras", "dias"),
    [
        ("c001", 3, 40),
        ("c002", 5, 4),
        ("c003", 2, 34),
        ("c004", 4, 25),
        ("c005", 1, 126),
        ("c007", 4, 61),
        ("c008", 3, 2),
    ],
)
def test_perfiles_de_la_tabla_del_dataset(datos, cliente, compras, dias):
    perfil = perfil_cliente(cliente, datos.ventas, datos.productos, HOY)
    assert (perfil.n_compras, perfil.dias_sin_comprar) == (compras, dias)


def test_perfil_de_cliente_sin_compras(datos):
    perfil = perfil_cliente("c006", datos.ventas, datos.productos, HOY)
    assert perfil == PerfilCliente("c006", 0, None, None, 0.0, 0.0, ())


def test_perfil_el_mismo_dia_de_la_ultima_compra(datos):
    perfil = perfil_cliente("c008", datos.ventas, datos.productos, date(2026, 10, 3))
    assert perfil.dias_sin_comprar == 0


def test_perfil_con_hoy_anterior_a_la_ultima_compra(datos):
    with pytest.raises(ValueError, match="anterior"):
        perfil_cliente("c008", datos.ventas, datos.productos, date(2026, 10, 1))


def test_perfil_cambia_si_cambia_la_fecha_de_referencia(datos):
    antes = perfil_cliente("c001", datos.ventas, datos.productos, HOY)
    despues = perfil_cliente("c001", datos.ventas, datos.productos, date(2026, 10, 15))
    assert despues.dias_sin_comprar == antes.dias_sin_comprar + 10


def test_perfil_es_inmutable(datos):
    perfil = perfil_cliente("c001", datos.ventas, datos.productos, HOY)
    with pytest.raises(FrozenInstanceError):
        perfil.n_compras = 99


def test_perfiles_uno_por_cliente_y_en_orden(datos):
    resultado = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    assert [p.id_cliente for p in resultado] == [c.id_cliente for c in datos.clientes]


def test_perfiles_acepta_generadores(datos):
    resultado = perfiles(iter(datos.clientes), iter(datos.ventas), iter(datos.productos), HOY)
    assert len(resultado) == 8


def test_totales_por_cliente_coinciden_con_pandas(datos, df):
    esperado = df.groupby("cliente")["monto"].sum()
    for p in perfiles(datos.clientes, datos.ventas, datos.productos, HOY):
        assert p.total_gastado == pytest.approx(esperado.get(p.id_cliente, 0.0))


# ---------- clasificación y descuentos ----------
def test_clasificacion_segun_el_umbral(datos):
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    clasificados = {c.id_cliente: type(c) for c in clasificar_clientes(datos.clientes, ps)}
    frecuentes = {k for k, t in clasificados.items() if t is ClienteFrecuente}
    assert frecuentes == {"c001", "c002", "c004", "c007", "c008"}
    assert clasificados["c003"] is ClienteRegular
    assert clasificados["c006"] is ClienteRegular


def test_umbral_por_defecto():
    assert UMBRAL_FRECUENTE == 3


def test_clasificar_con_otro_umbral(datos):
    cliente = next(c for c in datos.clientes if c.id_cliente == "c003")
    perfil = perfil_cliente("c003", datos.ventas, datos.productos, HOY)
    assert isinstance(clasificar_cliente(cliente, perfil, umbral=2), ClienteFrecuente)


def test_clasificar_crea_objeto_nuevo_sin_tocar_el_original(datos):
    original = datos.clientes[0]
    perfil = perfil_cliente("c001", datos.ventas, datos.productos, HOY)
    nuevo = clasificar_cliente(original, perfil)
    assert nuevo is not original
    assert isinstance(original, ClienteRegular)
    assert isinstance(nuevo, ClienteFrecuente)
    assert (nuevo.nombre, nuevo.telefono) == (original.nombre, original.telefono)


def test_clasificar_con_perfil_de_otro_cliente(datos):
    perfil_de_maria = perfil_cliente("c002", datos.ventas, datos.productos, HOY)
    with pytest.raises(ValueError, match="no corresponde"):
        clasificar_cliente(datos.clientes[0], perfil_de_maria)


def test_clasificar_clientes_sin_perfil(datos):
    with pytest.raises(ValueError, match="Faltan perfiles"):
        clasificar_clientes(datos.clientes, ())


def test_clasificar_clientes_acepta_generadores(datos):
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    assert len(clasificar_clientes(iter(datos.clientes), iter(ps))) == 8


def test_descuento_segun_el_tipo_de_cliente():
    assert precio_con_descuento(200.0, ClienteRegular("c001", "Juan")) == 200.0
    assert precio_con_descuento(200.0, ClienteFrecuente("c002", "Ana")) == 180.0


def test_descuento_redondea_a_centimos():
    assert precio_con_descuento(33.33, ClienteFrecuente("c001", "Juan")) == 30.0


def test_descuento_de_monto_cero_y_negativo():
    cliente = ClienteFrecuente("c001", "Juan")
    assert precio_con_descuento(0.0, cliente) == 0.0
    with pytest.raises(ValueError):
        precio_con_descuento(-1.0, cliente)


# ---------- pureza ----------
def test_las_funciones_son_deterministas(datos):
    a = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    b = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    assert a == b


def test_total_no_cambia_las_ventas_de_entrada():
    ventas = (venta("v1", precio=10.0), venta("v2", precio=5.0))
    total_ventas(ventas)
    assert ventas == (venta("v1", precio=10.0), venta("v2", precio=5.0))
