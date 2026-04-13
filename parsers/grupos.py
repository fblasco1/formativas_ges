# -*- coding: utf-8 -*-
"""
Parseadores de texto de grupos (DDLGrupos) para torneos FEBAMBA.
Cada año tiene estructuras distintas, con reglas específicas de parseo.
"""

import re
from typing import Any, Dict

from parsers.grupos_2025 import parsear_grupo_2025 as _parsear_grupo_2025


def parsear_grupo(year: int, fase_text: str, grupo_text: str) -> Dict[str, Any]:
    """
    Parseo del texto de Grupo para obtener nivel, zona y grupo normalizados.

    Args:
        year (int): Año del torneo (2019, 2022, 2023, 2024)
        fase_text (str): Texto seleccionado en DDLFases
        grupo_text (str): Texto seleccionado en DDLGrupos

    Returns:
        Dict con nivel, zona, grupo; en 2025 puede incluir fase, zona_refina, nivel_refina.
    """

    if not grupo_text:
        return {
            "nivel": "Desconocido",
            "zona": "Desconocida",
            "grupo": "Desconocido",
        }

    fase_text_upper = fase_text.upper().strip()
    grupo_text_upper = grupo_text.upper().strip()

    if year == 2019:
        return _parsear_grupo_2019(fase_text_upper, grupo_text_upper)
    elif year == 2022:
        return _parsear_grupo_2022(fase_text_upper, grupo_text_upper)
    elif year == 2023:
        return _parsear_grupo_2023(fase_text_upper, grupo_text_upper)
    elif year == 2024:
        return _parsear_grupo_2024(fase_text_upper, grupo_text_upper)
    elif year == 2025:
        return _parsear_grupo_2025(fase_text_upper, grupo_text_upper)
    else:
        return {
            "nivel": "Desconocido",
            "zona": "Desconocida",
            "grupo": grupo_text_upper,
        }


# ----------------------------------------------------------------
# Parsers por Año
# ----------------------------------------------------------------


