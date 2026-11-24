# Backlog y roadmap — Formativas GES

Estado del proyecto a **agosto 2026**. El portal unificado está en producción; el foco siguiente es **integrar productos ya desarrollados**, **automatizar regeneración** y **profundizar scouting/analítica**.

Referencias: [`README.md`](README.md) · [`Plan.md`](Plan.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## Leyenda de estados

| Estado | Significado |
|--------|-------------|
| **Hecho** | En `main`, usable |
| **En repo** | Código mergeado; falta publicar en portal o automatizar |
| **Planificado** | Definido; sin implementar |
| **Idea** | Exploratorio / depende de datos externos |

---

## Completados recientes

### Portal y organización
- [x] Hub de productos en `docs/index.html` con menú de herramientas
- [x] Modelo de ramas `main` / `develop` / `feat/*`
- [x] Deploy GitHub Pages desbloqueado (workflow + `.nojekyll`)
- [x] Standings Superior 2026
- [x] Scouting de rival (HTML + generador)
- [x] Sync Echagüe → Google Sheets + JSON SICLUB

### Buscador de jugadores
- [x] 2P / 3P / TL con filtros min–máx
- [x] Nombre completo, edad, fichas por `pid`
- [x] TS%, eFG%, Val/Min, Ast/Per
- [x] K-Means + 6 perfiles con badges
- [x] Scouting privado (localStorage), comparador, export CSV
- [x] Render optimizado (DocumentFragment + debounce)

### Standings y cumplimiento
- [x] Formativas 2026 con etapas, niveles, Inter A/B, Nivel 1
- [x] Mini Masc: marcadores raros, PBP, clasificación U11

### Viajes y comparativa
- [x] Informe viajes Elite 42 (niveles, matriz distancias)
- [x] Simulación de escenarios de fixture
- [x] Comparativa ligas U15/U16 (Brasil, España, Alemania, Serbia + ENEBA 2024)

### Ingesta y ops
- [x] Pipeline 2026 vía argentina.basketball
- [x] Scrape incremental Echagüe por scopes cacheados
- [x] Parsers LFF / Metro (fixture JSON, constantes compCatId)
- [x] Scripts exploratorios FEB, Genius, JBBL, DScore Serbia

---

## Próximas features

### Prioridad alta — Integración al portal

| # | Feature | Estado | Descripción | Entregable |
|---|---------|--------|-------------|------------|
| P1 | **Hub: LFF / Metro** | En repo | Agregar card en portal + publicar ficha objetivos | `docs/ficha_objetivos_partido_metro.html` en hub |
| P2 | **Hub: Entrenadores 2026** | En repo | Publicar informe visual multiclub | `docs/informe_entrenadores_2026.html` + card en hub |
| P3 | **Hub: Escenarios de viajes** | En repo | Enlazar informe de escenarios junto al de niveles 2027 | Card + `docs/informe_escenarios_viajes.html` |
| P3b | **Niveles 2027 + cron** | Hecho | Movilidad Fase 2 → 6 niveles; Action lunes 23:00 ART | `data/niveles_2027.json` · `regenerar_standings_niveles.yml` |
| P4 | **Regeneración automática standings** | Planificado | Workflow semanal que regenere formativas + superior y haga PR/commit | `.github/workflows/regenerar_standings.yml` |
| P5 | **Regeneración automática buscador** | Planificado | Cron que actualice cachés y republicue buscador cifrado | Workflow + secret de contraseña si aplica |

### Prioridad media — Scouting y analítica

| # | Feature | Estado | Descripción | Entregable |
|---|---------|--------|-------------|------------|
| M1 | **Scouting rival ↔ buscador** | Planificado | Reutilizar `boxscores_full.json` / caché compartida; evitar doble descarga | Refactor en `analysis/scouting_equipo_stats.py` |
| M2 | **YoY multi-temporada** | Planificado | Evolución jugador entre temporadas | `analysis/yoy.py`, vista en buscador |
| M3 | **Categorías femeninas y mini** | Planificado | Ampliar `CATEGORIAS` en buscador | Más competencias en dict + regeneración |
| M4 | **Comparativa internacional v2** | En repo | Automatizar descarga FEB/Genius/JBBL y merge al informe | Pipeline unificado + fecha de actualización visible |
| M5 | **LFF pipeline productivo** | En repo | Fixture LFF GES integrado al flujo principal de ingest | `ingest/ges/lff_fixture.py` en CLI + tests |
| M6 | **Entrenadores: alertas consecutivas** | En repo | Destacar entrenadores en misma categoría N temporadas seguidas | Sección en informe + filtros |

### Prioridad media — Operaciones y DX

| # | Feature | Estado | Descripción | Entregable |
|---|---------|--------|-------------|------------|
| O1 | **CLI unificado de informes** | Planificado | `python -m analysis publish --all` o script `regenerar_portal.py` | Un comando para regenerar + copiar a `docs/` |
| O2 | **Tests CI ampliados** | Planificado | Correr pytest en PRs a `develop` | Workflow `ci.yml` |
| O3 | **Documentar dependencias** | Planificado | `requirements.txt` raíz con extras opcionales | `[echague]`, `[ranking]`, `[dev]` |
| O4 | **Monitoreo sync Echagüe** | Idea | Alerta si cron falla o JSON no cambia en N días | Issue Action o badge en README |

### Prioridad baja — Futuro

| # | Feature | Estado | Descripción |
|---|---------|--------|-------------|
| B1 | Fotos de jugador en buscador | Idea | Fetch `/fotos/{pid}` o proxy |
| B2 | Dashboard PostgreSQL | Idea | Unificar búsqueda web con `dashboard_app.py` multi-temporada |
| B3 | Mini femenino | Idea | Extender cumplimiento U11 a categorías femeninas |
| B4 | Ranking en la nube | Idea | Deploy Streamlit (no solo local) |
| B5 | API REST ligera | Idea | Solo si se superan límites del HTML estático |

---

## Orden sugerido de implementación

```text
Sprint 1 (portal)
  P1 → P2 → P3          # Completar hub con productos ya hechos

Sprint 2 (automatización)
  P4 → P5 → O1          # Menos regeneración manual

Sprint 3 (scouting)
  M1 → M2 → M3          # Profundizar buscador

Sprint 4 (datos externos)
  M4 → M5 → M6          # LFF + internacional + entrenadores
```

---

## Deuda técnica conocida

- Caché `outputs/echague/scopes_cache.json` no debe commitearse (solo Actions).
- Archivos `tmp_*` ignorados en `.gitignore`; limpiar periodicamente en local.
- Algunos informes escriben a `outputs/` y requieren copia manual a `docs/`.
- El buscador cifrado en Pages requiere contraseña; documentar rotación.
- Deploy Pages: usar `workflow_dispatch` si el cron de Echagüe encola muchos redeploys.

---

## Cómo proponer una feature nueva

1. Crear issue o entrada en este backlog con **problema**, **usuario** y **entregable**.
2. Branch `feat/<nombre-corto>` desde `develop`.
3. PR a `develop` → revisión → PR a `main` cuando esté listo para Pages.
