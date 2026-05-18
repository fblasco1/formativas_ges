# Arquitectura — FeBAMBA Stats Tracker

Documento técnico de la arquitectura del proyecto de analítica para categorías formativas FeBAMBA (U13–U21). Define el módulo de ingesta, el modelo de datos, la lógica de análisis y las restricciones técnicas.

---

## 1. Módulo de Ingesta

### 1.1 Fuentes de datos

- **Portal público GES (competencia):** `competicionescabb.gesdeportiva.es` — categorías (`DDLCategorias`), fases y grupos (combos WebForms). Sin JavaScript en cliente: GET + POST simulado.
- **Temporada ≥ 2026 — calendario y actas:** `argentina.basketball` — `GET /liga-federal/fixture?handler=CargarFixture&compCatId=…&fechaIni=…&fechaFin=…` (HTML `table.tabla-calendarios`), boxscore `GET /liga-federal/partido/estadisticas/{token}==?key=`, play-by-play `…/en-vivo/…`. El flujo nuevo **no** usa `widgetscab.gesdeportiva.es` para listado ni acta.
- **Temporada ≤ 2025 (histórico):** listado y boxscore siguen pudiendo obtenerse vía widget GES (`widgetscab.gesdeportiva.es`) al ejecutar `main.py` con `ExtractorFactory.create(temporada="2025")` (comportamiento por defecto). Los JSON ya generados con `partido_id` GES se tratan como fuente de verdad; no hace falta re-scrapear el portal argentino para esas temporadas.
- **Cruce estructura + fixture (2026):** la página de competencia no expone `id_partido` en el calendario; el fixture argentino sí. El módulo `ingest/febamba/natural_key.py` define la clave natural **fecha + local + visitante** (nombres normalizados) para fusionar contexto de torneo cuando se activa el modo opcional de calendario widget solo como *skeleton* (`FEBAMBA_GES_WIDGET_CALENDAR=1`).

### 1.2 Estrategia de scraping


| Aspecto                          | Enfoque                                                                                                                                                                                                                                     |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Página de competencia**        | `GET competicion.aspx?competencia={id_competencia}`. BeautifulSoup: `DDLCategorias`, fases/grupos (postback categoría si aplica). Clases: `ingest/febamba/competition_parser.py` (envoltorio), implementación en `ingest/ges/extractor.py`. |
| **Listado de partidos (≤ 2025)** | POST al widget `widgetscab…/widget/informacion/partidos/…` (mismos parámetros que la página).                                                                                                                                               |
| **Listado de partidos (≥ 2026)** | `ArgentinaFixtureParser` en `ingest/febamba/fixture_parser_arg.py`: ventanas de fechas (`iter_date_windows`, por defecto ~45 días) sobre `CargarFixture`; parseo `parse_tabla_calendarios` (`ingest/argbasket/fixture.py`).                 |
| **Orquestación 2026**            | `ingest/febamba/argentina_pipeline.py` (`collect_partidos_temporada_2026`): une fixture argentino + opcional cruce con filas del widget GES vía clave natural. `main.py` usa este flujo cuando `ingesta_usa_portal_argentina(temporada)`.   |
| **Paginación**                   | **Histórico:** rango `FechaInicio`/`FechaFin` en el widget. **2026:** mismos límites en query string del fixture, troceados en ventanas para evitar timeouts.                                                                               |
| **Identificación de partidos**   | **Widget:** regex en `href` `…/partido/{id}==`. **Argentina:** token en enlace estadísticas bajo `/liga-federal/partido/…/`. **Sin ID:** `ingest/ges/partido_ids.py` (`gesn_…`) solo en flujo widget.                                       |
| **Estado del partido**           | Misma heurística fecha + marcador numérico (GES y pipeline argentina).                                                                                                                                                                      |
| **Boxscore**                     | **≤ 2025:** `widgetscab…/widget/partido/estadisticas/…`. **≥ 2026:** `FebambaDualSourceExtractor.get_boxscore` → `ArgentinaStatsParser` (`ingest/febamba/stats_parser_arg.py`) contra `argentina.basketball`.                               |


