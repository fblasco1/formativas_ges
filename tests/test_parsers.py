import csv
import logging
import sys
from pathlib import Path

# Add the parent directory to sys.path to resolve the ModuleNotFoundError
sys.path.append(str(Path(__file__).resolve().parent.parent))

from parsers.fases import parsear_fase
from parsers.grupos import parsear_grupo

# LOG SETUP
log_path = Path("debug_fase_grupo_v5.log")
csv_output_path = Path("errores_fase_grupo_v5.csv")

logging.basicConfig(
    filename=log_path,
    level=logging.DEBUG,
    filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ERRORES RECOLECTADOS
errores = []


def procesar_fila(anio, fase_text, grupo_text, categorias_raw):
    categorias = [c.strip() for c in categorias_raw.split(",")]

    logging.debug(
        f"INPUT | ANIO: {anio} | FASE: {fase_text} | GRUPO: {grupo_text} | CATEGORIAS: {categorias}"
    )

    try:
        fase_res = parsear_fase(int(anio), fase_text)
        grupo_res = parsear_grupo(int(anio), fase_text, grupo_text)
    except Exception as e:
        error = f"Error ejecutando los parsers: {str(e)}"
        errores.append([anio, fase_text, grupo_text, categorias_raw, error])
        logging.error(error)
        return None

    # Combinamos resultados
    resultado = {
        "anio": anio,
        "fase": fase_res["fase"],
        "ronda": fase_res["ronda"],
        "nivel": (
            fase_res["nivel"]
            if fase_res["nivel"] != "Desconocido"
            else grupo_res.get("nivel", "Desconocido")
        ),
        "zona": (
            fase_res["zona"]
            if fase_res["zona"] != "Desconocida"
            else grupo_res.get("zona", "Desconocida")
        ),
        "grupo": grupo_res.get("grupo", "Desconocido"),
        "categorias": categorias,
    }

    logging.debug(f"OUTPUT | {resultado}")

    # Validación final
    faltantes = [
        k
        for k in ["fase", "ronda", "nivel", "zona"]
        if resultado.get(k) == "Desconocido" or resultado.get(k) == "Desconocida"
    ]
    if faltantes:
        msg = f"Faltan: {', '.join(faltantes)}"
        errores.append([anio, fase_text, grupo_text, categorias_raw, msg])
        logging.warning(f"{msg} | Resultado: {resultado}")

    return resultado


def procesar_csv(archivo_entrada):
    with open(archivo_entrada, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            procesar_fila(
                anio=row["Anio"],
                fase_text=row["Fase"],
                grupo_text=row["Grupo"],
                categorias_raw=row["Categorias"],
            )

    exportar_errores()


def exportar_errores():
    if errores:
        with open(csv_output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["ANIO", "FASE_REC", "GRUPO_REC", "CATEGORIAS", "RESULTADO"]
            )
            writer.writerows(errores)
        logging.info(f"Archivo CSV de errores exportado: {csv_output_path}")
    else:
        logging.info("No hubo errores para exportar.")


procesar_csv("estructura_por_fase_y_grupo_sin_mosquitos.csv")
