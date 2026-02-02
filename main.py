"""
Orquestador de ingesta: extrae partidos y boxscores de competencias formativas
según config/config/competencias.json.
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ingest import ExtractorFactory, NetworkError, ParseError


def load_competencias_config(path: str = "config/competencias.json") -> dict:
    """Carga competencias, widget_key y rango de fechas desde config."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


extractor = ExtractorFactory.create()
thread_local = threading.local()
MAX_BOXWORKERS = 6
BATCH_SIZE = 50


def fetch_boxscore_threadsafe(partido_id: str):
    if not hasattr(thread_local, "extractor"):
        session = requests.Session()
        thread_local.extractor = ExtractorFactory.create(session=session)
    return thread_local.extractor.get_boxscore(partido_id)


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size], (i // size) + 1


def load_categoria_progress(progress_path):
    if not os.path.exists(progress_path):
        return 0
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("ultimo_lote", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def save_categoria_progress(progress_path, lote_idx):
    data = {"ultimo_lote": lote_idx}
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    cfg = load_competencias_config()
    competencias = cfg.get("competencias", [])
    fecha_inicio = cfg.get("fecha_inicio", "2022-1-1")
    fecha_fin = cfg.get("fecha_fin", "2026-12-30")
    widget_key = cfg.get("widget_key", "c93924c3-1e13-4bf5-8f86-6386aeebba20")

    for competencia in competencias:
        print(f"Procesando competencia: {competencia['nombre']} ({competencia['temporada']})")
        id_competencia = competencia["id_competencia"]
        nombre_competencia = competencia["nombre"]
        temporada = competencia["temporada"]
        try:
            categorias = extractor.get_ids_categorias(id_competencia)
        except (NetworkError, ParseError) as exc:
            print(f"Error al obtener categorías: {exc}")
            continue
        if not categorias:
            print(f"Sin categorías para la competencia {id_competencia}")
            continue

        for nombre_categoria, id_categoria in categorias.items():
            print(f"  Categoria: {nombre_categoria} ({id_categoria})")
            if isinstance(id_categoria, str) and id_categoria.isdigit():
                id_categoria = int(id_categoria)
            try:
                partidos = extractor.get_info_partidos(
                    id_categoria,
                    fecha_inicio,
                    fecha_fin,
                    key=widget_key,
                )
            except (NetworkError, ParseError) as exc:
                print(f"Error al obtener partidos de {id_categoria}: {exc}")
                continue
            safe_nombre = nombre_competencia.replace("/", "_").replace(" ", "_")
            safe_temporada = temporada.replace("/", "_").replace(" ", "_")
            safe_categoria = nombre_categoria.replace("/", "_").replace(" ", "_")
            progress_path = (
                f"progress_{safe_nombre}_{safe_temporada}_{safe_categoria}.json"
            )
            last_lote = load_categoria_progress(progress_path)
            for batch, lote_idx in chunked(partidos, BATCH_SIZE):
                if lote_idx <= last_lote:
                    continue
                boxscores: dict[str, object] = {}
                with ThreadPoolExecutor(max_workers=MAX_BOXWORKERS) as executor:
                    future_map = {
                        executor.submit(fetch_boxscore_threadsafe, p["ID_PARTIDO"]): p["ID_PARTIDO"]
                        for p in batch
                    }
                    for future in as_completed(future_map):
                        id_partido = future_map[future]
                        try:
                            boxscores[id_partido] = future.result()
                        except (NetworkError, ParseError) as exc:
                            print(f"Error al obtener boxscore {id_partido}: {exc}")
                            boxscores[id_partido] = None
                        except Exception as exc:
                            print(f"Error inesperado en boxscore {id_partido}: {exc}")
                            boxscores[id_partido] = None

                output = {}
                for partido in batch:
                    id_partido = partido["ID_PARTIDO"]
                    partido_json = {
                        "comp_id": id_competencia,
                        "competencia": nombre_competencia,
                        "temporada": temporada,
                        "categoria": nombre_categoria,
                        "categoria_id": id_categoria,
                        "partido_id": id_partido,
                        "fecha": partido["Fecha"],
                        "local": partido["Local"],
                        "visitante": partido["Visitante"],
                        "estado": partido["Estado"],
                        "estadisticas": boxscores.get(id_partido),
                    }
                    output[id_partido] = partido_json

                filename = (
                    f"partidos_{safe_nombre}_{safe_temporada}_{safe_categoria}_lote_{lote_idx}.json"
                )
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)
                save_categoria_progress(progress_path, lote_idx)
