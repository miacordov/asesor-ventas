"""Procesamiento de datos con programación funcional.

Reglas de este módulo:
  * Funciones puras: mismo argumento, mismo resultado, sin efectos secundarios.
  * Nada se modifica: las entradas son tuplas/objetos inmutables y los
    resultados son valores nuevos.
  * Nada depende del reloj: la fecha de referencia (`hoy`) siempre se recibe
    como parámetro.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from functools import partial, reduce

from ventas.modelos import Cliente, ClienteFrecuente, ClienteRegular, Producto, Venta

UMBRAL_FRECUENTE = 3  # compras (días distintos) para ser cliente frecuente

Predicado = Callable[[Venta], bool]


# =====================================================================
# Predicados (funciones que devuelven funciones) y filtrado
# =====================================================================
def de_cliente(id_cliente: str) -> Predicado:
    return lambda venta: venta.id_cliente == id_cliente


def monto_entre(minimo: float = 0.0, maximo: float = float("inf")) -> Predicado:
    return lambda venta: minimo <= venta.monto <= maximo


def entre_fechas(desde: date, hasta: date) -> Predicado:
    return lambda venta: desde <= venta.fecha <= hasta


def de_categoria(categoria: str, productos: Iterable[Producto]) -> Predicado:
    ids = frozenset(p.id_producto for p in productos if p.categoria == categoria)
    return lambda venta: venta.id_producto in ids


def todos(*predicados: Predicado) -> Predicado:
    """Combina predicados: la venta debe cumplirlos todos."""
    return lambda venta: all(predicado(venta) for predicado in predicados)


def filtrar(ventas: Iterable[Venta], predicado: Predicado) -> tuple[Venta, ...]:
    return tuple(filter(predicado, ventas))


# =====================================================================
# Composición de funciones
# =====================================================================
def componer(*funciones: Callable) -> Callable:
    """componer(f, g, h)(x) == f(g(h(x)))."""
    if not funciones:
        raise ValueError("componer necesita al menos una función.")
    return reduce(lambda f, g: lambda x: f(g(x)), funciones)


def total_del_cliente(id_cliente: str) -> Callable[[Iterable[Venta]], float]:
    """Función nueva: ventas -> total gastado por ese cliente."""
    return componer(total_ventas, partial(filtrar, predicado=de_cliente(id_cliente)))


# =====================================================================
# Métricas (reduce)
# =====================================================================
def total_ventas(ventas: Iterable[Venta]) -> float:
    return round(reduce(lambda acumulado, venta: acumulado + venta.monto, ventas, 0.0), 2)


def promedio_ventas(ventas: Iterable[Venta]) -> float:
    """Monto promedio por línea de venta; 0.0 si no hay ventas."""
    ventas = tuple(ventas)
    return round(total_ventas(ventas) / len(ventas), 2) if ventas else 0.0


def sumar_por(ventas: Iterable[Venta], clave: Callable[[Venta], str]) -> dict[str, float]:
    """Suma los montos agrupando por la clave dada (sin mutar nada)."""

    def acumular(acumulado: dict[str, float], venta: Venta) -> dict[str, float]:
        k = clave(venta)
        return {**acumulado, k: round(acumulado.get(k, 0.0) + venta.monto, 2)}

    return reduce(acumular, ventas, {})


def ventas_por_categoria(
    ventas: Iterable[Venta], productos: Iterable[Producto]
) -> tuple[tuple[str, float], ...]:
    """(categoria, monto) de mayor a menor."""
    categoria_de = {p.id_producto: p.categoria for p in productos}
    montos = sumar_por(ventas, lambda venta: categoria_de[venta.id_producto])
    return tuple(sorted(montos.items(), key=lambda par: (-par[1], par[0])))


def ventas_por_mes(ventas: Iterable[Venta]) -> tuple[tuple[str, float], ...]:
    """('AAAA-MM', monto) en orden cronológico."""
    montos = sumar_por(ventas, lambda venta: venta.fecha.strftime("%Y-%m"))
    return tuple(sorted(montos.items()))


def ranking_productos(ventas: Iterable[Venta], n: int = 5) -> tuple[tuple[str, int], ...]:
    """(id_producto, unidades vendidas) de mayor a menor, los primeros n."""

    def acumular(acumulado: dict[str, int], venta: Venta) -> dict[str, int]:
        return {**acumulado, venta.id_producto: acumulado.get(venta.id_producto, 0) + venta.cantidad}

    unidades = reduce(acumular, ventas, {})
    ordenado = sorted(unidades.items(), key=lambda par: (-par[1], par[0]))
    return tuple(ordenado[: max(n, 0)])


# =====================================================================
# Perfil del cliente (alimenta las reglas de la agenda)
# =====================================================================
@dataclass(frozen=True)
class PerfilCliente:
    id_cliente: str
    n_compras: int  # días distintos en que compró
    ultima_compra: date | None
    dias_sin_comprar: int | None
    total_gastado: float
    ticket_promedio: float  # gasto medio por día de compra
    categorias_habituales: tuple[str, ...]  # de la más a la menos frecuente


def _categorias_habituales(
    ventas: Iterable[Venta], categoria_de: dict[str, str]
) -> tuple[str, ...]:
    def contar(acumulado: dict[str, int], venta: Venta) -> dict[str, int]:
        categoria = categoria_de[venta.id_producto]
        return {**acumulado, categoria: acumulado.get(categoria, 0) + 1}

    conteo = reduce(contar, ventas, {})
    return tuple(c for c, _ in sorted(conteo.items(), key=lambda par: (-par[1], par[0])))


def perfil_cliente(
    id_cliente: str, ventas: Iterable[Venta], productos: Iterable[Producto], hoy: date
) -> PerfilCliente:
    propias = filtrar(ventas, de_cliente(id_cliente))
    if not propias:
        return PerfilCliente(id_cliente, 0, None, None, 0.0, 0.0, ())

    dias_de_compra = {venta.fecha for venta in propias}
    ultima = max(dias_de_compra)
    if hoy < ultima:
        raise ValueError(f"hoy ({hoy}) es anterior a la última compra de {id_cliente} ({ultima}).")

    categoria_de = {p.id_producto: p.categoria for p in productos}
    total = total_ventas(propias)
    return PerfilCliente(
        id_cliente=id_cliente,
        n_compras=len(dias_de_compra),
        ultima_compra=ultima,
        dias_sin_comprar=(hoy - ultima).days,
        total_gastado=total,
        ticket_promedio=round(total / len(dias_de_compra), 2),
        categorias_habituales=_categorias_habituales(propias, categoria_de),
    )


def perfiles(
    clientes: Iterable[Cliente], ventas: Iterable[Venta], productos: Iterable[Producto], hoy: date
) -> tuple[PerfilCliente, ...]:
    ventas, productos = tuple(ventas), tuple(productos)
    return tuple(map(lambda c: perfil_cliente(c.id_cliente, ventas, productos, hoy), clientes))


# =====================================================================
# Clasificación y descuentos (sin mutar: se crean objetos nuevos)
# =====================================================================
def clasificar_cliente(
    cliente: Cliente, perfil: PerfilCliente, umbral: int = UMBRAL_FRECUENTE
) -> Cliente:
    if perfil.id_cliente != cliente.id_cliente:
        raise ValueError(f"El perfil {perfil.id_cliente} no corresponde al cliente {cliente.id_cliente}.")
    clase = ClienteFrecuente if perfil.n_compras >= umbral else ClienteRegular
    return clase(cliente.id_cliente, cliente.nombre, cliente.telefono)


def clasificar_clientes(
    clientes: Iterable[Cliente], perfiles_: Iterable[PerfilCliente], umbral: int = UMBRAL_FRECUENTE
) -> tuple[Cliente, ...]:
    clientes = tuple(clientes)
    por_id = {p.id_cliente: p for p in perfiles_}
    faltantes = [c.id_cliente for c in clientes if c.id_cliente not in por_id]
    if faltantes:
        raise ValueError(f"Faltan perfiles para: {faltantes}")
    return tuple(map(lambda c: clasificar_cliente(c, por_id[c.id_cliente], umbral), clientes))


def precio_con_descuento(monto: float, cliente: Cliente) -> float:
    """Aplica el descuento propio del tipo de cliente (polimorfismo)."""
    if monto < 0:
        raise ValueError(f"monto no puede ser negativo, recibido: {monto!r}")
    return round(monto * (1 - cliente.descuento()), 2)
