# Renivelación por Tira — documentación técnica

## Objetivo

Calcular el ranking oficial de **Tiras** (ej. `PEDRO ECHAGUE A`, `OBRAS B`) para la renivelación FeBAMBA 2023–2026, con pipeline **incremental**: histórico congelado (2023–2025) + delta `partidos_2026.csv`.

## Categorías y mapeo U → columnas del ranking

Las **columnas** del ranking son los nombres FeBAMBA actuales (buckets U):

| Bucket (columna) | Equivalencia U | Notas |
|------------------|----------------|-------|
| `INFANTILES` | U13 | Antes la etiqueta GES era **PREINFANTILES** (ya no existe). |
| `CADETES` | U15 | En CSV 2023–24 la etiqueta era **INFANTILES**. |
| `JUVENILES` | U17 | En CSV 2023–24 la etiqueta era **CADETES**. |
| `LIGA PROXIMO` | U19 / U21 | En CSV 2023–24 la etiqueta era **JUVENILES**. |

### PREINFANTILES → INFANTILES (importante)

**PREINFANTILES dejó de usarse en GES.** No es una quinta categoría del ranking.

- En datos **ya scrapeados 2023–2024**, el CSV puede seguir diciendo `PREINFANTILES` en la columna `categoria`. El motor **no renombra** esa columna (porque en esos años `INFANTILES` en el CSV significa otra generación, U15).
- En el pipeline de renivelación, `bucket_renivelacion()` **parsea** cualquier fila con `PREINFANTILES` al bucket **`INFANTILES`** (U13), igual que `INFANTILES MASCULINO` en años nuevos.
- Scraper nuevo (`mapeos/categorias_map.json`): U13 → `INFANTILES MASCULINO`, no `PREINFANTILES`.

Implementación: `analisis/renivelacion_tiras/categorias.py` → `bucket_renivelacion(categoria, anio)`.

### Cómo se lee cada fila del CSV

**2023-2024** (sin `MASCULINO` / sin `LIGA PROXIMO`) — etiquetas **históricas** en `categoria`:

| `categoria` en CSV (histórico) | Bucket / columna donde suma |
|--------------------------------|-----------------------------|
| PREINFANTILES *(discontinuada)* | Pts_Aportados_INFANTILES |
| INFANTILES | Pts_Aportados_CADETES |
| CADETES | Pts_Aportados_JUVENILES |
| JUVENILES | Pts_Aportados_LIGA_PROXIMO |

**2025-2026** (`* MASCULINO`, `LIGA PROXIMO`) — etiquetas **actuales** en GES:

| `categoria` en CSV | Bucket / columna donde suma |
|--------------------|-----------------------------|
| INFANTILES MASCULINO | Pts_Aportados_INFANTILES |
| CADETES MASCULINO | Pts_Aportados_CADETES |
| JUVENILES MASCULINO | Pts_Aportados_JUVENILES |
| LIGA PROXIMO MASCULINO | Pts_Aportados_LIGA_PROXIMO |

Si en un scrape nuevo apareciera otra vez `PREINFANTILES`, se trata igual que **INFANTILES MASCULINO** (bucket `INFANTILES`).

`MINI` / `PREMINI`: no suman puntos; **sí** cuentan forfaits 0-20 (−1000).

## Comandos

```powershell
python -m analisis.renivelacion_tiras --congelar-historico
python -m analisis.renivelacion_tiras --actualizar-2026
python -m analisis.renivelacion_tiras

streamlit run visualizaciones/renivelacion_tiras_streamlit.py
```

Tras cambiar reglas de categoría, **regenerá el caché** (`--congelar-historico` de nuevo).

## Salidas

| Archivo | Contenido |
|---------|-----------|
| `Data/procesada/renivelacion/acumulado_tiras_2023_2025.csv` | Acumulado congelado |
| `Data/procesada/Ranking_Tiras_Actualizado_2026.csv` | Ranking final |
| `Data/procesada/Ranking_Tiras_Baseline_2026.csv` | Baseline GES |

Columnas del ranking final:

`Tira`, `Pts_Aportados_INFANTILES`, `Pts_Aportados_CADETES`, `Pts_Aportados_JUVENILES`, `Pts_Aportados_LIGA_PROXIMO`, `Cantidad_Forfaits`, `Total_Penalizaciones`, `Total_Renivelacion`, `Posicion`

---

## 1. Cómo se suman categorías y se descuentan forfaits (Pandas)

### Paso A — Puntos solo en las 4 categorías competitivas

`es_competitivo == True` cuando `bucket_renivelacion` ∈ {INFANTILES, CADETES, JUVENILES, LIGA PROXIMO}.

### Paso B — Agregación sin cruzar tiras

1. Filtra filas competitivas.
2. Agrupa por `(club_tira_local, bucket_renivelacion)` y por visitante.
3. Concatena y agrupa por `(Tira, bucket_renivelacion)`.

### Paso C — Pivot

`pivot_table(..., columns="bucket_renivelacion")` → `Pts_Aportados_INFANTILES`, etc.

### Paso D — Forfaits (todas las categorías del fixture)

`contar_forfaits_por_tira` recorre **todas** las filas (MINI, PREMINI, histórico `PREINFANTILES`, competitivas, etc.): cada partido 0-20 en contra de la tira suma 1 → **−1000** al total.

### Paso E — Ecuación final

```text
Total_Renivelacion = INFANTILES + CADETES + JUVENILES + LIGA_PROXIMO − (forfaits × 1000)
```

---

## 2. Tira A vs Tira B

`tira_desde_equipo()` conserva la letra (A/B). Las agregaciones usan `club_tira_*`; **no se mezclan** puntos ni forfaits entre tiras del mismo club.

---

## 3. Algoritmos

**Baseline:** `peso_fase × peso_ronda × peso_año × peso_nivel × (BP + ORP)` por las 4 categorías.

**Renivelación:** `peso_año × peso_etapa × peso_nivel × (BP + ORP)` + penalización forfait global.

---

## 4. Estructura del código

```
analisis/renivelacion_tiras/
  categorias.py   # bucket_renivelacion: PREINFANTILES → INFANTILES, etc.
  ingesta.py
  agregacion.py
  ...
```
