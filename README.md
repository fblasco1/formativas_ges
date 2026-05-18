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

- **CLI unificado:** `python ges_cli.py --help` — subcomandos para temporada 2026 (argentina.basketball), FeBAMBA y utilidades de base de datos.
- **Ingesta FeBAMBA/GES:** `python main.py` o `python ges_cli.py ingest febamba` — partidos y boxscores según `config/competencias.json`.
- **Persistencia lotes JSON:** `python persist/persistir_postgres.py` o `python ges_cli.py db persist-lotes` — crea esquema y carga `partidos_*_lote_*.json`.
- **Pipeline 2026 → PostgreSQL:** descarga fixture (5075–5080), boxscore y play-by-play desde [argentina.basketball](https://argentina.basketball) y persiste en `partidos` + tabla `play_by_play`:

  ```powershell
  python ges_cli.py argbasket ingest -- --fecha-ini 2025-04-26 --fecha-fin 2026-05-10 --progress --limite 5
  ```

  Requiere `psycopg` instalado y `config.json` con credenciales PostgreSQL. Opcional: exportar CSV de fixture al mismo tiempo: `--export-csv data/argbasket/fixture_consolidado.csv`. Paralelismo HTTP: `--workers 4`. Configuración DB: `config.json` en el cwd del proceso (por defecto la raíz del repo) o `--config ruta\config.json`.

- **Solo fixture CSV (sin DB):** `python ges_cli.py argbasket fixture -- --fecha-ini ... --fecha-fin ... --output fixture_consolidado.csv`
- **Un partido (JSON):** `python ges_cli.py argbasket partido -- --id-partido-token TOKEN --output partido.json`
- **Dashboard:** `streamlit run dashboard_app.py` — consulta jugadores y estadísticas.
- **Análisis:** módulos en `analysis/` (ver `ARCHITECTURE.md`) para normalización y YoY.

### Tabla `play_by_play`

Creada por `persist/persistir_postgres.py` (y al ejecutar la ingesta 2026). Clave primaria `(partido_id, event_idx)`, FK a `partidos(partido_id)` con `ON DELETE CASCADE`. Columnas derivadas del parser (`cuarto`, `clock`, `tipo`, `equipo`, `jugador`, `dorsal`, marcador, `hora_real`, `raw`) más `payload JSONB` con el evento completo.

### `ges_cli` y `--out-dir`

`--out-dir DIR` cambia el directorio de trabajo antes de lanzar el subcomando (útil para escribir CSV o lotes bajo `data/`).

## Estructura del repositorio

```
├── README.md
├── ARCHITECTURE.md
├── config.json             # Conexión DB (db.host, db.port, db.user, db.password, db.name)
├── ges_cli.py              # CLI: argbasket 2026, db, fixture, ingest febamba
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
