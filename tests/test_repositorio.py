import threading
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from ventas.cargador import Datos, ErrorDatos, cargar_todo
from ventas.combos import Combo
from ventas.modelos import ClienteRegular, Producto, Venta
from ventas.ofertas import Oferta
from ventas.repositorio import Repositorio, RepositorioSQLite

DATOS = Path(__file__).resolve().parent / "datos"


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


@pytest.fixture
def repo():
    r = RepositorioSQLite()
    yield r
    r.cerrar()


@pytest.fixture
def repo_con_datos(repo, datos):
    repo.reemplazar_todo(datos)
    return repo


def venta(id_venta="v900", cliente="c001", producto="p001", cantidad=1, precio=10.0, dia=1):
    return Venta(id_venta, cliente, producto, cantidad, precio, date(2026, 9, dia))


# =====================================================================
# Contrato y estado inicial
# =====================================================================
def test_el_contrato_es_abstracto():
    with pytest.raises(TypeError):
        Repositorio()


def test_implementa_el_contrato(repo):
    assert isinstance(repo, Repositorio)


def test_repositorio_nuevo_esta_vacio(repo):
    assert repo.esta_vacio()
    assert repo.cargar_todo() == Datos((), (), ())


def test_con_datos_ya_no_esta_vacio(repo_con_datos):
    assert not repo_con_datos.esta_vacio()


def test_con_un_solo_cliente_tampoco_esta_vacio(repo):
    repo.agregar_cliente(ClienteRegular("c001", "Juan"))
    assert not repo.esta_vacio()


# =====================================================================
# Ida y vuelta
# =====================================================================
def test_ida_y_vuelta_identica_al_csv(repo_con_datos, datos):
    assert repo_con_datos.cargar_todo() == datos


def test_conserva_el_orden_de_insercion(repo_con_datos, datos):
    leidos = repo_con_datos.cargar_todo()
    assert [v.id_venta for v in leidos.ventas] == [v.id_venta for v in datos.ventas]
    assert [c.id_cliente for c in leidos.clientes] == [c.id_cliente for c in datos.clientes]


def test_devuelve_tuplas_inmutables(repo_con_datos):
    leidos = repo_con_datos.cargar_todo()
    assert all(isinstance(t, tuple) for t in (leidos.clientes, leidos.productos, leidos.ventas))


@pytest.mark.parametrize("precio", [0.01, 0.1, 0.29, 0.57, 19.99, 45.5, 123.45, 2400.0, 99999.99])
def test_los_precios_con_centavos_no_pierden_exactitud(repo, precio):
    repo.agregar_producto(Producto("p001", "Algo", "cat", precio))
    assert repo.cargar_todo().productos[0].precio == precio


def test_acepta_acentos_y_caracteres_especiales(repo):
    repo.agregar_cliente(ClienteRegular("c001", "María Núñez & Hijos 'ñandú' 🙂", "51900000001"))
    assert repo.cargar_todo().clientes[0].nombre == "María Núñez & Hijos 'ñandú' 🙂"


def test_los_datos_persisten_en_un_archivo(tmp_path, datos):
    ruta = str(tmp_path / "asesor.db")
    primero = RepositorioSQLite(ruta)
    primero.reemplazar_todo(datos)
    primero.cerrar()
    segundo = RepositorioSQLite(ruta)
    try:
        assert segundo.cargar_todo() == datos
    finally:
        segundo.cerrar()


# =====================================================================
# Identificadores
# =====================================================================
def test_primer_id_de_cada_tipo(repo):
    assert [repo.siguiente_id(p) for p in "cpv"] == ["c001", "p001", "v001"]


def test_siguiente_id_sigue_al_mayor_existente(repo_con_datos):
    assert [repo_con_datos.siguiente_id(p) for p in "cpv"] == ["c009", "p011", "v031"]


def test_siguiente_id_con_huecos_no_reutiliza(repo):
    for i in ("c001", "c005"):
        repo.agregar_cliente(ClienteRegular(i, "X"))
    assert repo.siguiente_id("c") == "c006"


def test_siguiente_id_sigue_al_mayor_que_queda_tras_eliminar(repo):
    for i in ("c001", "c002"):
        repo.agregar_cliente(ClienteRegular(i, "X"))
    repo.eliminar_cliente("c002")
    assert repo.siguiente_id("c") == "c002"  # el mayor existente es c001


