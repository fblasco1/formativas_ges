---
name: add-club-alias
description: Añade o corrige alias de equipos en mapeos/equipos_map.json (mapa plano clave→valor en MAYÚSCULAS). Usar cuando falte normalización de nombres de clubes tras el scrape o el usuario pida un alias nuevo.
---

# Alias de equipos (FeBAMBA)

## Ubicación

- Archivo: `mapeos/equipos_map.json`
- Formato: **objeto JSON plano** `{ "NOMBRE COMO VIENE": "Nombre canónico" }`
- Claves: normalmente `NOMBRE.strip().upper()` como aparece en CSV/HTML problemático

## Pasos

1. Buscar en datos crudos (`Data/*.csv` o salida del scraper) el string exacto del club mal escrito.
2. Decidir el **valor canónico** (debe coincidir con el resto del dataset o con convención del proyecto).
3. Añadir entrada en `equipos_map.json`. No duplicar valores para la misma clave.
4. `mapeos/loader.py` → `normalizar_equipo(nombre, mapeo)` ya aplica upper + lookup; no hardcodear equipos en Python.

## Prohibido

- Listas anidadas o aliases solo en código fuera del JSON
- Tocar el scraper solo para un nombre cuando basta el mapeo
