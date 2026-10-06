import io
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ventas.analisis import (
    SEGMENTOS,
    a_csv,
    compras_totales,
    concentracion_top,
    dataframe_ventas,
    resumen_mensual,
    segmentar_clientes,
    tabla_segmentos,
    ticket_promedio_compra,
    top_clientes,
    ventas_por_categoria,
)
from ventas.cargador import Datos, cargar_todo
from ventas.funcional import (
    PerfilCliente,
    perfiles,
    total_ventas,
    ventas_por_mes,
)
from ventas.funcional import (
    ventas_por_categoria as categorias_funcional,
)

DATOS = Path(__file__).resolve().parent.parent / "datos"
HOY = date(2026, 10, 5)


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


@pytest.fixture
def df(datos):
    return dataframe_ventas(datos)


@pytest.fixture
def vacio(datos):
    return dataframe_ventas(Datos(datos.clientes, datos.productos, ()))


def perfil(id_cliente, n_compras, total):
    return PerfilCliente(id_cliente, n_compras, date(2026, 9, 1) if n_compras else None, 5 if n_compras else None, total, total, ())


# =====================================================================
# DataFrame base
# =====================================================================
def test_dataframe_tiene_una_fila_por_venta_y_las_columnas_esperadas(df):
    assert len(df) == 30
    assert list(df.columns) == [
        "id_venta", "id_cliente", "cliente", "id_producto", "producto",
        "categoria", "cantidad", "precio_unitario", "monto", "fecha", "mes",
    ]  # fmt: skip


def test_dataframe_trae_nombres_legibles_y_fechas_reales(df):
    fila = df[df["id_venta"] == "v001"].iloc[0]
    assert (fila["cliente"], fila["producto"], fila["categoria"]) == ("Juan Pérez", "Laptop 14 pulgadas", "computo")
    assert fila["fecha"] == pd.Timestamp("2026-07-20") and fila["mes"] == "2026-07"


def test_dataframe_sin_ventas_conserva_las_columnas(vacio):
    assert len(vacio) == 0 and "monto" in vacio.columns


# =====================================================================
# Contraste con las funciones puras (dos caminos al mismo número)
# =====================================================================
def test_total_coincide_con_reduce(df, datos):
    assert df["monto"].sum() == pytest.approx(total_ventas(datos.ventas))


def test_ventas_por_mes_coinciden_con_el_modulo_funcional(df, datos):
    esperado = dict(ventas_por_mes(datos.ventas))
    obtenido = dict(zip(resumen_mensual(df)["mes"], resumen_mensual(df)["ventas"], strict=True))
    assert obtenido == pytest.approx(esperado)


def test_ventas_por_categoria_coinciden_con_el_modulo_funcional(df, datos):
    esperado = dict(categorias_funcional(datos.ventas, datos.productos))
    tabla = ventas_por_categoria(df)
    assert dict(zip(tabla["categoria"], tabla["ventas"], strict=True)) == pytest.approx(esperado)


def test_compras_coinciden_con_los_perfiles(df, datos):
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    assert compras_totales(df) == sum(p.n_compras for p in ps)


# =====================================================================
# Cálculos a mano
# =====================================================================
def test_resumen_mensual_a_mano(df):
    r = resumen_mensual(df)
    assert list(r["mes"]) == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert list(r["ventas"]) == [810.0, 3065.0, 3425.0, 895.0, 260.0]
    assert list(r["compras"]) == [2, 4, 8, 6, 2]
    assert pd.isna(r["variacion_pct"].iloc[0])
    # (3065 - 810) / 810 = 278.4 %;  (3425 - 3065) / 3065 = 11.7 %;  (895 - 3425) / 3425 = -73.9 %
    assert list(r["variacion_pct"].iloc[1:]) == [278.4, 11.7, -73.9, -70.9]


def test_participacion_por_categoria_suma_cien(df):
    tabla = ventas_por_categoria(df)
    assert tabla.iloc[0]["categoria"] == "computo" and tabla.iloc[0]["participacion_pct"] == 56.2
    assert tabla["participacion_pct"].sum() == pytest.approx(100.0, abs=0.2)
    assert list(tabla["ventas"]) == sorted(tabla["ventas"], reverse=True)


def test_top_clientes_a_mano(df):
    t = top_clientes(df, 3)
    assert list(t["cliente"]) == ["María Torres", "Juan Pérez", "Pedro Salas"]
    assert list(t["ventas"]) == [3235.0, 2650.0, 1195.0]
    assert list(t["participacion_pct"]) == [38.3, 31.3, 14.1]


def test_concentracion_de_los_tres_mejores_clientes(df):
    assert concentracion_top(df, 3) == 83.7  # (3235 + 2650 + 1195) / 8455
    assert concentracion_top(df, 1) == 38.3
    assert concentracion_top(df, 100) == 100.0
    assert concentracion_top(df, 0) == 0.0


