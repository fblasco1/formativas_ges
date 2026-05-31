# -*- coding: utf-8 -*-
"""Registro central de competencias / patas de análisis GES."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from competencias.formativas.ges import TORNEOS_FORMATIVAS

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "Data"


@dataclass(frozen=True)
class CompetenciaConfig:
    slug: str
    nombre: str
    estado: str  # activo | planificado
    torneos: Mapping[int, Mapping[str, str | int]]
    focus_years: tuple[int, ...] | None = None

    @property
    def data_dir(self) -> Path:
        return DATA_ROOT / self.slug

    @property
    def procesada_dir(self) -> Path:
        return self.data_dir / "procesada"

    def partidos_path(self, anio: int) -> Path:
        return self.data_dir / f"partidos_{anio}.csv"

    def torneo(self, anio: int) -> dict[str, str | int]:
        if anio not in self.torneos:
            raise KeyError(f"Año {anio} no configurado para {self.slug}")
        t = self.torneos[anio]
        return {
            "id": t["id"],
            "url": t["url"],
            "Anio": anio,
            "torneo": t["torneo"],
        }


COMPETENCIAS: dict[str, CompetenciaConfig] = {
    "formativas": CompetenciaConfig(
        slug="formativas",
        nombre="Formativas FeBAMBA",
        estado="activo",
        torneos=TORNEOS_FORMATIVAS,
        focus_years=(2023, 2024, 2025, 2026),
    ),
    "liga_nacional": CompetenciaConfig(
        slug="liga_nacional",
        nombre="Liga Nacional",
        estado="planificado",
        torneos={},
    ),
    "liga_argentina": CompetenciaConfig(
        slug="liga_argentina",
        nombre="Liga Argentina (ex-TNA)",
        estado="planificado",
        torneos={},
    ),
    "liga_federal": CompetenciaConfig(
        slug="liga_federal",
        nombre="Liga Federal",
        estado="planificado",
        torneos={},
    ),
    "liga_femenina": CompetenciaConfig(
        slug="liga_femenina",
        nombre="Liga Femenina",
        estado="planificado",
        torneos={},
    ),
}


def get_competencia(slug: str) -> CompetenciaConfig:
    key = slug.strip().lower().replace("-", "_")
    if key not in COMPETENCIAS:
        disponibles = ", ".join(sorted(COMPETENCIAS))
        raise ValueError(f"Competencia desconocida: {slug!r}. Disponibles: {disponibles}")
    return COMPETENCIAS[key]


def list_competencias(*, solo_activas: bool = False) -> list[CompetenciaConfig]:
    items = list(COMPETENCIAS.values())
    if solo_activas:
        items = [c for c in items if c.estado == "activo"]
    return items
