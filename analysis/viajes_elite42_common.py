# -*- coding: utf-8 -*-
"""Utilidades compartidas para el informe de viajes élite 42 (tabla general de tiras)."""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
REF_XLSX = ROOT / "data" / "referencia" / "AFILIADAS y DIRECCIONES.xlsx"
STANDINGS_HTML = ROOT / "outputs" / "formativas_2026" / "tabla_posiciones.html"
OUT_DIR = ROOT / "outputs" / "viajes_elite42"
ELITE42_CSV = OUT_DIR / "elite42.csv"
MAPEO_CSV = OUT_DIR / "mapeo_clubes.csv"
GEOJSON = OUT_DIR / "clubes_geocodificados.json"

# Alias manual: clave_equipo (standings) -> substring que debe aparecer en AFILIADA normalizada.
_ALIAS_FEDERACION: Dict[str, str] = {
    "FERROCARRIL OESTE VERDE": "FERROCARRIL OESTE",
    "FERROCARRIL OESTE BLANCO": "FERROCARRIL OESTE",
    "3 DE FEBRERO BLANCO A": "3 DE FEBRERO",
    "BOCA JUNIORS AZUL A": "BOCA JUNIORS",
    "RIVER PLATE": "RIVER PLATE",
    "SAN LORENZO AZUL": "SAN LORENZO",
    "VELEZ SARSFIELD BLANCO A": "VELEZ",
    "GIMNASIA Y ESGRIMA LA PLATA A": "GIMNASIA Y ESGRIMA LA PLATA",
    "GIMNASIA Y ESGRIMA DE LOMAS DE ZAMORA": "GIMNASIA Y ESGRIMA LOMAS",
    "CIUDAD DE BUENOS AIRES A AZUL": "CIUDAD DE BUENOS AIRES",
    "CASA PADUA A": "CASA PADUA",
    "CLUB GEI AZUL A": "GEI",
    "GEVP BLANCO A": "GEVP",
    "NAUTICO HACOAJ BLANCO A": "NAUTICO HACOAJ",
    "INSTITUCION SARMIENTO A VERDE": "INSTITUCION SARMIENTO",
    "SPORTIVO PILAR MINI": "SPORTIVO PILAR",
    "COMUNICACIONES AMARILLO A": "COMUNICACIONES",
    "IMPERIO BLANCO A": "IMPERIO",
    "MORON ROJO A": "MORON",
    "MONTE GRANDE ROJO A": "MONTE GRANDE",
    "ARGENTINO DE CASTELAR NORTE A": "ARGENTINO DE CASTELAR",
    "ESTUDIANTIL PORTENO A": "ESTUDIANTIL PORTENO",
    "ARQUITECTURA NEGRO A": "ARQUITECTURA",
    "JOSE HERNANDEZ A": "JOSE HERNANDEZ",
    "PEDRO ECHAGUE AZUL": "PEDRO ECHAGUE",
    "ATENEO POPULAR VERSAILLES": "ATENEO POPULAR VERSAILLES",
    "INDEPENDIENTE DE BURZACO": "INDEPENDIENTE DE BURZACO",
    "CANUELAS FC": "CANUELAS",
    "BURZACO FC": "BURZACO",
    "UNION FLORIDA": "UNION FLORIDA",
    "PRESIDENTE DERQUI": "PRESIDENTE DERQUI",
    "SPORTIVO ESCOBAR": "SPORTIVO ESCOBAR",
    "CAZA Y PESCA A AZUL": "CAZA Y PESCA",
    "PLATENSE A": "PLATENSE",
    "LANUS A": "LANUS",
    "TEMPERLEY": "TEMPERLEY",
    "ITALIANO": "ITALIANO",
    "PINOCHO": "PINOCHO",
    "OBRAS BASKET": "OBRAS",
    "TRISTAN SUAREZ": "TRISTAN SUAREZ",
    "ALEJANDRO KORN": "ALEJANDRO KORN",
    "VILLA MITRE": "VILLA GENERAL MITRE",
    "IMPERIO BLANCO A": "IMPERIO JUNIORS",
    "MORON ROJO A": "MORON",
}

