from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from glob import glob
from typing import Dict, Iterable, List, Optional, Tuple

import psycopg
from psycopg.types.json import Json


DDL_PARTIDOS = """
CREATE TABLE IF NOT EXISTS partidos (
    partido_id TEXT PRIMARY KEY,
    comp_id INTEGER,
    competencia TEXT,
    temporada TEXT,
    categoria TEXT,
    categoria_id INTEGER,
    fase TEXT,
    fase_id INTEGER,
    grupo TEXT,
    grupo_id INTEGER,
    fase_ges TEXT,
    grupo_ges TEXT,
    zona TEXT,
    ronda TEXT,
    nivel TEXT,
    fecha TEXT,
    local TEXT,
    visitante TEXT,
    estado TEXT,
    equipo_local_id INTEGER,
    equipo_visitante_id INTEGER,
    entrenador_local TEXT,
    entrenador_visitante TEXT,
    estadisticas JSONB
);
"""


def migrate_partidos_torneo_columnas(cur) -> None:
    """Columnas nuevas en instalaciones previas (IF NOT EXISTS)."""
    stmts = [
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS fase_ges TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS grupo_ges TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS zona TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS ronda TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS nivel TEXT",
    ]
    for sql in stmts:
        cur.execute(sql)

DDL_CLUBES = """
CREATE TABLE IF NOT EXISTS clubes (
    club_id INTEGER PRIMARY KEY,
    nombre TEXT
);
"""

DDL_EQUIPOS = """
CREATE TABLE IF NOT EXISTS equipos (
    equipo_id INTEGER PRIMARY KEY,
    club_id INTEGER,
    nombre TEXT
);
"""

DDL_JUGADORES = """
CREATE TABLE IF NOT EXISTS jugadores (
    jugador_id INTEGER PRIMARY KEY,
    club_id INTEGER,
    nombre TEXT,
    nombre_completo TEXT
);
"""

DDL_TEMPORADAS = """
CREATE TABLE IF NOT EXISTS temporadas (
    temporada_id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) UNIQUE NOT NULL
);
"""

DDL_JCT = """
CREATE TABLE IF NOT EXISTS jugador_club_temporada (
    jct_id SERIAL PRIMARY KEY,
    jugador_id INTEGER,
    club_id INTEGER,
    temporada_id INTEGER,
    UNIQUE (jugador_id, club_id, temporada_id)
);
"""

DDL_ESTADISTICAS_JUGADOR = """
CREATE TABLE IF NOT EXISTS estadisticas_jugador (
    partido_id TEXT,
    equipo_id INTEGER,
    nro TEXT,
    inicial BOOLEAN,
    min TEXT,
    pts INTEGER,
    dos_a INTEGER,
    dos_i INTEGER,
    tres_a INTEGER,
    tres_i INTEGER,
    uno_a INTEGER,
    uno_i INTEGER,
    rebdef INTEGER,
    rebofe INTEGER,
    rebtot INTEGER,
    ast INTEGER,
    rec INTEGER,
    per INTEGER,
    tap INTEGER,
    fal INTEGER,
    val INTEGER,
    jct_id INTEGER NOT NULL,
    PRIMARY KEY (partido_id, jct_id)
);
"""

DDL_TOTALES_EQUIPO = """
CREATE TABLE IF NOT EXISTS totales_equipo (
    partido_id TEXT,
    equipo_id INTEGER,
    pts INTEGER,
    rebdef INTEGER,
    rebofe INTEGER,
    rebtot INTEGER,
    ast INTEGER,
    rec INTEGER,
    per INTEGER,
    tap INTEGER,
    fal INTEGER,
    dos_a INTEGER,
    dos_i INTEGER,
    tres_a INTEGER,
    tres_i INTEGER,
    uno_a INTEGER,
    uno_i INTEGER,
    PRIMARY KEY (partido_id, equipo_id)
);
"""

DDL_PLAY_BY_PLAY = """
CREATE TABLE IF NOT EXISTS play_by_play (
    partido_id TEXT NOT NULL,
    event_idx INTEGER NOT NULL,
    cuarto INTEGER,
    clock TEXT,
    tipo TEXT,
    equipo TEXT,
    jugador TEXT,
    dorsal INTEGER,
    score_local INTEGER,
    score_visitante INTEGER,
    hora_real TEXT,
    raw TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (partido_id, event_idx),
    CONSTRAINT play_by_play_partido_fk FOREIGN KEY (partido_id)
        REFERENCES partidos (partido_id) ON DELETE CASCADE
);
"""

