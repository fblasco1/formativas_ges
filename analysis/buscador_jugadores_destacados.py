# -*- coding: utf-8 -*-
"""
Buscador LOCAL de jugadores destacados por estadísticas (FORMATIVAS GES 2015).

Genera una página HTML autocontenida con una tabla de jugadores buscable,
filtrable y ordenable, basada en PROMEDIOS por partido, para las categorías:

  U13 = INFANTILES MASCULINO   (id_categoria 5078)
  U15 = CADETES MASCULINO      (id_categoria 5077)
  U17 = JUVENILES MASCULINO    (id_categoria 5076)
  U21 = LIGA PROXIMO MASCULINO (id_categoria 5075)

ESTO ES LOCAL: el HTML se guarda en ``outputs/buscador/`` y NO se publica en
docs/ ni se comitea.

Ejemplos (Windows PowerShell):
  .venv\\Scripts\\python.exe analysis/buscador_jugadores_destacados.py --progress
  .venv\\Scripts\\python.exe analysis/buscador_jugadores_destacados.py --desde-cache
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.partido import parse_boxscore_html, parse_ficha_jugador_html
from ingest.febamba.mini_masc_regla_plantilla import parse_minutos_a_segundos
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider

from analysis.buscador_metrics import (
    PERFILES,
    PERFIL_DESCRIPCIONES,
    PERFIL_INSUFICIENTE,
    enriquecer_jugadores,
)

ID_COMPETENCIA = 2015

# edad -> metadatos GES de la categoría (solo para este buscador).
CATEGORIAS: Dict[str, Dict[str, object]] = {
    "U13": {"nombre_ges": "INFANTILES MASCULINO", "id_categoria": 5078},
    "U15": {"nombre_ges": "CADETES MASCULINO", "id_categoria": 5077},
    "U17": {"nombre_ges": "JUVENILES MASCULINO", "id_categoria": 5076},
    "U21": {"nombre_ges": "LIGA PROXIMO MASCULINO", "id_categoria": 5075},
}

OUT_DIR = ROOT / "outputs" / "buscador"
OUT_HTML = OUT_DIR / "buscador_jugadores.html"
BOX_FULL_CACHE = OUT_DIR / "boxscores_full.json"
PARTIDOS_CACHE = OUT_DIR / "partidos.json"
FICHA_CACHE = OUT_DIR / "jugadores_ficha.json"

# Publicación cifrada (GitHub Pages, branch estadisticas).
DOCS_HTML = ROOT / "docs" / "buscador_jugadores.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/buscador_jugadores.html"

# Clave localStorage para lista de fichajes (personalizar por club).
CLUB_SCOUTING_KEY = "scouting_formativas_2026"

_PERFIL_CSS_MAP = {
    "Especialista 3&D": "perfil-Especialista-3-D",
    "Protector de Aro": "perfil-Protector-de-Aro",
    "Base Conductor": "perfil-Base-Conductor",
    "Anotador de Volumen": "perfil-Anotador-de-Volumen",
    "Generador Perimetral": "perfil-Generador-Perimetral",
    "Interno de Rol": "perfil-Interno-de-Rol",
    PERFIL_INSUFICIENTE: "perfil-Muestra-insuficiente",
}

# Parámetros de cifrado (deben coincidir con el JS de Web Crypto).
PBKDF2_ITER = 200000
PBKDF2_DKLEN = 32  # AES-256

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def _load_widget_key() -> str:
    with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return 0


def normalizar_nombre(nombre: str) -> str:
    """Mayúsculas, sin acentos, sin espacios extra (clave de jugador)."""
    nfkd = unicodedata.normalize("NFKD", nombre or "")
    base = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(base.upper().split())


# --------------------------------------------------------------------------- #
# Recolección de partidos COMPLETOS de las 4 categorías (todas las fases/grupos)
# --------------------------------------------------------------------------- #
def recolectar_partidos(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    progress: bool = False,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    vistos: set = set()
    for edad, meta in CATEGORIAS.items():
        cat = int(meta["id_categoria"])
        fases, _ = ges.get_ids_fases_grupos(ID_COMPETENCIA, id_categoria=cat)
        if progress:
            print(
                f"{edad} ({meta['nombre_ges']}): {len(fases)} fases",
                file=sys.stderr,
                flush=True,
            )
        if not fases:
            if progress:
                print(f"  ⚠ {edad}: sin fases (¿categoría inexistente?)", file=sys.stderr)
            continue
        for nombre_fase, id_fase in fases.items():
            grupos = ges.get_grupos_de_fase(ID_COMPETENCIA, cat, int(id_fase))
            n_cat = 0
            for nombre_grupo, id_grupo in grupos.items():
                partidos = ges.get_info_partidos(
                    cat,
                    fecha_ini,
                    fecha_fin,
                    key=key,
                    id_fase=int(id_fase),
                    id_grupo=int(id_grupo),
                )
                for p in partidos:
                    if p.get("Estado") != "COMPLETO":
                        continue
                    token = p.get("ID_PARTIDO") or ""
                    if not token or token in vistos:
                        continue
                    vistos.add(token)
                    out.append(
                        {
                            "id_partido": token,
                            "categoria": edad,
                            "fase": nombre_fase,
                            "zona": nombre_grupo,
                            "local": p.get("Local") or "",
                            "visitante": p.get("Visitante") or "",
                            "fecha": p.get("Fecha") or "",
                        }
                    )
                    n_cat += 1
            if progress:
                print(
                    f"  {edad} · {nombre_fase}: {len(grupos)} grupos",
                    file=sys.stderr,
                    flush=True,
                )
        if progress:
            tot = sum(1 for x in out if x["categoria"] == edad)
            print(f"  {edad}: {tot} partidos COMPLETOS", file=sys.stderr, flush=True)
    return out


# --------------------------------------------------------------------------- #
# Boxscores con estadísticas COMPLETAS (caché propia)
# --------------------------------------------------------------------------- #
def _descargar_box_full(token: str) -> Dict[str, object]:
    try:
        resp = requests.get(
            _boxscore_url(token),
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            timeout=45,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return {"ok": False}
    if len(html) < 8000:
        return {"ok": False}
    equipos = parse_boxscore_html(html).get("equipos") or []
    if not equipos:
        return {"ok": False}
    # Solo guardamos nombre + jugadores (con stats completas) para acotar tamaño.
    out = [
        {"nombre": eq.get("nombre") or "", "jugadores": eq.get("jugadores") or []}
        for eq in equipos[:2]
    ]
    return {"ok": True, "equipos": out}


def _cargar_box_cache() -> Dict[str, Dict[str, object]]:
    if BOX_FULL_CACHE.exists():
        try:
            return json.loads(BOX_FULL_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_box_cache(cache: Dict[str, Dict[str, object]]) -> None:
    BOX_FULL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BOX_FULL_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def descargar_boxscores_full(
    tokens: List[str],
    *,
    workers: int = 12,
    progress: bool = False,
    limite: int = 0,
    sin_descarga: bool = False,
    refetch: bool = False,
) -> Dict[str, Dict[str, object]]:
    cache = _cargar_box_cache()
    unicos = [t for t in dict.fromkeys(tokens) if t]
    # refetch: re-descargar y re-parsear TODO (necesario para poblar pid/purl).
    pendientes = list(unicos) if refetch else [t for t in unicos if t not in cache]
    if limite > 0:
        pendientes = pendientes[:limite]
    if progress:
        print(
            f"Boxscores full: {len(unicos)} partidos, {len(cache)} en caché, "
            f"{len(pendientes)} a descargar…",
            file=sys.stderr,
        )
    if pendientes and not sin_descarga:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut = {pool.submit(_descargar_box_full, t): t for t in pendientes}
            done = 0
            for f in as_completed(fut):
                cache[fut[f]] = f.result()
                done += 1
                if progress and (done % 100 == 0 or done == len(pendientes)):
                    print(f"  {done}/{len(pendientes)}", file=sys.stderr, flush=True)
        _guardar_box_cache(cache)
    return {t: cache[t] for t in unicos if t in cache and cache[t].get("ok")}


# --------------------------------------------------------------------------- #
# Fichas de jugador (nombre completo + fecha de nacimiento), caché por pid
# --------------------------------------------------------------------------- #
def _ficha_url(purl: str) -> str:
    purl = (purl or "").strip()
    if purl.startswith("http"):
        return purl
    return "https://argentina.basketball" + purl


def _descargar_ficha(purl: str) -> Dict[str, object]:
    try:
        resp = requests.get(
            _ficha_url(purl),
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            timeout=45,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        html = resp.text
    except Exception:
        return {"ok": False}
    if len(html) < 2000:
        return {"ok": False}
    return parse_ficha_jugador_html(html)


def _cargar_ficha_cache() -> Dict[str, Dict[str, object]]:
    if FICHA_CACHE.exists():
        try:
            return json.loads(FICHA_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_ficha_cache(cache: Dict[str, Dict[str, object]]) -> None:
    FICHA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FICHA_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def pids_purls_desde_boxscores(
    boxscores: Dict[str, Dict[str, object]]
) -> Dict[str, str]:
    """Mapa pid -> purl (primer href visto) recorriendo todas las actas."""
    out: Dict[str, str] = {}
    for box in boxscores.values():
        if not box or not box.get("ok"):
            continue
        for eq in box.get("equipos") or []:
            for j in eq.get("jugadores") or []:
                pid = j.get("pid")
                purl = j.get("purl")
                if pid and purl and pid not in out:
                    out[str(pid)] = purl
    return out


def descargar_fichas(
    pid_purl: Dict[str, str],
    *,
    workers: int = 16,
    progress: bool = False,
    limite: int = 0,
    sin_fichas: bool = False,
) -> Dict[str, Dict[str, object]]:
    cache = _cargar_ficha_cache()
    pendientes = [pid for pid in pid_purl if pid not in cache]
    if limite > 0:
        pendientes = pendientes[:limite]
    if progress:
        print(
            f"Fichas: {len(pid_purl)} jugadores únicos, {len(cache)} en caché, "
            f"{len(pendientes)} a descargar…",
            file=sys.stderr,
        )
    if pendientes and not sin_fichas:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut = {
                pool.submit(_descargar_ficha, pid_purl[pid]): pid for pid in pendientes
            }
            done = 0
            for f in as_completed(fut):
                cache[fut[f]] = f.result()
                done += 1
                if progress and (done % 200 == 0 or done == len(pendientes)):
                    print(f"  {done}/{len(pendientes)}", file=sys.stderr, flush=True)
                # Guardado incremental para no perder progreso en corridas largas.
                if done % 1000 == 0:
                    _guardar_ficha_cache(cache)
        _guardar_ficha_cache(cache)
    return {pid: cache[pid] for pid in pid_purl if pid in cache and cache[pid].get("ok")}


# --------------------------------------------------------------------------- #
# Agregación por jugador
# --------------------------------------------------------------------------- #
_ACUM_CAMPOS = (
    ("pts", "pts"),
    ("rebtot", "reb"),
    ("rebofe", "rebof"),
    ("rebdef", "rebdef"),
    ("ast", "ast"),
    ("rec", "rob"),
    ("per", "per"),
    ("tap_com", "tap"),
    ("fal_com", "fal"),
    ("val", "val"),
)

# Tipos de tiro: campo en el acta -> alias acumulado (anotados/intentados).
_TIROS = ("t2", "t3", "tl")


def _pct(a: int, i: int) -> float:
    """Porcentaje anotados/intentados; 0.0 si no hubo intentos (display '-' en UI)."""
    return round(a / i * 100, 1) if i > 0 else 0.0


def _edad_de_fnac(fnac: str) -> Optional[int]:
    """Edad (años) a partir de una fecha de nacimiento en formatos comunes."""
    fnac = (fnac or "").strip()
    if not fnac:
        return None
    dt = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(fnac[:10], fmt).date()
            break
        except ValueError:
            continue
    if dt is None:
        return None
    hoy = date.today()
    edad = hoy.year - dt.year - ((hoy.month, hoy.day) < (dt.month, dt.day))
    return edad if 0 < edad < 120 else None


def agregar_jugadores(
    partidos: List[Dict[str, str]],
    boxscores: Dict[str, Dict[str, object]],
    fichas: Optional[Dict[str, Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """
    Agrega por jugador. Clave: el ``pid`` (id de ficha) cuando existe — robusto ante
    cambios de equipo dentro de la categoría — combinado con la categoría para no
    mezclar a un mismo jugador entre categorías. Fallback a (categoría, equipo, nombre).
    """
    fichas = fichas or {}
    acc: Dict[Tuple[str, ...], Dict[str, object]] = {}

    for p in partidos:
        box = boxscores.get(p["id_partido"])
        if not box or not box.get("ok"):
            continue
        equipos = box.get("equipos") or []
        # equipos[0] = local, equipos[1] = visitante (mapeo por índice del acta).
        lados = [
            (p.get("local") or "", equipos[0] if len(equipos) > 0 else None),
            (p.get("visitante") or "", equipos[1] if len(equipos) > 1 else None),
        ]
        for equipo_nombre, eq in lados:
            if not eq:
                continue
            equipo_disp = eq.get("nombre") or equipo_nombre
            for j in eq.get("jugadores") or []:
                seg = parse_minutos_a_segundos(j.get("min")) or 0
                if seg <= 0:
                    continue  # DNP: no cuenta como partido jugado
                nombre = (j.get("nombre") or "").strip()
                if not nombre:
                    continue
                pid = (str(j.get("pid")).strip() if j.get("pid") else "") or None
                if pid:
                    clave: Tuple[str, ...] = ("pid", p["categoria"], pid)
                else:
                    clave = (
                        "nm",
                        p["categoria"],
                        normalizar_nombre(equipo_disp),
                        normalizar_nombre(nombre),
                    )
                a = acc.get(clave)
                if a is None:
                    a = {
                        "nombre": nombre,
                        "nc_oc": (j.get("nombre_completo") or "").strip(),
                        "categoria": p["categoria"],
                        "pid": pid,
                        "purl": j.get("purl"),
                        "equipos": {},  # equipo -> nº de partidos (para elegir el principal)
                        "pj": 0,
                        "seg": 0,
                    }
                    for _, alias in _ACUM_CAMPOS:
                        a[alias] = 0
                    for st in _TIROS:
                        a[st + "a"] = 0
                        a[st + "i"] = 0
                    acc[clave] = a
                a["pj"] += 1
                a["seg"] += seg
                a["equipos"][equipo_disp] = a["equipos"].get(equipo_disp, 0) + 1
                if pid and not a.get("pid"):
                    a["pid"] = pid
                    a["purl"] = j.get("purl")
                if not a.get("nc_oc") and j.get("nombre_completo"):
                    a["nc_oc"] = j["nombre_completo"].strip()
                for campo, alias in _ACUM_CAMPOS:
                    a[alias] += _to_int(j.get(campo))
                for st in _TIROS:
                    blk = j.get(st) or {}
                    a[st + "a"] += _to_int(blk.get("a"))
                    a[st + "i"] += _to_int(blk.get("i"))

    out: List[Dict[str, object]] = []
    for a in acc.values():
        pj = a["pj"]
        if pj <= 0:
            continue

        def avg(x: int) -> float:
            return round(x / pj, 1)

        equipo_disp = (
            max(a["equipos"].items(), key=lambda kv: kv[1])[0]
            if a["equipos"]
            else a.get("equipo", "")
        )
        ficha = fichas.get(a["pid"]) if a.get("pid") else None
        nombre_ficha = ""
        fnac = ""
        if ficha and ficha.get("ok"):
            nombre_ficha = (ficha.get("nombre_completo") or "").strip()
            fnac = (ficha.get("fnac") or "").strip()
        # Prioridad: ficha ("Nombre Apellido") > onclick ("APELLIDO, NOMBRE") > abreviado.
        nombre_completo = nombre_ficha or a.get("nc_oc") or a["nombre"]
        edad = _edad_de_fnac(fnac)

        out.append(
            {
                "pid": a.get("pid") or "",
                "purl": a.get("purl") or "",
                "nombre": a["nombre"],
                "nombre_completo": nombre_completo,
                "equipo": equipo_disp,
                "cat": a["categoria"],
                "fnac": fnac,
                "edad": edad if edad is not None else "",
                "pj": pj,
                "min_p": round((a["seg"] / pj) / 60.0, 1),
                "pts_p": avg(a["pts"]),
                "reb_p": avg(a["reb"]),
                "ast_p": avg(a["ast"]),
                "rob_p": avg(a["rob"]),
                "tap_p": avg(a["tap"]),
                "val_p": avg(a["val"]),
                "per": a["per"],
                # Tiros: anotados/intentados por partido + % de temporada.
                "t2a_p": avg(a["t2a"]),
                "t2i_p": avg(a["t2i"]),
                "t2_pct": _pct(a["t2a"], a["t2i"]),
                "t3a_p": avg(a["t3a"]),
                "t3i_p": avg(a["t3i"]),
                "t3_pct": _pct(a["t3a"], a["t3i"]),
                "tla_p": avg(a["tla"]),
                "tli_p": avg(a["tli"]),
                "tl_pct": _pct(a["tla"], a["tli"]),
                # totales (para referencia / decidir si mostrar % o '-')
                "pts": a["pts"],
                "reb": a["reb"],
                "ast": a["ast"],
                "rob": a["rob"],
                "tap": a["tap"],
                "val": a["val"],
                "t2i": a["t2i"],
                "t3i": a["t3i"],
                "tli": a["tli"],
                "t2a": a["t2a"],
                "t3a": a["t3a"],
                "tla": a["tla"],
            }
        )
    out.sort(key=lambda d: (-d["pts_p"], -d["pj"], d["nombre"]))
    return out


# --------------------------------------------------------------------------- #
# Render HTML autocontenido
# --------------------------------------------------------------------------- #
def _build_perfil_guia_html() -> str:
    orden = list(PERFILES) + [PERFIL_INSUFICIENTE]
    cards: List[str] = []
    for nombre in orden:
        info = PERFIL_DESCRIPCIONES[nombre]
        css = _PERFIL_CSS_MAP[nombre]
        cards.append(
            f"""<article class="perfil-card">
          <span class="perfil-badge {css}">{nombre}</span>
          <p class="perfil-resumen"><strong>{info["resumen"]}</strong></p>
          <p><span class="perfil-lbl">Características</span> {info["caracteristicas"]}</p>
          <p><span class="perfil-lbl">Uso en scouting</span> {info["scouting"]}</p>
        </article>"""
        )
    return (
        '<p class="note">Los perfiles se asignan con clustering K-Means (k=6) sobre '
        "volumen de triples, % de 3P, asistencias, robos, rebotes y puntos por partido. "
        f"Solo jugadores con PJ ≥ 5 reciben perfil; el resto queda como "
        f'"{PERFIL_INSUFICIENTE}".</p>'
        '<div class="perfil-grid">' + "".join(cards) + "</div>"
    )


def _build_html(
    *,
    fecha: str,
    cat_opts: str,
    perfil_opts: str,
    scout_key: str,
    perfil_css_map: str,
    perfil_guia_html: str,
    data_decl: str,
    arranque: str,
    login_block: str = "",
    app_style: str = "",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FORMATIVAS 2026 · Scouting de jugadores</title>
  <style>
    :root {{
      --bg:#f1f5f9; --paper:#fff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0;
      --accent:#1d4ed8; --accent-soft:#eff6ff; --ok:#059669; --star:#eab308;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg);
      color:var(--text); line-height:1.45; }}
    .layout {{ max-width:1400px; margin:0 auto; padding:20px; }}
    header, section {{ background:var(--paper); border:1px solid var(--line);
      border-radius:14px; padding:18px 20px; margin-bottom:16px; }}
    h1 {{ margin:0 0 4px; font-size:23px; }}
    .subtitle {{ color:var(--muted); font-size:13px; margin:0; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; }}
    label.fld {{ font-size:12px; color:var(--muted); display:flex; flex-direction:column; gap:4px; }}
    input, select, textarea {{ border:1px solid var(--line); border-radius:8px; padding:8px 10px;
      font-size:13px; background:#fff; color:var(--text); }}
    input[type="search"] {{ min-width:200px; }}
    input[type="number"] {{ width:110px; }}
    .count {{ margin-left:auto; font-size:13px; color:var(--muted); align-self:center; }}
    .count b {{ color:var(--accent); font-size:16px; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:7px 6px; text-align:center; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.04em;
      cursor:pointer; user-select:none; position:sticky; top:0; background:var(--paper); z-index:1; }}
    th:hover {{ color:var(--accent); }}
    th.sorted-asc::after {{ content:" ▲"; color:var(--accent); }}
    th.sorted-desc::after {{ content:" ▼"; color:var(--accent); }}
    td.eq, th.eq {{ text-align:left; }}
    td.nm {{ text-align:left; font-weight:600; }}
    td.nm a {{ color:var(--text); text-decoration:none; }}
    td.nm a:hover {{ color:var(--accent); text-decoration:underline; }}
    td.rank {{ color:var(--muted); }}
    td.main {{ font-weight:800; color:var(--accent); }}
    .cat-badge {{ display:inline-block; border-radius:999px; padding:1px 8px; font-size:11px;
      background:var(--accent-soft); color:var(--accent); font-weight:600; }}
    .perfil-badge {{ display:inline-block; border-radius:999px; padding:2px 8px; font-size:10px; font-weight:600; }}
    .perfil-Especialista-3-D {{ background:#EBF8FF; color:#2B6CB0; }}
    .perfil-Protector-de-Aro {{ background:#F0FFF4; color:#2F855A; }}
    .perfil-Base-Conductor {{ background:#FAF5FF; color:#6B46C1; }}
    .perfil-Anotador-de-Volumen {{ background:#FFF5F5; color:#C53030; }}
    .perfil-Generador-Perimetral {{ background:#FFFAF0; color:#DD6B20; }}
    .perfil-Interno-de-Rol {{ background:#EDF2F7; color:#4A5568; }}
    .perfil-Muestra-insuficiente {{ background:#f8fafc; color:#94a3b8; }}
    tbody tr:hover {{ background:#f8fafc; }}
    tbody tr.selected {{ background:#eff6ff; }}
    .tablewrap {{ overflow:auto; max-height:62vh; border:1px solid var(--line); border-radius:10px; }}
    .note {{ font-size:12px; color:var(--muted); margin-top:10px; }}
    .btn {{ border:1px solid var(--accent); color:var(--accent); background:#fff; border-radius:8px;
      padding:8px 14px; font-size:13px; font-weight:600; cursor:pointer; }}
    .btn:hover {{ background:var(--accent-soft); }}
    .btn.active {{ background:var(--accent); color:#fff; }}
    .btn-pill {{ border-radius:999px; padding:6px 12px; font-size:12px; border:1px solid var(--line);
      background:#fff; cursor:pointer; color:var(--text); }}
    .btn-pill:hover {{ border-color:var(--accent); color:var(--accent); }}
    .btn-pill.active {{ background:var(--accent-soft); border-color:var(--accent); color:var(--accent); font-weight:600; }}
    .presets {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }}
    .tabs {{ display:flex; gap:8px; margin-bottom:16px; }}
    .tab-btn {{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:8px 18px;
      font-size:13px; font-weight:600; cursor:pointer; color:var(--muted); }}
    .tab-btn:hover {{ border-color:var(--accent); color:var(--accent); }}
    .tab-btn.active {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
    .perfil-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:14px; margin-top:14px; }}
    .perfil-card {{ border:1px solid var(--line); border-radius:12px; padding:16px; background:#fafbfc; }}
    .perfil-card .perfil-badge {{ margin-bottom:10px; font-size:12px; }}
    .perfil-card p {{ margin:0 0 10px; font-size:13px; line-height:1.5; }}
    .perfil-card .perfil-resumen {{ margin-bottom:12px; }}
    .perfil-lbl {{ display:block; font-size:10px; text-transform:uppercase; letter-spacing:.05em;
      color:var(--muted); margin-bottom:2px; font-weight:600; }}
    details.statfilters {{ margin-top:14px; border:1px solid var(--line); border-radius:10px;
      padding:10px 14px; background:#fafbfc; }}
    details.statfilters > summary {{ cursor:pointer; font-size:13px; font-weight:600; color:var(--text);
      list-style:none; }}
    details.statfilters > summary::-webkit-details-marker {{ display:none; }}
    details.statfilters > summary::before {{ content:"▸ "; color:var(--accent); }}
    details.statfilters[open] > summary::before {{ content:"▾ "; }}
    .rangos-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px 16px; margin-top:12px; }}
    .rango {{ display:flex; flex-direction:column; gap:4px; }}
    .rango .lbl {{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
    .rango .pair {{ display:flex; align-items:center; gap:6px; }}
    .rango .pair input {{ width:100%; min-width:0; padding:6px 8px; }}
    .rango .pair span {{ color:var(--muted); font-size:12px; }}
    .star-btn {{ background:none; border:none; cursor:pointer; font-size:18px; padding:2px 6px; color:#cbd5e1; }}
    .star-btn.on {{ color:var(--star); }}
    .cmp-chk {{ width:16px; height:16px; cursor:pointer; }}
    #detail-panel {{ display:none; position:fixed; top:0; right:0; width:360px; max-width:95vw; height:100vh;
      background:var(--paper); border-left:1px solid var(--line); box-shadow:-4px 0 24px rgba(0,0,0,.08);
      z-index:100; overflow:auto; padding:20px; }}
    #detail-panel.open {{ display:block; }}
    #detail-panel h3 {{ margin:0 0 4px; font-size:18px; }}
    #detail-panel .meta {{ color:var(--muted); font-size:13px; margin-bottom:14px; }}
    #detail-panel .stats-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:13px; margin-bottom:14px; }}
    #detail-panel .stats-grid div {{ background:#f8fafc; padding:8px; border-radius:8px; }}
    #detail-panel .stats-grid span {{ display:block; font-size:11px; color:var(--muted); }}
    #detail-panel textarea {{ width:100%; min-height:80px; resize:vertical; margin-top:6px; }}
    #detail-close {{ position:absolute; top:12px; right:14px; background:none; border:none; font-size:22px; cursor:pointer; color:var(--muted); }}
    #compare-panel {{ display:none; position:fixed; bottom:0; left:0; right:0; max-height:40vh; overflow:auto;
      background:var(--paper); border-top:2px solid var(--accent); box-shadow:0 -4px 24px rgba(0,0,0,.1);
      z-index:99; padding:12px 20px; }}
    #compare-panel.open {{ display:block; }}
    #compare-panel h4 {{ margin:0 0 10px; font-size:14px; }}
    @media (max-width:900px) {{ .rangos-grid {{ grid-template-columns:repeat(2,1fr); }} }}
    .login-wrap {{ max-width:420px; margin:6vh auto 0; }}
    .login-card {{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:24px; }}
    .login-card h2 {{ margin:0 0 6px; font-size:18px; }}
    .login-card p {{ margin:0 0 14px; color:var(--muted); font-size:13px; }}
    .login-row {{ display:flex; gap:8px; }}
    .login-row input {{ flex:1; }}
    .login-err {{ color:#dc2626; font-size:13px; margin-top:10px; min-height:18px; }}
  </style>
</head>
<body>
  <div class="layout">
    <header>
      <h1>Scouting de jugadores</h1>
      <p class="subtitle">FORMATIVAS · GES 2015 · Masculino · Analítica avanzada · Actualizado: {fecha}</p>
    </header>
{login_block}
    <div id="app"{app_style}>
    <nav class="tabs">
      <button type="button" class="tab-btn active" data-tab="buscador">Buscador</button>
      <button type="button" class="tab-btn" data-tab="perfiles">Guía de perfiles</button>
    </nav>
    <div id="tab-buscador" class="tab-panel">
    <section>
      <div class="toolbar">
        <label class="fld">Categoría
          <select id="f-cat"><option value="">Todas</option>{cat_opts}</select>
        </label>
        <label class="fld">Perfil
          <select id="f-perfil"><option value="">Todos</option>{perfil_opts}</select>
        </label>
        <label class="fld">Buscar jugador
          <input type="search" id="f-nombre" placeholder="Nombre…"/>
        </label>
        <label class="fld">Buscar equipo
          <input type="search" id="f-equipo" placeholder="Equipo…"/>
        </label>
        <button type="button" class="btn-pill" id="f-fichajes">⭐ Mi lista de fichajes</button>
        <button type="button" class="btn" id="f-export">Exportar CSV</button>
        <button type="button" class="btn" id="f-limpiar">Limpiar filtros</button>
        <span class="count"><b id="n-filas">0</b> jugadores · <b id="n-scout">0</b> en seguimiento</span>
      </div>
      <div class="presets" id="presets"></div>
      <details class="statfilters" open>
        <summary>Filtros por estadística (rango mín–máx, combinables)</summary>
        <div class="rangos-grid" id="rangos"></div>
      </details>
      <p class="note">Clic en encabezado para ordenar. TS% y eFG% son de temporada. Percentiles (Pct) son relativos a la categoría. Perfiles vía clustering K-Means (PJ≥5). Seguimiento y notas se guardan en tu navegador.</p>
      <div class="tablewrap">
        <table>
          <thead><tr id="thead"></tr></thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </section>
    </div>
    <div id="tab-perfiles" class="tab-panel" style="display:none">
    <section>
      <h2 style="margin:0 0 8px;font-size:18px">Guía de perfiles de jugador</h2>
      {perfil_guia_html}
    </section>
    </div>
    </div>
  </div>
  <div id="detail-panel">
    <button type="button" id="detail-close" title="Cerrar">×</button>
    <div id="detail-content"></div>
  </div>
  <div id="compare-panel">
    <h4>Comparador <button type="button" class="btn-pill" id="cmp-clear" style="margin-left:8px">Limpiar</button></h4>
    <div id="compare-content"></div>
  </div>

  <script>
    {data_decl}
    const SCOUT_KEY = {json.dumps(scout_key)};
    const PERFIL_CLASS = {perfil_css_map};
    const COLS = [
      {{key:"__star", label:"★", type:"star"}},
      {{key:"__cmp", label:"⚖", type:"cmp"}},
      {{key:"__rank", label:"#", type:"rank"}},
      {{key:"perfil", label:"Perfil", type:"perfil"}},
      {{key:"nombre_completo", label:"Jugador", type:"player", cls:"nm"}},
      {{key:"equipo", label:"Equipo", type:"text", cls:"eq"}},
      {{key:"cat", label:"Cat.", type:"cat"}},
      {{key:"edad", label:"Edad", type:"num"}},
      {{key:"pj", label:"PJ", type:"num"}},
      {{key:"min_p", label:"Min/p", type:"num"}},
      {{key:"pts_p", label:"Pts/p", type:"num", main:true}},
      {{key:"pct_pts", label:"Pct Pts", type:"pctile", tip:"Percentil pts/p en categoría"}},
      {{key:"ts_pct", label:"TS%", type:"pct", tot:"t2i", altTot:"t3i"}},
      {{key:"pct_ts", label:"Pct TS", type:"pctile"}},
      {{key:"efg_pct", label:"eFG%", type:"pct", tot:"t2i", altTot:"t3i"}},
      {{key:"val_min", label:"Val/Min", type:"num"}},
      {{key:"pct_val", label:"Pct Val", type:"pctile"}},
      {{key:"reb_p", label:"Reb/p", type:"num"}},
      {{key:"ast_p", label:"Ast/p", type:"num"}},
      {{key:"ast_per", label:"Ast/Per", type:"num"}},
      {{key:"per_p", label:"Per/p", type:"num"}},
      {{key:"rob_p", label:"Rob/p", type:"num"}},
      {{key:"tap_p", label:"Tap/p", type:"num"}},
      {{key:"val_p", label:"Val/p", type:"num"}},
      {{key:"t2a_p", label:"2P A-I", type:"ai", keyA:"t2a_p", keyI:"t2i_p"}},
      {{key:"t2_pct", label:"2P%", type:"pct", tot:"t2i"}},
      {{key:"t3a_p", label:"3P A-I", type:"ai", keyA:"t3a_p", keyI:"t3i_p"}},
      {{key:"t3_pct", label:"3P%", type:"pct", tot:"t3i"}},
      {{key:"tla_p", label:"TL A-I", type:"ai", keyA:"tla_p", keyI:"tli_p"}},
      {{key:"tl_pct", label:"TL%", type:"pct", tot:"tli"}},
    ];
    const RANGOS = [
      {{key:"pj", label:"PJ", def_min:"3"}},
      {{key:"edad", label:"Edad"}},
      {{key:"min_p", label:"Min/p"}},
      {{key:"pts_p", label:"Pts/p"}},
      {{key:"ts_pct", label:"TS%"}},
      {{key:"efg_pct", label:"eFG%"}},
      {{key:"val_min", label:"Val/Min"}},
      {{key:"pct_pts", label:"Pct Pts"}},
      {{key:"pct_ts", label:"Pct TS"}},
      {{key:"pct_val", label:"Pct Val"}},
      {{key:"reb_p", label:"Reb/p"}},
      {{key:"ast_p", label:"Ast/p"}},
      {{key:"ast_per", label:"Ast/Per"}},
      {{key:"rob_p", label:"Rob/p"}},
      {{key:"tap_p", label:"Tap/p"}},
      {{key:"val_p", label:"Val/p"}},
      {{key:"t2_pct", label:"2P%"}},
      {{key:"t3_pct", label:"3P%"}},
      {{key:"tl_pct", label:"TL%"}},
      {{key:"t2i_p", label:"2P int/p"}},
      {{key:"t3i_p", label:"3P int/p"}},
      {{key:"tli_p", label:"TL int/p"}},
    ];
    const PRESETS = [
      {{id:"t3", label:"Tirador 3P", ranges:{{t3i_p:{{min:3}}, t3_pct:{{min:32}}}}}},
      {{id:"reb", label:"Interior reboteador", ranges:{{reb_p:{{min:6}}, tap_p:{{min:0.5}}}}}},
      {{id:"base", label:"Base creador", ranges:{{ast_p:{{min:3}}, ast_per:{{min:1.5}}}}}},
      {{id:"rot", label:"Eficiente rotación", ranges:{{min_p:{{max:18}}, val_min:{{min:0.6}}}}}},
    ];
    let sortKey = "pts_p";
    let sortDir = -1;
    let soloFichajes = false;
    let compareIds = [];
    let activePresetId = null;
    let renderTimer = null;
    let headBuilt = false;

    function esc(s) {{ return (s==null?"":String(s)).replace(/[&<>]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c])); }}
    function perfilCls(p) {{ return PERFIL_CLASS[p] || "perfil-Muestra-insuficiente"; }}
    function playerId(d) {{ return String(d.pid || d.nombre_completo + "|" + d.cat); }}
    function fichaUrl(purl) {{
      if (!purl) return "";
      return purl.startsWith("http") ? purl : "https://argentina.basketball" + purl;
    }}

    function loadScout() {{
      try {{ return JSON.parse(localStorage.getItem(SCOUT_KEY) || "{{}}"); }}
      catch(e) {{ return {{}}; }}
    }}
    function saveScout(data) {{ localStorage.setItem(SCOUT_KEY, JSON.stringify(data)); }}
    function isStarred(d) {{ const s = loadScout(); return !!(s[playerId(d)] && s[playerId(d)].starred); }}
    function toggleStar(d) {{
      const id = playerId(d);
      const s = loadScout();
      if (!s[id]) s[id] = {{starred:false, note:"", ts:Date.now()}};
      s[id].starred = !s[id].starred;
      s[id].ts = Date.now();
      saveScout(s);
      scheduleRender();
    }}
    function scoutCount() {{ return Object.values(loadScout()).filter(x => x.starred).length; }}

    function buildRangos() {{
      const cont = document.getElementById("rangos");
      cont.innerHTML = RANGOS.map(r => `
        <div class="rango">
          <span class="lbl">${{esc(r.label)}}</span>
          <div class="pair">
            <input type="number" step="any" inputmode="decimal" id="min-${{r.key}}" placeholder="mín" value="${{r.def_min||""}}"/>
            <span>–</span>
            <input type="number" step="any" inputmode="decimal" id="max-${{r.key}}" placeholder="máx"/>
          </div>
        </div>`).join("");
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).addEventListener("input", scheduleRender);
        document.getElementById("max-" + r.key).addEventListener("input", scheduleRender);
      }});
    }}

    function clearPresetRanges(p) {{
      for (const k of Object.keys(p.ranges)) {{
        const r = RANGOS.find(x => x.key === k);
        document.getElementById("min-" + k).value = (r && r.def_min) ? r.def_min : "";
        document.getElementById("max-" + k).value = "";
      }}
    }}

    function buildPresets() {{
      const cont = document.getElementById("presets");
      PRESETS.forEach(p => {{
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn-pill";
        btn.textContent = p.label;
        btn.dataset.preset = p.id;
        btn.addEventListener("click", () => applyPreset(p));
        cont.appendChild(btn);
      }});
    }}

    function applyPreset(p) {{
      if (activePresetId === p.id) {{
        clearPresetRanges(p);
        activePresetId = null;
        document.querySelectorAll("#presets .btn-pill").forEach(b => b.classList.remove("active"));
        scheduleRender();
        return;
      }}
      if (activePresetId) {{
        const prev = PRESETS.find(x => x.id === activePresetId);
        if (prev) clearPresetRanges(prev);
      }}
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).value = r.def_min || "";
        document.getElementById("max-" + r.key).value = "";
      }});
      for (const [k, rng] of Object.entries(p.ranges)) {{
        if (rng.min != null) document.getElementById("min-" + k).value = rng.min;
        if (rng.max != null) document.getElementById("max-" + k).value = rng.max;
      }}
      activePresetId = p.id;
      document.querySelectorAll("#presets .btn-pill").forEach(b => b.classList.toggle("active", b.dataset.preset === p.id));
      scheduleRender();
    }}

    function _numVal(id) {{
      const v = (document.getElementById(id).value || "").trim();
      if (v === "") return null;
      const n = parseFloat(v);
      return isNaN(n) ? null : n;
    }}

    function renderHead() {{
      const tr = document.getElementById("thead");
      tr.innerHTML = COLS.map(c => {{
        if (c.type === "rank" || c.type === "star" || c.type === "cmp") return `<th class="rank">${{esc(c.label)}}</th>`;
        let cls = c.cls || "";
        if (c.key === sortKey) cls += sortDir < 0 ? " sorted-desc" : " sorted-asc";
        const tip = c.tip ? ` title="${{esc(c.tip)}}"` : "";
        return `<th class="${{cls}}" data-key="${{c.key}}"${{tip}}>${{esc(c.label)}}</th>`;
      }}).join("");
      tr.querySelectorAll("th[data-key]").forEach(th => th.addEventListener("click", () => {{
        const k = th.dataset.key;
        if (k === sortKey) sortDir = -sortDir;
        else {{ sortKey = k; sortDir = TEXT_KEYS.has(k) || k === "perfil" ? 1 : -1; }}
        headBuilt = false;
        render();
      }}));
      headBuilt = true;
    }}

    function filtrar() {{
      const cat = document.getElementById("f-cat").value;
      const perfil = document.getElementById("f-perfil").value;
      const qn = document.getElementById("f-nombre").value.trim().toLowerCase();
      const qe = document.getElementById("f-equipo").value.trim().toLowerCase();
      const scout = loadScout();
      const rangos = RANGOS.map(r => ({{
        key: r.key, min: _numVal("min-" + r.key), max: _numVal("max-" + r.key)
      }})).filter(r => r.min !== null || r.max !== null);
      return DATA.filter(d => {{
        if (cat && d.cat !== cat) return false;
        if (perfil && d.perfil !== perfil) return false;
        if (soloFichajes) {{
          const s = scout[playerId(d)];
          if (!s || !s.starred) return false;
        }}
        if (qn) {{
          const hay = (d.nombre_completo || d.nombre || "").toLowerCase();
          const abr = (d.nombre || "").toLowerCase();
          if (!hay.includes(qn) && !abr.includes(qn)) return false;
        }}
        if (qe && !d.equipo.toLowerCase().includes(qe)) return false;
        for (const r of rangos) {{
          const v = d[r.key];
          if (v === "" || v == null) return false;
          if (r.min !== null && v < r.min) return false;
          if (r.max !== null && v > r.max) return false;
        }}
        return true;
      }});
    }}

    function limpiar() {{
      document.getElementById("f-cat").value = "";
      document.getElementById("f-perfil").value = "";
      document.getElementById("f-nombre").value = "";
      document.getElementById("f-equipo").value = "";
      soloFichajes = false;
      activePresetId = null;
      document.getElementById("f-fichajes").classList.remove("active");
      document.querySelectorAll("#presets .btn-pill").forEach(b => b.classList.remove("active"));
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).value = r.def_min || "";
        document.getElementById("max-" + r.key).value = "";
      }});
      scheduleRender();
    }}

    const TEXT_KEYS = new Set(["nombre", "nombre_completo", "equipo", "cat", "fnac", "perfil"]);
    function ordenar(rows) {{
      const k = sortKey, dir = sortDir;
      const num = !TEXT_KEYS.has(k);
      return rows.sort((a, b) => {{
        let va = a[k], vb = b[k];
        if (num) {{
          va = (va === null || va === undefined || va === "") ? -Infinity : va;
          vb = (vb === null || vb === undefined || vb === "") ? -Infinity : vb;
          return (va - vb) * dir;
        }}
        va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
        return va < vb ? -dir : (va > vb ? dir : 0);
      }});
    }}

    function cellValue(d, c) {{
      if (c.type === "rank") return String(arguments[2] || "");
      if (c.type === "star") return "";
      if (c.type === "cmp") return "";
      if (c.type === "perfil") return `<span class="perfil-badge ${{perfilCls(d.perfil)}}">${{esc(d.perfil||"-")}}</span>`;
      if (c.type === "player") {{
        const url = fichaUrl(d.purl);
        const nm = esc(d.nombre_completo || d.nombre);
        return url ? `<a href="${{esc(url)}}" target="_blank" rel="noopener">${{nm}}</a>` : nm;
      }}
      if (c.type === "cat") return `<span class="cat-badge">${{esc(d.cat)}}</span>`;
      if (c.type === "text") return esc(d[c.key]);
      if (c.type === "ai") return `${{d[c.keyA]}}-${{d[c.keyI]}}`;
      if (c.type === "pctile") return d[c.key] !== "" ? d[c.key] : "-";
      if (c.type === "pct") {{
        const hasShots = (d[c.tot] > 0) || (c.altTot && d[c.altTot] > 0) || (c.key === "ts_pct" && (d.t2i+d.t3i+d.tli) > 0);
        return hasShots && d[c.key] !== "" ? d[c.key] : "-";
      }}
      return d[c.key] === "" ? "-" : String(d[c.key]);
    }}

    function renderBody(rows) {{
      const body = document.getElementById("tbody");
      const fragment = document.createDocumentFragment();
      rows.forEach((d, i) => {{
        const tr = document.createElement("tr");
        const pid = playerId(d);
        if (compareIds.includes(pid)) tr.classList.add("selected");
        COLS.forEach(c => {{
          const td = document.createElement("td");
          if (c.cls) td.className = c.cls;
          if (c.type === "rank") {{ td.className = "rank"; td.textContent = i + 1; }}
          else if (c.type === "star") {{
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "star-btn" + (isStarred(d) ? " on" : "");
            btn.textContent = "★";
            btn.title = "Seguimiento";
            btn.addEventListener("click", e => {{ e.stopPropagation(); toggleStar(d); }});
            td.appendChild(btn);
          }}
          else if (c.type === "cmp") {{
            const chk = document.createElement("input");
            chk.type = "checkbox";
            chk.className = "cmp-chk";
            chk.checked = compareIds.includes(pid);
            chk.addEventListener("change", e => {{
              e.stopPropagation();
              if (chk.checked) {{
                if (compareIds.length >= 3) {{ chk.checked = false; return; }}
                compareIds.push(pid);
              }} else {{
                compareIds = compareIds.filter(x => x !== pid);
              }}
              renderCompare();
              scheduleRender();
            }});
            td.appendChild(chk);
          }}
          else if (c.main) {{ td.className = "main"; td.innerHTML = cellValue(d, c); }}
          else {{ td.innerHTML = cellValue(d, c); }}
          tr.appendChild(td);
        }});
        tr.style.cursor = "pointer";
        tr.addEventListener("click", () => openDetail(d));
        fragment.appendChild(tr);
      }});
      body.innerHTML = "";
      body.appendChild(fragment);
    }}

    function render() {{
      if (!headBuilt) renderHead();
      const rows = ordenar(filtrar());
      document.getElementById("n-filas").textContent = rows.length;
      document.getElementById("n-scout").textContent = scoutCount();
      renderBody(rows);
      window._lastRows = rows;
    }}

    function scheduleRender() {{
      clearTimeout(renderTimer);
      renderTimer = setTimeout(render, 150);
    }}

    function openDetail(d) {{
      const panel = document.getElementById("detail-panel");
      const id = playerId(d);
      const scout = loadScout();
      const note = (scout[id] && scout[id].note) || "";
      const url = fichaUrl(d.purl);
      const stats = [
        ["PJ", d.pj], ["Min/p", d.min_p], ["Pts/p", d.pts_p], ["TS%", d.ts_pct],
        ["eFG%", d.efg_pct], ["Val/Min", d.val_min], ["Reb/p", d.reb_p],
        ["Ast/p", d.ast_p], ["Ast/Per", d.ast_per], ["Per/p", d.per_p],
        ["Rob/p", d.rob_p], ["Tap/p", d.tap_p], ["Val/p", d.val_p],
        ["Perfil", d.perfil], ["Pct Pts", d.pct_pts], ["Pct TS", d.pct_ts],
      ];
      document.getElementById("detail-content").innerHTML = `
        <h3>${{esc(d.nombre_completo || d.nombre)}}</h3>
        <div class="meta">${{esc(d.equipo)}} · ${{esc(d.cat)}}${{d.edad ? " · " + d.edad + " años" : ""}}</div>
        <span class="perfil-badge ${{perfilCls(d.perfil)}}">${{esc(d.perfil||"-")}}</span>
        <div class="stats-grid">${{stats.map(([l,v]) => `<div><span>${{l}}</span><b>${{v!==""?v:"-"}}</b></div>`).join("")}}</div>
        ${{url ? `<a class="btn" href="${{esc(url)}}" target="_blank" rel="noopener">Abrir ficha</a>` : ""}}
        <label class="fld" style="margin-top:14px">Notas de scouting
          <textarea id="detail-note">${{esc(note)}}</textarea>
        </label>
        <button type="button" class="btn" id="detail-save" style="margin-top:8px">Guardar nota</button>
      `;
      document.getElementById("detail-save").addEventListener("click", () => {{
        const s = loadScout();
        if (!s[id]) s[id] = {{starred:false, note:"", ts:Date.now()}};
        s[id].note = document.getElementById("detail-note").value;
        s[id].ts = Date.now();
        saveScout(s);
      }});
      panel.classList.add("open");
    }}

    function renderCompare() {{
      const panel = document.getElementById("compare-panel");
      const cont = document.getElementById("compare-content");
      if (!compareIds.length) {{ panel.classList.remove("open"); cont.innerHTML = ""; return; }}
      const players = compareIds.map(id => DATA.find(d => playerId(d) === id)).filter(Boolean);
      if (!players.length) {{ panel.classList.remove("open"); return; }}
      const metrics = ["cat","pj","min_p","pts_p","ts_pct","efg_pct","val_min","reb_p","ast_p","per_p","perfil"];
      let html = "<table><thead><tr><th>Métrica</th>";
      players.forEach(p => {{ html += `<th>${{esc(p.nombre_completo||p.nombre)}}</th>`; }});
      html += "</tr></thead><tbody>";
      metrics.forEach(m => {{
        html += `<tr><td><b>${{m}}</b></td>`;
        players.forEach(p => {{ html += `<td>${{esc(p[m]!==""?p[m]:"-")}}</td>`; }});
        html += "</tr>";
      }});
      html += "</tbody></table>";
      cont.innerHTML = html;
      panel.classList.add("open");
    }}

    function exportCSV() {{
      const rows = window._lastRows || ordenar(filtrar());
      const scout = loadScout();
      const headers = ["pid","nombre_completo","equipo","cat","perfil","pj","min_p","pts_p","ts_pct","efg_pct","val_min","reb_p","ast_p","per_p","ast_per","pct_pts","pct_ts","nota_scouting","en_seguimiento"];
      const lines = [headers.join(",")];
      rows.forEach(d => {{
        const id = playerId(d);
        const sc = scout[id] || {{}};
        const vals = headers.map(h => {{
          if (h === "nota_scouting") return sc.note || "";
          if (h === "en_seguimiento") return sc.starred ? "1" : "0";
          const v = d[h];
          const s = v == null ? "" : String(v);
          return s.includes(",") || s.includes('"') ? '"' + s.replace(/"/g, '""') + '"' : s;
        }});
        lines.push(vals.join(","));
      }});
      const blob = new Blob([lines.join("\\n")], {{type:"text/csv;charset=utf-8"}});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "scouting_formativas.csv";
      a.click();
    }}

    function initTabs() {{
      document.querySelectorAll(".tab-btn").forEach(btn => {{
        btn.addEventListener("click", () => {{
          document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
          document.querySelectorAll(".tab-panel").forEach(p => {{ p.style.display = "none"; }});
          btn.classList.add("active");
          document.getElementById("tab-" + btn.dataset.tab).style.display = "";
        }});
      }});
    }}

    function iniciarApp() {{
      initTabs();
      document.getElementById("f-cat").addEventListener("change", scheduleRender);
      document.getElementById("f-perfil").addEventListener("change", scheduleRender);
      document.getElementById("f-nombre").addEventListener("input", scheduleRender);
      document.getElementById("f-equipo").addEventListener("input", scheduleRender);
      document.getElementById("f-fichajes").addEventListener("click", () => {{
        soloFichajes = !soloFichajes;
        document.getElementById("f-fichajes").classList.toggle("active", soloFichajes);
        scheduleRender();
      }});
      document.getElementById("f-export").addEventListener("click", exportCSV);
      document.getElementById("f-limpiar").addEventListener("click", limpiar);
      document.getElementById("detail-close").addEventListener("click", () => document.getElementById("detail-panel").classList.remove("open"));
      document.getElementById("cmp-clear").addEventListener("click", () => {{ compareIds = []; renderCompare(); scheduleRender(); }});
      buildRangos();
      buildPresets();
      render();
    }}
{arranque}
  </script>
</body>
</html>"""


