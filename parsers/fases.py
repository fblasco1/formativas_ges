# -*- coding: utf-8 -*-
"""
Parseadores de texto de fases para torneos FEBAMBA.
Cada año tiene una estructura de torneo distinta y se parsea respetando reglas específicas.
"""

import re
from typing import Dict


def parsear_fase(year: int, fase_text: str) -> Dict[str, str]:
    """
    Parseo del texto de Fase para obtener fase, ronda, nivel y zona normalizados.

    Args:
        year (int): Año del torneo (2019, 2022, 2023, 2024)
        fase_text (str): Texto original de la fase (tal como viene del HTML)

    Returns:
        Dict[str, str]: Diccionario con fase, ronda, nivel y zona
    """

    fase_mapa = "Desconocida"
    ronda_mapa = "Desconocida"
    nivel_mapa = "Desconocido"
    zona_mapa = "Desconocida"

    fase_text_upper = fase_text.upper().strip()

    try:
        if year == 2019:
            # 2019
            if any(
                x in fase_text_upper
                for x in [
                    "SUR 1RA FASE",
                    "CENTRO 1RA FASE",
                    "NORTE 1RA FASE",
                    "OESTE 1RA FASE",
                ]
            ):
                fase_mapa = "Fase Regular"
                ronda_mapa = "1ra Fase"
            elif "CONFERENCIA" in fase_text_upper and "2DA FASE" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"

                match = re.search(r"CONFERENCIA\s*(\d+)\s*([A-Z]+)", fase_text_upper)
                if match:
                    nivel_mapa = match.group(1)
                    zona_mapa = match.group(2)
            elif (
                "CONFERENCIA" in fase_text_upper
                and "FINAL" in fase_text_upper
                and "FINAL CONFERENCIA" not in fase_text_upper
                and "FINAL INTERCONFERENCIA" not in fase_text_upper
                and "FINALES INTERCONFERENCIAS" not in fase_text_upper
                and "FINAL INTERONFERENCIAS" not in fase_text_upper
            ):
                # Casos como: "CONFERENCIA 3 SUR FINAL" o "CONFERENCIA SUR 2 FINAL"
                fase_mapa = "Fase Regular"
                ronda_mapa = "3ra Fase"
                match_1 = re.search(
                    r"CONFERENCIA\s+(\d)\s+([A-Z]+)\s+FINAL", fase_text_upper
                )
                match_2 = re.search(
                    r"CONFERENCIA\s+([A-Z]+)\s+(\d)\s+FINAL", fase_text_upper
                )
                if match_1:
                    nivel_mapa, zona_mapa = match_1.group(1), match_1.group(2)
                elif match_2:
                    zona_mapa, nivel_mapa = match_2.group(1), match_2.group(2)
                else:
                    nivel_mapa = zona_mapa = "Desc"

            elif "INTERCONFERENCIA" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"
            elif "DESEMPATE" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"
            elif "ESTIMULO" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "Estimulo"
                nivel_mapa = 3
                if "CENTRO" in fase_text_upper:
                    zona_mapa = "CENTRO"
                elif "NORTE/CENTRO" in fase_text_upper:
                    zona_mapa = "NORTE"
                elif "OESTE" in fase_text_upper:
                    zona_mapa = "OESTE"
            elif "OCTAVOS DE FINAL" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Octavos de Final"
                if re.fullmatch(r"OCTAVOS DE FINAL", fase_text_upper.strip()):
                    nivel_mapa = "INTERCONFERENCIA"
                    zona_mapa = "INTERCONFERENCIA"
                else:
                    nivel_mapa, zona_mapa = _parsear_nivel_zona_playoffs_2019(
                        fase_text_upper
                    )
            elif "CUARTOS DE FINAL" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Cuartos de Final"
                if re.fullmatch(r"CUARTOS DE FINAL", fase_text_upper.strip()):
                    nivel_mapa = "INTERCONFERENCIA"
                    zona_mapa = "INTERCONFERENCIA"
                else:
                    nivel_mapa, zona_mapa = _parsear_nivel_zona_playoffs_2019(
                        fase_text_upper
                    )
            elif "CURTOS DE FINA CONF 1 NORTE" == fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Cuartos de Final"
                nivel_mapa = "1"
                zona_mapa = "NORTE"
            elif "CUARTOS DE FINA CONF 2 CENTRO" == fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Cuartos de Final"
                nivel_mapa = "2"
                zona_mapa = "CENTRO"
            elif "SEMIFINALES" in fase_text_upper or "SEMFINALES" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Semifinal"
                nivel_mapa, zona_mapa = _parsear_nivel_zona_playoffs_2019(
                    fase_text_upper
                )
            elif "FINAL CONFERENCIA" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Final"
                nivel_mapa, zona_mapa = _parsear_nivel_zona_playoffs_2019(
                    fase_text_upper
                )
            elif "FINALES INTERCONFERENCIAS" in fase_text_upper:
                fase_mapa = "FINAL FOUR"
                ronda_mapa = "Semifinal"
                match = re.search(r"FINALES INTERCONFERENCIAS\s*(\d+)", fase_text_upper)
                if match:
                    nivel_mapa = match.group(1)
                else:
                    nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"

            elif "FINAL INTERCONFERENCIAS" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Semifinal"
                match = re.search(r"FINAL INTERCONFERENCIAS\s*(\d+)", fase_text_upper)
                if match:
                    nivel_mapa = match.group(1)
                else:
                    nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"

            elif (
                "FINAL INTERCONFERENCIA" in fase_text_upper
                or "FINAL INTERONFERENCIAS" in fase_text_upper
            ):
                fase_mapa = "FINAL FOUR"
                ronda_mapa = "Final"
                match = re.search(r"FINAL INTERCONFERENCIA\S*\s*(\d+)", fase_text_upper)
                if match:
                    nivel_mapa = match.group(1)
                else:
                    nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"

        elif year == 2022:
            # 2022
            if (
                "FASE DE CLASIFICACION" in fase_text_upper
                or "FASE CLASIFICACION" in fase_text_upper
            ):
                fase_mapa = "Fase Regular"
                ronda_mapa = "1ra Fase"
                nivel_search = re.search(r"CLASIFICACION\s*(\d+)", fase_text_upper)
                if nivel_search:
                    nivel_mapa = nivel_search.group(1)
            elif "CUARTOS NIVEL 3" == fase_text_upper:
                fase_mapa = "Playoff"
                nivel_mapa = "3"
                zona_mapa = "CENTRO"
            elif "ANEXO NIVEL" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                zona_mapa = "CENTRO"
                nivel_search = re.search(r"NIVEL\s*(\d+)", fase_text_upper)
                if nivel_search:
                    nivel_mapa = nivel_search.group(1)
            elif "NIVEL" in fase_text_upper and "FASE" not in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                nivel_search = re.search(r"NIVEL\s*(\d+)", fase_text_upper)
                if nivel_search:
                    nivel_mapa = nivel_search.group(1)
            elif "INTERCONFERENCIAS" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"
            elif "PLAY OFF" in fase_text_upper:
                fase_mapa = "Playoff"
            elif "FINAL FOUR" in fase_text_upper:
                fase_mapa = "FINAL FOUR"

        elif year == 2023:
            # 2023
            if "FASE REGULAR" == fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "1ra Fase"
            elif "INTERCONFERENCIAS" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                nivel_mapa = "INTERCONFERENCIA"
                zona_mapa = "INTERCONFERENCIA"
            elif (
                "CONFERENCIA" in fase_text_upper
                and "CUARTOS DE FINAL " in fase_text_upper
            ):
                fase_mapa = "Playoff"
                nivel_mapa, zona_mapa = _parsear_nivel_zona_playoffs_2023(
                    fase_text_upper
                )
            elif "CONFERENCIA" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"

                # Buscar el nivel como antes
                nivel_search = re.search(r"CONFERENCIA\s*(\d+)", fase_text_upper)
                if nivel_search:
                    nivel_mapa = nivel_search.group(1)

                # Nuevas expresiones para zona y grupo base
                # Ej: CONFERENCIA 3 SUR A
                match_ext1 = re.search(
                    r"CONFERENCIA\s*\d+\s+([A-Z]+)\s+([A-Z])", fase_text_upper
                )
                # Ej: CONFERENCIA SUR 3 B
                match_ext2 = re.search(
                    r"CONFERENCIA\s+([A-Z]+)\s+(\d+)\s+([A-Z])", fase_text_upper
                )
                # Ej: CONFERENCIA 3 SUR
                match_simple1 = re.search(
                    r"CONFERENCIA\s*\d+\s+([A-Z]+)", fase_text_upper
                )
                # Ej: CONFERENCIA SUR 3
                match_simple2 = re.search(
                    r"CONFERENCIA\s+([A-Z]+)\s+\d+", fase_text_upper
                )

                if match_ext1:
                    zona_mapa = match_ext1.group(1)
                    grupo_mapa_base = match_ext1.group(2)
                elif match_ext2:
                    zona_mapa = match_ext2.group(1)
                    nivel_mapa = match_ext2.group(2)
                    grupo_mapa_base = match_ext2.group(3)
                elif match_simple1:
                    zona_mapa = match_simple1.group(1)
                elif match_simple2:
                    zona_mapa = match_simple2.group(1)

            elif "CONF 3 INTERZONALES" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
                nivel_mapa = 3
                zona_mapa = "CENTRO"

            elif "OCTAVOS DE FINAL" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Octavos de Final"
            elif "CUARTOS DE FINAL" in fase_text_upper:
                fase_mapa = "Playoff"

                # Normalizar errores frecuentes
                fase_text_upper = fase_text_upper.replace(
                    "OESTE", "OESTE"
                )  # prevenir 0ESTE
                fase_text_upper = re.sub(
                    r"[^A-Z0-9\s]", " ", fase_text_upper
                )  # limpiar signos raros

                # Buscar estructuras tipo: "CUARTOS DE FINAL - NORTE 1", "CUARTOS DE FINAL 2 CENTRO"
                match = re.search(
                    r"CUARTOS DE FINAL\s*(?:-)?\s*(\d)?\s*([A-Z]+)", fase_text_upper
                )
                if match:
                    nivel_mapa = match.group(1) if match.group(1) else None
                    zona_mapa = match.group(2)

            elif "SEMIFINAL" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Semifinal"

        elif year == 2024:
            # 2024
            if "1ER ETAPA" in fase_text_upper and "2DA" not in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "1ra Fase"
            elif "1ER ETAPA 2DA FASE" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "2da Fase"
            elif "FASE FINAL" in fase_text_upper:
                fase_mapa = "Fase Regular"
                ronda_mapa = "3ra Fase"
            elif "RECLASIFICACION" in fase_text_upper:
                fase_mapa = "Fase Regular"
                nivel_mapa = 3
                ronda_mapa = "3ra Fase"
                if "NORTE" in fase_text_upper:
                    zona_mapa = "NORTE" 
            elif "INTERCONFERRENCIAS B" in fase_text_upper:
                fase_mapa = "Playoff"
                nivel_mapa = "INTERCONFERENCIA B"
                zona_mapa = "INTERCONFERENCIA"
            elif "NIVEL 1 NORTE SEMIFINALES" == fase_text_upper:
                fase_mapa = "Playoff"
                nivel_mapa = 1
                zona_mapa = "NORTE"
            elif "PLAY IN" in fase_text_upper or "PLAY INN" in fase_text_upper:
                fase_mapa = "Playoff"
                ronda_mapa = "Play In"
                if "NIVEL 2" in fase_text_upper:
                    nivel_mapa = 2
            elif "PLAY OFF" in fase_text_upper:
                fase_mapa = "Playoff"
                if "-NIVEL 2" in fase_text_upper:
                    nivel_mapa = 2
                if "NIVEL 1" in fase_text_upper:
                    nivel_mapa = 1
                if "INTERCONFERENCIAS A" in fase_text_upper:
                    nivel_mapa = "INTERCONFERENCIA A"
                    zona_mapa = "INTERCONFERENCIA"
            elif "SEMIFINAL" in fase_text_upper:
                fase_mapa = "Playoff"
            elif "SEMIFIANL NIVEL 1 SUR" == fase_text_upper:
                fase_mapa = "Playoff"
                nivel_mapa = 1
                zona_mapa = "SUR"
        elif year == 2025:
            # 2025
            if "1ER ETAPA" in fase_text_upper:
                fase_mapa =  "Fase Regular"
                ronda_mapa = "Copa Febamba"
                nivel_mapa = "NIVELACION"

    except Exception as e:
        print(f"Error parseando fase '{fase_text}': {e}")

    return {
        "fase": fase_mapa,
        "ronda": ronda_mapa,
        "nivel": nivel_mapa,
        "zona": zona_mapa,
    }


