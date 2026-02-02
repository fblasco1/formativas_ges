from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import json
import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
import html

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

    def get_info_partidos(
        self,
        id_categoria: int,
        fecha_inicio: str,
        fecha_fin: str,
        key: str,
    ) -> List[Dict[str, str]]:
        url_base = (
            "https://widgetscab.gesdeportiva.es/widget/informacion/partidos/"
            f"{id_categoria}/-3/7?fase=-1&grupo=-1&equipo=-1&key={key}"
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
        get_response = self._client.request(
            "GET", url_base, headers=get_headers, timeout=15
        )
        BeautifulSoup(get_response.text, "html.parser")
        data = {
            "IdCategoria": id_categoria,
            "IdFase": "-1",
            "IdGrupo": "-1",
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
        response = self._client.request(
            "POST", url_post, data=data, headers=headers, timeout=15
        )
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        partidos: List[Dict[str, str]] = []
        for link in soup.find_all("a", id=lambda x: x and "HFEstadisticas" in x):
            href = link.get("href")
            if href:
                match = re.search(r"/partido/([\w-]+)==", href)
                id_partido = match.group(1) if match else ""
                fila = link.find_parent("tr")
                fecha = local = visitante = puntos_local = puntos_visitante = ""
                if fila:
                    celdas = fila.find_all("td")
                    if len(celdas) >= 6:
                        fecha_td = celdas[0]
                        for span in fecha_td.find_all("span", class_="d-none"):
                            span.decompose()
                        fecha = fecha_td.get_text(strip=True)
                        local = celdas[1].get_text(strip=True)
                        visitante = celdas[6].get_text(strip=True)
                        puntos_local = celdas[3].get_text(strip=True)
                        puntos_visitante = celdas[4].get_text(strip=True)
                estado = "PENDIENTE"
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
                partido = {
                    "ID_PARTIDO": id_partido,
                    "Fecha": fecha,
                    "Local": local,
                    "Visitante": visitante,
                    "Estado": estado,
                    "URL": href,
                }
                partidos.append(partido)
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
            r"EstadisticasComponente\((\{.*?\})\s*,\s*'(\d+)'\s*,\s*'(\d+)'",
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
        thead = table.find("thead")
        headers: List[str] = []
        tiro_headers: List[str] = []
        if thead:
            header_rows = thead.find_all("tr")
            if len(header_rows) >= 2:
                tiro_headers = [
                    th.get_text(strip=True) for th in header_rows[0].find_all("th")
                ]
                headers = [
                    th.get_text(strip=True) for th in header_rows[1].find_all("th")
                ]
        tbody = table.find("tbody")
        if tbody:
            for row in tbody.find_all("tr"):
                celdas = row.find_all("td")
                if not celdas:
                    continue
                if len(celdas) <= 21:
                    raise ParseError(
                        f"Fila incompleta en boxscore (celdas={len(celdas)})"
                    )
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
                tiro_map = {
                    "2P": 5,
                    "3P": 7,
                    "1P": 9,
                }
                for key, idx in tiro_map.items():
                    val = GesDeportivaExtractor.clean_shot_value(celdas[idx])
                    if "/" in val:
                        anotados, intentados = val.split("/")
                        jugador[key + "A"] = int(anotados) if anotados.isdigit() else 0
                        jugador[key + "I"] = int(intentados) if intentados.isdigit() else 0
                    else:
                        jugador[key + "A"] = 0
                        jugador[key + "I"] = 0
                jugador["rebdef"] = celdas[11].get_text(strip=True)
                jugador["rebofe"] = celdas[12].get_text(strip=True)
                jugador["rebtot"] = celdas[13].get_text(strip=True)
                jugador["ast"] = celdas[14].get_text(strip=True)
                jugador["rec"] = celdas[15].get_text(strip=True)
                jugador["per"] = celdas[16].get_text(strip=True)
                jugador["tap"] = celdas[17].get_text(strip=True)
                jugador["fal"] = celdas[19].get_text(strip=True)
                jugador["val"] = celdas[21].get_text(strip=True)
                jugadores.append(jugador)
                print(jugador)
        total: Dict[str, object] = {}
        tfoot = table.find("tfoot")
        if tfoot:
            total_row = tfoot.find("tr")
            if total_row:
                total_celdas = total_row.find_all("th")
                total = {
                    "pts": total_celdas[2].get_text(strip=True),
                    "rebdef": total_celdas[9].get_text(strip=True),
                    "rebofe": total_celdas[10].get_text(strip=True),
                    "rebtot": total_celdas[11].get_text(strip=True),
                    "ast": total_celdas[12].get_text(strip=True),
                    "rec": total_celdas[13].get_text(strip=True),
                    "per": total_celdas[14].get_text(strip=True),
                    "tap": total_celdas[15].get_text(strip=True),
                    "fal": total_celdas[17].get_text(strip=True),
                }
                tiro_map = {
                    "2P": 3,
                    "3P": 5,
                    "1P": 7,
                }
                for key, idx in tiro_map.items():
                    val = GesDeportivaExtractor.clean_shot_value(total_celdas[idx])
                    if "/" in val:
                        anotados, intentados = val.split("/")
                        total[key + "A"] = int(anotados) if anotados.isdigit() else 0
                        total[key + "I"] = int(intentados) if intentados.isdigit() else 0
                    else:
                        total[key + "A"] = 0
                        total[key + "I"] = 0

        return jugadores, total

    def get_boxscore(self, id_partido: str) -> Optional[Dict[str, object]]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Referer": (
                "https://widgetscab.gesdeportiva.es/widget/partido/partido/"
                f"{id_partido}==?key=9490f650-ca47-4adc-8a75-bb318dea6ecc"
            ),
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
        estadisticas = {
            "equipolocal": None,
            "entrenadorlocal": "",
            "estadisticasequipolocal": [],
            "totaleslocal": {},
            "equipovisitante": None,
            "entrenadorvisitante": "",
            "estadisticasequipovisitante": [],
            "totalesvisitante": {},
        }
        estadisticas["equipolocal"] = nombre_equipos[0].get_text(strip=True)
        entrenador_div_local = nombre_equipos[0].find_next_sibling(
            "div", class_="entrenador"
        )
        if entrenador_div_local and entrenador_div_local.find("span"):
            estadisticas["entrenadorlocal"] = entrenador_div_local.find(
                "span"
            ).get_text(strip=True)
        try:
            jugadores_local, totales_local = self.parse_table(tablas[0])
        except Exception as exc:
            raise ParseError(
                f"Error parseando boxscore local del partido {id_partido}: {exc}"
            ) from exc
        estadisticas["estadisticasequipolocal"] = jugadores_local
        estadisticas["totaleslocal"] = totales_local
        estadisticas["equipovisitante"] = nombre_equipos[1].get_text(strip=True)
        entrenador_div_visitante = nombre_equipos[1].find_next_sibling(
            "div", class_="entrenador"
        )
        if entrenador_div_visitante and entrenador_div_visitante.find("span"):
            estadisticas["entrenadorvisitante"] = entrenador_div_visitante.find(
                "span"
            ).get_text(strip=True)
        try:
            jugadores_visitante, totales_visitante = self.parse_table(tablas[1])
        except Exception as exc:
            raise ParseError(
                f"Error parseando boxscore visitante del partido {id_partido}: {exc}"
            ) from exc
        estadisticas["estadisticasequipovisitante"] = jugadores_visitante
        estadisticas["totalesvisitante"] = totales_visitante
        return estadisticas


class ExtractorFactory:
    @classmethod
    def create(
        cls,
        name: str = "gesdeportiva",
        session: Optional[requests.Session] = None,
    ) -> Extractor:
        if name != "gesdeportiva":
            raise ValueError(f"Extractor no soportado: {name}")
        if session is None:
            session = SessionProvider.get_session()
        client = HttpClient(session=session)
        return GesDeportivaExtractor(client=client)
