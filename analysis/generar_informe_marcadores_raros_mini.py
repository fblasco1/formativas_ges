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
    MIN_JUGADORES_REGLA,
    analizar_partido,
    jugador_cumple_regla,
)
from ingest.argbasket.partido import parse_boxscore_html

CSV_RAROS = ROOT / "outputs" / "mini_masc_clasificacion_marcadores_raros.csv"
OUT_DIR = ROOT / "outputs" / "mini_masc"
OUT_HTML = OUT_DIR / "informe_marcadores_raros.html"
OUT_JSON = OUT_DIR / "datos_marcadores_raros.json"
DOCS_HTML = ROOT / "docs" / "mini_masc_clasificacion.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/mini_masc_clasificacion.html"
LABEL_CAMBIOS = "Regla de cambios Q3 u otros"


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
            "flags": analisis["FLAGS"],
            "dif_box": analisis["DIF_BOX"],
        }
    )
    return base


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


def calcular_resumen(partidos: List[Dict[str, object]]) -> Dict[str, object]:
    total = len(partidos)
    con_box = [p for p in partidos if p.get("boxscore_ok")]
    especiales = [p for p in con_box if p.get("especial")]

    no_cumple_a = sum(1 for p in con_box if p.get("no_cumple_local"))
    no_cumple_b = sum(1 for p in con_box if p.get("no_cumple_visit"))
    np_a = sum(1 for p in con_box if p.get("np_local"))
    np_b = sum(1 for p in con_box if p.get("np_visit"))

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

    return {
        "total": total,
        "con_boxscore": len(con_box),
        "no_cumple_equipo_a": no_cumple_a,
        "no_cumple_equipo_b": no_cumple_b,
        "np_equipo_a": np_a,
        "np_equipo_b": np_b,
        "especiales": len(especiales),
        "dif_box_promedio_especial": avg_dif,
        "dif_box_maximo_especial": max_dif,
        "por_marcador_fixture": por_marcador,
    }


