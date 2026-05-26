# Actualización diaria (temporada activa 2026)

Cada ejecución:

1. **Scrapea GES** el torneo FORMATIVAS 2026 (reemplaza `Data/partidos_2026.csv`).
2. **Normaliza** nombres de equipo en ese CSV (`equipos_map.json`).
3. **Consolida** `Data/procesada/23-26.csv` (2023–2026).
4. **Actualiza** `Ranking_Tiras_Actualizado_2026.csv` (renivelación incremental).

## Ejecución manual

```powershell
cd "c:\Users\USUARIO\Documents\Proyectos de Codigo\GES LNB y TNA"
.\.venv\Scripts\python.exe pipelines\actualizar_temporada_activa.py
```

Solo reprocesar sin scrapear GES:

```powershell
.\.venv\Scripts\python.exe pipelines\actualizar_temporada_activa.py --sin-scrape
```

## Script para el Programador de tareas

```powershell
.\scripts\actualizar_diario.ps1
```

## Programar en Windows (una vez al día)

1. Abrí **Programador de tareas** → *Crear tarea básica*.
2. Nombre: `GES FeBAMBA actualización diaria`.
3. Desencadenador: **Diariamente** (ej. 06:00).
4. Acción: **Iniciar un programa**
   - Programa: `powershell.exe`
   - Argumentos:

     ```
     -ExecutionPolicy Bypass -File "c:\Users\USUARIO\Documents\Proyectos de Codigo\GES LNB y TNA\scripts\actualizar_diario.ps1"
     ```

   - Iniciar en:

     ```
     c:\Users\USUARIO\Documents\Proyectos de Codigo\GES LNB y TNA
     ```

5. Marcá *Ejecutar aunque el usuario no haya iniciado sesión* solo si la PC está encendida a esa hora.

### Línea de comandos (alternativa)

```powershell
schtasks /Create /TN "GES-FeBAMBA-Diario" /SC DAILY /ST 06:00 `
  /TR "powershell.exe -ExecutionPolicy Bypass -File `"c:\Users\USUARIO\Documents\Proyectos de Codigo\GES LNB y TNA\scripts\actualizar_diario.ps1`"" `
  /F
```

## Archivos de salida

| Archivo | Contenido |
|---------|-----------|
| `Data/partidos_2026.csv` | Partidos scrapeados |
| `Data/procesada/23-26.csv` | Consolidado para Streamlit |
| `Data/procesada/Ranking_Tiras_Actualizado_2026.csv` | Ranking de tiras |
| `Data/procesada/ultima_actualizacion.json` | Última corrida (ok, delta de partidos) |
| `logs/actualizacion_YYYYMMDD_HHMMSS.log` | Log detallado |

## Primera vez

Si nunca corriste renivelación histórica:

```powershell
.\.venv\Scripts\python.exe -m analisis.renivelacion_tiras --congelar-historico
```

Luego la actualización diaria solo usa `--actualizar-2026` (automático dentro del pipeline).

## Cambiar temporada activa

Editá `TEMPORADA_ACTIVA` en `analisis/Ranking/seasons.py` y agregá el torneo en `pipelines/scrape_temporadas.py` → `TORNEOS`.

## Bloqueo

Si una ejecución se corta, puede quedar `Data/.actualizacion_en_curso.lock`. Borralo solo si no hay otro proceso corriendo.
