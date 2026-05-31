# Visión del proyecto — analítica desde GES

Repositorio **`formativas_ges`** como base para distintas **patas de análisis** alimentadas por [GES Deportiva](https://competicionescabb.gesdeportiva.es/), cada una con su rama, datos y productos.

## Competencias / divisiones previstas

| Pata | Competencia GES (referencia) | Estado en repo |
|------|------------------------------|----------------|
| **Formativas** | Torneos Formativas U13–U21 (FeBAMBA) | **Activo** — rama `Ranking_V2` |
| **Liga Nacional** | Liga Nacional | Planificado |
| **Liga Argentina** | Ex-TNA | Planificado |
| **Liga Federal** | Liga Federal | Planificado (artefactos en rama `estadisticas`) |
| **Liga Femenina** | Liga Femenina | Planificado |

Cada pata puede compartir:

- Scraper GES (`scraper/`, `parsers/`)
- Utilidades (`utils/`)
- Convenciones de mapeo (`mapeos/` donde aplique)

pero debe tener **datos y pipelines separados** para no mezclar torneos ni reglas de negocio distintas.

## Estrategia de ramas Git

```text
main / master          → estable compartido (utils, scraper base)
Ranking_V2             → Renivelación formativas 2023–2026 (esta entrega)
estadisticas           → Estadísticas entrenadores, jugadores, box score,
                         fixtures Liga Federal, argentina.basketball, etc.
feature/*              → Experimentos por competencia o por producto
```

### Rama `Ranking_V2` (ahora)

- Ranking **renivelación por tira** (A/B).
- Partidos formativas, regiones FeBAMBA, Streamlit principal.
- Actualización diaria temporada activa (2026).
- Ver `docs/ALCANCE_RAMA.md` y `docs/RENIVELACION_TIRAS.md`.

### Rama `estadisticas` (avance paralelo)

Ahí se desarrollan las **features de estadística** para distintos proyectos de analítica:

- Entrenadores (actas, consolidados por competencia).
- Jugadores / box score / play-by-play cuando la fuente lo permita.
- Cruces con **Liga Federal**, **Liga Argentina**, etc.
- No mezclar esos CSV ni notebooks en commits de `Ranking_V2`.

Flujo recomendado: trabajar en `estadisticas`, merge a `main` cuando una feature esté madura; `Ranking_V2` hace merge/rebase de `main` solo para utilidades compartidas.

## Principios de diseño

1. **Un torneo = un namespace de datos**  
   Ej.: `Data/formativas/`, `Data/liga_federal/` (futuro), no un único CSV mezclado.

2. **Un producto = un entrypoint claro**  
   Ej.: `streamlit_app.py` (renivelación) vs apps de estadísticas en su rama.

3. **GES como fuente; fuentes externas explícitas**  
   Si se usa argentina.basketball u otra API, documentar en la rama `estadisticas`, no asumir el mismo pipeline que formativas.

4. **Ramas acotadas**  
   Lo que se ignora en `.gitignore` de `Ranking_V2` (entrenadores, fixtures) es para **no contaminar esta rama**; en `estadisticas` esos archivos sí viven.

## Roadmap sugerido (alto nivel)

| Fase | Rama | Entregable |
|------|------|------------|
| 1 | `Ranking_V2` | Renivelación formativas + deploy Streamlit |
| 2 | `estadisticas` | Pipeline entrenadores + jugadores formativas |
| 3 | `feature/liga-federal` | Ingesta GES + estadísticas Liga Federal |
| 4 | `feature/liga-argentina` | Ex-TNA desde GES |
| 5 | … | Liga Nacional, Liga Femenina |

## Documentación por pata

| Documento | Contenido |
|-----------|-----------|
| `docs/VISION_PROYECTO.md` | Este archivo |
| `docs/ALCANCE_RAMA.md` | Solo `Ranking_V2` |
| `docs/RENIVELACION_TIRAS.md` | Motor renivelación |
| `docs/DATA_LAYOUT.md` | CSV formativas en uso |
| `docs/ACTUALIZACION_DIARIA.md` | Job diario 2026 |
| `docs/DEPLOY_STREAMLIT.md` | Streamlit Cloud |

En la rama `estadisticas` conviene añadir `docs/ESTADISTICAS.md` cuando se estabilice el alcance.
