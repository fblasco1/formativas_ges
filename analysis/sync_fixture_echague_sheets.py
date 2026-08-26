# -*- coding: utf-8 -*-
"""
Sincroniza el fixture de PEDRO ECHAGUE a Google Sheets (CMs).

Competencias GES incluidas:
  - 2015 Formativas (U9–U17 + U21 / Liga Próximo)
  - 2013 Superior / Mayores (Pre Liga, Reclasificación, Copas)
  - 2310 Liga Metropolitana / Pre Federal (continuación plantel A)
  - 2018 Flex formativas
  - 2019 Flex superior (plantel C)
  - 2028 Tira femenina

Planteles Superior:
  - A: PRE LIGA (2013, nombre GES ``PEDRO ECHAGUE``) + Liga Metro (2310,
    ``INSTITUCION CULTURAL y DEPORTIVA PEDRO ECHAGUE``)
  - B: ``PEDRO ECHAGUE B`` (2013 Reclasificación / Copas)
  - C: SUP Flex (2019)

Columnas CM: FECHA | HORA | TIRA | CATEGORIA | RIVAL | LOCALIA | DIRECCION | RESULTADO
(+ ID_PARTIDO para upsert; no lo editan los CM).

Además del CSV y del Sheet, escribe un JSON con contrato máquina para SICLUB
(``outputs/echague/fixture_echague.json``): envelope version/source/generated_at
+ lista ``partidos`` con ``external_id`` = ID_PARTIDO.

Ejemplos:
  python analysis/sync_fixture_echague_sheets.py --solo-csv --progress
  python analysis/sync_fixture_echague_sheets.py --progress
  python analysis/sync_fixture_echague_sheets.py --desde-json outputs/formativas_2026/datos.json --solo-csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.febamba.standings_2026 import (
    clave_equipo,
    normalizar_nombre,
    norm_zona,
)
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider


def _load_widget_key() -> str:
    with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


CLUB_NEEDLE = "PEDRO ECHAGUE"
SEDE_PROPIA = "Portela 836, CABA (CP 1406)"

# (id_competencia, label_categoria_CM, id_categoria_GES)
# label es lo que ven los CM en la columna CATEGORIA.
FUENTES: Tuple[Tuple[int, str, int], ...] = (
    # Formativas 2026 (masculino)
    (2015, "U21", 5075),  # LIGA PROXIMO MASCULINO
    (2015, "U17", 5076),
    (2015, "U15", 5077),
    (2015, "U13", 5078),
    (2015, "U11", 5079),
    (2015, "U9", 5080),
    # Superior / Mayores (planteles A y B)
    (2013, "SUP", 5074),
    # Liga Metropolitana / Pre Federal — 2ª mitad plantel A
    (2310, "Liga Metro", 6290),  # PRE FEDERAL MASCULINO
    # Flex formativas
    (2018, "U17 Flex", 5558),  # JUVENILES FLEX
    (2018, "U15 Flex", 5557),  # CADETES MIXTO
    (2018, "U13 Flex", 5091),  # INFANTILES MIXTO
    (2018, "U11 Flex", 5090),  # MINI MIXTO
    (2018, "U9 Flex", 5089),  # PRE MINI MIXTO
    # Flex superior — plantel C
    (2019, "SUP Flex", 5088),
    # Femenina
    (2028, "U21 Fem", 5111),  # LIGA PROXIMO FEMENINO
    (2028, "U17 Fem", 5110),
    (2028, "U15 Fem", 5108),
    (2028, "U13 Fem", 5107),
    (2028, "U11 Fem", 5106),
    (2028, "U9 Fem", 5105),  # PRE MINI MIXTO en femeninas
)

COMPETENCIA_LABEL: Dict[int, str] = {
    2015: "Formativas",
    2013: "Superior",
    2310: "Liga Metropolitana",
    2018: "Flex formativas",
    2019: "Flex superior",
    2028: "Femenina",
}

HEADERS = [
    "FECHA",
    "HORA",
    "TIRA",
    "CATEGORIA",
    "RIVAL",
    "LOCALIA",
    "DIRECCION",
    "RESULTADO",
    "ID_PARTIDO",
]

OUT_DIR = ROOT / "outputs" / "echague"
OUT_CSV = OUT_DIR / "fixture_echague.csv"
OUT_JSON = OUT_DIR / "fixture_echague.json"

# Contrato máquina para SICLUB (club_management / Reserva Espacio).
JSON_VERSION = 1
JSON_SOURCE = "febamba_ges"
JSON_CLUB = "PEDRO ECHAGUE"
TZ_ART = timezone(timedelta(hours=-3))
_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FECHA_DMY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
SCOPES_CACHE = OUT_DIR / "scopes_cache.json"
CONFIG_SHEETS = ROOT / "config" / "echague_sheets.json"
SERVICE_ACCOUNT = ROOT / "config" / "google_service_account.json"
MAPEO_CSV = ROOT / "outputs" / "viajes_elite42" / "mapeo_clubes.csv"
GEOJSON = ROOT / "outputs" / "viajes_elite42" / "clubes_geocodificados.json"
AFILIADAS_XLSX = ROOT / "data" / "referencia" / "AFILIADAS y DIRECCIONES.xlsx"

DEFAULT_SPREADSHEET_ID = "1FFMSZhnfrYVvpjiXLBtgNseVLxiuG8NfH00uCXUXl9k"
DEFAULT_WORKSHEET = "Fixture"

# En filas ya existentes, no pisar estas columnas si el Sheet ya tiene valor (edición CM).
HEADERS_PRESERVAR_SI_LLENO = frozenset({"DIRECCION"})

_TOKENS_DESCARTAR_TIRA = {
    "INFANTILES",
    "INFANTIL",
    "CADETES",
    "CADETE",
    "JUVENILES",
    "JUVENIL",
    "MINI",
    "PREMINI",
    "PRE",
    "MOSQUITOS",
    "MOSQUITO",
    "PROXIMO",
    "LIGA",
    "MAYORES",
    "SUPERIOR",
    "MASCULINO",
    "FEMENINO",
    "FEMENINA",
    "MIXTO",
    "FORMATIVAS",
}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _strip_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _norm(texto: str) -> str:
    return " ".join(_strip_acentos(texto).upper().split())


def es_equipo_echague(nombre: str) -> bool:
    n = _norm(nombre)
    if CLUB_NEEDLE in n:
        return True
    # Nombre institucional en Liga Metropolitana (comp. 2310).
    return "INSTITUCION CULTURAL" in n and "PEDRO ECHAGUE" in n


def tira_desde_nombre(nombre: str, categoria: str = "") -> str:
    """
    Resuelve la tira/plantel para la columna TIRA del Sheet.

    Superior:
      - A: ``PEDRO ECHAGUE`` (Pre Liga) / nombre institucional (Liga Metro)
      - B: ``PEDRO ECHAGUE B``
      - C: SUP Flex
    Formativas: AZUL / AMARILLO / FLEX / etc. según sufijo GES.
    """
    n = _norm(nombre)
    cat = _norm(categoria)

    if cat == "SUP FLEX":
        return "C"
    if cat == "LIGA METRO":
        return "A"

    if "INSTITUCION CULTURAL" in n and CLUB_NEEDLE in n:
        if n.endswith(" B") or n.endswith("PEDRO ECHAGUE B"):
            return "B"
        return "A"

    resto = n.replace(CLUB_NEEDLE, "", 1).strip()
    tokens = [t for t in resto.split() if t not in _TOKENS_DESCARTAR_TIRA]
    if not tokens:
        # ``PEDRO ECHAGUE`` sin sufijo en Superior = plantel A
        if cat == "SUP":
            return "A"
        return "—"
    if tokens == ["B"]:
        return "B"
    if tokens == ["C"]:
        return "C"
    return " ".join(tokens)


def _es_fase_excluida(nombre_fase: str) -> bool:
    """Nacionales LFF y similares fuera del fixture CM del club."""
    u = (nombre_fase or "").strip().upper()
    return "LFF" in u


def listar_fases_categoria(
    ges: GesDeportivaExtractor,
    id_competencia: int,
    id_categoria: int,
) -> Dict[str, str]:
    """nombre_fase_GES -> id_fase (excluye LFF)."""
    fases, _ = ges.get_ids_fases_grupos(
        id_competencia, id_categoria=id_categoria
    )
    return {
        nombre: fid
        for nombre, fid in fases.items()
        if not _es_fase_excluida(nombre)
    }


def split_fecha_hora(fecha_raw: str) -> Tuple[str, str]:
    """'15/03/2026 12:30' -> ('15/03/2026', '12:30')."""
    t = (fecha_raw or "").strip()
    if not t:
        return "", ""
    partes = t.split()
    fecha = partes[0]
    hora = ""
    if len(partes) > 1 and ":" in partes[1]:
        hora = partes[1][:5]
    return fecha, hora


def _fecha_sort_key(fecha: str, hora: str) -> Tuple[int, int, int, int, int]:
    try:
        d, m, y = (int(x) for x in fecha.split("/"))
    except Exception:
        return (9999, 12, 31, 23, 59)
    hh = mm = 0
    if hora and ":" in hora:
        try:
            hh, mm = (int(x) for x in hora.split(":")[:2])
        except Exception:
            pass
    return (y, m, d, hh, mm)


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return None


# --------------------------------------------------------------------------- #
# Direcciones
# --------------------------------------------------------------------------- #
def _cargar_direcciones_mapeo(path: Path = MAPEO_CSV) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            direccion = (row.get("direccion") or "").strip()
            if not direccion:
                continue
            cp = (row.get("cod_postal") or "").strip()
            label = f"{direccion}, CP {cp}" if cp else direccion
            for key in (row.get("clave"), row.get("equipo")):
                k = _norm(key or "")
                if k and k not in out:
                    out[k] = label
    return out


def _cargar_direcciones_geojson(path: Path = GEOJSON) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for clave, meta in data.items():
        query = (meta.get("query") or "").strip()
        if not query:
            continue
        # "Portela 836, 1406, Argentina" -> "Portela 836, 1406"
        limpio = re.sub(r",\s*Argentina\s*$", "", query, flags=re.I).strip()
        k = _norm(clave)
        if k and limpio and k not in out:
            out[k] = limpio
    return out


def _cargar_direcciones_afiliadas(path: Path = AFILIADAS_XLSX) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    try:
        import pandas as pd
    except ImportError:
        return out
    try:
        df = pd.read_excel(path)
    except Exception:
        return out
    df = df.rename(columns=str.strip)
    cols = {c.upper(): c for c in df.columns}
    col_nom = cols.get("AFILIADA")
    col_dir = cols.get("DIRECCION")
    if not col_nom or not col_dir:
        return out
    col_cp = cols.get("COD POSTAL")
    for _, row in df.iterrows():
        afiliada = str(row[col_nom]).strip()
        if not afiliada or afiliada.lower() == "nan":
            continue
        direccion = "" if pd.isna(row[col_dir]) else str(row[col_dir]).strip()
        if not direccion:
            continue
        cp = ""
        if col_cp is not None and not pd.isna(row[col_cp]):
            cp = str(row[col_cp]).strip().replace(".0", "")
        label = f"{direccion}, CP {cp}" if cp else direccion
        k = _norm(afiliada)
        if k and k not in out:
            out[k] = label
    return out


def construir_indice_direcciones() -> Dict[str, str]:
    """clave/nombre normalizado -> dirección legible."""
    idx: Dict[str, str] = {}
    for fuente in (
        _cargar_direcciones_afiliadas(),
        _cargar_direcciones_geojson(),
        _cargar_direcciones_mapeo(),
    ):
        # mapeo (más específico por tira) pisa afiliada genérica
        idx.update(fuente)
    return idx


def resolver_direccion(
    *,
    localia: str,
    rival: str,
    indice: Dict[str, str],
) -> str:
    if localia == "Local":
        return SEDE_PROPIA
    # Visitante: sede del rival
    candidatos = [
        _norm(clave_equipo(rival)),
        _norm(rival),
        _norm(normalizar_nombre(rival)),
    ]
    for c in candidatos:
        if c in indice:
            return indice[c]
    # Match parcial: si la clave del rival está contenida en alguna clave del índice
    rival_tokens = set(candidatos[0].split())
    mejor = ""
    mejor_score = 0
    for k, dir_ in indice.items():
        k_tokens = set(k.split())
        if not k_tokens:
            continue
        inter = rival_tokens & k_tokens
        # exigir al menos 2 tokens en común (evitar falsos positivos)
        if len(inter) < 2:
            continue
        score = len(inter)
        if score > mejor_score:
            mejor_score = score
            mejor = dir_
    return mejor


# --------------------------------------------------------------------------- #
# Cache de scopes (comp/cat/fase/grupo donde juega Echagüe)
# --------------------------------------------------------------------------- #
def _scope_key(
    id_comp: int, id_cat: int, id_fase: str | int, id_grupo: str | int
) -> str:
    return f"{id_comp}|{id_cat}|{id_fase}|{id_grupo}"


def cargar_scopes_cache(path: Path = SCOPES_CACHE) -> Dict[str, dict]:
    """clave scope -> metadata."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, dict] = {}
    for s in data.get("scopes") or []:
        try:
            k = _scope_key(
                int(s["id_competencia"]),
                int(s["id_categoria"]),
                s["id_fase"],
                s["id_grupo"],
            )
        except (KeyError, TypeError, ValueError):
            continue
        out[k] = s
    return out


