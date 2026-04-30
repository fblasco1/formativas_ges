# -*- coding: utf-8 -*-
"""
Boxscore / estadísticas desde argentina.basketball
``/liga-federal/partido/estadisticas/{token}==?key=``.
"""

from __future__ import annotations

from typing import Dict, Optional

import requests

from ingest.argbasket.partido import (
    BASE_URL_DEFAULT,
    fetch_partido_estadisticas_html,
    parse_boxscore_html,
)


class ArgentinaStatsParser:
    """Descarga HTML del acta y parsea tablas con BeautifulSoup."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL_DEFAULT,
        session: Optional[requests.Session] = None,
        timeout_s: int = 60,
    ) -> None:
        self._base_url = base_url
        self._session = session or requests.Session()
        self._timeout_s = timeout_s

    def fetch_boxscore_payload(self, id_partido_token: str) -> Optional[Dict[str, object]]:
        if not (id_partido_token or "").strip():
            return None
        try:
            html = fetch_partido_estadisticas_html(
                id_partido_token=id_partido_token.strip(),
                base_url=self._base_url,
                referer=None,
                session=self._session,
                timeout_s=self._timeout_s,
            )
            parsed = parse_boxscore_html(html)
        except Exception:
            return None
        equipos = parsed.get("equipos") or []
        if not equipos:
            return None
        return {
            "portal": "argentina.basketball",
            "equipos": equipos,
        }
