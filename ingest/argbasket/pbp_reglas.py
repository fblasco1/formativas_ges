# -*- coding: utf-8 -*-
"""
Análisis de play-by-play (en-vivo) de argentina.basketball para reglas MINI.

Detecta, por partido:
  - Sustituciones DURANTE el 3er cuarto (reloj < 10:00, excluyendo la
    formación de arranque del cuarto que se registra a 00:10:00).
  - Jugadores que estuvieron en cancha en cuartos consecutivos.

El reloj del PBP es descendente: 00:10:00 = inicio del cuarto, 00:00:00 = fin.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

import requests

from ingest.argbasket.partido import parse_play_by_play_html

DURACION_CUARTO_SEG = 10 * 60  # 10:00 en formativas MINI

_RE_DORSAL = re.compile(r"#(\d+)")
_RE_CUARTO = re.compile(r"Cuarto\s+(\d+)\s*-\s*(\d{2}:\d{2}:\d{2})", flags=re.I)
# Un nombre válido tiene formato "APELLIDO, NOMBRE" en mayúsculas.
_RE_NOMBRE_VALIDO = re.compile(
    r"^[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ.'\- ]*,\s*[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ.'\- ]*$",
    flags=re.U,
)


def _clock_a_segundos(clock: Optional[str]) -> Optional[int]:
    if not clock:
        return None
    parts = str(clock).split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        h, m, s = nums
        return h * 3600 + m * 60 + s
    if len(nums) == 2:
        m, s = nums
        return m * 60 + s
    return None


def _normaliza_nombre(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", nombre or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _tipo_base(tipo: Optional[str]) -> str:
    t = (tipo or "").strip()
    t = re.sub(r"\s*#\d+\s*$", "", t)  # cambios traen "#NN" en el título
    return t.strip().upper()


def _extrae_jugador(raw: str, tipo_base: str) -> Dict[str, Optional[str]]:
    raw = raw or ""
    md = _RE_DORSAL.search(raw)
    dorsal = md.group(1) if md else None

    # Quitar el prefijo del tipo ("CANASTA-2P", "REBOTE-OFENSIVO", etc.) para
    # que no se mezcle con el apellido del jugador.
    work = raw
    if tipo_base and work.upper().startswith(tipo_base):
        work = work[len(tipo_base):]
    work = _RE_DORSAL.sub("", work)         # remover "#NN"
    work = re.split(r"Cuarto", work, maxsplit=1)[0]  # cortar antes de "Cuarto N"
    nombre = re.sub(r"\s+", " ", work).strip(" -|").strip()
    nombre = re.sub(r"\s+,", ",", nombre)   # "DELGADO , X" -> "DELGADO, X"
    if not _RE_NOMBRE_VALIDO.match(nombre):
        nombre = None
    return {"dorsal": dorsal, "nombre": nombre}


def _identidad(equipo: Optional[str], nombre: Optional[str], dorsal: Optional[str]) -> Optional[str]:
    eq = (equipo or "?")
    if nombre:
        return f"{eq}|{_normaliza_nombre(nombre)}"
    if dorsal:
        return f"{eq}|#{dorsal.lstrip('0') or '0'}"
    return None


def enriquecer_eventos(eventos: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Agrega tipo_base, nombre, dorsal, clock_seg e identidad a cada evento."""
    out: List[Dict[str, object]] = []
    for e in eventos:
        raw = str(e.get("raw") or "")
        tipo_base = _tipo_base(e.get("tipo"))
        jug = _extrae_jugador(raw, tipo_base)
        nombre = jug["nombre"]
        dorsal = jug["dorsal"]
        equipo = e.get("equipo")
        cuarto = e.get("cuarto")
        if cuarto is None:
            m = _RE_CUARTO.search(raw)
            if m:
                cuarto = int(m.group(1))
        clock_seg = _clock_a_segundos(e.get("clock"))
        out.append(
            {
                **e,
                "tipo_base": tipo_base,
                "nombre": nombre,
                "dorsal_pbp": dorsal,
                "cuarto": cuarto,
                "clock_seg": clock_seg,
                "identidad": _identidad(equipo, nombre, dorsal),
            }
        )
    return out


