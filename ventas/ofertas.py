"""Ofertas por temporada de ventas.

  * POO:        Temporada, Oferta y DesempenoTemporada modelan el dominio.
  * Funcional:  funciones puras miden cómo se vende cada producto en una
                temporada y aplican las ofertas vigentes a los precios.

La persona elige qué productos poner en oferta; estas funciones solo le
muestran los datos y una sugerencia para decidir.
"""

import calendar
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date

from ventas.funcional import PerfilCliente
from ventas.modelos import Producto, Recomendacion, Venta, _validar_id

PORCENTAJE_MINIMO = 1
PORCENTAJE_MAXIMO = 90
INDICE_PICO = 1.3  # se vende 30 % más que el resto del año
INDICE_BAJO = 0.7  # se vende 30 % menos que el resto del año


@dataclass(frozen=True)
class Temporada:
    clave: str
    nombre: str
    meses: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.meses or any(m not in range(1, 13) for m in self.meses):
            raise ValueError(f"meses inválidos para la temporada {self.clave}: {self.meses!r}")

    def incluye(self, fecha: date) -> bool:
        return fecha.month in self.meses

    def fechas(self, desde: date) -> tuple[date, date]:
        """Inicio y fin de la temporada en curso o de la próxima, a partir de `desde`.
        Si la temporada ya empezó, el inicio es `desde` (una oferta no empieza en el pasado)."""
        primero, ultimo = min(self.meses), max(self.meses)
        for anio in (desde.year, desde.year + 1):
            inicio = date(anio, primero, 1)
            fin = date(anio, ultimo, calendar.monthrange(anio, ultimo)[1])
            if desde <= fin:
                return max(inicio, desde), fin
        raise AssertionError("inalcanzable: la temporada siempre ocurre al año siguiente")


def temporada_proxima(fecha: date) -> Temporada:
    """La temporada en curso o la que empieza antes a partir de la fecha."""
    return min(TEMPORADAS.values(), key=lambda t: (t.fechas(fecha)[0], t.clave))


TEMPORADAS = {
    t.clave: t
    for t in (
        Temporada("escolar", "Campaña escolar (febrero y marzo)", (2, 3)),
        Temporada("dia_de_la_madre", "Día de la Madre (mayo)", (5,)),
        Temporada("fiestas_patrias", "Fiestas Patrias y gratificación (julio)", (7,)),
        Temporada("fin_de_anio", "Black Friday y Navidad (noviembre y diciembre)", (11, 12)),
    )
}


@dataclass(frozen=True)
class Oferta:
    """Descuento de un producto entre dos fechas (ambas incluidas)."""

    id_producto: str
    porcentaje: int
    desde: date
    hasta: date

    def __post_init__(self) -> None:
        _validar_id(self.id_producto, "id_producto")
        if (
            isinstance(self.porcentaje, bool)
            or not isinstance(self.porcentaje, int)
            or not PORCENTAJE_MINIMO <= self.porcentaje <= PORCENTAJE_MAXIMO
        ):
            raise ValueError(
                f"El descuento debe ser un entero entre {PORCENTAJE_MINIMO} y {PORCENTAJE_MAXIMO} %, "
                f"recibido: {self.porcentaje!r}"
            )
        if not isinstance(self.desde, date) or not isinstance(self.hasta, date):
            raise ValueError("Las fechas de la oferta deben ser datetime.date.")
        if self.hasta < self.desde:
            raise ValueError("La oferta no puede terminar antes de empezar.")

    def vigente(self, fecha: date) -> bool:
        return self.desde <= fecha <= self.hasta

    def precio(self, precio_normal: float) -> float:
        # Nunca menos de un céntimo: un producto siempre tiene precio.
        return max(round(precio_normal * (100 - self.porcentaje) / 100, 2), 0.01)


@dataclass(frozen=True)
class DesempenoTemporada:
    """Cómo se vende un producto en la temporada frente al resto del año."""

    producto: Producto
    unidades_temporada: int
    promedio_temporada: float  # unidades por mes de temporada
    promedio_resto: float  # unidades por mes fuera de temporada
    indice: float  # promedio_temporada / promedio_resto (inf si solo vende en temporada)

    @property
    def sugerencia(self) -> str:
        if self.unidades_temporada == 0 and self.promedio_resto == 0:
            return "sin_ventas"
        if self.indice >= INDICE_PICO:
            return "pico"
        if self.indice <= INDICE_BAJO:
            return "baja_rotacion"
        return "estable"


