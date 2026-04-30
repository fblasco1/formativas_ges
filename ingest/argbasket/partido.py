from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL_DEFAULT = "https://argentina.basketball"

_RE_DORSAL = re.compile(r"^\s*(\d+)\s*(\*)?\s*$")
_RE_SCORE = re.compile(r"\|\s*(\d+)\s*-\s*(\d+)\s*$")
_RE_CUARTO = re.compile(r"\bCuarto\s+(\d+)\s*-\s*(\d{2}:\d{2}:\d{2})\b", flags=re.I)
_RE_HORA_REAL = re.compile(r"(\d{1,2}:\d{2}:\d{2})\s*h\.", flags=re.I)
_RE_TIRO_BLOCK = re.compile(r"^\s*(?:(\d{1,3})\s+)?(\d+)\s*/\s*(\d+)\s*$")


def _default_headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,*/*",
        "Referer": referer,
    }


def build_estadisticas_url(
    id_partido_token: str, *, base_url: str = BASE_URL_DEFAULT
) -> str:
    path = f"liga-federal/partido/estadisticas/{id_partido_token}"
    url = urljoin(base_url.rstrip("/") + "/", path)
    if "?" not in url:
        url = url + "?key="
    return url


def build_en_vivo_url(
    id_partido_token: str, *, base_url: str = BASE_URL_DEFAULT
) -> str:
    path = f"liga-federal/partido/en-vivo/{id_partido_token}"
    url = urljoin(base_url.rstrip("/") + "/", path)
    if "?" not in url:
        url = url + "?key="
    return url


def fetch_partido_estadisticas_html(
    *,
    id_partido_token: str,
    base_url: str = BASE_URL_DEFAULT,
    referer: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
) -> str:
    """
    Descarga el HTML de boxscore desde:
    /liga-federal/partido/estadisticas/{token}==?key=
    """
    s = session or requests.Session()
    url = build_estadisticas_url(id_partido_token, base_url=base_url)
    ref = referer or url
    resp = s.get(url, headers=_default_headers(ref), timeout=timeout_s)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def fetch_partido_en_vivo_html(
    *,
    id_partido_token: str,
    base_url: str = BASE_URL_DEFAULT,
    referer: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
) -> str:
    """
    Descarga el HTML/texto de play-by-play desde:
    /liga-federal/partido/en-vivo/{token}==?key=
    """
    s = session or requests.Session()
    url = build_en_vivo_url(id_partido_token, base_url=base_url)
    ref = referer or url
    resp = s.get(url, headers=_default_headers(ref), timeout=timeout_s)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def _to_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    if value.lstrip("-").isdigit():
        return int(value)
    return None


def _parse_ai(value: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse "3/11" -> (3, 11)
    """
    value = (value or "").strip()
    if not value:
        return (None, None)
    if "/" not in value:
        return (None, None)
    a, i = value.split("/", 1)
    return (_to_int(a), _to_int(i))


def _parse_tiro_block(value: str) -> Dict[str, Optional[int]]:
    """
    Parse celdas tipo:
    - "42 3/7" -> {"pct":42, "a":3, "i":7}
    - "11/34" -> {"pct":None, "a":11, "i":34}
    - "0 0/0" -> {"pct":0, "a":0, "i":0}
    """
    value = (value or "").strip()
    if not value:
        return {"pct": None, "a": None, "i": None}
    m = _RE_TIRO_BLOCK.match(value.replace(" ", " ").strip())
    if not m:
        # fallback: si viene solo como A/I
        a, i = _parse_ai(value)
        return {"pct": None, "a": a, "i": i}
    pct_s, a_s, i_s = m.groups()
    return {"pct": _to_int(pct_s or ""), "a": _to_int(a_s), "i": _to_int(i_s)}


@dataclass(frozen=True)
class BoxscoreJugador:
    dorsal: Optional[int]
    inicial: bool
    nombre: str
    min: Optional[str]
    pts: Optional[int]
    t2: Dict[str, Optional[int]]
    t3: Dict[str, Optional[int]]
    tl: Dict[str, Optional[int]]
    reb_def: Optional[int]
    reb_of: Optional[int]
    reb_tot: Optional[int]
    ast: Optional[int]
    rec: Optional[int]
    per: Optional[int]
    tap_com: Optional[int]
    tap_rec: Optional[int]
    fal_com: Optional[int]
    fal_rec: Optional[int]
    val: Optional[int]
    mas_menos: Optional[int]

    def to_dict(self) -> Dict[str, object]:
        return {
            "dorsal": self.dorsal,
            "inicial": self.inicial,
            "nombre": self.nombre,
            "min": self.min,
            "pts": self.pts,
            "t2": self.t2,
            "t3": self.t3,
            "tl": self.tl,
            "rebdef": self.reb_def,
            "rebofe": self.reb_of,
            "rebtot": self.reb_tot,
            "ast": self.ast,
            "rec": self.rec,
            "per": self.per,
            "tap_com": self.tap_com,
            "tap_rec": self.tap_rec,
            "fal_com": self.fal_com,
            "fal_rec": self.fal_rec,
            "val": self.val,
            "masmenos": self.mas_menos,
        }


def _parse_player_row(cells: List[str]) -> Optional[BoxscoreJugador]:
    """
    Parse de una fila de `tabla-estadisticas` de argentina.basketball.

    Formato típico (con una celda inicial de imagen):
      [img, dorsal, nombre, min, pts,
       t2_ai, t2_pct, t3_ai, t3_pct, tl_ai, tl_pct,
       rebdef, rebofe, rebtot, ast, rec, per,
       tap_com, tap_rec, fal_com, fal_rec, val, masmenos]

    Este parser es tolerante: si detecta un leading cell vacío (imagen), lo descarta.
    """
    if not cells:
        return None
    cells = [(c or "").strip() for c in cells]
    # Si la primera celda está vacía (p.ej. imagen), y la segunda parece dorsal, descartamos la primera.
    if len(cells) >= 2 and (not cells[0] or cells[0] == "\xa0") and _RE_DORSAL.match(cells[1] or ""):
        cells = cells[1:]

    if not cells:
        return None

    first = (cells[0] or "").strip()
    if first.lower().startswith("totales") or first.lower().startswith("total"):
        return None

    m = _RE_DORSAL.match(first)
    dorsal = int(m.group(1)) if m and m.group(1) else None
    inicial = bool(m and m.group(2))

    nombre = (cells[1] if len(cells) > 1 else "").strip()
    if not nombre:
        return None

    min_s = (cells[2] if len(cells) > 2 else "").strip() or None
    pts = _to_int((cells[3] if len(cells) > 3 else "").strip())

    # Tiros: vienen en 2 celdas (A/I y %). Construimos el bloque unificado.
    t2_ai = cells[4] if len(cells) > 4 else ""
    t2_pct = cells[5] if len(cells) > 5 else ""
    t3_ai = cells[6] if len(cells) > 6 else ""
    t3_pct = cells[7] if len(cells) > 7 else ""
    tl_ai = cells[8] if len(cells) > 8 else ""
    tl_pct = cells[9] if len(cells) > 9 else ""

    t2 = {"pct": _to_int(t2_pct), **{k: v for k, v in _parse_tiro_block(t2_ai).items() if k in {"a", "i"}}}
    t3 = {"pct": _to_int(t3_pct), **{k: v for k, v in _parse_tiro_block(t3_ai).items() if k in {"a", "i"}}}
    tl = {"pct": _to_int(tl_pct), **{k: v for k, v in _parse_tiro_block(tl_ai).items() if k in {"a", "i"}}}

    reb_def = _to_int(cells[10] if len(cells) > 10 else "")
    reb_of = _to_int(cells[11] if len(cells) > 11 else "")
    reb_tot = _to_int(cells[12] if len(cells) > 12 else "")

    ast = _to_int(cells[13] if len(cells) > 13 else "")
    rec = _to_int(cells[14] if len(cells) > 14 else "")
    per = _to_int(cells[15] if len(cells) > 15 else "")
    tap_com = _to_int(cells[16] if len(cells) > 16 else "")
    tap_rec = _to_int(cells[17] if len(cells) > 17 else "")
    fal_com = _to_int(cells[18] if len(cells) > 18 else "")
    fal_rec = _to_int(cells[19] if len(cells) > 19 else "")
    val = _to_int(cells[20] if len(cells) > 20 else "")
    mas_menos = _to_int(cells[21] if len(cells) > 21 else "")

    return BoxscoreJugador(
        dorsal=dorsal,
        inicial=inicial,
        nombre=nombre,
        min=min_s,
        pts=pts,
        t2=t2,
        t3=t3,
        tl=tl,
        reb_def=reb_def,
        reb_of=reb_of,
        reb_tot=reb_tot,
        ast=ast,
        rec=rec,
        per=per,
        tap_com=tap_com,
        tap_rec=tap_rec,
        fal_com=fal_com,
        fal_rec=fal_rec,
        val=val,
        mas_menos=mas_menos,
    )


def parse_boxscore_html(html: str) -> Dict[str, object]:
    """
    Devuelve un dict con:
      {
        "equipos": [
          {"nombre": ..., "entrenador": ..., "jugadores": [...]} ,
          {"nombre": ..., "entrenador": ..., "jugadores": [...]}
        ]
      }
    """
    soup = BeautifulSoup(html, "html.parser")

    # Heurística: la página suele renderizar el nombre del equipo como texto suelto en títulos
    # y luego una tabla con filas de jugadores.
    tables = soup.find_all("table")
    equipos: List[Dict[str, object]] = []

    for tbl in tables:
        # Identificamos tablas de boxscore por presencia de "PTOS" o "Min" en el texto.
        ttext = (tbl.get_text(" ", strip=True) or "").upper()
        if "PTOS" not in ttext or "MIN" not in ttext:
            continue

        # En el HTML real el nombre/entrenador vienen en divs anteriores.
        nombre = ""
        entrenador = ""
        # Buscar dentro de la misma "tarjeta-widget" (viene repetida para local/visitante).
        cont = tbl.find_parent("div", class_=re.compile(r"\btarjeta-widget\b", re.I))
        if cont:
            nombre_el = tbl.find_previous("div", class_=re.compile(r"\bnombre-equipo\b", re.I))
            if nombre_el and cont in nombre_el.parents:
                strong = nombre_el.find("strong")
                nombre = (
                    strong.get_text(" ", strip=True)
                    if strong
                    else nombre_el.get_text(" ", strip=True)
                )
            ent_el = tbl.find_previous("div", class_=re.compile(r"\bentrenador\b", re.I))
            if ent_el and cont in ent_el.parents:
                span = ent_el.find("span")
                entrenador = span.get_text(" ", strip=True) if span else ""
        if not nombre:
            # fallback: buscar un strong anterior
            prev_strong = tbl.find_previous("strong")
            if prev_strong:
                nombre = prev_strong.get_text(" ", strip=True)

        jugadores: List[Dict[str, object]] = []
        tbody = tbl.find("tbody") or tbl
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            jugador = _parse_player_row(cells)
            if jugador:
                jugadores.append(jugador.to_dict())

        if jugadores:
            equipos.append(
                {
                    "nombre": nombre,
                    "entrenador": entrenador,
                    "jugadores": jugadores,
                }
            )

    return {"equipos": equipos}


def parse_play_by_play_text(text: str) -> List[Dict[str, object]]:
    """
    El endpoint /en-vivo/ suele devolver texto “line-oriented” (o HTML que se puede
    transformar a texto) con líneas del estilo:

      CANASTA-2P NOMBRE #23 - Cuarto 4 - 00:00:22 | 30 - 74
      INICIO-PARTIDO 14:02:20 h.

    Devuelve una lista de eventos ordenada como aparece.
    """
    out: List[Dict[str, object]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Eventos de hora real (inicio/final de partido o de período)
        hora_m = _RE_HORA_REAL.search(line)
        cuarto_m = _RE_CUARTO.search(line)
        score_m = _RE_SCORE.search(line)

        event: Dict[str, object] = {"raw": line}

        if hora_m and not cuarto_m:
            event["hora_real"] = hora_m.group(1)
            event["tipo"] = line.split(hora_m.group(0), 1)[0].strip().replace("  ", " ")
            out.append(event)
            continue

        # Parse más estructurado (tipo + jugador + dorsal + cuarto + clock)
        if "CUARTO" in line.upper() and "-" in line:
            # tipo: hasta antes del nombre (heurística: primera palabra/grupo)
            # En la práctica el tipo viene como "CANASTA-2P", "FALTA-COMETIDA", etc.
            tipo = line.split(" ", 1)[0].strip()
            rest = line[len(tipo) :].strip()

            # dorsal: "#NN"
            dorsal = None
            if "#" in rest:
                before_hash, after_hash = rest.split("#", 1)
                jugador = before_hash.strip(" -").strip()
                dorsal_s = after_hash.split(" ", 1)[0].strip()
                dorsal = _to_int(dorsal_s)
            else:
                jugador = rest.split("Cuarto", 1)[0].strip(" -").strip()

            if cuarto_m:
                event["cuarto"] = _to_int(cuarto_m.group(1))
                event["clock"] = cuarto_m.group(2)
            if score_m:
                event["score_local"] = _to_int(score_m.group(1))
                event["score_visitante"] = _to_int(score_m.group(2))

            event["tipo"] = tipo
            event["jugador"] = jugador or None
            event["dorsal"] = dorsal
            out.append(event)
            continue

        # Fallback: dejar raw
        out.append(event)

    return out


def parse_play_by_play_html(html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.select_one("ul.listadoAccionesPartido")
    if not ul:
        # fallback textual
        return parse_play_by_play_text(soup.get_text("\n", strip=True))

    out: List[Dict[str, object]] = []
    for li in ul.find_all("li", class_=re.compile(r"\baccion\b", re.I)):
        info = li.find("div", class_=re.compile(r"\binformacion\b", re.I))
        if not info:
            continue

        titulo_el = info.find("strong", class_=re.compile(r"\btitulo\b", re.I))
        titulo = titulo_el.get_text(" ", strip=True) if titulo_el else ""
        spans = info.find_all("span", class_=re.compile(r"\binformacion\b", re.I))
        # Heurística:
        # - si hay 1 span, puede ser hora real
        # - si hay >=2 spans, el 1ro suele ser jugador y el último suele contener dorsal/cuarto/clock
        hora_real = None
        jugador = None
        dorsal = None
        cuarto = None
        clock = None
        score_local = None
        score_visitante = None

        if spans:
            # Hora real suele estar en spans[0] para FINAL/INICIO-PERIODO
            h = _RE_HORA_REAL.search(spans[0].get_text(" ", strip=True))
            if h:
                hora_real = h.group(1)

        if len(spans) >= 2:
            jugador = spans[0].get_text(" ", strip=True).strip() or None
            detalle = spans[-1].get_text(" ", strip=True)
            # dorsal
            if "#" in detalle:
                try:
                    after_hash = detalle.split("#", 1)[1]
                    dorsal_s = after_hash.split(" ", 1)[0].strip()
                    dorsal = _to_int(dorsal_s)
                except Exception:
                    dorsal = None
            cm = _RE_CUARTO.search(detalle)
            if cm:
                cuarto = _to_int(cm.group(1))
                clock = cm.group(2)

        # score puede venir en el texto completo del li (ej: "| 30 - 74")
        score_m = _RE_SCORE.search(li.get_text(" ", strip=True))
        if score_m:
            score_local = _to_int(score_m.group(1))
            score_visitante = _to_int(score_m.group(2))

        clases = " ".join(li.get("class") or [])
        equipo = "local" if re.search(r"\blocal\b", clases, flags=re.I) else None
        if not equipo and re.search(r"\bvisitante\b", clases, flags=re.I):
            equipo = "visitante"

        out.append(
            {
                "tipo": titulo or None,
                "equipo": equipo,
                "jugador": jugador,
                "dorsal": dorsal,
                "cuarto": cuarto,
                "clock": clock,
                "hora_real": hora_real,
                "score_local": score_local,
                "score_visitante": score_visitante,
                "raw": li.get_text(" ", strip=True),
            }
        )

    return out

