# -*- coding: utf-8 -*-
"""
Landing pública: Propuesta de Competencias Formativas FeBAMBA 2027.

Une la narrativa de la presentación (formato, fases, calendarios, escenarios
de regionalización) con el explorador de mapas/distancias y tablas dinámicas
por nivel (misma fuente que informe_viajes_niveles.html).

  python analysis/generar_landing_formativas_2027.py
  python analysis/generar_landing_formativas_2027.py --recalcular
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NIVELES_JSON = ROOT / "outputs" / "viajes_elite42" / "niveles_viajes.json"
STANDINGS_HTML = ROOT / "docs" / "formativas_2026_tabla_posiciones.html"
STANDINGS_OUT = ROOT / "outputs" / "formativas_2026" / "tabla_posiciones.html"
OUT_HTML = ROOT / "docs" / "propuesta_formativas_2027.html"

FASES_SEGUNDA = (
    "INTERCONFERENCIA_A",
    "INTERCONFERENCIA_B",
    "NIVEL_1",
    "NIVEL_2",
    "NIVEL_3",
)
FASE_LABELS = {
    "INTERCONFERENCIA_A": "Interconferencia A",
    "INTERCONFERENCIA_B": "Interconferencia B",
    "NIVEL_1": "Nivel 1 (GES)",
    "NIVEL_2": "Nivel 2 (GES)",
    "NIVEL_3": "Nivel 3 (GES)",
}
# Nivel 2027 → fase actual Segunda Fase 2026
NIVEL_A_FASE_2026 = {
    1: "INTERCONFERENCIA_A",
    2: "INTERCONFERENCIA_B",
    3: "NIVEL_1",
    4: "NIVEL_2",
    5: "NIVEL_3",
    6: "NIVEL_3",
}


def _cargar_payload(*, recalcular: bool) -> dict:
    if recalcular:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from analysis.generar_informe_viajes_elite42 import calcular_payload

        return calcular_payload()
    if not NIVELES_JSON.exists():
        raise SystemExit(
            f"Falta {NIVELES_JSON}. Corré con --recalcular o generá el informe de viajes."
        )
    with NIVELES_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def _cargar_standings_segunda() -> dict:
    """Extrae tablas de Segunda Fase desde el HTML de standings GES."""
    import re

    path = STANDINGS_HTML if STANDINGS_HTML.exists() else STANDINGS_OUT
    if not path.exists():
        raise SystemExit(
            f"Falta standings HTML ({STANDINGS_HTML} o {STANDINGS_OUT})."
        )
    text = path.read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\s*\n", text, re.S)
    if not m:
        raise SystemExit(f"No se encontró DATA en {path}")
    raw = json.loads(m.group(1))
    tablas_in = raw.get("tablas") or {}
    tablas: dict = {}
    for fase in FASES_SEGUNDA:
        zonas = {}
        for zona, filas in (tablas_in.get(fase) or {}).items():
            zonas[zona] = [
                {
                    "pos": f.get("pos"),
                    "equipo": f.get("equipo"),
                    "pj": f.get("pj_general"),
                    "g": f.get("ganados"),
                    "p": f.get("perdidos"),
                    "pts_g": f.get("pts_general"),
                    "pts_pres": f.get("pts_presentacion"),
                    "pts": f.get("puntos"),
                }
                for f in filas
            ]
        tablas[fase] = zonas

    # Movilidad 2027 indexada por nombre de standings y por clave.
    movilidad: dict = {}
    niv_path = ROOT / "data" / "niveles_2027.json"
    if niv_path.exists():
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from ingest.febamba.standings_2026 import clave_equipo

        with niv_path.open(encoding="utf-8") as f:
            niv = json.load(f)
        by_clave: dict = {}
        for _n, bloque in (niv.get("niveles") or {}).items():
            for e in bloque.get("equipos") or []:
                info = {
                    "status": e.get("status") or "",
                    "nivel_2027": e.get("nivel_2027"),
                    "detalle": e.get("detalle") or "",
                }
                eq = e.get("equipo") or ""
                ck = e.get("clave") or clave_equipo(eq)
                if eq:
                    movilidad[eq] = info
                if ck:
                    by_clave[ck] = info
                    movilidad[ck] = info
        for clave, info in (niv.get("status_por_clave") or {}).items():
            if not clave:
                continue
            payload = {
                "status": info.get("status") or "",
                "nivel_2027": info.get("nivel_2027"),
                "detalle": info.get("detalle") or "",
            }
            by_clave[clave] = payload
            movilidad[clave] = payload

        # Cruzar nombres de la tabla GES → movilidad por clave.
        for fase in FASES_SEGUNDA:
            for _zona, filas in (tablas.get(fase) or {}).items():
                for f in filas:
                    eq = f.get("equipo") or ""
                    if not eq or eq in movilidad:
                        continue
                    ck = clave_equipo(eq)
                    if ck in by_clave:
                        movilidad[eq] = by_clave[ck]

    return {
        "fecha": raw.get("fecha") or "",
        "fase_labels": dict(FASE_LABELS),
        "nivel_a_fase": {str(k): v for k, v in NIVEL_A_FASE_2026.items()},
        "tablas": tablas,
        "movilidad": movilidad,
    }


def generar(payload: dict, out: Path = OUT_HTML) -> Path:
    data_js = json.dumps(payload, ensure_ascii=False)
    standings = _cargar_standings_segunda()
    standings_js = json.dumps(standings, ensure_ascii=False)
    colores = payload["colores_region"]
    total = payload.get("total_equipos", sum(n["n_equipos"] for n in payload["niveles"]))

    html = (
        _HTML_TEMPLATE.replace("__TOTAL_EQUIPOS__", str(total))
        .replace("__COLOR_CENTRO__", colores["CENTRO"])
        .replace("__COLOR_NORTE__", colores["NORTE"])
        .replace("__COLOR_SUR__", colores["SUR"])
        .replace("__COLOR_OESTE__", colores["OESTE"])
        .replace("__DATA_JS__", data_js)
        .replace("__STANDINGS_JS__", standings_js)
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FeBAMBA · Propuesta Formativas 2027</title>
  <meta name="description" content="Propuesta integral de formato competitivo por niveles para las categorías formativas FeBAMBA 2027."/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    :root {
      --bg: #e8eef6;
      --bg-deep: #0b1220;
      --paper: #ffffff;
      --ink: #0f172a;
      --muted: #64748b;
      --line: #d7e0ec;
      --brand: #1d4ed8;
      --brand-deep: #0f2a6b;
      --ok: #166534;
      --ok-bg: #dcfce7;
      --warn: #92400e;
      --warn-bg: #fef3c7;
      --bad: #991b1b;
      --bad-bg: #fee2e2;
      --r-centro: __COLOR_CENTRO__;
      --r-norte: __COLOR_NORTE__;
      --r-sur: __COLOR_SUR__;
      --r-oeste: __COLOR_OESTE__;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: "DM Sans", "Segoe UI", system-ui, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 10% -10%, rgba(29,78,216,.12), transparent 60%),
        radial-gradient(900px 420px at 90% 0%, rgba(14,165,233,.10), transparent 55%),
        var(--bg);
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }
    h1, h2, h3, .brand-name {
      font-family: Outfit, "DM Sans", system-ui, sans-serif;
      letter-spacing: -0.02em;
      line-height: 1.15;
    }
    a { color: var(--brand); }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 0 22px; }
    .wrap-wide { max-width: 1280px; margin: 0 auto; padding: 0 22px; }

    /* —— Nav —— */
    .topnav {
      position: sticky; top: 0; z-index: 40;
      backdrop-filter: blur(10px);
      background: rgba(11,18,32,.88);
      border-bottom: 1px solid rgba(255,255,255,.08);
    }
    .topnav .inner {
      display: flex; align-items: center; justify-content: space-between;
      gap: 16px; padding: 12px 0; max-width: 1280px; margin: 0 auto; padding-left: 22px; padding-right: 22px;
    }
    .topnav .logo {
      color: #f8fafc; font-weight: 800; font-size: 14px; text-decoration: none;
      letter-spacing: .04em; text-transform: uppercase;
    }
    .topnav nav { display: flex; flex-wrap: wrap; gap: 4px 14px; }
    .topnav nav a {
      color: #cbd5e1; text-decoration: none; font-size: 13px; font-weight: 500;
    }
    .topnav nav a:hover { color: #fff; }

    /* —— Hero —— */
    .hero {
      background:
        linear-gradient(145deg, rgba(11,18,32,.92) 0%, rgba(15,42,107,.88) 48%, rgba(29,78,216,.82) 100%),
        url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
      color: #f8fafc;
      padding: 56px 0 64px;
      position: relative;
      overflow: hidden;
    }
    .hero::after {
      content: "";
      position: absolute; inset: auto -10% -40% 40%;
      height: 420px;
      background: radial-gradient(circle, rgba(14,165,233,.35), transparent 65%);
      pointer-events: none;
    }
    .hero .wrap { position: relative; z-index: 1; }
    .eyebrow {
      text-transform: uppercase; letter-spacing: .18em; font-size: 11px;
      font-weight: 700; color: #93c5fd; margin: 0 0 14px;
    }
    .brand-name {
      margin: 0 0 10px; font-size: clamp(2.2rem, 5vw, 3.4rem); font-weight: 800;
    }
    .hero h1 {
      margin: 0 0 14px; font-size: clamp(1.35rem, 2.8vw, 1.85rem);
      font-weight: 700; color: #e2e8f0; max-width: 720px;
    }
    .hero .lede {
      margin: 0 0 28px; color: #cbd5e1; font-size: 16px; max-width: 640px;
    }
    .cta-row { display: flex; flex-wrap: wrap; gap: 10px; }
    .btn {
      display: inline-flex; align-items: center; justify-content: center;
      padding: 11px 18px; border-radius: 10px; font-weight: 700; font-size: 14px;
      text-decoration: none; border: 1px solid transparent; transition: transform .15s ease;
    }
    .btn:hover { transform: translateY(-1px); }
    .btn-primary { background: #fff; color: var(--brand-deep); }
    .btn-ghost { background: transparent; color: #fff; border-color: rgba(255,255,255,.35); }

    .kpi-strip {
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
      margin-top: 36px;
    }
    .kpi {
      background: rgba(255,255,255,.08);
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 14px; padding: 16px 18px;
    }
    .kpi b { display: block; font-size: 1.7rem; font-family: Outfit, sans-serif; }
    .kpi span { font-size: 12px; color: #94a3b8; }

    /* —— Sections —— */
    section.block { padding: 52px 0; }
    section.block.alt { background: rgba(255,255,255,.55); }
    .sec-kicker {
      text-transform: uppercase; letter-spacing: .14em; font-size: 11px;
      font-weight: 700; color: var(--brand); margin: 0 0 8px;
    }
    .sec-title { margin: 0 0 10px; font-size: clamp(1.45rem, 2.5vw, 1.9rem); }
    .sec-lead { margin: 0 0 28px; color: var(--muted); max-width: 720px; font-size: 15px; }

    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .panel {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 22px 22px 20px;
    }
    .panel h3 { margin: 0 0 10px; font-size: 1.05rem; }
    .panel p { margin: 0; color: var(--muted); font-size: 14px; }
    .panel ul { margin: 10px 0 0; padding-left: 18px; color: var(--muted); font-size: 14px; }
    .panel li { margin: 4px 0; }

    .tag {
      display: inline-block; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .04em;
      padding: 3px 8px; border-radius: 6px; margin-bottom: 10px;
    }
    .tag-ok { background: var(--ok-bg); color: var(--ok); }
    .tag-mid { background: #e0e7ff; color: #3730a3; }
    .tag-bad { background: var(--bad-bg); color: var(--bad); }
    .tag-warn { background: var(--warn-bg); color: var(--warn); }

    .check { color: var(--ok); font-weight: 700; }
    .cross { color: var(--bad); font-weight: 700; }

    /* Calendario interactivo */
    .cal-shell {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 18px 22px;
    }
    .cal-month-tabs {
      display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px;
    }
    .cal-month-tabs button {
      border: 1px solid #cbd5e1; background: #fff; border-radius: 8px;
      padding: 8px 12px; cursor: pointer; font-size: 13px; font-weight: 600;
      font-family: inherit; color: var(--ink);
    }
    .cal-month-tabs button.active {
      background: var(--brand); color: #fff; border-color: var(--brand);
    }
    .cal-month-tabs button .fase-dot {
      display: inline-block; width: 6px; height: 6px; border-radius: 50%;
      margin-right: 5px; vertical-align: middle; background: #94a3b8;
    }
    .cal-month-tabs button.active .fase-dot { background: #93c5fd; }
    .cal-month-tabs button[data-fase="po"] .fase-dot { background: #f59e0b; }
    .cal-toolbar {
      display: flex; flex-wrap: wrap; justify-content: space-between;
      align-items: baseline; gap: 10px; margin-bottom: 12px;
    }
    .cal-toolbar h3 { margin: 0; font-size: 1.15rem; }
    .cal-legend {
      display: flex; flex-wrap: wrap; gap: 10px 14px; font-size: 12px; color: var(--muted);
    }
    .cal-legend i {
      display: inline-block; width: 12px; height: 12px; border-radius: 4px;
      margin-right: 5px; vertical-align: -1px;
    }
    .cal-legend .lg-play { background: #1d4ed8; }
    .cal-legend .lg-excl { background: #dc2626; }
    .cal-legend .lg-po { background: #d97706; }
    .cal-legend .lg-warn { background: #ca8a04; }
    .cal-grid-days {
      display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px;
    }
    .cal-dow {
      text-align: center; font-size: 11px; font-weight: 700; color: var(--muted);
      text-transform: uppercase; letter-spacing: .06em; padding: 4px 0 8px;
    }
    .cal-cell {
      min-height: 64px; border-radius: 10px; border: 1px solid #e2e8f0;
      background: #f8fafc; padding: 6px 7px; position: relative;
      font-size: 13px;
    }
    .cal-cell.empty { background: transparent; border-color: transparent; }
    .cal-cell .num { font-weight: 700; font-variant-numeric: tabular-nums; }
    .cal-cell .tag-day {
      display: block; margin-top: 4px; font-size: 10px; font-weight: 700;
      line-height: 1.25; letter-spacing: .01em;
    }
    .cal-cell.play {
      background: #eff6ff; border-color: #93c5fd; color: #1e3a8a;
    }
    .cal-cell.play .tag-day { color: #1d4ed8; }
    .cal-cell.excluded {
      background: #fef2f2; border-color: #fca5a5; color: #7f1d1d;
    }
    .cal-cell.excluded .tag-day { color: #dc2626; }
    .cal-cell.playoff {
      background: #fff7ed; border-color: #fdba74; color: #9a3412;
    }
    .cal-cell.playoff .tag-day { color: #c2410c; }
    .cal-cell.warn {
      background: #fefce8; border-color: #fde047; color: #713f12;
    }
    .cal-cell.warn .tag-day { color: #a16207; }
    .cal-detail {
      margin-top: 14px; padding: 12px 14px; border-radius: 12px;
      background: #f1f5f9; font-size: 13px; color: var(--muted);
      min-height: 44px;
    }
    .cal-detail strong { color: var(--ink); }
    .note-box {
      margin-top: 16px; padding: 14px 16px; border-radius: 12px;
      background: var(--warn-bg); color: var(--warn); font-size: 13px;
      border: 1px solid #fcd34d;
    }

    /* Niveles · tabs + graphics */
    .nv-shell {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px 16px 22px;
    }
    .nv-tabs {
      display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px;
    }
    .nv-tabs button {
      border: 1px solid #cbd5e1; background: #fff; border-radius: 8px;
      padding: 9px 14px; cursor: pointer; font-size: 13px; font-weight: 700;
      font-family: inherit; color: var(--ink);
    }
    .nv-tabs button.active {
      background: var(--brand); color: #fff; border-color: var(--brand);
    }
    .nv-tabs button small {
      display: block; font-weight: 500; font-size: 10px; opacity: .75; margin-top: 2px;
    }
    .nv-panel { display: none; }
    .nv-panel.active { display: block; }
    .nv-hero {
      display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px;
      margin-bottom: 14px; align-items: flex-start;
    }
    .nv-hero h3 { margin: 0 0 4px; font-size: 1.35rem; }
    .nv-hero .sub { margin: 0; color: var(--muted); font-size: 13px; }
    .nv-kpis {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px; margin-bottom: 16px;
    }
    .nv-kpi {
      background: #f8fafc; border: 1px solid var(--line); border-radius: 12px;
      padding: 10px 12px;
    }
    .nv-kpi b { display: block; font-size: 1.05rem; color: var(--brand); font-family: Outfit, sans-serif; }
    .nv-kpi span { font-size: 11px; color: var(--muted); }
    .nv-flow {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 18px;
    }
    .nv-flow .step {
      border-radius: 12px; padding: 12px; font-size: 13px; border: 1px solid var(--line);
      background: #f8fafc;
    }
    .nv-flow .step b {
      display: block; margin-bottom: 4px; font-size: 11px; text-transform: uppercase;
      letter-spacing: .06em; color: var(--muted);
    }
    .nv-flow .up { border-color: #86efac; background: #f0fdf4; }
    .nv-flow .stay { border-color: #cbd5e1; }
    .nv-flow .down { border-color: #fca5a5; background: #fef2f2; }
    .nv-phases {
      display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px;
    }
    .nv-phase {
      border: 1px solid var(--line); border-radius: 14px; padding: 14px;
      background: linear-gradient(180deg, #f8fafc 0%, #fff 40%);
    }
    .nv-phase h4 {
      margin: 0 0 8px; font-size: 14px; display: flex; align-items: center; gap: 8px;
    }
    .nv-phase .badge-fase {
      display: inline-block; background: var(--brand); color: #fff;
      font-size: 10px; font-weight: 800; padding: 3px 7px; border-radius: 6px;
      letter-spacing: .04em;
    }
    .nv-phase .badge-fase.f2 { background: #0f766e; }
    .nv-phase ul { margin: 0; padding-left: 16px; color: var(--muted); font-size: 13px; }
    .nv-phase li { margin: 4px 0; }
    .nv-zone-tabs {
      display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px;
    }
    .nv-zone-tabs button {
      border: 1px solid #cbd5e1; background: #fff; border-radius: 999px;
      padding: 5px 11px; cursor: pointer; font-size: 12px; font-weight: 600;
      font-family: inherit;
    }
    .nv-zone-tabs button.active { background: #0f172a; color: #fff; border-color: #0f172a; }
    .mock-table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid var(--line); }
    table.mock {
      width: 100%; border-collapse: collapse; font-size: 12px; background: #fff;
    }
    table.mock th, table.mock td {
      padding: 7px 8px; border-bottom: 1px solid #e2e8f0; text-align: left;
    }
    table.mock th { background: #f1f5f9; font-size: 11px; color: var(--muted); }
    table.mock tr:last-child td { border-bottom: 0; }
    table.mock .pos { font-weight: 800; width: 28px; color: var(--muted); }
    table.mock .club { font-weight: 600; }
    table.mock .num { text-align: right; font-variant-numeric: tabular-nums; }
    table.mock tr.lff td { background: #ecfdf5; }
    table.mock tr.po td { background: #eff6ff; }
    table.mock tr.asc td { background: #ecfdf5; }
    table.mock tr.desc td { background: #fef2f2; }
    table.mock .chip-r {
      display: inline-block; font-size: 9px; font-weight: 800; padding: 1px 6px;
      border-radius: 999px; margin-left: 6px; vertical-align: middle;
    }
    .chip-r.lff { background: #dcfce7; color: #166534; }
    .chip-r.po { background: #dbeafe; color: #1e40af; }
    .chip-r.desc { background: #fee2e2; color: #991b1b; }
    .chip-r.asc { background: #dcfce7; color: #166534; }
    .chip-r.keep { background: #e2e8f0; color: #334155; }
    .nv-bracket-wrap { margin-top: 8px; }
    .nv-bracket-wrap h4 { margin: 0 0 10px; font-size: 14px; }
    .bracket-tree {
      display: grid; grid-template-columns: 1.2fr 1fr 0.8fr 0.7fr; gap: 10px;
      align-items: center; overflow-x: auto; padding-bottom: 6px;
    }
    .bracket-col { display: flex; flex-direction: column; gap: 8px; justify-content: space-around; min-height: 280px; }
    .bracket-col.sf { min-height: 200px; }
    .bracket-col.fi { min-height: 120px; }
    .bk-match {
      background: #fff; border: 1px solid var(--line); border-radius: 10px;
      padding: 8px 10px; font-size: 12px; box-shadow: 0 1px 0 rgba(15,23,42,.04);
    }
    .bk-match .rnd {
      font-size: 10px; font-weight: 800; color: var(--muted); text-transform: uppercase;
      letter-spacing: .05em; margin-bottom: 4px;
    }
    .bk-match .side {
      display: flex; justify-content: space-between; gap: 8px; padding: 3px 0;
      border-top: 1px dashed #e2e8f0;
    }
    .bk-match .side:first-of-type { border-top: 0; }
    .bk-match .seed { font-weight: 700; color: var(--ink); }
    .bk-match .vs { color: var(--muted); font-size: 11px; }
    .bracket-ff {
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;
    }
    .bk-region {
      border: 1px solid var(--line); border-radius: 12px; padding: 12px; background: #fff;
    }
    .bk-region h5 { margin: 0 0 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
    .bk-region .final-four {
      margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--line);
      font-size: 12px; color: var(--muted);
    }
    .mock-note {
      margin: 8px 0 0; font-size: 11px; color: var(--muted); font-style: italic;
    }
    #nv-map {
      height: 480px; border-radius: 12px; border: 1px solid var(--line); margin: 12px 0 14px;
    }
    .nv-map-block { margin: 18px 0 8px; }
    .nv-map-block h4 { margin: 0 0 8px; font-size: 14px; }
    .nv-medias {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 8px; margin-bottom: 12px;
    }
    .nv-medias .stat {
      background: #f8fafc; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;
    }
    .nv-medias .stat b {
      display: block; font-size: 1.05rem; color: var(--brand); font-family: Outfit, sans-serif;
    }
    .nv-medias .stat span { font-size: 11px; color: var(--muted); }
    .nv-mix-toggle {
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 12px;
      font-size: 13px;
    }
    .st-block { margin-top: 18px; }
    .st-block h4 { margin: 0 0 8px; font-size: 14px; }
    .st-meta { font-size: 12px; color: var(--muted); margin: 0 0 10px; }

    /* Dual metrics */
    .dual { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .dual .panel h3 { display: flex; align-items: center; gap: 8px; }

    /* Explorer */
    #explorador { scroll-margin-top: 64px; }
    .explorer-shell {
      background: var(--paper); border: 1px solid var(--line);
      border-radius: 18px; padding: 18px 18px 22px;
    }
    .legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 0 0 14px; }
    .legend span { display: inline-flex; align-items: center; gap: 6px; font-size: .85rem; color: var(--muted); }
    .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
    .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
    .tab {
      border: 1px solid #cbd5e1; background: #fff; border-radius: 8px;
      padding: 9px 14px; cursor: pointer; font-size: .9rem; font-family: inherit;
    }
    .tab.active { background: var(--brand); color: #fff; border-color: var(--brand); }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .stat { background: #f8fafc; border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
    .stat b { display: block; font-size: 1.15rem; color: var(--brand); font-family: Outfit, sans-serif; }
    .stat span { font-size: .76rem; color: var(--muted); }
    #map { height: 520px; border-radius: 12px; border: 1px solid var(--line); }
    .filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 14px; }
    .chip {
      border: 1px solid #cbd5e1; background: #fff; border-radius: 999px;
      padding: 6px 12px; cursor: pointer; font-size: .8rem; color: var(--ink); font-family: inherit;
    }
    .chip.active { background: var(--brand); color: #fff; border-color: var(--brand); }
    .search-row {
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 0 0 12px;
    }
    .search-row input {
      flex: 1; min-width: 200px; border: 1px solid #cbd5e1; border-radius: 10px;
      padding: 10px 12px; font-size: 14px; font-family: inherit;
    }
    .search-row select {
      border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 12px;
      font-size: 14px; font-family: inherit; background: #fff;
    }
    table.dyn { width: 100%; border-collapse: collapse; font-size: .82rem; }
    table.dyn th, table.dyn td { padding: 7px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; }
    table.dyn th { background: #f1f5f9; position: sticky; top: 0; z-index: 1; }
    table.dyn tfoot td { background: #eef2ff; font-weight: 600; border-top: 2px solid #c7d2fe; position: sticky; bottom: 0; }
    .region { font-weight: 600; }
    .muted { color: var(--muted); font-size: .88rem; line-height: 1.45; }
    .num { white-space: nowrap; }
    .mixta-only { display: none; }
    body.show-mixta .mixta-only { display: table-cell; }
    .badge-mov {
      display: inline-block; margin-left: 6px; padding: 1px 7px; border-radius: 999px;
      font-size: 10px; font-weight: 700; vertical-align: middle;
    }
    .badge-mov.ASC { background: var(--ok-bg); color: var(--ok); }
    .badge-mov.DESC { background: var(--bad-bg); color: var(--bad); }
    .badge-mov.KEEP { background: #e2e8f0; color: #334155; }

    /* Bracket mini */
    .bracket {
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
      font-size: 12px; color: var(--muted);
    }
    .bracket div {
      background: #f8fafc; border: 1px dashed var(--line); border-radius: 8px;
      padding: 10px; text-align: center;
    }

    /* Horarios */
    .horario-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .horario-list {
      list-style: none; margin: 12px 0 0; padding: 0;
      display: grid; gap: 6px;
    }
    .horario-list li {
      display: flex; justify-content: space-between; gap: 12px;
      padding: 8px 10px; background: #f8fafc; border-radius: 8px; font-size: 14px;
    }
    .horario-list span { color: var(--muted); font-variant-numeric: tabular-nums; }

    footer.site {
      padding: 28px 0 40px; text-align: center; color: var(--muted); font-size: 12px;
    }
    footer.site a { color: var(--brand); font-weight: 600; }

    @media (max-width: 900px) {
      .kpi-strip, .grid-2, .grid-3, .dual, .nv-phases, .nv-flow, .horario-grid, .bracket, .bracket-ff, .bracket-tree {
        grid-template-columns: 1fr;
      }
      .nv-flow { grid-template-columns: 1fr; }
      .bracket-col { min-height: auto !important; }
      .cal-cell { min-height: 52px; font-size: 12px; }
      #map { height: 380px; }
      .topnav nav { display: none; }
    }
  </style>
</head>
<body>
  <div class="topnav">
    <div class="inner">
      <a class="logo" href="index.html">FeBAMBA · Formativas</a>
      <nav>
        <a href="#vision">Visión</a>
        <a href="#calendario">Calendario</a>
        <a href="#escenarios">Escenarios</a>
        <a href="#niveles">Niveles</a>
        <a href="#explorador">Posiciones 2026</a>
        <a href="#metricas">Tablas</a>
        <a href="#horarios">Horarios</a>
      </nav>
    </div>
  </div>

  <header class="hero">
    <div class="wrap">
      <p class="eyebrow">Federación de Básquetbol del Área Metropolitana de Buenos Aires</p>
      <p class="brand-name">FeBAMBA 2027</p>
      <h1>Propuesta de competencias formativas</h1>
      <p class="lede">
        Formato competitivo por niveles para las categorías formativas:
        193 equipos, 6 niveles, dos fases regulares y playoffs.
      </p>
      <div class="cta-row">
        <a class="btn btn-primary" href="#niveles">Ver niveles y mapas</a>
        <a class="btn btn-ghost" href="#calendario">Ver calendario</a>
      </div>
      <div class="kpi-strip">
        <div class="kpi"><b>__TOTAL_EQUIPOS__</b><span>Equipos participantes</span></div>
        <div class="kpi"><b>6</b><span>Niveles de competencia</span></div>
        <div class="kpi"><b>2 + PO</b><span>Fases + Playoffs</span></div>
        <div class="kpi"><b>28</b><span>Fechas de fase regular</span></div>
      </div>
    </div>
  </header>

  <section class="block" id="vision">
    <div class="wrap">
      <p class="sec-kicker">Visión general</p>
      <h2 class="sec-title">Un torneo por niveles, con dos lógicas de clasificación</h2>
      <p class="sec-lead">
        La jerarquía institucional (ascensos y descensos) se define por la tira.
        La excelencia por franja etaria (LFF, playoff y campeones) se define por categoría.
      </p>
      <div class="dual">
        <div class="panel">
          <span class="tag tag-mid">Tabla por tira</span>
          <h3>Ascensos y descensos</h3>
          <p>
            Suma acumulada de <strong>U13 + U15 + U17 + U21</strong>.
            U11 aporta solo punto de presentación; U9 no suma (objetivo: reincorporarlo en ~2 años con trabajo en mosquitos).
          </p>
          <ul>
            <li>Define en qué nivel compite el club</li>
            <li>Métrica de jerarquía institucional</li>
          </ul>
        </div>
        <div class="panel">
          <span class="tag tag-ok">Por categoría</span>
          <h3>LFF, playoff y campeones</h3>
          <p>
            Posición individual en <strong>U11, U13, U15, U17 y U21</strong>.
            Un club puede clasificar al playoff en una categoría aunque su tira global no lidere.
          </p>
          <ul>
            <li>Premia el trabajo específico por generación</li>
            <li>Determina campeones de nivel y categoría</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <section class="block alt" id="calendario">
    <div class="wrap">
      <p class="sec-kicker">Calendario 2027 · tentativo</p>
      <h2 class="sec-title">28 fechas + playoffs</h2>
      <p class="sec-lead">
        Elegí un mes para ver el calendario. En azul: fechas de competencia.
        En rojo: fines de semana o días excluidos. En naranja: playoffs. En amarillo: potencial conflicto.
      </p>
      <div class="cal-shell">
        <div class="cal-month-tabs" id="cal-tabs" role="tablist" aria-label="Meses 2027"></div>
        <div class="cal-toolbar">
          <h3 id="cal-title">—</h3>
          <div class="cal-legend">
            <span><i class="lg-play"></i>Fecha</span>
            <span><i class="lg-excl"></i>Excluido</span>
            <span><i class="lg-po"></i>Playoff</span>
            <span><i class="lg-warn"></i>Potencial</span>
          </div>
        </div>
        <div class="cal-grid-days" id="cal-grid" aria-live="polite"></div>
        <div class="cal-detail" id="cal-detail"></div>
      </div>
      <div class="note-box">
        Calendario tentativo: sujeto a fines de semana largos nacionales, elecciones y política de feriados del Consejo.
      </div>
    </div>
  </section>

  <section class="block" id="escenarios">
    <div class="wrap">
      <p class="sec-kicker">Niveles 1 y 2 · Interregionales</p>
      <h2 class="sec-title">Cómo armar las 4 zonas de 8</h2>
      <p class="sec-lead">
        32 equipos por nivel. Tres alternativas de regionalización; la recomendada prioriza paridad competitiva.
      </p>
      <div class="grid-3">
        <div class="panel">
          <span class="tag tag-ok">Plan A · recomendado</span>
          <h3>Sin regionalización</h3>
          <p>Sorteo equilibrado en 4 copones según rendimiento 2026.</p>
          <ul>
            <li class="check">✔ Máxima paridad competitiva</li>
            <li class="check">✔ Alineado al desarrollo formativo</li>
          </ul>
        </div>
        <div class="panel">
          <span class="tag tag-mid">Plan B · intermedio</span>
          <h3>2 + 2 subregiones</h3>
          <p>2 zonas Norte–Oeste + 2 zonas Centro–Sur.</p>
          <ul>
            <li class="check">✔ Reduce distancias</li>
            <li class="check">✔ Balance competitividad / logística</li>
          </ul>
        </div>
        <div class="panel">
          <span class="tag tag-bad">Plan C · no recomendado</span>
          <h3>Regionalizado 100%</h3>
          <p>Una zona = una región (Norte, Oeste, Centro, Sur).</p>
          <ul>
            <li class="cross">✖ Paridad desigual entre regiones</li>
            <li class="cross">✖ Clasificación inequitativa</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <section class="block alt" id="niveles">
    <div class="wrap-wide">
      <p class="sec-kicker">Desarrollo por nivel</p>
      <h2 class="sec-title">Formato, clasificación y movilidad</h2>
      <p class="sec-lead">
        Elegí un nivel. Cada ficha incluye mapa, medias de viaje, proyección de distancias
        y el esquema de cupos / playoffs.
      </p>
      <div class="nv-shell">
        <div class="nv-tabs" id="nv-tabs" role="tablist" aria-label="Niveles 2027"></div>
        <div id="nv-content"></div>
      </div>
    </div>
  </section>

  <section class="block" id="explorador">
    <div class="wrap-wide">
      <p class="sec-kicker">Tabla de posiciones 2026</p>
      <h2 class="sec-title">Segunda fase · Formativas (GES)</h2>
      <p class="sec-lead">
        Tablas actuales de la Segunda Fase embebidas en esta página.
        Elegí la fase y la zona. Fecha de standings: <span id="st-fecha">—</span>.
      </p>
      <div class="nv-shell">
        <div class="nv-tabs" id="st-fase-tabs" role="tablist" aria-label="Fases Segunda 2026"></div>
        <div class="nv-zone-tabs" id="st-zona-tabs" style="margin-bottom:12px"></div>
        <div id="st-tabla-wrap"></div>
      </div>
    </div>
  </section>

  <section class="block alt" id="metricas">
    <div class="wrap">
      <p class="sec-kicker">Clasificaciones</p>
      <h2 class="sec-title">Tabla por tira vs clasificación por categoría</h2>
      <div class="dual">
        <div class="panel">
          <h3>Tabla por tira</h3>
          <p>Define ascensos y descensos de nivel. Un club sube o baja por su desempeño conjunto como institución (U13+U15+U17+U21).</p>
        </div>
        <div class="panel">
          <h3>Por categoría</h3>
          <p>Define LFF, playoff y campeones. Premia el trabajo específico con cada generación (U11 a U21).</p>
        </div>
      </div>
    </div>
  </section>

  <section class="block" id="horarios">
    <div class="wrap">
      <p class="sec-kicker">Jornada</p>
      <h2 class="sec-title">Dos opciones de horarios</h2>
      <p class="sec-lead">Ambas con trade-offs de arbitraje, facultad y permanencia en el club.</p>
      <div class="horario-grid">
        <div class="panel">
          <span class="tag tag-mid">Opción 1</span>
          <h3>Mayores primero</h3>
          <ul class="horario-list">
            <li>U15 <span>09:30</span></li>
            <li>U17 <span>11:00</span></li>
            <li>U21 <span>12:30</span></li>
            <li>U9 <span>14:00</span></li>
            <li>U11 <span>15:30</span></li>
            <li>U13 <span>17:00</span></li>
          </ul>
          <ul>
            <li class="check">✔ Estímulo previo a la categoría siguiente</li>
            <li class="check">✔ Dupla arbitral disponible para U21 (máx. 3 partidos)</li>
            <li class="cross">✖ U13/U15 toda la jornada en el club</li>
            <li class="cross">✖ Facultad sábado a.m. para U21</li>
          </ul>
        </div>
        <div class="panel">
          <span class="tag tag-mid">Opción 2</span>
          <h3>Ascendente etario</h3>
          <ul class="horario-list">
            <li>U9 <span>09:30</span></li>
            <li>U11 <span>11:00</span></li>
            <li>U13 <span>12:30</span></li>
            <li>U15 <span>14:00</span></li>
            <li>U17 <span>15:30</span></li>
            <li>U21 <span>17:00</span></li>
          </ul>
          <ul>
            <li class="check">✔ Continuidad entrenadores / dobles categorías</li>
            <li class="check">✔ Adolescentes alineados al ritmo circadiano</li>
            <li class="cross">✖ U21 requiere dupla arbitral adicional</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <footer class="site">
    <div class="wrap">
      Propuesta FeBAMBA Formativas 2027
    </div>
  </footer>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
/* —— Calendario 2027 (tabs por mes) —— */
const CAL_YEAR = 2027;
const CAL_MONTHS = [
  {
    m: 3, label: 'Marzo', fase: '1', faseLabel: 'Fase 1',
    play: {13: 'Fecha', 20: 'Fecha'},
    excluded: {26: 'Semana Santa', 27: 'Semana Santa', 28: 'Semana Santa'},
    warn: {},
    playoff: {},
    resumen: 'Fechas 13 y 20. Semana Santa 26–28 excluida.'
  },
  {
    m: 4, label: 'Abril', fase: '1', faseLabel: 'Fase 1',
    play: {10: 'Fecha', 17: 'Fecha', 24: 'Fecha'},
    excluded: {2: 'Finde largo', 3: 'Finde largo', 4: 'Finde largo'},
    warn: {},
    playoff: {},
    resumen: 'Fechas 10, 17 y 24. Finde largo 2–4 excluido.'
  },
  {
    m: 5, label: 'Mayo', fase: '1', faseLabel: 'Fase 1',
    play: {8: 'Fecha', 15: 'Fecha', 22: 'Fecha', 29: 'Fecha'},
    excluded: {1: 'Feriado 1/5'},
    warn: {},
    playoff: {},
    resumen: 'Fechas 8, 15, 22 y 29. El 1/5 queda excluido.'
  },
  {
    m: 6, label: 'Junio', fase: '1', faseLabel: 'Fase 1',
    play: {5: 'Fecha', 12: 'Fecha', 20: 'Fecha', 26: 'Fecha'},
    excluded: {},
    warn: {19: 'Finde largo potencial', 20: 'Finde largo potencial', 21: 'Finde largo potencial'},
    playoff: {},
    resumen: 'Fechas 5, 12, 20 y 26. Finde 19–21 potencial (puede reprogramarse).'
  },
  {
    m: 7, label: 'Julio', fase: '1', faseLabel: 'Fase 1',
    play: {3: 'Fecha', 10: 'Fecha', 17: 'Fecha'},
    excluded: {9: 'Finde largo', 11: 'Finde largo', 24: 'Vacaciones de invierno', 31: 'Vacaciones de invierno'},
    warn: {10: 'Finde largo 9–11 (revisar)'},
    playoff: {},
    resumen: 'Fechas 3, 10 y 17. Finde 9–11 excluido salvo revisión del 10; 24 y 31 vacaciones. Reanuda 7/8.'
  },
  {
    m: 8, label: 'Agosto', fase: '2', faseLabel: 'Fase 2',
    play: {7: 'Fecha', 14: 'Fecha', 21: 'Fecha', 28: 'Fecha'},
    excluded: {},
    warn: {14: 'Puente potencial', 15: 'Puente potencial', 16: 'Puente potencial'},
    playoff: {},
    resumen: 'Fechas 7, 14, 21 y 28. Puente 14–16 potencial.'
  },
  {
    m: 9, label: 'Septiembre', fase: '2', faseLabel: 'Fase 2',
    play: {4: 'Fecha', 11: 'Fecha', 18: 'Fecha', 25: 'Fecha'},
    excluded: {},
    warn: {},
    playoff: {},
    resumen: 'Fechas 4, 11, 18 y 25.'
  },
  {
    m: 10, label: 'Octubre', fase: '2', faseLabel: 'Fase 2',
    play: {2: 'Fecha', 16: 'Fecha', 23: 'Fecha', 30: 'Fecha'},
    excluded: {10: 'EAM Minibásquet'},
    warn: {23: 'Elecciones presidenciales'},
    playoff: {},
    resumen: 'Fechas 2, 16, 23 y 30. 10/10 EAM excluido; 23/10 sujeto a elecciones.'
  },
  {
    m: 11, label: 'Noviembre', fase: '2', faseLabel: 'Fase 2',
    play: {6: 'Fecha', 13: 'Fecha', 20: 'Fecha'},
    excluded: {},
    warn: {20: 'Finde largo potencial'},
    playoff: {27: 'Octavos de final'},
    resumen: 'Fechas 6, 13 y 20. Playoffs: octavos el 27. 20/11 potencial finde largo.'
  },
  {
    m: 12, label: 'Diciembre', fase: 'po', faseLabel: 'Playoffs',
    play: {},
    excluded: {},
    warn: {},
    playoff: {4: 'Cuartos', 8: 'Semifinal', 9: 'Semifinal', 11: 'Finales'},
    resumen: 'Playoffs: 4 cuartos · 8–9 semis · 11 finales.'
  }
];

const DOW = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}
/** Lunes=0 … Domingo=6 */
function mondayIndex(year, month, day) {
  const js = new Date(year, month - 1, day).getDay(); // Dom=0
  return (js + 6) % 7;
}

function renderCalMonth(idx) {
  const meta = CAL_MONTHS[idx];
  document.getElementById('cal-title').textContent =
    `${meta.label} ${CAL_YEAR} · ${meta.faseLabel}`;
  document.getElementById('cal-detail').innerHTML =
    `<strong>${meta.label}:</strong> ${meta.resumen}`;

  const grid = document.getElementById('cal-grid');
  let html = DOW.map(d => `<div class="cal-dow">${d}</div>`).join('');
  const firstPad = mondayIndex(CAL_YEAR, meta.m, 1);
  for (let i = 0; i < firstPad; i++) html += `<div class="cal-cell empty"></div>`;

  const nDays = daysInMonth(CAL_YEAR, meta.m);
  for (let d = 1; d <= nDays; d++) {
    const classes = ['cal-cell'];
    let tag = '';
    const isPlay = meta.play[d];
    const isExcl = meta.excluded[d];
    const isWarn = meta.warn[d];
    const isPo = meta.playoff[d];

    // Prioridad visual: playoff > excluido > warn > play
    if (isPo) {
      classes.push('playoff');
      tag = isPo;
    } else if (isExcl && !isPlay) {
      classes.push('excluded');
      tag = isExcl;
    } else if (isPlay && isWarn) {
      classes.push('play', 'warn');
      tag = `${isPlay} · ${isWarn}`;
    } else if (isPlay && isExcl) {
      classes.push('excluded');
      tag = `${isExcl} (no juega)`;
    } else if (isPlay) {
      classes.push('play');
      tag = isPlay;
    } else if (isWarn) {
      classes.push('warn');
      tag = isWarn;
    } else if (isExcl) {
      classes.push('excluded');
      tag = isExcl;
    }

    html += `<div class="${classes.join(' ')}"><span class="num">${d}</span>` +
      (tag ? `<span class="tag-day">${tag}</span>` : '') +
      `</div>`;
  }
  grid.innerHTML = html;
}

(function initCal() {
  const tabs = document.getElementById('cal-tabs');
  CAL_MONTHS.forEach((meta, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('role', 'tab');
    b.dataset.fase = meta.fase;
    b.innerHTML = `<span class="fase-dot"></span>${meta.label}`;
    b.addEventListener('click', () => {
      tabs.querySelectorAll('button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      history.replaceState(null, null, `#calendario-m${meta.m}`);
      renderCalMonth(i);
    });
    tabs.appendChild(b);
  });
  let start = 0;
  const h = window.location.hash;
  if (h && h.startsWith('#calendario-m')) {
    const mm = parseInt(h.replace('#calendario-m', ''), 10);
    const found = CAL_MONTHS.findIndex(x => x.m === mm);
    if (found >= 0) start = found;
  }
  tabs.children[start].classList.add('active');
  renderCalMonth(start);
})();

const DATA = __DATA_JS__;
const COLORS = DATA.colores_region;
const REGION_ORDER = ['CENTRO', 'NORTE', 'OESTE', 'SUR'];
const STANDINGS = __STANDINGS_JS__;

/* —— Niveles: tabs + mocks gráficos —— */
const NIVELES_FMT = [
  {
    id: 1,
    tab: 'Nivel 1',
    tabSub: 'Interregional',
    titulo: 'Nivel 1 · Super 32',
    sub: 'Interregional · 32 equipos · 4 zonas de 8 · 14 partidos ida y vuelta',
    tipo: 'inter',
    kpis: [
      ['32', 'equipos'],
      ['4 × 8', 'zonas'],
      ['20', 'plazas LFF (F1)'],
      ['16', 'a playoff (F2)'],
    ],
    flow: [
      ['up', 'Entran', '8 ascendidos desde Nivel 2 (Fase 2)'],
      ['stay', 'Permanecen', 'Top 6 de cada zona (por tira)'],
      ['down', 'Descienden', 'Últimos 2 de cada zona → Nivel 2 (−8)'],
    ],
    fase1: {
      title: 'Fase 1',
      bullets: [
        '4 zonas · 8 equipos · 14 fechas (ida y vuelta)',
        'LFF por categoría: top 5 de cada zona (U11–U21) → 20 plazas',
        'Descenso por tira: últimos 2 de cada grupo (−8 a Nivel 2)',
      ],
      lffRows: 5,
      descRows: 2,
      poRows: 0,
    },
    fase2: {
      title: 'Fase 2',
      bullets: [
        'Reagrupación: no se repiten rivales de Fase 1 en el mismo grupo',
        'Ingresan 8 ascendidos de Nivel 2',
        'Playoff por categoría: top 4 de cada grupo',
        'Descenso por tira: últimos 2 de cada zona (−8 a Nivel 2)',
      ],
      lffRows: 0,
      descRows: 2,
      poRows: 4,
    },
    zonas: ['Zona A', 'Zona B', 'Zona C', 'Zona D'],
    bracket: 'inter',
  },
  {
    id: 2,
    tab: 'Nivel 2',
    tabSub: 'Interregional',
    titulo: 'Nivel 2 · Interregional',
    sub: '32 equipos · 4 zonas de 8 · 14 partidos ida y vuelta',
    tipo: 'inter',
    kpis: [
      ['32', 'equipos'],
      ['4 × 8', 'zonas'],
      ['8', 'plazas LFF (F1)'],
      ['16', 'a playoff (F2)'],
    ],
    flow: [
      ['up', 'Entran / ascienden', '8 desde N3 + 8 desde N1 (descenso)'],
      ['stay', 'Permanecen', 'Mitad de tabla por tira'],
      ['down', 'Descienden', 'Últimos 2/zona → Nivel 3 (−8)'],
    ],
    fase1: {
      title: 'Fase 1',
      bullets: [
        '4 zonas · 8 equipos · 14 fechas',
        'LFF por categoría: top 2 de cada grupo → 8 plazas',
        'Descenso por tira: últimos 2/grupo → Nivel 3',
      ],
      lffRows: 2,
      descRows: 2,
      poRows: 0,
    },
    fase2: {
      title: 'Fase 2',
      bullets: [
        'Sin repetir rivales de Fase 1 en el mismo grupo',
        'Ingresan 8 ascendidos de Nivel 3',
        'Playoff: top 4 por categoría por grupo',
        'Descenso: últimos 2/zona → Nivel 3',
      ],
      lffRows: 0,
      descRows: 2,
      poRows: 4,
    },
    zonas: ['Zona A', 'Zona B', 'Zona C', 'Zona D'],
    bracket: 'inter',
  },
  {
    id: 3,
    tab: 'Nivel 3',
    tabSub: 'Regional',
    titulo: 'Nivel 3 · Regional',
    sub: '4 regiones × 8 · cupo 32 · re-regionalización si hay descendidos interregionales',
    tipo: 'regional',
    kpis: [
      ['32', 'equipos'],
      ['4 × 8', 'regiones'],
      ['4', 'plazas LFF (F1)'],
      ['FF', 'Final Four'],
    ],
    flow: [
      ['up', 'Ascenso', '1° y 2° por tira → Nivel 2'],
      ['stay', 'Mantienen', '3°, 4° y 5°'],
      ['down', 'Descenso', '6°, 7° y 8° → Nivel 4'],
    ],
    fase1: {
      title: 'Fase 1',
      bullets: [
        'Regiones Norte · Oeste · Centro · Sur',
        '14 partidos ida y vuelta por región',
        'LFF: 1° por categoría de cada región (4 equipos)',
      ],
      lffRows: 1,
      descRows: 3,
      poRows: 0,
      ascRows: 2,
    },
    fase2: {
      title: 'Fase 2',
      bullets: [
        '14 fechas por región',
        'Playoff regional: top 4 por categoría',
        'Final Four: campeones de las 4 regiones → campeón Nivel 3',
      ],
      lffRows: 0,
      descRows: 3,
      poRows: 4,
      ascRows: 2,
    },
    zonas: ['Norte', 'Oeste', 'Centro', 'Sur'],
    bracket: 'ff',
  },
  {
    id: 4,
    tab: 'Nivel 4',
    tabSub: 'Regional',
    titulo: 'Nivel 4 · Regional',
    sub: '4 regiones × 8 · cupo 32',
    tipo: 'regional',
    kpis: [['32', 'equipos'], ['4 × 8', 'regiones'], ['Playoff', 'regional'], ['FF', 'Final Four']],
    flow: [
      ['up', 'Ascenso', '1°, 2° y 3° por tira → Nivel 3'],
      ['stay', 'Mantienen', '4° y 5°'],
      ['down', 'Descenso', '6°, 7° y 8° → Nivel 5'],
    ],
    fase1: {
      title: 'Fase 1',
      bullets: ['8 por región · 14 fechas', 'Movilidad por tira al cierre'],
      lffRows: 0, descRows: 3, poRows: 0, ascRows: 3,
    },
    fase2: {
      title: 'Fase 2',
      bullets: ['Playoff regional top 4 por categoría', 'Final Four de campeones regionales'],
      lffRows: 0, descRows: 3, poRows: 4, ascRows: 3,
    },
    zonas: ['Norte', 'Oeste', 'Centro', 'Sur'],
    bracket: 'ff',
  },
  {
    id: 5,
    tab: 'Nivel 5',
    tabSub: 'Regional',
    titulo: 'Nivel 5 · Regional',
    sub: '4 regiones × 8 · cupo 32',
    tipo: 'regional',
    kpis: [['32', 'equipos'], ['4 × 8', 'regiones'], ['Playoff', 'regional'], ['FF', 'Final Four']],
    flow: [
      ['up', 'Ascenso', '1°, 2° y 3° → Nivel 4'],
      ['stay', 'Mantienen', '4° y 5°'],
      ['down', 'Descenso', '6°, 7° y 8° → Nivel 6'],
    ],
    fase1: {
      title: 'Fase 1',
      bullets: ['8 por región · 14 fechas', 'Movilidad por tira'],
      lffRows: 0, descRows: 3, poRows: 0, ascRows: 3,
    },
    fase2: {
      title: 'Fase 2',
      bullets: ['Playoff regional + Final Four'],
      lffRows: 0, descRows: 3, poRows: 4, ascRows: 3,
    },
    zonas: ['Norte', 'Oeste', 'Centro', 'Sur'],
    bracket: 'ff',
  },
  {
    id: 6,
    tab: 'Nivel 6',
    tabSub: 'Regional',
    titulo: 'Nivel 6 · Regional',
    sub: 'Piso del sistema · remanente (objetivo 8/región; cupo actual según plantel)',
    tipo: 'regional',
    kpis: [['Piso', 'sin descenso'], ['4 reg.', 'regiones'], ['Playoff', 'regional'], ['FF', 'Final Four']],
    flow: [
      ['up', 'Ascenso', '1°, 2° y 3° por tira → Nivel 5'],
      ['stay', 'Mantienen', '4° a 8°'],
      ['stay', 'Sin descenso', 'Último nivel del esquema'],
    ],
    fase1: {
      title: 'Fase 1',
      bullets: ['Formato regional · 14 fechas', 'Sin descenso de nivel'],
      lffRows: 0, descRows: 0, poRows: 0, ascRows: 3,
    },
    fase2: {
      title: 'Fase 2',
      bullets: ['Playoff regional top 4 por categoría', 'Final Four → campeón Nivel 6'],
      lffRows: 0, descRows: 0, poRows: 4, ascRows: 3,
    },
    zonas: ['Norte', 'Oeste', 'Centro', 'Sur'],
    bracket: 'ff',
  },
];

const MOCK_CLUBS = [
  'Atenas Mock', 'Belgrano Mock', 'Central Mock', 'Defensores Mock',
  'Estudiantes Mock', 'Ferro Mock', 'Gimnasia Mock', 'Huracán Mock',
];

function mockRows(faseCfg, modo) {
  // modo: 'categoria' → LFF / PO · 'tira' → ASC / DESC
  const rows = [];
  const porCat = modo === 'categoria';
  for (let i = 0; i < 8; i++) {
    const pos = i + 1;
    let mark = '';
    let cls = '';
    if (porCat) {
      if (faseCfg.lffRows && pos <= faseCfg.lffRows) {
        mark = 'LFF';
        cls = 'lff';
      } else if (faseCfg.poRows && pos <= faseCfg.poRows) {
        mark = 'PO';
        cls = 'po';
      }
    } else {
      if (faseCfg.descRows && pos > 8 - faseCfg.descRows) {
        mark = 'DESC';
        cls = 'desc';
      } else if (faseCfg.ascRows && pos <= faseCfg.ascRows) {
        mark = 'ASC';
        cls = 'asc';
      }
    }
    const pts = 28 - i * 2 - (i % 2);
    const pj = 14;
    const pg = Math.max(2, 12 - i);
    rows.push({ pos, club: MOCK_CLUBS[i], pts, pj, pg, mark, cls });
  }
  return rows;
}

function htmlMockTable(faseCfg, zonaLabel, modo) {
  const rows = mockRows(faseCfg, modo);
  const body = rows.map(r => {
    const chip = r.mark
      ? `<span class="chip-r ${r.mark === 'DESC' ? 'desc' : (r.mark === 'PO' ? 'po' : (r.mark === 'ASC' ? 'asc' : 'lff'))}">${r.mark}</span>`
      : '';
    return `<tr class="${r.cls}">
      <td class="pos">${r.pos}</td>
      <td class="club">${r.club}${chip}</td>
      <td class="num">${r.pj}</td>
      <td class="num">${r.pg}</td>
      <td class="num"><strong>${r.pts}</strong></td>
    </tr>`;
  }).join('');
  const modoLabel = modo === 'categoria' ? 'por categoría' : 'por tira';
  const nota = modo === 'categoria'
    ? 'Mock ilustrativo: marcas LFF / playoff (clasificación por categoría).'
    : 'Mock ilustrativo: marcas ASC / DESC (movilidad de nivel por tira).';
  return `
    <div class="mock-table-wrap">
      <table class="mock">
        <thead>
          <tr>
            <th>#</th>
            <th>${zonaLabel} · mock ${modoLabel}</th>
            <th class="num">PJ</th>
            <th class="num">PG</th>
            <th class="num">Pts</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
    <p class="mock-note">${nota}</p>`;
}

function mediaMixtoClub(e, mixScheme) {
  if (mixScheme === 'NC_OS') {
    if (e.region === 'NORTE' || e.region === 'CENTRO') return e.media_norte_centro;
    if (e.region === 'OESTE' || e.region === 'SUR') return e.media_oeste_sur;
  } else {
    if (e.region === 'NORTE' || e.region === 'OESTE') return e.media_norte_oeste;
    if (e.region === 'CENTRO' || e.region === 'SUR') return e.media_centro_sur;
  }
  return e.media_mixta;
}

function htmlClubsTable(dn, mixScheme) {
  const rows = (dn.equipos || []).map(e => {
    const color = COLORS[e.region] || '#64748b';
    const g = mixScheme === 'NC_OS' ? (e.grupo_mixto_alt || '—') : (e.grupo_mixto || '—');
    const st = e.status_2027 || '';
    let badge = '—';
    if (st === 'ASCIENDE') badge = '<span class="chip-r asc">ASC</span>';
    else if (st === 'DESCIENDE') badge = '<span class="chip-r desc">DESC</span>';
    else if (st === 'MANTIENE') badge = '<span class="chip-r keep">=</span>';
    const cerca = e.dist_corta == null
      ? '—'
      : `${e.mas_corta || '—'} <span class="num">(${fmtKm(e.dist_corta)})</span>`;
    const lejos = e.dist_lejana == null
      ? '—'
      : `${e.mas_lejana || '—'} <span class="num">(${fmtKm(e.dist_lejana)})</span>`;
    return `<tr>
      <td class="pos">${e.pos}</td>
      <td class="club">${e.equipo} ${badge}</td>
      <td class="region" style="color:${color}">${e.region}</td>
      <td>${g}</td>
      <td class="num">${fmtKm(e.media_regionalizado)}</td>
      <td class="num">${fmtKm(mediaMixtoClub(e, mixScheme))}</td>
      <td class="num">${fmtKm(e.media_sin_region)}</td>
      <td>${cerca}</td>
      <td>${lejos}</td>
    </tr>`;
  }).join('');
  return `
    <div class="mock-table-wrap" style="max-height:420px;overflow:auto">
      <table class="mock">
        <thead>
          <tr>
            <th>#</th><th>Equipo (proyección 2027)</th><th>Región</th>
            <th>Grupo mixto</th>
            <th class="num">Media región</th>
            <th class="num">Media grupo mixto</th>
            <th class="num">Sin regionalizar</th>
            <th>Más cerca</th>
            <th>Más lejos</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function htmlBracketInter() {
  const of = [
    ['1A', '4B'], ['2A', '3B'], ['1B', '4A'], ['2B', '3A'],
    ['1C', '4D'], ['2C', '3D'], ['1D', '4C'], ['2D', '3C'],
  ];
  const ofHtml = of.map((p, i) => `
    <div class="bk-match">
      <div class="rnd">OF${i + 1}</div>
      <div class="side"><span class="seed">${p[0]}</span><span class="vs">vs</span><span class="seed">${p[1]}</span></div>
    </div>`).join('');
  const cf = [1, 2, 3, 4].map(i => `
    <div class="bk-match">
      <div class="rnd">CF${i}</div>
      <div class="side"><span class="seed">G-OF${i * 2 - 1}</span><span class="vs">vs</span><span class="seed">G-OF${i * 2}</span></div>
    </div>`).join('');
  return `
    <div class="nv-bracket-wrap">
      <h4>Playoff interregional (por categoría) · mock</h4>
      <div class="bracket-tree">
        <div class="bracket-col">${ofHtml}</div>
        <div class="bracket-col">${cf}</div>
        <div class="bracket-col sf">
          <div class="bk-match"><div class="rnd">SF1</div><div class="side"><span class="seed">G-CF1</span><span class="vs">vs</span><span class="seed">G-CF2</span></div></div>
          <div class="bk-match"><div class="rnd">SF2</div><div class="side"><span class="seed">G-CF3</span><span class="vs">vs</span><span class="seed">G-CF4</span></div></div>
        </div>
        <div class="bracket-col fi">
          <div class="bk-match"><div class="rnd">Final</div><div class="side"><span class="seed">G-SF1</span><span class="vs">vs</span><span class="seed">G-SF2</span></div></div>
        </div>
      </div>
    </div>`;
}

function htmlBracketFF() {
  const regs = ['Norte', 'Oeste', 'Centro', 'Sur'];
  const semis = regs.map(r => `
    <div class="bk-region">
      <h5>${r}</h5>
      <div class="bk-match">
        <div class="rnd">Semis regionales</div>
        <div class="side"><span class="seed">1°</span><span class="vs">vs</span><span class="seed">4°</span></div>
        <div class="side"><span class="seed">2°</span><span class="vs">vs</span><span class="seed">3°</span></div>
      </div>
      <div class="bk-match" style="margin-top:8px">
        <div class="rnd">Final regional</div>
        <div class="side"><span class="seed">G-SF1</span><span class="vs">vs</span><span class="seed">G-SF2</span></div>
      </div>
    </div>`).join('');
  return `
    <div class="nv-bracket-wrap">
      <h4>Playoffs regionales + Final Four · mock</h4>
      <div class="bracket-ff" style="grid-template-columns:repeat(4,1fr)">${semis}</div>
      <div class="bk-match" style="margin-top:12px;max-width:420px">
        <div class="rnd">Final Four · campeones de región</div>
        <div class="side"><span class="seed">Norte</span><span class="vs">vs</span><span class="seed">Oeste</span></div>
        <div class="side"><span class="seed">Centro</span><span class="vs">vs</span><span class="seed">Sur</span></div>
        <div class="side" style="margin-top:6px;border-top:1px solid #e2e8f0;padding-top:6px">
          <span class="seed">Final</span><span class="vs">→</span><span class="seed">Campeón del nivel</span>
        </div>
      </div>
    </div>`;
}

function fmtKm(v) {
  return (v === null || v === undefined) ? '—' : Number(v).toFixed(1);
}

function dataNivel(id) {
  return DATA.niveles.find(n => n.id === id) || null;
}

function htmlDistStats(dn, mixScheme) {
  const s = dn.stats || {};
  const por = s.media_por_region || {};
  let html = `
    <div class="nv-medias">
      <div class="stat"><b>${fmtKm(por.NORTE)} km</b><span>media Norte</span></div>
      <div class="stat"><b>${fmtKm(por.OESTE)} km</b><span>media Oeste</span></div>
      <div class="stat"><b>${fmtKm(por.CENTRO)} km</b><span>media Centro</span></div>
      <div class="stat"><b>${fmtKm(por.SUR)} km</b><span>media Sur</span></div>
      <div class="stat"><b>${fmtKm(s.media_sin_region_nivel)} km</b><span>media sin regionalizar</span></div>
    </div>`;
  if (mixScheme === 'NO_CS') {
    html += `
    <div class="nv-medias">
      <div class="stat"><b>${fmtKm(s.media_norte_oeste_nivel)} km</b><span>mixta Norte–Oeste (${s.n_norte_oeste || 0})</span></div>
      <div class="stat"><b>${fmtKm(s.media_centro_sur_nivel)} km</b><span>mixta Centro–Sur (${s.n_centro_sur || 0})</span></div>
    </div>`;
  } else {
    html += `
    <div class="nv-medias">
      <div class="stat"><b>${fmtKm(s.media_norte_centro_nivel)} km</b><span>mixta Norte–Centro (${s.n_norte_centro || 0})</span></div>
      <div class="stat"><b>${fmtKm(s.media_oeste_sur_nivel)} km</b><span>mixta Oeste–Sur (${s.n_oeste_sur || 0})</span></div>
    </div>`;
  }
  return html;
}

function renderNvMap(equipos, mixScheme) {
  if (window._nvMap) {
    try { window._nvMap.remove(); } catch (e) {}
    window._nvMap = null;
  }
  const el = document.getElementById('nv-map');
  if (!el) return;
  const map = L.map(el, { scrollWheelZoom: false }).setView([-34.62, -58.45], 10);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 18,
    attribution: 'Tiles &copy; Esri'
  }).addTo(map);
  const layer = L.layerGroup().addTo(map);
  const bounds = [];
  for (const e of equipos) {
    if (e.lat == null || e.lon == null) continue;
    const color = COLORS[e.region] || '#64748b';
    const mk = L.circleMarker([e.lat, e.lon], {
      radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.92
    }).addTo(layer);
    const g = mixScheme === 'NC_OS' ? (e.grupo_mixto_alt || '') : (e.grupo_mixto || '');
    mk.bindPopup(
      `<strong>${e.equipo}</strong><br>${e.region}${g ? ' · ' + g : ''}<br>` +
      `<small>Media región ${fmtKm(e.media_regionalizado)} km · sin reg. ${fmtKm(e.media_sin_region)} km</small>`
    );
    bounds.push([e.lat, e.lon]);
  }
  if (bounds.length) map.fitBounds(bounds, { padding: [28, 28] });
  setTimeout(() => map.invalidateSize(), 120);
  window._nvMap = map;
}

function htmlStandingsTable(faseKey, zonaKey) {
  const zonas = (STANDINGS.tablas && STANDINGS.tablas[faseKey]) || {};
  const filas = zonas[zonaKey] || [];
  const label = (STANDINGS.fase_labels && STANDINGS.fase_labels[faseKey]) || faseKey;
  const mov = STANDINGS.movilidad || {};
  const body = filas.map(f => {
    const eq = f.equipo || '';
    const info = mov[eq] || null;
    let badge = '';
    if (info) {
      const st = info.status || '';
      const title = (info.detalle || st).replace(/"/g, '&quot;');
      if (st === 'ASCIENDE') badge = ` <span class="chip-r asc" title="${title}">ASC → N${info.nivel_2027 ?? ''}</span>`;
      else if (st === 'DESCIENDE') badge = ` <span class="chip-r desc" title="${title}">DESC → N${info.nivel_2027 ?? ''}</span>`;
      else if (st === 'MANTIENE') badge = ` <span class="chip-r keep" title="${title}">N${info.nivel_2027 ?? '='}</span>`;
    }
    return `<tr>
    <td class="pos">${f.pos ?? ''}</td>
    <td class="club">${eq}${badge}</td>
    <td class="num">${f.pj ?? '—'}</td>
    <td class="num">${f.g ?? '—'}</td>
    <td class="num">${f.p ?? '—'}</td>
    <td class="num">${f.pts_g ?? '—'}</td>
    <td class="num">${f.pts_pres ?? '—'}</td>
    <td class="num"><strong>${f.pts ?? '—'}</strong></td>
  </tr>`;
  }).join('');
  return `
    <div class="st-meta">${label} · ${zonaKey} · ${filas.length} equipos${STANDINGS.fecha ? ' · act. ' + STANDINGS.fecha : ''}
      · <span class="chip-r asc">ASC</span> asciende · <span class="chip-r desc">DESC</span> desciende · <span class="chip-r keep">N#</span> mantiene (proy. 2027)
    </div>
    <div class="mock-table-wrap" style="max-height:480px;overflow:auto">
      <table class="mock">
        <thead>
          <tr>
            <th>#</th><th>Equipo</th>
            <th class="num">PJ</th><th class="num">G</th><th class="num">P</th>
            <th class="num">Pts cat.</th><th class="num">Pres.</th><th class="num">Pts tira</th>
          </tr>
        </thead>
        <tbody>${body || '<tr><td colspan="8">Sin filas</td></tr>'}</tbody>
      </table>
    </div>`;
}

function bindStandingsZoneTabs(containerId, tableId, faseKey, preferredZona) {
  const zonas = Object.keys((STANDINGS.tablas && STANDINGS.tablas[faseKey]) || {});
  const box = document.getElementById(containerId);
  const tableWrap = document.getElementById(tableId);
  if (!box || !tableWrap || !zonas.length) return;
  let zona = preferredZona && zonas.includes(preferredZona) ? preferredZona : zonas[0];
  const paint = () => {
    box.innerHTML = zonas.map(z =>
      `<button type="button" class="${z === zona ? 'active' : ''}" data-z="${z}">${z}</button>`
    ).join('');
    tableWrap.innerHTML = htmlStandingsTable(faseKey, zona);
    box.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => { zona = btn.dataset.z; paint(); };
    });
  };
  paint();
}

function renderNivelFmt(idx, zonaIdx) {
  const n = NIVELES_FMT[idx];
  const zi = zonaIdx == null ? 0 : zonaIdx;
  const zona = n.zonas[zi];
  const faseActiva = window.__nvFase || 1;
  const mixScheme = window.__nvMix || 'NO_CS';
  const cupoModo = window.__nvCupo || 'categoria';
  const faseCfg = faseActiva === 1 ? n.fase1 : n.fase2;
  const dn = dataNivel(n.id);

  const kpis = n.kpis.map(([a, b]) => `<div class="nv-kpi"><b>${a}</b><span>${b}</span></div>`).join('');
  const flow = n.flow.map(([cls, t, d]) => `<div class="step ${cls}"><b>${t}</b>${d}</div>`).join('');
  const f1li = n.fase1.bullets.map(x => `<li>${x}</li>`).join('');
  const f2li = n.fase2.bullets.map(x => `<li>${x}</li>`).join('');
  const zoneTabs = n.zonas.map((z, i) =>
    `<button type="button" class="${i === zi ? 'active' : ''}" data-z="${i}">${z}</button>`
  ).join('');
  const bracket = n.bracket === 'inter' ? htmlBracketInter() : htmlBracketFF();

  const mapBlock = dn ? `
    <div class="nv-map-block">
      <h4>Mapa de equipos · ${dn.nombre}</h4>
      <div class="legend" style="margin-bottom:10px">
        <span><i class="dot" style="background:${COLORS.CENTRO}"></i>Centro</span>
        <span><i class="dot" style="background:${COLORS.NORTE}"></i>Norte</span>
        <span><i class="dot" style="background:${COLORS.SUR}"></i>Sur</span>
        <span><i class="dot" style="background:${COLORS.OESTE}"></i>Oeste</span>
      </div>
      <div class="nv-mix-toggle">
        <strong>Media mixta:</strong>
        <button type="button" class="chip ${mixScheme === 'NO_CS' ? 'active' : ''}" id="nv-mix-nocs">Norte–Oeste | Centro–Sur</button>
        <button type="button" class="chip ${mixScheme === 'NC_OS' ? 'active' : ''}" id="nv-mix-ncos">Norte–Centro | Oeste–Sur</button>
      </div>
      ${htmlDistStats(dn, mixScheme)}
      <div id="nv-map"></div>
      <h4 style="margin-top:16px">Proyección de distancias</h4>
      ${htmlClubsTable(dn, mixScheme)}
    </div>` : '';

  document.getElementById('nv-content').innerHTML = `
    <div class="nv-panel active">
      <div class="nv-hero">
        <div>
          <h3>${n.titulo}</h3>
          <p class="sub">${n.sub}</p>
        </div>
      </div>
      <div class="nv-kpis">${kpis}</div>
      <div class="nv-flow">${flow}</div>
      <div class="nv-phases">
        <div class="nv-phase">
          <h4><span class="badge-fase">Fase 1</span> ${n.fase1.title}</h4>
          <ul>${f1li}</ul>
        </div>
        <div class="nv-phase">
          <h4><span class="badge-fase f2">Fase 2</span> ${n.fase2.title}</h4>
          <ul>${f2li}</ul>
        </div>
      </div>
      ${mapBlock}
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:16px 0 10px">
        <strong style="font-size:13px">Esquema de cupos (mock por zona)</strong>
        <button type="button" class="chip ${faseActiva === 1 ? 'active' : ''}" id="nv-f1">Fase 1</button>
        <button type="button" class="chip ${faseActiva === 2 ? 'active' : ''}" id="nv-f2">Fase 2</button>
        <span style="width:1px;height:18px;background:#cbd5e1;margin:0 4px"></span>
        <button type="button" class="chip ${cupoModo === 'categoria' ? 'active' : ''}" id="nv-cupo-cat">Por categoría (LFF / PO)</button>
        <button type="button" class="chip ${cupoModo === 'tira' ? 'active' : ''}" id="nv-cupo-tira">Por tira (ASC / DESC)</button>
      </div>
      <div class="nv-zone-tabs" id="nv-zones">${zoneTabs}</div>
      ${htmlMockTable(faseCfg, zona, cupoModo)}
      ${bracket}
    </div>`;

  document.getElementById('nv-f1').onclick = () => { window.__nvFase = 1; renderNivelFmt(idx, zi); };
  document.getElementById('nv-f2').onclick = () => { window.__nvFase = 2; renderNivelFmt(idx, zi); };
  document.getElementById('nv-cupo-cat').onclick = () => { window.__nvCupo = 'categoria'; renderNivelFmt(idx, zi); };
  document.getElementById('nv-cupo-tira').onclick = () => { window.__nvCupo = 'tira'; renderNivelFmt(idx, zi); };
  document.querySelectorAll('#nv-zones button').forEach(btn => {
    btn.onclick = () => renderNivelFmt(idx, parseInt(btn.dataset.z, 10));
  });
  const mixA = document.getElementById('nv-mix-nocs');
  const mixB = document.getElementById('nv-mix-ncos');
  if (mixA) mixA.onclick = () => { window.__nvMix = 'NO_CS'; renderNivelFmt(idx, zi); };
  if (mixB) mixB.onclick = () => { window.__nvMix = 'NC_OS'; renderNivelFmt(idx, zi); };
  if (dn) renderNvMap(dn.equipos || [], mixScheme);
}

(function initStandingsGlobal() {
  const fechaEl = document.getElementById('st-fecha');
  if (fechaEl) fechaEl.textContent = STANDINGS.fecha || '—';
  const tabs = document.getElementById('st-fase-tabs');
  if (!tabs) return;
  const fases = Object.keys(STANDINGS.tablas || {});
  let fase = fases[0];
  const paint = () => {
    tabs.innerHTML = fases.map(f => {
      const lab = (STANDINGS.fase_labels && STANDINGS.fase_labels[f]) || f;
      return `<button type="button" class="${f === fase ? 'active' : ''}" data-f="${f}">${lab}</button>`;
    }).join('');
    tabs.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => { fase = btn.dataset.f; paint(); };
    });
    bindStandingsZoneTabs('st-zona-tabs', 'st-tabla-wrap', fase, null);
  };
  if (fases.length) paint();
})();

(function initNiveles() {
  const tabs = document.getElementById('nv-tabs');
  window.__nvFase = 1;
  window.__nvMix = 'NO_CS';
  NIVELES_FMT.forEach((n, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('role', 'tab');
    b.innerHTML = `${n.tab}<small>${n.tabSub}</small>`;
    b.addEventListener('click', () => {
      tabs.querySelectorAll('button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      window.__nvFase = 1;
      history.replaceState(null, null, `#nivel-${n.id}`);
      renderNivelFmt(i, 0);
    });
    tabs.appendChild(b);
  });
  let start = 0;
  const h = window.location.hash;
  if (h && h.startsWith('#nivel-')) {
    const nid = parseInt(h.replace('#nivel-', ''), 10);
    const found = NIVELES_FMT.findIndex(x => x.id === nid);
    if (found >= 0) start = found;
  }
  tabs.children[start].classList.add('active');
  renderNivelFmt(start, 0);
})();

</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera landing Formativas 2027")
    ap.add_argument("--recalcular", action="store_true", help="Recalcula payload de viajes")
    ap.add_argument("--output", type=Path, default=OUT_HTML)
    args = ap.parse_args()
    payload = _cargar_payload(recalcular=args.recalcular)
    path = generar(payload, args.output)
    print(f"Landing: {path}")
    print(f"Equipos en payload: {payload.get('total_equipos')}")
    for n in payload["niveles"]:
        print(f"  {n['nombre']}: {n['n_equipos']} equipos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