def _parsear_grupo_2019(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "Desconocido", "Desconocida", "Desconocido"

    if "1RA FASE" in fase:
        # Caso: CONFERENCIA NORTE 1 A
        match = re.search(r"CONFERENCIA\s+([A-Z]+)\s+(\d)\s*([A-Z])", grupo)
        if not match:
            # Caso: CONFERENCIA NORTE1A o CONFERENCIA NORTE1 B (sin espacio entre número y letra)
            match = re.search(r"CONFERENCIA\s+([A-Z]+)(\d)\s*([A-Z])", grupo)
        if match:
            zona_extraida, nivel, grupo_final = match.group(1), match.group(2), match.group(3)
            if zona == "Desconocida":
                zona = zona_extraida
    elif "CONFERENCIA" in fase and "2DA FASE" in fase:
        # Caso: ZONA [GRUPO] [ZONA] [NIVEL]
        match = re.match(r"ZONA\s+([A-Z])\s+([A-Z]+)\s+(\d)", grupo)
        if match:
            grupo_final = match.group(1)
            zona = match.group(2)
            nivel = match.group(3)
        else:
            # Si el grupo es una sola letra y la zona es más de una letra, invertir
            match = re.match(r"ZONA\s+([A-Z]+)\s+([A-Z])\s+(\d)", grupo)
            if match:
                zona = match.group(1)
                grupo_final = match.group(2)
                nivel = match.group(3)
            else:
                # ZONA SUR A 2 -> zona=SUR, grupo_final=A, nivel=2
                match = re.match(r"ZONA\s+([A-Z]+)\s+([A-Z])\s+(\d)", grupo)
                if match:
                    zona = match.group(1)
                    grupo_final = match.group(2)
                    nivel = match.group(3)
                else:
                    # ZONA SUR 3 -> zona=SUR, grupo_final=UNICO, nivel=3
                    match = re.match(r"ZONA\s+([A-Z]+)\s+(\d)", grupo)
                    if match:
                        zona = match.group(1)
                        grupo_final = "UNICO"
                        nivel = match.group(2)
                    else:
                        match = (
                            re.search(r"ZONA\s+(\d)\s+([A-Z]+)", grupo)  # ZONA 3 SUR
                        )
                        if match:
                            zona = match.group(2)
                            grupo_final = "UNICO"
                            nivel = match.group(1)
    elif "CONFERENCIA" in fase and "FINAL" in fase:
        # caso: ZONA A
        match = re.search(r"ZONA\s+([A-Z])", grupo)
        if match:
            grupo_final = match.group(1)
    elif "INTERCONFERENCIA" in fase:
        match = re.search(r"ZONA\s+([A-Z])", grupo)
        if match:
            nivel = "INTERCONFERENCIA"
            zona = "INTERCONFERENCIA"
            grupo_final = match.group(1)
            
    return {"nivel": nivel, "zona": zona, "grupo": grupo_final}


def _parsear_grupo_2022(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "Desconocido", "Desconocido", "Desconocido"

    if "CLASIFICACION" in fase:
        match = re.search(r"(\w+)\s*(\d)([A-Z])?", grupo)
        if match:
            zona, nivel = match.group(1), match.group(2)
            grupo_final = match.group(3) if match.group(3) else "UNICO"
    elif "NIVEL" in fase:
        if "SUR UNICA" == grupo or "ZONA UNICA" == grupo:
            zona = "SUR"
            grupo_final = "UNICO"
        else:
            match = re.search(r"(\w+)\s*ZONA\s+([A-Z]+)", grupo)
            if match:
                zona, grupo_final = match.group(1), match.group(2)
    elif "INTERCONFERENCIAS" in fase:
        match = re.search(r"ZONA\s+([A-Z])", grupo)
        if match:
            nivel = "INTERCONFERENCIA"
            zona = "INTERCONFERENCIA"
            grupo_final = match.group(1)
    elif "PLAY OFF" in fase:
        if "INTERCONFERENCIA" in grupo:
            zona = "INTERCONFERENCIA"
            nivel = "INTERCONFERENCIA"
        else:
            match = re.search(r"([A-Z]+)\s+(\d)", grupo)
            if match:
                zona = match.group(1)
                nivel = match.group(2)
    elif "FINAL FOUR" in fase:
        zona = "INTERCONFERENCIA"

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final}


def _parsear_grupo_2023(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "Desconocido", "Desconocido", "Desconocido"
    
    if "FASE REGULAR" in fase:
        match = re.search(r"(\w+)\s*(\d)?[”\"]?([A-Z])?[”\"]?", grupo)
        if match:
            zona = match.group(1)
            nivel = match.group(2) if match.group(2) else "Desconocido"
            grupo_final = match.group(3) if match.group(3) else "UNICO"
    if "CONFERENCIA" in fase:
        # Correcciones específicas
        grupo = grupo.replace("0ESTE", "OESTE")

        # Casos como NORTE 1"A", limpiar comillas dobles o triples
        grupo = re.sub(r'"+', "", grupo)

        # CONFERENCIA con OCTAVOS DE FINAL y zona simple
        if "OCTAVOS DE FINAL" in fase:
            zonas_posibles = ["NORTE", "SUR", "CENTRO", "OESTE"]
            if grupo == "CENTRO 1":
                zona = "CENTRO"
                nivel = (
                    fase.split("CONFERENCIA")[1].strip().split()[0]
                )  # Ej: "1" de "CONFERENCIA 1 OCTAVOS DE FINAL"
                grupo_final = "UNICO"
            for z in zonas_posibles:
                if grupo == z:
                    zona = z
                    nivel = (
                        fase.split("CONFERENCIA")[1].strip().split()[0]
                    )  # Ej: "1" de "CONFERENCIA 1 OCTAVOS DE FINAL"
                    grupo_final = "UNICO"
        else:
            # Casos como CONFERENCIA 3, grupo: CENTRO A, CENTRO B, OESTE, SUR A
            match = re.match(r"([A-Z]+)\s*(\d*)\s*([A-Z]?)", grupo)
            if match:
                posible_zona, posible_nivel, posible_grupo = match.groups()
                zonas_validas = {"NORTE", "SUR", "CENTRO", "OESTE"}

                if posible_zona in zonas_validas:
                    zona = posible_zona
                    nivel = (
                        posible_nivel
                        if posible_nivel
                        else fase.split("CONFERENCIA")[1].strip().split()[0]
                    )
                    grupo_final = posible_grupo if posible_grupo else "UNICO"

            # Casos como NORTE1A o CENTRO2B pegados
            match = re.match(r"([A-Z]+)(\d)([A-Z])$", grupo)
            if match:
                zona, nivel, grupo_final = match.groups()

            # Casos como NORTE1 sin grupo final
            match = re.match(r"([A-Z]+)(\d)$", grupo)
            if match:
                zona, nivel = match.groups()
                grupo_final = "UNICO"
    if "INTERCONFERENCIAS" == fase:
        match = re.search(r"ZONA\s+([A-Z])", grupo)
        if match:
            grupo_final = match.group(1)

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final}


def _parsear_grupo_2024(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "Desconocido", "Desconocido", "Desconocido"

    fase = fase.upper().strip()
    grupo = grupo.upper().strip()

    # 🔧 Normalización: comillas dobles => comilla simple
    grupo = grupo.replace('""', '"').replace("“", '"').replace("”", '"')
    grupo = re.sub(r'\s+', ' ', grupo).strip()

    if "RECLASIFICACION FLEX" in fase:
            nivel = 3
            match = re.search(r"([A-Z]+)\s*['”]?([A-Z\d])['”]?", grupo)
            if match:
                zona = match.group(1)
                grupo_final = match.group(2)
                if grupo_final == "1":
                    grupo_final = "A"
                elif grupo_final == "2":
                    grupo_final = "B"

    # FASE FINAL con INTERCONFERENCIAS
    if "FASE FINAL" in fase:
        # Caso RECLASIFICACION FLEX → NIVEL 3
        if "RECLASIFICACION FLEX" in grupo:
            nivel = "3"
            match = re.search(r"RECLASIFICACION FLEX ([A-ZÑÁÉÍÓÚÜ\-]+)\s+['”]?([A-Z])['”]?$", grupo)
            if match:
                zona = match.group(1)
                grupo_final = match.group(2)
                if grupo_final == "1":
                    grupo_final = "A"
                elif grupo_final == "2":
                    grupo_final = "B"
        elif "INTERCONFERENCIA" in grupo:
            match = re.search(r"INTERCONFER+ENCIAS?\s*([A-B])\s*ZONA\s*\"?([A-Z])\"?", grupo)
            if match:
                nivel = f"INTERCONFERENCIA {match.group(1)}"
                zona = "INTERCONFERENCIA"
                grupo_final = match.group(2)
        else:
            match = re.search(r'NIVEL\s*(\d)\s*([A-ZÑÁÉÍÓÚÜ\-]+)\s*(?:LFF)?\s*"?([A-Z])"?$', grupo)
            if match:
                nivel = match.group(1)
                zona = match.group(2)
                grupo_final = match.group(3)
            elif "UNICA" in grupo:
                match = re.search(r"NIVEL\s*(\d)\s*(\w+)\s*UNICA", grupo)
                if match:
                    nivel = match.group(1)
                    zona = match.group(2)
                    grupo_final = "UNICO"

    # Primera etapa sin "2DA"
    elif "1ER ETAPA" in fase and "2DA" not in fase:
        match = re.search(r'NIVEL\s*(\d)\s*([A-ZÑÁÉÍÓÚÜ\-]+)\s*(?:LFF)?\s*"?([A-Z])"?$', grupo)
        if match:
            nivel = match.group(1)
            zona = match.group(2)
            grupo_final = match.group(3)

    # 🔴 Segunda fase dentro de 1ER ETAPA
    if "1ER ETAPA" in fase and "2DA" in fase:
        match = re.search(r"NIVEL\s*(\d)\s*([A-ZÑ\-]+)\s*([A-Z])-([A-Z])", grupo)
        if match:
            nivel = match.group(1)
            zona = match.group(2)
            grupo_final = f"{match.group(3)}-{match.group(4)}"
        elif re.search(r'\b"?[A-Z]"?\b$', grupo):  # detectar grupo entre comillas o letra final
            match = re.search(r'NIVEL\s*(\d)\s+([A-ZÑ\-]+)\s+"?([A-Z])"?$', grupo)
            if match:
                nivel = match.group(1)
                zona = match.group(2)
                grupo_final = match.group(3)
        else:
            match = re.search(r"NIVEL\s*(\d)\s*([A-ZÑ\-]+)(?:\s*LFF)?", grupo)
            if match:
                nivel = match.group(1)
                zona = match.group(2)
                grupo_final = "A-B"
    
    elif "PLAY OFF" in fase or "PLAY IN" in fase or "PLAY INN" in fase:
        match = re.search(r"INTERCONFERENCIAS?\s*([AB])", grupo)
        if match:
            nivel = f"INTERCONFERENCIA {match.group(1)}"
            zona = "INTERCONFERENCIA"
            zona_match = re.search(r"ZONA\s*['”]?([A-Z])['”]?", grupo)
            if zona_match:
                grupo_final = zona_match.group(1)
            else:
                grupo_final = "Desconocido"
        elif re.search(r"NIVEL\s*(\d)\s*([A-ZÑ\-]+)", grupo):
            match = re.search(r"NIVEL\s*(\d)\s*([A-ZÑ\-]+)", grupo)
            if match:
                nivel = match.group(1)
                zona = match.group(2)
        else:
            # Corrección de errores comunes
            grupo_normalizado = grupo.replace("0ESTE", "OESTE")
            grupo_normalizado = grupo_normalizado.replace("CENTROB", "CENTRO-NORTE")
            grupo_normalizado = grupo_normalizado.replace("B/NORTE", "CENTRO-NORTE")  # si viene separado
            grupo_normalizado = grupo_normalizado.replace("/", "-")
            match = re.search(r"([A-ZÑÁÉÍÓÚÜ\-]+)\s+([A-Z](?:-[A-Z])?)", grupo)
            if match:
                zona = match.group(1).strip()
                grupo_final = match.group(2).strip()

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final}