# -*- coding: utf-8 -*-
"""
Genera la tabla de posiciones de SUPERIOR / MAYORES 2026 (competencia GES 2013).

Niveles / fases GES:
  · Pre Liga Metropolitana
  · Torneo Reclasificación Superior
  · Copa Oro / Copa Plata / Copa de Bronce (fase final)

Puntos: ganado=2, perdido=1; walkover 20-0 = 2 y 0 para el ausente.

Ejemplos:
  python analysis/generar_standings_superior_2026.py --progress
  python analysis/generar_standings_superior_2026.py --sin-boxscores --progress
  python analysis/generar_standings_superior_2026.py --desde-json outputs/superior_2026/datos.json
  python analysis/generar_standings_superior_2026.py --progress --publicar-docs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.partido import parse_boxscore_html
from ingest.febamba.mini_masc_regla_plantilla import parse_minutos_a_segundos
from ingest.febamba.standings_2026 import (
    PartidoGeneral,
    construir_tablas_categoria,
    nombre_display,
    puntos_partido_general,
    registrar_nombres_globales,
)
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider

ID_COMPETENCIA = 2013
ID_CATEGORIA = 5074
EDAD = "SUP"

# Nombre canónico de fase -> nombres GES posibles.
FASES_CANONICAS: Dict[str, Tuple[str, ...]] = {
    "PRE_LIGA": ("PRE LIGAMETROPOLITANA", "PRE LIGA METROPOLITANA", "PRELIGA METROPOLITANA"),
    "RECLASIFICACION": (
        "RECLASIFICACION SUPERIOR",
        "RECLASIFICACIÓN SUPERIOR",
        "TORNEO RECLASIFICACION SUPERIOR",
        "TORNEO RECLASIFICACIÓN SUPERIOR",
    ),
    "COPA_ORO": ("COPA ORO",),
    "COPA_PLATA": ("COPA PLATA",),
    "COPA_BRONCE": ("COPA DE BRONCE", "COPA BRONCE"),
}

FASE_LABEL: Dict[str, str] = {
    "PRE_LIGA": "Pre Liga Metropolitana",
    "RECLASIFICACION": "Torneo Reclasificación Superior",
    "COPA_ORO": "Copa Oro",
    "COPA_PLATA": "Copa Plata",
    "COPA_BRONCE": "Copa de Bronce",
}

FASE_ORDER = ["PRE_LIGA", "RECLASIFICACION", "COPA_ORO", "COPA_PLATA", "COPA_BRONCE"]

# Clasificación a Liga Metropolitana (solo Pre Liga):
# 3 mejores de cada zona + 2 mejores 4.º (desempate entre zonas por % victorias).
CLASIFICA_TOP_POR_ZONA = 3
MEJORES_CUARTOS = 2

OUT_DIR = ROOT / "outputs" / "superior_2026"
OUT_HTML = OUT_DIR / "tabla_posiciones.html"
OUT_JSON = OUT_DIR / "datos.json"
BOXSCORES_CACHE = OUT_DIR / "boxscores.json"
DOCS_HTML = ROOT / "docs" / "superior_2026_tabla_posiciones.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/superior_2026_tabla_posiciones.html"

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


def norm_zona(nombre: str) -> str:
    """Normaliza zona: 'CENTRO2/OESTE 2' -> 'CENTRO 2 / OESTE 2'."""
    t = (nombre or "").upper().strip()
    t = t.replace("0ESTE", "OESTE")
    t = t.replace("/", " / ")
    t = re.sub(r"([A-ZÁÉÍÓÚÑ])(\d)", r"\1 \2", t)
    return " ".join(t.split())


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


# --------------------------------------------------------------------------- #
# Resolución de fases
# --------------------------------------------------------------------------- #
def resolver_fases(ges: GesDeportivaExtractor) -> Dict[str, str]:
    """fase_canonica -> id_fase."""
    fases, _ = ges.get_ids_fases_grupos(ID_COMPETENCIA, id_categoria=ID_CATEGORIA)
    canon_map: Dict[str, str] = {}
    for canon, nombres in FASES_CANONICAS.items():
        wanted = {n.upper() for n in nombres}
        for nombre_ges, fid in fases.items():
            if nombre_ges.strip().upper() in wanted:
                canon_map[canon] = fid
                break
    return canon_map


# --------------------------------------------------------------------------- #
# Recolección de partidos
# --------------------------------------------------------------------------- #
def recolectar_partidos(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    fases: Dict[str, str],
    progress: bool = False,
) -> List[PartidoGeneral]:
    out: List[PartidoGeneral] = []
    for fase_canon, id_fase in fases.items():
        grupos = ges.get_grupos_de_fase(ID_COMPETENCIA, ID_CATEGORIA, int(id_fase))
        if progress:
            print(
                f"  {fase_canon}: {len(grupos)} zonas",
                file=sys.stderr,
                flush=True,
            )
        for nombre_grupo, id_grupo in grupos.items():
            zona = norm_zona(nombre_grupo)
            partidos = ges.get_info_partidos(
                ID_CATEGORIA,
                fecha_ini,
                fecha_fin,
                key=key,
                id_fase=int(id_fase),
                id_grupo=int(id_grupo),
            )
            completos = 0
            for p in partidos:
                if p.get("Estado") != "COMPLETO":
                    continue
                completos += 1
                out.append(
                    PartidoGeneral(
                        edad=EDAD,
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
            if progress:
                print(
                    f"    {zona}: {completos} partidos",
                    file=sys.stderr,
                    flush=True,
                )
    return out


# --------------------------------------------------------------------------- #
# Boxscores (modal)
# --------------------------------------------------------------------------- #
def _jugador_ui(j: Dict[str, object]) -> Dict[str, object]:
    return {
        "nro": j.get("dorsal") or j.get("nro") or "",
        "nombre": j.get("nombre") or "",
        "min": j.get("min") or "",
        "seg": parse_minutos_a_segundos(j.get("min")) or 0,
        "pts": j.get("pts") if j.get("pts") is not None else "",
    }


def _descargar_boxscore(token: str) -> Dict[str, object]:
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
        equipos.append({"nombre": eq.get("nombre") or "", "jugadores": jugs, "pts": pts})
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
# Dataset y payload
# --------------------------------------------------------------------------- #
def serializar_dataset(partidos: List[PartidoGeneral]) -> Dict[str, object]:
    return {"partidos": [asdict(p) for p in partidos]}


def cargar_dataset(data: Dict[str, object]) -> List[PartidoGeneral]:
    return [PartidoGeneral(**p) for p in data.get("partidos", [])]


def _fecha_key(fecha: object) -> Tuple[int, int, int, int, int]:
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


def construir_partidos_detalle(
    partidos: List[PartidoGeneral],
) -> Dict[str, Dict[str, list]]:
    """fase -> zona -> lista de partidos con flags de incumplimiento."""
    det: Dict[str, Dict[str, list]] = {}

    for pg in partidos:
        _, _, tipo = puntos_partido_general(pg.pts_local, pg.pts_visit)
        local, visit = nombre_display(pg.local), nombre_display(pg.visitante)
        inc: List[str] = []
        if tipo == "walkover_local":
            inc.append(f"{visit} no se presentó")
        elif tipo == "walkover_visit":
            inc.append(f"{local} no se presentó")
        elif tipo == "ambos_ausentes":
            inc.append("Ambos equipos ausentes")
        det.setdefault(pg.fase, {}).setdefault(pg.zona, []).append(
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

    for fase in det:
        for zona in det[fase]:
            det[fase][zona].sort(key=lambda m: _fecha_key(m.get("fecha")))
    return det


def _pct_victorias(ganados: int, pj: int) -> float:
    return (ganados / pj) if pj else 0.0


def construir_clasificacion_liga_metro(
    tablas_pre: Dict[str, list],
) -> Dict[str, object]:
    """
    Marca clasificados a Liga Metropolitana en Pre Liga.

    Regla: 3 primeros de cada zona + 2 mejores 4.º ordenados por % de victorias
    (ganados/PJ). Desempates secundarios: puntos, ganados, nombre.
    """
    # Anotar % en todas las filas.
    for zona, filas in tablas_pre.items():
        for f in filas:
            f["pct"] = round(_pct_victorias(int(f["ganados"]), int(f["pj"])), 6)
            f["clasifica"] = None  # top3 | mejor_4to | None

    cuartos: List[Dict[str, object]] = []
    clasificados_top3: List[Dict[str, object]] = []

    for zona, filas in tablas_pre.items():
        for f in filas:
            if int(f["pos"]) <= CLASIFICA_TOP_POR_ZONA:
                f["clasifica"] = "top3"
                clasificados_top3.append(
                    {
                        "equipo": f["equipo"],
                        "zona": zona,
                        "pos": f["pos"],
                        "pj": f["pj"],
                        "ganados": f["ganados"],
                        "puntos": f["puntos"],
                        "pct": f["pct"],
                        "via": "top3",
                    }
                )
            elif int(f["pos"]) == CLASIFICA_TOP_POR_ZONA + 1:
                cuartos.append(
                    {
                        "equipo": f["equipo"],
                        "zona": zona,
                        "pos": f["pos"],
                        "pj": f["pj"],
                        "ganados": f["ganados"],
                        "puntos": f["puntos"],
                        "pct": f["pct"],
                        "via": "4to",
                    }
                )

    cuartos.sort(
        key=lambda x: (
            -float(x["pct"]),
            -int(x["puntos"]),
            -int(x["ganados"]),
            str(x["equipo"]),
        )
    )
    for rank, c in enumerate(cuartos, start=1):
        c["rank_cuartos"] = rank
        c["clasifica"] = rank <= MEJORES_CUARTOS
        # Propagar a la fila de la tabla.
        for f in tablas_pre[str(c["zona"])]:
            if f["equipo"] == c["equipo"] and int(f["pos"]) == int(c["pos"]):
                f["clasifica"] = "mejor_4to" if c["clasifica"] else "4to"
                f["rank_cuartos"] = rank
                break

    mejores = [c for c in cuartos if c["clasifica"]]
    clasificados = clasificados_top3 + [
        {**c, "via": "mejor_4to"} for c in mejores
    ]

    return {
        "regla": (
            f"Clasifican a Liga Metropolitana los {CLASIFICA_TOP_POR_ZONA} mejores "
            f"de cada zona más los {MEJORES_CUARTOS} mejores 4.º (por % de victorias, "
            "porque las zonas tienen distinto número de equipos)."
        ),
        "top_por_zona": CLASIFICA_TOP_POR_ZONA,
        "mejores_cuartos": MEJORES_CUARTOS,
        "cuartos": cuartos,
        "clasificados": clasificados,
        "n_clasificados": len(clasificados),
    }


def construir_payload(
    partidos: List[PartidoGeneral],
    *,
    fecha_actualizacion: str,
    boxscores: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, object]:
    registrar_nombres_globales(partidos, [])
    tablas_cat = construir_tablas_categoria(partidos)

    tablas_json: Dict[str, Dict[str, list]] = {}
    for fase, zonas in tablas_cat.get(EDAD, {}).items():
        tablas_json[fase] = {}
        for zona in sorted(zonas):
            tablas_json[fase][zona] = [
                {
                    "pos": pos,
                    "equipo": f.equipo,
                    "pj": f.pj,
                    "ganados": f.ganados,
                    "perdidos": f.perdidos,
                    "walkover_favor": f.walkover_favor,
                    "walkover_contra": f.walkover_contra,
                    "puntos": f.puntos,
                    "pct": round(_pct_victorias(f.ganados, f.pj), 6),
                    "clasifica": None,
                }
                for pos, f in enumerate(zonas[zona], start=1)
            ]

    clasif_liga = None
    if "PRE_LIGA" in tablas_json:
        clasif_liga = construir_clasificacion_liga_metro(tablas_json["PRE_LIGA"])

    partidos_det = construir_partidos_detalle(partidos)

    equipos_unicos = set()
    for fase, zonas in tablas_json.items():
        for zona, filas in zonas.items():
            for f in filas:
                equipos_unicos.add((fase, zona, f["equipo"]))

    fases_presentes = [f for f in FASE_ORDER if f in tablas_json]

    return {
        "fecha": fecha_actualizacion,
        "titulo": "SUPERIOR 2026 · Tabla de posiciones",
        "subtitulo": "FeBAMBA · Competencia GES 2013 · Mayores Masculino",
        "fases": fases_presentes,
        "fase_labels": FASE_LABEL,
        "tablas": tablas_json,
        "partidos": partidos_det,
        "boxscores": boxscores or {},
        "clasificacion_liga_metro": clasif_liga,
        "resumen": {
            "partidos": len(partidos),
            "equipos": len(equipos_unicos),
            "zonas": sum(len(z) for z in tablas_json.values()),
            "clasificados_liga": (clasif_liga or {}).get("n_clasificados", 0),
        },
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
  <title>SUPERIOR 2026 · Tabla de posiciones</title>
  <style>
    :root {{
      --bg:#f1f5f9; --paper:#fff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0;
      --accent:#1d4ed8; --accent-soft:#eff6ff; --ok:#059669; --warn:#d97706; --bad:#dc2626;
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
    .seg {{ display:inline-flex; border:1px solid var(--line); border-radius:999px; overflow:hidden; flex-wrap:wrap; }}
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
    .small {{ font-size:11px; color:var(--muted); }}
    tr.inc-row td {{ background:#fef2f2; }}
    tr.cla-top3 td {{ background:#ecfdf5; }}
    tr.cla-4to td {{ background:#fffbeb; }}
    tr.cla-4to-out td {{ background:#f8fafc; }}
    .badge-cla {{ display:inline-block; border-radius:6px; padding:1px 8px; font-size:11px; font-weight:600; margin-left:6px; }}
    .badge-cla.top3 {{ background:#d1fae5; color:#065f46; }}
    .badge-cla.mejor {{ background:#fef3c7; color:#92400e; }}
    .badge-cla.out {{ background:#e2e8f0; color:#475569; }}
    .cla-box {{ margin-top:14px; border:1px solid var(--line); border-radius:10px; padding:14px 16px; background:#fafbfc; }}
    .cla-box h3 {{ margin:0 0 8px; font-size:14px; }}
    .cla-box ol {{ margin:8px 0 0; padding-left:20px; }}
    .cla-box li {{ margin:3px 0; font-size:13px; }}
    .cla-box li.ok {{ font-weight:600; color:#065f46; }}
    .res {{ font-weight:700; white-space:nowrap; }}
    .badge-inc {{ display:inline-block; background:#fee2e2; color:var(--bad); border-radius:6px;
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
    .note-bad {{ background:#fef2f2; border-color:#fca5a5; color:#7f1d1d; }}
    @media (max-width:760px) {{
      .stats {{ grid-template-columns:repeat(2,1fr); }}
      .hide-sm {{ display:none; }}
      .seg button {{ padding:8px 10px; font-size:12px; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <header>
      <h1>SUPERIOR 2026 · Tabla de posiciones</h1>
      <p class="subtitle">FeBAMBA · Competencia GES 2013 · Mayores Masculino · Actualizado: <span id="fecha"></span></p>
      <div class="stats" id="stats"></div>
    </header>

    <section>
      <div class="toolbar">
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
      <div id="cla-wrap" class="cla-box" style="display:none;"></div>

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
    let faseActual = (DATA.fases[0] || "");
    let zonaActual = "";
    let jornadaActual = 1;
    let matchesZona = [];

    document.getElementById("fecha").textContent = DATA.fecha;

    function renderStats() {{
      const r = DATA.resumen;
      const items = [
        ["Equipos en tablas", r.equipos],
        ["Partidos jugados", r.partidos],
        ["Clasif. Liga Metro", r.clasificados_liga || "—"],
      ];
      document.getElementById("stats").innerHTML = items.map(([l,n]) =>
        `<div class="stat"><div class="n">${{n}}</div><div class="l">${{l}}</div></div>`
      ).join("");
    }}

    function fmtPct(p) {{
      if (p == null) return "—";
      return (100 * p).toFixed(1).replace(".", ",") + "%";
    }}

    function renderSegFase() {{
      const seg = document.getElementById("seg-fase");
      seg.innerHTML = DATA.fases.map(f =>
        `<button data-fase="${{f}}" class="${{f===faseActual?'active':''}}">${{DATA.fase_labels[f]||f}}</button>`
      ).join("");
      seg.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {{
        faseActual = b.dataset.fase; zonaActual = "";
        renderSegFase(); renderZonas(); renderTabla(); renderNota(); renderClasificacion();
      }}));
    }}

    function renderZonas() {{
      const zonas = Object.keys((DATA.tablas||{{}})[faseActual] || {{}}).sort();
      if (!zonaActual || !zonas.includes(zonaActual)) zonaActual = zonas[0] || "";
      const sel = document.getElementById("sel-zona");
      sel.innerHTML = zonas.map(z => `<option value="${{z}}" ${{z===zonaActual?'selected':''}}>${{z}}</option>`).join("");
      sel.onchange = () => {{ zonaActual = sel.value; renderTabla(); }};
    }}

    function badgeCla(f) {{
      if (faseActual !== "PRE_LIGA") return "";
      if (f.clasifica === "top3") return `<span class="badge-cla top3">Liga Metro</span>`;
      if (f.clasifica === "mejor_4to") return `<span class="badge-cla mejor">Mejor 4.º</span>`;
      if (f.clasifica === "4to") return `<span class="badge-cla out">4.º #${{f.rank_cuartos||""}}</span>`;
      return "";
    }}

    function rowClass(f) {{
      if (faseActual !== "PRE_LIGA") return "";
      if (f.clasifica === "top3") return "cla-top3";
      if (f.clasifica === "mejor_4to") return "cla-4to";
      if (f.clasifica === "4to") return "cla-4to-out";
      return "";
    }}

    function renderTabla() {{
      const filas = ((DATA.tablas||{{}})[faseActual]||{{}})[zonaActual] || [];
      document.getElementById("titulo-tabla").textContent =
        `${{DATA.fase_labels[faseActual]||faseActual}} — Zona ${{zonaActual}}`;
      const showPct = faseActual === "PRE_LIGA";
      document.getElementById("thead").innerHTML = `<tr>
        <th class="pos">#</th><th class="eq">Equipo</th>
        <th>PJ</th><th>G</th><th>P</th>
        ${{showPct ? '<th title="Porcentaje de victorias (G/PJ)">%G</th>' : ""}}
        <th class="hide-sm" title="Ganados por no presentación rival">W.O.+</th>
        <th class="hide-sm" title="Perdidos por no presentarse">W.O.−</th>
        <th class="sep">Pts</th></tr>`;
      document.getElementById("tbody").innerHTML = filas.map(f => `<tr class="${{rowClass(f)}}">
        <td class="pos">${{f.pos}}</td>
        <td class="eq">${{esc(f.equipo)}}${{badgeCla(f)}}</td>
        <td>${{f.pj}}</td><td>${{f.ganados}}</td><td>${{f.perdidos}}</td>
        ${{showPct ? `<td>${{fmtPct(f.pct)}}</td>` : ""}}
        <td class="hide-sm">${{f.walkover_favor}}</td><td class="hide-sm">${{f.walkover_contra}}</td>
        <td class="sep tot">${{f.puntos}}</td></tr>`).join("");
      jornadaActual = 1;
      renderPartidos();
    }}

    function esc(s) {{ return (s==null?"":String(s)).replace(/[&<>]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c])); }}
    function score(m) {{ return `${{m.ml==null?"–":m.ml}} - ${{m.mv==null?"–":m.mv}}`; }}
    function boxBtn(m) {{
      if (!m.id) return '<span class="small">—</span>';
      return `<button type="button" class="btn" data-id="${{m.id}}">Ver detalle</button>`;
    }}

    function partidoRow(m) {{
      const cls = m.inc && m.inc.length ? "inc-row" : "";
      let det;
      if (m.inc && m.inc.length) {{
        det = m.inc.map(t => `<span class="badge-inc">${{esc(t)}}</span>`).join(" ");
      }} else {{
        det = `<span class="badge-ok">✓ Sin incumplimientos</span>`;
      }}
      return `<tr class="${{cls}}">
        <td class="small">${{esc(m.fecha||"")}}</td>
        <td class="eq">${{esc(m.local)}}</td>
        <td class="res">${{score(m)}}</td>
        <td class="eq">${{esc(m.visit)}}</td>
        <td class="det">${{det}}</td>
        <td>${{boxBtn(m)}}</td></tr>`;
    }}

    function renderPartidos() {{
      const todos = (((DATA.partidos||{{}})[faseActual]||{{}})[zonaActual] || []);
      const totalInc = todos.filter(m => m.inc && m.inc.length).length;
      const soloInc = document.getElementById("chk-inc").checked;
      const nfilas = (((DATA.tablas||{{}})[faseActual]||{{}})[zonaActual] || []).length;
      const porJornada = Math.max(1, Math.floor(nfilas / 2));

      const head = document.getElementById("partidos-head");
      const body = document.getElementById("partidos-body");
      const vacio = document.getElementById("partidos-vacio");
      const navWrap = document.getElementById("jornada-nav");

      document.getElementById("partidos-titulo").textContent =
        `Partidos — Zona ${{zonaActual}} (${{todos.length}}, con incumplimiento: ${{totalInc}})`;

      let lista;
      if (soloInc) {{
        navWrap.style.display = "none";
        lista = todos.filter(m => m.inc && m.inc.length);
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
      }}

      if (!lista.length) {{
        head.innerHTML = ""; body.innerHTML = "";
        vacio.style.display = "";
        vacio.textContent = soloInc ? "Sin incumplimientos en esta zona." : "Sin partidos para esta zona.";
        return;
      }}
      vacio.style.display = "none";
      head.innerHTML = `<tr><th>Fecha</th><th class="eq">Local</th><th>Resultado</th><th class="eq">Visitante</th><th class="det">Detalle</th><th>Acta</th></tr>`;
      body.innerHTML = lista.map(partidoRow).join("");
      matchesZona = todos;
      body.querySelectorAll(".btn[data-id]").forEach(b =>
        b.addEventListener("click", () => abrirModal(b.dataset.id)));
    }}

    function boxTeam(eq) {{
      const rows = (eq.jugadores || []).map(j =>
        `<tr><td>${{j.nro}}</td><td>${{esc(j.nombre)}}</td><td>${{j.min}}</td><td>${{j.pts}}</td></tr>`
      ).join("");
      return `<h3>${{esc(eq.nombre)}}</h3>
        <table class="box-table"><thead><tr><th>#</th><th>Jugador</th><th>Min</th><th>Pts</th></tr></thead>
        <tbody>${{rows}}</tbody></table>`;
    }}

    function abrirModal(id) {{
      const m = matchesZona.find(x => x.id === id);
      if (!m) return;
      const box = (DATA.boxscores || {{}})[id];
      const body = document.getElementById("modal-body");

      let nota;
      if (m.inc && m.inc.length) {{
        nota = `<p class="note note-bad"><strong>⚠ Incumplimiento:</strong> ${{m.inc.map(esc).join(" · ")}}</p>`;
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
        boxHtml = tot + box.equipos.map(boxTeam).join("");
      }} else {{
        boxHtml = `<div class="scoreline"><div class="scorebox"><div class="cap">Resultado</div><div class="pts">${{score(m)}}</div></div></div>
          <p class="small">Acta no disponible para este partido.</p>`;
      }}

      body.innerHTML = `<h2 id="modal-title" style="margin:0 24px 2px 0;">${{esc(m.local)}} vs ${{esc(m.visit)}}</h2>
        <p class="small">${{DATA.fase_labels[faseActual]||faseActual}} · Zona ${{zonaActual}}${{m.fecha ? " · " + esc(m.fecha) : ""}}</p>
        ${{nota}}
        ${{boxHtml}}`;
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
      const el = document.getElementById("nota-vista");
      if (faseActual === "PRE_LIGA") {{
        const c = DATA.clasificacion_liga_metro;
        el.innerHTML = `<strong>Clasificación a Liga Metropolitana.</strong> ${{c ? esc(c.regla) : ""}} `
          + `Ganar = 2, perder = 1. Un <em>20-0</em> es no presentación (0 pts). `
          + `<em>%G</em> = ganados / partidos jugados.`;
      }} else {{
        el.innerHTML = `<strong>Puntos por resultado.</strong> Ganar = 2, perder = 1. `
          + `Un <em>20-0</em> / <em>0-20</em> es no presentación: el ausente suma 0.`;
      }}
    }}

    function renderClasificacion() {{
      const wrap = document.getElementById("cla-wrap");
      const c = DATA.clasificacion_liga_metro;
      if (faseActual !== "PRE_LIGA" || !c) {{
        wrap.style.display = "none";
        wrap.innerHTML = "";
        return;
      }}
      wrap.style.display = "";
      const cuartosHtml = (c.cuartos || []).map(x => {{
        const cls = x.clasifica ? "ok" : "";
        const tag = x.clasifica
          ? `<span class="badge-cla mejor">Clasifica</span>`
          : `<span class="badge-cla out">No</span>`;
        return `<li class="${{cls}}">#${{x.rank_cuartos}} ${{esc(x.equipo)}} `
          + `<span class="small">(${{esc(x.zona)}} · ${{x.ganados}}/${{x.pj}} = ${{fmtPct(x.pct)}} · ${{x.puntos}} pts)</span> ${{tag}}</li>`;
      }}).join("");
      wrap.innerHTML = `<h3>Ranking de 4.º — acceso a Liga Metropolitana</h3>
        <p class="small" style="margin:0;">Ordenados por % de victorias (zonas con distinto tamaño). Clasifican los ${{c.mejores_cuartos}} primeros.</p>
        <ol>${{cuartosHtml}}</ol>`;
    }}

    document.getElementById("chk-inc").addEventListener("change", renderPartidos);
    document.getElementById("j-prev").addEventListener("click", () => {{ jornadaActual--; renderPartidos(); }});
    document.getElementById("j-next").addEventListener("click", () => {{ jornadaActual++; renderPartidos(); }});
    document.getElementById("modal-close").addEventListener("click", cerrarModal);
    document.getElementById("modal-backdrop").addEventListener("click", (e) => {{ if (e.target.id === "modal-backdrop") cerrarModal(); }});
    document.addEventListener("keydown", (e) => {{ if (e.key === "Escape") cerrarModal(); }});

    renderStats();
    renderSegFase();
    renderZonas();
    renderTabla();
    renderNota();
    renderClasificacion();
  </script>
</body>
</html>"""


