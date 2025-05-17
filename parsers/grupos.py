# -*- coding: utf-8 -*-
"""
Parseadores de texto de grupos (DDLGrupos) para torneos FEBAMBA.
Cada año tiene estructuras distintas, con reglas específicas de parseo.
"""

import re
from typing import Dict
from mapeos.loader import normalizar_equipo


def parsear_grupo(year: int, fase_text: str, grupo_text: str) -> Dict[str, str]:
    """
    Parseo del texto de Grupo para obtener nivel, zona y grupo normalizados.

    Args:
        year (int): Año del torneo (2019, 2022, 2023, 2024)
        fase_text (str): Texto seleccionado en DDLFases
        grupo_text (str): Texto seleccionado en DDLGrupos

    Returns:
        Dict[str, str]: Diccionario con nivel, zona y grupo
    """

    if not grupo_text:
        return {"nivel": "Desconocido", "zona": "Desconocido", "grupo": "Desconocido"}

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
            "zona": "Desconocido",
            "grupo": grupo_text_upper,
        }


# ----------------------------------------------------------------
# Parsers por Año
# ----------------------------------------------------------------


def _parsear_grupo_2019(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "Desconocido", "Desconocido", "Desconocido"

    if "1RA FASE" in fase:
        match = re.search(r"CONFERENCIA\s+([A-Z]+?)\s*(\d)\s*([A-Z])", grupo)
        if match:
            zona, nivel, grupo_final = match.group(1), match.group(2), match.group(3)
    elif "CONFERENCIA" in fase and "2DA FASE" in fase:
        match = (
            re.search(r"ZONA\s+([A-Z]+)\s+([A-Z])\s+(\d)", grupo)  # ZONA SUR A 3
            or re.search(r"ZONA\s+([A-Z])\s+([A-Z]+)\s+(\d)", grupo)  # ZONA A SUR 3
            or re.search(r"ZONA\s+([A-Z]+)\s+(\d)", grupo)  # ZONA SUR 3
            or re.search(r"ZONA\s+(\d)\s+([A-Z]+)", grupo)  # ZONA 3 SUR
        )

        if match:
            g1, g2, *rest = match.groups()

            if len(rest) == 1:
                g3 = rest[0]
                # Casos ZONA SUR 3 o ZONA 3 SUR
                if g1.isdigit():  # ZONA 3 SUR
                    nivel = g1
                    zona = g2
                elif g3.isdigit():  # ZONA SUR 3
                    nivel = g3
                    zona = g1
                else:
                    zona = nivel = grupo_final = "Desconocido"
                grupo_final = "Desconocido"

            elif len(rest) == 2:
                g3 = rest[0]
                # Casos ZONA SUR A 3 o ZONA A SUR 3
                if g1.isalpha() and len(g1) > 1:  # Ej: SUR
                    zona = g1
                    grupo_final = g2
                else:
                    grupo_final = g1
                    zona = g2
                nivel = g3

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
            grupo_final = "UNICA"
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
        grupo_final = grupo

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final}


def _parsear_grupo_2023(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "Desconocido", "Desconocido", "Desconocido"

    if "FASE REGULAR" in fase:
        match = re.search(r"(\w+)\s*(\d)?[”\"]?([A-Z])?[”\"]?", grupo)
        if match:
            zona = match.group(1)
            nivel = match.group(2) if match.group(2) else "Desconocido"
            grupo_final = match.group(3) if match.group(3) else "UNICO"
    elif "CONFERENCIA" in fase:
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
    elif "INTERCONFERENCIAS" in fase:
        match = re.search(r"ZONA\s+([A-Z])", grupo)
        if match:
            nivel = "INTERCONFERENCIA"
            zona = "INTERCONFERENCIA"
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


def _parsear_grupo_2025(fase: str, grupo: str) -> Dict[str, str]:
    nivel, zona, grupo_final = "NIVELACION", "Desconocido", "Desconocido"

    if "1ER ETAPA" in fase:
        # Extraer zona y grupo: ej. "CENTRO OESTE 4", "SUR 6"
        match = re.search(r"([A-ZÑ\s\-]+?)\s*(\d+)$", grupo)
        if match:
            zona = match.group(1).strip().replace("  ", " ")
            grupo_final = match.group(2)

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final}



def construir_nombre_llave(local: str, visitante: str) -> str:
    """
    Construye el nombre de un grupo tipo llave eliminatoria (Playoffs o Final Four).

    Args:
        local (str): Nombre crudo del equipo local.
        visitante (str): Nombre crudo del equipo visitante.

    Returns:
        str: Nombre normalizado del grupo en formato '{Local}-{Visitante}'.
    """
    local_norm = normalizar_equipo(local)
    visitante_norm = normalizar_equipo(visitante)
    return f"{local_norm}-{visitante_norm}"
