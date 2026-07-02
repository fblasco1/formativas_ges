# -*- coding: utf-8 -*-
"""Formato compacto y compresión de datos para el buscador (menor RAM y transferencia)."""

from __future__ import annotations

import base64
import gzip
import json
from typing import Dict, List, Tuple

from analysis.buscador_metrics import PERFILES, PERFIL_INSUFICIENTE

# Orden fijo de columnas por fila (índice = posición en el array).
ROW_SCHEMA: Tuple[str, ...] = (
    "pid",
    "nombre_completo",
    "equipo",
    "cat",
    "edad",
    "pj",
    "min_p",
    "pts_p",
    "pct_pts",
    "ts_pct",
    "pct_ts",
    "efg_pct",
    "val_min",
    "pct_val",
    "reb_p",
    "ast_p",
    "ast_per",
    "per_p",
    "rob_p",
    "tap_p",
    "val_p",
    "t2a_p",
    "t2i_p",
    "t2_pct",
    "t3a_p",
    "t3i_p",
    "t3_pct",
    "tla_p",
    "tli_p",
    "tl_pct",
    "pf",  # índice de perfil
    "purl",
)

PERFIL_NAMES: Tuple[str, ...] = tuple(PERFILES) + (PERFIL_INSUFICIENTE,)
_PERFIL_IDX: Dict[str, int] = {n: i for i, n in enumerate(PERFIL_NAMES)}


def _cell(value: object) -> object:
    if value is None or value == "":
        return ""
    return value


def row_from_jugador(j: Dict[str, object]) -> List[object]:
    perfil = str(j.get("perfil") or PERFIL_INSUFICIENTE)
    return [
        _cell(j.get("pid")),
        _cell(j.get("nombre_completo")),
        _cell(j.get("equipo")),
        _cell(j.get("cat")),
        _cell(j.get("edad")),
        _cell(j.get("pj")),
        _cell(j.get("min_p")),
        _cell(j.get("pts_p")),
        _cell(j.get("pct_pts")),
        _cell(j.get("ts_pct")),
        _cell(j.get("pct_ts")),
        _cell(j.get("efg_pct")),
        _cell(j.get("val_min")),
        _cell(j.get("pct_val")),
        _cell(j.get("reb_p")),
        _cell(j.get("ast_p")),
        _cell(j.get("ast_per")),
        _cell(j.get("per_p")),
        _cell(j.get("rob_p")),
        _cell(j.get("tap_p")),
        _cell(j.get("val_p")),
        _cell(j.get("t2a_p")),
        _cell(j.get("t2i_p")),
        _cell(j.get("t2_pct")),
        _cell(j.get("t3a_p")),
        _cell(j.get("t3i_p")),
        _cell(j.get("t3_pct")),
        _cell(j.get("tla_p")),
        _cell(j.get("tli_p")),
        _cell(j.get("tl_pct")),
        _PERFIL_IDX.get(perfil, len(PERFIL_NAMES) - 1),
        _cell(j.get("purl")),
    ]


def pack_jugadores(jugadores: List[Dict[str, object]]) -> Dict[str, object]:
    return {
        "v": 1,
        "s": list(ROW_SCHEMA),
        "p": list(PERFIL_NAMES),
        "d": [row_from_jugador(j) for j in jugadores],
    }


def pack_gzip_bytes(jugadores: List[Dict[str, object]]) -> bytes:
    payload = json.dumps(
        pack_jugadores(jugadores), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return gzip.compress(payload, compresslevel=9)


def cifrar_bytes(
    data: bytes,
    password: str,
    *,
    iteraciones: int,
    dklen: int,
) -> Dict[str, object]:
    """Cifra bytes con AES-256-GCM. Retorna metadatos (sin el ciphertext embebido)."""
    import hashlib
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iteraciones, dklen=dklen
    )
    ct = AESGCM(key).encrypt(iv, data, None)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ct": ct,
        "iter": iteraciones,
        "dklen": dklen,
    }
