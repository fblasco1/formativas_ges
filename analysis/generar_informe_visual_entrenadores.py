# -*- coding: utf-8 -*-
"""Genera informe HTML visual de entrenadores por categorías (temporada 2026)."""

from __future__ import annotations

import argparse
import csv
import html
import math
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent


def cargar_datos(combos_path: Path, listado_path: Path) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Tuple[str, int]], List[Tuple[str, int]], List[Tuple[str, str, int]], List[Tuple[str, str]]]:
    with open(combos_path, encoding="utf-8-sig", newline="") as f:
        combos = list(csv.DictReader(f))
    with open(listado_path, encoding="utf-8-sig", newline="") as f:
        listado = list(csv.DictReader(f))

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

    top = [
        (r["Combinacion"], int(r["Cantidad"]), int(r["N_Categorias"]))
        for r in combos
        if int(r["Cantidad"]) > 0 and int(r["N_Categorias"]) > 1
    ]
    top.sort(key=lambda x: (-x[1], x[0]))
    top = top[:15]

    seis = [
        (r["Entrenador"], r["Club"])
        for r in listado
        if r["Categorias_A_Cargo"].count(",") == 5
    ]

    return combos, listado, bucket_items, singles, top, seis


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
            f'<text x="0" y="{y + bar_h * 0.72}" fill="#334155" font-size="12" font-family="Segoe UI, sans-serif">{html.escape(label)}</text>'
        )
        lines.append(
            f'<rect x="{bar_x}" y="{y}" width="{w}" height="{bar_h}" rx="3" fill="#2563eb"/>'
        )
        lines.append(
            f'<text x="{bar_x + w + 8}" y="{y + bar_h * 0.72}" fill="#0f172a" font-size="12" font-weight="600" font-family="Segoe UI, sans-serif">{value}</text>'
        )
        y += bar_h + gap
    lines.append("</svg>")
    return "\n".join(lines)