def guardar_scopes_cache(
    partidos: List[Dict[str, object]],
    path: Path = SCOPES_CACHE,
) -> Path:
    scopes: Dict[str, dict] = {}
    for p in partidos:
        try:
            id_comp = int(p["id_competencia"])  # type: ignore[arg-type]
            id_cat = int(p["id_categoria"])  # type: ignore[arg-type]
            id_fase = str(p["id_fase"])
            id_grupo = str(p["id_grupo"])
        except (KeyError, TypeError, ValueError):
            continue
        k = _scope_key(id_comp, id_cat, id_fase, id_grupo)
        scopes[k] = {
            "id_competencia": id_comp,
            "id_categoria": id_cat,
            "cat_label": p.get("edad") or "",
            "id_fase": id_fase,
            "fase": p.get("fase") or "",
            "id_grupo": id_grupo,
            "zona": p.get("zona") or "",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "n_scopes": len(scopes),
        "scopes": sorted(
            scopes.values(),
            key=lambda s: (
                s["id_competencia"],
                s["id_categoria"],
                str(s["id_fase"]),
                str(s["id_grupo"]),
            ),
        ),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def scopes_a_consultar(
    *,
    id_comp: int,
    id_cat: int,
    fases: Dict[str, str],
    grupos_por_fase: Dict[str, Dict[str, str]],
    cache: Dict[str, dict],
    full: bool,
) -> List[Tuple[str, str, str, str]]:
    """
    Devuelve lista (nombre_fase, id_fase, nombre_grupo, id_grupo) a scrapear.

    Incremental: fases nuevas → todos sus grupos; fases ya vistas → solo grupos
    cacheados donde ya apareció Echagüe.
    """
    out: List[Tuple[str, str, str, str]] = []
    cached_fases = {
        str(s["id_fase"])
        for s in cache.values()
        if int(s["id_competencia"]) == id_comp and int(s["id_categoria"]) == id_cat
    }
    cached_grupos = {
        (str(s["id_fase"]), str(s["id_grupo"]))
        for s in cache.values()
        if int(s["id_competencia"]) == id_comp and int(s["id_categoria"]) == id_cat
    }

    for nombre_fase, id_fase in fases.items():
        fid = str(id_fase)
        grupos = grupos_por_fase.get(nombre_fase) or {}
        if full or fid not in cached_fases:
            for nombre_grupo, id_grupo in grupos.items():
                out.append((nombre_fase, fid, nombre_grupo, str(id_grupo)))
        else:
            for nombre_grupo, id_grupo in grupos.items():
                if (fid, str(id_grupo)) in cached_grupos:
                    out.append((nombre_fase, fid, nombre_grupo, str(id_grupo)))
    return out


def debe_actualizar_celda(header: str, old_val: object, new_val: object) -> bool:
    """False si no cambió, o si hay que preservar valor manual en el Sheet."""
    old_s = "" if old_val is None else str(old_val)
    new_s = "" if new_val is None else str(new_val)
    if old_s == new_s:
        return False
    if header in HEADERS_PRESERVAR_SI_LLENO and old_s.strip():
        return False
    return True


# --------------------------------------------------------------------------- #
# Recolección GES (incluye pendientes) — multi-competencia
# --------------------------------------------------------------------------- #
def recolectar_partidos_echague(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    progress: bool = False,
    fuentes: Sequence[Tuple[int, str, int]] = FUENTES,
    full: bool = False,
    scopes_cache: Optional[Dict[str, dict]] = None,
) -> List[Dict[str, object]]:
    """
    Partidos COMPLETO/PENDIENTE de Echagüe.

    Con ``full=False`` (default) solo consulta grupos del cache de scopes, más
    fases nuevas que aún no estaban cacheadas. Con ``full=True`` recorre todo.
    """
    cache = scopes_cache if scopes_cache is not None else cargar_scopes_cache()
    if not full and not cache:
        # Primera corrida sin cache: descubrimiento completo.
        full = True
        if progress:
            print(
                "Sin scopes_cache: corrida full de descubrimiento…",
                file=sys.stderr,
                flush=True,
            )

    out: List[Dict[str, object]] = []
    vistos: set = set()
    n_consultas = 0

    for id_comp, cat_label, id_cat in fuentes:
        comp_label = COMPETENCIA_LABEL.get(id_comp, str(id_comp))
        fases = listar_fases_categoria(ges, id_comp, id_cat)
        grupos_por_fase: Dict[str, Dict[str, str]] = {}
        for nombre_fase, id_fase in fases.items():
            grupos_por_fase[nombre_fase] = ges.get_grupos_de_fase(
                id_comp, id_cat, int(id_fase)
            )

        a_consultar = scopes_a_consultar(
            id_comp=id_comp,
            id_cat=id_cat,
            fases=fases,
            grupos_por_fase=grupos_por_fase,
            cache=cache,
            full=full,
        )
        if progress:
            tot_grupos = sum(len(g) for g in grupos_por_fase.values())
            print(
                f"=== {comp_label} · {cat_label} (comp {id_comp} / cat {id_cat}): "
                f"{len(fases)} fases · {len(a_consultar)}/{tot_grupos} zonas ===",
                file=sys.stderr,
                flush=True,
            )

        for nombre_fase, id_fase, nombre_grupo, id_grupo in a_consultar:
            zona = norm_zona(nombre_grupo)
            n_consultas += 1
            partidos = ges.get_info_partidos(
                id_cat,
                fecha_ini,
                fecha_fin,
                key=key,
                id_fase=int(id_fase),
                id_grupo=int(id_grupo),
            )
            for p in partidos:
                local = p.get("Local") or ""
                visit = p.get("Visitante") or ""
                if not (es_equipo_echague(local) or es_equipo_echague(visit)):
                    continue
                idp = (p.get("ID_PARTIDO") or "").strip()
                clave_dedup = (
                    idp
                    or f"{id_comp}|{cat_label}|{nombre_fase}|{zona}|{local}|{visit}|{p.get('Fecha')}"
                )
                if clave_dedup in vistos:
                    continue
                vistos.add(clave_dedup)
                out.append(
                    {
                        "edad": cat_label,
                        "competencia": comp_label,
                        "id_competencia": id_comp,
                        "id_categoria": id_cat,
                        "fase": nombre_fase,
                        "id_fase": str(id_fase),
                        "zona": zona,
                        "id_grupo": str(id_grupo),
                        "local": local,
                        "visitante": visit,
                        "pts_local": _to_int(p.get("PTS_LOCAL")),
                        "pts_visit": _to_int(p.get("PTS_VISITANTE")),
                        "id_partido": idp,
                        "fecha": p.get("Fecha") or "",
                        "estado": p.get("Estado") or "",
                    }
                )

    if progress:
        print(
            f"Consultas GES get_info_partidos: {n_consultas} · "
            f"partidos Echagüe: {len(out)}",
            file=sys.stderr,
            flush=True,
        )
    return out


def partidos_desde_json(path: Path) -> List[Dict[str, object]]:
    """Usa datos.json de standings formativas (solo COMPLETO, U9–U17)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[Dict[str, object]] = []
    vistos: set = set()
    for section in ("generales", "presentaciones"):
        for p in data.get(section) or []:
            local = p.get("local") or ""
            visit = p.get("visitante") or ""
            if not (es_equipo_echague(local) or es_equipo_echague(visit)):
                continue
            idp = (p.get("id_partido") or "").strip()
            clave = idp or f"{p.get('edad')}|{local}|{visit}|{p.get('fecha')}"
            if clave in vistos:
                continue
            vistos.add(clave)
            out.append(
                {
                    "edad": p.get("edad") or "",
                    "competencia": "Formativas",
                    "id_competencia": 2015,
                    "fase": p.get("fase") or "",
                    "zona": p.get("zona") or "",
                    "local": local,
                    "visitante": visit,
                    "pts_local": p.get("pts_local"),
                    "pts_visit": p.get("pts_visit"),
                    "id_partido": idp,
                    "fecha": p.get("fecha") or "",
                    "estado": "COMPLETO",
                }
            )
    return out

def mapear_fila(
    p: Dict[str, object],
    indice_dir: Dict[str, str],
) -> Dict[str, str]:
    local = str(p.get("local") or "")
    visit = str(p.get("visitante") or "")
    if es_equipo_echague(local):
        propio, rival, localia = local, visit, "Local"
        pts_prop, pts_riv = p.get("pts_local"), p.get("pts_visit")
    else:
        propio, rival, localia = visit, local, "Visitante"
        pts_prop, pts_riv = p.get("pts_visit"), p.get("pts_local")

    fecha, hora = split_fecha_hora(str(p.get("fecha") or ""))
    resultado = ""
    estado = str(p.get("estado") or "").strip().upper()
    if pts_prop is not None and pts_riv is not None:
        # 0-0 en GES suele ser partido aún no jugado (aunque a veces venga como COMPLETO).
        es_cero = int(pts_prop) == 0 and int(pts_riv) == 0
        if estado == "PENDIENTE" or (es_cero and estado != "COMPLETO"):
            resultado = ""
        elif estado == "COMPLETO" and not es_cero:
            resultado = f"{pts_prop}-{pts_riv}"
        elif estado == "COMPLETO" and es_cero:
            resultado = ""
        elif estado == "" and not es_cero:
            # datos.json / fuentes sin campo estado
            resultado = f"{pts_prop}-{pts_riv}"

    return {
        "FECHA": fecha,
        "HORA": hora,
        "TIRA": tira_desde_nombre(propio, str(p.get("edad") or "")),
        "CATEGORIA": str(p.get("edad") or ""),
        "RIVAL": rival,
        "LOCALIA": localia,
        "DIRECCION": resolver_direccion(
            localia=localia, rival=rival, indice=indice_dir
        ),
        "RESULTADO": resultado,
        "ID_PARTIDO": str(p.get("id_partido") or ""),
    }


def construir_filas(partidos: List[Dict[str, object]]) -> List[Dict[str, str]]:
    indice = construir_indice_direcciones()
    filas = [mapear_fila(p, indice) for p in partidos]
    filas.sort(key=lambda r: _fecha_sort_key(r["FECHA"], r["HORA"]))
    return filas


def fecha_a_iso(fecha: str) -> str:
    """DD/MM/YYYY (Sheet/CSV) → YYYY-MM-DD. Si ya es ISO o no parsea, se deja."""
    t = (fecha or "").strip()
    if not t:
        return ""
    if _FECHA_ISO_RE.match(t):
        return t
    m = _FECHA_DMY_RE.match(t)
    if not m:
        return t
    d, mo, y = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def fila_a_partido_json(fila: Dict[str, str]) -> Dict[str, object]:
    """Mapea una fila CM al ítem ``partidos[]`` del contrato SICLUB."""
    return {
        "source": JSON_SOURCE,
        "external_id": str(fila.get("ID_PARTIDO") or ""),
        "fecha": fecha_a_iso(str(fila.get("FECHA") or "")),
        "hora": str(fila.get("HORA") or ""),
        "tira": str(fila.get("TIRA") or ""),
        "categoria": str(fila.get("CATEGORIA") or ""),
        "rival": str(fila.get("RIVAL") or ""),
        "localia": str(fila.get("LOCALIA") or ""),
        "direccion": str(fila.get("DIRECCION") or ""),
        "resultado": str(fila.get("RESULTADO") or ""),
        "espacio": None,
    }


def timestamp_art(now: Optional[datetime] = None) -> str:
    """ISO-8601 con offset ART fijo (-03:00)."""
    dt = now if now is not None else datetime.now(TZ_ART)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_ART)
    else:
        dt = dt.astimezone(TZ_ART)
    return dt.isoformat(timespec="seconds")


def construir_payload_json(
    filas: List[Dict[str, str]],
    *,
    generated_at: Optional[str] = None,
) -> Dict[str, object]:
    """Envelope SICLUB. Incluye Local y Visitante; omite filas sin ID_PARTIDO."""
    partidos = [
        fila_a_partido_json(f)
        for f in filas
        if (f.get("ID_PARTIDO") or "").strip()
    ]
    return {
        "version": JSON_VERSION,
        "source": JSON_SOURCE,
        "generated_at": generated_at or timestamp_art(),
        "club": JSON_CLUB,
        "partidos": partidos,
    }


# --------------------------------------------------------------------------- #
# CSV / JSON / Sheets
# --------------------------------------------------------------------------- #
def escribir_csv(filas: List[Dict[str, str]], path: Path = OUT_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for row in filas:
            w.writerow({h: row.get(h, "") for h in HEADERS})
    return path


def escribir_json(
    filas: List[Dict[str, str]],
    path: Path = OUT_JSON,
    *,
    generated_at: Optional[str] = None,
) -> Path:
    """Publica el contrato SICLUB (UTF-8, indent 2, sin escapar unicode)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = construir_payload_json(filas, generated_at=generated_at)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _load_sheets_config(
    spreadsheet_id: str = "",
    worksheet: str = "",
) -> Tuple[str, str]:
    cfg: Dict[str, str] = {}
    if CONFIG_SHEETS.exists():
        try:
            cfg = json.loads(CONFIG_SHEETS.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    sid = spreadsheet_id or cfg.get("spreadsheet_id") or DEFAULT_SPREADSHEET_ID
    ws = worksheet or cfg.get("worksheet") or DEFAULT_WORKSHEET
    return sid, ws


def upsert_google_sheet(
    filas: List[Dict[str, str]],
    *,
    spreadsheet_id: str,
    worksheet: str,
    credentials_path: Path = SERVICE_ACCOUNT,
) -> Dict[str, int]:
    """
    Upsert por ID_PARTIDO.

    - Actualiza solo las columnas gestionadas (HEADERS) en filas existentes.
    - No toca columnas a la derecha de ID_PARTIDO (notas de CM).
    - Agrega filas nuevas al final.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise SystemExit(
            "Faltan dependencias: pip install gspread google-auth"
        ) from e

    if not credentials_path.exists():
        raise SystemExit(
            f"No está la service account en {credentials_path}.\n"
            "Creá una en Google Cloud, descargá el JSON y compartí el Sheet "
            "con el client_email (Editor)."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        str(credentials_path), scopes=scopes
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows=2000, cols=20)

    existing = ws.get_all_values()
    if not existing:
        # Hoja vacía: headers + todas las filas.
        values = [HEADERS] + [[r.get(h, "") for h in HEADERS] for r in filas]
        ws.update("A1", values, value_input_option="USER_ENTERED")
        return {"creadas": len(filas), "actualizadas": 0, "sin_cambio": 0}

    header_row = existing[0]
    # Asegurar que existan las columnas gestionadas (agregar al final si faltan).
    missing = [h for h in HEADERS if h not in header_row]
    if missing:
        new_header = header_row + missing
        ws.update("A1", [new_header], value_input_option="USER_ENTERED")
        header_row = new_header
        # Releer no hace falta: usamos header_row actualizado; filas existentes
        # no tienen valores en columnas nuevas (vacío implícito).

    col_idx = {name: i for i, name in enumerate(header_row)}
    id_col = col_idx.get("ID_PARTIDO")
    if id_col is None:
        raise SystemExit(
            "La hoja no tiene columna ID_PARTIDO y no se pudo agregar."
        )

    # Mapa id -> número de fila (1-based en Sheets; fila 1 = header)
    id_to_row: Dict[str, int] = {}
    for rnum, row in enumerate(existing[1:], start=2):
        if id_col < len(row):
            pid = (row[id_col] or "").strip()
            if pid:
                id_to_row[pid] = rnum

    actualizadas = creadas = sin_cambio = 0
    updates: List[Dict[str, object]] = []
    nuevas: List[List[str]] = []

    # Ancho actual de filas existentes (para no truncar columnas extra)
    width = max(len(header_row), max((len(r) for r in existing), default=0))

    for fila in filas:
        pid = (fila.get("ID_PARTIDO") or "").strip()
        if not pid:
            # Sin id no se puede upsert de forma estable: se omite.
            continue
        if pid in id_to_row:
            rnum = id_to_row[pid]
            old = existing[rnum - 1] if rnum - 1 < len(existing) else []
            changed = False
            for h in HEADERS:
                ci = col_idx[h]
                new_val = fila.get(h, "")
                old_val = old[ci] if ci < len(old) else ""
                if not debe_actualizar_celda(h, old_val, new_val):
                    continue
                changed = True
                col_letter = _col_letter(ci + 1)
                updates.append(
                    {
                        "range": f"{col_letter}{rnum}",
                        "values": [[new_val]],
                    }
                )
            if changed:
                actualizadas += 1
            else:
                sin_cambio += 1
        else:
            # Nueva fila: alinear a header_row (vacío en columnas extra)
            row_out = [""] * width
            for h in HEADERS:
                row_out[col_idx[h]] = fila.get(h, "")
            nuevas.append(row_out)
            creadas += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if nuevas:
        ws.append_rows(nuevas, value_input_option="USER_ENTERED")

    return {
        "creadas": creadas,
        "actualizadas": actualizadas,
        "sin_cambio": sin_cambio,
    }


def _col_letter(n: int) -> str:
    """1 -> A, 27 -> AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(
        description="Sync fixture Pedro Echagüe → Google Sheets + JSON SICLUB"
    )
    p.add_argument("--widget-key", default="", help="Default: config/competencias.json")
    p.add_argument("--fecha-ini", default="2025-1-1")
    p.add_argument("--fecha-fin", default="2026-12-31")
    p.add_argument(
        "--desde-json",
        default="",
        help="Usa outputs/.../datos.json (solo COMPLETO; sin pendientes)",
    )
    p.add_argument(
        "--solo-csv",
        action="store_true",
        help="No sube a Google; escribe CSV y JSON en outputs/echague/",
    )
    p.add_argument("--out-csv", default=str(OUT_CSV))
    p.add_argument("--out-json", default=str(OUT_JSON))
    p.add_argument("--spreadsheet-id", default="")
    p.add_argument("--worksheet", default="")
    p.add_argument(
        "--credentials",
        default=str(SERVICE_ACCOUNT),
        help="JSON de service account Google",
    )
    p.add_argument("--progress", action="store_true")
    p.add_argument(
        "--full",
        action="store_true",
        help="Recorre todas las zonas GES (descubrimiento). Default: solo scopes cacheados + fases nuevas",
    )
    p.add_argument(
        "--solo-categorias",
        default="",
        help="Filtra labels CM (coma-separadas), ej: U21,SUP,U17 Flex",
    )
    args = p.parse_args()

    fuentes = FUENTES
    if args.solo_categorias:
        wanted = {x.strip() for x in args.solo_categorias.split(",") if x.strip()}
        fuentes = tuple(f for f in FUENTES if f[1] in wanted)
        if not fuentes:
            print(f"Ninguna categoría coincide con {wanted}", file=sys.stderr)
            return 1

    if args.desde_json:
        if args.progress:
            print(f"Leyendo {args.desde_json}…", file=sys.stderr)
        partidos = partidos_desde_json(Path(args.desde_json))
    else:
        widget_key = args.widget_key or _load_widget_key()
        if not widget_key:
            print("Falta widget_key (config/competencias.json)", file=sys.stderr)
            return 1
        modo = "full" if args.full else "incremental"
        if args.progress:
            print(
                f"Descargando partidos Echagüe desde GES "
                f"({len(fuentes)} categorías, modo {modo})…",
                file=sys.stderr,
            )
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
        partidos = recolectar_partidos_echague(
            ges,
            key=widget_key,
            fecha_ini=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            progress=args.progress,
            fuentes=fuentes,
            full=args.full,
        )
        cache_path = guardar_scopes_cache(partidos)
        if args.progress:
            print(f"Scopes cache: {cache_path}", file=sys.stderr)

    filas = construir_filas(partidos)
    sin_dir = sum(1 for r in filas if r["LOCALIA"] == "Visitante" and not r["DIRECCION"])
    por_cat: Dict[str, int] = {}
    for r in filas:
        por_cat[r["CATEGORIA"]] = por_cat.get(r["CATEGORIA"], 0) + 1
    if args.progress:
        print(
            f"{len(filas)} partidos · {sin_dir} visitantes sin dirección",
            file=sys.stderr,
        )

    csv_path = escribir_csv(filas, Path(args.out_csv))
    json_path = escribir_json(filas, Path(args.out_json))
    result: Dict[str, object] = {
        "partidos": len(filas),
        "por_categoria": dict(sorted(por_cat.items())),
        "visitantes_sin_direccion": sin_dir,
        "csv": str(csv_path),
        "json": str(json_path),
        "scopes_cache": str(SCOPES_CACHE) if SCOPES_CACHE.exists() else None,
        "fecha_sync": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    if not args.solo_csv:
        sid, ws_name = _load_sheets_config(args.spreadsheet_id, args.worksheet)
        if args.progress:
            print(f"Upsert a Sheet {sid} / {ws_name}…", file=sys.stderr)
        stats = upsert_google_sheet(
            filas,
            spreadsheet_id=sid,
            worksheet=ws_name,
            credentials_path=Path(args.credentials),
        )
        result["sheets"] = {"spreadsheet_id": sid, "worksheet": ws_name, **stats}
        result["url"] = f"https://docs.google.com/spreadsheets/d/{sid}/edit"

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
