# -*- coding: utf-8 -*-
"""
Genera la tabla de posiciones general de FORMATIVAS 2026 (competencia GES 2015).

Suma, por zona y por nivel (Clasificatorio / Reclasificación / Interconferencia A-B /
Nivel 1), los puntos de las categorías U13/U15/U17 (ganado=2, perdido=1, walkover
20-0 = 2 y 0 para el ausente) más los puntos de presentación de U9/U11 (1 por equipo
que llega al mínimo de 12 jugadores con >= 10:00 de juego; en marcadores raros se
valida con el acta de argentina.basketball). La UI navega Etapa → Nivel → Zona.

Ejemplos:
  python analysis/generar_standings_febamba_2026.py --progress
  python analysis/generar_standings_febamba_2026.py --sin-actas --progress      # rápido
  python analysis/generar_standings_febamba_2026.py --desde-json outputs/formativas_2026/datos.json
  python analysis/generar_standings_febamba_2026.py --progress --publicar-docs
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.partido import parse_boxscore_html
from ingest.argbasket.pbp_reglas import fetch_y_analizar
from ingest.febamba.mini_masc_regla_plantilla import (
    jugador_cumple_regla,
    parse_minutos_a_segundos,
)
from ingest.febamba.standings_2026 import (
    CATEGORIAS,
    EDADES_GENERAL,
    EDADES_PRESENTACION,
    ETAPA_LABEL,
    ETAPA_POR_FASE,
    FASES_CANONICAS,
    FASE_LABEL,
    FASE_ORDER,
    ID_COMPETENCIA,
    MIN_JUGADORES_REGLA,
    NIVELES_POR_ETAPA,
    PartidoGeneral,
    PartidoPresentacion,
    construir_standings,
    construir_tablas_categoria,
    construir_tablas_presentacion,
    construir_tabla_resultado_mini,
    registrar_nombres_globales,
    nombre_display,
    norm_zona,
    puntos_partido_general,
    decidir_presentacion_partido,
    presentacion_desde_acta,
    segundos_minimos,
    es_marcador_raro,
)
from ingest.febamba.mini_masc_regla_plantilla import (
    MIN_SEGUNDOS_PREMINI,
    MIN_SEGUNDOS_REGLA,
)
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider

OUT_DIR = ROOT / "outputs" / "formativas_2026"
OUT_HTML = OUT_DIR / "tabla_posiciones.html"
OUT_JSON = OUT_DIR / "datos.json"
ACTAS_CACHE = OUT_DIR / "actas_cache.json"
BOXSCORES_CACHE = OUT_DIR / "boxscores.json"
PBP_U11_CACHE = OUT_DIR / "pbp_u11.json"
DOCS_HTML = ROOT / "docs" / "formativas_2026_tabla_posiciones.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/formativas_2026_tabla_posiciones.html"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def _load_widget_key() -> str:
    with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return None


def _es_fase_excluida(nombre_ges: str) -> bool:
    """True si la fase GES queda fuera del informe (p.ej. CLASIFICACION LFF)."""
    u = (nombre_ges or "").strip().upper()
    return "LFF" in u


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


def resolver_fases(
    ges: GesDeportivaExtractor,
) -> Dict[str, Dict[str, str]]:
    """edad -> {fase_canonica: id_fase}. Empareja por nombre GES; excluye LFF."""
    out: Dict[str, Dict[str, str]] = {}
    for edad, meta in CATEGORIAS.items():
        fases, _ = ges.get_ids_fases_grupos(
            ID_COMPETENCIA, id_categoria=int(meta["id_categoria"])
        )
        canon_map: Dict[str, str] = {}
        for canon, nombres in FASES_CANONICAS.items():
            wanted = {n.upper() for n in nombres}
            for nombre_ges, fid in fases.items():
                if _es_fase_excluida(nombre_ges):
                    continue
                if nombre_ges.strip().upper() in wanted:
                    canon_map[canon] = fid
                    break
        out[edad] = canon_map
    return out


# --------------------------------------------------------------------------- #
# Recolección de partidos generales (U13/U15/U17)
# --------------------------------------------------------------------------- #
def recolectar_generales(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    fases_por_edad: Dict[str, Dict[str, str]],
    progress: bool = False,
) -> List[PartidoGeneral]:
    out: List[PartidoGeneral] = []
    for edad in EDADES_GENERAL:
        cat = int(CATEGORIAS[edad]["id_categoria"])
        for fase_canon, id_fase in fases_por_edad.get(edad, {}).items():
            grupos = ges.get_grupos_de_fase(ID_COMPETENCIA, cat, int(id_fase))
            if progress:
                print(
                    f"  {edad} {fase_canon}: {len(grupos)} grupos",
                    file=sys.stderr,
                    flush=True,
                )
            for nombre_grupo, id_grupo in grupos.items():
                zona = norm_zona(nombre_grupo)
                partidos = ges.get_info_partidos(
                    cat,
                    fecha_ini,
                    fecha_fin,
                    key=key,
                    id_fase=int(id_fase),
                    id_grupo=int(id_grupo),
                )
                for p in partidos:
                    if p.get("Estado") != "COMPLETO":
                        continue  # excluye partidos no jugados / sin resultado (fecha futura)
                    out.append(
                        PartidoGeneral(
                            edad=edad,
                            fase=fase_canon,
                            zona=zona,
                            local=p.get("Local") or "",
                            visitante=p.get("Visitante") or "",
                            pts_local=_to_int(p.get("PTS_LOCAL")),
                            pts_visit=_to_int(p.get("PTS_VISITANTE")),
                            id_partido=p.get("ID_PARTIDO") or "",
                            fecha=p.get("Fecha") or "",
                        )
                    )
    return out


# --------------------------------------------------------------------------- #
# Recolección de partidos de presentación (U9/U11)
# --------------------------------------------------------------------------- #
def _actas_jugadores(token: str) -> Optional[Tuple[List[dict], List[dict]]]:
    """Descarga el acta y devuelve (jugadores_local, jugadores_visit) o None."""
    try:
        resp = requests.get(
            _boxscore_url(token),
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            timeout=45,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None
    if len(html) < 8000:
        return None
    equipos = parse_boxscore_html(html).get("equipos") or []
    jug_local = (equipos[0].get("jugadores") or []) if equipos else []
    jug_visit = (equipos[1].get("jugadores") or []) if len(equipos) > 1 else []
    return jug_local, jug_visit


def _jugador_ui(j: Dict[str, object]) -> Dict[str, object]:
    return {
        "nro": j.get("dorsal") or j.get("nro") or "",
        "nombre": j.get("nombre") or "",
        "min": j.get("min") or "",
        "seg": parse_minutos_a_segundos(j.get("min")) or 0,
        "pts": j.get("pts") if j.get("pts") is not None else "",
    }


def _descargar_boxscore(token: str) -> Dict[str, object]:
    """Descarga y parsea un acta. Devuelve dict con equipos/jugadores o {'ok': False}."""
    try:
        resp = requests.get(
            _boxscore_url(token),
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            timeout=45,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return {"ok": False}
    if len(html) < 8000:
        return {"ok": False}
    equipos_raw = parse_boxscore_html(html).get("equipos") or []
    equipos = []
    for eq in equipos_raw[:2]:
        jugs = [_jugador_ui(j) for j in (eq.get("jugadores") or [])]
        pts = sum((_to_int(j["pts"]) or 0) for j in jugs)
        equipos.append(
            {
                "nombre": eq.get("nombre") or "",
                "jugadores": jugs,
                "pts": pts,
            }
        )
    return {"ok": bool(equipos), "equipos": equipos}


def _cargar_boxscores_cache() -> Dict[str, Dict[str, object]]:
    if BOXSCORES_CACHE.exists():
        try:
            return json.loads(BOXSCORES_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_boxscores_cache(cache: Dict[str, Dict[str, object]]) -> None:
    BOXSCORES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BOXSCORES_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False), encoding="utf-8"
    )


def descargar_boxscores(
    tokens: List[str],
    *,
    workers: int = 12,
    progress: bool = False,
    limite: int = 0,
) -> Dict[str, Dict[str, object]]:
    """Descarga (con caché) los boxscores de los tokens dados. Devuelve token -> acta."""
    cache = _cargar_boxscores_cache()
    unicos = [t for t in dict.fromkeys(tokens) if t]
    pendientes = [t for t in unicos if t not in cache]
    if limite > 0:
        pendientes = pendientes[:limite]
    if progress:
        print(
            f"Boxscores: {len(unicos)} partidos, {len(cache)} en caché, "
            f"{len(pendientes)} a descargar…",
            file=sys.stderr,
        )
    if pendientes:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut = {pool.submit(_descargar_boxscore, t): t for t in pendientes}
            done = 0
            for f in as_completed(fut):
                cache[fut[f]] = f.result()
                done += 1
                if progress and (done % 100 == 0 or done == len(pendientes)):
                    print(f"  {done}/{len(pendientes)}", file=sys.stderr, flush=True)
        _guardar_boxscores_cache(cache)
    return {t: cache[t] for t in unicos if t in cache and cache[t].get("ok")}


# --------------------------------------------------------------------------- #
# Play-by-play (cambios Q3 / cuartos consecutivos) — SOLO U11
# --------------------------------------------------------------------------- #
def _cargar_pbp_cache() -> Dict[str, Dict[str, object]]:
    if PBP_U11_CACHE.exists():
        try:
            return json.loads(PBP_U11_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_pbp_cache(cache: Dict[str, Dict[str, object]]) -> None:
    PBP_U11_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PBP_U11_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _descargar_pbp_uno(
    token: str, session: requests.Session
) -> Dict[str, object]:
    try:
        return fetch_y_analizar(token, session=session)
    except Exception:
        return {"tiene_pbp": False}


def descargar_pbp_u11(
    tokens: List[str],
    *,
    workers: int = 12,
    progress: bool = False,
    limite: int = 0,
) -> Dict[str, Dict[str, object]]:
    """Descarga (con caché) el análisis PBP de los partidos U11 dados."""
    cache = _cargar_pbp_cache()
    unicos = [t for t in dict.fromkeys(tokens) if t]
    pendientes = [t for t in unicos if t not in cache]
    if limite > 0:
        pendientes = pendientes[:limite]
    if progress:
        print(
            f"PBP U11: {len(unicos)} partidos, {len(cache)} en caché, "
            f"{len(pendientes)} a descargar…",
            file=sys.stderr,
        )
    if pendientes:
        session = requests.Session()
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut = {pool.submit(_descargar_pbp_uno, t, session): t for t in pendientes}
            done = 0
            for f in as_completed(fut):
                cache[fut[f]] = f.result()
                done += 1
                if progress and (done % 100 == 0 or done == len(pendientes)):
                    print(f"  {done}/{len(pendientes)}", file=sys.stderr, flush=True)
        _guardar_pbp_cache(cache)
    return {t: cache[t] for t in unicos if t in cache}


def recomputar_presentaciones_desde_boxscores(
    presentaciones: List[PartidoPresentacion],
    boxscores: Dict[str, Dict[str, object]],
) -> int:
    """
    Recalcula la decisión de presentación de los partidos con marcador raro a
    partir del acta descargada, aplicando el umbral de minutos por categoría
    (PREMINI/U9 = 8:00, MINI/U11 = 10:00). Devuelve cuántos se recalcularon.
    """
    n = 0
    for pp in presentaciones:
        if not pp.raro:
            continue
        thr = segundos_minimos(pp.edad)
        box = boxscores.get(pp.id_partido)
        if box and box.get("ok") and len(box.get("equipos") or []) >= 2:
            jl = box["equipos"][0].get("jugadores") or []
            jv = box["equipos"][1].get("jugadores") or []
            pp.presenta_local = presentacion_desde_acta(jl, thr)
            pp.presenta_visit = presentacion_desde_acta(jv, thr)
        else:
            pp.presenta_local = None
            pp.presenta_visit = None
        n += 1
    return n


def _cargar_actas_cache() -> Dict[str, Dict[str, Optional[bool]]]:
    if ACTAS_CACHE.exists():
        try:
            return json.loads(ACTAS_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_actas_cache(cache: Dict[str, Dict[str, Optional[bool]]]) -> None:
    ACTAS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ACTAS_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8"
    )


def recolectar_presentaciones(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    fases_por_edad: Dict[str, Dict[str, str]],
    fetch_actas: bool = True,
    limite_actas: int = 0,
    workers: int = 8,
    progress: bool = False,
) -> List[PartidoPresentacion]:
    base: List[PartidoPresentacion] = []
    raros: List[PartidoPresentacion] = []  # con marcador raro (necesitan acta)

    for edad in EDADES_PRESENTACION:
        cat = int(CATEGORIAS[edad]["id_categoria"])
        for fase_canon, id_fase in fases_por_edad.get(edad, {}).items():
            grupos = ges.get_grupos_de_fase(ID_COMPETENCIA, cat, int(id_fase))
            total_fase = 0
            for nombre_grupo, id_grupo in grupos.items():
                zona = norm_zona(nombre_grupo)
                partidos = ges.get_info_partidos(
                    cat,
                    fecha_ini,
                    fecha_fin,
                    key=key,
                    id_fase=int(id_fase),
                    id_grupo=int(id_grupo),
                )
                completos = [p for p in partidos if p.get("Estado") == "COMPLETO"]
                total_fase += len(completos)
                for p in completos:
                    pl = _to_int(p.get("PTS_LOCAL"))
                    pv = _to_int(p.get("PTS_VISITANTE"))
                    raro = es_marcador_raro(pl, pv)
                    pres_l, pres_v = decidir_presentacion_partido(pl, pv)
                    pp = PartidoPresentacion(
                        edad=edad,
                        fase=fase_canon,
                        local=p.get("Local") or "",
                        visitante=p.get("Visitante") or "",
                        pts_local=pl,
                        pts_visit=pv,
                        id_partido=p.get("ID_PARTIDO") or "",
                        fecha=p.get("Fecha") or "",
                        zona=zona,
                        presenta_local=pres_l,
                        presenta_visit=pres_v,
                        raro=raro,
                    )
                    base.append(pp)
                    if raro and pp.id_partido:
                        raros.append(pp)
            if progress:
                print(
                    f"  {edad} {fase_canon}: {total_fase} partidos con resultado "
                    f"({len(grupos)} zonas)",
                    file=sys.stderr,
                    flush=True,
                )

    # Resolver presentación de raros usando caché de actas; descargar faltantes.
    cache = _cargar_actas_cache()
    for pp in raros:
        hit = cache.get(pp.id_partido)
        if hit is not None:
            pp.presenta_local = hit.get("presenta_local")
            pp.presenta_visit = hit.get("presenta_visit")

    pendientes = [pp for pp in raros if pp.id_partido not in cache]
    if fetch_actas and pendientes:
        if limite_actas > 0:
            pendientes = pendientes[:limite_actas]
        if progress:
            print(
                f"  Actas en caché: {len(raros) - len(pendientes)}; "
                f"descargando {len(pendientes)} nuevas…",
                file=sys.stderr,
                flush=True,
            )

        def _task(pp: PartidoPresentacion) -> Tuple[PartidoPresentacion, Optional[Tuple]]:
            return pp, _actas_jugadores(pp.id_partido)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(_task, pp) for pp in pendientes]
            done = 0
            for fut in as_completed(futures):
                pp, actas = fut.result()
                if actas is not None:
                    jl, jv = actas
                    pres_l, pres_v = decidir_presentacion_partido(
                        pp.pts_local, pp.pts_visit, jl, jv
                    )
                    pp.presenta_local = pres_l
                    pp.presenta_visit = pres_v
                    cache[pp.id_partido] = {
                        "presenta_local": pres_l,
                        "presenta_visit": pres_v,
                    }
                done += 1
                if progress and (done % 50 == 0 or done == len(pendientes)):
                    print(f"    actas {done}/{len(pendientes)}", file=sys.stderr, flush=True)
        _guardar_actas_cache(cache)

    return base


# --------------------------------------------------------------------------- #
# Dataset (caché) y payload HTML
# --------------------------------------------------------------------------- #
def serializar_dataset(
    generales: List[PartidoGeneral], presentaciones: List[PartidoPresentacion]
) -> Dict[str, object]:
    return {
        "generales": [asdict(g) for g in generales],
        "presentaciones": [asdict(p) for p in presentaciones],
    }


def cargar_dataset(
    data: Dict[str, object]
) -> Tuple[List[PartidoGeneral], List[PartidoPresentacion]]:
    generales = [PartidoGeneral(**g) for g in data.get("generales", [])]
    presentaciones = [PartidoPresentacion(**p) for p in data.get("presentaciones", [])]
    return generales, presentaciones


def _fecha_key(fecha: object) -> Tuple[int, int, int, int, int]:
    """Convierte 'dd/mm/YYYY [HH:MM]' en una tupla ordenable. Vacías van al final."""
    s = ("" if fecha is None else str(fecha)).strip()
    if not s:
        return (9999, 12, 31, 23, 59)
    try:
        partes = s.split()
        d, m, y = (int(x) for x in partes[0].split("/"))
        hh = mm = 0
        if len(partes) > 1 and ":" in partes[1]:
            hh, mm = (int(x) for x in partes[1].split(":")[:2])
        return (y, m, d, hh, mm)
    except Exception:
        return (9999, 12, 31, 23, 59)


def _categoria_label(edad: str) -> str:
    nombre = str(CATEGORIAS[edad]["nombre_ges"]).replace(" MASCULINO", "").title()
    return f"{edad} · {nombre}"


def construir_partidos_detalle(
    generales: List[PartidoGeneral],
    presentaciones: List[PartidoPresentacion],
) -> Dict[str, Dict[str, Dict[str, list]]]:
    """
    Detalle de partidos por edad -> fase -> zona, con flags de incumplimiento.
    Para U13/U15/U17 marca no presentaciones (20-0 / 0-20 / 0-0); para U9/U11
    marca qué equipo no llegó al mínimo de jugadores o si falta el acta.
    """
    det: Dict[str, Dict[str, Dict[str, list]]] = {}

    def _slot(edad: str, fase: str, zona: str) -> list:
        return det.setdefault(edad, {}).setdefault(fase, {}).setdefault(zona, [])

    for pg in generales:
        _, _, tipo = puntos_partido_general(pg.pts_local, pg.pts_visit)
        local, visit = nombre_display(pg.local), nombre_display(pg.visitante)
        inc: List[str] = []
        if tipo == "walkover_local":
            inc.append(f"{visit} no se presentó")
        elif tipo == "walkover_visit":
            inc.append(f"{local} no se presentó")
        elif tipo == "ambos_ausentes":
            inc.append("Ambos equipos ausentes")
        _slot(pg.edad, pg.fase, pg.zona).append(
            {
                "id": pg.id_partido,
                "fecha": pg.fecha,
                "local": local,
                "visit": visit,
                "ml": pg.pts_local,
                "mv": pg.pts_visit,
                "tipo": tipo,
                "inc": inc,
            }
        )

    for pp in presentaciones:
        presenta_local, presenta_visit = pp.presenta_local, pp.presenta_visit
        if presenta_local is None and presenta_visit is None:
            presenta_local, presenta_visit = decidir_presentacion_partido(
                pp.pts_local, pp.pts_visit
            )
        local, visit = nombre_display(pp.local), nombre_display(pp.visitante)
        inc = []
        if presenta_local is False:
            inc.append(f"{local} no llegó al mínimo de {MIN_JUGADORES_REGLA} jugadores")
        if presenta_visit is False:
            inc.append(f"{visit} no llegó al mínimo de {MIN_JUGADORES_REGLA} jugadores")
        s_dato = presenta_local is None or presenta_visit is None
        if s_dato:
            inc.append("Acta no disponible (marcador atípico)")
        _slot(pp.edad, pp.fase, pp.zona or "").append(
            {
                "id": pp.id_partido,
                "fecha": pp.fecha,
                "local": local,
                "visit": visit,
                "ml": pp.pts_local,
                "mv": pp.pts_visit,
                "pl": presenta_local,
                "pv": presenta_visit,
                "sdato": s_dato,
                "inc": inc,
            }
        )

    # Ordena los partidos por fecha para que la paginación simule jornadas reales.
    for edad in det:
        for fase in det[edad]:
            for zona in det[edad][fase]:
                det[edad][fase][zona].sort(key=lambda m: _fecha_key(m.get("fecha")))
    return det


def construir_payload(
    generales: List[PartidoGeneral],
    presentaciones: List[PartidoPresentacion],
    *,
    fecha_actualizacion: str,
    boxscores: Optional[Dict[str, Dict[str, object]]] = None,
    pbp: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, object]:
    registrar_nombres_globales(generales, presentaciones)
    resultado = construir_standings(generales, presentaciones)
    tablas_cat = construir_tablas_categoria(generales)
    tablas_pres = construir_tablas_presentacion(presentaciones)
    # Tabla de MINI/U11: resultados reales (boxscore) + columna de presentación.
    tabla_u11 = construir_tabla_resultado_mini(presentaciones, boxscores, edad="U11")
    partidos = construir_partidos_detalle(generales, presentaciones)

    # --- Tabla general (combinada por zona) ---
    tablas_json: Dict[str, Dict[str, list]] = {}
    for fase, zonas in resultado.tablas.items():
        tablas_json[fase] = {}
        for zona in sorted(zonas):
            filas_json = []
            for pos, f in enumerate(zonas[zona], start=1):
                filas_json.append(
                    {
                        "pos": pos,
                        "equipo": f.equipo,
                        "pj_general": f.pj_general,
                        "ganados": f.ganados,
                        "perdidos": f.perdidos,
                        "walkover_favor": f.walkover_favor,
                        "walkover_contra": f.walkover_contra,
                        "pts_general": f.pts_general,
                        "pres_jugados": f.pres_jugados,
                        "presentaciones": f.presentaciones,
                        "pres_no_presento": f.pres_no_presento,
                        "pres_desconocidos": f.pres_desconocidos,
                        "pts_presentacion": f.pts_presentacion,
                        "puntos": f.puntos,
                    }
                )
            tablas_json[fase][zona] = filas_json

    # --- Tablas por categoría U13/U15/U17 ---
    cat_json: Dict[str, Dict[str, Dict[str, list]]] = {}
    for edad, fases in tablas_cat.items():
        cat_json[edad] = {}
        for fase, zonas in fases.items():
            cat_json[edad][fase] = {}
            for zona in sorted(zonas):
                cat_json[edad][fase][zona] = [
                    {
                        "pos": pos,
                        "equipo": f.equipo,
                        "pj": f.pj,
                        "ganados": f.ganados,
                        "perdidos": f.perdidos,
                        "walkover_favor": f.walkover_favor,
                        "walkover_contra": f.walkover_contra,
                        "puntos": f.puntos,
                    }
                    for pos, f in enumerate(zonas[zona], start=1)
                ]

    # --- Tablas por categoría de presentación U9/U11 ---
    pres_json: Dict[str, Dict[str, Dict[str, list]]] = {}
    for edad, fases in tablas_pres.items():
        pres_json[edad] = {}
        for fase, zonas in fases.items():
            pres_json[edad][fase] = {}
            for zona in sorted(zonas):
                pres_json[edad][fase][zona] = [
                    {
                        "pos": pos,
                        "equipo": f.equipo,
                        "pj": f.pj,
                        "presentaciones": f.presentaciones,
                        "no_presento": f.no_presento,
                        "desconocidos": f.desconocidos,
                        "puntos": f.puntos,
                    }
                    for pos, f in enumerate(zonas[zona], start=1)
                ]

    # --- Tabla de resultados MINI/U11 (ganados/perdidos por acta + presentación) ---
    # fase -> zona -> filas ordenadas por resultados.
    u11_json: Dict[str, Dict[str, list]] = {}
    for fase, zonas in tabla_u11.items():
        u11_json[fase] = {}
        for zona in sorted(zonas):
            u11_json[fase][zona] = [
                {
                    "pos": pos,
                    "equipo": f.equipo,
                    "pj": f.pj,
                    "puntos": f.puntos,
                    "ganados": f.ganados,
                    "perdidos": f.perdidos,
                    "np": f.np,
                    "presentaciones": f.presentaciones,
                    "box_ganados": f.box_ganados,
                    "box_perdidos": f.box_perdidos,
                    "box_sin_dato": f.box_sin_dato,
                }
                for pos, f in enumerate(zonas[zona], start=1)
            ]

    # --- Vistas disponibles ---
    vistas = [{"id": "GENERAL", "label": "General", "tipo": "general"}]
    for edad in ["U17", "U15", "U13"]:
        if edad in cat_json:
            vistas.append({"id": edad, "label": _categoria_label(edad), "tipo": "categoria"})
    # U11 usa la tabla de resultados (acta) con columna de presentación.
    if u11_json:
        vistas.append({"id": "U11", "label": _categoria_label("U11"), "tipo": "resultado_mini"})
    if "U9" in pres_json:
        vistas.append({"id": "U9", "label": _categoria_label("U9"), "tipo": "presentacion"})

    equipos_unicos = set()
    for fase, zonas in resultado.tablas.items():
        for zona, filas in zonas.items():
            for f in filas:
                equipos_unicos.add((fase, zona, f.clave))

    # Agregar "sin zona" por (fase, edad, equipo) con conteo (evita repetir por partido).
    sin_zona_agg: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for x in resultado.presentaciones_sin_zona:
        k = (x["fase"], x["edad"], x["clave"])
        if k not in sin_zona_agg:
            sin_zona_agg[k] = {
                "fase": x["fase"],
                "edad": x["edad"],
                "equipo": x["equipo"],
                "partidos": 0,
            }
        sin_zona_agg[k]["partidos"] = int(sin_zona_agg[k]["partidos"]) + 1
    sin_zona_list = sorted(
        sin_zona_agg.values(), key=lambda d: (d["fase"], d["edad"], str(d["equipo"]))
    )

    resumen = {
        "partidos_general": len(generales),
        "partidos_presentacion": len(presentaciones),
        "filas_tabla": len(equipos_unicos),
        "equipos_sin_zona": len(sin_zona_list),
    }

    # Niveles (claves canónicas) presentes en alguna vista de tablas.
    niveles_presentes = set(tablas_json.keys())
    for cat in cat_json.values():
        niveles_presentes.update(cat.keys())
    for cat in pres_json.values():
        niveles_presentes.update(cat.keys())
    niveles_presentes.update(u11_json.keys())

    fases = [f for f in FASE_ORDER if f in niveles_presentes]

    niveles_por_etapa: Dict[str, List[str]] = {}
    for etapa, orden in NIVELES_POR_ETAPA.items():
        presentes = [n for n in orden if n in niveles_presentes]
        if presentes:
            niveles_por_etapa[etapa] = presentes

    etapas = [e for e in ("PRIMERA", "SEGUNDA") if e in niveles_por_etapa]

    return {
        "fecha": fecha_actualizacion,
        "etapas": etapas,
        "etapa_labels": ETAPA_LABEL,
        "niveles_por_etapa": niveles_por_etapa,
        "etapa_por_fase": ETAPA_POR_FASE,
        "fases": fases,
        "fase_labels": FASE_LABEL,
        "vistas": vistas,
        "tablas": tablas_json,
        "tablas_categoria": cat_json,
        "tablas_presentacion": pres_json,
        "tablas_resultado_mini": {"U11": u11_json},
        "partidos": partidos,
        "boxscores": boxscores or {},
        "pbp": pbp or {},
        "min_regla": MIN_JUGADORES_REGLA,
        "sin_zona": sin_zona_list,
        "resumen": resumen,
    }


# --------------------------------------------------------------------------- #
# Render HTML
# --------------------------------------------------------------------------- #
def _render_html(payload: Dict[str, object]) -> str:
    data_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FORMATIVAS 2026 · Tabla de posiciones general</title>
  <style>
    :root {{
      --bg:#f1f5f9; --paper:#fff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0;
      --accent:#1d4ed8; --accent-soft:#eff6ff; --ok:#059669; --warn:#d97706; --bad:#dc2626;
      --gold:#fef9c3;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg);
      color:var(--text); line-height:1.45; }}
    .layout {{ max-width:1080px; margin:0 auto; padding:20px; }}
    header, section {{ background:var(--paper); border:1px solid var(--line);
      border-radius:14px; padding:20px 22px; margin-bottom:16px; }}
    h1 {{ margin:0 0 4px; font-size:24px; }}
    h2 {{ margin:0 0 12px; font-size:17px; }}
    .subtitle {{ color:var(--muted); font-size:13px; margin:0; }}
    .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:16px; }}
    .stat {{ border:1px solid var(--line); border-radius:10px; padding:12px; background:#fafbfc; }}
    .stat .n {{ font-size:22px; font-weight:700; color:var(--accent); }}
    .stat .l {{ font-size:11px; color:var(--muted); margin-top:2px; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:14px; align-items:center; }}
    .seg {{ display:inline-flex; border:1px solid var(--line); border-radius:999px; overflow:hidden; }}
    .seg button {{ border:none; background:#fff; padding:8px 16px; font-size:13px; cursor:pointer; color:var(--muted); }}
    .seg button.active {{ background:var(--accent); color:#fff; font-weight:600; }}
    select {{ border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:13px; background:#fff; }}
    label.fld {{ font-size:12px; color:var(--muted); display:flex; gap:6px; align-items:center; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:9px 8px; text-align:center; }}
    th {{ color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.04em; }}
    td.eq, th.eq {{ text-align:left; }}
    td.eq {{ font-weight:600; }}
    td.pos {{ color:var(--muted); }}
    td.tot {{ font-weight:800; color:var(--accent); font-size:15px; }}
    tbody tr:nth-child(-n+2) td.pos {{ color:var(--ok); font-weight:700; }}
    .sep {{ border-left:1px solid var(--line); }}
    .note {{ background:var(--accent-soft); border:1px solid #bfdbfe; border-radius:8px;
      padding:10px 12px; font-size:12px; color:#1e3a8a; margin-top:12px; }}
    details {{ margin-top:10px; }}
    summary {{ cursor:pointer; font-size:13px; color:var(--muted); }}
    .pill {{ display:inline-block; border-radius:999px; padding:1px 7px; font-size:11px; background:#f1f5f9; color:var(--muted); }}
    .small {{ font-size:11px; color:var(--muted); }}
    tr.inc-row td {{ background:#fef2f2; }}
    tr.sdato-row td {{ background:#fffbeb; }}
    .res {{ font-weight:700; white-space:nowrap; }}
    .badge-inc {{ display:inline-block; background:#fee2e2; color:var(--bad); border-radius:6px;
      padding:1px 8px; font-size:11px; font-weight:600; }}
    .badge-sd {{ display:inline-block; background:#fef3c7; color:var(--warn); border-radius:6px;
      padding:1px 8px; font-size:11px; font-weight:600; }}
    .badge-ok {{ color:var(--ok); font-size:12px; }}
    td.det {{ text-align:left; font-size:12px; }}
    .ck {{ font-size:12px; color:var(--muted); display:flex; gap:6px; align-items:center; cursor:pointer; }}
    .btn {{ display:inline-block; border:1px solid var(--accent); color:var(--accent); background:#fff;
      border-radius:7px; padding:3px 10px; font-size:11px; font-weight:600; text-decoration:none; cursor:pointer; }}
    .btn:hover {{ background:var(--accent-soft); }}
    .btn[aria-disabled="true"] {{ border-color:var(--line); color:var(--muted); pointer-events:none; opacity:.5; }}
    .jnav {{ display:inline-flex; gap:8px; align-items:center; }}
    .jnav .lbl {{ font-size:13px; font-weight:600; min-width:120px; text-align:center; }}
    .modal-backdrop {{ position:fixed; inset:0; background:rgba(15,23,42,.45); display:none;
      align-items:center; justify-content:center; padding:20px; z-index:1000; }}
    .modal-backdrop.open {{ display:flex; }}
    .modal {{ background:var(--paper); border-radius:12px; border:1px solid var(--line);
      width:min(760px,100%); max-height:90vh; overflow:auto; padding:20px 22px; position:relative; }}
    .modal h3 {{ margin:16px 0 6px; font-size:14px; }}
    .modal-close {{ position:absolute; top:10px; right:14px; border:none; background:transparent;
      font-size:24px; line-height:1; cursor:pointer; color:var(--muted); }}
    .modal-close:hover {{ color:var(--text); }}
    .scoreline {{ display:flex; gap:12px; margin:8px 0 4px; }}
    .scorebox {{ flex:1; border:1px solid var(--line); border-radius:8px; padding:10px; text-align:center; }}
    .scorebox .pts {{ font-size:22px; font-weight:700; }}
    .scorebox .cap {{ font-size:11px; color:var(--muted); }}
    .box-table {{ width:100%; border-collapse:collapse; font-size:12px; margin-top:4px; }}
    .box-table th, .box-table td {{ border-bottom:1px solid var(--line); padding:5px 6px; text-align:left; }}
    .box-table td.min-ok {{ color:var(--ok); font-weight:700; }}
    .box-table td.min-no {{ color:var(--muted); }}
    .note-bad {{ background:#fef2f2; border-color:#fca5a5; color:#7f1d1d; }}
    @media (max-width:760px) {{
      .stats {{ grid-template-columns:repeat(2,1fr); }}
      .hide-sm {{ display:none; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <header>
      <h1>FORMATIVAS 2026 · Tabla de posiciones general</h1>
      <p class="subtitle">FeBAMBA · Competencia GES 2015 · Masculino · Actualizado: <span id="fecha"></span></p>
      <div class="stats" id="stats"></div>
    </header>

    <section>
      <div class="toolbar">
        <label class="fld">Vista
          <select id="sel-vista"></select>
        </label>
        <div class="seg" id="seg-etapa"></div>
        <div class="seg" id="seg-fase"></div>
        <label class="fld">Zona
          <select id="sel-zona"></select>
        </label>
      </div>
      <h2 id="titulo-tabla"></h2>
      <div style="overflow:auto;">
        <table>
          <thead id="thead"></thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
      <p class="note" id="nota-vista"></p>

      <div id="partidos-wrap" style="margin-top:20px;">
        <div class="toolbar" style="margin-bottom:8px;">
          <h2 id="partidos-titulo" style="margin:0;">Partidos</h2>
          <label class="ck" style="margin-left:auto;">
            <input type="checkbox" id="chk-inc"/> Solo con incumplimiento
          </label>
        </div>
        <div class="toolbar" id="jornada-nav" style="margin-bottom:8px;">
          <div class="jnav">
            <button class="btn" id="j-prev">◀</button>
            <span class="lbl" id="j-lbl">Jornada</span>
            <button class="btn" id="j-next">▶</button>
          </div>
          <span class="small" id="j-info"></span>
        </div>
        <div style="overflow:auto;">
          <table>
            <thead id="partidos-head"></thead>
            <tbody id="partidos-body"></tbody>
          </table>
        </div>
        <p class="small" id="partidos-vacio" style="display:none;">Sin partidos para esta zona.</p>
      </div>

      <details id="det-sinzona">
        <summary>Puntos de presentación no atribuidos a una zona</summary>
        <div id="sinzona-body" class="small" style="margin-top:8px;"></div>
      </details>
    </section>
  </div>

  <div class="modal-backdrop" id="modal-backdrop" aria-hidden="true">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <button type="button" class="modal-close" id="modal-close" aria-label="Cerrar">×</button>
      <div id="modal-body"></div>
    </div>
  </div>

  <script>
    const DATA = {data_json};
    const PBP = DATA.pbp || {{}};
    const MIN_REG = {MIN_JUGADORES_REGLA};
    const MIN_SEG_GENERAL = {MIN_SEGUNDOS_REGLA};
    const MIN_SEG_PREMINI = {MIN_SEGUNDOS_PREMINI};
    function minSegFor(viewId) {{ return viewId === "U9" ? MIN_SEG_PREMINI : MIN_SEG_GENERAL; }}
    function minLabel(viewId) {{ return viewId === "U9" ? "8:00" : "10:00"; }}
    let vistaActual = "GENERAL";
    let etapaActual = "";
    let faseActual = "";
    let zonaActual = "";
    let jornadaActual = 1;
    let matchesZona = [];

    document.getElementById("fecha").textContent = DATA.fecha;

    function vistaInfo(id) {{ return (DATA.vistas || []).find(v => v.id === id) || DATA.vistas[0]; }}

    // U11 (MINI) se muestra como tabla de resultados (acta) con columna de presentación.
    function esPres(tipo) {{ return tipo === "presentacion" || tipo === "resultado_mini"; }}

    function tablasDeVista() {{
      const v = vistaInfo(vistaActual);
      if (v.tipo === "general") return DATA.tablas || {{}};
      if (v.tipo === "categoria") return (DATA.tablas_categoria || {{}})[v.id] || {{}};
      if (v.tipo === "resultado_mini") return (DATA.tablas_resultado_mini || {{}})[v.id] || {{}};
      return (DATA.tablas_presentacion || {{}})[v.id] || {{}};
    }}

    function nivelesDeEtapa(etapa) {{
      const mapa = DATA.niveles_por_etapa || {{}};
      const orden = mapa[etapa] || [];
      const tablas = tablasDeVista();
      return orden.filter(n => tablas[n]);
    }}

    function etapaDeNivel(nivel) {{
      return (DATA.etapa_por_fase || {{}})[nivel] || "";
    }}

    function labelEtapaNivel() {{
      const et = (DATA.etapa_labels || {{}})[etapaActual] || etapaActual;
      const nv = (DATA.fase_labels || {{}})[faseActual] || faseActual;
      return `${{et}} · ${{nv}}`;
    }}

    function initNav() {{
      const etapas = DATA.etapas || [];
      // Preferir Segunda fase si tiene datos; si no, primera disponible.
      if (etapas.includes("SEGUNDA") && nivelesDeEtapa("SEGUNDA").length) {{
        etapaActual = "SEGUNDA";
      }} else {{
        etapaActual = etapas[0] || "";
      }}
      const niveles = nivelesDeEtapa(etapaActual);
      faseActual = niveles[0] || (DATA.fases || [])[0] || "";
    }}

    function renderStats() {{
      const r = DATA.resumen;
      const items = [
        ["Equipos en tablas", r.filas_tabla],
        ["Partidos U13/U15/U17", r.partidos_general],
        ["Partidos U9/U11", r.partidos_presentacion],
      ];
      document.getElementById("stats").innerHTML = items.map(([l,n]) =>
        `<div class="stat"><div class="n">${{n}}</div><div class="l">${{l}}</div></div>`
      ).join("");
    }}

    function renderVistas() {{
      const sel = document.getElementById("sel-vista");
      sel.innerHTML = (DATA.vistas||[]).map(v =>
        `<option value="${{v.id}}" ${{v.id===vistaActual?'selected':''}}>${{v.label}}</option>`
      ).join("");
      sel.onchange = () => {{
        vistaActual = sel.value; zonaActual = "";
        // Si el nivel actual no existe en la nueva vista, reelegir dentro de la etapa.
        const niveles = nivelesDeEtapa(etapaActual);
        if (!niveles.includes(faseActual)) faseActual = niveles[0] || "";
        renderSegEtapa(); renderSegFase(); renderZonas(); renderTabla(); renderNota();
      }};
    }}

    function renderSegEtapa() {{
      const seg = document.getElementById("seg-etapa");
      const etapas = (DATA.etapas || []).filter(e => nivelesDeEtapa(e).length);
      seg.innerHTML = etapas.map(e =>
        `<button data-etapa="${{e}}" class="${{e===etapaActual?'active':''}}">${{(DATA.etapa_labels||{{}})[e]||e}}</button>`
      ).join("");
      seg.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {{
        etapaActual = b.dataset.etapa;
        const niveles = nivelesDeEtapa(etapaActual);
        faseActual = niveles[0] || "";
        zonaActual = "";
        renderSegEtapa(); renderSegFase(); renderZonas(); renderTabla();
      }}));
    }}

    function renderSegFase() {{
      const seg = document.getElementById("seg-fase");
      const niveles = nivelesDeEtapa(etapaActual);
      if (!niveles.includes(faseActual)) faseActual = niveles[0] || "";
      seg.innerHTML = niveles.map(f =>
        `<button data-fase="${{f}}" class="${{f===faseActual?'active':''}}">${{DATA.fase_labels[f]||f}}</button>`
      ).join("");
      seg.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {{
        faseActual = b.dataset.fase;
        etapaActual = etapaDeNivel(faseActual) || etapaActual;
        zonaActual = "";
        renderSegEtapa(); renderSegFase(); renderZonas(); renderTabla();
      }}));
    }}

    function renderZonas() {{
      const zonas = Object.keys((tablasDeVista())[faseActual] || {{}}).sort();
      if (!zonaActual || !zonas.includes(zonaActual)) zonaActual = zonas[0] || "";
      const sel = document.getElementById("sel-zona");
      sel.innerHTML = zonas.map(z => `<option value="${{z}}" ${{z===zonaActual?'selected':''}}>${{z}}</option>`).join("");
      sel.onchange = () => {{ zonaActual = sel.value; renderTabla(); }};
    }}

    function headFor(tipo, viewId) {{
      if (tipo === "general") return `<tr>
        <th class="pos">#</th><th class="eq">Equipo</th>
        <th>PJ</th><th>G</th><th>P</th>
        <th class="sep">Pts Gen</th>
        <th class="sep hide-sm">Pres.</th><th class="hide-sm">Pts Pres</th>
        <th class="sep">Total</th></tr>`;
      if (tipo === "categoria") return `<tr>
        <th class="pos">#</th><th class="eq">Equipo</th>
        <th>PJ</th><th>G</th><th>P</th>
        <th class="hide-sm" title="Ganados por no presentación rival">W.O.+</th>
        <th class="hide-sm" title="Perdidos por no presentarse">W.O.−</th>
        <th class="sep">Pts</th></tr>`;
      if (tipo === "resultado_mini") return `<tr>
        <th class="pos">#</th><th class="eq">Equipo</th>
        <th>PJ</th>
        <th class="sep" title="Puntos: 2 ganado · 1 perdido o regla Q3 · 0 NP">Pts</th>
        <th title="Ganados (2 pts)">G</th>
        <th title="Perdidos / regla de cambios Q3 (1 pt)">P</th>
        <th title="No presentó (0 pts)">NP</th>
        <th class="hide-sm" title="Presentaciones: plantilla completa (≥${{MIN_REG}} jug. ≥10:00)">Pres.</th>
        <th class="sep hide-sm" title="Resultado informativo según el acta (ganados-perdidos)">Box</th></tr>`;
      return `<tr>
        <th class="pos">#</th><th class="eq">Equipo</th>
        <th>PJ</th>
        <th title="Partidos en que se presentó (≥${{MIN_REG}} jug. con ≥${{minLabel(viewId)}})">Presentó</th>
        <th class="hide-sm">No present.</th><th class="hide-sm">S/dato</th>
        <th class="sep">Pts</th></tr>`;
    }}

    function rowFor(tipo, f) {{
      if (tipo === "general") return `<tr>
        <td class="pos">${{f.pos}}</td><td class="eq">${{f.equipo}}</td>
        <td>${{f.pj_general}}</td><td>${{f.ganados}}</td><td>${{f.perdidos}}</td>
        <td class="sep">${{f.pts_general}}</td>
        <td class="sep hide-sm">${{f.pres_jugados}}</td><td class="hide-sm">${{f.pts_presentacion}}</td>
        <td class="sep tot">${{f.puntos}}</td></tr>`;
      if (tipo === "categoria") return `<tr>
        <td class="pos">${{f.pos}}</td><td class="eq">${{f.equipo}}</td>
        <td>${{f.pj}}</td><td>${{f.ganados}}</td><td>${{f.perdidos}}</td>
        <td class="hide-sm">${{f.walkover_favor}}</td><td class="hide-sm">${{f.walkover_contra}}</td>
        <td class="sep tot">${{f.puntos}}</td></tr>`;
      if (tipo === "resultado_mini") return `<tr>
        <td class="pos">${{f.pos}}</td><td class="eq">${{f.equipo}}</td>
        <td>${{f.pj}}</td>
        <td class="sep tot">${{f.puntos}}</td>
        <td>${{f.ganados}}</td><td>${{f.perdidos}}</td><td>${{f.np}}</td>
        <td class="hide-sm">${{f.presentaciones}}</td>
        <td class="sep hide-sm">${{f.box_ganados}}-${{f.box_perdidos}}</td></tr>`;
      return `<tr>
        <td class="pos">${{f.pos}}</td><td class="eq">${{f.equipo}}</td>
        <td>${{f.pj}}</td><td>${{f.presentaciones}}</td>
        <td class="hide-sm">${{f.no_presento}}</td><td class="hide-sm">${{f.desconocidos}}</td>
        <td class="sep tot">${{f.puntos}}</td></tr>`;
    }}

    function renderTabla() {{
      const v = vistaInfo(vistaActual);
      const filas = ((tablasDeVista())[faseActual]||{{}})[zonaActual] || [];
      document.getElementById("titulo-tabla").textContent =
        `${{v.label}} · ${{labelEtapaNivel()}} — Zona ${{zonaActual}}`;
      document.getElementById("thead").innerHTML = headFor(v.tipo, v.id);
      document.getElementById("tbody").innerHTML = filas.map(f => rowFor(v.tipo, f)).join("");
      jornadaActual = 1;
      renderPartidos();
    }}

    function esc(s) {{ return (s==null?"":String(s)).replace(/[&<>]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c])); }}
    function score(m) {{ return `${{m.ml==null?"–":m.ml}} - ${{m.mv==null?"–":m.mv}}`; }}
    function boxBtn(m) {{
      if (!m.id) return '<span class="small">—</span>';
      return `<button type="button" class="btn" data-id="${{m.id}}">Ver detalle</button>`;
    }}

    function partidoRow(tipo, m) {{
      const cls = m.inc && m.inc.length ? (m.sdato ? "sdato-row" : "inc-row") : "";
      let det;
      if (m.inc && m.inc.length) {{
        const badge = m.sdato ? "badge-sd" : "badge-inc";
        det = m.inc.map(t => `<span class="${{badge}}">${{esc(t)}}</span>`).join(" ");
      }} else {{
        det = `<span class="badge-ok">✓ Sin incumplimientos</span>`;
      }}
      let pres = "";
      if (tipo === "presentacion") {{
        const tag = (ok) => ok===true ? '<span class="badge-ok">✓</span>'
          : ok===false ? '<span class="badge-inc">✗</span>' : '<span class="badge-sd">?</span>';
        pres = `<td class="hide-sm">${{tag(m.pl)}}</td><td class="hide-sm">${{tag(m.pv)}}</td>`;
      }}
      return `<tr class="${{cls}}">
        <td class="small">${{esc(m.fecha||"")}}</td>
        <td class="eq">${{esc(m.local)}}</td>
        <td class="res">${{score(m)}}</td>
        <td class="eq">${{esc(m.visit)}}</td>
        ${{pres}}
        <td class="det">${{det}}</td>
        <td>${{boxBtn(m)}}</td></tr>`;
    }}

    function partidosHead(tipo) {{
      const pres = tipo === "presentacion"
        ? '<th class="hide-sm" title="¿Local cumplió plantilla?">L</th><th class="hide-sm" title="¿Visitante cumplió plantilla?">V</th>'
        : "";
      return `<tr><th>Fecha</th><th class="eq">Local</th><th>Resultado</th><th class="eq">Visitante</th>${{pres}}<th class="det">Detalle</th><th>Acta</th></tr>`;
    }}

    function renderPartidos() {{
      const v = vistaInfo(vistaActual);
      const wrap = document.getElementById("partidos-wrap");
      if (v.tipo === "general") {{ wrap.style.display = "none"; return; }}
      wrap.style.display = "";
      const todos = (((DATA.partidos||{{}})[v.id]||{{}})[faseActual]||{{}})[zonaActual] || [];
      const totalInc = todos.filter(m => m.inc && m.inc.length).length;
      const soloInc = document.getElementById("chk-inc").checked;
      const nfilas = (((tablasDeVista())[faseActual]||{{}})[zonaActual] || []).length;
      const porJornada = Math.max(1, Math.floor(nfilas / 2));

      const head = document.getElementById("partidos-head");
      const body = document.getElementById("partidos-body");
      const vacio = document.getElementById("partidos-vacio");
      const navWrap = document.getElementById("jornada-nav");

      document.getElementById("partidos-titulo").textContent =
        `Partidos — Zona ${{zonaActual}} (${{todos.length}}, con incumplimiento: ${{totalInc}})`;

      let lista, infoTxt;
      if (soloInc) {{
        navWrap.style.display = "none";
        lista = todos.filter(m => m.inc && m.inc.length);
        infoTxt = `${{lista.length}} partido(s) con incumplimiento`;
      }} else {{
        navWrap.style.display = "";
        const nJornadas = Math.max(1, Math.ceil(todos.length / porJornada));
        if (jornadaActual > nJornadas) jornadaActual = nJornadas;
        if (jornadaActual < 1) jornadaActual = 1;
        const ini = (jornadaActual - 1) * porJornada;
        lista = todos.slice(ini, ini + porJornada);
        document.getElementById("j-lbl").textContent = `Jornada ${{jornadaActual}} / ${{nJornadas}}`;
        document.getElementById("j-prev").setAttribute("aria-disabled", jornadaActual<=1);
        document.getElementById("j-next").setAttribute("aria-disabled", jornadaActual>=nJornadas);
        document.getElementById("j-info").textContent =
          `${{porJornada}} partidos por jornada (${{nfilas}} equipos)`;
        infoTxt = "";
      }}

      if (!lista.length) {{
        head.innerHTML = ""; body.innerHTML = "";
        vacio.style.display = ""; vacio.textContent = soloInc ? "Sin incumplimientos en esta zona." : "Sin partidos para esta zona.";
        return;
      }}
      vacio.style.display = "none";
      const tipoP = esPres(v.tipo) ? "presentacion" : v.tipo;
      head.innerHTML = partidosHead(tipoP);
      body.innerHTML = lista.map(m => partidoRow(tipoP, m)).join("");
      matchesZona = todos;
      body.querySelectorAll(".btn[data-id]").forEach(b =>
        b.addEventListener("click", () => abrirModal(b.dataset.id)));
    }}

    function boxTeam(eq, tipo, viewId) {{
      const minSeg = minSegFor(viewId);
      const rows = (eq.jugadores || []).map(j => {{
        const cumple = (j.seg||0) >= minSeg;
        return `<tr><td>${{j.nro}}</td><td>${{esc(j.nombre)}}</td>
          <td class="${{cumple ? "min-ok" : "min-no"}}">${{j.min}}</td>
          <td>${{j.pts}}</td></tr>`;
      }}).join("");
      let badge = "";
      if (tipo === "presentacion") {{
        const jugReg = (eq.jugadores || []).filter(j => (j.seg||0) >= minSeg).length;
        const ok = jugReg >= MIN_REG;
        badge = ` <span class="${{ok ? "badge-ok" : "badge-inc"}}">${{jugReg}}/${{MIN_REG}} con ≥${{minLabel(viewId)}}</span>`;
      }}
      return `<h3>${{esc(eq.nombre)}}${{badge}}</h3>
        <table class="box-table"><thead><tr><th>#</th><th>Jugador</th><th>Min</th><th>Pts</th></tr></thead>
        <tbody>${{rows}}</tbody></table>`;
    }}

    function nombreLado(m, lado) {{
      return lado === "local" ? m.local : (lado === "visitante" ? m.visit : "?");
    }}

    // Detalle de play-by-play (solo U11): cambios durante el 3er cuarto y
    // jugadores que jugaron cuartos consecutivos. Replica el informe Mini.
    function pbpHtml(pbp, m) {{
      if (!pbp || !pbp.tiene_pbp) {{
        return `<h3 style="margin-top:18px;">Play-by-play</h3>
          <p class="small">Sin relato en vivo disponible para este partido.</p>`;
      }}
      let subsHtml;
      if (!pbp.hubo_subs_q3) {{
        subsHtml = '<p class="small">Sin sustituciones durante el 3er cuarto (solo formación de arranque).</p>';
      }} else {{
        const items = (pbp.subs_q3 || []).map(s => {{
          const eq = nombreLado(m, s.equipo);
          const cls = s.accion === "ENTRA" ? "badge-ok" : "badge-inc";
          return `<li><span class="${{cls}}">${{esc(s.accion)}}</span> #${{esc(s.dorsal||"")}} ${{esc(s.nombre||"")}} <span class="small">(${{esc(eq)}} · ${{esc(s.clock||"")}})</span></li>`;
        }}).join("");
        subsHtml = `<ul style="margin:6px 0 0; padding-left:18px;">${{items}}</ul>`;
      }}
      let consecHtml;
      if (!pbp.hubo_consecutivos) {{
        consecHtml = '<p class="small">Ningún jugador estuvo en cancha en cuartos consecutivos.</p>';
      }} else {{
        const items = (pbp.jugadores_consecutivos || []).map(c => {{
          const eq = nombreLado(m, c.equipo);
          const pares = (c.pares || []).map(par => par.join("-")).join(", ");
          const cuartos = (c.cuartos || []).join(", ");
          return `<li>#${{esc(c.dorsal||"")}} ${{esc(c.nombre||"")}} <span class="small">(${{esc(eq)}})</span> — cuartos jugados: ${{esc(cuartos)}} · consecutivos: <strong>${{esc(pares)}}</strong></li>`;
        }}).join("");
        consecHtml = `<ul style="margin:6px 0 0; padding-left:18px;">${{items}}</ul>`;
      }}
      return `
        <h3 style="margin-top:18px;">Cambios durante el 3er cuarto <span class="${{pbp.hubo_subs_q3 ? "badge-sd" : "badge-ok"}}">${{pbp.subs_q3_entra||0}} ingreso(s) · ${{pbp.subs_q3_sale||0}} salida(s)</span></h3>
        ${{subsHtml}}
        <h3 style="margin-top:16px;">Jugadores en cuartos consecutivos <span class="${{pbp.hubo_consecutivos ? "badge-inc" : "badge-ok"}}">${{pbp.n_consecutivos||0}}</span></h3>
        ${{consecHtml}}`;
    }}

    function abrirModal(id) {{
      const m = matchesZona.find(x => x.id === id);
      if (!m) return;
      const v = vistaInfo(vistaActual);
      const box = (DATA.boxscores || {{}})[id];
      const body = document.getElementById("modal-body");

      let nota;
      if (m.inc && m.inc.length) {{
        const cls = m.sdato ? "" : "note-bad";
        nota = `<p class="note ${{cls}}"><strong>⚠ Incumplimiento:</strong> ${{m.inc.map(esc).join(" · ")}}</p>`;
      }} else {{
        nota = `<p class="note"><span class="badge-ok">✓ Sin incumplimientos</span></p>`;
      }}

      let boxHtml;
      if (box && box.ok && box.equipos && box.equipos.length) {{
        const tot = (box.equipos[0] && box.equipos[0].pts!=null && box.equipos[1] && box.equipos[1].pts!=null)
          ? `<div class="scoreline">
               <div class="scorebox"><div class="cap">Resultado (fixture)</div><div class="pts">${{score(m)}}</div></div>
               <div class="scorebox"><div class="cap">Suma del acta</div><div class="pts">${{box.equipos[0].pts}} - ${{box.equipos[1].pts}}</div></div>
             </div>` : "";
        const tipoBox = esPres(v.tipo) ? "presentacion" : v.tipo;
        boxHtml = tot + box.equipos.map(eq => boxTeam(eq, tipoBox, v.id)).join("");
      }} else {{
        boxHtml = `<div class="scoreline"><div class="scorebox"><div class="cap">Resultado</div><div class="pts">${{score(m)}}</div></div></div>
          <p class="small">Acta no disponible para este partido.</p>`;
      }}

      // PBP (cambios Q3 / cuartos consecutivos): solo para U11.
      const pbpSection = v.id === "U11" ? pbpHtml(PBP[id], m) : "";

      body.innerHTML = `<h2 id="modal-title" style="margin:0 24px 2px 0;">${{esc(m.local)}} vs ${{esc(m.visit)}}</h2>
        <p class="small">${{v.label}} · ${{labelEtapaNivel()}} · Zona ${{zonaActual}}${{m.fecha ? " · " + esc(m.fecha) : ""}}</p>
        ${{nota}}
        ${{boxHtml}}
        ${{pbpSection}}`;
      const backdrop = document.getElementById("modal-backdrop");
      backdrop.classList.add("open");
      backdrop.setAttribute("aria-hidden", "false");
    }}

    function cerrarModal() {{
      const backdrop = document.getElementById("modal-backdrop");
      backdrop.classList.remove("open");
      backdrop.setAttribute("aria-hidden", "true");
      document.getElementById("modal-body").innerHTML = "";
    }}

    function renderNota() {{
      const v = vistaInfo(vistaActual);
      const el = document.getElementById("nota-vista");
      if (v.tipo === "resultado_mini") {{
        el.innerHTML = `<strong>MINI (U11).</strong> Puntos por el marcador oficial del fixture (penalizador): <em>ganar = 2</em>, <em>perder = 1</em>. En marcadores 20-0 / 0-20 / 0-0 el equipo penalizado suma <em>1 pt si presentó plantilla</em> (regla de cambios Q3) o <em>0 si no se presentó</em> (NP). <em>Pres.</em> = puntos de presentación (plantilla completa: ≥ ${{MIN_REG}} jugadores con ≥ 10:00) que alimentan la general. <em>Box</em> es el resultado real del acta, solo informativo. La tabla se ordena por puntos (Pts ↓, Pres. ↓, G ↓).`;
      }} else if (v.tipo === "presentacion") {{
        el.innerHTML = `<strong>Puntos de presentación.</strong> Cada equipo suma 1 punto por partido salvo que no llegue a ${{MIN_REG}} jugadores con ≥ ${{minLabel(v.id)}} de juego (validado con el acta en marcadores 0-0 / 20-0 / 0-20). <em>S/dato</em> = acta no disponible.${{v.id === "U9" ? " En PREMINI el cuarto dura 8 minutos." : ""}}`;
      }} else if (v.tipo === "categoria") {{
        el.innerHTML = `<strong>Puntos por resultado.</strong> Ganar = 2, perder = 1. Un <em>20-0</em> es no presentación: el ausente suma 0.`;
      }} else {{
        el.innerHTML = `<strong>Tabla general.</strong> Suma los puntos de U13/U15/U17 (ganar 2, perder 1; 20-0 = 0 para el ausente) más los puntos de presentación de U9/U11 (1 por equipo que llega a ${{MIN_REG}} jugadores con ≥ 10:00).`;
      }}
    }}

    function renderSinZona() {{
      const arr = DATA.sin_zona || [];
      const body = document.getElementById("sinzona-body");
      if (!arr.length) {{ body.textContent = "Sin casos."; return; }}
      const porFase = {{}};
      arr.forEach(x => {{ (porFase[x.fase] = porFase[x.fase] || []).push(x); }});
      body.innerHTML = Object.keys(porFase).map(fase => {{
        const items = porFase[fase].map(x =>
          `<span class="pill">${{x.edad}} · ${{x.equipo}} (${{x.partidos}})</span>`).join(" ");
        return `<div style="margin-bottom:6px;"><strong>${{DATA.fase_labels[fase]||fase}}</strong> (${{porFase[fase].length}}): ${{items}}</div>`;
      }}).join("");
    }}

    document.getElementById("chk-inc").addEventListener("change", renderPartidos);
    document.getElementById("j-prev").addEventListener("click", () => {{ jornadaActual--; renderPartidos(); }});
    document.getElementById("j-next").addEventListener("click", () => {{ jornadaActual++; renderPartidos(); }});
    document.getElementById("modal-close").addEventListener("click", cerrarModal);
    document.getElementById("modal-backdrop").addEventListener("click", (e) => {{ if (e.target.id === "modal-backdrop") cerrarModal(); }});
    document.addEventListener("keydown", (e) => {{ if (e.key === "Escape") cerrarModal(); }});

    renderStats();
    initNav();
    renderVistas();
    renderSegEtapa();
    renderSegFase();
    renderZonas();
    renderTabla();
    renderNota();
    renderSinZona();
  </script>
</body>
</html>"""


