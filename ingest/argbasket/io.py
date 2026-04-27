from __future__ import annotations

import csv
from typing import Dict, Iterable, List, Sequence


def write_csv_rows(path: str, rows: Iterable[Dict[str, str]], fieldnames: Sequence[str]) -> None:
    rows_list = list(rows)
    if not rows_list:
        raise ValueError("No hay filas para escribir (salida vacía).")

    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for r in rows_list:
            w.writerow({k: r.get(k, "") for k in fieldnames})

