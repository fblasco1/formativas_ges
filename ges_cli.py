#!/usr/bin/env python3
"""
Punto de entrada unificado para el pipeline 2026 (argentina.basketball) y utilidades.
Ejecutar desde la raíz del proyecto.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run_script(rel_path: str, forwarded: list[str], *, cwd: str | None = None) -> int:
    script = ROOT / rel_path
    if not script.is_file():
        print(f"No existe el script: {script}", file=sys.stderr)
        return 1
    env = os.environ.copy()
    root_s = str(ROOT)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root_s if not prev else f"{root_s}{os.pathsep}{prev}"
    proc = subprocess.run(
        [sys.executable, str(script)] + forwarded,
        cwd=cwd or root_s,
        env=env,
    )
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(
        prog="ges_cli",
        description="CLI: argentina.basketball 2026 a Postgres, FeBAMBA, DB.",
    )
    p.add_argument(
        "--out-dir",
        default="",
        help="Si se indica, cambia el cwd a ese directorio antes de ejecutar el subcomando.",
    )
    sub = p.add_subparsers(dest="domain", required=True)

    p_arg = sub.add_parser("argbasket", help="Fixture / ingest / partido (argentina.basketball)")
    p_arg.add_argument(
        "action",
        choices=("fixture", "ingest", "partido"),
        help="fixture=CSV consolidado; ingest=Postgres; partido=JSON un partido",
    )
    p_arg.add_argument("rest", nargs=argparse.REMAINDER, help="Argumentos del script destino")

    p_db = sub.add_parser("db", help="Persistencia y consultas")
    p_db.add_argument(
        "action",
        choices=("persist-lotes", "consultar", "export-fixture", "contextualizar"),
    )
    p_db.add_argument("rest", nargs=argparse.REMAINDER)

    p_fx = sub.add_parser("fixture", help="Utilidades CSV de fixture")
    p_fx.add_argument("action", choices=("unify",))
    p_fx.add_argument("rest", nargs=argparse.REMAINDER)

    p_in = sub.add_parser("ingest", help="Ingesta FeBAMBA/GES (main.py)")
    p_in.add_argument("action", choices=("febamba",))
    p_in.add_argument("rest", nargs=argparse.REMAINDER)

    ns = p.parse_args(argv)

    out_dir = (ns.out_dir or "").strip()
    cwd_run = str(ROOT)
    if out_dir:
        try:
            os.makedirs(out_dir, exist_ok=True)
            cwd_run = str(Path(out_dir).resolve())
        except OSError as exc:
            print(f"No se pudo usar --out-dir {out_dir!r}: {exc}", file=sys.stderr)
            return 1

    if ns.domain == "argbasket":
        fwd = list(ns.rest or [])
        if fwd and fwd[0] == "--":
            fwd = fwd[1:]
        if ns.action == "fixture":
            return _run_script("ingest/argbasket/pipeline_fixture.py", fwd, cwd=cwd_run)
        if ns.action == "ingest":
            return _run_script("ingest/argbasket/pipeline_to_postgres.py", fwd, cwd=cwd_run)
        if ns.action == "partido":
            return _run_script("extraer_boxscore_pbp_argbasket.py", fwd, cwd=cwd_run)
        return 2

    if ns.domain == "db":
        fwd = list(ns.rest or [])
        if fwd and fwd[0] == "--":
            fwd = fwd[1:]
        if ns.action == "persist-lotes":
            return _run_script("persist/persistir_postgres.py", fwd, cwd=cwd_run)
        if ns.action == "consultar":
            return _run_script("consultar_partidos.py", fwd, cwd=cwd_run)
        if ns.action == "export-fixture":
            return _run_script("cargar_fixture_consolidado.py", fwd, cwd=cwd_run)
        if ns.action == "contextualizar":
            return _run_script("contextualizar_partidos_natural_key.py", fwd, cwd=cwd_run)
        return 2

    if ns.domain == "fixture":
        fwd = list(ns.rest or [])
        if fwd and fwd[0] == "--":
            fwd = fwd[1:]
        if ns.action == "unify":
            return _run_script("unificar_fixture.py", fwd, cwd=cwd_run)
        return 2

    if ns.domain == "ingest":
        fwd = list(ns.rest or [])
        if fwd and fwd[0] == "--":
            fwd = fwd[1:]
        if ns.action == "febamba":
            return _run_script("main.py", fwd, cwd=cwd_run)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
