"""Asesor comercial: interfaz web con Streamlit.

Ejecutar desde la carpeta del proyecto:  streamlit run app.py

La interfaz solo presenta datos: toda la lógica vive en ventas/servicio.py y en
los módulos de cada paradigma.
"""

import threading
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Asesor comercial", layout="wide")

try:
    from ventas.cargador import ErrorDatos, cargar_todo
    from ventas.funcional import UMBRAL_FRECUENTE
    from ventas.logico import DIAS_INACTIVIDAD, PuenteProlog
    from ventas.mensajes import dinero
    from ventas.modelos import ClienteFrecuente
    from ventas.pedido import armar_pedido_manual
    from ventas.servicio import (
        TarjetaAgenda,
        clientes_con_perfil,
        construir_tarjetas,
        resumen_ventas,
    )
except Exception as error:  # p. ej. SWI-Prolog no instalado: pyswip falla al importarse
    st.error(
        "No se pudo iniciar el motor lógico. Verifica que SWI-Prolog esté instalado "
        "(https://www.swi-prolog.org) con la misma arquitectura que Python, y que ejecutaste "
        "`streamlit run app.py` desde la carpeta del proyecto."
    )
    st.caption(f"Detalle técnico: {type(error).__name__}: {error}")
    st.stop()

DATOS = Path(__file__).resolve().parent / "datos"
FECHA_DEMO = date(2026, 10, 5)  # fecha fija para que la demostración sea reproducible
PAGINAS = ("Agenda de hoy", "Arma mi pedido", "Clientes", "Resumen")

NOMBRES_CATEGORIA = {
    "computo": "Cómputo",
    "perifericos": "Periféricos",
    "monitores": "Monitores",
    "audio": "Audio",
    "accesorios": "Accesorios",
    "almacenamiento": "Almacenamiento",
    "mobiliario": "Mobiliario",
}


def nombre_categoria(categoria: str) -> str:
    return NOMBRES_CATEGORIA.get(categoria, categoria.replace("_", " ").capitalize())


# ---------------------------------------------------------------------
# Recursos compartidos
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def cargar_datos():
    return cargar_todo(DATOS)


@st.cache_resource
def recursos():
    """Un único motor Prolog por proceso, protegido con un candado: SWI-Prolog
    comparte sus hechos entre sesiones y cada cálculo los recarga."""
    return PuenteProlog(), threading.Lock()


def fecha_valida(datos, hoy: date) -> bool:
    """La fecha de referencia no puede ser anterior a la última venta."""
    ultima = max((v.fecha for v in datos.ventas), default=None)
    if ultima is not None and hoy < ultima:
        st.error(
            f"La fecha de referencia ({hoy:%d/%m/%Y}) es anterior a la última venta registrada "
            f"({ultima:%d/%m/%Y}). Elige esa fecha o una posterior."
        )
        return False
    return True


# ---------------------------------------------------------------------
# Página: agenda
# ---------------------------------------------------------------------
def pagina_agenda(datos, hoy: date) -> None:
    st.header("Agenda de hoy")
    if not fecha_valida(datos, hoy):
        return
    motor, candado = recursos()
    with candado:
        tarjetas = construir_tarjetas(datos, hoy, motor)
    if not tarjetas:
        st.info("No hay clientes para contactar con los datos y la fecha elegidos.")
        return
    st.caption(
        f"{len(tarjetas)} contactos, ordenados por urgencia y, a igual urgencia, por gasto total. "
        "Prolog deduce la acción y el motivo (agenda.pl)."
    )
    for posicion, tarjeta in enumerate(tarjetas, start=1):
        mostrar_tarjeta(posicion, tarjeta)