# Sedes confirmadas manualmente (clave_equipo -> afiliada, dirección, CP).
_SEDE_CONFIRMADA: Dict[str, Tuple[str, str, str]] = {
    "VICTORIA NEGRO": (
        "Victoria",
        "Ingeniero White 1153, Victoria",
        "1644",
    ),

    "BANCO PROVINCIA": (
        "Banco Provincia",
        "Pres. Hipólito Yrigoyen 803, Vicente López",
        "1638",
    ),
    "SOCIEDAD HEBRAICA ARGENTINA": (
        "Sociedad Hebraica Argentina",
        "Av. Sgto Cayetano Beliera 1199, Pilar",
        "1629",
    ),

    "BANCO NACION A AZUL": (
        "Banco Nación",
        "Zufriategui 1251, Vicente López",
        "1638",
    ),
    "3 DE FEBRERO C CELESTE": (
        "Club Tres de Febrero",
        "Islas Malvinas 2681, Villa San Andrés",
        "1651",
    ),
    "VICTORIA BLANCO": (
        "Victoria",
        "Ing. White 1153, Victoria",
        "1644",
    ),

    "MORON A ROJO": (
        "CLUB MORON",
        "Bernardo de Irigoyen 138, Castelar",
        "1708",
    ),
    "INSTITUCION SARMIENTO A VERDE": (
        "INSTITUCION SARMIENTO",
        "Av. La Plata 3434, Santos Lugares",
        "1676",
    ),
    "GEVP A BLANCO": (
        "Gimnasia y Esgrima de Villa del Parque",
        "Tinogasta 3455, Villa del Parque, CABA",
        "1417",
    ),
    "GEVP B CELESTE": (
        "Gimnasia y Esgrima de Villa del Parque",
        "Tinogasta 3455, Villa del Parque, CABA",
        "1417",
    ),
    "3 DE FEBRERO AZUL B": (
        "Club Tres de Febrero",
        "Islas Malvinas 2681, Villa San Andrés",
        "1651",
    ),
    "CAZA Y PESCA B VERDE": (
        "Club Atlético Caza y Pesca",
        "Balbastro Y Ruta 202, Pilar",
        "1611",
    ),
    "INSTITUCION SARMIENTO B BLANCO": (
        "INSTITUCION SARMIENTO",
        "Av. La Plata 3434, Santos Lugares",
        "1676",
    ),
    "PLATENSE A": (
        "Club Platense",
        "Zufriategui 2021, Vicente Lopez",
        "1638",
    ),
    "INDEPENDIENTE DE BURZACO": (
        "Independiente de Burzaco",
        "Carlos Pellegrini 557, Burzaco",
        "1852",
    ),
    "3 DE FEBRERO A BLANCO": (
        "Club Tres de Febrero",
        "Islas Malvinas 2681, Villa San Andrés",
        "1651",
    ),
    "SAN LORENZO AZUL": (
        "San Lorenzo",
        "Av. Varela 2706, Flores, CABA",
        "1416",
    ),
    "NAUTICO HACOAJ A BLANCO": (
        "Náutico Hacoaj",
        "Luis Garcia 943, Tigre",
        "1648",
    ),
    "ALEJANDRO KORN": (
        "Club Social Alejandro Korn",
        "Lombardi 150, Alejandro Korn",
        "1864",
    ),
    "CASA PADUA A": (
        "CASA Padua",
        "Independencia 725, San Antonio de Padua",
        "1718",
    ),
    "TEMPERLEY": (
        "Temperley",
        "Av. 9 de Julio, Lomas de Zamora",
        "1832",
    ),
    "MORON B BLANCO": (
        "CLUB MORON",
        "Bernardo de Irigoyen 138, Castelar",
        "1708",
    ),
    "NAUTICO HACOAJ AZUL B": (
        "Náutico Hacoaj",
        "Luis Garcia 943, Tigre",
        "1648",
    ),
    # Correcciones 2026-07-23
    "SPORTIVO VILLA BALLESTER": (
        "Sportivo Villa Ballester",
        "Gral. Roca 3123, Villa Ballester",
        "1653",
    ),
    "UNION VILLEGAS": (
        "Unión Escalada Villegas",
        "Gral. Villegas 811, Remedios de Escalada",
        "1826",
    ),
    "OLIMPO": (
        "Olimpo",
        "Santiago Plaul 2122, Lanús",
        "1824",
    ),
    "LOBOS": (
        "Lobos Athletic Club",
        "Castelli 60, Lobos",
        "7240",
    ),
    "UNION VECINAL DE MUNRO": (
        "Unión Vecinal de Munro",
        "Armenia 2590, Munro",
        "1605",
    ),
    "INDEPENDIENTE": (
        "Independiente de Avellaneda",
        "Av. Bartolomé Mitre 470, Avellaneda",
        "1870",
    ),
    "EL PORVENIR JOSE PAZ C": (
        "El Porvenir José C. Paz",
        "Av. Pres. Hipólito Yrigoyen 1643, José C. Paz",
        "1660",
    ),
    "CEDEM": (
        "CEDEM 3 de Febrero",
        "Juan Bautista Alberdi 5524, Caseros",
        "1678",
    ),
    "MIDLAND": (
        "Ferrocarril Midland",
        "Av. Eva Perón 4050, Merlo",
        "1716",
    ),
    "ARGENTINO DE CASTELAR CENTRO B": (
        "Argentino de Castelar",
        "Montes de Oca 2242, Castelar",
        "1712",
    ),
    "ARGENTINO DE CASTELAR SUR C": (
        "Argentino de Castelar",
        "Montes de Oca 2242, Castelar",
        "1712",
    ),
    "ATLETICO PILAR": (
        "Atlético Pilar",
        "Ituzaingó 759, Pilar",
        "1629",
    ),
    "COOP DE TORTUGUITAS": (
        "Cooperativa de Tortuguitas",
        "Moreno 1160, Tortuguitas",
        "1667",
    ),
    "SOCIAL LANUS": (
        "Club Social Lanús",
        "Cnel. Pringles 1061, Lanús",
        "1824",
    ),
    "CASA PADUA B": (
        "CASA Padua",
        "Independencia 725, San Antonio de Padua",
        "1718",
    ),
    "RAMOS MEJIA LTC": (
        "Ramos Mejía Lawn Tennis Club",
        "Esteban Echeverría 361, Villa Sarmiento",
        "1707",
    ),
    "SPORTIVO HAEDO": (
        "Sportivo Haedo",
        "Héroes de Malvinas Argentinas 72, Haedo",
        "1706",
    ),
    "IMPERIO B NEGRO": (
        "Imperio Juniors",
        "Gral. César Díaz 3047, CABA",
        "1416",
    ),
    "MUNICAVELLANEDA": (
        "Municipalidad de Avellaneda",
        "Lincoln y Bolívar, Wilde",
        "1875",
    ),
    "SAN LORENZO B ROJO": (
        "San Lorenzo",
        "Av. Varela 2706, Flores, CABA",
        "1416",
    ),
    "BANCO NACION B BLANCO": (
        "Banco Nación",
        "Zufriategui 1251, Vicente López",
        "1638",
    ),
}

