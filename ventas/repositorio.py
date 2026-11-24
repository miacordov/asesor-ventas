"""Persistencia de clientes, productos y ventas.

`Repositorio` es el contrato: el resto del sistema no sabe qué base de datos hay
detrás. `RepositorioSQLite` lo implementa con `sqlite3`, que viene incluido en
Python.

Los precios se guardan como centavos enteros (igual que en las reglas Prolog),
y las fechas como texto ISO (AAAA-MM-DD).
"""

import re
import sqlite3
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from ventas.cargador import Datos, ErrorDatos
from ventas.combos import Combo
from ventas.contactos import Contacto
from ventas.modelos import Cliente, ClienteRegular, Producto, Venta
from ventas.ofertas import Oferta

_TABLAS = {
    "c": ("clientes", "id_cliente"),
    "p": ("productos", "id_producto"),
    "v": ("ventas", "id_venta"),
    "cb": ("combos", "id_combo"),
}

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente TEXT PRIMARY KEY,
    nombre     TEXT NOT NULL,
    telefono   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS productos (
    id_producto     TEXT PRIMARY KEY,
    nombre          TEXT NOT NULL,
    categoria       TEXT NOT NULL,
    precio_centavos INTEGER NOT NULL CHECK (precio_centavos > 0),
    costo_centavos  INTEGER CHECK (costo_centavos IS NULL OR costo_centavos > 0),
    stock           INTEGER CHECK (stock IS NULL OR stock >= 0)
);
CREATE TABLE IF NOT EXISTS ventas (
    id_venta        TEXT PRIMARY KEY,
    id_cliente      TEXT NOT NULL REFERENCES clientes (id_cliente),
    id_producto     TEXT NOT NULL REFERENCES productos (id_producto),
    cantidad        INTEGER NOT NULL CHECK (cantidad >= 1),
    precio_centavos INTEGER NOT NULL CHECK (precio_centavos > 0),
    fecha           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ofertas (
    id_producto TEXT PRIMARY KEY REFERENCES productos (id_producto) ON DELETE CASCADE,
    porcentaje  INTEGER NOT NULL CHECK (porcentaje BETWEEN 1 AND 90),
    desde       TEXT NOT NULL,
    hasta       TEXT NOT NULL CHECK (hasta >= desde)
);
CREATE TABLE IF NOT EXISTS contactos (
    id_contacto INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente  TEXT NOT NULL REFERENCES clientes (id_cliente) ON DELETE CASCADE,
    fecha       TEXT NOT NULL,
    resultado   TEXT NOT NULL,
    volver_el   TEXT NOT NULL CHECK (volver_el >= fecha)
);
CREATE TABLE IF NOT EXISTS combos (
    id_combo       TEXT PRIMARY KEY,
    id_cliente     TEXT REFERENCES clientes (id_cliente) ON DELETE CASCADE,
    nombre_cliente TEXT NOT NULL DEFAULT '',  -- cliente no registrado (sin id_cliente)
    fecha          TEXT NOT NULL,
    descuento      INTEGER CHECK (descuento IS NULL OR descuento BETWEEN 0 AND 90),  -- NULL: el del cliente
    descartado     INTEGER NOT NULL DEFAULT 0,
    CHECK ((id_cliente IS NULL) <> (nombre_cliente = ''))
);
CREATE TABLE IF NOT EXISTS combo_productos (
    id_combo    TEXT NOT NULL REFERENCES combos (id_combo) ON DELETE CASCADE,
    id_producto TEXT NOT NULL REFERENCES productos (id_producto) ON DELETE CASCADE,
    orden       INTEGER NOT NULL,
    precio_centavos INTEGER CHECK (precio_centavos IS NULL OR precio_centavos > 0),  -- fijado al enviar
    PRIMARY KEY (id_combo, id_producto)
);
CREATE TABLE IF NOT EXISTS combo_ventas (
    id_combo TEXT NOT NULL REFERENCES combos (id_combo) ON DELETE CASCADE,
    id_venta TEXT NOT NULL REFERENCES ventas (id_venta) ON DELETE CASCADE,
    orden    INTEGER NOT NULL,
    PRIMARY KEY (id_combo, id_venta)
);
"""


def _centavos(monto: float) -> int:
    return round(monto * 100)


_INSERTAR_PRODUCTO = (
    "INSERT INTO productos (id_producto, nombre, categoria, precio_centavos, costo_centavos, stock) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

# El stock lo cuida la base: cualquier venta (suelta o de un combo) lo descuenta,
# anularla lo devuelve, y sin stock suficiente la operación entera se deshace.
# Un producto con stock NULL no se controla.
_DISPARADORES = """
CREATE TRIGGER IF NOT EXISTS ventas_controlan_stock BEFORE INSERT ON ventas
WHEN (SELECT stock FROM productos WHERE id_producto = NEW.id_producto) < NEW.cantidad
BEGIN
    SELECT RAISE(ABORT, 'stock_insuficiente');
END;
CREATE TRIGGER IF NOT EXISTS ventas_descuentan_stock AFTER INSERT ON ventas
BEGIN
    UPDATE productos SET stock = stock - NEW.cantidad WHERE id_producto = NEW.id_producto AND stock IS NOT NULL;
END;
CREATE TRIGGER IF NOT EXISTS ventas_devuelven_stock AFTER DELETE ON ventas
BEGIN
    UPDATE productos SET stock = stock + OLD.cantidad WHERE id_producto = OLD.id_producto AND stock IS NOT NULL;
END;
"""

class Repositorio(ABC):
    """Contrato de persistencia."""

    @abstractmethod
    def cargar_todo(self) -> Datos: ...

    @abstractmethod
    def esta_vacio(self) -> bool: ...

    @abstractmethod
    def reemplazar_todo(self, datos: Datos) -> None: ...

    @abstractmethod
    def siguiente_id(self, prefijo: str) -> str: ...

    @abstractmethod
    def agregar_cliente(self, cliente: Cliente) -> None: ...

    @abstractmethod
    def actualizar_cliente(self, cliente: Cliente) -> None: ...

    @abstractmethod
    def eliminar_cliente(self, id_cliente: str) -> None: ...

    @abstractmethod
    def agregar_producto(self, producto: Producto) -> None: ...

    @abstractmethod
    def actualizar_producto(self, producto: Producto) -> None: ...

    @abstractmethod
    def eliminar_producto(self, id_producto: str) -> None: ...

    @abstractmethod
    def agregar_venta(self, venta: Venta) -> None: ...

    @abstractmethod
    def eliminar_venta(self, id_venta: str) -> None: ...

    @abstractmethod
    def cargar_ofertas(self) -> tuple[Oferta, ...]: ...

    @abstractmethod
    def guardar_oferta(self, oferta: Oferta) -> None:
        """Crea la oferta del producto o reemplaza la que tenía (una por producto)."""

    @abstractmethod
    def eliminar_oferta(self, id_producto: str) -> None: ...

    @abstractmethod
    def cargar_contactos(self) -> tuple[Contacto, ...]: ...

    @abstractmethod
    def agregar_contacto(self, contacto: Contacto) -> None: ...

    @abstractmethod
    def cargar_combos(self) -> tuple[Combo, ...]: ...

    @abstractmethod
    def agregar_combo(self, combo: Combo) -> None: ...

    @abstractmethod
    def actualizar_combo(self, combo: Combo) -> None:
        """Guarda el descuento, los precios fijos y si está descartado."""

    @abstractmethod
    def eliminar_combo(self, id_combo: str) -> None: ...

    @abstractmethod
    def registrar_combo(self, id_combo: str, ventas: tuple[Venta, ...], cliente_nuevo: Cliente | None = None) -> None:
        """Guarda las ventas del combo y las enlaza a él, todo o nada. Si el combo
        era de un cliente no registrado, `cliente_nuevo` se registra en la misma operación."""


class RepositorioSQLite(Repositorio):
    """Implementación con SQLite. Segura para varios hilos (un candado protege la conexión)."""

    def __init__(self, ruta: str = ":memory:") -> None:
        self._candado = threading.RLock()
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        self._con.execute("PRAGMA foreign_keys = ON")
        if ruta != ":memory:" and self._hay_migraciones_pendientes():
            self._respaldar_antes_de_migrar(Path(ruta))
        with self._candado, self._con:
            self._con.executescript(_ESQUEMA)
        self._migrar_combos_sin_cliente()
        self._migrar_costo_y_stock()
        self._migrar_pedidos()
        with self._candado, self._con:
            self._con.executescript(_DISPARADORES)

    @contextmanager
    def _transaccion(self) -> Iterator[None]:
        """Todo o nada, también para CREATE/ALTER/DROP: el módulo sqlite3 confirma
        esas sentencias al instante si no hay una transacción abierta, y una
        migración fallida dejaría la base a medias (y la app sin arrancar)."""
        with self._candado:
            self._con.execute("BEGIN")
            try:
                yield
            except BaseException:
                self._con.rollback()
                raise
            self._con.commit()

    def _hay_migraciones_pendientes(self) -> bool:
        """¿La base es de una versión anterior y hay que transformarla?"""
        tablas = {f[0] for f in self._con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

        def faltan(tabla: str, *columnas: str) -> bool:
            if tabla not in tablas:
                return False  # el esquema la crea completa
            existentes = {f[1] for f in self._con.execute(f"PRAGMA table_info({tabla})")}
            return not set(columnas) <= existentes

        return (
            "propuestas" in tablas
            or faltan("combos", "nombre_cliente", "descuento", "descartado")
            or faltan("combo_productos", "precio_centavos")
            or faltan("productos", "costo_centavos", "stock")
        )

    def _respaldar_antes_de_migrar(self, ruta: Path) -> Path:
        """Copia la base tal como está, junto a ella, antes de transformarla."""
        destino = ruta.with_name(f"{ruta.stem}-antes-de-migrar-{datetime.now().astimezone():%Y%m%d-%H%M%S-%f}.db")
        copia = sqlite3.connect(destino)
        try:
            with self._candado:
                self._con.backup(copia)
        finally:
            copia.close()
        return destino

    def _migrar_pedidos(self) -> None:
        """Los combos pasan a ser pedidos con descuento, precios fijos y estado; y
        cada propuesta guardada se convierte en un pedido enviado (con sus precios
        y su descuento). Después se borran las tablas de propuestas."""
        with self._transaccion():
            columnas = {f[1] for f in self._con.execute("PRAGMA table_info(combos)")}
            if "descuento" not in columnas:
                self._con.execute(
                    "ALTER TABLE combos ADD COLUMN descuento INTEGER CHECK (descuento IS NULL OR descuento BETWEEN 0 AND 90)"
                )
            if "descartado" not in columnas:
                self._con.execute("ALTER TABLE combos ADD COLUMN descartado INTEGER NOT NULL DEFAULT 0")
            if "precio_centavos" not in {f[1] for f in self._con.execute("PRAGMA table_info(combo_productos)")}:
                self._con.execute(
                    "ALTER TABLE combo_productos ADD COLUMN precio_centavos INTEGER "
                    "CHECK (precio_centavos IS NULL OR precio_centavos > 0)"
                )
            tablas = {f[0] for f in self._con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "propuestas" not in tablas:
                return
            numeros = [
                int(i[2:]) for (i,) in self._con.execute("SELECT id_combo FROM combos") if re.fullmatch(r"cb\d+", i)
            ]
            siguiente = max(numeros, default=0) + 1
            for id_cliente, descuento, fecha in self._con.execute(
                "SELECT id_cliente, descuento, fecha FROM propuestas ORDER BY fecha, id_cliente"
            ).fetchall():
                lineas = self._con.execute(
                    "SELECT id_producto, precio_centavos FROM propuesta_productos WHERE id_cliente = ? ORDER BY orden",
                    (id_cliente,),
                ).fetchall()
                if len(lineas) < 2:  # perdió productos: ya no era un combo
                    continue
                id_combo = f"cb{siguiente:03d}"
                siguiente += 1
                self._con.execute(
                    "INSERT INTO combos (id_combo, id_cliente, nombre_cliente, fecha, descuento) VALUES (?, ?, '', ?, ?)",
                    (id_combo, id_cliente, fecha, descuento),
                )
                self._con.executemany(
                    "INSERT INTO combo_productos (id_combo, id_producto, orden, precio_centavos) VALUES (?, ?, ?, ?)",
                    [(id_combo, i, orden, precio) for orden, (i, precio) in enumerate(lineas)],
                )
            self._con.execute("DROP TABLE IF EXISTS propuesta_productos")
            self._con.execute("DROP TABLE propuestas")

    def _migrar_costo_y_stock(self) -> None:
        """Las bases anteriores no tenían costo ni stock: se agregan las columnas
        vacías (sin costo y sin control de stock), sin tocar las filas."""
        with self._transaccion():
            columnas = {fila[1] for fila in self._con.execute("PRAGMA table_info(productos)")}
            if "costo_centavos" not in columnas:
                self._con.execute(
                    "ALTER TABLE productos ADD COLUMN costo_centavos INTEGER "
                    "CHECK (costo_centavos IS NULL OR costo_centavos > 0)"
                )
            if "stock" not in columnas:
                self._con.execute("ALTER TABLE productos ADD COLUMN stock INTEGER CHECK (stock IS NULL OR stock >= 0)")

    def _migrar_combos_sin_cliente(self) -> None:
        """Bases creadas antes de admitir clientes no registrados: la tabla combos
        exigía id_cliente. SQLite no cambia un NOT NULL con ALTER TABLE, así que se
        rehace la tabla copiando sus filas (las de combo_productos y combo_ventas
        no se tocan: siguen apuntando al mismo id_combo)."""
        with self._candado:
            columnas = [fila[1] for fila in self._con.execute("PRAGMA table_info(combos)")]
            if "nombre_cliente" in columnas:
                return
            # Sin claves foráneas mientras se rehace: DROP TABLE no debe borrar en cascada.
            self._con.execute("PRAGMA foreign_keys = OFF")  # fuera de la transacción: dentro no tiene efecto
            try:
                with self._transaccion():
                    self._con.execute(
                        """CREATE TABLE combos_nuevo (
                            id_combo       TEXT PRIMARY KEY,
                            id_cliente     TEXT REFERENCES clientes (id_cliente) ON DELETE CASCADE,
                            nombre_cliente TEXT NOT NULL DEFAULT '',
                            fecha          TEXT NOT NULL,
                            CHECK ((id_cliente IS NULL) <> (nombre_cliente = ''))
                        )"""
                    )
                    self._con.execute(
                        "INSERT INTO combos_nuevo (id_combo, id_cliente, fecha) SELECT id_combo, id_cliente, fecha FROM combos"
                    )
                    self._con.execute("DROP TABLE combos")
                    self._con.execute("ALTER TABLE combos_nuevo RENAME TO combos")
                    if self._con.execute("PRAGMA foreign_key_check").fetchall():
                        raise sqlite3.IntegrityError("la migración de combos dejó referencias rotas")
            finally:
                self._con.execute("PRAGMA foreign_keys = ON")

    def cerrar(self) -> None:
        with self._candado:
            self._con.close()

    # ---------- lectura ----------
    def cargar_todo(self) -> Datos:
        with self._candado:
            clientes = tuple(
                ClienteRegular(i, n, t)
                for i, n, t in self._con.execute("SELECT id_cliente, nombre, telefono FROM clientes ORDER BY rowid")
            )
            productos = tuple(
                Producto(i, n, c, p / 100, None if co is None else co / 100, s)
                for i, n, c, p, co, s in self._con.execute(
                    "SELECT id_producto, nombre, categoria, precio_centavos, costo_centavos, stock "
                    "FROM productos ORDER BY rowid"
                )
            )
            ventas = tuple(
                Venta(i, c, p, q, pc / 100, date.fromisoformat(f))
                for i, c, p, q, pc, f in self._con.execute(
                    "SELECT id_venta, id_cliente, id_producto, cantidad, precio_centavos, fecha FROM ventas ORDER BY rowid"
                )
            )
        return Datos(clientes, productos, ventas)

    def esta_vacio(self) -> bool:
        with self._candado:
            return not any(
                self._con.execute(f"SELECT 1 FROM {tabla} LIMIT 1").fetchone() for tabla, _ in _TABLAS.values()
            )

    def siguiente_id(self, prefijo: str) -> str:
        """c001, c002... (la numeración sigue al mayor identificador existente)."""
        if prefijo not in _TABLAS:
            raise ValueError(f"Prefijo desconocido: {prefijo!r}. Use uno de {sorted(_TABLAS)}.")
        tabla, columna = _TABLAS[prefijo]
        patron = re.compile(rf"^{prefijo}(\d+)$")
        with self._candado:
            ids = [fila[0] for fila in self._con.execute(f"SELECT {columna} FROM {tabla}")]
        numeros = [int(m.group(1)) for i in ids if (m := patron.match(i))]
        return f"{prefijo}{max(numeros, default=0) + 1:03d}"

    # ---------- escritura ----------
    def reemplazar_todo(self, datos: Datos) -> None:
        """Sustituye todo el contenido en una sola transacción (todo o nada)."""
        try:
            with self._candado, self._con:
                for tabla in (
                    "contactos",
                    "combo_ventas",
                    "combo_productos",
                    "combos",
                    "ofertas",
                    "ventas",
                    "clientes",
                    "productos",
                ):
                    self._con.execute(f"DELETE FROM {tabla}")
                self._con.executemany(
                    "INSERT INTO clientes VALUES (?, ?, ?)",
                    [(c.id_cliente, c.nombre, c.telefono) for c in datos.clientes],
                )
                # Sin stock al principio: las ventas históricas no deben descontarlo.
                self._con.executemany(
                    _INSERTAR_PRODUCTO, [_fila_producto(replace(p, stock=None)) for p in datos.productos]
                )
                self._con.executemany(
                    "INSERT INTO ventas VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (v.id_venta, v.id_cliente, v.id_producto, v.cantidad, _centavos(v.precio_unitario), v.fecha.isoformat())
                        for v in datos.ventas
                    ],
                )
                self._con.executemany(
                    "UPDATE productos SET stock = ? WHERE id_producto = ?",
                    [(p.stock, p.id_producto) for p in datos.productos if p.stock is not None],
                )
        except sqlite3.IntegrityError as error:
            raise ErrorDatos(_traducir(error, "los datos a cargar")) from error

    def _ejecutar(self, sql: str, parametros: tuple, descripcion: str) -> int:
        try:
            with self._candado, self._con:
                return self._con.execute(sql, parametros).rowcount
        except sqlite3.IntegrityError as error:
            raise ErrorDatos(_traducir(error, descripcion)) from error

    def agregar_cliente(self, cliente: Cliente) -> None:
        self._ejecutar(
            "INSERT INTO clientes VALUES (?, ?, ?)",
            (cliente.id_cliente, cliente.nombre, cliente.telefono),
            f"el cliente {cliente.id_cliente}",
        )

    def actualizar_cliente(self, cliente: Cliente) -> None:
        filas = self._ejecutar(
            "UPDATE clientes SET nombre = ?, telefono = ? WHERE id_cliente = ?",
            (cliente.nombre, cliente.telefono, cliente.id_cliente),
            f"el cliente {cliente.id_cliente}",
        )
        if not filas:
            raise ErrorDatos(f"No existe el cliente {cliente.id_cliente}.")

    def eliminar_cliente(self, id_cliente: str) -> None:
        self._eliminar("clientes", "id_cliente", id_cliente, "ventas", "cliente")

    def agregar_producto(self, producto: Producto) -> None:
        self._ejecutar(_INSERTAR_PRODUCTO, _fila_producto(producto), f"el producto {producto.id_producto}")

    def actualizar_producto(self, producto: Producto) -> None:
        filas = self._ejecutar(
            "UPDATE productos SET nombre = ?, categoria = ?, precio_centavos = ?, costo_centavos = ?, stock = ? "
            "WHERE id_producto = ?",
            (*_fila_producto(producto)[1:], producto.id_producto),
            f"el producto {producto.id_producto}",
        )
        if not filas:
            raise ErrorDatos(f"No existe el producto {producto.id_producto}.")

    def eliminar_producto(self, id_producto: str) -> None:
        self._eliminar("productos", "id_producto", id_producto, "ventas", "producto")

    def agregar_venta(self, venta: Venta) -> None:
        self._ejecutar(
            "INSERT INTO ventas VALUES (?, ?, ?, ?, ?, ?)",
            (
                venta.id_venta,
                venta.id_cliente,
                venta.id_producto,
                venta.cantidad,
                _centavos(venta.precio_unitario),
                venta.fecha.isoformat(),
            ),
            f"la venta {venta.id_venta}",
        )

    def eliminar_venta(self, id_venta: str) -> None:
        if not self._ejecutar("DELETE FROM ventas WHERE id_venta = ?", (id_venta,), f"la venta {id_venta}"):
            raise ErrorDatos(f"No existe la venta {id_venta}.")

    # ---------- ofertas ----------
    def cargar_ofertas(self) -> tuple[Oferta, ...]:
        with self._candado:
            filas = self._con.execute(
                "SELECT id_producto, porcentaje, desde, hasta FROM ofertas ORDER BY id_producto"
            ).fetchall()
        return tuple(Oferta(i, p, date.fromisoformat(d), date.fromisoformat(h)) for i, p, d, h in filas)

    def guardar_oferta(self, oferta: Oferta) -> None:
        self._ejecutar(
            "INSERT INTO ofertas VALUES (?, ?, ?, ?) ON CONFLICT (id_producto) DO UPDATE SET "
            "porcentaje = excluded.porcentaje, desde = excluded.desde, hasta = excluded.hasta",
            (oferta.id_producto, oferta.porcentaje, oferta.desde.isoformat(), oferta.hasta.isoformat()),
            f"la oferta del producto {oferta.id_producto}",
        )

    def eliminar_oferta(self, id_producto: str) -> None:
        if not self._ejecutar("DELETE FROM ofertas WHERE id_producto = ?", (id_producto,), "la oferta"):
            raise ErrorDatos(f"El producto {id_producto} no tiene oferta.")

    # ---------- contactos ----------
    def cargar_contactos(self) -> tuple[Contacto, ...]:
        with self._candado:
            filas = self._con.execute(
                "SELECT id_cliente, fecha, resultado, volver_el FROM contactos ORDER BY fecha, id_contacto"
            ).fetchall()
        return tuple(Contacto(c, date.fromisoformat(f), r, date.fromisoformat(v)) for c, f, r, v in filas)

    def agregar_contacto(self, contacto: Contacto) -> None:
        self._ejecutar(
            "INSERT INTO contactos (id_cliente, fecha, resultado, volver_el) VALUES (?, ?, ?, ?)",
            (contacto.id_cliente, contacto.fecha.isoformat(), contacto.resultado, contacto.volver_el.isoformat()),
            f"el contacto con {contacto.id_cliente}",
        )

    # ---------- combos ----------
    def cargar_combos(self) -> tuple[Combo, ...]:
        """Los combos guardados. Uno que perdió productos (borrados del catálogo)
        y quedó con menos de 2 ya no es un combo y no se devuelve."""
        with self._candado:
            cabeceras = self._con.execute(
                "SELECT id_combo, id_cliente, fecha, nombre_cliente, descuento, descartado FROM combos ORDER BY id_combo"
            ).fetchall()
            productos = self._con.execute(
                "SELECT id_combo, id_producto, precio_centavos FROM combo_productos ORDER BY id_combo, orden"
            ).fetchall()
            ventas = self._con.execute("SELECT id_combo, id_venta FROM combo_ventas ORDER BY id_combo, orden").fetchall()
        de_productos: dict[str, list[str]] = {}
        de_precios: dict[str, list[int | None]] = {}
        for id_combo, id_producto, precio in productos:
            de_productos.setdefault(id_combo, []).append(id_producto)
            de_precios.setdefault(id_combo, []).append(precio)

        def fijos(id_combo: str) -> tuple[float, ...]:
            precios = de_precios[id_combo]
            return () if None in precios else tuple(p / 100 for p in precios)

        de_ventas: dict[str, list[str]] = {}
        for id_combo, id_venta in ventas:
            de_ventas.setdefault(id_combo, []).append(id_venta)
        return tuple(
            Combo(
                i,
                c,
                tuple(de_productos[i]),
                date.fromisoformat(f),
                tuple(de_ventas.get(i, ())),
                n,
                descuento=d,
                precios=fijos(i),
                descartado=bool(x) and not de_ventas.get(i),
            )
            for i, c, f, n, d, x in cabeceras
            if len(de_productos.get(i, ())) >= 2
        )

    def agregar_combo(self, combo: Combo) -> None:
        try:
            with self._candado, self._con:
                self._con.execute(
                    "INSERT INTO combos (id_combo, id_cliente, nombre_cliente, fecha, descuento, descartado) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        combo.id_combo,
                        combo.id_cliente,
                        combo.nombre_cliente,
                        combo.fecha.isoformat(),
                        combo.descuento,
                        int(combo.descartado),
                    ),
                )
                self._con.executemany(
                    "INSERT INTO combo_productos (id_combo, id_producto, orden, precio_centavos) VALUES (?, ?, ?, ?)",
                    [(combo.id_combo, i, orden, precio) for orden, (i, precio) in enumerate(_precios_fijos(combo))],
                )
        except sqlite3.IntegrityError as error:
            raise ErrorDatos(_traducir(error, f"el combo {combo.id_combo}")) from error

    def actualizar_combo(self, combo: Combo) -> None:
        try:
            with self._candado, self._con:
                filas = self._con.execute(
                    "UPDATE combos SET descuento = ?, descartado = ? WHERE id_combo = ?",
                    (combo.descuento, int(combo.descartado), combo.id_combo),
                ).rowcount
                if not filas:
                    raise ErrorDatos(f"No existe el combo {combo.id_combo}.")
                self._con.executemany(
                    "UPDATE combo_productos SET precio_centavos = ? WHERE id_combo = ? AND id_producto = ?",
                    [(precio, combo.id_combo, i) for i, precio in _precios_fijos(combo)],
                )
        except sqlite3.IntegrityError as error:
            raise ErrorDatos(_traducir(error, f"el combo {combo.id_combo}")) from error

    def eliminar_combo(self, id_combo: str) -> None:
        if not self._ejecutar("DELETE FROM combos WHERE id_combo = ?", (id_combo,), f"el combo {id_combo}"):
            raise ErrorDatos(f"No existe el combo {id_combo}.")

    def registrar_combo(self, id_combo: str, ventas: tuple[Venta, ...], cliente_nuevo: Cliente | None = None) -> None:
        try:
            with self._candado, self._con:
                if not self._con.execute("SELECT 1 FROM combos WHERE id_combo = ?", (id_combo,)).fetchone():
                    raise ErrorDatos(f"No existe el combo {id_combo}.")
                if cliente_nuevo is not None:
                    self._con.execute(
                        "INSERT INTO clientes VALUES (?, ?, ?)",
                        (cliente_nuevo.id_cliente, cliente_nuevo.nombre, cliente_nuevo.telefono),
                    )
                    self._con.execute(
                        "UPDATE combos SET id_cliente = ?, nombre_cliente = '' WHERE id_combo = ?",
                        (cliente_nuevo.id_cliente, id_combo),
                    )
                self._con.executemany(
                    "INSERT INTO ventas VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (v.id_venta, v.id_cliente, v.id_producto, v.cantidad, _centavos(v.precio_unitario), v.fecha.isoformat())
                        for v in ventas
                    ],
                )
                self._con.executemany(
                    "INSERT INTO combo_ventas VALUES (?, ?, ?)", [(id_combo, v.id_venta, orden) for orden, v in enumerate(ventas)]
                )
        except sqlite3.IntegrityError as error:
            raise ErrorDatos(_traducir(error, f"las ventas del combo {id_combo}")) from error

    def _eliminar(self, tabla: str, columna: str, valor: str, tabla_hija: str, nombre: str) -> None:
        with self._candado:
            existe = self._con.execute(f"SELECT 1 FROM {tabla} WHERE {columna} = ?", (valor,)).fetchone()
            if not existe:
                raise ErrorDatos(f"No existe el {nombre} {valor}.")
            (n,) = self._con.execute(f"SELECT COUNT(*) FROM {tabla_hija} WHERE {columna} = ?", (valor,)).fetchone()
        if n:
            raise ErrorDatos(
                f"No se puede eliminar el {nombre} {valor}: tiene {n} {'venta registrada' if n == 1 else 'ventas registradas'}."
            )
        self._ejecutar(f"DELETE FROM {tabla} WHERE {columna} = ?", (valor,), f"el {nombre} {valor}")


def _precios_fijos(combo: Combo) -> list[tuple[str, int | None]]:
    """(id_producto, precio fijo en centavos o None) de cada producto del pedido."""
    precios = [_centavos(p) for p in combo.precios] or [None] * len(combo.ids_productos)
    return list(zip(combo.ids_productos, precios, strict=True))


def _fila_producto(p: Producto) -> tuple:
    costo = None if p.costo is None else _centavos(p.costo)
    return (p.id_producto, p.nombre, p.categoria, _centavos(p.precio), costo, p.stock)


def _traducir(error: sqlite3.IntegrityError, descripcion: str) -> str:
    texto = str(error)
    if "stock_insuficiente" in texto:
        return f"No hay stock suficiente para registrar {descripcion}."
    if "UNIQUE" in texto or "PRIMARY KEY" in texto:
        return f"Ya existe {descripcion}."
    if "FOREIGN KEY" in texto:
        return f"No se pudo guardar {descripcion}: hace referencia a un cliente o producto que no existe."
    return f"No se pudo guardar {descripcion}: {texto}"