# Login + descifrado (Web Crypto) para la versión publicada cifrada.
_LOGIN_HTML = """
    <div id="login" class="login-wrap">
      <div class="login-card">
        <h2>Acceso restringido</h2>
        <p>Ingresá la contraseña para acceder al buscador de jugadores.</p>
        <div class="login-row">
          <input type="password" id="pw" placeholder="Contraseña" autocomplete="current-password"/>
          <button type="button" class="btn" id="pw-btn">Ingresar</button>
        </div>
        <div class="login-err" id="login-err"></div>
      </div>
    </div>"""

_LOGIN_JS = """    const _b64d = s => {
      const bin = atob(s); const a = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
      return a;
    };
    async function _ingresar() {
      const pass = document.getElementById("pw").value;
      const err = document.getElementById("login-err");
      err.textContent = "";
      try {
        const enc = new TextEncoder();
        const baseKey = await crypto.subtle.importKey(
          "raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]
        );
        const key = await crypto.subtle.deriveKey(
          {name: "PBKDF2", salt: _b64d(CRYPTO.salt), iterations: CRYPTO.iter, hash: "SHA-256"},
          baseKey, {name: "AES-GCM", length: 256}, false, ["decrypt"]
        );
        const plain = await crypto.subtle.decrypt(
          {name: "AES-GCM", iv: _b64d(CRYPTO.iv)}, key, _b64d(CRYPTO.ct)
        );
        DATA = JSON.parse(new TextDecoder().decode(plain));
        document.getElementById("login").style.display = "none";
        document.getElementById("app").style.display = "";
        iniciarApp();
      } catch (e) {
        err.textContent = "Contraseña incorrecta. Probá de nuevo.";
      }
    }
    document.getElementById("pw-btn").addEventListener("click", _ingresar);
    document.getElementById("pw").addEventListener("keydown", e => {
      if (e.key === "Enter") _ingresar();
    });"""


