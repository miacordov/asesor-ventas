"""Sección de administración: resumen del negocio, clientes, productos y ventas.

Las páginas solo presentan y recogen datos: validar, guardar y calcular lo hacen
ventas/administracion.py, ventas/repositorio.py, ventas/analisis.py y
ventas/servicio.py. Cada botón ejecuta un callback (se ejecuta antes de volver a
dibujar la página), de modo que los avisos y los campos limpios se ven al instante.
"""

import pandas as pd
import streamlit as st

from interfaz import comun, estilo
from interfaz.comun import dinero, dinero_corto, nombre_categoria
from ventas import administracion as admin
from ventas import analisis
from ventas.funcional import UMBRAL_FRECUENTE
from ventas.modelos import ClienteFrecuente
from ventas.ofertas import ofertas_vigentes
from ventas.servicio import (
    acciones_por_cliente,
    clientes_con_perfil,
    describir_cambio_agenda,
)

NUEVA_CATEGORIA = "Nueva categoría…"
AYUDA_TELEFONO = (
    "Con o sin código de país. Un celular de 9 dígitos se toma como peruano (+51). "
    "Sin teléfono no habrá botón de WhatsApp para este cliente."
)
COLOR_GRAFICO = "#14305E"  # azul navy
COLOR_GRAFICO_2 = "#C69B3F"  # dorado


def _titulo(ilustracion: str, titulo: str, subtitulo: str) -> None:
    comun.mostrar_aviso()
    estilo.hero("Administración", titulo, subtitulo, ilustracion)


def _repo():
    return comun.repositorio()


# =====================================================================
# Resumen del negocio
# =====================================================================
def pagina_resumen() -> None:
    _titulo(
        "resumen",
        "Resumen del negocio",
        "Cómo van las ventas: indicadores, tendencia por mes, categorías y tus mejores clientes.",
    )
    datos, hoy = comun.datos(), comun.fecha_referencia()
    df = analisis.dataframe_ventas(datos)
    if df.empty:
        st.info("Aún no hay ventas registradas. Regístralas en Administración › Ventas.", icon=":material/info:")
    else:
        indicadores(df)
        with st.container(key="fila_graficos"):
            izquierda, derecha = st.columns(2, gap="large")
        with izquierda:
            ventas_por_mes(df)
        with derecha:
            ventas_por_categoria(df)
        clientes_y_segmentos(datos, hoy, df)
        st.download_button(
            "Descargar ventas (CSV)",
            analisis.a_csv(df),
            file_name="ventas.csv",
            mime="text/csv",
            icon=":material/download:",
            help="Se abre directamente en Excel.",
        )
    datos_de_ejemplo()


def indicadores(df: pd.DataFrame) -> None:
    with st.container(key="fila_indicadores"):
        c = st.columns(5)
    c[0].metric("Ventas totales", dinero_corto(float(df["monto"].sum())), border=True)
    c[1].metric(
        "Compras",
        analisis.compras_totales(df),
        border=True,
        help="Una compra es un día distinto en que un cliente adquirió algo.",
    )
    c[2].metric("Ticket promedio", dinero_corto(analisis.ticket_promedio_compra(df)), border=True, help="Gasto medio por compra.")
    c[3].metric("Clientes con compras", int(df["id_cliente"].nunique()), border=True)
    c[4].metric(
        "Top 3 clientes",
        f"{analisis.concentracion_top(df, 3):.0f} %",
        border=True,
        help="Porcentaje de las ventas que concentran los tres mejores clientes.",
    )


def ventas_por_mes(df: pd.DataFrame) -> None:
    st.subheader("Ventas por mes")
    resumen = analisis.resumen_mensual(df)
    st.bar_chart(resumen, x="mes", y="ventas", x_label="Mes", y_label="Ventas (S/)", color=COLOR_GRAFICO)
    resumen["variacion_pct"] = resumen["variacion_pct"].map(lambda x: "—" if pd.isna(x) else f"{x:+.1f} %")
    st.dataframe(
        resumen,
        hide_index=True,
        column_config={
            "mes": st.column_config.TextColumn("Mes"),
            "ventas": st.column_config.NumberColumn("Ventas", format="S/ %.2f"),
            "compras": st.column_config.NumberColumn("Compras", format="%d"),
            "variacion_pct": st.column_config.TextColumn("Variación", help="Frente al mes anterior."),
        },
    )
    st.caption("El último mes puede estar incompleto, y su variación lo refleja.")


