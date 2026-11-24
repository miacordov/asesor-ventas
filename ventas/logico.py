"""Puente entre Python y el motor lógico (SWI-Prolog vía pyswip).

Las reglas viven en prolog/reglas.pl, agenda.pl y pedido.pl; este módulo solo traduce:
    Venta (objetos)        ->  hechos compro/2
    PerfilCliente (objeto) ->  hechos n_compras/2, compras_recientes/2, intervalo_promedio/2,
                               dias_sin_comprar/2, umbral/2
    Producto (objeto)      ->  hechos producto/3 (precio en centavos)
    soluciones Prolog      ->  objetos Recomendacion, acciones y pedidos
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from pathlib import Path

from pyswip import Prolog

from ventas.funcional import UMBRAL_FRECUENTE, PerfilCliente
from ventas.modelos import Producto, Recomendacion, Venta, _validar_id

RUTA_PROLOG = Path(__file__).resolve().parent.parent / "prolog"
RUTA_REGLAS = RUTA_PROLOG / "reglas.pl"
RUTA_AGENDA = RUTA_PROLOG / "agenda.pl"
RUTA_PEDIDO = RUTA_PROLOG / "pedido.pl"
DIAS_INACTIVIDAD = 30  # inactivo, para quien no tiene un ritmo de compra propio (ver agenda.pl)
MINIMO_PRODUCTOS = 2  # una combinación lleva al menos 2 productos (ver pedido.pl)


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
    def limite_inactividad(self, id_cliente: str) -> int | None:
        """Días sin comprar a partir de los cuales el cliente está inactivo
        (None si no hay perfiles cargados)."""

    @abstractmethod
    def acciones(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        """(id_cliente, tipo, motivos) que el motor deduce, en orden estable."""


class MotorPedidos(ABC):
    """Contrato para motores que arman pedidos por búsqueda de combinaciones."""

    @abstractmethod
    def cargar_catalogo(self, productos: Iterable[Producto]) -> None:
        """Reemplaza los productos disponibles para armar pedidos."""

    @abstractmethod
    def complementos(self, id_cliente: str) -> tuple[str, ...]:
        """El producto más barato de cada categoría que complementa lo que el
        cliente compró y que todavía no compra, ordenados por categoría."""

    @abstractmethod
    def armar_pedidos(
        self,
        presupuesto: float,
        categorias: Sequence[str],
        id_cliente: str | None = None,
        max_combinaciones: int = 200,
    ) -> tuple[tuple[str, ...], ...]:
        """Combinaciones válidas (ids ordenados), un producto por categoría pedida,
        sin pasarse del presupuesto. Con id_cliente excluye lo que ya compró.
        Una combinación lleva al menos MINIMO_PRODUCTOS productos: con una sola
        categoría no hay combinaciones."""


def _a_centavos(monto: float) -> int:
    """Los precios viajan a Prolog como enteros: sin errores de decimales."""
    return round(monto * 100)


def pares_compra(ventas: Iterable[Venta]) -> tuple[tuple[str, str], ...]:
    """Pares (cliente, producto) sin repetir, en orden estable.

    Función pura: varias ventas del mismo producto al mismo cliente son un
    solo hecho para el motor.
    """
    return tuple(sorted({(v.id_cliente, v.id_producto) for v in ventas}))


class PuenteProlog(MotorLogico, MotorPedidos):
    """Motor lógico real: consulta SWI-Prolog mediante pyswip.

    Nota: SWI-Prolog es un único motor por proceso. Dos instancias comparten
    la misma base de hechos, por eso cargar_compras() siempre limpia antes.
    """

    def __init__(
        self, rutas_reglas: Iterable[Path | str] = (RUTA_REGLAS, RUTA_AGENDA, RUTA_PEDIDO)
    ) -> None:
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
        for hecho in ("umbral(_, _)", "n_compras(_, _)", "compras_recientes(_, _)", "intervalo_promedio(_, _)",
                      "dias_sin_comprar(_, _)"):
            list(self._prolog.query(f"retractall({hecho})"))
        self._prolog.assertz(f"umbral(frecuente, {umbral_frecuente})")
        self._prolog.assertz(f"umbral(inactividad, {dias_inactividad})")
        for perfil in perfiles:
            _validar_id(perfil.id_cliente, "id_cliente")
            self._prolog.assertz(f"n_compras({perfil.id_cliente}, {int(perfil.n_compras)})")
            self._prolog.assertz(f"compras_recientes({perfil.id_cliente}, {int(perfil.compras_recientes)})")
            if perfil.intervalo_promedio is not None:
                self._prolog.assertz(f"intervalo_promedio({perfil.id_cliente}, {float(perfil.intervalo_promedio)!r})")
            if perfil.dias_sin_comprar is not None:
                self._prolog.assertz(f"dias_sin_comprar({perfil.id_cliente}, {perfil.dias_sin_comprar})")

    def limite_inactividad(self, id_cliente: str) -> int | None:
        _validar_id(id_cliente, "id_cliente")
        resultado = list(self._prolog.query(f"limite_inactividad({id_cliente}, L)"))
        return int(resultado[0]["L"]) if resultado else None

    def acciones(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        soluciones = self._prolog.query("accion(C, T, M)")
        resultado = [(str(s["C"]), str(s["T"]), tuple(str(m) for m in s["M"])) for s in soluciones]
        return tuple(sorted(resultado))

    def cargar_catalogo(self, productos: Iterable[Producto]) -> None:
        list(self._prolog.query("retractall(producto(_, _, _))"))
        for p in productos:
            self._prolog.assertz(
                f"producto({p.id_producto}, {p.categoria}, {_a_centavos(p.precio)})"
            )

    def complementos(self, id_cliente: str) -> tuple[str, ...]:
        _validar_id(id_cliente, "id_cliente")
        mas_barato: dict[str, tuple[int, str]] = {}
        for s in self._prolog.query(f"complemento({id_cliente}, Cat, P, Centavos)"):
            candidato = (int(s["Centavos"]), str(s["P"]))
            categoria = str(s["Cat"])
            mas_barato[categoria] = min(mas_barato.get(categoria, candidato), candidato)
        return tuple(mas_barato[c][1] for c in sorted(mas_barato))

    def armar_pedidos(
        self,
        presupuesto: float,
        categorias: Sequence[str],
        id_cliente: str | None = None,
        max_combinaciones: int = 200,
    ) -> tuple[tuple[str, ...], ...]:
        if (
            isinstance(presupuesto, bool)
            or not isinstance(presupuesto, (int, float))
            or not math.isfinite(presupuesto)
            or presupuesto <= 0
        ):
            raise ValueError(f"presupuesto debe ser un número mayor que 0, recibido: {presupuesto!r}")
        categorias = tuple(categorias)
        if not categorias:
            raise ValueError("Indique al menos una categoría.")
        for categoria in categorias:
            _validar_id(categoria, "categoria")
        if id_cliente is not None:
            _validar_id(id_cliente, "id_cliente")
        if isinstance(max_combinaciones, bool) or not isinstance(max_combinaciones, int) or max_combinaciones < 1:
            raise ValueError(f"max_combinaciones debe ser un entero >= 1, recibido: {max_combinaciones!r}")

        lista = "[" + ", ".join(categorias) + "]"
        centavos = _a_centavos(presupuesto)
        if id_cliente is None:
            consulta = f"armar({centavos}, {lista}, P, T)"
        else:
            consulta = f"armar_para({id_cliente}, {centavos}, {lista}, P, T)"
        soluciones = self._prolog.query(consulta, maxresult=max_combinaciones)
        # Dos categorías iguales producen la misma combinación en distinto orden.
        combinaciones = {tuple(sorted(str(id_) for id_ in s["P"])) for s in soluciones}
        return tuple(sorted(combinaciones))

    def _una_solucion(self, consulta: str) -> dict:
        # maxresult=1 cierra la consulta; una consulta abierta bloquea las siguientes.
        return list(self._prolog.query(consulta, maxresult=1))[0]
