from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

import requests

from ingest.argbasket.partido import (
    BASE_URL_DEFAULT,
    fetch_partido_en_vivo_html,
    fetch_partido_estadisticas_html,
    parse_boxscore_html,
    parse_play_by_play_html,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extrae boxscore y play-by-play desde argentina.basketball para un partido."
    )
    p.add_argument("--id-partido-token", required=True, help="Token tipo: tyXdruVpQxJ9...==")
    p.add_argument("--base-url", default=BASE_URL_DEFAULT)
    p.add_argument("--output", default="", help="Si se pasa, escribe JSON a este path")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    s = requests.Session()

    stats_html = fetch_partido_estadisticas_html(
        id_partido_token=args.id_partido_token, base_url=args.base_url, session=s
    )
    pbp_html = fetch_partido_en_vivo_html(
        id_partido_token=args.id_partido_token, base_url=args.base_url, session=s
    )

    payload = {
        "id_partido_token": args.id_partido_token,
        "boxscore": parse_boxscore_html(stats_html),
        "play_by_play": parse_play_by_play_html(pbp_html),
    }

    out_json = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"OK: escrito {args.output}")
    else:
        print(out_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

