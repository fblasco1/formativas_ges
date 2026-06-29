# -*- coding: utf-8 -*-
"""
Genera informe HTML interactivo de marcadores raros MINI MASC / TORNEO DE CLASIFICACION.

Regla: >= 12 jugadores con al menos 10:00 min de juego por equipo.

  python analysis/generar_informe_marcadores_raros_mini.py --progress
  python analysis/generar_informe_marcadores_raros_mini.py --desde-csv outputs/mini_masc_clasificacion_marcadores_raros.csv
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.febamba.mini_masc_regla_plantilla import (
    LABEL_CAMBIOS,
    LABEL_OTRO,
    MIN_JUGADORES_REGLA,
    analizar_partido,
    jugador_cumple_regla,
)
from ingest.argbasket.partido import parse_boxscore_html

CSV_RAROS = ROOT / "outputs" / "mini_masc_clasificacion_marcadores_raros.csv"
CSV_TODOS = ROOT / "outputs" / "mini_masc_clasificacion_partidos.csv"
OUT_DIR = ROOT / "outputs" / "mini_masc"
OUT_HTML = OUT_DIR / "informe_marcadores_raros.html"
OUT_JSON = OUT_DIR / "datos_marcadores_raros.json"
PBP_JSON = OUT_DIR / "pbp_analisis.json"
DOCS_HTML = ROOT / "docs" / "mini_masc_clasificacion.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/mini_masc_clasificacion.html"


PBP_CAMPOS = (
    "tiene_pbp",
    "hubo_subs_q3",
    "subs_q3_entra",
    "subs_q3_sale",
    "subs_q3",
    "hubo_consecutivos",
    "n_consecutivos",
    "jugadores_consecutivos",
)


def cargar_pbp_por_id(path: Path) -> Dict[str, Dict[str, object]]:
    """Carga el análisis de play-by-play indexado por id de partido."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("partidos") or {}


def fusionar_pbp(
    partidos: List[Dict[str, object]], pbp_por_id: Dict[str, Dict[str, object]]
) -> Dict[str, int]:
    """
    Enriquecé cada partido con sus campos de play-by-play (por id). Devuelve un
    resumen contado sobre el conjunto de partidos mostrado.
    """
    con_pbp = con_subs_q3 = con_consec = 0
    for p in partidos:
        info = pbp_por_id.get(str(p.get("id") or ""))
        pbp = {
            "tiene_pbp": False,
            "hubo_subs_q3": False,
            "subs_q3_entra": 0,
            "subs_q3_sale": 0,
            "subs_q3": [],
            "hubo_consecutivos": False,
            "n_consecutivos": 0,
            "jugadores_consecutivos": [],
        }
        if info and info.get("tiene_pbp"):
            for k in PBP_CAMPOS:
                if k in info:
                    pbp[k] = info[k]
        p["pbp"] = pbp
        if pbp["tiene_pbp"]:
            con_pbp += 1
        if pbp["hubo_subs_q3"]:
            con_subs_q3 += 1
        if pbp["hubo_consecutivos"]:
            con_consec += 1
    return {
        "con_pbp": con_pbp,
        "con_subs_q3": con_subs_q3,
        "con_consecutivos": con_consec,
    }


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return None


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


def _team_totales_pts(html: str) -> List[Optional[int]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Optional[int]] = []
    for tbl in soup.find_all("table"):
        ttext = (tbl.get_text(" ", strip=True) or "").upper()
        if "PTOS" not in ttext or "MIN" not in ttext:
            continue
        tbody = tbl.find("tbody") or tbl
        pts_equipo: Optional[int] = None
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if cells and cells[0].lower().startswith("total"):
                pts_equipo = _to_int(cells[2] if len(cells) > 2 else "")
                break
        if pts_equipo is not None:
            out.append(pts_equipo)
    return out


