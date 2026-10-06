"""Agenda comercial: a quién contactar hoy, qué hacer y por qué.

Aquí se integran los tres paradigmas:
  * Lógico:     Prolog decide QUÉ acción corresponde y POR QUÉ (motivos).
  * Funcional:  los perfiles se calculan con funciones puras y la agenda se
                ordena con una clave explícita.
  * POO:        cada tipo de acción es una clase con su propio título,
                prioridad y comportamiento (herencia y polimorfismo).
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from functools import reduce
from typing import ClassVar

from ventas.funcional import PerfilCliente, perfiles
from ventas.logico import MotorLogico
from ventas.modelos import Cliente, Producto, Recomendacion, Venta, _validar_id

# ---------------------------------------------------------------------
# Motivos (átomos de Prolog) -> frases para el vendedor
# ---------------------------------------------------------------------
_FRASES: dict[str, Callable[[PerfilCliente], str]] = {
    "frecuente": lambda p: f"compró {p.n_compras} veces",
    "inactivo": lambda p: f"lleva {p.dias_sin_comprar} días sin comprar",
    "reciente": lambda p: f"su última compra fue {_hace(p.dias_sin_comprar)}",
    "no_frecuente": lambda p: f"tiene pocas compras ({p.n_compras})",
    "similares": lambda p: "clientes con compras parecidas ya llevaron otros productos",
}


def _hace(dias: int) -> str:
    """0 -> 'hoy', 1 -> 'hace 1 día', 4 -> 'hace 4 días'."""
    if dias == 0:
        return "hoy"
    return "hace 1 día" if dias == 1 else f"hace {dias} días"


def _frase(motivo: str, perfil: PerfilCliente) -> str:
    if motivo not in _FRASES:
        raise ValueError(f"Motivo desconocido: {motivo!r}")
    return _FRASES[motivo](perfil)


# ---------------------------------------------------------------------
# POO: jerarquía de acciones
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Accion(ABC):
    """Algo que el vendedor puede hacer con un cliente."""

    id_cliente: str
    motivos: tuple[str, ...]

    tipo: ClassVar[str]
    prioridad: ClassVar[str]  # texto para mostrar: alta, media, baja
    peso: ClassVar[int]  # número para ordenar (mayor = más urgente)

    def __post_init__(self) -> None:
        _validar_id(self.id_cliente, "id_cliente")
        if not self.motivos:
            raise ValueError("Una acción necesita al menos un motivo.")

    @abstractmethod
    def titulo(self) -> str:
        """Título corto para la tarjeta de la agenda."""

    def explicar(self, perfil: PerfilCliente) -> str:
        """El 'por qué' en una frase, a partir de los motivos del motor lógico."""
        texto = ", ".join(_frase(motivo, perfil) for motivo in self.motivos)
        return texto[0].upper() + texto[1:]


@dataclass(frozen=True)
class Reactivar(Accion):
    tipo: ClassVar[str] = "reactivar"
    prioridad: ClassVar[str] = "alta"
    peso: ClassVar[int] = 3

    def titulo(self) -> str:
        return "Reactivar cliente"


@dataclass(frozen=True)
class Fidelizar(Accion):
    tipo: ClassVar[str] = "fidelizar"
    prioridad: ClassVar[str] = "media"
    peso: ClassVar[int] = 2

    def titulo(self) -> str:
        return "Fidelizar cliente"


@dataclass(frozen=True)
class Cruzar(Accion):
    tipo: ClassVar[str] = "cruzar"
    prioridad: ClassVar[str] = "baja"
    peso: ClassVar[int] = 1

    def titulo(self) -> str:
        return "Ofrecer productos complementarios"


_CLASES: dict[str, type[Accion]] = {c.tipo: c for c in (Reactivar, Fidelizar, Cruzar)}


def crear_accion(tipo: str, id_cliente: str, motivos: Iterable[str]) -> Accion:
    """Fábrica: convierte lo que dice Prolog en el objeto correspondiente."""
    if tipo not in _CLASES:
        raise ValueError(f"Tipo de acción desconocido: {tipo!r}")
    return _CLASES[tipo](id_cliente, tuple(motivos))


# ---------------------------------------------------------------------
# Agenda
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class EntradaAgenda:
    accion: Accion
    perfil: PerfilCliente
    motivo: str
    recomendaciones: tuple[Recomendacion, ...]


def _mejor_por_cliente(acciones: Iterable[Accion]) -> tuple[Accion, ...]:
    """Si un cliente tiene varias acciones posibles, queda la más urgente."""

    def elegir(elegidas: dict[str, Accion], accion: Accion) -> dict[str, Accion]:
        actual = elegidas.get(accion.id_cliente)
        if actual is not None and actual.peso >= accion.peso:
            return elegidas
        return {**elegidas, accion.id_cliente: accion}

    return tuple(reduce(elegir, acciones, {}).values())


def construir_agenda(
    clientes: Iterable[Cliente],
    ventas: Iterable[Venta],
    productos: Iterable[Producto],
    hoy: date,
    motor: MotorLogico,
    max_recomendaciones: int = 3,
) -> tuple[EntradaAgenda, ...]:
    """Agenda del día, ordenada: primero la acción más urgente y, a igual
    urgencia, el cliente que más ha gastado."""
    clientes, ventas, productos = tuple(clientes), tuple(ventas), tuple(productos)
    perfiles_ = perfiles(clientes, ventas, productos, hoy)  # funcional
    por_cliente = {p.id_cliente: p for p in perfiles_}

    motor.cargar_compras(ventas)  # lógico
    motor.cargar_perfiles(perfiles_)
    candidatas = (crear_accion(tipo, c, motivos) for c, tipo, motivos in motor.acciones())

    entradas = tuple(
        EntradaAgenda(
            accion=accion,
            perfil=por_cliente[accion.id_cliente],
            motivo=accion.explicar(por_cliente[accion.id_cliente]),  # POO
            recomendaciones=motor.recomendar(accion.id_cliente)[: max(max_recomendaciones, 0)],
        )
        for accion in _mejor_por_cliente(candidatas)
    )
    return tuple(
        sorted(
            entradas,
            key=lambda e: (-e.accion.peso, -e.perfil.total_gastado, e.accion.id_cliente),
        )
    )
