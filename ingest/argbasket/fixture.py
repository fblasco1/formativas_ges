from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ingest.argbasket.io import write_csv_rows
from ingest.argbasket.lff_constants import (
    LFF_DETALLE_TORNEO_PATH,
    LFF_FIXTURE_TO_TORNEO_COMP_CAT_ID,
    LFF_TORNEO_TO_FIXTURE_COMP_CAT_ID,
    LFF_U15_DETALLE_URL,
    LFF_U15_FIXTURE_COMP_CAT_ID,
    LFF_U15_TORNEO_COMP_CAT_ID,
)

BASE_URL_DEFAULT = "https://argentina.basketball"

DEFAULT_FIELDNAMES = [
    "id_partido_token",
    "Local",
    "Visitante",
    "PTS_LOCAL",
    "PTS_VISITANTE",
    "DIF_PTS",
    "Fecha_Programada",
    "hora_inicio_partido",
    "hora_fin_partido",
    "URL_Estadisticas",
]

_RE_PARTIDO_ID = re.compile(r"/liga-federal/partido/([^/]+)/", re.I)
_RE_HORA_REAL = re.compile(r"(\d{1,2}:\d{2}:\d{2})\s*h\.", flags=re.I)


def _default_headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,*/*",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    }


def _json_headers() -> dict[str, str]:
    return {
        "User-Agent": _default_headers(BASE_URL_DEFAULT)["User-Agent"],
        "Accept": "application/json, text/plain, */*",
    }


def is_lff_u15_comp_cat_id(comp_cat_id: int) -> bool:
    known = set(LFF_U15_TORNEO_COMP_CAT_ID.values()) | set(LFF_U15_FIXTURE_COMP_CAT_ID.values())
    return int(comp_cat_id) in known


def resolve_lff_fixture_comp_cat_id(comp_cat_id: int) -> int:
    """ID torneo/detalle (4643) -> ID handler CargarFixture (5117)."""
    return LFF_TORNEO_TO_FIXTURE_COMP_CAT_ID.get(int(comp_cat_id), int(comp_cat_id))


def resolve_lff_torneo_comp_cat_id(comp_cat_id: int) -> int:
    """ID handler CargarFixture (5117) -> ID torneo/detalle (4643)."""
    return LFF_FIXTURE_TO_TORNEO_COMP_CAT_ID.get(int(comp_cat_id), int(comp_cat_id))


def genero_lff_from_comp_cat_id(comp_cat_id: int) -> Literal["masc", "fem"]:
    cid = int(comp_cat_id)
    if cid in (LFF_U15_TORNEO_COMP_CAT_ID["fem"], LFF_U15_FIXTURE_COMP_CAT_ID["fem"]):
        return "fem"
    return "masc"


def fetch_cargar_subpagina_fixture_html(
    *,
    comp_cat_id: int,
    fecha_ini: str,
    fecha_fin: str,
    genero: Literal["masc", "fem"] | None = None,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
) -> str:
    s = session or requests.Session()
    gen = genero or genero_lff_from_comp_cat_id(comp_cat_id)
    torneo_id = resolve_lff_torneo_comp_cat_id(comp_cat_id)
    referer = LFF_U15_DETALLE_URL[gen]
    s.get(referer, headers={"User-Agent": _default_headers(referer)["User-Agent"]}, timeout=timeout_s)

    path = LFF_DETALLE_TORNEO_PATH[gen]
    url = urljoin(base_url.rstrip("/") + "/", path)
    params = {
        "handler": "CargarSubPagina",
        "compCatId": str(torneo_id),
        "fechaIni": fecha_ini,
        "fechaFin": fecha_fin,
        "aux": "fixture",
    }
    resp = s.get(url, params=params, headers=_default_headers(referer), timeout=timeout_s)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def fetch_fixture_liga_federal_json(
    *,
    comp_cat_id: int,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
) -> dict[str, Any]:
    s = session or requests.Session()
    torneo_id = resolve_lff_torneo_comp_cat_id(comp_cat_id)
    url = urljoin(base_url.rstrip("/") + "/", "api/fixture/liga-federal")
    params = {
        "compCatId": str(torneo_id),
        "fechaInicio": fecha_ini,
        "fechaFin": fecha_fin,
    }
    resp = s.get(url, params=params, headers=_json_headers(), timeout=timeout_s)
    resp.raise_for_status()
    return resp.json()


def _pts_str(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value).strip()


def _dif_pts(pts_local: str, pts_visit: str) -> str:
    try:
        if pts_local != "" and pts_visit != "":
            return str(int(float(pts_local)) - int(float(pts_visit)))
    except (TypeError, ValueError):
        pass
    return ""