# Consulta Nominatim preferida (clave_equipo -> query).
_GEOCODE_QUERY: Dict[str, str] = {
    "BANCO NACION A AZUL": "Zufriategui 1251, Vicente López, Provincia de Buenos Aires, Argentina",
    "3 DE FEBRERO C CELESTE": "Islas Malvinas 2681, Villa San Andrés, Provincia de Buenos Aires, Argentina",
    "VICTORIA BLANCO": "Ingeniero White 1153, Victoria, Buenos Aires",

    "MORON A ROJO": "Bernardo de Irigoyen 138, Castelar, Provincia de Buenos Aires, Argentina",
    "INSTITUCION SARMIENTO A VERDE": "Av. La Plata 3434, Santos Lugares, Provincia de Buenos Aires, Argentina",
    "GEVP A BLANCO": "Tinogasta 3455, Villa del Parque, CABA, Argentina",
    "GEVP B CELESTE": "Tinogasta 3455, Villa del Parque, CABA, Argentina",
    "PLATENSE A": "Zufriategui 2021, Vicente Lopez, Provincia de Buenos Aires, Argentina",
    "INDEPENDIENTE DE BURZACO": "Carlos Pellegrini 557, Burzaco, Provincia de Buenos Aires, Argentina",
    "3 DE FEBRERO A BLANCO": "Islas Malvinas 2681, Villa San Andrés, Provincia de Buenos Aires, Argentina",
    "3 DE FEBRERO AZUL B": "Islas Malvinas 2681, Villa San Andrés, Provincia de Buenos Aires, Argentina",
    "SAN LORENZO AZUL": "Av. Varela 2706, Flores, Ciudad Autónoma de Buenos Aires, Argentina",
    "NAUTICO HACOAJ A BLANCO": "Luis Garcia 943, Tigre, Provincia de Buenos Aires, Argentina",
    "ALEJANDRO KORN": "Lombardi 150, Alejandro Korn, Provincia de Buenos Aires, Argentina",
    "CASA PADUA A": "Independencia 725, San Antonio de Padua, Provincia de Buenos Aires, Argentina",
    "TEMPERLEY": "Av. 9 de Julio, Lomas de Zamora, Provincia de Buenos Aires, Argentina",
    "CAZA Y PESCA B VERDE": "Balbastro Y Ruta 202, Pilar, Provincia de Buenos Aires, Argentina",
    "INSTITUCION SARMIENTO B BLANCO": "Av. La Plata 3434, Santos Lugares, Provincia de Buenos Aires, Argentina",
    "CENTRO GALICIA": "Av Libertador 2925, Buenos Aires, Argentina",
    "VARELA JRS": "Av San Martin 3275, Florencio Varela, Buenos Aires, Argentina",
    "AFALP A": "Geranios, Ciudad Jardin Lomas del Palomar, Buenos Aires, Argentina",
    "YUPANQUI": "Guamini 4512, Lugano, Ciudad Autónoma de Buenos Aires, Argentina",
    "NAUTICO HACOAJ AZUL B": "Luis Garcia 943, Tigre, Provincia de Buenos Aires, Argentina",
    "SPORTIVO VILLA BALLESTER": "Gral. Roca 3123, Villa Ballester, Provincia de Buenos Aires, Argentina",
    "UNION VILLEGAS": "Gral. Villegas 811, Remedios de Escalada, Provincia de Buenos Aires, Argentina",
    "OLIMPO": "Santiago Plaul 2122, Lanús, Provincia de Buenos Aires, Argentina",
    "LOBOS": "Castelli 60, Lobos, Provincia de Buenos Aires, Argentina",
    "UNION VECINAL DE MUNRO": "Armenia 2590, Munro, Provincia de Buenos Aires, Argentina",
    "INDEPENDIENTE": "Av. Bartolomé Mitre 470, Avellaneda, Provincia de Buenos Aires, Argentina",
    "EL PORVENIR JOSE PAZ C": "Av. Pres. Hipólito Yrigoyen 1643, José C. Paz, Provincia de Buenos Aires, Argentina",
    "CEDEM": "Juan Bautista Alberdi 5524, Caseros, Provincia de Buenos Aires, Argentina",
    "MIDLAND": "Av. Eva Perón 4050, Merlo, Provincia de Buenos Aires, Argentina",
    "ARGENTINO DE CASTELAR CENTRO B": "Montes de Oca 2242, Castelar, Provincia de Buenos Aires, Argentina",
    "ARGENTINO DE CASTELAR SUR C": "Montes de Oca 2242, Castelar, Provincia de Buenos Aires, Argentina",
    "ATLETICO PILAR": "Ituzaingó 759, Pilar, Provincia de Buenos Aires, Argentina",
    "COOP DE TORTUGUITAS": "Moreno 1160, Tortuguitas, Provincia de Buenos Aires, Argentina",
    "SOCIAL LANUS": "Coronel Pringles 1061, Lanús, Provincia de Buenos Aires, Argentina",
    "CASA PADUA B": "Independencia 725, San Antonio de Padua, Provincia de Buenos Aires, Argentina",
    "RAMOS MEJIA LTC": "Esteban Echeverría 361, Villa Sarmiento, Provincia de Buenos Aires, Argentina",
    "SPORTIVO HAEDO": "Héroes de Malvinas Argentinas 72, Haedo, Provincia de Buenos Aires, Argentina",
    "IMPERIO B NEGRO": "General César Díaz 3047, Ciudad Autónoma de Buenos Aires, Argentina",
    "MUNICAVELLANEDA": "Lincoln y Bolívar, Wilde, Provincia de Buenos Aires, Argentina",
    "SAN LORENZO B ROJO": "Av. Varela 2706, Flores, Ciudad Autónoma de Buenos Aires, Argentina",
    "BANCO NACION B BLANCO": "Zufriategui 1251, Vicente López, Provincia de Buenos Aires, Argentina",
}

