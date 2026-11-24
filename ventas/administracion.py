"""Casos de uso de la administración: altas, ediciones y bajas.

Cada función recibe el repositorio, valida lo que escribió la persona (texto
libre de un formulario), crea objetos del dominio —que se validan solos— y los
guarda. Si algo está mal lanza ValueError o ErrorDatos con un mensaje en español
que la interfaz muestra tal cual.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path

from ventas.cargador import ErrorDatos, cargar_todo
from ventas.combos import (
    ESTADOS,
    Combo,
    Cotizacion,
    congelar,
    cotizar,
    ventas_del_combo,
)
from ventas.contactos import Contacto, nuevo_contacto
from ventas.funcional import clasificar_cliente, perfil_cliente
from ventas.mensajes import validar_telefono
from ventas.modelos import Cliente, ClienteRegular, Producto, Venta
from ventas.ofertas import Oferta, ofertas_vigentes
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
_SIN_CAMBIO = object()  # editar_producto: conservar el valor actual


def _costo(valor) -> float | None:
    return None if valor is None else round(float(valor), 2)


def _stock(valor) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return valor


def crear_producto(
    repo: Repositorio, nombre: str, categoria: str, precio: float, costo: float | None = None, stock: int | None = None
) -> Producto:
    producto = Producto(
        repo.siguiente_id("p"),
        limpiar_nombre(nombre),
        normalizar_categoria(categoria),
        round(float(precio), 2),
        costo=_costo(costo),
        stock=_stock(stock),
    )
    repo.agregar_producto(producto)
    return producto


def editar_producto(
    repo: Repositorio,
    id_producto: str,
    nombre: str,
    categoria: str,
    precio: float,
    costo=_SIN_CAMBIO,
    stock=_SIN_CAMBIO,
) -> Producto:
    """Sin `costo` o `stock`, se conservan los actuales; None deja de cargarlos."""
    actual = _buscar(repo.cargar_todo().productos, "id_producto", id_producto, "producto")
    producto = Producto(
        id_producto,
        limpiar_nombre(nombre),
        normalizar_categoria(categoria),
        round(float(precio), 2),
        costo=actual.costo if costo is _SIN_CAMBIO else _costo(costo),
        stock=actual.stock if stock is _SIN_CAMBIO else _stock(stock),
    )
    repo.actualizar_producto(producto)
    return producto


def revisar_stock(productos: Iterable[Producto], pedido: Mapping[str, int]) -> None:
    """Falla con un mensaje claro si algún producto no alcanza (los que no
    controlan stock siempre alcanzan). La base de datos igual lo garantiza."""
    for p in productos:
        if p.id_producto in pedido and p.stock is not None and pedido[p.id_producto] > p.stock:
            queda = "queda 1" if p.stock == 1 else f"quedan {p.stock}"
            raise ValueError(f"No hay stock suficiente de {p.nombre}: {queda}.")


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
    revisar_stock([producto], {id_producto: cantidad})
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


# ---------------------------------------------------------------------
# Contactos de la agenda
# ---------------------------------------------------------------------
def registrar_contacto(repo: Repositorio, id_cliente: str, resultado: str, hoy: date, dias: int | None = None) -> Contacto:
    """Anota que se contactó al cliente hoy y cuándo volver a mostrarlo en la agenda."""
    _buscar(repo.cargar_todo().clientes, "id_cliente", id_cliente, "cliente")
    if isinstance(dias, float) and dias.is_integer():
        dias = int(dias)
    contacto = nuevo_contacto(id_cliente, hoy, resultado, dias)
    repo.agregar_contacto(contacto)
    return contacto


# ---------------------------------------------------------------------
# Combos de «Arma mi pedido» que pasan a ventas
# ---------------------------------------------------------------------
def guardar_combo(
    repo: Repositorio,
    id_cliente: str | None,
    ids_productos: list[str],
    hoy: date,
    nombre_cliente: str = "",
    descuento: int | None = None,
) -> Combo:
    """Guarda un pedido en borrador con un id nuevo (cb001, cb002...), para un
    cliente registrado (id_cliente) o uno no registrado (solo su nombre). Sin
    descuento, le corresponde el del cliente."""
    datos = repo.cargar_todo()
    if id_cliente is None:
        nombre_cliente = limpiar_nombre(nombre_cliente, "nombre del cliente")
    else:
        _buscar(datos.clientes, "id_cliente", id_cliente, "cliente")
        nombre_cliente = ""
    for id_producto in ids_productos:
        _buscar(datos.productos, "id_producto", id_producto, "producto")
    combo = Combo(
        repo.siguiente_id("cb"),
        id_cliente,
        tuple(ids_productos),
        hoy,
        nombre_cliente=nombre_cliente,
        descuento=_entero_o_none(descuento),
    )
    repo.agregar_combo(combo)
    return combo


def _entero_o_none(valor):
    return int(valor) if isinstance(valor, float) and valor.is_integer() else valor


def _combo(repo: Repositorio, id_combo: str) -> Combo:
    return _buscar(repo.cargar_combos(), "id_combo", id_combo, "combo")


def _abierto(combo: Combo) -> Combo:
    if not combo.pendiente:
        raise ValueError(f"El pedido {combo.id_combo} ya está {ESTADOS[combo.estado].lower()}.")
    return combo


def cliente_clasificado(datos, id_cliente: str | None, fecha: date) -> Cliente | None:
    """El cliente como regular o frecuente a esa fecha (None si no está registrado)."""
    if id_cliente is None:
        return None
    cliente = _buscar(datos.clientes, "id_cliente", id_cliente, "cliente")
    return clasificar_cliente(cliente, perfil_cliente(id_cliente, datos.ventas, datos.productos, fecha))


def cotizar_combo(repo: Repositorio, id_combo: str, fecha: date) -> Cotizacion:
    """Lo que sale el pedido a esa fecha, con la única regla de precio."""
    combo = _combo(repo, id_combo)
    datos = repo.cargar_todo()
    vigentes = ofertas_vigentes(repo.cargar_ofertas(), fecha)
    return cotizar(combo, datos.productos, vigentes, cliente_clasificado(datos, combo.id_cliente, fecha))


def cambiar_descuento(repo: Repositorio, id_combo: str, descuento: int | None) -> Combo:
    """El descuento del borrador: un % del vendedor, o None para el del cliente."""
    combo = replace(_abierto(_combo(repo, id_combo)), descuento=_entero_o_none(descuento))
    if combo.estado != "borrador":
        raise ValueError(f"El pedido {id_combo} ya está enviado: su precio quedó fijo.")
    repo.actualizar_combo(combo)
    return combo


def enviar_combo(repo: Repositorio, id_combo: str, fecha: date) -> Combo:
    """Marca el pedido como enviado: precios y descuento quedan fijos (se cobrará
    lo prometido aunque venza una oferta). Si el cliente está registrado, se
    anota en la agenda que se le envió una propuesta."""
    combo = _abierto(_combo(repo, id_combo))
    if combo.estado == "enviado":
        raise ValueError(f"El pedido {id_combo} ya está enviado.")
    cotizacion = cotizar_combo(repo, id_combo, fecha)
    enviado = congelar(combo, cotizacion.lineas, cotizacion.descuento)
    repo.actualizar_combo(enviado)
    if enviado.registrado:
        registrar_contacto(repo, enviado.id_cliente, "propuesta_enviada", fecha)
    return enviado


def registrar_combo(repo: Repositorio, id_combo: str, fecha: date) -> tuple[Venta, ...]:
    """Registra el pedido como ventas (una por producto) con la única regla de
    precio: lo acordado si se envió; si no, las ofertas de `fecha` y el descuento
    del pedido. Si el cliente no estaba registrado, se registra con su nombre en
    la misma operación."""
    combo = _combo(repo, id_combo)
    cotizacion = cotizar_combo(repo, id_combo, fecha)
    nuevo = None if combo.registrado else ClienteRegular(repo.siguiente_id("c"), combo.nombre_cliente)
    primero = int(repo.siguiente_id("v")[1:])
    ids_ventas = [f"v{primero + i:03d}" for i in range(len(cotizacion.lineas))]
    ventas = ventas_del_combo(
        combo, cotizacion.lineas, ids_ventas, fecha, nuevo.id_cliente if nuevo else None, cotizacion.descuento
    )
    revisar_stock((linea.producto for linea in cotizacion.lineas), {v.id_producto: v.cantidad for v in ventas})
    repo.registrar_combo(id_combo, ventas, nuevo)
    return ventas


def descartar_combo(repo: Repositorio, id_combo: str) -> Combo:
    """Descarta un pedido abierto (queda en el historial; uno vendido se anula desde sus ventas)."""
    combo = replace(_abierto(_combo(repo, id_combo)), descartado=True)
    repo.actualizar_combo(combo)
    return combo


def sembrar(repo: Repositorio, directorio: str | Path) -> None:
    """Reemplaza todo por los datos de ejemplo (CSV). Todo o nada."""
    repo.reemplazar_todo(cargar_todo(directorio))


def asegurar_datos(repo: Repositorio, directorio: str | Path) -> bool:
    """Si la base está vacía carga los datos de ejemplo. Devuelve True si los cargó."""
    if not repo.esta_vacio():
        return False
    sembrar(repo, directorio)
    return True
