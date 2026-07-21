# -*- coding: utf-8 -*-
"""
Motor de la tabla de posiciones general de FORMATIVAS 2026 (competencia GES 2015).

Reglas (confirmadas con la organización):

* Navegación por etapa → nivel → zona. Los "niveles" son fases GES:
  Primera: ``TORNEO DE CLASIFICACION`` / ``TORNEO RECLASIFICATORIO``.
  Segunda: ``INTERCONFERENCIA A`` / ``INTERCONFERENCIA B`` / ``NIVEL 1``.
  (``CLASIFICACION LFF`` es nacional y queda fuera de este informe.)
* Categorías que suman a la tabla general (puntos por resultado):
  U13 (Infantiles), U15 (Cadetes), U17 (Juveniles).
    - Partido ganado: 2 puntos. Partido perdido: 1 punto.
    - Walkover ``20-0`` / ``0-20``: el ausente NO suma nada (0); el presente suma 2.
    - ``0-0``: ambos ausentes -> 0 para los dos.
* Categorías de presentación (no suman por resultado): U11 (Mini), U9 (Pre Mini).
    - Cada equipo suma 1 punto de presentación, salvo que no llegue al mínimo de
      jugadores con >= 10:00 de juego (regla mini: 12 jugadores).
    - En marcadores raros (0-0 / 20-0 / 0-20) se valida con el acta; en marcadores
      normales se asume que ambos equipos se presentaron.
* La tabla general es POR ZONA dentro de cada fase: a cada club/equipo se le suman los
  puntos de todas sus categorías. Las zonas se definen por las categorías grandes
  (NORTE/CENTRO/OESTE/SUR x 1A/2B/3C); los puntos de presentación U9/U11 se atribuyen
  al equipo por nombre normalizado.

Este módulo es lógica pura (sin red); la descarga/orquestación vive en
``analysis/generar_standings_febamba_2026.py``.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ingest.febamba.mini_masc_regla_plantilla import (
    MIN_JUGADORES_REGLA,
    MIN_SEGUNDOS_PREMINI,
    MIN_SEGUNDOS_REGLA,
    cuenta_jugadores_regla,
    ganador_boxscore,
)

ID_COMPETENCIA = 2015

PUNTOS_GANADO = 2
PUNTOS_PERDIDO = 1
PUNTO_PRESENTACION = 1

ROL_GENERAL = "general"
ROL_PRESENTACION = "presentacion"

# edad -> metadatos GES de la categoría.
CATEGORIAS: Dict[str, Dict[str, object]] = {
    "U9": {"nombre_ges": "PRE MINI MASCULINO", "id_categoria": 5080, "rol": ROL_PRESENTACION},
    "U11": {"nombre_ges": "MINI MASCULINO", "id_categoria": 5079, "rol": ROL_PRESENTACION},
    "U13": {"nombre_ges": "INFANTILES MASCULINO", "id_categoria": 5078, "rol": ROL_GENERAL},
    "U15": {"nombre_ges": "CADETES MASCULINO", "id_categoria": 5077, "rol": ROL_GENERAL},
    "U17": {"nombre_ges": "JUVENILES MASCULINO", "id_categoria": 5076, "rol": ROL_GENERAL},
}

EDADES_GENERAL = [e for e, c in CATEGORIAS.items() if c["rol"] == ROL_GENERAL]
EDADES_PRESENTACION = [e for e, c in CATEGORIAS.items() if c["rol"] == ROL_PRESENTACION]

# Nombre canónico de nivel (campo `fase` en partidos) -> nombres GES posibles.
# La grafía varía entre categorías; "fase" en el dataclass es en realidad el nivel.
FASES_CANONICAS: Dict[str, Tuple[str, ...]] = {
    "CLASIFICACION": ("TORNEO DE CLASIFICACION", "TORNEO CLASIFICATORIO"),
    "RECLASIFICACION": ("TORNEO RECLASIFICATORIO", "TORNEO RECLASIFICACION"),
    "INTERCONFERENCIA_A": ("INTERCONFERENCIA A",),
    "INTERCONFERENCIA_B": ("INTERCONFERENCIA B",),
    "NIVEL_1": ("NIVEL 1",),
}

FASE_LABEL: Dict[str, str] = {
    "CLASIFICACION": "Torneo Clasificatorio",
    "RECLASIFICACION": "Torneo Reclasificación",
    "INTERCONFERENCIA_A": "Interconferencia A",
    "INTERCONFERENCIA_B": "Interconferencia B",
    "NIVEL_1": "Nivel 1",
}

# Nivel canónico -> etapa de navegación (Primera / Segunda fase).
ETAPA_POR_FASE: Dict[str, str] = {
    "CLASIFICACION": "PRIMERA",
    "RECLASIFICACION": "PRIMERA",
    "INTERCONFERENCIA_A": "SEGUNDA",
    "INTERCONFERENCIA_B": "SEGUNDA",
    "NIVEL_1": "SEGUNDA",
}

ETAPA_LABEL: Dict[str, str] = {
    "PRIMERA": "Primera fase",
    "SEGUNDA": "Segunda fase",
}

# Orden de niveles dentro de cada etapa (para UI y payload).
NIVELES_POR_ETAPA: Dict[str, Tuple[str, ...]] = {
    "PRIMERA": ("CLASIFICACION", "RECLASIFICACION"),
    "SEGUNDA": ("INTERCONFERENCIA_A", "INTERCONFERENCIA_B", "NIVEL_1"),
}

FASE_ORDER: Tuple[str, ...] = (
    "CLASIFICACION",
    "RECLASIFICACION",
    "INTERCONFERENCIA_A",
    "INTERCONFERENCIA_B",
    "NIVEL_1",
)

# Palabras de categoría a remover de la clave de emparejamiento de equipos.
_TOKENS_CATEGORIA = {
    "INFANTILES",
    "INFANTIL",
    "CADETES",
    "CADETE",
    "JUVENILES",
    "JUVENIL",
    "MINI",
    "PREMINI",
    "MOSQUITOS",
    "MOSQUITO",
    "PROXIMO",
    "SUPERIOR",
    "MAYORES",
}

# Colores femeninos -> masculino (canónico) para unificar "BLANCA"/"BLANCO".
_COLOR_FEM_A_MASC = {
    "BLANCA": "BLANCO",
    "NEGRA": "NEGRO",
    "ROJA": "ROJO",
    "AMARILLA": "AMARILLO",
    "DORADA": "DORADO",
    "PLATEADA": "PLATEADO",
    "VIOLETA": "VIOLETA",
}

# Colores canónicos (forma masculina o invariable).
_COLORES = {
    "BLANCO",
    "NEGRO",
    "ROJO",
    "AZUL",
    "AMARILLO",
    "VERDE",
    "NARANJA",
    "CELESTE",
    "BORDO",
    "GRIS",
    "VIOLETA",
    "ROSA",
    "MARRON",
    "DORADO",
    "PLATEADO",
    "BEIGE",
    "FUCSIA",
    "LILA",
    "CYAN",
    "TURQUESA",
    "AGUA",
    "ORO",
    "PLATA",
}

# Letras que designan equipos de un mismo club (A, B, C, ...).
_LETRAS_EQUIPO = {"A", "B", "C", "D", "E", "F"}


# Alias explícitos confirmados: clave canónica calculada -> clave canónica final.
# Se usan para unificar equipos que figuran con nombres distintos entre categorías
# (mismo club, sin similitud automática suficiente). Editar cuando se confirme un caso.
_ALIAS_CLAVE: Dict[str, str] = {
    # U9/U11 "NAUTICO BUCHARDO" (NORTE 3C) == grande "NAUTICO BUCHARDO A"
    "NAUTICO BUCHARDO": "NAUTICO BUCHARDO A",
    # U9/U11 "JUVENTUD" (SUR 2A) == grande "JUVENTUD UNIDA"
    "JUVENTUD": "JUVENTUD UNIDA",
    # U9 "INSTITUCION SARMIENTO" (OESTE 3C) == grande "INSTITUCION SARMIENTO VERDE A"
    "INSTITUCION SARMIENTO": "INSTITUCION SARMIENTO A VERDE",
    # "GEVP BLANCO" (NORTE 3C) == "GEVP BLANCO A"
    "GEVP BLANCO": "GEVP A BLANCO",
}


def _canon_token(tok: str) -> str:
    return _COLOR_FEM_A_MASC.get(tok, tok)


def _es_modificador(tok: str) -> bool:
    return tok in _COLORES or tok in _LETRAS_EQUIPO


def _strip_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return nfkd.encode("ascii", "ignore").decode("ascii")


def normalizar_nombre(nombre: str) -> str:
    """Normaliza un nombre de equipo (mayúsculas, sin acentos, sin comillas, espacios)."""
    t = _strip_acentos(nombre or "")
    t = t.upper().replace('"', " ").replace("'", " ")
    return " ".join(t.split())


def norm_zona(nombre: str) -> str:
    """
    Normaliza nombre de zona GES.

    Corrige tipografías frecuentes: ``0ESTE``→``OESTE``, ``CENTTRO``→``CENTRO``,
    ``CENTRO 2 B``→``CENTRO 2B``, ``ZONA  A3``→``ZONA A3``.
    """
    t = (nombre or "").upper().strip()
    t = t.replace("0ESTE", "OESTE")
    t = t.replace("CENTTRO", "CENTRO")
    t = " ".join(t.split())
    t = re.sub(r"(\d)\s+([A-Z])", r"\1\2", t)
    return t


def clave_equipo(nombre: str) -> str:
    """
    Clave para emparejar el mismo equipo entre categorías.

    Conserva el sufijo de color/letra (AZUL, A, B, ...) porque distingue equipos de un
    mismo club, pero:
      * elimina las palabras de categoría (CADETES, INFANTILES, ...);
      * unifica el género del color (BLANCA -> BLANCO);
      * unifica el orden de los modificadores color/letra (AZUL A == A AZUL).

    Ejemplos:
        "SPORTIVO PILAR CADETES"            -> "SPORTIVO PILAR"
        "CAZA Y PESCA AZUL A"               -> "CAZA Y PESCA A AZUL"
        "FERROCARRIL OESTE BLANCA"          -> "FERROCARRIL OESTE BLANCO"
        "CIUDAD DE BUENOS AIRES A AZUL"     -> "CIUDAD DE BUENOS AIRES A AZUL"
        "CIUDAD DE BUENOS AIRES AZUL A"     -> "CIUDAD DE BUENOS AIRES A AZUL"
    """
    tokens = _tokens_canonicos(nombre)
    base_tokens = [t for t in tokens if not _es_modificador(t)]
    modificadores = sorted(t for t in tokens if _es_modificador(t))
    clave = " ".join(base_tokens + modificadores)
    return _ALIAS_CLAVE.get(clave, clave)


def _tokens_canonicos(nombre: str) -> List[str]:
    """Tokens normalizados de un nombre (sin palabras de categoría, puntos ni guiones)."""
    base = normalizar_nombre(nombre).replace("PRE MINI", "PREMINI")
    base = base.replace(".", "").replace("-", " ")  # "C.A.S.A." == "C.A.S.A", "BLANCO - A"
    return [
        _canon_token(tok)
        for tok in base.split()
        if tok not in _TOKENS_CATEGORIA
    ]


# --------------------------------------------------------------------------- #
# Estructuras de entrada
# --------------------------------------------------------------------------- #
@dataclass
class PartidoGeneral:
    """Partido de categoría que suma a la tabla (U13/U15/U17)."""

    edad: str
    fase: str  # clave canónica de nivel (CLASIFICACION, INTERCONFERENCIA_A, …)
    zona: str  # nombre de zona normalizado (ej. "NORTE 1A", "ZONA A3")
    local: str
    visitante: str
    pts_local: Optional[int]
    pts_visit: Optional[int]
    id_partido: str = ""
    fecha: str = ""  # fecha del partido (dd/mm/YYYY [HH:MM])


@dataclass
class PartidoPresentacion:
    """Partido de categoría de presentación (U9/U11)."""

    edad: str
    fase: str
    local: str
    visitante: str
    pts_local: Optional[int]
    pts_visit: Optional[int]
    id_partido: str = ""
    fecha: str = ""  # fecha del partido (dd/mm/YYYY [HH:MM])
    zona: str = ""  # zona propia de la categoría (U9/U11), para tablas por categoría
    # None = desconocido (acta no disponible); True/False = cumplió/no el mínimo.
    presenta_local: Optional[bool] = None
    presenta_visit: Optional[bool] = None
    raro: bool = False


# --------------------------------------------------------------------------- #
# Reglas de puntaje
# --------------------------------------------------------------------------- #
def es_marcador_raro(pl: Optional[int], pv: Optional[int]) -> bool:
    return (pl, pv) in {(0, 0), (20, 0), (0, 20)}


def puntos_partido_general(
    pl: Optional[int], pv: Optional[int]
) -> Tuple[int, int, str]:
    """
    Puntos (local, visitante) y tipo para un partido U13/U15/U17.

    tipo ∈ {sin_resultado, ambos_ausentes, walkover_local, walkover_visit, normal, empate}.
    """
    if pl is None or pv is None:
        return 0, 0, "sin_resultado"
    if pl == 0 and pv == 0:
        return 0, 0, "ambos_ausentes"
    if pl == 20 and pv == 0:
        return PUNTOS_GANADO, 0, "walkover_local"
    if pl == 0 and pv == 20:
        return 0, PUNTOS_GANADO, "walkover_visit"
    if pl > pv:
        return PUNTOS_GANADO, PUNTOS_PERDIDO, "normal"
    if pv > pl:
        return PUNTOS_PERDIDO, PUNTOS_GANADO, "normal"
    return PUNTOS_PERDIDO, PUNTOS_PERDIDO, "empate"


def segundos_minimos(edad: Optional[str]) -> int:
    """Umbral de minutos en cancha según la categoría (PREMINI/U9 = 8:00, resto 10:00)."""
    return MIN_SEGUNDOS_PREMINI if edad == "U9" else MIN_SEGUNDOS_REGLA


def presentacion_desde_acta(
    jugadores: List[Dict[str, object]],
    min_segundos: int = MIN_SEGUNDOS_REGLA,
) -> bool:
    """True si el equipo llega al mínimo de jugadores con >= min_segundos de juego."""
    return cuenta_jugadores_regla(jugadores, min_segundos) >= MIN_JUGADORES_REGLA


def decidir_presentacion_partido(
    pl: Optional[int],
    pv: Optional[int],
    jug_local: Optional[List[Dict[str, object]]] = None,
    jug_visit: Optional[List[Dict[str, object]]] = None,
    min_segundos: int = MIN_SEGUNDOS_REGLA,
) -> Tuple[Optional[bool], Optional[bool]]:
    """
    Decide si cada equipo suma el punto de presentación.

    - Marcador normal -> ambos se presentaron (True, True). No requiere acta.
    - Marcador raro -> usa el acta (>= 12 jugadores con >= min_segundos).
      Sin acta -> (None, None). En PREMINI/U9 el umbral es 8:00.
    """
    if not es_marcador_raro(pl, pv):
        if pl is None or pv is None:
            return None, None
        return True, True
    if jug_local is None or jug_visit is None:
        return None, None
    return (
        presentacion_desde_acta(jug_local, min_segundos),
        presentacion_desde_acta(jug_visit, min_segundos),
    )


# --------------------------------------------------------------------------- #
# Agregación por zona
# --------------------------------------------------------------------------- #
@dataclass
class FilaPosicion:
    equipo: str  # nombre para mostrar (limpio, sin categoría)
    clave: str
    nombres_ges: set = field(default_factory=set)
    pj_general: int = 0
    ganados: int = 0
    perdidos: int = 0
    walkover_favor: int = 0  # ganó por presentación rival (20-0 a favor)
    walkover_contra: int = 0  # perdió por no presentarse (0 puntos)
    pts_general: int = 0
    # Presentación U9/U11
    presentaciones: int = 0  # cantidad de puntos de presentación sumados
    pres_jugados: int = 0
    pres_no_presento: int = 0
    pres_desconocidos: int = 0
    pts_presentacion: int = 0

    @property
    def puntos(self) -> int:
        return self.pts_general + self.pts_presentacion


@dataclass
class StandingsResultado:
    # fase -> zona -> filas ordenadas
    tablas: Dict[str, Dict[str, List[FilaPosicion]]]
    # (fase, clave_equipo) de presentaciones que no se pudieron atribuir a una zona
    presentaciones_sin_zona: List[Dict[str, object]]


# Mapa global clave_equipo -> nombre de display (un solo nombre por equipo en
# todas las vistas). Se rellena con registrar_nombres_globales(...).
_NOMBRES_GLOBAL: Dict[str, str] = {}


def _elegir_nombre(nombres_ges, clave: str) -> str:
    """
    Elige el nombre de display de un equipo. Prefiere, en este orden:
      1) el que cubre más tokens de la clave canónica (no pierde color/letra ni
         palabras del nombre, p.ej. evita 'JUVENTUD' cuando la clave es
         'JUVENTUD UNIDA' o 'NAUTICO BUCHARDO' cuando es 'NAUTICO BUCHARDO A');
      2) sin palabras de categoría;
      3) el más corto / alfabético.
    """
    limpios = [normalizar_nombre(n) for n in nombres_ges if normalizar_nombre(n)]
    limpios = [n for n in limpios if n]
    if not limpios:
        return clave
    clave_tokens = set(clave.split())

    def score(nombre: str):
        cov = len(clave_tokens & set(_tokens_canonicos(nombre)))
        con_cat = 1 if (set(nombre.split()) & _TOKENS_CATEGORIA) else 0
        return (-cov, con_cat, len(nombre), nombre)

    elegido = min(limpios, key=score)
    sin_cat = " ".join(t for t in elegido.split() if t not in _TOKENS_CATEGORIA)
    return sin_cat or elegido


def registrar_nombres_globales(
    generales: List["PartidoGeneral"],
    presentaciones: List["PartidoPresentacion"],
) -> None:
    """
    Construye un único nombre de display por equipo (clave) usando los nombres de
    TODAS las categorías, para que el mismo club se muestre igual en cada vista.
    """
    nombres: Dict[str, set] = defaultdict(set)
    for pg in generales:
        nombres[clave_equipo(pg.local)].add(pg.local)
        nombres[clave_equipo(pg.visitante)].add(pg.visitante)
    for pp in presentaciones:
        nombres[clave_equipo(pp.local)].add(pp.local)
        nombres[clave_equipo(pp.visitante)].add(pp.visitante)
    _NOMBRES_GLOBAL.clear()
    for clave, ges in nombres.items():
        _NOMBRES_GLOBAL[clave] = _elegir_nombre(ges, clave)


def _nombre_para_mostrar(nombres_ges: set, clave: str) -> str:
    """
    Devuelve el nombre de display del equipo. Prioriza el mapa global (un solo
    nombre por equipo); si no está registrado, lo deriva de los nombres locales.
    """
    if clave in _NOMBRES_GLOBAL:
        return _NOMBRES_GLOBAL[clave]
    return _elegir_nombre(nombres_ges, clave)


def nombre_display(nombre: str) -> str:
    """Nombre de display unificado de un equipo a partir de un nombre crudo de GES."""
    clave = clave_equipo(nombre)
    if clave in _NOMBRES_GLOBAL:
        return _NOMBRES_GLOBAL[clave]
    return _elegir_nombre({nombre}, clave)


def construir_standings(
    generales: List[PartidoGeneral],
    presentaciones: List[PartidoPresentacion],
) -> StandingsResultado:
    """Construye las tablas por fase y zona a partir de los partidos."""
    # fase -> zona -> clave_equipo -> FilaPosicion
    tablas: Dict[str, Dict[str, Dict[str, FilaPosicion]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    # fase -> clave_equipo -> set(zonas) (para atribuir presentación)
    equipo_zonas: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))

    def _fila(fase: str, zona: str, nombre: str) -> FilaPosicion:
        clave = clave_equipo(nombre)
        zona_dict = tablas[fase][zona]
        if clave not in zona_dict:
            zona_dict[clave] = FilaPosicion(
                equipo=clave, clave=clave
            )
        fila = zona_dict[clave]
        fila.nombres_ges.add(nombre)
        equipo_zonas[fase][clave].add(zona)
        return fila

    # 1) Partidos generales (U13/U15/U17)
    for pg in generales:
        pl_pts, pv_pts, tipo = puntos_partido_general(pg.pts_local, pg.pts_visit)
        if tipo == "sin_resultado":
            continue
        fl = _fila(pg.fase, pg.zona, pg.local)
        fv = _fila(pg.fase, pg.zona, pg.visitante)

        fl.pj_general += 1
        fv.pj_general += 1
        fl.pts_general += pl_pts
        fv.pts_general += pv_pts

        if tipo == "normal":
            if pl_pts > pv_pts:
                fl.ganados += 1
                fv.perdidos += 1
            else:
                fv.ganados += 1
                fl.perdidos += 1
        elif tipo == "walkover_local":
            fl.ganados += 1
            fl.walkover_favor += 1
            fv.walkover_contra += 1
        elif tipo == "walkover_visit":
            fv.ganados += 1
            fv.walkover_favor += 1
            fl.walkover_contra += 1
        elif tipo == "ambos_ausentes":
            fl.walkover_contra += 1
            fv.walkover_contra += 1
        elif tipo == "empate":
            fl.perdidos += 1
            fv.perdidos += 1

    # 2) Resolver nombres para mostrar
    for fase, zonas in tablas.items():
        for zona, filas in zonas.items():
            for clave, fila in filas.items():
                fila.equipo = _nombre_para_mostrar(fila.nombres_ges, clave)

    # 3) Presentación U9/U11 -> atribuir por clave de equipo a sus zonas en esa fase.
    sin_zona: List[Dict[str, object]] = []

    def _aplicar_pres(fila: FilaPosicion, presento: Optional[bool]) -> None:
        fila.pres_jugados += 1
        if presento is True:
            fila.presentaciones += 1
            fila.pts_presentacion += PUNTO_PRESENTACION
        elif presento is False:
            fila.pres_no_presento += 1
        else:
            fila.pres_desconocidos += 1

    for pp in presentaciones:
        presenta_local, presenta_visit = pp.presenta_local, pp.presenta_visit
        if presenta_local is None and presenta_visit is None:
            # No se pre-decidió: derivar del marcador (normal -> ambos presentan).
            presenta_local, presenta_visit = decidir_presentacion_partido(
                pp.pts_local, pp.pts_visit
            )
        for nombre, presento in (
            (pp.local, presenta_local),
            (pp.visitante, presenta_visit),
        ):
            clave = clave_equipo(nombre)
            zonas = equipo_zonas.get(pp.fase, {}).get(clave)
            if not zonas:
                sin_zona.append(
                    {
                        "fase": pp.fase,
                        "edad": pp.edad,
                        "equipo": nombre,
                        "clave": clave,
                        "presento": presento,
                        "id_partido": pp.id_partido,
                    }
                )
                continue
            for zona in zonas:
                fila = tablas[pp.fase][zona].get(clave)
                if fila is not None:
                    _aplicar_pres(fila, presento)

    # 4) Ordenar
    tablas_ordenadas: Dict[str, Dict[str, List[FilaPosicion]]] = {}
    for fase, zonas in tablas.items():
        tablas_ordenadas[fase] = {}
        for zona, filas in zonas.items():
            tablas_ordenadas[fase][zona] = ordenar_tabla(list(filas.values()))

    return StandingsResultado(
        tablas=tablas_ordenadas, presentaciones_sin_zona=sin_zona
    )


def ordenar_tabla(filas: List[FilaPosicion]) -> List[FilaPosicion]:
    """Ordena por puntos totales desc, luego puntos generales, luego ganados."""
    return sorted(
        filas,
        key=lambda f: (-f.puntos, -f.pts_general, -f.ganados, f.equipo),
    )


# --------------------------------------------------------------------------- #
# Tablas por categoría (U13/U15/U17): standings propios de cada categoría
# --------------------------------------------------------------------------- #
@dataclass
class FilaCategoria:
    equipo: str
    clave: str
    nombres_ges: set = field(default_factory=set)
    pj: int = 0
    ganados: int = 0
    perdidos: int = 0
    walkover_favor: int = 0
    walkover_contra: int = 0
    puntos: int = 0


def construir_tablas_categoria(
    generales: List[PartidoGeneral],
) -> Dict[str, Dict[str, Dict[str, List[FilaCategoria]]]]:
    """edad -> fase -> zona -> filas ordenadas (standings 2/1 por categoría)."""
    acc: Dict[str, Dict[str, Dict[str, Dict[str, FilaCategoria]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict))
    )

    def _fila(edad: str, fase: str, zona: str, nombre: str) -> FilaCategoria:
        clave = clave_equipo(nombre)
        zona_dict = acc[edad][fase][zona]
        if clave not in zona_dict:
            zona_dict[clave] = FilaCategoria(equipo=clave, clave=clave)
        fila = zona_dict[clave]
        fila.nombres_ges.add(nombre)
        return fila

    for pg in generales:
        pl_pts, pv_pts, tipo = puntos_partido_general(pg.pts_local, pg.pts_visit)
        if tipo == "sin_resultado":
            continue
        fl = _fila(pg.edad, pg.fase, pg.zona, pg.local)
        fv = _fila(pg.edad, pg.fase, pg.zona, pg.visitante)
        fl.pj += 1
        fv.pj += 1
        fl.puntos += pl_pts
        fv.puntos += pv_pts
        if tipo == "normal":
            if pl_pts > pv_pts:
                fl.ganados += 1
                fv.perdidos += 1
            else:
                fv.ganados += 1
                fl.perdidos += 1
        elif tipo == "walkover_local":
            fl.ganados += 1
            fl.walkover_favor += 1
            fv.walkover_contra += 1
        elif tipo == "walkover_visit":
            fv.ganados += 1
            fv.walkover_favor += 1
            fl.walkover_contra += 1
        elif tipo == "ambos_ausentes":
            fl.walkover_contra += 1
            fv.walkover_contra += 1
        elif tipo == "empate":
            fl.perdidos += 1
            fv.perdidos += 1

    out: Dict[str, Dict[str, Dict[str, List[FilaCategoria]]]] = {}
    for edad, fases in acc.items():
        out[edad] = {}
        for fase, zonas in fases.items():
            out[edad][fase] = {}
            for zona, filas in zonas.items():
                for clave, fila in filas.items():
                    fila.equipo = _nombre_para_mostrar(fila.nombres_ges, clave)
                out[edad][fase][zona] = sorted(
                    filas.values(),
                    key=lambda f: (-f.puntos, -f.ganados, f.equipo),
                )
    return out


# --------------------------------------------------------------------------- #
# Tablas por categoría de presentación (U9/U11): puntos de presentación por zona
# --------------------------------------------------------------------------- #
@dataclass
class FilaPresentacion:
    equipo: str
    clave: str
    nombres_ges: set = field(default_factory=set)
    pj: int = 0
    presentaciones: int = 0
    no_presento: int = 0
    desconocidos: int = 0
    puntos: int = 0


def construir_tablas_presentacion(
    presentaciones: List[PartidoPresentacion],
) -> Dict[str, Dict[str, Dict[str, List[FilaPresentacion]]]]:
    """edad -> fase -> zona -> filas ordenadas (puntos de presentación por categoría)."""
    acc: Dict[str, Dict[str, Dict[str, Dict[str, FilaPresentacion]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict))
    )

    def _fila(edad: str, fase: str, zona: str, nombre: str) -> FilaPresentacion:
        clave = clave_equipo(nombre)
        zona_dict = acc[edad][fase][zona]
        if clave not in zona_dict:
            zona_dict[clave] = FilaPresentacion(equipo=clave, clave=clave)
        fila = zona_dict[clave]
        fila.nombres_ges.add(nombre)
        return fila

    for pp in presentaciones:
        presenta_local, presenta_visit = pp.presenta_local, pp.presenta_visit
        if presenta_local is None and presenta_visit is None:
            presenta_local, presenta_visit = decidir_presentacion_partido(
                pp.pts_local, pp.pts_visit
            )
        zona = pp.zona or "(sin zona)"
        for nombre, presento in (
            (pp.local, presenta_local),
            (pp.visitante, presenta_visit),
        ):
            fila = _fila(pp.edad, pp.fase, zona, nombre)
            fila.pj += 1
            if presento is True:
                fila.presentaciones += 1
                fila.puntos += PUNTO_PRESENTACION
            elif presento is False:
                fila.no_presento += 1
            else:
                fila.desconocidos += 1

    out: Dict[str, Dict[str, Dict[str, List[FilaPresentacion]]]] = {}
    for edad, fases in acc.items():
        out[edad] = {}
        for fase, zonas in fases.items():
            out[edad][fase] = {}
            for zona, filas in zonas.items():
                for clave, fila in filas.items():
                    fila.equipo = _nombre_para_mostrar(fila.nombres_ges, clave)
                out[edad][fase][zona] = sorted(
                    filas.values(),
                    key=lambda f: (-f.puntos, -f.presentaciones, f.equipo),
                )
    return out


# --------------------------------------------------------------------------- #
# Tabla de MINI (U11): puntos por MARCADOR DE FIXTURE (penalizador) + presentación
# --------------------------------------------------------------------------- #
# En MINI el marcador del fixture es el resultado OFICIAL (penalizador):
#   * 20-0  -> penalizado el VISITANTE (local gana).
#   * 0-20  -> penalizado el LOCAL (visitante gana).
#   * 0-0   -> penalizados AMBOS.
#   * cualquier otro marcador (ej. 48-46) -> partido normal, sin penalización.
# Que el equipo penalizado haya PRESENTADO o no (regla de plantilla MINI:
# >= 12 jugadores con >= 10:00, evaluada sobre el acta) distingue el motivo:
#   * penalizado y NO presentó -> NP -> 0 puntos.
#   * penalizado y SÍ presentó -> regla de cambios Q3 u otra -> 1 punto.
# El ganado/perdido del boxscore NO asigna puntos: queda solo como columna
# informativa "Box".


@dataclass
class FilaResultadoMini:
    """
    Fila de la tabla de MINI/U11.

    Los puntos salen del *marcador de fixture* (penalizador) más la
    presentación (regla de plantilla), NO del ganador del boxscore:
      * ``puntos`` = 2 por partido ganado, 1 por perdido / regla Q3, 0 por NP.
      * ``ganados`` = partidos con 2 pts; ``perdidos`` = con 1 pt; ``np`` = con 0.
      * ``presentaciones`` = puntos de presentación (1 por partido en que el
        equipo presentó plantilla completa); alimenta la tabla general.
      * ``box_ganados``/``box_perdidos`` = resultado real del acta, SOLO
        informativo (no influye en los puntos).
    """

    equipo: str
    clave: str
    nombres_ges: set = field(default_factory=set)
    pj: int = 0
    puntos: int = 0
    ganados: int = 0  # partidos con 2 pts (ganó por marcador de fixture)
    perdidos: int = 0  # partidos con 1 pt (perdió o regla de cambios Q3)
    np: int = 0  # partidos con 0 pts (penalizado y no presentó)
    presentaciones: int = 0  # puntos de presentación (plantilla completa)
    # Informativo: resultado según el acta (puntos reales del boxscore).
    box_ganados: int = 0
    box_perdidos: int = 0
    box_sin_dato: int = 0


def puntos_partido_mini(
    pl: Optional[int],
    pv: Optional[int],
    presenta_local: Optional[bool],
    presenta_visit: Optional[bool],
) -> Optional[Tuple[int, int, bool, bool]]:
    """
    Puntos de MINI por equipo a partir del marcador de fixture + presentación.

    Devuelve ``(pts_local, pts_visit, pres_local, pres_visit)`` donde ``pres_*``
    indica si el equipo suma punto de presentación. ``None`` si no hay marcador.

    Reglas (penalizador):
      * marcador real (no raro): ganador 2, perdedor 1, empate 1/1; ambos
        presentaron.
      * 20-0: local 2 y presenta; visitante 1 si presentó (Q3) o 0 si NP.
      * 0-20: espejo del anterior.
      * 0-0: cada equipo 1 si presentó (Q3) o 0 si NP.
    """
    if pl is None or pv is None:
        return None
    if not es_marcador_raro(pl, pv):
        if pl > pv:
            return (PUNTOS_GANADO, PUNTOS_PERDIDO, True, True)
        if pv > pl:
            return (PUNTOS_PERDIDO, PUNTOS_GANADO, True, True)
        return (PUNTOS_PERDIDO, PUNTOS_PERDIDO, True, True)  # empate (rarísimo)
    pres_l = presenta_local is True
    pres_v = presenta_visit is True
    if pl == 20 and pv == 0:
        return (PUNTOS_GANADO, PUNTOS_PERDIDO if pres_v else 0, True, pres_v)
    if pl == 0 and pv == 20:
        return (PUNTOS_PERDIDO if pres_l else 0, PUNTOS_GANADO, pres_l, True)
    # 0-0: ambos penalizados.
    return (
        PUNTOS_PERDIDO if pres_l else 0,
        PUNTOS_PERDIDO if pres_v else 0,
        pres_l,
        pres_v,
    )


def ordenar_tabla_resultado_mini(
    filas: List[FilaResultadoMini],
) -> List[FilaResultadoMini]:
    """
    Ordena la tabla de MINI por puntos.

    Criterio (de mayor a menor prioridad):
      1) más puntos (modelo de fixture + presentación),
      2) más puntos de presentación,
      3) más ganados,
      4) nombre del equipo (desempate estable/alfabético).
    """
    return sorted(
        filas,
        key=lambda f: (-f.puntos, -f.presentaciones, -f.ganados, f.equipo),
    )


def construir_tabla_resultado_mini(
    presentaciones: List[PartidoPresentacion],
    boxscores: Optional[Dict[str, Dict[str, object]]] = None,
    *,
    edad: str = "U11",
) -> Dict[str, Dict[str, List[FilaResultadoMini]]]:
    """
    Construye la tabla de MINI (U11) por fase -> zona, ordenada por puntos.

    Los puntos salen del marcador de fixture (penalizador) y de la presentación
    (ver ``puntos_partido_mini``). Para los marcadores raros la presentación se
    toma de ``presenta_local``/``presenta_visit`` del partido (recalculados desde
    el acta con el umbral por edad); en marcadores reales, ambos presentaron. La
    columna ``Box`` (ganador del acta) es solo informativa.
    """
    boxscores = boxscores or {}
    acc: Dict[str, Dict[str, Dict[str, FilaResultadoMini]]] = defaultdict(
        lambda: defaultdict(dict)
    )

    def _fila(fase: str, zona: str, nombre: str) -> FilaResultadoMini:
        clave = clave_equipo(nombre)
        zona_dict = acc[fase][zona]
        if clave not in zona_dict:
            zona_dict[clave] = FilaResultadoMini(equipo=clave, clave=clave)
        fila = zona_dict[clave]
        fila.nombres_ges.add(nombre)
        return fila

    def _aplicar(fila: FilaResultadoMini, pts: int, presento: bool) -> None:
        fila.puntos += pts
        if pts == PUNTOS_GANADO:
            fila.ganados += 1
        elif pts == PUNTOS_PERDIDO:
            fila.perdidos += 1
        else:
            fila.np += 1
        if presento:
            fila.presentaciones += 1

    for pp in presentaciones:
        if pp.edad != edad:
            continue
        # Presentación: en raros se usa el acta (ya recalculada); en marcador
        # real ambos presentaron.
        if es_marcador_raro(pp.pts_local, pp.pts_visit):
            pres_l, pres_v = pp.presenta_local, pp.presenta_visit
        else:
            pres_l, pres_v = True, True

        res = puntos_partido_mini(pp.pts_local, pp.pts_visit, pres_l, pres_v)
        if res is None:
            continue  # sin marcador: no contabiliza

        zona = pp.zona or "(sin zona)"
        fl = _fila(pp.fase, zona, pp.local)
        fv = _fila(pp.fase, zona, pp.visitante)
        fl.pj += 1
        fv.pj += 1

        pts_l, pts_v, p_l, p_v = res
        _aplicar(fl, pts_l, p_l)
        _aplicar(fv, pts_v, p_v)

        # Columna informativa Box: ganador según puntos reales del acta.
        box = boxscores.get(pp.id_partido)
        equipos = box.get("equipos") if (box and box.get("ok")) else None
        if equipos and len(equipos) >= 2:
            ganador = ganador_boxscore(
                equipos[0].get("pts"), equipos[1].get("pts")
            )
            if ganador == "local":
                fl.box_ganados += 1
                fv.box_perdidos += 1
            elif ganador == "visitante":
                fv.box_ganados += 1
                fl.box_perdidos += 1
            else:
                fl.box_sin_dato += 1
                fv.box_sin_dato += 1
        else:
            fl.box_sin_dato += 1
            fv.box_sin_dato += 1

    out: Dict[str, Dict[str, List[FilaResultadoMini]]] = {}
    for fase, zonas in acc.items():
        out[fase] = {}
        for zona, filas in zonas.items():
            for clave, fila in filas.items():
                fila.equipo = _nombre_para_mostrar(fila.nombres_ges, clave)
            out[fase][zona] = ordenar_tabla_resultado_mini(list(filas.values()))
    return out
