"""Mensajes personalizados y enlaces de WhatsApp.

El sistema NUNCA envía mensajes: solo prepara el texto y un enlace que abre
WhatsApp con el mensaje escrito. El vendedor decide si lo envía.

  * Funcional:  la redacción es una composición de funciones puras.
  * POO:        Mensaje es un objeto inmutable que valida sus datos.
  * Lógico:     la oferta sale de las recomendaciones y los pedidos que
                calcula el motor Prolog (pedido.py).
"""

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from ventas.agenda import EntradaAgenda
from ventas.funcional import PerfilCliente, clasificar_cliente
from ventas.modelos import Cliente, Producto, Recomendacion, _validar_id, _validar_texto
from ventas.pedido import PedidoSugerido, pedidos_para_cliente

# Formato internacional de WhatsApp: solo dígitos, sin "+", sin cero inicial, hasta 15.
_PATRON_TELEFONO = re.compile(r"^[1-9]\d{7,14}$")


class MotorAsesor(Protocol):
    """Lo que necesita este módulo del motor lógico (lo cumple PuenteProlog)."""

    def recomendar(self, id_cliente: str) -> tuple[Recomendacion, ...]: ...

    def cargar_catalogo(self, productos: Iterable[Producto]) -> None: ...

    def armar_pedidos(
        self,
        presupuesto: float,
        categorias: Sequence[str],
        id_cliente: str | None = None,
        max_combinaciones: int = 200,
    ) -> tuple[tuple[str, ...], ...]: ...


# ---------------------------------------------------------------------
# Funciones puras de formato
# ---------------------------------------------------------------------
def validar_telefono(telefono: str) -> str:
    if not isinstance(telefono, str) or not _PATRON_TELEFONO.match(telefono):
        raise ValueError(
            f"Teléfono inválido: {telefono!r}. Use solo dígitos con código de país, "
            "sin '+' ni cero inicial (ej: 51900000001)."
        )
    return telefono


def enlace_whatsapp(telefono: str, texto: str) -> str:
    """Enlace que abre WhatsApp con el mensaje ya escrito (no lo envía)."""
    validar_telefono(telefono)
    _validar_texto(texto, "texto")
    return f"https://wa.me/{telefono}?text={quote(texto, safe='')}"


def enumerar(items: Sequence[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b y c'."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def dinero(monto: float) -> str:
    return f"S/ {monto:,.2f}"


def dias_texto(dias: int) -> str:
    return f"{dias} día" if dias == 1 else f"{dias} días"


def primer_nombre(nombre: str) -> str:
    return nombre.split()[0]


def frase_oferta(
    cliente: Cliente,
    pedido: PedidoSugerido | None,
    recomendados: Sequence[str],
) -> str:
    """La parte del mensaje con la propuesta ('' si no hay nada que ofrecer)."""
    if pedido is not None:
        lista = enumerar([p.nombre for p in pedido.pedido.productos])
        subtotal, total = pedido.pedido.subtotal, pedido.total_con_descuento
        if total < subtotal:
            porcentaje = round(cliente.descuento() * 100)
            return (
                f"Te armamos esta propuesta: {lista} por {dinero(subtotal)} "
                f"({dinero(total)} con tu descuento del {porcentaje} %)."
            )
        return f"Te armamos esta propuesta: {lista} por {dinero(total)}."
    if recomendados:
        return f"Creemos que te pueden interesar: {enumerar(list(recomendados))}."
    return ""


# Una plantilla por tipo de acción: (saludo, cierre).
_PLANTILLAS: dict[str, tuple[Callable[[str, PerfilCliente], str], str]] = {
    "reactivar": (
        lambda n, p: f"Hola {n}, hace {dias_texto(p.dias_sin_comprar)} que no nos visitas y queremos saber cómo estás.",
        "¡Te esperamos!",
    ),
    "fidelizar": (
        lambda n, p: f"Hola {n}, gracias por seguir eligiéndonos.",
        "¡Gracias por tu confianza!",
    ),
    "cruzar": (
        lambda n, p: f"Hola {n}, por lo que has comprado con nosotros, creemos que podemos ayudarte.",
        "¡Cuéntanos si te interesa!",
    ),
}


def redactar_mensaje(
    tipo_accion: str,
    cliente: Cliente,
    perfil: PerfilCliente,
    pedido: PedidoSugerido | None,
    recomendados: Sequence[str] = (),
) -> str:
    if tipo_accion not in _PLANTILLAS:
        raise ValueError(f"Tipo de acción sin plantilla: {tipo_accion!r}")
    saludo, cierre = _PLANTILLAS[tipo_accion]
    partes = [saludo(primer_nombre(cliente.nombre), perfil), frase_oferta(cliente, pedido, recomendados), cierre]
    return " ".join(parte for parte in partes if parte)


# ---------------------------------------------------------------------
# POO
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Mensaje:
    id_cliente: str
    nombre: str
    telefono: str  # vacío si el cliente no tiene teléfono registrado
    tipo_accion: str
    texto: str

    def __post_init__(self) -> None:
        _validar_id(self.id_cliente, "id_cliente")
        _validar_texto(self.nombre, "nombre")
        _validar_texto(self.texto, "texto")
        if self.telefono:
            validar_telefono(self.telefono)

    @property
    def enlace(self) -> str | None:
        """Enlace de WhatsApp, o None si no hay teléfono."""
        return enlace_whatsapp(self.telefono, self.texto) if self.telefono else None


# ---------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------
def mensajes_para_agenda(
    agenda: Iterable[EntradaAgenda],
    clientes: Iterable[Cliente],
    productos: Iterable[Producto],
    motor: MotorAsesor,
) -> tuple[Mensaje, ...]:
    """Un mensaje por cada entrada de la agenda, en el mismo orden.

    Precondición: el motor ya tiene las compras cargadas (construir_agenda lo hace).
    """
    por_id = {c.id_cliente: c for c in clientes}
    productos = tuple(productos)
    nombre_de = {p.id_producto: p.nombre for p in productos}
    mensajes = []
    for entrada in agenda:
        base = por_id[entrada.accion.id_cliente]
        cliente = clasificar_cliente(base, entrada.perfil)
        recomendaciones = motor.recomendar(cliente.id_cliente)
        sugeridos = pedidos_para_cliente(cliente, entrada.perfil, recomendaciones, productos, motor, n=1)
        texto = redactar_mensaje(
            entrada.accion.tipo,
            cliente,
            entrada.perfil,
            sugeridos[0] if sugeridos else None,
            [nombre_de[r.id_producto] for r in recomendaciones[:3]],
        )
        mensajes.append(Mensaje(cliente.id_cliente, cliente.nombre, cliente.telefono, entrada.accion.tipo, texto))
    return tuple(mensajes)
