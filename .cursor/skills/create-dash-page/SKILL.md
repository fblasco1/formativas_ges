---
name: create-dash-page
description: Crea o extiende páginas del dashboard Dash según .cursor/rules/04-dashboard-patterns.mdc. Usar al añadir vistas, callbacks o componentes en dashboard/ o analisis/dashboard_zonas_dash.py durante la migración.
---

# Página Dash (FeBAMBA)

## Referencia obligatoria

Leer y cumplir `04-dashboard-patterns.mdc`: layout + `register_callbacks`, IDs `pagina-bloque-elemento`, sin I/O directo a disco en lógica pesada (preferir `dcc.Store`).

## Rutas en el repo

- **Objetivo**: `dashboard/pages/*.py` + `dashboard/app.py`
- **Transición**: puede existir lógica en `analisis/dashboard_zonas_dash.py` — al migrar, mover bloques a `dashboard/` sin cambiar el contrato de columnas (`matches_clean` o equivalente).

## Stack

- `dash` 3.x, `dash-bootstrap-components` 2.x, `plotly` únicamente (no matplotlib, no Streamlit en código nuevo).

## Checklist

1. `layout()` sin negocio pesado; funciones en `analisis/` para agregaciones.
2. Callbacks con responsabilidad única; `prevent_initial_call` donde corresponda.
3. IDs estables y previsibles para tests manuales.
