import itertools
import math
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest

from ventas.cargador import cargar_todo
from ventas.funcional import PerfilCliente, clasificar_clientes, perfiles
from ventas.logico import MotorLogico, MotorPedidos, PuenteProlog
from ventas.modelos import ClienteFrecuente, ClienteRegular, Producto, Recomendacion
from ventas.ofertas import Oferta, ofertas_para_cliente
from ventas.pedido import (
    Pedido,
    armar_pedido_manual,
    categorias_alcanzables,
    categorias_de_recomendaciones,
    pedidos_para_cliente,
    presupuesto_sugerido,
    puntaje,
)

DATOS = Path(__file__).resolve().parent / "datos"
HOY = date(2026, 10, 5)


@pytest.fixture
def datos():
    return cargar_todo(DATOS)


@pytest.fixture
def motor():
    # SWI-Prolog es un único motor por proceso: se limpia en cada prueba.
    puente = PuenteProlog()
    puente.cargar_compras([])
    puente.cargar_perfiles([])
    puente.cargar_catalogo([])
    return puente


def contexto(datos, motor, id_cliente):
    ps = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)
    perfil = next(p for p in ps if p.id_cliente == id_cliente)
    cliente = next(c for c in clasificar_clientes(datos.clientes, ps) if c.id_cliente == id_cliente)
    motor.cargar_compras(datos.ventas)
    return cliente, perfil, motor.recomendar(id_cliente)


def sugeridos(datos, motor, id_cliente, **kwargs):
    cliente, perfil, recs = contexto(datos, motor, id_cliente)
    return pedidos_para_cliente(cliente, perfil, recs, datos.productos, motor, **kwargs)


def oraculo_pedidos(productos, ventas, presupuesto, categorias, id_cliente=None):
    """Verdad independiente: fuerza bruta con itertools.product."""
    propios = {v.id_producto for v in ventas if v.id_cliente == id_cliente} if id_cliente else set()
    opciones = [
        [p for p in productos if p.categoria == c and p.id_producto not in propios]
        for c in categorias
    ]
    limite = round(presupuesto * 100)
    resultado = set()
    for combo in itertools.product(*opciones):
        ids = [p.id_producto for p in combo]
        if len(ids) >= 2 and len(set(ids)) == len(ids) and sum(round(p.precio * 100) for p in combo) <= limite:
            resultado.add(tuple(sorted(ids)))
    return tuple(sorted(resultado))


# =====================================================================
# Reglas Prolog de pedidos (a través del puente)
# =====================================================================
def test_los_contratos_son_abstractos_y_el_puente_cumple_ambos(motor):
    with pytest.raises(TypeError):
        MotorPedidos()
    assert isinstance(motor, MotorPedidos) and isinstance(motor, MotorLogico)


def test_combinaciones_de_mostrador_calculadas_a_mano(motor, datos):
    # perifericos: p002=45, p003=120, p006=110 | accesorios: p007=85, p009=60
    # Con S/ 200 entran 5 de las 6 combinaciones (p003+p007 = 205 se pasa).
    motor.cargar_catalogo(datos.productos)
    assert motor.armar_pedidos(200, ["perifericos", "accesorios"]) == (
        ("p002", "p007"),
        ("p002", "p009"),
        ("p003", "p009"),
        ("p006", "p007"),
        ("p006", "p009"),
    )


def test_el_presupuesto_es_inclusivo_al_centavo(motor, datos):
    motor.cargar_catalogo(datos.productos)
    assert motor.armar_pedidos(105, ["perifericos", "accesorios"]) == (("p002", "p009"),)
    assert motor.armar_pedidos(104.99, ["perifericos", "accesorios"]) == ()


def test_misma_categoria_dos_veces_no_repite_producto_ni_orden(motor, datos):
    # p002+p003 = 165 y p002+p006 = 155 entran; p003+p006 = 230 no.
    motor.cargar_catalogo(datos.productos)
    assert motor.armar_pedidos(200, ["perifericos", "perifericos"]) == (
        ("p002", "p003"),
        ("p002", "p006"),
    )


