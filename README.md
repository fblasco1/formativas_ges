# FeBAMBA — Formativas GES

Monorepo unificado (`main`): **GitHub Pages** como portal público + **CLI/ops** (standings, Echagüe, ingest) + **Ranking** Streamlit en `apps/ranking/`.

## Portal (GitHub Pages)

Índice: [docs/index.html](docs/index.html) (publicado en Pages).

| Producto | Entrada |
|----------|---------|
| Standings Formativas 2026 | `docs/formativas_2026_tabla_posiciones.html` |
| Standings Superior 2026 | `docs/superior_2026_tabla_posiciones.html` |
| Buscador jugadores | `docs/buscador_jugadores.html` |
| Scouting rival | `docs/scouting_rival.html` |
| Mini Masc | `docs/mini_masc_clasificacion.html` |
| Viajes / escenarios | `docs/informe_viajes_niveles.html` |
| Comparativa ligas | `docs/comparativa_ligas_formativas.html` |
| Ranking / renivelación | `docs/ranking.md` → `streamlit run apps/ranking/streamlit_app.py` |
| Sync Echagüe → Sheets + JSON SICLUB | `docs/sync_fixture_echague.md` + workflow Actions |

## Regenerar informes (desde la raíz del repo)

```powershell
python analysis/generar_standings_febamba_2026.py
python analysis/generar_standings_superior_2026.py
python analysis/buscador_jugadores_destacados.py
python analysis/generar_scouting_rival.py --desde-cache
python analysis/sync_fixture_echague_sheets.py --progress
```

Copiá/publicá los HTML resultantes bajo `docs/` según el script (varios ya escriben ahí o a `outputs/`).

## Ranking

```powershell
pip install -r apps/ranking/requirements.txt
streamlit run apps/ranking/streamlit_app.py
```

Detalle: [docs/ranking.md](docs/ranking.md).

## Stack / estructura

```text
main/
  analysis/          # standings, sync, viajes, buscador, informes
  ingest/            # GES / argentina.basketball
  apps/ranking/      # Power Ranking + Streamlit (ex Ranking_V2)
  docs/              # GitHub Pages = app pública
  .github/workflows/ # pages.yml + sync_echague_sheets.yml
  config/
  tests/
```

## Requisitos

- Python 3.10+
- Dependencias según el flujo: `requests`, `beautifulsoup4`, `pandas`; Echagüe: `gspread`, `google-auth`; Ranking: ver `apps/ranking/requirements.txt`
- PostgreSQL opcional para pipelines de persistencia legacy (`config.json`)

## Instalación rápida

```powershell
python -m venv .venv
.venv\Scripts\Activate
pip install requests beautifulsoup4 pandas gspread google-auth
```

Configurar competencias en `config/competencias.json`. Service account Echagüe: `config/google_service_account.json` (gitignored) o secret `GOOGLE_SERVICE_ACCOUNT_JSON` en Actions.

## Ramas

- **`main`**: producción (GitHub Pages, Actions Echagüe/SICLUB, portal público).
- **`develop`**: integración de trabajo en curso; base para nuevas `feat/*`.
- **`feat/<tema>`**: features cortas (`feat/portal-scouting`, `feat/lff`, etc.) → PR a `develop` → PR a `main`.
- Tags de archivo: `archive/main-pre-unificacion`, `archive/Ranking_V2-2026-05`, etc.

## CLI legacy

`python ges_cli.py --help` — argbasket, ingest FeBAMBA y utilidades de DB. Ver `ARCHITECTURE.md` para el modelo de datos histórico.

## Licencia

Uso interno FeBAMBA / análisis formativas.
