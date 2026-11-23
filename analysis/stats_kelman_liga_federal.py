# -*- coding: utf-8 -*-
"""Stats de Nicolas Kelman en Liga Federal (GES competencia 2032)."""

from __future__ import annotations

import json
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.partido import parse_boxscore_html
from ingest.febamba.mini_masc_regla_plantilla import parse_minutos_a_segundos
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider

ID_COMP = 2032
ID_CAT = 5117  # LA LIGA FEDERAL
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
OUT = ROOT / "outputs" / "liga_federal" / "kelman_2032.json"


def norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return " ".join(nfkd.encode("ascii", "ignore").decode("ascii").upper().split())


def to_int(x: object) -> int:
    if x is None:
        return 0
    if isinstance(x, int):
        return x
    s = str(x).strip()
    return int(s) if s.lstrip("-").isdigit() else 0


def pct(a: int, i: int) -> Optional[float]:
    return round(a / i * 100, 1) if i else None


def recolectar_river(ges: GesDeportivaExtractor, key: str) -> List[Dict[str, str]]:
    fases, _ = ges.get_ids_fases_grupos(ID_COMP, id_categoria=ID_CAT)
    out: List[Dict[str, str]] = []
    vistos: set = set()
    for nf, idf in fases.items():
        grupos = ges.get_grupos_de_fase(ID_COMP, ID_CAT, int(idf))
        for ng, ig in grupos.items():
            ps = ges.get_info_partidos(
                ID_CAT,
                "2025-1-1",
                "2026-12-31",
                key=key,
                id_fase=int(idf),
                id_grupo=int(ig),
            )
            for p in ps:
                loc = p.get("Local") or ""
                vis = p.get("Visitante") or ""
                if "RIVER" not in norm(loc) and "RIVER" not in norm(vis):
                    continue
                if p.get("Estado") != "COMPLETO":
                    continue
                tok = p.get("ID_PARTIDO") or ""
                if not tok or tok in vistos:
                    continue
                vistos.add(tok)
                out.append(
                    {
                        "token": tok,
                        "fase": nf,
                        "zona": ng,
                        "local": loc,
                        "visitante": vis,
                        "fecha": p.get("Fecha") or "",
                    }
                )
    return out


def fetch_box(tok: str) -> tuple[str, Optional[Dict[str, Any]]]:
    url = f"https://argentina.basketball/liga-federal/partido/estadisticas/{tok}==?key="
    try:
        r = requests.get(
            url, headers={"User-Agent": UA, "Accept": "text/html,*/*"}, timeout=45
        )
        r.raise_for_status()
        if len(r.text) < 8000:
            return tok, None
        return tok, parse_boxscore_html(r.text)
    except Exception:
        return tok, None