def test_categoria_sin_productos(motor, datos):
    motor.cargar_catalogo(datos.productos)
    assert motor.armar_pedidos(5000, ["juguetes"]) == ()


def test_sin_catalogo_no_hay_pedidos(motor):
    assert motor.armar_pedidos(500, ["perifericos"]) == ()


def test_los_precios_con_decimales_no_fallan_por_redondeo(motor):
    # En decimales binarios 0.1 + 0.2 = 0.30000000000000004 y no cabría en 0.3.
    motor.cargar_catalogo([Producto("p001", "a", "a", 0.1), Producto("p002", "b", "b", 0.2)])
    assert motor.armar_pedidos(0.3, ["a", "b"]) == (("p001", "p002"),)


def test_los_centavos_se_redondean_no_se_truncan(motor):
    # 0.57 * 100 = 56.99999999999999 y 0.56 * 100 = 56.00000000000001. Truncando,
    # ambos darían 56 y un producto de S/ 0.57 "cabría" en un presupuesto de S/ 0.56.
    # Igual con 0.29 * 100 = 28.999999999999996: truncando, 0.28 + 0.29 "cabría" en 0.56.
    motor.cargar_catalogo([Producto("p001", "a", "a", 0.28), Producto("p002", "b", "b", 0.29)])
    assert motor.armar_pedidos(0.56, ["a", "b"]) == ()
    assert motor.armar_pedidos(0.57, ["a", "b"]) == (("p001", "p002"),)


def test_cargar_catalogo_reemplaza_el_anterior(motor, datos):
    motor.cargar_catalogo(datos.productos)
    motor.cargar_catalogo([Producto("p001", "Solo", "unica", 10.0), Producto("p002", "Otro", "otra", 5.0)])
    assert motor.armar_pedidos(100, ["perifericos", "accesorios"]) == ()
    assert motor.armar_pedidos(100, ["unica", "otra"]) == (("p001", "p002"),)


def test_un_solo_producto_no_es_una_combinacion(motor, datos):
    # Una combinación lleva al menos 2 productos: una sola categoría no alcanza.
    motor.cargar_catalogo(datos.productos)
    assert motor.armar_pedidos(5000, ["perifericos"]) == ()
    assert motor.armar_pedidos(5000, ["perifericos", "perifericos"]) != ()


@pytest.mark.parametrize(
    ("presupuesto", "categorias", "cliente"),
    [
        (200, ["perifericos", "accesorios"], None),
        (200, ["perifericos", "perifericos"], None),
        (1000, ["perifericos", "accesorios", "audio"], "c001"),
        (3000, ["computo", "monitores"], None),
        (500, ["perifericos", "perifericos", "accesorios"], "c005"),
        (50, ["perifericos"], None),
        (10, ["perifericos"], None),
        (972, ["accesorios", "audio", "monitores"], "c001"),
        (700, ["monitores", "mobiliario"], "c002"),
    ],
)
def test_coincide_con_la_fuerza_bruta(motor, datos, presupuesto, categorias, cliente):
    motor.cargar_catalogo(datos.productos)
    motor.cargar_compras(datos.ventas)
    esperado = oraculo_pedidos(datos.productos, datos.ventas, presupuesto, categorias, cliente)
    assert motor.armar_pedidos(presupuesto, categorias, id_cliente=cliente) == esperado


def test_excluye_lo_que_el_cliente_ya_compro(motor, datos):
    motor.cargar_catalogo(datos.productos)
    motor.cargar_compras(datos.ventas)
    # Juan (c001) ya compró el accesorio p007; sin él, solo queda p009.
    sin_filtro = motor.armar_pedidos(200, ["accesorios", "audio"])
    para_juan = motor.armar_pedidos(200, ["accesorios", "audio"], id_cliente="c001")
    assert sin_filtro == (("p005", "p007"), ("p005", "p009"))
    assert para_juan == (("p005", "p009"),)


