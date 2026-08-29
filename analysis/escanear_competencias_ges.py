# -*- coding: utf-8 -*-
"""Escanea competicion.aspx por ID y filtra por delegación + temporada."""

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

DELEGACION_OBJETIVO = "FEDERACION DE BASQUETBOL DEL AREA METROPOLITANA DE BUENOS AIRES"

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
        parsed = parse_page(html) if "LTituloCompeticion" in html or "LTemporada" in html else {
            "temporada": "",
            "titulo": "",
            "delegacion": "",
            "categorias": {},
        }
        return {
            "id": comp_id,
            "status": r.status_code,
            "bytes": len(html),
            "ok": True,
            **parsed,
        }
    except Exception as exc:
        return {
            "id": comp_id,
            "status": -1,
            "bytes": 0,
            "ok": False,
            "error": str(exc),
            "temporada": "",
            "titulo": "",
            "delegacion": "",
            "categorias": {},
        }


def es_febamba(delegacion: str) -> bool:
    n = _norm(delegacion)
    if n == DELEGACION_OBJETIVO:
        return True
    return "AREA METROPOLITANA DE BUENOS AIRES" in n and "FEDERACION" in n


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--desde", type=int, default=1)
    p.add_argument("--hasta", type=int, default=9999)
    p.add_argument("--workers", type=int, default=10)
    p.add_argument(
        "--out-dir",
        default=str(ROOT / "outputs" / "ges_scan"),
    )
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = list(range(args.desde, args.hasta + 1))
    total = len(ids)
    print(f"Escaneando {args.desde}-{args.hasta} ({total} ids, {args.workers} workers)", flush=True)

    hits_febamba_2026: List[Dict[str, object]] = []
    hits_2026: List[Dict[str, object]] = []
    hits_febamba: List[Dict[str, object]] = []
    errors: List[Dict[str, object]] = []
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(probe, i): i for i in ids}
        for fut in as_completed(futs):
            row = fut.result()
            done += 1
            if not row.get("ok"):
                errors.append(row)
            titulo = str(row.get("titulo") or "")
            temporada = str(row.get("temporada") or "").strip()
            delegacion = str(row.get("delegacion") or "")
            compact = {
                "id": row["id"],
                "temporada": temporada,
                "titulo": titulo,
                "delegacion": delegacion,
                "n_categorias": len(row.get("categorias") or {}),
                "categorias": row.get("categorias") or {},
                "url": URL.format(id=row["id"]),
            }
            if titulo:
                if temporada == "2026":
                    hits_2026.append(compact)
                if es_febamba(delegacion):
                    hits_febamba.append(compact)
                    if temporada == "2026":
                        hits_febamba_2026.append(compact)
                        print(
                            f"MATCH {row['id']}\t{titulo}\tcats={compact['n_categorias']}",
                            flush=True,
                        )
            if done % 250 == 0:
                print(
                    f"  {done}/{total}  febamba2026={len(hits_febamba_2026)}  "
                    f"t2026={len(hits_2026)}  err={len(errors)}",
                    flush=True,
                )
                _dump(out_dir, hits_febamba_2026, hits_2026, hits_febamba, errors)

    _dump(out_dir, hits_febamba_2026, hits_2026, hits_febamba, errors)
    print("--- FIN ---", flush=True)
    print(f"FeBAMBA 2026: {len(hits_febamba_2026)}", flush=True)
    for h in sorted(hits_febamba_2026, key=lambda x: int(x["id"])):
        cats = ", ".join(h["categorias"].keys()) or "-"
        print(f"  {h['id']:>4}  {h['titulo']}  [{cats}]", flush=True)
    print(f"FeBAMBA (todas las temporadas): {len(hits_febamba)}", flush=True)
    print(f"Temporada 2026 (cualquier federación): {len(hits_2026)}", flush=True)
    print(f"Errores: {len(errors)}", flush=True)
    print(f"Salida: {out_dir}", flush=True)
    return 0


def _dump(
    out_dir: Path,
    febamba_2026: List[Dict[str, object]],
    t2026: List[Dict[str, object]],
    febamba: List[Dict[str, object]],
    errors: List[Dict[str, object]],
) -> None:
    payload = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "filtro_delegacion": DELEGACION_OBJETIVO,
        "filtro_temporada": "2026",
        "n": len(febamba_2026),
        "competencias": sorted(febamba_2026, key=lambda x: int(x["id"])),
    }
    (out_dir / "febamba_2026.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "temporada_2026.json").write_text(
        json.dumps(
            {"n": len(t2026), "competencias": sorted(t2026, key=lambda x: int(x["id"]))},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "febamba_todas.json").write_text(
        json.dumps(
            {"n": len(febamba), "competencias": sorted(febamba, key=lambda x: int(x["id"]))},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if errors:
        (out_dir / "errores.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
