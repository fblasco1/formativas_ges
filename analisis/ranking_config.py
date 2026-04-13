"""
Constantes numéricas del motor FeBAMBA (adaptación FIBA). Un solo lugar para B, W, O, A, M, descuento, etc.
"""

from __future__ import annotations

# --- Fórmula: Perdedor G = B × R × S | Ganador GW = G × W × O × A × M ---

BASE_FACTOR: float = 1.0
"""Factor B en G = B × R × S."""

WINNING_FACTOR: float = 1.0
"""Factor W en GW = G × W × O × A × M."""

# O = 1 + O_K * (TL - INITIAL_RATING) / max(INITIAL_RATING, eps), acotado
O_COEFF: float = 0.35
O_MIN: float = 0.75
O_MAX: float = 1.35

# Localía: ganador local vs visitante (cancha neutral = 1.0)
A_HOME_WIN: float = 1.02
A_AWAY_WIN: float = 1.06

# R(margen): mezcla entre mínimo y máximo según diferencia de puntos
R_MIN: float = 0.82
R_MAX: float = 1.18
R_MARGIN_REF: float = 20.0

# M(margen): solo para el ganador; techo para no sobre-premiar goleadas
M_MIN: float = 1.0
M_MAX: float = 1.25
M_MARGIN_REF: float = 30.0

INITIAL_RATING: float = 1000.0
DISCOUNT_FACTOR: float = 0.985
"""Multiplicador aplicado a todos los ratings al cambiar de temporada lógica (inicio de año nuevo)."""

REGION_FACTOR: dict[str, float] = {"default": 1.0}
"""Reservado para futuras expansiones por región/zona."""

# Ponderación por categoría canónica (age_group). Claves en MAYÚSCULAS.
AGE_GROUP_WEIGHT: dict[str, float] = {
    "PREMINI": 0.6,
    "MINI": 0.65,
    "PREINFANTILES": 0.75,
    "INFANTILES": 0.85,
    "CADETES": 0.95,
    "JUVENILES": 1.0,
    "MOSQUITOS": 0.7,
    "LIGA PROXIMO MASCULINO": 1.05,
    "DEFAULT": 1.0,
}
