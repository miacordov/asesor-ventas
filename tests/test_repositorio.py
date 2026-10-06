import threading
from datetime import date
from pathlib import Path

import pytest

from ventas.cargador import Datos, ErrorDatos, cargar_todo
from ventas.modelos import ClienteRegular, Producto, Venta
from ventas.repositorio import Repositorio, RepositorioSQLite

DATOS = Path(__file__).resolve().parent.parent / "datos"


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
