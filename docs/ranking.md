# Ranking / Renivelación (FeBAMBA)

Motor de Power Ranking y renivelación por tiras, portado desde la rama `Ranking_V2` a `apps/ranking/`.

## Ejecutar la app

Desde la raíz del repo:

```powershell
pip install -r apps/ranking/requirements.txt
streamlit run apps/ranking/streamlit_app.py
```

En Streamlit Community Cloud:

- **Branch:** `main`
- **Main file path:** `apps/ranking/streamlit_app.py`

## CLI del motor

```powershell
# Power Ranking por año / acumulado
python -m analisis.Ranking --help

# Renivelación por tiras
python -m analisis.renivelacion_tiras --help
```

Ejecutar con `PYTHONPATH=apps/ranking` (o `cd apps/ranking` primero) para que `analisis` y `mapeos` resuelvan.

## Datos

- Partidos consolidados: `apps/ranking/Data/procesada/23-26.csv`
- Rankings snapshot: `apps/ranking/Data/procesada/Ranking*.csv`
- Mapeos de equipos/categorías: `apps/ranking/mapeos/`

Si falta el CSV consolidado, regenerarlo con el pipeline documentado en `apps/ranking/RENIVELACION_TIRAS.md` (histórico en tag `archive/Ranking_V2-2026-05`).

## Tests

```powershell
pytest tests/ranking -q
```

## Docs internas del paquete

- `apps/ranking/RENIVELACION_TIRAS.md`
- `apps/ranking/DEPLOY_STREAMLIT.md`
