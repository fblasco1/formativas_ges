# -*- coding: utf-8 -*-
"""
Informe comparativo de volumen y eficiencia de lanzamiento entre ligas formativas.

Por defecto compara:
  - Brasil CBI U15 Masc 2025 (Genius Sports)
  - España FEB Cadete U16 2025 (feb.es, temporada resumida)
  - Alemania JBBL U16 2025/26 (nbbl-basketball.de)
  - Serbia PF U15 Pioniri 2025/26 (dscore.live + kss-live.com)
  - Argentina LFF Cadetes U15 2025 (argentina.basketball)
  - Referencia Argentina 2024 ENEBA (FeBAMBA + LFF interior, valores aproximados)

Ejemplo:
  python analysis/generar_informe_comparativo_ligas.py
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
REF_JSON = ROOT / "data" / "referencia" / "eneba_febamba_lff_2024.json"
DOCS_INDEX = ROOT / "docs" / "index.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/"

METRICAS_VOLUMEN: List[Tuple[str, str, str]] = [
    ("pts_pp", "Puntos", "pts/partido"),
    ("t2_pp", "Tiros de 2", "2PA/partido"),
    ("t3_pp", "Triples", "3PA/partido"),
    ("tl_pp", "Tiros libres", "TLA/partido"),
]

METRICAS_EFICIENCIA: List[Tuple[str, str, str]] = [
    ("t2_pct", "2P%", "%"),
    ("t3_pct", "3P%", "%"),
    ("tl_pct", "TL%", "%"),
    ("fg_pct", "FG%", "%"),
    ("efg_pct", "eFG%", "%"),
    ("ts_pct", "TS%", "%"),
]

# Promedios de pts/partido por encima de este umbral suelen ser errores de carga (ej. FEB).
PTS_PP_OUTLIER = 120.0

LIGAS_DEFAULT = [
    {
        "id": "brasil",
        "nombre": "Brasil · CBI",
        "categoria": "U15 Masculino",
        "temporada": "2025",
        "equipos_label": "ventana 16–24 nov 2025",
        "fuente": "cbb.web.geniussports.com (comp 41761)",
        "csv": ROOT / "outputs" / "cbb" / "lanzamiento_cbi_u15_masc_2025.csv",
        "color": "#059669",
    },
    {
        "id": "feb",
        "nombre": "España · FEB",
        "categoria": "U16 Cadete Masculino",
        "temporada": "2025/26",
        "equipos_label": "16 equipos · final PLAY-OFF",
        "fuente": "feb.es (Campeonato de Clubes Cadete)",
        "csv": ROOT / "outputs" / "feb" / "lanzamiento_cespclubescadmasc_2025_todas.csv",
        "feb_fase_id": "-44960",
        "color": "#dc2626",
    },
    {
        "id": "jbbl",
        "nombre": "Alemania · JBBL",
        "categoria": "U16 Masculino",
        "temporada": "2025/26",
        "equipos_label": "16 equipos · Viertelfinal (PO)",
        "fuente": "nbbl-basketball.de / api.bbl.scb.world",
        "csv": ROOT / "outputs" / "jbbl" / "lanzamiento_equipos_jbbl_2025_playoff16.csv",
        "color": "#2563eb",
    },
    {
        "id": "serbia",
        "nombre": "Serbia · KSS",
        "categoria": "U15 Pioniri Masculino",
        "temporada": "2025/26",
        "equipos_label": "16 equipos · 36 partidos",
        "fuente": "new-api.dscore.live + kss-live.com",
        "csv": ROOT / "outputs" / "serbia" / "lanzamiento_u15_pioniri_2025.csv",
        "color": "#7c3aed",
    },
]

LIGAS_ARGENTINA = [
    {
        "id": "lff",
        "nombre": "Argentina · LFF",
        "categoria": "U15 Cadetes Masculino",
        "temporada": "2025",
        "equipos_label": "comparativa equipos",
        "fuente": "argentina.basketball (compCat 4643)",
        "csv": ROOT / "outputs" / "lff" / "lanzamiento_equipos_cadetes_masculino_2025.csv",
        "color": "#0284c7",
        "include_in_scatter": False,
    },
]

# Reglamento defensivo por competición. "permisividad" (0-3) ordena de defensa más
# individual/restrictiva (0) a más libre/colectiva (3), y alimenta el indicador visual.
REGLAMENTOS_DEFENSIVOS: List[Dict[str, Any]] = [
    {
        "pais": "España",
        "competicion": "FEB",
        "color": "#dc2626",
        "zona": "Permitida",
        "permisividad": 3,
        "resumen": "Defensa zonal totalmente permitida en torneos nacionales.",
        "detalle": (
            "Libre albedrío táctico: se admiten ayudas complejas, trampas 2 contra 1 y "
            "flotaciones profundas con colapso de la pintura."
        ),
    },
    {
        "pais": "Alemania",
        "competicion": "JBBL",
        "color": "#2563eb",
        "zona": "Prohibida",
        "permisividad": 2,
        "resumen": "Defensa zonal totalmente prohibida.",
        "detalle": (
            "Se permite la ayuda del lado débil y flotar, con una regla de permanencia en "
            "la pintura similar a los tres segundos defensivos de la NBA. Se puede doblar la marca."
        ),
    },
    {
        "pais": "Serbia",
        "competicion": "KSS",
        "color": "#7c3aed",
        "zona": "Prohibida",
        "permisividad": 1,
        "resumen": "Defensa zonal totalmente prohibida.",
        "detalle": (
            "Se permite la ayuda del lado débil, pero obligando al intercambio de marcas "
            "tras la rotación."
        ),
    },
    {
        "pais": "Brasil",
        "competicion": "CBI",
        "color": "#059669",
        "zona": "Permitida",
        "permisividad": 3,
        "resumen": "Defensa libre.",
        "detalle": (
            "Se admite la defensa zonal y las ayudas sin restricciones reglamentarias."
        ),
    },
    {
        "pais": "Argentina",
        "competicion": "CAB",
        "color": "#0284c7",
        "zona": "Permitida",
        "permisividad": 3,
        "resumen": "Reglas FIBA sin modificaciones.",
        "detalle": "Se aplica la normativa FIBA estándar, sin restricciones defensivas adicionales.",
    },
    {
        "pais": "Argentina",
        "competicion": "FeBAMBA",
        "color": "#ca8a04",
        "zona": "Prohibida",
        "permisividad": 0,
        "resumen": "Zonal prohibida; defensa a un brazo de distancia del defendido.",
        "detalle": (
            "El defensor debe ubicarse siempre a un brazo de distancia de su marca y solo "
            "puede ayudar cuando el defensor de la pelota la pierde de forma definitiva."
        ),
    },
]

# Volumen de entrenamiento del club tipo por competición.
ENTRENAMIENTOS: List[Dict[str, Any]] = [
    {
        "pais": "Serbia",
        "competicion": "KSS",
        "color": "#7c3aed",
        "carga": "Alta",
        "resumen": "Doble turno diario (mañana y tarde), los cinco días de la semana.",
        "detalle": (
            "Los clubes de mayor jerarquía sostienen doble turno de equipo los cinco días, con "
            "algún turno libre. Los equipos de menor grado mantienen el doble turno pero recortan "
            "uno o dos estímulos: conservan el entrenamiento de equipo y suman técnica individual "
            "opcional por la mañana o la tarde según el horario escolar."
        ),
    },
    {
        "pais": "España",
        "competicion": "FEB",
        "color": "#dc2626",
        "carga": "Alta",
        "resumen": "Doble turno diario, 4–5 veces por semana (equipos TOP).",
        "detalle": (
            "Los clubes de élite integran lo escolar con el entrenamiento, lo que habilita doble "
            "turno diario cuatro o cinco veces por semana."
        ),
    },
    {
        "pais": "Alemania",
        "competicion": "JBBL",
        "color": "#2563eb",
        "carga": "Alta",
        "resumen": "Doble turno diario, 4–5 veces por semana (equipos TOP).",
        "detalle": (
            "Al igual que España y Serbia, los planes de los equipos TOP integran escuela y "
            "entrenamiento, generando doble turno diario cuatro o cinco veces por semana."
        ),
    },
    {
        "pais": "Argentina",
        "competicion": "CAB / FeBAMBA",
        "color": "#0284c7",
        "carga": "Media-baja",
        "resumen": "Tres sesiones por semana de cancha + físico.",
        "detalle": (
            "Habitualmente se entrena tres veces por semana: 1.5 a 2 horas de cancha más una hora "
            "de físico. Los chicos suman trabajo extra en cancha por cuenta propia."
        ),
    },
    {
        "pais": "Brasil",
        "competicion": "CBI",
        "color": "#059669",
        "carga": "Sin dato",
        "resumen": "Sin información disponible.",
        "detalle": "No se encontró información confiable sobre la carga de entrenamiento del club tipo.",
    },
]


@dataclass
class EquipoPunto:
    nombre: str
    liga: str
    t3_pp: float
    t3_pct: float
    pts_pp: float = 0.0
    t2_pp: float = 0.0
    tl_pp: float = 0.0
    efg_pct: float = 0.0
    ts_pct: float = 0.0
    aprox: bool = False
    contexto: str = ""


@dataclass
class ResumenLiga:
    id: str
    nombre: str
    categoria: str
    temporada: str
    equipos_label: str
    fuente: str
    color: str
    n_equipos: int = 0
    n_equipos_filtrados: int = 0
    outliers_pts: List[Tuple[str, float]] = field(default_factory=list)
    medias: Dict[str, float] = field(default_factory=dict)
    equipos: List[EquipoPunto] = field(default_factory=list)
    include_in_scatter: bool = True
    metricas_parciales: bool = False
    nota: str = ""


def _float(val: object) -> Optional[float]:
    try:
        s = str(val or "").strip().replace(",", ".")
        if not s:
            return None
        return float(s)
    except ValueError:
        return None


def _filtrar_filas_liga(cfg: dict, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if cfg["id"] == "feb":
        fase_id = str(cfg.get("feb_fase_id", "-44960")).strip()
        filtradas = [r for r in rows if str(r.get("fase_id", "")).strip() == fase_id]
        if filtradas:
            return filtradas
    return rows


def cargar_liga(cfg: dict) -> ResumenLiga:
    path: Path = cfg["csv"]
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    rows = _filtrar_filas_liga(cfg, rows)

    outliers: List[Tuple[str, float]] = []
    rows_filtradas: List[Dict[str, str]] = []
    for r in rows:
        pts = _float(r.get("pts_pp"))
        if pts is not None and pts > PTS_PP_OUTLIER:
            outliers.append((r.get("equipo", ""), pts))
            continue
        rows_filtradas.append(r)

    res = ResumenLiga(
        id=cfg["id"],
        nombre=cfg["nombre"],
        categoria=cfg["categoria"],
        temporada=cfg["temporada"],
        equipos_label=cfg["equipos_label"],
        fuente=cfg["fuente"],
        color=cfg["color"],
        n_equipos=len(rows),
        n_equipos_filtrados=len(rows_filtradas),
        outliers_pts=sorted(outliers, key=lambda x: -x[1]),
        include_in_scatter=cfg.get("include_in_scatter", True),
    )
    if cfg["id"] in ("brasil", "feb", "jbbl", "serbia", "lff"):
        res.equipos_label = f"{len(rows_filtradas)} equipos · {cfg['equipos_label'].split(' · ', 1)[-1]}"

    keys = [m[0] for m in METRICAS_VOLUMEN + METRICAS_EFICIENCIA]
    for key in keys:
        vals = [_float(r.get(key)) for r in rows_filtradas]
        vals = [v for v in vals if v is not None]
        res.medias[key] = statistics.mean(vals) if vals else 0.0

    for r in rows_filtradas:
        t3_pp = _float(r.get("t3_pp"))
        t3_pct = _float(r.get("t3_pct"))
        if t3_pp is None or t3_pct is None:
            continue
        res.equipos.append(
            EquipoPunto(
                nombre=r.get("equipo", ""),
                liga=cfg["nombre"],
                t3_pp=t3_pp,
                t3_pct=t3_pct,
                pts_pp=_float(r.get("pts_pp")) or 0.0,
                t2_pp=_float(r.get("t2_pp")) or 0.0,
                tl_pp=_float(r.get("tl_pp")) or 0.0,
                efg_pct=_float(r.get("efg_pct")) or 0.0,
                ts_pct=_float(r.get("ts_pct")) or 0.0,
            )
        )
    return res


def _pct_desde_pp(intentados: float, anotados: float) -> float:
    return (anotados / intentados * 100.0) if intentados else 0.0


def cargar_referencia_febamba_2024(data: Dict[str, Any]) -> ResumenLiga:
    feb = data["promedios_agregados"]["febamba"]
    t3_pp = feb["t3_pp_intentados"]
    t3_pct = _pct_desde_pp(t3_pp, feb["t3_pp_anotados"])
    equipos: List[EquipoPunto] = []
    for eq, vals in data.get("doble_competencia_aprox_pp", {}).items():
        feb_pp = vals.get("feb_t3_pp")
        if feb_pp is None:
            continue
        equipos.append(
            EquipoPunto(
                nombre=eq,
                liga="Argentina · FeBAMBA (ref.)",
                t3_pp=float(feb_pp),
                t3_pct=t3_pct,
                aprox=True,
                contexto="3PA aprox. · 3P% = media agregada FeBAMBA",
            )
        )
    return ResumenLiga(
        id="febamba_ref",
        nombre="Argentina · FeBAMBA",
        categoria="U15 (referencia 2024)",
        temporada="2024",
        equipos_label=f"{len(equipos)} equipos · doble competencia (aprox.)",
        fuente=data["fuente"],
        color="#ca8a04",
        n_equipos=len(equipos),
        n_equipos_filtrados=len(equipos),
        medias={"t3_pp": t3_pp, "t3_pct": t3_pct},
        equipos=equipos,
        include_in_scatter=True,
        metricas_parciales=True,
        nota="Promedios agregados del trabajo ENEBA. 3PA por equipo: lectura visual del gráfico.",
    )


def cargar_referencia_lff_2024(data: Dict[str, Any]) -> ResumenLiga:
    lff = data["promedios_agregados"]["liga_federal_interior"]
    t3_pp = lff["t3_pp_intentados"]
    t3_pct_media = _pct_desde_pp(t3_pp, lff["t3_pp_anotados"])
    com = data.get("comunicaciones_detalle", {}).get("liga_federal", {})
    equipos: List[EquipoPunto] = []
    for eq, vals in data.get("doble_competencia_aprox_pp", {}).items():
        lff_pp = vals.get("lff_t3_pp")
        if lff_pp is None:
            continue
        aciertos_pp = vals.get("lff_t3_aciertos_pp")
        if eq == "COMUNICACIONES" and com:
            t3_pct = float(com.get("t3_pct", t3_pct_media))
            aprox = False
            ctx = "Comunicaciones — dato textual del documento"
        elif aciertos_pp is not None:
            t3_pct = _pct_desde_pp(float(lff_pp), float(aciertos_pp))
            aprox = True
            ctx = "3PA/3PM aprox. — lectura visual del gráfico"
        else:
            t3_pct = t3_pct_media
            aprox = True
            ctx = "3PA aprox. · 3P% = media agregada LFF interior"
        equipos.append(
            EquipoPunto(
                nombre=eq,
                liga="Argentina · LFF interior (ref.)",
                t3_pp=float(lff_pp),
                t3_pct=t3_pct,
                aprox=aprox,
                contexto=ctx,
            )
        )
    return ResumenLiga(
        id="lff_ref",
        nombre="Argentina · LFF interior",
        categoria="U15 (referencia 2024)",
        temporada="2024",
        equipos_label=f"{len(equipos)} equipos · doble competencia",
        fuente=data["fuente"],
        color="#ea580c",
        n_equipos=len(equipos),
        n_equipos_filtrados=len(equipos),
        medias={"t3_pp": t3_pp, "t3_pct": t3_pct_media},
        equipos=equipos,
        include_in_scatter=True,
        metricas_parciales=True,
        nota="Equipos del interior con doble competencia FeBAMBA+LFF. Valores aproximados salvo Comunicaciones.",
    )


def _scatter_3p_html(ligas: List[ResumenLiga], *, width: int = 920, height: int = 500) -> str:
    puntos: List[Tuple[EquipoPunto, str]] = []
    for l in ligas:
        if not l.include_in_scatter:
            continue
        for eq in l.equipos:
            puntos.append((eq, l.color))

    if not puntos:
        return "<p class=\"caption\">Sin datos de triples.</p>"

    pad_l, pad_b, pad_r, pad_t = 58, 52, 168, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_b - pad_t

    xs = [eq.t3_pp for eq, _ in puntos]
    ys = [eq.t3_pct for eq, _ in puntos]
    gmx = statistics.mean(xs) if xs else 0.0
    gmy = statistics.mean(ys) if ys else 0.0
    x_min = max(0.0, min(xs) - 2.0)
    x_max = max(xs) + 2.0
    y_min = max(0.0, min(ys) - 4.0)
    y_max = min(55.0, max(ys) + 4.0)
    if x_max <= x_min:
        x_max = x_min + 1.0
    if y_max <= y_min:
        y_max = y_min + 1.0

    def sx(x: float) -> float:
        return pad_l + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return pad_t + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    lines = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Dispersión 3PA vs 3P%">',
        f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" fill="#f8fafc" stroke="#e2e8f0"/>',
    ]

    # Rejilla ligera
    for i in range(5):
        gx = pad_l + plot_w * i / 4
        gy = pad_t + plot_h * i / 4
        lines.append(f'<line x1="{gx:.1f}" y1="{pad_t}" x2="{gx:.1f}" y2="{pad_t + plot_h}" stroke="#e2e8f0"/>')
        lines.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + plot_w}" y2="{gy:.1f}" stroke="#e2e8f0"/>')

    # Medias globales (líneas punteadas únicas)
    glx, gly = sx(gmx), sy(gmy)
    ref_color = "#64748b"
    lines.append(
        f'<line x1="{glx:.1f}" y1="{pad_t}" x2="{glx:.1f}" y2="{pad_t + plot_h}" '
        f'stroke="{ref_color}" stroke-width="1.5" stroke-dasharray="7,5" opacity="0.9"/>'
    )
    lines.append(
        f'<line x1="{pad_l}" y1="{gly:.1f}" x2="{pad_l + plot_w}" y2="{gly:.1f}" '
        f'stroke="{ref_color}" stroke-width="1.5" stroke-dasharray="7,5" opacity="0.9"/>'
    )

    # Equipos (tooltip interactivo vía JS)
    for eq, color in puntos:
        attrs = (
            f'data-team="{html.escape(eq.nombre, quote=True)}" '
            f'data-liga="{html.escape(eq.liga, quote=True)}" '
            f'data-t3pp="{eq.t3_pp:.2f}" data-t3pct="{eq.t3_pct:.1f}" '
            f'data-ptspp="{eq.pts_pp:.1f}" data-t2pp="{eq.t2_pp:.1f}" '
            f'data-tlpp="{eq.tl_pp:.1f}" data-efg="{eq.efg_pct:.1f}" data-ts="{eq.ts_pct:.1f}" '
            f'data-aprox="{"1" if eq.aprox else "0"}" '
            f'data-ctx="{html.escape(eq.contexto, quote=True)}"'
        )
        cx, cy = sx(eq.t3_pp), sy(eq.t3_pct)
        if eq.aprox:
            lines.append(
                f'<polygon class="scatter-dot" points="{cx:.1f},{cy - 6.5:.1f} {cx + 5.6:.1f},{cy:.1f} '
                f'{cx:.1f},{cy + 6.5:.1f} {cx - 5.6:.1f},{cy:.1f}" '
                f'fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="4,3" {attrs}/>'
            )
        else:
            lines.append(
                f'<circle class="scatter-dot" cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" '
                f'fill="{color}" fill-opacity="0.78" stroke="#fff" stroke-width="1" {attrs}/>'
            )

    # Ejes
    lines.append(
        f'<text x="{pad_l + plot_w / 2:.1f}" y="{height - 14}" text-anchor="middle" '
        f'fill="#334155" font-size="13" font-weight="600" font-family="Segoe UI, sans-serif">3PA / partido</text>'
    )
    lines.append(
        f'<text x="16" y="{pad_t + plot_h / 2:.1f}" text-anchor="middle" '
        f'fill="#334155" font-size="13" font-weight="600" font-family="Segoe UI, sans-serif" '
        f'transform="rotate(-90 16 {pad_t + plot_h / 2:.1f})">3P%</text>'
    )

    # Ticks X
    for i in range(5):
        val = x_min + (x_max - x_min) * i / 4
        gx = pad_l + plot_w * i / 4
        lines.append(
            f'<text x="{gx:.1f}" y="{pad_t + plot_h + 18}" text-anchor="middle" fill="#64748b" '
            f'font-size="11" font-family="Segoe UI, sans-serif">{val:.0f}</text>'
        )

    # Ticks Y
    for i in range(5):
        val = y_min + (y_max - y_min) * i / 4
        gy = pad_t + plot_h - plot_h * i / 4
        lines.append(
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" fill="#64748b" '
            f'font-size="11" font-family="Segoe UI, sans-serif">{val:.0f}%</text>'
        )

    # Leyenda
    ly = pad_t + 8
    lx = width - pad_r + 8
    lines.append(
        f'<text x="{lx}" y="{ly}" fill="#334155" font-size="12" font-weight="700" '
        f'font-family="Segoe UI, sans-serif">Referencia global</text>'
    )
    ly += 16
    lines.append(
        f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 28}" y2="{ly - 4}" '
        f'stroke="{ref_color}" stroke-width="1.5" stroke-dasharray="7,5"/>'
    )
    lines.append(
        f'<text x="{lx + 34}" y="{ly}" fill="#64748b" font-size="10" '
        f'font-family="Segoe UI, sans-serif">{gmx:.1f} 3PA · {gmy:.1f}%</text>'
    )
    ly += 22
    lines.append(
        f'<text x="{lx}" y="{ly}" fill="#334155" font-size="12" font-weight="700" '
        f'font-family="Segoe UI, sans-serif">Ligas</text>'
    )
    ly += 18
    for l in ligas:
        if not l.include_in_scatter:
            continue
        short = l.nombre.split(" · ")[1] if " · " in l.nombre else l.nombre
        lines.append(f'<circle cx="{lx + 6}" cy="{ly - 4}" r="5" fill="{l.color}"/>')
        lines.append(
            f'<text x="{lx + 18}" y="{ly}" fill="#334155" font-size="11" '
            f'font-family="Segoe UI, sans-serif">{html.escape(short)}</text>'
        )
        ly += 22
    if any(eq.aprox for eq, _ in puntos):
        ly += 4
        lx_d = lx + 6
        lines.append(
            f'<polygon points="{lx_d},{ly - 5:.1f} {lx_d + 5:.1f},{ly:.1f} {lx_d},{ly + 5:.1f} {lx_d - 5:.1f},{ly:.1f}" '
            f'fill="none" stroke="#64748b" stroke-width="1.5" stroke-dasharray="4,3"/>'
        )
        lines.append(
            f'<text x="{lx + 18}" y="{ly + 4}" fill="#64748b" font-size="10" '
            f'font-family="Segoe UI, sans-serif">Aprox. ENEBA 2024</text>'
        )

    lines.append("</svg>")
    svg = "\n".join(lines)
    return f"""<div class="scatter-chart" id="scatter-3p">
  {svg}
  <div class="scatter-tooltip" aria-hidden="true"></div>