def test_ticket_promedio_por_compra(df):
    assert compras_totales(df) == 22
    assert ticket_promedio_compra(df) == 384.32  # 8455 / 22


def test_ventas_del_mismo_dia_del_mismo_cliente_son_una_compra(df):
    # c001 compró dos productos el 26-ago: cuenta una sola compra ese día
    juan = df[df["id_cliente"] == "c001"]
    assert len(juan) == 4 and compras_totales(juan) == 3


# =====================================================================
# Casos de borde con datos vacíos
# =====================================================================
def test_todo_funciona_sin_ventas(vacio):
    assert resumen_mensual(vacio).empty
    assert ventas_por_categoria(vacio).empty
    assert top_clientes(vacio).empty
    assert concentracion_top(vacio) == 0.0
    assert compras_totales(vacio) == 0
    assert ticket_promedio_compra(vacio) == 0.0


def test_una_sola_venta(datos):
    una = dataframe_ventas(Datos(datos.clientes, datos.productos, datos.ventas[:1]))
    r = resumen_mensual(una)
    assert len(r) == 1 and pd.isna(r["variacion_pct"].iloc[0])
    assert concentracion_top(una, 3) == 100.0


# =====================================================================
# Segmentación
# =====================================================================
def test_segmentos_calculados_a_mano(datos):
    # Gastos: 290, 310, 320, 455, 1195, 2650, 3235 -> terciles 320 y 1195
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    assert segmentar_clientes(ps) == {
        "c001": "Alto", "c002": "Alto", "c007": "Alto",
        "c003": "Medio", "c004": "Medio",
        "c005": "Bajo", "c008": "Bajo",
        "c006": "Sin compras",
    }  # fmt: skip


def test_la_tabla_de_segmentos_siempre_tiene_los_cuatro(datos):
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    t = tabla_segmentos(ps)
    assert list(t["segmento"]) == list(SEGMENTOS)
    assert list(t["clientes"]) == [3, 2, 2, 1]
    assert list(t["ventas"]) == [7080.0, 775.0, 600.0, 0.0]
    assert list(t["participacion_pct"]) == [83.7, 9.2, 7.1, 0.0]
    assert t["clientes"].sum() == len(ps)


def test_el_total_de_los_segmentos_coincide_con_el_de_ventas(datos, df):
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    assert tabla_segmentos(ps)["ventas"].sum() == pytest.approx(df["monto"].sum())


def test_segmentar_sin_clientes():
    assert segmentar_clientes([]) == {}
    assert list(tabla_segmentos([])["clientes"]) == [0, 0, 0, 0]


def test_segmentar_solo_clientes_sin_compras():
    assert segmentar_clientes([perfil("c001", 0, 0.0), perfil("c002", 0, 0.0)]) == {
        "c001": "Sin compras", "c002": "Sin compras",
    }  # fmt: skip


def test_si_todos_gastaron_lo_mismo_todos_son_medio():
    ps = [perfil(f"c00{i}", 1, 100.0) for i in range(1, 5)]
    assert set(segmentar_clientes(ps).values()) == {"Medio"}


def test_un_solo_cliente_con_compras_es_medio():
    assert segmentar_clientes([perfil("c001", 2, 500.0)]) == {"c001": "Medio"}


def test_los_cortes_de_los_terciles_no_dependen_del_orden():
    ps = [perfil(f"c00{i}", 1, g) for i, g in enumerate([10.0, 20.0, 30.0, 40.0, 50.0, 60.0], start=1)]
    a = segmentar_clientes(ps)
    b = segmentar_clientes(list(reversed(ps)))
    assert a == b
    assert sorted(set(a.values())) == ["Alto", "Bajo", "Medio"]


def test_segmentos_coinciden_con_numpy_directo(datos):
    ps = [p for p in perfiles(datos.clientes, datos.ventas, datos.productos, HOY) if p.n_compras]
    gastos = np.array([p.total_gastado for p in ps])
    bajo, alto = np.quantile(gastos, [1 / 3, 2 / 3])
    segmentos = segmentar_clientes(ps)
    for p in ps:
        esperado = "Alto" if p.total_gastado >= round(alto, 2) else "Medio" if p.total_gastado >= round(bajo, 2) else "Bajo"
        assert segmentos[p.id_cliente] == esperado


# =====================================================================
# Exportación
# =====================================================================
def test_csv_exportado_se_puede_leer_de_vuelta(df):
    contenido = a_csv(df)
    assert contenido.startswith(b"\xef\xbb\xbf")  # marca UTF-8 para Excel
    leido = pd.read_csv(io.BytesIO(contenido))
    assert len(leido) == 30
    assert leido["cliente"].iloc[0] == "Juan Pérez"
    assert leido["monto"].sum() == pytest.approx(8455.0)
