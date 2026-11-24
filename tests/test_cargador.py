from datetime import date
from pathlib import Path

import pytest

from ventas.cargador import (
    ErrorDatos,
    cargar_clientes,
    cargar_productos,
    cargar_todo,
    cargar_ventas,
    validar_integridad,
)

DATOS = Path(__file__).resolve().parent / "datos"

CABECERA_CLIENTES = "id_cliente,nombre,telefono\n"
CABECERA_PRODUCTOS = "id_producto,nombre,categoria,precio\n"
CABECERA_VENTAS = "id_venta,id_cliente,id_producto,cantidad,precio_unitario,fecha\n"


def escribir(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# ---------- dataset real del proyecto ----------
def test_dataset_real_carga_completo():
    datos = cargar_todo(DATOS)
    assert len(datos.clientes) == 8
    assert len(datos.productos) == 10
    assert len(datos.ventas) == 30


def test_dataset_real_monto_total():
    datos = cargar_todo(DATOS)
    assert sum(v.monto for v in datos.ventas) == 8455.0


def test_dataset_real_cliente_sin_compras():
    datos = cargar_todo(DATOS)
    con_ventas = {v.id_cliente for v in datos.ventas}
    sin_ventas = {c.id_cliente for c in datos.clientes} - con_ventas
    assert sin_ventas == {"c006"}


def test_dataset_real_precio_historico_distinto_al_actual():
    datos = cargar_todo(DATOS)
    laptop = next(p for p in datos.productos if p.id_producto == "p001")
    venta = next(v for v in datos.ventas if v.id_venta == "v004")
    assert venta.precio_unitario == 2350 and laptop.precio == 2400


def test_dataset_real_devuelve_tuplas_inmutables():
    datos = cargar_todo(DATOS)
    assert isinstance(datos.ventas, tuple)
    with pytest.raises(AttributeError):
        datos.ventas.append(None)


# ---------- lectura correcta ----------
def test_cliente_valido_y_espacios_se_recortan(tmp_path):
    ruta = escribir(tmp_path, "c.csv", CABECERA_CLIENTES + " c001 , Juan Pérez ,51900000001\n")
    (cliente,) = cargar_clientes(ruta)
    assert cliente.id_cliente == "c001"
    assert cliente.nombre == "Juan Pérez"


def test_telefono_vacio_es_valido(tmp_path):
    ruta = escribir(tmp_path, "c.csv", CABECERA_CLIENTES + "c001,Juan,\n")
    assert cargar_clientes(ruta)[0].telefono == ""


def test_archivo_solo_con_cabecera_da_tupla_vacia(tmp_path):
    ruta = escribir(tmp_path, "v.csv", CABECERA_VENTAS)
    assert cargar_ventas(ruta) == ()


def test_archivo_con_bom_de_excel(tmp_path):
    ruta = tmp_path / "c.csv"
    ruta.write_text(CABECERA_CLIENTES + "c001,Juan,\n", encoding="utf-8-sig")
    assert len(cargar_clientes(ruta)) == 1


def test_venta_se_convierte_a_tipos_correctos(tmp_path):
    ruta = escribir(tmp_path, "v.csv", CABECERA_VENTAS + "v001,c001,p001,2,35.5,2026-09-01\n")
    (venta,) = cargar_ventas(ruta)
    assert venta.cantidad == 2 and venta.fecha == date(2026, 9, 1)
    assert venta.monto == 71.0


# ---------- errores de archivo y estructura ----------
def test_archivo_inexistente(tmp_path):
    with pytest.raises(ErrorDatos, match="No se encontró"):
        cargar_clientes(tmp_path / "no_existe.csv")


def test_columna_faltante(tmp_path):
    ruta = escribir(tmp_path, "p.csv", "id_producto,nombre,precio\np001,Mouse,10\n")
    with pytest.raises(ErrorDatos, match="categoria"):
        cargar_productos(ruta)


def test_archivo_vacio_sin_cabecera(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "")
    with pytest.raises(ErrorDatos, match="faltan las columnas"):
        cargar_clientes(ruta)


# ---------- errores de contenido (con número de fila) ----------
def test_error_indica_archivo_y_fila(tmp_path):
    contenido = CABECERA_PRODUCTOS + "p001,Mouse,perifericos,10\np002,Teclado,perifericos,-5\n"
    ruta = escribir(tmp_path, "p.csv", contenido)
    with pytest.raises(ErrorDatos, match=r"p\.csv, fila 3"):
        cargar_productos(ruta)


@pytest.mark.parametrize(
    "fila",
    [
        "v001,c001,p001,dos,10,2026-09-01",  # cantidad no entera
        "v001,c001,p001,0,10,2026-09-01",  # cantidad cero
        "v001,c001,p001,1,abc,2026-09-01",  # precio no numérico
        "v001,c001,p001,1,10,01/09/2026",  # fecha con otro formato
        "v001,c001,p001,1,10,2026-02-30",  # fecha inexistente
        "V001,c001,p001,1,10,2026-09-01",  # id con mayúscula
    ],
)
def test_venta_con_datos_invalidos(tmp_path, fila):
    ruta = escribir(tmp_path, "v.csv", CABECERA_VENTAS + fila + "\n")
    with pytest.raises(ErrorDatos):
        cargar_ventas(ruta)


def test_fila_incompleta(tmp_path):
    ruta = escribir(tmp_path, "v.csv", CABECERA_VENTAS + "v001,c001,p001\n")
    with pytest.raises(ErrorDatos, match="fila 2"):
        cargar_ventas(ruta)


def test_telefono_con_letras(tmp_path):
    ruta = escribir(tmp_path, "c.csv", CABECERA_CLIENTES + "c001,Juan,abc123\n")
    with pytest.raises(ErrorDatos, match="telefono"):
        cargar_clientes(ruta)


def test_id_duplicado(tmp_path):
    ruta = escribir(tmp_path, "c.csv", CABECERA_CLIENTES + "c001,Juan,\nc001,Ana,\n")
    with pytest.raises(ErrorDatos, match="duplicado"):
        cargar_clientes(ruta)


# ---------- integridad referencial ----------
def test_integridad_cliente_inexistente(tmp_path):
    clientes = cargar_clientes(escribir(tmp_path, "c.csv", CABECERA_CLIENTES + "c001,Juan,\n"))
    productos = cargar_productos(
        escribir(tmp_path, "p.csv", CABECERA_PRODUCTOS + "p001,Mouse,perifericos,10\n")
    )
    ventas = cargar_ventas(
        escribir(tmp_path, "v.csv", CABECERA_VENTAS + "v001,c999,p001,1,10,2026-09-01\n")
    )
    with pytest.raises(ErrorDatos, match="cliente inexistente"):
        validar_integridad(clientes, productos, ventas)


def test_integridad_producto_inexistente(tmp_path):
    clientes = cargar_clientes(escribir(tmp_path, "c.csv", CABECERA_CLIENTES + "c001,Juan,\n"))
    productos = cargar_productos(
        escribir(tmp_path, "p.csv", CABECERA_PRODUCTOS + "p001,Mouse,perifericos,10\n")
    )
    ventas = cargar_ventas(
        escribir(tmp_path, "v.csv", CABECERA_VENTAS + "v001,c001,p999,1,10,2026-09-01\n")
    )
    with pytest.raises(ErrorDatos, match="producto inexistente"):
        validar_integridad(clientes, productos, ventas)


def test_cargar_todo_detecta_integridad(tmp_path):
    escribir(tmp_path, "clientes.csv", CABECERA_CLIENTES + "c001,Juan,\n")
    escribir(tmp_path, "productos.csv", CABECERA_PRODUCTOS + "p001,Mouse,perifericos,10\n")
    escribir(tmp_path, "ventas.csv", CABECERA_VENTAS + "v001,c001,p999,1,10,2026-09-01\n")
    with pytest.raises(ErrorDatos, match="inexistente"):
        cargar_todo(tmp_path)
