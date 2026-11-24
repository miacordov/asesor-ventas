"""Propuestas armadas a mano para un cliente y guardadas en la agenda.

El vendedor elige los productos (con o sin oferta) y un descuento para el
combo; la propuesta se guarda con los precios de ese momento, así el mensaje
que se envía después dice lo mismo que se acordó, aunque la oferta venza.

  * POO:        LineaPropuesta y Propuesta validan sus datos.
  * Funcional:  armar_propuesta es una función pura (el texto está en mensajes.py).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from ventas.modelos import Producto, _validar_id
from ventas.ofertas import Oferta

MINIMO_PRODUCTOS = 2  # una propuesta es un combo
DESCUENTO_MAXIMO = 90


@dataclass(frozen=True)
class LineaPropuesta:
    id_producto: str
    precio_normal: float
    precio: float  # con la oferta vigente al guardar (igual al normal si no había)

    def __post_init__(self) -> None:
        _validar_id(self.id_producto, "id_producto")
        if not 0 < self.precio <= self.precio_normal:
            raise ValueError(f"Precio inválido para {self.id_producto}: {self.precio!r} (normal {self.precio_normal!r}).")

    @property
    def en_oferta(self) -> bool:
        return self.precio < self.precio_normal


@dataclass(frozen=True)
class Propuesta:
    id_cliente: str
    lineas: tuple[LineaPropuesta, ...]
    descuento: int  # % sobre el combo, decidido por el vendedor
    fecha: date

    def __post_init__(self) -> None:
        _validar_id(self.id_cliente, "id_cliente")
        ids = [linea.id_producto for linea in self.lineas]
        if len(set(ids)) < MINIMO_PRODUCTOS:
            raise ValueError(f"Una propuesta es un combo: elige al menos {MINIMO_PRODUCTOS} productos distintos.")
        if len(set(ids)) != len(ids):
            raise ValueError("La propuesta repite un producto.")
        if (
            isinstance(self.descuento, bool)
            or not isinstance(self.descuento, int)
            or not 0 <= self.descuento <= DESCUENTO_MAXIMO
        ):
            raise ValueError(f"El descuento del combo debe ser un entero entre 0 y {DESCUENTO_MAXIMO} %, recibido: {self.descuento!r}")
        if not isinstance(self.fecha, date):
            raise ValueError("La fecha de la propuesta debe ser datetime.date.")

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(linea.id_producto for linea in self.lineas)

    @property
    def subtotal(self) -> float:
        return round(sum(linea.precio for linea in self.lineas), 2)

    @property
    def total(self) -> float:
        return round(self.subtotal * (100 - self.descuento) / 100, 2)


# ---------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------
def armar_propuesta(
    id_cliente: str,
    ids_productos: Iterable[str],
    descuento: int,
    fecha: date,
    productos: Iterable[Producto],
    vigentes: Mapping[str, Oferta],
) -> Propuesta:
    """La propuesta con los precios de hoy: el de oferta si hay una vigente."""
    por_id = {p.id_producto: p for p in productos}
    lineas = []
    for id_producto in ids_productos:
        if id_producto not in por_id:
            raise ValueError(f"No existe el producto {id_producto}.")
        normal = por_id[id_producto].precio
        oferta = vigentes.get(id_producto)
        lineas.append(LineaPropuesta(id_producto, normal, oferta.precio(normal) if oferta else normal))
    return Propuesta(id_cliente, tuple(lineas), descuento, fecha)
