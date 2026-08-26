# Sync fixture Pedro Echagüe → Google Sheets + JSON SICLUB

Mantiene actualizado el spreadsheet de CMs con partidos del club en varias competencias FeBAMBA 2026, y publica un JSON con contrato máquina para que SICLUB (`club_management`) importe reservas sin leer el Sheet.

Sheet: https://docs.google.com/spreadsheets/d/1FFMSZhnfrYVvpjiXLBtgNseVLxiuG8NfH00uCXUXl9k/edit

JSON (repo): `outputs/echague/fixture_echague.json`  
JSON (Pages): `docs/fixture_echague.json` (misma carga; el cron lo copia al publicar).

## Competencias incluidas

| GES | Torneo | Categorías en el Sheet |
|-----|--------|------------------------|
| 2015 | Formativas | U9, U11, U13, U15, U17, **U21** |
| 2013 | Superior | **SUP** (Pre Liga, Reclasificación, Copas Oro/Plata/Bronce) |
| 2310 | Liga Metropolitana / Pre Federal | **Liga Metro** (continuación plantel A) |
| 2018 | Flex formativas | U9–U17 Flex |
| 2019 | Flex superior | **SUP Flex** (plantel C) |
| 2028 | Femenina | U9–U21 Fem |

### Planteles Superior (columna TIRA)

| Tira | Qué es | Nombre GES típico |
|------|--------|-------------------|
| **A** | Plantel A | `PEDRO ECHAGUE` (Pre Liga 2013) · `INSTITUCION CULTURAL y DEPORTIVA PEDRO ECHAGUE` (Liga Metro 2310) |
| **B** | Plantel B | `PEDRO ECHAGUE B` |
| **C** | Plantel C | partidos de **SUP Flex** (2019) |

Se excluyen fases con `LFF` en el nombre (nacional).

## Columnas

| Columna | Contenido |
|---------|-----------|
| FECHA / HORA | Programación GES |
| TIRA | AZUL / AMARILLO / FLEX / B / — |
| CATEGORIA | U15, SUP, U17 Flex, U13 Fem, … |
| RIVAL | Rival |
| LOCALIA | Local / Visitante |
| DIRECCION | Sede propia (Portela 836) o del rival (lookup afiliadas) |
| RESULTADO | `propios-rival` cuando está jugado; vacío si pendiente |
| ID_PARTIDO | Clave técnica (no editar; sirve para no duplicar filas) |

Los CM pueden agregar columnas a la **derecha** de `ID_PARTIDO`: el sync no las pisa.

## JSON para SICLUB

Tras `construir_filas()` el script escribe el contrato (UTF-8, `ensure_ascii=False`, indent 2):

```json
{
  "version": 1,
  "source": "febamba_ges",
  "generated_at": "2026-08-26T20:00:00-03:00",
  "club": "PEDRO ECHAGUE",
  "partidos": [
    {
      "source": "febamba_ges",
      "external_id": "<ID_PARTIDO>",
      "fecha": "2026-09-06",
      "hora": "20:00",
      "tira": "AZUL",
      "categoria": "U17",
      "rival": "Club Visitante",
      "localia": "Local",
      "direccion": "Portela 836, CABA (CP 1406)",
      "resultado": "",
      "espacio": null
    }
  ]
}
```

- `external_id` = `ID_PARTIDO` (clave de upsert). Filas sin id no entran al JSON.
- `fecha` en ISO `YYYY-MM-DD` (el Sheet/CSV sigue en `DD/MM/YYYY`).
- `hora` tal cual el pipeline CM (`"20:00"`, `"20 A 22"`, …).
- `localia`: `"Local"` / `"Visitante"`. Se publican ambos; SICLUB solo ocupa espacio físico en Local.
- `espacio`: siempre `null` (GES no trae cancha).
- `generated_at`: ISO-8601 con offset ART (`-03:00`).

El CSV no se commitea (`*.csv` en `.gitignore`). El JSON sí: el workflow lo pushea a `main` y copia a `docs/` para GitHub Pages.

URL canónica para SICLUB (raw en `main`):

`https://raw.githubusercontent.com/fblasco1/formativas_ges/main/outputs/echague/fixture_echague.json`

## Setup (una vez)

1. En [Google Cloud Console](https://console.cloud.google.com/) crear un proyecto → habilitar **Google Sheets API** y **Google Drive API**.
2. Crear una **Service Account**, descargar el JSON.
3. Guardarlo como `config/google_service_account.json` (está en `.gitignore`).
4. Compartir el spreadsheet con el `client_email` del JSON, rol **Editor**.
5. (Opcional) Ajustar `config/echague_sheets.json` (`spreadsheet_id`, `worksheet`). La pestaña por defecto se llama `Fixture` (se crea si no existe).

Plantilla del JSON: `config/google_service_account.example.json`.

## Uso local

```powershell
# Solo CSV (sin Google), desde GES en vivo (incluye pendientes)
.\.venv\Scripts\python.exe analysis/sync_fixture_echague_sheets.py --solo-csv --progress

# Subir / actualizar el Sheet
.\.venv\Scripts\python.exe analysis/sync_fixture_echague_sheets.py --progress

# Solo algunas categorías (debug)
.\.venv\Scripts\python.exe analysis/sync_fixture_echague_sheets.py --solo-csv --solo-categorias U21,SUP,SUP Flex --progress

# Rápido: solo partidos ya en datos.json formativas (COMPLETO U9–U17)
.\.venv\Scripts\python.exe analysis/sync_fixture_echague_sheets.py --desde-json outputs/formativas_2026/datos.json --solo-csv
```

Salida CSV de respaldo: `outputs/echague/fixture_echague.csv`.  
JSON SICLUB: `outputs/echague/fixture_echague.json`.

## Automatización

### GitHub Actions (recomendado)

Workflow: [`.github/workflows/sync_echague_sheets.yml`](../.github/workflows/sync_echague_sheets.yml)

- Corre a las **08:00 y 20:00** (hora Argentina).
- También se puede disparar a mano (*Actions → Sync fixture Echagüe → Run workflow*).
- Secret del repo: `GOOGLE_SERVICE_ACCOUNT_JSON` = contenido íntegro del JSON de la service account.
- Tras el upsert al Sheet, commitea `outputs/echague/fixture_echague.json` y `docs/fixture_echague.json` (SICLUB consume el raw de `main`).

### Task Scheduler (Windows)

1. Acción: `C:\...\GES LNB y TNA\.venv\Scripts\python.exe`
2. Argumentos: `analysis/sync_fixture_echague_sheets.py --progress`
3. Iniciar en: la carpeta del repo.
4. Desencadenadores: diario 08:00 y 20:00.

## Optimización y direcciones manuales

- El cron corre en modo **incremental**: solo vuelve a consultar zonas donde ya jugó Echagüe, más **fases nuevas** que aparezcan en GES.
- Descubrimiento completo (todas las zonas):  
  `python analysis/sync_fixture_echague_sheets.py --full --progress`
- Cache de zonas: `outputs/echague/scopes_cache.json` (se regenera en cada corrida GES).
- **DIRECCION**: si en el Sheet ya hay un valor (cargado a mano), el sync **no lo pisa**. Solo completa celdas vacías o filas nuevas.
