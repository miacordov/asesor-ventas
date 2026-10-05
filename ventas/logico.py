"""Puente entre Python y el motor lógico (SWI-Prolog vía pyswip).

Las reglas viven en prolog/reglas.pl; este módulo solo traduce:
    Venta (objetos)  ->  hechos compro/2
    soluciones Prolog -> objetos Recomendacion
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from pyswip import Prolog

from ventas.modelos import Recomendacion, Venta, _validar_id

RUTA_REGLAS = Path(__file__).resolve().parent.parent / "prolog" / "reglas.pl"


class MotorLogico(ABC):
    """Contrato que debe cumplir cualquier motor de reglas."""

    @abstractmethod
    def cargar_compras(self, ventas: Iterable[Venta]) -> None:
        """Reemplaza los hechos del motor por las compras dadas."""

    @abstractmethod
    def recomendar(self, id_cliente: str) -> tuple[Recomendacion, ...]:
        """Productos sugeridos para el cliente, de mayor a menor confianza."""

    @abstractmethod
    def respaldo(self, id_cliente: str, id_producto: str) -> tuple[str, ...]:
        """Clientes similares que sustentan la recomendación (el 'por qué')."""


def pares_compra(ventas: Iterable[Venta]) -> tuple[tuple[str, str], ...]:
    """Pares (cliente, producto) sin repetir, en orden estable.

    Función pura: varias ventas del mismo producto al mismo cliente son un
    solo hecho para el motor.
    """
    return tuple(sorted({(v.id_cliente, v.id_producto) for v in ventas}))


class PuenteProlog(MotorLogico):
    """Motor lógico real: consulta SWI-Prolog mediante pyswip.

    Nota: SWI-Prolog es un único motor por proceso. Dos instancias comparten
    la misma base de hechos, por eso cargar_compras() siempre limpia antes.
    """

    def __init__(self, ruta_reglas: Path | str = RUTA_REGLAS) -> None:
        self._prolog = Prolog()
        self._prolog.consult(str(ruta_reglas))

    def cargar_compras(self, ventas: Iterable[Venta]) -> None:
        list(self._prolog.query("retractall(compro(_, _))"))
        for id_cliente, id_producto in pares_compra(ventas):
            self._prolog.assertz(f"compro({id_cliente}, {id_producto})")

    def recomendar(self, id_cliente: str) -> tuple[Recomendacion, ...]:
        # Se valida antes de armar la consulta: evita inyectar código Prolog.
        _validar_id(id_cliente, "id_cliente")
        similares = self._una_solucion(f"clientes_similares({id_cliente}, L)")["L"]
        if not similares:
            return ()
        recomendaciones = []
        for solucion in self._prolog.query(f"respaldo({id_cliente}, P, L)"):
            soporte = len(solucion["L"])
            recomendaciones.append(
                Recomendacion(
                    id_cliente=id_cliente,
                    id_producto=str(solucion["P"]),
                    soporte=soporte,
                    confianza=soporte / len(similares),
                )
            )
        return tuple(sorted(recomendaciones, key=lambda r: (-r.confianza, r.id_producto)))

    def respaldo(self, id_cliente: str, id_producto: str) -> tuple[str, ...]:
        _validar_id(id_cliente, "id_cliente")
        _validar_id(id_producto, "id_producto")
        consulta = f"respaldo({id_cliente}, {id_producto}, L)"
        resultado = list(self._prolog.query(consulta))
        return tuple(str(c) for c in resultado[0]["L"]) if resultado else ()

    def _una_solucion(self, consulta: str) -> dict:
        # maxresult=1 cierra la consulta; una consulta abierta bloquea las siguientes.
        return list(self._prolog.query(consulta, maxresult=1))[0]
