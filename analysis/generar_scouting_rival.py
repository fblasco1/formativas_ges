# -*- coding: utf-8 -*-
"""
Hoja de scouting de rival (Formativas FeBAMBA).

Seleccionar equipo (+ categoría) → top 3 por rubro (3P, RO, RD, REC, AST, 2P),
vista de equipo (métricas + radar vs media) y perfil de jugador (foto, stats,
descripción, radar).

  .venv\\Scripts\\python.exe analysis/generar_scouting_rival.py --desde-cache
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Evitar analysis/__init__.py (sqlalchemy) al importar submódulos.
import types

if "analysis" not in sys.modules:
    _analysis = types.ModuleType("analysis")
    _analysis.__path__ = [str(ROOT / "analysis")]  # type: ignore[attr-defined]
    sys.modules["analysis"] = _analysis

from analysis.buscador_jugadores_destacados import (  # noqa: E402
    BOX_FULL_CACHE,
    FICHA_CACHE,
    OUT_DIR,
    agregar_jugadores,
)
from analysis.buscador_metrics import (  # noqa: E402
    MIN_PJ_CLUSTER,
    PERFIL_DESCRIPCIONES,
    PERFIL_INSUFICIENTE,
    enriquecer_jugadores,
)
from analysis.scouting_equipo_stats import (  # noqa: E402
    clave_equipo,
    construir_partidos_equipo,
    mapa_display_equipos,
    promediar_avanzadas,
    serializar_partido,
)

OUT_HTML = OUT_DIR / "scouting_rival.html"
DOCS_HTML = ROOT / "docs" / "scouting_rival.html"
PARTIDOS_CACHE = OUT_DIR / "partidos.json"

RUBROS: Tuple[Tuple[str, str, str], ...] = (
    ("t3a_p", "3P", "Triples anotados / partido"),
    ("rebof_p", "RO", "Rebotes ofensivos / partido"),
    ("rebdef_p", "RD", "Rebotes defensivos / partido"),
    ("rob_p", "REC", "Recuperaciones / partido"),
    ("ast_p", "AST", "Asistencias / partido"),
    ("t2a_p", "2P", "Dobles anotados / partido"),
)

RADAR_KEYS: Tuple[Tuple[str, str], ...] = (
    ("pts_p", "PTS"),
    ("t3a_p", "3P"),
    ("t2a_p", "2P"),
    ("rebof_p", "RO"),
    ("rebdef_p", "RD"),
    ("ast_p", "AST"),
    ("rob_p", "REC"),
    ("val_p", "VAL"),
)

MIN_PJ_TOP = 3
TOP_N = 3
LAST_N = 5
FOTO_BASE = "https://argentina.basketball/fotos/"

# Claves de promedios de plantel (radar) + labels de medias de competencia (equipo).
TEAM_METRIC_KEYS: Tuple[Tuple[str, str], ...] = (
    ("pts", "PTS"),
    ("t3a", "3P"),
    ("t2a", "2P"),
    ("ro", "RO"),
    ("rd", "RD"),
    ("ast", "AST"),
    ("rec", "REC"),
    ("val", "VAL"),
)

ADV_METRIC_KEYS: Tuple[Tuple[str, str], ...] = (
    ("poss", "POSS"),
    ("oer", "OER"),
    ("der", "DER"),
    ("efg", "eFG%"),
    ("ts", "TS%"),
    ("orb_pct", "ORB%"),
    ("drb_pct", "DRB%"),
)


def _pctile(value: float, population: Sequence[float]) -> int:
    if not population:
        return 0
    below = sum(1 for v in population if v < value)
    equal = sum(1 for v in population if v == value)
    return int(round(100.0 * (below + 0.5 * equal) / len(population)))


def describir_jugador(j: Dict[str, object]) -> str:
    """Texto corto de scouting a partir de stats y perfil."""
    perfil = str(j.get("perfil") or PERFIL_INSUFICIENTE)
    base = PERFIL_DESCRIPCIONES.get(perfil, {}).get("resumen") or ""
    bits: List[str] = []
    pj = int(j.get("pj") or 0)
    pts = float(j.get("pts_p") or 0)
    t3a = float(j.get("t3a_p") or 0)
    t3pct = float(j.get("t3_pct") or 0)
    t2a = float(j.get("t2a_p") or 0)
    t2pct = float(j.get("t2_pct") or 0)
    ro = float(j.get("rebof_p") or 0)
    rd = float(j.get("rebdef_p") or 0)
    ast = float(j.get("ast_p") or 0)
    rob = float(j.get("rob_p") or 0)
    min_p = float(j.get("min_p") or 0)

    if pts >= 12:
        bits.append(f"anota {pts:.1f} pts/p")
    elif pts >= 8:
        bits.append(f"aporta {pts:.1f} pts/p")
    if t3a >= 1.5 and t3pct >= 28:
        bits.append(f"amenaza de triple ({t3a:.1f}×3P al {t3pct:.0f}%)")
    if t2a >= 3 and t2pct >= 45:
        bits.append(f"eficiente cerca del aro ({t2a:.1f}×2P al {t2pct:.0f}%)")
    if rd >= 4 or ro >= 2:
        bits.append(f"rebotea {ro:.1f} RO / {rd:.1f} RD")
    if ast >= 2:
        bits.append(f"facilita ({ast:.1f} ast/p)")
    if rob >= 1.5:
        bits.append(f"presiona el balón ({rob:.1f} rec/p)")
    if min_p >= 25:
        bits.append(f"carga minutos ({min_p:.0f} min/p)")

    head = f"{j.get('nombre_completo') or j.get('nombre')} · {j.get('cat')} · {pj} PJ."
    mid = (" " + ". ".join(bits).capitalize() + ".") if bits else ""
    tail = f" Perfil: {perfil}. {base}" if base else f" Perfil: {perfil}."
    return (head + mid + tail).strip()


def _pack_player(j: Dict[str, object], cat_pops: Dict[str, List[float]]) -> Dict[str, object]:
    radar = []
    for key, _label in RADAR_KEYS:
        v = float(j.get(key) or 0)
        radar.append(_pctile(v, cat_pops.get(key) or []))
    return {
        "pid": j.get("pid") or "",
        "n": j.get("nombre_completo") or j.get("nombre") or "",
        "eq": j.get("equipo") or "",
        "cat": j.get("cat") or "",
        "edad": j.get("edad") if j.get("edad") != "" else None,
        "pj": int(j.get("pj") or 0),
        "min": float(j.get("min_p") or 0),
        "pts": float(j.get("pts_p") or 0),
        "t2a": float(j.get("t2a_p") or 0),
        "t2i": float(j.get("t2i_p") or 0),
        "t2p": float(j.get("t2_pct") or 0),
        "t3a": float(j.get("t3a_p") or 0),
        "t3i": float(j.get("t3i_p") or 0),
        "t3p": float(j.get("t3_pct") or 0),
        "ro": float(j.get("rebof_p") or 0),
        "rd": float(j.get("rebdef_p") or 0),
        "reb": float(j.get("reb_p") or 0),
        "ast": float(j.get("ast_p") or 0),
        "rec": float(j.get("rob_p") or 0),
        "tap": float(j.get("tap_p") or 0),
        "val": float(j.get("val_p") or 0),
        "ts": j.get("ts_pct") if j.get("ts_pct") != "" else None,
        "efg": j.get("efg_pct") if j.get("efg_pct") != "" else None,
        "perfil": j.get("perfil") or PERFIL_INSUFICIENTE,
        "desc": describir_jugador(j),
        "radar": radar,
        "foto": (FOTO_BASE + str(j["pid"])) if j.get("pid") else "",
        "purl": j.get("purl") or "",
    }


def _top3(
    pool: List[Dict[str, object]], key: str
) -> List[Dict[str, object]]:
    elegibles = [j for j in pool if int(j.get("pj") or 0) >= MIN_PJ_TOP]
    elegibles.sort(key=lambda j: (-float(j.get(key) or 0), -int(j.get("pj") or 0)))
    return elegibles[:TOP_N]


def _team_averages(pool: List[Dict[str, object]]) -> Dict[str, float]:
    if not pool:
        return {k: 0.0 for k, _ in RADAR_KEYS}
    n = len(pool)
    out: Dict[str, float] = {}
    for key, _ in RADAR_KEYS:
        out[key] = round(sum(float(j.get(key) or 0) for j in pool) / n, 2)
    out["min_p"] = round(sum(float(j.get("min_p") or 0) for j in pool) / n, 1)
    return out


def _aplicar_nombres_canon(
    jugadores: List[Dict[str, object]], display: Dict[str, str]
) -> None:
    for j in jugadores:
        raw = str(j.get("equipo") or "")
        j["equipo"] = display.get(clave_equipo(raw), raw)


def build_payload(
    jugadores: List[Dict[str, object]],
    partidos: List[Dict[str, str]],
    boxscores: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    # Display map desde fixture + actas + agregación de jugadores.
    nombres: List[str] = []
    for p in partidos:
        nombres.append(p.get("local") or "")
        nombres.append(p.get("visitante") or "")
    for box in boxscores.values():
        for eq in box.get("equipos") or []:
            nombres.append(str(eq.get("nombre") or ""))
    for j in jugadores:
        nombres.append(str(j.get("equipo") or ""))
    display = mapa_display_equipos(nombres)
    _aplicar_nombres_canon(jugadores, display)

    games_idx = construir_partidos_equipo(partidos, boxscores, display)
    fases_por_cat: Dict[str, set] = defaultdict(set)
    for (_eq, cat), games in games_idx.items():
        for g in games:
            fase = str(g.get("fase") or "").strip()
            if fase:
                fases_por_cat[cat].add(fase)

    by_cat: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for j in jugadores:
        by_cat[str(j.get("cat") or "")].append(j)

    cat_pops: Dict[str, Dict[str, List[float]]] = {}
    cat_avg_radar: Dict[str, List[float]] = {}
    for cat, pool in by_cat.items():
        pops = {key: [float(j.get(key) or 0) for j in pool] for key, _ in RADAR_KEYS}
        cat_pops[cat] = pops
        # Referencia plana = percentil 50 (media de la distribución de jugadores).
        cat_avg_radar[cat] = [50] * len(RADAR_KEYS)

    equipos: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    players: Dict[str, Dict[str, object]] = {}

    for j in jugadores:
        pid = str(j.get("pid") or "")
        cat = str(j.get("cat") or "").strip()
        eq = str(j.get("equipo") or "").strip()
        key = f"{pid}:{cat}" if pid else f"nm:{cat}:{eq}:{j.get('nombre')}"
        packed = _pack_player(j, cat_pops.get(cat, {}))
        players[key] = packed
        if eq and cat:
            equipos[eq][cat].append(key)

    scouting: Dict[str, Dict[str, object]] = {}
    for eq, cats in equipos.items():
        scouting[eq] = {}
        for cat, keys in cats.items():
            pool = [j for j in by_cat[cat] if str(j.get("equipo") or "") == eq]
            tops: Dict[str, List[str]] = {}
            for metric, label, _hint in RUBROS:
                tops[label] = []
                for p in _top3(pool, metric):
                    ppid = str(p.get("pid") or "")
                    tops[label].append(
                        f"{ppid}:{p.get('cat')}"
                        if ppid
                        else f"nm:{p.get('cat')}:{p.get('equipo')}:{p.get('nombre')}"
                    )
            avgs = _team_averages(pool)
            team_radar = [
                _pctile(avgs[key], cat_pops[cat][key]) for key, _ in RADAR_KEYS
            ]
            games = games_idx.get((eq, cat), [])
            by_fase_games: Dict[str, List[Dict[str, object]]] = defaultdict(list)
            for g in games:
                fase = str(g.get("fase") or "").strip()
                if fase:
                    by_fase_games[fase].append(g)
            by_fase: Dict[str, Dict[str, object]] = {}
            for fase, gs in by_fase_games.items():
                season_f = promediar_avanzadas(gs)
                by_fase[fase] = {
                    "pj": season_f.get("pj") or len(gs),
                    "team": {k: season_f.get(k) for k, _ in TEAM_METRIC_KEYS},
                    "advanced": {k: season_f.get(k) for k, _ in ADV_METRIC_KEYS},
                }
            scouting[eq][cat] = {
                "n": len(pool),
                "tops": tops,
                "avg": {k: avgs[k] for k, _ in RADAR_KEYS},
                "radar": team_radar,
                "fases": sorted(by_fase.keys()),
                "by_fase": by_fase,
                "games": [serializar_partido(g) for g in games],
                "roster": keys,
            }

    return {
        "v": 3,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rubros": [{"k": k, "l": l, "h": h} for k, l, h in RUBROS],
        "radar_labels": [l for _, l in RADAR_KEYS],
        "team_metric_labels": [{"k": k, "l": l} for k, l in TEAM_METRIC_KEYS],
        "adv_metric_labels": [{"k": k, "l": l} for k, l in ADV_METRIC_KEYS],
        "cat_ref": cat_avg_radar,
        "fases_por_cat": {cat: sorted(list(fases)) for cat, fases in fases_por_cat.items()},
        "equipos": sorted(scouting.keys()),
        "scouting": scouting,
        "players": players,
    }


def _render_html(payload: Dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(raw, compresslevel=9)).decode("ascii")
    fecha = payload.get("fecha") or ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Scouting rival · Formativas FeBAMBA</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg:#e8edf5; --paper:#fff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0;
      --brand:#1d4ed8; --brand2:#0ea5e9; --ink:#0f172a; --ok:#059669; --warn:#d97706;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg);
      color:var(--text); line-height:1.45; -webkit-font-smoothing:antialiased;
    }}
    .wrap {{ max-width:1180px; margin:0 auto; padding:18px 16px 48px; }}
    .hero {{
      background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 55%,#1d4ed8 100%);
      color:#f8fafc; border-radius:18px; padding:22px 24px; margin-bottom:16px;
      box-shadow:0 18px 40px -22px rgba(30,58,138,.7);
    }}
    .hero .eyebrow {{ text-transform:uppercase; letter-spacing:.14em; font-size:11px;
      font-weight:700; color:#93c5fd; margin:0 0 8px; }}
    .hero h1 {{ margin:0 0 6px; font-size:24px; font-weight:800; letter-spacing:-.02em; }}
    .hero p {{ margin:0; color:#cbd5e1; font-size:13px; }}
    .toolbar {{
      display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end;
      background:var(--paper); border:1px solid var(--line); border-radius:14px;
      padding:14px 16px; margin-bottom:14px;
    }}
    label.fld {{ font-size:11px; color:var(--muted); display:flex; flex-direction:column; gap:4px; font-weight:600; }}
    select {{ border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:13px; min-width:220px; background:#fff; }}
    .fase-chips {{ display:flex; flex-wrap:wrap; gap:8px; max-width:560px; }}
    .fase-chip {{
      display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600;
      border:1px solid var(--line); border-radius:999px; padding:6px 12px; background:#fff;
      cursor:pointer; color:var(--text); user-select:none;
    }}
    .fase-chip:has(input:checked) {{ background:#eff6ff; border-color:var(--brand); color:var(--brand); }}
    .fase-chip input {{ margin:0; }}
    .fase-actions {{ display:flex; gap:8px; margin-top:6px; }}
    .fase-actions button {{
      border:none; background:transparent; color:var(--brand); font-size:11px;
      font-weight:700; cursor:pointer; padding:0;
    }}
    .tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }}
    .tab {{
      border:1px solid var(--line); background:#fff; border-radius:999px; padding:8px 16px;
      font-size:13px; font-weight:600; cursor:pointer; color:var(--muted);
    }}
    .tab:hover {{ border-color:var(--brand); color:var(--brand); }}
    .tab.active {{ background:var(--brand); border-color:var(--brand); color:#fff; }}
    .panel {{ display:none; }}
    .panel.active {{ display:block; }}
    .team-head {{
      display:grid; grid-template-columns:auto 1fr; gap:16px; align-items:center;
      background:var(--paper); border:1px solid var(--line); border-radius:14px;
      padding:16px 18px; margin-bottom:14px;
    }}
    .crest {{
      width:64px; height:64px; border-radius:14px; background:linear-gradient(145deg,#1e3a8a,#3b82f6);
      color:#fff; display:flex; align-items:center; justify-content:center;
      font-weight:800; font-size:20px; letter-spacing:-.02em;
    }}
    .team-head h2 {{ margin:0 0 4px; font-size:20px; }}
    .team-head .sub {{ color:var(--muted); font-size:13px; }}
    .metrics {{
      display:grid; grid-template-columns:repeat(auto-fill,minmax(90px,1fr)); gap:8px;
      margin-top:12px;
    }}
    .metric {{
      background:#f8fafc; border:1px solid var(--line); border-radius:10px; padding:8px 10px; text-align:center;
    }}
    .metric .v {{ font-size:16px; font-weight:800; letter-spacing:-.02em; }}
    .metric .l {{ font-size:10px; color:var(--muted); font-weight:700; text-transform:uppercase; letter-spacing:.04em; }}
    .metric .m {{ font-size:10px; color:#94a3b8; margin-top:2px; }}
    .metric .m b {{ color:var(--muted); font-weight:600; }}
    .pill-g {{ color:#059669; font-weight:800; }}
    .pill-p {{ color:#dc2626; font-weight:800; }}
    .tablewrap {{ overflow:auto; border:1px solid var(--line); border-radius:10px; }}
    table.games {{ width:100%; border-collapse:collapse; font-size:12px; min-width:920px; }}
    table.games th, table.games td {{ padding:7px 6px; border-bottom:1px solid var(--line); text-align:center; white-space:nowrap; }}
    table.games th {{ color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.03em; background:#f8fafc; position:sticky; top:0; }}
    table.games td.left {{ text-align:left; font-weight:600; }}
    .grid-2 {{ display:grid; grid-template-columns:1.1fr 1fr; gap:14px; margin-bottom:14px; }}
    @media (max-width:900px) {{ .grid-2 {{ grid-template-columns:1fr; }} }}
    .card {{
      background:var(--paper); border:1px solid var(--line); border-radius:14px;
      padding:16px 18px; margin-bottom:14px;
    }}
    .card h3 {{ margin:0 0 10px; font-size:15px; font-weight:700; }}
    .chart-box {{ position:relative; height:280px; }}
    .tops {{
      display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:12px;
    }}
    .top-card {{
      border:1px solid var(--line); border-radius:12px; padding:12px 14px; background:#fafbfe;
      border-top:3px solid var(--brand);
    }}
    .top-card h4 {{ margin:0 0 4px; font-size:13px; font-weight:800; }}
    .top-card .hint {{ font-size:11px; color:var(--muted); margin:0 0 10px; }}
    .top-row {{
      display:grid; grid-template-columns:28px 36px 1fr auto; gap:8px; align-items:center;
      padding:6px 0; border-bottom:1px solid var(--line); cursor:pointer;
    }}
    .top-row:last-child {{ border-bottom:none; }}
    .top-row:hover {{ background:#eff6ff; border-radius:8px; }}
    .rank {{ font-size:12px; font-weight:800; color:var(--muted); text-align:center; }}
    .av {{
      width:36px; height:36px; border-radius:50%; object-fit:cover; background:#e2e8f0;
      display:block;
    }}
    .av-fallback {{
      width:36px; height:36px; border-radius:50%; background:#1e3a8a; color:#fff;
      display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;
    }}
    .nm {{ font-size:13px; font-weight:700; }}
    .nm small {{ display:block; font-weight:500; color:var(--muted); font-size:11px; }}
    .stat {{ font-size:14px; font-weight:800; color:var(--brand); }}
    .perfil {{
      display:inline-block; font-size:10px; font-weight:700; padding:2px 8px; border-radius:999px;
      background:#eff6ff; color:var(--brand); margin-top:4px;
    }}
    .player-view {{
      display:grid; grid-template-columns:220px 1fr 1fr; gap:16px;
    }}
    @media (max-width:980px) {{ .player-view {{ grid-template-columns:1fr; }} }}
    .player-photo {{
      width:100%; aspect-ratio:3/4; object-fit:cover; border-radius:14px; background:#e2e8f0;
      border:1px solid var(--line);
    }}
    .player-photo-ph {{
      width:100%; aspect-ratio:3/4; border-radius:14px;
      background:linear-gradient(160deg,#1e3a8a,#60a5fa); color:#fff;
      display:flex; align-items:center; justify-content:center; font-size:42px; font-weight:800;
    }}
    table.stats {{ width:100%; border-collapse:collapse; font-size:13px; }}
    table.stats th, table.stats td {{ padding:7px 6px; border-bottom:1px solid var(--line); text-align:left; }}
    table.stats th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
    table.stats td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:700; }}
    .desc {{
      background:#f8faff; border-left:4px solid var(--brand); border-radius:0 10px 10px 0;
      padding:12px 14px; font-size:13px; color:#1e293b; margin:0;
    }}
    .empty {{ color:var(--muted); font-size:14px; padding:24px; text-align:center; }}
    .back {{
      border:none; background:transparent; color:var(--brand); font-weight:700; cursor:pointer;
      font-size:13px; padding:0; margin-bottom:10px;
    }}
    footer {{ text-align:center; color:var(--muted); font-size:11px; margin-top:20px; }}
    a.ext {{ color:var(--brand); font-size:12px; font-weight:600; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <p class="eyebrow">FeBAMBA · Formativas</p>
      <h1>Scouting de rival</h1>
      <p>Elegí rival, categoría y torneo(s). Las medias y la comparación se calculan solo sobre esos torneos.</p>
    </header>

    <div class="toolbar">
      <label class="fld">Equipo rival
        <select id="sel-eq"></select>
      </label>
      <label class="fld">Categoría
        <select id="sel-cat"></select>
      </label>
      <label class="fld">Torneo(s) para medias
        <div id="sel-fases" class="fase-chips"></div>
        <span class="fase-actions">
          <button type="button" id="btn-fases-all">Todos</button>
          <button type="button" id="btn-fases-none">Ninguno</button>
        </span>
      </label>
      <span id="meta" style="margin-left:auto;font-size:12px;color:#64748b"></span>
    </div>

    <div class="tabs" id="tabs">
      <button class="tab active" data-tab="resumen">Resumen equipo</button>
      <button class="tab" data-tab="destacados">Jugadores destacados</button>
      <button class="tab" data-tab="jugador">Perfil jugador</button>
    </div>

    <div id="panel-resumen" class="panel active"></div>
    <div id="panel-destacados" class="panel"></div>
    <div id="panel-jugador" class="panel"></div>

    <footer>Datos GES · generado {fecha} · <a class="ext" href="index.html">Portal</a></footer>
  </div>

  <script id="payload" type="application/gzip+json" data-encoding="base64">{b64}</script>
  <script>
(function() {{
  function gunzipB64(b64) {{
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip")))
      .json();
  }}

  const el = document.getElementById("payload");
  let DATA = null;
  let teamChart = null;
  let playerChart = null;
  let selectedPid = null;

  const initials = (name) => (name || "?")
    .split(/\\s+/).filter(Boolean).slice(0, 2).map(s => s[0]).join("").toUpperCase();

  function avatarHtml(p, cls) {{
    cls = cls || "av";
    if (p.foto) {{
      return `<img class="${{cls}}" src="${{p.foto}}" alt="" loading="lazy"
        referrerpolicy="no-referrer"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"/>
        <span class="av-fallback" style="display:none">${{initials(p.n)}}</span>`;
    }}
    return `<span class="av-fallback">${{initials(p.n)}}</span>`;
  }}

  function destroyCharts() {{
    if (teamChart) {{ teamChart.destroy(); teamChart = null; }}
    if (playerChart) {{ playerChart.destroy(); playerChart = null; }}
  }}

  function radarConfig(labelA, dataA, labelB, dataB) {{
    return {{
      type: "radar",
      data: {{
        labels: DATA.radar_labels,
        datasets: [
          {{
            label: labelA,
            data: dataA,
            borderColor: "#1d4ed8",
            backgroundColor: "rgba(29,78,216,.22)",
            pointBackgroundColor: "#1d4ed8",
            borderWidth: 2
          }},
          {{
            label: labelB,
            data: dataB,
            borderColor: "#94a3b8",
            backgroundColor: "rgba(148,163,184,.12)",
            pointBackgroundColor: "#94a3b8",
            borderWidth: 1.5
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: "bottom", labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
        scales: {{
          r: {{
            min: 0, max: 100,
            ticks: {{ display: false, stepSize: 25 }},
            grid: {{ color: "#e2e8f0" }},
            pointLabels: {{ font: {{ size: 11, weight: "600" }}, color: "#475569" }}
          }}
        }}
      }}
    }};
  }}

  function current() {{
    const eq = document.getElementById("sel-eq").value;
    const cat = document.getElementById("sel-cat").value;
    const block = (DATA.scouting[eq] || {{}})[cat];
    return {{ eq, cat, block }};
  }}

  function selectedFases() {{
    return [...document.querySelectorAll("#sel-fases input:checked")].map(i => i.value);
  }}

  function fillCats() {{
    const eq = document.getElementById("sel-eq").value;
    const cats = Object.keys(DATA.scouting[eq] || {{}}).sort();
    const sel = document.getElementById("sel-cat");
    const prev = sel.value;
    sel.innerHTML = cats.map(c => `<option value="${{c}}">${{c}}</option>`).join("");
    if (cats.includes(prev)) sel.value = prev;
    fillFases(sel.value !== prev);
  }}

  function fillFases(reset) {{
    const cat = document.getElementById("sel-cat").value;
    const prev = reset ? new Set() : new Set(selectedFases());
    const fases = (DATA.fases_por_cat && DATA.fases_por_cat[cat]) || [];
    const root = document.getElementById("sel-fases");
    const keep = prev.size ? prev : new Set(fases);
    root.innerHTML = fases.map(f => {{
      const checked = keep.has(f) ? "checked" : "";
      return `<label class="fase-chip"><input type="checkbox" value="${{f}}" ${{checked}}/> ${{f}}</label>`;
    }}).join("");
    root.querySelectorAll("input").forEach(inp => {{
      inp.addEventListener("change", refresh);
    }});
  }}

  function setTab(name) {{
    document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + name));
  }}

  function openPlayer(pid) {{
    selectedPid = pid;
    setTab("jugador");
    renderPlayer();
  }}

  function fmt(v, d) {{
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    return n.toFixed(d == null ? 1 : d);
  }}

  function pctile(value, pop) {{
    if (!pop.length || value == null) return 50;
    let below = 0, eq = 0;
    for (const v of pop) {{
      if (v < value) below++;
      else if (v === value) eq++;
    }}
    return Math.round(100 * (below + 0.5 * eq) / pop.length);
  }}

  function mergeByFases(block, fases) {{
    const keysT = (DATA.team_metric_labels || []).map(x => x.k);
    const keysA = (DATA.adv_metric_labels || []).map(x => x.k);
    let w = 0;
    const team = {{}}, adv = {{}};
    for (const f of fases) {{
      const s = (block.by_fase || {{}})[f];
      if (!s || !s.pj) continue;
      const pj = Number(s.pj) || 0;
      w += pj;
      for (const k of keysT) {{
        const v = s.team && s.team[k];
        if (v != null) team[k] = (team[k] || 0) + Number(v) * pj;
      }}
      for (const k of keysA) {{
        const v = s.advanced && s.advanced[k];
        if (v != null) adv[k] = (adv[k] || 0) + Number(v) * pj;
      }}
    }}
    const round = (obj) => {{
      const out = {{}};
      for (const k of Object.keys(obj)) out[k] = Math.round(obj[k] / w * 10) / 10;
      return out;
    }};
    if (!w) return {{ pj: 0, team: {{}}, advanced: {{}} }};
    return {{ pj: w, team: round(team), advanced: round(adv) }};
  }}

  function compForFases(cat, fases) {{
    const keysT = (DATA.team_metric_labels || []).map(x => x.k);
    const keysA = (DATA.adv_metric_labels || []).map(x => x.k);
    const rows = [];
    for (const eq of DATA.equipos) {{
      const blk = (DATA.scouting[eq] || {{}})[cat];
      if (!blk) continue;
      const m = mergeByFases(blk, fases);
      if (m.pj > 0) rows.push(m);
    }}
    const avgKeys = (keys, getter) => {{
      const out = {{}};
      for (const k of keys) {{
        const vals = rows.map(r => getter(r)[k]).filter(v => v != null);
        out[k] = vals.length ? Math.round(vals.reduce((a,b)=>a+b,0) / vals.length * 10) / 10 : null;
      }}
      return out;
    }};
    return {{
      n: rows.length,
      team: avgKeys(keysT, r => r.team),
      advanced: avgKeys(keysA, r => r.advanced),
      dist: keysT.reduce((acc, k) => {{
        acc[k] = rows.map(r => r.team[k]).filter(v => v != null);
        return acc;
      }}, {{}})
    }};
  }}

  function lastGames(block, fases, n) {{
    const set = new Set(fases);
    return (block.games || [])
      .filter(g => set.has(g.fase))
      .sort((a, b) => (b.dt || "").localeCompare(a.dt || ""))
      .slice(0, n);
  }}

  function renderResumen() {{
    const {{ eq, cat, block }} = current();
    const root = document.getElementById("panel-resumen");
    if (!block) {{ root.innerHTML = `<div class="empty">Sin datos para este equipo/categoría.</div>`; return; }}

    const fases = selectedFases();
    if (!fases.length) {{
      root.innerHTML = `<div class="empty">Elegí al menos un torneo para calcular las medias y comparar.</div>`;
      destroyCharts();
      return;
    }}

    const teamLabels = DATA.team_metric_labels || [];
    const advLabels = DATA.adv_metric_labels || [];
    const own = mergeByFases(block, fases);
    const comp = compForFases(cat, fases);
    const team = own.team;
    const adv = own.advanced;
    const faseTxt = fases.length === 1 ? fases[0] : (fases.length + " torneos");

    const metricsTrad = teamLabels.map(m => {{
      const v = team[m.k];
      const c = comp.team[m.k];
      return `<div class="metric">
        <div class="v">${{fmt(v)}}</div>
        <div class="l">${{m.l}}</div>
        <div class="m">media: <b>${{fmt(c)}}</b></div>
      </div>`;
    }}).join("");

    const metricsAdv = advLabels.map(m => {{
      const v = adv[m.k];
      const c = comp.advanced[m.k];
      return `<div class="metric">
        <div class="v">${{fmt(v)}}</div>
        <div class="l">${{m.l}}</div>
        <div class="m">media: <b>${{fmt(c)}}</b></div>
      </div>`;
    }}).join("");

    const last5 = lastGames(block, fases, {LAST_N});
    const rows = last5.map(g => {{
      const resCls = g.res === "G" ? "pill-g" : "pill-p";
      return `<tr>
        <td class="left">${{g.fecha || ""}}</td>
        <td class="left">${{g.fase || ""}}</td>
        <td>${{g.loc || ""}}</td>
        <td class="left">${{g.rival || ""}}</td>
        <td class="${{resCls}}">${{g.res || ""}} ${{g.pts}}-${{g.pts_riv}}</td>
        <td>${{g.t2 || "—"}}</td>
        <td>${{g.t3 || "—"}}</td>
        <td>${{g.tl || "—"}}</td>
        <td>${{g.ro}}</td>
        <td>${{g.rd}}</td>
        <td>${{g.ast}}</td>
        <td>${{g.rec}}</td>
        <td>${{g.per}}</td>
        <td>${{g.val}}</td>
        <td>${{fmt(g.poss)}}</td>
        <td>${{fmt(g.oer)}}</td>
        <td>${{fmt(g.der)}}</td>
        <td>${{fmt(g.efg)}}</td>
        <td>${{fmt(g.ts)}}</td>
        <td>${{fmt(g.orb_pct)}}</td>
        <td>${{fmt(g.drb_pct)}}</td>
      </tr>`;
    }}).join("");

    const radarTeam = teamLabels.map(m => pctile(team[m.k], comp.dist[m.k] || []));
    const radarRef = teamLabels.map(() => 50);
    const sinMuestra = own.pj === 0;

    root.innerHTML = `
      <div class="team-head">
        <div class="crest">${{initials(eq)}}</div>
        <div>
          <h2>${{eq}}</h2>
          <div class="sub">${{cat}} · ${{faseTxt}} · ${{own.pj || 0}} partidos del rival ·
            media sobre ${{comp.n || 0}} equipos</div>
        </div>
      </div>
      ${{sinMuestra ? '<div class="empty">Este rival no jugó los torneos seleccionados. Las medias sí corresponden a esos torneos.</div>' : ''}}

      <div class="card">
        <h3>Promedios de equipo vs media de ${{faseTxt}}</h3>
        <div class="metrics">${{metricsTrad}}</div>
      </div>

      <div class="card">
        <h3>Estadísticas avanzadas vs media de ${{faseTxt}}</h3>
        <div class="metrics">${{metricsAdv}}</div>
        <p style="margin:10px 0 0;font-size:12px;color:#64748b">
          POSS ≈ FGA + 0.44·FTA − ORB + TO. OER/DER = puntos por 100 posesiones.
        </p>
      </div>

      <div class="grid-2">
        <div class="card">
          <h3>Radar vs media de los torneos elegidos (percentiles de equipo)</h3>
          <div class="chart-box"><canvas id="teamRadar"></canvas></div>
        </div>
        <div class="card">
          <h3>Lectura rápida</h3>
          <p style="margin:0 0 10px;font-size:13px;color:#64748b">
            Las tarjetas y el radar usan <b>solo los torneos tildados</b>.
            La media es el promedio de equipos de ${{cat}} en esos torneos.
          </p>
          <p style="margin:0;font-size:13px">
            En <b>Jugadores destacados</b> el ranking de plantel es de toda la temporada.
          </p>
        </div>
      </div>

      <div class="card">
        <h3>Últimos ${{last5.length}} partidos (torneos elegidos)</h3>
        <div class="tablewrap">
          <table class="games">
            <thead>
              <tr>
                <th>Fecha</th><th>Torneo</th><th>Loc</th><th>Rival</th><th>Res</th>
                <th>2P</th><th>3P</th><th>TL</th><th>RO</th><th>RD</th>
                <th>AST</th><th>REC</th><th>PER</th><th>VAL</th>
                <th>POSS</th><th>OER</th><th>DER</th><th>eFG%</th><th>TS%</th>
                <th>ORB%</th><th>DRB%</th>
              </tr>
            </thead>
            <tbody>${{rows || '<tr><td colspan="21" class="empty">Sin partidos en esos torneos</td></tr>'}}</tbody>
          </table>
        </div>
      </div>`;

    destroyCharts();
    const ctx = document.getElementById("teamRadar");
    teamChart = new Chart(ctx, radarConfig(
      eq,
      radarTeam,
      "Media " + faseTxt,
      radarRef
    ));
  }}

  function renderDestacados() {{
    const {{ cat, block }} = current();
    const root = document.getElementById("panel-destacados");
    if (!block) {{ root.innerHTML = `<div class="empty">Sin datos.</div>`; return; }}
    const rubros = DATA.rubros;
    const valueKey = {{ "3P":"t3a", "RO":"ro", "RD":"rd", "REC":"rec", "AST":"ast", "2P":"t2a" }};
    const cards = rubros.map(r => {{
      const ids = (block.tops && block.tops[r.l]) || [];
      const rows = ids.map((id, idx) => {{
        const p = DATA.players[id];
        if (!p) return "";
        const vk = valueKey[r.l];
        const val = p[vk] != null ? Number(p[vk]).toFixed(1) : "—";
        return `<div class="top-row" data-pid="${{id}}">
          <div class="rank">${{idx+1}}</div>
          ${{avatarHtml(p)}}
          <div class="nm">${{p.n}}<small>${{p.pj}} PJ · ${{p.perfil}}</small></div>
          <div class="stat">${{val}}</div>
        </div>`;
      }}).join("");
      return `<div class="top-card"><h4>${{r.l}}</h4><p class="hint">${{r.h}}</p>${{rows || '<div class="empty">Sin muestra</div>'}}</div>`;
    }}).join("");
    root.innerHTML = `<div class="tops">${{cards}}</div>`;
    root.querySelectorAll(".top-row").forEach(row => {{
      row.addEventListener("click", () => openPlayer(row.dataset.pid));
    }});
  }}

  function renderPlayer() {{
    const root = document.getElementById("panel-jugador");
    const {{ cat, block }} = current();
    if (!selectedPid && block && block.roster && block.roster.length) {{
      selectedPid = block.roster[0];
    }}
    const p = DATA.players[selectedPid];
    if (!p) {{
      root.innerHTML = `<div class="empty">Seleccioná un jugador desde Destacados.</div>`;
      return;
    }}
    const foto = p.foto
      ? `<img class="player-photo" src="${{p.foto}}" alt="${{p.n}}" referrerpolicy="no-referrer"
           onerror="this.outerHTML='<div class=\\\\'player-photo-ph\\\\'>${{initials(p.n)}}</div>'"/>`
      : `<div class="player-photo-ph">${{initials(p.n)}}</div>`;
    const ficha = p.purl
      ? `<a class="ext" href="https://argentina.basketball${{p.purl}}" target="_blank" rel="noopener">Ficha GES ↗</a>`
      : "";
    const rows = [
      ["Partidos", p.pj], ["Min/p", p.min], ["Pts/p", p.pts],
      ["2P", `${{Number(p.t2a).toFixed(1)}}/${{Number(p.t2i).toFixed(1)}} (${{Number(p.t2p).toFixed(0)}}%)`],
      ["3P", `${{Number(p.t3a).toFixed(1)}}/${{Number(p.t3i).toFixed(1)}} (${{Number(p.t3p).toFixed(0)}}%)`],
      ["RO / RD", `${{Number(p.ro).toFixed(1)}} / ${{Number(p.rd).toFixed(1)}}`],
      ["Reb tot/p", p.reb], ["Ast/p", p.ast], ["Rec/p", p.rec], ["Tap/p", p.tap],
      ["Val/p", p.val], ["TS%", p.ts != null ? p.ts : "—"], ["eFG%", p.efg != null ? p.efg : "—"]
    ].map(([k,v]) => `<tr><th>${{k}}</th><td class="num">${{v}}</td></tr>`).join("");

    const rosterOpts = (block.roster || []).map(id => {{
      const q = DATA.players[id];
      if (!q) return "";
      const sel = id === selectedPid ? "selected" : "";
      return `<option value="${{id}}" ${{sel}}>${{q.n}}</option>`;
    }}).join("");

    root.innerHTML = `
      <button class="back" id="back-dest">← Destacados</button>
      <div class="card" style="margin-bottom:12px">
        <label class="fld">Jugador del plantel
          <select id="sel-player">${{rosterOpts}}</select>
        </label>
      </div>
      <div class="player-view">
        <div>
          ${{foto}}
        </div>
        <div class="card" style="margin:0">
          <h3 style="margin:0 0 4px;font-size:18px">${{p.n}}</h3>
          <div class="sub" style="color:#64748b;font-size:13px;margin-bottom:8px">
            ${{p.eq}} · ${{p.cat}}${{p.edad != null ? " · " + p.edad + " años" : ""}}
          </div>
          <span class="perfil">${{p.perfil}}</span>
          <p class="desc" style="margin-top:12px">${{p.desc}}</p>
          <div style="margin-top:10px">${{ficha}}</div>
          <table class="stats" style="margin-top:14px">${{rows}}</table>
        </div>
        <div class="card" style="margin:0">
          <h3>Radar vs media ${{cat}}</h3>
          <div class="chart-box"><canvas id="playerRadar"></canvas></div>
        </div>
      </div>`;

    document.getElementById("back-dest").onclick = () => setTab("destacados");
    document.getElementById("sel-player").onchange = (e) => {{
      selectedPid = e.target.value;
      renderPlayer();
    }};

    if (playerChart) {{ playerChart.destroy(); playerChart = null; }}
    playerChart = new Chart(document.getElementById("playerRadar"), radarConfig(
      p.n.split(" ").slice(-1)[0] || p.n,
      p.radar || [],
      "Media " + cat,
      DATA.cat_ref[cat] || [50,50,50,50,50,50,50,50]
    ));
  }}

  function refresh() {{
    document.getElementById("meta").textContent =
      `Actualizado ${{DATA.fecha}} · ${{DATA.equipos.length}} equipos`;
    renderResumen();
    renderDestacados();
    if (document.getElementById("panel-jugador").classList.contains("active")) renderPlayer();
  }}

  gunzipB64(el.textContent.trim()).then(data => {{
    DATA = data;
    const selEq = document.getElementById("sel-eq");
    selEq.innerHTML = DATA.equipos.map(e => `<option value="${{e}}">${{e}}</option>`).join("");
    const prefer = DATA.equipos.find(e => /OBRAS|ESTUDIANTES|GEBA|RIVER|BOCA|SAN LORENZO/i.test(e));
    if (prefer) selEq.value = prefer;
    fillCats();
    selEq.addEventListener("change", () => {{ selectedPid = null; fillCats(); refresh(); }});
    document.getElementById("sel-cat").addEventListener("change", () => {{
      selectedPid = null;
      fillFases(true);
      refresh();
    }});
    document.getElementById("btn-fases-all").addEventListener("click", () => {{
      document.querySelectorAll("#sel-fases input").forEach(i => {{ i.checked = true; }});
      refresh();
    }});
    document.getElementById("btn-fases-none").addEventListener("click", () => {{
      document.querySelectorAll("#sel-fases input").forEach(i => {{ i.checked = false; }});
      refresh();
    }});
    document.querySelectorAll(".tab").forEach(btn => {{
      btn.addEventListener("click", () => {{
        setTab(btn.dataset.tab);
        if (btn.dataset.tab === "resumen") renderResumen();
        if (btn.dataset.tab === "destacados") renderDestacados();
        if (btn.dataset.tab === "jugador") renderPlayer();
      }});
    }});
    refresh();
  }}).catch(err => {{
    document.getElementById("panel-resumen").innerHTML =
      `<div class="empty">Error cargando datos: ${{err}}</div>`;
  }});
}})();
  </script>
</body>
</html>
"""


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Hoja de scouting de rival FeBAMBA")
    p.add_argument(
        "--desde-cache",
        action="store_true",
        help="Usa partidos.json + boxscores_full.json + jugadores_ficha.json",
    )
    p.add_argument("--progress", action="store_true")
    args = p.parse_args(argv)

    if not args.desde_cache:
        print(
            "Usá --desde-cache (misma caché que el buscador). "
            "Para refrescar boxscores: analysis/buscador_jugadores_destacados.py",
            file=sys.stderr,
        )
        return 2

    if not PARTIDOS_CACHE.is_file() or not BOX_FULL_CACHE.is_file():
        print(
            f"Falta caché en {OUT_DIR}. Corré antes el buscador de jugadores.",
            file=sys.stderr,
        )
        return 1

    partidos = json.loads(PARTIDOS_CACHE.read_text(encoding="utf-8"))
    boxscores = json.loads(BOX_FULL_CACHE.read_text(encoding="utf-8"))
    fichas: Dict[str, Dict[str, object]] = {}
    if FICHA_CACHE.is_file():
        fichas = json.loads(FICHA_CACHE.read_text(encoding="utf-8"))

    if args.progress:
        print(
            f"Partidos={len(partidos)} boxscores={len(boxscores)} fichas={len(fichas)}",
            file=sys.stderr,
        )

    jugadores = agregar_jugadores(partidos, boxscores, fichas)
    jugadores = enriquecer_jugadores(jugadores)
    if args.progress:
        print(f"Jugadores agregados: {len(jugadores)}", file=sys.stderr)

    payload = build_payload(jugadores, partidos, boxscores)
    html = _render_html(payload)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    DOCS_HTML.write_text(html, encoding="utf-8")
    print(f"OK -> {OUT_HTML}")
    print(f"OK -> {DOCS_HTML}")
    print(
        f"Equipos={len(payload['equipos'])} jugadores={len(payload['players'])} "
        f"PJ>={MIN_PJ_TOP} para tops · perfiles PJ>={MIN_PJ_CLUSTER}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
