from datetime import date
from pathlib import Path

import pytest

from ventas.administracion import (
    anular_venta,
    asegurar_datos,
    crear_cliente,
    crear_producto,
    editar_cliente,
    editar_producto,
    eliminar_cliente,
    eliminar_producto,
    limpiar_nombre,
    normalizar_categoria,
    normalizar_telefono,
    registrar_venta,
    sembrar,
)
from ventas.cargador import ErrorDatos, cargar_todo
from ventas.logico import PuenteProlog
from ventas.repositorio import RepositorioSQLite
from ventas.servicio import construir_tarjetas

DATOS = Path(__file__).resolve().parent / "datos"
HOY = date(2026, 10, 5)


@pytest.fixture
def repo():
    r = RepositorioSQLite()
    sembrar(r, DATOS)
    yield r
    r.cerrar()


@pytest.fixture
def vacio():
    r = RepositorioSQLite()
    yield r
    r.cerrar()


# =====================================================================
# Normalización (funciones puras)
# =====================================================================
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("Juan", "Juan"), ("  Juan   Pérez ", "Juan Pérez"), ("Ana\tRíos\n", "Ana Ríos"), ("María  José  Núñez", "María José Núñez")],
)
def test_limpiar_nombre(texto, esperado):
    assert limpiar_nombre(texto) == esperado


@pytest.mark.parametrize("texto", ["", "   ", "\t\n"])
def test_nombre_vacio(texto):
    with pytest.raises(ValueError, match="no puede estar vacío"):
        limpiar_nombre(texto)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("51900000001", "51900000001"),
        ("+51 900 000 001", "51900000001"),
        ("(51) 900-000-001", "51900000001"),
        ("900 000 001", "51900000001"),  # celular local: se agrega el código de país
        ("900000001", "51900000001"),
        ("  ", ""),
        ("", ""),
        ("12125550123", "12125550123"),
        ("+1 212 555 0123", "12125550123"),
    ],
)
def test_normalizar_telefono(texto, esperado):
    assert normalizar_telefono(texto) == esperado


@pytest.mark.parametrize("texto", ["abc", "51 9000 abc", "123", "051900000001", "9" * 16])
def test_telefono_invalido(texto):
    with pytest.raises(ValueError, match="Teléfono inválido"):
        normalizar_telefono(texto)


def test_codigo_de_pais_configurable():
    assert normalizar_telefono("900000001", codigo_pais="57") == "57900000001"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Periféricos", "perifericos"),
        ("  Cómputo  ", "computo"),
        ("Audio y video", "audio_y_video"),
        ("ñandú", "nandu"),
        ("ACCESORIOS", "accesorios"),
        ("Cables-USB", "cables_usb"),
        ("3D", "cat_3d"),
        ("¡Ofertas!", "ofertas"),
    ],
)
def test_normalizar_categoria(texto, esperado):
    assert normalizar_categoria(texto) == esperado


@pytest.mark.parametrize("texto", ["", "   ", "!!!", "¿?"])
def test_categoria_vacia(texto):
    with pytest.raises(ValueError, match="categoría"):
        normalizar_categoria(texto)


# =====================================================================
# Clientes
# =====================================================================
def test_crear_cliente_genera_el_siguiente_id(repo):
    nuevo = crear_cliente(repo, "  Sofía   Paredes ", "900 111 222")
    assert (nuevo.id_cliente, nuevo.nombre, nuevo.telefono) == ("c009", "Sofía Paredes", "51900111222")
    assert nuevo in repo.cargar_todo().clientes


def test_crear_cliente_sin_telefono(vacio):
    assert crear_cliente(vacio, "Ana").telefono == ""


def test_crear_cliente_con_datos_invalidos_no_guarda_nada(repo):
    with pytest.raises(ValueError):
        crear_cliente(repo, "", "900111222")
    with pytest.raises(ValueError):
        crear_cliente(repo, "Ana", "abc")
    assert len(repo.cargar_todo().clientes) == 8


def test_ids_consecutivos(vacio):
    ids = [crear_cliente(vacio, f"Cliente {i}").id_cliente for i in range(3)]
    assert ids == ["c001", "c002", "c003"]


def test_editar_cliente(repo):
    editado = editar_cliente(repo, "c006", "Rosa Chávez Díaz", "+51 900 000 066")
    assert (editado.nombre, editado.telefono) == ("Rosa Chávez Díaz", "51900000066")
    leido = next(c for c in repo.cargar_todo().clientes if c.id_cliente == "c006")
    assert leido == editado