def test_cliente_desconocido_no_excluye_nada(motor, datos):
    motor.cargar_catalogo(datos.productos)
    motor.cargar_compras(datos.ventas)
    assert motor.armar_pedidos(200, ["accesorios", "audio"], id_cliente="c999") == (("p005", "p007"), ("p005", "p009"))


def test_limite_de_combinaciones(motor, datos):
    motor.cargar_catalogo(datos.productos)
    assert len(motor.armar_pedidos(5000, ["perifericos", "accesorios"], max_combinaciones=2)) <= 2


@pytest.mark.parametrize("malo", [0, -5, math.nan, math.inf, "100", True, None])
def test_presupuesto_invalido(motor, malo):
    with pytest.raises(ValueError):
        motor.armar_pedidos(malo, ["perifericos"])


@pytest.mark.parametrize("malo", [[], ["Perifericos"], ["a); halt("], ["audio", "a b"], [""]])
def test_categorias_invalidas_o_peligrosas(motor, malo):
    with pytest.raises(ValueError):
        motor.armar_pedidos(100, malo)


@pytest.mark.parametrize("malo", ["C001", "c001); halt(", ""])
def test_id_cliente_invalido_o_peligroso(motor, malo):
    with pytest.raises(ValueError):
        motor.armar_pedidos(100, ["audio"], id_cliente=malo)


@pytest.mark.parametrize("malo", [0, -1, 2.5, True, "10"])
def test_max_combinaciones_invalido(motor, malo):
    with pytest.raises(ValueError):
        motor.armar_pedidos(100, ["audio"], max_combinaciones=malo)


# =====================================================================
# Funciones puras
# =====================================================================
def test_presupuesto_sugerido_de_juan(datos):
    perfil = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)[0]
    assert perfil.ticket_promedio == 883.33
    assert presupuesto_sugerido(perfil) == 972.0  # 883.33 * 1.10 = 971.66 -> 972
    assert presupuesto_sugerido(perfil, margen=0) == 884.0


def test_presupuesto_sugerido_no_sufre_errores_de_coma_flotante():
    perfil = PerfilCliente("c001", 1, date(2026, 9, 1), 4, 100.0, 100.0, ())
    assert presupuesto_sugerido(perfil, margen=0.10) == 110.0  # y no 111


def test_presupuesto_sugerido_sin_historial_o_margen_negativo(datos):
    sin_compras = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)[5]
    with pytest.raises(ValueError, match="historial"):
        presupuesto_sugerido(sin_compras)
    con_compras = perfiles(datos.clientes, datos.ventas, datos.productos, HOY)[0]
    with pytest.raises(ValueError, match="margen"):
        presupuesto_sugerido(con_compras, margen=-0.1)


def test_categorias_de_las_recomendaciones(datos, motor):
    _, _, recs = contexto(datos, motor, "c001")
    # p009 accesorios, p005 audio, p004 monitores, p006 perifericos, p010 mobiliario
    assert categorias_de_recomendaciones(recs, datos.productos) == (
        "accesorios",
        "audio",
        "monitores",
    )
    assert categorias_de_recomendaciones(recs, datos.productos, maximo=2) == ("accesorios", "audio")
    assert categorias_de_recomendaciones(recs, datos.productos, maximo=0) == ()
    assert len(categorias_de_recomendaciones(recs, datos.productos, maximo=10)) == 5


def test_categorias_de_recomendaciones_producto_fuera_del_catalogo(datos):
    rec = Recomendacion("c001", "p999", soporte=1, confianza=0.5)
    with pytest.raises(ValueError, match="catálogo"):
        categorias_de_recomendaciones([rec], datos.productos)