def mostrar_tarjeta(posicion: int, t: TarjetaAgenda) -> None:
    accion, perfil = t.entrada.accion, t.entrada.perfil
    tipo_cliente = "frecuente" if isinstance(t.cliente, ClienteFrecuente) else "regular"
    with st.container(border=True):
        izquierda, derecha = st.columns([4, 1])
        izquierda.subheader(f"{posicion}. {t.cliente.nombre} · {accion.titulo()}")
        derecha.markdown(f"**Prioridad {accion.prioridad}**")
        st.write(t.entrada.motivo)
        st.caption(
            f"Cliente {tipo_cliente} · ticket promedio {dinero(perfil.ticket_promedio)} · "
            f"gasto total {dinero(perfil.total_gastado)}"
        )
        with st.expander("¿Por qué?"):
            mostrar_por_que(t)
        titulo_pedido = (
            f"Pedido sugerido · {dinero(t.pedidos[0].total_con_descuento)}" if t.pedidos else "Pedido sugerido"
        )
        with st.expander(titulo_pedido):
            mostrar_pedidos(t)
        with st.expander("Mensaje para WhatsApp"):
            st.write(t.mensaje.texto)
        if t.mensaje.enlace:
            st.link_button("Abrir en WhatsApp", t.mensaje.enlace)
        else:
            st.caption("Este cliente no tiene teléfono registrado.")


def mostrar_por_que(t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    st.markdown("**Reglas de Prolog que se aplicaron:** " + ", ".join(f"`{m}`" for m in accion.motivos))
    st.caption(
        f"Umbrales: cliente frecuente desde {UMBRAL_FRECUENTE} compras; "
        f"inactivo si pasan más de {DIAS_INACTIVIDAD} días sin comprar."
    )
    if not t.recomendaciones:
        st.info("Por ahora no hay productos que recomendar a este cliente.")
        return
    st.markdown("**Productos recomendados**")
    nombres = {p.id_producto: p.nombre for p in cargar_datos().productos}
    filas = [
        {
            "Producto": nombres[r.id_producto],
            "Confianza": f"{r.confianza:.0%}",
            "Lo llevaron": f"{r.soporte} de {t.clientes_similares} clientes con compras parecidas",
        }
        for r in t.recomendaciones[:5]
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True)


def tabla_de_productos(productos) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Producto": p.nombre, "Categoría": nombre_categoria(p.categoria), "Precio": dinero(p.precio)} for p in productos]
    )


def mostrar_pedidos(t: TarjetaAgenda) -> None:
    if not t.pedidos:
        st.info("Ningún pedido con los productos recomendados cabe en el presupuesto habitual de este cliente.")
        return
    for numero, sugerido in enumerate(t.pedidos, start=1):
        if len(t.pedidos) > 1:
            st.markdown(f"**Opción {numero}**")
        st.dataframe(tabla_de_productos(sugerido.pedido.productos), hide_index=True)
        st.caption(
            f"Subtotal {dinero(sugerido.pedido.subtotal)} · total con descuento "
            f"{dinero(sugerido.total_con_descuento)} · presupuesto {dinero(sugerido.presupuesto)} "
            f"(ticket promedio + 10 %)"
        )


# ---------------------------------------------------------------------
# Página: arma mi pedido (modo mostrador)
# ---------------------------------------------------------------------
def pagina_pedido(datos) -> None:
    st.header("Arma mi pedido")
    st.caption("Indica el presupuesto y las categorías: Prolog recorre por backtracking todas las combinaciones posibles.")
    categorias = sorted({p.categoria for p in datos.productos})
    presupuesto = st.number_input("Presupuesto (S/)", min_value=1.0, value=200.0, step=10.0)
    elegidas = st.multiselect(
        "Categorías",
        categorias,
        default=[c for c in ("perifericos", "accesorios") if c in categorias],
        format_func=nombre_categoria,
    )
    if not elegidas:
        st.info("Elige al menos una categoría.")
        return
    motor, candado = recursos()
    with candado:
        pedidos = armar_pedido_manual(motor, datos.productos, presupuesto, elegidas, n=5)
    if not pedidos:
        st.warning("Ninguna combinación cabe en ese presupuesto. Prueba con más dinero o menos categorías.")
        return
    st.subheader(f"{len(pedidos)} combinaciones, de la que más aprovecha el presupuesto a la que menos")
    for numero, pedido in enumerate(pedidos, start=1):
        with st.container(border=True):
            st.markdown(f"**Opción {numero} · {dinero(pedido.subtotal)}** · sobran {dinero(presupuesto - pedido.subtotal)}")
            st.dataframe(tabla_de_productos(pedido.productos), hide_index=True)