# Búsqueda forzada por substring en AFILIADA (clave_equipo -> texto).
_FORZADO_CONTIENE: Dict[str, str] = {
    "IMPERIO A BLANCO": "IMPERIO JUNIORS",
    "FERROCARRIL OESTE BLANCO": "FERROCARRIL OESTE",
    "FERROCARRIL OESTE VERDE": "FERROCARRIL OESTE",
    "3 DE FEBRERO A BLANCO": "CLUB ATLETICO 3 DE FEBRERO",
    "3 DE FEBRERO AZUL B": "CLUB ATLETICO 3 DE FEBRERO",
    "GEVP A BLANCO": "GIMNASIA y ESGRIMA DE VILLA DEL PARQUE",
    "GEVP B CELESTE": "GIMNASIA y ESGRIMA DE VILLA DEL PARQUE",
    "CLUB GEI (A) AZUL": "GIMNASIA y ESGRIMA DE ITUZAINGO",
    "MORON A ROJO": "CLUB MORON",
    "DEPORTIVO MORON A": "CLUB DEPORTIVO MORON",
    "INDEPENDIENTE": "INDEPENDIENTE de AVELLANEDA",
    "INDEPENDIENTE DE BURZACO": "INDEPENDIENTE DE BURZACO",
    "RACING CLUB": "RACING CLUB de AVELLANEDA",
    "ALL BOYS BLANCO": "CLUB ATLETICO ALL BOYS",
    "BANADE ROJO": "BANCO NACIONAL DE DESARROLLO",
    "ARMENIA": "CENTRO ARMENIO",
    "AFALP A": "CIUDAD JARDIN LOMAS DEL PALOMAR",
    "LOS INDIOS A": "LOS INDIOS DE MORENO",
    "LOS INDIOS B": "LOS INDIOS DE MORENO",
    "EL PORVENIR JOSE PAZ C": "EL PORVENIR JCP",
    "UVVA UNION VECINAL VILLA ADELINA": "VILLA ADELINA",
    "UNION VECINAL DE MUNRO": "MUNRO",
    "SOCBECCAR": "BECCAR",
    "DEPORTIVO CROVARA A": "CROVARA",
    "COLEGIALES BLANCO": "COLEGIALES",
    "DEFENSORES DE HURLINGHAM VERDE": "DEFENSORES DE HURLINGHAM",
    "UNION VILLEGAS": "UNION ESCALADA VILLEGAS",
    "PORTENO ATLETICO CLUB AZUL": "PORTE",
    "COUNTRY BANFIELD A": "INFANTIL DE BANFIELD",
    "CENTRO GALICIA": "CENTRO GALICIA",
    "SAN MIGUEL VERDE": "SAN MIGUEL",
    "CLARIDAD": "CLARIDAD",
    "BELLA VISTA": "BELLA VISTA",
    "VARELA JRS": "VARELA JUNIOR",
    "HURACAN DE SAN JUSTO A": "HURACAN DE SAN JUSTO",
    "UNIVERSIDAD DE LA MATANZA": "LA MATANZA",
    "SAN FERNANDO AZUL": "SAN FERNANDO",
    "EZEIZA": "EZEIZA",
    "ATLETICO PILAR": "ATLETICO PILAR",
    "MIDLAND": "FERROCARRIL MIDLAND",
    "ARGENTINO DE CASTELAR CENTRO B": "ARGENTINO DE CASTELAR",
    "ARGENTINO DE CASTELAR NORTE A": "ARGENTINO DE CASTELAR",
    "YUPANQUI": "YUPANQUI",
    "INSTITUCION SARMIENTO B BLANCO": "DOMINGO FAUSTINO SARMIENTO",
    "ESTRELLA DE BOEDO": "ESTRELLA DE BOEDO",
    "ALEM": "LEANDRO N. ALEM",
    "QUILMES ATLETICO CLUB": "QUILMES",
    "EL TALAR": "EL TALAR",
    "LOS ANDES": "LOS ANDES",
    "OLIMPO": "OLIMPO",
    "SPORTIVO VILLA BALLESTER": "VILLA BALLESTER",
    "COPELLO": "COPELLO",
    "LOBOS": "LOBOS",
    "WILDE SPORTING": "WILDE",
    "CAZA Y PESCA B VERDE": "CAZA y PESCA",
    "BOCA JUNIORS AMARILLO B": "BOCA JUNIORS",
    "ARQUITECTURA B BLANCO": "ARQUITECTURA",
    "PINOCHO BLANCO": "PINOCHO",
    # Reclasificación / Primera fase (resto)
    "CSDY MORENO C": "MORENO DE QUILMES",
    "COOPERARIOS DE QUILMES": "COOPERARIOS",
    "CEDEM": "MUNICIPALIDAD DE 3 DE FEBRERO",
    "GEBA": "GIMNASIA y ESGRIMA de BUENOS AIRES",
    "BERAZATEGUI": "BERAZATEGUI",
    "SAN ANDRES": "SAN ANDRES",
    "VELEZ SARSFIELD AZUL B": "VELEZ SARSFIELD",
    "CLUB CEPA": "CEPA",
    "DEFENSORES DE BANFIELD": "DEFENSORES DE BANFIELD",
    "SITAS ROJO": "TIRO AL SEGNO",
    "DEFENSORES DE GLEW": "DEFENSORES DE GLEW",
    "VILLA ESPANA": "VILLA ESPA",
    "ITALIANO B": "CLUB ITALIANO",
    "DEFENSORES DE SANTOS LUGARES": "SANTOS LUGARES",
    "EL PALOMAR": "CLUB ATLETICO EL PALOMAR",
    "NOLTING": "NOLTING",
    "BANCO PROVINCIA": "BANCO PROVINCIA",
    "HARRODS GATH Y CHAVES": "HARRODS",
    "JOSE HERNANDEZ B": "JOSE HERNANDEZ",
    "SOCIAL LANUS": "SOCIAL LANUS",
    "SPORTIVO ALSINA": "SPORTIVO ALSINA",
    "EL FOGON": "EL FOGON",
    "RACING ANEXO": "VILLA DEL PARQUE",
    "CASA PADUA B": "CASA de PADUA",
    "JUVENCIA": "JUVENCIA",
    "BANCO NACION A AZUL": "BANCO NACION",
    "PEDRO ECHAGUE AMARILLO": "PEDRO ECHAGUE",
    "CIRCULO URQUIZA": "GENERAL URQUIZA",
    "CLUB SOCIAL Y DEPORTIVO ARENAL": "ARENAL",
    "LUZ Y ARTE": "LUZ y ARTE",
    "MONTE GRANDE B NEGRO": "MONTE GRANDE",
    "MORON B BLANCO": "CLUB MORON",
    "ARGENTINOS JUNIORS": "ARGENTINOS JUNIORS",
    "CENTRO ESPANOL": "ESPANOL",
    "CLUB ATENEO INGENIERO RAVER": "INGENIERO RAVER",
    "CLUB ATLETICO HURACAN DE PARQUE PATRICIOS": "PARQUE PATRICIOS",
    "ESTUDIANTIL PORTENO B": "ESTUDIANTIL PORTE",
    "IMPERIO B NEGRO": "IMPERIO JUNIORS",
    "PORTUGUES DEL GRAN BUENOS AIRES": "PORTUGUES",
    "COLON FC": "COLON FUTBOL",
    "COMUNICACIONES B NEGRO": "COMUNICACIONES",
    "FERROCARRIL OESTE NARANJA": "FERROCARRIL OESTE",
    "SPORTIVO HAEDO": "SPORTIVO HAEDO",
    "DEPORTIVO CROVARA B": "CROVARA",
    "UNITARIOS DE MARCOS PAZ": "MARCOS PAZ",
    "CIUDADELA NORTE": "CIUDADELA NORTE",
    "MUNICAVELLANEDA": "MUNICIPALIDAD DE AVELLANEDA",
    "VICTORIA NEGRO": "FOMENTO VICTORIA",
    "DEFENSORES DE MORENO": "DEFENSORES DE MORENO",
    "PASO DEL REY": "PASO DEL REY",
    "CLUB ATLETICO Y PROGRESO DE BRANDSEN": "BRANDSEN",
    "LAS HERAS": "LAS HERAS",
    "NAUTICO BUCHARDO A": "NAUTICO BUCHARDO",
    "BERNAL": "BERNAL",
    "CIUDAD DE BUENOS AIRES B BLANCO": "CIUDAD DE BUENOS AIRES",
    "CLUB GEI (B) BLANCO": "GIMNASIA y ESGRIMA DE ITUZAINGO",
    "GIMNASIA Y ESGRIMA DE LOMAS DE ZAMORA B": "LOMAS DE ZAMORA",
    "MACABI": "MACABI",
    "GIMNASIA Y ESGRIMA LA B PLATA": "GIMNASIA Y ESGRIMA LA PLATA",
    "NAUTICO BUCHARDO CENTRO (B)": "NAUTICO BUCHARDO",
    "MUNICIPALIDAD DE HURLINGHAM": "MUNICIPALIDAD DE HURLINGHAM",
    "17 DE AGOSTO": "17 DE AGOSTO",
    "SAN LORENZO B ROJO": "SAN LORENZO",
    "TALLERES": "TALLERES DE R. ESCALADA",
    "COOP DE TORTUGUITAS": "TORTUGUITAS",
    "PORTENO ATLETICO CLUB B BLANCO": "PORTE",
    "ALDO BONZI": "ALDO BONZI",
    "JUVENTUD UNIDA": "JUVENTUD UNIDA DE CA",
    "RAMOS MEJIA LTC": "RAMOS MEJIA",
    "NAUTICO HACOAJ AZUL B": "NAUTICO HACOAJ",
    "ALL BOYS SAAVEDRA": "ALL BOYS DE SAAVEDRA",
    "GUILLON BASQUET": "LUIS GUILLON",
    "LANUS B": "CLUB ATLETICO LANUS",
    "PAMPERO": "PAMPERO",
    "CLUB ATLETICO 9 DE JULIO DE LANUS": "9 DE JULIO DE LANUS",
    "COUNTRY BANFIELD B": "INFANTIL DE BANFIELD",
    "COLEGIALES NEGRO": "COLEGIALES",
    "INDEPENDIENTE DE ESCOBAR": "INDEPENDIENTE DE ESCOBAR",
    "ITALIANO DE JOSE PAZ C": "ITALIANO DE JOSE C PAZ",
    "PLATENSE B": "PLATENSE",
    "TAPONAZO FUTBOL CLUB": "TAPONAZO",
    "DEPORTIVO MORON B": "CLUB DEPORTIVO MORON",
    "ATLETICO BOULOGNE": "BOULOGNE",
    "SAN FERNANDO BLANCO": "SAN FERNANDO",
    "TAMBEROS UNIDOS": "TAMBEROS",
    "DEFENSORES DE HURLINGHAM BLANCO": "DEFENSORES DE HURLINGHAM",
    "SOCIEDAD HEBRAICA ARGENTINA": "HEBRAICA",
    "SAN MIGUEL BLANCO": "SAN MIGUEL",
    "ALL BOYS NEGRO": "CLUB ATLETICO ALL BOYS",
    "ARGENTINO DE CASTELAR SUR C": "ARGENTINO DE CASTELAR",
    "SPORTIVO PILAR B BLANCO": "SPORTIVO PILAR",
    "VICTORIA BLANCO": "FOMENTO VICTORIA",
    "PINOCHO VERDE": "PINOCHO",
    "3 DE FEBRERO C CELESTE": "CLUB ATLETICO 3 DE FEBRERO",
    "CLUB GEI GRIS(C)": "GIMNASIA y ESGRIMA DE ITUZAINGO",
    "HURACAN DE SAN JUSTO B": "HURACAN DE SAN JUSTO",
    "BANCO NACION B BLANCO": "BANCO NACION",
    "SITAS VERDE": "TIRO AL SEGNO",
    "BECCAR AZUL": "BECCAR",
    "UNIVERSIDAD DE BUENOS AIRES": "UNIVERSIDAD DE BUENOS AIRES",
    "LA UNION": "LA UNION BERAZATEGUI",
    "NUEVA CHICAGO": "NUEVA CHICAGO",
}

