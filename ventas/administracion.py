"""Casos de uso de la administración: altas, ediciones y bajas.

Cada función recibe el repositorio, valida lo que escribió la persona (texto
libre de un formulario), crea objetos del dominio —que se validan solos— y los
guarda. Si algo está mal lanza ValueError o ErrorDatos con un mensaje en español
que la interfaz muestra tal cual.
"""

import re
import unicodedata
from datetime import date
from pathlib import Path

from ventas.cargador import ErrorDatos, cargar_todo
from ventas.mensajes import validar_telefono
from ventas.modelos import Cliente, ClienteRegular, Producto, Venta
from ventas.ofertas import Oferta
from ventas.repositorio import Repositorio


# ---------------------------------------------------------------------
# Normalización de lo que escribe la persona (funciones puras)
# ---------------------------------------------------------------------
def limpiar_nombre(texto: str, campo: str = "nombre") -> str:
    """Quita espacios sobrantes: '  Juan   Pérez ' -> 'Juan Pérez'."""
    nombre = " ".join(str(texto).split())
    if not nombre:
        raise ValueError(f"El {campo} no puede estar vacío.")
    return nombre


def normalizar_telefono(texto: str, codigo_pais: str = "51") -> str:
    """'+51 900-000-001' -> '51900000001'. Un celular de 9 dígitos que empieza
    con 9 recibe el código de país. Vacío significa 'sin teléfono'."""
    limpio = re.sub(r"[\s\-().]", "", str(texto).strip())
    limpio = limpio.removeprefix("+")
    if not limpio:
        return ""
    if re.fullmatch(r"9\d{8}", limpio):
        limpio = codigo_pais + limpio
    return validar_telefono(limpio)


def normalizar_categoria(texto: str) -> str:
    """'Periféricos' -> 'perifericos'. Las categorías se usan como átomos de Prolog:
    minúsculas, sin tildes ni espacios."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    categoria = re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")
    if not categoria:
        raise ValueError("La categoría no puede estar vacía.")
    return f"cat_{categoria}" if categoria[0].isdigit() else categoria


def _buscar(items, atributo: str, valor: str, nombre: str):
    for item in items:
        if getattr(item, atributo) == valor:
            return item
    raise ErrorDatos(f"No existe el {nombre} {valor}.")


# ---------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------
def crear_cliente(repo: Repositorio, nombre: str, telefono: str = "") -> Cliente:
    cliente = ClienteRegular(repo.siguiente_id("c"), limpiar_nombre(nombre), normalizar_telefono(telefono))
    repo.agregar_cliente(cliente)
    return cliente


def editar_cliente(repo: Repositorio, id_cliente: str, nombre: str, telefono: str = "") -> Cliente:
    _buscar(repo.cargar_todo().clientes, "id_cliente", id_cliente, "cliente")
    cliente = ClienteRegular(id_cliente, limpiar_nombre(nombre), normalizar_telefono(telefono))
    repo.actualizar_cliente(cliente)
    return cliente


def eliminar_cliente(repo: Repositorio, id_cliente: str) -> None:
    repo.eliminar_cliente(id_cliente)


# ---------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------
def crear_producto(repo: Repositorio, nombre: str, categoria: str, precio: float) -> Producto:
    producto = Producto(
        repo.siguiente_id("p"), limpiar_nombre(nombre), normalizar_categoria(categoria), round(float(precio), 2)
    )
    repo.agregar_producto(producto)
    return producto


def editar_producto(repo: Repositorio, id_producto: str, nombre: str, categoria: str, precio: float) -> Producto:
    _buscar(repo.cargar_todo().productos, "id_producto", id_producto, "producto")
    producto = Producto(id_producto, limpiar_nombre(nombre), normalizar_categoria(categoria), round(float(precio), 2))
    repo.actualizar_producto(producto)
    return producto


def eliminar_producto(repo: Repositorio, id_producto: str) -> None:
    repo.eliminar_producto(id_producto)


# ---------------------------------------------------------------------
# Ventas
# ---------------------------------------------------------------------
def registrar_venta(
    repo: Repositorio,
    id_cliente: str,
    id_producto: str,
    cantidad: int,
    fecha: date,
    precio_unitario: float | None = None,
) -> Venta:
    """Registra una venta. Si no se indica precio, se usa el actual del producto
    (que queda guardado: cambiarlo después no altera esta venta)."""
    datos = repo.cargar_todo()
    _buscar(datos.clientes, "id_cliente", id_cliente, "cliente")
    producto = _buscar(datos.productos, "id_producto", id_producto, "producto")
    precio = producto.precio if precio_unitario is None else round(float(precio_unitario), 2)
    venta = Venta(repo.siguiente_id("v"), id_cliente, id_producto, cantidad, precio, fecha)
    repo.agregar_venta(venta)
    return venta


def anular_venta(repo: Repositorio, id_venta: str) -> None:
    repo.eliminar_venta(id_venta)


# ---------------------------------------------------------------------
# Datos de ejemplo
# ---------------------------------------------------------------------
def poner_oferta(repo: Repositorio, id_producto: str, porcentaje: int, desde: date, hasta: date) -> Oferta:
    """Pone (o cambia) la oferta de un producto del catálogo."""
    _buscar(repo.cargar_todo().productos, "id_producto", id_producto, "producto")
    if isinstance(porcentaje, float) and porcentaje.is_integer():
        porcentaje = int(porcentaje)  # st.number_input puede devolver 15.0
    oferta = Oferta(id_producto, porcentaje, desde, hasta)
    repo.guardar_oferta(oferta)
    return oferta


def quitar_oferta(repo: Repositorio, id_producto: str) -> None:
    repo.eliminar_oferta(id_producto)


def sembrar(repo: Repositorio, directorio: str | Path) -> None:
    """Reemplaza todo por los datos de ejemplo (CSV). Todo o nada."""
    repo.reemplazar_todo(cargar_todo(directorio))


def asegurar_datos(repo: Repositorio, directorio: str | Path) -> bool:
    """Si la base está vacía carga los datos de ejemplo. Devuelve True si los cargó."""
    if not repo.esta_vacio():
        return False
    sembrar(repo, directorio)
    return True