def test_categorias_alcanzables(datos):
    todas = ("computo", "monitores", "perifericos", "accesorios", "inexistente")
    # Con S/ 100: el periférico más barato cuesta 45 y el accesorio más barato 60.
    assert categorias_alcanzables(todas, datos.productos, 100) == ("perifericos", "accesorios")
    assert categorias_alcanzables(todas, datos.productos, 45) == ("perifericos",)
    assert categorias_alcanzables(todas, datos.productos, 44.99) == ()


def test_puntaje_suma_la_confianza_de_lo_incluido():
    recs = [
        Recomendacion("c001", "p009", soporte=5, confianza=1.0),
        Recomendacion("c001", "p005", soporte=4, confianza=0.8),
    ]
    assert puntaje(["p009", "p005", "p001"], recs) == 1.8
    assert puntaje(["p001"], recs) == 0
    assert puntaje([], recs) == 0


# =====================================================================
# Objetos
# =====================================================================
def test_pedido_subtotal_y_descuento_polimorfico(datos):
    por_id = {p.id_producto: p for p in datos.productos}
    pedido = Pedido((por_id["p004"], por_id["p005"], por_id["p009"]))
    assert pedido.ids == ("p004", "p005", "p009")
    assert pedido.subtotal == 675.0
    assert pedido.total_para(ClienteRegular("c001", "Juan")) == 675.0
    assert pedido.total_para(ClienteFrecuente("c001", "Juan")) == 607.5


def test_pedido_vacio_no_es_valido():
    with pytest.raises(ValueError):
        Pedido(())


def test_pedido_es_inmutable(datos):
    pedido = Pedido((datos.productos[0],))
    with pytest.raises(FrozenInstanceError):
        pedido.productos = ()


# =====================================================================
# Pedido sugerido para un cliente (calculado a mano sobre el dataset)
# =====================================================================
def test_pedido_de_juan(datos, motor):
    # Presupuesto 972. Recomendados: accesorios p009, audio p005, monitores p004.
    # Juan ya tiene p007, así que accesorios solo ofrece p009: 60 + 95 + 520 = 675.
    (sugerido,) = sugeridos(datos, motor, "c001")
    assert sugerido.pedido.ids == ("p004", "p005", "p009")
    assert sugerido.pedido.subtotal == 675.0
    assert sugerido.presupuesto == 972.0
    assert sugerido.recomendados_incluidos == ("p009", "p005", "p004")
    assert sugerido.puntaje == pytest.approx(2.2)
    assert sugerido.total_con_descuento == 607.5  # cliente frecuente: -10%


def test_pedido_de_maria(datos, motor):
    (sugerido,) = sugeridos(datos, motor, "c002")
    assert sugerido.pedido.ids == ("p006", "p007", "p008")
    assert sugerido.pedido.subtotal == 425.0
    assert sugerido.total_con_descuento == 382.5


def test_sin_dos_productos_que_quepan_no_se_sugiere_pedido(datos, motor):
    # Carlos (c003): presupuesto 176. Computo, monitores y almacenamiento no caben;
    # de perifericos (p002 y p003 ya los tiene) solo queda p006 = 110: un producto
    # solo no es una combinación.
    assert sugeridos(datos, motor, "c003") == ()


def test_respaldo_nunca_baja_a_un_solo_producto(datos, motor):
    # Lucía (c008): presupuesto 114. El periférico recomendado (p003 = 120) no cabe y
    # dos accesorios (p007 + p009 = 145) tampoco: antes se ofrecía p007 solo.
    assert sugeridos(datos, motor, "c008") == ()


def test_varios_pedidos_ordenados_por_puntaje(datos, motor):
    # Luis (c005), presupuesto 319: perifericos + audio + accesorios (p007).
    # Confianzas: p002 = 1.0, p003 = 0.6, p006 = 0.4, p005 = 0.8, p007 = 0.2
    resultado = sugeridos(datos, motor, "c005")
    assert [s.pedido.ids for s in resultado] == [
        ("p002", "p005", "p007"),
        ("p003", "p005", "p007"),
        ("p005", "p006", "p007"),
    ]
    assert [s.puntaje for s in resultado] == pytest.approx([2.0, 1.6, 1.4])


