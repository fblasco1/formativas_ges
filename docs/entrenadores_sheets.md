# Entrenadores → Google Sheets (WhatsApp bidireccional)

El listado de entrenadores se sincroniza a un Google Sheet. El HTML lee/escribe **WhatsApp** vía un Apps Script Web App.

## Requisitos

- `config/google_service_account.json` (misma SA que Echagüe)
- `pip install gspread google-auth`
- Spreadsheet vacío compartido con el `client_email` de la SA (**Editor**)

Service account actual típica: `redesechague@…iam.gserviceaccount.com` (ver el JSON).

## Setup (una vez)

1. Creá un [Google Sheet](https://sheets.google.com) vacío.
2. Compartilo con el `client_email` de `config/google_service_account.json` → rol **Editor**.
3. Copiá el ID de la URL (`/d/<SPREADSHEET_ID>/edit`) a [`config/entrenadores_sheets.json`](../config/entrenadores_sheets.json) → `spreadsheet_id`.
4. Sincronizá el listado:

```powershell
python analysis/sync_entrenadores_sheets.py
```

5. En el Sheet: **Extensiones → Apps Script**, pegá el contenido de [`analysis/entrenadores_sheets_apps_script.js`](../analysis/entrenadores_sheets_apps_script.js).
6. **Implementar → Nueva implementación → Aplicación web**
   - Ejecutar como: **Yo**
   - Quién tiene acceso: **Cualquier persona**
7. Copiá la URL (`…/exec`) a `config/entrenadores_sheets.json` → `webapp_url`.
8. Regenerá el HTML:

```powershell
python analysis/generar_informe_visual_entrenadores.py
```

9. Abrí `outputs/entrenadores/informe_entrenadores_2026.html` → pestaña **Listado de entrenadores**.

## Columnas de la pestaña `Entrenadores`

| Columna | Origen |
|--------|--------|
| KEY | `ENTRENADOR\|\|CLUB` normalizado (upsert) |
| ENTRENADOR | Sync Python |
| CLUB | Sync Python |
| CATEGORIAS | Sync Python (separadas con ` \| `) |
| WHATSAPP | Editado desde el HTML (el sync **no** lo pisa) |

## Comportamiento del HTML

- Al abrir el listado: `GET` al Web App → carga filas + WhatsApp.
- Si falla la red: usa el listado embebido al generar el HTML (sin WhatsApp del Sheet).
- Al editar WhatsApp: `POST` al Web App → actualiza la celda en Sheets.
- Filtros: categoría, búsqueda, con/sin WhatsApp; export CSV con `;`.

## Re-sync del listado

Cuando regenerés el CSV de entrenadores:

```powershell
python analysis/sync_entrenadores_sheets.py
python analysis/generar_informe_visual_entrenadores.py
```

Los números de WhatsApp ya cargados en el Sheet se conservan.
