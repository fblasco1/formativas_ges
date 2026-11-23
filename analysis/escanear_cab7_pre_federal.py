# -*- coding: utf-8 -*-
"""Escanea GES (competicion.aspx) buscando REGIÓN DEPORTIVA CAB N° 7 + PRE FEDERAL MASCULINO.

Ejemplo:
  py -3.13 analysis/escanear_cab7_pre_federal.py
  py -3.13 analysis/escanear_cab7_pre_federal.py --desde 0 --hasta 9999 --workers 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

URL = "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia={id}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    )
}

RE_SPAN = re.compile(
    r'id="(LTemporada|LTituloCompeticion|LTituloDelegacion)"[^>]*>([^<]*)',
    re.I,
)
RE_CAT_OPT = re.compile(
    r'<select[^>]*id="DDLCategorias"[^>]*>(.*?)</select>',
    re.I | re.S,
)
RE_OPTION = re.compile(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', re.I)

_tls = threading.local()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.upper().split())


def _session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        _tls.session = s
    return s


def parse_page(html: str) -> Dict[str, object]:
    fields = {m.group(1): m.group(2).strip() for m in RE_SPAN.finditer(html)}
    cats: Dict[str, str] = {}
    msel = RE_CAT_OPT.search(html)
    if msel:
        for val, name in RE_OPTION.findall(msel.group(1)):
            val = val.strip()
            name = " ".join(name.split())
            if val:
                cats[name] = val
    return {
        "temporada": fields.get("LTemporada", ""),
        "titulo": fields.get("LTituloCompeticion", ""),
        "delegacion": fields.get("LTituloDelegacion", ""),
        "categorias": cats,
    }


def probe(comp_id: int) -> Dict[str, object]:
    url = URL.format(id=comp_id)
    try:
        r = _session().get(url, headers=HEADERS, timeout=20)
        html = r.text
        parsed = (
            parse_page(html)
            if "LTituloCompeticion" in html or "LTemporada" in html
            else {"temporada": "", "titulo": "", "delegacion": "", "categorias": {}}
        )
        return {"id": comp_id, "status": r.status_code, "ok": True, "url": url, **parsed}
    except Exception as exc:
        return {
            "id": comp_id,
            "status": -1,
            "ok": False,
            "error": str(exc),
            "url": url,
            "temporada": "",
            "titulo": "",
            "delegacion": "",
            "categorias": {},
        }


def es_cab7(delegacion: str) -> bool:
    # NFKD convierte "Nº" -> "No" -> "NO"; aceptar CAB NO 7 / CAB N 7 / CAB N°7.
    n = _norm(delegacion).replace("°", " ").replace("º", " ").replace("ª", " ")
    n = " ".join(n.split())
    if "REGION DEPORTIVA" not in n or "CAB" not in n:
        return False
    return bool(re.search(r"\bCAB\s+N(?:O)?\s*[:.]?\s*0*7\b", n))


def tiene_pre_federal_masculino(titulo: str, categorias: Dict[str, str]) -> bool:
    if "PRE FEDERAL MASCULINO" in _norm(titulo):
        return True
    return any("PRE FEDERAL MASCULINO" in _norm(name) for name in categorias)


def compact_row(row: Dict[str, object]) -> Dict[str, object]:
    cats = row.get("categorias") or {}
    return {
        "id": row["id"],
        "temporada": str(row.get("temporada") or "").strip(),
        "titulo": str(row.get("titulo") or ""),
        "delegacion": str(row.get("delegacion") or ""),
        "n_categorias": len(cats),
        "categorias": cats,
        "url": row.get("url") or URL.format(id=row["id"]),
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Busca REGIÓN DEPORTIVA CAB N° 7 + PRE FEDERAL MASCULINO en GES."
    )
    p.add_argument("--desde", type=int, default=0)
    p.add_argument("--hasta", type=int, default=9999)
    p.add_argument("--workers", type=int, default=20)
    p.add_argument(
        "--out-dir",
        default=str(ROOT / "outputs" / "ges_scan"),
    )
    p.add_argument(
        "--solo-match",
        action="store_true",
        help="Solo guarda matches exactos (CAB7 + PRE FEDERAL MASCULINO). Por defecto también lista todo CAB7.",
    )
    args = p.parse_args()

    if args.hasta < args.desde:
        print("--hasta debe ser >= --desde", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ids = list(range(args.desde, args.hasta + 1))
    total = len(ids)
    print(
        f"Escaneando {args.desde}-{args.hasta} ({total} ids, {args.workers} workers)",
        flush=True,
    )
    print("Filtro: REGIÓN DEPORTIVA CAB N° 7 + PRE FEDERAL MASCULINO", flush=True)

    hits_match: List[Dict[str, object]] = []
    hits_cab7: List[Dict[str, object]] = []
    errors = 0
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(probe, i): i for i in ids}
        for fut in as_completed(futs):
            row = fut.result()
            done += 1
            if not row.get("ok"):
                errors += 1

            titulo = str(row.get("titulo") or "")
            delegacion = str(row.get("delegacion") or "")
            cats = row.get("categorias") or {}
            if not titulo and not delegacion:
                if done % 500 == 0:
                    _progress(done, total, hits_match, hits_cab7, errors)
                continue

            if not es_cab7(delegacion):
                if done % 500 == 0:
                    _progress(done, total, hits_match, hits_cab7, errors)
                continue

            compact = compact_row(row)
            hits_cab7.append(compact)
            is_match = tiene_pre_federal_masculino(titulo, cats)  # type: ignore[arg-type]
            if is_match:
                hits_match.append(compact)
                print(
                    f"MATCH {compact['id']}\t{compact['temporada']}\t"
                    f"{compact['titulo']}\t{list(compact['categorias'].keys())}",
                    flush=True,
                )
            else:
                print(
                    f"CAB7  {compact['id']}\t{compact['temporada']}\t"
                    f"{compact['titulo']}\t{list(compact['categorias'].keys())}",
                    flush=True,
                )

            if done % 500 == 0:
                _progress(done, total, hits_match, hits_cab7, errors)
                _dump(out_dir, args, hits_match, hits_cab7, errors)

    _dump(out_dir, args, hits_match, hits_cab7, errors)
    print("--- FIN ---", flush=True)
    print(f"MATCH CAB7 + PRE FEDERAL MASCULINO: {len(hits_match)}", flush=True)
    for h in sorted(hits_match, key=lambda x: int(x["id"])):
        cats = h["categorias"]
        print(
            f"  {h['id']:>4}  {h['temporada']}  {h['titulo']}  {cats}",
            flush=True,
        )
    if not args.solo_match:
        print(f"CAB N7 (todas): {len(hits_cab7)}", flush=True)
    print(f"Errores: {errors}", flush=True)
    print(f"Salida: {out_dir / 'cab7_pre_federal.json'}", flush=True)
    return 0


def _progress(
    done: int,
    total: int,
    hits_match: List[Dict[str, object]],
    hits_cab7: List[Dict[str, object]],
    errors: int,
) -> None:
    print(
        f"  {done}/{total}  match={len(hits_match)}  cab7={len(hits_cab7)}  err={errors}",
        flush=True,
    )


def _dump(
    out_dir: Path,
    args: argparse.Namespace,
    hits_match: List[Dict[str, object]],
    hits_cab7: List[Dict[str, object]],
    errors: int,
) -> None:
    payload = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "rango": [args.desde, args.hasta],
        "filtro_delegacion": "REGION DEPORTIVA CAB N° 7",
        "filtro_categoria_o_titulo": "PRE FEDERAL MASCULINO",
        "n_match": len(hits_match),
        "n_cab7": len(hits_cab7),
        "errores": errors,
        "matches": sorted(hits_match, key=lambda x: int(x["id"])),
        "cab7_todas": []
        if args.solo_match
        else sorted(hits_cab7, key=lambda x: int(x["id"])),
    }
    (out_dir / "cab7_pre_federal.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