def test_siguiente_id_pasa_de_mil(repo):
    repo.agregar_cliente(ClienteRegular("c999", "X"))
    assert repo.siguiente_id("c") == "c1000"


def test_siguiente_id_ignora_ids_con_otro_formato(repo):
    repo.agregar_cliente(ClienteRegular("cliente_especial", "X"))
    assert repo.siguiente_id("c") == "c001"


@pytest.mark.parametrize("malo", ["x", "", "cc", "C"])
def test_prefijo_desconocido(repo, malo):
    with pytest.raises(ValueError):
        repo.siguiente_id(malo)


# =====================================================================
# Clientes
# =====================================================================
def test_agregar_y_actualizar_cliente(repo):
    repo.agregar_cliente(ClienteRegular("c001", "Juan", ""))
    repo.actualizar_cliente(ClienteRegular("c001", "Juan Pérez", "51900000001"))
    (cliente,) = repo.cargar_todo().clientes
    assert (cliente.nombre, cliente.telefono) == ("Juan Pérez", "51900000001")


def test_cliente_duplicado(repo):
    repo.agregar_cliente(ClienteRegular("c001", "Juan"))
    with pytest.raises(ErrorDatos, match="Ya existe el cliente c001"):
        repo.agregar_cliente(ClienteRegular("c001", "Otro"))
    assert len(repo.cargar_todo().clientes) == 1


def test_actualizar_cliente_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el cliente c999"):
        repo.actualizar_cliente(ClienteRegular("c999", "X"))


def test_eliminar_cliente_sin_ventas(repo_con_datos):
    repo_con_datos.eliminar_cliente("c006")  # Rosa no tiene compras
    assert "c006" not in {c.id_cliente for c in repo_con_datos.cargar_todo().clientes}


def test_no_se_elimina_un_cliente_con_ventas(repo_con_datos, datos):
    with pytest.raises(ErrorDatos, match="tiene 4 ventas registradas"):
        repo_con_datos.eliminar_cliente("c001")
    assert repo_con_datos.cargar_todo() == datos


def test_mensaje_en_singular_con_una_sola_venta(repo):
    repo.agregar_cliente(ClienteRegular("c001", "Juan"))
    repo.agregar_producto(Producto("p001", "Algo", "cat", 10.0))
    repo.agregar_venta(venta())
    with pytest.raises(ErrorDatos, match="tiene 1 venta registrada"):
        repo.eliminar_cliente("c001")


def test_eliminar_cliente_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el cliente c999"):
        repo.eliminar_cliente("c999")


# =====================================================================
# Productos
# =====================================================================
def test_agregar_y_actualizar_producto(repo):
    repo.agregar_producto(Producto("p001", "Mouse", "perifericos", 45.0))
    repo.actualizar_producto(Producto("p001", "Mouse óptico", "perifericos", 49.9))
    (producto,) = repo.cargar_todo().productos
    assert (producto.nombre, producto.precio) == ("Mouse óptico", 49.9)


def test_producto_duplicado(repo):
    repo.agregar_producto(Producto("p001", "Mouse", "perifericos", 45.0))
    with pytest.raises(ErrorDatos, match="Ya existe el producto p001"):
        repo.agregar_producto(Producto("p001", "Otro", "perifericos", 1.0))


def test_actualizar_producto_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el producto"):
        repo.actualizar_producto(Producto("p999", "X", "cat", 1.0))


def test_cambiar_el_precio_no_altera_las_ventas_pasadas(repo_con_datos):
    antes = repo_con_datos.cargar_todo()
    laptop = next(p for p in antes.productos if p.id_producto == "p001")
    repo_con_datos.actualizar_producto(Producto("p001", laptop.nombre, laptop.categoria, 3000.0))
    despues = repo_con_datos.cargar_todo()
    assert despues.ventas == antes.ventas
    assert next(p for p in despues.productos if p.id_producto == "p001").precio == 3000.0


def test_no_se_elimina_un_producto_con_ventas(repo_con_datos):
    with pytest.raises(ErrorDatos, match="producto p001: tiene 2 ventas registradas"):
        repo_con_datos.eliminar_producto("p001")


def test_eliminar_producto_sin_ventas(repo):
    repo.agregar_producto(Producto("p001", "Mouse", "perifericos", 45.0))
    repo.eliminar_producto("p001")
    assert repo.cargar_todo().productos == ()