def publicar_docs(out_html: Path) -> Path:
    DOCS_HTML.parent.mkdir(parents=True, exist_ok=True)
    DOCS_HTML.write_text(out_html.read_text(encoding="utf-8"), encoding="utf-8")
    return DOCS_HTML


def main() -> int:
    p = argparse.ArgumentParser(description="Tabla de posiciones SUPERIOR 2026")
    p.add_argument("--widget-key", default="", help="Default: config/competencias.json")
    p.add_argument("--fecha-ini", default="2025-1-1")
    p.add_argument("--fecha-fin", default="2026-12-31")
    p.add_argument("--out-html", default=str(OUT_HTML))
    p.add_argument("--out-json", default=str(OUT_JSON))
    p.add_argument("--desde-json", default="", help="Saltea la descarga y usa el dataset cacheado")
    p.add_argument("--sin-boxscores", action="store_true", help="No descarga/embebe boxscores para el modal")
    p.add_argument("--limite-boxscores", type=int, default=0, help="Tope de boxscores a descargar (debug)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--publicar-docs", action="store_true", help=f"Copia a docs/ ({PUBLIC_URL})")
    p.add_argument("--progress", action="store_true")
    args = p.parse_args()

    fecha_actualizacion = date.today().strftime("%d/%m/%Y")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.desde_json:
        data = json.loads(Path(args.desde_json).read_text(encoding="utf-8"))
        partidos = cargar_dataset(data)
    else:
        widget_key = args.widget_key or _load_widget_key()
        if not widget_key:
            print("Falta widget_key (config/competencias.json)", file=sys.stderr)
            return 1
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))

        if args.progress:
            print("Resolviendo fases…", file=sys.stderr)
        fases = resolver_fases(ges)
        if not fases:
            print("No se encontraron las fases esperadas en GES.", file=sys.stderr)
            return 1
        if args.progress:
            for canon, fid in fases.items():
                print(f"  {canon} -> {fid} ({FASE_LABEL.get(canon, canon)})", file=sys.stderr)

        if args.progress:
            print("Descargando partidos…", file=sys.stderr)
        partidos = recolectar_partidos(
            ges,
            key=widget_key,
            fecha_ini=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            fases=fases,
            progress=args.progress,
        )

        Path(args.out_json).write_text(
            json.dumps(serializar_dataset(partidos), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    boxscores: Dict[str, Dict[str, object]] = {}
    if not args.sin_boxscores:
        if args.progress:
            print("Descargando boxscores para el modal…", file=sys.stderr)
        tokens = [p.id_partido for p in partidos]
        boxscores = descargar_boxscores(
            tokens,
            workers=max(args.workers, 12),
            progress=args.progress,
            limite=args.limite_boxscores,
        )

    payload = construir_payload(
        partidos,
        fecha_actualizacion=fecha_actualizacion,
        boxscores=boxscores,
    )
    out_html = Path(args.out_html)
    out_html.write_text(_render_html(payload), encoding="utf-8")

    publicado = str(publicar_docs(out_html)) if args.publicar_docs else None

    print(
        json.dumps(
            {
                "resumen": payload["resumen"],
                "fases": payload["fases"],
                "clasificacion_liga_metro": {
                    "n": (payload.get("clasificacion_liga_metro") or {}).get("n_clasificados"),
                    "mejores_cuartos": [
                        {
                            "equipo": c["equipo"],
                            "zona": c["zona"],
                            "pct": c["pct"],
                            "ganados": c["ganados"],
                            "pj": c["pj"],
                        }
                        for c in ((payload.get("clasificacion_liga_metro") or {}).get("cuartos") or [])
                        if c.get("clasifica")
                    ],
                },
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