DELETE_PLAY_BY_PLAY_PARTIDO = "DELETE FROM play_by_play WHERE partido_id = %(partido_id)s"

INSERT_PLAY_BY_PLAY = """
INSERT INTO play_by_play (
    partido_id,
    event_idx,
    cuarto,
    clock,
    tipo,
    equipo,
    jugador,
    dorsal,
    score_local,
    score_visitante,
    hora_real,
    raw,
    payload
)
VALUES (
    %(partido_id)s,
    %(event_idx)s,
    %(cuarto)s,
    %(clock)s,
    %(tipo)s,
    %(equipo)s,
    %(jugador)s,
    %(dorsal)s,
    %(score_local)s,
    %(score_visitante)s,
    %(hora_real)s,
    %(raw)s,
    %(payload)s
);
"""


INSERT_PARTIDOS = """
INSERT INTO partidos (
    partido_id,
    comp_id,
    competencia,
    temporada,
    categoria,
    categoria_id,
    fase,
    fase_id,
    grupo,
    grupo_id,
    fase_ges,
    grupo_ges,
    zona,
    ronda,
    nivel,
    fecha,
    local,
    visitante,
    estado,
    equipo_local_id,
    equipo_visitante_id,
    entrenador_local,
    entrenador_visitante,
    estadisticas
)
VALUES (
    %(partido_id)s,
    %(comp_id)s,
    %(competencia)s,
    %(temporada)s,
    %(categoria)s,
    %(categoria_id)s,
    %(fase)s,
    %(fase_id)s,
    %(grupo)s,
    %(grupo_id)s,
    %(fase_ges)s,
    %(grupo_ges)s,
    %(zona)s,
    %(ronda)s,
    %(nivel)s,
    %(fecha)s,
    %(local)s,
    %(visitante)s,
    %(estado)s,
    %(equipo_local_id)s,
    %(equipo_visitante_id)s,
    %(entrenador_local)s,
    %(entrenador_visitante)s,
    %(estadisticas)s
)
ON CONFLICT (partido_id)
DO UPDATE SET
    comp_id = EXCLUDED.comp_id,
    competencia = EXCLUDED.competencia,
    temporada = EXCLUDED.temporada,
    categoria = EXCLUDED.categoria,
    categoria_id = EXCLUDED.categoria_id,
    fase = EXCLUDED.fase,
    fase_id = EXCLUDED.fase_id,
    grupo = EXCLUDED.grupo,
    grupo_id = EXCLUDED.grupo_id,
    fase_ges = EXCLUDED.fase_ges,
    grupo_ges = EXCLUDED.grupo_ges,
    zona = EXCLUDED.zona,
    ronda = EXCLUDED.ronda,
    nivel = EXCLUDED.nivel,
    fecha = EXCLUDED.fecha,
    local = EXCLUDED.local,
    visitante = EXCLUDED.visitante,
    estado = EXCLUDED.estado,
    equipo_local_id = EXCLUDED.equipo_local_id,
    equipo_visitante_id = EXCLUDED.equipo_visitante_id,
    entrenador_local = EXCLUDED.entrenador_local,
    entrenador_visitante = EXCLUDED.entrenador_visitante,
    estadisticas = EXCLUDED.estadisticas;
"""


INSERT_CLUBES = """
INSERT INTO clubes (club_id, nombre)
VALUES (%(club_id)s, %(nombre)s)
ON CONFLICT (club_id)
DO UPDATE SET nombre = EXCLUDED.nombre;
"""


INSERT_EQUIPOS = """
INSERT INTO equipos (equipo_id, club_id, nombre)
VALUES (%(equipo_id)s, %(club_id)s, %(nombre)s)
ON CONFLICT (equipo_id)
DO UPDATE SET
    club_id = EXCLUDED.club_id,
    nombre = EXCLUDED.nombre;
"""


INSERT_JUGADORES = """
INSERT INTO jugadores (jugador_id, club_id, nombre, nombre_completo)
VALUES (%(jugador_id)s, %(club_id)s, %(nombre)s, %(nombre_completo)s)
ON CONFLICT (jugador_id)
DO UPDATE SET
    club_id = EXCLUDED.club_id,
    nombre = EXCLUDED.nombre,
    nombre_completo = EXCLUDED.nombre_completo;
"""

