# -*- coding: utf-8 -*-
"""
Extrae el árbol Categoría → Fase → Grupo desde competicion.aspx (GES Deportiva)
y genera JSON + HTML navegable. Misma jerarquía que usa FebambaScraper antes
de parsear ronda vía parsers/fases.py y parsers/grupos.py.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from mapeos.loader import cargar_mapeo_categorias
from parsers.fases import parsear_fase
from parsers.grupos import parsear_grupo
from utils.logger import get_logger
from utils.requester import hacer_solicitud

logger = get_logger("mapa_estructura_competencia")

BASE_GES = "https://competicionescabb.gesdeportiva.es"


def _categoria_canonica(cat_web: str, mapeo: dict[str, str]) -> str:
    if cat_web in mapeo:
        return mapeo[cat_web]
    for k, v in mapeo.items():
        if k.lower() == cat_web.lower():
            return v
    return cat_web


def _opciones_select(soup: BeautifulSoup, name: str) -> list[tuple[str, str]]:
    sel = soup.find("select", {"name": name})
    if not sel:
        return []
    out: list[tuple[str, str]] = []
    for opt in sel.find_all("option"):
        oid = opt.get("value")
        text = (opt.text or "").strip()
        if not oid or oid == "0" or "Seleccionar" in text:
            continue
        out.append((str(oid), text))
    return out


def extraer_arbol(
    url_competicion: str,
    anio: int,
    pausa_categoria_s: float = 1.0,
    pausa_fase_s: float = 0.5,
) -> dict[str, Any]:
    """
    Recorre DDLCategorias → DDLFases → DDLGrupos sin bajar partidos.

    Args:
        url_competicion: URL completa del torneo (incluye competencia=...).
        anio: Año lógico del torneo (p. ej. 2025) para parsear_fase/grupo.
        pausa_*: cortesías entre solicitudes HTTP.

    Returns:
        Diccionario serializable con metadatos y lista `categorias`.
    """
    mapeo_cat = cargar_mapeo_categorias()
    match = re.search(r"competencia=(\d+)", url_competicion, re.I)
    competencia_id = match.group(1) if match else "unknown"

    raw = hacer_solicitud(url_competicion)
    if not raw:
        logger.error("No se pudo cargar la página inicial: %s", url_competicion)
        return {
            "competencia_id": competencia_id,
            "url": url_competicion,
            "anio": anio,
            "categorias": [],
            "error": "fetch_failed",
        }

    soup = BeautifulSoup(raw, "html.parser")
    cats = _opciones_select(soup, "DDLCategorias")
    arbol_cats: list[dict[str, Any]] = []

    for cat_id, cat_web in cats:
        if cat_web.lower() == "mosquitos":
            logger.info("Omitiendo categoría Mosquitos")
            continue

        cat_mapa = _categoria_canonica(cat_web, mapeo_cat)
        url_cat = f"{url_competicion}&categoria={cat_id}"
        html_cat = hacer_solicitud(url_cat)
        if not html_cat:
            logger.warning("Sin respuesta para categoría %s", url_cat)
            time.sleep(pausa_categoria_s)
            continue
        soup_cat = BeautifulSoup(html_cat, "html.parser")
        fases = _opciones_select(soup_cat, "DDLFases")
        nodos_fases: list[dict[str, Any]] = []

        for fase_id, fase_text in fases:
            fase_parse_sin_grupo = parsear_fase(anio, fase_text, None)
            url_fase = f"{url_cat}&fase={fase_id}"
            html_fase = hacer_solicitud(url_fase)
            grupos_items: list[dict[str, Any]] = []
            if not html_fase:
                logger.warning("Sin respuesta para fase %s", url_fase)
            else:
                soup_fase = BeautifulSoup(html_fase, "html.parser")
                grupos = _opciones_select(soup_fase, "DDLGrupos")
                if not grupos:
                    grupos_items.append(
                        {
                            "grupo_id": None,
                            "grupo_texto": "(sin selector de grupo — vista única)",
                            "parseo_grupo": {},
                        }
                    )
                else:
                    for grupo_id, grupo_text in grupos:
                        gparse = parsear_grupo(anio, fase_text, grupo_text)
                        fase_parse = parsear_fase(anio, fase_text, grupo_text)
                        grupos_items.append(
                            {
                                "grupo_id": grupo_id,
                                "grupo_texto": grupo_text,
                                "parseo_fase": fase_parse,
                                "parseo_grupo": gparse,
                            }
                        )

            nodos_fases.append(
                {
                    "fase_id": fase_id,
                    "fase_texto": fase_text,
                    "parseo_fase": fase_parse_sin_grupo,
                    "grupos": grupos_items,
                }
            )
            time.sleep(pausa_fase_s)

        arbol_cats.append(
            {
                "categoria_id": cat_id,
                "categoria_web": cat_web,
                "categoria_canonica": cat_mapa,
                "fases": nodos_fases,
            }
        )
        time.sleep(pausa_categoria_s)

    return {
        "competencia_id": competencia_id,
        "url": url_competicion,
        "anio": anio,
        "categorias": arbol_cats,
    }


def _escape(s: str) -> str:
    return html_lib.escape(s, quote=True)


def escribir_html(arbol: dict[str, Any], ruta: Path) -> None:
    """Genera un árbol colapsable categoría → fase → grupos."""
    titulo = (
        f"Mapa estructura — competencia {arbol.get('competencia_id', '?')} "
        f"({arbol.get('anio', '')})"
    )
    bloques: list[str] = []
    for cat in arbol.get("categorias", []):
        cweb = cat.get("categoria_web", "")
        cmap = cat.get("categoria_canonica", "")
        cid = cat.get("categoria_id", "")
        inner_fases: list[str] = []
        for fase in cat.get("fases", []):
            ft = fase.get("fase_texto", "")
            fp = fase.get("parseo_fase", {})
            ronda = fp.get("ronda", "")
            fase_parse_txt = (
                f"fase={_escape(str(fp.get('fase', '')))}, "
                f"ronda={_escape(str(ronda))}, "
                f"nivel={_escape(str(fp.get('nivel', '')))}, "
                f"zona={_escape(str(fp.get('zona', '')))}"
            )
            inner_gr: list[str] = []
            for gr in fase.get("grupos", []):
                gt = gr.get("grupo_texto", "")
                fp_gr = gr.get("parseo_fase") or fp
                ronda_g = fp_gr.get("ronda", "")
                fase_g_txt = (
                    f"fase={_escape(str(fp_gr.get('fase', '')))}, "
                    f"ronda={_escape(str(ronda_g))}, "
                    f"nivel={_escape(str(fp_gr.get('nivel', '')))}, "
                    f"zona={_escape(str(fp_gr.get('zona', '')))}"
                )
                gp = gr.get("parseo_grupo") or {}
                gtxt = (
                    f"{fase_g_txt} · "
                    f"nivel={_escape(str(gp.get('nivel', '')))}, "
                    f"zona={_escape(str(gp.get('zona', '')))}, "
                    f"grupo={_escape(str(gp.get('grupo', '')))}"
                )
                inner_gr.append(
                    f"<li><span class=\"grupo\">{_escape(gt)}</span>"
                    f"<span class=\"meta\"> — {gtxt}</span></li>"
                )
            inner_fases.append(
                "<details class=\"fase\">"
                f"<summary><strong>{_escape(ft)}</strong>"
                f"<span class=\"meta\"> · {fase_parse_txt}</span></summary>"
                f"<ul class=\"grupos\">{''.join(inner_gr)}</ul>"
                "</details>"
            )
        bloques.append(
            "<details class=\"cat\" open>"
            f"<summary><strong>{_escape(cweb)}</strong> → "
            f"<em>{_escape(cmap)}</em> <span class=\"id\">id={_escape(str(cid))}</span>"
            "</summary>"
            f"<div class=\"fases\">{''.join(inner_fases)}</div>"
            "</details>"
        )

    src_url = _escape(str(arbol.get("url", "")))
    body = "\n".join(bloques)
    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(titulo)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem 1.5rem; line-height: 1.45;
      color: #1a1a1a; max-width: 56rem; }}
    h1 {{ font-size: 1.15rem; margin-bottom: 0.5rem; }}
    .src {{ font-size: 0.9rem; color: #444; margin-bottom: 1rem; word-break: break-all; }}
    .cat {{ margin: 0.75rem 0; border: 1px solid #ccc; border-radius: 6px; padding: 0.35rem; }}
    .fases {{ margin: 0.5rem 0 0 0.75rem; }}
    .fase {{ margin: 0.35rem 0; }}
    .grupos {{ margin: 0.25rem 0 0.5rem 1.25rem; }}
    .meta {{ font-size: 0.8rem; color: #555; font-weight: normal; }}
    .id {{ font-size: 0.75rem; color: #888; }}
    summary {{ cursor: pointer; }}
    .grupo {{ font-weight: 500; }}
  </style>
</head>
<body>
  <h1>{_escape(titulo)}</h1>
  <p class="src">Fuente: <a href="{src_url}">{src_url}</a></p>
  {body}
  <p class="meta" style="margin-top:1.5rem">Ronda/nivel/zona mostrados salen de
    <code>parsers/fases.py</code> y <code>parsers/grupos.py</code> (año {arbol.get("anio", "")}).</p>
</body>
</html>
"""
    ruta.write_text(doc, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Genera mapa Categoría→Fase→Grupo desde competicion.aspx"
    )
    ap.add_argument(
        "--competencia",
        type=str,
        default="1623",
        help="ID numérico de competencia (default: 1623 FORMATIVAS 2025)",
    )
    ap.add_argument(
        "--anio",
        type=int,
        default=2025,
        help="Año para parseo de fase/grupo (default: 2025)",
    )
    ap.add_argument(
        "--out-dir",
        type=str,
        default="outputs",
        help="Directorio de salida (default: outputs)",
    )
    args = ap.parse_args()
    url = f"{BASE_GES}/competicion.aspx?competencia={args.competencia}"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Extrayendo estructura desde %s (anio=%s)", url, args.anio)
    arbol = extraer_arbol(url, args.anio)
    stem = f"mapa_competencia_{arbol.get('competencia_id', args.competencia)}_{args.anio}"
    json_path = out_dir / f"{stem}.json"
    html_path = out_dir / f"{stem}.html"

    json_path.write_text(
        json.dumps(arbol, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    escribir_html(arbol, html_path)
    logger.info("Escrito %s y %s", json_path, html_path)


if __name__ == "__main__":
    main()