# Claves sin fila usable en el padrón federativo (completar sede a mano en mapeo_clubes.csv).
_SIN_PADRON: frozenset[str] = frozenset({"JUVENCIA"})

# Tokens a ignorar en nombres de afiliadas federativas.
_FED_NOISE = {
    "FLEX",
    "MASTER",
    "AFALP",
    "ASOCIACION",
    "CLUB",
    "ATLETICO",
    "ATLETICA",
    "BASKET",
    "BASQUET",
    "DEPORTIVO",
    "DEPORTIVA",
    "SOCIAL",
    "CULTURAL",
    "Y",
    "DEL",
    "DE",
    "LA",
    "EL",
    "LOS",
    "LAS",
}


@dataclass
class EquipoElite:
    pos: int
    equipo: str
    clave: str
    zona: str
    puntos: int
    pts_general: int
    presentaciones: int
    ganados: int
    fase: str = "CLASIFICACION"


@dataclass
class ClubFederacion:
    idx: int
    afiliada: str
    direccion: str
    cod_postal: str
    norm: str
    tokens: frozenset


@dataclass
class MapeoClub:
    pos: int
    equipo: str
    clave: str
    zona: str
    puntos: int
    afiliada: str
    direccion: str
    cod_postal: str
    confianza: str
    score: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    geocode_precision: str = ""
    fase: str = "CLASIFICACION"


def _import_standings():
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ingest.febamba.standings_2026 import clave_equipo

    return clave_equipo


def strip_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return nfkd.encode("ascii", "ignore").decode("ascii")


def norm_federacion(nombre: str) -> str:
    t = strip_acentos(nombre).upper()
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    tokens = [tok for tok in t.split() if tok not in _FED_NOISE]
    return " ".join(tokens)


def norm_match(nombre: str) -> str:
    t = strip_acentos(nombre).upper()
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    return " ".join(t.split())