def test_limite_de_pedidos_sugeridos(datos, motor):
    assert len(sugeridos(datos, motor, "c005", n=1)) == 1
    assert sugeridos(datos, motor, "c005", n=0) == ()


def test_margen_mayor_amplia_las_opciones(datos, motor):
    base = sugeridos(datos, motor, "c004")  # presupuesto 126: solo cabe p003, sin pareja
    amplio = sugeridos(datos, motor, "c004", margen=5.0)  # presupuesto 683: caben combinaciones
    assert base == ()
    assert amplio[0].presupuesto == 683.0 and len(amplio[0].pedido.ids) >= 2


def test_cliente_sin_compras_o_sin_recomendaciones(datos, motor):
    cliente, perfil, _ = contexto(datos, motor, "c006")
    assert pedidos_para_cliente(cliente, perfil, [], datos.productos, motor) == ()
    c1, p1, _ = contexto(datos, motor, "c001")
    assert pedidos_para_cliente(c1, p1, [], datos.productos, motor) == ()


@pytest.mark.parametrize("id_cliente", ["c001", "c002", "c003", "c004", "c005", "c007", "c008"])
def test_invariantes_de_todos_los_pedidos(datos, motor, id_cliente):
    propios = {v.id_producto for v in datos.ventas if v.id_cliente == id_cliente}
    resultado = sugeridos(datos, motor, id_cliente)
    # Carlos, Ana y Lucía no tienen dos productos que quepan juntos en su presupuesto.
    assert bool(resultado) == (id_cliente not in {"c003", "c004", "c008"})
    for s in resultado:
        assert len(s.pedido.ids) >= 2
        assert s.pedido.subtotal <= s.presupuesto
        assert not set(s.pedido.ids) & propios
        assert len(set(s.pedido.ids)) == len(s.pedido.ids)
        assert s.total_con_descuento <= s.pedido.subtotal
    puntajes = [s.puntaje for s in resultado]
    assert puntajes == sorted(puntajes, reverse=True)


def test_desempate_prefiere_el_pedido_de_mayor_valor():
    puente = PuenteProlog()
    puente.cargar_compras([])
    productos = [
        Producto("p001", "Barato", "cat", 10.0),
        Producto("p002", "Caro", "cat", 30.0),
        Producto("p003", "Medio", "cat", 20.0),
    ]
    perfil = PerfilCliente("c001", 1, date(2026, 9, 1), 4, 40.0, 40.0, ("cat",))
    rec = Recomendacion("c001", "p001", soporte=1, confianza=0.5)
    cliente = ClienteRegular("c001", "Juan")
    resultado = pedidos_para_cliente(cliente, perfil, [rec], productos, puente, n=3)
    # Presupuesto 44: p002 + p003 = 50 no cabe. Ambas parejas llevan el recomendado
    # p001 (mismo puntaje), así que gana la de mayor valor.
    assert [s.pedido.ids for s in resultado] == [("p001", "p002"), ("p001", "p003")]


# =====================================================================
# Modo mostrador
# =====================================================================
def test_pedido_manual_ordenado_por_aprovechamiento(datos, motor):
    resultado = armar_pedido_manual(motor, datos.productos, 200, ["perifericos", "accesorios"])
    assert [(p.ids, p.subtotal) for p in resultado] == [
        (("p006", "p007"), 195.0),
        (("p003", "p009"), 180.0),
        (("p006", "p009"), 170.0),
        (("p002", "p007"), 130.0),
        (("p002", "p009"), 105.0),
    ]


def test_pedido_manual_limita_la_cantidad(datos, motor):
    args = (motor, datos.productos, 200, ["perifericos", "accesorios"])
    assert len(armar_pedido_manual(*args, n=2)) == 2
    assert armar_pedido_manual(*args, n=0) == ()


