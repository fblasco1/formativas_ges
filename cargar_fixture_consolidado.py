from __future__ import annotations

import csv
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from ingest.argbasket.partido import (
    BASE_URL_DEFAULT,
    fetch_partido_en_vivo_html,
    parse_play_by_play_html,
)
from persist.persistir_postgres import connect


CSV_HEADER: Sequence[str] = (
    "compCatId",
    "Categoria",
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
)


_RE_HORA_REAL = re.compile(r"(\d{1,2}:\d{2}:\d{2})\s*h\.", flags=re.I)
_RE_FINAL_PERIODO_N = re.compile(r"FINAL-PERIODO\s+(\d+)", flags=re.I)


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        return int(s)
    return None


def _safe_get(d: Any, *path: str) -> Any:
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _extract_pts_from_estadisticas(estadisticas: Any) -> Tuple[Optional[int], Optional[int]]:
    """
    Espec requerido por el usuario:
    - PTS_LOCAL = estadisticas.totaleslocal.pts
    - PTS_VISITANTE = estadisticas.totalesvisitante.pts
    """
    if not isinstance(estadisticas, dict):
        return (None, None)
    pl = _to_int(_safe_get(estadisticas, "totaleslocal", "pts"))
    pv = _to_int(_safe_get(estadisticas, "totalesvisitante", "pts"))
    return (pl, pv)


