# FeBAMBA Stats Tracker

Proyecto de **analítica de datos** para categorías formativas de FeBAMBA (U13 a U21). Extrae datos del sistema GES (web scraping y API interna) para documentar y analizar la evolución de jugadores año tras año.

## Objetivos

1. **Búsqueda de jugadores** por parámetros estadísticos en múltiples temporadas.
2. **Comparativa interanual (YoY)** de métricas clave: PTS, REB, AST, % tiros, etc.

## Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Ingesta | Python, Requests, BeautifulSoup |
| Persistencia | PostgreSQL |
| Análisis | Pandas |
| Config | `config.json` (DB), variables de entorno |

## Requisitos

- Python 3.10+
- PostgreSQL (o SQLite para desarrollo)
- Dependencias: `requests`, `beautifulsoup4`, `psycopg`, `pandas`

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\Activate
pip install requests beautifulsoup4 psycopg pandas
```

Configurar:

- **Base de datos:** `config.json` en la raíz (clave `db`: host, port, user, password, name).
- **Competencias:** `config/competencias.json` (mapeo temporada → id_competencia, widget_key, fecha_inicio/fin). Actualizar cada campaña.

Ejecutar siempre desde la **raíz del proyecto**.

## Uso rápido

- **Ingesta:** `python main.py` — extrae partidos y boxscores según `config/competencias.json`.
- **Persistencia:** `python persist/persistir_postgres.py` — crea esquema y carga lotes `partidos_*_lote_*.json` en PostgreSQL.
- **Dashboard:** `streamlit run dashboard_app.py` — consulta jugadores y estadísticas.
- **Análisis:** módulos en `analysis/` (ver `ARCHITECTURE.md`) para normalización y YoY.

## Estructura del repositorio

```
├── README.md
├── ARCHITECTURE.md
├── config.json             # Conexión DB (db.host, db.port, db.user, db.password, db.name)
├── main.py                 # Orquestador de ingesta (lee config/competencias.json)
├── ingest/                 # Módulo de ingesta
│   ├── __init__.py
│   ├── errors.py
│   ├── http_client.py
│   ├── extractors.py
│   ├── extract_boxscore.py
│   └── extraer_info_partidos.py
├── persist/                # Persistencia
│   ├── __init__.py
│   └── persistir_postgres.py
├── analysis/               # Lógica de análisis (normalizer, yoy, queries — pendiente)
│   └── __init__.py
├── config/
│   └── competencias.json   # id_competencia por temporada, widget_key, fechas
└── dashboard_app.py        # Streamlit: búsqueda de jugadores y estadísticas
```

## Restricciones técnicas

- **IDs de torneos:** GES cambia `id_competencia` por temporada; usar mapeo externo (ej. `competencias.json`) y actualizarlo cada campaña.
- **Rate limiting:** el cliente HTTP aplica reintentos con backoff ante 429/5xx; respetar pausas entre lotes en scraping masivo.

## Documentación

- **ARCHITECTURE.md:** diseño del módulo de ingesta, modelo de datos SQL, lógica de análisis (normalización, YoY), endpoints de la API interna y estrategia de scraping.

## Licencia

MIT