def test_pedido_manual_sin_resultados(datos, motor):
    assert armar_pedido_manual(motor, datos.productos, 50, ["perifericos", "accesorios"]) == ()


def test_pedido_manual_acepta_generadores(datos, motor):
    resultado = armar_pedido_manual(motor, iter(datos.productos), 200, iter(["perifericos", "accesorios"]))
    assert len(resultado) == 5


def test_pedido_manual_con_una_categoria_combina_dos_productos_de_ella(datos, motor):
    # Periféricos: p002 = 45, p003 = 120, p006 = 110. p003 + p006 = 230 no cabe en 200.
    resultado = armar_pedido_manual(motor, datos.productos, 200, ["perifericos"])
    assert [(p.ids, p.subtotal) for p in resultado] == [(("p002", "p003"), 165.0), (("p002", "p006"), 155.0)]


def test_pedido_manual_si_solo_alcanza_un_producto_no_hay_combinacion(datos, motor):
    # Audio tiene un solo producto (p005 = 95): con S/ 200 no hay con qué combinarlo.
    assert armar_pedido_manual(motor, datos.productos, 200, ["audio"]) == ()
    # Periféricos + monitores: el monitor (520) no cabe; un periférico solo no es combinación.
    assert armar_pedido_manual(motor, datos.productos, 200, ["perifericos", "monitores"]) == ()


# =====================================================================
# Ofertas en el modo mostrador
# =====================================================================
MEDIO_PRECIO_MOUSE = {"p002": Oferta("p002", 50, date(2026, 10, 1), date(2026, 10, 31))}


def test_las_combinaciones_con_oferta_van_primero(datos, motor):
    # Mouse p002: 45 -> 22.50. Luego, el resto de mayor a menor valor.
    resultado = armar_pedido_manual(
        motor, datos.productos, 200, ["perifericos", "accesorios"], vigentes=MEDIO_PRECIO_MOUSE
    )
    assert [(p.ids, p.subtotal) for p in resultado] == [
        (("p002", "p007"), 107.5),
        (("p002", "p009"), 82.5),
        (("p006", "p007"), 195.0),
        (("p003", "p009"), 180.0),
        (("p006", "p009"), 170.0),
    ]


def test_la_oferta_hace_caber_una_combinacion(datos, motor):
    # Sin oferta, p002 + p009 = 105 no cabe en 100; con el mouse a 22.50 sí (82.50).
    args = (motor, datos.productos, 100, ["perifericos", "accesorios"])
    assert armar_pedido_manual(*args) == ()
    assert [p.ids for p in armar_pedido_manual(*args, vigentes=MEDIO_PRECIO_MOUSE)] == [("p002", "p009")]


def test_el_pedido_lleva_el_precio_de_oferta(datos, motor):
    (pedido, *_) = armar_pedido_manual(
        motor, datos.productos, 200, ["perifericos", "accesorios"], vigentes=MEDIO_PRECIO_MOUSE
    )
    assert [p.precio for p in pedido.productos] == [22.5, 85.0]


def test_mas_ofertas_en_la_combinacion_la_suben_mas(datos, motor):
    vigentes = {
        **MEDIO_PRECIO_MOUSE,
        "p009": Oferta("p009", 10, date(2026, 10, 1), date(2026, 10, 31)),  # hub: 60 -> 54
    }
    (primero, *_) = armar_pedido_manual(motor, datos.productos, 200, ["perifericos", "accesorios"], vigentes=vigentes)
    assert primero.ids == ("p002", "p009") and primero.subtotal == 76.5