def parse_fixture_json(
    data: dict[str, Any], *, base_url: str = BASE_URL_DEFAULT
) -> List[Dict[str, str]]:
    partidos = data.get("partidos") or []
    out: List[Dict[str, str]] = []
    for p in partidos:
        token = _pts_str(p.get("idPartido"))
        local = _pts_str(p.get("equipoLocal"))
        visitante = _pts_str(p.get("equipoVisitante"))
        loc_ruta = _pts_str(p.get("localRuta"))
        vis_ruta = _pts_str(p.get("visitanteRuta"))
        pts_local = _pts_str(p.get("resultadoLocal"))
        pts_visit = _pts_str(p.get("resultadoVisitante"))
        fecha_hora = _pts_str(p.get("fecha"))

        slug = f"{loc_ruta}-vs-{vis_ruta}" if loc_ruta and vis_ruta else ""
        stats_url = ""
        if token and slug:
            stats_path = f"liga-federal/partido/{token}/{slug}"
            stats_url = urljoin(base_url.rstrip("/") + "/", stats_path)

        out.append(
            {
                "id_partido_token": token,
                "Local": local,
                "Visitante": visitante,
                "PTS_LOCAL": pts_local,
                "PTS_VISITANTE": pts_visit,
                "DIF_PTS": _dif_pts(pts_local, pts_visit),
                "Fecha_Programada": fecha_hora,
                "URL_Estadisticas": stats_url,
                "hora_inicio_partido": "",
                "hora_fin_partido": "",
            }
        )
    return out


def fetch_fixture_rows_lff(
    *,
    comp_cat_id: int,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
    progress: bool = False,
) -> List[Dict[str, str]]:
    """CargarFixture (ID mapeado) -> JSON API -> CargarSubPagina."""
    s = session or requests.Session()
    fixture_id = resolve_lff_fixture_comp_cat_id(comp_cat_id)
    torneo_id = resolve_lff_torneo_comp_cat_id(comp_cat_id)

    html = fetch_cargar_fixture_html(
        comp_cat_id=fixture_id,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url=base_url,
        session=s,
        timeout_s=timeout_s,
    )
    rows = parse_tabla_calendarios(html, base_url=base_url)
    if rows:
        if progress:
            print(
                f"[fixture-lff] compCatId={torneo_id} CargarFixture({fixture_id}): {len(rows)} filas",
                file=sys.stderr,
                flush=True,
            )
        return rows

    data = fetch_fixture_liga_federal_json(
        comp_cat_id=torneo_id,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url=base_url,
        session=s,
        timeout_s=timeout_s,
    )
    rows = parse_fixture_json(data, base_url=base_url)
    if rows:
        if progress:
            print(
                f"[fixture-lff] compCatId={torneo_id} JSON API: {len(rows)} filas",
                file=sys.stderr,
                flush=True,
            )
        return rows

    html = fetch_cargar_subpagina_fixture_html(
        comp_cat_id=torneo_id,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url=base_url,
        session=s,
        timeout_s=timeout_s,
    )
    rows = parse_tabla_calendarios(html, base_url=base_url)
    if progress:
        print(
            f"[fixture-lff] compCatId={torneo_id} CargarSubPagina: {len(rows)} filas",
            file=sys.stderr,
            flush=True,
        )
    return rows


def fetch_cargar_fixture_html(
    *,
    comp_cat_id: int,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
) -> str:
    s = session or requests.Session()
    url = urljoin(base_url.rstrip("/") + "/", "liga-federal/fixture")
    params = {
        "handler": "CargarFixture",
        "compCatId": str(comp_cat_id),
        "fechaIni": fecha_ini,
        "fechaFin": fecha_fin,
    }
    referer = urljoin(base_url.rstrip("/") + "/", "liga-federal/fixture")
    resp = s.get(url, params=params, headers=_default_headers(referer), timeout=timeout_s)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def _normalizar_hora_real(value: str) -> str:
    if not value:
        return ""
    m = _RE_HORA_REAL.search(value.strip())
    return m.group(1) if m else value.strip()