INSERT_TEMPORADAS = """
INSERT INTO temporadas (nombre)
VALUES (%(nombre)s)
ON CONFLICT (nombre)
DO UPDATE SET nombre = EXCLUDED.nombre
RETURNING temporada_id;
"""

INSERT_JCT = """
INSERT INTO jugador_club_temporada (jugador_id, club_id, temporada_id)
VALUES (%(jugador_id)s, %(club_id)s, %(temporada_id)s)
ON CONFLICT (jugador_id, club_id, temporada_id)
DO UPDATE SET jugador_id = EXCLUDED.jugador_id
RETURNING jct_id;
"""


INSERT_ESTADISTICAS_JUGADOR = """
INSERT INTO estadisticas_jugador (
    partido_id,
    equipo_id,
    nro,
    inicial,
    min,
    pts,
    dos_a,
    dos_i,
    tres_a,
    tres_i,
    uno_a,
    uno_i,
    rebdef,
    rebofe,
    rebtot,
    ast,
    rec,
    per,
    tap,
    fal,
    val,
    jct_id
)
VALUES (
    %(partido_id)s,
    %(equipo_id)s,
    %(nro)s,
    %(inicial)s,
    %(min)s,
    %(pts)s,
    %(dos_a)s,
    %(dos_i)s,
    %(tres_a)s,
    %(tres_i)s,
    %(uno_a)s,
    %(uno_i)s,
    %(rebdef)s,
    %(rebofe)s,
    %(rebtot)s,
    %(ast)s,
    %(rec)s,
    %(per)s,
    %(tap)s,
    %(fal)s,
    %(val)s,
    %(jct_id)s
)
ON CONFLICT (partido_id, jct_id)
DO UPDATE SET
    equipo_id = EXCLUDED.equipo_id,
    nro = EXCLUDED.nro,
    inicial = EXCLUDED.inicial,
    min = EXCLUDED.min,
    pts = EXCLUDED.pts,
    dos_a = EXCLUDED.dos_a,
    dos_i = EXCLUDED.dos_i,
    tres_a = EXCLUDED.tres_a,
    tres_i = EXCLUDED.tres_i,
    uno_a = EXCLUDED.uno_a,
    uno_i = EXCLUDED.uno_i,
    rebdef = EXCLUDED.rebdef,
    rebofe = EXCLUDED.rebofe,
    rebtot = EXCLUDED.rebtot,
    ast = EXCLUDED.ast,
    rec = EXCLUDED.rec,
    per = EXCLUDED.per,
    tap = EXCLUDED.tap,
    fal = EXCLUDED.fal,
    val = EXCLUDED.val;
"""


INSERT_TOTALES_EQUIPO = """
INSERT INTO totales_equipo (
    partido_id,
    equipo_id,
    pts,
    rebdef,
    rebofe,
    rebtot,
    ast,
    rec,
    per,
    tap,
    fal,
    dos_a,
    dos_i,
    tres_a,
    tres_i,
    uno_a,
    uno_i
)
VALUES (
    %(partido_id)s,
    %(equipo_id)s,
    %(pts)s,
    %(rebdef)s,
    %(rebofe)s,
    %(rebtot)s,
    %(ast)s,
    %(rec)s,
    %(per)s,
    %(tap)s,
    %(fal)s,
    %(dos_a)s,
    %(dos_i)s,
    %(tres_a)s,
    %(tres_i)s,
    %(uno_a)s,
    %(uno_i)s
)
ON CONFLICT (partido_id, equipo_id)
DO UPDATE SET
    pts = EXCLUDED.pts,
    rebdef = EXCLUDED.rebdef,
    rebofe = EXCLUDED.rebofe,
    rebtot = EXCLUDED.rebtot,
    ast = EXCLUDED.ast,
    rec = EXCLUDED.rec,
    per = EXCLUDED.per,
    tap = EXCLUDED.tap,
    fal = EXCLUDED.fal,
    dos_a = EXCLUDED.dos_a,
    dos_i = EXCLUDED.dos_i,
    tres_a = EXCLUDED.tres_a,
    tres_i = EXCLUDED.tres_i,
    uno_a = EXCLUDED.uno_a,
    uno_i = EXCLUDED.uno_i;
"""


def load_lote(path: str) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return list(data.values())
    return data