def ventas_por_categoria(df: pd.DataFrame) -> None:
    st.subheader("Ventas por categoría")
    tabla = analisis.ventas_por_categoria(df)
    tabla["categoria"] = tabla["categoria"].map(nombre_categoria)
    st.bar_chart(tabla, x="categoria", y="ventas", x_label="Categoría", y_label="Ventas (S/)", color=COLOR_GRAFICO_2)
    st.dataframe(
        tabla,
        hide_index=True,
        column_config={
            "categoria": st.column_config.TextColumn("Categoría"),
            "ventas": st.column_config.NumberColumn("Ventas", format="S/ %.2f"),
            "participacion_pct": st.column_config.ProgressColumn("Participación", format="%.1f %%", min_value=0, max_value=100),
        },
    )


def clientes_y_segmentos(datos, hoy, df: pd.DataFrame) -> None:
    st.subheader("Clientes")
    with st.container(key="fila_segmentos"):
        izquierda, derecha = st.columns(2, gap="large")
    with izquierda:
        st.markdown("**Segmentos por gasto total**")
        if comun.fecha_valida(datos, hoy):
            perfiles = [perfil for _, perfil in clientes_con_perfil(datos, hoy)]
            st.dataframe(
                analisis.tabla_segmentos(perfiles),
                hide_index=True,
                column_config={
                    "segmento": st.column_config.TextColumn("Segmento"),
                    "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
                    "ventas": st.column_config.NumberColumn("Ventas", format="S/ %.2f"),
                    "participacion_pct": st.column_config.ProgressColumn("Participación", format="%.1f %%", min_value=0, max_value=100),
                },
            )
            st.caption("Alto, medio y bajo son los terciles del gasto total (NumPy).")
    with derecha:
        st.markdown("**Mejores clientes**")
        st.dataframe(
            analisis.top_clientes(df, 5),
            hide_index=True,
            column_config={
                "cliente": st.column_config.TextColumn("Cliente"),
                "ventas": st.column_config.NumberColumn("Ventas", format="S/ %.2f"),
                "participacion_pct": st.column_config.ProgressColumn("Participación", format="%.1f %%", min_value=0, max_value=100),
            },
        )


def _restablecer() -> None:
    try:
        admin.sembrar(_repo(), comun.CARPETA_CSV)
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", "Datos de ejemplo restablecidos.")
    st.session_state["confirmar_restablecer"] = False


def datos_de_ejemplo() -> None:
    with st.expander("Datos de ejemplo", icon=":material/database:"):
        st.caption(
            "Vuelve a cargar los archivos CSV de la carpeta datos/. Se pierden los clientes, "
            "productos y ventas que hayas registrado. Útil para repetir la demostración."
        )
        confirmar = st.checkbox("Entiendo que se borrarán mis cambios", key="confirmar_restablecer")
        st.button("Restablecer datos de ejemplo", disabled=not confirmar, on_click=_restablecer, icon=":material/restart_alt:")


# =====================================================================
# Clientes
# =====================================================================
def pagina_clientes() -> None:
    _titulo(
        "clientes",
        "Clientes",
        "Tu cartera de clientes. El tipo y el segmento se calculan solos con su historial de compras.",
    )
    datos, hoy = comun.datos(), comun.fecha_referencia()
    lista, nuevo, editar = st.tabs(["Lista", "Nuevo cliente", "Editar o eliminar"])
    with lista:
        lista_clientes(datos, hoy)
    with nuevo:
        nuevo_cliente()
    with editar:
        editar_cliente(datos)


