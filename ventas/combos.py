"""Combinaciones guardadas desde «Arma mi pedido» para registrarlas como venta.

Un combo guarda el cliente y los productos, no los precios: mientras está
pendiente se muestra con las ofertas vigentes de cada día, y al registrarlo
cada producto se vende al precio de ese momento (con su oferta si sigue vigente).

  * POO:        Combo y LineaCombo validan sus datos.
  * Funcional:  lineas_combo y ventas_del_combo son funciones puras.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ventas.modelos import Producto, Venta, _validar_id
from ventas.ofertas import Oferta

MINIMO_PRODUCTOS = 2


@dataclass(frozen=True)
class Combo:
    id_combo: str
    id_cliente: str
    ids_productos: tuple[str, ...]
    fecha: date  # cuándo se guardó
    ids_ventas: tuple[str, ...] = ()  # ventas con que se registró (vacío: pendiente)

    def __post_init__(self) -> None:
        _validar_id(self.id_combo, "id_combo")
        _validar_id(self.id_cliente, "id_cliente")
        for id_producto in self.ids_productos:
            _validar_id(id_producto, "id_producto")
        if len(set(self.ids_productos)) != len(self.ids_productos):
            raise ValueError("El combo repite un producto.")
        if len(self.ids_productos) < MINIMO_PRODUCTOS:
            raise ValueError(f"Un combo lleva al menos {MINIMO_PRODUCTOS} productos.")
        if not isinstance(self.fecha, date):
            raise ValueError("La fecha del combo debe ser datetime.date.")

    @property
    def pendiente(self) -> bool:
        return not self.ids_ventas


@dataclass(frozen=True)
class LineaCombo:
    producto: Producto  # con su precio normal
    oferta: Oferta | None  # vigente en la fecha consultada

    @property
    def precio(self) -> float:
        return self.oferta.precio(self.producto.precio) if self.oferta else self.producto.precio


def lineas_combo(combo: Combo, productos: Iterable[Producto], vigentes: Mapping[str, Oferta]) -> tuple[LineaCombo, ...]:
    """Los productos del combo con la oferta que tengan vigente."""
    por_id = {p.id_producto: p for p in productos}
    return tuple(LineaCombo(por_id[i], vigentes.get(i)) for i in combo.ids_productos if i in por_id)


def total_combo(lineas: Iterable[LineaCombo]) -> float:
    return round(sum(linea.precio for linea in lineas), 2)


def ventas_del_combo(
    combo: Combo, lineas: Sequence[LineaCombo], ids_ventas: Sequence[str], fecha: date
) -> tuple[Venta, ...]:
    """Una venta (cantidad 1) por producto, al precio del día: con oferta si sigue vigente."""
    if not combo.pendiente:
        raise ValueError(f"El combo {combo.id_combo} ya se registró.")
    if len(lineas) != len(combo.ids_productos):
        raise ValueError(f"El combo {combo.id_combo} tiene productos que ya no están en el catálogo.")
    if len(ids_ventas) != len(lineas):
        raise ValueError("Se necesita un número de venta por producto.")
    return tuple(
        Venta(id_venta, combo.id_cliente, linea.producto.id_producto, 1, linea.precio, fecha)
        for id_venta, linea in zip(ids_ventas, lineas, strict=True)
    )