def cargar_elite42(
    *,
    fase: str = "PRIMERA",
    top_n: Optional[int] = None,
) -> List[EquipoElite]:
    """
    Carga la tabla general.

    ``fase``:
      - ``PRIMERA`` / ``primera``: Clasificación + Reclasificación (orden: clasif. por pts, luego reclas. por pts)
      - ``CLASIFICACION`` / ``RECLASIFICACION``: solo esa fase
    """
    clave_equipo = _import_standings()
    text = STANDINGS_HTML.read_text(encoding="utf-8")
    start = text.index("const DATA = ") + len("const DATA = ")
    end = text.index(";\n", start)
    data = json.loads(text[start:end])

    fase_key = (fase or "PRIMERA").upper().strip()
    if fase_key in {"PRIMERA", "PRIMERA_FASE", "ALL", "TODAS"}:
        fases = ["CLASIFICACION", "RECLASIFICACION"]
    else:
        fases = [fase_key]

    def _rows_de(fase_nombre: str) -> List[dict]:
        rows: List[dict] = []
        for zona, filas in data["tablas"].get(fase_nombre, {}).items():
            for f in filas:
                rows.append({**f, "zona": zona, "fase": fase_nombre})
        rows.sort(
            key=lambda r: (
                -r["puntos"],
                -r.get("pts_general", 0),
                -r.get("presentaciones", 0),
                -r.get("ganados", 0),
                r["equipo"],
            )
        )
        return rows

    rows: List[dict] = []
    for fn in fases:
        rows.extend(_rows_de(fn))
    if top_n is not None:
        rows = rows[:top_n]

    elite: List[EquipoElite] = []
    for pos, r in enumerate(rows, start=1):
        elite.append(
            EquipoElite(
                pos=pos,
                equipo=r["equipo"],
                clave=clave_equipo(r["equipo"]),
                zona=r["zona"],
                puntos=r["puntos"],
                pts_general=int(r.get("pts_general") or 0),
                presentaciones=int(r.get("presentaciones") or 0),
                ganados=int(r.get("ganados") or 0),
                fase=r.get("fase") or fase_key,
            )
        )
    return elite


def cargar_federacion(path: Optional[Path] = None) -> List[ClubFederacion]:
    path = path or REF_XLSX
    df = pd.read_excel(path)
    df = df.rename(columns=str.strip)
    cols = {c.upper(): c for c in df.columns}
    col_nom = cols.get("AFILIADA", list(df.columns)[0])
    col_dir = cols.get("DIRECCION", list(df.columns)[1])
    col_cp = cols.get("COD POSTAL", list(df.columns)[2] if len(df.columns) > 2 else col_dir)

    clubs: List[ClubFederacion] = []
    for idx, row in df.iterrows():
        afiliada = str(row[col_nom]).strip()
        if not afiliada or afiliada.lower() == "nan":
            continue
        direccion = "" if pd.isna(row[col_dir]) else str(row[col_dir]).strip()
        cp_raw = row[col_cp]
        cp = "" if pd.isna(cp_raw) else str(cp_raw).strip().replace(".0", "")
        norm = norm_federacion(afiliada)
        tokens = frozenset(norm.split())
        clubs.append(
            ClubFederacion(
                idx=int(idx),
                afiliada=afiliada,
                direccion=direccion,
                cod_postal=cp,
                norm=norm,
                tokens=tokens,
            )
        )
    return clubs


def _score_match(clave: str, equipo: str, club: ClubFederacion) -> float:
    alias = _ALIAS_FEDERACION.get(clave, clave)
    alias_norm = norm_federacion(alias)
    clave_norm = norm_match(clave)

    scores: List[float] = []
    for needle in {alias_norm, clave_norm, norm_match(equipo)}:
        if not needle:
            continue
        if needle in club.norm or club.norm in needle:
            scores.append(0.98)
        scores.append(SequenceMatcher(None, needle, club.norm).ratio())
        inter = frozenset(needle.split()) & club.tokens
        union = frozenset(needle.split()) | club.tokens
        if union:
            scores.append(len(inter) / len(union))

    return max(scores) if scores else 0.0


def _club_forzado(clave: str, federacion: List[ClubFederacion]) -> Optional[ClubFederacion]:
    needle = _FORZADO_CONTIENE.get(clave)
    if not needle:
        return None
    up = needle.upper()
    candidatos = [c for c in federacion if up in strip_acentos(c.afiliada).upper()]
    if clave == "MORON A ROJO":
        candidatos = [c for c in candidatos if "DEPORTIVO" not in c.afiliada.upper()]
    if clave == "ALL BOYS BLANCO":
        candidatos = [c for c in candidatos if "SAAVEDRA" not in c.afiliada.upper()]
    if clave == "INDEPENDIENTE":
        candidatos = [c for c in candidatos if "BURZACO" not in c.afiliada.upper()]
    if clave in {
        "PORTENO ATLETICO CLUB AZUL",
        "PORTENO ATLETICO CLUB B BLANCO",
    }:
        candidatos = [
            c
            for c in candidatos
            if "PORTE" in strip_acentos(c.afiliada).upper()
            and "ESTUDIANTIL" not in strip_acentos(c.afiliada).upper()
        ]
    if clave in {"ALL BOYS BLANCO", "ALL BOYS NEGRO"}:
        candidatos = [c for c in candidatos if "SAAVEDRA" not in c.afiliada.upper()]
    if clave == "ALL BOYS SAAVEDRA":
        candidatos = [c for c in candidatos if "SAAVEDRA" in c.afiliada.upper()]
    if clave == "MORON B BLANCO":
        candidatos = [c for c in candidatos if "DEPORTIVO" not in c.afiliada.upper()]
    if clave in {"ITALIANO B"}:
        candidatos = [c for c in candidatos if "JOSE" not in c.afiliada.upper()]
    if clave == "ITALIANO DE JOSE PAZ C":
        candidatos = [c for c in candidatos if "JOSE" in c.afiliada.upper()]
    if clave == "RACING ANEXO":
        candidatos = [c for c in candidatos if "ANEXO" in c.afiliada.upper() or "VILLA DEL PARQUE" in c.afiliada.upper()]
    if clave == "JUVENTUD UNIDA":
        candidatos = [c for c in candidatos if "CA" in strip_acentos(c.afiliada).upper()]
    if candidatos:
        return candidatos[0]
    return None


def aplicar_sedes_confirmadas(mapeos: List[MapeoClub]) -> List[MapeoClub]:
    out: List[MapeoClub] = []
    for m in mapeos:
        sede = _SEDE_CONFIRMADA.get(m.clave)
        if not sede:
            out.append(m)
            continue
        af, direccion, cp = sede
        out.append(
            MapeoClub(
                pos=m.pos,
                equipo=m.equipo,
                clave=m.clave,
                zona=m.zona,
                puntos=m.puntos,
                afiliada=af,
                direccion=direccion,
                cod_postal=cp,
                confianza="confirmado",
                score=1.0,
                lat=None,
                lon=None,
                geocode_precision="",
                fase=m.fase,
            )
        )
    return out


