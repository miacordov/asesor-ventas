"""Sección de asesoría: propuesta personalizada.

El vendedor elige un cliente, ve las ofertas que le corresponden (y las demás
vigentes), arma el combo, le pone un descuento y lo guarda en la agenda para
enviarlo después por WhatsApp.
"""

import pandas as pd
import streamlit as st

from interfaz import comun, estilo
from interfaz.comun import dinero, nombre_categoria
from ventas import administracion as admin
from ventas.mensajes import Mensaje, mensaje_propuesta
from ventas.modelos import ClienteFrecuente
from ventas.ofertas import ofertas_para_cliente, ofertas_vigentes
from ventas.pedido import productos_comprados
from ventas.propuestas import DESCUENTO_MAXIMO, MINIMO_PRODUCTOS, armar_propuesta
from ventas.servicio import clientes_con_perfil

MOTIVOS = {
    "similares": "La compraron clientes con compras parecidas",
    "categoria_habitual": "Es de una categoría que suele comprar",
    "cliente_frecuente": "Compra seguido",
}
CLAVE_CLIENTE = "propuesta_cliente"


def pagina_propuesta() -> None:
    comun.mostrar_aviso()
    estilo.hero(
        "Asesoría",
        "Propuesta personalizada",
        "Arma a mano el combo de un cliente: mira sus ofertas, elige los productos, ponle un descuento "
        "y guárdalo en la agenda para enviárselo cuando quieras.",
        "propuesta",
    )
    datos, hoy = comun.datos(), comun.fecha_referencia()
    if not datos.clientes or len(datos.productos) < MINIMO_PRODUCTOS:
        st.info("Necesitas clientes y al menos dos productos registrados.", icon=":material/info:")
        return
    vigentes = ofertas_vigentes(comun.ofertas(), hoy)
    con_perfil = {c.id_cliente: (c, p) for c, p in clientes_con_perfil(datos, hoy)}
    guardadas = {p.id_cliente: p for p in comun.propuestas()}

    ids = sorted(con_perfil, key=lambda i: con_perfil[i][0].nombre)
    if st.session_state.get(CLAVE_CLIENTE) not in ids:
        st.session_state.pop(CLAVE_CLIENTE, None)
    id_cliente = st.selectbox("Cliente", ids, format_func=lambda i: con_perfil[i][0].nombre, key=CLAVE_CLIENTE)
    cliente, perfil = con_perfil[id_cliente]
    frecuente = isinstance(cliente, ClienteFrecuente)
    st.markdown(
        estilo.chip("Cliente frecuente" if frecuente else "Cliente regular")
        + estilo.chip(f"{perfil.n_compras} compras")
        + (estilo.chip(f"Ticket promedio {dinero(perfil.ticket_promedio)}") if perfil.n_compras else "")
        + "".join(estilo.chip(nombre_categoria(c)) for c in perfil.categorias_habituales[:3]),
        unsafe_allow_html=True,
    )

    motor, candado = comun.motor_y_candado()
    with candado:
        motor.cargar_compras(datos.ventas)
        recomendaciones = motor.recomendar(id_cliente)
    comprados = productos_comprados(datos.ventas, id_cliente)
    suyas = ofertas_para_cliente(vigentes, datos.productos, perfil, recomendaciones, frecuente, comprados)

    izquierda, derecha = st.columns([1, 1], gap="large")
    with izquierda:
        st.subheader("Ofertas vigentes")
        tabla_ofertas(datos, vigentes, suyas, comprados)
    with derecha:
        formulario(datos, cliente, vigentes, guardadas.get(id_cliente), hoy)
    st.divider()
    propuestas_guardadas(datos, guardadas)


def tabla_ofertas(datos, vigentes, suyas, comprados) -> None:
    if not vigentes:
        st.info("No hay ofertas vigentes. Créalas en Asesoría › Ofertas de temporada.", icon=":material/sell:")
        return
    motivos = {o.id_producto: o.motivos for o in suyas}
    filas = [
        {
            "Producto": p.nombre,
            "Precio": vigentes[p.id_producto].precio(p.precio),
            "Descuento": f"-{vigentes[p.id_producto].porcentaje} %",
            "Hasta": f"{vigentes[p.id_producto].hasta:%d/%m/%Y}",
            "Para este cliente": (
                "Ya lo compró"
                if p.id_producto in comprados
                else "; ".join(MOTIVOS[m] for m in motivos.get(p.id_producto, ())) or "—"
            ),
        }
        for p in sorted(
            (p for p in datos.productos if p.id_producto in vigentes),
            key=lambda p: (p.id_producto not in motivos, p.nombre),
        )
    ]
    st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        key="tabla_ofertas_cliente",
        column_config={"Precio": st.column_config.NumberColumn("Precio con oferta", format="S/ %.2f")},
    )


