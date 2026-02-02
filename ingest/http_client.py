from __future__ import annotations

from typing import Optional

import requests
import time
import random

from ingest.errors import NetworkError


class SessionProvider:
    _session: Optional[requests.Session] = None

    @classmethod
    def get_session(cls) -> requests.Session:
        if cls._session is None:
            cls._session = requests.Session()
        return cls._session


class HttpClient:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or SessionProvider.get_session()

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        data: Optional[dict] = None,
        timeout: int = 15,
        retries: int = 3,
        backoff_base: float = 0.5,
        backoff_factor: float = 2.0,
        jitter: float = 0.1,
    ) -> requests.Response:
        last_exception: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data,
                    timeout=timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < retries:
                        self._sleep_backoff(attempt, backoff_base, backoff_factor, jitter)
                        continue
                    raise NetworkError(
                        f"Respuesta HTTP {response.status_code} al llamar {url}"
                    )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_exception = exc
                if attempt < retries:
                    self._sleep_backoff(attempt, backoff_base, backoff_factor, jitter)
                    continue
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    status = exc.response.status_code
                    raise NetworkError(
                        f"Respuesta HTTP {status} al llamar {url}"
                    ) from exc
                raise NetworkError(f"Fallo de red al llamar {url}") from exc
        raise NetworkError(f"Fallo de red al llamar {url}") from last_exception

    @staticmethod
    def _sleep_backoff(
        attempt: int, base: float, factor: float, jitter: float
    ) -> None:
        delay = base * (factor ** attempt)
        delay += random.uniform(0, jitter)
        time.sleep(delay)
