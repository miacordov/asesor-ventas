"""Sección de asesoría: la agenda del día y el modo mostrador."""

import pandas as pd
import streamlit as st

from interfaz import comun
from interfaz.comun import dinero, nombre_categoria
from ventas.funcional import UMBRAL_FRECUENTE
from ventas.logico import DIAS_INACTIVIDAD
from ventas.modelos import ClienteFrecuente
from ventas.pedido import armar_pedido_manual
from ventas.servicio import TarjetaAgenda, construir_tarjetas

COLOR_PRIORIDAD = {"alta": "red", "media": "orange", "baja": "blue"}
ICONO_ACCION = {
    "reactivar": ":material/replay:",
    "fidelizar": ":material/favorite:",
    "cruzar": ":material/add_shopping_cart:",
}
FILTROS = {"Todos": None, "Reactivar": "reactivar", "Fidelizar": "fidelizar", "Complementar": "cruzar"}


def lista_markdown(productos) -> str:
    return "\n".join(f"- {p.nombre} · **{dinero(p.precio)}**" for p in productos)


# ---------------------------------------------------------------------
# Agenda de hoy
# ---------------------------------------------------------------------
def pagina_agenda() -> None:
    comun.mostrar_aviso()
    st.title(":material/event_note: Agenda de hoy")
    datos, hoy = comun.datos(), comun.fecha_referencia()
    if not comun.fecha_valida(datos, hoy):
        return
    motor, candado = comun.motor_y_candado()
    with candado:
        tarjetas = construir_tarjetas(datos, hoy, motor)
    if not tarjetas:
        st.info(
            "Todavía no hay clientes para contactar. Registra ventas en Administración › Ventas "
            "y la agenda se armará sola.",
            icon=":material/info:",
        )
        return

    resumen_superior(tarjetas)
    st.caption(
        "Ordenada por urgencia y, a igual urgencia, por gasto total. "
        "Prolog deduce la acción y el motivo; nada se envía solo."
    )
    filtro = st.segmented_control(
        "Mostrar", list(FILTROS), default="Todos", key="filtro_agenda", label_visibility="collapsed"
    )
    tipo = FILTROS[filtro or "Todos"]
    visibles = [(i, t) for i, t in enumerate(tarjetas, start=1) if tipo is None or t.entrada.accion.tipo == tipo]
    for inicio in range(0, len(visibles), 2):
        columnas = st.columns(2)
        for columna, (posicion, tarjeta_) in zip(columnas, visibles[inicio : inicio + 2], strict=False):
            with columna:
                tarjeta(posicion, tarjeta_)


def resumen_superior(tarjetas: tuple[TarjetaAgenda, ...]) -> None:
    def cuantos(tipo: str) -> int:
        return sum(t.entrada.accion.tipo == tipo for t in tarjetas)

    potencial = sum(t.pedidos[0].total_con_descuento for t in tarjetas if t.pedidos)
    c = st.columns([1, 1, 1, 1, 1.5])
    c[0].metric("Contactos de hoy", len(tarjetas), border=True)
    c[1].metric("Por reactivar", cuantos("reactivar"), border=True, help="Compraban seguido y dejaron de venir.")
    c[2].metric("Por fidelizar", cuantos("fidelizar"), border=True, help="Clientes frecuentes y activos.")
    c[3].metric("Complementar", cuantos("cruzar"), border=True, help="Compran poco: se les ofrece lo que llevan otros.")
    c[4].metric(
        "Valor en pedidos sugeridos",
        dinero(potencial),
        border=True,
        help="Suma del mejor pedido de cada cliente, con su descuento.",
    )