def test_eliminar_producto_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el producto p999"):
        repo.eliminar_producto("p999")


# =====================================================================
# Ventas
# =====================================================================
def test_agregar_venta(repo_con_datos):
    repo_con_datos.agregar_venta(venta("v031", "c006", "p002", cantidad=2, precio=45.0))
    ultima = repo_con_datos.cargar_todo().ventas[-1]
    assert (ultima.id_venta, ultima.id_cliente, ultima.cantidad, ultima.monto) == ("v031", "c006", 2, 90.0)


def test_venta_duplicada(repo_con_datos):
    with pytest.raises(ErrorDatos, match="Ya existe la venta v001"):
        repo_con_datos.agregar_venta(venta("v001"))


def test_venta_con_cliente_inexistente(repo_con_datos):
    with pytest.raises(ErrorDatos, match="no existe"):
        repo_con_datos.agregar_venta(venta("v900", cliente="c999"))
    assert len(repo_con_datos.cargar_todo().ventas) == 30


def test_venta_con_producto_inexistente(repo_con_datos):
    with pytest.raises(ErrorDatos, match="no existe"):
        repo_con_datos.agregar_venta(venta("v900", producto="p999"))


def test_eliminar_venta(repo_con_datos):
    repo_con_datos.eliminar_venta("v001")
    ids = [v.id_venta for v in repo_con_datos.cargar_todo().ventas]
    assert len(ids) == 29 and "v001" not in ids


def test_eliminar_venta_inexistente(repo_con_datos):
    with pytest.raises(ErrorDatos, match="No existe la venta v999"):
        repo_con_datos.eliminar_venta("v999")


# =====================================================================
# Reemplazo total (todo o nada)
# =====================================================================
def test_reemplazar_sustituye_todo(repo_con_datos):
    nuevo = Datos((ClienteRegular("c001", "Solo"),), (Producto("p001", "Uno", "cat", 5.0),), ())
    repo_con_datos.reemplazar_todo(nuevo)
    assert repo_con_datos.cargar_todo() == nuevo


def test_reemplazar_con_datos_incoherentes_no_pierde_lo_anterior(repo_con_datos, datos):
    malo = Datos((ClienteRegular("c001", "Solo"),), (Producto("p001", "Uno", "cat", 5.0),), (venta("v1", "c999"),))
    with pytest.raises(ErrorDatos):
        repo_con_datos.reemplazar_todo(malo)
    assert repo_con_datos.cargar_todo() == datos


def test_reemplazar_con_vacio_limpia_todo(repo_con_datos):
    repo_con_datos.reemplazar_todo(Datos((), (), ()))
    assert repo_con_datos.esta_vacio()


