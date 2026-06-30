# -*- coding: utf-8 -*-
"""
Buscador LOCAL de jugadores destacados por estadísticas (FORMATIVAS GES 2015).

Genera una página HTML autocontenida con una tabla de jugadores buscable,
filtrable y ordenable, basada en PROMEDIOS por partido, para las categorías:

  U13 = INFANTILES MASCULINO   (id_categoria 5078)
  U15 = CADETES MASCULINO      (id_categoria 5077)
  U17 = JUVENILES MASCULINO    (id_categoria 5076)
  U21 = LIGA PROXIMO MASCULINO (id_categoria 5075)

ESTO ES LOCAL: el HTML se guarda en ``outputs/buscador/`` y NO se publica en
docs/ ni se comitea.

Ejemplos (Windows PowerShell):
  .venv\\Scripts\\python.exe analysis/buscador_jugadores_destacados.py --progress
  .venv\\Scripts\\python.exe analysis/buscador_jugadores_destacados.py --desde-cache
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.partido import parse_boxscore_html
from ingest.febamba.mini_masc_regla_plantilla import parse_minutos_a_segundos
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider

ID_COMPETENCIA = 2015

# edad -> metadatos GES de la categoría (solo para este buscador).
CATEGORIAS: Dict[str, Dict[str, object]] = {
    "U13": {"nombre_ges": "INFANTILES MASCULINO", "id_categoria": 5078},
    "U15": {"nombre_ges": "CADETES MASCULINO", "id_categoria": 5077},
    "U17": {"nombre_ges": "JUVENILES MASCULINO", "id_categoria": 5076},
    "U21": {"nombre_ges": "LIGA PROXIMO MASCULINO", "id_categoria": 5075},
}

OUT_DIR = ROOT / "outputs" / "buscador"
OUT_HTML = OUT_DIR / "buscador_jugadores.html"
BOX_FULL_CACHE = OUT_DIR / "boxscores_full.json"
PARTIDOS_CACHE = OUT_DIR / "partidos.json"

# Publicación cifrada (GitHub Pages, branch estadisticas).
DOCS_HTML = ROOT / "docs" / "buscador_jugadores.html"
PUBLIC_URL = "https://fblasco1.github.io/formativas_ges/buscador_jugadores.html"

# Parámetros de cifrado (deben coincidir con el JS de Web Crypto).
PBKDF2_ITER = 200000
PBKDF2_DKLEN = 32  # AES-256

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def _load_widget_key() -> str:
    with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return 0


def normalizar_nombre(nombre: str) -> str:
    """Mayúsculas, sin acentos, sin espacios extra (clave de jugador)."""
    nfkd = unicodedata.normalize("NFKD", nombre or "")
    base = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(base.upper().split())


# --------------------------------------------------------------------------- #
# Recolección de partidos COMPLETOS de las 4 categorías (todas las fases/grupos)
# --------------------------------------------------------------------------- #
def recolectar_partidos(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    progress: bool = False,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    vistos: set = set()
    for edad, meta in CATEGORIAS.items():
        cat = int(meta["id_categoria"])
        fases, _ = ges.get_ids_fases_grupos(ID_COMPETENCIA, id_categoria=cat)
        if progress:
            print(
                f"{edad} ({meta['nombre_ges']}): {len(fases)} fases",
                file=sys.stderr,
                flush=True,
            )
        if not fases:
            if progress:
                print(f"  ⚠ {edad}: sin fases (¿categoría inexistente?)", file=sys.stderr)
            continue
        for nombre_fase, id_fase in fases.items():
            grupos = ges.get_grupos_de_fase(ID_COMPETENCIA, cat, int(id_fase))
            n_cat = 0
            for nombre_grupo, id_grupo in grupos.items():
                partidos = ges.get_info_partidos(
                    cat,
                    fecha_ini,
                    fecha_fin,
                    key=key,
                    id_fase=int(id_fase),
                    id_grupo=int(id_grupo),
                )
                for p in partidos:
                    if p.get("Estado") != "COMPLETO":
                        continue
                    token = p.get("ID_PARTIDO") or ""
                    if not token or token in vistos:
                        continue
                    vistos.add(token)
                    out.append(
                        {
                            "id_partido": token,
                            "categoria": edad,
                            "fase": nombre_fase,
                            "zona": nombre_grupo,
                            "local": p.get("Local") or "",
                            "visitante": p.get("Visitante") or "",
                            "fecha": p.get("Fecha") or "",
                        }
                    )
                    n_cat += 1
            if progress:
                print(
                    f"  {edad} · {nombre_fase}: {len(grupos)} grupos",
                    file=sys.stderr,
                    flush=True,
                )
        if progress:
            tot = sum(1 for x in out if x["categoria"] == edad)
            print(f"  {edad}: {tot} partidos COMPLETOS", file=sys.stderr, flush=True)
    return out


# --------------------------------------------------------------------------- #
# Boxscores con estadísticas COMPLETAS (caché propia)
# --------------------------------------------------------------------------- #
def _descargar_box_full(token: str) -> Dict[str, object]:
    try:
        resp = requests.get(
            _boxscore_url(token),
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            timeout=45,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return {"ok": False}
    if len(html) < 8000:
        return {"ok": False}
    equipos = parse_boxscore_html(html).get("equipos") or []
    if not equipos:
        return {"ok": False}
    # Solo guardamos nombre + jugadores (con stats completas) para acotar tamaño.
    out = [
        {"nombre": eq.get("nombre") or "", "jugadores": eq.get("jugadores") or []}
        for eq in equipos[:2]
    ]
    return {"ok": True, "equipos": out}


def _cargar_box_cache() -> Dict[str, Dict[str, object]]:
    if BOX_FULL_CACHE.exists():
        try:
            return json.loads(BOX_FULL_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _guardar_box_cache(cache: Dict[str, Dict[str, object]]) -> None:
    BOX_FULL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BOX_FULL_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def descargar_boxscores_full(
    tokens: List[str],
    *,
    workers: int = 12,
    progress: bool = False,
    limite: int = 0,
    sin_descarga: bool = False,
) -> Dict[str, Dict[str, object]]:
    cache = _cargar_box_cache()
    unicos = [t for t in dict.fromkeys(tokens) if t]
    pendientes = [t for t in unicos if t not in cache]
    if limite > 0:
        pendientes = pendientes[:limite]
    if progress:
        print(
            f"Boxscores full: {len(unicos)} partidos, {len(cache)} en caché, "
            f"{len(pendientes)} a descargar…",
            file=sys.stderr,
        )
    if pendientes and not sin_descarga:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut = {pool.submit(_descargar_box_full, t): t for t in pendientes}
            done = 0
            for f in as_completed(fut):
                cache[fut[f]] = f.result()
                done += 1
                if progress and (done % 100 == 0 or done == len(pendientes)):
                    print(f"  {done}/{len(pendientes)}", file=sys.stderr, flush=True)
        _guardar_box_cache(cache)
    return {t: cache[t] for t in unicos if t in cache and cache[t].get("ok")}


# --------------------------------------------------------------------------- #
# Agregación por jugador
# --------------------------------------------------------------------------- #
_ACUM_CAMPOS = (
    ("pts", "pts"),
    ("rebtot", "reb"),
    ("rebofe", "rebof"),
    ("rebdef", "rebdef"),
    ("ast", "ast"),
    ("rec", "rob"),
    ("per", "per"),
    ("tap_com", "tap"),
    ("fal_com", "fal"),
    ("val", "val"),
)


def agregar_jugadores(
    partidos: List[Dict[str, str]],
    boxscores: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    # clave -> acumulador
    acc: Dict[Tuple[str, str, str], Dict[str, object]] = {}

    for p in partidos:
        box = boxscores.get(p["id_partido"])
        if not box or not box.get("ok"):
            continue
        equipos = box.get("equipos") or []
        # equipos[0] = local, equipos[1] = visitante (mapeo por índice del acta).
        lados = [
            (p.get("local") or "", equipos[0] if len(equipos) > 0 else None),
            (p.get("visitante") or "", equipos[1] if len(equipos) > 1 else None),
        ]
        for equipo_nombre, eq in lados:
            if not eq:
                continue
            equipo_disp = eq.get("nombre") or equipo_nombre
            for j in eq.get("jugadores") or []:
                seg = parse_minutos_a_segundos(j.get("min")) or 0
                if seg <= 0:
                    continue  # DNP: no cuenta como partido jugado
                nombre = (j.get("nombre") or "").strip()
                if not nombre:
                    continue
                clave = (p["categoria"], normalizar_nombre(equipo_disp), normalizar_nombre(nombre))
                a = acc.get(clave)
                if a is None:
                    a = {
                        "nombre": nombre,
                        "equipo": equipo_disp,
                        "categoria": p["categoria"],
                        "pj": 0,
                        "seg": 0,
                    }
                    for _, alias in _ACUM_CAMPOS:
                        a[alias] = 0
                    acc[clave] = a
                a["pj"] += 1
                a["seg"] += seg
                for campo, alias in _ACUM_CAMPOS:
                    a[alias] += _to_int(j.get(campo))

    out: List[Dict[str, object]] = []
    for a in acc.values():
        pj = a["pj"]
        if pj <= 0:
            continue

        def avg(x: int) -> float:
            return round(x / pj, 1)

        out.append(
            {
                "nombre": a["nombre"],
                "equipo": a["equipo"],
                "cat": a["categoria"],
                "pj": pj,
                "min_p": round((a["seg"] / pj) / 60.0, 1),
                "pts_p": avg(a["pts"]),
                "reb_p": avg(a["reb"]),
                "ast_p": avg(a["ast"]),
                "rob_p": avg(a["rob"]),
                "tap_p": avg(a["tap"]),
                "val_p": avg(a["val"]),
                # totales (para tooltip / referencia)
                "pts": a["pts"],
                "reb": a["reb"],
                "ast": a["ast"],
                "rob": a["rob"],
                "tap": a["tap"],
                "val": a["val"],
            }
        )
    out.sort(key=lambda d: (-d["pts_p"], -d["pj"], d["nombre"]))
    return out


# --------------------------------------------------------------------------- #
# Render HTML autocontenido
# --------------------------------------------------------------------------- #
def _build_html(
    *,
    fecha: str,
    cat_opts: str,
    data_decl: str,
    arranque: str,
    login_block: str = "",
    app_style: str = "",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>FORMATIVAS 2026 · Buscador de jugadores destacados</title>
  <style>
    :root {{
      --bg:#f1f5f9; --paper:#fff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0;
      --accent:#1d4ed8; --accent-soft:#eff6ff; --ok:#059669;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg);
      color:var(--text); line-height:1.45; }}
    .layout {{ max-width:1180px; margin:0 auto; padding:20px; }}
    header, section {{ background:var(--paper); border:1px solid var(--line);
      border-radius:14px; padding:18px 20px; margin-bottom:16px; }}
    h1 {{ margin:0 0 4px; font-size:23px; }}
    .subtitle {{ color:var(--muted); font-size:13px; margin:0; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; }}
    label.fld {{ font-size:12px; color:var(--muted); display:flex; flex-direction:column; gap:4px; }}
    input, select {{ border:1px solid var(--line); border-radius:8px; padding:8px 10px;
      font-size:13px; background:#fff; color:var(--text); }}
    input[type="search"] {{ min-width:220px; }}
    input[type="number"] {{ width:120px; }}
    .count {{ margin-left:auto; font-size:13px; color:var(--muted); align-self:center; }}
    .count b {{ color:var(--accent); font-size:16px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:8px 8px; text-align:center; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.04em;
      cursor:pointer; user-select:none; position:sticky; top:0; background:var(--paper); }}
    th:hover {{ color:var(--accent); }}
    th.sorted-asc::after {{ content:" ▲"; color:var(--accent); }}
    th.sorted-desc::after {{ content:" ▼"; color:var(--accent); }}
    td.eq, th.eq {{ text-align:left; }}
    td.nm {{ text-align:left; font-weight:600; }}
    td.rank {{ color:var(--muted); }}
    td.main {{ font-weight:800; color:var(--accent); }}
    .cat-badge {{ display:inline-block; border-radius:999px; padding:1px 8px; font-size:11px;
      background:var(--accent-soft); color:var(--accent); font-weight:600; }}
    tbody tr:hover {{ background:#f8fafc; }}
    .tablewrap {{ overflow:auto; max-height:72vh; border:1px solid var(--line); border-radius:10px; }}
    .note {{ font-size:12px; color:var(--muted); margin-top:10px; }}
    .btn {{ border:1px solid var(--accent); color:var(--accent); background:#fff; border-radius:8px;
      padding:8px 14px; font-size:13px; font-weight:600; cursor:pointer; }}
    .btn:hover {{ background:var(--accent-soft); }}
    details.statfilters {{ margin-top:14px; border:1px solid var(--line); border-radius:10px;
      padding:10px 14px; background:#fafbfc; }}
    details.statfilters > summary {{ cursor:pointer; font-size:13px; font-weight:600; color:var(--text);
      list-style:none; }}
    details.statfilters > summary::-webkit-details-marker {{ display:none; }}
    details.statfilters > summary::before {{ content:"▸ "; color:var(--accent); }}
    details.statfilters[open] > summary::before {{ content:"▾ "; }}
    .rangos-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px 16px; margin-top:12px; }}
    .rango {{ display:flex; flex-direction:column; gap:4px; }}
    .rango .lbl {{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
    .rango .pair {{ display:flex; align-items:center; gap:6px; }}
    .rango .pair input {{ width:100%; min-width:0; padding:6px 8px; }}
    .rango .pair span {{ color:var(--muted); font-size:12px; }}
    @media (max-width:900px) {{ .rangos-grid {{ grid-template-columns:repeat(2,1fr); }} }}
    .login-wrap {{ max-width:420px; margin:6vh auto 0; }}
    .login-card {{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:24px; }}
    .login-card h2 {{ margin:0 0 6px; font-size:18px; }}
    .login-card p {{ margin:0 0 14px; color:var(--muted); font-size:13px; }}
    .login-row {{ display:flex; gap:8px; }}
    .login-row input {{ flex:1; }}
    .login-err {{ color:#dc2626; font-size:13px; margin-top:10px; min-height:18px; }}
  </style>
</head>
<body>
  <div class="layout">
    <header>
      <h1>Buscador de jugadores destacados</h1>
      <p class="subtitle">FORMATIVAS · Competencia GES 2015 · Masculino · Promedios por partido · Actualizado: {fecha}</p>
    </header>
{login_block}
    <div id="app"{app_style}>
    <section>
      <div class="toolbar">
        <label class="fld">Categoría
          <select id="f-cat"><option value="">Todas</option>{cat_opts}</select>
        </label>
        <label class="fld">Buscar jugador
          <input type="search" id="f-nombre" placeholder="Nombre…"/>
        </label>
        <label class="fld">Buscar equipo
          <input type="search" id="f-equipo" placeholder="Equipo…"/>
        </label>
        <button type="button" class="btn" id="f-limpiar">Limpiar filtros</button>
        <span class="count"><b id="n-filas">0</b> jugadores</span>
      </div>
      <details class="statfilters" open>
        <summary>Filtros por estadística (rango mín–máx, combinables)</summary>
        <div class="rangos-grid" id="rangos"></div>
      </details>
      <p class="note">Clic en cualquier encabezado para ordenar (asc/desc). Los rangos se combinan entre sí y con la búsqueda (lógica Y: se muestran los jugadores que cumplen TODOS los filtros activos). Min/p = minutos por partido; el resto son promedios por partido (Rob = robos, Tap = tapones a favor, Val = valoración).</p>
      <div class="tablewrap">
        <table>
          <thead><tr id="thead"></tr></thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </section>
    </div>
  </div>

  <script>
    {data_decl}
    const COLS = [
      {{key:"__rank", label:"#", type:"rank"}},
      {{key:"nombre", label:"Jugador", type:"text", cls:"nm"}},
      {{key:"equipo", label:"Equipo", type:"text", cls:"eq"}},
      {{key:"cat", label:"Cat.", type:"cat"}},
      {{key:"pj", label:"PJ", type:"num"}},
      {{key:"min_p", label:"Min/p", type:"num"}},
      {{key:"pts_p", label:"Pts/p", type:"num", main:true}},
      {{key:"reb_p", label:"Reb/p", type:"num"}},
      {{key:"ast_p", label:"Ast/p", type:"num"}},
      {{key:"rob_p", label:"Rob/p", type:"num"}},
      {{key:"tap_p", label:"Tap/p", type:"num"}},
      {{key:"val_p", label:"Val/p", type:"num"}},
    ];
    // Columnas numéricas con filtro de rango (mín–máx). PJ arranca con mín=3.
    const RANGOS = [
      {{key:"pj", label:"PJ", def_min:"3"}},
      {{key:"min_p", label:"Min/p"}},
      {{key:"pts_p", label:"Pts/p"}},
      {{key:"reb_p", label:"Reb/p"}},
      {{key:"ast_p", label:"Ast/p"}},
      {{key:"rob_p", label:"Rob/p"}},
      {{key:"tap_p", label:"Tap/p"}},
      {{key:"val_p", label:"Val/p"}},
    ];
    let sortKey = "pts_p";
    let sortDir = -1; // -1 desc, 1 asc

    function esc(s) {{ return (s==null?"":String(s)).replace(/[&<>]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c])); }}

    function buildRangos() {{
      const cont = document.getElementById("rangos");
      cont.innerHTML = RANGOS.map(r => `
        <div class="rango">
          <span class="lbl">${{esc(r.label)}}</span>
          <div class="pair">
            <input type="number" step="any" inputmode="decimal" id="min-${{r.key}}" placeholder="mín" value="${{r.def_min||""}}"/>
            <span>–</span>
            <input type="number" step="any" inputmode="decimal" id="max-${{r.key}}" placeholder="máx"/>
          </div>
        </div>`).join("");
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).addEventListener("input", render);
        document.getElementById("max-" + r.key).addEventListener("input", render);
      }});
    }}

    function _numVal(id) {{
      const v = (document.getElementById(id).value || "").trim();
      if (v === "") return null;
      const n = parseFloat(v);
      return isNaN(n) ? null : n;
    }}

    function renderHead() {{
      const tr = document.getElementById("thead");
      tr.innerHTML = COLS.map(c => {{
        if (c.type === "rank") return `<th class="rank"></th>`;
        let cls = c.cls || "";
        if (c.key === sortKey) cls += sortDir < 0 ? " sorted-desc" : " sorted-asc";
        return `<th class="${{cls}}" data-key="${{c.key}}">${{esc(c.label)}}</th>`;
      }}).join("");
      tr.querySelectorAll("th[data-key]").forEach(th => th.addEventListener("click", () => {{
        const k = th.dataset.key;
        if (k === sortKey) {{ sortDir = -sortDir; }}
        else {{ sortKey = k; sortDir = (k === "nombre" || k === "equipo" || k === "cat") ? 1 : -1; }}
        render();
      }}));
    }}

    function filtrar() {{
      const cat = document.getElementById("f-cat").value;
      const qn = document.getElementById("f-nombre").value.trim().toLowerCase();
      const qe = document.getElementById("f-equipo").value.trim().toLowerCase();
      // Rangos activos: solo los extremos con valor restringen (lógica AND).
      const rangos = RANGOS.map(r => ({{
        key: r.key, min: _numVal("min-" + r.key), max: _numVal("max-" + r.key)
      }})).filter(r => r.min !== null || r.max !== null);
      return DATA.filter(d => {{
        if (cat && d.cat !== cat) return false;
        if (qn && !d.nombre.toLowerCase().includes(qn)) return false;
        if (qe && !d.equipo.toLowerCase().includes(qe)) return false;
        for (const r of rangos) {{
          const v = d[r.key];
          if (r.min !== null && v < r.min) return false;
          if (r.max !== null && v > r.max) return false;
        }}
        return true;
      }});
    }}

    function limpiar() {{
      document.getElementById("f-cat").value = "";
      document.getElementById("f-nombre").value = "";
      document.getElementById("f-equipo").value = "";
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).value = r.def_min || "";
        document.getElementById("max-" + r.key).value = "";
      }});
      render();
    }}

    function ordenar(rows) {{
      const k = sortKey, dir = sortDir;
      const num = !(k === "nombre" || k === "equipo" || k === "cat");
      return rows.sort((a, b) => {{
        let va = a[k], vb = b[k];
        if (num) {{ return (va - vb) * dir; }}
        va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
        return va < vb ? -dir : (va > vb ? dir : 0);
      }});
    }}

    function render() {{
      renderHead();
      const rows = ordenar(filtrar());
      document.getElementById("n-filas").textContent = rows.length;
      const body = document.getElementById("tbody");
      const frag = rows.map((d, i) => {{
        const tds = COLS.map(c => {{
          if (c.type === "rank") return `<td class="rank">${{i + 1}}</td>`;
          if (c.type === "cat") return `<td><span class="cat-badge">${{esc(d.cat)}}</span></td>`;
          if (c.type === "text") return `<td class="${{c.cls||""}}">${{esc(d[c.key])}}</td>`;
          const cls = c.main ? "main" : "";
          return `<td class="${{cls}}">${{d[c.key]}}</td>`;
        }}).join("");
        return `<tr>${{tds}}</tr>`;
      }}).join("");
      body.innerHTML = frag;
    }}

    function iniciarApp() {{
      document.getElementById("f-cat").addEventListener("change", render);
      document.getElementById("f-nombre").addEventListener("input", render);
      document.getElementById("f-equipo").addEventListener("input", render);
      document.getElementById("f-limpiar").addEventListener("click", limpiar);
      buildRangos();
      render();
    }}
{arranque}
  </script>
</body>
</html>"""


