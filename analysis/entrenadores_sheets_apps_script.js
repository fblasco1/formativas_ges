/**
 * Apps Script — puente CORS entre el HTML de entrenadores y esta hoja.
 *
 * Instalación:
 * 1. Abrí el Google Sheet de entrenadores.
 * 2. Extensiones → Apps Script → pegá este archivo (reemplazando Code.gs).
 * 3. Guardá → Implementar → Nueva implementación → Tipo: Aplicación web
 *    - Ejecutar como: Yo
 *    - Quién tiene acceso: Cualquier persona
 * 4. Copiá la URL (/exec) a config/entrenadores_sheets.json → "webapp_url"
 * 5. Regenerá el HTML: python analysis/generar_informe_visual_entrenadores.py
 *
 * La hoja debe llamarse "Entrenadores" (o el nombre en SHEET_NAME) con columnas:
 * KEY | ENTRENADOR | CLUB | CATEGORIAS | WHATSAPP
 */

var SHEET_NAME = "Entrenadores";

function _sheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    throw new Error("No existe la pestaña: " + SHEET_NAME);
  }
  return sh;
}

function _cors(output) {
  return ContentService.createTextOutput(output).setMimeType(
    ContentService.MimeType.JSON
  );
}

function _headersIndex(headerRow) {
  var idx = {};
  for (var i = 0; i < headerRow.length; i++) {
    idx[String(headerRow[i] || "").trim().toUpperCase()] = i;
  }
  return idx;
}

/**
 * GET → { ok, rows: [{ key, entrenador, club, categorias: [], whatsapp }] }
 */
function doGet(e) {
  try {
    var sh = _sheet();
    var values = sh.getDataRange().getValues();
    if (!values || values.length < 1) {
      return _cors(JSON.stringify({ ok: true, rows: [] }));
    }
    var idx = _headersIndex(values[0]);
    var iKey = idx.KEY;
    var iEnt = idx.ENTRENADOR;
    var iClub = idx.CLUB;
    var iCat = idx.CATEGORIAS;
    var iWp = idx.WHATSAPP;
    if (iKey === undefined || iEnt === undefined || iClub === undefined) {
      return _cors(
        JSON.stringify({
          ok: false,
          error: "Faltan columnas KEY / ENTRENADOR / CLUB",
        })
      );
    }
    var rows = [];
    for (var r = 1; r < values.length; r++) {
      var row = values[r];
      var ent = String(row[iEnt] || "").trim();
      var club = String(row[iClub] || "").trim();
      if (!ent && !club) continue;
      var catsRaw = iCat !== undefined ? String(row[iCat] || "") : "";
      var cats = catsRaw
        .split("|")
        .map(function (c) {
          return c.trim();
        })
        .filter(Boolean);
      rows.push({
        key: String(row[iKey] || "").trim(),
        entrenador: ent,
        club: club,
        categorias: cats,
        whatsapp: iWp !== undefined ? String(row[iWp] || "").trim() : "",
      });
    }
    return _cors(JSON.stringify({ ok: true, rows: rows }));
  } catch (err) {
    return _cors(JSON.stringify({ ok: false, error: String(err) }));
  }
}

/**
 * POST body JSON: { key: "...", whatsapp: "54911..." }
 * También acepta form: key, whatsapp (para text/plain desde el HTML).
 */
function doPost(e) {
  try {
    var payload = {};
    if (e && e.postData && e.postData.contents) {
      var raw = e.postData.contents;
      try {
        payload = JSON.parse(raw);
      } catch (parseErr) {
        // application/x-www-form-urlencoded
        payload = e.parameter || {};
      }
    } else if (e && e.parameter) {
      payload = e.parameter;
    }
    var key = String(payload.key || "").trim();
    var whatsapp = String(payload.whatsapp || "").trim();
    if (!key) {
      return _cors(JSON.stringify({ ok: false, error: "Falta key" }));
    }

    var sh = _sheet();
    var values = sh.getDataRange().getValues();
    if (!values || values.length < 1) {
      return _cors(JSON.stringify({ ok: false, error: "Hoja vacía" }));
    }
    var idx = _headersIndex(values[0]);
    var iKey = idx.KEY;
    var iWp = idx.WHATSAPP;
    if (iKey === undefined) {
      return _cors(JSON.stringify({ ok: false, error: "Falta columna KEY" }));
    }
    if (iWp === undefined) {
      // Agregar columna WHATSAPP al final
      var lastCol = values[0].length + 1;
      sh.getRange(1, lastCol).setValue("WHATSAPP");
      iWp = lastCol - 1;
      values = sh.getDataRange().getValues();
      idx = _headersIndex(values[0]);
      iWp = idx.WHATSAPP;
    }

    var found = false;
    for (var r = 1; r < values.length; r++) {
      var cellKey = String(values[r][iKey] || "").trim();
      if (cellKey === key) {
        sh.getRange(r + 1, iWp + 1).setValue(whatsapp);
        found = true;
        break;
      }
    }
    if (!found) {
      return _cors(
        JSON.stringify({ ok: false, error: "KEY no encontrada: " + key })
      );
    }
    return _cors(JSON.stringify({ ok: true, key: key, whatsapp: whatsapp }));
  } catch (err) {
    return _cors(JSON.stringify({ ok: false, error: String(err) }));
  }
}