# =====================================================================
# Varios hilos (Streamlit atiende cada sesión en un hilo distinto)
# =====================================================================
def test_escrituras_concurrentes_no_se_pierden(repo_con_datos):
    errores = []

    def registrar(n):
        try:
            repo_con_datos.agregar_venta(venta(f"v9{n:02d}", "c006", "p002"))
        except Exception as error:  # pragma: no cover - solo si falla
            errores.append(error)

    hilos = [threading.Thread(target=registrar, args=(n,)) for n in range(20)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    assert len(repo_con_datos.cargar_todo().ventas) == 50


def test_leer_mientras_se_escribe(repo_con_datos):
    resultados = []

    def leer():
        resultados.append(len(repo_con_datos.cargar_todo().ventas))

    hilos = [threading.Thread(target=leer) for _ in range(10)]
    hilos.append(threading.Thread(target=lambda: repo_con_datos.agregar_venta(venta("v950", "c006", "p002"))))
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert all(n in (30, 31) for n in resultados)


# =====================================================================
# Ofertas
# =====================================================================
def test_sin_ofertas_al_empezar(repo_con_datos):
    assert repo_con_datos.cargar_ofertas() == ()


def test_guardar_y_leer_una_oferta(repo_con_datos):
    oferta = Oferta("p002", 15, date(2026, 11, 1), date(2026, 12, 31))
    repo_con_datos.guardar_oferta(oferta)
    assert repo_con_datos.cargar_ofertas() == (oferta,)


def test_guardar_otra_vez_reemplaza_la_oferta_del_producto(repo_con_datos):
    repo_con_datos.guardar_oferta(Oferta("p002", 15, date(2026, 11, 1), date(2026, 12, 31)))
    nueva = Oferta("p002", 30, date(2026, 12, 1), date(2026, 12, 24))
    repo_con_datos.guardar_oferta(nueva)
    assert repo_con_datos.cargar_ofertas() == (nueva,)


def test_eliminar_una_oferta(repo_con_datos):
    repo_con_datos.guardar_oferta(Oferta("p002", 15, date(2026, 11, 1), date(2026, 12, 31)))
    repo_con_datos.eliminar_oferta("p002")
    assert repo_con_datos.cargar_ofertas() == ()
    with pytest.raises(ErrorDatos, match="no tiene oferta"):
        repo_con_datos.eliminar_oferta("p002")


def test_no_se_puede_ofertar_un_producto_inexistente(repo_con_datos):
    with pytest.raises(ErrorDatos, match="no existe"):
        repo_con_datos.guardar_oferta(Oferta("p999", 10, date(2026, 11, 1), date(2026, 11, 2)))


def test_eliminar_el_producto_elimina_su_oferta(repo_con_datos):
    repo_con_datos.agregar_producto(Producto("p100", "Nuevo", "audio", 50.0))
    repo_con_datos.guardar_oferta(Oferta("p100", 10, date(2026, 11, 1), date(2026, 11, 30)))
    repo_con_datos.eliminar_producto("p100")
    assert repo_con_datos.cargar_ofertas() == ()


def test_restablecer_los_datos_borra_las_ofertas(repo_con_datos, datos):
    repo_con_datos.guardar_oferta(Oferta("p002", 15, date(2026, 11, 1), date(2026, 12, 31)))
    repo_con_datos.reemplazar_todo(datos)
    assert repo_con_datos.cargar_ofertas() == ()


def test_una_base_existente_recibe_la_tabla_de_ofertas(tmp_path, datos):
    # Una base creada antes de existir las ofertas: abrirla agrega la tabla sin tocar lo demás.
    ruta = str(tmp_path / "vieja.db")
    viejo = RepositorioSQLite(ruta)
    viejo.reemplazar_todo(datos)
    viejo._con.execute("DROP TABLE ofertas")
    viejo.cerrar()
    reabierto = RepositorioSQLite(ruta)
    assert reabierto.cargar_todo() == datos and reabierto.cargar_ofertas() == ()
    reabierto.cerrar()


# =====================================================================
# Pedidos: estado, descuento y precios fijos
# =====================================================================
def test_guardar_y_leer_un_pedido_enviado(repo_con_datos):
    enviado = Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5), descuento=15, precios=(36.0, 60.0))
    repo_con_datos.agregar_combo(enviado)
    assert repo_con_datos.cargar_combos() == (enviado,)


def test_actualizar_un_pedido(repo_con_datos):
    borrador = Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5))
    repo_con_datos.agregar_combo(borrador)
    enviado = replace(borrador, descuento=5, precios=(45.0, 60.0))
    repo_con_datos.actualizar_combo(enviado)
    assert repo_con_datos.cargar_combos() == (enviado,)
    descartado = replace(enviado, descartado=True)
    repo_con_datos.actualizar_combo(descartado)
    assert repo_con_datos.cargar_combos()[0].estado == "descartado"
    with pytest.raises(ErrorDatos, match="No existe el combo cb999"):
        repo_con_datos.actualizar_combo(replace(borrador, id_combo="cb999"))


