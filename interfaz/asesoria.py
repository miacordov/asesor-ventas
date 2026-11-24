"""Sección de asesoría: la agenda del día y el modo mostrador."""

import pandas as pd
import streamlit as st

from interfaz import comun, estilo
from interfaz.comun import dinero, nombre_categoria
from ventas.funcional import UMBRAL_FRECUENTE
from ventas.logico import DIAS_INACTIVIDAD
from ventas.modelos import ClienteFrecuente
from ventas.ofertas import ofertas_vigentes
from ventas.pedido import armar_pedido_manual
from ventas.servicio import TarjetaAgenda, construir_tarjetas

TONO_PRIORIDAD = {"alta": "alta", "media": "media", "baja": "baja"}
FILTROS = {"Todos": None, "Reactivar": "reactivar", "Fidelizar": "fidelizar", "Complementar": "cruzar"}


# Agenda de fidelización
def pagina_agenda() -> None:
    comun.mostrar_aviso()
    estilo.hero(
        "Asesoría",
        "Agenda de fidelización",
        "Los clientes a quienes conviene contactar hoy, ordenados por urgencia, con el motivo, "
        "el pedido sugerido y el mensaje listo para enviar.",
        "agenda",
    )
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
        "**Reactivar:** compraban seguido y dejaron de venir. **Fidelizar:** clientes frecuentes y activos. "
        "**Complementar:** compran poco, se les ofrece lo que llevan otros. "
        "**Valor en pedidos:** suma del mejor pedido de cada cliente, con su descuento. "
    )
    filtro = st.segmented_control(
        "Mostrar", list(FILTROS), default="Todos", key="filtro_agenda", label_visibility="collapsed"
    )
    tipo = FILTROS[filtro or "Todos"]
    visibles = [(i, t) for i, t in enumerate(tarjetas, start=1) if tipo is None or t.entrada.accion.tipo == tipo]
    with st.container(key="fila_rejilla"):
        for inicio in range(0, len(visibles), 2):
            columnas = st.columns(2)
            for columna, (posicion, tarjeta_) in zip(columnas, visibles[inicio : inicio + 2], strict=False):
                with columna:
                    tarjeta(posicion, tarjeta_)


def resumen_superior(tarjetas: tuple[TarjetaAgenda, ...]) -> None:
    def cuantos(tipo: str) -> int:
        return sum(t.entrada.accion.tipo == tipo for t in tarjetas)

    potencial = sum(t.pedidos[0].total_con_descuento for t in tarjetas if t.pedidos)
    with st.container(key="fila_indicadores"):
        c = st.columns([1, 1, 1, 1, 1.5])
    c[0].metric("Contactos", len(tarjetas), border=True)
    c[1].metric("Por reactivar", cuantos("reactivar"), border=True)
    c[2].metric("Por fidelizar", cuantos("fidelizar"), border=True)
    c[3].metric("Complementar", cuantos("cruzar"), border=True)
    c[4].metric(
        "Valor en pedidos sugeridos",
        dinero(potencial),
        border=True,
    )


