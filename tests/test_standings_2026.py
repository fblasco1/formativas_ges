# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.febamba.standings_2026 import (
    PartidoGeneral,
    PartidoPresentacion,
    clave_equipo,
    construir_standings,
    construir_tabla_resultado_mini,
    decidir_presentacion_partido,
    es_marcador_raro,
    puntos_partido_general,
)


def _jugadores(n_con_min: int, minutos: str = "12:00", extra_cortos: int = 0):
    js = [{"min": minutos} for _ in range(n_con_min)]
    js += [{"min": "05:00"} for _ in range(extra_cortos)]
    return js


# --------------------------------------------------------------------------- #
# Clave de equipo
# --------------------------------------------------------------------------- #
def test_clave_equipo_quita_categoria():
    assert clave_equipo("SPORTIVO PILAR CADETES") == "SPORTIVO PILAR"
    assert clave_equipo("SPORTIVO PILAR  JUVENILES") == "SPORTIVO PILAR"
    assert clave_equipo("SPORTIVO PILAR INFANTILES") == "SPORTIVO PILAR"


def test_clave_equipo_conserva_color_letra():
    # Los modificadores (color/letra) se ordenan, pero se conservan.
    assert clave_equipo("CAZA Y PESCA AZUL A") == "CAZA Y PESCA A AZUL"
    assert clave_equipo('A.F.A.L.P. "A"') == "AFALP A"


def test_clave_equipo_ignora_puntos_y_guiones():
    assert clave_equipo("C.A.S.A PADUA B") == clave_equipo("C.A.S.A. PADUA B")
    assert clave_equipo("VELEZ SARSFIELD BLANCO - A") == clave_equipo(
        "VELEZ SARSFIELD BLANCO A"
    )


def test_clave_equipo_unifica_orden():
    assert clave_equipo("CIUDAD DE BUENOS AIRES A AZUL") == clave_equipo(
        "CIUDAD DE BUENOS AIRES AZUL A"
    )


def test_clave_equipo_unifica_genero_color():
    assert clave_equipo("FERROCARRIL OESTE BLANCA") == clave_equipo(
        "FERROCARRIL OESTE BLANCO"
    )
    # Pero NARANJA y VERDE son equipos distintos.
    assert clave_equipo("FERROCARRIL OESTE NARANJA") != clave_equipo(
        "FERROCARRIL OESTE VERDE"
    )


def test_clave_equipo_no_sobreunifica():
    assert clave_equipo("BOCA JUNIORS AZUL A") != clave_equipo("BOCA JUNIORS AMARILLO B")


# --------------------------------------------------------------------------- #
# Puntaje general
# --------------------------------------------------------------------------- #
def test_puntos_normal():
    assert puntos_partido_general(70, 57) == (2, 1, "normal")
    assert puntos_partido_general(57, 70) == (1, 2, "normal")


def test_puntos_walkover():
    assert puntos_partido_general(20, 0) == (2, 0, "walkover_local")
    assert puntos_partido_general(0, 20) == (0, 2, "walkover_visit")


def test_puntos_ambos_ausentes_y_pendiente():
    assert puntos_partido_general(0, 0) == (0, 0, "ambos_ausentes")
    assert puntos_partido_general(None, None) == (0, 0, "sin_resultado")


# --------------------------------------------------------------------------- #
# Presentación
# --------------------------------------------------------------------------- #
def test_marcador_raro():
    assert es_marcador_raro(20, 0)
    assert es_marcador_raro(0, 20)
    assert es_marcador_raro(0, 0)
    assert not es_marcador_raro(15, 8)


def test_presentacion_normal_ambos():
    assert decidir_presentacion_partido(15, 12) == (True, True)


def test_presentacion_raro_usa_acta():
    # 20-0: local con 12+ jugadores presenta, visitante con 5 no.
    res = decidir_presentacion_partido(20, 0, _jugadores(12), _jugadores(5))
    assert res == (True, False)


def test_presentacion_raro_sin_acta_desconocido():
    assert decidir_presentacion_partido(0, 0) == (None, None)


