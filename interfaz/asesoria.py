"""Sección de asesoría: la agenda del día y el modo mostrador."""

import pandas as pd
import streamlit as st

from interfaz import comun, estilo
from interfaz.comun import dinero, nombre_categoria
from ventas import administracion as admin
from ventas.combos import ESTADOS
from ventas.contactos import RESULTADOS, conversion, pospuestos, ultimo_contacto
from ventas.funcional import UMBRAL_FRECUENTE, VENTANA_FRECUENCIA
from ventas.mensajes import enumerar
from ventas.modelos import ClienteFrecuente
from ventas.ofertas import ofertas_vigentes
from ventas.pedido import ORDENES_MOSTRADOR, armar_pedido_manual
from ventas.servicio import TarjetaAgenda, construir_tarjetas

TONO_PRIORIDAD = {"alta": "alta", "media": "media", "baja": "baja"}
MOTIVOS_OFERTA = {
    "similares": "La compraron clientes con compras parecidas",
    "categoria_habitual": "Es de una categoría que suele comprar",
    "cliente_frecuente": "Compra seguido",
}
REGISTRADO, NO_REGISTRADO = "Registrado", "No registrado"
CHIP_PEDIDO = {"borrador": "Pedido en borrador", "enviado": "Pedido enviado"}
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
    vigentes = ofertas_vigentes(comun.ofertas(), hoy)
    motor, candado = comun.motor_y_candado()
    with candado:
        tarjetas = construir_tarjetas(datos, hoy, motor, vigentes=vigentes, pedidos=comun.combos())
    if not tarjetas:
        st.info(
            "Todavía no hay clientes para contactar. Registra ventas en Administración › Ventas "
            "y la agenda se armará sola.",
            icon=":material/info:",
        )
        return

    contactos = comun.contactos()
    en_espera = pospuestos(contactos, hoy) & {t.cliente.id_cliente for t in tarjetas}
    if en_espera:
        st.toggle(
            f"Mostrar también los pospuestos ({len(en_espera)})",
            key="ver_pospuestos",
            help="Clientes que contactaste y pediste volver a mostrar más adelante.",
        )
    if not st.session_state.get("ver_pospuestos"):
        tarjetas = tuple(t for t in tarjetas if t.cliente.id_cliente not in en_espera)
    resumen_superior(tarjetas, conversion(contactos, datos.ventas, hoy))
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


def resumen_superior(tarjetas: tuple[TarjetaAgenda, ...], conv) -> None:
    def cuantos(tipo: str) -> int:
        return sum(t.entrada.accion.tipo == tipo for t in tarjetas)

    with st.container(key="fila_indicadores"):
        c = st.columns([1, 1, 1, 1, 1.5])
    c[0].metric("Contactos", len(tarjetas), border=True)
    c[1].metric("Por reactivar", cuantos("reactivar"), border=True)
    c[2].metric("Por fidelizar", cuantos("fidelizar"), border=True)
    c[3].metric("Complementar", cuantos("cruzar"), border=True)
    c[4].metric(
        "Conversión (15 días)",
        "—" if conv.tasa is None else f"{conv.tasa:.0%}".replace("%", " %"),
        border=True,
        help=f"De {conv.contactos} contactos registrados, {conv.compraron} terminaron en una compra en los 15 días siguientes.",
    )


