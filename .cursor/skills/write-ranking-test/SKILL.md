---
name: write-ranking-test
description: Escribe o amplía tests pytest para el motor FeBAMBARanking (orden cronológico, forfeit, factor S, descuento estacional). Usar al cambiar fórmula de ranking o analisis/ranking/*.
---

# Tests del ranking FeBAMBA

## Ubicación

- `tests/test_ranking.py` (crear si no existe) junto al resto de `tests/`

## Contrato a verificar (según rules 03)

1. Partidos con `is_forfeit=True` no alteran ratings.
2. Procesamiento en orden por `anio` y fecha cuando exista.
3. Factor **S** como producto de pesos de fase, ronda y nivel (no un único mapa `STAGE_*` sustituto sin descomposición).
4. **`TL` (rating del perdedor) es pre-partido** antes de actualizar.
5. `apply_seasonal_discount` o equivalente respeta `DISCOUNT_FACTOR` desde config.

## Estilo

- `pytest`, fixtures con DataFrames mínimos; sin red ni scraping.
- Nombres de test descriptivos en inglés o español consistente con `tests/test_parsers.py`.

## Legacy

Si el paquete `analisis/ranking/` aún no está en el árbol, documentar skip o marcar como pendiente hasta existir `FeBAMBARanking` importable.