def _render_html(
    partidos: List[Dict[str, object]],
    resumen: Dict[str, object],
    *,
    fecha_actualizacion: str,
) -> str:
    data_json = json.dumps(partidos, ensure_ascii=False)
    res_json = json.dumps(resumen, ensure_ascii=False)

    casos_rows = []
    for p in partidos:
        if not p.get("especial"):
            continue
        plb = p.get("pts_box_local")
        pvb = p.get("pts_box_visit")
        plf = p.get("pts_fix_local")
        pvf = p.get("pts_fix_visit")
        casos_rows.append(
            "<tr>"
            f"<td>{html.escape(str(p.get('fecha', '')))}</td>"
            f"<td>{html.escape(str(p.get('local', '')))}</td>"
            f"<td>{html.escape(str(p.get('visitante', '')))}</td>"
            f"<td>{html.escape(str(p.get('flags', '')))}</td>"
            f"<td>{html.escape(str(p.get('ganador_nombre', '')))}</td>"
            f"<td>{plf}-{pvf}</td>"
            f"<td>{plb}-{pvb}</td>"
            f"<td><strong>{p.get('dif_box', '')}</strong></td>"
            "</tr>"
        )

    casos_table = "\n".join(casos_rows) if casos_rows else (
        f"<tr><td colspan='8'>No hay partidos con {html.escape(LABEL_CAMBIOS)}.</td></tr>"
    )
    label_cambios_js = json.dumps(LABEL_CAMBIOS, ensure_ascii=False)

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
      display: grid;
      grid-template-columns: 1fr 420px;
      gap: 16px;
      max-width: 1400px;
      margin: 0 auto;
      padding: 20px;
      align-items: start;
    }}
    header, section, .panel {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 20px 22px;
    }}
    header {{ grid-column: 1 / -1; }}
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
    tbody tr {{ cursor: pointer; }}
    tbody tr:hover {{ background: #f1f5f9; }}
    tbody tr.selected {{ background: #eff6ff; }}
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
    .panel {{ max-height: none; overflow: visible; }}
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
    .share {{
      margin-top: 14px;
      padding: 12px 14px;
      border: 1px solid #bfdbfe;
      border-radius: 10px;
      background: #f0f9ff;
      font-size: 13px;
    }}
    .share a {{ color: var(--accent); font-weight: 600; word-break: break-all; }}
    @media (max-width: 1100px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      .panel {{ max-height: none; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <header>
      <h1>MINI MASCULINO · Torneo de Clasificación</h1>
      <p class="subtitle">Competencia GES 2015 · A=local, B=visitante · Actualizado: {html.escape(fecha_actualizacion)}</p>
      <p class="subtitle" style="margin-top:6px">A:NP / B:NP = equipo con &lt;12 jugadores con ≥10:00 min · {html.escape(LABEL_CAMBIOS)} = boxscore contradice fixture (0-0 / 20-0 / 0-20)</p>
      <div class="share">
        <strong>Link para dirigentes FeBAMBA:</strong>
        <a href="{html.escape(PUBLIC_URL)}">{html.escape(PUBLIC_URL)}</a>
      </div>
      <div class="stats" id="stats"></div>
    </header>

    <section>
      <h2>Partidos con marcador 0-0, 20-0 o 0-20</h2>
      <p class="caption">Seleccioná un partido para ver el boxscore y sus indicadores (A:NP, B:NP, {html.escape(LABEL_CAMBIOS)}).</p>
      <div class="toolbar">
        <input type="search" id="q" placeholder="Buscar equipo o fecha…"/>
        <select id="filtro">
          <option value="todos">Todos</option>
          <option value="box">Con boxscore</option>
          <option value="no_cumple_a">Equipo A no llega mínimo</option>
          <option value="no_cumple_b">Equipo B no llega mínimo</option>
          <option value="especial">{html.escape(LABEL_CAMBIOS)}</option>
        </select>
        <button type="button" class="chip active" data-chip="todos">Todos</button>
        <button type="button" class="chip" data-chip="especial">{html.escape(LABEL_CAMBIOS)}</button>
      </div>
      <div style="overflow:auto; max-height: 62vh;">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Local</th>
              <th>Vis</th>
              <th>Fix</th>
              <th>Box</th>
              <th>Ganador</th>
              <th>Flags</th>
            </tr>
          </thead>
          <tbody id="lista"></tbody>
        </table>
      </div>
    </section>

    <aside class="panel" id="detalle">
      <h2>Boxscore</h2>
      <p class="caption">Elegí un partido de la tabla.</p>
    </aside>

    <section style="grid-column: 1 / -1;">
      <h2>Partidos con {html.escape(LABEL_CAMBIOS)}</h2>
      <p class="caption">Diferencia de puntos según boxscore (|local − visitante|). 20-0+B gana box · 0-20+A gana box · 0-0+ganador en boxscore.</p>
      <div style="overflow:auto;">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Local (A)</th>
              <th>Visitante (B)</th>
              <th>Flags</th>
              <th>Ganador (box)</th>
              <th>Fixture</th>
              <th>Boxscore</th>
              <th>Dif. box</th>
            </tr>
          </thead>
          <tbody>{casos_table}</tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    const PARTIDOS = {data_json};
    const RESUMEN = {res_json};
    const MIN_REG = {MIN_JUGADORES_REGLA};
    const LABEL_CAMBIOS = {label_cambios_js};

    function fmtScore(a, b) {{
      if (a == null || b == null) return "—";
      return a + "-" + b;
    }}

    function labelFlag(f) {{
      if (f === "ESPECIAL") return LABEL_CAMBIOS;
      return f;
    }}

    function badgeFlags(p) {{
      if (!p.boxscore_ok) return '<span class="badge no">Sin acta</span>';
      const flags = p.flags || "";
      if (!flags) return '<span class="badge no">—</span>';
      return flags.split(" | ").map(f => {{
        const lbl = labelFlag(f);
        const cls = (f === "ESPECIAL" || lbl === LABEL_CAMBIOS) ? "special" : (f.includes("NP") ? "no" : "ok");
        return `<span class="badge ${{cls}}">${{lbl}}</span>`;
      }}).join(" ");
    }}

    function renderStats() {{
      const el = document.getElementById("stats");
      const items = [
        ["Partidos con marcador 0-0/20-0/0-20", RESUMEN.total],
        ["Con boxscore", RESUMEN.con_boxscore],
        ["EQUIPO A no llega mínimo de jugadores", RESUMEN.no_cumple_equipo_a],
        ["EQUIPO B no llega mínimo de jugadores", RESUMEN.no_cumple_equipo_b],
        [LABEL_CAMBIOS, RESUMEN.especiales],
        ["Diferencia de Puntos en partidos con Regla de cambios Q3 u otros.", RESUMEN.dif_box_promedio_especial],
      ];
      el.innerHTML = items.map(([l, n]) =>
        `<div class="stat"><div class="n">${{n}}</div><div class="l">${{l}}</div></div>`
      ).join("");
    }}

    function matchFiltro(p, q, filtro) {{
      const hay = (p.local + " " + p.visitante + " " + p.fecha + " " + (p.flags||"")).toLowerCase().includes(q);
      if (!hay) return false;
      if (filtro === "box") return p.boxscore_ok;
      if (filtro === "no_cumple_a") return p.no_cumple_local;
      if (filtro === "no_cumple_b") return p.no_cumple_visit;
      if (filtro === "especial") return p.especial;
      return true;
    }}

    function renderLista() {{
      const q = document.getElementById("q").value.trim().toLowerCase();
      const filtro = document.getElementById("filtro").value;
      const tbody = document.getElementById("lista");
      const rows = PARTIDOS.filter(p => matchFiltro(p, q, filtro));
      tbody.innerHTML = rows.map(p => {{
        const gan = p.ganador_nombre || "—";
        return `<tr data-id="${{p.id}}">
          <td>${{p.fecha}}</td>
          <td>${{p.local}}</td>
          <td>${{p.visitante}}</td>
          <td>${{fmtScore(p.pts_fix_local, p.pts_fix_visit)}}</td>
          <td>${{fmtScore(p.pts_box_local, p.pts_box_visit)}}</td>
          <td>${{gan}}</td>
          <td>${{badgeFlags(p)}}</td>
        </tr>`;
      }}).join("");
      tbody.querySelectorAll("tr").forEach(tr => {{
        tr.addEventListener("click", () => {{
          tbody.querySelectorAll("tr").forEach(r => r.classList.remove("selected"));
          tr.classList.add("selected");
          renderDetalle(tr.dataset.id);
        }});
      }});
    }}

    function renderDetalle(id) {{
      const p = PARTIDOS.find(x => x.id === id);
      const el = document.getElementById("detalle");
      if (!p) return;
      if (!p.boxscore_ok) {{
        el.innerHTML = `<h2>${{p.local}} vs ${{p.visitante}}</h2><p class="caption">${{p.fecha}}</p><div class="note">${{p.error || "Sin boxscore"}}</div>`;
        return;
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

      const flagsTxt = (p.flags || "").split(" | ").map(labelFlag).join(" | ");
      const nota = p.flags
        ? `<div class="note"><strong>Indicadores:</strong> ${{flagsTxt}}${{p.especial ? ` · Dif. box: <strong>${{p.dif_box}}</strong> pts` : ""}}</div>`
        : "";

      el.innerHTML = `
        <h2>${{p.local}} vs ${{p.visitante}}</h2>
        <p class="caption">${{p.fecha}} · A (local) · B (visitante) · Ganador box: <strong>${{p.ganador_nombre || "Empate"}}</strong></p>
        <div class="scoreline">
          <div class="scorebox fixture"><div>Fixture</div><div class="pts">${{fmtScore(p.pts_fix_local, p.pts_fix_visit)}}</div></div>
          <div class="scorebox box"><div>Boxscore</div><div class="pts">${{fmtScore(p.pts_box_local, p.pts_box_visit)}}</div></div>
        </div>
        ${{nota}}
        ${{eqHtml}}`;
    }}

    document.getElementById("q").addEventListener("input", renderLista);
    document.getElementById("filtro").addEventListener("change", renderLista);
    document.querySelectorAll("[data-chip]").forEach(btn => {{
      btn.addEventListener("click", () => {{
        document.querySelectorAll("[data-chip]").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("filtro").value = btn.dataset.chip === "especial" ? "especial" : "todos";
        renderLista();
      }});
    }});

    renderStats();
    renderLista();
    if (PARTIDOS.length) {{
      const first = PARTIDOS.find(p => p.boxscore_ok) || PARTIDOS[0];
      renderDetalle(first.id);
      const tr = document.querySelector(`tr[data-id="${{first.id}}"]`);
      if (tr) tr.classList.add("selected");
    }}
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
    p.add_argument("--out-html", default=str(OUT_HTML))
    p.add_argument("--out-json", default=str(OUT_JSON))
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

    resumen = calcular_resumen(partidos)
    resumen["fecha_actualizacion"] = fecha_actualizacion
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(
        json.dumps(partidos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out_path = Path(args.out_html)
    out_path.write_text(
        _render_html(partidos, resumen, fecha_actualizacion=fecha_actualizacion),
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
