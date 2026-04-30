# -*- coding: utf-8 -*-
"""
Fixture argentina.basketball (handler=CargarFixture).
Ventanas por rango de fechas para reducir timeouts / respuestas enormes.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator, List, Optional, Tuple

import requests

from ingest.argbasket.fixture import (
    BASE_URL_DEFAULT,
    fetch_cargar_fixture_html,
    parse_tabla_calendarios,
)


def parse_config_date(s: str) -> date:
    """Acepta '2026-1-5', '2026-01-05', '2026/1/5' (solo componente fecha)."""
    raw = (s or "").strip().split()[0].replace("/", "-")
    parts = [int(x) for x in raw.split("-")]
    if len(parts) != 3:
        raise ValueError(f"Fecha invalida en config: {s!r}")
    y, mo, d = parts
    return date(y, mo, d)


def iter_date_windows(
    d0: date, d1: date, max_days: int = 45
) -> Iterator[Tuple[str, str]]:
    """Pares (fechaIni, fechaFin) en ISO YYYY-MM-DD, ventanas contiguas."""
    if d0 > d1:
        return
    span = max(1, int(max_days))
    cur = d0
    while cur <= d1:
        end = min(cur + timedelta(days=span - 1), d1)
        yield cur.isoformat(), end.isoformat()
        cur = end + timedelta(days=1)


class ArgentinaFixtureParser:
    """
    Descarga y parsea HTML de ``/liga-federal/fixture?handler=CargarFixture``.
    No usa el dominio widgetscab.
    """

    def __init__(
        self,
        *,
        base_url: str = BASE_URL_DEFAULT,
        session: Optional[requests.Session] = None,
        timeout_s: int = 60,
        chunk_days: int = 45,
    ) -> None:
        self._base_url = base_url
        self._session = session or requests.Session()
        self._timeout_s = timeout_s
        self._chunk_days = chunk_days

    def fetch_rows_window(
        self, comp_cat_id: int, fecha_ini: str, fecha_fin: str
    ) -> List[Dict[str, str]]:
        html = fetch_cargar_fixture_html(
            comp_cat_id=comp_cat_id,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            base_url=self._base_url,
            session=self._session,
            timeout_s=self._timeout_s,
        )
        return parse_tabla_calendarios(html, base_url=self._base_url)

    def fetch_all_chunked(
        self,
        comp_cat_id: int,
        fecha_inicio_cfg: str,
        fecha_fin_cfg: str,
    ) -> List[Dict[str, str]]:
        d0 = parse_config_date(fecha_inicio_cfg)
        d1 = parse_config_date(fecha_fin_cfg)
        seen: set[str] = set()
        out: List[Dict[str, str]] = []
        for ini, fin in iter_date_windows(d0, d1, self._chunk_days):
            batch = self.fetch_rows_window(comp_cat_id, ini, fin)
            for row in batch:
                tok = (row.get("id_partido_token") or "").strip()
                if not tok or tok in seen:
                    continue
                seen.add(tok)
                out.append(row)
        return out
