from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import psycopg
import streamlit as st


def load_config(path: str = "config.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dsn(cfg: Dict[str, Any]) -> str:
    db = cfg.get("db", {})
    host = db.get("host", "localhost")
    port = db.get("port", 5432)
    user = db.get("user")
    password = db.get("password")
    name = db.get("name")
    if not user or not password or not name:
        raise RuntimeError("Config incompleta en config.json (db.user/db.password/db.name)")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def get_conn() -> psycopg.Connection:
    config_path = os.environ.get("CONFIG_PATH", "config.json")
    cfg = load_config(config_path)
    dsn = build_dsn(cfg)
    return psycopg.connect(dsn)


def fetch_all(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def load_players_summary(
    search: str = "",
    min_partidos: int = 1,
    exact_fullname: bool = False,
    duplicates_only: bool = False,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    conditions = []
    if search:
        if exact_fullname:
            conditions.append("(j.nombre_completo = %(q)s)")
            params["q"] = search
        else:
            conditions.append("(j.nombre ILIKE %(q)s OR j.nombre_completo ILIKE %(q)s)")
            params["q"] = f"%{search}%"
    if duplicates_only:
        conditions.append(
            "j.nombre_completo IN ("
            "SELECT nombre_completo FROM jugadores "
            "WHERE nombre_completo IS NOT NULL "
            "GROUP BY nombre_completo HAVING COUNT(*) > 1)"
        )
    params["min_partidos"] = max(1, min_partidos)
    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"""
    SELECT
        j.jugador_id,
        COALESCE(j.nombre_completo, j.nombre) AS jugador,
        COUNT(*) AS partidos,
        AVG(e.pts)::numeric(10,2) AS pts_avg,
        CASE
            WHEN SUM(e.dos_i) > 0
            THEN ROUND(100.0 * SUM(e.dos_a) / SUM(e.dos_i), 2)
            ELSE NULL
        END AS pct_2p,
        CASE
            WHEN SUM(e.tres_i) > 0
            THEN ROUND(100.0 * SUM(e.tres_a) / SUM(e.tres_i), 2)
            ELSE NULL
        END AS pct_3p,
        CASE
            WHEN SUM(e.uno_i) > 0
            THEN ROUND(100.0 * SUM(e.uno_a) / SUM(e.uno_i), 2)
            ELSE NULL
        END AS pct_tl,
        AVG(e.rebofe)::numeric(10,2) AS ro_avg,
        AVG(e.rebdef)::numeric(10,2) AS rd_avg,
        AVG(e.val)::numeric(10,2) AS val_avg
    FROM estadisticas_jugador e
    JOIN jugador_club_temporada jct ON jct.jct_id = e.jct_id
    JOIN jugadores j ON j.jugador_id = jct.jugador_id
    {where}
    GROUP BY j.jugador_id, j.nombre, j.nombre_completo
    HAVING COUNT(*) >= %(min_partidos)s
    ORDER BY val_avg DESC NULLS LAST, pts_avg DESC NULLS LAST
    """
    return fetch_all(sql, params)


def load_player_detail(player_id: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT
        p.temporada,
        p.categoria,
        COALESCE(c.nombre, 'SIN CLUB') AS club,
        COUNT(*) AS partidos,
        AVG(e.pts)::numeric(10,2) AS pts_avg,
        CASE
            WHEN SUM(e.dos_i) > 0
            THEN ROUND(100.0 * SUM(e.dos_a) / SUM(e.dos_i), 2)
            ELSE NULL
        END AS pct_2p,
        CASE
            WHEN SUM(e.tres_i) > 0
            THEN ROUND(100.0 * SUM(e.tres_a) / SUM(e.tres_i), 2)
            ELSE NULL
        END AS pct_3p,
        CASE
            WHEN SUM(e.uno_i) > 0
            THEN ROUND(100.0 * SUM(e.uno_a) / SUM(e.uno_i), 2)
            ELSE NULL
        END AS pct_tl,
        AVG(e.rebofe)::numeric(10,2) AS ro_avg,
        AVG(e.rebdef)::numeric(10,2) AS rd_avg,
        AVG(e.val)::numeric(10,2) AS val_avg
    FROM estadisticas_jugador e
    JOIN partidos p ON p.partido_id = e.partido_id
    JOIN jugador_club_temporada jct ON jct.jct_id = e.jct_id
    LEFT JOIN clubes c ON c.club_id = jct.club_id
    WHERE jct.jugador_id = %(player_id)s
    GROUP BY p.temporada, p.categoria, c.nombre
    ORDER BY p.temporada DESC, p.categoria, club
    """
    return fetch_all(sql, {"player_id": player_id})


def main() -> None:
    st.set_page_config(page_title="Dashboard Jugadores", layout="wide")
    st.title("Dashboard de jugadores")

    with st.sidebar:
        st.subheader("Filtros")
        search = st.text_input("Buscar jugador", placeholder="Apellido o nombre")
        exact_fullname = st.checkbox("Coincidir nombre completo exacto", value=False)
        duplicates_only = st.checkbox("Solo nombres duplicados", value=False)
        min_partidos = st.number_input(
            "Mínimo partidos jugados",
            min_value=1,
            value=1,
            step=1,
        )

    try:
        players = load_players_summary(
            search=search,
            min_partidos=min_partidos,
            exact_fullname=exact_fullname,
            duplicates_only=duplicates_only,
        )
    except Exception as exc:
        st.error(f"Error consultando la base: {exc}")
        return

    if not players:
        st.info("No se encontraron jugadores con esos filtros.")
        return

    player_options = {
        f"{p['jugador']} (ID {p['jugador_id']})": p["jugador_id"] for p in players
    }
    selected_label = st.selectbox("Jugador", list(player_options.keys()))
    selected_id = player_options[selected_label]

    st.subheader("Resumen general")
    players_view = [
        {
            "ID Jugador": p["jugador_id"],
            "Jugador": p["jugador"],
            "Partidos": p["partidos"],
            "PTS": p["pts_avg"],
            "%2P": p["pct_2p"],
            "%3P": p["pct_3p"],
            "%TL": p["pct_tl"],
            "RO": p["ro_avg"],
            "RD": p["rd_avg"],
            "VAL": p["val_avg"],
        }
        for p in players
    ]
    st.dataframe(players_view, width="stretch")

    st.subheader("Desglose por temporada / categoría / club")
    try:
        detail_rows = load_player_detail(selected_id)
        detail_view = [
            {
                "Temporada": d["temporada"],
                "Categoria": d["categoria"],
                "Club": d["club"],
                "Partidos": d["partidos"],
                "PTS": d["pts_avg"],
                "%2P": d["pct_2p"],
                "%3P": d["pct_3p"],
                "%TL": d["pct_tl"],
                "RO": d["ro_avg"],
                "RD": d["rd_avg"],
                "VAL": d["val_avg"],
            }
            for d in detail_rows
        ]
        st.dataframe(detail_view, width="stretch")
    except Exception as exc:
        st.error(f"Error cargando detalle: {exc}")


if __name__ == "__main__":
    main()