# ---------------------------------------------------------------------
# Página: clientes
# ---------------------------------------------------------------------
def pagina_clientes(datos, hoy: date) -> None:
    st.header("Clientes")
    if not fecha_valida(datos, hoy):
        return
    filas = []
    for cliente, perfil in clientes_con_perfil(datos, hoy):
        filas.append(
            {
                "Cliente": cliente.nombre,
                "Tipo": "Frecuente" if isinstance(cliente, ClienteFrecuente) else "Regular",
                "Compras": perfil.n_compras,
                "Días sin comprar": perfil.dias_sin_comprar,
                "Total gastado (S/)": perfil.total_gastado,
                "Ticket promedio (S/)": perfil.ticket_promedio,
                "Categorías habituales": ", ".join(nombre_categoria(c) for c in perfil.categorias_habituales[:3]),
            }
        )
    st.dataframe(pd.DataFrame(filas), hide_index=True)
    st.caption("Calculado con funciones puras (funcional.py). Una compra es un día distinto en que el cliente adquirió algo.")


# ---------------------------------------------------------------------
# Página: resumen
# ---------------------------------------------------------------------
def pagina_resumen(datos) -> None:
    st.header("Resumen de ventas")
    r = resumen_ventas(datos)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas totales", dinero(r.total))
    c2.metric("Promedio por línea", dinero(r.promedio_por_linea))
    c3.metric("Líneas de venta", r.n_ventas)
    c4.metric("Clientes", r.n_clientes)
    if not r.n_ventas:
        st.info("Aún no hay ventas registradas.")
        return
    st.subheader("Ventas por mes")
    st.bar_chart(pd.DataFrame(r.por_mes, columns=["Mes", "Ventas (S/)"]).set_index("Mes"))
    st.subheader("Ventas por categoría")
    por_categoria = [(nombre_categoria(c), monto) for c, monto in r.por_categoria]
    st.bar_chart(pd.DataFrame(por_categoria, columns=["Categoría", "Ventas (S/)"]).set_index("Categoría"))
    st.subheader("Productos más vendidos")
    st.dataframe(pd.DataFrame(r.top_productos, columns=["Producto", "Unidades"]), hide_index=True)
    st.caption("Calculado con funciones puras y reduce (funcional.py).")


# ---------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------
def main() -> None:
    try:
        datos = cargar_datos()
    except ErrorDatos as error:
        st.error(f"No se pudieron cargar los datos: {error}")
        st.info("Revisa los archivos clientes.csv, productos.csv y ventas.csv de la carpeta datos/.")
        st.stop()

    st.sidebar.title("Asesor comercial")
    pagina = st.sidebar.radio("Navegación", PAGINAS)
    hoy = st.sidebar.date_input(
        "Fecha de referencia",
        value=FECHA_DEMO,
        help="Los días sin comprar se cuentan hasta esta fecha. Se fija para que la demostración sea reproducible.",
    )
    st.sidebar.caption("Orientado a objetos · funcional · lógico (Prolog)")

    if pagina == "Agenda de hoy":
        pagina_agenda(datos, hoy)
    elif pagina == "Arma mi pedido":
        pagina_pedido(datos)
    elif pagina == "Clientes":
        pagina_clientes(datos, hoy)
    else:
        pagina_resumen(datos)


main()