def iter_lotes(pattern: str) -> Iterable[str]:
    return sorted(glob(pattern))


def should_skip_categoria(categoria: Optional[str]) -> bool:
    if not categoria:
        return False
    categoria_upper = categoria.upper()
    return "PRE MINI" in categoria_upper or "MINI" in categoria_upper


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _to_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1", "si", "sí"}:
            return True
        if value.lower() in {"false", "0", "no"}:
            return False
    return None


def _to_str(value: object) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@dataclass(frozen=True)
class Partido:
    partido_id: str
    comp_id: Optional[int]
    competencia: Optional[str]
    temporada: Optional[str]
    categoria: Optional[str]
    categoria_id: Optional[int]
    fase: Optional[str]
    fase_id: Optional[int]
    grupo: Optional[str]
    grupo_id: Optional[int]
    fase_ges: Optional[str]
    grupo_ges: Optional[str]
    zona: Optional[str]
    ronda: Optional[str]
    nivel: Optional[str]
    fecha: Optional[str]
    local: Optional[str]
    visitante: Optional[str]
    estado: Optional[str]
    estadisticas: object
    equipo_local_id: Optional[int]
    equipo_visitante_id: Optional[int]
    entrenador_local: Optional[str]
    entrenador_visitante: Optional[str]

    @classmethod
    def from_dict(cls, row: Dict[str, object]) -> "Partido":
        partido_id = row.get("partido_id")
        if not partido_id:
            raise ValueError("partido_id es requerido")
        estadisticas = row.get("estadisticas") or {}
        return cls(
            partido_id=str(partido_id),
            comp_id=_to_int(row.get("comp_id")),
            competencia=row.get("competencia"),
            temporada=row.get("temporada"),
            categoria=row.get("categoria"),
            categoria_id=_to_int(row.get("categoria_id")),
            fase=_to_str(row.get("fase")),
            fase_id=_to_int(row.get("fase_id")),
            grupo=_to_str(row.get("grupo")),
            grupo_id=_to_int(row.get("grupo_id")),
            fase_ges=_to_str(row.get("fase_ges")),
            grupo_ges=_to_str(row.get("grupo_ges")),
            zona=_to_str(row.get("zona")),
            ronda=_to_str(row.get("ronda")),
            nivel=_to_str(row.get("nivel")),
            fecha=row.get("fecha"),
            local=row.get("local"),
            visitante=row.get("visitante"),
            estado=row.get("estado"),
            estadisticas=estadisticas,
            equipo_local_id=None,
            equipo_visitante_id=None,
            entrenador_local=_to_str(estadisticas.get("entrenadorlocal")),
            entrenador_visitante=_to_str(estadisticas.get("entrenadorvisitante")),
        )

    def to_db_dict(self) -> Dict[str, object]:
        return {
            "partido_id": self.partido_id,
            "comp_id": self.comp_id,
            "competencia": self.competencia,
            "temporada": self.temporada,
            "categoria": self.categoria,
            "categoria_id": self.categoria_id,
            "fase": self.fase,
            "fase_id": self.fase_id,
            "grupo": self.grupo,
            "grupo_id": self.grupo_id,
            "fase_ges": self.fase_ges,
            "grupo_ges": self.grupo_ges,
            "zona": self.zona,
            "ronda": self.ronda,
            "nivel": self.nivel,
            "fecha": self.fecha,
            "local": self.local,
            "visitante": self.visitante,
            "estado": self.estado,
            "equipo_local_id": self.equipo_local_id,
            "equipo_visitante_id": self.equipo_visitante_id,
            "entrenador_local": self.entrenador_local,
            "entrenador_visitante": self.entrenador_visitante,
            "estadisticas": json.dumps(self.estadisticas),
        }


@dataclass(frozen=True)
class Club:
    club_id: int
    nombre: Optional[str]

    def to_db_dict(self) -> Dict[str, object]:
        return {"club_id": self.club_id, "nombre": self.nombre}


@dataclass(frozen=True)
class Equipo:
    equipo_id: int
    club_id: Optional[int]
    nombre: Optional[str]

    def to_db_dict(self) -> Dict[str, object]:
        return {
            "equipo_id": self.equipo_id,
            "club_id": self.club_id,
            "nombre": self.nombre,
        }