# --------------------------------------------------------------------------- #
# Agregación por zona
# --------------------------------------------------------------------------- #
def test_standings_basico_por_zona():
    generales = [
        # Zona NORTE 1A, U15: A le gana a B
        PartidoGeneral("U15", "CLASIFICACION", "NORTE 1A", "CLUB A", "CLUB B", 70, 60),
        # U13: B le gana a A
        PartidoGeneral("U13", "CLASIFICACION", "NORTE 1A", "CLUB B", "CLUB A", 50, 40),
        # U17: A walkover 20-0 contra B (B no se presentó)
        PartidoGeneral("U17", "CLASIFICACION", "NORTE 1A", "CLUB A", "CLUB B", 20, 0),
    ]
    presentaciones = [
        # U11: A y B juegan normal -> ambos presentan
        PartidoPresentacion("U11", "CLASIFICACION", "CLUB A", "CLUB B", 18, 10),
        # U9: A presenta, B no (20-0 con acta)
        PartidoPresentacion(
            "U9", "CLASIFICACION", "CLUB A", "CLUB B", 20, 0,
            presenta_local=True, presenta_visit=False, raro=True,
        ),
    ]
    res = construir_standings(generales, presentaciones)
    tabla = res.tablas["CLASIFICACION"]["NORTE 1A"]
    por_eq = {f.equipo: f for f in tabla}

    a = por_eq["CLUB A"]
    b = por_eq["CLUB B"]

    # CLUB A: U15 gana(2) + U13 pierde(1) + U17 walkover gana(2) = 5 generales
    assert a.pts_general == 5
    # presentación: U11 (1) + U9 (1) = 2
    assert a.pts_presentacion == 2
    assert a.puntos == 7
    assert a.ganados == 2
    assert a.perdidos == 1
    assert a.walkover_favor == 1

    # CLUB B: U15 pierde(1) + U13 gana(2) + U17 no se presentó(0) = 3 generales
    assert b.pts_general == 3
    # presentación: U11 (1) + U9 no presentó (0) = 1
    assert b.pts_presentacion == 1
    assert b.puntos == 4
    assert b.walkover_contra == 1

    # Orden: A primero
    assert tabla[0].equipo == "CLUB A"


# --------------------------------------------------------------------------- #
# Tabla de resultados MINI (U11): ganado/perdido por acta + presentación
# --------------------------------------------------------------------------- #
def _box(pts_local, jl, pts_visit, jv):
    """Acta sintética: jl/jv = nº de jugadores con >= 10:00 (presentación)."""
    return {
        "ok": True,
        "equipos": [
            {"nombre": "L", "jugadores": _jugadores(jl), "pts": pts_local},
            {"nombre": "V", "jugadores": _jugadores(jv), "pts": pts_visit},
        ],
    }


def _pp_u11(local, visit, idp, pl=0, pv=0, zona="NORTE 1A", raro=True):
    return PartidoPresentacion(
        "U11", "CLASIFICACION", local, visit, pl, pv,
        id_partido=idp, zona=zona, raro=raro,
    )


def test_u11_resultado_por_boxscore_no_por_fixture():
    # Marcador de fixture 20-0 (código de presentación), pero el acta dice 48-55:
    # gana el visitante. Ambos presentan (12 jugadores con >= 10:00).
    presentaciones = [_pp_u11("CLUB A", "CLUB B", "p1", pl=20, pv=0)]
    boxscores = {"p1": _box(48, 12, 55, 12)}
    tabla = construir_tabla_resultado_mini(presentaciones, boxscores)
    por_eq = {f.equipo: f for f in tabla["CLASIFICACION"]["NORTE 1A"]}
    a, b = por_eq["CLUB A"], por_eq["CLUB B"]
    assert (a.ganados, a.perdidos) == (0, 1)
    assert (b.ganados, b.perdidos) == (1, 0)
    # Ambos presentaron -> 1 punto de presentación cada uno.
    assert a.presentaciones == 1
    assert b.presentaciones == 1