def analizar_eventos(eventos_crudos: List[Dict[str, object]]) -> Dict[str, object]:
    """
    Devuelve un dict con el análisis del partido a partir de los eventos crudos
    de ``parse_play_by_play_html``.
    """
    eventos = enriquecer_eventos(eventos_crudos)

    cuartos_detectados = sorted(
        {int(e["cuarto"]) for e in eventos if isinstance(e.get("cuarto"), int)}
    )
    tiene_pbp = bool(eventos) and bool(cuartos_detectados)

    # --- Sustituciones DURANTE el 3er cuarto (reloj < 10:00) ---
    subs_q3: List[Dict[str, object]] = []
    vistos_q3: set = set()
    for e in eventos:
        if e.get("cuarto") != 3:
            continue
        tb = e.get("tipo_base") or ""
        if not tb.startswith("CAMBIO-JUGADOR"):
            continue
        cs = e.get("clock_seg")
        if cs is None or cs >= DURACION_CUARTO_SEG:
            continue  # excluye formación de arranque (10:00)
        accion = "ENTRA" if "ENTRA" in tb else ("SALE" if "SALE" in tb else "CAMBIO")
        # El feed a veces repite el mismo evento; deduplicar.
        clave = (e.get("equipo"), accion, e.get("identidad"), e.get("clock"))
        if clave in vistos_q3:
            continue
        vistos_q3.add(clave)
        subs_q3.append(
            {
                "equipo": e.get("equipo"),
                "accion": accion,
                "nombre": e.get("nombre"),
                "dorsal": e.get("dorsal_pbp"),
                "clock": e.get("clock"),
            }
        )

    subs_q3_entra = sum(1 for s in subs_q3 if s["accion"] == "ENTRA")
    subs_q3_sale = sum(1 for s in subs_q3 if s["accion"] == "SALE")

    # --- Cuartos en cancha por jugador ---
    cuartos_por_jugador: Dict[str, Dict[str, object]] = {}
    for e in eventos:
        ident = e.get("identidad")
        cuarto = e.get("cuarto")
        if not ident or not isinstance(cuarto, int):
            continue
        info = cuartos_por_jugador.setdefault(
            ident,
            {
                "equipo": e.get("equipo"),
                "nombre": e.get("nombre"),
                "dorsal": e.get("dorsal_pbp"),
                "cuartos": set(),
            },
        )
        info["cuartos"].add(cuarto)
        if not info.get("nombre") and e.get("nombre"):
            info["nombre"] = e.get("nombre")

    # --- Jugadores que jugaron cuartos consecutivos ---
    consecutivos: List[Dict[str, object]] = []
    for ident, info in cuartos_por_jugador.items():
        qs = sorted(info["cuartos"])
        pares = [(a, b) for a, b in zip(qs, qs[1:]) if b == a + 1]
        if pares:
            consecutivos.append(
                {
                    "equipo": info.get("equipo"),
                    "nombre": info.get("nombre"),
                    "dorsal": info.get("dorsal"),
                    "cuartos": qs,
                    "pares": pares,
                }
            )

    consecutivos.sort(key=lambda c: (str(c.get("equipo") or ""), str(c.get("nombre") or "")))

    return {
        "tiene_pbp": tiene_pbp,
        "n_eventos": len(eventos),
        "cuartos": cuartos_detectados,
        "subs_q3": subs_q3,
        "subs_q3_entra": subs_q3_entra,
        "subs_q3_sale": subs_q3_sale,
        "hubo_subs_q3": bool(subs_q3),
        "jugadores_consecutivos": consecutivos,
        "n_consecutivos": len(consecutivos),
        "hubo_consecutivos": bool(consecutivos),
    }


def _en_vivo_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/en-vivo/"
        f"{token.strip()}==?key="
    )


def fetch_y_analizar(
    token: str, *, session: Optional[requests.Session] = None, timeout_s: int = 45
) -> Dict[str, object]:
    s = session or requests.Session()
    url = _en_vivo_url(token)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,*/*",
        "Referer": url,
    }
    resp = s.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    eventos = parse_play_by_play_html(resp.text)
    return analizar_eventos(eventos)
