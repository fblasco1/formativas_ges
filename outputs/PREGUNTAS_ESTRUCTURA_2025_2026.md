# Preguntas para ajustar parsers (fase / ronda / nivel)

Basado en auditoría GES (`outputs/auditoria_estructura_ges_2025_2026.csv`) y scrape completo.

**Datos scrapeados:** `Data/partidos_2025.csv` (15.131) · `Data/partidos_2026.csv` (18.692)

Hoy ~**54%** de partidos formativos 2025 y ~**62%** en 2026 quedan con `fase=Desconocida` porque el parser solo reconoce `1ER ETAPA LFF` en 2025 y nada en 2026.

---

## Temporada 2025 — textos en GES (Cadetes / Infantiles / Juveniles)

| Texto en GES (DDLFases) | ¿Cómo mapearlo? |
|-------------------------|-----------------|
| `1er ETAPA LFF` | Hoy: Fase Regular + ronda `Copa Febamba` + nivel `NIVELACION`. ¿Correcto? |
| `2do SEMESTRE` | ¿2.º cuatrimestre de fase regular, campeonato, u otra fase? |
| `CLASIFICACION LFF` | ¿Playoff? ¿Ronda? |
| `NIVEL 1`, `NIVEL 2`, `NIVEL 3` | ¿Playoff por nivel en cada zona? ¿El número es el **nivel** competitivo? |
| `NIVEL NORTE 2A`, `SUR 2B`, `OESTE 2A`, etc. | ¿Nivel=2, zona=NORTE, grupo=A/B/C? |
| `FINAL FOUR 1`, `FINAL FOUR 2`, `FINAL FOUR 3` | ¿Un F4 por nivel (1/2/3)? ¿O por región? |
| `INTERCONFERENCIA A`, `INTERCONFERENCIA B`, `INTERCONFERENCIAS` | ¿Fase Playoff? ¿Nivel INTERCONFERENCIA A/B? |
| `PLAY OFF INTERCONFERENCIA A` | ¿Playoff + ronda según jornada? |
| `TRIANGULAR FINAL` | ¿Qué fase y ronda? |
| `NORTE AB/OESTE AB` | ¿Playoff entre subzonas? |

---

## Temporada 2026 — textos en GES

| Texto en GES | ¿Cómo mapearlo? |
|--------------|-----------------|
| `TORNEO DE CLASIFICACION` | ¿Fase regular (nivelación inicial)? ¿Ronda `1RA FASE`? |
| `TORNEO RECLASIFICATORIO` / `TORNEO RECLASIFICACION` | ¿Misma fase u playoff de permanencia? |
| `1ER ENCUENTRO`, `2do ENCUENTRO` (Liga Próximo) | ¿Encuentros del año calendario = fase regular? |

---

## Preguntas generales (para cerrar el modelo)

1. **Categorías del informe:** ¿Solo Cadetes, Infantiles, Juveniles (+ Preinfantiles)? ¿Excluimos Mini, Premini, Liga Próximo, Mosquitos?

2. **Modelo de 3 campos:** ¿Confirmás que querés siempre?
   - `fase` ∈ {Fase Regular, Playoff, Final Four, …}
   - `ronda` ∈ {1RA FASE, 2DA FASE, CUARTOS, SEMIFINAL, FINAL, …}
   - `nivel` ∈ {1, 2, 3, NIVELACION, INTERCONFERENCIA A, …}

3. **2025 — “2do SEMESTRE”:** ¿Reemplaza a playoff del 1.er semestre o es la continuación de la fase regular?

4. **2026:** ¿El flujo es solo Clasificación → Reclasificatorio → (después) encuentros por nivel, o hay más fases ya publicadas en GES que aún no tienen partidos cargados?

5. **Zona en grupos:** En `1er ETAPA LFF`, los grupos vienen como `CENTRO 4`, `SUR 6`. ¿La zona se toma del prefijo y el número es el **grupo** dentro de la zona?

6. **Partidos sin resultado en GES:** Muchas URLs de fase/grupo no tienen tabla de partidos aún. ¿El informe debe contar solo partidos **jugados** (con marcador) o también fixture programado?

---

Respondé con una tabla o frases del tipo: `FINAL FOUR 2 → fase=Final Four, nivel=2, ronda=según jornada`.
