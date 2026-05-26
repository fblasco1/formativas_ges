# Deploy en Streamlit Community Cloud

Streamlit Cloud **solo despliega desde GitHub**, no desde archivos locales sueltos.

## Por qué aparece el error

> *The app's code is not connected to a remote GitHub repository*

Suele pasar si:

1. Abrís el deploy desde la carpeta **`Proyectos de Codigo`** (no tiene `.git`).
2. El repo correcto está en **`GES LNB y TNA`**, con remoto  
   `https://github.com/fblasco1/formativas_ges.git`.
3. Los cambios nuevos **no están pusheados** a GitHub (Streamlit lee el remoto, no tu PC).

## Pasos (recomendado)

### 1. Subir el código a GitHub

En PowerShell, desde la carpeta del proyecto:

```powershell
cd "C:\Users\USUARIO\Documents\Proyectos de Codigo\GES LNB y TNA"
git status
git add streamlit_app.py visualizaciones/ranking_streamlit.py requirements.txt
git add analisis mapeos pipelines utils docs
git add Data/procesada/23-26.csv
git commit -m "App Streamlit ranking renivelación y datos consolidados"
git push origin Ranking_V2
```

Incluí también lo que falte para que la app funcione en la nube (`Data/procesada/23-26.csv` ~6 MB es necesario).

No subas: `.venv/`, `__pycache__/`, `gesdeportiva.json`, logs.

### 2. Crear la app en la web

1. Entrá a [https://share.streamlit.io](https://share.streamlit.io) con la cuenta vinculada a **GitHub**.
2. **New app** → repositorio `fblasco1/formativas_ges`.
3. **Branch:** `Ranking_V2` (o `main` si fusionás ahí).
4. **Main file path:** `streamlit_app.py`
5. **Deploy**.

### 3. En Cursor / VS Code

Si usás el botón de deploy del IDE, abrí como workspace la carpeta **`GES LNB y TNA`** (donde está `.git`), no la carpeta padre.

## Comprobar conexión Git

```powershell
cd "C:\Users\USUARIO\Documents\Proyectos de Codigo\GES LNB y TNA"
git remote -v
```

Deberías ver `origin` → `github.com/fblasco1/formativas_ges.git`.

## Limitaciones en la nube

- **No** corre el scrape diario en Streamlit Cloud (solo muestra datos del repo).
- Para datos frescos: corré en tu PC `pipelines/actualizar_temporada_activa.py` y hacé **push** del CSV actualizado.
- El ranking se calcula en memoria al cargar; con `23-26.csv` suele ir bien.

## Actualización automática de datos (opcional)

Streamlit Cloud no ejecuta tu script diario. Flujo habitual:

1. PC: `python pipelines/actualizar_temporada_activa.py`
2. `git add Data/partidos_2026.csv Data/procesada/23-26.csv Data/procesada/Ranking_Tiras_Actualizado_2026.csv`
3. `git commit` + `git push` → la app en la nube se redeploya sola.