@dataclass(frozen=True)
class Jugador:
    jugador_id: int
    club_id: Optional[int]
    nombre: Optional[str]
    nombre_completo: Optional[str]

    def to_db_dict(self) -> Dict[str, object]:
        return {
            "jugador_id": self.jugador_id,
            "club_id": self.club_id,
            "nombre": self.nombre,
            "nombre_completo": self.nombre_completo,
        }


@dataclass(frozen=True)
class EstadisticaJugador:
    partido_id: str
    jugador_id: int
    equipo_id: Optional[int]
    club_id: Optional[int]
    nro: Optional[str]
    inicial: Optional[bool]
    min: Optional[str]
    pts: Optional[int]
    dos_a: Optional[int]
    dos_i: Optional[int]
    tres_a: Optional[int]
    tres_i: Optional[int]
    uno_a: Optional[int]
    uno_i: Optional[int]
    rebdef: Optional[int]
    rebofe: Optional[int]
    rebtot: Optional[int]
    ast: Optional[int]
    rec: Optional[int]
    per: Optional[int]
    tap: Optional[int]
    fal: Optional[int]
    val: Optional[int]
    jct_id: Optional[int]

    @classmethod
    def from_dict(
        cls, partido_id: str, row: Dict[str, object]
    ) -> "EstadisticaJugador":
        jugador_id = _to_int(row.get("jugador_id"))
        if jugador_id is None:
            raise ValueError("jugador_id es requerido")
        return cls(
            partido_id=partido_id,
            jugador_id=jugador_id,
            equipo_id=_to_int(row.get("equipo_id")),
            club_id=_to_int(row.get("club_id")),
            nro=_to_str(row.get("nro")),
            inicial=_to_bool(row.get("inicial")),
            min=_to_str(row.get("min")),
            pts=_to_int(row.get("pts")),
            dos_a=_to_int(row.get("2PA")),
            dos_i=_to_int(row.get("2PI")),
            tres_a=_to_int(row.get("3PA")),
            tres_i=_to_int(row.get("3PI")),
            uno_a=_to_int(row.get("1PA")),
            uno_i=_to_int(row.get("1PI")),
            rebdef=_to_int(row.get("rebdef")),
            rebofe=_to_int(row.get("rebofe")),
            rebtot=_to_int(row.get("rebtot")),
            ast=_to_int(row.get("ast")),
            rec=_to_int(row.get("rec")),
            per=_to_int(row.get("per")),
            tap=_to_int(row.get("tap")),
            fal=_to_int(row.get("fal")),
            val=_to_int(row.get("val")),
            jct_id=None,
        )

    def to_db_dict(self) -> Dict[str, object]:
        return {
            "partido_id": self.partido_id,
            "equipo_id": self.equipo_id,
            "nro": self.nro,
            "inicial": self.inicial,
            "min": self.min,
            "pts": self.pts,
            "dos_a": self.dos_a,
            "dos_i": self.dos_i,
            "tres_a": self.tres_a,
            "tres_i": self.tres_i,
            "uno_a": self.uno_a,
            "uno_i": self.uno_i,
            "rebdef": self.rebdef,
            "rebofe": self.rebofe,
            "rebtot": self.rebtot,
            "ast": self.ast,
            "rec": self.rec,
            "per": self.per,
            "tap": self.tap,
            "fal": self.fal,
            "val": self.val,
            "jct_id": self.jct_id,
        }