# Login + descifrado (Web Crypto) para la versión publicada cifrada.
_LOGIN_HTML = """
    <div id="login" class="login-wrap">
      <div class="login-card">
        <h2>Acceso restringido</h2>
        <p>Ingresá la contraseña para acceder al buscador de jugadores.</p>
        <div class="login-row">
          <input type="password" id="pw" placeholder="Contraseña" autocomplete="current-password"/>
          <button type="button" class="btn" id="pw-btn">Ingresar</button>
        </div>
        <div class="login-err" id="login-err"></div>
      </div>
    </div>"""

_LOGIN_JS = """    const _b64d = s => {
      const bin = atob(s); const a = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
      return a;
    };
    async function _ingresar() {
      const pass = document.getElementById("pw").value;
      const err = document.getElementById("login-err");
      err.textContent = "";
      try {
        const enc = new TextEncoder();
        const baseKey = await crypto.subtle.importKey(
          "raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]
        );
        const key = await crypto.subtle.deriveKey(
          {name: "PBKDF2", salt: _b64d(CRYPTO.salt), iterations: CRYPTO.iter, hash: "SHA-256"},
          baseKey, {name: "AES-GCM", length: 256}, false, ["decrypt"]
        );
        const plain = await crypto.subtle.decrypt(
          {name: "AES-GCM", iv: _b64d(CRYPTO.iv)}, key, _b64d(CRYPTO.ct)
        );
        DATA = JSON.parse(new TextDecoder().decode(plain));
        document.getElementById("login").style.display = "none";
        document.getElementById("app").style.display = "";
        iniciarApp();
      } catch (e) {
        err.textContent = "Contraseña incorrecta. Probá de nuevo.";
      }
    }
    document.getElementById("pw-btn").addEventListener("click", _ingresar);
    document.getElementById("pw").addEventListener("keydown", e => {
      if (e.key === "Enter") _ingresar();
    });"""


