"""Recursos y utilidades compartidas por todas las páginas."""

import os
import threading
from datetime import date
from pathlib import Path

import streamlit as st

from ventas.administracion import asegurar_datos
from ventas.cargador import Datos
from ventas.combos import Combo
from ventas.contactos import Contacto
from ventas.logico import PuenteProlog
from ventas.mensajes import dinero
from ventas.ofertas import Oferta
from ventas.repositorio import RepositorioSQLite

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_CSV = RAIZ / "datos"
def fecha_inicial() -> date:
    """Hoy. Con ASESOR_FECHA=AAAA-MM-DD se fija otra fecha (demostraciones y pruebas)."""
    try:
        return date.fromisoformat(os.environ["ASESOR_FECHA"])
    except (KeyError, ValueError):
        return date.today()

NOMBRES_CATEGORIA = {
    "computo": "Cómputo",
    "perifericos": "Periféricos",
    "monitores": "Monitores",
    "audio": "Audio",
    "accesorios": "Accesorios",
    "almacenamiento": "Almacenamiento",
    "mobiliario": "Mobiliario",
    "graficas": "Tarjetas gráficas",
    "memorias": "Memorias USB y microSD",
    "memoria_ram": "Memoria RAM",
}


def texto_stock(producto) -> str:
    """«Sin control», «Agotado» o las unidades que quedan."""
    if producto.stock is None:
        return "Sin control"
    return "Agotado" if producto.stock == 0 else str(producto.stock)


def nombre_categoria(categoria: str) -> str:
    return NOMBRES_CATEGORIA.get(categoria, categoria.replace("_", " ").capitalize())


# ---------------------------------------------------------------------
# Recursos que viven mientras corre la aplicación
# ---------------------------------------------------------------------
def ruta_base_de_datos() -> str:
    """Archivo SQLite de la aplicación. Se puede cambiar con ASESOR_DB (las pruebas usan ':memory:')."""
    return os.environ.get("ASESOR_DB", str(CARPETA_CSV / "asesor.db"))


@st.cache_resource
def repositorio() -> RepositorioSQLite:
    """La base de datos; la primera vez se llena con los datos de ejemplo."""
    repo = RepositorioSQLite(ruta_base_de_datos())
    asegurar_datos(repo, CARPETA_CSV)
    return repo


@st.cache_resource
def motor_y_candado() -> tuple[PuenteProlog, threading.Lock]:
    """Un único motor Prolog por proceso, protegido con un candado: SWI-Prolog
    comparte sus hechos entre sesiones y cada cálculo los recarga."""
    return PuenteProlog(), threading.Lock()


def datos() -> Datos:
    """Lo último que hay en la base (se lee en cada ejecución: es pequeño y siempre está al día)."""
    return repositorio().cargar_todo()


def contactos() -> tuple[Contacto, ...]:
    """Los contactos registrados desde la agenda."""
    return repositorio().cargar_contactos()


def combos() -> tuple[Combo, ...]:
    """Las combinaciones guardadas desde «Arma mi pedido» (pendientes o registradas)."""
    return repositorio().cargar_combos()


def html_cotizacion(cotizacion, titulo: str = "") -> str:
    """Las líneas del pedido y su total, con la única regla de precio:
    ofertas (o precios acordados) y el descuento del pedido."""
    from interfaz import estilo  # estilo no depende de comun

    def nota(linea) -> str:
        if linea.oferta:
            return (
                f"Oferta -{linea.oferta.porcentaje} % hasta el {linea.oferta.hasta:%d/%m/%Y} · "
                f"antes {dinero(linea.producto.precio)}"
            )
        if linea.precio_fijo is not None and linea.en_oferta:
            return f"Precio acordado · antes {dinero(linea.producto.precio)}"
        return nombre_categoria(linea.producto.categoria)

    filas = "".join(
        estilo.fila_producto(linea.producto.nombre, linea.producto.categoria, dinero(linea.precio), nota(linea))
        for linea in cotizacion.lineas
    )
    normal = round(sum(linea.producto.precio for linea in cotizacion.lineas), 2)
    if cotizacion.descuento:
        cierre = estilo.total(
            "Total", dinero(cotizacion.total), tachado=dinero(cotizacion.subtotal), nota=f"{cotizacion.descuento} % de descuento"
        )
    elif cotizacion.total < normal:
        cierre = estilo.total(
            "Total", dinero(cotizacion.total), tachado=dinero(normal), nota=f"Ahorras {dinero(normal - cotizacion.total)} con las ofertas"
        )
    else:
        cierre = estilo.total("Total", dinero(cotizacion.total))
    cabecera = f'<div class="pedido-titulo">{titulo}</div>' if titulo else ""
    return cabecera + filas + cierre


def ofertas() -> tuple[Oferta, ...]:
    """Las ofertas registradas (vigentes o no)."""
    return repositorio().cargar_ofertas()


# ---------------------------------------------------------------------
# Fecha de referencia y mensajes entre ejecuciones
# ---------------------------------------------------------------------
def fecha_referencia() -> date:
    return st.session_state.get("fecha_referencia", fecha_inicial())


def fecha_valida(datos_: Datos, hoy: date) -> bool:
    """La fecha de referencia no puede ser anterior a la última venta."""
    ultima = max((v.fecha for v in datos_.ventas), default=None)
    if ultima is not None and hoy < ultima:
        st.error(
            f"La fecha de referencia ({hoy:%d/%m/%Y}) es anterior a la última venta registrada "
            f"({ultima:%d/%m/%Y}). Elige esa fecha o una posterior en el menú lateral.",
            icon=":material/event_busy:",
        )
        return False
    return True


def avisar(tipo: str, texto: str) -> None:
    """Guarda un aviso para mostrarlo después de recargar la página."""
    st.session_state["_aviso"] = (tipo, texto)


def mostrar_aviso() -> None:
    aviso = st.session_state.pop("_aviso", None)
    if aviso:
        tipo, texto = aviso
        {"exito": st.success, "error": st.error, "info": st.info}[tipo](texto, icon=None)


def version(nombre: str) -> int:
    """Número que cambia al guardar; se usa en las claves de los campos para limpiarlos."""
    return st.session_state.get(f"_v_{nombre}", 0)


def reiniciar(nombre: str) -> None:
    st.session_state[f"_v_{nombre}"] = version(nombre) + 1


def dinero_corto(monto: float) -> str:
    """Sin decimales, para indicadores grandes: 8455.0 -> 'S/ 8,455'."""
    return f"S/ {monto:,.0f}"


__all__ = ["dinero", "dinero_corto"]