def _render_html(jugadores: List[Dict[str, object]], *, fecha: str) -> str:
    """Versión LOCAL en claro (datos embebidos sin cifrar)."""
    data_json = json.dumps(jugadores, ensure_ascii=False, separators=(",", ":"))
    cat_opts = "".join(f'<option value="{c}">{c}</option>' for c in CATEGORIAS)
    perfil_opts = "".join(f'<option value="{p}">{p}</option>' for p in PERFILES)
    perfil_opts += f'<option value="{PERFIL_INSUFICIENTE}">{PERFIL_INSUFICIENTE}</option>'
    guia = _build_perfil_guia_html()
    return _build_html(
        fecha=fecha,
        cat_opts=cat_opts,
        perfil_opts=perfil_opts,
        scout_key=CLUB_SCOUTING_KEY,
        perfil_css_map=json.dumps(_PERFIL_CSS_MAP, ensure_ascii=False),
        perfil_guia_html=guia,
        data_decl=f"let DATA = {data_json};",
        arranque="    iniciarApp();",
    )


def _cifrar_payload(
    data_json: str,
    password: str,
    *,
    iteraciones: int = PBKDF2_ITER,
    dklen: int = PBKDF2_DKLEN,
) -> Dict[str, object]:
    """Cifra el JSON con AES-256-GCM y clave derivada por PBKDF2-HMAC-SHA256."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iteraciones, dklen=dklen
    )
    # AESGCM.encrypt concatena el tag (16 bytes) al final del ciphertext.
    ct = AESGCM(key).encrypt(iv, data_json.encode("utf-8"), None)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
        "iter": iteraciones,
        "dklen": dklen,
    }


def _render_html_cifrado(
    jugadores: List[Dict[str, object]], *, fecha: str, password: str
) -> str:
    """Versión PÚBLICA: login + datos cifrados (AES-GCM) descifrados en el navegador."""
    data_json = json.dumps(jugadores, ensure_ascii=False, separators=(",", ":"))
    cripto = _cifrar_payload(data_json, password)
    cat_opts = "".join(f'<option value="{c}">{c}</option>' for c in CATEGORIAS)
    perfil_opts = "".join(f'<option value="{p}">{p}</option>' for p in PERFILES)
    perfil_opts += f'<option value="{PERFIL_INSUFICIENTE}">{PERFIL_INSUFICIENTE}</option>'
    guia = _build_perfil_guia_html()
    data_decl = "let DATA = [];\n    const CRYPTO = " + json.dumps(cripto) + ";"
    return _build_html(
        fecha=fecha,
        cat_opts=cat_opts,
        perfil_opts=perfil_opts,
        scout_key=CLUB_SCOUTING_KEY,
        perfil_css_map=json.dumps(_PERFIL_CSS_MAP, ensure_ascii=False),
        perfil_guia_html=guia,
        data_decl=data_decl,
        arranque=_LOGIN_JS,
        login_block=_LOGIN_HTML,
        app_style=' style="display:none"',
    )


# --------------------------------------------------------------------------- #
# Caché de partidos (para regenerar offline con --desde-cache)
# --------------------------------------------------------------------------- #
def _guardar_partidos_cache(partidos: List[Dict[str, str]]) -> None:
    PARTIDOS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PARTIDOS_CACHE.write_text(
        json.dumps(partidos, ensure_ascii=False), encoding="utf-8"
    )


def _cargar_partidos_cache() -> List[Dict[str, str]]:
    if PARTIDOS_CACHE.exists():
        return json.loads(PARTIDOS_CACHE.read_text(encoding="utf-8"))
    return []


def _control(jugadores: List[Dict[str, object]], partidos: List[Dict[str, str]]) -> None:
    print("\n=== CONTROL ===", file=sys.stderr)
    for edad in CATEGORIAS:
        n_part = sum(1 for p in partidos if p["categoria"] == edad)
        jugs = [j for j in jugadores if j["cat"] == edad]
        print(
            f"{edad}: {n_part} partidos · {len(jugs)} jugadores", file=sys.stderr
        )
        top = sorted(
            [j for j in jugs if j["pj"] >= 3], key=lambda j: -j["pts_p"]
        )[:5]
        for j in top:
            print(
                f"    {j['pts_p']:5.1f} Pts/p  {j['nombre']} ({j['equipo']}) "
                f"PJ={j['pj']}",
                file=sys.stderr,
            )


def main() -> int:
    p = argparse.ArgumentParser(description="Buscador local de jugadores destacados")
    p.add_argument("--widget-key", default="", help="Default: config/competencias.json")
    p.add_argument("--fecha-ini", default="2025-1-1")
    p.add_argument("--fecha-fin", default="2026-12-31")
    p.add_argument("--out-html", default=str(OUT_HTML))
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--limite", type=int, default=0, help="Tope de boxscores a descargar (debug)")
    p.add_argument("--progress", action="store_true")
    p.add_argument(
        "--desde-cache",
        action="store_true",
        help="No usa la red: parte de partidos.json + boxscores_full.json cacheados",
    )
    p.add_argument(
        "--sin-descarga",
        action="store_true",
        help="Recolecta partidos de GES pero NO descarga boxscores nuevos (usa caché)",
    )
    p.add_argument(
        "--refetch-box",
        action="store_true",
        help="Re-descarga y re-parsea TODAS las actas (para poblar pid/purl en la caché)",
    )
    p.add_argument(
        "--sin-fichas",
        action="store_true",
        help="No descarga fichas de jugador (usa solo lo cacheado en jugadores_ficha.json)",
    )
    p.add_argument(
        "--password",
        default="",
        help="Contraseña para la versión cifrada publicada (NO se guarda; pasar por CLI)",
    )
    p.add_argument(
        "--publicar-docs",
        action="store_true",
        help=f"Genera la versión cifrada en docs/ ({PUBLIC_URL}). Requiere --password",
    )
    p.add_argument("--out-docs", default=str(DOCS_HTML))
    args = p.parse_args()
    password = args.password or os.environ.get("BUSCADOR_PASSWORD", "")

    fecha = date.today().strftime("%d/%m/%Y")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.desde_cache:
        partidos = _cargar_partidos_cache()
        if not partidos:
            print("No hay partidos.json cacheado; corré sin --desde-cache primero.", file=sys.stderr)
            return 1
        if args.progress:
            print(f"Usando caché: {len(partidos)} partidos", file=sys.stderr)
    else:
        widget_key = args.widget_key or _load_widget_key()
        if not widget_key:
            print("Falta widget_key (config/competencias.json)", file=sys.stderr)
            return 1
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
        if args.progress:
            print("Recolectando partidos COMPLETOS de las 4 categorías…", file=sys.stderr)
        partidos = recolectar_partidos(
            ges,
            key=widget_key,
            fecha_ini=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            progress=args.progress,
        )
        _guardar_partidos_cache(partidos)

    tokens = [p["id_partido"] for p in partidos]
    # --refetch-box fuerza red aunque estemos en modo caché (para poblar pid/purl).
    sin_descarga_box = (args.desde_cache or args.sin_descarga) and not args.refetch_box
    boxscores = descargar_boxscores_full(
        tokens,
        workers=args.workers,
        progress=args.progress,
        limite=args.limite,
        sin_descarga=sin_descarga_box,
        refetch=args.refetch_box,
    )

    if args.progress:
        print(f"Boxscores con stats: {len(boxscores)}", file=sys.stderr)

    # Fichas de jugador (nombre completo + fecha de nacimiento) por pid.
    pid_purl = pids_purls_desde_boxscores(boxscores)
    sin_fichas = args.sin_fichas or (args.desde_cache and not args.refetch_box)
    fichas = descargar_fichas(
        pid_purl,
        workers=args.workers,
        progress=args.progress,
        sin_fichas=sin_fichas,
    )
    if args.progress:
        print(
            f"Jugadores con pid: {len(pid_purl)} · con ficha resuelta: {len(fichas)}",
            file=sys.stderr,
        )

    jugadores = agregar_jugadores(partidos, boxscores, fichas)
    jugadores = enriquecer_jugadores(jugadores)

    # Versión LOCAL en claro (no se publica).
    out_html = Path(args.out_html)
    out_html.write_text(_render_html(jugadores, fecha=fecha), encoding="utf-8")

    # Versión PÚBLICA cifrada (login + AES-GCM) para GitHub Pages.
    docs_html: Optional[str] = None
    if args.publicar_docs:
        if not password:
            print(
                "Falta --password (o variable de entorno BUSCADOR_PASSWORD) "
                "para publicar la versión cifrada en docs/.",
                file=sys.stderr,
            )
            return 1
        Path(args.out_docs).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_docs).write_text(
            _render_html_cifrado(jugadores, fecha=fecha, password=password),
            encoding="utf-8",
        )
        docs_html = args.out_docs
        if args.progress:
            print(
                f"Publicado cifrado en {docs_html} "
                f"(AES-256-GCM, PBKDF2-SHA256 x{PBKDF2_ITER})",
                file=sys.stderr,
            )

    if args.progress:
        _control(jugadores, partidos)

    print(
        json.dumps(
            {
                "partidos": len(partidos),
                "boxscores_con_stats": len(boxscores),
                "jugadores": len(jugadores),
                "por_categoria": {
                    edad: {
                        "partidos": sum(1 for x in partidos if x["categoria"] == edad),
                        "jugadores": sum(1 for j in jugadores if j["cat"] == edad),
                    }
                    for edad in CATEGORIAS
                },
                "jugadores_con_fnac": sum(1 for j in jugadores if j.get("fnac")),
                "jugadores_con_nombre_completo": sum(
                    1 for j in jugadores if j.get("nombre_completo") and j["nombre_completo"] != j["nombre"]
                ),
                "html": str(out_html),
                "docs_html": docs_html,
                "public_url": PUBLIC_URL if args.publicar_docs else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