def tarjeta(posicion: int, t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    frecuente = isinstance(t.cliente, ClienteFrecuente)
    with st.container(border=True, key=f"tarjeta_{t.cliente.id_cliente}"):
        st.markdown(f"#### {posicion}. {t.cliente.nombre}")
        st.markdown(
            estilo.chip(accion.titulo(), TONO_PRIORIDAD[accion.prioridad])
            + estilo.chip(f"Prioridad {accion.prioridad}")
            + estilo.chip("Cliente frecuente" if frecuente else "Cliente regular")
            + (estilo.chip("Oferta para este cliente", "ok") if t.ofertas else "")
            + (estilo.chip(CHIP_PEDIDO[t.pedido.estado], "media") if t.pedido else ""),
            unsafe_allow_html=True,
        )
        st.write(t.entrada.motivo)
        ultimo = ultimo_contacto(comun.contactos(), t.cliente.id_cliente)
        if ultimo:
            vuelve = f" · vuelve el {ultimo.volver_el:%d/%m/%Y}" if ultimo.volver_el > ultimo.fecha else ""
            st.caption(f"Último contacto: {ultimo.fecha:%d/%m/%Y} · {ultimo.texto}{vuelve}")
        if t.pedido:
            st.markdown(
                comun.html_cotizacion(
                    t.cotizacion,
                    f"Pedido {t.pedido.id_combo} · {ESTADOS[t.pedido.estado]} · guardado el {t.pedido.fecha:%d/%m/%Y}",
                ),
                unsafe_allow_html=True,
            )
            st.caption("Ajusta el descuento, márcalo como enviado o regístralo en Administración › Ventas › Pedidos abiertos.")
        else:
            mostrar_pedido_resumido(t)
            if t.pedidos:
                st.button(
                    "Guardar como pedido",
                    key=f"guardar_sugerido_{t.cliente.id_cliente}",
                    icon=":material/add_shopping_cart:",
                    on_click=_guardar_sugerido,
                    args=(t.cliente.id_cliente, t.cliente.nombre, t.pedidos[0].pedido.ids),
                )
        boton_whatsapp, por_que, mensaje, personalizar = st.columns([1.35, 1, 1, 1.25])
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
        with st.popover("Registrar contacto", icon=":material/how_to_reg:", width="stretch"):
            formulario_contacto(t)
        if personalizar.button(
            "Personalizar",
            key=f"personalizar_{t.cliente.id_cliente}",
            icon=":material/edit_note:",
            width="stretch",
            help="Abre «Arma mi pedido» con este cliente elegido.",
        ):
            st.session_state["combo_tipo"] = REGISTRADO
            st.session_state["combo_cliente"] = t.cliente.id_cliente
            st.switch_page("paginas/pedido.py")


def filas_html(productos) -> str:
    return "".join(estilo.fila_producto(p.nombre, p.categoria, dinero(p.precio), nombre_categoria(p.categoria)) for p in productos)


def filas_sugerido_html(sugerido) -> str:
    """Filas del pedido sugerido; las que traen oferta dicen hasta cuándo vale."""
    oferta_de = {o.id_producto: o for o in sugerido.ofertas_incluidas}
    return "".join(
        estilo.fila_producto(
            p.nombre,
            p.categoria,
            dinero(p.precio),
            f"Oferta -{oferta_de[p.id_producto].porcentaje} % hasta el {oferta_de[p.id_producto].hasta:%d/%m/%Y}"
            if p.id_producto in oferta_de
            else nombre_categoria(p.categoria),
        )
        for p in sugerido.pedido.productos
    )


def formulario_contacto(t: TarjetaAgenda) -> None:
    id_cliente = t.cliente.id_cliente
    resultado = st.radio(
        "¿Cómo te fue?", list(RESULTADOS), format_func=lambda r: RESULTADOS[r][0], key=f"resultado_{id_cliente}"
    )
    st.number_input(
        "Volver a mostrar en (días)",
        min_value=0,
        max_value=365,
        value=RESULTADOS[resultado][1],
        step=1,
        key=f"dias_{id_cliente}_{resultado}",
    )
    st.button(
        "Guardar contacto",
        key=f"guardar_contacto_{id_cliente}",
        type="primary",
        on_click=_guardar_contacto,
        args=(id_cliente, t.cliente.nombre),
    )


def _guardar_contacto(id_cliente: str, nombre: str) -> None:
    resultado = st.session_state[f"resultado_{id_cliente}"]
    dias = st.session_state.get(f"dias_{id_cliente}_{resultado}")
    try:
        contacto = admin.registrar_contacto(comun.repositorio(), id_cliente, resultado, comun.fecha_referencia(), dias)
    except ValueError as error:
        comun.avisar("error", str(error))
        return
    vuelta = (
        f" Vuelve a la agenda el {contacto.volver_el:%d/%m/%Y}." if contacto.volver_el > contacto.fecha else ""
    )
    comun.avisar("exito", f"Contacto con {nombre} registrado: {contacto.texto}.{vuelta}")


def _guardar_sugerido(id_cliente: str, nombre: str, ids: tuple[str, ...]) -> None:
    try:
        combo = admin.guardar_combo(comun.repositorio(), id_cliente, list(ids), comun.fecha_referencia())
    except ValueError as error:
        comun.avisar("error", str(error))
        return
    comun.avisar("exito", f"Pedido {combo.id_combo} guardado para {nombre}.")


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
        '<div class="pedido-titulo">Pedido sugerido</div>' + filas_sugerido_html(mejor) + cierre,
        unsafe_allow_html=True,
    )
    if len(t.pedidos) > 1:
        st.caption(f"Hay {len(t.pedidos) - 1} opciones más de pedido para este cliente.")


