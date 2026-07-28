# -*- coding: utf-8 -*-
"""
Informe HTML por niveles de la tabla general metropolitana.

Niveles:
  1 → puestos 1–32
  2 → puestos 33–64
  3 → puestos 65–96
  4 → resto

  python analysis/emparejar_clubes_federacion.py --geocodificar
  python analysis/generar_informe_viajes_elite42.py
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs" / "viajes_elite42"
MAPEO_CSV = OUT_DIR / "mapeo_clubes.csv"
MATRIZ_JSON = OUT_DIR / "matriz_distancias_km.json"
NIVELES_JSON = OUT_DIR / "niveles_viajes.json"
OUT_HTML = OUT_DIR / "informe_viajes_elite42.html"

# Colores de región (pedido del usuario).
REGION_COLOR = {
    "CENTRO": "#dc2626",  # rojo
    "NORTE": "#2563eb",  # azul
    "SUR": "#eab308",  # amarillo
    "OESTE": "#16a34a",  # verde
}

NIVELES = [
    {"id": 1, "nombre": "Nivel 1", "rango": "Interconferencia A"},
    {"id": 2, "nombre": "Nivel 2", "rango": "Interconferencia B"},
    {"id": 3, "nombre": "Nivel 3", "rango": "Nivel 1"},
    {"id": 4, "nombre": "Nivel 4", "rango": "Resto de equipos"},
]


def _region(zona: str) -> str:
    return (zona or "").split()[0].upper()


def _cargar_mapeo() -> List[dict]:
    with MAPEO_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # Índice por nombre de equipo en el orden del CSV (coincide con matriz).
    for i, r in enumerate(rows):
        r["_idx"] = i
        r["pos"] = int(r["pos"])
        r["puntos"] = int(float(r["puntos"]))
        r["region"] = _region(r["zona"])
        r["fase"] = r.get("fase") or ""
        r["lat"] = float(r["lat"]) if r.get("lat") else None
        r["lon"] = float(r["lon"]) if r.get("lon") else None
    return rows


def _obtener_fases_segunda() -> Dict[str, str]:
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ingest.febamba.standings_2026 import clave_equipo

    html_path = ROOT / "outputs" / "formativas_2026" / "tabla_posiciones.html"
    if not html_path.exists():
        return {}
    text = html_path.read_text(encoding="utf-8")
    start = text.index("const DATA = ") + len("const DATA = ")
    end = text.index(";\n", start)
    data = json.loads(text[start:end])
    
    mapa = {}
    for fase in ["INTERCONFERENCIA_A", "INTERCONFERENCIA_B", "NIVEL_1"]:
        for zona, filas in data["tablas"].get(fase, {}).items():
            for f in filas:
                mapa[clave_equipo(f["equipo"])] = fase
    return mapa


def _dist(
    mat: List[List[Optional[float]]], i: int, j: int
) -> Optional[float]:
    if i < 0 or j < 0 or i >= len(mat) or j >= len(mat[i]):
        return None
    v = mat[i][j]
    if v is None:
        return None
    return float(v)


def _metricas_nivel(
    clubs: List[dict], mat: List[List[Optional[float]]]
) -> List[dict]:
    """Por club: rival +lejos, +cerca, media km regionalizado y sin región (ida)."""
    out: List[dict] = []
    geo = [c for c in clubs if c["lat"] is not None and c["lon"] is not None]
    for c in clubs:
        if c["lat"] is None or c["lon"] is None:
            out.append(
                {
                    "pos": c["pos"],
                    "equipo": c["equipo"],
                    "region": c["region"],
                    "zona": c["zona"],
                    "puntos": c["puntos"],
                    "direccion": c.get("direccion") or "",
                    "afiliada": c.get("afiliada") or "",
                    "fase": c.get("fase") or "",
                    "lat": None,
                    "lon": None,
                    "mas_lejana": "—",
                    "dist_lejana": None,
                    "mas_corta": "—",
                    "dist_corta": None,
                    "media_regionalizado": None,
                    "media_sin_region": None,
                }
            )
            continue

        i = c["_idx"]
        lejana_eq, lejana_d = "—", None
        corta_eq, corta_d = "—", None
        dists_nivel: List[float] = []
        dists_region: List[float] = []

        for o in geo:
            if o["_idx"] == i:
                continue
            d = _dist(mat, i, o["_idx"])
            if d is None:
                continue
            dists_nivel.append(d)
            if lejana_d is None or d > lejana_d:
                lejana_d, lejana_eq = d, o["equipo"]
            if corta_d is None or d < corta_d:
                corta_d, corta_eq = d, o["equipo"]
            if o["region"] == c["region"]:
                dists_region.append(d)

        out.append(
            {
                "pos": c["pos"],
                "equipo": c["equipo"],
                "region": c["region"],
                "zona": c["zona"],
                "puntos": c["puntos"],
                "direccion": c.get("direccion") or "",
                "afiliada": c.get("afiliada") or "",
                "fase": c.get("fase") or "",
                "lat": c["lat"],
                "lon": c["lon"],
                "mas_lejana": lejana_eq,
                "dist_lejana": round(lejana_d, 1) if lejana_d is not None else None,
                "mas_corta": corta_eq,
                "dist_corta": round(corta_d, 1) if corta_d is not None else None,
                "media_regionalizado": (
                    round(statistics.mean(dists_region), 1) if dists_region else None
                ),
                "media_sin_region": (
                    round(statistics.mean(dists_nivel), 1) if dists_nivel else None
                ),
            }
        )
    return out


def calcular_payload() -> dict:
    mapeo = _cargar_mapeo()
    with MATRIZ_JSON.open(encoding="utf-8") as f:
        mat = json.load(f)["km"]

    fase_segunda_map = _obtener_fases_segunda()
    por_nivel: Dict[int, List[dict]] = {n["id"]: [] for n in NIVELES}
    for row in mapeo:
        fase2 = fase_segunda_map.get(row["clave"])
        if fase2 == "INTERCONFERENCIA_A":
            nid = 1
        elif fase2 == "INTERCONFERENCIA_B":
            nid = 2
        elif fase2 == "NIVEL_1":
            nid = 3
        else:
            nid = 4
        por_nivel[nid].append(row)

    niveles_out = []
    for meta in NIVELES:
        clubs = sorted(por_nivel[meta["id"]], key=lambda x: x["pos"])
        filas = _metricas_nivel(clubs, mat)
        medias_reg = [f["media_regionalizado"] for f in filas if f["media_regionalizado"] is not None]
        medias_sin = [f["media_sin_region"] for f in filas if f["media_sin_region"] is not None]
        niveles_out.append(
            {
                **meta,
                "n_equipos": len(filas),
                "n_geocodificados": sum(1 for f in filas if f["lat"] is not None),
                "stats": {
                    "media_regionalizado_nivel": (
                        round(statistics.mean(medias_reg), 1) if medias_reg else None
                    ),
                    "media_sin_region_nivel": (
                        round(statistics.mean(medias_sin), 1) if medias_sin else None
                    ),
                },
                "equipos": filas,
            }
        )

    payload = {
        "colores_region": REGION_COLOR,
        "niveles": niveles_out,
        "total_equipos": len(mapeo),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with NIVELES_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def generar(out: Path = OUT_HTML) -> Path:
    payload = calcular_payload()
    colores = payload["colores_region"]

    out.write_text(
        f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Tabla general · Niveles y viajes</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    :root {{
      --bg:#f8fafc; --card:#fff; --ink:#0f172a; --muted:#64748b; --accent:#1d4ed8;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ background:linear-gradient(135deg,#0f172a,#1e3a5f); color:#fff; padding:24px 28px; }}
    header h1 {{ margin:0 0 8px; font-size:1.5rem; }}
    header p {{ margin:0; opacity:.92; max-width:980px; line-height:1.5; font-size:.93rem; }}
    main {{ max-width:1280px; margin:0 auto; padding:20px 24px 48px; }}
    .legend {{ display:flex; flex-wrap:wrap; gap:12px; margin:0 0 16px; }}
    .legend span {{ display:inline-flex; align-items:center; gap:6px; font-size:.85rem; color:var(--muted); }}
    .dot {{ width:12px; height:12px; border-radius:50%; display:inline-block; }}
    .tabs {{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px; }}
    .tab {{
      border:1px solid #cbd5e1; background:#fff; border-radius:8px;
      padding:9px 14px; cursor:pointer; font-size:.9rem;
    }}
    .tab.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
    .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:14px; }}
    .stat {{ background:var(--card); border-radius:10px; padding:12px 14px; box-shadow:0 1px 3px rgba(15,23,42,.07); }}
    .stat b {{ display:block; font-size:1.2rem; color:var(--accent); }}
    .stat span {{ font-size:.78rem; color:var(--muted); }}
    #map {{ height:540px; border-radius:12px; box-shadow:0 6px 20px rgba(15,23,42,.1); }}
    .card {{ background:var(--card); border-radius:10px; padding:16px; margin-top:18px;
      box-shadow:0 1px 3px rgba(15,23,42,.07); }}
    table {{ width:100%; border-collapse:collapse; font-size:.84rem; }}
    th, td {{ padding:7px 9px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
    th {{ background:#f1f5f9; position:sticky; top:0; }}
    .region {{ font-weight:600; }}
    .muted {{ color:var(--muted); font-size:.88rem; line-height:1.45; }}
    .num {{ white-space:nowrap; }}
    @media (max-width:900px) {{
      .stats {{ grid-template-columns:1fr 1fr; }}
      #map {{ height:400px; }}
    }}
  </style>
</head>
<body>
<header>
  <h1>Tabla general metropolitana · Niveles y distancias</h1>
    <p>
    Equipos de Primera fase FeBAMBA asignados según su clasificación a la <strong>Segunda Fase</strong>.
    Mapa filtrable por nivel.
    Colores: <strong>Centro rojo</strong>, <strong>Norte azul</strong>,
    <strong>Sur amarillo</strong>, <strong>Oeste verde</strong>.
    Medias = distancia ida promedio a rivales del nivel
    (regionalizado = misma región; sin regionalización = todo el nivel).
  </p>
</header>
<main>
  <div class="legend">
    <span><i class="dot" style="background:{colores['CENTRO']}"></i>Centro</span>
    <span><i class="dot" style="background:{colores['NORTE']}"></i>Norte</span>
    <span><i class="dot" style="background:{colores['SUR']}"></i>Sur</span>
    <span><i class="dot" style="background:{colores['OESTE']}"></i>Oeste</span>
  </div>

  <div class="tabs" id="tabs"></div>
  <div class="stats" id="stats"></div>
  <div id="map"></div>

  <div class="card">
    <h2 id="tabla-titulo" style="margin:0 0 10px;font-size:1.1rem;">Equipos del nivel</h2>
    <p class="muted" style="margin-top:0">
      Para cada equipo: rival más lejano y más cercano <em>dentro del nivel</em>,
      media de km si juega solo contra su región (regionalizado) y media si juega
      contra todo el nivel (sin regionalización).
    </p>
    <div style="overflow-x:auto;max-height:560px;">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Equipo</th>
            <th>Fase</th>
            <th>Región</th>
            <th>Dirección</th>
            <th>Más lejana (km)</th>
            <th>Más corta (km)</th>
            <th>Media km regionalizado</th>
            <th>Media km sin región</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const COLORS = DATA.colores_region;

const map = L.map('map').setView([-34.62, -58.45], 10);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18, attribution: '&copy; OpenStreetMap'
}}).addTo(map);
const layer = L.layerGroup().addTo(map);

const tabs = document.getElementById('tabs');
DATA.niveles.forEach((n, i) => {{
  const b = document.createElement('button');
  b.className = 'tab';
  b.textContent = `${{n.nombre}} · ${{n.rango}} (${{n.n_equipos}})`;
  b.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    b.classList.add('active');
    history.replaceState(null, null, `#nivel-${{n.id}}`);
    renderNivel(i);
  }});
  tabs.appendChild(b);
}});

function fmt(v) {{
  return (v === null || v === undefined) ? '—' : Number(v).toFixed(1);
}}

function renderNivel(idx) {{
  const n = DATA.niveles[idx];
  document.getElementById('stats').innerHTML = `
    <div class="stat"><b>${{n.n_equipos}}</b><span>equipos en el nivel</span></div>
    <div class="stat"><b>${{n.n_geocodificados}}</b><span>con sede en mapa</span></div>
    <div class="stat"><b>${{fmt(n.stats.media_regionalizado_nivel)}} km</b><span>media nivel regionalizado</span></div>
    <div class="stat"><b>${{fmt(n.stats.media_sin_region_nivel)}} km</b><span>media nivel sin región</span></div>`;

  document.getElementById('tabla-titulo').textContent =
    `${{n.nombre}} (${{n.rango}}) · ${{n.n_equipos}} equipos`;

  layer.clearLayers();
  const bounds = [];
  for (const e of n.equipos) {{
    if (e.lat == null || e.lon == null) continue;
    const color = COLORS[e.region] || '#64748b';
    const mk = L.circleMarker([e.lat, e.lon], {{
      radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.92
    }}).addTo(layer);
    mk.bindPopup(
      `<strong>#${{e.pos}} ${{e.equipo}}</strong><br>` +
      `${{e.region}} · ${{e.zona}} · ${{e.puntos}} pts<br>` +
      `<small>${{e.direccion || ''}}</small>`
    );
    bounds.push([e.lat, e.lon]);
  }}
  if (bounds.length) map.fitBounds(bounds, {{ padding: [30, 30] }});
  setTimeout(() => map.invalidateSize(), 50);

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = n.equipos.map(e => {{
    const color = COLORS[e.region] || '#64748b';
    const lejana = e.dist_lejana == null
      ? '—'
      : `${{e.mas_lejana}} <span class="num">(${{fmt(e.dist_lejana)}})</span>`;
    const corta = e.dist_corta == null
      ? '—'
      : `${{e.mas_corta}} <span class="num">(${{fmt(e.dist_corta)}})</span>`;
    return `<tr>
      <td>${{e.pos}}</td>
      <td><strong>${{e.equipo}}</strong></td>
      <td>${{e.fase === 'RECLASIFICACION' ? 'Reclasif.' : 'Clasif.'}}</td>
      <td class="region" style="color:${{color}}">${{e.region}}</td>
      <td>${{e.direccion || '—'}}</td>
      <td>${{lejana}}</td>
      <td>${{corta}}</td>
      <td class="num">${{fmt(e.media_regionalizado)}}</td>
      <td class="num">${{fmt(e.media_sin_region)}}</td>
    </tr>`;
  }}).join('');
}}

let startIdx = 0;
const hash = window.location.hash;
if (hash && hash.startsWith('#nivel-')) {{
  const nid = parseInt(hash.replace('#nivel-', ''), 10);
  const found = DATA.niveles.findIndex(n => n.id === nid);
  if (found >= 0) startIdx = found;
}}
document.querySelectorAll('.tab')[startIdx].classList.add('active');
renderNivel(startIdx);
</script>
</body>
</html>""",
        encoding="utf-8",
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=OUT_HTML)
    args = ap.parse_args()
    if not MAPEO_CSV.exists() or not MATRIZ_JSON.exists():
        print(
            "Falta mapeo/matriz. Corré:\n"
            "  python analysis/emparejar_clubes_federacion.py --geocodificar"
        )
        return 1
    path = generar(args.output)
    with NIVELES_JSON.open(encoding="utf-8") as f:
        payload = json.load(f)
    print(f"Informe: {path}")
    print(f"Datos: {NIVELES_JSON}")
    for n in payload["niveles"]:
        s = n["stats"]
        print(
            f"  {n['nombre']} ({n['rango']}): {n['n_equipos']} equipos · "
            f"reg={s['media_regionalizado_nivel']} · "
            f"sin_reg={s['media_sin_region_nivel']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
