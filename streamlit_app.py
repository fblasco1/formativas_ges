# -*- coding: utf-8 -*-
"""
Punto de entrada para Streamlit Community Cloud.

En share.streamlit.io usar:
  Main file path: streamlit_app.py
"""
from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parent / "visualizaciones" / "ranking_streamlit.py"),
    run_name="__main__",
)