def main() -> int:
    key = json.loads((ROOT / "config" / "competencias.json").read_text(encoding="utf-8"))[
        "widget_key"
    ]
    ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
    print("Recolectando partidos de River en Liga Federal…", file=sys.stderr, flush=True)
    partidos = recolectar_river(ges, key)
    print(f"River COMPLETOS: {len(partidos)}", file=sys.stderr, flush=True)

    boxes: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(fetch_box, p["token"]) for p in partidos]
        for f in as_completed(futs):
            tok, box = f.result()
            boxes[tok] = box

    game_rows: List[Dict[str, Any]] = []
    for p in partidos:
        box = boxes.get(p["token"])
        if not box:
            continue
        equipos = box.get("equipos") or []
        lados = [
            (p["local"], equipos[0] if len(equipos) > 0 else None),
            (p["visitante"], equipos[1] if len(equipos) > 1 else None),
        ]
        for eq_name, eq in lados:
            if not eq or "RIVER" not in norm(eq.get("nombre") or eq_name):
                continue
            for j in eq.get("jugadores") or []:
                nom = norm(j.get("nombre") or "")
                nc = norm(j.get("nombre_completo") or "")
                if "KELMAN" not in nom and "KELMAN" not in nc:
                    continue
                seg = parse_minutos_a_segundos(j.get("min")) or 0
                rival = (
                    p["visitante"] if "RIVER" in norm(p["local"]) else p["local"]
                )
                game_rows.append(
                    {
                        "fecha": p["fecha"],
                        "fase": p["fase"],
                        "zona": p["zona"],
                        "rival": rival,
                        "localia": "L" if "RIVER" in norm(p["local"]) else "V",
                        "nombre": j.get("nombre"),
                        "nombre_completo": j.get("nombre_completo"),
                        "pid": j.get("pid"),
                        "min": j.get("min"),
                        "seg": seg,
                        "pts": to_int(j.get("pts")),
                        "reb": to_int(j.get("rebtot")),
                        "rebof": to_int(j.get("rebofe")),
                        "rebdef": to_int(j.get("rebdef")),
                        "ast": to_int(j.get("ast")),
                        "rob": to_int(j.get("rec")),
                        "per": to_int(j.get("per")),
                        "tap": to_int(j.get("tap_com")),
                        "fal": to_int(j.get("fal_com")),
                        "val": to_int(j.get("val")),
                        "t2a": to_int((j.get("t2") or {}).get("a")),
                        "t2i": to_int((j.get("t2") or {}).get("i")),
                        "t3a": to_int((j.get("t3") or {}).get("a")),
                        "t3i": to_int((j.get("t3") or {}).get("i")),
                        "tla": to_int((j.get("tl") or {}).get("a")),
                        "tli": to_int((j.get("tl") or {}).get("i")),
                    }
                )

    played = [g for g in game_rows if g["seg"] > 0]
    print(
        f"Líneas Kelman: {len(game_rows)} · PJ: {len(played)} · "
        f"boxes OK: {sum(1 for b in boxes.values() if b)}",
        file=sys.stderr,
        flush=True,
    )
    if not played:
        print("No se encontraron minutos de Kelman.", file=sys.stderr)
        return 1

    n = len(played)

    def avg(k: str) -> float:
        return round(sum(g[k] for g in played) / n, 1)

    def tot(k: str) -> int:
        return sum(g[k] for g in played)

    t2a, t2i = tot("t2a"), tot("t2i")
    t3a, t3i = tot("t3a"), tot("t3i")
    tla, tli = tot("tla"), tot("tli")
    fgm, fga = t2a + t3a, t2i + t3i
    ts = (
        round(tot("pts") / (2 * (fga + 0.44 * tli)) * 100, 1)
        if (fga + 0.44 * tli) > 0
        else None
    )
    efg = round((fgm + 0.5 * t3a) / fga * 100, 1) if fga else None
    min_p = round(sum(g["seg"] for g in played) / n / 60, 1)

    out = {
        "jugador": "Nicolas Kelman",
        "competencia_ges": ID_COMP,
        "url": f"https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia={ID_COMP}",
        "competicion": "LA LIGA FEDERAL",
        "equipo": "RIVER",
        "pj": n,
        "promedios": {
            "min_p": min_p,
            "pts_p": avg("pts"),
            "reb_p": avg("reb"),
            "ast_p": avg("ast"),
            "rob_p": avg("rob"),
            "per_p": avg("per"),
            "tap_p": avg("tap"),
            "fal_p": avg("fal"),
            "val_p": avg("val"),
            "t2_pct": pct(t2a, t2i),
            "t3_pct": pct(t3a, t3i),
            "tl_pct": pct(tla, tli),
            "ts_pct": ts,
            "efg_pct": efg,
        },
        "totales": {
            "pts": tot("pts"),
            "reb": tot("reb"),
            "ast": tot("ast"),
            "rob": tot("rob"),
            "per": tot("per"),
            "tap": tot("tap"),
            "val": tot("val"),
            "t2": f"{t2a}/{t2i}",
            "t3": f"{t3a}/{t3i}",
            "tl": f"{tla}/{tli}",
        },
        "partidos": sorted(played, key=lambda x: x["fecha"]),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Nicolas Kelman · Liga Federal (2032) · River ===")
    print(
        f"PJ={n}  Min/p={min_p}  Pts/p={avg('pts')}  Reb/p={avg('reb')}  "
        f"Ast/p={avg('ast')}  Rob/p={avg('rob')}  Per/p={avg('per')}  Val/p={avg('val')}"
    )
    print(
        f"2P%={pct(t2a, t2i)} ({t2a}/{t2i})  3P%={pct(t3a, t3i)} ({t3a}/{t3i})  "
        f"TL%={pct(tla, tli)} ({tla}/{tli})  TS%={ts}  eFG%={efg}"
    )
    print("--- partidos ---")
    for g in out["partidos"]:
        print(
            f"{g['fecha'][:16]:16} {g['fase'][:30]:30} {g['localia']} vs "
            f"{g['rival'][:28]:28} min={str(g['min']):5} pts={g['pts']:2} "
            f"reb={g['reb']:2} ast={g['ast']:2} val={g['val']:3}"
        )
    print(f"JSON: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
