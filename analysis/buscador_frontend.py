# -*- coding: utf-8 -*-
"""JavaScript del buscador: datos externos, scroll virtual y filtrado por índices."""


def script_buscador(
    *,
    data_boot: str,
    scout_key: str,
    perfil_css_map: str,
    arranque: str,
) -> str:
    return f"""
    {data_boot}
    const SCOUT_KEY = {scout_key};
    const PERFIL_CLASS = {perfil_css_map};
    const ROW_H = 34;
    const COLS = [
      {{key:"__star", label:"★", type:"star"}},
      {{key:"__cmp", label:"⚖", type:"cmp"}},
      {{key:"__rank", label:"#", type:"rank"}},
      {{key:"perfil", label:"Perfil", type:"perfil"}},
      {{key:"nombre_completo", label:"Jugador", type:"player", cls:"nm"}},
      {{key:"equipo", label:"Equipo", type:"text", cls:"eq"}},
      {{key:"cat", label:"Cat.", type:"cat"}},
      {{key:"edad", label:"Edad", type:"num"}},
      {{key:"pj", label:"PJ", type:"num"}},
      {{key:"min_p", label:"Min/p", type:"num"}},
      {{key:"pts_p", label:"Pts/p", type:"num", main:true}},
      {{key:"pct_pts", label:"Pct Pts", type:"pctile", tip:"Percentil pts/p en categoría"}},
      {{key:"ts_pct", label:"TS%", type:"pct", checkKey:"t2i_p"}},
      {{key:"pct_ts", label:"Pct TS", type:"pctile"}},
      {{key:"efg_pct", label:"eFG%", type:"pct", checkKey:"t2i_p"}},
      {{key:"val_min", label:"Val/Min", type:"num"}},
      {{key:"pct_val", label:"Pct Val", type:"pctile"}},
      {{key:"reb_p", label:"Reb/p", type:"num"}},
      {{key:"ast_p", label:"Ast/p", type:"num"}},
      {{key:"ast_per", label:"Ast/Per", type:"num"}},
      {{key:"per_p", label:"Per/p", type:"num"}},
      {{key:"rob_p", label:"Rob/p", type:"num"}},
      {{key:"tap_p", label:"Tap/p", type:"num"}},
      {{key:"val_p", label:"Val/p", type:"num"}},
      {{key:"t2a_p", label:"2P A-I", type:"ai", keyA:"t2a_p", keyI:"t2i_p"}},
      {{key:"t2_pct", label:"2P%", type:"pct", checkKey:"t2i_p"}},
      {{key:"t3a_p", label:"3P A-I", type:"ai", keyA:"t3a_p", keyI:"t3i_p"}},
      {{key:"t3_pct", label:"3P%", type:"pct", checkKey:"t3i_p"}},
      {{key:"tla_p", label:"TL A-I", type:"ai", keyA:"tla_p", keyI:"tli_p"}},
      {{key:"tl_pct", label:"TL%", type:"pct", checkKey:"tli_p"}},
    ];
    const RANGOS = [
      {{key:"pj", label:"PJ", def_min:"3"}},
      {{key:"edad", label:"Edad"}},
      {{key:"min_p", label:"Min/p"}},
      {{key:"pts_p", label:"Pts/p"}},
      {{key:"ts_pct", label:"TS%"}},
      {{key:"efg_pct", label:"eFG%"}},
      {{key:"val_min", label:"Val/Min"}},
      {{key:"pct_pts", label:"Pct Pts"}},
      {{key:"pct_ts", label:"Pct TS"}},
      {{key:"pct_val", label:"Pct Val"}},
      {{key:"reb_p", label:"Reb/p"}},
      {{key:"ast_p", label:"Ast/p"}},
      {{key:"ast_per", label:"Ast/Per"}},
      {{key:"rob_p", label:"Rob/p"}},
      {{key:"tap_p", label:"Tap/p"}},
      {{key:"val_p", label:"Val/p"}},
      {{key:"t2_pct", label:"2P%"}},
      {{key:"t3_pct", label:"3P%"}},
      {{key:"tl_pct", label:"TL%"}},
      {{key:"t2i_p", label:"2P int/p"}},
      {{key:"t3i_p", label:"3P int/p"}},
      {{key:"tli_p", label:"TL int/p"}},
    ];
    const PRESETS = [
      {{id:"t3", label:"Tirador 3P", ranges:{{t3i_p:{{min:3}}, t3_pct:{{min:32}}}}}},
      {{id:"reb", label:"Interior reboteador", ranges:{{reb_p:{{min:6}}, tap_p:{{min:0.5}}}}}},
      {{id:"base", label:"Base creador", ranges:{{ast_p:{{min:3}}, ast_per:{{min:1.5}}}}}},
      {{id:"rot", label:"Eficiente rotación", ranges:{{min_p:{{max:18}}, val_min:{{min:0.6}}}}}},
    ];
    let ROWS = [], SCHEMA = [], KEY = {{}}, PERFIL_NAMES = [];
    let filteredIdx = [];
    let sortKey = "pts_p", sortDir = -1;
    let soloFichajes = false, compareIds = [], activePresetId = null;
    let renderTimer = null, headBuilt = false, scrollBound = false;

    function esc(s) {{ return (s==null?"":String(s)).replace(/[&<>]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c])); }}
    function v(row, k) {{ const i = KEY[k]; return i == null ? "" : row[i]; }}
    function perfilName(row) {{ return PERFIL_NAMES[v(row,"pf")] || ""; }}
    function perfilCls(p) {{ return PERFIL_CLASS[p] || "perfil-Muestra-insuficiente"; }}
    function playerIdRow(row) {{ return String(v(row,"pid") || v(row,"nombre_completo") + "|" + v(row,"cat")); }}
    function fichaUrl(purl) {{ if (!purl) return ""; return purl.startsWith("http") ? purl : "https://argentina.basketball" + purl; }}

    function initData(pack) {{
      SCHEMA = pack.s; PERFIL_NAMES = pack.p; ROWS = pack.d;
      KEY = Object.fromEntries(SCHEMA.map((k,i) => [k,i]));
      filteredIdx = ROWS.map((_,i) => i);
    }}

    async function gunzipBytes(buf) {{
      if (typeof DecompressionStream !== "undefined") {{
        const ds = new DecompressionStream("gzip");
        return await new Response(new Blob([buf]).stream().pipeThrough(ds)).arrayBuffer();
      }}
      throw new Error("El navegador no soporta descompresión gzip.");
    }}

    async function loadPlainData() {{
      document.getElementById("loading").style.display = "flex";
      const r = await fetch(DATA_BOOT.url, {{cache:"no-cache"}});
      if (!r.ok) throw new Error("No se pudo cargar " + DATA_BOOT.url);
      const gz = await r.arrayBuffer();
      const raw = await gunzipBytes(gz);
      initData(JSON.parse(new TextDecoder().decode(raw)));
      document.getElementById("loading").style.display = "none";
    }}

    function loadScout() {{
      try {{ return JSON.parse(localStorage.getItem(SCOUT_KEY) || "{{}}"); }}
      catch(e) {{ return {{}}; }}
    }}
    function saveScout(data) {{ localStorage.setItem(SCOUT_KEY, JSON.stringify(data)); }}
    function isStarredRow(row) {{ const s = loadScout(); return !!(s[playerIdRow(row)] && s[playerIdRow(row)].starred); }}
    function toggleStarRow(row) {{
      const id = playerIdRow(row);
      const s = loadScout();
      if (!s[id]) s[id] = {{starred:false, note:"", ts:Date.now()}};
      s[id].starred = !s[id].starred; s[id].ts = Date.now();
      saveScout(s); scheduleRender();
    }}
    function scoutCount() {{ return Object.values(loadScout()).filter(x => x.starred).length; }}

    function buildRangos() {{
      const cont = document.getElementById("rangos");
      cont.innerHTML = RANGOS.map(r => `
        <div class="rango"><span class="lbl">${{esc(r.label)}}</span>
          <div class="pair">
            <input type="number" step="any" id="min-${{r.key}}" placeholder="mín" value="${{r.def_min||""}}"/>
            <span>–</span><input type="number" step="any" id="max-${{r.key}}" placeholder="máx"/>
          </div></div>`).join("");
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).addEventListener("input", scheduleRender);
        document.getElementById("max-" + r.key).addEventListener("input", scheduleRender);
      }});
    }}

    function clearPresetRanges(p) {{
      for (const k of Object.keys(p.ranges)) {{
        const r = RANGOS.find(x => x.key === k);
        document.getElementById("min-" + k).value = (r && r.def_min) ? r.def_min : "";
        document.getElementById("max-" + k).value = "";
      }}
    }}

    function buildPresets() {{
      const cont = document.getElementById("presets");
      PRESETS.forEach(p => {{
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "btn-pill"; btn.textContent = p.label; btn.dataset.preset = p.id;
        btn.addEventListener("click", () => applyPreset(p));
        cont.appendChild(btn);
      }});
    }}

    function applyPreset(p) {{
      if (activePresetId === p.id) {{
        clearPresetRanges(p); activePresetId = null;
        document.querySelectorAll("#presets .btn-pill").forEach(b => b.classList.remove("active"));
        scheduleRender(true); return;
      }}
      if (activePresetId) {{ const prev = PRESETS.find(x => x.id === activePresetId); if (prev) clearPresetRanges(prev); }}
      RANGOS.forEach(r => {{ document.getElementById("min-" + r.key).value = r.def_min || ""; document.getElementById("max-" + r.key).value = ""; }});
      for (const [k, rng] of Object.entries(p.ranges)) {{
        if (rng.min != null) document.getElementById("min-" + k).value = rng.min;
        if (rng.max != null) document.getElementById("max-" + k).value = rng.max;
      }}
      activePresetId = p.id;
      document.querySelectorAll("#presets .btn-pill").forEach(b => b.classList.toggle("active", b.dataset.preset === p.id));
      scheduleRender(true);
    }}

    function _numVal(id) {{
      const t = (document.getElementById(id).value || "").trim();
      if (!t) return null;
      const n = parseFloat(t); return isNaN(n) ? null : n;
    }}

    function renderHead() {{
      const tr = document.getElementById("thead");
      tr.innerHTML = COLS.map(c => {{
        if (c.type === "rank" || c.type === "star" || c.type === "cmp") return `<th class="rank">${{esc(c.label)}}</th>`;
        let cls = c.cls || "";
        if (c.key === sortKey) cls += sortDir < 0 ? " sorted-desc" : " sorted-asc";
        const tip = c.tip ? ` title="${{esc(c.tip)}}"` : "";
        return `<th class="${{cls}}" data-key="${{c.key}}"${{tip}}>${{esc(c.label)}}</th>`;
      }}).join("");
      tr.querySelectorAll("th[data-key]").forEach(th => th.addEventListener("click", () => {{
        const k = th.dataset.key;
        if (k === sortKey) sortDir = -sortDir;
        else {{ sortKey = k; sortDir = TEXT_KEYS.has(k) || k === "perfil" ? 1 : -1; }}
        headBuilt = false; render(true);
      }}));
      headBuilt = true;
    }}

    function filtrarIndices() {{
      const cat = document.getElementById("f-cat").value;
      const perfil = document.getElementById("f-perfil").value;
      const qn = document.getElementById("f-nombre").value.trim().toLowerCase();
      const qe = document.getElementById("f-equipo").value.trim().toLowerCase();
      const scout = loadScout();
      const rangos = RANGOS.map(r => ({{key:r.key, min:_numVal("min-"+r.key), max:_numVal("max-"+r.key)}}))
        .filter(r => r.min !== null || r.max !== null);
      const out = [];
      for (let i = 0; i < ROWS.length; i++) {{
        const row = ROWS[i];
        if (cat && v(row,"cat") !== cat) continue;
        if (perfil && perfilName(row) !== perfil) continue;
        if (soloFichajes) {{ const s = scout[playerIdRow(row)]; if (!s || !s.starred) continue; }}
        if (qn && !String(v(row,"nombre_completo")).toLowerCase().includes(qn)) continue;
        if (qe && !String(v(row,"equipo")).toLowerCase().includes(qe)) continue;
        let ok = true;
        for (const r of rangos) {{
          const val = v(row, r.key);
          if (val === "" || val == null) {{ ok = false; break; }}
          if (r.min !== null && val < r.min) {{ ok = false; break; }}
          if (r.max !== null && val > r.max) {{ ok = false; break; }}
        }}
        if (ok) out.push(i);
      }}
      return out;
    }}

    const TEXT_KEYS = new Set(["nombre_completo","equipo","cat","perfil"]);
    function ordenarIndices(indices) {{
      const k = sortKey, dir = sortDir, ki = KEY[k];
      const isPerfil = k === "perfil";
      const num = !TEXT_KEYS.has(k);
      indices.sort((ai, bi) => {{
        const a = ROWS[ai], b = ROWS[bi];
        let va = isPerfil ? perfilName(a) : a[ki], vb = isPerfil ? perfilName(b) : b[ki];
        if (num) {{
          va = (va === "" || va == null) ? -Infinity : va;
          vb = (vb === "" || vb == null) ? -Infinity : vb;
          return (va - vb) * dir;
        }}
        va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
        return va < vb ? -dir : (va > vb ? dir : 0);
      }});
    }}

    function cellHtml(row, c, rank) {{
      if (c.type === "rank") return String(rank);
      if (c.type === "perfil") return `<span class="perfil-badge ${{perfilCls(perfilName(row))}}">${{esc(perfilName(row)||"-")}}</span>`;
      if (c.type === "player") {{
        const url = fichaUrl(v(row,"purl"));
        const nm = esc(v(row,"nombre_completo"));
        return url ? `<a href="${{esc(url)}}" target="_blank" rel="noopener">${{nm}}</a>` : nm;
      }}
      if (c.type === "cat") return `<span class="cat-badge">${{esc(v(row,"cat"))}}</span>`;
      if (c.type === "text") return esc(v(row,c.key));
      if (c.type === "ai") return `${{v(row,c.keyA)}}-${{v(row,c.keyI)}}`;
      if (c.type === "pctile") {{ const x = v(row,c.key); return x !== "" ? x : "-"; }}
      if (c.type === "pct") {{
        const ck = c.checkKey;
        const has = ck ? v(row, ck) > 0 : false;
        const x = v(row, c.key);
        return has && x !== "" ? x : "-";
      }}
      const x = v(row, c.key);
      return x === "" ? "-" : String(x);
    }}

    function buildRow(row, dataIdx, rank) {{
      const tr = document.createElement("tr");
      tr.dataset.idx = dataIdx;
      const pid = playerIdRow(row);
      if (compareIds.includes(pid)) tr.classList.add("selected");
      COLS.forEach(c => {{
        const td = document.createElement("td");
        if (c.cls) td.className = c.cls;
        if (c.type === "rank") {{ td.className = "rank"; td.textContent = rank; }}
        else if (c.type === "star") {{
          const btn = document.createElement("button");
          btn.type = "button"; btn.className = "star-btn" + (isStarredRow(row) ? " on" : "");
          btn.textContent = "★"; btn.dataset.action = "star";
          td.appendChild(btn);
        }} else if (c.type === "cmp") {{
          const chk = document.createElement("input");
          chk.type = "checkbox"; chk.className = "cmp-chk"; chk.dataset.action = "cmp";
          chk.checked = compareIds.includes(pid);
          td.appendChild(chk);
        }} else if (c.main) {{ td.className = "main"; td.innerHTML = cellHtml(row, c, rank); }}
        else {{ td.innerHTML = cellHtml(row, c, rank); }}
        tr.appendChild(td);
      }});
      tr.style.cursor = "pointer";
      return tr;
    }}

    function renderBodyVirtual(indices) {{
      const wrap = document.querySelector(".tablewrap");
      const body = document.getElementById("tbody");
      const total = indices.length;
      const scrollTop = wrap.scrollTop;
      const viewH = wrap.clientHeight || 600;
      const start = Math.max(0, Math.floor(scrollTop / ROW_H) - 20);
      const end = Math.min(total, start + Math.ceil(viewH / ROW_H) + 40);
      const topH = start * ROW_H;
      const bottomH = Math.max(0, (total - end) * ROW_H);
      const fragment = document.createDocumentFragment();
      const trTop = document.createElement("tr");
      trTop.innerHTML = `<td colspan="${{COLS.length}}" style="height:${{topH}}px;padding:0;border:0"></td>`;
      fragment.appendChild(trTop);
      for (let vi = start; vi < end; vi++) {{
        const dataIdx = indices[vi];
        fragment.appendChild(buildRow(ROWS[dataIdx], dataIdx, vi + 1));
      }}
      const trBot = document.createElement("tr");
      trBot.innerHTML = `<td colspan="${{COLS.length}}" style="height:${{bottomH}}px;padding:0;border:0"></td>`;
      fragment.appendChild(trBot);
      body.replaceChildren(fragment);
    }}

    function render(resetScroll) {{
      if (!headBuilt) renderHead();
      filteredIdx = filtrarIndices();
      ordenarIndices(filteredIdx);
      document.getElementById("n-filas").textContent = filteredIdx.length;
      document.getElementById("n-scout").textContent = scoutCount();
      if (resetScroll) document.querySelector(".tablewrap").scrollTop = 0;
      renderBodyVirtual(filteredIdx);
      window._lastIdx = filteredIdx.slice();
    }}

    function scheduleRender(resetScroll) {{
      clearTimeout(renderTimer);
      renderTimer = setTimeout(() => render(!!resetScroll), 120);
    }}

    function openDetailIdx(dataIdx) {{
      const row = ROWS[dataIdx];
      const panel = document.getElementById("detail-panel");
      const id = playerIdRow(row);
      const scout = loadScout();
      const note = (scout[id] && scout[id].note) || "";
      const url = fichaUrl(v(row,"purl"));
      const pf = perfilName(row);
      const stats = [
        ["PJ", v(row,"pj")], ["Min/p", v(row,"min_p")], ["Pts/p", v(row,"pts_p")], ["TS%", v(row,"ts_pct")],
        ["eFG%", v(row,"efg_pct")], ["Val/Min", v(row,"val_min")], ["Reb/p", v(row,"reb_p")],
        ["Ast/p", v(row,"ast_p")], ["Ast/Per", v(row,"ast_per")], ["Per/p", v(row,"per_p")],
        ["Rob/p", v(row,"rob_p")], ["Tap/p", v(row,"tap_p")], ["Val/p", v(row,"val_p")],
        ["Perfil", pf], ["Pct Pts", v(row,"pct_pts")], ["Pct TS", v(row,"pct_ts")],
      ];
      document.getElementById("detail-content").innerHTML = `
        <h3>${{esc(v(row,"nombre_completo"))}}</h3>
        <div class="meta">${{esc(v(row,"equipo"))}} · ${{esc(v(row,"cat"))}}${{v(row,"edad") ? " · " + v(row,"edad") + " años" : ""}}</div>
        <span class="perfil-badge ${{perfilCls(pf)}}">${{esc(pf||"-")}}</span>
        <div class="stats-grid">${{stats.map(([l,val]) => `<div><span>${{l}}</span><b>${{val!==""?val:"-"}}</b></div>`).join("")}}</div>
        ${{url ? `<a class="btn" href="${{esc(url)}}" target="_blank" rel="noopener">Abrir ficha</a>` : ""}}
        <label class="fld" style="margin-top:14px">Notas de scouting<textarea id="detail-note">${{esc(note)}}</textarea></label>
        <button type="button" class="btn" id="detail-save" style="margin-top:8px">Guardar nota</button>`;
      document.getElementById("detail-save").addEventListener("click", () => {{
        const s = loadScout();
        if (!s[id]) s[id] = {{starred:false, note:"", ts:Date.now()}};
        s[id].note = document.getElementById("detail-note").value; s[id].ts = Date.now();
        saveScout(s);
      }});
      panel.classList.add("open");
    }}

    function renderCompare() {{
      const panel = document.getElementById("compare-panel");
      const cont = document.getElementById("compare-content");
      if (!compareIds.length) {{ panel.classList.remove("open"); cont.innerHTML = ""; return; }}
      const rows = compareIds.map(id => ROWS.find(r => playerIdRow(r) === id)).filter(Boolean);
      if (!rows.length) {{ panel.classList.remove("open"); return; }}
      const metrics = ["cat","pj","min_p","pts_p","ts_pct","efg_pct","val_min","reb_p","ast_p","per_p","perfil"];
      let html = "<table><thead><tr><th>Métrica</th>";
      rows.forEach(r => {{ html += `<th>${{esc(v(r,"nombre_completo"))}}</th>`; }});
      html += "</tr></thead><tbody>";
      metrics.forEach(m => {{
        html += `<tr><td><b>${{m}}</b></td>`;
        rows.forEach(r => {{
          const val = m === "perfil" ? perfilName(r) : v(r, m);
          html += `<td>${{esc(val!==""?val:"-")}}</td>`;
        }});
        html += "</tr>";
      }});
      html += "</tbody></table>";
      cont.innerHTML = html; panel.classList.add("open");
    }}

    function exportCSV() {{
      const indices = window._lastIdx || filteredIdx;
      const scout = loadScout();
      const headers = ["pid","nombre_completo","equipo","cat","perfil","pj","min_p","pts_p","ts_pct","efg_pct","val_min","reb_p","ast_p","per_p","ast_per","pct_pts","pct_ts","nota_scouting","en_seguimiento"];
      const lines = [headers.join(",")];
      indices.forEach(i => {{
        const row = ROWS[i]; const id = playerIdRow(row); const sc = scout[id] || {{}};
        const vals = headers.map(h => {{
          if (h === "nota_scouting") return sc.note || "";
          if (h === "en_seguimiento") return sc.starred ? "1" : "0";
          if (h === "perfil") return perfilName(row);
          const val = v(row, h); const s = val == null ? "" : String(val);
          return s.includes(",") || s.includes('"') ? '"' + s.replace(/"/g, '""') + '"' : s;
        }});
        lines.push(vals.join(","));
      }});
      const blob = new Blob([lines.join("\\n")], {{type:"text/csv;charset=utf-8"}});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "scouting_formativas.csv"; a.click();
    }}

    function limpiar() {{
      document.getElementById("f-cat").value = "";
      document.getElementById("f-perfil").value = "";
      document.getElementById("f-nombre").value = "";
      document.getElementById("f-equipo").value = "";
      soloFichajes = false; activePresetId = null;
      document.getElementById("f-fichajes").classList.remove("active");
      document.querySelectorAll("#presets .btn-pill").forEach(b => b.classList.remove("active"));
      RANGOS.forEach(r => {{
        document.getElementById("min-" + r.key).value = r.def_min || "";
        document.getElementById("max-" + r.key).value = "";
      }});
      scheduleRender(true);
    }}

    function initTabs() {{
      document.querySelectorAll(".tab-btn").forEach(btn => {{
        btn.addEventListener("click", () => {{
          document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
          document.querySelectorAll(".tab-panel").forEach(p => {{ p.style.display = "none"; }});
          btn.classList.add("active");
          document.getElementById("tab-" + btn.dataset.tab).style.display = "";
        }});
      }});
    }}

    function bindTableEvents() {{
      const body = document.getElementById("tbody");
      body.addEventListener("click", e => {{
        const tr = e.target.closest("tr[data-idx]");
        if (!tr) return;
        const dataIdx = +tr.dataset.idx;
        const row = ROWS[dataIdx];
        if (e.target.dataset.action === "star") {{ e.stopPropagation(); toggleStarRow(row); return; }}
        if (e.target.classList.contains("cmp-chk")) return;
        openDetailIdx(dataIdx);
      }});
      body.addEventListener("change", e => {{
        if (!e.target.classList.contains("cmp-chk")) return;
        const tr = e.target.closest("tr[data-idx]");
        if (!tr) return;
        const id = playerIdRow(ROWS[+tr.dataset.idx]);
        if (e.target.checked) {{
          if (compareIds.length >= 3) {{ e.target.checked = false; return; }}
          compareIds.push(id);
        }} else {{
          compareIds = compareIds.filter(x => x !== id);
        }}
        renderCompare(); scheduleRender();
      }});
      if (!scrollBound) {{
        document.querySelector(".tablewrap").addEventListener("scroll", () => scheduleRender(), {{passive:true}});
        scrollBound = true;
      }}
    }}

    function iniciarApp() {{
      initTabs(); bindTableEvents();
      document.getElementById("f-cat").addEventListener("change", () => scheduleRender(true));
      document.getElementById("f-perfil").addEventListener("change", () => scheduleRender(true));
      document.getElementById("f-nombre").addEventListener("input", () => scheduleRender(true));
      document.getElementById("f-equipo").addEventListener("input", () => scheduleRender(true));
      document.getElementById("f-fichajes").addEventListener("click", () => {{
        soloFichajes = !soloFichajes;
        document.getElementById("f-fichajes").classList.toggle("active", soloFichajes);
        scheduleRender(true);
      }});
      document.getElementById("f-export").addEventListener("click", exportCSV);
      document.getElementById("f-limpiar").addEventListener("click", limpiar);
      document.getElementById("detail-close").addEventListener("click", () => document.getElementById("detail-panel").classList.remove("open"));
      document.getElementById("cmp-clear").addEventListener("click", () => {{ compareIds = []; renderCompare(); scheduleRender(); }});
      buildRangos(); buildPresets(); render(true);
    }}
{arranque}
"""
