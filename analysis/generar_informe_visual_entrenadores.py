# -*- coding: utf-8 -*-
"""Genera informe HTML visual de entrenadores (resumen + listado interactivo)."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent

CATEGORIAS_ORDEN = (
    "PRE MINI",
    "MINI",
    "INFANTILES",
    "CADETES",
    "JUVENILES",
    "LIGA PROXIMO",
    "LIGA METRO",
)

CONFIG_SHEETS = ROOT / "config" / "entrenadores_sheets.json"
_RE_WS = __import__("re").compile(r"\s+")


def _load_webapp_url() -> str:
    if not CONFIG_SHEETS.is_file():
        return ""
    try:
        cfg = json.loads(CONFIG_SHEETS.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(cfg.get("webapp_url") or "").strip()


def _row_key(entrenador: str, club: str) -> str:
    e = _RE_WS.sub(" ", (entrenador or "").strip().upper())
    c = _RE_WS.sub(" ", (club or "").strip().upper())
    return f"{e}||{c}"


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _bar_svg(items: List[tuple[str, int]], *, width: int = 640, bar_h: int = 28, gap: int = 10) -> str:
    if not items:
        return ""
    max_v = max(v for _, v in items) or 1
    height = len(items) * (bar_h + gap) + 20
    lines = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Gráfico de barras">',
        f'<rect width="{width}" height="{height}" fill="transparent"/>',
    ]
    y = 10
    label_w = 280
    bar_x = label_w + 12
    bar_max_w = width - bar_x - 48
    for label, value in items:
        w = max(2, int(bar_max_w * value / max_v))
        lines.append(
            f'<text x="0" y="{y + bar_h * 0.72}" fill="#334155" font-size="12" '
            f'font-family="Segoe UI, sans-serif">{html.escape(label)}</text>'
        )
        lines.append(
            f'<rect x="{bar_x}" y="{y}" width="{w}" height="{bar_h}" rx="3" fill="#2563eb"/>'
        )
        lines.append(
            f'<text x="{bar_x + w + 8}" y="{y + bar_h * 0.72}" fill="#0f172a" font-size="12" '
            f'font-weight="600" font-family="Segoe UI, sans-serif">{value}</text>'
        )
        y += bar_h + gap
    lines.append("</svg>")
    return "\n".join(lines)


def _donut_svg(buckets: List[tuple[str, int]], size: int = 220) -> str:
    total = sum(v for _, v in buckets) or 1
    colors = ["#2563eb", "#0891b2", "#059669", "#d97706", "#7c3aed", "#dc2626", "#0f766e"]
    cx = cy = size // 2
    r = size * 0.36
    ir = r * 0.58
    start = -90.0
    parts: List[str] = [
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img">'
    ]
    for i, (_label, value) in enumerate(buckets):
        angle = 360.0 * value / total
        if angle <= 0:
            continue
        end = start + angle
        large = 1 if angle > 180 else 0
        x1 = cx + r * math.cos(math.radians(start))
        y1 = cy + r * math.sin(math.radians(start))
        x2 = cx + r * math.cos(math.radians(end))
        y2 = cy + r * math.sin(math.radians(end))
        xi1 = cx + ir * math.cos(math.radians(end))
        yi1 = cy + ir * math.sin(math.radians(end))
        xi2 = cx + ir * math.cos(math.radians(start))
        yi2 = cy + ir * math.sin(math.radians(start))
        color = colors[i % len(colors)]
        parts.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} '
            f'L {xi1:.2f} {yi1:.2f} A {ir:.2f} {ir:.2f} 0 {large} 0 {xi2:.2f} {yi2:.2f} Z" fill="{color}"/>'
        )
        start = end
    parts.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" fill="#0f172a" font-size="22" '
        f'font-weight="700" font-family="Segoe UI, sans-serif">{total}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" fill="#64748b" font-size="11" '
        f'font-family="Segoe UI, sans-serif">vínculos</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _parse_cats(s: str) -> List[str]:
    # Las categorías están unidas por ", " — no son parte del nombre del entrenador.
    return [c.strip() for c in (s or "").split(",") if c.strip()]


def cargar_datos(
    combos_path: Path, listado_path: Path
) -> Tuple[
    List[Dict[str, str]],
    List[Dict[str, object]],
    List[Tuple[str, int]],
    List[Tuple[str, int]],
]:
    with open(combos_path, encoding="utf-8-sig", newline="") as f:
        combos = list(csv.DictReader(f))
    with open(listado_path, encoding="utf-8-sig", newline="") as f:
        raw_listado = list(csv.DictReader(f))

    listado: List[Dict[str, object]] = []
    for r in raw_listado:
        cats = _parse_cats(r.get("Categorias_A_Cargo") or "")
        ent = (r.get("Entrenador") or "").strip()
        club = (r.get("Club") or "").strip()
        listado.append(
            {
                "key": _row_key(ent, club),
                "entrenador": ent,
                "club": club,
                "categorias": cats,
                "whatsapp": "",
            }
        )

    buckets: Counter[int] = Counter()
    for row in combos:
        n = int(row["Cantidad"])
        if n > 0:
            buckets[int(row["N_Categorias"])] += n
    bucket_items = [(f"{k} categoría{'s' if k > 1 else ''}", buckets[k]) for k in sorted(buckets)]

    singles = [
        (r["Combinacion"], int(r["Cantidad"]))
        for r in combos
        if int(r["N_Categorias"]) == 1 and int(r["Cantidad"]) > 0
    ]
    singles.sort(key=lambda x: -x[1])

    return combos, listado, bucket_items, singles


def generar_html(
    *,
    fecha_ini: str,
    fecha_fin: str,
    out_path: Path,
    combos_path: Path,
    listado_path: Path,
    partidos: int = 6010,
) -> None:
    combos, listado, bucket_items, singles = cargar_datos(combos_path, listado_path)
    activas = [r for r in combos if int(r["Cantidad"]) > 0]
    vinculos = len(listado)
    combos_activas = len(activas)
    partidos_fmt = _fmt_int(partidos)
    colors = ["#2563eb", "#0891b2", "#059669", "#d97706", "#7c3aed", "#dc2626", "#0f766e"]
    top_all = sorted(activas, key=lambda x: (-int(x["Cantidad"]), x["Combinacion"]))[:15]
    total_combos_teoricas = len(combos)
    restantes = total_combos_teoricas - len(activas)
    max_cats = max((int(r["N_Categorias"]) for r in combos), default=0)
    full_combo_label = next(
        (r["Combinacion"] for r in combos if int(r["N_Categorias"]) == max_cats),
        "",
    )
    full_set = [
        (str(r["entrenador"]), str(r["club"]))
        for r in listado
        if len(r["categorias"]) == max_cats and max_cats > 0  # type: ignore[arg-type]
    ]
    n_full = len(full_set)

    data_json = json.dumps(listado, ensure_ascii=False)
    cats_json = json.dumps(list(CATEGORIAS_ORDEN), ensure_ascii=False)
    webapp_url = _load_webapp_url()
    webapp_json = json.dumps(webapp_url, ensure_ascii=False)
    sheets_status = (
        "Conectado a Google Sheets (lectura/escritura WhatsApp)."
        if webapp_url
        else "Sin webapp_url en config/entrenadores_sheets.json — usando listado embebido; WhatsApp solo local."
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Entrenadores formativas + Liga Metro 2026</title>
  <style>
    :root {{
      --bg: #f1f5f9;
      --paper: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --accent: #2563eb;
      --accent-soft: #eff6ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    .page {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }}
    header {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 24px 28px;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }}
    .subtitle {{ color: var(--muted); font-size: 13px; margin: 0; }}
    .tabs {{
      display: flex; gap: 6px; margin-bottom: 16px;
      background: var(--paper); border: 1px solid var(--line);
      border-radius: 10px; padding: 6px; width: fit-content;
    }}
    .tab-btn {{
      border: 0; background: transparent; color: var(--muted);
      padding: 10px 16px; border-radius: 8px; font: inherit; font-weight: 600;
      cursor: pointer;
    }}
    .tab-btn.active {{ background: var(--accent); color: #fff; }}
    .panel {{ display: none; }}
    .panel.active {{ display: block; }}
    .stats {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0 20px;
    }}
    .stat {{
      background: var(--paper); border: 1px solid var(--line);
      border-radius: 10px; padding: 16px;
    }}
    .stat .n {{ font-size: 26px; font-weight: 700; color: var(--accent); }}
    .stat .l {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
    section, .card {{
      background: var(--paper); border: 1px solid var(--line);
      border-radius: 12px; padding: 20px 22px; margin-bottom: 16px;
    }}
    h2 {{ margin: 0 0 6px; font-size: 16px; font-weight: 700; }}
    .caption {{ margin: 0 0 14px; font-size: 12px; color: var(--muted); }}
    .legend {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 12px;
    }}
    .legend span {{ display: flex; align-items: center; gap: 8px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{
      border-bottom: 1px solid var(--line); padding: 10px 8px;
      text-align: left; vertical-align: middle;
    }}
    th {{
      color: var(--muted); font-weight: 600; font-size: 11px;
      text-transform: uppercase; letter-spacing: 0.04em;
      position: sticky; top: 0; background: var(--paper); z-index: 1;
    }}
    .note {{
      background: var(--accent-soft); border: 1px solid #bfdbfe;
      border-radius: 8px; padding: 12px 14px; font-size: 12px;
      color: #1e3a8a; margin-top: 12px;
    }}
    .filters {{
      display: flex; flex-wrap: wrap; gap: 10px; align-items: end;
      margin-bottom: 14px;
    }}
    .filters label {{ display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }}
    .filters input, .filters select {{
      border: 1px solid var(--line); border-radius: 8px;
      padding: 9px 11px; font: inherit; min-width: 180px; color: var(--text);
      background: #fff;
    }}
    .filters input.wp {{
      min-width: 140px; width: 150px; font-variant-numeric: tabular-nums;
    }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .chip {{
      display: inline-block; background: #f1f5f9; border: 1px solid var(--line);
      border-radius: 999px; padding: 2px 9px; font-size: 11px; color: #334155;
      white-space: nowrap;
    }}
    .name-cell {{ font-weight: 600; white-space: nowrap; }}
    .club-cell {{ color: #334155; }}
    .count-bar {{
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 10px; font-size: 13px; color: var(--muted);
    }}
    .table-wrap {{
      max-height: 70vh; overflow: auto; border: 1px solid var(--line);
      border-radius: 10px;
    }}
    .table-wrap table {{ margin: 0; }}
    .table-wrap td, .table-wrap th {{ padding: 11px 12px; }}
    .status-pill {{
      display: inline-block; font-size: 11px; font-weight: 600;
      padding: 4px 10px; border-radius: 999px; margin-top: 8px;
      background: #f1f5f9; color: #475569; border: 1px solid var(--line);
    }}
    .status-pill.ok {{ background: #ecfdf5; color: #065f46; border-color: #a7f3d0; }}
    .status-pill.warn {{ background: #fffbeb; color: #92400e; border-color: #fde68a; }}
    .status-pill.err {{ background: #fef2f2; color: #991b1b; border-color: #fecaca; }}
    .wp-wrap {{ display: flex; align-items: center; gap: 6px; }}
    .wp-msg {{ font-size: 11px; color: var(--muted); min-width: 2.5rem; }}
    .wp-msg.ok {{ color: #059669; }}
    .wp-msg.err {{ color: #dc2626; }}
    footer {{ text-align: center; color: var(--muted); font-size: 11px; margin-top: 20px; }}
    @media (max-width: 800px) {{
      .stats, .grid-2 {{ grid-template-columns: 1fr 1fr; }}
      .name-cell {{ white-space: normal; }}
    }}
    @media print {{
      .tabs, .filters {{ display: none !important; }}
      .panel {{ display: block !important; }}
      .table-wrap {{ max-height: none; overflow: visible; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <h1>Entrenadores por club y categorías</h1>
      <p class="subtitle">Temporada 2026 · Formativas + Liga Metro · {html.escape(fecha_ini)} a {html.escape(fecha_fin)}</p>
      <p class="subtitle" style="margin-top:6px">Fuente: argentina.basketball (5075–5080 + 6290). El nombre completo del entrenador es un solo campo (apellido + nombre).</p>
    </header>

    <div class="tabs" role="tablist">
      <button type="button" class="tab-btn active" data-tab="resumen" role="tab">Resumen</button>
      <button type="button" class="tab-btn" data-tab="listado" role="tab">Listado de entrenadores</button>
    </div>

    <div id="panel-resumen" class="panel active" role="tabpanel">
      <div class="stats">
        <div class="stat"><div class="n">{partidos_fmt}</div><div class="l">Partidos analizados</div></div>
        <div class="stat"><div class="n">{vinculos}</div><div class="l">Vínculos entrenador–club</div></div>
        <div class="stat"><div class="n">{combos_activas}</div><div class="l">Combinaciones con casos</div></div>
        <div class="stat"><div class="n">{n_full}</div><div class="l">Con las {max_cats} categorías</div></div>
      </div>

      <div class="grid-2">
        <section>
          <h2>Distribución por cantidad de categorías a cargo</h2>
          <p class="caption">Conteo exclusivo: cada entrenador–club suma en una sola combinación.</p>
          <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
            {_donut_svg(bucket_items)}
            <div class="legend">
              {''.join(f'<span><i class="dot" style="background:{colors[i % len(colors)]}"></i>{html.escape(l)} · {v}</span>' for i, (l, v) in enumerate(bucket_items))}
            </div>
          </div>
        </section>
        <section>
          <h2>Solo una categoría</h2>
          <p class="caption">Entrenadores–club que dirigen únicamente esa categoría.</p>
          {_bar_svg(singles, width=420)}
        </section>
      </div>

      <section>
        <h2>Combinaciones más frecuentes (top 15)</h2>
        <p class="caption">Cada vínculo aparece en una sola fila.</p>
        {_bar_svg([(r['Combinacion'], int(r['Cantidad'])) for r in top_all], width=900, bar_h=24, gap=8)}
      </section>

      <section>
        <h2>Entrenadores con las {max_cats} categorías a cargo</h2>
        <p class="caption">{html.escape(full_combo_label)}</p>
        <table>
          <thead><tr><th>Entrenador</th><th>Club</th></tr></thead>
          <tbody>
            {''.join(f"<tr><td class='name-cell'>{html.escape(e)}</td><td>{html.escape(c)}</td></tr>" for e, c in full_set) if full_set else "<tr><td colspan='2'>Ninguno en este período</td></tr>"}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Combinaciones activas ({len(activas)} de {total_combos_teoricas})</h2>
        <p class="caption">{restantes} combinaciones teóricas con cantidad 0.</p>
        <table>
          <thead><tr><th>Combinación</th><th>Cantidad</th><th>N°</th></tr></thead>
          <tbody>
            {''.join(f"<tr><td>{html.escape(r['Combinacion'])}</td><td>{r['Cantidad']}</td><td>{r['N_Categorias']}</td></tr>" for r in sorted(activas, key=lambda x:(-int(x['Cantidad']), x['Combinacion'])))}
          </tbody>
        </table>
        <div class="note">Las cantidades no se suman entre filas: un entrenador con 3 categorías cuenta solo en su combinación exacta.</div>
      </section>
    </div>

    <div id="panel-listado" class="panel" role="tabpanel">
      <div class="card">
        <h2>Listado de entrenadores</h2>
        <p class="caption">Nombre completo en una sola columna. Filtrá por categoría. El WhatsApp se guarda en Google Sheets.</p>
        <span id="sheetsStatus" class="status-pill">{html.escape(sheets_status)}</span>

        <div class="filters" style="margin-top:14px">
          <label>Buscar
            <input type="search" id="q" placeholder="Nombre o club…" autocomplete="off"/>
          </label>
          <label>Categoría
            <select id="cat">
              <option value="">Todas</option>
            </select>
          </label>
          <label>Solo con WhatsApp
            <select id="wpFilter">
              <option value="">Todos</option>
              <option value="con">Con número</option>
              <option value="sin">Sin número</option>
            </select>
          </label>
          <button type="button" id="btnReload" class="tab-btn" style="background:#f8fafc;border:1px solid var(--line);color:var(--text);align-self:end">Recargar Sheet</button>
        </div>

        <div class="count-bar">
          <span id="countLabel">0 entrenadores</span>
          <button type="button" id="btnExport" class="tab-btn" style="background:#f8fafc;border:1px solid var(--line);color:var(--text)">Exportar CSV</button>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Entrenador</th>
                <th>Club</th>
                <th>Categorías a cargo</th>
                <th>WhatsApp</th>
              </tr>
            </thead>
            <tbody id="tbody"></tbody>
          </table>
        </div>
        <div class="note">Ver setup en <code>docs/entrenadores_sheets.md</code>. Si no hay <code>webapp_url</code>, el WhatsApp queda solo en este navegador (localStorage) como respaldo.</div>
      </div>
    </div>

    <footer>Generado automáticamente · GES LNB y TNA</footer>
  </div>

  <script>
  const EMBEDDED_DATA = {data_json};
  let DATA = EMBEDDED_DATA.slice();
  const CATS = {cats_json};
  const WEBAPP_URL = {webapp_json};
  const WP_KEY = "entrenadores_wp_2026_v1";
  const wpCache = Object.create(null);

  function setStatus(text, kind) {{
    const el = document.getElementById("sheetsStatus");
    el.textContent = text;
    el.className = "status-pill" + (kind ? " " + kind : "");
  }}

  function loadLocalWp() {{
    try {{ return JSON.parse(localStorage.getItem(WP_KEY) || "{{}}"); }}
    catch (e) {{ return {{}}; }}
  }}
  function saveLocalWp(map) {{
    localStorage.setItem(WP_KEY, JSON.stringify(map));
  }}
  function rowKey(r) {{
    if (r.key) return String(r.key).toUpperCase();
    return (r.entrenador + "||" + r.club).toUpperCase();
  }}
  function getWp(r) {{
    const k = rowKey(r);
    if (wpCache[k] !== undefined) return wpCache[k];
    if (r.whatsapp) return r.whatsapp;
    return loadLocalWp()[k] || "";
  }}
  function setWpLocal(r, value) {{
    const k = rowKey(r);
    wpCache[k] = value;
    const map = loadLocalWp();
    if (value) map[k] = value; else delete map[k];
    saveLocalWp(map);
  }}

  const catSel = document.getElementById("cat");
  CATS.forEach(c => {{
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    catSel.appendChild(o);
  }});

  document.querySelectorAll(".tab-btn[data-tab]").forEach(btn => {{
    btn.addEventListener("click", () => {{
      document.querySelectorAll(".tab-btn[data-tab]").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("panel-" + btn.dataset.tab).classList.add("active");
    }});
  }});

  function filtered() {{
    const q = (document.getElementById("q").value || "").trim().toUpperCase();
    const cat = catSel.value;
    const wpMode = document.getElementById("wpFilter").value;
    return DATA.filter(r => {{
      if (cat && !(r.categorias || []).includes(cat)) return false;
      if (q) {{
        const hay = (r.entrenador + " " + r.club).toUpperCase();
        if (!hay.includes(q)) return false;
      }}
      const num = (getWp(r) || "").trim();
      if (wpMode === "con" && !num) return false;
      if (wpMode === "sin" && num) return false;
      return true;
    }});
  }}

  async function saveWpToSheets(r, value, msgEl) {{
    setWpLocal(r, value);
    if (!WEBAPP_URL) {{
      if (msgEl) {{ msgEl.textContent = "local"; msgEl.className = "wp-msg ok"; }}
      return;
    }}
    if (msgEl) {{ msgEl.textContent = "…"; msgEl.className = "wp-msg"; }}
    try {{
      const res = await fetch(WEBAPP_URL, {{
        method: "POST",
        headers: {{ "Content-Type": "text/plain;charset=utf-8" }},
        body: JSON.stringify({{ key: rowKey(r), whatsapp: value }}),
        redirect: "follow",
      }});
      const text = await res.text();
      let data = null;
      try {{ data = JSON.parse(text); }} catch (e) {{}}
      if (data && data.ok) {{
        if (msgEl) {{ msgEl.textContent = "OK"; msgEl.className = "wp-msg ok"; }}
      }} else {{
        const err = (data && data.error) || ("HTTP " + res.status);
        if (msgEl) {{ msgEl.textContent = "err"; msgEl.className = "wp-msg err"; msgEl.title = err; }}
      }}
    }} catch (err) {{
      if (msgEl) {{
        msgEl.textContent = "err";
        msgEl.className = "wp-msg err";
        msgEl.title = String(err);
      }}
    }}
  }}

  function render() {{
    const rows = filtered();
    const tb = document.getElementById("tbody");
    tb.innerHTML = "";
    document.getElementById("countLabel").textContent =
      rows.length + " de " + DATA.length + " entrenadores";

    rows.forEach(r => {{
      const tr = document.createElement("tr");

      const tdN = document.createElement("td");
      tdN.className = "name-cell";
      tdN.textContent = r.entrenador;

      const tdC = document.createElement("td");
      tdC.className = "club-cell";
      tdC.textContent = r.club;

      const tdCat = document.createElement("td");
      const wrap = document.createElement("div");
      wrap.className = "chip-row";
      (r.categorias || []).forEach(c => {{
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = c;
        wrap.appendChild(chip);
      }});
      tdCat.appendChild(wrap);

      const tdW = document.createElement("td");
      const wrapW = document.createElement("div");
      wrapW.className = "wp-wrap";
      const inp = document.createElement("input");
      inp.className = "wp";
      inp.type = "tel";
      inp.inputMode = "numeric";
      inp.placeholder = "54911…";
      inp.value = getWp(r);
      const msg = document.createElement("span");
      msg.className = "wp-msg";
      inp.addEventListener("change", () => {{
        saveWpToSheets(r, inp.value.trim(), msg);
      }});
      wrapW.appendChild(inp);
      wrapW.appendChild(msg);
      tdW.appendChild(wrapW);

      tr.appendChild(tdN);
      tr.appendChild(tdC);
      tr.appendChild(tdCat);
      tr.appendChild(tdW);
      tb.appendChild(tr);
    }});
  }}

  async function loadFromSheets() {{
    if (!WEBAPP_URL) {{
      setStatus("Sin webapp_url — listado embebido (WhatsApp local)", "warn");
      DATA = EMBEDDED_DATA.slice();
      render();
      return;
    }}
    setStatus("Cargando desde Google Sheets…", "");
    try {{
      const res = await fetch(WEBAPP_URL, {{ method: "GET", redirect: "follow" }});
      const text = await res.text();
      const data = JSON.parse(text);
      if (!data.ok || !Array.isArray(data.rows)) {{
        throw new Error((data && data.error) || "Respuesta inválida");
      }}
      DATA = data.rows.map(r => ({{
        key: r.key || rowKey(r),
        entrenador: r.entrenador || "",
        club: r.club || "",
        categorias: Array.isArray(r.categorias) ? r.categorias : [],
        whatsapp: r.whatsapp || "",
      }}));
      DATA.forEach(r => {{
        if (r.whatsapp) wpCache[rowKey(r)] = r.whatsapp;
      }});
      setStatus("Conectado a Google Sheets · " + DATA.length + " filas", "ok");
      render();
    }} catch (err) {{
      setStatus("No se pudo leer Sheets — usando listado embebido (" + String(err) + ")", "err");
      DATA = EMBEDDED_DATA.slice();
      render();
    }}
  }}

  ["q", "cat", "wpFilter"].forEach(id => {{
    document.getElementById(id).addEventListener("input", render);
    document.getElementById(id).addEventListener("change", render);
  }});
  document.getElementById("btnReload").addEventListener("click", loadFromSheets);

  document.getElementById("btnExport").addEventListener("click", () => {{
    const rows = filtered();
    const lines = [["Entrenador", "Club", "Categorias", "WhatsApp"].join(";")];
    rows.forEach(r => {{
      const cats = (r.categorias || []).join(" | ");
      const num = getWp(r) || "";
      const cells = [r.entrenador, r.club, cats, num].map(v => {{
        const s = String(v).replace(/"/g, '""');
        return '"' + s + '"';
      }});
      lines.push(cells.join(";"));
    }});
    const blob = new Blob(["\\ufeff" + lines.join("\\n")], {{ type: "text/csv;charset=utf-8" }});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "entrenadores_con_whatsapp.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }});

  loadFromSheets();
  </script>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Informe HTML -> {out_path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fecha-ini", default="2026-03-01 (formativas) / 2026-08-01 (Metro)")
    p.add_argument("--fecha-fin", default="2026-05-31 (formativas) / 2026-11-30 (Metro)")
    p.add_argument(
        "--combos",
        default=str(ROOT / "outputs" / "entrenadores" / "combinaciones_categorias_2026.csv"),
    )
    p.add_argument(
        "--listado",
        default=str(ROOT / "outputs" / "entrenadores" / "entrenadores_club_categorias_2026.csv"),
    )
    p.add_argument("--partidos", type=int, default=6535)
    p.add_argument(
        "--out",
        default=str(ROOT / "outputs" / "entrenadores" / "informe_entrenadores_2026.html"),
    )
    args = p.parse_args()
    generar_html(
        fecha_ini=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        out_path=Path(args.out),
        combos_path=Path(args.combos),
        listado_path=Path(args.listado),
        partidos=args.partidos,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