def _donut_svg(buckets: List[tuple[str, int]], size: int = 220) -> str:
    total = sum(v for _, v in buckets) or 1
    colors = ["#2563eb", "#0891b2", "#059669", "#d97706", "#7c3aed", "#dc2626"]
    cx = cy = size // 2
    r = size * 0.36
    ir = r * 0.58
    start = -90
    parts: List[str] = [
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" aria-label="Distribución por cantidad de categorías">',
    ]
    legend_y = 12
    for i, (label, value) in enumerate(buckets):
        angle = 360 * value / total
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
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" fill="#0f172a" font-size="22" font-weight="700" font-family="Segoe UI, sans-serif">{total}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" fill="#64748b" font-size="11" font-family="Segoe UI, sans-serif">vínculos</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def cargar_combinaciones(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def generar_html(
    *,
    fecha_ini: str,
    fecha_fin: str,
    out_path: Path,
    combos_path: Path,
    listado_path: Path,
    partidos: int = 6010,
) -> None:
    combos, listado, bucket_items, singles, top, seis_cats = cargar_datos(combos_path, listado_path)
    activas = [r for r in combos if int(r["Cantidad"]) > 0]
    vinculos = len(listado)
    combos_activas = len(activas)
    seis = len(seis_cats)
    partidos_fmt = _fmt_int(partidos)
    colors = ["#2563eb", "#0891b2", "#059669", "#d97706", "#7c3aed", "#dc2626"]
    top_all = sorted(activas, key=lambda x: (-int(x["Cantidad"]), x["Combinacion"]))[:15]
    restantes = 63 - len(activas)

    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Entrenadores formativas 2026</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --paper: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --accent: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    .page {{
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 24px 48px;
    }}
    header {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 28px 32px;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .subtitle {{ color: var(--muted); font-size: 14px; margin: 0; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin: 24px 0;
    }}
    .stat {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 16px;
    }}
    .stat .n {{ font-size: 26px; font-weight: 700; color: var(--accent); }}
    .stat .l {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 20px;
    }}
    section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 22px 24px;
      margin-bottom: 20px;
    }}
    h2 {{
      margin: 0 0 6px;
      font-size: 17px;
      font-weight: 700;
    }}
    .caption {{
      margin: 0 0 16px;
      font-size: 12px;
      color: var(--muted);
    }}
    .legend {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 16px;
      font-size: 12px;
      margin-top: 8px;
    }}
    .legend span {{ display: flex; align-items: center; gap: 8px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
    tr:last-child td {{ border-bottom: none; }}
    .note {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 12px;
      color: #1e3a8a;
      margin-top: 12px;
    }}
    footer {{
      text-align: center;
      color: var(--muted);
      font-size: 11px;
      margin-top: 24px;
    }}
    @media print {{
      body {{ background: white; }}
      .page {{ max-width: none; padding: 0; }}
      section, header, .stat {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <h1>Entrenadores por club y categorías formativas</h1>
      <p class="subtitle">Temporada 2026 · Liga Federal Formativas · {fecha_ini} a {fecha_fin} · Fuente: argentina.basketball (compCats 5075–5080)</p>
      <p class="subtitle" style="margin-top:8px">Criterio: entrenador principal = quien más partidos dirigió en cada (club, categoría). Cada vínculo entrenador–club se cuenta una sola vez en su combinación exacta de categorías.</p>
    </header>

    <div class="stats">
      <div class="stat"><div class="n">{partidos_fmt}</div><div class="l">Partidos analizados</div></div>
      <div class="stat"><div class="n">{vinculos}</div><div class="l">Vínculos entrenador–club</div></div>
      <div class="stat"><div class="n">{combos_activas}</div><div class="l">Combinaciones con casos</div></div>
      <div class="stat"><div class="n">{seis}</div><div class="l">Con las 6 categorías</div></div>
    </div>

    <div class="grid-2">
      <section>
        <h2>Distribución por cantidad de categorías a cargo</h2>
        <p class="caption">Cantidad de entrenadores–club según cuántas categorías dirigen (conteo exclusivo).</p>
        <div style="display:flex;gap:20px;align-items:center">
          {_donut_svg(bucket_items)}
          <div class="legend">
            {''.join(f'<span><i class="dot" style="background:{colors[i % len(colors)]}"></i>{html.escape(l)} · {v}</span>' for i, (l, v) in enumerate(bucket_items))}
          </div>
        </div>
      </section>
      <section>
        <h2>Solo una categoría (6 grupos individuales)</h2>
        <p class="caption">Entrenadores–club que dirigen únicamente esa categoría.</p>
        {_bar_svg(singles, width=420)}
      </section>
    </div>

    <section>
      <h2>Combinaciones más frecuentes (top 15)</h2>
      <p class="caption">Solo combinaciones con cantidad &gt; 0. Cada entrenador–club aparece en una sola fila.</p>
      {_bar_svg([(r['Combinacion'], int(r['Cantidad'])) for r in top_all], width=900, bar_h=24, gap=8)}
    </section>

    <section>
      <h2>Entrenadores con las 6 categorías a cargo</h2>
      <p class="caption">PRE MINI, MINI, INFANTILES, CADETES, JUVENILES y LIGA PROXIMO en el mismo club.</p>
      <table>
        <thead><tr><th>Entrenador</th><th>Club</th><th>Categorías</th></tr></thead>
        <tbody>
          {''.join(f"<tr><td>{html.escape(e)}</td><td>{html.escape(c)}</td><td>PRE MINI, MINI, INFANTILES, CADETES, JUVENILES, LIGA PROXIMO</td></tr>" for e, c in seis_cats)}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Tabla completa de combinaciones activas ({len(activas)} de 63)</h2>
      <p class="caption">Las {restantes} combinaciones teóricas restantes tienen cantidad 0 en este período.</p>
      <table>
        <thead><tr><th>Combinación</th><th>Cantidad</th><th>N° categorías</th></tr></thead>
        <tbody>
          {''.join(f"<tr><td>{html.escape(r['Combinacion'])}</td><td>{r['Cantidad']}</td><td>{r['N_Categorias']}</td></tr>" for r in sorted(activas, key=lambda x:(-int(x['Cantidad']), x['Combinacion'])))}
        </tbody>
      </table>
      <div class="note">Importante: las cantidades no se suman entre filas. Un entrenador con 3 categorías cuenta solo en su combinación exacta, no en subgrupos más pequeños.</div>
    </section>

    <footer>Generado automáticamente · GES LNB y TNA · {fecha_ini} – {fecha_fin}</footer>
  </div>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Informe HTML -> {out_path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fecha-ini", default="2026-03-01")
    p.add_argument("--fecha-fin", default="2026-05-31")
    p.add_argument(
        "--combos",
        default=str(ROOT / "outputs" / "entrenadores" / "combinaciones_categorias_2026.csv"),
    )
    p.add_argument(
        "--listado",
        default=str(ROOT / "outputs" / "entrenadores" / "entrenadores_club_categorias_2026.csv"),
    )
    p.add_argument(
        "--partidos",
        type=int,
        default=6010,
        help="Partidos analizados (metadato del informe).",
    )
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