def test_una_base_con_propuestas_las_convierte_en_pedidos_enviados(tmp_path, datos):
    import sqlite3

    ruta = str(tmp_path / "vieja.db")
    viejo = RepositorioSQLite(ruta)
    viejo.reemplazar_todo(datos)
    viejo.agregar_combo(Combo("cb001", "c002", ("p002", "p009"), date(2026, 10, 1)))
    viejo.cerrar()
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE propuestas (
            id_cliente TEXT PRIMARY KEY REFERENCES clientes (id_cliente) ON DELETE CASCADE,
            descuento  INTEGER NOT NULL CHECK (descuento BETWEEN 0 AND 90),
            fecha      TEXT NOT NULL
        );
        CREATE TABLE propuesta_productos (
            id_cliente             TEXT NOT NULL REFERENCES propuestas (id_cliente) ON DELETE CASCADE,
            id_producto            TEXT NOT NULL REFERENCES productos (id_producto) ON DELETE CASCADE,
            orden                  INTEGER NOT NULL,
            precio_normal_centavos INTEGER NOT NULL CHECK (precio_normal_centavos > 0),
            precio_centavos        INTEGER NOT NULL CHECK (precio_centavos > 0),
            PRIMARY KEY (id_cliente, id_producto)
        );
        INSERT INTO propuestas VALUES ('c001', 10, '2026-10-04');
        INSERT INTO propuesta_productos VALUES ('c001', 'p009', 1, 6000, 4800), ('c001', 'p002', 0, 4500, 4500);
        """
    )
    con.commit()
    con.close()

    migrado = RepositorioSQLite(ruta)
    assert migrado.cargar_combos() == (
        Combo("cb001", "c002", ("p002", "p009"), date(2026, 10, 1)),
        Combo("cb002", "c001", ("p002", "p009"), date(2026, 10, 4), descuento=10, precios=(45.0, 48.0)),
    )
    tablas = {f[0] for f in migrado._con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tablas & {"propuestas", "propuesta_productos"}
    assert migrado.cargar_todo() == datos
    migrado.cerrar()
    assert len(RepositorioSQLite(ruta).cargar_combos()) == 2  # abrirla otra vez no duplica nada


# =====================================================================
# Combos guardados para pasar a ventas
# =====================================================================
def test_guardar_y_leer_un_combo(repo_con_datos):
    combo = Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5))
    repo_con_datos.agregar_combo(combo)
    assert repo_con_datos.cargar_combos() == (combo,)
    assert repo_con_datos.siguiente_id("cb") == "cb002"


def test_registrar_combo_es_todo_o_nada(repo_con_datos):
    repo_con_datos.agregar_combo(Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5)))
    n = len(repo_con_datos.cargar_todo().ventas)
    repetida = venta(id_venta="v001", producto="p002")  # v001 ya existe
    with pytest.raises(ErrorDatos):
        repo_con_datos.registrar_combo("cb001", (venta(id_venta="v900", producto="p009"), repetida))
    assert len(repo_con_datos.cargar_todo().ventas) == n
    assert repo_con_datos.cargar_combos()[0].pendiente


def test_anular_las_ventas_de_un_combo_lo_deja_pendiente(repo_con_datos):
    repo_con_datos.agregar_combo(Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5)))
    repo_con_datos.registrar_combo("cb001", (venta("v900", producto="p002"), venta("v901", producto="p009")))
    assert repo_con_datos.cargar_combos()[0].ids_ventas == ("v900", "v901")
    repo_con_datos.eliminar_venta("v900")
    repo_con_datos.eliminar_venta("v901")
    assert repo_con_datos.cargar_combos()[0].pendiente


def test_restablecer_los_datos_borra_los_combos(repo_con_datos, datos):
    repo_con_datos.agregar_combo(Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5)))
    repo_con_datos.reemplazar_todo(datos)
    assert repo_con_datos.cargar_combos() == ()


def test_una_base_con_la_tabla_combos_vieja_se_migra_sin_perder_nada(tmp_path, datos):
    # Esquema anterior: combos.id_cliente era obligatorio y no había nombre_cliente.
    import sqlite3

    ruta = str(tmp_path / "vieja.db")
    viejo = RepositorioSQLite(ruta)
    viejo.reemplazar_todo(datos)
    viejo.cerrar()
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA foreign_keys = OFF")
    con.executescript(
        """
        DROP TABLE combos;
        CREATE TABLE combos (
            id_combo   TEXT PRIMARY KEY,
            id_cliente TEXT NOT NULL REFERENCES clientes (id_cliente) ON DELETE CASCADE,
            fecha      TEXT NOT NULL
        );
        INSERT INTO combos VALUES ('cb001', 'c001', '2026-10-05');
        INSERT INTO combo_productos (id_combo, id_producto, orden) VALUES ('cb001', 'p002', 0), ('cb001', 'p009', 1);
        INSERT INTO combo_ventas VALUES ('cb001', 'v001', 0);
        """
    )
    con.commit()
    con.close()

    migrado = RepositorioSQLite(ruta)
    assert migrado.cargar_todo() == datos
    assert migrado.cargar_combos() == (Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5), ("v001",)),)
    # Ya admite clientes no registrados, y las claves foráneas siguen activas.
    migrado.agregar_combo(Combo("cb002", None, ("p002", "p009"), date(2026, 10, 5), nombre_cliente="Pedro"))
    with pytest.raises(ErrorDatos):
        migrado.agregar_combo(Combo("cb003", "c999", ("p002", "p009"), date(2026, 10, 5)))
    migrado.cerrar()
    # Abrirla otra vez no vuelve a migrar ni pierde nada.
    otra_vez = RepositorioSQLite(ruta)
    assert [c.id_combo for c in otra_vez.cargar_combos()] == ["cb001", "cb002"]
    otra_vez.cerrar()


# =====================================================================
# Contactos de la agenda
# =====================================================================
def test_guardar_y_leer_contactos_en_orden(repo_con_datos):
    from ventas.contactos import nuevo_contacto

    primero = nuevo_contacto("c001", date(2026, 11, 1), "no_responde")
    segundo = nuevo_contacto("c001", date(2026, 11, 8), "interesado")
    repo_con_datos.agregar_contacto(primero)
    repo_con_datos.agregar_contacto(segundo)
    assert repo_con_datos.cargar_contactos() == (primero, segundo)


def test_contacto_de_un_cliente_inexistente(repo_con_datos):
    from ventas.contactos import nuevo_contacto

    with pytest.raises(ErrorDatos, match="no existe"):
        repo_con_datos.agregar_contacto(nuevo_contacto("c999", date(2026, 11, 1), "interesado"))


def test_restablecer_los_datos_borra_los_contactos(repo_con_datos, datos):
    from ventas.contactos import nuevo_contacto

    repo_con_datos.agregar_contacto(nuevo_contacto("c001", date(2026, 11, 1), "interesado"))
    repo_con_datos.reemplazar_todo(datos)
    assert repo_con_datos.cargar_contactos() == ()


# =====================================================================
# Costo y stock
# =====================================================================
def con_stock(repo, id_producto, stock, costo=None):
    p = next(p for p in repo.cargar_todo().productos if p.id_producto == id_producto)
    repo.actualizar_producto(Producto(p.id_producto, p.nombre, p.categoria, p.precio, costo=costo, stock=stock))


def stock_de(repo, id_producto):
    return next(p.stock for p in repo.cargar_todo().productos if p.id_producto == id_producto)


def test_guarda_costo_y_stock(repo_con_datos):
    con_stock(repo_con_datos, "p002", 7, costo=30.5)
    p = next(p for p in repo_con_datos.cargar_todo().productos if p.id_producto == "p002")
    assert (p.costo, p.stock) == (30.5, 7)


def test_vender_descuenta_y_anular_devuelve_el_stock(repo_con_datos):
    con_stock(repo_con_datos, "p002", 5)
    repo_con_datos.agregar_venta(venta("v900", producto="p002", cantidad=2))
    assert stock_de(repo_con_datos, "p002") == 3
    repo_con_datos.eliminar_venta("v900")
    assert stock_de(repo_con_datos, "p002") == 5


def test_sin_stock_suficiente_no_se_vende(repo_con_datos):
    con_stock(repo_con_datos, "p002", 1)
    with pytest.raises(ErrorDatos, match="No hay stock suficiente"):
        repo_con_datos.agregar_venta(venta("v900", producto="p002", cantidad=2))
    assert stock_de(repo_con_datos, "p002") == 1
    assert "v900" not in {v.id_venta for v in repo_con_datos.cargar_todo().ventas}


def test_sin_stock_cargado_no_se_controla(repo_con_datos):
    repo_con_datos.agregar_venta(venta("v900", producto="p002", cantidad=50))
    assert stock_de(repo_con_datos, "p002") is None


def test_un_combo_sin_stock_de_un_producto_no_registra_nada(repo_con_datos):
    from ventas.combos import Combo

    repo_con_datos.agregar_combo(Combo("cb001", "c001", ("p002", "p009"), date(2026, 10, 5)))
    con_stock(repo_con_datos, "p002", 3)
    con_stock(repo_con_datos, "p009", 0)
    with pytest.raises(ErrorDatos, match="No hay stock suficiente"):
        repo_con_datos.registrar_combo("cb001", (venta("v900", producto="p002"), venta("v901", producto="p009")))
    assert (stock_de(repo_con_datos, "p002"), stock_de(repo_con_datos, "p009")) == (3, 0)
    assert repo_con_datos.cargar_combos()[0].pendiente


def test_cargar_datos_respeta_el_stock_indicado(repo, datos):
    # El stock del archivo es el actual: las ventas históricas no lo vuelven a descontar.
    productos = tuple(Producto(p.id_producto, p.nombre, p.categoria, p.precio, stock=10) for p in datos.productos)
    repo.reemplazar_todo(type(datos)(datos.clientes, productos, datos.ventas))
    assert {p.stock for p in repo.cargar_todo().productos} == {10}


def test_una_base_sin_costo_ni_stock_se_migra_sin_perder_nada(tmp_path, datos):
    import sqlite3

    ruta = str(tmp_path / "vieja.db")
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE productos (
            id_producto     TEXT PRIMARY KEY,
            nombre          TEXT NOT NULL,
            categoria       TEXT NOT NULL,
            precio_centavos INTEGER NOT NULL CHECK (precio_centavos > 0)
        );
        INSERT INTO productos VALUES ('p001', 'Mouse', 'perifericos', 4500);
        """
    )
    con.commit()
    con.close()
    repo = RepositorioSQLite(ruta)
    assert repo.cargar_todo().productos == (Producto("p001", "Mouse", "perifericos", 45.0),)
    con_stock(repo, "p001", 2, costo=30.0)
    assert stock_de(repo, "p001") == 2
    repo.cerrar()


