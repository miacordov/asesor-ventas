"""Memoria de la agenda: a quién se contactó, qué respondió y cuándo volver.

  * POO:        Contacto valida sus datos.
  * Funcional:  funciones puras deciden quién está pospuesto.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from ventas.modelos import _validar_id

# resultado -> (texto para mostrar, días sugeridos para volver a contactar)
RESULTADOS = {
    "propuesta_enviada": ("Propuesta enviada", 3),
    "interesado": ("Interesado", 3),
    "no_responde": ("No responde", 7),
    "no_interesado": ("No interesado", 30),
}
MAX_DIAS = 365


@dataclass(frozen=True)
class Contacto:
    id_cliente: str
    fecha: date
    resultado: str
    volver_el: date  # hasta esta fecha (sin incluirla) el cliente no aparece en la agenda

    def __post_init__(self) -> None:
        _validar_id(self.id_cliente, "id_cliente")
        if self.resultado not in RESULTADOS:
            raise ValueError(f"Resultado desconocido: {self.resultado!r}. Use uno de {sorted(RESULTADOS)}.")
        if not isinstance(self.fecha, date) or not isinstance(self.volver_el, date):
            raise ValueError("Las fechas del contacto deben ser datetime.date.")
        if self.volver_el < self.fecha:
            raise ValueError("No se puede volver a contactar antes del contacto.")

    @property
    def texto(self) -> str:
        return RESULTADOS[self.resultado][0]


def nuevo_contacto(id_cliente: str, fecha: date, resultado: str, dias: int | None = None) -> Contacto:
    """El contacto de hoy; sin `dias`, se vuelve según lo sugerido para ese resultado."""
    if resultado not in RESULTADOS:
        raise ValueError(f"Resultado desconocido: {resultado!r}. Use uno de {sorted(RESULTADOS)}.")
    dias = RESULTADOS[resultado][1] if dias is None else dias
    if isinstance(dias, bool) or not isinstance(dias, int) or not 0 <= dias <= MAX_DIAS:
        raise ValueError(f"Los días para volver deben ser un entero entre 0 y {MAX_DIAS}, recibido: {dias!r}")
    return Contacto(id_cliente, fecha, resultado, fecha + timedelta(days=dias))


def ultimo_contacto(contactos: Iterable[Contacto], id_cliente: str) -> Contacto | None:
    propios = [c for c in contactos if c.id_cliente == id_cliente]
    return max(propios, key=lambda c: c.fecha, default=None)


def pospuestos(contactos: Iterable[Contacto], hoy: date) -> set[str]:
    """Clientes cuyo último contacto pide esperar más allá de hoy."""
    contactos = tuple(contactos)
    clientes = {c.id_cliente for c in contactos}
    return {c for c in clientes if (u := ultimo_contacto(contactos, c)) and u.volver_el > hoy}
