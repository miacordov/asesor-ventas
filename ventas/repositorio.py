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
from datetime import date

from ventas.cargador import Datos, ErrorDatos
from ventas.combos import Combo
from ventas.modelos import Cliente, ClienteRegular, Producto, Venta
from ventas.ofertas import Oferta
from ventas.propuestas import LineaPropuesta, Propuesta

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
    precio_centavos INTEGER NOT NULL CHECK (precio_centavos > 0)
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
CREATE TABLE IF NOT EXISTS propuestas (
    id_cliente TEXT PRIMARY KEY REFERENCES clientes (id_cliente) ON DELETE CASCADE,
    descuento  INTEGER NOT NULL CHECK (descuento BETWEEN 0 AND 90),
    fecha      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS propuesta_productos (
    id_cliente             TEXT NOT NULL REFERENCES propuestas (id_cliente) ON DELETE CASCADE,
    id_producto            TEXT NOT NULL REFERENCES productos (id_producto) ON DELETE CASCADE,
    orden                  INTEGER NOT NULL,
    precio_normal_centavos INTEGER NOT NULL CHECK (precio_normal_centavos > 0),
    precio_centavos        INTEGER NOT NULL CHECK (precio_centavos > 0),
    PRIMARY KEY (id_cliente, id_producto)
);
CREATE TABLE IF NOT EXISTS combos (
    id_combo       TEXT PRIMARY KEY,
    id_cliente     TEXT REFERENCES clientes (id_cliente) ON DELETE CASCADE,
    nombre_cliente TEXT NOT NULL DEFAULT '',  -- cliente no registrado (sin id_cliente)
    fecha          TEXT NOT NULL,
    CHECK ((id_cliente IS NULL) <> (nombre_cliente = ''))
);
CREATE TABLE IF NOT EXISTS combo_productos (
    id_combo    TEXT NOT NULL REFERENCES combos (id_combo) ON DELETE CASCADE,
    id_producto TEXT NOT NULL REFERENCES productos (id_producto) ON DELETE CASCADE,
    orden       INTEGER NOT NULL,
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
    def cargar_propuestas(self) -> tuple[Propuesta, ...]: ...

    @abstractmethod
    def guardar_propuesta(self, propuesta: Propuesta) -> None:
        """Guarda la propuesta del cliente o reemplaza la que tenía (una por cliente)."""

    @abstractmethod
    def eliminar_propuesta(self, id_cliente: str) -> None: ...

    @abstractmethod
    def cargar_combos(self) -> tuple[Combo, ...]: ...

    @abstractmethod
    def agregar_combo(self, combo: Combo) -> None: ...

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
        with self._candado, self._con:
            self._con.executescript(_ESQUEMA)
        self._migrar_combos_sin_cliente()

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
            self._con.execute("PRAGMA foreign_keys = OFF")
            try:
                with self._con:
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
                Producto(i, n, c, p / 100)
                for i, n, c, p in self._con.execute(
                    "SELECT id_producto, nombre, categoria, precio_centavos FROM productos ORDER BY rowid"
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
                    "combo_ventas",
                    "combo_productos",
                    "combos",
                    "propuesta_productos",
                    "propuestas",
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
                self._con.executemany(
                    "INSERT INTO productos VALUES (?, ?, ?, ?)",
                    [(p.id_producto, p.nombre, p.categoria, _centavos(p.precio)) for p in datos.productos],
                )
                self._con.executemany(
                    "INSERT INTO ventas VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (v.id_venta, v.id_cliente, v.id_producto, v.cantidad, _centavos(v.precio_unitario), v.fecha.isoformat())
                        for v in datos.ventas
                    ],
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
        self._ejecutar(
            "INSERT INTO productos VALUES (?, ?, ?, ?)",
            (producto.id_producto, producto.nombre, producto.categoria, _centavos(producto.precio)),
            f"el producto {producto.id_producto}",
        )

    def actualizar_producto(self, producto: Producto) -> None:
        filas = self._ejecutar(
            "UPDATE productos SET nombre = ?, categoria = ?, precio_centavos = ? WHERE id_producto = ?",
            (producto.nombre, producto.categoria, _centavos(producto.precio), producto.id_producto),
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

    # ---------- propuestas ----------
    def cargar_propuestas(self) -> tuple[Propuesta, ...]:
        """Las propuestas guardadas. Si al borrar productos una quedó con menos de
        2, ya no es un combo y no se devuelve."""
        with self._candado:
            cabeceras = self._con.execute("SELECT id_cliente, descuento, fecha FROM propuestas ORDER BY fecha, id_cliente").fetchall()
            lineas = self._con.execute(
                "SELECT id_cliente, id_producto, precio_normal_centavos, precio_centavos FROM propuesta_productos ORDER BY id_cliente, orden"
            ).fetchall()
        por_cliente: dict[str, list[LineaPropuesta]] = {}
        for id_cliente, id_producto, normal, precio in lineas:
            por_cliente.setdefault(id_cliente, []).append(LineaPropuesta(id_producto, normal / 100, precio / 100))
        return tuple(
            Propuesta(c, tuple(por_cliente[c]), d, date.fromisoformat(f))
            for c, d, f in cabeceras
            if len(por_cliente.get(c, ())) >= 2
        )

    def guardar_propuesta(self, propuesta: Propuesta) -> None:
        try:
            with self._candado, self._con:
                self._con.execute("DELETE FROM propuestas WHERE id_cliente = ?", (propuesta.id_cliente,))
                self._con.execute(
                    "INSERT INTO propuestas VALUES (?, ?, ?)",
                    (propuesta.id_cliente, propuesta.descuento, propuesta.fecha.isoformat()),
                )
                self._con.executemany(
                    "INSERT INTO propuesta_productos VALUES (?, ?, ?, ?, ?)",
                    [
                        (propuesta.id_cliente, linea.id_producto, orden, _centavos(linea.precio_normal), _centavos(linea.precio))
                        for orden, linea in enumerate(propuesta.lineas)
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise ErrorDatos(_traducir(error, f"la propuesta para {propuesta.id_cliente}")) from error

    def eliminar_propuesta(self, id_cliente: str) -> None:
        if not self._ejecutar("DELETE FROM propuestas WHERE id_cliente = ?", (id_cliente,), "la propuesta"):
            raise ErrorDatos(f"El cliente {id_cliente} no tiene una propuesta guardada.")

    # ---------- combos ----------
    def cargar_combos(self) -> tuple[Combo, ...]:
        """Los combos guardados. Uno que perdió productos (borrados del catálogo)
        y quedó con menos de 2 ya no es un combo y no se devuelve."""
        with self._candado:
            cabeceras = self._con.execute(
                "SELECT id_combo, id_cliente, fecha, nombre_cliente FROM combos ORDER BY id_combo"
            ).fetchall()
            productos = self._con.execute("SELECT id_combo, id_producto FROM combo_productos ORDER BY id_combo, orden").fetchall()
            ventas = self._con.execute("SELECT id_combo, id_venta FROM combo_ventas ORDER BY id_combo, orden").fetchall()
        de_productos: dict[str, list[str]] = {}
        for id_combo, id_producto in productos:
            de_productos.setdefault(id_combo, []).append(id_producto)
        de_ventas: dict[str, list[str]] = {}
        for id_combo, id_venta in ventas:
            de_ventas.setdefault(id_combo, []).append(id_venta)
        return tuple(
            Combo(i, c, tuple(de_productos[i]), date.fromisoformat(f), tuple(de_ventas.get(i, ())), n)
            for i, c, f, n in cabeceras
            if len(de_productos.get(i, ())) >= 2
        )

    def agregar_combo(self, combo: Combo) -> None:
        try:
            with self._candado, self._con:
                self._con.execute(
                    "INSERT INTO combos (id_combo, id_cliente, nombre_cliente, fecha) VALUES (?, ?, ?, ?)",
                    (combo.id_combo, combo.id_cliente, combo.nombre_cliente, combo.fecha.isoformat()),
                )
                self._con.executemany(
                    "INSERT INTO combo_productos VALUES (?, ?, ?)",
                    [(combo.id_combo, i, orden) for orden, i in enumerate(combo.ids_productos)],
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


def _traducir(error: sqlite3.IntegrityError, descripcion: str) -> str:
    texto = str(error)
    if "UNIQUE" in texto or "PRIMARY KEY" in texto:
        return f"Ya existe {descripcion}."
    if "FOREIGN KEY" in texto:
        return f"No se pudo guardar {descripcion}: hace referencia a un cliente o producto que no existe."
    return f"No se pudo guardar {descripcion}: {texto}"
