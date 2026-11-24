"""Carga de datos desde CSV hacia objetos del dominio.

Es la única capa que conoce el formato de los archivos. Valida columnas,
tipos, duplicados e integridad referencial, y reporta el archivo y la fila
exacta donde está el problema.
"""

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ventas.modelos import Cliente, ClienteRegular, Producto, Venta


class ErrorDatos(ValueError):
    """Los datos de entrada no son válidos (archivo, columna o fila)."""


@dataclass(frozen=True)
class Datos:
    clientes: tuple[Cliente, ...]
    productos: tuple[Producto, ...]
    ventas: tuple[Venta, ...]


# ---------- conversiones de texto a tipos ----------
def _entero(valor: str, campo: str) -> int:
    try:
        return int(valor.strip())
    except ValueError:
        raise ValueError(f"{campo} debe ser un entero, recibido: {valor!r}") from None


def _decimal(valor: str, campo: str) -> float:
    try:
        return float(valor.strip())
    except ValueError:
        raise ValueError(f"{campo} debe ser un número, recibido: {valor!r}") from None


def _fecha(valor: str, campo: str) -> date:
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        raise ValueError(f"{campo} debe tener formato AAAA-MM-DD, recibido: {valor!r}") from None


# ---------- fábricas: una fila (dict) -> un objeto ----------
def _cliente(fila: dict[str, str]) -> Cliente:
    telefono = fila["telefono"].strip()
    if telefono and not telefono.isdigit():
        raise ValueError(f"telefono debe tener solo dígitos, recibido: {telefono!r}")
    return ClienteRegular(fila["id_cliente"].strip(), fila["nombre"].strip(), telefono)


def _producto(fila: dict[str, str]) -> Producto:
    costo = (fila.get("costo") or "").strip()  # columnas opcionales
    stock = (fila.get("stock") or "").strip()
    return Producto(
        fila["id_producto"].strip(),
        fila["nombre"].strip(),
        fila["categoria"].strip(),
        _decimal(fila["precio"], "precio"),
        costo=_decimal(costo, "costo") if costo else None,
        stock=_entero(stock, "stock") if stock else None,
    )


def _venta(fila: dict[str, str]) -> Venta:
    return Venta(
        fila["id_venta"].strip(),
        fila["id_cliente"].strip(),
        fila["id_producto"].strip(),
        _entero(fila["cantidad"], "cantidad"),
        _decimal(fila["precio_unitario"], "precio_unitario"),
        _fecha(fila["fecha"], "fecha"),
    )


# ---------- lectura genérica ----------
def _leer(ruta: Path, columnas: tuple[str, ...], fabrica: Callable, campo_id: str) -> tuple:
    if not ruta.is_file():
        raise ErrorDatos(f"No se encontró el archivo: {ruta}")
    objetos = []
    ids_vistos: set[str] = set()
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        faltantes = [c for c in columnas if c not in (lector.fieldnames or [])]
        if faltantes:
            raise ErrorDatos(f"{ruta.name}: faltan las columnas {faltantes}")
        for numero, fila in enumerate(lector, start=2):
            try:
                objeto = fabrica(fila)
            except (ValueError, TypeError, AttributeError) as error:
                raise ErrorDatos(f"{ruta.name}, fila {numero}: {error}") from error
            identificador = getattr(objeto, campo_id)
            if identificador in ids_vistos:
                raise ErrorDatos(f"{ruta.name}, fila {numero}: {campo_id} duplicado: {identificador!r}")
            ids_vistos.add(identificador)
            objetos.append(objeto)
    return tuple(objetos)


def cargar_clientes(ruta: str | Path) -> tuple[Cliente, ...]:
    return _leer(
        Path(ruta), ("id_cliente", "nombre", "telefono"), _cliente, "id_cliente"
    )


def cargar_productos(ruta: str | Path) -> tuple[Producto, ...]:
    return _leer(
        Path(ruta), ("id_producto", "nombre", "categoria", "precio"), _producto, "id_producto"
    )


def cargar_ventas(ruta: str | Path) -> tuple[Venta, ...]:
    columnas = ("id_venta", "id_cliente", "id_producto", "cantidad", "precio_unitario", "fecha")
    return _leer(Path(ruta), columnas, _venta, "id_venta")


def validar_integridad(
    clientes: tuple[Cliente, ...],
    productos: tuple[Producto, ...],
    ventas: tuple[Venta, ...],
) -> None:
    """Toda venta debe referirse a un cliente y a un producto existentes."""
    ids_clientes = {c.id_cliente for c in clientes}
    ids_productos = {p.id_producto for p in productos}
    for venta in ventas:
        if venta.id_cliente not in ids_clientes:
            raise ErrorDatos(f"Venta {venta.id_venta}: cliente inexistente {venta.id_cliente!r}")
        if venta.id_producto not in ids_productos:
            raise ErrorDatos(f"Venta {venta.id_venta}: producto inexistente {venta.id_producto!r}")


def cargar_todo(directorio: str | Path = "datos") -> Datos:
    base = Path(directorio)
    clientes = cargar_clientes(base / "clientes.csv")
    productos = cargar_productos(base / "productos.csv")
    ventas = cargar_ventas(base / "ventas.csv")
    validar_integridad(clientes, productos, ventas)
    return Datos(clientes, productos, ventas)