def emparejar_elite_con_federacion(
    elite: List[EquipoElite],
    federacion: List[ClubFederacion],
    *,
    umbral_alto: float = 0.72,
    umbral_bajo: float = 0.55,
) -> List[MapeoClub]:
    mapeos: List[MapeoClub] = []

    for eq in elite:
        if eq.clave in _SIN_PADRON:
            mapeos.append(
                MapeoClub(
                    pos=eq.pos,
                    equipo=eq.equipo,
                    clave=eq.clave,
                    zona=eq.zona,
                    puntos=eq.puntos,
                    afiliada="",
                    direccion="",
                    cod_postal="",
                    confianza="sin_padron",
                    score=0.0,
                    fase=eq.fase,
                )
            )
            continue

        forzado = _club_forzado(eq.clave, federacion)
        if forzado is not None:
            best_club, best_score = forzado, 1.0
            confianza = "forzado"
        else:
            candidatos = [
                (c, _score_match(eq.clave, eq.equipo, c)) for c in federacion
            ]
            candidatos.sort(key=lambda x: -x[1])
            best_club, best_score = candidatos[0]
            if eq.clave in _ALIAS_FEDERACION:
                confianza = "alias"
            elif best_score >= umbral_alto:
                confianza = "auto"
            elif best_score >= umbral_bajo:
                confianza = "revision"
            else:
                confianza = "bajo"

        mapeos.append(
            MapeoClub(
                pos=eq.pos,
                equipo=eq.equipo,
                clave=eq.clave,
                zona=eq.zona,
                puntos=eq.puntos,
                afiliada=best_club.afiliada,
                direccion=best_club.direccion,
                cod_postal=best_club.cod_postal,
                confianza=confianza,
                score=round(best_score, 4),
                fase=eq.fase,
            )
        )
    return mapeos


def exportar_elite_csv(elite: List[EquipoElite], path: Path = ELITE42_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(e) for e in elite])
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def exportar_mapeo_csv(mapeos: List[MapeoClub], path: Path = MAPEO_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(m) for m in mapeos])
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _cargar_geocache() -> Dict[str, dict]:
    if GEOJSON.exists():
        with GEOJSON.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def _guardar_geocache(cache: Dict[str, dict]) -> None:
    GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    with GEOJSON.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# Coordenadas manuales (clave_equipo -> lat, lon, nota).
_GEOCODE_MANUAL: Dict[str, Tuple[float, float, str]] = {
    "VELEZ SARSFIELD A BLANCO": (-34.6315, -58.5089, "manual_velez"),
    "GIMNASIA Y ESGRIMA LA A PLATA": (-34.9214, -57.9544, "manual_gelp"),
    "TRISTAN SUAREZ": (-34.8593, -58.5625, "manual_tristan"),
    "ARGENTINO DE CASTELAR NORTE A": (-34.6547, -58.6408, "manual_castelar"),
    "IMPERIO A BLANCO": (-34.6058, -58.4562, "manual_imperio"),
    "CAZA Y PESCA A AZUL": (-34.4585, -58.8102, "manual_caza_pesca"),
    "CAZA Y PESCA B VERDE": (-34.4585, -58.8102, "manual_caza_pesca"),
    "COPELLO": (-34.6012, -58.5138, "manual_copello_devoto"),
    "LOS INDIOS A": (-34.6518, -58.7895, "manual_indios_moreno"),
    "LOS INDIOS B": (-34.6518, -58.7895, "manual_indios_moreno"),
    "SAN MIGUEL VERDE": (-34.5432, -58.7118, "manual_san_miguel"),
    "CENTRO GALICIA": (-34.5031, -58.4813, "manual_centro_galicia"),
    "VARELA JRS": (-34.7745, -58.2813, "manual_varela_jrs"),
    "AFALP A": (-34.6030, -58.5895, "manual_afalp"),
    "SAN FERNANDO AZUL": (-34.4472, -58.5702, "manual_san_fernando"),
    "YUPANQUI": (-34.6839, -58.4816, "manual_yupanqui"),
    "BERAZATEGUI": (-34.7635, -58.2125, "manual_berazategui"),
    "DEFENSORES DE BANFIELD": (-34.7440, -58.3945, "manual_def_banfield"),
    "VILLA ESPANA": (-34.7605, -58.2650, "manual_villa_espana"),
    "EL PALOMAR": (-34.6180, -58.5955, "manual_el_palomar"),
    "JUVENCIA": (-34.6050, -58.4500, "manual_juvencia_aprox"),
    "CIRCULO URQUIZA": (-34.5735, -58.4870, "manual_circulo_urquiza"),
    "MORON B BLANCO": (-34.6507, -58.6301, "manual_moron_castelar"),
    "PORTUGUES DEL GRAN BUENOS AIRES": (-34.6650, -58.5600, "manual_portugues"),
    "MUNICAVELLANEDA": (-34.6625, -58.3650, "manual_munic_avellaneda"),
    "DEFENSORES DE MORENO": (-34.6500, -58.7900, "manual_def_moreno"),
    "CLUB ATLETICO Y PROGRESO DE BRANDSEN": (-35.1685, -58.2400, "manual_brandsen"),
    "BERNAL": (-34.7100, -58.2800, "manual_bernal"),
    "TALLERES": (-34.7350, -58.3900, "manual_talleres_re"),
    "ALDO BONZI": (-34.7100, -58.5150, "manual_aldo_bonzi"),
    "NAUTICO HACOAJ AZUL B": (-34.4250, -58.5800, "manual_hacoaj_tigre"),
    "ITALIANO DE JOSE PAZ C": (-34.5150, -58.7600, "manual_italiano_jcp"),
    "SAN FERNANDO BLANCO": (-34.4472, -58.5702, "manual_san_fernando"),
    "SAN MIGUEL BLANCO": (-34.5432, -58.7118, "manual_san_miguel"),
    "UNIVERSIDAD DE BUENOS AIRES": (-34.5425, -58.4395, "manual_uba_ciudad_univ"),
    "LOBOS": (-35.1860, -59.0965, "manual_lobos"),
    "COOP DE TORTUGUITAS": (-34.4705, -58.7550, "manual_tortuguitas"),
    "MUNICAVELLANEDA": (-34.7005, -58.3205, "manual_wilde_avellaneda"),
    "CEDEM": (-34.6065, -58.5635, "manual_cedem_caseros"),
    "SPORTIVO VILLA BALLESTER": (-34.5465, -58.5565, "manual_villa_ballester"),
    "UNION VILLEGAS": (-34.7255, -58.4005, "manual_union_villegas"),
    "OLIMPO": (-34.7085, -58.3905, "manual_olimpo_lanus"),
    "UNION VECINAL DE MUNRO": (-34.5305, -58.5255, "manual_munro"),
    "EL PORVENIR JOSE PAZ C": (-34.5155, -58.7655, "manual_porvenir_jcp"),
    "MIDLAND": (-34.6855, -58.7305, "manual_midland_merlo"),
    "ATLETICO PILAR": (-34.4585, -58.9145, "manual_atletico_pilar"),
    "SOCIAL LANUS": (-34.7080, -58.3920, "manual_social_lanus"),
    "RAMOS MEJIA LTC": (-34.6455, -58.5655, "manual_ramos_mejia_ltc"),
    "SPORTIVO HAEDO": (-34.6450, -58.5950, "manual_sportivo_haedo"),
    "IMPERIO B NEGRO": (-34.6058, -58.4562, "manual_imperio"),
    "BANCO NACION B BLANCO": (-34.5265, -58.4755, "manual_banco_nacion_vl"),
}

