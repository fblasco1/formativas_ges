# -*- coding: utf-8 -*-
"""
Sincroniza el fixture de PEDRO ECHAGUE a Google Sheets (CMs).

Competencias GES incluidas:
  - 2015 Formativas (U9–U17 + U21 / Liga Próximo)
  - 2013 Superior / Mayores
  - 2018 Flex formativas
  - 2019 Flex superior
  - 2028 Tira femenina

Columnas CM: FECHA | HORA | TIRA | CATEGORIA | RIVAL | LOCALIA | DIRECCION | RESULTADO
(+ ID_PARTIDO para upsert; no lo editan los CM).

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
from datetime import datetime
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
    # Superior / Mayores
    (2013, "SUP", 5074),
    # Flex formativas
    (2018, "U17 Flex", 5558),  # JUVENILES FLEX
    (2018, "U15 Flex", 5557),  # CADETES MIXTO
    (2018, "U13 Flex", 5091),  # INFANTILES MIXTO
    (2018, "U11 Flex", 5090),  # MINI MIXTO
    (2018, "U9 Flex", 5089),  # PRE MINI MIXTO
    # Flex superior
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
CONFIG_SHEETS = ROOT / "config" / "echague_sheets.json"
SERVICE_ACCOUNT = ROOT / "config" / "google_service_account.json"
MAPEO_CSV = ROOT / "outputs" / "viajes_elite42" / "mapeo_clubes.csv"
GEOJSON = ROOT / "outputs" / "viajes_elite42" / "clubes_geocodificados.json"
AFILIADAS_XLSX = ROOT / "data" / "referencia" / "AFILIADAS y DIRECCIONES.xlsx"

DEFAULT_SPREADSHEET_ID = "1FFMSZhnfrYVvpjiXLBtgNseVLxiuG8NfH00uCXUXl9k"
DEFAULT_WORKSHEET = "Fixture"

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
    return CLUB_NEEDLE in _norm(nombre)


def tira_desde_nombre(nombre: str) -> str:
    """'PEDRO ECHAGUE AZUL' -> 'AZUL'; 'PEDRO ECHAGUE FLEX' -> 'FLEX'."""
    n = _norm(nombre)
    resto = n.replace(CLUB_NEEDLE, "", 1).strip()
    tokens = [t for t in resto.split() if t not in _TOKENS_DESCARTAR_TIRA]
    return " ".join(tokens) if tokens else "—"


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
) -> List[Dict[str, object]]:
    """Todos los partidos (COMPLETO y PENDIENTE) donde juega Echagüe."""
    out: List[Dict[str, object]] = []
    vistos: set = set()

    for id_comp, cat_label, id_cat in fuentes:
        comp_label = COMPETENCIA_LABEL.get(id_comp, str(id_comp))
        fases = listar_fases_categoria(ges, id_comp, id_cat)
        if progress:
            print(
                f"=== {comp_label} · {cat_label} (comp {id_comp} / cat {id_cat}): "
                f"{len(fases)} fases ===",
                file=sys.stderr,
                flush=True,
            )
        for nombre_fase, id_fase in fases.items():
            grupos = ges.get_grupos_de_fase(id_comp, id_cat, int(id_fase))
            if progress:
                print(
                    f"  {nombre_fase}: {len(grupos)} zonas",
                    file=sys.stderr,
                    flush=True,
                )
            for nombre_grupo, id_grupo in grupos.items():
                zona = norm_zona(nombre_grupo)
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
                            "fase": nombre_fase,
                            "zona": zona,
                            "local": local,
                            "visitante": visit,
                            "pts_local": _to_int(p.get("PTS_LOCAL")),
                            "pts_visit": _to_int(p.get("PTS_VISITANTE")),
                            "id_partido": idp,
                            "fecha": p.get("Fecha") or "",
                            "estado": p.get("Estado") or "",
                        }
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
    estado = str(p.get("estado") or "")
    if estado == "COMPLETO" and pts_prop is not None and pts_riv is not None:
        resultado = f"{pts_prop}-{pts_riv}"
    elif (
        pts_prop is not None
        and pts_riv is not None
        and str(pts_prop).strip() != ""
        and str(pts_riv).strip() != ""
    ):
        # datos.json sin campo estado
        resultado = f"{pts_prop}-{pts_riv}"

    return {
        "FECHA": fecha,
        "HORA": hora,
        "TIRA": tira_desde_nombre(propio),
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


# --------------------------------------------------------------------------- #
# CSV / Sheets
# --------------------------------------------------------------------------- #
def escribir_csv(filas: List[Dict[str, str]], path: Path = OUT_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for row in filas:
            w.writerow({h: row.get(h, "") for h in HEADERS})
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
                if str(old_val) != str(new_val):
                    changed = True
                    # Celda A1-notation
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
        description="Sync fixture Pedro Echagüe Formativas 2026 → Google Sheets"
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
        help="No sube a Google; escribe outputs/echague/fixture_echague.csv",
    )
    p.add_argument("--out-csv", default=str(OUT_CSV))
    p.add_argument("--spreadsheet-id", default="")
    p.add_argument("--worksheet", default="")
    p.add_argument(
        "--credentials",
        default=str(SERVICE_ACCOUNT),
        help="JSON de service account Google",
    )
    p.add_argument("--progress", action="store_true")
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
        if args.progress:
            print(
                f"Descargando partidos Echagüe desde GES "
                f"({len(fuentes)} categorías)…",
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
        )

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
    result: Dict[str, object] = {
        "partidos": len(filas),
        "por_categoria": dict(sorted(por_cat.items())),
        "visitantes_sin_direccion": sin_dir,
        "csv": str(csv_path),
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