def formulario(datos, cliente, vigentes, guardada, hoy) -> None:
    clave = f"pp_{cliente.id_cliente}_{comun.version('propuesta')}"
    por_id = {p.id_producto: p for p in datos.productos}

    def etiqueta(i: str) -> str:
        p = por_id[i]
        if i in vigentes:
            return f"{p.nombre} · {dinero(vigentes[i].precio(p.precio))} (oferta -{vigentes[i].porcentaje} %)"
        return f"{p.nombre} · {dinero(p.precio)}"

    orden = sorted(por_id, key=lambda i: (i not in vigentes, por_id[i].nombre))
    with st.container(border=True, key="panel_propuesta"):
        st.subheader("Combo para el cliente")
        elegidos = st.multiselect(
            "Productos",
            orden,
            default=[i for i in (guardada.ids if guardada else ()) if i in por_id],
            format_func=etiqueta,
            placeholder="Elige al menos 2 productos",
            key=f"{clave}_productos",
        )
        descuento = st.number_input(
            "Descuento al combo (%)",
            min_value=0,
            max_value=DESCUENTO_MAXIMO,
            value=guardada.descuento if guardada else round(cliente.descuento() * 100),
            step=1,
            key=f"{clave}_descuento",
        )
        try:
            propuesta = armar_propuesta(cliente.id_cliente, elegidos, int(descuento), hoy, datos.productos, vigentes)
        except ValueError as error:
            st.caption(str(error))
            return
        filas = "".join(
            estilo.fila_producto(
                por_id[linea.id_producto].nombre,
                por_id[linea.id_producto].categoria,
                dinero(linea.precio),
                f"Oferta · antes {dinero(linea.precio_normal)}" if linea.en_oferta else nombre_categoria(por_id[linea.id_producto].categoria),
            )
            for linea in propuesta.lineas
        )
        if propuesta.descuento:
            cierre = estilo.total(
                "Total",
                dinero(propuesta.total),
                tachado=dinero(propuesta.subtotal),
                nota=f"{propuesta.descuento} % de descuento al combo",
            )
        else:
            cierre = estilo.total("Total", dinero(propuesta.total))
        st.markdown(filas + cierre, unsafe_allow_html=True)
        with st.expander("Mensaje que se enviará"):
            st.write(mensaje_propuesta(cliente, propuesta, {i: p.nombre for i, p in por_id.items()}))
        st.button(
            "Guardar en la agenda",
            type="primary",
            icon=":material/bookmark_added:",
            on_click=_guardar,
            args=(cliente.id_cliente, cliente.nombre, clave),
            key="guardar_propuesta",
        )


def _guardar(id_cliente: str, nombre: str, clave: str) -> None:
    hoy = comun.fecha_referencia()
    try:
        admin.guardar_propuesta(
            comun.repositorio(),
            id_cliente,
            list(st.session_state[f"{clave}_productos"]),
            st.session_state[f"{clave}_descuento"],
            hoy,
            ofertas_vigentes(comun.ofertas(), hoy),
        )
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Propuesta para {nombre} guardada en la agenda.")
        comun.reiniciar("propuesta")


def _quitar(id_cliente: str, nombre: str) -> None:
    try:
        admin.quitar_propuesta(comun.repositorio(), id_cliente)
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Propuesta de {nombre} quitada de la agenda.")
        comun.reiniciar("propuesta")


def propuestas_guardadas(datos, guardadas: dict) -> None:
    st.subheader("Propuestas guardadas")
    if not guardadas:
        st.info("Todavía no guardaste propuestas.", icon=":material/bookmark:")
        return
    clientes = {c.id_cliente: c for c, _ in clientes_con_perfil(datos, comun.fecha_referencia())}
    nombres = {p.id_producto: p.nombre for p in datos.productos}
    for propuesta in guardadas.values():
        cliente = clientes[propuesta.id_cliente]
        mensaje = Mensaje(
            cliente.id_cliente, cliente.nombre, cliente.telefono, "fidelizar", mensaje_propuesta(cliente, propuesta, nombres)
        )
        with st.container(border=True, key=f"guardada_{cliente.id_cliente}"):
            texto, enviar, quitar = st.columns([4, 1.2, 1], vertical_alignment="center")
            texto.markdown(
                f"**{cliente.nombre}** · {enumerar_nombres(propuesta, nombres)} · **{dinero(propuesta.total)}** "
                f"· guardada el {propuesta.fecha:%d/%m/%Y}"
            )
            if mensaje.enlace:
                enviar.link_button("WhatsApp", mensaje.enlace, icon=":material/chat:", width="stretch")
            else:
                enviar.caption("Sin teléfono")
            quitar.button(
                "Quitar",
                key=f"quitar_propuesta_{cliente.id_cliente}",
                on_click=_quitar,
                args=(cliente.id_cliente, cliente.nombre),
                width="stretch",
            )


def enumerar_nombres(propuesta, nombres) -> str:
    return ", ".join(nombres[i] for i in propuesta.ids)
