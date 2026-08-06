import json
import os
from pathlib import Path
from typing import Dict, Iterable, Mapping

BASE_DIR = Path(__file__).resolve().parent
EQUIPOS_MAP_PATH = BASE_DIR / "equipos_map.json"
CATEGORIAS_MAP_PATH = BASE_DIR / "categorias_map.json"


def clave_mapeo(nombre: str) -> str:
    """Clave estándar para entradas de equipos_map.json."""
    if not isinstance(nombre, str):
        return ""
    return nombre.upper().strip()


def cargar_mapeo_categorias() -> Dict[str, str]:
    with open(CATEGORIAS_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def cargar_mapeo_equipos() -> Dict[str, str]:
    with open(EQUIPOS_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_mapeo_equipos(mapeo: Mapping[str, str]) -> None:
    """Persiste equipos_map.json (claves en mayúsculas)."""
    limpio = {clave_mapeo(k): str(v).strip() for k, v in mapeo.items() if clave_mapeo(k)}
    with open(EQUIPOS_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(limpio, f, ensure_ascii=False, indent=2)
        f.write("\n")


def agregar_entradas_mapeo(entradas: Mapping[str, str]) -> Dict[str, str]:
    """Fusiona entradas origen→destino y guarda el JSON."""
    mapeo = cargar_mapeo_equipos()
    for origen, destino in entradas.items():
        key = clave_mapeo(origen)
        if not key or not isinstance(destino, str) or not destino.strip():
            continue
        mapeo[key] = destino.strip()
    guardar_mapeo_equipos(mapeo)
    return mapeo


def normalizar_equipo(nombre: str, mapeo_equipos: Dict[str, str]) -> str:
    if not isinstance(nombre, str):
        return nombre
    key = clave_mapeo(nombre)
    return mapeo_equipos.get(key, nombre.strip())


def normalizar_columna_equipos(series, mapeo_equipos: Dict[str, str], *, upper: bool = False):
    out = series.apply(lambda x: normalizar_equipo(x, mapeo_equipos))
    if upper:
        out = out.apply(lambda x: x.upper() if isinstance(x, str) else x)
    return out