@dataclass(frozen=True)
class OfertaParaCliente:
    """Una oferta vigente que tiene sentido proponerle a un cliente, y por qué."""

    oferta: Oferta
    producto: Producto
    motivos: tuple[str, ...]  # "similares", "categoria_habitual", "cliente_frecuente"

    @property
    def id_producto(self) -> str:
        return self.producto.id_producto


# ---------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------
def meses_del_historial(ventas: Iterable[Venta]) -> tuple[tuple[int, int], ...]:
    """(año, mes) de cada mes calendario entre la primera y la última venta."""
    fechas = [v.fecha for v in ventas]
    if not fechas:
        return ()
    inicio, fin = min(fechas), max(fechas)
    total = (fin.year - inicio.year) * 12 + fin.month - inicio.month + 1
    return tuple(
        (inicio.year + (inicio.month - 1 + i) // 12, (inicio.month - 1 + i) % 12 + 1) for i in range(total)
    )


def desempeno_en_temporada(
    productos: Iterable[Producto], ventas: Iterable[Venta], temporada: Temporada
) -> tuple[DesempenoTemporada, ...]:
    """Unidades por mes de cada producto en la temporada y fuera de ella.

    Orden: primero los picos de temporada (índice más alto), luego los demás.
    """
    ventas = tuple(ventas)
    meses = meses_del_historial(ventas)
    n_temporada = sum(1 for _, mes in meses if mes in temporada.meses)
    n_resto = len(meses) - n_temporada

    resultado = []
    for producto in productos:
        propias = [v for v in ventas if v.id_producto == producto.id_producto]
        en_temporada = sum(v.cantidad for v in propias if temporada.incluye(v.fecha))
        fuera = sum(v.cantidad for v in propias) - en_temporada
        promedio_temporada = en_temporada / n_temporada if n_temporada else 0.0
        promedio_resto = fuera / n_resto if n_resto else 0.0
        if promedio_resto:
            indice = promedio_temporada / promedio_resto
        else:
            indice = math.inf if promedio_temporada else 0.0
        resultado.append(
            DesempenoTemporada(
                producto=producto,
                unidades_temporada=en_temporada,
                promedio_temporada=round(promedio_temporada, 2),
                promedio_resto=round(promedio_resto, 2),
                indice=indice if math.isinf(indice) else round(indice, 2),
            )
        )
    return tuple(sorted(resultado, key=lambda d: (-d.indice, -d.unidades_temporada, d.producto.id_producto)))


def ofertas_vigentes(ofertas: Iterable[Oferta], fecha: date) -> dict[str, Oferta]:
    """Las ofertas activas en la fecha, por producto."""
    return {o.id_producto: o for o in ofertas if o.vigente(fecha)}


def aplicar_ofertas(productos: Iterable[Producto], vigentes: Mapping[str, Oferta]) -> tuple[Producto, ...]:
    """Los productos con el precio de su oferta vigente (los demás quedan igual)."""
    return tuple(
        replace(p, precio=vigentes[p.id_producto].precio(p.precio)) if p.id_producto in vigentes else p
        for p in productos
    )


def ofertas_para_cliente(
    vigentes: Mapping[str, Oferta],
    productos: Iterable[Producto],
    perfil: PerfilCliente,
    recomendaciones: Iterable[Recomendacion],
    frecuente: bool,
    comprados: Iterable[str] = (),
) -> tuple[OfertaParaCliente, ...]:
    """Las ofertas vigentes que le corresponden al cliente, nunca de algo que ya compró:

      * similares:          la compraron clientes con compras parecidas (motor Prolog);
      * categoria_habitual: es de una categoría que el cliente compra;
      * cliente_frecuente:  a quien compra seguido se le ofrecen todas.

    Orden: más motivos primero; luego mayor descuento.
    """
    recomendados = {r.id_producto for r in recomendaciones}
    habituales = set(perfil.categorias_habituales)
    comprados = set(comprados)
    resultado = []
    for producto in productos:
        oferta = vigentes.get(producto.id_producto)
        if oferta is None or producto.id_producto in comprados:
            continue
        motivos = tuple(
            motivo
            for motivo, aplica in (
                ("similares", producto.id_producto in recomendados),
                ("categoria_habitual", producto.categoria in habituales),
                ("cliente_frecuente", frecuente),
            )
            if aplica
        )
        if motivos:
            resultado.append(OfertaParaCliente(oferta, producto, motivos))
    return tuple(sorted(resultado, key=lambda o: (-len(o.motivos), -o.oferta.porcentaje, o.id_producto)))