def test_u11_presentacion_segun_plantilla():
    # Local presenta (12), visitante no (5). Local gana en cancha.
    presentaciones = [_pp_u11("CLUB A", "CLUB B", "p1", pl=0, pv=0)]
    boxscores = {"p1": _box(60, 12, 40, 5)}
    tabla = construir_tabla_resultado_mini(presentaciones, boxscores)
    por_eq = {f.equipo: f for f in tabla["CLASIFICACION"]["NORTE 1A"]}
    a, b = por_eq["CLUB A"], por_eq["CLUB B"]
    assert a.presentaciones == 1 and a.no_presento == 0
    assert b.presentaciones == 0 and b.no_presento == 1
    assert (a.ganados, b.perdidos) == (1, 1)


def test_u11_sin_acta_no_suma_resultado():
    presentaciones = [_pp_u11("CLUB A", "CLUB B", "p1", pl=0, pv=0)]
    tabla = construir_tabla_resultado_mini(presentaciones, boxscores={})
    por_eq = {f.equipo: f for f in tabla["CLASIFICACION"]["NORTE 1A"]}
    a = por_eq["CLUB A"]
    assert a.pj == 1
    assert (a.ganados, a.perdidos) == (0, 0)
    assert a.sin_resultado == 1
    assert a.sin_acta == 1
    assert a.presentaciones == 0


def test_u11_orden_por_resultados():
    # A: 2 ganados; B: 1 ganado; C: 0. Orden esperado A, B, C.
    presentaciones = [
        _pp_u11("CLUB A", "CLUB B", "p1"),
        _pp_u11("CLUB A", "CLUB C", "p2"),
        _pp_u11("CLUB B", "CLUB C", "p3"),
    ]
    boxscores = {
        "p1": _box(60, 12, 40, 12),  # A gana a B
        "p2": _box(60, 12, 40, 12),  # A gana a C
        "p3": _box(60, 12, 40, 12),  # B gana a C
    }
    tabla = construir_tabla_resultado_mini(presentaciones, boxscores)
    orden = [f.equipo for f in tabla["CLASIFICACION"]["NORTE 1A"]]
    assert orden == ["CLUB A", "CLUB B", "CLUB C"]


def test_u11_desempate_por_presentaciones():
    # A y B con 1 ganado y 0 perdido cada uno (rivales distintos), pero B presentó
    # más veces -> B va arriba por el tercer criterio (presentaciones desc).
    presentaciones = [
        _pp_u11("CLUB A", "CLUB X", "p1"),
        _pp_u11("CLUB B", "CLUB Y", "p2"),
    ]
    boxscores = {
        "p1": _box(60, 5, 40, 5),    # A gana; nadie presenta (5 < 12)
        "p2": _box(60, 12, 40, 5),   # B gana y presenta
    }
    tabla = construir_tabla_resultado_mini(presentaciones, boxscores)
    filas = {f.equipo: f for f in tabla["CLASIFICACION"]["NORTE 1A"]}
    assert filas["CLUB A"].presentaciones == 0
    assert filas["CLUB B"].presentaciones == 1
    orden = [f.equipo for f in tabla["CLASIFICACION"]["NORTE 1A"]]
    assert orden.index("CLUB B") < orden.index("CLUB A")


def test_presentacion_sin_zona_se_reporta():
    generales = [
        PartidoGeneral("U15", "CLASIFICACION", "NORTE 1A", "CLUB A", "CLUB B", 70, 60),
    ]
    presentaciones = [
        # Equipo que no existe en ninguna zona general
        PartidoPresentacion("U11", "CLASIFICACION", "CLUB FANTASMA", "CLUB B", 18, 10),
    ]
    res = construir_standings(generales, presentaciones)
    claves_sin = {x["clave"] for x in res.presentaciones_sin_zona}
    assert "CLUB FANTASMA" in claves_sin
    # CLUB B sí está en zona -> recibe su punto
    b = {f.equipo: f for f in res.tablas["CLASIFICACION"]["NORTE 1A"]}["CLUB B"]
    assert b.pts_presentacion == 1
