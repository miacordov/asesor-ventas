"""Modelos del dominio (paradigma orientado a objetos).

Todas las entidades son inmutables (frozen) y validan sus datos al crearse.
Los identificadores deben ser átomos válidos de Prolog (minúscula inicial, sin
espacios), porque más adelante se usan tal cual en los hechos del motor lógico.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

_PATRON_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _validar_id(valor: str, campo: str) -> None:
    """Exige un identificador compatible con un átomo de Prolog."""
    if not isinstance(valor, str) or not _PATRON_ID.match(valor):
        raise ValueError(
            f"{campo} inválido: {valor!r}. Use minúsculas, dígitos o '_' "
            "y empiece con una letra (ej: 'c001')."
        )


def _validar_texto(valor: str, campo: str) -> None:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{campo} no puede estar vacío.")


@dataclass(frozen=True)
class Cliente(ABC):
    """Cliente de la tienda. Clase abstracta: el descuento depende del tipo."""

    id_cliente: str
    nombre: str
    telefono: str = ""

    def __post_init__(self) -> None:
        _validar_id(self.id_cliente, "id_cliente")
        _validar_texto(self.nombre, "nombre")

    @abstractmethod
    def descuento(self) -> float:
        """Fracción de descuento (0.10 = 10%)."""


@dataclass(frozen=True)
class ClienteRegular(Cliente):
    def descuento(self) -> float:
        return 0.0


@dataclass(frozen=True)
class ClienteFrecuente(Cliente):
    def descuento(self) -> float:
        return 0.10


@dataclass(frozen=True)
class Producto:
    id_producto: str
    nombre: str
    categoria: str
    precio: float

    def __post_init__(self) -> None:
        _validar_id(self.id_producto, "id_producto")
        _validar_texto(self.nombre, "nombre")
        _validar_id(self.categoria, "categoria")
        if not isinstance(self.precio, (int, float)) or self.precio <= 0:
            raise ValueError(f"precio debe ser mayor que 0, recibido: {self.precio!r}")


@dataclass(frozen=True)
class Venta:
    """Una línea de venta. Guarda el precio del momento (no cambia si el
    producto sube de precio después)."""

    id_venta: str
    id_cliente: str
    id_producto: str
    cantidad: int
    precio_unitario: float
    fecha: date

    def __post_init__(self) -> None:
        _validar_id(self.id_venta, "id_venta")
        _validar_id(self.id_cliente, "id_cliente")
        _validar_id(self.id_producto, "id_producto")
        if not isinstance(self.cantidad, int) or self.cantidad < 1:
            raise ValueError(f"cantidad debe ser un entero >= 1, recibido: {self.cantidad!r}")
        if not isinstance(self.precio_unitario, (int, float)) or self.precio_unitario <= 0:
            raise ValueError(
                f"precio_unitario debe ser mayor que 0, recibido: {self.precio_unitario!r}"
            )
        if not isinstance(self.fecha, date):
            raise ValueError(f"fecha debe ser datetime.date, recibido: {self.fecha!r}")

    @property
    def monto(self) -> float:
        return round(self.cantidad * self.precio_unitario, 2)


@dataclass(frozen=True)
class Recomendacion:
    """Resultado del motor lógico: qué producto sugerir y con qué respaldo."""

    id_cliente: str
    id_producto: str
    soporte: int
    confianza: float

    def __post_init__(self) -> None:
        _validar_id(self.id_cliente, "id_cliente")
        _validar_id(self.id_producto, "id_producto")
        if not isinstance(self.soporte, int) or self.soporte < 1:
            raise ValueError(f"soporte debe ser un entero >= 1, recibido: {self.soporte!r}")
        if not 0 <= self.confianza <= 1:
            raise ValueError(f"confianza debe estar entre 0 y 1, recibido: {self.confianza!r}")