def lista_clientes(datos, hoy) -> None:
    if not datos.clientes:
        st.info("Aún no hay clientes. Registra el primero en la pestaña «Nuevo cliente».", icon=":material/info:")
        return
    if not comun.fecha_valida(datos, hoy):
        return
    pares = clientes_con_perfil(datos, hoy)
    segmento_de = analisis.segmentar_clientes([perfil for _, perfil in pares])
    buscar = st.text_input("Buscar", placeholder="Buscar por nombre", label_visibility="collapsed", key="buscar_cliente")
    filas = [
        {
            "Cliente": cliente.nombre,
            "Tipo": "Frecuente" if isinstance(cliente, ClienteFrecuente) else "Regular",
            "Segmento": segmento_de[cliente.id_cliente],
            "Compras": perfil.n_compras,
            "Días sin comprar": "—" if perfil.dias_sin_comprar is None else str(perfil.dias_sin_comprar),
            "Total gastado": perfil.total_gastado,
            "Ticket promedio": perfil.ticket_promedio,
            "Categorías habituales": ", ".join(nombre_categoria(c) for c in perfil.categorias_habituales[:3]) or "—",
            "Teléfono": cliente.telefono or "—",
        }
        for cliente, perfil in pares
        if buscar.strip().lower() in cliente.nombre.lower()
    ]
    st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        column_config={
            "Compras": st.column_config.NumberColumn(format="%d"),
            "Total gastado": st.column_config.NumberColumn(format="S/ %.2f"),
            "Ticket promedio": st.column_config.NumberColumn(format="S/ %.2f"),
        },
    )
    st.caption(
        f"{len(filas)} de {len(pares)} clientes. Frecuente: {UMBRAL_FRECUENTE} compras o más. "
        "Una compra es un día distinto en que el cliente adquirió algo."
    )


def _crear_cliente() -> None:
    v = comun.version("cliente")
    try:
        cliente = admin.crear_cliente(_repo(), st.session_state[f"nc_nombre_{v}"], st.session_state[f"nc_tel_{v}"])
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Cliente {cliente.nombre} registrado ({cliente.id_cliente}).")
        comun.reiniciar("cliente")


def nuevo_cliente() -> None:
    v = comun.version("cliente")
    with st.container(border=True):
        st.text_input("Nombre completo", key=f"nc_nombre_{v}", placeholder="Ej.: Ana Torres")
        st.text_input("Teléfono (opcional)", key=f"nc_tel_{v}", placeholder="900 000 000", help=AYUDA_TELEFONO)
        st.button("Registrar cliente", type="primary", icon=":material/person_add:", on_click=_crear_cliente)


def _guardar_cliente(id_cliente: str) -> None:
    v = comun.version("cliente_ed")
    try:
        cliente = admin.editar_cliente(
            _repo(), id_cliente, st.session_state[f"ec_nombre_{id_cliente}_{v}"], st.session_state[f"ec_tel_{id_cliente}_{v}"]
        )
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Datos de {cliente.nombre} actualizados.")
        comun.reiniciar("cliente_ed")


def _eliminar_cliente(id_cliente: str, nombre: str) -> None:
    try:
        admin.eliminar_cliente(_repo(), id_cliente)
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Cliente {nombre} eliminado.")
        st.session_state.pop("editar_cliente_sel", None)
    st.session_state.pop(f"conf_del_cliente_{id_cliente}", None)


def editar_cliente(datos) -> None:
    if not datos.clientes:
        st.info("Aún no hay clientes para editar.", icon=":material/info:")
        return
    por_id = {c.id_cliente: c for c in datos.clientes}
    elegido = st.selectbox("Cliente", list(por_id), format_func=lambda i: por_id[i].nombre, key="editar_cliente_sel")
    cliente = por_id[elegido]
    v = comun.version("cliente_ed")
    with st.container(border=True):
        st.text_input("Nombre completo", value=cliente.nombre, key=f"ec_nombre_{elegido}_{v}")
        st.text_input("Teléfono", value=cliente.telefono, key=f"ec_tel_{elegido}_{v}", help=AYUDA_TELEFONO)
        st.button(
            "Guardar cambios", type="primary", icon=":material/save:", on_click=_guardar_cliente, args=(elegido,), key=f"guardar_cliente_{elegido}"
        )
    with st.expander("Eliminar este cliente", icon=":material/delete:"):
        st.caption("Solo se pueden eliminar clientes que no tengan ventas registradas.")
        confirmar = st.checkbox(f"Confirmo que quiero eliminar a {cliente.nombre}", key=f"conf_del_cliente_{elegido}")
        st.button(
            "Eliminar cliente",
            disabled=not confirmar,
            on_click=_eliminar_cliente,
            args=(elegido, cliente.nombre),
            key=f"eliminar_cliente_{elegido}",
        )


# =====================================================================
# Productos
# =====================================================================
def pagina_productos() -> None:
    _titulo(
        "productos",
        "Productos",
        "El catálogo y lo que más se vende. Cambiar un precio no altera las ventas ya registradas.",
    )
    datos = comun.datos()
    catalogo, nuevo, editar = st.tabs(["Catálogo", "Nuevo producto", "Editar o eliminar"])
    with catalogo:
        lista_productos(datos)
    with nuevo:
        nuevo_producto(datos)
    with editar:
        editar_producto(datos)