def mostrar_por_que(t: TarjetaAgenda) -> None:
    accion = t.entrada.accion
    st.markdown("**Reglas de Prolog que se aplicaron**")
    st.markdown("".join(estilo.chip(m) for m in accion.motivos), unsafe_allow_html=True)
    perfil = t.entrada.perfil
    if perfil.intervalo_promedio is None:
        ritmo = "Todavía no tiene un ritmo de compra"
    else:
        ritmo = f"Compra cada {perfil.intervalo_promedio:g} días en promedio"
    st.caption(
        f"Frecuente: {UMBRAL_FRECUENTE} compras o más en los últimos {VENTANA_FRECUENCIA} días "
        f"(lleva {perfil.compras_recientes}). {ritmo}: se considera inactivo pasados "
        f"{t.limite_inactividad} días sin comprar."
    )
    if t.complementos:
        partes = [f"{p.nombre} ({dinero(p.precio)})" for p in t.complementos]
        st.markdown(f"**Complementa lo que compró:** {enumerar(partes)}")
    if t.ofertas:
        st.markdown("**Ofertas pensadas para este cliente**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Producto": o.producto.nombre,
                        "Descuento": f"-{o.oferta.porcentaje} %",
                        "Hasta": f"{o.oferta.hasta:%d/%m/%Y}",
                        "Por qué": "; ".join(MOTIVOS_OFERTA[m] for m in o.motivos),
                    }
                    for o in t.ofertas
                ]
            ),
            hide_index=True,
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
        with st.container(border=True, key="panel_cliente_combo"):
            tipo = st.segmented_control(
                "Cliente", [REGISTRADO, NO_REGISTRADO], default=REGISTRADO, key="combo_tipo"
            )
            if tipo == NO_REGISTRADO:
                st.text_input(
                    "Nombre del cliente", placeholder="Ej.: Pedro Gómez", key="combo_nombre", label_visibility="collapsed"
                )
                st.caption("Se registra como cliente al registrar la venta del combo.")
            else:
                clientes = {c.id_cliente: c.nombre for c in datos.clientes}
                st.selectbox(
                    "Cliente registrado",
                    sorted(clientes, key=clientes.get),
                    index=None,
                    format_func=clientes.get,
                    placeholder="Elige para quién es el combo",
                    key="combo_cliente",
                    label_visibility="collapsed",
                )
            st.caption("Con «Guardar combinación» el combo pasa a Administración › Ventas para registrarlo.")
    with derecha:
        if not elegidas:
            st.info("Elige al menos una categoría para ver combinaciones.", icon=":material/touch_app:")
            return
        sugerir_otras_ofertas(datos, vigentes, elegidas)
        orden = st.segmented_control(
            "Ordenar por",
            list(ORDENES_MOSTRADOR),
            default="presupuesto",
            format_func=ORDENES_MOSTRADOR.get,
            key="orden_combinaciones",
        ) or "presupuesto"
        motor, candado = comun.motor_y_candado()
        with candado:
            pedidos = armar_pedido_manual(
                motor, datos.productos, presupuesto, list(elegidas), n=5, vigentes=vigentes, orden=orden
            )
        if not pedidos:
            st.warning(
                "Ninguna combinación de al menos 2 productos cabe en ese presupuesto. "
                "Prueba con más dinero o con otras categorías.",
                icon=":material/search_off:",
            )
            return
        st.subheader(f"{len(pedidos)} combinaciones")
        if orden == "margen":
            st.caption("De la que más ganancia deja a la que menos (las que tienen productos sin costo cargado, al final).")
        elif any(i in vigentes for p in pedidos for i in p.ids):
            st.caption("Primero las que llevan productos en oferta; luego, de la que más aprovecha el presupuesto a la que menos.")
        else:
            st.caption("De la que más aprovecha el presupuesto a la que menos.")
        normal = {p.id_producto: p.precio for p in datos.productos}
        for numero, pedido in enumerate(pedidos, start=1):
            con_oferta = [i for i in pedido.ids if i in vigentes]
            with st.container(border=True, key=f"opcion_{numero}"):
                st.markdown(f"**Opción {numero} · {dinero(pedido.subtotal)}** · sobran {dinero(presupuesto - pedido.subtotal)}")
                if pedido.margen is not None:
                    st.markdown(f"Margen: {dinero(pedido.margen)}")
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
                st.button(
                    "Guardar combinación",
                    key=f"guardar_combo_{numero}",
                    icon=":material/add_shopping_cart:",
                    on_click=_guardar_combo,
                    args=(pedido.ids,),
                    disabled=cliente_del_combo() is None,
                    help="Primero elige el cliente (o escribe su nombre) a la izquierda.",
                )


def cliente_del_combo() -> tuple[str | None, str] | None:
    """(id_cliente, nombre_no_registrado) elegido en el panel, o None si falta."""
    if st.session_state.get("combo_tipo") == NO_REGISTRADO:
        nombre = " ".join(str(st.session_state.get("combo_nombre", "")).split())
        return (None, nombre) if nombre else None
    id_cliente = st.session_state.get("combo_cliente")
    return (id_cliente, "") if id_cliente else None


def _guardar_combo(ids: tuple[str, ...]) -> None:
    elegido = cliente_del_combo()
    if elegido is None:
        comun.avisar("error", "Elige el cliente o escribe su nombre antes de guardar la combinación.")
        return
    id_cliente, nombre_libre = elegido
    try:
        combo = admin.guardar_combo(comun.repositorio(), id_cliente, list(ids), comun.fecha_referencia(), nombre_libre)
    except ValueError as error:
        comun.avisar("error", str(error))
        return
    if combo.registrado:
        nombre = next(c.nombre for c in comun.datos().clientes if c.id_cliente == id_cliente)
    else:
        nombre = f"{combo.nombre_cliente} (no registrado)"
    comun.avisar(
        "exito",
        f"Combinación {combo.id_combo} guardada para {nombre}. Gestiónala en Administración › Ventas › Pedidos abiertos.",
    )


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