def test_editar_cliente_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el cliente c999"):
        editar_cliente(repo, "c999", "X")


def test_editar_cliente_con_telefono_invalido_no_cambia_nada(repo):
    antes = repo.cargar_todo()
    with pytest.raises(ValueError):
        editar_cliente(repo, "c001", "Juan", "xyz")
    assert repo.cargar_todo() == antes


def test_eliminar_cliente_sin_ventas(repo):
    eliminar_cliente(repo, "c006")
    assert len(repo.cargar_todo().clientes) == 7


def test_eliminar_cliente_con_ventas_se_rechaza(repo):
    with pytest.raises(ErrorDatos, match="tiene 4 ventas"):
        eliminar_cliente(repo, "c001")


# =====================================================================
# Productos
# =====================================================================
def test_crear_producto_normaliza_la_categoria(repo):
    nuevo = crear_producto(repo, " Impresora  láser ", "Impresión", 450.5)
    assert (nuevo.id_producto, nuevo.nombre, nuevo.categoria, nuevo.precio) == ("p011", "Impresora láser", "impresion", 450.5)


def test_crear_producto_redondea_a_centavos(vacio):
    assert crear_producto(vacio, "X", "cat", 19.999).precio == 20.0


@pytest.mark.parametrize("precio", [0, -5, 0.001])
def test_crear_producto_con_precio_invalido(vacio, precio):
    with pytest.raises(ValueError):
        crear_producto(vacio, "X", "cat", precio)
    assert vacio.cargar_todo().productos == ()


def test_editar_producto(repo):
    editado = editar_producto(repo, "p002", "Mouse inalámbrico", "Periféricos", 49.9)
    assert (editado.categoria, editado.precio) == ("perifericos", 49.9)


def test_editar_producto_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el producto p999"):
        editar_producto(repo, "p999", "X", "cat", 1)


def test_eliminar_producto_sin_ventas(repo):
    nuevo = crear_producto(repo, "Cable", "Cables", 10)
    eliminar_producto(repo, nuevo.id_producto)
    assert nuevo not in repo.cargar_todo().productos


def test_eliminar_producto_con_ventas_se_rechaza(repo):
    with pytest.raises(ErrorDatos, match="tiene"):
        eliminar_producto(repo, "p002")


# =====================================================================
# Ventas
# =====================================================================
def test_registrar_venta_usa_el_precio_actual_del_producto(repo):
    venta = registrar_venta(repo, "c006", "p002", 2, HOY)
    assert (venta.id_venta, venta.precio_unitario, venta.monto) == ("v031", 45.0, 90.0)
    assert repo.cargar_todo().ventas[-1] == venta


def test_registrar_venta_con_precio_distinto(repo):
    venta = registrar_venta(repo, "c006", "p001", 1, HOY, precio_unitario=2300.456)
    assert venta.precio_unitario == 2300.46


def test_registrar_venta_cliente_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el cliente c999"):
        registrar_venta(repo, "c999", "p002", 1, HOY)


def test_registrar_venta_producto_inexistente(repo):
    with pytest.raises(ErrorDatos, match="No existe el producto p999"):
        registrar_venta(repo, "c001", "p999", 1, HOY)


@pytest.mark.parametrize("cantidad", [0, -1, 1.5])
def test_registrar_venta_con_cantidad_invalida(repo, cantidad):
    with pytest.raises(ValueError):
        registrar_venta(repo, "c001", "p002", cantidad, HOY)
    assert len(repo.cargar_todo().ventas) == 30


def test_registrar_venta_con_fecha_invalida(repo):
    with pytest.raises(ValueError, match="fecha"):
        registrar_venta(repo, "c001", "p002", 1, "2026-10-05")


def test_registrar_venta_con_precio_cero(repo):
    with pytest.raises(ValueError):
        registrar_venta(repo, "c001", "p002", 1, HOY, precio_unitario=0)


def test_cambiar_el_precio_despues_no_cambia_la_venta_ya_registrada(repo):
    venta = registrar_venta(repo, "c006", "p002", 1, HOY)
    editar_producto(repo, "p002", "Mouse inalámbrico", "perifericos", 99.0)
    guardada = next(v for v in repo.cargar_todo().ventas if v.id_venta == venta.id_venta)
    assert guardada.precio_unitario == 45.0