def _extract_inicio_fin_from_pbp(estadisticas: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca INICIO-PARTIDO / FINAL-PARTIDO en el play-by-play y devuelve HH:MM:SS.
    Soporta dos formatos:
    - eventos ya parseados: {"tipo": "...", "hora_real": "14:12:54", "raw": "..."}
    - eventos raw: líneas o strings donde aparece "14:12:54 h."
    """
    if not isinstance(estadisticas, dict):
        return (None, None)

    pbp = estadisticas.get("play_by_play") or estadisticas.get("playByPlay") or None
    if pbp is None:
        return (None, None)

    inicio: Optional[str] = None
    fin: Optional[str] = None
    fin_periodo_max: Optional[int] = None

    def consume_line(tipo: Optional[str], raw: str, hora_real: Optional[str]) -> None:
        nonlocal inicio, fin, fin_periodo_max
        t = (tipo or "").strip().upper()
        raw_u = (raw or "").strip().upper()
        hr = (hora_real or "").strip() or None
        if not hr:
            m = _RE_HORA_REAL.search(raw or "")
            if m:
                hr = m.group(1)
        if not hr:
            return
        if "INICIO-PARTIDO" in t or "INICIO-PARTIDO" in raw_u:
            if inicio is None:
                inicio = hr
        # En muchos PBP no existe FINAL-PARTIDO.
        # Para fin de partido: elegir FINAL-PERIODO con el mayor N (4,5,... OT) para evitar
        # el problema de orden (a veces el PBP viene del más nuevo al más viejo).
        if "FINAL-PARTIDO" in t or "FINAL-PARTIDO" in raw_u:
            fin = hr
        if "FINAL-PERIODO" in t or "FINAL-PERIODO" in raw_u:
            m = _RE_FINAL_PERIODO_N.search(t) or _RE_FINAL_PERIODO_N.search(raw_u)
            n = _to_int(m.group(1)) if m else None
            # Si no pudimos parsear N, igual usamos hr como fallback.
            if n is None:
                if fin is None:
                    fin = hr
                return
            if fin_periodo_max is None or n >= fin_periodo_max:
                fin_periodo_max = n
                fin = hr

    if isinstance(pbp, list):
        for ev in pbp:
            if isinstance(ev, dict):
                consume_line(ev.get("tipo"), str(ev.get("raw") or ""), ev.get("hora_real"))
            elif isinstance(ev, str):
                consume_line(None, ev, None)
    elif isinstance(pbp, str):
        for line in pbp.splitlines():
            consume_line(None, line, None)

    return (inicio, fin)


def _extract_inicio_fin_from_pbp_events(pbp_events: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Igual que `_extract_inicio_fin_from_pbp` pero operando sobre eventos ya parseados
    (lista de dicts o texto). Se usa cuando el PBP viene desde el endpoint /en-vivo/.
    """
    inicio: Optional[str] = None
    fin: Optional[str] = None
    fin_periodo_max: Optional[int] = None

    def consume_line(tipo: Optional[str], raw: str, hora_real: Optional[str]) -> None:
        nonlocal inicio, fin, fin_periodo_max
        t = (tipo or "").strip().upper()
        raw_u = (raw or "").strip().upper()
        hr = (hora_real or "").strip() or None
        if not hr:
            m = _RE_HORA_REAL.search(raw or "")
            if m:
                hr = m.group(1)
        if not hr:
            return
        if "INICIO-PARTIDO" in t or "INICIO-PARTIDO" in raw_u:
            if inicio is None:
                inicio = hr
        # En vivo / PBP frecuentemente no tiene evento FINAL-PARTIDO.
        # Usamos el FINAL-PERIODO con mayor N (4,5,... incluyendo OTs) como hora_fin_partido.
        if "FINAL-PARTIDO" in t or "FINAL-PARTIDO" in raw_u:
            fin = hr
        if "FINAL-PERIODO" in t or "FINAL-PERIODO" in raw_u:
            m = _RE_FINAL_PERIODO_N.search(t) or _RE_FINAL_PERIODO_N.search(raw_u)
            n = _to_int(m.group(1)) if m else None
            if n is None:
                if fin is None:
                    fin = hr
                return
            if fin_periodo_max is None or n >= fin_periodo_max:
                fin_periodo_max = n
                fin = hr

    if isinstance(pbp_events, list):
        for ev in pbp_events:
            if isinstance(ev, dict):
                consume_line(ev.get("tipo"), str(ev.get("raw") or ""), ev.get("hora_real"))
            elif isinstance(ev, str):
                consume_line(None, ev, None)
    elif isinstance(pbp_events, str):
        for line in pbp_events.splitlines():
            consume_line(None, line, None)

    return (inicio, fin)


thread_local = threading.local()


def _get_session() -> requests.Session:
    s = getattr(thread_local, "session", None)
    if s is None:
        s = requests.Session()
        thread_local.session = s
    return s


def _fetch_inicio_fin_from_web(
    token: str, *, base_url: str, timeout_s: int
) -> Tuple[Optional[str], Optional[str]]:
    """
    Descarga PBP desde argentina.basketball y extrae INICIO/FINAL del partido.
    """
    token = (token or "").strip()
    if not token:
        return (None, None)
    # En algunos casos el ID puede venir sin padding '=='
    if not token.endswith("=="):
        token = token + "=="

    s = _get_session()
    html = fetch_partido_en_vivo_html(
        id_partido_token=token,
        base_url=base_url,
        session=s,
        timeout_s=timeout_s,
    )
    pbp_events = parse_play_by_play_html(html)
    return _extract_inicio_fin_from_pbp_events(pbp_events)


def _parse_csv_rows(path: str) -> Iterable[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (v or "").strip() for k, v in row.items()}


def _write_csv_rows(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_HEADER))
        w.writeheader()
        for r in rows:
            out = {k: ("" if r.get(k) is None else r.get(k)) for k in CSV_HEADER}
            w.writerow(out)


