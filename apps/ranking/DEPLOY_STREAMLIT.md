# Deploy en Streamlit Community Cloud

Streamlit Cloud **solo despliega desde GitHub**, no desde archivos locales sueltos.

## Pasos

1. Pusheá `main` con `apps/ranking/` (incluye `Data/procesada/23-26.csv`).
2. En [https://share.streamlit.io](https://share.streamlit.io): **New app** → `fblasco1/formativas_ges`.
3. **Branch:** `main`
4. **Main file path:** `apps/ranking/streamlit_app.py`
5. **Deploy**.

Local:

```powershell
streamlit run apps/ranking/streamlit_app.py
```

Ver también [docs/ranking.md](../../docs/ranking.md).

## Limitaciones en la nube

- **No** corre scrape diario en Streamlit Cloud (solo datos del repo).
- Para datos frescos: regenerá el consolidado y hacé push de `apps/ranking/Data/procesada/23-26.csv`.
