# -*- coding: utf-8 -*-
"""
Sincroniza el listado de entrenadores a Google Sheets.

Lee ``outputs/entrenadores/entrenadores_club_categorias_YYYY.csv`` y hace upsert
por KEY (ENTRENADOR||CLUB). Preserva la columna WHATSAPP si ya existe en el Sheet.

Config: ``config/entrenadores_sheets.json``
Credenciales: ``config/google_service_account.json`` (misma SA que Echagüe).

Ejemplo:
  python analysis/sync_entrenadores_sheets.py
  python analysis/sync_entrenadores_sheets.py --csv outputs/entrenadores/entrenadores_club_categorias_2026.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVICE_ACCOUNT = ROOT / "config" / "google_service_account.json"
CONFIG_SHEETS = ROOT / "config" / "entrenadores_sheets.json"

HEADERS = ["KEY", "ENTRENADOR", "CLUB", "CATEGORIAS", "WHATSAPP"]
_RE_WS = re.compile(r"\s+")


def _norm_key_part(s: str) -> str:
    return _RE_WS.sub(" ", (s or "").strip().upper())


def make_key(entrenador: str, club: str) -> str:
    return f"{_norm_key_part(entrenador)}||{_norm_key_part(club)}"


def cats_to_sheet(categorias_csv: str) -> str:
    """CSV usa comas entre categorías; en Sheet usamos ' | ' para no chocar con APELLIDO, NOMBRE."""
    parts = [c.strip() for c in (categorias_csv or "").split(",") if c.strip()]
    return " | ".join(parts)


def load_filas_from_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out: List[Dict[str, str]] = []
    for r in rows:
        ent = (r.get("Entrenador") or "").strip()
        club = (r.get("Club") or "").strip()
        if not ent or not club:
            continue
        out.append(
            {
                "KEY": make_key(ent, club),
                "ENTRENADOR": ent,
                "CLUB": club,
                "CATEGORIAS": cats_to_sheet(r.get("Categorias_A_Cargo") or ""),
                "WHATSAPP": "",  # nunca pisar desde CSV; se preserva en upsert
            }
        )
    return out


def _load_config(
    spreadsheet_id: str = "",
    worksheet: str = "",
) -> Tuple[str, str, str]:
    cfg: Dict[str, str] = {}
    if CONFIG_SHEETS.exists():
        try:
            cfg = json.loads(CONFIG_SHEETS.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    sid = spreadsheet_id or cfg.get("spreadsheet_id") or ""
    ws = worksheet or cfg.get("worksheet") or "Entrenadores"
    webapp = (cfg.get("webapp_url") or "").strip()
    return sid, ws, webapp


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def upsert_entrenadores_sheet(
    filas: List[Dict[str, str]],
    *,
    spreadsheet_id: str,
    worksheet: str,
    credentials_path: Path = SERVICE_ACCOUNT,
) -> Dict[str, int]:
    """
    Upsert por KEY.

    Actualiza ENTRENADOR, CLUB, CATEGORIAS. No pisa WHATSAPP si ya tiene valor.
    Filas nuevas se agregan al final (WHATSAPP vacío).
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise SystemExit("Faltan dependencias: pip install gspread google-auth") from e

    if not credentials_path.exists():
        raise SystemExit(
            f"No está la service account en {credentials_path}.\n"
            "Compartí el Sheet con el client_email del JSON (rol Editor)."
        )
    if not spreadsheet_id:
        raise SystemExit(
            "Falta spreadsheet_id. Creá un Google Sheet vacío, compartilo con la "
            "service account y pegá el ID en config/entrenadores_sheets.json."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(credentials_path), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows=max(1000, len(filas) + 10), cols=10)

    existing = ws.get_all_values()
    if not existing:
        values = [HEADERS] + [[r.get(h, "") for h in HEADERS] for r in filas]
        ws.update(values=values, range_name="A1", value_input_option="USER_ENTERED")
        return {"creadas": len(filas), "actualizadas": 0, "sin_cambio": 0}

    header_row = existing[0]
    missing = [h for h in HEADERS if h not in header_row]
    if missing:
        new_header = header_row + missing
        ws.update(values=[new_header], range_name="A1", value_input_option="USER_ENTERED")
        header_row = new_header

    col_idx = {name: i for i, name in enumerate(header_row)}
    key_col = col_idx.get("KEY")
    if key_col is None:
        raise SystemExit("La hoja no tiene columna KEY.")

    key_to_row: Dict[str, int] = {}
    for rnum, row in enumerate(existing[1:], start=2):
        if key_col < len(row):
            k = (row[key_col] or "").strip()
            if k:
                key_to_row[k] = rnum

    actualizadas = creadas = sin_cambio = 0
    updates: List[Dict[str, object]] = []
    nuevas: List[List[str]] = []
    width = max(len(header_row), max((len(r) for r in existing), default=0))

    managed = ["ENTRENADOR", "CLUB", "CATEGORIAS"]  # no WHATSAPP

    for fila in filas:
        key = (fila.get("KEY") or "").strip()
        if not key:
            continue
        if key in key_to_row:
            rnum = key_to_row[key]
            old = existing[rnum - 1] if rnum - 1 < len(existing) else []
            changed = False
            for h in managed:
                ci = col_idx[h]
                new_val = fila.get(h, "")
                old_val = old[ci] if ci < len(old) else ""
                if str(old_val) == str(new_val):
                    continue
                changed = True
                updates.append(
                    {
                        "range": f"{_col_letter(ci + 1)}{rnum}",
                        "values": [[new_val]],
                    }
                )
            # KEY siempre alineada
            if "KEY" in col_idx:
                ci = col_idx["KEY"]
                old_key = old[ci] if ci < len(old) else ""
                if str(old_key) != key:
                    updates.append(
                        {
                            "range": f"{_col_letter(ci + 1)}{rnum}",
                            "values": [[key]],
                        }
                    )
                    changed = True
            if changed:
                actualizadas += 1
            else:
                sin_cambio += 1
        else:
            row_out = [""] * width
            for h in HEADERS:
                if h in col_idx:
                    row_out[col_idx[h]] = fila.get(h, "")
            nuevas.append(row_out)
            creadas += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if nuevas:
        ws.append_rows(nuevas, value_input_option="USER_ENTERED")

    return {
        "creadas": creadas,
        "actualizadas": actualizadas,
        "sin_cambio": sin_cambio,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Sync entrenadores → Google Sheets")
    p.add_argument(
        "--csv",
        default=str(
            ROOT / "outputs" / "entrenadores" / "entrenadores_club_categorias_2026.csv"
        ),
    )
    p.add_argument("--spreadsheet-id", default="")
    p.add_argument("--worksheet", default="")
    p.add_argument("--credentials", default=str(SERVICE_ACCOUNT))
    args = p.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"No existe {csv_path}", file=sys.stderr)
        return 1

    sid, ws_name, _webapp = _load_config(args.spreadsheet_id, args.worksheet)
    filas = load_filas_from_csv(csv_path)
    print(f"Filas CSV: {len(filas)}")
    stats = upsert_entrenadores_sheet(
        filas,
        spreadsheet_id=sid,
        worksheet=ws_name,
        credentials_path=Path(args.credentials),
    )
    print(
        f"Sheet OK: creadas={stats['creadas']} "
        f"actualizadas={stats['actualizadas']} sin_cambio={stats['sin_cambio']}"
    )
    print(f"https://docs.google.com/spreadsheets/d/{sid}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
