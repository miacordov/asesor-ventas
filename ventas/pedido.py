"""Pedidos sugeridos: "Arma mi pedido".

Reparto de trabajo:
  * Lógico:     Prolog GENERA todas las combinaciones válidas (backtracking con
                presupuesto, categorías y exclusión de lo ya comprado).
  * Funcional:  funciones puras ELIGEN las mejores combinaciones y calculan
                presupuesto, puntaje y descuento.
  * POO:        Pedido y PedidoSugerido modelan el resultado.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import reduce
from itertools import combinations

from ventas.funcional import PerfilCliente, precio_con_descuento
from ventas.logico import MINIMO_PRODUCTOS, MotorPedidos
from ventas.modelos import Cliente, ClienteFrecuente, Producto, Recomendacion, Venta
from ventas.ofertas import Oferta, aplicar_ofertas, ofertas_para_cliente

MAX_CATEGORIAS = 3  # un pedido sugerido combina como máximo 3 categorías
MAX_COMBINACIONES_MOSTRADOR = 5000  # se revisan todas para ordenar bien (ofertas y aprovechamiento)


# ---------------------------------------------------------------------
# POO
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Pedido:
    productos: tuple[Producto, ...]

    def __post_init__(self) -> None:
        if not self.productos:
            raise ValueError("Un pedido necesita al menos un producto.")

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(p.id_producto for p in self.productos)

    @property
    def subtotal(self) -> float:
        return round(sum(p.precio for p in self.productos), 2)

    def total_para(self, cliente: Cliente) -> float:
        """Total con el descuento propio del tipo de cliente (polimorfismo)."""
        return precio_con_descuento(self.subtotal, cliente)


@dataclass(frozen=True)
class PedidoSugerido:
    id_cliente: str
    pedido: Pedido
    presupuesto: float
    recomendados_incluidos: tuple[str, ...]
    puntaje: float
    total_con_descuento: float
    ofertas_incluidas: tuple[Oferta, ...] = ()  # ofertas para este cliente que trae el pedido


# ---------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------
def presupuesto_sugerido(perfil: PerfilCliente, margen: float = 0.10) -> float:
    """Su ticket promedio más un margen, redondeado hacia arriba a soles enteros."""
    if perfil.n_compras == 0:
        raise ValueError("El cliente no tiene historial de compras.")
    if margen < 0:
        raise ValueError(f"margen no puede ser negativo, recibido: {margen!r}")
    return float(math.ceil(round(perfil.ticket_promedio * (1 + margen), 2)))


def categorias_de_recomendaciones(
    recomendaciones: Iterable[Recomendacion], productos: Iterable[Producto], maximo: int = 3
) -> tuple[str, ...]:
    """Categorías distintas de los productos recomendados, de mayor a menor confianza."""
    categoria_de = {p.id_producto: p.categoria for p in productos}
    categorias = []
    for r in recomendaciones:
        if r.id_producto not in categoria_de:
            raise ValueError(f"El producto {r.id_producto} no está en el catálogo.")
        categorias.append(categoria_de[r.id_producto])
    return tuple(dict.fromkeys(categorias))[: max(maximo, 0)]


def categorias_alcanzables(
    categorias: Iterable[str], productos: Iterable[Producto], presupuesto: float
) -> tuple[str, ...]:
    """Descarta las categorías cuyo producto más barato ya excede el presupuesto."""

    def acumular_minimo(minimos: dict[str, float], producto: Producto) -> dict[str, float]:
        actual = minimos.get(producto.categoria, producto.precio)
        return {**minimos, producto.categoria: min(actual, producto.precio)}

    minimos = reduce(acumular_minimo, productos, {})
    return tuple(c for c in categorias if minimos.get(c, math.inf) <= presupuesto)


def categorias_para_combinar(categorias: Iterable[str]) -> tuple[str, ...]:
    """Una sola categoría se pide dos veces: así la combinación junta dos
    productos distintos de ella. Con dos o más, quedan igual."""
    categorias = tuple(categorias)
    return categorias * MINIMO_PRODUCTOS if len(categorias) == 1 else categorias


def productos_comprados(ventas: Iterable[Venta], id_cliente: str) -> frozenset[str]:
    """Los productos que el cliente ya compró alguna vez."""
    return frozenset(v.id_producto for v in ventas if v.id_cliente == id_cliente)


def puntaje(ids: Iterable[str], recomendaciones: Iterable[Recomendacion]) -> float:
    """Suma de la confianza de los productos recomendados que el pedido incluye."""
    ids = frozenset(ids)
    return round(sum(r.confianza for r in recomendaciones if r.id_producto in ids), 4)


# ---------------------------------------------------------------------
# Casos de uso
# ---------------------------------------------------------------------
def pedidos_para_cliente(
    cliente: Cliente,
    perfil: PerfilCliente,
    recomendaciones: Sequence[Recomendacion],
    productos: Iterable[Producto],
    motor: MotorPedidos,
    n: int = 3,
    margen: float = 0.10,
    vigentes: Mapping[str, Oferta] | None = None,
    comprados: Iterable[str] = (),
) -> tuple[PedidoSugerido, ...]:
    """Mejores pedidos para un cliente. Van primero los que traen más ofertas
    pensadas para él (ver ofertas_para_cliente); luego, los que incluyen más
    productos recomendados (ponderados por confianza) y, a igual puntaje, los de
    mayor valor. Solo se consideran categorías que el presupuesto alcanza.

    Las ofertas vigentes bajan el precio de sus productos. `comprados` son los
    productos que el cliente ya tiene: nunca se le ofertan.

    Precondición: el motor ya tiene las compras cargadas (para no repetirle lo
    que ya compró). construir_agenda() lo hace.
    """
    productos = tuple(productos)
    vigentes = dict(vigentes or {})
    if perfil.n_compras == 0:
        return ()
    relevantes = ofertas_para_cliente(
        vigentes, productos, perfil, recomendaciones, isinstance(cliente, ClienteFrecuente), comprados
    )
    if not recomendaciones and not relevantes:
        return ()
    productos = aplicar_ofertas(productos, vigentes)
    presupuesto = presupuesto_sugerido(perfil, margen)
    candidatas = tuple(o.producto.categoria for o in relevantes) + categorias_de_recomendaciones(
        recomendaciones, productos, maximo=len(recomendaciones)
    )
    categorias = categorias_alcanzables(tuple(dict.fromkeys(candidatas)), productos, presupuesto)[:MAX_CATEGORIAS]

    # Se intenta cubrir todas las categorías; si no cabe en el presupuesto, se
    # prueban subconjuntos cada vez más chicos (conservando el orden de confianza),
    # nunca de menos de MINIMO_PRODUCTOS categorías. Como último recurso, dos
    # productos de una misma categoría. Un producto solo no es una combinación.
    motor.cargar_catalogo(productos)
    subconjuntos = [
        subconjunto
        for k in range(len(categorias), MINIMO_PRODUCTOS - 1, -1)
        for subconjunto in combinations(categorias, k)
    ] + [categorias_para_combinar((c,)) for c in categorias]
    intentos = (
        motor.armar_pedidos(presupuesto, subconjunto, id_cliente=cliente.id_cliente)
        for subconjunto in subconjuntos
    )
    combinaciones = next((c for c in intentos if c), ())

    por_id = {p.id_producto: p for p in productos}
    pedidos = tuple(Pedido(tuple(por_id[i] for i in ids)) for ids in combinaciones)
    en_oferta = {o.id_producto for o in relevantes}
    mejores = sorted(
        pedidos,
        key=lambda p: (-len(en_oferta.intersection(p.ids)), -puntaje(p.ids, recomendaciones), -p.subtotal, p.ids),
    )[: max(n, 0)]
    return tuple(
        PedidoSugerido(
            id_cliente=cliente.id_cliente,
            pedido=pedido,
            presupuesto=presupuesto,
            recomendados_incluidos=tuple(
                r.id_producto for r in recomendaciones if r.id_producto in pedido.ids
            ),
            puntaje=puntaje(pedido.ids, recomendaciones),
            total_con_descuento=pedido.total_para(cliente),
            ofertas_incluidas=tuple(o.oferta for o in relevantes if o.id_producto in pedido.ids),
        )
        for pedido in mejores
    )


def armar_pedido_manual(
    motor: MotorPedidos,
    productos: Iterable[Producto],
    presupuesto: float,
    categorias: Sequence[str],
    n: int = 5,
    vigentes: Mapping[str, Oferta] | None = None,
) -> tuple[Pedido, ...]:
    """Modo mostrador: el vendedor indica presupuesto y categorías. Con una sola
    categoría se combinan dos productos de ella.

    Las ofertas vigentes bajan el precio (y así caben más combinaciones) y se
    sugieren primero: van delante los pedidos con más productos en oferta y,
    entre ellos, los que más aprovechan el presupuesto.
    """
    vigentes = dict(vigentes or {})
    productos = aplicar_ofertas(productos, vigentes)
    motor.cargar_catalogo(productos)
    combinaciones = motor.armar_pedidos(
        presupuesto, categorias_para_combinar(categorias), max_combinaciones=MAX_COMBINACIONES_MOSTRADOR
    )
    por_id = {p.id_producto: p for p in productos}
    pedidos = (Pedido(tuple(por_id[i] for i in ids)) for ids in combinaciones)

    def orden(pedido: Pedido) -> tuple:
        return (-sum(i in vigentes for i in pedido.ids), -pedido.subtotal, pedido.ids)

    return tuple(sorted(pedidos, key=orden)[: max(n, 0)])