def lista_productos(datos) -> None:
    if not datos.productos:
        st.info("Aún no hay productos. Registra el primero en la pestaña «Nuevo producto».", icon=":material/info:")
        return
    df = analisis.dataframe_ventas(datos)
    unidades = df.groupby("id_producto")["cantidad"].sum() if not df.empty else pd.Series(dtype=int)
    ingresos = df.groupby("id_producto")["monto"].sum() if not df.empty else pd.Series(dtype=float)
    vigentes = ofertas_vigentes(comun.ofertas(), comun.fecha_referencia())
    buscar = st.text_input("Buscar", placeholder="Buscar por nombre", label_visibility="collapsed", key="buscar_producto")
    filas = [
        {
            "Producto": p.nombre,
            "Categoría": nombre_categoria(p.categoria),
            "Precio actual": p.precio,
            "Oferta": (
                f"-{vigentes[p.id_producto].porcentaje} % hasta el {vigentes[p.id_producto].hasta:%d/%m/%Y}"
                if p.id_producto in vigentes
                else ""
            ),
            "Precio con oferta": vigentes[p.id_producto].precio(p.precio) if p.id_producto in vigentes else p.precio,
            "Unidades vendidas": int(unidades.get(p.id_producto, 0)),
            "Ingresos": float(ingresos.get(p.id_producto, 0.0)),
        }
        for p in datos.productos
        if buscar.strip().lower() in p.nombre.lower()
    ]
    st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        column_config={
            "Precio actual": st.column_config.NumberColumn(format="S/ %.2f"),
            "Oferta": st.column_config.TextColumn(help="Oferta vigente a la fecha de referencia. Se gestiona en Asesoría › Ofertas de temporada."),
            "Precio con oferta": st.column_config.NumberColumn(format="S/ %.2f"),
            "Unidades vendidas": st.column_config.NumberColumn(format="%d"),
            "Ingresos": st.column_config.NumberColumn(format="S/ %.2f"),
        },
    )
    st.caption(f"{len(filas)} de {len(datos.productos)} productos.")


def selector_categoria(datos, clave: str, actual: str | None = None) -> None:
    """Lista de categorías existentes más la opción de crear una nueva."""
    existentes = sorted({p.categoria for p in datos.productos})
    indice = existentes.index(actual) if actual in existentes else 0
    elegida = st.selectbox(
        "Categoría",
        [*existentes, NUEVA_CATEGORIA],
        index=indice,
        format_func=lambda c: c if c == NUEVA_CATEGORIA else nombre_categoria(c),
        key=f"{clave}_cat",
    )
    if elegida == NUEVA_CATEGORIA:
        st.text_input(
            "Nombre de la categoría nueva",
            key=f"{clave}_cat_nueva",
            placeholder="Ej.: Impresión",
            help="Se guarda sin tildes ni espacios (por ejemplo, «Impresión 3D» queda como impresion_3d).",
        )


def categoria_elegida(clave: str) -> str:
    elegida = st.session_state[f"{clave}_cat"]
    return st.session_state.get(f"{clave}_cat_nueva", "") if elegida == NUEVA_CATEGORIA else elegida


def _crear_producto() -> None:
    v = comun.version("producto")
    clave = f"np_{v}"
    try:
        producto = admin.crear_producto(
            _repo(), st.session_state[f"{clave}_nombre"], categoria_elegida(clave), st.session_state[f"{clave}_precio"]
        )
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Producto {producto.nombre} registrado ({producto.id_producto}).")
        comun.reiniciar("producto")


def nuevo_producto(datos) -> None:
    clave = f"np_{comun.version('producto')}"
    with st.container(border=True):
        st.text_input("Nombre del producto", key=f"{clave}_nombre", placeholder="Ej.: Impresora láser")
        selector_categoria(datos, clave)
        st.number_input("Precio (S/)", min_value=0.01, value=50.0, step=1.0, format="%.2f", key=f"{clave}_precio")
        st.button("Registrar producto", type="primary", icon=":material/add_box:", on_click=_crear_producto)


def _guardar_producto(id_producto: str) -> None:
    clave = f"ep_{id_producto}_{comun.version('producto_ed')}"
    try:
        producto = admin.editar_producto(
            _repo(), id_producto, st.session_state[f"{clave}_nombre"], categoria_elegida(clave), st.session_state[f"{clave}_precio"]
        )
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Producto {producto.nombre} actualizado.")
        comun.reiniciar("producto_ed")


