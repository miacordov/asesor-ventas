"""Análisis exploratorio de las ventas con pandas y NumPy.

Lo usa el panel de administración. Los totales se pueden contrastar con los que
calcula `funcional.py` con `reduce`: son dos formas independientes de llegar al
mismo número.
"""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from ventas.cargador import Datos
from ventas.funcional import PerfilCliente

SEGMENTOS = ("Alto", "Medio", "Bajo", "Sin compras")
_COLUMNAS = [
    "id_venta", "id_cliente", "cliente", "id_producto", "producto",
    "categoria", "cantidad", "precio_unitario", "monto", "fecha", "mes",
]  # fmt: skip


def dataframe_ventas(datos: Datos) -> pd.DataFrame:
    """Una fila por venta, con nombres legibles, monto, fecha y mes (AAAA-MM)."""
    cliente_de = {c.id_cliente: c.nombre for c in datos.clientes}
    producto_de = {p.id_producto: p for p in datos.productos}
    filas = [
        {
            "id_venta": v.id_venta,
            "id_cliente": v.id_cliente,
            "cliente": cliente_de[v.id_cliente],
            "id_producto": v.id_producto,
            "producto": producto_de[v.id_producto].nombre,
            "categoria": producto_de[v.id_producto].categoria,
            "cantidad": v.cantidad,
            "precio_unitario": v.precio_unitario,
            "monto": v.monto,
            "fecha": v.fecha,
            "mes": v.fecha.strftime("%Y-%m"),
        }
        for v in datos.ventas
    ]
    df = pd.DataFrame(filas, columns=_COLUMNAS)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def compras_totales(df: pd.DataFrame) -> int:
    """Una compra es un día distinto en que un cliente adquirió algo."""
    return int(df[["id_cliente", "fecha"]].drop_duplicates().shape[0])


def ticket_promedio_compra(df: pd.DataFrame) -> float:
    compras = compras_totales(df)
    return round(float(df["monto"].sum()) / compras, 2) if compras else 0.0


def resumen_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Ventas, compras y variación porcentual respecto al mes anterior.

    El último mes puede estar incompleto, y su variación lo refleja.
    """
    columnas = ["mes", "ventas", "compras", "variacion_pct"]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    ventas = df.groupby("mes")["monto"].sum().round(2)
    compras = df[["id_cliente", "fecha", "mes"]].drop_duplicates().groupby("mes").size()
    resumen = pd.DataFrame({"ventas": ventas, "compras": compras}).sort_index()
    resumen["variacion_pct"] = (resumen["ventas"].pct_change() * 100).round(1)
    return resumen.reset_index(names="mes")[columnas]


def ventas_por_categoria(df: pd.DataFrame) -> pd.DataFrame:
    columnas = ["categoria", "ventas", "participacion_pct"]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    por_categoria = df.groupby("categoria")["monto"].sum().round(2).sort_values(ascending=False)
    resultado = por_categoria.rename("ventas").reset_index()
    resultado["participacion_pct"] = (resultado["ventas"] / resultado["ventas"].sum() * 100).round(1)
    return resultado[columnas]


def top_clientes(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    columnas = ["cliente", "ventas", "participacion_pct"]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    por_cliente = df.groupby(["id_cliente", "cliente"])["monto"].sum().round(2).rename("ventas").reset_index()
    por_cliente = por_cliente.sort_values(["ventas", "id_cliente"], ascending=[False, True]).head(max(n, 0))
    total = df["monto"].sum()
    por_cliente["participacion_pct"] = (por_cliente["ventas"] / total * 100).round(1)
    return por_cliente[columnas].reset_index(drop=True)


def concentracion_top(df: pd.DataFrame, n: int = 3) -> float:
    """Porcentaje de las ventas que concentran los n mejores clientes."""
    if df.empty:
        return 0.0
    totales = np.sort(df.groupby("id_cliente")["monto"].sum().to_numpy())[::-1]
    return round(float(totales[: max(n, 0)].sum() / totales.sum() * 100), 1)


def segmentar_clientes(perfiles: Iterable[PerfilCliente]) -> dict[str, str]:
    """Alto, Medio o Bajo según el gasto total, por terciles (NumPy).

    Los clientes sin compras quedan como 'Sin compras' y no entran en el cálculo
    de los terciles. Si todos gastaron lo mismo, todos son 'Medio'.
    """
    perfiles = tuple(perfiles)
    con_compras = [p for p in perfiles if p.n_compras > 0]
    segmentos = {p.id_cliente: "Sin compras" for p in perfiles}
    if not con_compras:
        return segmentos
    gastos = np.array([p.total_gastado for p in con_compras], dtype=float)
    corte_bajo, corte_alto = np.round(np.quantile(gastos, [1 / 3, 2 / 3]), 2)
    for perfil in con_compras:
        if corte_bajo == corte_alto:
            segmentos[perfil.id_cliente] = "Medio"
        elif perfil.total_gastado >= corte_alto:
            segmentos[perfil.id_cliente] = "Alto"
        elif perfil.total_gastado >= corte_bajo:
            segmentos[perfil.id_cliente] = "Medio"
        else:
            segmentos[perfil.id_cliente] = "Bajo"
    return segmentos


def tabla_segmentos(perfiles: Iterable[PerfilCliente]) -> pd.DataFrame:
    """Clientes, ventas y participación de cada segmento (siempre los cuatro)."""
    perfiles = tuple(perfiles)
    segmento_de = segmentar_clientes(perfiles)
    df = pd.DataFrame(
        {"segmento": [segmento_de[p.id_cliente] for p in perfiles], "ventas": [p.total_gastado for p in perfiles]},
        columns=["segmento", "ventas"],
    )
    agrupado = df.groupby("segmento")["ventas"].agg(clientes="size", ventas="sum")
    tabla = agrupado.reindex(list(SEGMENTOS), fill_value=0).reset_index()
    total = tabla["ventas"].sum()
    tabla["ventas"] = tabla["ventas"].round(2)
    tabla["participacion_pct"] = (tabla["ventas"] / total * 100).round(1) if total else 0.0
    return tabla


def a_csv(df: pd.DataFrame) -> bytes:
    """CSV listo para abrir en Excel (UTF-8 con marca de orden de bytes)."""
    return df.to_csv(index=False).encode("utf-8-sig")
