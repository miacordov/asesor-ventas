"""Pedidos guardados para un cliente: del armado a la venta.

Un pedido nace como borrador (desde la agenda o desde «Arma mi pedido») y
pasa por estos estados, que se deducen de lo que guarda:

    borrador  -> precios en vivo: cada día con las ofertas vigentes
    enviado   -> precios y descuento fijos: se cobra lo que se le prometió
    vendido   -> ya tiene sus ventas registradas
    descartado

Una sola regla de precio: precio base -> oferta vigente -> descuento del
pedido, que es el que puso el vendedor o, si no puso ninguno, el del cliente
(10 % si es frecuente).

  * POO:        Combo y LineaCombo validan sus datos.
  * Funcional:  lineas_combo, descuento_de, congelar y ventas_del_combo son puras.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

from ventas.modelos import Cliente, Producto, Venta, _validar_id
from ventas.ofertas import Oferta

MINIMO_PRODUCTOS = 2
DESCUENTO_MAXIMO = 90
ESTADOS = {"borrador": "Borrador", "enviado": "Enviado", "vendido": "Vendido", "descartado": "Descartado"}


@dataclass(frozen=True)
class Combo:
    id_combo: str
    id_cliente: str | None  # None: cliente no registrado (ver nombre_cliente)
    ids_productos: tuple[str, ...]
    fecha: date  # cuándo se guardó
    ids_ventas: tuple[str, ...] = ()  # ventas con que se registró (vacío: no vendido)
    nombre_cliente: str = ""  # solo para clientes no registrados
    descuento: int | None = None  # % del vendedor; None: el que le corresponde al cliente
    precios: tuple[float, ...] = ()  # fijados al enviarlo, uno por producto (vacío: en vivo)
    descartado: bool = False

    def __post_init__(self) -> None:
        _validar_id(self.id_combo, "id_combo")
        if self.id_cliente is None:
            if not isinstance(self.nombre_cliente, str) or not self.nombre_cliente.strip():
                raise ValueError("Indica el cliente registrado o el nombre del cliente no registrado.")
        else:
            _validar_id(self.id_cliente, "id_cliente")
            if self.nombre_cliente:
                raise ValueError("Un combo es de un cliente registrado o de uno no registrado, no de ambos.")
        for id_producto in self.ids_productos:
            _validar_id(id_producto, "id_producto")
        if len(set(self.ids_productos)) != len(self.ids_productos):
            raise ValueError("El combo repite un producto.")
        if len(self.ids_productos) < MINIMO_PRODUCTOS:
            raise ValueError(f"Un combo lleva al menos {MINIMO_PRODUCTOS} productos.")
        if not isinstance(self.fecha, date):
            raise ValueError("La fecha del combo debe ser datetime.date.")
        if self.descuento is not None and (
            isinstance(self.descuento, bool)
            or not isinstance(self.descuento, int)
            or not 0 <= self.descuento <= DESCUENTO_MAXIMO
        ):
            raise ValueError(f"El descuento debe ser un entero entre 0 y {DESCUENTO_MAXIMO} %, recibido: {self.descuento!r}")
        if self.precios:
            if len(self.precios) != len(self.ids_productos):
                raise ValueError("Un pedido enviado lleva un precio por producto.")
            if any(isinstance(p, bool) or not isinstance(p, (int, float)) or p <= 0 for p in self.precios):
                raise ValueError(f"Cada precio debe ser mayor que 0, recibido: {self.precios!r}")
        if self.descartado and self.ids_ventas:
            raise ValueError("Un pedido vendido no se puede descartar: anula sus ventas.")

    @property
    def estado(self) -> str:
        if self.ids_ventas:
            return "vendido"
        if self.descartado:
            return "descartado"
        return "enviado" if self.precios else "borrador"

    @property
    def pendiente(self) -> bool:
        """¿Sigue abierto (borrador o enviado)?"""
        return self.estado in ("borrador", "enviado")

    @property
    def registrado(self) -> bool:
        """¿El cliente ya está registrado?"""
        return self.id_cliente is not None


@dataclass(frozen=True)
class LineaCombo:
    producto: Producto  # con su precio normal
    oferta: Oferta | None  # vigente en la fecha consultada (None si el precio está fijado)
    precio_fijo: float | None = None  # el acordado al enviar el pedido

    @property
    def en_oferta(self) -> bool:
        return self.precio < self.producto.precio

    @property
    def precio(self) -> float:
        if self.precio_fijo is not None:
            return self.precio_fijo
        return self.oferta.precio(self.producto.precio) if self.oferta else self.producto.precio


def lineas_combo(combo: Combo, productos: Iterable[Producto], vigentes: Mapping[str, Oferta]) -> tuple[LineaCombo, ...]:
    """Los productos del pedido: con sus precios fijos si se envió, o con la
    oferta que tengan vigente si todavía es un borrador."""
    por_id = {p.id_producto: p for p in productos}
    if combo.precios:
        return tuple(
            LineaCombo(por_id[i], None, precio)
            for i, precio in zip(combo.ids_productos, combo.precios, strict=True)
            if i in por_id
        )
    return tuple(LineaCombo(por_id[i], vigentes.get(i)) for i in combo.ids_productos if i in por_id)


def descuento_de(combo: Combo, cliente: Cliente | None) -> int:
    """El del vendedor si lo puso; si no, el del tipo de cliente (polimorfismo)."""
    if combo.descuento is not None:
        return combo.descuento
    return round(cliente.descuento() * 100) if cliente is not None else 0


def total_combo(lineas: Iterable[LineaCombo]) -> float:
    return round(sum(linea.precio for linea in lineas), 2)


def total_combo_con_descuento(lineas: Iterable[LineaCombo], descuento: int) -> float:
    return round(total_combo(lineas) * (100 - descuento) / 100, 2)


def congelar(combo: Combo, lineas: Sequence[LineaCombo], descuento: int) -> Combo:
    """El pedido enviado: precios y descuento quedan fijos."""
    if not combo.pendiente:
        raise ValueError(f"El pedido {combo.id_combo} ya está {ESTADOS[combo.estado].lower()}.")
    if len(lineas) != len(combo.ids_productos):
        raise ValueError(f"El pedido {combo.id_combo} tiene productos que ya no están en el catálogo.")
    return replace(combo, precios=tuple(linea.precio for linea in lineas), descuento=descuento)


def ventas_del_combo(
    combo: Combo,
    lineas: Sequence[LineaCombo],
    ids_ventas: Sequence[str],
    fecha: date,
    id_cliente: str | None = None,
    descuento: int = 0,
) -> tuple[Venta, ...]:
    """Una venta (cantidad 1) por producto. El descuento del pedido se reparte
    entre las líneas y la última absorbe el redondeo, para que las ventas sumen
    exactamente el total. Para un cliente no registrado, `id_cliente` es el del
    cliente que se crea al registrar la venta."""
    id_cliente = combo.id_cliente or id_cliente
    if id_cliente is None:
        raise ValueError(f"El combo {combo.id_combo} es de un cliente no registrado: falta crear su cliente.")
    if combo.estado == "vendido":
        raise ValueError(f"El combo {combo.id_combo} ya se registró.")
    if combo.estado == "descartado":
        raise ValueError(f"El pedido {combo.id_combo} está descartado.")
    if len(lineas) != len(combo.ids_productos):
        raise ValueError(f"El combo {combo.id_combo} tiene productos que ya no están en el catálogo.")
    if len(ids_ventas) != len(lineas):
        raise ValueError("Se necesita un número de venta por producto.")
    precios = [round(linea.precio * (100 - descuento) / 100, 2) for linea in lineas]
    precios[-1] = round(total_combo_con_descuento(lineas, descuento) - sum(precios[:-1]), 2)
    if precios[-1] <= 0:
        raise ValueError(f"El descuento del pedido {combo.id_combo} deja un producto sin precio.")
    return tuple(
        Venta(id_venta, id_cliente, linea.producto.id_producto, 1, precio, fecha)
        for id_venta, linea, precio in zip(ids_ventas, lineas, precios, strict=True)
    )


@dataclass(frozen=True)
class Cotizacion:
    """Cuánto sale el pedido hoy (o lo que se acordó, si ya se envió)."""

    lineas: tuple[LineaCombo, ...]
    descuento: int

    @property
    def subtotal(self) -> float:
        return total_combo(self.lineas)

    @property
    def total(self) -> float:
        return total_combo_con_descuento(self.lineas, self.descuento)


def cotizar(
    combo: Combo, productos: Iterable[Producto], vigentes: Mapping[str, Oferta], cliente: Cliente | None
) -> Cotizacion:
    """La única regla de precio: base -> oferta (o precio fijo) -> descuento del pedido."""
    return Cotizacion(lineas_combo(combo, productos, vigentes), descuento_de(combo, cliente))
