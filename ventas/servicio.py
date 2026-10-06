"""Servicio del asesor: la fachada que usa la interfaz.

La interfaz (app.py) no conoce Prolog, ni las reglas, ni los módulos internos:
le pide a este servicio tarjetas, tablas y resúmenes ya calculados. Así toda la
lógica de negocio se prueba sin necesidad de abrir Streamlit.
"""

from dataclasses import dataclass
from datetime import date

from ventas.agenda import EntradaAgenda, construir_agenda
from ventas.cargador import Datos
from ventas.funcional import (
    PerfilCliente,
    clasificar_cliente,
    clasificar_clientes,
    perfiles,
    promedio_ventas,
    ranking_productos,
    total_ventas,
    ventas_por_categoria,
    ventas_por_mes,
)
from ventas.mensajes import Mensaje, MotorAsesor, mensajes_para_agenda
from ventas.modelos import Cliente, Recomendacion
from ventas.pedido import PedidoSugerido, pedidos_para_cliente


@dataclass(frozen=True)
class TarjetaAgenda:
    """Todo lo que el vendedor necesita ver de un cliente en la agenda."""

    entrada: EntradaAgenda
    cliente: Cliente  # ya clasificado como regular o frecuente
    recomendaciones: tuple[Recomendacion, ...]
    clientes_similares: int  # base sobre la que se calculó la confianza
    pedidos: tuple[PedidoSugerido, ...]
    mensaje: Mensaje


@dataclass(frozen=True)
class ResumenVentas:
    total: float
    promedio_por_linea: float
    n_ventas: int
    n_clientes: int
    por_mes: tuple[tuple[str, float], ...]
    por_categoria: tuple[tuple[str, float], ...]
    top_productos: tuple[tuple[str, int], ...]  # (nombre, unidades)


def construir_tarjetas(
    datos: Datos, hoy: date, motor: MotorAsesor, max_pedidos: int = 3
) -> tuple[TarjetaAgenda, ...]:
    """Agenda completa del día, lista para mostrar.

    Precondición: nadie más usa el motor mientras se ejecuta (SWI-Prolog es un
    único motor por proceso); la interfaz lo protege con un candado.
    """
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, hoy, motor)
    mensajes = mensajes_para_agenda(agenda, datos.clientes, datos.productos, motor)
    por_id = {c.id_cliente: c for c in datos.clientes}

    tarjetas = []
    for entrada, mensaje in zip(agenda, mensajes, strict=True):
        cliente = clasificar_cliente(por_id[entrada.accion.id_cliente], entrada.perfil)
        recomendaciones = motor.recomendar(cliente.id_cliente)
        pedidos = pedidos_para_cliente(
            cliente, entrada.perfil, recomendaciones, datos.productos, motor, n=max_pedidos
        )
        tarjetas.append(
            TarjetaAgenda(
                entrada=entrada,
                cliente=cliente,
                recomendaciones=recomendaciones,
                clientes_similares=_clientes_similares(recomendaciones),
                pedidos=pedidos,
                mensaje=mensaje,
            )
        )
    return tuple(tarjetas)


def _clientes_similares(recomendaciones: tuple[Recomendacion, ...]) -> int:
    """soporte / confianza = número de clientes similares (0 si no hay)."""
    if not recomendaciones:
        return 0
    primera = recomendaciones[0]
    return round(primera.soporte / primera.confianza)


def clientes_con_perfil(datos: Datos, hoy: date) -> tuple[tuple[Cliente, PerfilCliente], ...]:
    """Cada cliente (clasificado) junto con su perfil, en el orden del archivo."""
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, hoy)
    clasificados = clasificar_clientes(datos.clientes, ps)
    return tuple(zip(clasificados, ps, strict=True))


def resumen_ventas(datos: Datos) -> ResumenVentas:
    nombre_de = {p.id_producto: p.nombre for p in datos.productos}
    return ResumenVentas(
        total=total_ventas(datos.ventas),
        promedio_por_linea=promedio_ventas(datos.ventas),
        n_ventas=len(datos.ventas),
        n_clientes=len(datos.clientes),
        por_mes=ventas_por_mes(datos.ventas),
        por_categoria=ventas_por_categoria(datos.ventas, datos.productos),
        top_productos=tuple((nombre_de[i], u) for i, u in ranking_productos(datos.ventas, n=5)),
    )