def _fecha_prefix(fecha_programada: str) -> str:
    """
    En `partidos.fecha` suele venir 'dd/mm/yyyy HH:MM' o similar.
    Para matcheo tolerante: usar el prefijo 'dd/mm/yyyy'.
    """
    s = (fecha_programada or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%d/%m/%Y %H:%M")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return s.split(" ", 1)[0].strip()


def _fetch_partidos_por_categorias(
    cur, categoria_ids: List[int]
) -> List[Dict[str, Any]]:
    if not categoria_ids:
        return []
    # Evitar SQL dinámico complejo: usar ANY(%s) con array.
    cur.execute(
        """
        SELECT
            partido_id,
            categoria_id,
            categoria,
            fecha,
            local,
            visitante,
            estadisticas
        FROM partidos
        WHERE categoria_id = ANY(%s)
        """,
        (categoria_ids,),
    )
    out: List[Dict[str, Any]] = []
    for (
        partido_id,
        categoria_id,
        categoria,
        fecha,
        local,
        visitante,
        estadisticas,
    ) in cur.fetchall():
        out.append(
            {
                "partido_id": partido_id,
                "categoria_id": categoria_id,
                "categoria": categoria,
                "fecha": fecha,
                "local": local,
                "visitante": visitante,
                "estadisticas": estadisticas,
            }
        )
    return out


def _row_key(comp_cat_id: Optional[int], partido_id_token: str) -> Optional[Tuple[int, str]]:
    if comp_cat_id is None:
        return None
    token = (partido_id_token or "").strip()
    if not token:
        return None
    return (comp_cat_id, token)


def _build_csv_row_from_db(p: Dict[str, Any]) -> Dict[str, Any]:
    comp_cat_id = _to_int(p.get("categoria_id"))
    token = (p.get("partido_id") or "").strip()
    categoria = (p.get("categoria") or "").strip()
    local = (p.get("local") or "").strip()
    visitante = (p.get("visitante") or "").strip()
    fecha = (p.get("fecha") or "").strip()
    estadisticas = p.get("estadisticas")

    pts_local, pts_visitante = _extract_pts_from_estadisticas(estadisticas)
    dif_pts = (
        (pts_local - pts_visitante)
        if (pts_local is not None and pts_visitante is not None)
        else None
    )
    # Nota: por requerimiento del usuario, las horas deben salir del endpoint /en-vivo/ (PBP).
    # En esta función dejamos None; se completa luego con fetch web si se habilita.
    hora_ini, hora_fin = (None, None)

    return {
        # Mapeo exacto pedido:
        # compCatId = categoria_id
        # Categoria = categoria
        # id_partido_token = partido_id
        # Local/Visitante = local/visitante
        # PTS_* = estadisticas.totales{local,visitante}.pts
        # DIF_PTS = PTS_LOCAL - PTS_VISITANTE
        # Fecha_Programada = fecha
        # hora_* = desde play-by-play (si existe)
        # URL_Estadisticas = vacío
        "compCatId": comp_cat_id,
        "Categoria": categoria,
        "id_partido_token": token,
        "Local": local,
        "Visitante": visitante,
        "PTS_LOCAL": pts_local,
        "PTS_VISITANTE": pts_visitante,
        "DIF_PTS": dif_pts,
        "Fecha_Programada": fecha,
        "hora_inicio_partido": hora_ini,
        "hora_fin_partido": hora_fin,
        "URL_Estadisticas": "",
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description=(
            "Exporta TODOS los partidos persistidos en Postgres a un CSV "
            "con el formato fixture_consolidado (sin crear/alterar tablas)."
        )
    )
    p.add_argument(
        "--out",
        default="",
        help="Ruta de salida. Si no se pasa, escribe 'fixture_consolidado.desde_bd.csv' en el cwd.",
    )
    p.add_argument(
        "--fetch-pbp",
        action="store_true",
        help="Completa hora_inicio_partido/hora_fin_partido consultando /en-vivo/ (recomendado).",
    )
    p.add_argument(
        "--base-url",
        default=BASE_URL_DEFAULT,
        help="Base URL para argentina.basketball (default: https://argentina.basketball).",
    )
    p.add_argument(
        "--timeout-s",
        type=int,
        default=60,
        help="Timeout por request al endpoint /en-vivo/.",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Cantidad de threads para descargar PBP en paralelo.",
    )
    p.add_argument(
        "--log",
        default="",
        help="Ruta de log. Si no se pasa, loguea solo a consola.",
    )
    p.add_argument(
        "--log-every",
        type=int,
        default=250,
        help="Loguea progreso cada N PBP completados.",
    )
    p.add_argument(
        "--checkpoint-every",
        type=int,
        default=0,
        help="Si >0, escribe un CSV parcial cada N PBP completados (en '<out>.partial.csv').",
    )
    args = p.parse_args()

    log_handlers: List[logging.Handler] = [logging.StreamHandler()]
    if args.log.strip():
        log_handlers.append(logging.FileHandler(args.log.strip(), encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=log_handlers,
    )
    log = logging.getLogger("fixture")

    out_path = args.out.strip() or "fixture_consolidado.desde_bd.csv"
    total_partidos = 0
    with_puntos = 0
    with_inicio = 0
    with_fin = 0

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    partido_id,
                    categoria_id,
                    categoria,
                    fecha,
                    local,
                    visitante,
                    estadisticas
                FROM partidos
                """
            )
            output_rows: List[Dict[str, Any]] = []
            for (
                partido_id,
                categoria_id,
                categoria,
                fecha,
                local,
                visitante,
                estadisticas,
            ) in cur.fetchall():
                total_partidos += 1
                row = _build_csv_row_from_db(
                    {
                        "partido_id": partido_id,
                        "categoria_id": categoria_id,
                        "categoria": categoria,
                        "fecha": fecha,
                        "local": local,
                        "visitante": visitante,
                        "estadisticas": estadisticas,
                    }
                )
                if row.get("PTS_LOCAL") is not None or row.get("PTS_VISITANTE") is not None:
                    with_puntos += 1
                output_rows.append(row)

    log.info(
        "Export BD OK: filas=%s con_pts=%s out=%s",
        total_partidos,
        with_puntos,
        out_path,
    )

    # Completar horas desde PBP web si se solicitó
    if args.fetch_pbp:
        tokens: List[str] = [str(r.get("id_partido_token") or "").strip() for r in output_rows]
        total_fetch = sum(1 for t in tokens if t)

        def job(idx: int, token: str) -> Tuple[int, str, Optional[str], Optional[str], Optional[str]]:
            try:
                ini, fin = _fetch_inicio_fin_from_web(
                    token, base_url=args.base_url, timeout_s=args.timeout_s
                )
                return (idx, token, ini, fin, None)
            except Exception as exc:
                return (idx, token, None, None, str(exc))

        errors = 0
        completed = 0
        first_errors: List[str] = []
        partial_path = f"{out_path}.partial.csv"
        lock = threading.Lock()

        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as ex:
            futs = [ex.submit(job, i, t) for i, t in enumerate(tokens) if t]
            for fut in as_completed(futs):
                idx, token, ini, fin, err = fut.result()
                with lock:
                    completed += 1
                    if err:
                        errors += 1
                        if len(first_errors) < 5:
                            first_errors.append(f"{token}: {err}")
                    else:
                        output_rows[idx]["hora_inicio_partido"] = ini
                        output_rows[idx]["hora_fin_partido"] = fin

                    if args.log_every and completed % int(args.log_every) == 0:
                        log.info(
                            "PBP progreso: completados=%s/%s ok=%s err=%s",
                            completed,
                            total_fetch,
                            completed - errors,
                            errors,
                        )
                    if args.checkpoint_every and int(args.checkpoint_every) > 0:
                        if completed % int(args.checkpoint_every) == 0:
                            _write_csv_rows(partial_path, output_rows)
                            log.info("Checkpoint escrito: %s", partial_path)

        with_inicio = sum(1 for r in output_rows if (r.get("hora_inicio_partido") or ""))
        with_fin = sum(1 for r in output_rows if (r.get("hora_fin_partido") or ""))
        log.info(
            "PBP fin: ok=%s err=%s con_inicio=%s con_fin=%s",
            completed - errors,
            errors,
            with_inicio,
            with_fin,
        )
        if first_errors:
            log.warning("Primeros errores (muestra): %s", " | ".join(first_errors))

    _write_csv_rows(out_path, output_rows)
    log.info("CSV final escrito: %s", out_path)

    print(
        json.dumps(
            {
                "exported_rows": total_partidos,
                "rows_with_pts": with_puntos,
                "rows_with_hora_inicio": with_inicio,
                "rows_with_hora_fin": with_fin,
                "pbp_fetch_enabled": bool(args.fetch_pbp),
                "out_csv": out_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