# =====================================================================
# Ofertas en los pedidos sugeridos de la agenda
# =====================================================================
OCTUBRE = (date(2026, 10, 1), date(2026, 10, 31))
CATALOGO_AB = [
    Producto("p001", "A barato", "a", 10.0),
    Producto("p002", "A caro", "a", 30.0),
    Producto("p003", "B normal", "b", 20.0),
    Producto("p004", "B en oferta", "b", 25.0),
]
PERFIL_A = PerfilCliente("c001", 1, date(2026, 9, 1), 4, 50.0, 50.0, ("a",))  # presupuesto 55
REC_P001 = (Recomendacion("c001", "p001", soporte=1, confianza=0.5),)
OFERTA_P004 = {"p004": Oferta("p004", 30, *OCTUBRE)}  # 25 -> 17.50


def sugeridos_ab(cliente, vigentes, perfil=PERFIL_A, recs=REC_P001, n=3):
    puente = PuenteProlog()
    puente.cargar_compras([])
    return pedidos_para_cliente(cliente, perfil, recs, CATALOGO_AB, puente, n=n, vigentes=vigentes)


def test_una_oferta_sin_relacion_con_el_cliente_no_se_le_empuja():
    # Regular, compra la categoría a y su recomendado es p001: la oferta de b no le corresponde.
    resultado = sugeridos_ab(ClienteRegular("c001", "Juan"), OFERTA_P004)
    assert [s.pedido.ids for s in resultado] == [("p001", "p002")]
    assert resultado[0].ofertas_incluidas == ()


def test_al_cliente_frecuente_se_le_priorizan_las_ofertas():
    # Presupuesto 55. Primero las parejas con la oferta (p004 = 17.50), y entre ellas
    # la que lleva el recomendado p001; luego las demás por puntaje.
    resultado = sugeridos_ab(ClienteFrecuente("c001", "Juan"), OFERTA_P004)
    assert [(s.pedido.ids, s.pedido.subtotal) for s in resultado] == [
        (("p001", "p004"), 27.5),
        (("p002", "p004"), 47.5),
        (("p001", "p003"), 30.0),
    ]
    assert [o.id_producto for o in resultado[0].ofertas_incluidas] == ["p004"]
    assert resultado[0].total_con_descuento == 24.75  # además, su 10 % de cliente frecuente


def test_oferta_en_una_categoria_que_el_cliente_compra():
    perfil = PerfilCliente("c001", 1, date(2026, 9, 1), 4, 50.0, 50.0, ("b",))
    resultado = sugeridos_ab(ClienteRegular("c001", "Juan"), OFERTA_P004, perfil=perfil)
    assert resultado[0].pedido.ids == ("p001", "p004")


def test_sin_recomendaciones_pero_con_ofertas_para_el_cliente_igual_se_sugiere():
    resultado = sugeridos_ab(ClienteFrecuente("c001", "Juan"), OFERTA_P004, recs=())
    assert resultado and all("p004" in s.pedido.ids for s in resultado[:2])


def test_ofertas_para_cliente_y_sus_motivos():
    vigentes = {
        "p001": Oferta("p001", 10, *OCTUBRE),  # recomendado: lo compraron clientes parecidos
        "p002": Oferta("p002", 10, *OCTUBRE),  # categoría a, la que compra
        "p003": Oferta("p003", 10, *OCTUBRE),  # categoría b: solo por ser frecuente
        "p004": Oferta("p004", 50, *OCTUBRE),  # ya lo compró: nunca
    }
    regular = ofertas_para_cliente(vigentes, CATALOGO_AB, PERFIL_A, REC_P001, frecuente=False, comprados={"p004"})
    assert [(o.id_producto, o.motivos) for o in regular] == [
        ("p001", ("similares", "categoria_habitual")),
        ("p002", ("categoria_habitual",)),
    ]
    frecuente = ofertas_para_cliente(vigentes, CATALOGO_AB, PERFIL_A, REC_P001, frecuente=True, comprados={"p004"})
    assert [(o.id_producto, o.motivos) for o in frecuente] == [
        ("p001", ("similares", "categoria_habitual", "cliente_frecuente")),
        ("p002", ("categoria_habitual", "cliente_frecuente")),
        ("p003", ("cliente_frecuente",)),
    ]
