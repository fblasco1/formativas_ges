---
name: build-ranking-engine
description: Implementa o modifica el motor FeBAMBA tipo FIBA con factor S multiplicativo (fase × ronda × nivel), config central y clase FeBAMBARanking en analisis/ranking/. Usar al tocar GRP, pesos de etapa o agregación multi-categoría.
---

# Motor de ranking (implementación)

## Layout objetivo del paquete

```
analisis/ranking_config.py      # B, W, O, A, M, DISCOUNT, INITIAL, REGION, CATEGORY_WEIGHT
analisis/ranking/
  __init__.py                   # export público p.ej. FeBAMBARanking
  stage_weights.py              # PHASE_WEIGHT, ROUND_WEIGHT, LEVEL_WEIGHT → S = producto
  febamba_ranking.py            # clase FeBAMBARanking
  ranking_general.py            # agregación ponderada por categoría canónica
  data_loader.py / ranking_runner.py  # según necesidad
```

**No** usar `analisis/ranking.py` como archivo: choca con el paquete `analisis/ranking/`.

## Factor S

- **S = w_fase(fase) × w_ronda(ronda) × w_nivel(nivel)** usando texto tal cual viene del pipeline (normalización de strings en los pesos).
- **No** reintroducir `tournament_stage` en normalize solo para el ranking si existe descomposición en fase/ronda/nivel; el motor puede calcular S en `process_match`.
- Historial útil por partido: `factor_etapa`, `fase`, `ronda`, `nivel`.

## Exclusiones explícitas del chat de diseño

- Mapa único tipo `STAGE_KEYWORDS` → un solo código de etapa sustituyendo todo lo demás.
- **`MIXTO_FACTOR` 0.5** aplicado en el motor para duplicar géneros (removido en diseño nuevo; MIXTO se modela vía `genero` y conjuntos de ranking, no penalización arbitraria salvo regla de negocio explícita).

## Constantes

- Un solo módulo de constantes numéricas (`ranking_config.py`); no duplicar magic numbers en notebooks ni dashboard.

## Legacy

- Código en `analisis/Ranking/` (mayúscula) es herencia: al portar, migrar a `analisis/ranking/` (minúsculas, paquete) y tests en `tests/test_ranking.py`.
