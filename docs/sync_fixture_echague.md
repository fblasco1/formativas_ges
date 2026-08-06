# Sync fixture Pedro Echagüe → Google Sheets

Mantiene actualizado el spreadsheet de CMs con partidos del club en varias competencias FeBAMBA 2026.

Sheet: https://docs.google.com/spreadsheets/d/1FFMSZhnfrYVvpjiXLBtgNseVLxiuG8NfH00uCXUXl9k/edit

## Competencias incluidas

| GES | Torneo | Categorías en el Sheet |
|-----|--------|------------------------|
| 2015 | Formativas | U9, U11, U13, U15, U17, **U21** |
| 2013 | Superior | **SUP** |
| 2018 | Flex formativas | U9–U17 Flex |
| 2019 | Flex superior | **SUP Flex** |
| 2028 | Femenina | U9–U21 Fem |

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

## Automatización

### GitHub Actions (recomendado)

Workflow: [`.github/workflows/sync_echague_sheets.yml`](../.github/workflows/sync_echague_sheets.yml)

- Corre a las **08:00 y 20:00** (hora Argentina).
- También se puede disparar a mano (*Actions → Sync fixture Echagüe → Run workflow*).
- Secret del repo: `GOOGLE_SERVICE_ACCOUNT_JSON` = contenido íntegro del JSON de la service account.

### Task Scheduler (Windows)

1. Acción: `C:\...\GES LNB y TNA\.venv\Scripts\python.exe`
2. Argumentos: `analysis/sync_fixture_echague_sheets.py --progress`
3. Iniciar en: la carpeta del repo.
4. Desencadenadores: diario 08:00 y 20:00.

## Notas

- GES no empuja eventos: “en tiempo real” = cada pocas horas alcanza para CMs.
- Si un visitante queda sin `DIRECCION`, completar el club en `data/referencia/AFILIADAS y DIRECCIONES.xlsx` o en el mapeo de viajes y volver a correr.
- La corrida completa (todas las competencias) tarda varios minutos por la cantidad de zonas GES.
