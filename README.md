# FeBAMBA Formativas (GES)

Herramientas de **extracción, normalización y análisis** de datos de torneos de básquet **formativas FeBAMBA** (aprox. 2019–2025), a partir del sitio [competicionescabb.gesdeportiva.es](https://competicionescabb.gesdeportiva.es). El foco analítico es un **ranking de clubes** inspirado en la lógica del ranking FIBA (adaptado a fases, zonas y categorías del reglamento local), **comparación entre regiones**, **diferencias de puntos por fase/categoría** y métricas sobre **campeones y formatos** de competencia.

## Stack

- **Python 3.11+** (ver `pyproject.toml`)
- **ETL**: BeautifulSoup, pandas, Parquet/CSV en `Data/`
- **Tests**: pytest
- **Dashboard**: Dash + Dash Bootstrap Components (visualizaciones en Streamlit en el repo se consideran **legado**; el objetivo es consolidar el UI en Dash)

## Instalación y pruebas

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

Los datos procesados van en `Data/raw/` y `Data/procesada/`. El catálogo amplio de competencias del proveedor está en `gesdeportiva.json` (no editar a mano); el pipeline filtra torneos FeBAMBA según federación. Mapeos de categorías y equipos viven en `mapeos/`.

## Estructura del repositorio

| Ruta | Rol |
|------|-----|
| `scraper/` | Scraping HTML del GES |
| `parsers/` | Fases, grupos, jornadas, rondas |
| `pipelines/` | Orquestación ETL y normalización |
| `mapeos/` | JSON + `loader.py` (categorías canónicas, aliases de clubes) |
| `analisis/` | Ranking FeBAMBA, métricas, dashboard Dash en evolución |
| `tests/` | Pruebas pytest |
| `utils/` | Logger, requests, utilidades de DataFrames/CSV |
| `outputs/` | Artefactos exportados (CSVs, tablas de análisis) |
| `Data/` | Entradas salidas de datos (raw / procesada) |

## Flujo de trabajo con Git

Se usa un modelo tipo **Git Flow simplificado** con tres niveles:

| Rama | Propósito |
|------|-----------|
| **`main`** | Historial **estable**, alineado con lo publicado o listo para release. Solo entra código integrado y revisado (vía `develop` o hotfix). |
| **`develop`** | **Integración** diaria: aquí convergen `feature/*` y `fix/*` antes de preparar un corte para `main`. |
| **`feature/<nombre-corto>`** | Nueva funcionalidad. Ej.: `feature/ranking-zonas-2025`. Se abre desde **`develop`**. |
| **`fix/<nombre-corto>`** | Corrección de bug o deuda técnica no urgente. Ej.: `fix/normalize-encoding`. Se abre desde **`develop`**. |

**Hotfixes** críticos sobre producción: rama `hotfix/<nombre>` desde **`main`**, merge a **main** y **también** a **develop** para no perder el arreglo.

Flujo típico de una mejora:

1. `git checkout develop && git pull`
2. `git checkout -b feature/mi-cambio`
3. Commits en la rama feature; `git push -u origin feature/mi-cambio` y PR hacia **`develop`**
4. Tras revisión, merge a **`develop`**
5. Cuando haya un conjunto estable para release: PR **`develop` → `main`** (o merge acordado por el equipo)

En el clon ya existen ramas locales **`main`** y **`develop`**, creadas a partir del estado de **`origin/master`** (default actual del remoto). Cuando quieras alinear el remoto con esta convención:

- Publicar `develop`: `git push -u origin develop`
- Si el hosting permite renombrar la rama por defecto, puedes pasar de `master` a `main` allí y luego `git fetch` y ajustar upstreams según la guía del proveedor (GitHub, GitLab, etc.).

## Colaboración

Issues y pull requests son bienvenidos. Mantener cambios acotados al objetivo del PR, evitar commitear `__pycache__/`, `.pyc` o datos masivos sensibles en `Data/procesada/` según la política del equipo (ver `.gitignore`).

## Licencia

Sin licencia explícita en este repositorio: acordar uso con los mantenedores si se reutiliza el código o los datos derivados.