def tarjeta(posicion: int, t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    frecuente = isinstance(t.cliente, ClienteFrecuente)
    color = COLOR_PRIORIDAD[accion.prioridad]
    with st.container(border=True):
        st.markdown(f"#### {posicion}. {t.cliente.nombre}")
        st.markdown(
            f":{color}-badge[{ICONO_ACCION[accion.tipo]} {accion.titulo()}] "
            f":gray-badge[Prioridad {accion.prioridad}] "
            f":gray-badge[{'Cliente frecuente' if frecuente else 'Cliente regular'}]"
        )
        st.write(t.entrada.motivo)
        mostrar_pedido_resumido(t)
        boton_whatsapp, por_que, mensaje = st.columns([1.35, 1, 1])
        if t.mensaje.enlace:
            boton_whatsapp.link_button(
                "WhatsApp", t.mensaje.enlace, type="primary", icon=":material/chat:", width="stretch"
            )
        else:
            boton_whatsapp.button("Sin teléfono", disabled=True, width="stretch", key=f"sin_tel_{t.cliente.id_cliente}")
        with por_que.popover("¿Por qué?", width="stretch"):
            mostrar_por_que(t)
        with mensaje.popover("Mensaje", width="stretch"):
            st.write(t.mensaje.texto)
            if not t.mensaje.enlace:
                st.caption("Este cliente no tiene teléfono registrado; agrégalo en Administración › Clientes.")


def mostrar_pedido_resumido(t: TarjetaAgenda) -> None:
    if not t.pedidos:
        st.caption("No hay un pedido sugerido dentro del presupuesto habitual de este cliente.")
        return
    mejor = t.pedidos[0]
    st.markdown(f"**Pedido sugerido**\n\n{lista_markdown(mejor.pedido.productos)}")
    if mejor.total_con_descuento < mejor.pedido.subtotal:
        porcentaje = round(t.cliente.descuento() * 100)
        st.markdown(
            f"**Total {dinero(mejor.total_con_descuento)}** · ~~{dinero(mejor.pedido.subtotal)}~~ "
            f"con {porcentaje} % de descuento"
        )
    else:
        st.markdown(f"**Total {dinero(mejor.total_con_descuento)}**")
    if len(t.pedidos) > 1:
        st.caption(f"Hay {len(t.pedidos) - 1} opciones más de pedido para este cliente.")


def mostrar_por_que(t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    st.markdown("**Reglas de Prolog que se aplicaron**")
    st.markdown(" ".join(f":gray-badge[{m}]" for m in accion.motivos))
    st.caption(
        f"Frecuente: {UMBRAL_FRECUENTE} compras o más. "
        f"Inactivo: más de {DIAS_INACTIVIDAD} días sin comprar."
    )
    if not t.recomendaciones:
        st.info("Por ahora no hay productos que recomendar a este cliente.")
        return
    nombres = {p.id_producto: p.nombre for p in comun.datos().productos}
    st.markdown("**Productos recomendados**")
    filas = [
        {
            "Producto": nombres[r.id_producto],
            "Confianza": r.confianza * 100,
            "Lo llevaron": f"{r.soporte} de {t.clientes_similares}",
        }
        for r in t.recomendaciones[:5]
    ]
    st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        column_config={
            "Confianza": st.column_config.ProgressColumn("Confianza", format="%.0f %%", min_value=0, max_value=100),
            "Lo llevaron": st.column_config.TextColumn("Lo llevaron", help="Clientes con compras parecidas que lo compraron."),
        },
    )


# ---------------------------------------------------------------------
# Arma mi pedido (modo mostrador)
# ---------------------------------------------------------------------
def pagina_pedido() -> None:
    comun.mostrar_aviso()
    st.title(":material/shopping_cart: Arma mi pedido")
    st.caption("Modo mostrador: indica el presupuesto y las categorías, y Prolog recorre por backtracking todas las combinaciones posibles.")
    datos = comun.datos()
    categorias = sorted({p.categoria for p in datos.productos})
    if not categorias:
        st.info("No hay productos registrados. Agrégalos en Administración › Productos.", icon=":material/info:")
        return

    izquierda, derecha = st.columns([1, 2], gap="large")
    with izquierda:
        with st.container(border=True):
            presupuesto = st.number_input("Presupuesto (S/)", min_value=1.0, value=200.0, step=10.0, key="presupuesto_pedido")
            elegidas = st.pills(
                "Categorías",
                categorias,
                selection_mode="multi",
                default=[c for c in ("perifericos", "accesorios") if c in categorias],
                format_func=nombre_categoria,
                key="categorias_pedido",
            )
            st.caption("Se arma un producto por cada categoría elegida, sin repetir y sin pasarse del presupuesto.")
    with derecha:
        if not elegidas:
            st.info("Elige al menos una categoría para ver combinaciones.", icon=":material/touch_app:")
            return
        motor, candado = comun.motor_y_candado()
        with candado:
            pedidos = armar_pedido_manual(motor, datos.productos, presupuesto, list(elegidas), n=5)
        if not pedidos:
            st.warning("Ninguna combinación cabe en ese presupuesto. Prueba con más dinero o con menos categorías.", icon=":material/search_off:")
            return
        st.subheader(f"{len(pedidos)} combinaciones")
        st.caption("De la que más aprovecha el presupuesto a la que menos.")
        for numero, pedido in enumerate(pedidos, start=1):
            with st.container(border=True):
                st.markdown(f"**Opción {numero} · {dinero(pedido.subtotal)}** · sobran {dinero(presupuesto - pedido.subtotal)}")
                st.progress(
                    min(pedido.subtotal / presupuesto, 1.0),
                    text=f"Usa el {pedido.subtotal / presupuesto:.0%} del presupuesto",
                )
                st.markdown(lista_markdown(pedido.productos))
