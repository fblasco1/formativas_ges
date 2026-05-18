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
from ingest.febamba.argentina_pipeline import collect_partidos_temporada_2026
from ingest.febamba.fixture_contexto import merge_contexto_torneo
from ingest.febamba.runtime_ctx import set_comp_cat_argentina_id
from ingest.febamba.season import ingesta_usa_portal_argentina
from ingest.ges.partido_ids import es_id_sintetico, synthetic_partido_id


def load_competencias_config(path: str = "config/competencias.json") -> dict:
    """Carga competencias, widget_key y rango de fechas desde config."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


thread_local = threading.local()
MAX_BOXWORKERS = 6
BATCH_SIZE = 50


def _configure_comp_cat_argentina(
    competencia: dict, nombre_categoria: str, id_categoria: int
) -> None:
    """``comp_cat_argentina`` o mapa ``comp_cat_por_categoria`` en config/competencias.json."""
    m = competencia.get("comp_cat_por_categoria")
    if isinstance(m, dict):
        raw = m.get(nombre_categoria)
        if raw is not None and str(raw).strip().isdigit():
            set_comp_cat_argentina_id(int(raw))
            return
    raw = competencia.get("comp_cat_argentina")
    if raw is not None and str(raw).strip().isdigit():
        set_comp_cat_argentina_id(int(raw))
        return
    set_comp_cat_argentina_id(None)


def fetch_boxscore_threadsafe(partido_id: str):
    if not hasattr(thread_local, "extractor"):
        session = requests.Session()
        tmp = getattr(thread_local, "ingesta_temporada", None)
        thread_local.extractor = ExtractorFactory.create(
            session=session, temporada=tmp
        )
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


def main(argv=None) -> None:
    """Orquestador FeBAMBA/GES. ``argv`` reservado para compatibilidad con CLI."""
    del argv
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
        thread_local.ingesta_temporada = temporada
        extractor = ExtractorFactory.create(temporada=temporada)
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
            _configure_comp_cat_argentina(competencia, nombre_categoria, id_categoria)
            try:
                fases, grupos = extractor.get_ids_fases_grupos(
                    id_competencia, id_categoria=id_categoria
                )
            except Exception as exc:
                print(
                    f"Error al obtener fases/grupos (comp={id_competencia}, cat={id_categoria}): {exc}"
                )
                fases, grupos = {}, {}

            # Si no hay combos, mantener comportamiento histórico (fase/grupo = -1).
            fases_iter = list(fases.items()) or [("TODAS", "-1")]
            grupos_iter = list(grupos.items()) or [("TODOS", "-1")]

            partidos: list[dict[str, str]] = []
            if ingesta_usa_portal_argentina(temporada):
                try:
                    partidos = collect_partidos_temporada_2026(
                        ges=extractor,
                        temporada=temporada,
                        id_categoria=id_categoria,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        widget_key=widget_key,
                        fases=fases,
                        grupos=grupos,
                        session=extractor._client._session,
                    )
                except (NetworkError, ParseError, Exception) as exc:
                    print(
                        f"Error fixture argentina (cat={id_categoria}): {exc}"
                    )
                    partidos = []
            else:
                vistos: set[str] = set()
                for nombre_fase, id_fase in fases_iter:
                    for nombre_grupo, id_grupo in grupos_iter:
                        try:
                            sub = extractor.get_info_partidos(
                                id_categoria,
                                fecha_inicio,
                                fecha_fin,
                                key=widget_key,
                                id_fase=int(id_fase)
                                if str(id_fase).lstrip("-").isdigit()
                                else -1,
                                id_grupo=int(id_grupo)
                                if str(id_grupo).lstrip("-").isdigit()
                                else -1,
                            )
                        except (NetworkError, ParseError) as exc:
                            print(
                                f"Error al obtener partidos (cat={id_categoria}, fase={id_fase}, grupo={id_grupo}): {exc}"
                            )
                            continue
                        ctx_torneo = merge_contexto_torneo(
                            temporada, nombre_fase, nombre_grupo
                        )
                        for p in sub:
                            raw_pid = (p.get("ID_PARTIDO") or "").strip()
                            fecha_p = (p.get("Fecha") or "").strip()
                            loc_p = (p.get("Local") or "").strip()
                            vis_p = (p.get("Visitante") or "").strip()
                            if raw_pid:
                                pid = raw_pid
                            else:
                                if not (fecha_p and loc_p and vis_p):
                                    continue
                                pid = synthetic_partido_id(
                                    id_competencia, id_categoria, fecha_p, loc_p, vis_p
                                )
                                p["ID_PARTIDO"] = pid
                            if pid in vistos:
                                if es_id_sintetico(pid):
                                    for existente in partidos:
                                        if existente.get("ID_PARTIDO") != pid:
                                            continue
                                        prev = existente.get("TORNEO_CTX") or {}
                                        if not (
                                            prev.get("fase_ges") or prev.get("grupo_ges")
                                        ) and (
                                            ctx_torneo.get("fase_ges")
                                            or ctx_torneo.get("grupo_ges")
                                        ):
                                            existente["TORNEO_CTX"] = ctx_torneo
                                            existente["ID_FASE"] = str(id_fase)
                                            existente["ID_GRUPO"] = str(id_grupo)
                                        break
                                continue
                            vistos.add(pid)
                            p["TORNEO_CTX"] = ctx_torneo
                            p["ID_FASE"] = str(id_fase)
                            p["ID_GRUPO"] = str(id_grupo)
                            partidos.append(p)
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
                    future_map = {}
                    for p in batch:
                        pid_b = p["ID_PARTIDO"]
                        if es_id_sintetico(pid_b):
                            boxscores[pid_b] = None
                        else:
                            future_map[
                                executor.submit(fetch_boxscore_threadsafe, pid_b)
                            ] = pid_b
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
                    ctx = partido.get("TORNEO_CTX") or {}
                    partido_json = {
                        "comp_id": id_competencia,
                        "competencia": nombre_competencia,
                        "temporada": temporada,
                        "categoria": nombre_categoria,
                        "categoria_id": id_categoria,
                        "fase": ctx.get("fase"),
                        "fase_id": partido.get("ID_FASE"),
                        "grupo": ctx.get("grupo"),
                        "grupo_id": partido.get("ID_GRUPO"),
                        "fase_ges": ctx.get("fase_ges"),
                        "grupo_ges": ctx.get("grupo_ges"),
                        "zona": ctx.get("zona"),
                        "ronda": ctx.get("ronda"),
                        "nivel": ctx.get("nivel"),
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


if __name__ == "__main__":
    main()