</div>
<script>
(function () {{
  const chart = document.getElementById("scatter-3p");
  if (!chart) return;
  const tip = chart.querySelector(".scatter-tooltip");
  function showTip(dot, e) {{
    const liga = dot.dataset.liga.split(" · ").pop();
    let extra = "";
    if (dot.dataset.aprox === "1") extra = "<br><em>Aprox.</em>";
    if (dot.dataset.ctx) extra += "<br><span class=\\"muted\\">" + dot.dataset.ctx + "</span>";
    tip.innerHTML =
      "<strong>" + dot.dataset.team + "</strong><br>" +
      "<span class=\\"muted\\">" + liga + "</span><br>" +
      dot.dataset.t3pp + " 3PA · " + dot.dataset.t3pct + "% 3P" + extra + "<br>" +
      dot.dataset.ptspp + " pts · " + dot.dataset.t2pp + " 2PA · " + dot.dataset.tlpp + " TLA<br>" +
      "eFG " + dot.dataset.efg + "% · TS " + dot.dataset.ts + "%";
    tip.style.opacity = "1";
    moveTip(e);
  }}
  function moveTip(e) {{
    tip.style.left = (e.clientX + 14) + "px";
    tip.style.top = (e.clientY - 10) + "px";
  }}
  function hideTip() {{ tip.style.opacity = "0"; }}
  chart.querySelectorAll(".scatter-dot").forEach(function (dot) {{
    dot.addEventListener("mouseenter", function (e) {{ showTip(dot, e); }});
    dot.addEventListener("mousemove", moveTip);
    dot.addEventListener("mouseleave", hideTip);
  }});
}})();
</script>"""


def _bar_group_svg(
    ligas: List[ResumenLiga],
    metric_key: str,
    *,
    width: int = 640,
    bar_h: int = 22,
    gap: int = 8,
) -> str:
    items = []
    for l in ligas:
        if l.metricas_parciales and metric_key not in l.medias:
            continue
        label = l.nombre.split(" · ")[1] if " · " in l.nombre else l.nombre
        items.append((label, l.medias.get(metric_key, 0), l.color))
    max_v = max(v for _, v, _ in items) or 1
    height = len(items) * (bar_h + gap) + 16
    lines = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">',
    ]
    y = 8
    label_w = 100
    bar_x = label_w + 8
    bar_max = width - bar_x - 56
    for label, value, color in items:
        w = max(2, int(bar_max * value / max_v))
        lines.append(
            f'<text x="0" y="{y + bar_h * 0.72}" fill="#334155" font-size="12" font-family="Segoe UI, sans-serif">{html.escape(label)}</text>'
        )
        lines.append(f'<rect x="{bar_x}" y="{y}" width="{w}" height="{bar_h}" rx="2" fill="{color}"/>')
        fmt = f"{value:.1f}" if value >= 10 else f"{value:.2f}"
        lines.append(
            f'<text x="{bar_x + w + 6}" y="{y + bar_h * 0.72}" fill="#0f172a" font-size="12" font-weight="600" font-family="Segoe UI, sans-serif">{fmt}</text>'
        )
        y += bar_h + gap
    lines.append("</svg>")
    return "\n".join(lines)


def _tabla_comparativa(ligas: List[ResumenLiga]) -> str:
    rows_html = []
    for key, label, unit in METRICAS_VOLUMEN + METRICAS_EFICIENCIA:
        cells = [f"<td><strong>{html.escape(label)}</strong><br><span class=\"unit\">{html.escape(unit)}</span></td>"]
        vals: List[Optional[float]] = []
        for l in ligas:
            if l.metricas_parciales and key not in l.medias:
                vals.append(None)
            else:
                vals.append(l.medias.get(key, 0))
        comparables = [v for v in vals if v is not None]
        if not comparables:
            continue
        best = max(comparables) if key.endswith("_pp") or key in (
            "efg_pct", "ts_pct", "fg_pct", "t2_pct", "t3_pct", "tl_pct"
        ) else min(comparables)
        for v in vals:
            if v is None:
                cells.append('<td class="na">—</td>')
            else:
                fmt = f"{v:.1f}" if "pct" in key or v >= 10 else f"{v:.2f}"
                cls = ' class="best"' if abs(v - best) < 0.05 else ""
                cells.append(f"<td{cls}>{fmt}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    headers = "".join(
        f"<th>{html.escape(l.nombre)}<br><span class=\"sub\">{html.escape(l.categoria)} · {html.escape(l.temporada)}</span></th>"
        for l in ligas
    )
    return f"""
    <table class="compare">
      <thead><tr><th>Métrica</th>{headers}</tr></thead>
      <tbody>{"".join(rows_html)}</tbody>
    </table>
    """


def _nota_outliers(ligas: List[ResumenLiga]) -> str:
    items = []
    for l in ligas:
        for eq, pts in l.outliers_pts:
            items.append(f"<li><strong>{html.escape(l.nombre)}</strong> · {html.escape(eq)} ({pts:.1f} pts/partido)</li>")
    if not items:
        return ""
    return (
        '<div class="note warn">'
        f"<strong>Outliers excluidos</strong> (pts/partido &gt; {PTS_PP_OUTLIER:.0f}): "
        "no entran en medias de liga ni en el gráfico de triples. Suelen reflejar errores de carga en la fuente, "
        "no un ritmo real de juego."
        f"<ul>{''.join(items)}</ul></div>"
    )


def _badges_html(ligas: List[ResumenLiga]) -> str:
    return "".join(
        f'<span class="badge" style="border-color:{l.color};color:{l.color}">'
        f'{html.escape(l.nombre)} {html.escape(l.categoria.split()[0])}</span>'
        for l in ligas
    )


def _stats_cards_html(ligas: List[ResumenLiga]) -> str:
    cards = []
    for l in ligas:
        short = l.nombre.split(" · ")[0] if " · " in l.nombre else l.nombre
        cards.append(
            f"""
      <div class="stat" style="--accent:{l.color}">
        <div class="n">{l.medias.get('t3_pp', 0):.1f}</div>
        <div class="l">{html.escape(short)} · 3PA/partido (media equipos)</div>
        <div class="s">{l.medias.get('t3_pct', 0):.1f}% 3P · {html.escape(l.equipos_label)}</div>
      </div>"""
        )
    return "\n".join(cards)


def _bar_doble_competencia_svg(data: Dict[str, Any], *, width: int = 920) -> str:
    items = []
    for eq, vals in sorted(data.get("doble_competencia_aprox_pp", {}).items()):
        lff = vals.get("lff_t3_pp")
        feb = vals.get("feb_t3_pp")
        if lff is None and feb is None:
            continue
        items.append((eq, float(lff) if lff is not None else 0.0, float(feb) if feb is not None else 0.0))
    if not items:
        return "<p class=\"caption\">Sin datos de doble competencia.</p>"

    bar_h = 18
    gap = 10
    label_w = 130
    bar_x = label_w + 10
    bar_max = width - bar_x - 50
    max_v = max(max(lff, feb) for _, lff, feb in items) or 1
    height = len(items) * (bar_h * 2 + gap + 6) + 24
    color_lff = "#ea580c"
    color_feb = "#ca8a04"
    lines = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Doble competencia 3PA">']
    y = 12
    for eq, lff, feb in items:
        lines.append(
            f'<text x="0" y="{y + bar_h * 0.75}" fill="#334155" font-size="11" font-weight="600" '
            f'font-family="Segoe UI, sans-serif">{html.escape(eq)}</text>'
        )
        if lff > 0:
            w = max(2, int(bar_max * lff / max_v))
            lines.append(f'<rect x="{bar_x}" y="{y}" width="{w}" height="{bar_h}" rx="2" fill="{color_lff}"/>')
            lines.append(
                f'<text x="{bar_x + w + 4}" y="{y + bar_h * 0.75}" fill="#9a3412" font-size="10" '
                f'font-family="Segoe UI, sans-serif">{lff:.1f}</text>'
            )
        y += bar_h + 2
        if feb > 0:
            w = max(2, int(bar_max * feb / max_v))
            lines.append(f'<rect x="{bar_x}" y="{y}" width="{w}" height="{bar_h}" rx="2" fill="{color_feb}"/>')
            lines.append(
                f'<text x="{bar_x + w + 4}" y="{y + bar_h * 0.75}" fill="#854d0e" font-size="10" '
                f'font-family="Segoe UI, sans-serif">{feb:.1f}</text>'
            )
        y += bar_h + gap
    lx = bar_x
    ly = height - 8
    lines.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="8" fill="{color_lff}"/>')
    lines.append(f'<text x="{lx + 16}" y="{ly - 3}" font-size="10" fill="#64748b">LFF interior (aprox.)</text>')
    lines.append(f'<rect x="{lx + 150}" y="{ly - 10}" width="12" height="8" fill="{color_feb}"/>')
    lines.append(f'<text x="{lx + 166}" y="{ly - 3}" font-size="10" fill="#64748b">FeBAMBA (aprox.)</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def _tabla_doble_competencia(data: Dict[str, Any]) -> str:
    rows = []
    com = data.get("comunicaciones_detalle", {}).get("liga_federal", {})
    for eq, vals in sorted(data.get("doble_competencia_aprox_pp", {}).items()):
        lff_pp = vals.get("lff_t3_pp")
        lff_ac = vals.get("lff_t3_aciertos_pp")
        feb_pp = vals.get("feb_t3_pp")
        if eq == "COMUNICACIONES" and com:
            lff_pct = f'{com.get("t3_pct", "")}%'
            nota = "Comunicaciones: dato exacto (documento)"
        elif lff_ac is not None and lff_pp:
            lff_pct = f"{_pct_desde_pp(float(lff_pp), float(lff_ac)):.1f}%"
            nota = "Aprox."
        else:
            lff_pct = "—"
            nota = "Aprox. 3PA"
        rows.append(
            "<tr>"
            f"<td>{html.escape(eq)}</td>"
            f"<td>{lff_pp if lff_pp is not None else '—'}</td>"
            f"<td>{lff_ac if lff_ac is not None else '—'}</td>"
            f"<td>{lff_pct}</td>"
            f"<td>{feb_pp if feb_pp is not None else '—'}</td>"
            f"<td>{html.escape(nota)}</td>"
            "</tr>"
        )
    return f"""
    <table class="compare">
      <thead>
        <tr>
          <th>Equipo</th><th>LFF 3PA/pp</th><th>LFF 3PM/pp</th><th>LFF 3P%</th>
          <th>FeBAMBA 3PA/pp</th><th>Nota</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    """


def _section_argentina_2024(ref_data: Dict[str, Any], ligas_ref: List[ResumenLiga]) -> str:
    feb = next((l for l in ligas_ref if l.id == "febamba_ref"), None)
    lff = next((l for l in ligas_ref if l.id == "lff_ref"), None)
    agg = ref_data.get("promedios_agregados", {})
    return f"""
    <section>
      <h2>Argentina — referencia 2024 (ENEBA)</h2>
      <p class="caption">
        Datos de 2024 tomados del trabajo tesis ENEBA de Tomás Curi, que comparaba la reglamentación
        de FeBAMBA y la LFF del interior. Los rombos punteados en el gráfico de dispersión son estos equipos.
      </p>
      <div class="stats" style="grid-template-columns: repeat(2, 1fr);">
        <div class="stat" style="--accent:#ca8a04">
          <div class="n">{agg.get('febamba', {}).get('t3_pp_intentados', 0):.1f}</div>
          <div class="l">FeBAMBA · 3PA/partido (media agregada)</div>
          <div class="s">{agg.get('febamba', {}).get('t3_pp_anotados', 0):.2f} 3PM/pp · {(feb.medias.get('t3_pct', 0) if feb else 0):.1f}% 3P</div>
        </div>
        <div class="stat" style="--accent:#ea580c">
          <div class="n">{agg.get('liga_federal_interior', {}).get('t3_pp_intentados', 0):.1f}</div>
          <div class="l">LFF interior · 3PA/partido (media agregada)</div>
          <div class="s">{agg.get('liga_federal_interior', {}).get('t3_pp_anotados', 0):.2f} 3PM/pp · {lff.medias.get('t3_pct', 0) if lff else 0:.1f}% 3P</div>
        </div>
      </div>
      <h3 style="font-size:15px;margin:20px 0 8px;">Doble competencia — 3PA por partido</h3>
      <p class="caption">Barras por equipo: LFF interior (naranja) vs FeBAMBA (dorado).</p>
      {_bar_doble_competencia_svg(ref_data)}
    </section>
    """


def _section_reglamentos() -> str:
    escala = {
        0: ("Individual estricta", "#15803d"),
        1: ("Ayuda con intercambio", "#65a30d"),
        2: ("Ayuda colectiva acotada", "#d97706"),
        3: ("Defensa libre / zonal", "#dc2626"),
    }
    zona_badge = {
        "Permitida": ("Zonal permitida", "#fee2e2", "#b91c1c"),
        "Parcial": ("Zonal parcial", "#fef3c7", "#b45309"),
        "Prohibida": ("Zonal prohibida", "#dcfce7", "#15803d"),
    }
    cards = []
    for r in REGLAMENTOS_DEFENSIVOS:
        nivel_txt, nivel_color = escala[r["permisividad"]]
        z_txt, z_bg, z_fg = zona_badge[r["zona"]]
        pips = "".join(
            f'<span class="pip" style="background:{nivel_color if i <= r["permisividad"] else "#e2e8f0"}"></span>'
            for i in range(4)
        )
        cards.append(
            f"""
        <article class="rule-card" style="--accent:{r['color']}">
          <header class="rule-head">
            <div>
              <span class="rule-country">{html.escape(r['pais'])}</span>
              <span class="rule-comp">{html.escape(r['competicion'])}</span>
            </div>
            <span class="chip" style="background:{z_bg};color:{z_fg}">{html.escape(z_txt)}</span>
          </header>
          <p class="rule-summary">{html.escape(r['resumen'])}</p>
          <p class="rule-detail">{html.escape(r['detalle'])}</p>
          <div class="rule-scale" title="{html.escape(nivel_txt)}">
            <div class="pips">{pips}</div>
            <span class="rule-scale-label">{html.escape(nivel_txt)}</span>
          </div>
        </article>"""
        )
    return f"""
    <section>
      <h2>Reglamento defensivo por competición</h2>
      <p class="caption">
        El marco normativo condiciona cuánto espacio encuentra el lanzador exterior. Las competiciones
        que prohíben la zona y limitan las ayudas tienden a generar más tiros abiertos de media distancia
        y menos colapsos de la pintura; las que permiten zona y trampas premian el triple como respuesta
        al cierre interior. La barra inferior de cada tarjeta indica cuán colectiva es la defensa permitida.
      </p>
      <div class="rules-grid">{"".join(cards)}</div>
    </section>
    """


def _section_entrenamientos() -> str:
    carga_rank = {"Alta": 3, "Media-baja": 1, "Media": 2, "Sin dato": 0}
    carga_color = {
        "Alta": "#15803d",
        "Media": "#d97706",
        "Media-baja": "#ea580c",
        "Sin dato": "#94a3b8",
    }
    max_rank = 3
    rows = []
    for e in sorted(ENTRENAMIENTOS, key=lambda x: -carga_rank.get(x["carga"], 0)):
        rank = carga_rank.get(e["carga"], 0)
        color = carga_color.get(e["carga"], "#94a3b8")
        width = int(100 * rank / max_rank) if rank else 6
        rows.append(
            f"""
        <div class="train-row">
          <div class="train-label">
            <span class="train-country">{html.escape(e['pais'])}</span>
            <span class="train-comp">{html.escape(e['competicion'])}</span>
          </div>
          <div class="train-bar-wrap">
            <div class="train-bar" style="width:{width}%;background:{color}"></div>
            <span class="train-tag" style="color:{color}">{html.escape(e['carga'])}</span>
          </div>
          <p class="train-detail">{html.escape(e['detalle'])}</p>
        </div>"""
        )
    return f"""
    <section>
      <h2>Volumen de entrenamiento del club tipo</h2>
      <p class="caption">
        La carga semanal de práctica ayuda a interpretar las diferencias de volumen y eficiencia: más
        repeticiones técnicas y minutos de cancha se traducen en mayor capacidad para sostener un perfil
        de tiro exigente. La barra estima la intensidad relativa del club tipo de cada competición.
      </p>
      <div class="train-list">{"".join(rows)}</div>
    </section>
    """


def generar_html(
    ligas: List[ResumenLiga],
    out_path: Path,
    *,
    ref_data: Optional[Dict[str, Any]] = None,
    ligas_ref: Optional[List[ResumenLiga]] = None,
) -> None:
    ligas_ref = ligas_ref or []
    todas = ligas + ligas_ref
    n = len(todas)
    cols = min(max(n, 1), 4)
    titulo_ligas = " · ".join(l.nombre.split(" · ")[0] for l in ligas)
    _fuentes_unicas: List[str] = []
    for l in todas:
        if l.fuente not in _fuentes_unicas:
            _fuentes_unicas.append(l.fuente)
    fuentes = " · ".join(html.escape(f) for f in _fuentes_unicas)

    by_id = {l.id: l for l in todas}
    br = by_id.get("brasil", ligas[0])
    fe = by_id.get("feb", ligas[min(1, len(ligas) - 1)])
    de = by_id.get("jbbl", ligas[min(2, len(ligas) - 1)])
    rs = by_id.get("serbia")
    lff = by_id.get("lff")
    lff_ref = by_id.get("lff_ref")

    scatter_n = sum(l.n_equipos_filtrados for l in ligas if l.include_in_scatter)
    scatter_n += sum(l.n_equipos_filtrados for l in ligas_ref if l.include_in_scatter)
    section_arg = _section_argentina_2024(ref_data, ligas_ref) if ref_data and ligas_ref else ""
    insight_lff = ""
    if lff_ref and lff:
        insight_lff = (
            f" La referencia LFF interior 2024 (~{lff_ref.medias.get('t3_pp', 0):.0f} 3PA) "
            f"supera a LFF 2025 (~{lff.medias.get('t3_pp', 0):.0f} 3PA) en volumen de triples."
        )

    def _lider(metric: str) -> Tuple[str, float]:
        cand = [(l.nombre.split(" · ")[0], l.medias.get(metric, 0)) for l in ligas]
        return max(cand, key=lambda x: x[1]) if cand else ("", 0.0)

    lider_efg = _lider("efg_pct")
    lider_ts = _lider("ts_pct")
    lider_3p = _lider("t3_pct")
    insight_efic = (
        f"{html.escape(lider_efg[0])} encabeza la eficiencia de campo efectiva (~{lider_efg[1]:.1f}% eFG) y el acierto "
        f"de triple (~{lider_3p[1]:.1f}% 3P), por delante de España (~{fe.medias.get('t3_pct', 0):.1f}% 3P), "
        f"Brasil (~{br.medias.get('t3_pct', 0):.1f}% 3P) y Alemania (~{de.medias.get('t3_pct', 0):.1f}% 3P). "
        f"En porcentaje de tiro real (TS%), {html.escape(lider_ts[0])} marca el tope con ~{lider_ts[1]:.1f}%."
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Comparativa ligas formativas — {html.escape(titulo_ligas)}</title>
  <style>
    :root {{
      --bg: #eef2f7; --paper: #ffffff; --text: #0f172a; --muted: #64748b;
      --line: #e2e8f0; --brand: #1d4ed8; --brand-2: #0ea5e9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}
    .page {{ max-width: 1140px; margin: 0 auto; padding: 36px 24px 56px; }}
    header.hero {{
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #1d4ed8 100%);
      color: #f8fafc; border-radius: 18px; padding: 38px 40px;
      margin-bottom: 26px; box-shadow: 0 18px 40px -22px rgba(30,58,138,.7);
    }}
    header.hero .eyebrow {{
      text-transform: uppercase; letter-spacing: .16em; font-size: 11px;
      font-weight: 700; color: #93c5fd; margin: 0 0 10px;
    }}
    h1 {{ margin: 0 0 12px; font-size: 30px; font-weight: 800; letter-spacing: -0.025em; line-height: 1.15; }}
    .subtitle {{ color: #cbd5e1; font-size: 15px; margin: 0; max-width: 760px; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; }}
    .badge {{
      font-size: 11px; font-weight: 600; padding: 5px 12px; border-radius: 999px;
      border: 1px solid rgba(255,255,255,.28); color: #e2e8f0;
      background: rgba(255,255,255,.08); backdrop-filter: blur(4px);
    }}
    .stats {{ display: grid; grid-template-columns: repeat({cols}, 1fr); gap: 14px; margin: 0 0 26px; }}
    .stat {{
      background: var(--paper); border: 1px solid var(--line); border-radius: 14px;
      padding: 18px; border-top: 4px solid var(--accent, #2563eb);
      box-shadow: 0 8px 22px -18px rgba(15,23,42,.4); transition: transform .15s ease, box-shadow .15s ease;
    }}
    .stat:hover {{ transform: translateY(-2px); box-shadow: 0 14px 28px -18px rgba(15,23,42,.5); }}
    .stat .n {{ font-size: 30px; font-weight: 800; letter-spacing: -0.02em; }}
    .stat .l {{ font-size: 12px; color: var(--text); font-weight: 600; margin-top: 6px; }}
    .stat .s {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}
    section {{
      background: var(--paper); border: 1px solid var(--line); border-radius: 16px;
      padding: 26px 28px; margin-bottom: 22px; box-shadow: 0 10px 26px -22px rgba(15,23,42,.35);
    }}
    h2 {{
      margin: 0 0 8px; font-size: 19px; font-weight: 700; letter-spacing: -0.01em;
      display: flex; align-items: center; gap: 10px;
    }}
    h2::before {{
      content: ""; width: 6px; height: 20px; border-radius: 3px;
      background: linear-gradient(180deg, var(--brand), var(--brand-2));
    }}
    h3 {{ font-size: 15px; font-weight: 700; }}
    .caption {{ margin: 0 0 18px; font-size: 13px; color: var(--muted); max-width: 880px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    .scatter-wrap {{ overflow-x: auto; }}
    .scatter-chart {{ position: relative; }}
    .scatter-dot {{ cursor: pointer; transition: fill-opacity .1s ease; }}
    .scatter-dot:hover {{ fill-opacity: 1; stroke-width: 1.5; }}
    .scatter-tooltip {{
      position: fixed; pointer-events: none; z-index: 100;
      background: #0f172a; color: #f8fafc; font-size: 12px; line-height: 1.5;
      padding: 9px 12px; border-radius: 10px; box-shadow: 0 8px 22px rgba(15,23,42,.35);
      opacity: 0; transition: opacity .12s ease; max-width: 250px;
    }}
    .scatter-tooltip .muted {{ color: #94a3b8; font-size: 11px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 11px 9px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
    th .sub, td .unit {{ font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--muted); font-size: 11px; }}
    tr:last-child td {{ border-bottom: none; }}
    table.compare tbody tr:hover td {{ background: #f8fafc; }}
    table.compare td:not(:first-child) {{ text-align: center; font-variant-numeric: tabular-nums; }}
    td.best {{ background: #ecfdf5; font-weight: 700; color: #047857; }}
    td.na {{ color: #cbd5e1; }}
    .note {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; padding: 13px 15px; font-size: 12px; color: #1e3a8a; margin-top: 14px; }}
    .note.warn {{ background: #fff7ed; border-color: #fdba74; color: #9a3412; }}
    .note ul {{ margin: 8px 0 0 18px; padding: 0; }}
    .insight {{
      border-left: 4px solid var(--brand); background: #f8faff; border-radius: 0 8px 8px 0;
      padding: 12px 16px; margin: 18px 0 0; font-size: 13px; color: #1e293b;
    }}
    /* Reglamentos */
    .rules-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
    .rule-card {{
      border: 1px solid var(--line); border-radius: 14px; padding: 18px 18px 16px;
      border-top: 4px solid var(--accent); background: #fdfdff;
      display: flex; flex-direction: column; gap: 8px;
    }}
    .rule-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
    .rule-country {{ font-size: 15px; font-weight: 800; }}
    .rule-comp {{ font-size: 12px; color: var(--muted); margin-left: 6px; font-weight: 600; }}
    .chip {{ font-size: 10px; font-weight: 700; padding: 4px 9px; border-radius: 999px; white-space: nowrap; }}
    .rule-summary {{ margin: 0; font-size: 13px; font-weight: 600; color: #0f172a; }}
    .rule-detail {{ margin: 0; font-size: 12.5px; color: var(--muted); flex: 1; }}
    .rule-scale {{ display: flex; align-items: center; gap: 10px; margin-top: 6px; }}
    .pips {{ display: flex; gap: 4px; }}
    .pip {{ width: 22px; height: 6px; border-radius: 3px; }}
    .rule-scale-label {{ font-size: 11px; color: var(--muted); font-weight: 600; }}
    /* Entrenamientos */
    .train-list {{ display: flex; flex-direction: column; gap: 14px; }}
    .train-row {{
      display: grid; grid-template-columns: 160px 1fr; gap: 8px 18px; align-items: center;
      padding-bottom: 14px; border-bottom: 1px solid var(--line);
    }}
    .train-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
    .train-label {{ display: flex; flex-direction: column; }}
    .train-country {{ font-size: 14px; font-weight: 800; }}
    .train-comp {{ font-size: 11px; color: var(--muted); font-weight: 600; }}
    .train-bar-wrap {{ display: flex; align-items: center; gap: 10px; }}
    .train-bar {{ height: 12px; border-radius: 6px; min-width: 6px; transition: width .3s ease; }}
    .train-tag {{ font-size: 12px; font-weight: 700; white-space: nowrap; }}
    .train-detail {{ grid-column: 2; margin: 0; font-size: 12.5px; color: var(--muted); }}
    footer {{ text-align: center; color: var(--muted); font-size: 11px; margin-top: 28px; line-height: 1.6; }}
    @media (max-width: 900px) {{
      .stats, .grid-2 {{ grid-template-columns: 1fr !important; }}
      .train-row {{ grid-template-columns: 1fr; }}
      .train-detail {{ grid-column: 1; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <p class="eyebrow">Scouting formativo · Tiro exterior</p>
      <h1>El triple en la formación: seis competiciones bajo la misma lupa</h1>
      <p class="subtitle">
        Volumen (intentos de triple por partido) y eficiencia (3P%) en categorías U15 y U16 masculinas,
        cruzados con el marco reglamentario y la carga de entrenamiento de cada país. Temporadas 2024 a 2025/26.
      </p>
      <div class="badges">{_badges_html(todas)}</div>
    </header>

    <div class="stats">{_stats_cards_html(todas)}</div>

    <section>
      <h2>Mapa de dispersión — volumen vs eficiencia de triple</h2>
      <p class="caption">
        Cada punto es un equipo (los 16 finalistas de cada liga internacional). El eje horizontal mide
        cuántos triples intenta por partido y el vertical su acierto. Los rombos punteados corresponden a la
        referencia argentina 2024 (trabajo ENEBA). Las líneas punteadas marcan la media global de los
        {scatter_n} equipos representados generando cuadrantes: arriba-derecha, alta eficiencia y alto volumen;
        abajo-derecha, baja eficiencia y alto volumen; arriba-izquierda, alta eficiencia y bajo volumen; y
        abajo-izquierda, baja eficiencia y bajo volumen. Pasá el cursor sobre un punto para ver el detalle.
      </p>
      <div class="scatter-wrap">{_scatter_3p_html(todas)}</div>
    </section>

    <section>
      <h2>Tabla comparativa de métricas</h2>
      <p class="caption">
        Promedio simple entre los equipos de cada liga. La celda resaltada señala el mejor valor de cada fila.
        Las referencias argentinas de 2024 solo aportan datos de triple, por lo que el resto de métricas figura como «—».
      </p>
      {_tabla_comparativa(todas)}
      <div class="note">
        <strong>Nota metodológica.</strong> Brasil, Serbia y Argentina compiten en U15; España y Alemania en U16.
        En todas las ligas comparamos los <strong>16 equipos finalistas</strong> de su torneo. Debido a la pérdida
        de acceso a la base de datos de GES Argentina, se tomaron datos de 2024 de un trabajo tesis ENEBA que
        buscaba comparar cómo variaba la reglamentación entre FeBAMBA y la LFF del interior, realizado por Tomás Curi.
      </div>
      {_nota_outliers(ligas)}
    </section>

    {section_arg}

    {_section_reglamentos()}

    {_section_entrenamientos()}

    <section>
      <h2>Volumen de juego</h2>
      <p class="caption">Intentos por partido, promediados entre los equipos de cada liga.</p>
      <div class="grid-2">
        <div><p class="caption">Puntos anotados</p>{_bar_group_svg(todas, "pts_pp")}</div>
        <div><p class="caption">Tiros de 2 intentados</p>{_bar_group_svg(todas, "t2_pp")}</div>
        <div><p class="caption">Triples intentados</p>{_bar_group_svg(todas, "t3_pp")}</div>
        <div><p class="caption">Tiros libres intentados</p>{_bar_group_svg(todas, "tl_pp")}</div>
      </div>
      <div class="insight">
        España encabeza el volumen de triples (~{fe.medias.get('t3_pp', 0):.0f} 3PA) por delante de Alemania (~{de.medias.get('t3_pp', 0):.0f})
        {f", Serbia (~{rs.medias.get('t3_pp', 0):.0f})" if rs else ""} y Brasil (~{br.medias.get('t3_pp', 0):.0f}) en la ventana analizada.{insight_lff}
      </div>
    </section>

    <section>
      <h2>Eficiencia de tiro</h2>
      <p class="caption">Porcentajes medios entre los equipos de cada liga.</p>
      <div class="grid-2">
        <div><p class="caption">3P%</p>{_bar_group_svg(todas, "t3_pct")}</div>
        <div><p class="caption">eFG%</p>{_bar_group_svg(todas, "efg_pct")}</div>
        <div><p class="caption">TS%</p>{_bar_group_svg(todas, "ts_pct")}</div>
        <div><p class="caption">TL%</p>{_bar_group_svg(todas, "tl_pct")}</div>
      </div>
      <div class="insight">{insight_efic}</div>
    </section>

    <footer>
      Fuentes: {fuentes}
    </footer>
  </div>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")


def publicar_docs(out_path: Path) -> Path:
    """Copia el informe a docs/index.html para GitHub Pages."""
    DOCS_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOCS_INDEX.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    return DOCS_INDEX


def main() -> int:
    p = argparse.ArgumentParser(description="Informe comparativo ligas formativas")
    p.add_argument(
        "--output",
        default=str(ROOT / "outputs" / "comparativa" / "informe_ligas_u15_u16_2025.html"),
    )
    p.add_argument("--brasil", default=str(LIGAS_DEFAULT[0]["csv"]))
    p.add_argument("--feb", default=str(LIGAS_DEFAULT[1]["csv"]))
    p.add_argument("--jbbl", default=str(LIGAS_DEFAULT[2]["csv"]))
    p.add_argument("--serbia", default=str(LIGAS_DEFAULT[3]["csv"]))
    p.add_argument("--referencia", default=str(REF_JSON))
    p.add_argument("--sin-serbia", action="store_true", help="Excluir Serbia del informe")
    p.add_argument("--sin-argentina", action="store_true", help="Excluir la referencia ENEBA 2024")
    p.add_argument(
        "--con-lff-2025",
        action="store_true",
        help="Incluir además la LFF Cadetes 2025 (por defecto solo se muestra la referencia 2024)",
    )
    p.add_argument(
        "--lff",
        default=str(LIGAS_ARGENTINA[0]["csv"]),
        help="CSV de LFF 2025 (solo se usa con --con-lff-2025)",
    )
    p.add_argument(
        "--publicar",
        action="store_true",
        help=f"Copia el informe a docs/index.html para GitHub Pages ({PUBLIC_URL})",
    )
    args = p.parse_args()

    cfgs = [
        {**LIGAS_DEFAULT[0], "csv": Path(args.brasil)},
        {**LIGAS_DEFAULT[1], "csv": Path(args.feb)},
        {**LIGAS_DEFAULT[2], "csv": Path(args.jbbl)},
    ]
    if not args.sin_serbia:
        cfgs.append({**LIGAS_DEFAULT[3], "csv": Path(args.serbia)})
    if args.con_lff_2025:
        cfgs.append({**LIGAS_ARGENTINA[0], "csv": Path(args.lff)})

    for cfg in cfgs:
        if not cfg["csv"].exists():
            print(f"Falta CSV: {cfg['csv']}")
            return 1

    ligas = [cargar_liga(c) for c in cfgs]

    ref_data: Optional[Dict[str, Any]] = None
    ligas_ref: List[ResumenLiga] = []
    if not args.sin_argentina:
        ref_path = Path(args.referencia)
        if ref_path.exists():
            with ref_path.open(encoding="utf-8") as f:
                ref_data = json.load(f)
            ligas_ref = [
                cargar_referencia_febamba_2024(ref_data),
                cargar_referencia_lff_2024(ref_data),
            ]
        else:
            print(f"Aviso: sin referencia 2024 ({ref_path})")

    out = Path(args.output)
    generar_html(ligas, out, ref_data=ref_data, ligas_ref=ligas_ref)
    print(f"Informe generado: {out}")
    if args.publicar:
        docs = publicar_docs(out)
        print(f"Publicado en: {docs}")
        print(f"Link (GitHub Pages): {PUBLIC_URL}")
    for l in ligas + ligas_ref:
        print(f"  {l.nombre}: {l.n_equipos} equipos, {l.medias.get('t3_pp', 0):.1f} 3PA/partido")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
