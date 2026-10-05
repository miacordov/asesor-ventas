"""Puente entre Python y el motor lógico (SWI-Prolog vía pyswip).

Las reglas viven en prolog/reglas.pl y prolog/agenda.pl; este módulo solo traduce:
    Venta (objetos)        ->  hechos compro/2
    PerfilCliente (objeto) ->  hechos n_compras/2, dias_sin_comprar/2, umbral/2
    soluciones Prolog      ->  objetos Recomendacion y acciones
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from pyswip import Prolog

from ventas.funcional import UMBRAL_FRECUENTE, PerfilCliente
from ventas.modelos import Recomendacion, Venta, _validar_id

RUTA_PROLOG = Path(__file__).resolve().parent.parent / "prolog"
RUTA_REGLAS = RUTA_PROLOG / "reglas.pl"
RUTA_AGENDA = RUTA_PROLOG / "agenda.pl"
DIAS_INACTIVIDAD = 30  # más de estos días sin comprar = cliente inactivo


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

    @abstractmethod
    def cargar_perfiles(
        self,
        perfiles: Iterable[PerfilCliente],
        umbral_frecuente: int = UMBRAL_FRECUENTE,
        dias_inactividad: int = DIAS_INACTIVIDAD,
    ) -> None:
        """Reemplaza los hechos de perfil y los umbrales de las reglas."""

    @abstractmethod
    def acciones(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        """(id_cliente, tipo, motivos) que el motor deduce, en orden estable."""


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

    def __init__(self, rutas_reglas: Iterable[Path | str] = (RUTA_REGLAS, RUTA_AGENDA)) -> None:
        self._prolog = Prolog()
        for ruta in rutas_reglas:
            self._prolog.consult(str(ruta))

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

    def cargar_perfiles(
        self,
        perfiles: Iterable[PerfilCliente],
        umbral_frecuente: int = UMBRAL_FRECUENTE,
        dias_inactividad: int = DIAS_INACTIVIDAD,
    ) -> None:
        for nombre, valor in (("umbral_frecuente", umbral_frecuente), ("dias_inactividad", dias_inactividad)):
            if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
                raise ValueError(f"{nombre} debe ser un entero >= 0, recibido: {valor!r}")
        for hecho in ("umbral(_, _)", "n_compras(_, _)", "dias_sin_comprar(_, _)"):
            list(self._prolog.query(f"retractall({hecho})"))
        self._prolog.assertz(f"umbral(frecuente, {umbral_frecuente})")
        self._prolog.assertz(f"umbral(inactividad, {dias_inactividad})")
        for perfil in perfiles:
            _validar_id(perfil.id_cliente, "id_cliente")
            self._prolog.assertz(f"n_compras({perfil.id_cliente}, {perfil.n_compras})")
            if perfil.dias_sin_comprar is not None:
                self._prolog.assertz(f"dias_sin_comprar({perfil.id_cliente}, {perfil.dias_sin_comprar})")

    def acciones(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        soluciones = self._prolog.query("accion(C, T, M)")
        resultado = [(str(s["C"]), str(s["T"]), tuple(str(m) for m in s["M"])) for s in soluciones]
        return tuple(sorted(resultado))

    def _una_solucion(self, consulta: str) -> dict:
        # maxresult=1 cierra la consulta; una consulta abierta bloquea las siguientes.
        return list(self._prolog.query(consulta, maxresult=1))[0]
