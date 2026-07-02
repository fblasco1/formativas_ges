# Backlog — Formativas 2026 / Buscador de jugadores

Fuente de verdad para scouting avanzado: [`Plan.md`](Plan.md).

Contexto: el buscador está en `analysis/buscador_jugadores_destacados.py`
(salida local `outputs/buscador/buscador_jugadores.html` y versión cifrada en
`docs/buscador_jugadores.html`). Cachés: `boxscores_full.json`, `jugadores_ficha.json`,
`partidos.json`.

---

## Completados

### 1) Tiros intentados y anotados: 2P / 3P / TL
- Columnas A-I por partido, porcentajes de temporada y filtros min–máx.

### 2) Nombre completo + fecha de nacimiento
- Fichas por `pid`, edad calculada, agregación robusta por ID de jugador.

### 3) Métricas avanzadas (TS%, eFG%, Val/Min, Ast/Per)
- Módulo `analysis/buscador_metrics.py`.

### 4) Perfiles K-Means + percentiles por categoría
- 6 perfiles con badges de color en la tabla.

### 5) Scouting privado (localStorage)
- Estrellas, notas, lista de fichajes, panel de detalle.

### 6) Comparador y export CSV
- Hasta 3 jugadores; CSV de resultados filtrados.

### 7) Optimización de render
- DocumentFragment + debounce en filtros.

---

## Pendientes (futuro)

### YoY multi-temporada
- Módulos `analysis/yoy.py` y `analysis/queries.py` (ver ARCHITECTURE.md).
- Requiere datos históricos en caché o PostgreSQL.

### Categorías femeninas y mini
- Ampliar dict `CATEGORIAS` en el script del buscador.

### Fotos de jugador en tabla
- Fetch de `/fotos/{pid}`; por ahora link a ficha en argentina.basketball.

### Integración dashboard PostgreSQL
- Unificar búsqueda web estática con `dashboard_app.py` multi-temporada.
