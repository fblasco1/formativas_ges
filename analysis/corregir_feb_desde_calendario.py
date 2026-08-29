# -*- coding: utf-8 -*-
"""
Corrige estadísticas de un equipo FEB reconstruyéndolas desde el calendario y actas.

Cuando la tabla agregada de feb.es duplica totales (ej. Canterbury School), este script
obtiene los partidos del calendario, parsea cada acta (Partido.aspx) y actualiza el CSV.

Ejemplo:
  python analysis/corregir_feb_desde_calendario.py --equipo "CANTERBURY SCHOOL" --grupo-id 89741
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36",
}

CALENDAR_URL = "https://www.feb.es/competiciones/calendario/cespclubescadmasc/35/2025"
GRUPO_TARGET = "_ctl0:MainContentPlaceHolderMaster:gruposDropDownList"


@dataclass
class TotalesTiro:
    partidos: int = 0
    pts: int = 0
    t2a: int = 0
    t2i: int = 0
    t3a: int = 0
    t3i: int = 0
    tla: int = 0
    tli: int = 0

    def add(self, other: "TotalesTiro") -> None:
        self.partidos += other.partidos
        self.pts += other.pts
        self.t2a += other.t2a
        self.t2i += other.t2i
        self.t3a += other.t3a
        self.t3i += other.t3i
        self.tla += other.tla
        self.tli += other.tli


def _norm_equipo(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre or "")
    t = t.encode("ascii", "ignore").decode("ascii")
    return " ".join(t.upper().replace('"', "").split())


def _parse_shot_partido(text: str) -> Tuple[int, int]:
    """Parsea celdas FEB de acta: '26/49 53,1%' o '26/4953,1%' -> (26, 49)."""
    text = (text or "").strip()
    token = text.split()[0] if text else ""
    if "/" not in token:
        return 0, 0
    a, b = token.split("/", 1)
    try:
        return int(a.strip()), int(b.strip())
    except ValueError:
        return 0, 0


def _pct(a: int, i: int) -> str:
    if i <= 0:
        return ""
    return f"{100.0 * a / i:.1f}"


def _pp(total: float, n: int) -> str:
    if n <= 0:
        return ""
    return f"{total / n:.2f}"


def _efg(fgm: int, tpm: int, fga: int) -> str:
    if fga <= 0:
        return ""
    return f"{100.0 * (fgm + 0.5 * tpm) / fga:.1f}"


def _ts(pts: int, fga: int, fta: int) -> str:
    denom = 2 * (fga + 0.44 * fta)
    if denom <= 0:
        return ""
    return f"{100.0 * pts / denom:.1f}"


def _hidden_fields(soup: BeautifulSoup) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for inp in soup.find_all("input"):
        if inp.get("name"):
            out[inp["name"]] = inp.get("value", "")
    for sel in soup.find_all("select"):
        if sel.get("name"):
            opt = sel.find("option", selected=True) or sel.find("option")
            out[sel["name"]] = opt.get("value", "") if opt else ""
    return out


def _postback(session: requests.Session, url: str, soup: BeautifulSoup, target: str, value: str) -> BeautifulSoup:
    data = _hidden_fields(soup)
    data["__EVENTTARGET"] = target
    data["__EVENTARGUMENT"] = ""
    data[target] = value
    r = session.post(
        url,
        data=data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def listar_partidos_calendario(
    session: requests.Session,
    calendar_url: str,
    grupo_id: str,
    equipo: str,
) -> List[Tuple[str, str, str, str]]:
    """Devuelve (local, resultado, visitante, url_partido) donde participa el equipo."""
    r = session.get(calendar_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    soup = _postback(session, calendar_url, soup, GRUPO_TARGET, grupo_id)

    target = _norm_equipo(equipo)
    out: List[Tuple[str, str, str, str]] = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        local = tds[0].get_text(" ", strip=True)
        res_td = tds[1]
        visit = tds[2].get_text(" ", strip=True)
        if _norm_equipo(local) != target and _norm_equipo(visit) != target:
            continue
        link = res_td.select_one("a[href*='Partido.aspx']")
        if not link:
            continue
        href = link.get("href", "")
        if href and not href.startswith("http"):
            href = "https://www.feb.es" + href
        out.append((local, link.get_text(strip=True), visit, href))
    return out


def parse_partido_equipo(html: str, equipo: str) -> TotalesTiro:
    soup = BeautifulSoup(html, "html.parser")
    target = _norm_equipo(equipo)

    for h in soup.select("h1.titulo-modulo"):
        if _norm_equipo(h.get_text(" ", strip=True)) != target:
            continue
        table = h.find_next("table")
        if not table:
            continue
        for tr in table.select("tr"):
            name_td = tr.select_one("td.nombre.jugador")
            pts_td = tr.select_one("td.puntos")
            t2_td = tr.select_one("td.tiros.dos")
            t3_td = tr.select_one("td.tiros.tres")
            tl_td = tr.select_one("td.tiros.libres")
            if not name_td or not pts_td or not t2_td or not t3_td or not tl_td:
                continue
            if name_td.get_text(strip=True):
                continue
            t2a, t2i = _parse_shot_partido(t2_td.get_text(" ", strip=True))
            t3a, t3i = _parse_shot_partido(t3_td.get_text(" ", strip=True))
            tla, tli = _parse_shot_partido(tl_td.get_text(" ", strip=True))
            return TotalesTiro(
                partidos=1,
                pts=int(pts_td.get_text(strip=True)),
                t2a=t2a,
                t2i=t2i,
                t3a=t3a,
                t3i=t3i,
                tla=tla,
                tli=tli,
            )
    raise ValueError(f"No se encontraron totales de equipo en acta para {equipo}")


def reconstruir_equipo(
    session: requests.Session,
    *,
    calendar_url: str,
    grupo_id: str,
    equipo: str,
) -> Tuple[TotalesTiro, List[Tuple[str, str, str, str]]]:
    partidos = listar_partidos_calendario(session, calendar_url, grupo_id, equipo)
    if not partidos:
        raise ValueError(f"Sin partidos en calendario para {equipo} (grupo {grupo_id})")

    ac = TotalesTiro()
    for local, resultado, visit, href in partidos:
        r = session.get(href, headers=HEADERS, timeout=30)
        r.raise_for_status()
        st = parse_partido_equipo(r.text, equipo)
        ac.add(st)
    return ac, partidos


def _row_from_totales(
    base_row: Dict[str, str],
    ac: TotalesTiro,
) -> Dict[str, str]:
    p = ac.partidos
    fgm = ac.t2a + ac.t3a
    fga = ac.t2i + ac.t3i
    row = dict(base_row)
    row["partidos"] = str(p)
    row["pts_total"] = str(ac.pts)
    row["pts_pp"] = _pp(ac.pts, p)
    row["tl_total"] = str(ac.tli)
    row["tl_pp"] = _pp(ac.tli, p)
    row["tl_aciertos"] = str(ac.tla)
    row["tl_aciertos_pp"] = _pp(ac.tla, p)
    row["tl_pct"] = _pct(ac.tla, ac.tli)
    row["t2_total"] = str(ac.t2i)
    row["t2_pp"] = _pp(ac.t2i, p)
    row["t2_aciertos"] = str(ac.t2a)
    row["t2_aciertos_pp"] = _pp(ac.t2a, p)
    row["t2_pct"] = _pct(ac.t2a, ac.t2i)
    row["t3_total"] = str(ac.t3i)
    row["t3_pp"] = _pp(ac.t3i, p)
    row["t3_aciertos"] = str(ac.t3a)
    row["t3_aciertos_pp"] = _pp(ac.t3a, p)
    row["t3_pct"] = _pct(ac.t3a, ac.t3i)
    row["fg_pct"] = _pct(fgm, fga)
    row["efg_pct"] = _efg(fgm, ac.t3a, fga)
    row["ts_pct"] = _ts(ac.pts, fga, ac.tli)
    return row


def corregir_csv(
    csv_path: Path,
    *,
    equipo: str,
    fase_id: str,
    ac: TotalesTiro,
) -> bool:
    target = _norm_equipo(equipo)
    rows: List[Dict[str, str]] = []
    updated = False

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            if str(row.get("fase_id", "")).strip() == fase_id and _norm_equipo(row.get("equipo", "")) == target:
                row = _row_from_totales(row, ac)
                updated = True
            rows.append(row)

    if not updated:
        return False

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Corrige stats FEB desde calendario + actas")
    p.add_argument("--equipo", default="CANTERBURY SCHOOL")
    p.add_argument("--grupo-id", default="89741", help="PRIMERA FASE H")
    p.add_argument("--fase-id", default="89741")
    p.add_argument("--calendar-url", default=CALENDAR_URL)
    p.add_argument(
        "--input",
        default=str(ROOT / "outputs" / "feb" / "lanzamiento_cespclubescadmasc_2025_todas.csv"),
    )
    p.add_argument("--resumir", action="store_true", default=True)
    args = p.parse_args()

    session = requests.Session()
    try:
        ac, partidos = reconstruir_equipo(
            session,
            calendar_url=args.calendar_url,
            grupo_id=args.grupo_id,
            equipo=args.equipo,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"Partidos encontrados: {len(partidos)}")
    for local, resultado, visit, href in partidos:
        print(f"  {local} {resultado} {visit}")
    print(
        f"Totales corregidos: {ac.pts} pts en {ac.partidos} PJ "
        f"({float(_pp(ac.pts, ac.partidos)):.2f} pts/PJ) | "
        f"2P {ac.t2a}/{ac.t2i} | 3P {ac.t3a}/{ac.t3i} | TL {ac.tla}/{ac.tli}"
    )

    inp = Path(args.input)
    if not inp.exists():
        print(f"No existe: {inp}", file=sys.stderr)
        return 1

    if not corregir_csv(inp, equipo=args.equipo, fase_id=args.fase_id, ac=ac):
        print("No se encontró fila para actualizar", file=sys.stderr)
        return 1
    print(f"Actualizado: {inp}")

    if args.resumir:
        sys.path.insert(0, str(ROOT / "analysis"))
        from sumarizar_feb_temporada import cargar_y_resumir, escribir_csv

        rows = cargar_y_resumir(inp)
        stem = inp.stem.replace("_todas", "")
        out = inp.parent / f"{stem}_resumen.csv"
        escribir_csv(out, rows)
        print(f"Resumen regenerado: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