**Recomendación:** Para tablas que en el futuro dependan más de JS (SPA), valorar **Playwright** para ejecutar el navegador y extraer HTML tras render; para el flujo actual (POST → HTML), Requests + BeautifulSoup es suficiente.

### 1.3 Endpoints relevantes

**Competencia (todas las temporadas)** — `https://competicionescabb.gesdeportiva.es`


| Recurso            | Método                                  | Uso                                              |
| ------------------ | --------------------------------------- | ------------------------------------------------ |
| **Categorías**     | GET `competicion.aspx?competencia={id}` | Opciones `DDLCategorias`.                        |
| **Fases / grupos** | GET + POST WebForms (categoría)         | Opciones de combos para `merge_contexto_torneo`. |


**Histórico (widget)** — `https://widgetscab.gesdeportiva.es`


| Recurso     | Uso                                                  |
| ----------- | ---------------------------------------------------- |
| **Listado** | POST partidos por categoría / fase / grupo / fechas. |
| **Acta**    | GET estadísticas por `id_partido`.                   |


**Temporada 2026+** — `https://argentina.basketball`


| Recurso           | Uso                                                                                                      |
| ----------------- | -------------------------------------------------------------------------------------------------------- |
| **Fixture**       | GET `liga-federal/fixture?handler=CargarFixture&compCatId={id}&fechaIni=YYYY-MM-DD&fechaFin=YYYY-MM-DD`. |
| **Estadísticas**  | GET `liga-federal/partido/estadisticas/{token}==?key=`                                                   |
| **En vivo / PBP** | GET `liga-federal/partido/en-vivo/{token}==?key=`                                                        |


**Config:** opcional `comp_cat_argentina` o `comp_cat_por_categoria` en `config/competencias.json` si `compCatId` del portal ≠ `id_categoria` GES. Variable de entorno `FEBAMBA_GES_WIDGET_CALENDAR=1` habilita cruce opcional con el listado widget para rellenar `fase_ges` / `grupo_ges` por clave natural.

### 1.4 Rate limiting y robustez

- **Cliente HTTP:** Reintentos con backoff exponencial ante `429` (Too Many Requests) y 5xx. Parámetros sugeridos: `retries=3`, `backoff_base=0.5`, `backoff_factor=2.0`, jitter opcional.
- **Pausas entre peticiones:** Entre partidos o entre lotes de partidos, aplicar `sleep` (p. ej. 0.5–2 s) para reducir riesgo de bloqueo.
- **Concurrencia:** Limitar workers paralelos (p. ej. 4–6 para boxscores) y tamaño de lote (p. ej. 50 partidos por lote) para no saturar el servidor.
- **Persistencia de progreso:** Guardar último lote o último `partido_id` procesado por competencia/categoría para reanudar sin reextraer todo.

---

## 2. Modelo de Datos (SQL)

Objetivo: vincular **jugador** (`jugador_id`) a través de **temporadas** y **tipos de torneo** (Apertura, Clausura, Copa de Oro/Plata), y soportar **cambios de club** del mismo jugador.

### 2.1 Entidades principales