# =====================================================================
# Migraciones seguras
# =====================================================================
def _base_con_combos_viejos(ruta: str, datos, id_cliente: str = "c001") -> None:
    import sqlite3

    viejo = RepositorioSQLite(ruta)
    viejo.reemplazar_todo(datos)
    viejo.cerrar()
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA foreign_keys = OFF")
    con.executescript(
        f"""
        DROP TABLE combos;
        CREATE TABLE combos (
            id_combo   TEXT PRIMARY KEY,
            id_cliente TEXT NOT NULL REFERENCES clientes (id_cliente) ON DELETE CASCADE,
            fecha      TEXT NOT NULL
        );
        INSERT INTO combos VALUES ('cb001', '{id_cliente}', '2026-10-05');
        INSERT INTO combo_productos (id_combo, id_producto, orden) VALUES ('cb001', 'p002', 0), ('cb001', 'p009', 1);
        """
    )
    con.commit()
    con.close()


def _tablas(ruta: str) -> set[str]:
    import sqlite3

    con = sqlite3.connect(ruta)
    try:
        return {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()


def test_una_migracion_fallida_no_deja_la_base_a_medias(tmp_path, datos):
    import sqlite3

    ruta = str(tmp_path / "rota.db")
    _base_con_combos_viejos(ruta, datos, id_cliente="c999")  # referencia rota: la migración falla
    with pytest.raises(sqlite3.IntegrityError):
        RepositorioSQLite(ruta)
    assert "combos_nuevo" not in _tablas(ruta)
    # Corregido el dato, el siguiente intento migra sin problemas.
    con = sqlite3.connect(ruta)
    con.execute("UPDATE combos SET id_cliente = 'c001'")
    con.commit()
    con.close()
    repo = RepositorioSQLite(ruta)
    assert [c.id_cliente for c in repo.cargar_combos()] == ["c001"]
    repo.cerrar()


def test_antes_de_migrar_se_respalda_la_base(tmp_path, datos):
    ruta = tmp_path / "vieja.db"
    _base_con_combos_viejos(str(ruta), datos)
    RepositorioSQLite(str(ruta)).cerrar()
    respaldos = sorted(tmp_path.glob("vieja-antes-de-migrar-*.db"))
    assert len(respaldos) == 1
    assert "nombre_cliente" not in _columnas(str(respaldos[0]), "combos")  # es la base tal como estaba
    restaurado = RepositorioSQLite(str(respaldos[0]))  # y se puede abrir (y migrar) si hace falta volver
    assert restaurado.cargar_todo() == datos
    restaurado.cerrar()


def test_sin_migraciones_pendientes_no_se_respalda(tmp_path, datos):
    ruta = tmp_path / "al-dia.db"
    repo = RepositorioSQLite(str(ruta))  # base nueva
    repo.reemplazar_todo(datos)
    repo.cerrar()
    RepositorioSQLite(str(ruta)).cerrar()  # ya está al día
    assert list(tmp_path.glob("*antes-de-migrar*")) == []


def _columnas(ruta: str, tabla: str) -> set[str]:
    import sqlite3

    con = sqlite3.connect(ruta)
    try:
        return {f[1] for f in con.execute(f"PRAGMA table_info({tabla})")}
    finally:
        con.close()
