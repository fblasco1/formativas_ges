# -*- coding: utf-8 -*-
"""
Informe HTML — FeBAMBA 2024 vs Liga Federal Formativa U15 interior (referencia ENEBA).

Usa datos de data/referencia/eneba_febamba_lff_2024.json (extraídos del .docx).

  python analysis/generar_informe_febamba_lff_2024.py
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_JSON = ROOT / "data" / "referencia" / "eneba_febamba_lff_2024.json"


def _html_tabla_promedios(data: dict) -> str:
    feb = data["promedios_agregados"]["febamba"]
    lff = data["promedios_agregados"]["liga_federal_interior"]
    rows = [
        ("FeBAMBA U15", feb["t3_pp_intentados"], feb["t3_pp_anotados"]),
        ("LFF interior U15", lff["t3_pp_intentados"], lff["t3_pp_anotados"]),
        ("LFF interior (gráfico equipos sel.)", lff["t3_pp_intentados_alt"], lff["t3_pp_anotados"]),
        ("FeBAMBA (gráfico equipos sel.)", feb["t3_pp_intentados_alt"], feb["t3_pp_anotados"]),
    ]
    trs = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{a:.2f}</td><td>{m:.2f}</td></tr>"
        for n, a, m in rows
    )
    return f"""
    <table>
      <thead><tr><th>Grupo</th><th>3PA/partido</th><th>3PM/partido</th></tr></thead>
      <tbody>{trs}</tbody>
    </table>
    """


def _html_tabla_doble(data: dict) -> str:
    rows = []
    com = data.get("comunicaciones_detalle", {}).get("liga_federal", {})
    if com:
        rows.append(
            (
                "COMUNICACIONES",
                f"{com.get('t3_pp', '')}",
                f"{com.get('t3_aciertos_pp', '')}",
                f"{com.get('t3_pct', '')}%",
                "565 tot. / 117 ac. (FeBAMBA, partidos no indicados)",
            )
        )
    for eq, vals in sorted(data.get("doble_competencia_aprox_pp", {}).items()):
        if eq == "COMUNICACIONES":
            continue
        rows.append(
            (
                eq,
                str(vals.get("lff_t3_pp") or "—"),
                str(vals.get("lff_t3_aciertos_pp") or "—"),
                "—",
                f"FeBAMBA ~{vals.get('feb_t3_pp') or '—'} 3PA/pp (aprox.)",
            )
        )
    trs = "".join(
        f"<tr><td>{html.escape(r[0])}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{html.escape(r[4])}</td></tr>"
        for r in rows
    )
    return f"""
    <table>
      <thead>
        <tr><th>Equipo</th><th>LFF 3PA/pp</th><th>LFF 3PM/pp</th><th>LFF 3P%</th><th>FeBAMBA (notas)</th></tr>
      </thead>
      <tbody>{trs}</tbody>
    </table>
    """


def generar_html(data: dict, img_dir: Path) -> str:
    imgs = ""
    for name in ["image2.png", "image3.png", "image4.png"]:
        p = img_dir / name
        if p.exists():
            rel = p.relative_to(ROOT).as_posix()
            imgs += f'<figure><img src="../{rel}" alt="{name}" style="max-width:100%"/><figcaption>{html.escape(name)}</figcaption></figure>'

    equipos_lff = ", ".join(html.escape(e) for e in data["equipos_liga_federal_u15_2024"])
    equipos_feb = ", ".join(html.escape(e) for e in data["equipos_febamba_2024"])

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <title>FeBAMBA vs LFF U15 — referencia 2024 (ENEBA)</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 2rem; color: #1e293b; max-width: 1100px; }}
    h1 {{ color: #0f172a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: #f1f5f9; }}
    .nota {{ background: #fffbeb; border-left: 4px solid #f59e0b; padding: 1rem; margin: 1rem 0; }}
    figure {{ margin: 1.5rem 0; }}
  </style>
</head>
<body>
  <h1>FeBAMBA 2024 vs Liga Federal Formativa U15 (interior)</h1>
  <p><strong>Fuente:</strong> {html.escape(data["fuente"])}</p>
  <p>{html.escape(data["tema"])}</p>

  <div class="nota">
    <strong>Contexto:</strong> estos datos se usan como referencia histórica porque el acceso
    automatizado a estadísticas de LFF U15 2024 no está disponible hoy. Los valores por equipo
    del gráfico de doble competencia son aproximados (lectura visual), salvo Comunicaciones
    que tiene cifras textuales en el documento.
  </div>

  <h2>Promedios de triples (3PA / 3PM por partido)</h2>
  {_html_tabla_promedios(data)}

  <h2>Equipos interior — Liga Federal Formativa U15 (2024)</h2>
  <p>{equipos_lff}</p>

  <h2>Equipos FeBAMBA U15 (2024)</h2>
  <p>{equipos_feb}</p>

  <h2>Doble competencia (FeBAMBA + LFF)</h2>
  {_html_tabla_doble(data)}

  <h2>Gráficos del documento</h2>
  {imgs}
</body>
</html>
"""


def main() -> int:
    p = argparse.ArgumentParser(description="Informe FeBAMBA vs LFF 2024 (referencia ENEBA)")
    p.add_argument(
        "--output",
        default=str(ROOT / "outputs" / "lff" / "informe_febamba_lff_2024.html"),
    )
    args = p.parse_args()

    with REF_JSON.open(encoding="utf-8") as f:
        data = json.load(f)

    img_dir = ROOT / "outputs" / "lff" / "doc_eneba_2024"
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generar_html(data, img_dir), encoding="utf-8")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
