/**
 * Apps Script para consulta de anticipos por cédula desde el bot WhatsApp ProAlto.
 *
 * Despliegue:
 *   1. Abrir el Sheet "Anticipo Express ProAlto (Respuestas)".
 *   2. Extensiones → Apps Script → reemplazar Code.gs con este archivo.
 *   3. Guardar (Ctrl+S).
 *   4. Implementar → Nueva implementación → Aplicación web.
 *      - Ejecutar como: yo (la cuenta dueña del Sheet)
 *      - Quién tiene acceso: Cualquier persona
 *   5. Copiar la URL https://script.google.com/macros/s/AKfy.../exec
 *   6. Cargarla en Render como GOOGLE_APPS_SCRIPT_ANTICIPO_URL.
 *
 * Consumido por src/google_sheets.py → get_anticipo_by_cedula().
 *
 * Endpoint:  GET <URL>?cedula=1234567
 * Respuesta: {"found": true, "cedula", "nombre_completo", "fecha_de_solicitud",
 *             "empresa", "estado", "estado_interno"} | {"found": false}
 *
 *   - estado:         "Aprobado" / "Denegado" / "" (decisión de aprobación)
 *   - estado_interno: "Listo para llamar" / "Listo en panda" /
 *                     "Listo para documentación" / "Desprendible" /
 *                     "Desembolsado" / "" (etapa operativa post-aprobación)
 */

const SHEET_NAME = "Respuestas de formulario 1";

// Matching por substring (case-insensitive) del header. Robusto a saltos de
// línea, notas largas y reordenamientos del Form.
const COL_MATCHERS = {
  fecha:    "marca temporal",
  nombre1:  "nombre completo",   // apellidos en este Form
  nombre2:  "nombres",           // primer/segundo nombre
  cedula:   "cédula",
  empresa:  "empresa",
  estado:   "estado",            // "Estado" (Aprobado / Denegado / vacío)
  interno:  "estado interno",    // "Estado Interno" (Desembolsado, Desprendible, etc.)
};

function _findCols(headers) {
  const idx = {};
  // Solo usamos la PRIMERA LÍNEA del header para hacer matching.
  // Los headers del Form a veces traen notas largas después de un salto de
  // línea (ej. "Nombre Completo\n\nNota: ...escribe tus nombres y apellidos...")
  // que contaminaban los substrings y hacían que "Nombre Completo" y "Nombres"
  // colapsaran a la misma columna.
  const lc = headers.map(h => String(h || "").split("\n")[0].toLowerCase().trim());

  // "estado" matchea "estado interno" también — para evitar ambigüedad,
  // resolvemos "interno" primero y luego "estado" excluyendo esa columna.
  idx.interno = lc.findIndex(h => h.includes("estado interno"));
  idx.estado  = lc.findIndex((h, i) => i !== idx.interno && h.includes("estado"));

  for (const key in COL_MATCHERS) {
    if (key === "estado" || key === "interno") continue;
    const needle = COL_MATCHERS[key];
    idx[key] = lc.findIndex(h => h.includes(needle));
  }
  return idx;
}

function _normCedula(v) {
  return String(v == null ? "" : v).replace(/\D+/g, "").trim();
}

function _buildName(row, idx) {
  const apellido = idx.nombre1 >= 0 ? String(row[idx.nombre1] || "").trim() : "";
  const nombre   = idx.nombre2 >= 0 ? String(row[idx.nombre2] || "").trim() : "";
  if (nombre && apellido) return `${nombre} ${apellido}`.replace(/\s+/g, " ").trim();
  return (nombre || apellido).replace(/\s+/g, " ").trim();
}

function _formatDate(v) {
  if (!v) return "";
  try {
    if (v instanceof Date) return Utilities.formatDate(v, "America/Bogota", "yyyy-MM-dd");
    return String(v);
  } catch (e) { return String(v); }
}

function doGet(e) {
  const out = ContentService.createTextOutput().setMimeType(ContentService.MimeType.JSON);
  const cedula = _normCedula((e && e.parameter && e.parameter.cedula) || "");
  if (!cedula) {
    out.setContent(JSON.stringify({ found: false, error: "missing_cedula" }));
    return out;
  }

  const sh = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sh) {
    out.setContent(JSON.stringify({ found: false, error: "sheet_not_found" }));
    return out;
  }

  const data = sh.getDataRange().getValues();
  if (data.length < 2) {
    out.setContent(JSON.stringify({ found: false }));
    return out;
  }

  const headers = data.shift();
  const idx = _findCols(headers);
  if (idx.cedula < 0) {
    out.setContent(JSON.stringify({ found: false, error: "cedula_column_not_found" }));
    return out;
  }

  // Recorrer de abajo hacia arriba: devuelve la solicitud más reciente
  for (let r = data.length - 1; r >= 0; r--) {
    if (_normCedula(data[r][idx.cedula]) === cedula) {
      const row = data[r];
      out.setContent(JSON.stringify({
        found: true,
        cedula: cedula,
        nombre_completo:    _buildName(row, idx),
        fecha_de_solicitud: _formatDate(row[idx.fecha]),
        empresa:            idx.empresa >= 0 ? String(row[idx.empresa] || "").trim() : "",
        estado:             idx.estado  >= 0 ? String(row[idx.estado]  || "").trim() : "",
        estado_interno:     idx.interno >= 0 ? String(row[idx.interno] || "").trim() : "",
      }));
      return out;
    }
  }

  out.setContent(JSON.stringify({ found: false }));
  return out;
}
