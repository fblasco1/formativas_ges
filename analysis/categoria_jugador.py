"""
Asignación de la categoría más joven por jugador y temporada (FeBAMBA).

Ignora categoria_id del GES (cambia cada temporada). Usa solo el texto
de public.partidos.categoria con un orden hardcodeado de menor a mayor edad.

Uso en FastAPI (inyección de engine):

    from sqlalchemy.engine import Engine
    from analysis.db import get_engine
    from analysis.categoria_jugador import run_pipeline

    @app.get("/jugadores/categoria-mas-joven")
    def get_categoria_mas_joven(engine: Engine = Depends(get_engine_dep)):
        df = run_pipeline(engine=engine)
        return df.to_dict(orient="records")

    # Dependency: def get_engine_dep(): return get_engine()
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from analysis.db import get_engine

# Orden de menor a mayor (1 = más joven). Cualquier otra categoría recibe rango alto.
CATEGORIA_RANKS: Dict[str, int] = {
    "INFANTILES MASCULINO": 1,
    "CADETES MASCULINO": 2,
    "JUVENILES MASCULINO": 3,
    "LIGA PROXIMO MASCULINO": 4,
}
RANGO_DESCONOCIDO = 999


def normalizar_categoria(categoria: Optional[str]) -> str:
    """
    Limpia el string de categoría para comparación: strip y upper.
    Valores nulos o vacíos se devuelven como string vacío.
    """
    if categoria is None or not isinstance(categoria, str):
        return ""
    return categoria.strip().upper()


def rank_categoria(categoria_normalizada: str) -> int:
    """Devuelve el rango de la categoría (menor = más joven)."""
    if not categoria_normalizada:
        return RANGO_DESCONOCIDO
    return CATEGORIA_RANKS.get(categoria_normalizada, RANGO_DESCONOCIDO)


# Query: jugador_id, temporada_id, categoria por participación en partidos.
QUERY_JUGADOR_CATEGORIAS = text("""
SELECT DISTINCT
    jct.jugador_id,
    jct.temporada_id,
    p.categoria
FROM public.estadisticas_jugador e
JOIN public.partidos p ON e.partido_id = p.partido_id
JOIN public.jugador_club_temporada jct ON e.jct_id = jct.jct_id
WHERE p.categoria IS NOT NULL
  AND TRIM(p.categoria) != ''
""")


def extract_jugador_categorias(engine: Optional[Engine] = None) -> pd.DataFrame:
    """
    Extrae (jugador_id, temporada_id, categoria) desde PostgreSQL.

    JOIN: estadisticas_jugador -> partidos (partido_id), estadisticas_jugador -> jugador_club_temporada (jct_id).
    Si engine es None, se crea uno con get_engine().
    """
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(QUERY_JUGADOR_CATEGORIAS, conn)
    if df.empty:
        return df
    # Validación: normalizar categoría antes de clasificar
    df["categoria_norm"] = df["categoria"].map(normalizar_categoria)
    df = df[df["categoria_norm"] != ""].copy()
    return df


def clasificar_categoria_mas_joven(df: pd.DataFrame) -> pd.DataFrame:
    """
    Por (jugador_id, temporada_id) elige la categoría con rango más bajo (más joven).

    Espera columnas: jugador_id, temporada_id, categoria_norm (o categoria, que se normaliza).
    Devuelve DataFrame con columnas: jugador_id, temporada_id, categoria_asignada, rango.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["jugador_id", "temporada_id", "categoria_asignada", "rango"]
        )
    if "categoria_norm" not in df.columns:
        df = df.copy()
        df["categoria_norm"] = df["categoria"].map(normalizar_categoria)
    df["rango"] = df["categoria_norm"].map(rank_categoria)
    # Por jugador y temporada, quedarse con la fila de menor rango
    idx_min = df.groupby(["jugador_id", "temporada_id"], dropna=False)["rango"].idxmin()
    result = df.loc[idx_min, ["jugador_id", "temporada_id", "categoria_norm", "rango"]].copy()
    result = result.rename(columns={"categoria_norm": "categoria_asignada"})
    return result.reset_index(drop=True)


def run_pipeline(engine: Optional[Engine] = None) -> pd.DataFrame:
    """
    Pipeline completo: extracción + clasificación.

    Retorna DataFrame con jugador_id, temporada_id, categoria_asignada, rango.
    Pensado para uso en script o en API FastAPI (inyectando engine).
    """
    df_raw = extract_jugador_categorias(engine=engine)
    return clasificar_categoria_mas_joven(df_raw)


def main() -> pd.DataFrame:
    """Punto de entrada para uso como script o desde FastAPI."""
    return run_pipeline()


if __name__ == "__main__":
    result = main()
    print(result.head(20))
    print(f"\nTotal filas: {len(result)}")
