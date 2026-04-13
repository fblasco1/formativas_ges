# -*- coding: utf-8 -*-
"""
Legacy: normaliza CSV en la raíz de ``Data/`` y escribe ``matches_clean.*``.

Preferir ``python -m pipelines.normalize`` leyendo ``Data/raw/`` tras el scraper.
"""

from __future__ import annotations

import os
import sys

# Raíz del proyecto en sys.path (ejecución como script desde la raíz)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipelines.normalize import main_legacy_flat_csv_in_data  # noqa: E402

if __name__ == "__main__":
    main_legacy_flat_csv_in_data()