def extraer_hora_inicio_fin_desde_en_vivo_html(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    inicio = ""
    fin = ""
    for li in soup.find_all("li", class_=re.compile(r"\baccion\b", re.I)):
        titulo_el = li.find("strong", class_=re.compile(r"\btitulo\b", re.I))
        info_div = li.find("div", class_=re.compile(r"\binformacion\b", re.I))
        hora_el = (
            info_div.find("span", class_=re.compile(r"\binformacion\b", re.I))
            if info_div
            else None
        )

        titulo = titulo_el.get_text(" ", strip=True) if titulo_el else ""
        hora_raw = hora_el.get_text(" ", strip=True) if hora_el else ""
        titulo_norm = titulo.strip().upper().replace(" ", "")
        hora = _normalizar_hora_real(hora_raw)

        if "INICIO-PARTIDO" in titulo_norm or "INICIOPARTIDO" in titulo_norm:
            if hora:
                inicio = hora
        if "FINAL-PARTIDO" in titulo_norm or "FINALPARTIDO" in titulo_norm:
            if hora:
                fin = hora

    return (inicio, fin)


def fetch_partido_en_vivo_html(
    *,
    id_partido_token: str,
    base_url: str = BASE_URL_DEFAULT,
    referer_partido_url: str,
    session: Optional[requests.Session] = None,
    timeout_s: int = 60,
) -> str:
    s = session or requests.Session()
    path = f"liga-federal/partido/en-vivo/{id_partido_token}"
    url = urljoin(base_url.rstrip("/") + "/", path)
    if "?" not in url:
        url = url + "?key="

    headers = {
        "User-Agent": _default_headers(referer_partido_url)["User-Agent"],
        "Accept": "text/html,*/*",
        "Referer": referer_partido_url,
    }
    resp = s.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def parse_tabla_calendarios(
    html: str, *, base_url: str = BASE_URL_DEFAULT
) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tabla-calendarios")
    if not table:
        return []

    out: List[Dict[str, str]] = []
    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 8:
            continue

        local_td, visit_td = tds[1], tds[4]
        pts_local_td, pts_visit_td = tds[2], tds[3]
        fecha_td = tds[6]
        stats_td = tds[7]

        local_name = local_td.select_one("strong.nombre-equipo")
        visit_name = visit_td.select_one("strong.nombre-equipo")

        pts_local = pts_local_td.get_text(strip=True)
        pts_visit = pts_visit_td.get_text(strip=True)

        fecha_strong = fecha_td.find("strong")
        fecha_hora = (
            fecha_strong.get_text(" ", strip=True)
            if fecha_strong
            else fecha_td.get_text(" ", strip=True)
        )

        stats_a = stats_td.select_one("a.btn-estadisticas[href]")
        stats_href = stats_a.get("href").strip() if stats_a and stats_a.get("href") else ""
        stats_url = (
            urljoin(base_url.rstrip("/") + "/", stats_href.lstrip("/")) if stats_href else ""
        )

        m_partido = _RE_PARTIDO_ID.search(stats_href) if stats_href else None
        id_partido_token = m_partido.group(1) if m_partido else ""

        local = (
            (local_name.get_text(" ", strip=True) if local_name else local_td.get_text(" ", strip=True))
            .strip()
        )
        visitante = (
            (visit_name.get_text(" ", strip=True) if visit_name else visit_td.get_text(" ", strip=True))
            .strip()
        )

        dif_pts = ""
        if pts_local.isdigit() and pts_visit.isdigit():
            dif_pts = str(int(pts_local) - int(pts_visit))

        out.append(
            {
                "id_partido_token": id_partido_token,
                "Local": local,
                "Visitante": visitante,
                "PTS_LOCAL": pts_local,
                "PTS_VISITANTE": pts_visit,
                "DIF_PTS": dif_pts,
                "Fecha_Programada": fecha_hora,
                "URL_Estadisticas": stats_url,
                "hora_inicio_partido": "",
                "hora_fin_partido": "",
            }
        )

    return out


def _attach_horas_reales(
    rows: List[Dict[str, str]],
    *,
    comp_cat_id: int,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    max_horas_requests: int = 0,
    sleep_s_entre_horas: float = 0.0,
    progress: bool = False,
    progress_cada: int = 25,
) -> List[Dict[str, str]]:
    if progress:
        print(
            f"[fixture] compCatId={comp_cat_id} calendario: {len(rows)} partidos, "
            f"descargando horas reales (cada {progress_cada} aviso)...",
            file=sys.stderr,
            flush=True,
        )

    s = session or requests.Session()
    horas_hechas = 0
    for idx, row in enumerate(rows, start=1):
        if max_horas_requests and idx > max_horas_requests:
            break
        token = (row.get("id_partido_token") or "").strip()
        ref = (row.get("URL_Estadisticas") or "").strip()
        if not token or not ref:
            continue
        try:
            ev_html = fetch_partido_en_vivo_html(
                id_partido_token=token,
                base_url=base_url,
                referer_partido_url=ref,
                session=s,
            )
            ini, fin = extraer_hora_inicio_fin_desde_en_vivo_html(ev_html)
            row["hora_inicio_partido"] = ini
            row["hora_fin_partido"] = fin
        except Exception:
            row["hora_inicio_partido"] = ""
            row["hora_fin_partido"] = ""

        horas_hechas += 1
        if progress and progress_cada > 0 and horas_hechas % progress_cada == 0:
            print(
                f"[fixture] compCatId={comp_cat_id} horas: {horas_hechas} "
                f"peticiones en-vivo (fila ~{idx}/{len(rows)})",
                file=sys.stderr,
                flush=True,
            )

        if sleep_s_entre_horas > 0:
            time.sleep(sleep_s_entre_horas)

    if progress:
        print(
            f"[fixture] compCatId={comp_cat_id} listo: {horas_hechas} horas reales "
            f"sobre {len(rows)} filas del calendario",
            file=sys.stderr,
            flush=True,
        )

    return rows


def get_fixture_partidos_lff(
    *,
    comp_cat_id: int,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    incluir_horas_reales: bool = True,
    max_horas_requests: int = 0,
    sleep_s_entre_horas: float = 0.0,
    progress: bool = False,
    progress_cada: int = 25,
    timeout_s: int = 60,
) -> List[Dict[str, str]]:
    torneo_id = resolve_lff_torneo_comp_cat_id(comp_cat_id)
    rows = fetch_fixture_rows_lff(
        comp_cat_id=torneo_id,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url=base_url,
        session=session,
        timeout_s=timeout_s,
        progress=progress,
    )

    if not incluir_horas_reales:
        if progress:
            print(
                f"[fixture-lff] compCatId={torneo_id} calendario: {len(rows)} filas (sin horas reales)",
                file=sys.stderr,
                flush=True,
            )
        return rows

    return _attach_horas_reales(
        rows,
        comp_cat_id=torneo_id,
        base_url=base_url,
        session=session,
        max_horas_requests=max_horas_requests,
        sleep_s_entre_horas=sleep_s_entre_horas,
        progress=progress,
        progress_cada=progress_cada,
    )


def get_fixture_partidos_argentina_basketball(
    *,
    comp_cat_id: int,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str = BASE_URL_DEFAULT,
    session: Optional[requests.Session] = None,
    incluir_horas_reales: bool = True,
    max_horas_requests: int = 0,
    sleep_s_entre_horas: float = 0.0,
    progress: bool = False,
    progress_cada: int = 25,
) -> List[Dict[str, str]]:
    if is_lff_u15_comp_cat_id(comp_cat_id):
        return get_fixture_partidos_lff(
            comp_cat_id=comp_cat_id,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            base_url=base_url,
            session=session,
            incluir_horas_reales=incluir_horas_reales,
            max_horas_requests=max_horas_requests,
            sleep_s_entre_horas=sleep_s_entre_horas,
            progress=progress,
            progress_cada=progress_cada,
        )

    html = fetch_cargar_fixture_html(
        comp_cat_id=comp_cat_id,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url=base_url,
        session=session,
    )
    rows = parse_tabla_calendarios(html, base_url=base_url)

    if not incluir_horas_reales:
        if progress:
            print(
                f"[fixture] compCatId={comp_cat_id} calendario: {len(rows)} filas (sin horas reales)",
                file=sys.stderr,
                flush=True,
            )
        return rows

    return _attach_horas_reales(
        rows,
        comp_cat_id=comp_cat_id,
        base_url=base_url,
        session=session,
        max_horas_requests=max_horas_requests,
        sleep_s_entre_horas=sleep_s_entre_horas,
        progress=progress,
        progress_cada=progress_cada,
    )


def write_csv(path: str, rows: List[Dict[str, str]]) -> None:
    write_csv_rows(path, rows, DEFAULT_FIELDNAMES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extrae partidos desde argentina.basketball (handler=CargarFixture)"
    )
    parser.add_argument("--comp-cat-id", type=int, required=True)
    parser.add_argument("--fecha-ini", required=True, help="YYYY-MM-DD")
    parser.add_argument("--fecha-fin", required=True, help="YYYY-MM-DD")
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--output", default="fixture_argentina_basketball.csv")
    parser.add_argument("--sin-horas-reales", action="store_true")
    parser.add_argument("--max-horas", type=int, default=0)
    parser.add_argument("--sleep-horas", type=float, default=0.0)
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Imprime avance por stderr (horas reales y calendario).",
    )
    parser.add_argument(
        "--progress-cada",
        type=int,
        default=25,
        metavar="N",
        help="Cada N peticiones en-vivo imprime una línea (solo con --progress).",
    )
    args = parser.parse_args()

    rows = get_fixture_partidos_argentina_basketball(
        comp_cat_id=args.comp_cat_id,
        fecha_ini=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        base_url=args.base_url,
        incluir_horas_reales=not args.sin_horas_reales,
        max_horas_requests=args.max_horas,
        sleep_s_entre_horas=args.sleep_horas,
        progress=args.progress,
        progress_cada=args.progress_cada,
    )
    write_csv(args.output, rows)
    print(f"OK: {len(rows)} partidos -> {args.output}")