@dataclass(frozen=True)
class TotalesEquipo:
    partido_id: str
    equipo_id: int
    pts: Optional[int]
    rebdef: Optional[int]
    rebofe: Optional[int]
    rebtot: Optional[int]
    ast: Optional[int]
    rec: Optional[int]
    per: Optional[int]
    tap: Optional[int]
    fal: Optional[int]
    dos_a: Optional[int]
    dos_i: Optional[int]
    tres_a: Optional[int]
    tres_i: Optional[int]
    uno_a: Optional[int]
    uno_i: Optional[int]

    @classmethod
    def from_dict(
        cls, partido_id: str, equipo_id: Optional[int], row: Dict[str, object]
    ) -> Optional["TotalesEquipo"]:
        if equipo_id is None:
            return None
        return cls(
            partido_id=partido_id,
            equipo_id=equipo_id,
            pts=_to_int(row.get("pts")),
            rebdef=_to_int(row.get("rebdef")),
            rebofe=_to_int(row.get("rebofe")),
            rebtot=_to_int(row.get("rebtot")),
            ast=_to_int(row.get("ast")),
            rec=_to_int(row.get("rec")),
            per=_to_int(row.get("per")),
            tap=_to_int(row.get("tap")),
            fal=_to_int(row.get("fal")),
            dos_a=_to_int(row.get("2PA")),
            dos_i=_to_int(row.get("2PI")),
            tres_a=_to_int(row.get("3PA")),
            tres_i=_to_int(row.get("3PI")),
            uno_a=_to_int(row.get("1PA")),
            uno_i=_to_int(row.get("1PI")),
        )

    def to_db_dict(self) -> Dict[str, object]:
        return {
            "partido_id": self.partido_id,
            "equipo_id": self.equipo_id,
            "pts": self.pts,
            "rebdef": self.rebdef,
            "rebofe": self.rebofe,
            "rebtot": self.rebtot,
            "ast": self.ast,
            "rec": self.rec,
            "per": self.per,
            "tap": self.tap,
            "fal": self.fal,
            "dos_a": self.dos_a,
            "dos_i": self.dos_i,
            "tres_a": self.tres_a,
            "tres_i": self.tres_i,
            "uno_a": self.uno_a,
            "uno_i": self.uno_i,
        }