def _eliminar_producto(id_producto: str, nombre: str) -> None:
    try:
        admin.eliminar_producto(_repo(), id_producto)
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Producto {nombre} eliminado.")
        st.session_state.pop("editar_producto_sel", None)
    st.session_state.pop(f"conf_del_producto_{id_producto}", None)


def editar_producto(datos) -> None:
    if not datos.productos:
        st.info("Aún no hay productos para editar.", icon=":material/info:")
        return
    por_id = {p.id_producto: p for p in datos.productos}
    elegido = st.selectbox("Producto", list(por_id), format_func=lambda i: por_id[i].nombre, key="editar_producto_sel")
    producto = por_id[elegido]
    clave = f"ep_{elegido}_{comun.version('producto_ed')}"
    with st.container(border=True):
        st.text_input("Nombre del producto", value=producto.nombre, key=f"{clave}_nombre")
        selector_categoria(datos, clave, actual=producto.categoria)
        st.number_input("Precio (S/)", min_value=0.01, value=float(producto.precio), step=1.0, format="%.2f", key=f"{clave}_precio")
        st.caption("Cambiar el precio no altera las ventas ya registradas: cada venta conserva el precio con que se hizo.")
        st.button(
            "Guardar cambios", type="primary", icon=":material/save:", on_click=_guardar_producto, args=(elegido,), key=f"guardar_producto_{elegido}"
        )
    with st.expander("Eliminar este producto", icon=":material/delete:"):
        st.caption("Solo se pueden eliminar productos que no tengan ventas registradas.")
        confirmar = st.checkbox(f"Confirmo que quiero eliminar {producto.nombre}", key=f"conf_del_producto_{elegido}")
        st.button(
            "Eliminar producto",
            disabled=not confirmar,
            on_click=_eliminar_producto,
            args=(elegido, producto.nombre),
            key=f"eliminar_producto_{elegido}",
        )


# =====================================================================
# Ventas
# =====================================================================
def pagina_ventas() -> None:
    _titulo(
        "ventas",
        "Ventas",
        "Registra una venta y la agenda se recalcula al instante; consulta, filtra y anula desde el historial.",
    )
    datos, hoy = comun.datos(), comun.fecha_referencia()
    registrar, historial = st.tabs(["Registrar venta", "Historial"])
    with registrar:
        formulario_venta(datos, hoy)
    with historial:
        historial_ventas(datos)


def _registrar_venta(hoy) -> None:
    v = comun.version("venta")
    repo = _repo()
    id_cliente = st.session_state[f"venta_cliente_{v}"]
    id_producto = st.session_state[f"venta_producto_{v}"]
    try:
        motor, candado = comun.motor_y_candado()
        with candado:
            antes = acciones_por_cliente(repo.cargar_todo(), hoy, motor)
        venta = admin.registrar_venta(
            repo,
            id_cliente,
            id_producto,
            int(st.session_state[f"venta_cantidad_{v}"]),
            st.session_state[f"venta_fecha_{v}_{hoy}"],
            st.session_state[f"venta_precio_{v}_{id_producto}"],
        )
        datos = repo.cargar_todo()
        with candado:
            despues = acciones_por_cliente(datos, hoy, motor)
    except ValueError as error:
        comun.avisar("error", str(error))
        return
    nombre = next(c.nombre for c in datos.clientes if c.id_cliente == id_cliente)
    cambio = describir_cambio_agenda(nombre, antes.get(id_cliente), despues.get(id_cliente))
    comun.avisar("exito", f"Venta {venta.id_venta} registrada por {dinero(venta.monto)}. {cambio}")
    comun.reiniciar("venta")