# CP -> localidad para reintentos de geocodificación.
_CP_LOCALIDAD: Dict[str, str] = {
    "1900": "La Plata",
    "1814": "Cañuelas",
    "1864": "Alejandro Korn",
    "1842": "Monte Grande",
    "1852": "Burzaco",
    "1834": "Lomas de Zamora",
    "1824": "Lanús",
    "1702": "Villa Sarmiento",
    "1704": "Ciudadela",
    "1708": "Morón",
    "1676": "Villa Bosch",
    "1653": "Villa Bosch",
    "1629": "Pilar",
    "1625": "Escobar",
    "1635": "Presidente Derqui",
    "1611": "Pilar",
    "1604": "Florida",
    "1416": "Parque Chacabuco",
    "1417": "Villa del Parque",
    "1714": "Ituzaingó",
    "1424": "Caballito",
    "1428": "Núñez",
    "1429": "Belgrano",
    "1431": "Villa Urquiza",
    "1437": "Boedo",
    "1440": "Villa Luro",
    "1406": "Flores",
    "1407": "Villa Crespo",
    "1408": "Versailles",
    "1409": "Caballito",
    "1157": "La Boca",
}


def _en_amba(lat: float, lon: float) -> bool:
    return -36.2 <= lat <= -34.15 and -59.4 <= lon <= -57.75


def _queries_geocode(m: MapeoClub, pais: str) -> List[str]:
    cp = (m.cod_postal or "").strip()
    loc = _CP_LOCALIDAD.get(cp, "")
    direccion = (m.direccion or "").strip()
    queries: List[str] = []
    if direccion and loc:
        queries.append(f"{direccion}, {loc}, Provincia de Buenos Aires, {pais}")
    if direccion and cp:
        queries.append(f"{direccion}, {cp}, {pais}")
    if direccion:
        queries.append(f"{direccion}, Ciudad Autónoma de Buenos Aires, {pais}")
        queries.append(f"{direccion}, {pais}")
    if cp and loc:
        queries.append(f"{loc}, {cp}, {pais}")
    return queries


def _nominatim_buscar(session: requests.Session, query: str) -> Optional[Tuple[float, float, str]]:
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={quote(query)}&format=json&limit=3&countrycodes=ar"
    )
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        for item in resp.json():
            lat = float(item["lat"])
            lon = float(item["lon"])
            if _en_amba(lat, lon):
                return lat, lon, item.get("type", "ok")
    except requests.RequestException:
        return None
    return None


def geocodificar_mapeos(
    mapeos: List[MapeoClub],
    *,
    pais: str = "Argentina",
    sleep_s: float = 1.1,
    forzar: bool = False,
) -> List[MapeoClub]:
    cache = _cargar_geocache()
    session = requests.Session()
    session.headers["User-Agent"] = "GES-LNB-TNA-viajes-elite42/1.0"

    result: List[MapeoClub] = []
    for m in mapeos:
        key = m.clave

        if m.confianza == "sin_padron":
            manual = _GEOCODE_MANUAL.get(key)
            if manual:
                lat, lon, precision = manual
                result.append(
                    MapeoClub(
                        **{**asdict(m), "lat": lat, "lon": lon, "geocode_precision": precision}
                    )
                )
            else:
                result.append(MapeoClub(**asdict(m)))
            continue

        if not forzar and key in cache:
            hit = cache[key]
            lat, lon = hit.get("lat"), hit.get("lon")
            if lat is not None and lon is not None and _en_amba(float(lat), float(lon)):
                result.append(
                    MapeoClub(
                        **{
                            **asdict(m),
                            "lat": float(lat),
                            "lon": float(lon),
                            "geocode_precision": hit.get("precision", "cache"),
                        }
                    )
                )
                continue

        manual = _GEOCODE_MANUAL.get(key)
        if manual:
            lat, lon, precision = manual
            query = "manual"
        elif key in _GEOCODE_QUERY:
            hit = _nominatim_buscar(session, _GEOCODE_QUERY[key])
            time.sleep(sleep_s)
            if hit:
                lat, lon, precision = hit
                query = _GEOCODE_QUERY[key]
            else:
                lat = lon = None
                precision = "fallo"
                query = _GEOCODE_QUERY[key]
        else:
            lat = lon = None
            precision = "fallo"
            query = ""
            for q in _queries_geocode(m, pais):
                hit = _nominatim_buscar(session, q)
                time.sleep(sleep_s)
                if hit:
                    lat, lon, precision = hit
                    query = q
                    break

        cache[key] = {
            "clave": key,
            "equipo": m.equipo,
            "afiliada": m.afiliada,
            "query": query,
            "lat": lat,
            "lon": lon,
            "precision": precision,
        }
        _guardar_geocache(cache)

        result.append(
            MapeoClub(
                **{**asdict(m), "lat": lat, "lon": lon, "geocode_precision": precision}
            )
        )
    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def matriz_distancias(mapeos: List[MapeoClub]) -> Tuple[List[str], List[List[Optional[float]]]]:
    nombres = [m.equipo for m in mapeos]
    n = len(mapeos)
    mat: List[List[Optional[float]]] = [[None] * n for _ in range(n)]
    for i, a in enumerate(mapeos):
        for j, b in enumerate(mapeos):
            if i == j:
                mat[i][j] = 0.0
            elif a.lat is None or a.lon is None or b.lat is None or b.lon is None:
                mat[i][j] = None
            else:
                mat[i][j] = round(haversine_km(a.lat, a.lon, b.lat, b.lon), 1)
    return nombres, mat
