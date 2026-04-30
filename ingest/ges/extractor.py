from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import html
import json
import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from ingest.errors import NetworkError, ParseError
from ingest.http_client import HttpClient, SessionProvider


class Extractor(ABC):
    @abstractmethod
    def get_ids_categorias(self, id_competencia: int) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def get_info_partidos(
        self,
        id_categoria: int,
        fecha_inicio: str,
        fecha_fin: str,
        key: str,
        id_fase: int = -1,
        id_grupo: int = -1,
    ) -> List[Dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def get_boxscore(self, id_partido: str) -> Optional[Dict[str, object]]:
        raise NotImplementedError


class GesDeportivaExtractor(Extractor):
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def get_ids_categorias(self, id_competencia: int) -> Dict[str, str]:
        url = (
            "https://competicionescabb.gesdeportiva.es/competicion.aspx"
            f"?competencia={id_competencia}"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            )
        }

        try:
            response = self._client.request("GET", url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")

            select_categorias = soup.find("select", {"id": "DDLCategorias"})
            if not select_categorias:
                raise ParseError(
                    "No se encontró el selector de categorías para "
                    f"la competencia {id_competencia}"
                )

            categorias: Dict[str, str] = {}
            for option in select_categorias.find_all("option"):
                nombre = option.get_text(strip=True)
                id_cat = option.get("value")
                if id_cat:
                    categorias[nombre] = id_cat
            return categorias
        except (NetworkError, ParseError) as e:
            print(f"Error al obtener categorías: {e}")
            return {}

    @staticmethod
    def _find_select(soup: BeautifulSoup, *id_candidates: str) -> Optional[Tag]:
        for candidate in id_candidates:
            sel = soup.find("select", {"id": candidate})
            if sel:
                return sel
        return None

    @staticmethod
    def _extract_options(select_tag: Tag) -> Dict[str, str]:
        options: Dict[str, str] = {}
        for option in select_tag.find_all("option"):
            nombre = option.get_text(strip=True)
            value = option.get("value")
            if value is None:
                continue
            value_str = str(value).strip()
            if not value_str:
                continue
            options[nombre] = value_str
        return options

    def get_ids_fases_grupos(
        self, id_competencia: int, id_categoria: Optional[int] = None
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Obtiene IDs de fases y grupos desde `competicion.aspx`.

        Nota: en algunas competencias los combos de fase/grupo dependen de la categoría
        seleccionada. Para robustez, si se provee `id_categoria`, se simula el postback
        de ASP.NET para que el HTML devuelva las opciones correctas.
        """
        url = (
            "https://competicionescabb.gesdeportiva.es/competicion.aspx"
            f"?competencia={id_competencia}"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            )
        }

        resp = self._client.request("GET", url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        if id_categoria is not None:
            # ASP.NET WebForms: simular el AutoPostBack del combo de categorías.
            form = soup.find("form")
            if not form:
                return {}, {}
            payload: Dict[str, str] = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if not name:
                    continue
                payload[name] = inp.get("value") or ""
            payload["__EVENTTARGET"] = "DDLCategorias"
            payload["__EVENTARGUMENT"] = ""
            payload["DDLCategorias"] = str(id_categoria)
            resp2 = self._client.request(
                "POST",
                url,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://competicionescabb.gesdeportiva.es",
                    "Referer": url,
                },
                data=payload,
                timeout=20,
            )
            soup = BeautifulSoup(resp2.text, "html.parser")

        sel_fase = self._find_select(soup, "DDLFases", "DDLFase", "DDLFASE", "DDLFaseCompeticion")
        sel_grupo = self._find_select(soup, "DDLGrupos", "DDLGrupo", "DDLGRUPO", "DDLGrupoCompeticion")

        fases = self._extract_options(sel_fase) if sel_fase else {}
        grupos = self._extract_options(sel_grupo) if sel_grupo else {}

        # Normalizar valores vacíos / "Todos".
        fases = {k: v for k, v in fases.items() if v not in {"", "0"}}
        grupos = {k: v for k, v in grupos.items() if v not in {"", "0"}}
        return fases, grupos

    def get_info_partidos(
        self,
        id_categoria: int,
        fecha_inicio: str,
        fecha_fin: str,
        key: str,
        id_fase: int = -1,
        id_grupo: int = -1,
    ) -> List[Dict[str, str]]:
        url_base = (
            "https://widgetscab.gesdeportiva.es/widget/informacion/partidos/"
            f"{id_categoria}/-3/7?fase={id_fase}&grupo={id_grupo}&equipo=-1&key={key}"
        )
        url_post = url_base
        get_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            ),
            "Referer": url_post,
            "Origin": "https://widgetscab.gesdeportiva.es",
        }
        self._client.request("GET", url_base, headers=get_headers, timeout=15)
        data = {
            "IdCategoria": id_categoria,
            "IdFase": str(id_fase),
            "IdGrupo": str(id_grupo),
            "IdEquipo": "-1",
            "Key": key,
            "FechaInicio": fecha_inicio,
            "FechaFin": fecha_fin,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url_post,
            "Origin": "https://widgetscab.gesdeportiva.es",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            ),
        }
        response = self._client.request("POST", url_post, data=data, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        partidos: List[Dict[str, str]] = []
        for link in soup.find_all("a", id=lambda x: x and "HFEstadisticas" in x):
            href = link.get("href") or ""
            match = re.search(r"/partido/([\\w-]+)==", href)
            id_partido = match.group(1) if match else ""
            fila = link.find_parent("tr")
            fecha = local = visitante = puntos_local = puntos_visitante = ""
            if fila:
                celdas = fila.find_all("td")
                if len(celdas) >= 7:
                    fecha_td = celdas[0]
                    for span in fecha_td.find_all("span", class_="d-none"):
                        span.decompose()
                    fecha = fecha_td.get_text(strip=True)
                    local = celdas[1].get_text(strip=True)
                    visitante = celdas[6].get_text(strip=True)
                    puntos_local = celdas[3].get_text(strip=True)
                    puntos_visitante = celdas[4].get_text(strip=True)
            estado = "PENDIENTE"
            pl_num = pv_num = None
            try:
                fecha_dt = datetime.strptime(fecha.split()[0], "%d/%m/%Y")
                hoy = datetime.now()
                pl = puntos_local.strip().replace("\n", "")
                pv = puntos_visitante.strip().replace("\n", "")
                pl_num = int(pl) if pl and pl.replace("-", "").isdigit() else None
                pv_num = int(pv) if pv and pv.replace("-", "").isdigit() else None
                if fecha_dt < hoy and pl_num is not None and pv_num is not None:
                    estado = "COMPLETO"
            except Exception:
                pass
            dif_pts = (pl_num - pv_num) if (pl_num is not None and pv_num is not None) else None
            partidos.append(
                {
                    "ID_PARTIDO": id_partido,
                    "Fecha": fecha,
                    "Local": local,
                    "Visitante": visitante,
                    "PTS_LOCAL": "" if pl_num is None else str(pl_num),
                    "PTS_VISITANTE": "" if pv_num is None else str(pv_num),
                    "DIF_PTS": "" if dif_pts is None else str(dif_pts),
                    "Estado": estado,
                    "URL": href,
                    "ID_FASE": str(id_fase),
                    "ID_GRUPO": str(id_grupo),
                }
            )
        return partidos

    @staticmethod
    def clean_shot_value(td: Tag) -> str:
        for span in td.find_all("span", class_="d-none"):
            span.decompose()
        return td.get_text(strip=True)

    @staticmethod
    def _to_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @staticmethod
    def _extract_onclick_player_meta(row: Tag) -> Dict[str, Optional[object]]:
        onclick = row.get("onclick") or ""
        if "EstadisticasComponente" not in onclick:
            return {}
        decoded = html.unescape(onclick)
        match = re.search(
            r"EstadisticasComponente\\((\\{.*?\\})\\s*,\\s*'(\\d+)'\\s*,\\s*'(\\d+)'",
            decoded,
            flags=re.DOTALL,
        )
        if not match:
            return {}
        raw_obj, id_club, id_equipo = match.groups()
        try:
            payload = json.loads(raw_obj)
        except json.JSONDecodeError:
            return {}
        jugador_id = payload.get("IdJugador")
        return {
            "jugador_id": GesDeportivaExtractor._to_int(jugador_id),
            "club_id": GesDeportivaExtractor._to_int(id_club),
            "equipo_id": GesDeportivaExtractor._to_int(id_equipo),
            "nombre_completo": payload.get("NombreCompleto"),
        }

    @staticmethod
    def parse_table(table: Tag) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
        jugadores: List[Dict[str, object]] = []
        tbody = table.find("tbody")
        if tbody:
            for row in tbody.find_all("tr"):
                celdas = row.find_all("td")
                if not celdas:
                    continue
                if len(celdas) <= 21:
                    raise ParseError(f"Fila incompleta en boxscore (celdas={len(celdas)})")
                jugador: Dict[str, object] = {}
                jugador.update(GesDeportivaExtractor._extract_onclick_player_meta(row))
                nro_raw = celdas[1].get_text(strip=True)
                if "*" in nro_raw:
                    jugador["nro"] = nro_raw.replace("*", "").strip()
                    jugador["inicial"] = True
                else:
                    jugador["nro"] = nro_raw.strip()
                    jugador["inicial"] = False
                jugador["nombre"] = celdas[2].get_text(strip=True)
                jugador["min"] = celdas[3].get_text(strip=True)
                jugador["pts"] = celdas[4].get_text(strip=True)
                jugadores.append(jugador)
        return jugadores, {}

    def get_boxscore(self, id_partido: str) -> Optional[Dict[str, object]]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            )
        }
        url = (
            "https://widgetscab.gesdeportiva.es/widget/partido/estadisticas/"
            f"{id_partido}==?key=9490f650-ca47-4adc-8a75-bb318dea6ecc"
        )
        resp = self._client.request("GET", url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        nombre_equipos = soup.find_all("div", class_="nombre-equipo")
        tablas = soup.find_all("table")
        if len(nombre_equipos) < 2 or len(tablas) < 2:
            raise ParseError(f"Boxscore incompleto para partido {id_partido}")
        return {
            "equipolocal": nombre_equipos[0].get_text(strip=True),
            "equipovisitante": nombre_equipos[1].get_text(strip=True),
        }


class ExtractorFactory:
    @classmethod
    def create(
        cls,
        name: str = "gesdeportiva",
        session: Optional[requests.Session] = None,
        temporada: Optional[str] = None,
    ) -> Extractor:
        if name != "gesdeportiva":
            raise ValueError(f"Extractor no soportado: {name}")
        if session is None:
            session = SessionProvider.get_session()
        client = HttpClient(session=session)
        if temporada:
            from ingest.febamba.season import ingesta_usa_portal_argentina
            from ingest.febamba.dual_source_extractor import FebambaDualSourceExtractor

            if ingesta_usa_portal_argentina(temporada):
                return FebambaDualSourceExtractor(client=client, temporada=temporada)
        return GesDeportivaExtractor(client=client)