def formulario_venta(datos, hoy) -> None:
    if not datos.clientes or not datos.productos:
        st.info("Para registrar una venta primero necesitas al menos un cliente y un producto.", icon=":material/info:")
        return
    if not comun.fecha_valida(datos, hoy):
        return
    clientes = {c.id_cliente: c for c in datos.clientes}
    productos = {p.id_producto: p for p in datos.productos}
    v = comun.version("venta")
    with st.container(border=True):
        izquierda, derecha = st.columns(2)
        izquierda.selectbox("Cliente", list(clientes), format_func=lambda i: clientes[i].nombre, key=f"venta_cliente_{v}")
        id_producto = derecha.selectbox(
            "Producto",
            list(productos),
            format_func=lambda i: f"{productos[i].nombre} · {dinero(productos[i].precio)}",
            key=f"venta_producto_{v}",
        )
        c1, c2, c3 = st.columns(3)
        cantidad = c1.number_input("Cantidad", min_value=1, value=1, step=1, key=f"venta_cantidad_{v}")
        precio = c2.number_input(
            "Precio unitario (S/)",
            min_value=0.01,
            value=float(productos[id_producto].precio),
            step=1.0,
            format="%.2f",
            key=f"venta_precio_{v}_{id_producto}",
            help="Por defecto es el precio actual del producto; puedes cambiarlo para esta venta.",
        )
        c3.date_input(
            "Fecha", value=hoy, max_value=hoy, format="DD/MM/YYYY", key=f"venta_fecha_{v}_{hoy}", help="No puede ser posterior a la fecha de referencia."
        )
        st.markdown(f"**Total de la venta: {dinero(cantidad * precio)}**")
        st.button("Registrar venta", type="primary", icon=":material/add_circle:", on_click=_registrar_venta, args=(hoy,))
    st.caption("Al registrar la venta, la agenda se recalcula y verás qué cambió para ese cliente.")


def _anular_venta(id_venta: str) -> None:
    try:
        admin.anular_venta(_repo(), id_venta)
    except ValueError as error:
        comun.avisar("error", str(error))
    else:
        comun.avisar("exito", f"Venta {id_venta} anulada.")
        st.session_state.pop("anular_venta_sel", None)
    st.session_state.pop("conf_anular_venta", None)


def historial_ventas(datos) -> None:
    if not datos.ventas:
        st.info("Aún no hay ventas registradas.", icon=":material/info:")
        return
    df = analisis.dataframe_ventas(datos)
    izquierda, derecha = st.columns(2)
    cliente = izquierda.selectbox("Cliente", ["Todos", *sorted(df["cliente"].unique())], key="filtro_venta_cliente")
    categoria = derecha.selectbox(
        "Categoría", ["Todas", *sorted(df["categoria"].unique())], format_func=lambda c: c if c == "Todas" else nombre_categoria(c), key="filtro_venta_categoria"
    )
    filtrado = df
    if cliente != "Todos":
        filtrado = filtrado[filtrado["cliente"] == cliente]
    if categoria != "Todas":
        filtrado = filtrado[filtrado["categoria"] == categoria]
    filtrado = filtrado.sort_values(["fecha", "id_venta"], ascending=False)
    tabla = filtrado[["id_venta", "fecha", "cliente", "producto", "cantidad", "precio_unitario", "monto"]]
    st.dataframe(
        tabla,
        hide_index=True,
        column_config={
            "id_venta": st.column_config.TextColumn("N.º"),
            "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "cliente": st.column_config.TextColumn("Cliente"),
            "producto": st.column_config.TextColumn("Producto"),
            "cantidad": st.column_config.NumberColumn("Cant.", format="%d"),
            "precio_unitario": st.column_config.NumberColumn("Precio unit.", format="S/ %.2f"),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f"),
        },
    )
    st.caption(f"{len(filtrado)} ventas por {dinero(float(filtrado['monto'].sum()))}.")
    st.download_button(
        "Descargar esta tabla (CSV)", analisis.a_csv(tabla), file_name="historial_ventas.csv", mime="text/csv", icon=":material/download:"
    )
    anular_venta(datos)


def anular_venta(datos) -> None:
    clientes = {c.id_cliente: c.nombre for c in datos.clientes}
    productos = {p.id_producto: p.nombre for p in datos.productos}
    recientes = {v.id_venta: v for v in reversed(datos.ventas[-30:])}
    with st.expander("Anular una venta", icon=":material/undo:"):
        st.caption("Úsalo para corregir un error de registro (se muestran las 30 más recientes). No se puede deshacer.")
        elegida = st.selectbox(
            "Venta",
            list(recientes),
            format_func=lambda i: (
                f"{i} · {recientes[i].fecha:%d/%m/%Y} · {clientes[recientes[i].id_cliente]} · {productos[recientes[i].id_producto]}"
            ),
            key="anular_venta_sel",
        )
        confirmar = st.checkbox("Confirmo que quiero anular esta venta", key="conf_anular_venta")
        st.button("Anular venta", disabled=not confirmar, on_click=_anular_venta, args=(elegida,), key="boton_anular_venta")
