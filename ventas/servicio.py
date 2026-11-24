"""Servicio del asesor: la fachada que usa la interfaz.

La interfaz (app.py) no conoce Prolog, ni las reglas, ni los módulos internos:
le pide a este servicio tarjetas, tablas y resúmenes ya calculados. Así toda la
lógica de negocio se prueba sin necesidad de abrir Streamlit.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date

from ventas.agenda import EntradaAgenda, construir_agenda
from ventas.cargador import Datos
from ventas.combos import Combo, Cotizacion, cotizar
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
from ventas.mensajes import (
    Mensaje,
    MotorAsesor,
    mensaje_de_entrada,
    mensaje_pedido,
)
from ventas.modelos import Cliente, ClienteFrecuente, Producto, Recomendacion
from ventas.ofertas import Oferta, OfertaParaCliente, ofertas_para_cliente
from ventas.pedido import (
    PedidoSugerido,
    disponibles,
    pedidos_para_cliente,
    productos_comprados,
)


@dataclass(frozen=True)
class TarjetaAgenda:
    """Todo lo que el vendedor necesita ver de un cliente en la agenda."""

    entrada: EntradaAgenda
    cliente: Cliente  # ya clasificado como regular o frecuente
    recomendaciones: tuple[Recomendacion, ...]
    clientes_similares: int  # base sobre la que se calculó la confianza
    pedidos: tuple[PedidoSugerido, ...]
    mensaje: Mensaje
    ofertas: tuple[OfertaParaCliente, ...] = ()  # ofertas vigentes pensadas para este cliente
    pedido: Combo | None = None  # pedido abierto del cliente: su mensaje reemplaza al automático
    cotizacion: Cotizacion | None = None  # cuánto sale ese pedido
    complementos: tuple[Producto, ...] = ()  # de categorías que complementan lo que compró
    limite_inactividad: int | None = None  # días sin comprar desde los que está inactivo (Prolog)


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
    datos: Datos,
    hoy: date,
    motor: MotorAsesor,
    max_pedidos: int = 3,
    vigentes: Mapping[str, Oferta] | None = None,
    pedidos: Iterable[Combo] = (),
) -> tuple[TarjetaAgenda, ...]:
    """Agenda completa del día, lista para mostrar. Las ofertas vigentes se
    proponen a quien le corresponden y van primero en sus pedidos. Si el
    cliente tiene un pedido abierto (borrador o enviado), el mensaje es el de ese
    pedido (el más reciente) con la única regla de precio.

    Precondición: nadie más usa el motor mientras se ejecuta (SWI-Prolog es un
    único motor por proceso); la interfaz lo protege con un candado.
    """
    # Todas las recomendaciones de cada cliente se calculan una sola vez, en la agenda.
    agenda = construir_agenda(
        datos.clientes, datos.ventas, datos.productos, hoy, motor, max_recomendaciones=len(datos.productos)
    )
    vigentes = dict(vigentes or {})
    por_id = {c.id_cliente: c for c in datos.clientes}
    abiertos = {
        p.id_cliente: p for p in sorted(pedidos, key=lambda p: (p.fecha, p.id_combo)) if p.pendiente and p.registrado
    }
    nombres = {p.id_producto: p.nombre for p in datos.productos}
    producto_de = {p.id_producto: p for p in datos.productos}

    tarjetas = []
    for entrada in agenda:
        cliente = clasificar_cliente(por_id[entrada.accion.id_cliente], entrada.perfil)
        recomendaciones = entrada.recomendaciones
        comprados = productos_comprados(datos.ventas, cliente.id_cliente)
        pedidos = pedidos_para_cliente(
            cliente,
            entrada.perfil,
            recomendaciones,
            datos.productos,
            motor,
            n=max_pedidos,
            vigentes=vigentes,
            comprados=comprados,
        )
        ofertas = ofertas_para_cliente(
            vigentes,
            datos.productos,
            entrada.perfil,
            recomendaciones,
            isinstance(cliente, ClienteFrecuente),
            comprados,
        )
        limite = motor.limite_inactividad(cliente.id_cliente)
        abierto = abiertos.get(cliente.id_cliente)
        cotizacion = cotizar(abierto, datos.productos, vigentes, cliente) if abierto else None
        motor.cargar_catalogo(disponibles(datos.productos))
        complementos = tuple(producto_de[i] for i in motor.complementos(cliente.id_cliente))
        tarjetas.append(
            TarjetaAgenda(
                entrada=entrada,
                cliente=cliente,
                recomendaciones=recomendaciones,
                clientes_similares=_clientes_similares(recomendaciones),
                pedidos=pedidos,
                mensaje=_mensaje_de(
                    mensaje_de_entrada(entrada, cliente, pedidos[0] if pedidos else None, nombres), cotizacion
                ),
                ofertas=ofertas,
                pedido=abierto,
                cotizacion=cotizacion,
                complementos=complementos,
                limite_inactividad=limite,
            )
        )
    return tuple(tarjetas)


def _mensaje_de(automatico: Mensaje, cotizacion: Cotizacion | None) -> Mensaje:
    if cotizacion is None:
        return automatico
    return replace(automatico, texto=mensaje_pedido(automatico.nombre, cotizacion))


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


# ---------------------------------------------------------------------
# Efecto de un cambio en los datos sobre la agenda
# ---------------------------------------------------------------------
TITULOS_ACCION = {"reactivar": "Reactivar", "fidelizar": "Fidelizar", "cruzar": "Complementar"}


def acciones_por_cliente(datos: Datos, hoy: date, motor: MotorAsesor) -> dict[str, str]:
    """{id_cliente: tipo de acción} de la agenda de ese día (solo los que aparecen)."""
    agenda = construir_agenda(datos.clientes, datos.ventas, datos.productos, hoy, motor)
    return {entrada.accion.id_cliente: entrada.accion.tipo for entrada in agenda}


def describir_cambio_agenda(nombre: str, antes: str | None, despues: str | None) -> str:
    """Frase para mostrar qué le pasó a un cliente en la agenda tras registrar una venta."""
    if antes == despues:
        if antes is None:
            return f"{nombre} sigue sin aparecer en la agenda."
        return f"{nombre} sigue en la agenda como «{TITULOS_ACCION[antes]}»."
    if antes is None:
        return f"{nombre} ahora aparece en la agenda como «{TITULOS_ACCION[despues]}»."
    if despues is None:
        return f"{nombre} ya no aparece en la agenda."
    return f"{nombre} pasó de «{TITULOS_ACCION[antes]}» a «{TITULOS_ACCION[despues]}» en la agenda."