def _parsear_nivel_zona_playoffs_2019(text: str) -> tuple[str, str]:
    text = text.replace(".", "").upper().strip()

    # Corrección de errores tipográficos frecuentes
    text = text.replace("CURTOS", "CUARTOS")
    text = text.replace("CUARTOS DE FINA", "CUARTOS DE FINAL")
    text = text.replace("CONF1", "CONF 1").replace(
        "CONF2", "CONF 2"
    )  # para casos sin espacio
    text = re.sub(r"CONF\s*(\d)", r"CONF \1", text)  # normaliza CONF1 → CONF 1

    # Extraer nivel (ej. CONF 1, CONF 2, etc.)
    match_nivel = re.search(r"CONF\s*(\d)", text)
    if match_nivel:
        nivel = match_nivel.group(1)
    elif "CONF" in text:
        nivel = "1"  # fallback si aparece CONF sin número

    # Extraer zona
    zonas = ["SUR", "CENTRO", "NORTE", "OESTE"]
    for z in zonas:
        if z in text:
            zona = z
            break

    # Fallback para casos donde no se encuentra nada explícito
    if not nivel or not zona:
        if "INTERCONFERENCIA" in text:
            nivel = zona = "INTERCONFERENCIA"

    return nivel, zona


def _parsear_nivel_zona_playoffs_2023(texto: str) -> tuple[str, str]:
    texto = texto.upper().replace(".", " ").replace("-", " ").replace("  ", " ")
    texto = texto.strip()

    # Nivel
    nivel = None
    zona = None

    match_nivel = re.search(r"\b(\d)\b", texto)
    if match_nivel:
        nivel = match_nivel.group(1)

    for z in ["SUR", "CENTRO", "NORTE", "OESTE"]:
        if z in texto:
            zona = z
            break

    if "INTERCONFERENCIA" in texto:
        return "INTERCONFERENCIA", "INTERCONFERENCIA"

    return nivel or "Desconocido", zona or "Desconocida"
