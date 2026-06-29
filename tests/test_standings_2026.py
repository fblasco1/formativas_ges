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