def tarjeta(posicion: int, t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    frecuente = isinstance(t.cliente, ClienteFrecuente)
    with st.container(border=True, key=f"tarjeta_{t.cliente.id_cliente}"):
        st.markdown(f"#### {posicion}. {t.cliente.nombre}")
        st.markdown(
            estilo.chip(accion.titulo(), TONO_PRIORIDAD[accion.prioridad])
            + estilo.chip(f"Prioridad {accion.prioridad}")
            + estilo.chip("Cliente frecuente" if frecuente else "Cliente regular"),
            unsafe_allow_html=True,
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


def filas_html(productos) -> str:
    return "".join(estilo.fila_producto(p.nombre, p.categoria, dinero(p.precio), nombre_categoria(p.categoria)) for p in productos)


def mostrar_pedido_resumido(t: TarjetaAgenda) -> None:
    if not t.pedidos:
        st.caption("No hay una combinación de al menos 2 productos dentro del presupuesto habitual de este cliente.")
        return
    mejor = t.pedidos[0]
    subtotal, total = mejor.pedido.subtotal, mejor.total_con_descuento
    if total < subtotal:
        porcentaje = round(t.cliente.descuento() * 100)
        cierre = estilo.total(
            "Total", dinero(total), tachado=dinero(subtotal), nota=f"Ahorras {dinero(subtotal - total)} ({porcentaje} % de descuento)"
        )
    else:
        cierre = estilo.total("Total", dinero(total))
    st.markdown(
        '<div class="pedido-titulo">Pedido sugerido</div>' + filas_html(mejor.pedido.productos) + cierre,
        unsafe_allow_html=True,
    )
    if len(t.pedidos) > 1:
        st.caption(f"Hay {len(t.pedidos) - 1} opciones más de pedido para este cliente.")


def mostrar_por_que(t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    st.markdown("**Reglas de Prolog que se aplicaron**")
    st.markdown("".join(estilo.chip(m) for m in accion.motivos), unsafe_allow_html=True)
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
    estilo.hero(
        "Asesoría · modo mostrador",
        "Arma mi pedido",
        "Indica el presupuesto y las categorías: Prolog recorre por backtracking todas las combinaciones posibles.",
        "pedido",
    )
    datos = comun.datos()
    vigentes = ofertas_vigentes(comun.ofertas(), comun.fecha_referencia())
    categorias = sorted({p.categoria for p in datos.productos})
    if not categorias:
        st.info("No hay productos registrados. Agrégalos en Administración › Productos.", icon=":material/info:")
        return

    with st.container(key="fila_pedido"):
        izquierda, derecha = st.columns([1, 2], gap="large")
    with izquierda:
        with st.container(border=True, key="panel_filtros"):
            presupuesto = st.number_input("Presupuesto (S/)", min_value=1.0, value=200.0, step=10.0, key="presupuesto_pedido")
            elegidas = st.pills(
                "Categorías",
                categorias,
                selection_mode="multi",
                default=[c for c in ("perifericos", "accesorios") if c in categorias],
                format_func=nombre_categoria,
                key="categorias_pedido",
            )
            st.caption(
                "Cada combinación lleva al menos 2 productos: uno por cada categoría elegida "
                "(con una sola categoría, dos de ella), sin repetir y sin pasarse del presupuesto."
            )
    with derecha:
        if not elegidas:
            st.info("Elige al menos una categoría para ver combinaciones.", icon=":material/touch_app:")
            return
        sugerir_otras_ofertas(datos, vigentes, elegidas)
        motor, candado = comun.motor_y_candado()
        with candado:
            pedidos = armar_pedido_manual(motor, datos.productos, presupuesto, list(elegidas), n=5, vigentes=vigentes)
        if not pedidos:
            st.warning(
                "Ninguna combinación de al menos 2 productos cabe en ese presupuesto. "
                "Prueba con más dinero o con otras categorías.",
                icon=":material/search_off:",
            )
            return
        st.subheader(f"{len(pedidos)} combinaciones")
        if any(i in vigentes for p in pedidos for i in p.ids):
            st.caption("Primero las que llevan productos en oferta; luego, de la que más aprovecha el presupuesto a la que menos.")
        else:
            st.caption("De la que más aprovecha el presupuesto a la que menos.")
        normal = {p.id_producto: p.precio for p in datos.productos}
        for numero, pedido in enumerate(pedidos, start=1):
            con_oferta = [i for i in pedido.ids if i in vigentes]
            with st.container(border=True, key=f"opcion_{numero}"):
                st.markdown(f"**Opción {numero} · {dinero(pedido.subtotal)}** · sobran {dinero(presupuesto - pedido.subtotal)}")
                if con_oferta:
                    ahorro = sum(normal[i] for i in pedido.ids) - pedido.subtotal
                    st.markdown(
                        estilo.chip("En oferta", "ok") + estilo.chip(f"Ahorras {dinero(ahorro)}", "ok"),
                        unsafe_allow_html=True,
                    )
                st.progress(
                    min(pedido.subtotal / presupuesto, 1.0),
                    text=f"Usa el {pedido.subtotal / presupuesto:.0%} del presupuesto",
                )
                st.markdown(filas_pedido_html(pedido.productos, vigentes, normal), unsafe_allow_html=True)


def filas_pedido_html(productos, vigentes, normal: dict[str, float]) -> str:
    """Filas de producto; las que están en oferta muestran el descuento y el precio de antes."""
    return "".join(
        estilo.fila_producto(
            p.nombre,
            p.categoria,
            dinero(p.precio),
            f"Oferta -{vigentes[p.id_producto].porcentaje} % · antes {dinero(normal[p.id_producto])}"
            if p.id_producto in vigentes
            else nombre_categoria(p.categoria),
        )
        for p in productos
    )


def sugerir_otras_ofertas(datos, vigentes, elegidas) -> None:
    """Ofertas vigentes en categorías que no se eligieron: se sugieren para sumarlas."""
    otras = [p for p in datos.productos if p.id_producto in vigentes and p.categoria not in elegidas]
    if otras:
        lista = ", ".join(f"{p.nombre} (-{vigentes[p.id_producto].porcentaje} %)" for p in otras[:4])
        resto = f" y {len(otras) - 4} más" if len(otras) > 4 else ""
        st.info(
            f"También hay ofertas en otras categorías: {lista}{resto}. Agrega su categoría para combinarlas.",
            icon=":material/sell:",
        )