- **partidos:** Un partido por fila; `partido_id` (texto) PK; `comp_id`, `competencia`, `temporada`, `categoria`, `categoria_id`, `fecha`, equipos, estado, etc. Incluye `comp_id` para mapear al torneo/competencia en GES. En temporada 2026+ con argentina.basketball, `partido_id` suele ser el token del portal y `estadisticas` (JSONB) guarda el boxscore parseado (`fuente`, `equipos`, …).
- **play_by_play:** Eventos jugada a jugada por partido. PK (`partido_id`, `event_idx`); FK a `partidos(partido_id)` con `ON DELETE CASCADE`. Columnas útiles para consultas (`cuarto`, `clock`, `tipo`, `equipo`, `jugador`, `dorsal`, marcadores, `hora_real`, `raw`) y `payload JSONB` con el evento completo del parser. Poblada por `ingest/argbasket/pipeline_to_postgres.py` (vía `ges_cli.py argbasket ingest`).
- **clubes:** `club_id` (PK), `nombre`. Un club puede tener varios equipos por temporada.
- **equipos:** `equipo_id` (PK), `club_id`, `nombre`. Equipo concreto en una competencia (el mismo club puede tener distinto `equipo_id` por torneo).
- **jugadores:** `jugador_id` (PK), `club_id` (último conocido o principal), `nombre`, `nombre_completo`. Identidad estable del jugador en GES.
- **temporadas:** `temporada_id` (PK), `nombre` (ej. "2023", "2024"). Año o etiqueta de temporada.

### 2.2 Vinculación jugador–club–temporada (cambios de club)

Tabla **jugador_club_temporada (JCT):**

- `jct_id` (PK), `jugador_id`, `club_id`, `temporada_id`.
- UNIQUE (`jugador_id`, `club_id`, `temporada_id`).

Interpretación: por cada temporada, un jugador puede estar en uno o más clubes (traspasos). Cada fila es una relación jugador–club en una temporada. Las estadísticas de partido se enlazan a **jct_id** (no solo a jugador_id), de modo que las métricas se puedan atribuir correctamente al club y temporada.

### 2.3 Estadísticas

- **estadisticas_jugador:** Por partido y por jugador en ese partido. Incluye `partido_id`, `jct_id`, `equipo_id`, y campos de boxscore: `min`, `pts`, `dos_a`, `dos_i`, `tres_a`, `tres_i`, `uno_a`, `uno_i`, `rebdef`, `rebofe`, `rebtot`, `ast`, `rec`, `per`, `tap`, `fal`, `val`. PK: (`partido_id`, `jct_id`).
- **totales_equipo:** Totales por partido y equipo (`partido_id`, `equipo_id`).

### 2.4 Torneos (Apertura, Clausura, Copa)

- Los distintos torneos (Apertura, Clausura, Copa de Oro/Plata) en GES suelen ser **competencias distintas** (`id_competencia` distinto) o **categorías** dentro de una competencia.
- En la BD: `partidos.comp_id` y `partidos.competencia` / `partidos.categoria` permiten filtrar por tipo de torneo.
- Para análisis YoY unificado: agrupar por `temporada` (y opcionalmente por `competencia`/tipo de torneo) y vincular siempre al mismo `jugador_id` (y `jct_id` cuando se requiera desglose por club).

### 2.5 Mapeo dinámico de IDs de torneos

- GES cambia `id_competencia` (y a veces `id_categoria`) cada temporada.
- **Solución:** Mantener un **fichero de configuración** (p. ej. `config/competencias.json` o lista en código) con estructura tipo:
  - Por temporada: lista de `{ "id_competencia": number, "nombre": string, "temporada": string }` para Formativas, y si aplica entradas para Apertura, Clausura, Copa.
  - En tiempo de ejecución: leer este mapeo para saber qué `id_competencia` usar por temporada; actualizar el fichero cuando GES publique nuevas competencias.

---

## 3. Lógica de Análisis

### 3.1 Normalización de estadísticas

- **Minutos:** En algunas categorías GES no expone minutos jugados (`min` vacío o no fiable). No se pueden calcular “por 36 min” de forma homogénea en todos los partidos.
  - **Enfoque recomendado:**
    - Si `min` está disponible y es numérico: usar estadísticas **por minuto** (p. ej. PTS/36, REB/36) para comparar jugadores con distintos minutos.
    - Si `min` no está disponible: trabajar con **totales por partido** o **promedios por partido** en esa categoría/temporada, y documentar en metadatos que la normalización “por minuto” no aplica.
  - Algoritmo sugerido: función que, por fila de estadística, devuelve (valor_raw, minutos, valor_per_36 si aplica, flag_min_disponible). Las agregaciones temporada/categoría se hacen sobre valores consistentes (o bien totales, o bien per_36 cuando min exista).