def publicar_docs(out_html: Path) -> Path:
    DOCS_HTML.parent.mkdir(parents=True, exist_ok=True)
    DOCS_HTML.write_text(out_html.read_text(encoding="utf-8"), encoding="utf-8")
    return DOCS_HTML


def main() -> int:
    p = argparse.ArgumentParser(description="Tabla de posiciones general FORMATIVAS 2026")
    p.add_argument("--widget-key", default="", help="Default: config/competencias.json")
    p.add_argument("--fecha-ini", default="2025-1-1")
    p.add_argument("--fecha-fin", default="2026-12-31")
    p.add_argument("--out-html", default=str(OUT_HTML))
    p.add_argument("--out-json", default=str(OUT_JSON))
    p.add_argument("--desde-json", default="", help="Saltea la descarga y usa el dataset cacheado")
    p.add_argument("--sin-actas", action="store_true", help="No descarga actas (raros quedan como desconocidos)")
    p.add_argument("--limite-actas", type=int, default=0, help="Tope de actas a descargar (debug)")
    p.add_argument("--sin-boxscores", action="store_true", help="No descarga/embebe boxscores para el modal")
    p.add_argument("--limite-boxscores", type=int, default=0, help="Tope de boxscores a descargar (debug)")
    p.add_argument("--sin-pbp", action="store_true", help="No descarga el play-by-play U11 (cambios Q3 / consecutivos)")
    p.add_argument("--limite-pbp", type=int, default=0, help="Tope de partidos PBP U11 a descargar (debug)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--publicar-docs", action="store_true", help=f"Copia a docs/ ({PUBLIC_URL})")
    p.add_argument("--progress", action="store_true")
    args = p.parse_args()

    fecha_actualizacion = date.today().strftime("%d/%m/%Y")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.desde_json:
        data = json.loads(Path(args.desde_json).read_text(encoding="utf-8"))
        generales, presentaciones = cargar_dataset(data)
    else:
        widget_key = args.widget_key or _load_widget_key()
        if not widget_key:
            print("Falta widget_key (config/competencias.json)", file=sys.stderr)
            return 1
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))

        if args.progress:
            print("Resolviendo fases por categoría…", file=sys.stderr)
        fases_por_edad = resolver_fases(ges)

        if args.progress:
            print("Descargando partidos U13/U15/U17…", file=sys.stderr)
        generales = recolectar_generales(
            ges,
            key=widget_key,
            fecha_ini=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            fases_por_edad=fases_por_edad,
            progress=args.progress,
        )

        if args.progress:
            print("Descargando partidos U9/U11…", file=sys.stderr)
        presentaciones = recolectar_presentaciones(
            ges,
            key=widget_key,
            fecha_ini=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            fases_por_edad=fases_por_edad,
            fetch_actas=not args.sin_actas,
            limite_actas=args.limite_actas,
            workers=args.workers,
            progress=args.progress,
        )

        Path(args.out_json).write_text(
            json.dumps(serializar_dataset(generales, presentaciones), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    boxscores: Dict[str, Dict[str, object]] = {}
    if not args.sin_boxscores:
        if args.progress:
            print("Descargando boxscores para el modal…", file=sys.stderr)
        tokens = [p.id_partido for p in generales] + [
            p.id_partido for p in presentaciones
        ]
        boxscores = descargar_boxscores(
            tokens,
            workers=max(args.workers, 12),
            progress=args.progress,
            limite=args.limite_boxscores,
        )
        rec = recomputar_presentaciones_desde_boxscores(presentaciones, boxscores)
        if args.progress:
            print(
                f"Presentaciones de marcadores raros recalculadas: {rec} "
                f"(U9 con umbral 8:00, resto 10:00)",
                file=sys.stderr,
            )

    pbp_u11: Dict[str, Dict[str, object]] = {}
    if not args.sin_pbp:
        if args.progress:
            print("Descargando play-by-play U11 (cambios Q3 / consecutivos)…", file=sys.stderr)
        tokens_u11 = [
            p.id_partido
            for p in presentaciones
            if p.edad == "U11" and p.id_partido
        ]
        pbp_u11 = descargar_pbp_u11(
            tokens_u11,
            workers=max(args.workers, 12),
            progress=args.progress,
            limite=args.limite_pbp,
        )
        if args.progress:
            con_pbp = sum(1 for v in pbp_u11.values() if v.get("tiene_pbp"))
            con_subs = sum(1 for v in pbp_u11.values() if v.get("hubo_subs_q3"))
            con_cons = sum(1 for v in pbp_u11.values() if v.get("hubo_consecutivos"))
            print(
                f"PBP U11: {con_pbp} con relato · {con_subs} con cambios Q3 · "
                f"{con_cons} con cuartos consecutivos",
                file=sys.stderr,
            )

    payload = construir_payload(
        generales,
        presentaciones,
        fecha_actualizacion=fecha_actualizacion,
        boxscores=boxscores,
        pbp=pbp_u11,
    )
    out_html = Path(args.out_html)
    out_html.write_text(_render_html(payload), encoding="utf-8")

    publicado = str(publicar_docs(out_html)) if args.publicar_docs else None

    print(
        json.dumps(
            {
                "resumen": payload["resumen"],
                "fases": payload["fases"],
                "html": str(out_html),
                "json": args.out_json,
                "docs_html": publicado,
                "public_url": PUBLIC_URL if args.publicar_docs else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