def _jugador_para_ui(j: Dict[str, object]) -> Dict[str, object]:
    return {
        "nombre": j.get("nombre") or "",
        "nro": j.get("dorsal") or j.get("nro") or "",
        "min": j.get("min") or "",
        "pts": j.get("pts") if j.get("pts") is not None else "",
        "cumple": jugador_cumple_regla(j.get("min")),
    }


def fetch_partido_completo(
    row: Dict[str, str],
) -> Dict[str, object]:
    token = (row.get("ID_PARTIDO") or "").strip()
    pl_fix = _to_int(row.get("PTS_LOCAL"))
    pv_fix = _to_int(row.get("PTS_VISITANTE"))

    base: Dict[str, object] = {
        "id": token,
        "fecha": row.get("Fecha") or "",
        "local": row.get("Local") or "",
        "visitante": row.get("Visitante") or "",
        "pts_fix_local": pl_fix,
        "pts_fix_visit": pv_fix,
        "url": row.get("URL_Estadisticas") or _boxscore_url(token),
        "boxscore_ok": False,
        "equipos": [],
    }

    try:
        resp = requests.get(
            _boxscore_url(token),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,*/*",
            },
            timeout=45,
        )
        resp.raise_for_status()
        raw_html = resp.text
    except Exception as exc:
        base["error"] = str(exc)
        return base

    if len(raw_html) < 8000:
        base["error"] = "Acta vacía o no disponible"
        return base

    parsed = parse_boxscore_html(raw_html)
    equipos_raw = parsed.get("equipos") or []
    totales = _team_totales_pts(raw_html)

    pl_box = pv_box = None
    if len(totales) >= 2:
        pl_box, pv_box = totales[0], totales[1]
    elif len(equipos_raw) >= 2:
        pl_box = sum(_to_int(j.get("pts")) or 0 for j in equipos_raw[0].get("jugadores") or [])
        pv_box = sum(_to_int(j.get("pts")) or 0 for j in equipos_raw[1].get("jugadores") or [])

    jug_local = (equipos_raw[0].get("jugadores") or []) if equipos_raw else []
    jug_visit = (equipos_raw[1].get("jugadores") or []) if len(equipos_raw) > 1 else []

    analisis = analizar_partido(
        pl_fix=pl_fix,
        pv_fix=pv_fix,
        pl_box=pl_box,
        pv_box=pv_box,
        jug_local=jug_local,
        jug_visit=jug_visit,
    )

    equipos_ui = []
    for eq in equipos_raw[:2]:
        jugadores = [_jugador_para_ui(j) for j in (eq.get("jugadores") or [])]
        equipos_ui.append(
            {
                "nombre": eq.get("nombre") or "",
                "jugadores": jugadores,
                "jug_regla": sum(1 for j in jugadores if j["cumple"]),
            }
        )

    ganador = analisis.get("GANADOR_BOX") or ""
    ganador_nombre = ""
    if ganador == "local":
        ganador_nombre = base["local"]
    elif ganador == "visitante":
        ganador_nombre = base["visitante"]

    base.update(
        {
            "boxscore_ok": True,
            "pts_box_local": pl_box,
            "pts_box_visit": pv_box,
            "equipos": equipos_ui,
            "jug_reg_local": analisis["JUG_REG_LOCAL"],
            "jug_reg_visit": analisis["JUG_REG_VISITANTE"],
            "cumple_local": analisis["CUMPLE_LOCAL"],
            "cumple_visit": analisis["CUMPLE_VISITANTE"],
            "no_cumple_local": analisis["NO_CUMPLE_LOCAL"],
            "no_cumple_visit": analisis["NO_CUMPLE_VISITANTE"],
            "ganador_box": ganador,
            "ganador_nombre": ganador_nombre,
            "np_local": analisis["NP_LOCAL"],
            "np_visit": analisis["NP_VISITANTE"],
            "especial": analisis["ESPECIAL"],
            "otro": analisis["OTRO"],
            "flags": analisis["FLAGS"],
            "dif_box": analisis["DIF_BOX"],
        }
    )
    return base


def cargar_total_categoria(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def _pct(n: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * n / total, 1)


def cargar_filas_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def construir_dataset(
    rows: List[Dict[str, str]], *, workers: int, progress: bool
) -> List[Dict[str, object]]:
    out: List[Optional[Dict[str, object]]] = [None] * len(rows)

    def _task(i: int, row: Dict[str, str]) -> tuple[int, Dict[str, object]]:
        return i, fetch_partido_completo(row)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_task, i, r) for i, r in enumerate(rows)]
        done = 0
        for fut in as_completed(futures):
            i, data = fut.result()
            out[i] = data
            done += 1
            if progress and (done % 25 == 0 or done == len(rows)):
                print(f"  descargados {done}/{len(rows)}", file=sys.stderr, flush=True)
    return [x for x in out if x is not None]


def calcular_resumen(
    partidos: List[Dict[str, object]], *, total_categoria: int
) -> Dict[str, object]:
    total = len(partidos)
    con_box = [p for p in partidos if p.get("boxscore_ok")]
    especiales = [p for p in con_box if p.get("especial")]
    otros = [p for p in con_box if p.get("otro")]

    no_cumple_a = sum(1 for p in con_box if p.get("no_cumple_local"))
    no_cumple_b = sum(1 for p in con_box if p.get("no_cumple_visit"))

    difs = [p["dif_box"] for p in especiales if p.get("dif_box") is not None]
    avg_dif = round(sum(difs) / len(difs), 1) if difs else 0
    max_dif = max(difs) if difs else 0

    por_marcador: Dict[str, int] = {"0-0": 0, "20-0": 0, "0-20": 0}
    for p in partidos:
        pl = p.get("pts_fix_local")
        pv = p.get("pts_fix_visit")
        key = f"{pl}-{pv}"
        if key in por_marcador:
            por_marcador[key] += 1

    base_total = total_categoria or total

    return {
        "total_categoria": base_total,
        "total": total,
        "pct_marcadores_raros": _pct(total, base_total),
        "con_boxscore": len(con_box),
        "pct_con_boxscore": _pct(len(con_box), base_total),
        "no_cumple_equipo_a": no_cumple_a,
        "pct_no_cumple_equipo_a": _pct(no_cumple_a, base_total),
        "no_cumple_equipo_b": no_cumple_b,
        "pct_no_cumple_equipo_b": _pct(no_cumple_b, base_total),
        "especiales": len(especiales),
        "pct_especiales": _pct(len(especiales), base_total),
        "otros": len(otros),
        "pct_otros": _pct(len(otros), base_total),
        "dif_box_promedio_especial": avg_dif,
        "dif_box_maximo_especial": max_dif,
        "por_marcador_fixture": por_marcador,
    }


def _render_html(
    partidos: List[Dict[str, object]],
    resumen: Dict[str, object],
    *,
    fecha_actualizacion: str,
    pbp_resumen: Optional[Dict[str, object]] = None,
) -> str:
    data_json = json.dumps(partidos, ensure_ascii=False)
    res_json = json.dumps(resumen, ensure_ascii=False)
    pbp_res_json = json.dumps(pbp_resumen or {}, ensure_ascii=False)

    label_cambios_js = json.dumps(LABEL_CAMBIOS, ensure_ascii=False)
    label_otro_js = json.dumps(LABEL_OTRO, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>MINI MASC Clasificación — marcadores 0-0 / 20-0 / 0-20</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --paper: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --accent: #2563eb;
      --ok: #059669;
      --warn: #d97706;
      --bad: #dc2626;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    .layout {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }}
    header, section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 20px 22px;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    h2 {{ margin: 0 0 8px; font-size: 16px; }}
    .subtitle {{ color: var(--muted); font-size: 13px; margin: 0; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-top: 16px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      background: #fafbfc;
    }}
    .stat .n {{ font-size: 22px; font-weight: 700; color: var(--accent); }}
    .stat .l {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}
    .caption {{ font-size: 12px; color: var(--muted); margin: 0 0 12px; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
      align-items: center;
    }}
    input[type="search"], select {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 13px;
      background: white;
    }}
    input[type="search"] {{ flex: 1; min-width: 180px; }}
    .chip {{
      border: 1px solid var(--line);
      background: white;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      cursor: pointer;
    }}
    .chip.active {{ background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }}
    tbody tr:hover {{ background: #f8fafc; }}
    .btn-detalle {{
      border: 1px solid #93c5fd;
      background: #eff6ff;
      color: #1d4ed8;
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
    }}
    .btn-detalle:hover {{ background: #dbeafe; }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 10px;
      font-weight: 600;
    }}
    .badge.ok {{ background: #ecfdf5; color: var(--ok); }}
    .badge.no {{ background: #fef2f2; color: var(--bad); }}
    .badge.special {{ background: #fff7ed; color: var(--warn); }}
    .scoreline {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin: 12px 0;
      font-size: 14px;
    }}
    .scorebox {{
      flex: 1;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      text-align: center;
    }}
    .scorebox .pts {{ font-size: 22px; font-weight: 700; }}
    .scorebox.fixture {{ background: #fef2f2; }}
    .scorebox.box {{ background: #ecfdf5; }}
    .box-table td.cumple {{ color: var(--ok); font-weight: 600; }}
    .box-table td.nocumple {{ color: var(--muted); }}
    .note {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 12px;
      color: #1e3a8a;
      margin-top: 10px;
    }}
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.45);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 1000;
    }}
    .modal-backdrop.open {{ display: flex; }}
    .modal {{
      background: var(--paper);
      border-radius: 12px;
      border: 1px solid var(--line);
      width: min(720px, 100%);
      max-height: 90vh;
      overflow: auto;
      padding: 20px 22px;
      position: relative;
    }}
    .modal-close {{
      position: absolute;
      top: 12px;
      right: 14px;
      border: none;
      background: transparent;
      font-size: 22px;
      line-height: 1;
      cursor: pointer;
      color: var(--muted);
    }}
    .modal-close:hover {{ color: var(--text); }}
    @media (max-width: 1100px) {{
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <header>
      <h1>MINI MASCULINO · Torneo de Clasificación</h1>
      <p class="subtitle">Competencia GES 2015 · A=local, B=visitante · Actualizado: {html.escape(fecha_actualizacion)}</p>
      <p class="subtitle" style="margin-top:6px">Clasificación por resultado de fixture y jugadores con ≥10:00 min (A=local, B=visitante).</p>
      <div class="stats" id="stats"></div>
    </header>

    <section>
      <h2>Partidos con marcador 0-0, 20-0 o 0-20</h2>
      <p class="caption">
        Filtrá por indicador o buscá por equipo/fecha. Usá <strong>Ver detalle</strong> para abrir el boxscore completo,
        las reglas incumplidas y el análisis de play-by-play (cambios en el 3er cuarto y cuartos consecutivos).
      </p>
      <div class="toolbar">
        <input type="search" id="q" placeholder="Buscar equipo o fecha…"/>
        <button type="button" class="chip active" data-flag="todos">Todos</button>
        <button type="button" class="chip" data-flag="A:NP">A:NP</button>
        <button type="button" class="chip" data-flag="B:NP">B:NP</button>
        <button type="button" class="chip" data-flag="cambios">{html.escape(LABEL_CAMBIOS)}</button>
        <button type="button" class="chip" data-flag="otro">{html.escape(LABEL_OTRO)}</button>
        <button type="button" class="chip" data-flag="subs_q3">Con cambios en Q3</button>
        <button type="button" class="chip" data-flag="consecutivos">Con cuartos consecutivos</button>
      </div>
      <div style="overflow:auto;">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Local (A)</th>
              <th>Visitante (B)</th>
              <th>Fixture</th>
              <th>Boxscore</th>
              <th>NP</th>
              <th>Cambios Q3</th>
              <th>Cuartos consecutivos</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="lista"></tbody>
        </table>
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
    const PARTIDOS = {data_json};
    const RESUMEN = {res_json};
    const PBP_RESUMEN = {pbp_res_json};
    const MIN_REG = {MIN_JUGADORES_REGLA};
    const LABEL_CAMBIOS = {label_cambios_js};
    const LABEL_OTRO = {label_otro_js};

    function fmtScore(a, b) {{
      if (a == null || b == null) return "—";
      return a + "-" + b;
    }}

    function fmtStat(n, pct) {{
      if (pct === undefined || pct === null) return String(n);
      return `${{n}} (${{pct}}%)`;
    }}

    function nombreEquipo(p, lado) {{
      return lado === "local" ? p.local : (lado === "visitante" ? p.visitante : "?");
    }}

    function celdaNP(p) {{
      if (!p.boxscore_ok) return '<span class="badge no">Sin acta</span>';
      const out = [];
      if (p.np_local || (p.flags || "").includes("A:NP")) out.push('<span class="badge no">A:NP</span>');
      if (p.np_visit || (p.flags || "").includes("B:NP")) out.push('<span class="badge no">B:NP</span>');
      return out.length ? out.join(" ") : '<span class="caption">—</span>';
    }}

    function celdaCambiosQ3(p) {{
      const pbp = p.pbp || {{}};
      if (!pbp.tiene_pbp) return '<span class="caption">Sin relato</span>';
      if (!pbp.hubo_subs_q3) return '<span class="badge ok">No</span>';
      return `<span class="badge special">Sí · ${{pbp.subs_q3_entra||0}} ingreso(s)</span>`;
    }}

    function celdaConsecutivos(p) {{
      const pbp = p.pbp || {{}};
      if (!pbp.tiene_pbp) return '<span class="caption">Sin relato</span>';
      if (!pbp.hubo_consecutivos) return '<span class="badge ok">No</span>';
      return `<span class="badge no">${{pbp.n_consecutivos||0}} jugador(es)</span>`;
    }}

    function renderStats() {{
      const el = document.getElementById("stats");
      const items = [
        ["Total partidos categoría", RESUMEN.total_categoria, null],
        ["Partidos con marcador 0-0/20-0/0-20", RESUMEN.total, RESUMEN.pct_marcadores_raros],
        ["EQUIPO A no llega mínimo de jugadores", RESUMEN.no_cumple_equipo_a, RESUMEN.pct_no_cumple_equipo_a],
        ["EQUIPO B no llega mínimo de jugadores", RESUMEN.no_cumple_equipo_b, RESUMEN.pct_no_cumple_equipo_b],
        [LABEL_CAMBIOS, RESUMEN.especiales, RESUMEN.pct_especiales],
        [LABEL_OTRO, RESUMEN.otros, RESUMEN.pct_otros],
        ["Diferencia de Puntos en partidos con Regla de cambios Q3 u otros.", RESUMEN.dif_box_promedio_especial, null],
      ];
      if (PBP_RESUMEN && PBP_RESUMEN.con_pbp) {{
        const base = PBP_RESUMEN.con_pbp;
        const pctPbp = (n) => base > 0 ? Math.round(1000 * n / base) / 10 : 0;
        items.push(["Marcadores raros con cambios DURANTE el 3er cuarto", PBP_RESUMEN.con_subs_q3, pctPbp(PBP_RESUMEN.con_subs_q3)]);
        items.push(["Marcadores raros con jugadores en cuartos consecutivos", PBP_RESUMEN.con_consecutivos, pctPbp(PBP_RESUMEN.con_consecutivos)]);
      }}
      el.innerHTML = items.map(([l, n, pct]) =>
        `<div class="stat"><div class="n">${{fmtStat(n, pct)}}</div><div class="l">${{l}}</div></div>`
      ).join("");
    }}

    let filtroFlag = "todos";

    function matchFiltro(p, q) {{
      const pbp = p.pbp || {{}};
      const hay = (p.local + " " + p.visitante + " " + p.fecha + " " + (p.flags||"")).toLowerCase().includes(q);
      if (!hay) return false;
      if (filtroFlag === "todos") return true;
      if (filtroFlag === "A:NP") return p.np_local || (p.flags || "").includes("A:NP");
      if (filtroFlag === "B:NP") return p.np_visit || (p.flags || "").includes("B:NP");
      if (filtroFlag === "cambios") return p.especial || (p.flags || "").includes(LABEL_CAMBIOS);
      if (filtroFlag === "otro") return p.otro || (p.flags || "").includes(LABEL_OTRO);
      if (filtroFlag === "subs_q3") return !!pbp.hubo_subs_q3;
      if (filtroFlag === "consecutivos") return !!pbp.hubo_consecutivos;
      return true;
    }}

    function renderLista() {{
      const q = document.getElementById("q").value.trim().toLowerCase();
      const tbody = document.getElementById("lista");
      const rows = PARTIDOS.filter(p => matchFiltro(p, q));
      tbody.innerHTML = rows.map(p => `<tr>
          <td>${{p.fecha}}</td>
          <td>${{p.local}}</td>
          <td>${{p.visitante}}</td>
          <td>${{fmtScore(p.pts_fix_local, p.pts_fix_visit)}}</td>
          <td>${{fmtScore(p.pts_box_local, p.pts_box_visit)}}</td>
          <td>${{celdaNP(p)}}</td>
          <td>${{celdaCambiosQ3(p)}}</td>
          <td>${{celdaConsecutivos(p)}}</td>
          <td><button type="button" class="btn-detalle" data-id="${{p.id}}">Ver detalle</button></td>
        </tr>`).join("");
      tbody.querySelectorAll(".btn-detalle").forEach(btn => {{
        btn.addEventListener("click", (e) => {{
          e.stopPropagation();
          abrirModal(btn.dataset.id);
        }});
      }});
    }}

    function cerrarModal() {{
      const backdrop = document.getElementById("modal-backdrop");
      backdrop.classList.remove("open");
      backdrop.setAttribute("aria-hidden", "true");
      document.getElementById("modal-body").innerHTML = "";
    }}

    function boxscoreHtml(p) {{
      if (!p.boxscore_ok) {{
        return `<div class="note">${{p.error || "Sin boxscore disponible"}}</div>`;
      }}
      const eqHtml = (p.equipos || []).map(eq => {{
        const rows = (eq.jugadores || []).map(j => {{
          const cls = j.cumple ? "cumple" : "nocumple";
          return `<tr><td>${{j.nro}}</td><td>${{j.nombre}}</td><td class="${{cls}}">${{j.min}}</td><td>${{j.pts}}</td></tr>`;
        }}).join("");
        const ok = eq.jug_regla >= MIN_REG;
        return `<h3>${{eq.nombre}} <span class="badge ${{ok ? "ok" : "no"}}">${{eq.jug_regla}}/${{MIN_REG}} ≥10:00</span></h3>
          <table class="box-table"><thead><tr><th>#</th><th>Jugador</th><th>Min</th><th>Pts</th></tr></thead><tbody>${{rows}}</tbody></table>`;
      }}).join("");
      const flagsTxt = p.flags || "";
      const nota = flagsTxt
        ? `<div class="note"><strong>Indicadores:</strong> ${{flagsTxt}}${{p.especial && p.dif_box != null ? ` · Dif. box: <strong>${{p.dif_box}}</strong> pts` : ""}}</div>`
        : "";
      return `
        <div class="scoreline">
          <div class="scorebox fixture"><div>Fixture</div><div class="pts">${{fmtScore(p.pts_fix_local, p.pts_fix_visit)}}</div></div>
          <div class="scorebox box"><div>Boxscore</div><div class="pts">${{fmtScore(p.pts_box_local, p.pts_box_visit)}}</div></div>
        </div>
        ${{nota}}
        ${{eqHtml}}`;
    }}

    function pbpHtml(p) {{
      const pbp = p.pbp || {{}};
      if (!pbp.tiene_pbp) {{
        return '<h3 style="margin-top:18px;">Play-by-play</h3><p class="caption">Este partido no tiene relato en vivo disponible.</p>';
      }}
      let subsHtml;
      if (!pbp.hubo_subs_q3) {{
        subsHtml = '<p class="caption">Sin sustituciones durante el 3er cuarto (solo formación de arranque).</p>';
      }} else {{
        const items = (pbp.subs_q3 || []).map(s => {{
          const eq = nombreEquipo(p, s.equipo);
          const cls = s.accion === "ENTRA" ? "ok" : "no";
          return `<li><span class="badge ${{cls}}">${{s.accion}}</span> #${{s.dorsal||""}} ${{s.nombre||""}} <span class="caption">(${{eq}} · ${{s.clock}})</span></li>`;
        }}).join("");
        subsHtml = `<ul style="margin:6px 0 0; padding-left:18px;">${{items}}</ul>`;
      }}
      let consecHtml;
      if (!pbp.hubo_consecutivos) {{
        consecHtml = '<p class="caption">Ningún jugador estuvo en cancha en cuartos consecutivos.</p>';
      }} else {{
        const items = (pbp.jugadores_consecutivos || []).map(c => {{
          const eq = nombreEquipo(p, c.equipo);
          const pares = (c.pares || []).map(par => par.join("-")).join(", ");
          const cuartos = (c.cuartos || []).join(", ");
          return `<li>#${{c.dorsal||""}} ${{c.nombre||""}} <span class="caption">(${{eq}})</span> — cuartos jugados: ${{cuartos}} · consecutivos: <strong>${{pares}}</strong></li>`;
        }}).join("");
        consecHtml = `<ul style="margin:6px 0 0; padding-left:18px;">${{items}}</ul>`;
      }}
      return `
        <h3 style="margin-top:18px;">Cambios durante el 3er cuarto <span class="badge ${{pbp.hubo_subs_q3 ? "special" : "ok"}}">${{pbp.subs_q3_entra||0}} ingreso(s) · ${{pbp.subs_q3_sale||0}} salida(s)</span></h3>
        ${{subsHtml}}
        <h3 style="margin-top:16px;">Jugadores en cuartos consecutivos <span class="badge ${{pbp.hubo_consecutivos ? "no" : "ok"}}">${{pbp.n_consecutivos||0}}</span></h3>
        ${{consecHtml}}`;
    }}

    function abrirModal(id) {{
      const p = PARTIDOS.find(x => x.id === id);
      const body = document.getElementById("modal-body");
      const backdrop = document.getElementById("modal-backdrop");
      if (!p) return;
      body.innerHTML = `
        <h2 id="modal-title">${{p.local}} vs ${{p.visitante}}</h2>
        <p class="caption">${{p.fecha}} · A (local) · B (visitante)${{p.boxscore_ok ? ` · Ganador box: <strong>${{p.ganador_nombre || "Empate"}}</strong>` : ""}}</p>
        ${{boxscoreHtml(p)}}
        ${{pbpHtml(p)}}`;
      backdrop.classList.add("open");
      backdrop.setAttribute("aria-hidden", "false");
    }}

    document.getElementById("q").addEventListener("input", renderLista);
    document.querySelectorAll("[data-flag]").forEach(btn => {{
      btn.addEventListener("click", () => {{
        document.querySelectorAll("[data-flag]").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        filtroFlag = btn.dataset.flag;
        renderLista();
      }});
    }});
    document.getElementById("modal-close").addEventListener("click", cerrarModal);
    document.getElementById("modal-backdrop").addEventListener("click", (e) => {{
      if (e.target.id === "modal-backdrop") cerrarModal();
    }});
    document.addEventListener("keydown", (e) => {{
      if (e.key === "Escape") cerrarModal();
    }});

    renderStats();
    renderLista();
  </script>
</body>
</html>"""


def publicar_docs(out_html: Path) -> Path:
    """Copia el informe a docs/ para GitHub Pages."""
    DOCS_HTML.parent.mkdir(parents=True, exist_ok=True)
    DOCS_HTML.write_text(out_html.read_text(encoding="utf-8"), encoding="utf-8")
    return DOCS_HTML


def main() -> int:
    p = argparse.ArgumentParser(description="Informe HTML marcadores raros MINI MASC")
    p.add_argument("--csv", default=str(CSV_RAROS))
    p.add_argument(
        "--csv-todos",
        default=str(CSV_TODOS),
        help="CSV con todos los partidos de la categoría (para total y %).",
    )
    p.add_argument("--out-html", default=str(OUT_HTML))
    p.add_argument("--out-json", default=str(OUT_JSON))
    p.add_argument(
        "--pbp-json",
        default=str(PBP_JSON),
        help="Análisis de play-by-play (analysis/analizar_pbp_mini.py).",
    )
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--desde-json", default="", help="Saltear descarga y usar JSON cache")
    p.add_argument(
        "--publicar-docs",
        action="store_true",
        help=f"Copia a docs/ para GitHub Pages ({PUBLIC_URL})",
    )
    p.add_argument("--progress", action="store_true")
    args = p.parse_args()

    fecha_actualizacion = date.today().strftime("%d/%m/%Y")
    total_categoria = cargar_total_categoria(Path(args.csv_todos))

    if args.desde_json:
        partidos = json.loads(Path(args.desde_json).read_text(encoding="utf-8"))
    else:
        rows = cargar_filas_csv(Path(args.csv))
        if not rows:
            print("CSV vacío", file=sys.stderr)
            return 1
        if args.progress:
            print(f"Descargando {len(rows)} boxscores…", file=sys.stderr)
        partidos = construir_dataset(rows, workers=args.workers, progress=args.progress)

    resumen = calcular_resumen(partidos, total_categoria=total_categoria)
    resumen["fecha_actualizacion"] = fecha_actualizacion

    # Persistir cache de boxscore (sin datos PBP) antes de fusionar.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(
        json.dumps(partidos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Fusionar play-by-play por id de partido en cada fila.
    pbp_por_id = cargar_pbp_por_id(Path(args.pbp_json))
    pbp_resumen = fusionar_pbp(partidos, pbp_por_id)
    if args.progress:
        print(
            f"PBP fusionado: {pbp_resumen['con_pbp']}/{len(partidos)} con relato | "
            f"subs Q3={pbp_resumen['con_subs_q3']} | consecutivos={pbp_resumen['con_consecutivos']}",
            file=sys.stderr,
        )

    out_path = Path(args.out_html)
    out_path.write_text(
        _render_html(
            partidos,
            resumen,
            fecha_actualizacion=fecha_actualizacion,
            pbp_resumen=pbp_resumen,
        ),
        encoding="utf-8",
    )

    publicado = None
    if args.publicar_docs:
        publicado = str(publicar_docs(out_path))

    result = {
        "resumen": resumen,
        "html": str(out_path),
        "json": args.out_json,
        "public_url": PUBLIC_URL if args.publicar_docs else None,
        "docs_html": publicado,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.publicar_docs:
        print(f"\nLink para dirigentes FeBAMBA: {PUBLIC_URL}", file=sys.stderr)
        print("(Publicar: commit + push de docs/ a la rama configurada en GitHub Pages)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