def load_config(path: str = "config.json") -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dsn(cfg: Dict[str, object]) -> str:
    db = cfg.get("db", {})
    host = db.get("host", "localhost")
    port = db.get("port", 5432)
    user = db.get("user")
    password = db.get("password")
    name = db.get("name")
    if not user or not password or not name:
        raise RuntimeError("Config incompleta en config.json (db.user/db.password/db.name)")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _default_config_path() -> str:
    """Ruta por defecto a config.json en la raíz del proyecto."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config.json")


def connect():
    config_path = os.environ.get("CONFIG_PATH", _default_config_path())
    cfg = load_config(config_path)
    dsn = build_dsn(cfg)
    return psycopg.connect(dsn)


def ensure_schema_argbasket(cur) -> None:
    """Crea `partidos` (si no existe) y tabla `play_by_play` para pipeline argentina.basketball."""
    cur.execute(DDL_PARTIDOS)
    migrate_partidos_torneo_columnas(cur)
    cur.execute(DDL_PLAY_BY_PLAY)


def _estado_desde_marcador(pts_local: Optional[int], pts_visitante: Optional[int]) -> str:
    if pts_local is not None and pts_visitante is not None:
        return "COMPLETO"
    return "PENDIENTE"


def _entrenadores_desde_boxscore(box: Dict[str, object]) -> Tuple[Optional[str], Optional[str]]:
    equipos = box.get("equipos") if isinstance(box, dict) else None
    if not isinstance(equipos, list) or not equipos:
        return (None, None)
    loc = equipos[0] if len(equipos) > 0 else {}
    vis = equipos[1] if len(equipos) > 1 else {}
    el = _to_str(loc.get("entrenador")) if isinstance(loc, dict) else None
    ev = _to_str(vis.get("entrenador")) if isinstance(vis, dict) else None
    return (el, ev)


def build_argbasket_partido_row(
    *,
    partido_id: str,
    comp_cat_id: int,
    categoria: str,
    fecha: str,
    local: str,
    visitante: str,
    pts_local: Optional[str],
    pts_visitante: Optional[str],
    estadisticas: object,
    temporada: str = "2026",
    competencia: str = "LIGA FEDERAL FORMATIVAS",
) -> Dict[str, object]:
    pl = _to_int(pts_local) if pts_local not in (None, "") else None
    pv = _to_int(pts_visitante) if pts_visitante not in (None, "") else None
    estado = _estado_desde_marcador(pl, pv)
    ent_l: Optional[str] = None
    ent_v: Optional[str] = None
    if isinstance(estadisticas, dict) and estadisticas.get("equipos"):
        ent_l, ent_v = _entrenadores_desde_boxscore(estadisticas)
    if isinstance(estadisticas, str):
        stats_json = estadisticas
    else:
        stats_json = json.dumps(estadisticas or {}, ensure_ascii=False)
    return {
        "partido_id": partido_id,
        "comp_id": comp_cat_id,
        "competencia": competencia,
        "temporada": temporada,
        "categoria": categoria,
        "categoria_id": comp_cat_id,
        "fase": None,
        "fase_id": None,
        "grupo": None,
        "grupo_id": None,
        "fase_ges": None,
        "grupo_ges": None,
        "zona": None,
        "ronda": None,
        "nivel": None,
        "fecha": fecha,
        "local": local,
        "visitante": visitante,
        "estado": estado,
        "equipo_local_id": None,
        "equipo_visitante_id": None,
        "entrenador_local": ent_l,
        "entrenador_visitante": ent_v,
        "estadisticas": stats_json,
    }


def upsert_partido_argbasket(cur, row: Dict[str, object]) -> None:
    cur.execute(INSERT_PARTIDOS, row)


def _event_to_play_row(partido_id: str, event_idx: int, ev: Dict[str, object]) -> Dict[str, object]:
    raw = ev.get("raw")
    raw_s = (str(raw) if raw is not None else "")[:20000]
    return {
        "partido_id": partido_id,
        "event_idx": event_idx,
        "cuarto": _to_int(ev.get("cuarto")),
        "clock": _to_str(ev.get("clock")),
        "tipo": _to_str(ev.get("tipo")),
        "equipo": _to_str(ev.get("equipo")),
        "jugador": _to_str(ev.get("jugador")),
        "dorsal": _to_int(ev.get("dorsal")),
        "score_local": _to_int(ev.get("score_local")),
        "score_visitante": _to_int(ev.get("score_visitante")),
        "hora_real": _to_str(ev.get("hora_real")),
        "raw": raw_s or None,
        "payload": Json(ev),
    }


def replace_play_by_play_events(
    cur, partido_id: str, events: List[Dict[str, object]]
) -> None:
    cur.execute(DELETE_PLAY_BY_PLAY_PARTIDO, {"partido_id": partido_id})
    if not events:
        return
    rows = [
        _event_to_play_row(partido_id, i, ev)
        for i, ev in enumerate(events)
        if isinstance(ev, dict)
    ]
    if rows:
        cur.executemany(INSERT_PLAY_BY_PLAY, rows)


def get_temporada_id(
    cur, cache: Dict[str, int], temporada: Optional[str]
) -> Optional[int]:
    if not temporada:
        return None
    if temporada in cache:
        return cache[temporada]
    cur.execute(INSERT_TEMPORADAS, {"nombre": temporada})
    temporada_id = cur.fetchone()[0]
    cache[temporada] = temporada_id
    return temporada_id


def get_jct_id(
    cur,
    cache: Dict[tuple, int],
    jugador_id: Optional[int],
    club_id: Optional[int],
    temporada_id: Optional[int],
) -> Optional[int]:
    if jugador_id is None or club_id is None or temporada_id is None:
        return None
    key = (jugador_id, club_id, temporada_id)
    if key in cache:
        return cache[key]
    cur.execute(
        INSERT_JCT,
        {
            "jugador_id": jugador_id,
            "club_id": club_id,
            "temporada_id": temporada_id,
        },
    )
    jct_id = cur.fetchone()[0]
    cache[key] = jct_id
    return jct_id


def main():
    pattern = os.environ.get(
        "LOTES_PATTERN", "partidos_*_lote_*.json"
    )
    if not os.path.isabs(pattern) and not pattern.startswith("*"):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = os.path.join(root, pattern)
    files = list(iter_lotes(pattern))
    if not files:
        print(f"No se encontraron lotes con patron: {pattern}")
        return

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL_PARTIDOS)
            migrate_partidos_torneo_columnas(cur)
            cur.execute(DDL_CLUBES)
            cur.execute(DDL_EQUIPOS)
            cur.execute(DDL_JUGADORES)
            cur.execute(DDL_TEMPORADAS)
            cur.execute(DDL_JCT)
            cur.execute(DDL_ESTADISTICAS_JUGADOR)
            cur.execute(DDL_TOTALES_EQUIPO)
            cur.execute(DDL_PLAY_BY_PLAY)
            conn.commit()

        for path in files:
            rows = load_lote(path)
            partidos_payload: List[Dict[str, object]] = []
            clubes_payload: Dict[int, Dict[str, object]] = {}
            equipos_payload: Dict[int, Dict[str, object]] = {}
            jugadores_payload: Dict[int, Dict[str, object]] = {}
            estadisticas_payload: List[Dict[str, object]] = []
            totales_payload: List[Dict[str, object]] = []
            temporada_cache: Dict[str, int] = {}
            jct_cache: Dict[tuple, int] = {}
            with conn.cursor() as cur_lookup:
                for row in rows:
                    try:
                        partido = Partido.from_dict(row)
                    except ValueError as exc:
                        print(f"Fila invalida en {path}: {exc}")
                        continue
                    if should_skip_categoria(partido.categoria):
                        continue
                    estadisticas = partido.estadisticas or {}
                    temporada_id = get_temporada_id(
                        cur_lookup, temporada_cache, partido.temporada
                    )
                    local_stats = estadisticas.get("estadisticasequipolocal") or []
                    visitante_stats = estadisticas.get("estadisticasequipovisitante") or []
                    local_equipo_id = _to_int(
                        local_stats[0].get("equipo_id") if local_stats else None
                    )
                    visitante_equipo_id = _to_int(
                        visitante_stats[0].get("equipo_id") if visitante_stats else None
                    )
                    partido = replace(
                        partido,
                        equipo_local_id=local_equipo_id,
                        equipo_visitante_id=visitante_equipo_id,
                    )
                    partidos_payload.append(partido.to_db_dict())

                    for jugador_row in local_stats + visitante_stats:
                        jugador_id = _to_int(jugador_row.get("jugador_id"))
                        club_id = _to_int(jugador_row.get("club_id"))
                        equipo_id = _to_int(jugador_row.get("equipo_id"))
                        if club_id is not None:
                            clubes_payload.setdefault(
                                club_id, Club(club_id=club_id, nombre=None).to_db_dict()
                            )
                        if equipo_id is not None:
                            equipo_nombre = None
                            if equipo_id == local_equipo_id:
                                equipo_nombre = estadisticas.get("equipolocal") or partido.local
                            if equipo_id == visitante_equipo_id:
                                equipo_nombre = estadisticas.get("equipovisitante") or partido.visitante
                            equipos_payload.setdefault(
                                equipo_id,
                                Equipo(
                                    equipo_id=equipo_id,
                                    club_id=club_id,
                                    nombre=equipo_nombre,
                                ).to_db_dict(),
                            )
                        if jugador_id is not None:
                            jugadores_payload.setdefault(
                                jugador_id,
                                Jugador(
                                    jugador_id=jugador_id,
                                    club_id=club_id,
                                    nombre=_to_str(jugador_row.get("nombre")),
                                    nombre_completo=_to_str(jugador_row.get("nombre_completo")),
                                ).to_db_dict(),
                            )
                        try:
                            estadistica = EstadisticaJugador.from_dict(
                                partido.partido_id, jugador_row
                            )
                        except ValueError:
                            continue
                        jct_id = get_jct_id(
                            cur_lookup, jct_cache, jugador_id, club_id, temporada_id
                        )
                        if jct_id is None:
                            continue
                        estadistica = replace(estadistica, jct_id=jct_id)
                        estadisticas_payload.append(estadistica.to_db_dict())

                    total_local = estadisticas.get("totaleslocal") or {}
                    total_visitante = estadisticas.get("totalesvisitante") or {}
                    total_local_row = TotalesEquipo.from_dict(
                        partido.partido_id, local_equipo_id, total_local
                    )
                    if total_local_row:
                        totales_payload.append(total_local_row.to_db_dict())
                    total_visitante_row = TotalesEquipo.from_dict(
                        partido.partido_id, visitante_equipo_id, total_visitante
                    )
                    if total_visitante_row:
                        totales_payload.append(total_visitante_row.to_db_dict())

            if not partidos_payload:
                print(f"Sin filas validas: {path}")
                continue
            with conn.cursor() as cur:
                if clubes_payload:
                    cur.executemany(INSERT_CLUBES, list(clubes_payload.values()))
                if equipos_payload:
                    cur.executemany(INSERT_EQUIPOS, list(equipos_payload.values()))
                if jugadores_payload:
                    cur.executemany(INSERT_JUGADORES, list(jugadores_payload.values()))
                cur.executemany(INSERT_PARTIDOS, partidos_payload)
                if estadisticas_payload:
                    cur.executemany(INSERT_ESTADISTICAS_JUGADOR, estadisticas_payload)
                if totales_payload:
                    cur.executemany(INSERT_TOTALES_EQUIPO, totales_payload)
            conn.commit()
            print(
                "Persistido: "
                f"{path} (partidos={len(partidos_payload)}, "
                f"jugadores={len(jugadores_payload)}, "
                f"estadisticas={len(estadisticas_payload)})"
            )


if __name__ == "__main__":
    main()
