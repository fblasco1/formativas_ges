"""Compatibilidad: delega al pipeline actual de normalización."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.normalizar_equipos import main

if __name__ == "__main__":
    print(
        "Usá: python pipelines/normalizar_equipos.py --consolidar --ranking\n"
        "O la app: streamlit run visualizaciones/mapeo_equipos_streamlit.py\n"
    )
    raise SystemExit(main(["--consolidar"]))
