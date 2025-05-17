import json
import os
from typing import Dict

BASE_DIR = os.path.dirname(__file__)


def cargar_mapeo_categorias() -> Dict[str, str]:
    path = os.path.join(BASE_DIR, "categorias.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cargar_mapeo_equipos() -> Dict[str, str]:
    path = os.path.join(BASE_DIR, "equipos.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalizar_equipo(nombre: str, mapeo_equipos: Dict[str, str]) -> str:
    if not isinstance(nombre, str):
        return nombre
    nombre_upper = nombre.upper().strip()
    return mapeo_equipos.get(nombre_upper, nombre.strip())