def _render_html(jugadores: List[Dict[str, object]], *, fecha: str) -> str:
    """Versión LOCAL en claro (datos embebidos sin cifrar)."""
    data_json = json.dumps(jugadores, ensure_ascii=False, separators=(",", ":"))
    cat_opts = "".join(f'<option value="{c}">{c}</option>' for c in CATEGORIAS)
    return _build_html(
        fecha=fecha,
        cat_opts=cat_opts,
        data_decl=f"let DATA = {data_json};",
        arranque="    iniciarApp();",
    )


def _cifrar_payload(
    data_json: str,
    password: str,
    *,
    iteraciones: int = PBKDF2_ITER,
    dklen: int = PBKDF2_DKLEN,
) -> Dict[str, object]:
    """Cifra el JSON con AES-256-GCM y clave derivada por PBKDF2-HMAC-SHA256."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iteraciones, dklen=dklen
    )
    # AESGCM.encrypt concatena el tag (16 bytes) al final del ciphertext.
    ct = AESGCM(key).encrypt(iv, data_json.encode("utf-8"), None)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
        "iter": iteraciones,
        "dklen": dklen,
    }


def _render_html_cifrado(
    jugadores: List[Dict[str, object]], *, fecha: str, password: str
) -> str:
    """Versión PÚBLICA: login + datos cifrados (AES-GCM) descifrados en el navegador."""
    data_json = json.dumps(jugadores, ensure_ascii=False, separators=(",", ":"))
    cripto = _cifrar_payload(data_json, password)
    cat_opts = "".join(f'<option value="{c}">{c}</option>' for c in CATEGORIAS)
    data_decl = "let DATA = [];\n    const CRYPTO = " + json.dumps(cripto) + ";"
    return _build_html(
        fecha=fecha,
        cat_opts=cat_opts,
        data_decl=data_decl,
        arranque=_LOGIN_JS,
        login_block=_LOGIN_HTML,
        app_style=' style="display:none"',
    )


# --------------------------------------------------------------------------- #
# Caché de partidos (para regenerar offline con --desde-cache)
# --------------------------------------------------------------------------- #
def _guardar_partidos_cache(partidos: List[Dict[str, str]]) -> None:
    PARTIDOS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PARTIDOS_CACHE.write_text(
        json.dumps(partidos, ensure_ascii=False), encoding="utf-8"
    )


def _cargar_partidos_cache() -> List[Dict[str, str]]:
    if PARTIDOS_CACHE.exists():
        return json.loads(PARTIDOS_CACHE.read_text(encoding="utf-8"))
    return []


def _control(jugadores: List[Dict[str, object]], partidos: List[Dict[str, str]]) -> None:
    print("\n=== CONTROL ===", file=sys.stderr)
    for edad in CATEGORIAS:
        n_part = sum(1 for p in partidos if p["categoria"] == edad)
        jugs = [j for j in jugadores if j["cat"] == edad]
        print(
            f"{edad}: {n_part} partidos · {len(jugs)} jugadores", file=sys.stderr
        )
        top = sorted(
            [j for j in jugs if j["pj"] >= 3], key=lambda j: -j["pts_p"]
        )[:5]
        for j in top:
            print(
                f"    {j['pts_p']:5.1f} Pts/p  {j['nombre']} ({j['equipo']}) "
                f"PJ={j['pj']}",
                file=sys.stderr,
            )


def main() -> int:
    p = argparse.ArgumentParser(description="Buscador local de jugadores destacados")
    p.add_argument("--widget-key", default="", help="Default: config/competencias.json")
    p.add_argument("--fecha-ini", default="2025-1-1")
    p.add_argument("--fecha-fin", default="2026-12-31")
    p.add_argument("--out-html", default=str(OUT_HTML))
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--limite", type=int, default=0, help="Tope de boxscores a descargar (debug)")
    p.add_argument("--progress", action="store_true")
    p.add_argument(
        "--desde-cache",
        action="store_true",
        help="No usa la red: parte de partidos.json + boxscores_full.json cacheados",
    )
    p.add_argument(
        "--sin-descarga",
        action="store_true",
        help="Recolecta partidos de GES pero NO descarga boxscores nuevos (usa caché)",
    )
    p.add_argument(
        "--password",
        default="",
        help="Contraseña para la versión cifrada publicada (NO se guarda; pasar por CLI)",
    )
    p.add_argument(
        "--publicar-docs",
        action="store_true",
        help=f"Genera la versión cifrada en docs/ ({PUBLIC_URL}). Requiere --password",
    )
    p.add_argument("--out-docs", default=str(DOCS_HTML))
    args = p.parse_args()

    fecha = date.today().strftime("%d/%m/%Y")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.desde_cache:
        partidos = _cargar_partidos_cache()
        if not partidos:
            print("No hay partidos.json cacheado; corré sin --desde-cache primero.", file=sys.stderr)
            return 1
        if args.progress:
            print(f"Usando caché: {len(partidos)} partidos", file=sys.stderr)
    else:
        widget_key = args.widget_key or _load_widget_key()
        if not widget_key:
            print("Falta widget_key (config/competencias.json)", file=sys.stderr)
            return 1
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
        if args.progress:
            print("Recolectando partidos COMPLETOS de las 4 categorías…", file=sys.stderr)
        partidos = recolectar_partidos(
            ges,
            key=widget_key,
            fecha_ini=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            progress=args.progress,
        )
        _guardar_partidos_cache(partidos)

    tokens = [p["id_partido"] for p in partidos]
    boxscores = descargar_boxscores_full(
        tokens,
        workers=args.workers,
        progress=args.progress,
        limite=args.limite,
        sin_descarga=args.desde_cache or args.sin_descarga,
    )

    if args.progress:
        print(f"Boxscores con stats: {len(boxscores)}", file=sys.stderr)

    jugadores = agregar_jugadores(partidos, boxscores)

    # Versión LOCAL en claro (no se publica).
    out_html = Path(args.out_html)
    out_html.write_text(_render_html(jugadores, fecha=fecha), encoding="utf-8")

    # Versión PÚBLICA cifrada (login + AES-GCM) para GitHub Pages.
    docs_html: Optional[str] = None
    if args.publicar_docs:
        if not args.password:
            print(
                "Falta --password para publicar la versión cifrada en docs/.",
                file=sys.stderr,
            )
            return 1
        Path(args.out_docs).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_docs).write_text(
            _render_html_cifrado(jugadores, fecha=fecha, password=args.password),
            encoding="utf-8",
        )
        docs_html = args.out_docs
        if args.progress:
            print(
                f"Publicado cifrado en {docs_html} "
                f"(AES-256-GCM, PBKDF2-SHA256 x{PBKDF2_ITER})",
                file=sys.stderr,
            )

    if args.progress:
        _control(jugadores, partidos)

    print(
        json.dumps(
            {
                "partidos": len(partidos),
                "boxscores_con_stats": len(boxscores),
                "jugadores": len(jugadores),
                "por_categoria": {
                    edad: {
                        "partidos": sum(1 for x in partidos if x["categoria"] == edad),
                        "jugadores": sum(1 for j in jugadores if j["cat"] == edad),
                    }
                    for edad in CATEGORIAS
                },
                "html": str(out_html),
                "docs_html": docs_html,
                "public_url": PUBLIC_URL if args.publicar_docs else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
