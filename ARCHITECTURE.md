# Arquitectura — FeBAMBA Stats Tracker

Documento técnico de la arquitectura del proyecto de analítica para categorías formativas FeBAMBA (U13–U21). Define el módulo de ingesta, el modelo de datos, la lógica de análisis y las restricciones técnicas.

---

## 1. Módulo de Ingesta

### 1.1 Fuentes de datos

- **Portal público GES:** páginas HTML servidas por `competicionescabb.gesdeportiva.es` y widgets en `widgetscab.gesdeportiva.es`.
- **API interna (widgets/actas):** mismos dominios; la lógica de partidos y boxscore se consume vía HTTP GET/POST hacia URLs de widgets, no un REST API documentado.

### 1.2 Estrategia de scraping (portal GES)

| Aspecto | Enfoque |
|--------|---------|
| **Página de competencia** | `GET competicion.aspx?competencia={id_competencia}`. Parser con BeautifulSoup del `<select id="DDLCategorias">` para obtener `id_categoria` por nombre (U13, U14, … U21). |
| **Tablas dinámicas** | Los listados de partidos se obtienen vía **POST** al widget de partidos (ver 1.3). No depender de JavaScript en el cliente: reproducir el POST con los mismos parámetros que usa la página. |
| **Paginación** | El widget de partidos devuelve HTML con todos los partidos en el rango de fechas; no hay paginación clásica por página. Paginación efectiva: por **rango de fechas** (`FechaInicio`, `FechaFin`) o por **categoría**. Dividir temporada en ventanas si el servidor devuelve muchos resultados. |
| **Identificación de partidos** | Enlaces con patrón `.../partido/{id_partido}==` en atributo `href`; `id` del enlace contiene `HFEstadisticas`. Regex: `/partido/([\w-]+)==`. |
| **Estado del partido** | Inferido: si `Fecha < hoy` y hay puntos numéricos en las celdas → estado "COMPLETO"; si no → "PENDIENTE". |

**Recomendación:** Para tablas que en el futuro dependan más de JS (SPA), valorar **Playwright** para ejecutar el navegador y extraer HTML tras render; para el flujo actual (POST → HTML), Requests + BeautifulSoup es suficiente.

### 1.3 Endpoints / URLs internas (sistema de actas y widgets)

Base: `https://widgetscab.gesdeportiva.es`.

| Recurso | Método | URL / cuerpo | Uso |
|---------|--------|--------------|-----|
| **Categorías** | GET | `https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia={id_competencia}` | Obtener opciones del `<select>` DDLCategorias → mapeo nombre categoría ↔ `id_categoria`. |
| **Listado partidos** | GET (cookie/session) + POST | Widget: `widget/informacion/partidos/{id_categoria}/-3/7?fase=-1&grupo=-1&equipo=-1&key={key}`. POST con `IdCategoria`, `IdFase`, `IdGrupo`, `IdEquipo`, `Key`, `FechaInicio`, `FechaFin`. | Lista de partidos de la categoría en el rango de fechas. Respuesta: HTML con filas y enlaces a partido. |
| **Boxscore (acta)** | GET | `widget/partido/partido/{id_partido}` (o ruta equivalente que devuelva el HTML del acta con tablas de jugadores). | Estadísticas por jugador y totales de equipo; parser de `<table>` con thead/tbody/tfoot. |

El valor `key` del widget de partidos se obtiene del mismo GET inicial al widget; se incluye en el POST. Las sesiones (cookies) pueden ser necesarias entre GET y POST del mismo widget.

### 1.4 Rate limiting y robustez

- **Cliente HTTP:** Reintentos con backoff exponencial ante `429` (Too Many Requests) y 5xx. Parámetros sugeridos: `retries=3`, `backoff_base=0.5`, `backoff_factor=2.0`, jitter opcional.
- **Pausas entre peticiones:** Entre partidos o entre lotes de partidos, aplicar `sleep` (p. ej. 0.5–2 s) para reducir riesgo de bloqueo.
- **Concurrencia:** Limitar workers paralelos (p. ej. 4–6 para boxscores) y tamaño de lote (p. ej. 50 partidos por lote) para no saturar el servidor.
- **Persistencia de progreso:** Guardar último lote o último `partido_id` procesado por competencia/categoría para reanudar sin reextraer todo.

---

## 2. Modelo de Datos (SQL)

Objetivo: vincular **jugador** (`jugador_id`) a través de **temporadas** y **tipos de torneo** (Apertura, Clausura, Copa de Oro/Plata), y soportar **cambios de club** del mismo jugador.

### 2.1 Entidades principales

- **partidos:** Un partido por fila; `partido_id` (texto) PK; `comp_id`, `competencia`, `temporada`, `categoria`, `categoria_id`, `fecha`, equipos, estado, etc. Incluye `comp_id` para mapear al torneo/competencia en GES.
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

| Componente | Tecnología | Notas |
|------------|------------|--------|
| Lenguaje | Python 3.10+ | Coherencia con código existente. |
| Scraping | Requests + BeautifulSoup | Para flujo actual (POST → HTML). Playwright opcional si más contenido pasa a ser SPA. |
| Persistencia | PostgreSQL | Recomendado para producción; esquema actual con partidos, JCT, estadísticas. SQLite aceptable para desarrollo local. |
| Análisis | Pandas | Agregaciones por temporada/jugador, cálculo YoY, export a CSV/Excel. |
| Configuración | JSON (`config.json`) | DB y, si se desea, rutas y parámetros de scraping. |

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
│   ├── extractors.py      # Extractores GES (categorías, partidos, boxscore)
│   ├── http_client.py     # Cliente HTTP con reintentos y backoff
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