### 3.2 Cálculo de evolución YoY (año contra año)

- Por **jugador_id** (y opcionalmente por **jct_id** si se quiere por club):
  - Agregar métricas por temporada: promedios o totales (PTS, REB, AST, %2P, %3P, %1P, etc.) según la normalización elegida.
- **Tasa de crecimiento anual:** para una métrica M y temporadas T y T+1:
  - `crecimiento_pct = (M_{T+1} - M_T) / M_T * 100` si `M_T != 0`, si no definir convención (p. ej. crecimiento infinito o N/A).
- Considerar: pocos partidos en una temporada puede distorsionar; umbral mínimo de partidos (o minutos) para incluir una temporada en el YoY.

---

## 4. Stack Tecnológico Recomendado


| Componente    | Tecnología               | Notas                                                                                                                |
| ------------- | ------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Lenguaje      | Python 3.10+             | Coherencia con código existente.                                                                                     |
| Scraping      | Requests + BeautifulSoup | Para flujo actual (POST → HTML). Playwright opcional si más contenido pasa a ser SPA.                                |
| Persistencia  | PostgreSQL               | Recomendado para producción; esquema actual con partidos, JCT, estadísticas. SQLite aceptable para desarrollo local. |
| Análisis      | Pandas                   | Agregaciones por temporada/jugador, cálculo YoY, export a CSV/Excel.                                                 |
| Configuración | JSON (`config.json`)     | DB y, si se desea, rutas y parámetros de scraping.                                                                   |


---

## 5. Restricciones Técnicas

- **IDs de torneos variables:** No hardcodear `id_competencia`; usar mapeo por temporada (config/competencias) y actualizarlo al inicio de cada campaña.
- **Rate limiting:** Respetar backoff del cliente HTTP y pausas entre lotes; limitar concurrencia de workers.
- **Disponibilidad de minutos:** No asumir que `min` existe en todas las categorías; la capa de análisis debe contemplar ambos modos (por partido y por minuto cuando exista).
- **Identidad del jugador:** GES identifica jugadores por `jugador_id`; mantener esa PK y usar JCT solo para historial club/temporada.

---

## 6. Estructura de Carpetas Sugerida

```
├── README.md
├── ARCHITECTURE.md
├── config.json
├── main.py
├── ingest/
│   ├── __init__.py
│   ├── extractors.py      # Shim → ingest/ges/extractor.py
│   ├── http_client.py     # Cliente HTTP con reintentos y backoff
│   ├── febamba/           # Contexto torneo, 2026+ argentina.basketball, clave natural
│   ├── ges/               # GesDeportivaExtractor, ExtractorFactory, partido_ids
│   ├── argbasket/         # Fixture/stats HTML argentina.basketball
│   ├── extract_boxscore.py
│   └── extraer_info_partidos.py
├── persist/
│   ├── __init__.py
│   ├── persistir_postgres.py
│   └── ddl/               # (opcional) DDL y migraciones
├── analysis/
│   ├── __init__.py
│   ├── normalizer.py      # Normalización (min, per_36, flag disponibilidad)
│   ├── yoy.py             # Cálculo evolución YoY
│   └── queries.py        # Búsqueda por parámetros estadísticos
├── config/
│   └── competencias.json  # Mapeo temporada → id_competencia (Apertura, Clausura, Copa)
├── errors.py
├── ligas.py
└── dashboard_app.py       # (opcional)
```

Con esta estructura, el flujo queda: **ingest** (scraping + API interna) → **persist** (PostgreSQL + JCT) → **analysis** (normalización + YoY + consultas), con configuración centralizada de torneos en `config/`.