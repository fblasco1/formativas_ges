# -*- coding: utf-8 -*-
"""
Mapeo de equipos: iterar casos, revisar mapa y equipos por región.

  streamlit run visualizaciones/mapeo_equipos_streamlit.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, resolve_partidos_consolidado  # noqa: E402
from mapeos.equipos_casos import (  # noqa: E402
    cargar_partidos_consolidado,
    casos_a_dataframe,
    detectar_casos,
    exportar_casos_csv,
)
from mapeos.equipos_region import (  # noqa: E402
    cargar_partidos_normalizados,
    equipos_detalle_region,
    resumen_mapeo,
    totales_por_region,
)
from mapeos.equipos_listado import filtrar_listado, listado_por_temporada  # noqa: E402
from mapeos.equipos_temporadas import (  # noqa: E402
    cruce_a_dataframe,
    detectar_cruce_temporadas,
    exportar_cruce_csv,
    filtrar_cruce,
)
from mapeos.loader import (  # noqa: E402
    agregar_entradas_mapeo,
    cargar_mapeo_equipos,
    clave_mapeo,
    guardar_mapeo_equipos,
)

OUTPUT_CASOS = ROOT / "outputs" / "mapeo_equipos_casos.csv"
OUTPUT_CRUCE = ROOT / "outputs" / "mapeo_cruce_temporadas.csv"
OUTPUT_LISTADO = ROOT / "outputs" / "mapeo_listado_temporadas.csv"

FILTROS_LISTADO = {
    "Todos": "todos",
    "Mismo nombre exacto (2+ temporadas)": "mismo_nombre_csv",
    "Mismo nombre normalizado (2+ temporadas)": "mismo_nombre_norm",
    "Club: cambia nombre entre temporadas": "club_nombre_distinto_por_temporada",
    "Mismo club, varios textos CSV": "mismo_club_varios_nombres",
    "Solo en una temporada (ese texto)": "solo_una_temporada",
    "Sin mapear": "sin_mapear",
}
TIPOS_FILTRO = {
    "Todos": None,
    "club_varios_nombres": "club_varios_nombres",
    "alias_sin_mapear": "alias_sin_mapear",
    "una_temporada": "una_temporada",
}


@st.cache_data(ttl=30)
def _cargar_casos(path_str: str, partidos_mtime: float, map_mtime: float) -> tuple[pd.DataFrame, list]:
    _ = partidos_mtime, map_mtime
    df = cargar_partidos_consolidado(Path(path_str))
    casos = detectar_casos(df)
    return casos_a_dataframe(casos), casos


@st.cache_data(ttl=30)
def _cargar_partidos_region(path_str: str, partidos_mtime: float, map_mtime: float) -> pd.DataFrame:
    _ = partidos_mtime, map_mtime
    return cargar_partidos_normalizados(Path(path_str))


@st.cache_data(ttl=30)
def _cargar_cruce(path_str: str, partidos_mtime: float, map_mtime: float) -> tuple[pd.DataFrame, list]:
    _ = partidos_mtime, map_mtime
    df = cargar_partidos_consolidado(Path(path_str))
    casos = detectar_cruce_temporadas(df)
    return cruce_a_dataframe(casos), casos


@st.cache_data(ttl=30)
def _cargar_listado(path_str: str, partidos_mtime: float, map_mtime: float) -> pd.DataFrame:
    _ = partidos_mtime, map_mtime
    df = cargar_partidos_consolidado(Path(path_str))
    return listado_por_temporada(df)


def _limpiar_cache() -> None:
    _cargar_casos.clear()
    _cargar_partidos_region.clear()
    _cargar_cruce.clear()
    _cargar_listado.clear()


def _filtrar_casos(casos: list, tipo: str | None, buscar: str) -> list:
    out = casos
    if tipo:
        out = [c for c in out if c.tipo == tipo]
    if buscar.strip():
        q = buscar.strip().upper()
        out = [
            c
            for c in out
            if q in c.club_base.upper()
            or any(q in v.nombre_raw.upper() for v in c.variantes)
        ]
    return out


def _ejecutar_normalizador(consolidar: bool, ranking: bool) -> tuple[bool, str]:
    cmd = [sys.executable, str(ROOT / "pipelines" / "normalizar_equipos.py")]
    if consolidar:
        cmd.append("--consolidar")
    if ranking:
        cmd.append("--ranking")
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    log = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, log


def _tab_iterar_casos(
    consolidado: Path,
    map_path: Path,
    tabla_casos: pd.DataFrame,
    casos_lista: list,
) -> None:
    tipo_label = st.selectbox("Tipo de caso", list(TIPOS_FILTRO.keys()), key="filtro_tipo")
    buscar = st.text_input("Buscar club o nombre", key="filtro_buscar")
    tipo_filtro = TIPOS_FILTRO[tipo_label]
    casos_filtrados = _filtrar_casos(casos_lista, tipo_filtro, buscar)
    n = len(casos_filtrados)

    st.caption(
        f"**{n}** casos a revisar (de {len(casos_lista)} totales)"
    )

    if st.button("Exportar CSV de casos", key="export_casos"):
        exportar_casos_csv(casos_filtrados or casos_lista, OUTPUT_CASOS)
        st.success(f"Guardado: {OUTPUT_CASOS}")

    if n == 0:
        st.info("No hay casos con ese filtro.")
        st.dataframe(tabla_casos, use_container_width=True, height=400)
        return

    if "indice_caso" not in st.session_state:
        st.session_state.indice_caso = 0

    col_prev, col_idx, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("← Anterior", use_container_width=True):
            st.session_state.indice_caso = (st.session_state.indice_caso - 1) % n
            st.rerun()
    with col_next:
        if st.button("Siguiente →", use_container_width=True):
            st.session_state.indice_caso = (st.session_state.indice_caso + 1) % n
            st.rerun()
    with col_idx:
        idx = st.number_input(
            "Caso",
            min_value=1,
            max_value=n,
            value=min(st.session_state.indice_caso + 1, n),
            step=1,
        )
        st.session_state.indice_caso = int(idx) - 1

    caso = casos_filtrados[st.session_state.indice_caso]
    st.subheader(f"{caso.id} · {caso.tipo}")
    st.markdown(f"**Club base:** `{caso.club_base}`")
    st.info(caso.nota)

    filas = [
        {
            "Nombre en CSV": v.nombre_raw,
            "Tras mapeo": v.nombre_norm,
            "En mapa": "Sí" if v.en_mapeo else "No",
            "Destino actual": v.destino_mapeo or "—",
            "Partidos": v.partidos,
            "Temporadas": ", ".join(str(t) for t in v.temporadas),
        }
        for v in caso.variantes
    ]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    canonicos = sorted({str(v).strip() for v in cargar_mapeo_equipos().values()})
    sugerencia = caso.sugerencia or (caso.variantes[0].nombre_norm if caso.variantes else "")
    opciones_dest = sorted(set(canonicos + [sugerencia]))
    destino = st.selectbox(
        "Nombre canónico (destino)",
        options=opciones_dest,
        index=opciones_dest.index(sugerencia) if sugerencia in opciones_dest else 0,
    )
    destino_custom = st.text_input("O escribir otro destino", value="", key="dest_custom")
    if destino_custom.strip():
        destino = destino_custom.strip()

    variantes_a_mapear = st.multiselect(
        "Variantes a mapear",
        options=[v.nombre_raw for v in caso.variantes],
        default=[v.nombre_raw for v in caso.variantes if not v.en_mapeo]
        or [v.nombre_raw for v in caso.variantes],
    )

    c1, c2 = st.columns(2)
    with c1:
        guardar = st.button("Guardar en equipos_map.json", type="primary", use_container_width=True)
    with c2:
        guardar_siguiente = st.button("Guardar y siguiente", use_container_width=True)

    if guardar or guardar_siguiente:
        if not variantes_a_mapear:
            st.warning("Elegí al menos una variante.")
        else:
            agregar_entradas_mapeo({orig: destino for orig in variantes_a_mapear})
            _limpiar_cache()
            st.success("Mapeo guardado.")
            if guardar_siguiente:
                st.session_state.indice_caso = (st.session_state.indice_caso + 1) % n
            st.rerun()


def _tab_equipos_region(df: pd.DataFrame) -> None:
    años = sorted(df["anio"].unique().tolist())
    cats = sorted(df["categoria"].dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    with c1:
        anio = st.selectbox("Temporada", años, index=len(años) - 1 if años else 0)
    with c2:
        cat = st.selectbox("Categoría", ["_TODAS_"] + cats)
    with c3:
        region_sel = st.selectbox(
            "Región",
            ["Todas"] + sorted(df[df["anio"] == anio]["zona"].dropna().unique().tolist()),
        )

    detalle = equipos_detalle_region(
        df, anio=int(anio), categoria=cat if cat != "_TODAS_" else None
    )
    if region_sel != "Todas":
        detalle = detalle[detalle["zona"] == region_sel.upper()]

    totales = totales_por_region(detalle)

    st.subheader("Cantidades por región")
    if totales.empty:
        st.warning("Sin equipos para estos filtros.")
        return

    cols = st.columns(min(len(totales), 6))
    for i, row in totales.iterrows():
        with cols[i % len(cols)]:
            st.metric(str(row["zona"]), int(row["equipos_distintos"]))

    st.dataframe(
        totales.rename(columns={"zona": "Región", "equipos_distintos": "Equipos"}),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Listado por región (orden alfabético)")
    for zona in totales["zona"].tolist():
        sub = detalle[detalle["zona"] == zona][["equipo", "partidos"]].copy()
        sub = sub.rename(columns={"equipo": "Equipo", "partidos": "Partidos"})
        with st.expander(f"{zona} — {len(sub)} equipos", expanded=(region_sel == "Todas" and zona == totales.iloc[0]["zona"])):
            st.dataframe(sub, use_container_width=True, hide_index=True)

    buscar_eq = st.text_input("Buscar equipo en el listado", key="buscar_region")
    if buscar_eq.strip():
        q = buscar_eq.strip().upper()
        hit = detalle[detalle["equipo"].str.upper().str.contains(q, na=False)]
        st.dataframe(
            hit.rename(columns={"zona": "Región", "equipo": "Equipo", "partidos": "Partidos"}),
            use_container_width=True,
            hide_index=True,
        )


def _tab_cruce_temporadas(tabla_cruce: pd.DataFrame, casos_cruce: list) -> None:
    st.markdown(
        "Compará **cómo figura el mismo club en cada temporada** (texto en CSV → nombre tras el mapa). "
        "Así detectás si el mapeo unifica bien de año en año."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        solo_inc = st.checkbox("Solo inconsistentes", value=True, key="cruce_inc")
    with c2:
        min_anios = st.selectbox("Mín. temporadas con datos", [2, 3, 4], index=0, key="cruce_min")
    with c3:
        buscar = st.text_input("Buscar club", key="cruce_buscar")

    filtrados = filtrar_cruce(
        casos_cruce,
        solo_inconsistentes=solo_inc,
        min_anios=min_anios,
        buscar=buscar,
    )
    n = len(filtrados)

    st.caption(f"**{n}** clubes a revisar (de {len(casos_cruce)} agrupados por club base)")

    if st.button("Exportar cruce temporadas CSV", key="export_cruce"):
        exportar_cruce_csv(filtrados or casos_cruce, OUTPUT_CRUCE)
        st.success(f"Guardado: {OUTPUT_CRUCE}")

    with st.expander("Matriz completa (todas las filas)", expanded=False):
        view = tabla_cruce
        if solo_inc and "inconsistente" in view.columns:
            view = view[view["inconsistente"]]
        if buscar.strip():
            q = buscar.strip().upper()
            mask = (
                view["club_base"].str.upper().str.contains(q, na=False)
                | view.astype(str).apply(lambda col: col.str.upper().str.contains(q, na=False)).any(axis=1)
            )
            view = view[mask]
        st.dataframe(view, use_container_width=True, height=360)

    if n == 0:
        st.success("No hay cruces con ese filtro.")
        return

    if "indice_cruce" not in st.session_state:
        st.session_state.indice_cruce = 0

    p1, p2, p3 = st.columns([1, 3, 1])
    with p1:
        if st.button("← Ant.", key="cruce_prev"):
            st.session_state.indice_cruce = (st.session_state.indice_cruce - 1) % n
            st.rerun()
    with p3:
        if st.button("Sig. →", key="cruce_next"):
            st.session_state.indice_cruce = (st.session_state.indice_cruce + 1) % n
            st.rerun()
    with p2:
        ix = st.number_input(
            "Cruce",
            min_value=1,
            max_value=n,
            value=min(st.session_state.indice_cruce + 1, n),
            key="cruce_idx",
        )
        st.session_state.indice_cruce = int(ix) - 1

    cruce = filtrados[st.session_state.indice_cruce]
    estado = "⚠️ Revisar" if cruce.inconsistente else "✓ OK"
    st.subheader(f"{cruce.id} · {cruce.club_base} · {estado}")
    st.write(cruce.motivo)

    filas_anio = []
    for anio in FOCUS_YEARS:
        items = cruce.por_anio.get(anio, [])
        if not items:
            filas_anio.append(
                {"Temporada": anio, "En datos": "No", "Texto CSV": "—", "Tras mapa": "—", "Partidos": 0, "En mapa": ""}
            )
        else:
            for it in items:
                filas_anio.append(
                    {
                        "Temporada": anio,
                        "En datos": "Sí",
                        "Texto CSV": it.nombre_raw,
                        "Tras mapa": it.nombre_norm,
                        "Partidos": it.partidos,
                        "En mapa": "Sí" if it.en_mapeo else "No",
                    }
                )
    st.dataframe(pd.DataFrame(filas_anio), use_container_width=True, hide_index=True)

    todos_raw = [it.nombre_raw for items in cruce.por_anio.values() for it in items]
    canonicos = sorted({str(v).strip() for v in cargar_mapeo_equipos().values()})
    sugerencia = cruce.sugerencia or ""
    opciones = sorted(set(canonicos + ([sugerencia] if sugerencia else [])))
    destino = st.selectbox(
        "Unificar todo a (canónico)",
        options=opciones,
        index=opciones.index(sugerencia) if sugerencia in opciones else 0,
        key="cruce_dest",
    )
    custom = st.text_input("Otro destino", value="", key="cruce_dest_custom")
    if custom.strip():
        destino = custom.strip()

    a_mapear = st.multiselect(
        "Textos CSV a mapear (todas las temporadas)",
        options=todos_raw,
        default=todos_raw,
        key="cruce_orig",
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Guardar mapeos", type="primary", key="cruce_save"):
            if a_mapear:
                agregar_entradas_mapeo({o: destino for o in a_mapear})
                _limpiar_cache()
                st.success("Guardado.")
                st.rerun()
    with b2:
        if st.button("Guardar y siguiente", key="cruce_save_next"):
            if a_mapear:
                agregar_entradas_mapeo({o: destino for o in a_mapear})
                _limpiar_cache()
                st.session_state.indice_cruce = (st.session_state.indice_cruce + 1) % n
                st.rerun()


def _tab_listado_temporadas(tabla: pd.DataFrame) -> None:
    st.markdown(
        "Listado **temporada × nombre**. Ordená alfabéticamente y filtrá repetidos o "
        "clubes con **un nombre distinto por año** (no aparecen en «Cruzar temporadas»)."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        temp_op = st.selectbox(
            "Temporada",
            ["Todas"] + [str(y) for y in FOCUS_YEARS],
            key="list_temp",
        )
    with c2:
        filtro_label = st.selectbox("Filtrar", list(FILTROS_LISTADO.keys()), key="list_filtro")
    with c3:
        orden = st.selectbox(
            "Ordenar por",
            [
                "nombre_csv",
                "nombre_normalizado",
                "club_base_desde_csv",
                "club_base",
                "temporada",
                "partidos",
            ],
            index=2,
            key="list_orden",
        )
    with c4:
        orden_desc = st.checkbox("Descendente", value=False, key="list_desc")

    buscar = st.text_input("Buscar nombre o club", key="list_buscar")

    temp_val = None if temp_op == "Todas" else int(temp_op)
    vista = filtrar_listado(
        tabla,
        temporada=temp_val,
        buscar=buscar,
        filtro_tipo=FILTROS_LISTADO[filtro_label],
    )
    if orden in ("nombre_csv", "nombre_normalizado", "club_base", "club_base_desde_csv") and orden in vista.columns:
        vista = vista.assign(_ord=vista[orden].astype(str).str.upper())
        vista = vista.sort_values("_ord", ascending=not orden_desc).drop(columns="_ord")
    else:
        vista = vista.sort_values(orden, ascending=not orden_desc)

    st.caption(f"**{len(vista)}** filas (de {len(tabla)} totales)")

    if st.button("Exportar listado CSV", key="export_listado"):
        OUTPUT_LISTADO.parent.mkdir(parents=True, exist_ok=True)
        vista.to_csv(OUTPUT_LISTADO, index=False, encoding="utf-8-sig", sep=";")
        st.success(f"Guardado: {OUTPUT_LISTADO}")

    mostrar = vista.rename(
        columns={
            "temporada": "Temporada",
            "nombre_csv": "Nombre en CSV",
            "nombre_normalizado": "Tras mapa",
            "club_base": "Club base (norm)",
            "club_base_desde_csv": "Club base (CSV)",
            "partidos": "Partidos",
            "en_mapa": "En mapa",
            "destino_mapeo": "Destino mapa",
            "temporadas_con_mismo_csv": "Temp. mismo CSV",
            "temporadas_con_mismo_norm": "Temp. mismo norm",
            "variantes_csv_mismo_club": "Variantes club",
            "solo_esta_temporada": "Solo 1 temp.",
        }
    )
    st.dataframe(mostrar, use_container_width=True, hide_index=True, height=420)

    if not vista.empty and "club_base_desde_csv" in vista.columns:
        with st.expander("Vista por club (pivot temporadas)", expanded=False):
            pivot_rows = []
            for club, g in vista.groupby("club_base_desde_csv"):
                row = {"Club base (CSV)": club}
                for y in FOCUS_YEARS:
                    sub = g[g["temporada"] == y]
                    row[str(y)] = (
                        ", ".join(sorted(sub["nombre_csv"].unique())) if len(sub) else "—"
                    )
                pivot_rows.append(row)
            st.dataframe(
                pd.DataFrame(pivot_rows).sort_values("Club base (CSV)"),
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("Unificar selección")
    if vista.empty:
        return

    opciones = [
        f"{int(r.temporada)} | {r.nombre_csv}"
        for r in vista.itertuples(index=False)
    ]
    elegidos = st.multiselect(
        "Elegí filas (temporada | nombre CSV)",
        options=opciones,
        key="list_multi",
    )
    canonicos = sorted({str(v).strip() for v in cargar_mapeo_equipos().values()})
    destino = st.selectbox("Unificar a", options=canonicos, key="list_dest")
    dest_custom = st.text_input("Otro destino", value="", key="list_dest_c")
    if dest_custom.strip():
        destino = dest_custom.strip()

    if st.button("Guardar mapeos seleccionados", type="primary", key="list_save"):
        if not elegidos:
            st.warning("Elegí al menos una fila.")
        else:
            entradas = {}
            for op in elegidos:
                nombre = op.split(" | ", 1)[1]
                entradas[nombre] = destino
            agregar_entradas_mapeo(entradas)
            _limpiar_cache()
            st.success(f"{len(entradas)} entradas guardadas.")
            st.rerun()


def _tab_estado_mapeo(map_path: Path) -> None:
    mapeo = cargar_mapeo_equipos()
    stats = resumen_mapeo(mapeo)

    c1, c2, c3 = st.columns(3)
    c1.metric("Entradas en mapa", stats["entradas"])
    c2.metric("Nombres canónicos distintos", stats["destinos_unicos"])
    c3.metric("Alias → mismo destino", stats["origenes_duplicados_destino"])

    inv_dest: dict[str, list[str]] = defaultdict(list)
    for origen, destino in sorted(mapeo.items(), key=lambda x: x[0]):
        inv_dest[destino].append(origen)

    multi = {d: o for d, o in inv_dest.items() if len(o) > 1}
    st.subheader("Destinos con varios alias")
    if not multi:
        st.info("Cada destino tiene un solo origen (o revisá el JSON).")
    else:
        filas = [
            {"Canónico": d, "Cantidad alias": len(origs), "Alias (muestra)": ", ".join(origs[:5])}
            for d, origs in sorted(multi.items(), key=lambda x: -len(x[1]))[:50]
        ]
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    st.subheader("Tabla completa (origen → destino, A-Z)")
    tabla = pd.DataFrame(
        [{"Origen": k, "Destino": v} for k, v in sorted(mapeo.items(), key=lambda x: x[0])]
    )
    st.dataframe(tabla, use_container_width=True, hide_index=True, height=400)

    with st.expander("Editar equipos_map.json"):
        texto = st.text_area("JSON", value=map_path.read_text(encoding="utf-8"), height=200)
        if st.button("Guardar JSON"):
            try:
                data = json.loads(texto)
                if not isinstance(data, dict):
                    raise ValueError("Debe ser un objeto JSON.")
                guardar_mapeo_equipos(data)
                _limpiar_cache()
                st.success("Guardado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))


def main() -> None:
    st.set_page_config(page_title="Mapeo de equipos", layout="wide")
    st.title("Mapeo de equipos")

    consolidado = resolve_partidos_consolidado()
    if not consolidado.is_file():
        st.error(
            f"No existe {consolidado}. Ejecutá: "
            "`python pipelines/consolidar_temporadas.py`"
        )
        st.stop()

    map_path = ROOT / "mapeos" / "equipos_map.json"
    p_mtime = consolidado.stat().st_mtime
    m_mtime = map_path.stat().st_mtime

    with st.sidebar:
        st.header("Pipeline")
        chk_consolidar = st.checkbox("Consolidar 23-26.csv", value=True)
        chk_ranking = st.checkbox("Regenerar rankings", value=True)
        if st.button("Aplicar normalizador", type="primary", use_container_width=True):
            ok, log = _ejecutar_normalizador(chk_consolidar, chk_ranking)
            _limpiar_cache()
            if ok:
                st.success("Listo.")
            else:
                st.error("Error (ver log).")
            if log.strip():
                st.code(log[-3000:])
        if st.button("Refrescar datos", use_container_width=True):
            _limpiar_cache()
            st.rerun()
        st.caption(f"`{consolidado.name}` · mapa: {len(cargar_mapeo_equipos())} entradas")

    tabla_casos, casos_lista = _cargar_casos(str(consolidado), p_mtime, m_mtime)
    df_partidos = _cargar_partidos_region(str(consolidado), p_mtime, m_mtime)
    tabla_cruce, casos_cruce = _cargar_cruce(str(consolidado), p_mtime, m_mtime)
    tabla_listado = _cargar_listado(str(consolidado), p_mtime, m_mtime)

    tab_casos, tab_listado, tab_cruce, tab_region, tab_mapa = st.tabs(
        [
            "Iterar casos",
            "Listado por temporada",
            "Cruzar temporadas",
            "Equipos por región",
            "Estado del mapeo",
        ]
    )
    with tab_casos:
        _tab_iterar_casos(consolidado, map_path, tabla_casos, casos_lista)
    with tab_listado:
        _tab_listado_temporadas(tabla_listado)
    with tab_cruce:
        _tab_cruce_temporadas(tabla_cruce, casos_cruce)
    with tab_region:
        _tab_equipos_region(df_partidos)
    with tab_mapa:
        _tab_estado_mapeo(map_path)


if __name__ == "__main__":
    main()