def test_anular_venta(repo):
    anular_venta(repo, "v030")
    assert len(repo.cargar_todo().ventas) == 29
    with pytest.raises(ErrorDatos):
        anular_venta(repo, "v030")


def test_se_puede_eliminar_un_cliente_cuando_se_anulan_sus_ventas(repo):
    registrar_venta(repo, "c006", "p002", 1, HOY)
    with pytest.raises(ErrorDatos):
        eliminar_cliente(repo, "c006")
    anular_venta(repo, "v031")
    eliminar_cliente(repo, "c006")
    assert len(repo.cargar_todo().clientes) == 7


# =====================================================================
# Datos de ejemplo
# =====================================================================
def test_sembrar_restaura_el_estado_original(repo):
    crear_cliente(repo, "Nuevo")
    registrar_venta(repo, "c006", "p002", 1, HOY)
    sembrar(repo, DATOS)
    assert repo.cargar_todo() == cargar_todo(DATOS)


def test_sembrar_con_archivos_danados_no_borra_lo_existente(repo, tmp_path):
    antes = repo.cargar_todo()
    for nombre in ("clientes.csv", "productos.csv"):
        (tmp_path / nombre).write_text((DATOS / nombre).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "ventas.csv").write_text(
        "id_venta,id_cliente,id_producto,cantidad,precio_unitario,fecha\nv001,c001,p001,dos,10,2026-09-01\n", encoding="utf-8"
    )
    with pytest.raises(ErrorDatos):
        sembrar(repo, tmp_path)
    assert repo.cargar_todo() == antes


def test_asegurar_datos_solo_siembra_si_esta_vacio(vacio):
    assert asegurar_datos(vacio, DATOS) is True
    assert asegurar_datos(vacio, DATOS) is False
    crear_cliente(vacio, "Extra")
    assert asegurar_datos(vacio, DATOS) is False
    assert len(vacio.cargar_todo().clientes) == 9


# =====================================================================
# Integración: lo que se registra en administración cambia la asesoría
# =====================================================================
def test_registrar_una_venta_cambia_la_agenda():
    repo = RepositorioSQLite()
    sembrar(repo, DATOS)
    motor = PuenteProlog()
    antes = {t.cliente.id_cliente: t.entrada.accion.tipo for t in construir_tarjetas(repo.cargar_todo(), HOY, motor)}
    assert antes["c001"] == "reactivar"  # Juan lleva 40 días sin comprar

    registrar_venta(repo, "c001", "p009", 1, HOY)

    despues = {t.cliente.id_cliente: t.entrada.accion.tipo for t in construir_tarjetas(repo.cargar_todo(), HOY, motor)}
    assert despues["c001"] == "fidelizar"  # ya compró hoy
    repo.cerrar()


def test_un_cliente_nuevo_sin_compras_no_aparece_en_la_agenda(repo):
    motor = PuenteProlog()
    nuevo = crear_cliente(repo, "Recién llegado")
    ids = [t.cliente.id_cliente for t in construir_tarjetas(repo.cargar_todo(), HOY, motor)]
    assert nuevo.id_cliente not in ids


def test_la_primera_compra_de_un_cliente_nuevo_lo_incorpora_a_la_agenda(repo):
    motor = PuenteProlog()
    nuevo = crear_cliente(repo, "Recién llegado")
    registrar_venta(repo, nuevo.id_cliente, "p002", 1, date(2026, 10, 4))
    tarjetas = construir_tarjetas(repo.cargar_todo(), HOY, motor)
    tarjeta = next(t for t in tarjetas if t.cliente.id_cliente == nuevo.id_cliente)
    assert tarjeta.entrada.accion.tipo == "cruzar"  # compra poco; se le ofrece lo que llevaron otros


def test_un_producto_nuevo_se_puede_recomendar_tras_venderse(repo):
    nuevo = crear_producto(repo, "Cable HDMI", "Cables", 25)
    for cliente in ("c001", "c002"):
        registrar_venta(repo, cliente, nuevo.id_producto, 1, HOY)
    motor = PuenteProlog()
    tarjetas = construir_tarjetas(repo.cargar_todo(), HOY, motor)
    recomendados = {r.id_producto for t in tarjetas for r in t.recomendaciones}
    assert nuevo.id_producto in recomendados
