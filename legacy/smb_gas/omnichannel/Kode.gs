// =================================================================================
// ERP CV KIRAL - BACKEND MODUL RETAIL & OMNICHANNEL
// Legacy UI + Compact Omni_Order Adapter v1.6.4 - Incremental Import + Warehouse Summary Contract
// Fokus v1.5.1: semua import/mapping/laporan retur memakai Omni_Retur; Data_Retur_AppSheet hanya dibaca manual lewat migration helper sebelum dihapus.
// =================================================================================

var MASTER_SPREADSHEET_ID = "1bbtCMQfK5p_2c5GzIkTIrcIPcPsm3Wjh_R8PfAagu6I";
var OMNI_SHEET = "Omni_Order";
var IMPORT_LOG_SHEET = "Import_Log";
var RETUR_SHEET = "Omni_Retur";
var RETUR_LEGACY_SHEET = "Data_Retur_AppSheet"; // hanya untuk MIGRATE_DataReturAppSheet_to_OmniRetur(), tidak dipakai runtime
var SETTLEMENT_SHEET = "Omni_Settlement";
var ADJUSTMENT_SHEET = "Data_Keuangan_Penyesuaian";
var POS_SHEET = "Omni_POS_Sales";
var TZ = "Asia/Jakarta";

var OMNI_HEADERS = [
  "Tanggal",
  "Tanggal Key",
  "No Pesanan",
  "Status",
  "Toko",
  "SKU",
  "Item Gudang",
  "Qty",
  "Harga Jual",
  "Total",
  "Unit_Cost",
  "COGS_Value",
  "Cost_Period",
  "Cost_Status",
  "Cost_Source",
  "Cost_Synced_At",
  "Finance_Bucket",
  "No Resi",
  "Marketplace Item Name",
  "Marketplace_Variation",
  "Settlement Status",
  "Import_ID",
  "Updated_At",
  "Updated_By",
  "Is_Deleted"
];

var IMPORT_LOG_HEADERS = [
  "Import_ID",
  "Import_Date",
  "File_Type",
  "File_Name",
  "Rows_Read",
  "Rows_Insert",
  "Rows_Update",
  "Unmapped_Count",
  "Imported_By",
  "Notes"
];

var RETUR_HEADERS = [
  "Tgl Pesan",
  "Tgl Sampai (RTS)",
  "No Pesanan",
  "No Resi",
  "SKU BigSeller",
  "Item Gudang (Mapped)",
  "QTY Marketplace",
  "Conversion Qty",
  "QTY Retur Fisik",
  "Status Marketplace",
  "Status Scan AppSheet",
  "Marketplace_Product_Name",
  "Marketplace_Variation",
  "QC_Source",
  "Gudang_Action",
  "Finance_Status",
  "Notes",
  "Updated_At",
  "Updated_By"
];

var SETTLEMENT_HEADERS = [
  "Toko",
  "No Pesanan",
  "Tgl Pencairan",
  "Tgl Pencairan Key",
  "Pendapatan Bersih",
  "Biaya Admin",
  "Biaya Layanan",
  "Komisi Affiliate",
  "Ongkir Penjual",
  "Import_ID",
  "Updated_At",
  "Updated_By"
];

var ADJUSTMENT_HEADERS = [
  "Tgl Penyesuaian",
  "Toko",
  "ID Pesanan Terkait",
  "Jenis Transaksi",
  "Nomor Penyesuaian",
  "Nilai Penyesuaian (Rp)",
  "Import_ID",
  "Updated_At",
  "Updated_By"
];

var POS_HEADERS = [
  "POS_ID",
  "Tanggal",
  "Tanggal_Key",
  "No_POS",
  "Metode_Bayar",
  "Item_ID",
  "Item_Name",
  "Qty",
  "Harga_Jual",
  "Total",
  "Stock_Posted",
  "Stock_Post_Result",
  "Source_Module",
  "Created_At",
  "Created_By",
  "Is_Deleted"
];

var OMNI_STOCK_MOVEMENT_HEADERS = [
  "Movement_ID", "Tx_Key", "Tanggal", "Source_Date", "Item_ID", "Item_Name", "Item_Category", "Item_Type", "Unit",
  "Warehouse_Code", "Direction", "Movement_Type", "Qty", "Unit_Cost",
  "Cost_Period", "Cost_Status", "Unit_Cost_Provisional", "Value_Provisional", "Unit_Cost_Final", "Value_Final",
  "Cost_Source", "Cost_Synced_At", "Closed_At", "Closed_By",
  "Source_Module", "Source_ID", "Source_Line_ID", "Ref_No", "Batch_ID", "External_Ref", "Notes", "Status", "Created_At", "Created_By", "Is_Deleted"
];

var LOG_ERROR_HEADERS = [
  "Error_ID",
  "Timestamp",
  "Module_Code",
  "Function_Name",
  "Error_Message",
  "Payload_JSON",
  "User_Email",
  "Status"
];

var CACHE_SECONDS = 300;
var WRITE_CHUNK_SIZE = 1000;

var MASTER_SKU_MAP_HEADERS = [
  "Map_ID",
  "Marketplace_SKU",
  "Marketplace_Product_Name",
  "Marketplace_Variation",
  "Internal_Item_Name",
  "Conversion_Qty",
  "Status",
  "Updated_At",
  "Updated_By",
  "Notes",
  "Mapping_Type"
];

var OMNI_RUNTIME_EMAIL = "";

var OMNI_CFG = {
  VERSION: "OMNI_v1.6.5_SHIPPED_TRANSIT_EXACT",
  MASTER_SPREADSHEET_ID: MASTER_SPREADSHEET_ID,
  MODULE_CODE: "OMNI",
  MODULE_ALIASES: ["OMNI", "OMNICHANNEL", "RETAIL", "RETAIL OMNI", "RETAIL_OMNI", "MODUL OMNI", "MODUL OMNICHANNEL"],
  FINANCE_MODULE_ALIASES: ["FIN", "FINANCE", "KEUANGAN", "MODUL FINANCE", "MODUL KEUANGAN"],
  SESSION_TTL_MS: 6 * 60 * 60 * 1000,
  SHARED_SECRET: "CV_KIRAL_FLOW_SUBLIM_STYLE_FIXED_SECRET_2026_KIRAL",
  HEARTBEAT_CELL: "J1",
  HEARTBEAT_UPDATED_CELL: "J2",
  HEARTBEAT_NOTES_CELL: "J3",
  MASTER_USER_SHEET: "Master_User",
  MASTER_MODULE_SHEET: "Master_Module",
  LOG_LOGIN_SHEET: "Log_Login",
  PORTAL_CODES: ["PORTAL", "PRTL", "HOME", "BERANDA"],
  TZ: TZ || "Asia/Jakarta"
};

// =========================== WEB APP + SECURITY ===========================

function doGet(e) {
  var auth = ERP_doGetAccess_(e);
  if (!auth.allowed) return ERP_forbiddenOutput_(auth);

  var tpl = HtmlService.createTemplateFromFile("Index");
  var pass = auth.passport || ((e && e.parameter && (e.parameter.paspor || e.parameter.passport || e.parameter.token)) || "");
  tpl.ERP_PASSPORT = pass;
  tpl.ERP_PORTAL_URL = ERP_getPortalUrl_();
  tpl.ERP_USER_EMAIL = auth.email || "";
  tpl.ERP_DISPLAY_NAME = auth.displayName || auth.email || "";
  tpl.OMNI_BOOTSTRAP = {
    moduleCode: OMNI_CFG.MODULE_CODE,
    version: OMNI_CFG.VERSION,
    email: tpl.ERP_USER_EMAIL,
    userEmail: tpl.ERP_USER_EMAIL,
    displayName: tpl.ERP_DISPLAY_NAME,
    passport: pass,
    paspor: pass,
    portalUrl: tpl.ERP_PORTAL_URL
  };

  return tpl.evaluate()
    .setTitle("ERP - Retail & Omni")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag("viewport", "width=device-width, initial-scale=1");
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

function hasOmniAccess_(email) {
  try {
    var auth = ERP_securityCheck_(email, "", false);
    return !!(auth && auth.allowed);
  } catch (e) {
    return false;
  }
}

// =========================== SETUP ===========================

function SETUP_installOmniLegacyAdapter() {
  var ss = getActiveOmni_();
  ensureSheetWithHeaders_(ss, OMNI_SHEET, OMNI_HEADERS);
  ensureSheetWithHeaders_(ss, IMPORT_LOG_SHEET, IMPORT_LOG_HEADERS);
  ensureSheetWithHeaders_(ss, RETUR_SHEET, RETUR_HEADERS);
  ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  ensureSheetWithHeaders_(ss, ADJUSTMENT_SHEET, ADJUSTMENT_HEADERS);
  ensureSheetWithHeaders_(ss, POS_SHEET, POS_HEADERS);
  OMNI_ensureDailySummarySheets_(ss);

  try {
    ensureSheetWithHeaders_(openMaster_(), "Log_Error", LOG_ERROR_HEADERS);
    ensureMasterSkuHeaders_();
  } catch (e) {
    // Setup tetap lanjut, TEST akan lapor error detail bila penting.
  }

  // Build awal hanya bila source sudah berisi data dan summary masih kosong.
  try { OMNI_ensureSummaryReady_(); } catch (summaryError) { logError_("SETUP_installOmniLegacyAdapter.summary", summaryError, {}); }
  return TEST_omniLegacyAdapter();
}

function TEST_omniLegacyAdapter() {
  var out = { success: true, version: OMNI_CFG.VERSION, checks: [] };
  try {
    var ss = getActiveOmni_();
    requireHeaders_(ss, OMNI_SHEET, ["Tanggal", "Tanggal Key", "No Pesanan", "Status", "Toko", "SKU", "Item Gudang", "Qty", "Harga Jual", "Total", "Unit_Cost", "COGS_Value", "Cost_Period", "Cost_Status", "Finance_Bucket", "No Resi", "Marketplace_Variation", "Settlement Status"]);
    out.checks.push("✅ Omni_Order warehouse-ready, support Marketplace_Variation, COGS per order line, dan siap >10.000 baris.");

    requireHeaders_(ss, IMPORT_LOG_SHEET, IMPORT_LOG_HEADERS);
    out.checks.push("✅ Import_Log aman.");

    requireHeaders_(ss, RETUR_SHEET, ["No Pesanan", "SKU BigSeller", "Item Gudang (Mapped)", "QTY Marketplace", "Conversion Qty", "QTY Retur Fisik", "QC_Source", "Gudang_Action", "Finance_Status"]);
    out.checks.push("✅ Omni_Retur aman; semua import/mapping/laporan retur runtime hanya memakai Omni_Retur.");

    requireHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
    out.checks.push("✅ Omni_Settlement terpisah aman dan siap finance handoff.");

    requireHeaders_(ss, POS_SHEET, ["POS_ID", "No_POS", "Item_Name", "Qty", "Stock_Posted"]);
    out.checks.push("✅ Omni_POS_Sales siap; POS tidak masuk Omni_Order/PR Gudang.");

    requireHeaders_(ss, OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS);
    requireHeaders_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
    requireHeaders_(ss, OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS);
    out.checks.push("✅ Daily summary toko, produk, dan settlement siap untuk Dashboard Omni + Finance.");

    var master = openMaster_();
    requireHeadersAny_(master, "Master_Item", [["Item_ID"], ["Item_Name", "Nama Item", "Produk"], ["Category", "Kategori"], ["Subcategory", "Sub_Category", "Sub Category", "Sub Kategori", "Sub-Kategori"]]);
    out.checks.push("✅ Master_Item terbaca termasuk header Subcategory.");

    requireHeaders_(master, "Master_SKU_Map", ["Marketplace_SKU", "Internal_Item_Name", "Conversion_Qty"]);
    out.checks.push("✅ Master_SKU_Map terbaca.");

    requireHeaders_(master, "Master_Store", ["Store_Name", "External_Store_Name"]);
    out.checks.push("✅ Master_Store terbaca.");

    out.omniSpreadsheetId = ss.getId();
    out.masterSpreadsheetId = MASTER_SPREADSHEET_ID;
  } catch (e) {
    out.success = false;
    out.error = e.message;
    logError_("TEST_omniLegacyAdapter", e, {});
  }
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

// =========================== LOW LEVEL HELPERS ===========================

function openMaster_() {
  return SpreadsheetApp.openById(MASTER_SPREADSHEET_ID);
}

function getActiveOmni_() {
  return SpreadsheetApp.getActiveSpreadsheet();
}

function nowText_() {
  return Utilities.formatDate(new Date(), TZ, "dd/MM/yyyy HH:mm:ss");
}

function userEmail_() {
  if (OMNI_RUNTIME_EMAIL) return OMNI_RUNTIME_EMAIL;
  try { return Session.getActiveUser().getEmail() || "unknown"; } catch(e) { return "unknown"; }
}

function uuid_(prefix) {
  return prefix + "-" + Utilities.getUuid().slice(0, 8).toUpperCase();
}

function normalize_(v) {
  return String(v || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function escapeServer_(v) {
  return String(v || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toNumber_(value) {
  if (value === null || value === undefined || value === "") return 0;
  if (typeof value === "number") return isFinite(value) ? value : 0;

  var s = String(value).trim();
  if (!s) return 0;

  s = s.replace(/[Rp\s]/gi, "");
  s = s.replace(/[^\d,.\-]/g, "");
  if (!s || s === "-" || s === "," || s === ".") return 0;

  var lastComma = s.lastIndexOf(",");
  var lastDot = s.lastIndexOf(".");

  if (lastComma !== -1 && lastDot !== -1) {
    var decimalSep = lastComma > lastDot ? "," : ".";
    var thousandSep = decimalSep === "," ? "." : ",";
    s = s.split(thousandSep).join("");
    s = s.replace(decimalSep, ".");
    return parseFloat(s) || 0;
  }

  if (lastComma !== -1) {
    var commaParts = s.split(",");
    if (commaParts.length === 2 && String(commaParts[1] || "").length <= 2) {
      s = commaParts[0].replace(/\./g, "") + "." + commaParts[1];
    } else {
      s = commaParts.join("");
    }
    return parseFloat(s) || 0;
  }

  if (lastDot !== -1) {
    var dotParts = s.split(".");
    if (dotParts.length > 2) {
      s = dotParts.join("");
    } else if (dotParts.length === 2 && dotParts[1].length === 3 && dotParts[0] !== "0") {
      s = dotParts[0] + dotParts[1];
    }
    return parseFloat(s) || 0;
  }

  return parseFloat(s) || 0;
}

function parseDateMs_(value) {
  if (!value) return 0;
  if (value instanceof Date && !isNaN(value.getTime())) return value.getTime();

  var s = String(value).trim();
  if (!s) return 0;

  // Google Sheets sometimes gives: 01 Jul 2026 7:55
  var monthMap = {
    jan:0, january:0, feb:1, februari:1, february:1, mar:2, maret:2, march:2,
    apr:3, april:3, mei:4, may:4, jun:5, juni:5, june:5, jul:6, juli:6, july:6,
    agu:7, agustus:7, aug:7, august:7, sep:8, september:8, okt:9, oktober:9, oct:9, october:9,
    nov:10, november:10, des:11, desember:11, dec:11, december:11
  };
  var named = s.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (named) {
    var monKey = named[2].toLowerCase();
    if (monthMap[monKey] !== undefined) {
      return new Date(
        parseInt(named[3], 10), monthMap[monKey], parseInt(named[1], 10),
        parseInt(named[4] || "0", 10), parseInt(named[5] || "0", 10), parseInt(named[6] || "0", 10)
      ).getTime();
    }
  }

  var datePart = s.split(" ")[0];
  var timePart = s.indexOf(" ") !== -1 ? s.split(" ").slice(1).join(" ") : "";
  var hm = timePart.match(/(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/);
  var hh = hm ? parseInt(hm[1], 10) : 0;
  var mi = hm ? parseInt(hm[2], 10) : 0;
  var ss = hm ? parseInt(hm[3] || "0", 10) : 0;

  var dmy = datePart.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})/);
  if (dmy) return new Date(parseInt(dmy[3], 10), parseInt(dmy[2], 10) - 1, parseInt(dmy[1], 10), hh, mi, ss).getTime();

  var ymd = datePart.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (ymd) return new Date(parseInt(ymd[1], 10), parseInt(ymd[2], 10) - 1, parseInt(ymd[3], 10), hh, mi, ss).getTime();

  var d = new Date(s);
  return isNaN(d.getTime()) ? 0 : d.getTime();
}

function formatDateKey_(ms) {
  return Utilities.formatDate(new Date(ms), TZ, "yyyy-MM-dd");
}

function ensureSheetWithHeaders_(ss, sheetName, headers) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) sh = ss.insertSheet(sheetName);

  if (sh.getLastRow() === 0 || sh.getLastColumn() === 0) {
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    sh.setFrozenRows(1);
    return sh;
  }

  var current = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(function(h) {
    return String(h || "").trim();
  });

  var lower = {};
  current.forEach(function(h) {
    if (h) lower[h.toLowerCase()] = true;
  });

  var toAdd = [];
  headers.forEach(function(h) {
    if (!lower[String(h).toLowerCase()]) toAdd.push(h);
  });

  if (toAdd.length > 0) {
    sh.getRange(1, current.length + 1, 1, toAdd.length).setValues([toAdd]);
  }

  sh.setFrozenRows(1);
  return sh;
}

function requireHeaders_(ss, sheetName, headers) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) throw new Error("Sheet belum ada: " + sheetName);

  var info = headerInfo_(sh);
  var missing = [];
  headers.forEach(function(h) {
    if (col_(info, h) === -1) missing.push(h);
  });
  if (missing.length) throw new Error("Header kurang di " + sheetName + ": " + missing.join(", "));
  return true;
}

function requireHeadersAny_(ss, sheetName, headerGroups) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) throw new Error("Sheet belum ada: " + sheetName);
  var info = headerInfo_(sh);
  (headerGroups || []).forEach(function(group) {
    group = Array.isArray(group) ? group : [group];
    if (col_(info, group, -1) === -1) throw new Error("Header kurang di " + sheetName + ": salah satu dari " + group.join(" / "));
  });
  return true;
}

function headerInfo_(sheet) {
  var lastCol = Math.max(1, sheet.getLastColumn());
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(function(h) {
    return String(h || "").trim();
  });
  var map = {};
  headers.forEach(function(h, i) {
    if (h) map[h.toLowerCase()] = i;
  });
  return { sheet: sheet, headers: headers, map: map };
}

function col_(info, headerNames, fallback) {
  var names = Array.isArray(headerNames) ? headerNames : [headerNames];
  for (var i = 0; i < names.length; i++) {
    var key = String(names[i] || "").trim().toLowerCase();
    if (info.map[key] !== undefined) return info.map[key];
  }
  return fallback === undefined ? -1 : fallback;
}

function readTable_(ss, sheetName, createHeaders, options) {
  options = options || {};
  var sh = ss.getSheetByName(sheetName);
  if (!sh && createHeaders && !options.noCreate) sh = ensureSheetWithHeaders_(ss, sheetName, createHeaders);
  if (!sh) return { sheet: null, headers: [], rows: [], fullData: [], info: null };

  var lastRow = sh.getLastRow();
  var lastCol = Math.max(1, sh.getLastColumn());
  var values = lastRow > 0 ? sh.getRange(1, 1, lastRow, lastCol).getValues() : [];
  var headers = values.length ? values[0].map(function(h){ return String(h || "").trim(); }) : [];
  var info = headerInfo_(sh);
  return {
    sheet: sh,
    headers: headers,
    rows: values.length > 1 ? values.slice(1) : [],
    fullData: values,
    info: info
  };
}

function tableCompat_(ss, sheetName) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) return null;
  var lastRow = sh.getLastRow();
  var lastCol = Math.max(1, sh.getLastColumn());
  var data = lastRow ? sh.getRange(1, 1, lastRow, lastCol).getValues() : [];
  var headers = data.length > 0 ? data[0] : [];
  var map = {};
  for (var i = 0; i < headers.length; i++) {
    if (headers[i]) map[headers[i].toString().trim().toLowerCase()] = i;
  }
  var c = function(headerNames, fallbackIndex) {
    var names = Array.isArray(headerNames) ? headerNames : [headerNames];
    for (var k = 0; k < names.length; k++) {
      var key = String(names[k] || "").toLowerCase();
      if (map[key] !== undefined) return map[key];
    }
    return fallbackIndex;
  };
  return { rows: data.length > 1 ? data.slice(1) : [], c: c, sheet: sh, headers: headers, fullData: data };
}

function getRowValue_(row, info, header) {
  var c = col_(info, header);
  return c !== -1 ? row[c] : "";
}

function setRowValue_(row, info, header, value) {
  var c = col_(info, header);
  if (c !== -1) row[c] = value;
}

function appendRowsChunked_(sheet, rows, width) {
  if (!rows || rows.length === 0) return 0;
  var inserted = 0;
  for (var i = 0; i < rows.length; i += WRITE_CHUNK_SIZE) {
    var chunk = rows.slice(i, i + WRITE_CHUNK_SIZE).map(function(r) {
      while (r.length < width) r.push("");
      return r.slice(0, width);
    });
    sheet.getRange(sheet.getLastRow() + 1, 1, chunk.length, width).setValues(chunk);
    inserted += chunk.length;
  }
  return inserted;
}

function writeChangedRows_(sheet, rowUpdates, width) {
  if (!rowUpdates || rowUpdates.length === 0) return 0;

  rowUpdates.sort(function(a, b) { return a.rowNumber - b.rowNumber; });
  var written = 0;
  var group = [];
  var startRow = null;
  var lastRow = null;

  function flushGroup() {
    if (!group.length) return;
    sheet.getRange(startRow, 1, group.length, width).setValues(group.map(function(r) {
      while (r.length < width) r.push("");
      return r.slice(0, width);
    }));
    written += group.length;
    group = [];
    startRow = null;
    lastRow = null;
  }

  rowUpdates.forEach(function(u) {
    if (!u.rowNumber || u.rowNumber < 2) return;
    var row = u.row || [];
    if (startRow === null) {
      startRow = u.rowNumber;
      lastRow = u.rowNumber;
      group.push(row);
    } else if (u.rowNumber === lastRow + 1 && group.length < WRITE_CHUNK_SIZE) {
      lastRow = u.rowNumber;
      group.push(row);
    } else {
      flushGroup();
      startRow = u.rowNumber;
      lastRow = u.rowNumber;
      group.push(row);
    }
  });
  flushGroup();
  return written;
}

function logError_(functionName, error, payload) {
  try {
    var master = openMaster_();
    var sh = ensureSheetWithHeaders_(master, "Log_Error", LOG_ERROR_HEADERS);
    var info = headerInfo_(sh);
    var row = new Array(info.headers.length).fill("");
    setRowValue_(row, info, "Error_ID", uuid_("ERR"));
    setRowValue_(row, info, "Timestamp", nowText_());
    setRowValue_(row, info, "Module_Code", "OMNI");
    setRowValue_(row, info, "Function_Name", functionName || "");
    setRowValue_(row, info, "Error_Message", error && error.message ? error.message : String(error));
    var json = "";
    try { json = JSON.stringify(payload || {}); } catch (e) { json = String(payload || ""); }
    if (json.length > 45000) json = json.slice(0, 45000) + "...TRUNCATED";
    setRowValue_(row, info, "Payload_JSON", json);
    setRowValue_(row, info, "User_Email", userEmail_());
    setRowValue_(row, info, "Status", "OPEN");
    sh.getRange(sh.getLastRow() + 1, 1, 1, info.headers.length).setValues([row]);
  } catch (e2) {
    Logger.log("Gagal log error: " + e2.message);
  }
}

// =========================== MASTER CACHE + MAPS ===========================

function cacheGet_(key) {
  try {
    var raw = CacheService.getScriptCache().get(key);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function cachePut_(key, value, seconds) {
  try {
    CacheService.getScriptCache().put(key, JSON.stringify(value), seconds || CACHE_SECONDS);
  } catch (e) {
    // Cache limit bisa penuh, abaikan.
  }
}

function cacheRemove_(key) {
  try { CacheService.getScriptCache().remove(key); } catch (e) {}
}

function getModulLinks(emailOp, pasporOp) {
  var auth = OMNI_requirePassport_(emailOp, pasporOp);
  try {
    var links = ERP_readModuleLinksRaw_();
    var out = [];
    for (var i = 0; i < links.length; i++) {
      var m = links[i];
      var code = ERP_key_(m.code);
      var nameKey = ERP_key_(m.name);
      if (!m.url || !ERP_isActive_(m.status)) continue;
      if (code === ERP_GLOBAL_CFG.MODULE_CODE || nameKey.indexOf('OMNI') !== -1 || nameKey.indexOf('OMNICHANNEL') !== -1) continue;
      if (!(auth.isAdmin || ERP_userCanOpenModule_(auth, m.code, m.name))) continue;
      out.push({ code: m.code, nama: m.name, name: m.name, url: ERP_appendPassportToUrl_(m.url, auth, pasporOp || auth.passport || auth.passportId || '') });
    }
    return out;
  } catch (e) {
    logError_("getModulLinks", e, {});
    return [];
  }
}

function getStoreMap_() {
  var cached = cacheGet_("OMNI_STORE_MAP_V08");
  if (cached) return cached;

  var t = tableCompat_(openMaster_(), "Master_Store");
  var map = {};
  if (!t) return map;

  var cName = t.c(["Store_Name", "Nama Toko", "Toko"], 1);
  var cExt = t.c(["External_Store_Name", "Nama Panggilan Toko BigSeller"], -1);
  var cPlat = t.c(["Platform", "Marketplace"], 2);
  var cStatus = t.c(["Status"], -1);

  t.rows.forEach(function(r) {
    var status = cStatus !== -1 ? String(r[cStatus] || "").toUpperCase() : "ACTIVE";
    if (status === "INACTIVE" || status === "NONAKTIF") return;

    var name = r[cName] ? String(r[cName]).trim() : "";
    var platform = cPlat !== -1 && r[cPlat] ? String(r[cPlat]).trim() : "";
    if (!name) return;

    var obj = { toko: name, platform: platform };
    map[normalize_(name)] = obj;

    if (cExt !== -1 && r[cExt]) {
      String(r[cExt]).split("|").forEach(function(alias) {
        alias = alias.trim();
        if (alias) map[normalize_(alias)] = obj;
      });
    }
  });

  cachePut_("OMNI_STORE_MAP_V08", map);
  return map;
}

function getSkuMap_() {
  var cached = cacheGet_("OMNI_SKU_MAP_V13");
  if (cached) return cached;

  var t = tableCompat_(openMaster_(), "Master_SKU_Map");
  var map = { __primaryKeys: [] };
  if (!t) return map;

  var cSku = t.c(["Marketplace_SKU", "SKU BigSeller", "SKU"], 1);
  var cProduct = t.c(["Marketplace_Product_Name", "Marketplace Product Name", "Product_Name", "Nama Produk", "Marketplace Item Name"], 2);
  var cVariation = t.c(["Marketplace_Variation", "Marketplace Variation", "Variation", "Variasi", "Nama Variasi", "Varian"], 3);
  var cTarget = t.c(["Internal_Item_Name", "Target_Sub_Category", "Mapped_Sub_Category", "Item Gudang", "Nama Item"], 4);
  var cQty = t.c(["Conversion_Qty", "Isi", "Isi Paket"], 5);
  var cMapType = t.c(["Mapping_Type", "Map_Type", "Mapping Type"], 10);
  var cTargetCat = t.c(["Target_Category", "Category", "Kategori"], -1);
  var cTargetSub = t.c(["Target_Sub_Category", "Subcategory", "Sub_Category", "Sub Category", "Sub Kategori", "Sub-Kategori"], -1);
  var cStatus = t.c(["Status"], 6);

  function addKey_(key, obj, alias) {
    key = String(key || "").trim();
    if (!key) return;
    var rawKey = key;
    if (!map[rawKey]) map[rawKey] = alias ? Object.assign({}, obj, { alias: true, lookupKey: rawKey }) : Object.assign({}, obj, { alias: false, lookupKey: rawKey });
    var normKey = "NORM:" + normalizeSkuLookupKey_(rawKey);
    if (!map[normKey]) map[normKey] = Object.assign({}, obj, { alias: true, lookupKey: rawKey });
  }

  t.rows.forEach(function(r) {
    var status = cStatus !== -1 ? String(r[cStatus] || "").toUpperCase() : "ACTIVE";
    if (status === "INACTIVE" || status === "NONAKTIF") return;

    var sku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
    var product = cProduct !== -1 && r[cProduct] ? String(r[cProduct]).trim() : "";
    var variation = cVariation !== -1 && r[cVariation] ? String(r[cVariation]).trim() : "";
    var target = cTarget !== -1 && r[cTarget] ? String(r[cTarget]).trim() : "";
    if (!target) return;

    var explicitType = cMapType !== -1 ? String(r[cMapType] || "").trim() : "";
    var mapType = classifyMappingTarget_(target, explicitType);
    var obj = {
      sku: sku,
      productName: product,
      variation: variation,
      item: target,
      isi: toNumber_(r[cQty]) || 1,
      mapType: mapType,
      targetCategory: cTargetCat !== -1 ? String(r[cTargetCat] || "").trim() : "",
      targetSubCategory: cTargetSub !== -1 ? String(r[cTargetSub] || "").trim() : ""
    };

    var primary = sku || (product && variation ? product + " || " + variation : "") || variation || product;
    addKey_(primary, obj, false);
    if (primary && map.__primaryKeys.indexOf(primary) === -1) map.__primaryKeys.push(primary);

    // Alias lookup final: SKU, SKU+Variasi, Produk+Variasi, Variasi saja, Produk saja.
    addKey_(sku, obj, true);
    if (sku && variation) addKey_(sku + " || " + variation, obj, true);
    if (product && variation) addKey_(product + " || " + variation, obj, true);
    addKey_(variation, obj, true);
    addKey_(product, obj, true);
  });

  cachePut_("OMNI_SKU_MAP_V13", map);
  return map;
}
function ensureMasterSkuHeaders_() {
  // Header disederhanakan sesuai desain terbaru.
  // Kolom lama seperti Platform/Store_ID/Internal_Item_ID tidak lagi wajib.
  return ensureSheetWithHeaders_(openMaster_(), "Master_SKU_Map", MASTER_SKU_MAP_HEADERS);
}

function getMasterItemLookup_() {
  var cached = cacheGet_("OMNI_MASTER_ITEM_LOOKUP_V10");
  if (cached) return cached;

  var t = tableCompat_(openMaster_(), "Master_Item");
  var lookup = { item: {}, sub: {}, categoryByItem: {}, categoryBySub: {} };
  if (!t) return lookup;

  var cItem = t.c(["Item_Name", "Nama Item", "Nama Barang", "Item", "Produk"], 2);
  var cCat = t.c(["Category", "Kategori"], 0);
  var cSub = t.c(["Subcategory", "Sub_Category", "Sub Category", "Sub Kategori", "Sub-Kategori", "Sub"], 1);
  var cStatus = t.c(["Status"], -1);

  t.rows.forEach(function(r) {
    var status = cStatus !== -1 ? String(r[cStatus] || "").toUpperCase() : "ACTIVE";
    if (status === "INACTIVE" || status === "NONAKTIF") return;
    var item = cItem !== -1 && r[cItem] ? String(r[cItem]).trim() : "";
    var cat = cCat !== -1 && r[cCat] ? String(r[cCat]).trim() : "";
    var sub = cSub !== -1 && r[cSub] ? String(r[cSub]).trim() : "";
    if (item) {
      lookup.item[normalize_(item)] = item;
      lookup.categoryByItem[normalize_(item)] = cat || "";
    }
    if (sub) {
      lookup.sub[normalize_(sub)] = sub;
      lookup.categoryBySub[normalize_(sub)] = cat || "";
    }
  });

  cachePut_("OMNI_MASTER_ITEM_LOOKUP_V10", lookup);
  return lookup;
}

function classifyMappingTarget_(targetName, explicitType) {
  var target = String(targetName || "").trim();
  var typeRaw = String(explicitType || "").toUpperCase().trim();
  if (typeRaw === "ITEM" || typeRaw === "NAMA_ITEM") return "ITEM";
  if (typeRaw === "SUB_CATEGORY" || typeRaw === "SUBKATEGORI" || typeRaw === "SUB-KATEGORI" || typeRaw === "BUNDLING") return "SUB_CATEGORY";
  if (!target || target === "UNMAPPED") return "UNMAPPED";

  var lookup = getMasterItemLookup_();
  var key = normalize_(target);
  if (lookup.sub[key]) return "SUB_CATEGORY";
  if (lookup.item[key]) return "ITEM";
  return "UNKNOWN";
}

function normalizeOrderDateKey_(value, preference) {
  return OMNI_dateKeyStrict_(value, preference || "DMY");
}

function normalizeOrderDateDisplay_(value) {
  var ms = parseDateMs_(value);
  if (!ms) return String(value || "");
  return Utilities.formatDate(new Date(ms), TZ, "dd/MM/yyyy");
}

function isCancelLikeStatus_(status) {
  var s = String(status || "").toLowerCase();
  return s.indexOf("batal") !== -1 || s.indexOf("cancel") !== -1 || s.indexOf("retur") !== -1 || s.indexOf("return") !== -1 || s.indexOf("gagal") !== -1 || s.indexOf("failed") !== -1;
}

function deriveWarehouseState_(status, noResi, mappingStatus, qtyGudang, packedQty) {
  var st = String(status || "");
  var resi = String(noResi || "").trim();
  var mapOk = String(mappingStatus || "").toUpperCase() === "MAPPED";
  var qty = toNumber_(qtyGudang);
  var packed = Math.max(0, toNumber_(packedQty));
  var remaining = Math.max(0, qty - packed);
  var notes = "";

  if (!mapOk) return { status: "UNMAPPED", remaining: 0, notes: "SKU belum mapping ke item/sub-kategori gudang" };
  if (qty <= 0) return { status: "QTY_EMPTY", remaining: 0, notes: "Qty gudang kosong atau nol" };
  if (isCancelLikeStatus_(st)) notes = "Batal/retur/gagal tetap ikut tarikan; keputusan Pack/Tidak Pack ada di Gudang.";
  if (remaining <= 0) return { status: "PACKED", remaining: 0, notes: notes || "Sudah keluar gudang" };
  if (packed > 0) return { status: "PARTIAL", remaining: remaining, notes: notes || "Sebagian sudah keluar gudang" };
  return { status: "OPEN", remaining: remaining, notes: notes || "Siap ditarik gudang" };
}


function normalizeSkuLookupKey_(v) {
  return String(v || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function compactJoinKey_(parts) {
  return (parts || []).map(function(x){ return String(x || "").trim(); }).filter(function(x){ return !!x; }).join(" || ");
}

function firstNonEmpty_() {
  for (var i = 0; i < arguments.length; i++) {
    var v = arguments[i];
    if (v !== null && v !== undefined && String(v).trim() !== "") return String(v).trim();
  }
  return "";
}

function marketplaceSkuFallback_(sku, productName, variation, noPesanan) {
  sku = String(sku || "").trim();
  productName = String(productName || "").trim();
  variation = String(variation || "").trim();
  if (sku) return sku;
  if (variation) return variation;
  if (productName) return productName;
  return noPesanan ? ("TANPA-SKU-" + String(noPesanan).trim()) : "TANPA-SKU";
}

function getMappingCandidates_(sku, productName, variation) {
  sku = String(sku || "").trim();
  productName = String(productName || "").trim();
  variation = String(variation || "").trim();
  var out = [];
  function add(x) {
    x = String(x || "").trim();
    if (!x) return;
    if (out.indexOf(x) === -1) out.push(x);
    var n = "NORM:" + normalizeSkuLookupKey_(x);
    if (out.indexOf(n) === -1) out.push(n);
  }
  add(compactJoinKey_([sku, variation]));
  add(compactJoinKey_([productName, variation]));
  add(sku);
  add(variation);
  add(productName);
  return out;
}

function resolveSkuMapping_(sku, productName, variation, skuMap) {
  skuMap = skuMap || getSkuMap_();
  var candidates = getMappingCandidates_(sku, productName, variation);
  for (var i = 0; i < candidates.length; i++) {
    var key = candidates[i];
    if (skuMap[key]) return Object.assign({}, skuMap[key], { matchedKey: key });
  }
  return { item: "UNMAPPED", isi: 1, mapType: "UNMAPPED", matchedKey: "" };
}

function mappingKeyMatchesRow_(mapKey, rowSku, rowProduct, rowVariation) {
  mapKey = String(mapKey || "").trim();
  if (!mapKey) return false;
  var keys = getMappingCandidates_(rowSku, rowProduct, rowVariation).concat([marketplaceSkuFallback_(rowSku, rowProduct, rowVariation, "")]);
  for (var i = 0; i < keys.length; i++) {
    if (String(keys[i] || "") === mapKey) return true;
    if (normalizeSkuLookupKey_(keys[i]) === normalizeSkuLookupKey_(mapKey)) return true;
  }
  return false;
}

function getDaftarTokoDinamis() {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  var t = tableCompat_(openMaster_(), "Master_Store");
  if (!t) return [];

  var cName = t.c(["Store_Name", "Toko", "Nama Toko"], 1);
  var cPlat = t.c(["Platform", "Marketplace"], 2);
  var cStatus = t.c(["Status"], -1);
  var seen = {};
  var out = [];

  t.rows.forEach(function(r) {
    var status = cStatus !== -1 ? String(r[cStatus] || "").toUpperCase() : "ACTIVE";
    if (status === "INACTIVE" || status === "NONAKTIF") return;

    var toko = r[cName] ? String(r[cName]).trim() : "";
    var plat = r[cPlat] ? String(r[cPlat]).trim() : "Lainnya";
    if (toko && !seen[toko]) {
      seen[toko] = true;
      out.push({ platform: plat, toko: toko });
    }
  });
  return out;
}

function resolveStoreName_(rawName) {
  var storeMap = getStoreMap_();
  var key = normalize_(rawName);
  return storeMap[key] ? storeMap[key].toko : String(rawName || "").trim();
}

// =========================== IMPORT ORDER - HIGH PERFORMANCE ===========================

function prosesImportOmni(payload) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success: false, error: "Server sibuk. Coba lagi." }; }

  try {
    var input = normalizeImportPayload_(payload);
    var rows = input.rows;
    if (rows.length === 0) return { success: false, error: "Data kosong." };

    var started = new Date().getTime();
    var ss = getActiveOmni_();
    var sh = ensureSheetWithHeaders_(ss, OMNI_SHEET, OMNI_HEADERS);
    OMNI_setPlainTextColumnByHeader_(sh, ["Tanggal Key"]);
    var t = readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
    var info = t.info;
    var width = info.headers.length;

    var skuMap = getSkuMap_();
    var storeMap = getStoreMap_();
    var importId = input.importId || uuid_("IMP");
    var now = nowText_();
    var user = userEmail_();
    var costCtx = null; // Lazy-load Gudang hanya jika ada order baru/perubahan input HPP.

    var existingMap = buildExistingOrderIndex_(t);
    var agg = aggregateOrderRows_(rows);

    var unmapped = [];
    var insertRows = [];
    var updateRows = [];
    var changedRowsForSummary = [];
    var oldSummaryGroups = {};
    var processedKeys = Object.keys(agg);

    processedKeys.forEach(function(key) {
      var p = agg[key];
      var no = String(p.no || "").trim();
      var sku = marketplaceSkuFallback_(p.sku, p.productName || p.itemName, p.variation, no);
      var productName = firstNonEmpty_(p.productName, p.itemName, sku);
      var variation = String(p.variation || "").trim();
      if (!no || !sku) return;

      var mapData = resolveSkuMapping_(sku, productName, variation, skuMap);
      var mappingStatus = mapData.item && mapData.item !== "UNMAPPED" ? "MAPPED" : "UNMAPPED";
      var unmappedKey = mapData.matchedKey || compactJoinKey_([sku, variation]) || sku;
      if (mappingStatus !== "MAPPED" && unmapped.indexOf(unmappedKey) === -1) unmapped.push(unmappedKey);

      var rawQty = toNumber_(p.qty);
      var conversion = toNumber_(mapData.isi) || 1;
      var qtyGudang = rawQty * conversion;
      var total = toNumber_(p.subtotal);
      var hargaSat = qtyGudang > 0 ? total / qtyGudang : 0;

      var storeObj = storeMap[normalize_(p.toko)] || null;
      var mappedStore = storeObj ? storeObj.toko : String(p.toko || "").trim();

      var existing = existingMap[buildOrderIndexKey_(no, sku, variation)] || existingMap[no + "|" + sku];
      var row = existing ? existing.row.slice(0, width) : new Array(width).fill("");
      while (row.length < width) row.push("");

      var orderDateKey = OMNI_dateKeyStrict_(p.tglKey || p.tgl || "", p.dateOrder || "DMY");
      setRowValue_(row, info, "Tanggal", p.tgl || orderDateKey || "");
      setRowValue_(row, info, "Tanggal Key", orderDateKey);
      setRowValue_(row, info, "No Pesanan", no);
      setRowValue_(row, info, "Status", p.status || "");
      setRowValue_(row, info, "Toko", mappedStore);
      setRowValue_(row, info, "SKU", sku);
      setRowValue_(row, info, "Item Gudang", mapData.item);
      setRowValue_(row, info, "Qty", qtyGudang);
      setRowValue_(row, info, "Harga Jual", hargaSat);
      setRowValue_(row, info, "Total", total);
      if (!existing || OMNI_orderCostInputsChanged_(existing.row, row, info)) {
        if (!costCtx) costCtx = OMNI_prepareOrderCogsContext_();
        OMNI_applyOrderCogsToRow_(row, info, costCtx, mapData.item, qtyGudang, orderDateKey || p.tgl || row[col_(info, "Tanggal", -1)] || new Date(), total);
      }
      setRowValue_(row, info, "No Resi", p.resi || "");
      setRowValue_(row, info, "Marketplace Item Name", productName || sku);
      setRowValue_(row, info, "Marketplace_Variation", variation);
      setRowValue_(row, info, "Settlement Status", getRowValue_(row, info, "Settlement Status") || "BELUM CAIR");
      setRowValue_(row, info, "Is_Deleted", false);

      if (existing && OMNI_orderRowsEquivalent_(existing.row, row, info)) {
        // Tidak ada perubahan bisnis. Jangan tulis ulang row hanya karena waktu/import ID berubah.
        return;
      }

      var summaryChanged = !existing || OMNI_orderSummaryInputsChanged_(existing.row, row, info);
      if (existing && summaryChanged) {
        OMNI_addSummaryGroupFromOrderRow_(oldSummaryGroups, existing.row, info);
      }

      setRowValue_(row, info, "Import_ID", importId);
      setRowValue_(row, info, "Updated_At", now);
      setRowValue_(row, info, "Updated_By", user);

      if (existing) updateRows.push({ rowNumber: existing.rowNumber, row: row });
      else insertRows.push(row);
      if (summaryChanged) changedRowsForSummary.push(row);
    });

    var inserted = appendRowsChunked_(sh, insertRows, width);
    var updated = writeChangedRows_(sh, updateRows, width);

    // Mutasikan tabel yang sudah ada di memori agar summary tidak membaca Omni_Order penuh untuk kedua kalinya.
    updateRows.forEach(function(u) {
      if (u.rowNumber >= 2) t.rows[u.rowNumber - 2] = u.row.slice(0, width);
    });
    insertRows.forEach(function(r) { t.rows.push(r.slice(0, width)); });

    var newSummaryGroups = {};
    changedRowsForSummary.forEach(function(r) { OMNI_addSummaryGroupFromOrderRow_(newSummaryGroups, r, info); });
    var summaryGroups = OMNI_mergeGroupFilters_(oldSummaryGroups, newSummaryGroups);
    var changedCount = inserted + updated;
    var summaryResult = changedCount > 0 && Object.keys(summaryGroups).length > 0
      ? OMNI_rebuildOrderDailySummary_(summaryGroups, t, { storeMap: storeMap, skuMap: skuMap })
      : { success:true, skipped:true, groups:0, orderStoreRows:0, orderProductRows:0, sourceRows:0 };

    writeImportLog_("BIGSELLER_ORDER", input.fileName, rows.length, inserted, updated, unmapped, importId);
    if (changedCount > 0) OMNI_touchMutation_("prosesImportOmni");

    return {
      success: true,
      insert: inserted,
      update: updated,
      unchanged: Math.max(0, processedKeys.length - inserted - updated),
      processed: processedKeys.length,
      unmapped: unmapped.sort(),
      readyWarehouse: countReadyWarehouse_(insertRows.concat(updateRows.map(function(u){ return u.row; })), info),
      importId: importId,
      dailySummary: summaryResult,
      ms: new Date().getTime() - started
    };
  } catch(e) {
    logError_("prosesImportOmni", e, { rows: Array.isArray(payload) ? payload.length : (payload && payload.rows ? payload.rows.length : 0) });
    return { success: false, error: e.message };
  } finally {
    lock.releaseLock();
  }
}

function OMNI_orderCostInputsChanged_(oldRow, newRow, info) {
  var headers = ["Tanggal Key", "Item Gudang", "Qty", "Total"];
  for (var i = 0; i < headers.length; i++) {
    var c = col_(info, headers[i], -1);
    if (c === -1) continue;
    if (OMNI_compareCellValue_(oldRow[c], headers[i]) !== OMNI_compareCellValue_(newRow[c], headers[i])) return true;
  }
  return false;
}

function OMNI_orderSummaryInputsChanged_(oldRow, newRow, info) {
  var headers = [
    "Tanggal Key", "No Pesanan", "Status", "Toko", "Item Gudang", "Qty", "Total",
    "COGS_Value", "Finance_Bucket", "Settlement Status", "Is_Deleted"
  ];
  for (var i = 0; i < headers.length; i++) {
    var c = col_(info, headers[i], -1);
    if (c === -1) continue;
    if (OMNI_compareCellValue_(oldRow[c], headers[i]) !== OMNI_compareCellValue_(newRow[c], headers[i])) return true;
  }
  return false;
}

function OMNI_orderRowsEquivalent_(oldRow, newRow, info) {
  var headers = [
    "Tanggal", "Tanggal Key", "No Pesanan", "Status", "Toko", "SKU",
    "Item Gudang", "Qty", "Harga Jual", "Total", "Unit_Cost", "COGS_Value",
    "Cost_Period", "Cost_Status", "Cost_Source", "Finance_Bucket", "No Resi",
    "Marketplace Item Name", "Marketplace_Variation", "Settlement Status", "Is_Deleted"
  ];
  for (var i = 0; i < headers.length; i++) {
    var c = col_(info, headers[i], -1);
    if (c === -1) continue;
    if (OMNI_compareCellValue_(oldRow[c], headers[i]) !== OMNI_compareCellValue_(newRow[c], headers[i])) return false;
  }
  return true;
}

function OMNI_compareCellValue_(value, header) {
  if (value === null || value === undefined || value === "") return "";
  var h = normalize_(header || "");
  if (value instanceof Date && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, TZ, "yyyy-MM-dd HH:mm:ss");
  }
  if (h === "tanggal") {
    var ms = parseDateMs_(value);
    if (ms) return Utilities.formatDate(new Date(ms), TZ, "yyyy-MM-dd HH:mm:ss");
  }
  if (["qty","harga_jual","total","unit_cost","cogs_value"].indexOf(h.replace(/ /g, "_")) !== -1) {
    var n = toNumber_(value);
    return String(Math.round(n * 1000000) / 1000000);
  }
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  var s = String(value).trim();
  if (h === "is_deleted") {
    var u = s.toUpperCase();
    return ["TRUE","YES","YA","Y","1","DELETED"].indexOf(u) !== -1 ? "TRUE" : "FALSE";
  }
  return s;
}

function OMNI_addSummaryGroupFromOrderRow_(out, row, info) {
  out = out || {};
  if (!row || !info) return out;
  var dateKey = OMNI_dateKeyFromAny_(getRowValueAny_(row, info, ["Tanggal Key","Tanggal"]));
  var store = String(getRowValueAny_(row, info, ["Toko"]) || "").trim();
  if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  return out;
}

function normalizeImportPayload_(payload) {
  if (Array.isArray(payload)) return { rows: payload, fileName: "", importId: "" };
  payload = payload || {};
  return {
    rows: payload.rows || payload.Rows || payload.data || [],
    fileName: payload.fileName || payload.File_Name || "",
    importId: payload.importId || payload.Import_ID || ""
  };
}

function buildOrderIndexKey_(no, sku, variation) {
  return String(no || "").trim() + "|" + String(sku || "").trim() + "|" + normalizeSkuLookupKey_(variation || "");
}

function buildExistingOrderIndex_(table) {
  var info = table.info;
  var cNo = col_(info, ["No Pesanan"]);
  var cSku = col_(info, ["SKU"]);
  var cVariation = col_(info, ["Marketplace_Variation", "Marketplace Variation", "Nama Variasi", "Variation"], -1);
  var cDel = col_(info, ["Is_Deleted"], -1);
  var map = {};

  table.rows.forEach(function(r, idx) {
    if (cDel !== -1) {
      var del = String(r[cDel] || "").toUpperCase();
      if (del === "TRUE" || del === "YA" || del === "1") return;
    }
    var no = cNo !== -1 && r[cNo] ? String(r[cNo]).trim() : "";
    var sku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
    var variation = cVariation !== -1 && r[cVariation] ? String(r[cVariation]).trim() : "";
    if (no && sku) {
      map[buildOrderIndexKey_(no, sku, variation)] = { rowNumber: idx + 2, row: r };
      // Fallback backward compatibility untuk data lama sebelum kolom variasi ada.
      if (!map[no + "|" + sku]) map[no + "|" + sku] = { rowNumber: idx + 2, row: r };
    }
  });
  return map;
}

function aggregateOrderRows_(rows) {
  var agg = {};
  rows.forEach(function(p) {
    var no = String(p.no || p.No || p.Order_No || "").trim();
    var rawSku = firstNonEmpty_(p.sku, p.SKU, p.Marketplace_SKU);
    var productName = firstNonEmpty_(p.productName, p.Marketplace_Product_Name, p.Marketplace_Item_Name, p.itemName, p.nama, p.Nama_Produk, p["Nama Produk"]);
    var variation = firstNonEmpty_(p.variation, p.Marketplace_Variation, p.Variation, p.Varisi, p.Variasi, p["Nama Variasi"], p.Varian);
    var sku = marketplaceSkuFallback_(rawSku, productName, variation, no);
    if (!no || !sku) return;

    var key = buildOrderIndexKey_(no, sku, variation);
    if (!agg[key]) {
      agg[key] = {
        no: no,
        sku: sku,
        productName: productName,
        variation: variation,
        tgl: p.tgl || p.Tanggal || p.Order_Date || "",
        tglKey: p.tglKey || p.Tanggal_Key || p["Tanggal Key"] || "",
        dateOrder: p.dateOrder || p.Date_Order || "DMY",
        status: p.status || p.Status || "",
        toko: p.toko || p.Toko || p.Store_Name || "",
        qty: 0,
        subtotal: 0,
        resi: p.resi || p.No_Resi || p.Tracking_No || "",
        itemName: productName || sku
      };
    }
    agg[key].qty += toNumber_(p.qty || p.Qty || p.Jumlah);
    agg[key].subtotal += toNumber_(p.subtotal || p.Total || p.Line_Subtotal);
    // Ambil metadata terbaru jika ada.
    if (p.status || p.Status) agg[key].status = p.status || p.Status;
    if (p.resi || p.No_Resi || p.Tracking_No) agg[key].resi = p.resi || p.No_Resi || p.Tracking_No;
    if (p.tgl || p.Tanggal || p.Order_Date) agg[key].tgl = p.tgl || p.Tanggal || p.Order_Date;
    if (p.tglKey || p.Tanggal_Key || p["Tanggal Key"]) agg[key].tglKey = p.tglKey || p.Tanggal_Key || p["Tanggal Key"];
    if (p.dateOrder || p.Date_Order) agg[key].dateOrder = p.dateOrder || p.Date_Order;
    if (p.toko || p.Toko || p.Store_Name) agg[key].toko = p.toko || p.Toko || p.Store_Name;
    if (productName) { agg[key].productName = productName; agg[key].itemName = productName; }
    if (variation) agg[key].variation = variation;
  });
  return agg;
}

function writeImportLog_(fileType, fileName, rowsRead, rowsInsert, rowsUpdate, unmapped, importId) {
  var ss = getActiveOmni_();
  var sh = ensureSheetWithHeaders_(ss, IMPORT_LOG_SHEET, IMPORT_LOG_HEADERS);
  var info = headerInfo_(sh);
  var row = new Array(info.headers.length).fill("");
  setRowValue_(row, info, "Import_ID", importId || uuid_("IMP"));
  setRowValue_(row, info, "Import_Date", nowText_());
  setRowValue_(row, info, "File_Type", fileType);
  setRowValue_(row, info, "File_Name", fileName || "");
  setRowValue_(row, info, "Rows_Read", rowsRead || 0);
  setRowValue_(row, info, "Rows_Insert", rowsInsert || 0);
  setRowValue_(row, info, "Rows_Update", rowsUpdate || 0);
  setRowValue_(row, info, "Unmapped_Count", unmapped ? unmapped.length : 0);
  setRowValue_(row, info, "Imported_By", userEmail_());
  setRowValue_(row, info, "Notes", unmapped && unmapped.length ? "Unmapped: " + unmapped.join(", ") : "OK");
  sh.getRange(sh.getLastRow() + 1, 1, 1, info.headers.length).setValues([row]);
}

// =========================== MAPPING SKU ===========================

function countReadyWarehouse_(rows, info) {
  var cItem = col_(info, "Item Gudang", -1);
  var cQty = col_(info, "Qty", -1);
  var n = 0;
  rows.forEach(function(r) {
    var item = cItem !== -1 ? String(r[cItem] || "").trim().toUpperCase() : "";
    var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
    if (item && item !== "UNMAPPED" && qty > 0) n++;
  });
  return n;
}

function REBUILD_omniOrderWarehouseFields() {
  // v1.3.1: function ini bisa dipanggil dari UI (dengan email+paspor)
  // atau manual dari Apps Script editor (tanpa argumen) untuk maintenance setelah update header/mapping.
  var __auth = OMNI_requirePassportOrEditor_(arguments, 'REBUILD_omniOrderWarehouseFields');

  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success: false, error: "Server sibuk." }; }

  try {
    var ss = getActiveOmni_();
    ensureSheetWithHeaders_(ss, OMNI_SHEET, OMNI_HEADERS);
    var t = readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
    if (!t.sheet || t.rows.length === 0) return { success: true, total: 0, updated: 0, ready: 0, unmapped: 0, qtyEmpty: 0 };

    var info = t.info;
    var skuMap = getSkuMap_();
    var updates = [];
    var stat = { success: true, total: t.rows.length, updated: 0, ready: 0, unmapped: 0, qtyEmpty: 0, cancelIncluded: 0 };
    var now = nowText_();
    var user = userEmail_();
    var costCtx = OMNI_prepareOrderCogsContext_();

    var cSku = col_(info, "SKU", -1);
    var cTanggal = col_(info, "Tanggal", -1);
    var cTglKey = col_(info, "Tanggal Key", -1);
    var cStatus = col_(info, "Status", -1);
    var cResi = col_(info, "No Resi", -1);
    var cItem = col_(info, "Item Gudang", -1);
    var cQty = col_(info, "Qty", -1);
    var cHarga = col_(info, "Harga Jual", -1);
    var cTotal = col_(info, "Total", -1);
    var cProduct = col_(info, ["Marketplace Item Name", "Marketplace_Product_Name", "Product Name"], -1);
    var cVariation = col_(info, ["Marketplace_Variation", "Marketplace Variation", "Nama Variasi", "Variation"], -1);
    var cSettlement = col_(info, "Settlement Status", -1);
    var cUpdated = col_(info, "Updated_At", -1);
    var cBy = col_(info, "Updated_By", -1);
    var cDel = col_(info, "Is_Deleted", -1);

    t.rows.forEach(function(r, idx) {
      if (cDel !== -1) {
        var del = String(r[cDel] || "").toUpperCase();
        if (del === "TRUE" || del === "YA" || del === "1") return;
      }
      var oldSku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
      var productName = cProduct !== -1 && r[cProduct] ? String(r[cProduct]).trim() : "";
      var variation = cVariation !== -1 && r[cVariation] ? String(r[cVariation]).trim() : "";
      var sku = marketplaceSkuFallback_(oldSku, productName, variation, "");
      if (!sku) return;

      var mapData = resolveSkuMapping_(sku, productName, variation, skuMap);
      var item = mapData && mapData.item ? mapData.item : (cItem !== -1 ? String(r[cItem] || "").trim() : "");
      var conversion = mapData ? (toNumber_(mapData.isi) || 1) : 1;

      var oldQty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
      var qtyFinal = oldQty;
      if (mapData && (String(r[cItem] || "").trim().toUpperCase() === "UNMAPPED" || String(r[cItem] || "").trim() === "")) {
        qtyFinal = oldQty * conversion;
      }

      var total = cTotal !== -1 ? toNumber_(r[cTotal]) : 0;
      var harga = qtyFinal > 0 ? total / qtyFinal : 0;
      var isMapped = item && item.toUpperCase() !== "UNMAPPED";
      var status = cStatus !== -1 ? String(r[cStatus] || "") : "";

      if (!isMapped) stat.unmapped++;
      else if (qtyFinal <= 0) stat.qtyEmpty++;
      else { if (isCancelLikeStatus_(status)) stat.cancelIncluded++; stat.ready++; }

      var row = r.slice(0, info.headers.length);
      while (row.length < info.headers.length) row.push("");
      if (cSku !== -1) row[cSku] = sku;
      if (cTglKey !== -1 && !row[cTglKey] && cTanggal !== -1) row[cTglKey] = normalizeOrderDateKey_(row[cTanggal]);
      if (cItem !== -1) row[cItem] = isMapped ? item : "UNMAPPED";
      if (cQty !== -1) row[cQty] = qtyFinal;
      if (cHarga !== -1) row[cHarga] = harga;
      OMNI_applyOrderCogsToRow_(row, info, costCtx, isMapped ? item : "", qtyFinal, cTanggal !== -1 ? row[cTanggal] : new Date(), total);
      if (cSettlement !== -1 && !row[cSettlement]) row[cSettlement] = "BELUM CAIR";
      if (cUpdated !== -1) row[cUpdated] = now;
      if (cBy !== -1) row[cBy] = user;
      updates.push({ rowNumber: idx + 2, row: row });
    });

    stat.updated = writeChangedRows_(t.sheet, updates, info.headers.length);
    SpreadsheetApp.flush();
    stat.dailySummary = OMNI_rebuildOrderDailySummary_(null);
    OMNI_touchMutation_("REBUILD_omniOrderWarehouseFields");
    return stat;
  } catch(e) {
    logError_("REBUILD_omniOrderWarehouseFields", e, {});
    return { success: false, error: e.message };
  } finally { lock.releaseLock(); }
}

function getDataMappingSKU() {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  try {
    ensureMasterSkuHeaders_();

    var skuMap = getSkuMap_();
    var masterItems = getMasterItemOptionsWithPrice_();

    var mapped = {};
    (skuMap.__primaryKeys || []).sort().forEach(function(key) {
      var m = skuMap[key];
      if (!m || m.alias) return;
      var label = m.item || "";
      var isi = toNumber_(m.isi) || 1;
      var tipe = m.mapType ? (" | " + m.mapType) : "";
      mapped[key] = label + " (Isi: " + isi + " pcs" + tipe + ")";
    });

    var unmapped = [];
    var seen = {};
    function addUnmapped_(key) {
      key = String(key || "").trim();
      if (!key) return;
      if (seen[key]) return;
      seen[key] = true;
      unmapped.push(key);
    }

    var omni = readTable_(getActiveOmni_(), OMNI_SHEET, OMNI_HEADERS);
    if (omni.sheet) {
      var cSku = col_(omni.info, ["SKU", "Marketplace_SKU"], -1);
      var cItem = col_(omni.info, ["Item Gudang", "Internal_Item_Name"], -1);
      var cProduct = col_(omni.info, ["Marketplace Item Name", "Marketplace_Product_Name", "Nama Produk"], -1);
      var cVariation = col_(omni.info, ["Marketplace_Variation", "Marketplace Variation", "Nama Variasi", "Variation", "Varian"], -1);
      var cDel = col_(omni.info, "Is_Deleted", -1);

      omni.rows.forEach(function(r) {
        if (cDel !== -1) {
          var del = String(r[cDel] || "").toUpperCase();
          if (del === "TRUE" || del === "YA" || del === "1") return;
        }

        var sku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
        var productName = cProduct !== -1 && r[cProduct] ? String(r[cProduct]).trim() : "";
        var variation = cVariation !== -1 && r[cVariation] ? String(r[cVariation]).trim() : "";
        sku = marketplaceSkuFallback_(sku, productName, variation, "");
        if (!sku) return;

        var mapData = resolveSkuMapping_(sku, productName, variation, skuMap);
        var item = cItem !== -1 && r[cItem] ? String(r[cItem]).trim() : "";
        if (!mapData || !mapData.item || mapData.item === "UNMAPPED" || item === "" || item.toUpperCase() === "UNMAPPED") {
          addUnmapped_(compactJoinKey_([sku, variation]) || sku);
        }
      });
    }

    collectUnmappedFromRetur_(unmapped, skuMap);

    unmapped.sort(function(a,b){ return a.localeCompare(b); });
    return {
      success: true,
      masterItems: masterItems || [],
      unmapped: unmapped,
      mapped: mapped,
      counts: {
        masterItems: masterItems ? masterItems.length : 0,
        mapped: Object.keys(mapped).length,
        unmapped: unmapped.length
      }
    };
  } catch (e) {
    logError_("getDataMappingSKU", e, {});
    return { success: false, error: e.message, masterItems: [], unmapped: [], mapped: {}, counts: { masterItems: 0, mapped: 0, unmapped: 0 } };
  }
}

function collectUnmappedFromRetur_(unmapped, skuMap) {
  var seen = {};
  unmapped.forEach(function(x){ seen[x] = true; });

  readReturTables_(false).forEach(function(t) {
    var cSku = col_(t.info, ["SKU BigSeller", "SKU"]);
    var cItem = col_(t.info, ["Item Gudang (Mapped)", "Item Gudang"]);
    t.rows.forEach(function(r) {
      var sku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
      var item = cItem !== -1 && r[cItem] ? String(r[cItem]).trim() : "";
      if (!sku) return;
      if ((!skuMap[sku] || item === "UNMAPPED" || item === "") && !seen[sku]) {
        seen[sku] = true;
        unmapped.push(sku);
      }
    });
  });
}

function simpanMappingBaru(sku, namaItem, isiPaket) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch(e) { return "Server sibuk."; }

  try {
    sku = String(sku || "").trim();
    namaItem = String(namaItem || "").trim();
    isiPaket = toNumber_(isiPaket) || 1;

    if (!sku) throw new Error("SKU kosong.");
    if (!namaItem) throw new Error("Item/Sub-kategori target kosong.");
    if (isiPaket <= 0) throw new Error("Isi paket harus lebih dari 0.");

    upsertMasterSkuMap_(sku, namaItem, isiPaket);
    applyMappingToOmni_(sku, namaItem, isiPaket);
    applyMappingToRetur_(sku, namaItem, isiPaket);

    cacheRemove_("OMNI_SKU_MAP_V13");
    cacheRemove_("OMNI_SKU_MAP_V10");
    cacheRemove_("OMNI_MASTER_ITEM_LOOKUP_V10");
    SpreadsheetApp.flush();
    OMNI_rebuildOrderDailySummary_(null);
    OMNI_touchMutation_("simpanMappingBaru");
    return "OK";
  } catch(e) {
    logError_("simpanMappingBaru", e, { sku: sku, namaItem: namaItem, isiPaket: isiPaket });
    return e.message;
  } finally {
    lock.releaseLock();
  }
}

function upsertMasterSkuMap_(sku, targetName, isiPaket) {
  var master = openMaster_();
  var sh = ensureMasterSkuHeaders_();
  var t = readTable_(master, "Master_SKU_Map");
  var info = t.info;
  var cSku = col_(info, "Marketplace_SKU");
  var cProduct = col_(info, ["Marketplace_Product_Name", "Marketplace Product Name"], -1);
  var cVariation = col_(info, ["Marketplace_Variation", "Marketplace Variation"], -1);
  var rowIndex = -1;

  var key = String(sku || "").trim();
  var parts = key.split(" || ");
  var maybeSku = parts.length > 1 ? parts[0].trim() : key;
  var maybeVariation = parts.length > 1 ? parts.slice(1).join(" || ").trim() : "";

  for (var i = 0; i < t.rows.length; i++) {
    var rSku = cSku !== -1 && t.rows[i][cSku] ? String(t.rows[i][cSku]).trim() : "";
    var rProduct = cProduct !== -1 && t.rows[i][cProduct] ? String(t.rows[i][cProduct]).trim() : "";
    var rVariation = cVariation !== -1 && t.rows[i][cVariation] ? String(t.rows[i][cVariation]).trim() : "";
    if (normalizeSkuLookupKey_(rSku) === normalizeSkuLookupKey_(key) || normalizeSkuLookupKey_(compactJoinKey_([rSku, rVariation])) === normalizeSkuLookupKey_(key) || normalizeSkuLookupKey_(compactJoinKey_([rProduct, rVariation])) === normalizeSkuLookupKey_(key)) {
      rowIndex = i + 2;
      break;
    }
  }

  var row;
  if (rowIndex !== -1) row = sh.getRange(rowIndex, 1, 1, info.headers.length).getValues()[0];
  else row = new Array(info.headers.length).fill("");

  var mapType = classifyMappingTarget_(targetName, "");

  if (rowIndex === -1) setRowValue_(row, info, "Map_ID", uuid_("MAP"));
  setRowValue_(row, info, "Marketplace_SKU", maybeSku || key);
  if (!getRowValue_(row, info, "Marketplace_Product_Name")) setRowValue_(row, info, "Marketplace_Product_Name", parts.length > 1 ? maybeSku : key);
  if (!getRowValue_(row, info, "Marketplace_Variation")) setRowValue_(row, info, "Marketplace_Variation", maybeVariation);

  setRowValue_(row, info, "Internal_Item_Name", targetName);
  setRowValue_(row, info, "Conversion_Qty", isiPaket);
  setRowValue_(row, info, "Status", "ACTIVE");
  setRowValue_(row, info, "Updated_At", nowText_());
  setRowValue_(row, info, "Updated_By", userEmail_());
  setRowValue_(row, info, "Notes", "Mapping dari UI Omni v1.3. Target bisa nama item atau sub-kategori; key bisa SKU, SKU+variasi, product+variasi, atau variasi saja.");
  setRowValue_(row, info, "Mapping_Type", mapType);

  if (rowIndex !== -1) sh.getRange(rowIndex, 1, 1, info.headers.length).setValues([row]);
  else sh.getRange(sh.getLastRow() + 1, 1, 1, info.headers.length).setValues([row]);
}

function applyMappingToOmni_(sku, namaItem, isiPaket) {
  var t = readTable_(getActiveOmni_(), OMNI_SHEET, OMNI_HEADERS);
  if (!t.sheet || t.fullData.length <= 1) return 0;

  var info = t.info;
  var cSku = col_(info, "SKU", -1);
  var cProduct = col_(info, ["Marketplace Item Name", "Marketplace_Product_Name", "Nama Produk"], -1);
  var cVariation = col_(info, ["Marketplace_Variation", "Marketplace Variation", "Nama Variasi", "Variation"], -1);
  var cItem = col_(info, "Item Gudang", -1);
  var cQty = col_(info, "Qty", -1);
  var cHarga = col_(info, "Harga Jual", -1);
  var cTotal = col_(info, "Total", -1);
  var cUpdated = col_(info, "Updated_At", -1);
  var cBy = col_(info, "Updated_By", -1);

  var updates = [];
  var now = nowText_();
  var user = userEmail_();

  t.rows.forEach(function(r, idx) {
    var rSku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
    var rProduct = cProduct !== -1 && r[cProduct] ? String(r[cProduct]).trim() : "";
    var rVariation = cVariation !== -1 && r[cVariation] ? String(r[cVariation]).trim() : "";
    if (!mappingKeyMatchesRow_(sku, rSku, rProduct, rVariation)) return;

    var oldItem = cItem !== -1 ? String(r[cItem] || "").trim() : "";
    var oldQty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
    var newQty = (oldItem === "" || oldItem.toUpperCase() === "UNMAPPED") ? oldQty * (toNumber_(isiPaket) || 1) : oldQty;
    var total = cTotal !== -1 ? toNumber_(r[cTotal]) : 0;
    var harga = newQty > 0 ? total / newQty : 0;

    var row = r.slice(0, info.headers.length);
    while (row.length < info.headers.length) row.push("");
    if (cItem !== -1) row[cItem] = namaItem;
    if (cQty !== -1) row[cQty] = newQty;
    if (cHarga !== -1) row[cHarga] = harga;
    if (cUpdated !== -1) row[cUpdated] = now;
    if (cBy !== -1) row[cBy] = user;
    updates.push({ rowNumber: idx + 2, row: row });
  });

  return writeChangedRows_(t.sheet, updates, info.headers.length);
}

function applyMappingToRetur_(sku, namaItem, isiPaket) {
  var totalUpdated = 0;

  readReturTables_(false).forEach(function(t) {
    if (!t.sheet || t.fullData.length <= 1) return;

    var info = t.info;
    var cSku = col_(info, ["SKU BigSeller", "SKU"]);
    var cProduct = col_(info, ["Marketplace_Product_Name", "Marketplace Item Name", "Nama Produk"], -1);
    var cVariation = col_(info, ["Marketplace_Variation", "Marketplace Variation", "Nama Variasi", "Variation"], -1);
    var cItem = col_(info, ["Item Gudang (Mapped)", "Item Gudang"]);
    var cQtyMarket = col_(info, ["QTY Marketplace", "Qty Marketplace"], -1);
    var cConv = col_(info, "Conversion Qty", -1);
    var cQtyRetur = col_(info, ["QTY Retur Fisik", "Qty"]);
    var cUpdated = col_(info, "Updated_At", -1);
    var cBy = col_(info, "Updated_By", -1);

    var updates = [];
    var now = nowText_();
    var user = userEmail_();

    t.rows.forEach(function(r, idx) {
      var rSku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
      var rProduct = cProduct !== -1 && r[cProduct] ? String(r[cProduct]).trim() : "";
      var rVariation = cVariation !== -1 && r[cVariation] ? String(r[cVariation]).trim() : "";
      if (!mappingKeyMatchesRow_(sku, rSku, rProduct, rVariation)) return;

      var qtyMarket = cQtyMarket !== -1 ? toNumber_(r[cQtyMarket]) : 0;
      var conversion = toNumber_(isiPaket) || 1;
      var row = r.slice(0, info.headers.length);
      while (row.length < info.headers.length) row.push("");
      if (cItem !== -1) row[cItem] = namaItem;
      if (cConv !== -1) row[cConv] = conversion;
      if (cQtyRetur !== -1) row[cQtyRetur] = qtyMarket * conversion;
      if (cUpdated !== -1) row[cUpdated] = now;
      if (cBy !== -1) row[cBy] = user;
      updates.push({ rowNumber: idx + 2, row: row });
    });

    totalUpdated += writeChangedRows_(t.sheet, updates, info.headers.length);
  });

  return totalUpdated;
}

// =========================== POS ===========================

function getMenuPOS() {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  try {
    return getMasterItemOptionsWithPrice_();
  } catch (e) {
    logError_("getMenuPOS", e, {});
    return [];
  }
}

function getMasterItemOptionsWithPrice_() {
  var cached = cacheGet_("OMNI_MASTER_ITEM_POS_V07");
  if (cached) return cached;

  var t = tableCompat_(openMaster_(), "Master_Item");
  if (!t) return [];

  var cKat = t.c(["Category", "Kategori"], 4);
  var cSub = t.c(["Subcategory", "Sub_Category", "Sub Category", "Sub Kategori", "Sub-Kategori"], 5);
  var cName = t.c(["Item_Name", "Nama Item", "Nama", "Item", "Produk"], 2);
  var cPrice = t.c(["Default_Selling_Price", "Harga Jual", "Harga", "Harga Eceran", "Price"], 8);
  var cStatus = t.c(["Status"], -1);

  var seen = {};
  var out = [];

  t.rows.forEach(function(r) {
    var status = cStatus !== -1 ? String(r[cStatus] || "").toUpperCase() : "ACTIVE";
    if (status === "INACTIVE" || status === "NONAKTIF") return;

    var kat = r[cKat] ? String(r[cKat]).trim() : "Umum";
    var sub = r[cSub] ? String(r[cSub]).trim() : "";
    var name = r[cName] ? String(r[cName]).trim() : "";
    var price = toNumber_(r[cPrice]);

    if (sub && sub !== "Biaya Ongkos Kirim" && !seen[sub]) {
      seen[sub] = true;
      out.push({ kat: kat + " / Sub-Kategori", nama: sub, harga: price });
    }
    if (name && name !== "Biaya Ongkos Kirim" && !seen[name]) {
      seen[name] = true;
      out.push({ kat: kat + " / Item", nama: name, harga: price });
    }
  });

  out.sort(function(a,b) { return a.nama.localeCompare(b.nama); });
  cachePut_("OMNI_MASTER_ITEM_POS_V07", out);
  return out;
}

function formatInputTglPOS(d) {
  return Utilities.formatDate(d, TZ, "dd/MM/yyyy HH:mm");
}

function simpanPOS(cart, metodeBayar) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch(e) { return {success: false, msg: "Server sibuk"}; }

  try {
    cart = cart || [];
    if (cart.length === 0) throw new Error("Keranjang kosong.");

    var ss = getActiveOmni_();
    var posSh = ensureSheetWithHeaders_(ss, POS_SHEET, POS_HEADERS);
    var posInfo = headerInfo_(posSh);

    var now = new Date();
    var tglStr = formatInputTglPOS(now);
    var tglKey = Utilities.formatDate(now, TZ, "yyyy-MM-dd");
    var noPesanan = "POS-" + now.getTime().toString().slice(-8);
    var user = userEmail_();
    var metode = metodeBayar || "Tunai";

    var normalizedCart = cart.map(function(c, idx) {
      var qty = toNumber_(c.qty);
      var harga = toNumber_(c.harga);
      var itemName = String(c.item || c.nama || c.Item_Name || "").trim();
      if (!itemName) throw new Error("Item POS baris " + (idx + 1) + " kosong.");
      if (qty <= 0) throw new Error("Qty POS harus lebih dari 0 untuk " + itemName + ".");
      if (harga < 0) throw new Error("Harga POS tidak valid untuk " + itemName + ".");
      return { item: itemName, qty: qty, harga: harga, total: qty * harga };
    });

    // v1.4: POS tidak masuk Omni_Order supaya tidak muncul sebagai PR/tarikan Gudang.
    // Sebagai pengganti, POS dicatat di Omni_POS_Sales dan langsung posting OUT ke Stock_Movement Gudang.
    var stockResult = OMNI_postPosToGudangStock_(normalizedCart, {
      noPos: noPesanan,
      tgl: now,
      tglKey: tglKey,
      metode: metode,
      user: user
    });

    var rows = [];
    normalizedCart.forEach(function(c, idx) {
      var item = stockResult.items[idx] || {};
      var row = new Array(posInfo.headers.length).fill("");
      setRowValue_(row, posInfo, "POS_ID", uuid_("POSL"));
      setRowValue_(row, posInfo, "Tanggal", tglStr);
      setRowValue_(row, posInfo, "Tanggal_Key", tglKey);
      setRowValue_(row, posInfo, "No_POS", noPesanan);
      setRowValue_(row, posInfo, "Metode_Bayar", metode);
      setRowValue_(row, posInfo, "Item_ID", item.Item_ID || "");
      setRowValue_(row, posInfo, "Item_Name", c.item);
      setRowValue_(row, posInfo, "Qty", c.qty);
      setRowValue_(row, posInfo, "Harga_Jual", c.harga);
      setRowValue_(row, posInfo, "Total", c.total);
      setRowValue_(row, posInfo, "Stock_Posted", stockResult.success ? "YES" : "NO");
      setRowValue_(row, posInfo, "Stock_Post_Result", stockResult.message || stockResult.inserted + " movement");
      setRowValue_(row, posInfo, "Source_Module", "OMNI_POS");
      setRowValue_(row, posInfo, "Created_At", nowText_());
      setRowValue_(row, posInfo, "Created_By", user);
      setRowValue_(row, posInfo, "Is_Deleted", false);
      rows.push(row);
    });

    appendRowsChunked_(posSh, rows, posInfo.headers.length);
    SpreadsheetApp.flush();
    OMNI_touchMutation_("simpanPOS");
    return {
      success: true,
      noPesanan: noPesanan,
      tgl: tglStr,
      stock: { success: true, inserted: stockResult.inserted || 0, gudangSpreadsheetId: stockResult.gudangSpreadsheetId || "" },
      msg: "POS tersimpan dan stok Gudang sudah terpotong."
    };
  } catch(e) {
    logError_("simpanPOS", e, { cartLength: cart ? cart.length : 0, metodeBayar: metodeBayar });
    return {success: false, msg: e.message};
  } finally {
    lock.releaseLock();
  }
}

function OMNI_postPosToGudangStock_(cart, ctx) {
  ctx = ctx || {};
  var whSs = OMNI_openGudangSpreadsheet_();
  var sh = ensureSheetWithHeaders_(whSs, "Stock_Movement", OMNI_STOCK_MOVEMENT_HEADERS);
  var info = headerInfo_(sh);
  var itemLookup = OMNI_buildStockItemLookup_();
  var balance = OMNI_readGudangStockBalance_(whSs);
  var existingKeys = OMNI_readGudangTxKeys_(whSs);
  var rows = [];
  var resolvedItems = [];
  var stockNeed = {};

  cart.forEach(function(c, idx) {
    var item = itemLookup.byName[normalize_(c.item)] || itemLookup.byDisplay[normalize_(c.item)];
    if (!item) throw new Error("Item POS tidak ditemukan di Master_Item: " + c.item);
    resolvedItems.push(item);
    stockNeed[item.Item_ID] = (stockNeed[item.Item_ID] || 0) + toNumber_(c.qty);
  });

  Object.keys(stockNeed).forEach(function(itemId) {
    var item = itemLookup.byId[itemId] || { Item_Name: itemId };
    var available = (balance[itemId] || 0) + (balance["NAME|" + normalize_(item.Item_Name)] || 0);
    if (stockNeed[itemId] > available) {
      throw new Error("Stok tidak cukup untuk POS: " + item.Item_Name + ". Stok tersedia " + available + ", diminta " + stockNeed[itemId] + ".");
    }
  });

  cart.forEach(function(c, idx) {
    var item = resolvedItems[idx];
    var qty = toNumber_(c.qty);
    var cost = OMNI_resolveGudangCost_(whSs, item, qty, ctx.tgl || new Date());
    var movementId = uuid_("SM");
    var sourceLine = "ITEM|" + item.Item_Name + "|" + (idx + 1);
    var txKey = ["OMNI_POS", ctx.noPos, item.Item_ID, idx + 1, qty].join("|");
    if (existingKeys[txKey]) throw new Error("POS stock movement duplikat ditolak: " + txKey);
    existingKeys[txKey] = true;

    var row = new Array(info.headers.length).fill("");
    setRowValue_(row, info, "Movement_ID", movementId);
    setRowValue_(row, info, "Tx_Key", txKey);
    setRowValue_(row, info, "Tanggal", ctx.tglKey || Utilities.formatDate(ctx.tgl || new Date(), TZ, "yyyy-MM-dd"));
    setRowValue_(row, info, "Source_Date", ctx.tglKey || Utilities.formatDate(ctx.tgl || new Date(), TZ, "yyyy-MM-dd"));
    setRowValue_(row, info, "Item_ID", item.Item_ID || "");
    setRowValue_(row, info, "Item_Name", item.Item_Name || c.item);
    setRowValue_(row, info, "Item_Category", item.Category || "");
    setRowValue_(row, info, "Item_Type", item.Item_Type || "");
    setRowValue_(row, info, "Unit", item.Unit || "");
    setRowValue_(row, info, "Warehouse_Code", "MAIN");
    setRowValue_(row, info, "Direction", "OUT");
    setRowValue_(row, info, "Movement_Type", "POS_OUT");
    setRowValue_(row, info, "Qty", qty);
    setRowValue_(row, info, "Unit_Cost", cost.Unit_Cost);
    setRowValue_(row, info, "Cost_Period", cost.Cost_Period);
    setRowValue_(row, info, "Cost_Status", cost.Cost_Status);
    setRowValue_(row, info, "Unit_Cost_Provisional", cost.Unit_Cost_Provisional);
    setRowValue_(row, info, "Value_Provisional", cost.Value_Provisional);
    setRowValue_(row, info, "Unit_Cost_Final", cost.Unit_Cost_Final);
    setRowValue_(row, info, "Value_Final", cost.Value_Final);
    setRowValue_(row, info, "Cost_Source", cost.Cost_Source);
    setRowValue_(row, info, "Cost_Synced_At", cost.Cost_Synced_At);
    setRowValue_(row, info, "Closed_At", cost.Closed_At);
    setRowValue_(row, info, "Closed_By", cost.Closed_By);
    setRowValue_(row, info, "Source_Module", "OMNI_POS");
    setRowValue_(row, info, "Source_ID", ctx.noPos || "");
    setRowValue_(row, info, "Source_Line_ID", sourceLine);
    setRowValue_(row, info, "Ref_No", ctx.noPos || "");
    setRowValue_(row, info, "Batch_ID", ctx.noPos || "");
    setRowValue_(row, info, "External_Ref", "POS|" + (ctx.metode || "Tunai"));
    setRowValue_(row, info, "Notes", "Penjualan POS Omni - " + (ctx.metode || "Tunai"));
    setRowValue_(row, info, "Status", "POSTED");
    setRowValue_(row, info, "Created_At", nowText_());
    setRowValue_(row, info, "Created_By", ctx.user || userEmail_());
    setRowValue_(row, info, "Is_Deleted", false);
    rows.push(row);
  });

  appendRowsChunked_(sh, rows, info.headers.length);
  return { success: true, inserted: rows.length, items: resolvedItems, gudangSpreadsheetId: whSs.getId(), message: rows.length + " POS_OUT" };
}

function OMNI_openGudangSpreadsheet_() {
  var master = openMaster_();
  var sh = master.getSheetByName("Master_Module");
  if (!sh) throw new Error("Master_Module tidak ditemukan. Tidak bisa membuka file Gudang.");
  var rows = ERP_readRows_(sh);
  var aliases = ["WH", "GUDANG", "WAREHOUSE", "INVENTORY", "STOCK", "MODUL GUDANG"];
  for (var i = 0; i < rows.length; i++) {
    var code = ERP_key_(rows[i].Module_Code || rows[i].Code || "");
    var name = ERP_key_(rows[i].Module_Name || rows[i].Name || rows[i].Nama || "");
    var status = rows[i].Status || "ACTIVE";
    if (!ERP_isActive_(status)) continue;
    var match = aliases.some(function(a) { var k = ERP_key_(a); return code === k || name.indexOf(k) !== -1; });
    if (!match) continue;
    var id = String(rows[i].Spreadsheet_ID || rows[i].SpreadsheetId || rows[i].Sheet_ID || "").trim();
    if (!id) {
      var url = String(rows[i].Spreadsheet_URL || rows[i].SpreadsheetUrl || rows[i].URL || "").trim();
      var m = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
      if (m) id = m[1];
    }
    if (id) return SpreadsheetApp.openById(id);
  }
  throw new Error("Spreadsheet modul Gudang belum ditemukan di Master_Module. Pastikan kode WH/GUDANG punya Spreadsheet_ID.");
}

function OMNI_buildStockItemLookup_() {
  var t = tableCompat_(openMaster_(), "Master_Item");
  if (!t) throw new Error("Master_Item tidak ditemukan.");
  var cId = t.c(["Item_ID", "ID", "Kode Item", "Kode_Barang"], 0);
  var cName = t.c(["Item_Name", "Nama Item", "Nama", "Item", "Produk"], 1);
  var cCat = t.c(["Category", "Kategori"], -1);
  var cSub = t.c(["Subcategory", "Sub_Category", "Sub Category", "Sub Kategori", "Sub-Kategori"], -1);
  var cType = t.c(["Item_Type", "Type", "Jenis"], -1);
  var cUnit = t.c(["Unit", "Satuan"], -1);
  var cCost = t.c(["Default_Cost", "HPP", "HPP_Rata_Rata", "Average_Cost", "Harga Pokok", "Harga_Beli"], -1);
  var out = { byId: {}, byName: {}, byDisplay: {} };
  t.rows.forEach(function(r) {
    var id = String(r[cId] || "").trim();
    var name = String(r[cName] || "").trim();
    if (!id && !name) return;
    var item = {
      Item_ID: id || name,
      Item_Name: name || id,
      Category: cCat !== -1 ? String(r[cCat] || "").trim() : "",
      Subcategory: cSub !== -1 ? String(r[cSub] || "").trim() : "",
      Item_Type: cType !== -1 ? String(r[cType] || "").trim() : "",
      Unit: cUnit !== -1 ? String(r[cUnit] || "").trim() : "",
      Default_Cost: cCost !== -1 ? toNumber_(r[cCost]) : 0
    };
    out.byId[item.Item_ID] = item;
    out.byName[normalize_(item.Item_Name)] = item;
    if (item.Subcategory) out.byDisplay[normalize_(item.Subcategory)] = item;
  });
  return out;
}

function OMNI_readGudangTxKeys_(whSs) {
  var sh = whSs.getSheetByName("Stock_Movement");
  var out = {};
  if (!sh || sh.getLastRow() < 2) return out;
  var info = headerInfo_(sh);
  var cKey = col_(info, "Tx_Key", -1);
  var cMov = col_(info, "Movement_ID", -1);
  var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  vals.forEach(function(r) {
    if (cKey !== -1 && r[cKey]) out[String(r[cKey])] = true;
    if (cMov !== -1 && r[cMov]) out["MOVEMENT_ID|" + String(r[cMov])] = true;
  });
  return out;
}

function OMNI_readGudangStockBalance_(whSs) {
  var sh = whSs.getSheetByName("Stock_Movement");
  var out = {};
  if (!sh || sh.getLastRow() < 2) return out;
  var info = headerInfo_(sh);
  var cId = col_(info, "Item_ID", -1);
  var cName = col_(info, "Item_Name", -1);
  var cDir = col_(info, "Direction", -1);
  var cQty = col_(info, "Qty", -1);
  var cDel = col_(info, "Is_Deleted", -1);
  var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  vals.forEach(function(r) {
    var del = cDel !== -1 ? String(r[cDel] || "").toUpperCase() : "";
    if (["TRUE", "YES", "1", "DELETED"].indexOf(del) !== -1) return;
    var id = cId !== -1 ? String(r[cId] || "").trim() : "";
    var name = cName !== -1 ? String(r[cName] || "").trim() : "";
    if (!id && !name) return;
    var key = id || ("NAME|" + normalize_(name));
    var dir = cDir !== -1 ? String(r[cDir] || "").toUpperCase().trim() : "";
    var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
    if (dir === "IN") out[key] = (out[key] || 0) + qty;
    if (dir === "OUT") out[key] = (out[key] || 0) - qty;
  });
  return out;
}

function OMNI_resolveGudangCost_(whSs, item, qty, dateObj) {
  qty = toNumber_(qty);
  var period = Utilities.formatDate(dateObj || new Date(), TZ, "yyyy-MM");
  var row = OMNI_findCostPeriodRow_(whSs, item, period);
  var status = row ? String(row.Cost_Status || "PROVISIONAL").toUpperCase() : "PROVISIONAL";
  var prov = row ? toNumber_(row.Unit_Cost_Provisional) : 0;
  var fin = row ? toNumber_(row.Unit_Cost_Final) : 0;
  if (!prov && !fin && item && item.Default_Cost) prov = toNumber_(item.Default_Cost);
  var unit = status === "FINAL" && fin ? fin : (prov || fin || 0);
  return {
    Cost_Period: period,
    Cost_Status: status === "FINAL" ? "FINAL" : "PROVISIONAL",
    Unit_Cost: unit,
    Unit_Cost_Provisional: status === "FINAL" ? (prov || fin || unit) : unit,
    Value_Provisional: qty * (status === "FINAL" ? (prov || fin || unit) : unit),
    Unit_Cost_Final: status === "FINAL" ? unit : "",
    Value_Final: status === "FINAL" ? qty * unit : "",
    Cost_Source: row ? ((row.Source_Module || "STOCK_COST_PERIOD") + (row.Source_ID ? "|" + row.Source_ID : "")) : "MASTER_ITEM",
    Cost_Synced_At: row ? (row.Synced_At || nowText_()) : nowText_(),
    Closed_At: status === "FINAL" ? (row.Closed_At || "") : "",
    Closed_By: status === "FINAL" ? (row.Closed_By || "") : ""
  };
}

function OMNI_findCostPeriodRow_(whSs, item, period) {
  var sh = whSs.getSheetByName("Stock_Cost_Period");
  if (!sh || sh.getLastRow() < 2) return null;
  var info = headerInfo_(sh);
  var cPeriod = col_(info, "Period", -1);
  var cId = col_(info, "Item_ID", -1);
  var cName = col_(info, "Item_Name", -1);
  var cProv = col_(info, "Unit_Cost_Provisional", -1);
  var cFinal = col_(info, "Unit_Cost_Final", -1);
  var cStatus = col_(info, "Cost_Status", -1);
  var cSrc = col_(info, "Source_Module", -1);
  var cSrcId = col_(info, "Source_ID", -1);
  var cSync = col_(info, "Synced_At", -1);
  var cClosedAt = col_(info, "Closed_At", -1);
  var cClosedBy = col_(info, "Closed_By", -1);
  var cDel = col_(info, "Is_Deleted", -1);
  var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var best = null;
  vals.forEach(function(r) {
    var del = cDel !== -1 ? String(r[cDel] || "").toUpperCase() : "";
    if (["TRUE", "YES", "1", "DELETED"].indexOf(del) !== -1) return;
    if (cPeriod !== -1 && String(r[cPeriod] || "").trim() !== period) return;
    var id = cId !== -1 ? String(r[cId] || "").trim() : "";
    var name = cName !== -1 ? String(r[cName] || "").trim() : "";
    var match = (item.Item_ID && id && id === item.Item_ID) || (item.Item_Name && normalize_(name) === normalize_(item.Item_Name));
    if (!match) return;
    var obj = {
      Unit_Cost_Provisional: cProv !== -1 ? r[cProv] : 0,
      Unit_Cost_Final: cFinal !== -1 ? r[cFinal] : 0,
      Cost_Status: cStatus !== -1 ? r[cStatus] : "PROVISIONAL",
      Source_Module: cSrc !== -1 ? r[cSrc] : "STOCK_COST_PERIOD",
      Source_ID: cSrcId !== -1 ? r[cSrcId] : "",
      Synced_At: cSync !== -1 ? r[cSync] : "",
      Closed_At: cClosedAt !== -1 ? r[cClosedAt] : "",
      Closed_By: cClosedBy !== -1 ? r[cClosedBy] : ""
    };
    if (!best || String(obj.Cost_Status || "").toUpperCase() === "FINAL") best = obj;
  });
  return best;
}

// =========================== RETUR ===========================

function prosesImportRetur(payload) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success: false, error: "Server sibuk" }; }

  try {
    payload = payload || [];
    if (payload.length === 0) return { success: false, error: "Data kosong." };

    var ss = getActiveOmni_();
    var sh = ensureSheetWithHeaders_(ss, RETUR_SHEET, RETUR_HEADERS);
    var t = readTable_(ss, RETUR_SHEET, RETUR_HEADERS);
    var info = t.info;
    var width = info.headers.length;
    var skuMap = getSkuMap_();
    var now = nowText_();
    var user = userEmail_();
    var existing = {};

    var cNo = col_(info, "No Pesanan");
    var cSku = col_(info, ["SKU BigSeller", "SKU"]);
    t.rows.forEach(function(r) {
      var no = cNo !== -1 && r[cNo] ? String(r[cNo]).trim() : "";
      var sku = cSku !== -1 && r[cSku] ? String(r[cSku]).trim() : "";
      if (no && sku) existing[no + "|" + sku] = true;
    });

    var rowsToInsert = [];
    var unmapped = [];

    payload.forEach(function(p) {
      var no = String(p.no || "").trim();
      var productName = firstNonEmpty_(p.productName, p.Marketplace_Product_Name, p.itemName, p.nama);
      var variation = firstNonEmpty_(p.variation, p.Marketplace_Variation, p.Variation, p.Variasi, p["Nama Variasi"]);
      var sku = marketplaceSkuFallback_(p.sku, productName, variation, no);
      if (!no || !sku) return;
      var key = no + "|" + sku;
      if (existing[key]) return;

      var mapData = resolveSkuMapping_(sku, productName, variation, skuMap);
      if (mapData.item === "UNMAPPED" && unmapped.indexOf(sku) === -1) unmapped.push(sku);

      var qtyMarket = toNumber_(p.qty) || 1;
      var conversion = toNumber_(mapData.isi) || 1;
      var qtyFisik = qtyMarket * conversion;

      var row = new Array(width).fill("");
      setRowValue_(row, info, "Tgl Pesan", p.wktPesan || "");
      setRowValue_(row, info, "Tgl Sampai (RTS)", p.wktSampai || "");
      setRowValue_(row, info, "No Pesanan", no);
      setRowValue_(row, info, "No Resi", p.resi || "-");
      setRowValue_(row, info, "SKU BigSeller", sku);
      setRowValue_(row, info, "Item Gudang (Mapped)", mapData.item);
      setRowValue_(row, info, "QTY Marketplace", qtyMarket);
      setRowValue_(row, info, "Conversion Qty", conversion);
      setRowValue_(row, info, "QTY Retur Fisik", qtyFisik);
      setRowValue_(row, info, "Status Marketplace", p.status || "");
      setRowValue_(row, info, "Status Scan AppSheet", "REFERENSI_MARKETPLACE");
      setRowValue_(row, info, "Marketplace_Product_Name", productName);
      setRowValue_(row, info, "Marketplace_Variation", variation);
      setRowValue_(row, info, "QC_Source", "RETUR_QC_MODULE");
      setRowValue_(row, info, "Gudang_Action", "NO_DIRECT_STOCK_ACTION");
      setRowValue_(row, info, "Finance_Status", "REFERENCE_ONLY");
      setRowValue_(row, info, "Notes", "Retur marketplace hanya referensi Omni. Barang siap jual masuk Gudang via modul Retur QC.");
      setRowValue_(row, info, "Updated_At", now);
      setRowValue_(row, info, "Updated_By", user);
      rowsToInsert.push(row);
      existing[key] = true;
    });

    appendRowsChunked_(sh, rowsToInsert, width);
    SpreadsheetApp.flush();
    var affectedOrderNos = payload.map(function(p){ return String((p && p.no) || '').trim(); }).filter(function(x){ return !!x; });
    var summaryGroups = OMNI_collectOrderGroupsForOrderNumbers_(affectedOrderNos);
    var summaryResult = OMNI_rebuildOrderDailySummary_(summaryGroups);
    OMNI_touchMutation_("prosesImportRetur");
    return { success: true, insert: rowsToInsert.length, total: payload.length, unmapped: unmapped.sort(), dailySummary: summaryResult };
  } catch(e) {
    logError_("prosesImportRetur", e, { rows: payload ? payload.length : 0 });
    return { success: false, error: e.message };
  } finally {
    lock.releaseLock();
  }
}

function getReturOrderSet_() {
  var set = {};
  readReturTables_(false).forEach(function(t) {
    var cNo = col_(t.info, "No Pesanan");
    t.rows.forEach(function(r) {
      var no = cNo !== -1 && r[cNo] ? String(r[cNo]).trim() : "";
      if (no) set[no] = true;
    });
  });
  return set;
}

function readReturTables_(createMain) {
  // v1.5.1: Runtime Omni hanya memakai Omni_Retur.
  // Data_Retur_AppSheet sengaja tidak dibaca lagi agar aman dihapus setelah migrasi.
  var ss = getActiveOmni_();
  var tables = [];
  var main = readTable_(ss, RETUR_SHEET, RETUR_HEADERS, { noCreate: !createMain });
  if (main && main.sheet) tables.push(main);
  return tables;
}

function MIGRATE_DataReturAppSheet_to_OmniRetur() {
  // Jalankan sekali dari Apps Script editor kalau masih ada data lama di Data_Retur_AppSheet.
  // Setelah hasilnya aman, sheet Data_Retur_AppSheet boleh dihapus manual.
  var __auth = OMNI_requirePassportOrEditor_(arguments, 'MIGRATE_DataReturAppSheet_to_OmniRetur');

  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success: false, error: 'Server sibuk.' }; }

  try {
    var ss = getActiveOmni_();
    var legacySheet = ss.getSheetByName(RETUR_LEGACY_SHEET);
    if (!legacySheet) {
      return { success: true, migrated: 0, skipped: 0, message: RETUR_LEGACY_SHEET + ' tidak ada. Runtime sudah memakai ' + RETUR_SHEET + '.' };
    }

    var targetSheet = ensureSheetWithHeaders_(ss, RETUR_SHEET, RETUR_HEADERS);
    var target = readTable_(ss, RETUR_SHEET, RETUR_HEADERS);
    var legacy = readTable_(ss, RETUR_LEGACY_SHEET, null, { noCreate: true });
    if (!legacy || !legacy.sheet || !legacy.rows.length) {
      return { success: true, migrated: 0, skipped: 0, message: RETUR_LEGACY_SHEET + ' kosong. Boleh dihapus kalau tidak diperlukan.' };
    }

    var targetInfo = target.info;
    var targetWidth = targetInfo.headers.length;
    var existing = {};
    function returKey_(row, info) {
      var no = String(getRowValueAny_(row, info, ['No Pesanan']) || '').trim();
      var sku = String(getRowValueAny_(row, info, ['SKU BigSeller', 'SKU']) || '').trim();
      var resi = String(getRowValueAny_(row, info, ['No Resi']) || '').trim();
      return [no, sku, resi].join('|');
    }

    target.rows.forEach(function(r) {
      var key = returKey_(r, targetInfo);
      if (key.replace(/\|/g, '')) existing[key] = true;
    });

    var now = nowText_();
    var user = userEmail_();
    var rowsToInsert = [];
    var skipped = 0;

    legacy.rows.forEach(function(src) {
      var key = returKey_(src, legacy.info);
      if (!key.replace(/\|/g, '') || existing[key]) { skipped++; return; }

      var row = new Array(targetWidth).fill('');
      targetInfo.headers.forEach(function(h) {
        var v = getRowValueAny_(src, legacy.info, [h]);
        if (v !== '') setRowValue_(row, targetInfo, h, v);
      });

      // Fallback alias untuk schema lama.
      setRowIfEmpty_(row, targetInfo, 'Tgl Pesan', getRowValueAny_(src, legacy.info, ['Tgl Pesan', 'Tanggal Pesan', 'Tanggal', 'Waktu Pemesanan']));
      setRowIfEmpty_(row, targetInfo, 'Tgl Sampai (RTS)', getRowValueAny_(src, legacy.info, ['Tgl Sampai (RTS)', 'Tanggal Sampai', 'Waktu Sampai Gudang', 'Tanggal Retur']));
      setRowIfEmpty_(row, targetInfo, 'No Pesanan', getRowValueAny_(src, legacy.info, ['No Pesanan', 'Nomor Pesanan', 'Order ID']));
      setRowIfEmpty_(row, targetInfo, 'No Resi', getRowValueAny_(src, legacy.info, ['No Resi', 'Nomor Resi', 'Resi']));
      setRowIfEmpty_(row, targetInfo, 'SKU BigSeller', getRowValueAny_(src, legacy.info, ['SKU BigSeller', 'SKU', 'SKU Gudang', 'Marketplace_SKU']));
      setRowIfEmpty_(row, targetInfo, 'Item Gudang (Mapped)', getRowValueAny_(src, legacy.info, ['Item Gudang (Mapped)', 'Item Gudang', 'Internal_Item_Name']));
      setRowIfEmpty_(row, targetInfo, 'QTY Marketplace', getRowValueAny_(src, legacy.info, ['QTY Marketplace', 'Qty Marketplace', 'Jumlah', 'Qty']));
      setRowIfEmpty_(row, targetInfo, 'Conversion Qty', getRowValueAny_(src, legacy.info, ['Conversion Qty', 'Conversion_Qty', 'Isi Paket']));
      setRowIfEmpty_(row, targetInfo, 'QTY Retur Fisik', getRowValueAny_(src, legacy.info, ['QTY Retur Fisik', 'Qty Retur Fisik', 'Qty Fisik', 'Qty']));
      setRowIfEmpty_(row, targetInfo, 'Status Marketplace', getRowValueAny_(src, legacy.info, ['Status Marketplace', 'Status Pesanan', 'Status Purna Jual', 'Status']));
      setRowIfEmpty_(row, targetInfo, 'Status Scan AppSheet', 'REFERENSI_MARKETPLACE');
      setRowIfEmpty_(row, targetInfo, 'QC_Source', 'RETUR_QC_MODULE');
      setRowIfEmpty_(row, targetInfo, 'Gudang_Action', 'NO_DIRECT_STOCK_ACTION');
      setRowIfEmpty_(row, targetInfo, 'Finance_Status', 'REFERENCE_ONLY');
      setRowIfEmpty_(row, targetInfo, 'Notes', 'Migrasi dari Data_Retur_AppSheet ke Omni_Retur. Retur hanya referensi marketplace; stok siap jual masuk via Retur QC -> Gudang.');
      setRowValue_(row, targetInfo, 'Updated_At', now);
      setRowValue_(row, targetInfo, 'Updated_By', user);

      rowsToInsert.push(row);
      existing[key] = true;
    });

    var migrated = appendRowsChunked_(targetSheet, rowsToInsert, targetWidth);
    SpreadsheetApp.flush();
    var summaryResult = null;
    if (migrated) {
      summaryResult = OMNI_rebuildOrderDailySummary_(null);
      OMNI_touchMutation_('MIGRATE_DataReturAppSheet_to_OmniRetur');
    }
    return { success: true, migrated: migrated, skipped: skipped, source: RETUR_LEGACY_SHEET, target: RETUR_SHEET, dailySummary: summaryResult, message: 'Migrasi selesai. Setelah dicek, Data_Retur_AppSheet boleh dihapus manual.' };
  } catch(e) {
    logError_('MIGRATE_DataReturAppSheet_to_OmniRetur', e, {});
    return { success: false, error: e.message };
  } finally {
    lock.releaseLock();
  }
}

function getRowValueAny_(row, info, headerNames) {
  if (!info) return '';
  var c = col_(info, headerNames, -1);
  return c !== -1 ? (row[c] === undefined || row[c] === null ? '' : row[c]) : '';
}

function setRowIfEmpty_(row, info, headerName, value) {
  if (value === undefined || value === null || value === '') return;
  var c = col_(info, headerName, -1);
  if (c === -1) return;
  if (row[c] === undefined || row[c] === null || row[c] === '') row[c] = value;
}

// =========================== SETTLEMENT / KEUANGAN ===========================

function prosesImportKeuangan(pesanan, penyesuaian) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);

  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success: false, error: "Server sibuk, coba lagi." }; }

  try {
    var importId = uuid_("SET");
    var oldSettlementGroups = OMNI_collectOldSettlementGroupsForPayload_(pesanan || []);
    var upserted = upsertSettlement_(pesanan || [], importId);
    var statusSync = syncSettlementStatusToOrders_(pesanan || [], importId);
    var insertedPenyesuaian = upsertAdjustment_(penyesuaian || [], importId);
    SpreadsheetApp.flush();
    var settlementGroups = OMNI_mergeGroupFilters_(oldSettlementGroups, OMNI_collectSettlementGroupsFromPayload_(pesanan || []));
    var orderGroups = OMNI_collectOrderGroupsForOrderKeys_(pesanan || []);
    var settlementSummary = OMNI_rebuildSettlementDailySummary_(settlementGroups);
    var orderSummary = OMNI_rebuildOrderDailySummary_(orderGroups);
    OMNI_touchMutation_("prosesImportKeuangan");
    return { success: true, updated: upserted.updated + upserted.inserted, settlementStatusUpdated: statusSync.updated || 0, inserted: insertedPenyesuaian.inserted, updatedPeny: insertedPenyesuaian.updated, dailySummary: { order:orderSummary, settlement:settlementSummary } };
  } catch(e) {
    logError_("prosesImportKeuangan", e, { pesanan: pesanan ? pesanan.length : 0, penyesuaian: penyesuaian ? penyesuaian.length : 0 });
    return { success: false, error: e.message };
  } finally {
    lock.releaseLock();
  }
}

function upsertSettlement_(pesanan, importId) {
  if (!pesanan || pesanan.length === 0) return { inserted: 0, updated: 0 };

  var ss = getActiveOmni_();
  var sh = ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  OMNI_setPlainTextColumnByHeader_(sh, ["Tgl Pencairan Key"]);
  var t = readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  var info = t.info;
  var width = info.headers.length;
  var cToko = col_(info, "Toko");
  var cNo = col_(info, "No Pesanan");
  var map = {};

  t.rows.forEach(function(r, idx) {
    var toko = cToko !== -1 && r[cToko] ? String(r[cToko]).trim() : "";
    var no = cNo !== -1 && r[cNo] ? String(r[cNo]).trim() : "";
    if (toko && no) map[toko + "|" + no] = { rowNumber: idx + 2, row: r };
  });

  var insertRows = [];
  var updateRows = [];
  var now = nowText_();
  var user = userEmail_();

  pesanan.forEach(function(p) {
    var toko = String(p.toko || "").trim();
    var no = String(p.no || "").trim();
    if (!toko || !no) return;
    var existing = map[toko + "|" + no];
    var row = existing ? existing.row.slice(0, width) : new Array(width).fill("");
    while (row.length < width) row.push("");

    var settlementDateRaw = p.tglCair || p.tgl || "";
    // Settlement source yang dikirim client sudah dinormalisasi sebagai dd/MM/yyyy.
    // Jangan mendahulukan tglCairKey dari client karena key itu bisa sudah tertukar DMY/MDY.
    // Server selalu membentuk ulang key dari tanggal sumber; key client hanya fallback bila raw kosong.
    var settlementDateKey = OMNI_settlementDateKeyFromPayload_(p);
    setRowValue_(row, info, "Toko", toko);
    setRowValue_(row, info, "No Pesanan", no);
    setRowValue_(row, info, "Tgl Pencairan", settlementDateRaw || settlementDateKey);
    setRowValue_(row, info, "Tgl Pencairan Key", settlementDateKey);
    setRowValue_(row, info, "Pendapatan Bersih", toNumber_(p.bersih));
    setRowValue_(row, info, "Biaya Admin", toNumber_(p.komisiPlat));
    setRowValue_(row, info, "Biaya Layanan", toNumber_(p.biayaLayanan));
    setRowValue_(row, info, "Komisi Affiliate", toNumber_(p.komisiAff));
    setRowValue_(row, info, "Ongkir Penjual", toNumber_(p.ongkirPenjual));
    setRowValue_(row, info, "Import_ID", importId);
    setRowValue_(row, info, "Updated_At", now);
    setRowValue_(row, info, "Updated_By", user);

    if (existing) updateRows.push({ rowNumber: existing.rowNumber, row: row });
    else insertRows.push(row);
  });

  return {
    inserted: appendRowsChunked_(sh, insertRows, width),
    updated: writeChangedRows_(sh, updateRows, width)
  };
}

function upsertAdjustment_(penyesuaian, importId) {
  if (!penyesuaian || penyesuaian.length === 0) return { inserted: 0, updated: 0 };

  var ss = getActiveOmni_();
  var sh = ensureSheetWithHeaders_(ss, ADJUSTMENT_SHEET, ADJUSTMENT_HEADERS);
  ensureSheetWithHeaders_(ss, POS_SHEET, POS_HEADERS);
  var t = readTable_(ss, ADJUSTMENT_SHEET, ADJUSTMENT_HEADERS);
  var info = t.info;
  var width = info.headers.length;
  var cId = col_(info, "Nomor Penyesuaian");
  var map = {};

  t.rows.forEach(function(r, idx) {
    var id = cId !== -1 && r[cId] ? String(r[cId]).trim() : "";
    if (id) map[id] = { rowNumber: idx + 2, row: r };
  });

  var insertRows = [];
  var updateRows = [];
  var now = nowText_();
  var user = userEmail_();

  penyesuaian.forEach(function(py) {
    var id = String(py.idPenyesuaian || "").trim();
    if (!id) return;
    var existing = map[id];
    var row = existing ? existing.row.slice(0, width) : new Array(width).fill("");
    while (row.length < width) row.push("");

    setRowValue_(row, info, "Tgl Penyesuaian", py.tgl || "");
    setRowValue_(row, info, "Toko", py.toko || "");
    setRowValue_(row, info, "ID Pesanan Terkait", py.idTerkait || "");
    setRowValue_(row, info, "Jenis Transaksi", py.jenis || "");
    setRowValue_(row, info, "Nomor Penyesuaian", id);
    setRowValue_(row, info, "Nilai Penyesuaian (Rp)", toNumber_(py.nilai));
    setRowValue_(row, info, "Import_ID", importId);
    setRowValue_(row, info, "Updated_At", now);
    setRowValue_(row, info, "Updated_By", user);

    if (existing) updateRows.push({ rowNumber: existing.rowNumber, row: row });
    else insertRows.push(row);
  });

  return {
    inserted: appendRowsChunked_(sh, insertRows, width),
    updated: writeChangedRows_(sh, updateRows, width)
  };
}

function getSettlementMap_() {
  var t = readTable_(getActiveOmni_(), SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  var map = {};
  if (!t.sheet) return map;

  var cToko = col_(t.info, "Toko");
  var cNo = col_(t.info, "No Pesanan");
  var cTgl = col_(t.info, "Tgl Pencairan");
  var cBersih = col_(t.info, "Pendapatan Bersih");
  var cAdmin = col_(t.info, "Biaya Admin");
  var cLayanan = col_(t.info, "Biaya Layanan");
  var cAff = col_(t.info, "Komisi Affiliate");
  var cOngkir = col_(t.info, "Ongkir Penjual");

  t.rows.forEach(function(r) {
    var toko = cToko !== -1 && r[cToko] ? String(r[cToko]).trim() : "";
    var no = cNo !== -1 && r[cNo] ? String(r[cNo]).trim() : "";
    if (!toko || !no) return;
    map[toko + "|" + no] = {
      tgl: cTgl !== -1 ? r[cTgl] : "",
      bersih: cBersih !== -1 ? toNumber_(r[cBersih]) : 0,
      admin: cAdmin !== -1 ? toNumber_(r[cAdmin]) : 0,
      layanan: cLayanan !== -1 ? toNumber_(r[cLayanan]) : 0,
      affiliate: cAff !== -1 ? toNumber_(r[cAff]) : 0,
      ongkir: cOngkir !== -1 ? toNumber_(r[cOngkir]) : 0
    };
  });
  return map;
}


function syncSettlementStatusToOrders_(pesanan, importId) {
  if (!pesanan || pesanan.length === 0) return { updated: 0 };

  var wanted = {};
  pesanan.forEach(function(p) {
    var toko = String(p.toko || "").trim();
    var no = String(p.no || "").trim();
    if (toko && no) wanted[toko + "|" + no] = { tglCair: p.tglCair || "", importId: importId || "" };
  });
  if (Object.keys(wanted).length === 0) return { updated: 0 };

  var t = readTable_(getActiveOmni_(), OMNI_SHEET, OMNI_HEADERS);
  if (!t.sheet || t.fullData.length <= 1) return { updated: 0 };

  var info = t.info;
  var cToko = col_(info, "Toko", -1);
  var cNo = col_(info, "No Pesanan", -1);
  var cSet = col_(info, "Settlement Status", -1);
  var cUpdated = col_(info, "Updated_At", -1);
  var cBy = col_(info, "Updated_By", -1);
  if (cToko === -1 || cNo === -1 || cSet === -1) return { updated: 0 };

  var updates = [];
  var now = nowText_();
  var user = userEmail_();
  t.rows.forEach(function(r, idx) {
    var toko = cToko !== -1 && r[cToko] ? String(r[cToko]).trim() : "";
    var no = cNo !== -1 && r[cNo] ? String(r[cNo]).trim() : "";
    var hit = wanted[toko + "|" + no];
    if (!hit) return;
    var row = r.slice(0, info.headers.length);
    while (row.length < info.headers.length) row.push("");
    row[cSet] = "SUDAH_CAIR" + (hit.tglCair ? " | " + hit.tglCair : "");
    if (cUpdated !== -1) row[cUpdated] = now;
    if (cBy !== -1) row[cBy] = user;
    updates.push({ rowNumber: idx + 2, row: row });
  });

  return { updated: writeChangedRows_(t.sheet, updates, info.headers.length) };
}

// =========================== FINANCE HANDOFF + RETUR ALIGNMENT v1.5 ===========================

function getOmniFinanceBundle(period, emailOp, pasporOp) {
  var auth = OMNI_requirePassportFinance_(emailOp, pasporOp);
  var sales = getOmniSalesForFinance(period, emailOp, pasporOp);
  var pos = getOmniPosSalesForFinance(period, emailOp, pasporOp);
  var settlements = getOmniSettlementForFinance(period, emailOp, pasporOp);
  var adjustments = getOmniAdjustmentForFinance(period, emailOp, pasporOp);
  var returns = getOmniReturnForFinance(period, emailOp, pasporOp);

  var summary = {
    period: financeRange_(period).period,
    marketplaceGrossValid: sales.summary.grossValid || 0,
    marketplaceGrossCancelled: sales.summary.grossCancelled || 0,
    posGross: pos.summary.gross || 0,
    settlementNet: settlements.summary.net || 0,
    settlementFees: settlements.summary.fees || 0,
    adjustments: adjustments.summary.total || 0,
    returnQty: returns.summary.qty || 0,
    rows: { sales: sales.rows.length, pos: pos.rows.length, settlements: settlements.rows.length, adjustments: adjustments.rows.length, returns: returns.rows.length }
  };

  return { success: true, generatedAt: nowText_(), generatedBy: auth.email || "", period: summary.period, summary: summary, sales: sales.rows, pos: pos.rows, settlements: settlements.rows, adjustments: adjustments.rows, returns: returns.rows };
}

function getOmniSalesForFinance(period, emailOp, pasporOp) {
  OMNI_requirePassportFinance_(emailOp, pasporOp);
  var range = financeRange_(period);
  var ss = getActiveOmni_();
  var t = readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
  var out = [];
  var summary = { grossValid: 0, grossCancelled: 0, qtyValid: 0, qtyCancelled: 0 };
  if (!t.sheet) return { success: true, period: range.period, rows: out, summary: summary };

  var info = t.info;
  var cTgl = col_(info, ["Tanggal"], -1);
  var cToko = col_(info, ["Toko"], -1);
  var cNo = col_(info, ["No Pesanan"], -1);
  var cStatus = col_(info, ["Status"], -1);
  var cSku = col_(info, ["SKU"], -1);
  var cItem = col_(info, ["Item Gudang"], -1);
  var cVar = col_(info, ["Marketplace_Variation", "Marketplace Variation"], -1);
  var cProduct = col_(info, ["Marketplace Item Name", "Marketplace_Product_Name"], -1);
  var cQty = col_(info, ["Qty"], -1);
  var cHarga = col_(info, ["Harga Jual"], -1);
  var cTotal = col_(info, ["Total"], -1);
  var cResi = col_(info, ["No Resi"], -1);
  var cSet = col_(info, ["Settlement Status"], -1);
  var cDel = col_(info, ["Is_Deleted"], -1);

  t.rows.forEach(function(r) {
    if (isDeletedRow_(r, cDel)) return;
    var ms = cTgl !== -1 ? parseDateMs_(r[cTgl]) : 0;
    if (!ms || ms < range.start || ms > range.end) return;
    var status = cStatus !== -1 ? String(r[cStatus] || "") : "";
    var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
    var total = cTotal !== -1 ? toNumber_(r[cTotal]) : 0;
    var canceled = isCanceledStatus_(status);
    if (canceled) { summary.grossCancelled += total; summary.qtyCancelled += qty; }
    else { summary.grossValid += total; summary.qtyValid += qty; }

    out.push({
      Source_Module: "OMNI",
      Source_ID: cNo !== -1 ? String(r[cNo] || "") : "",
      Source_Line_ID: compactJoinKey_([cSku !== -1 ? r[cSku] : "", cVar !== -1 ? r[cVar] : ""]),
      Period: range.period,
      Date: cTgl !== -1 ? r[cTgl] : "",
      Store: cToko !== -1 ? r[cToko] : "",
      No_Pesanan: cNo !== -1 ? r[cNo] : "",
      Status: status,
      SKU: cSku !== -1 ? r[cSku] : "",
      Marketplace_Product_Name: cProduct !== -1 ? r[cProduct] : "",
      Marketplace_Variation: cVar !== -1 ? r[cVar] : "",
      Item_Gudang: cItem !== -1 ? r[cItem] : "",
      Qty: qty,
      Harga_Jual: cHarga !== -1 ? toNumber_(r[cHarga]) : 0,
      Gross_Sales: total,
      No_Resi: cResi !== -1 ? r[cResi] : "",
      Settlement_Status: cSet !== -1 ? r[cSet] : "",
      Is_Cancelled: canceled
    });
  });

  return { success: true, period: range.period, rows: out, summary: summary };
}

function getOmniPosSalesForFinance(period, emailOp, pasporOp) {
  OMNI_requirePassportFinance_(emailOp, pasporOp);
  var range = financeRange_(period);
  var t = readTable_(getActiveOmni_(), POS_SHEET, POS_HEADERS, { noCreate: true });
  var rows = [];
  var summary = { gross: 0, qty: 0 };
  if (!t.sheet) return { success: true, period: range.period, rows: rows, summary: summary };

  var info = t.info;
  var cTgl = col_(info, ["Tanggal"], -1);
  var cNo = col_(info, ["No_POS"], -1);
  var cMetode = col_(info, ["Metode_Bayar"], -1);
  var cItemId = col_(info, ["Item_ID"], -1);
  var cItem = col_(info, ["Item_Name"], -1);
  var cQty = col_(info, ["Qty"], -1);
  var cHarga = col_(info, ["Harga_Jual"], -1);
  var cTotal = col_(info, ["Total"], -1);
  var cPosted = col_(info, ["Stock_Posted"], -1);
  var cDel = col_(info, ["Is_Deleted"], -1);

  t.rows.forEach(function(r) {
    if (isDeletedRow_(r, cDel)) return;
    var ms = cTgl !== -1 ? parseDateMs_(r[cTgl]) : 0;
    if (!ms || ms < range.start || ms > range.end) return;
    var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
    var total = cTotal !== -1 ? toNumber_(r[cTotal]) : 0;
    summary.gross += total;
    summary.qty += qty;
    rows.push({ Source_Module: "OMNI_POS", Source_ID: cNo !== -1 ? r[cNo] : "", Period: range.period, Date: cTgl !== -1 ? r[cTgl] : "", No_POS: cNo !== -1 ? r[cNo] : "", Metode_Bayar: cMetode !== -1 ? r[cMetode] : "", Item_ID: cItemId !== -1 ? r[cItemId] : "", Item_Name: cItem !== -1 ? r[cItem] : "", Qty: qty, Harga_Jual: cHarga !== -1 ? toNumber_(r[cHarga]) : 0, Gross_Sales: total, Stock_Posted: cPosted !== -1 ? r[cPosted] : "" });
  });
  return { success: true, period: range.period, rows: rows, summary: summary };
}

function getOmniSettlementForFinance(period, emailOp, pasporOp) {
  OMNI_requirePassportFinance_(emailOp, pasporOp);
  var range = financeRange_(period);
  var t = readTable_(getActiveOmni_(), SETTLEMENT_SHEET, SETTLEMENT_HEADERS, { noCreate: true });
  var rows = [];
  var summary = { net: 0, fees: 0, admin: 0, layanan: 0, affiliate: 0, ongkir: 0 };
  if (!t.sheet) return { success: true, period: range.period, rows: rows, summary: summary };

  var info = t.info;
  var cTgl = col_(info, ["Tgl Pencairan"], -1);
  var cToko = col_(info, ["Toko"], -1);
  var cNo = col_(info, ["No Pesanan"], -1);
  var cBersih = col_(info, ["Pendapatan Bersih"], -1);
  var cAdmin = col_(info, ["Biaya Admin"], -1);
  var cLayanan = col_(info, ["Biaya Layanan"], -1);
  var cAff = col_(info, ["Komisi Affiliate"], -1);
  var cOngkir = col_(info, ["Ongkir Penjual"], -1);

  t.rows.forEach(function(r) {
    var ms = cTgl !== -1 ? parseDateMs_(r[cTgl]) : 0;
    if (!ms || ms < range.start || ms > range.end) return;
    var admin = cAdmin !== -1 ? toNumber_(r[cAdmin]) : 0;
    var layanan = cLayanan !== -1 ? toNumber_(r[cLayanan]) : 0;
    var affiliate = cAff !== -1 ? toNumber_(r[cAff]) : 0;
    var ongkir = cOngkir !== -1 ? toNumber_(r[cOngkir]) : 0;
    var net = cBersih !== -1 ? toNumber_(r[cBersih]) : 0;
    summary.net += net; summary.admin += admin; summary.layanan += layanan; summary.affiliate += affiliate; summary.ongkir += ongkir; summary.fees += admin + layanan + affiliate + ongkir;
    rows.push({ Source_Module: "OMNI_SETTLEMENT", Source_ID: cNo !== -1 ? r[cNo] : "", Period: range.period, Date: cTgl !== -1 ? r[cTgl] : "", Store: cToko !== -1 ? r[cToko] : "", No_Pesanan: cNo !== -1 ? r[cNo] : "", Pendapatan_Bersih: net, Biaya_Admin: admin, Biaya_Layanan: layanan, Komisi_Affiliate: affiliate, Ongkir_Penjual: ongkir });
  });
  return { success: true, period: range.period, rows: rows, summary: summary };
}

function getOmniAdjustmentForFinance(period, emailOp, pasporOp) {
  OMNI_requirePassportFinance_(emailOp, pasporOp);
  var range = financeRange_(period);
  var t = readTable_(getActiveOmni_(), ADJUSTMENT_SHEET, ADJUSTMENT_HEADERS, { noCreate: true });
  var rows = [];
  var summary = { total: 0 };
  if (!t.sheet) return { success: true, period: range.period, rows: rows, summary: summary };

  var info = t.info;
  var cTgl = col_(info, ["Tgl Penyesuaian"], -1);
  var cToko = col_(info, ["Toko"], -1);
  var cNo = col_(info, ["ID Pesanan Terkait"], -1);
  var cJenis = col_(info, ["Jenis Transaksi"], -1);
  var cAdj = col_(info, ["Nomor Penyesuaian"], -1);
  var cNilai = col_(info, ["Nilai Penyesuaian (Rp)"], -1);
  t.rows.forEach(function(r) {
    var ms = cTgl !== -1 ? parseDateMs_(r[cTgl]) : 0;
    if (!ms || ms < range.start || ms > range.end) return;
    var nilai = cNilai !== -1 ? toNumber_(r[cNilai]) : 0;
    summary.total += nilai;
    rows.push({ Source_Module: "OMNI_ADJUSTMENT", Source_ID: cAdj !== -1 ? r[cAdj] : "", Period: range.period, Date: cTgl !== -1 ? r[cTgl] : "", Store: cToko !== -1 ? r[cToko] : "", No_Pesanan: cNo !== -1 ? r[cNo] : "", Jenis_Transaksi: cJenis !== -1 ? r[cJenis] : "", Nomor_Penyesuaian: cAdj !== -1 ? r[cAdj] : "", Nilai_Penyesuaian: nilai });
  });
  return { success: true, period: range.period, rows: rows, summary: summary };
}

function getOmniReturnForFinance(period, emailOp, pasporOp) {
  OMNI_requirePassportFinance_(emailOp, pasporOp);
  var range = financeRange_(period);
  var rows = [];
  var summary = { qty: 0, marketplaceRows: 0 };

  readReturTables_(false).forEach(function(t) {
    var info = t.info;
    var cTgl = col_(info, ["Tgl Sampai (RTS)", "Tgl Pesan"], -1);
    var cNo = col_(info, ["No Pesanan"], -1);
    var cResi = col_(info, ["No Resi"], -1);
    var cSku = col_(info, ["SKU BigSeller", "SKU"], -1);
    var cItem = col_(info, ["Item Gudang (Mapped)", "Item Gudang"], -1);
    var cQty = col_(info, ["QTY Retur Fisik", "Qty"], -1);
    var cStatus = col_(info, ["Status Marketplace"], -1);
    var cFinance = col_(info, ["Finance_Status"], -1);
    var cQc = col_(info, ["QC_Source"], -1);
    t.rows.forEach(function(r) {
      var ms = cTgl !== -1 ? parseDateMs_(r[cTgl]) : 0;
      if (!ms || ms < range.start || ms > range.end) return;
      var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
      summary.qty += qty;
      summary.marketplaceRows += 1;
      rows.push({ Source_Module: "OMNI_RETUR", Source_ID: cNo !== -1 ? r[cNo] : "", Period: range.period, Date: cTgl !== -1 ? r[cTgl] : "", No_Pesanan: cNo !== -1 ? r[cNo] : "", No_Resi: cResi !== -1 ? r[cResi] : "", SKU: cSku !== -1 ? r[cSku] : "", Item_Gudang: cItem !== -1 ? r[cItem] : "", Qty_Retur_Fisik: qty, Status_Marketplace: cStatus !== -1 ? r[cStatus] : "", Finance_Status: cFinance !== -1 ? r[cFinance] : "REFERENCE_ONLY", QC_Source: cQc !== -1 ? r[cQc] : "RETUR_QC_MODULE", Note: "Retur Omni hanya referensi marketplace. Stock RETURN_IN siap jual berasal dari modul Retur QC ke Gudang." });
    });
  });
  return { success: true, period: range.period, rows: rows, summary: summary };
}

function financeRange_(period) {
  var raw = period;
  if (period && typeof period === "object") raw = period.period || period.month || period.start || period.startDate || "";
  raw = String(raw || "").trim();
  var startD, endD, periodKey;
  if (/^\d{4}-\d{2}$/.test(raw)) {
    var p = raw.split("-");
    startD = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, 1, 0, 0, 0, 0);
    endD = new Date(parseInt(p[0], 10), parseInt(p[1], 10), 0, 23, 59, 59, 999);
    periodKey = raw;
  } else {
    var startStr = period && typeof period === "object" ? (period.start || period.startDate || "") : raw;
    var endStr = period && typeof period === "object" ? (period.end || period.endDate || "") : "";
    var r = buildDateRange_(startStr, endStr);
    startD = new Date(r.start);
    endD = new Date(r.end);
    periodKey = Utilities.formatDate(startD, TZ, "yyyy-MM");
  }
  return { period: periodKey, start: startD.getTime(), end: endD.getTime(), startDate: startD, endDate: endD };
}

function isDeletedRow_(row, cDel) {
  if (cDel === -1 || cDel === undefined || cDel === null) return false;
  var del = String(row[cDel] || "").toUpperCase();
  return del === "TRUE" || del === "YA" || del === "1" || del === "Y";
}

function OMNI_requirePassportFinance_(emailOp, pasporOp) {
  emailOp = ERP_normEmail_(emailOp || "");
  pasporOp = ERP_clean_(pasporOp || "");
  if (!emailOp || !pasporOp) throw new Error("Sesi Finance/Omni tidak lengkap. Masuk ulang dari Portal.");

  var authBase = ERP_securityCheck_(emailOp, pasporOp, true);
  if (authBase && authBase.allowed) {
    OMNI_RUNTIME_EMAIL = authBase.email || emailOp;
    return authBase;
  }

  var user = ERP_findUser_(emailOp);
  if (!user) throw new Error("Akses Finance/Omni ditolak: USER_TIDAK_ADA_DI_MASTER_USER");
  if (!ERP_isActive_(ERP_pick_(user, ["Status", "Status_Akun", "Aktif"]))) throw new Error("Akses Finance/Omni ditolak: USER_NONAKTIF");
  var pv = ERP_validatePassport_(emailOp, pasporOp);
  if (!pv.ok) throw new Error("Akses Finance/Omni ditolak: PASPOR_" + pv.reason);

  var role = ERP_pick_(user, ["Role", "Jabatan", "Hak_Akses", "Akses"]) || "";
  var department = ERP_pick_(user, ["Department", "Departemen", "Divisi"]) || "";
  var allowedModules = ERP_pick_(user, ["Allowed_Modules", "Allowed Modules", "Module_Access", "Hak_Modul", "Akses_Modul", "Modul"]) || "";
  var isAdmin = ERP_key_(role).indexOf("ADMIN") !== -1 || ERP_key_(department).indexOf("ADMIN") !== -1 || ERP_key_(allowedModules).indexOf("SUPERADMIN") !== -1 || ERP_key_(allowedModules).indexOf("ALL") !== -1;
  var canFinance = ERP_userCanOpenModule_({ allowedModules: allowedModules, role: role, department: department }, "FIN", "Finance", OMNI_CFG.FINANCE_MODULE_ALIASES || []);
  if (!isAdmin && !canFinance) throw new Error("Akses Finance/Omni ditolak: MODULE_ACCESS_DENIED");

  var auth = { allowed: true, reason: "OK_FINANCE_HANDOFF", email: emailOp, displayName: ERP_userDisplayName_(user, emailOp), role: role, department: department, allowedModules: allowedModules, isAdmin: isAdmin, passport: pasporOp, passportId: pasporOp };
  OMNI_RUNTIME_EMAIL = auth.email;
  return auth;
}

// =========================== LAPORAN ===========================

function getLaporanRetail(startStr, endStr) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);
  try {
    var storeTable = OMNI_readOrderDailyStore_(startStr, endStr);
    var productTable = OMNI_readOrderDailyProduct_(startStr, endStr);
    var metrics = { seluruhnya:0, selesai:0, perjalanan:0, batal:0, qtyValid:0, biayaAdmin:0, biayaLayanan:0, biayaAffiliate:0, ongkirPenjual:0, pendapatanBersih:0 };
    var mapTgl = {}, mapToko = {}, mapItem = {};

    if (storeTable.info) {
      var i = storeTable.info;
      var cDate = col_(i, ['Date_Key'], -1), cStore = col_(i, ['Store_Name'], -1);
      var cQty = col_(i, ['Item_Qty'], -1), cGross = col_(i, ['Gross_Sales'], -1);
      var cActive = col_(i, ['Active_Sales'], -1), cDone = col_(i, ['Completed_Sales'], -1);
      var cTransit = col_(i, ['In_Transit_Sales'], -1), cCancel = col_(i, ['Cancelled_Sales'], -1);
      var cNet = col_(i, ['Settlement_Net'], -1), cAdmin = col_(i, ['Admin_Fee'], -1);
      var cService = col_(i, ['Service_Fee'], -1), cAffiliate = col_(i, ['Affiliate_Fee'], -1);
      var cShipping = col_(i, ['Seller_Shipping'], -1);
      storeTable.rows.forEach(function(r) {
        var dateKey = cDate !== -1 ? String(r[cDate] || '') : '';
        var store = cStore !== -1 ? String(r[cStore] || 'Tidak Diketahui') : 'Tidak Diketahui';
        var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
        var active = cActive !== -1 ? toNumber_(r[cActive]) : 0;
        metrics.seluruhnya += cGross !== -1 ? toNumber_(r[cGross]) : 0;
        metrics.selesai += cDone !== -1 ? toNumber_(r[cDone]) : 0;
        metrics.perjalanan += cTransit !== -1 ? toNumber_(r[cTransit]) : 0;
        metrics.batal += cCancel !== -1 ? toNumber_(r[cCancel]) : 0;
        metrics.qtyValid += qty;
        metrics.pendapatanBersih += cNet !== -1 ? toNumber_(r[cNet]) : 0;
        metrics.biayaAdmin += cAdmin !== -1 ? toNumber_(r[cAdmin]) : 0;
        metrics.biayaLayanan += cService !== -1 ? toNumber_(r[cService]) : 0;
        metrics.biayaAffiliate += cAffiliate !== -1 ? toNumber_(r[cAffiliate]) : 0;
        metrics.ongkirPenjual += cShipping !== -1 ? toNumber_(r[cShipping]) : 0;
        if (dateKey) mapTgl[dateKey] = (mapTgl[dateKey] || 0) + active;
        if (!mapToko[store]) mapToko[store] = { toko:store, qty:0, omset:0 };
        mapToko[store].qty += qty;
        mapToko[store].omset += active;
      });
    }

    if (productTable.info) {
      var pi = productTable.info;
      var pcItem = col_(pi, ['Internal_Item_Name'], -1), pcQty = col_(pi, ['Item_Qty'], -1), pcSales = col_(pi, ['Gross_Sales'], -1);
      productTable.rows.forEach(function(r) {
        var item = pcItem !== -1 ? String(r[pcItem] || '') : '';
        if (!item) return;
        if (!mapItem[item]) mapItem[item] = { item:item, qty:0, omset:0 };
        mapItem[item].qty += pcQty !== -1 ? toNumber_(r[pcQty]) : 0;
        mapItem[item].omset += pcSales !== -1 ? toNumber_(r[pcSales]) : 0;
      });
    }

    var labels = Object.keys(mapTgl).sort();
    return {
      rekapToko:Object.keys(mapToko).map(function(k){return mapToko[k];}).sort(function(a,b){return b.omset-a.omset;}),
      rekapItem:Object.keys(mapItem).map(function(k){return mapItem[k];}).sort(function(a,b){return b.qty-a.qty;}),
      metrics:metrics,
      chartData:{
        labels:labels.map(function(k){var p=k.split('-');return p[2]+'/'+p[1]+'/'+p[0];}),
        data:labels.map(function(k){return mapTgl[k];})
      }
    };
  } catch (e) {
    logError_('getLaporanRetail', e, { startStr:startStr, endStr:endStr });
    return { error:e.message || String(e) };
  }
}

function emptyRetailReport_() {
  return { rekapToko: [], rekapItem: [], metrics: { seluruhnya: 0, selesai: 0, perjalanan: 0, batal: 0, qtyValid: 0, biayaAdmin: 0, biayaLayanan: 0, biayaAffiliate: 0, ongkirPenjual: 0, pendapatanBersih: 0 }, chartData: { labels: [], data: [] } };
}

function buildDateRange_(startStr, endStr) {
  var endD = new Date();
  var startD = new Date();
  startD.setDate(endD.getDate() - 30);

  if (startStr) {
    var ps = startStr.split('-');
    startD = new Date(parseInt(ps[0], 10), parseInt(ps[1], 10) - 1, parseInt(ps[2], 10), 0, 0, 0, 0);
  } else {
    startD.setHours(0,0,0,0);
  }
  if (endStr) {
    var pe = endStr.split('-');
    endD = new Date(parseInt(pe[0], 10), parseInt(pe[1], 10) - 1, parseInt(pe[2], 10), 23, 59, 59, 999);
  } else {
    endD.setHours(23,59,59,999);
  }
  return { start: startD.getTime(), end: endD.getTime() };
}

function isCanceledStatus_(s) {
  s = String(s || "").toLowerCase();
  return s.includes("batal") || s.includes("cancel") || s.includes("retur") || s.includes("refund") || s.includes("gagal");
}

function isCompletedStatus_(s) {
  s = String(s || "").toLowerCase();
  return s.includes("selesai") || s.includes("completed") || s.includes("delivered");
}

/**
 * Status global BigSeller yang diakui sebagai barang benar-benar dalam pengiriman.
 * Sengaja exact-match agar status aktif lain (menunggu proses, siap dikirim, pickup, dll.)
 * tidak masuk Persediaan Barang Dalam Pengiriman.
 */
function isShippedStatus_(s) {
  return normalize_(s) === 'sudah dikirim';
}

function getLaporanBiaya(startStr, endStr) {
  var __auth = OMNI_requirePassportFromArgs_(arguments);
  try {
    var table = OMNI_readOrderDailyStore_(startStr, endStr);
    if (!table.info) return { data:[] };
    var i = table.info;
    var cStore = col_(i, ['Store_Name'], -1), cActive = col_(i, ['Active_Sales'], -1), cSettled = col_(i, ['Settled_Sales'], -1);
    var cNet = col_(i, ['Settlement_Net'], -1), cAdmin = col_(i, ['Admin_Fee'], -1), cService = col_(i, ['Service_Fee'], -1);
    var cAffiliate = col_(i, ['Affiliate_Fee'], -1), cShipping = col_(i, ['Seller_Shipping'], -1);
    var map = {};
    table.rows.forEach(function(r) {
      var store = cStore !== -1 ? String(r[cStore] || 'Tidak Diketahui') : 'Tidak Diketahui';
      if (!map[store]) map[store] = { toko:store, omsetTotal:0, omsetCair:0, bersih:0, admin:0, layanan:0, affiliate:0, ongkir:0 };
      var x = map[store];
      x.omsetTotal += cActive !== -1 ? toNumber_(r[cActive]) : 0;
      x.omsetCair += cSettled !== -1 ? toNumber_(r[cSettled]) : 0;
      x.bersih += cNet !== -1 ? toNumber_(r[cNet]) : 0;
      x.admin += cAdmin !== -1 ? toNumber_(r[cAdmin]) : 0;
      x.layanan += cService !== -1 ? toNumber_(r[cService]) : 0;
      x.affiliate += cAffiliate !== -1 ? toNumber_(r[cAffiliate]) : 0;
      x.ongkir += cShipping !== -1 ? toNumber_(r[cShipping]) : 0;
    });
    var data = Object.keys(map).map(function(k) {
      var x = map[k], d = x.omsetCair;
      x.pctAdmin = d > 0 ? ((x.admin/d)*100).toFixed(1) : 0;
      x.pctLayanan = d > 0 ? ((x.layanan/d)*100).toFixed(1) : 0;
      x.pctAffiliate = d > 0 ? ((x.affiliate/d)*100).toFixed(1) : 0;
      x.pctOngkir = d > 0 ? ((x.ongkir/d)*100).toFixed(1) : 0;
      x.pctBersih = d > 0 ? ((x.bersih/d)*100).toFixed(1) : 0;
      return x;
    }).sort(function(a,b){return b.omsetTotal-a.omsetTotal;});
    return { data:data };
  } catch (e) {
    logError_('getLaporanBiaya', e, { startStr:startStr, endStr:endStr });
    return { error:e.message || String(e) };
  }
}


// ===== OMNI v1.2 INIT + FLOW-STYLE SECURITY + NAV + HEARTBEAT =====

function getInitDataOmni(emailOp, pasporOp) {
  var auth = OMNI_requirePassport_(emailOp, pasporOp);
  var end = new Date();
  var start = new Date();
  start.setDate(end.getDate() - 30);
  var startStr = Utilities.formatDate(start, OMNI_CFG.TZ, "yyyy-MM-dd");
  var endStr = Utilities.formatDate(end, OMNI_CFG.TZ, "yyyy-MM-dd");
  return {
    success: true,
    user: { email: auth.email || "", name: auth.displayName || auth.email || "", role: auth.role || "", department: auth.department || "" },
    links: getModulLinks(emailOp, pasporOp),
    stores: getDaftarTokoDinamis(emailOp, pasporOp),
    mapping: getDataMappingSKU(emailOp, pasporOp),
    posItems: getMenuPOS(emailOp, pasporOp),
    laporan: getLaporanRetail(startStr, endStr, emailOp, pasporOp),
    biaya: getLaporanBiaya(startStr, endStr, emailOp, pasporOp),
    period: { start: startStr, end: endStr },
    heartbeat: ERP_readGlobalHeartbeat_(),
    version: OMNI_CFG.VERSION
  };
}

function getOmniDashboardRefresh(emailOp, pasporOp) {
  OMNI_requirePassport_(emailOp, pasporOp);
  var end = new Date();
  var start = new Date();
  start.setDate(end.getDate() - 30);
  var startStr = Utilities.formatDate(start, OMNI_CFG.TZ, "yyyy-MM-dd");
  var endStr = Utilities.formatDate(end, OMNI_CFG.TZ, "yyyy-MM-dd");
  return {
    success:true,
    laporan:getLaporanRetail(startStr, endStr, emailOp, pasporOp),
    biaya:getLaporanBiaya(startStr, endStr, emailOp, pasporOp),
    period:{ start:startStr, end:endStr },
    heartbeat:ERP_readGlobalHeartbeat_(),
    version:OMNI_CFG.VERSION
  };
}


var ERP_GLOBAL_CFG = {
  MASTER_SPREADSHEET_ID: OMNI_CFG.MASTER_SPREADSHEET_ID,
  MODULE_CODE: OMNI_CFG.MODULE_CODE,
  SESSION_TTL_MS: OMNI_CFG.SESSION_TTL_MS,
  SHARED_SECRET: OMNI_CFG.SHARED_SECRET,
  HEARTBEAT_CELL: OMNI_CFG.HEARTBEAT_CELL,
  HEARTBEAT_UPDATED_CELL: OMNI_CFG.HEARTBEAT_UPDATED_CELL,
  HEARTBEAT_NOTES_CELL: OMNI_CFG.HEARTBEAT_NOTES_CELL,
  MASTER_USER_SHEET: OMNI_CFG.MASTER_USER_SHEET,
  MASTER_MODULE_SHEET: OMNI_CFG.MASTER_MODULE_SHEET,
  LOG_LOGIN_SHEET: OMNI_CFG.LOG_LOGIN_SHEET,
  PORTAL_CODES: OMNI_CFG.PORTAL_CODES,
  TZ: OMNI_CFG.TZ || (Session.getScriptTimeZone() || 'Asia/Jakarta')
};

function OMNI_requirePassportFromArgs_(args) {
  var a = Array.prototype.slice.call(args || []);
  return OMNI_requirePassport_(a.length >= 2 ? a[a.length - 2] : '', a.length >= 1 ? a[a.length - 1] : '');
}

function OMNI_requirePassport_(emailOp, pasporOp) {
  emailOp = ERP_normEmail_(emailOp || '');
  pasporOp = ERP_clean_(pasporOp || '');
  if (!emailOp || !pasporOp) throw new Error('Sesi Omni tidak lengkap. Masuk ulang dari Portal.');
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth || !auth.allowed) throw new Error('Akses Omni ditolak: ' + (auth && auth.reason ? auth.reason : 'UNKNOWN'));
  if (auth.email && emailOp && ERP_normEmail_(auth.email) !== emailOp) throw new Error('Passport tidak cocok dengan email aktif. Masuk ulang dari Portal.');
  OMNI_RUNTIME_EMAIL = auth.email || emailOp;
  return auth;
}

function OMNI_requirePassportOrEditor_(args, fnName) {
  var a = Array.prototype.slice.call(args || []);
  var maybeEmail = a.length >= 2 ? a[a.length - 2] : '';
  var maybePass = a.length >= 1 ? a[a.length - 1] : '';
  if (maybeEmail || maybePass) return OMNI_requirePassport_(maybeEmail, maybePass);

  // Maintenance mode: dipakai hanya ketika function dijalankan langsung dari Apps Script editor.
  // Tetap validasi akun ke Master_User + hak akses OMNI, tapi tidak butuh passport URL.
  var email = ERP_normEmail_(ERP_userEmail_() || userEmail_() || '');
  if (!email || email === 'unknown') {
    throw new Error('Sesi Omni tidak lengkap. Jalankan dari Portal, atau jalankan manual dari Apps Script editor memakai akun yang terdaftar di Master_User.');
  }
  var auth = ERP_securityCheck_(email, '', false);
  if (!auth || !auth.allowed) {
    throw new Error('Akses maintenance Omni ditolak untuk ' + email + ': ' + (auth && auth.reason ? auth.reason : 'UNKNOWN'));
  }
  OMNI_RUNTIME_EMAIL = auth.email || email;
  try { Logger.log('OMNI maintenance mode OK: ' + (fnName || 'maintenance') + ' by ' + OMNI_RUNTIME_EMAIL); } catch(e) {}
  return auth;
}

function OMNI_touchMutation_(fnName) {
  try { ERP_mutation_(fnName || 'OMNI_MUTATION'); } catch(e) {}
}

function ERP_doGetAccess_(e) {
  var p = (e && e.parameter) || {};
  var email = ERP_normEmail_(p.vouch || p.email || p.user || '');
  var passport = ERP_clean_(p.paspor || p.passport || p.token || '');
  var auth = ERP_securityCheck_(email, passport, true);
  if (auth.allowed) {
    auth.passport = passport;
    auth.passportId = passport;
  }
  return auth;
}

function ERP_forbiddenOutput_(auth) {
  var portal = ERP_withLoginParam_(ERP_getPortalUrl_());
  var btn = portal ? '<p><a style="display:inline-block;background:#1677ff;color:white;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:800" href="'+ERP_escapeHtml_(portal)+'" target="_top">Kembali ke Portal</a></p>' : '';
  return HtmlService.createHtmlOutput('<base target="_top"><div style="font-family:Arial,sans-serif;text-align:center;margin-top:13vh;background:#f8fafc;padding:48px;border-radius:22px;max-width:680px;margin-left:auto;margin-right:auto;box-shadow:0 10px 25px rgba(0,0,0,.12)"><div style="font-size:78px">⛔</div><h1 style="color:#ef4444">AKSES / SESSION DITOLAK</h1><p>Alasan: <b>'+ERP_escapeHtml_(auth && auth.reason || 'UNKNOWN')+'</b></p><p>Email: <b>'+ERP_escapeHtml_(auth && auth.email || '(kosong)')+'</b></p><p>Silakan masuk dari Portal/Beranda supaya paspor session valid.</p>'+btn+'</div>').setTitle('Akses Ditolak');
}

function ERP_globalHeartbeat(clientVersion, emailOp, pasporOp) {
  if (arguments.length >= 4) {
    clientVersion = arguments[1];
    emailOp = arguments[2];
    pasporOp = arguments[3] || arguments[0] || '';
  }
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth.allowed) return { ok:false, success:false, reason:auth.reason || 'SESSION_INVALID', shouldLogout:true, portalUrl:ERP_withLoginParam_(ERP_getPortalUrl_()) };
  OMNI_RUNTIME_EMAIL = auth.email || '';
  var hb = ERP_readGlobalHeartbeat_();
  return {
    ok: true,
    success: true,
    reason: auth.reason,
    shouldLogout: false,
    moduleCode: ERP_GLOBAL_CFG.MODULE_CODE,
    passport: pasporOp || auth.passport || auth.passportId || '',
    paspor: pasporOp || auth.passport || auth.passportId || '',
    userEmail: auth.email || '',
    displayName: auth.displayName || auth.email || '',
    user: { email: auth.email || '', name: auth.displayName || auth.email || '', role: auth.role || '', department: auth.department || '' },
    serverVersion: hb.version,
    updatedAt: hb.updatedAt,
    shouldRefresh: !!clientVersion && String(clientVersion) !== String(hb.version),
    portalUrl: ERP_withLoginParam_(ERP_getPortalUrl_()),
    session: ERP_sessionInfoFromToken_(auth.email, pasporOp || auth.passport || auth.passportId || ''),
    now: ERP_formatDateTime_(new Date())
  };
}

function ERP_globalLogout(passportId, emailOp, pasporOp) {
  var email = emailOp || '';
  var paspor = pasporOp || passportId || '';
  var auth = ERP_securityCheck_(email, paspor, true);
  if (!auth.allowed) return { success:false, ok:false, reason:auth.reason || 'SESSION_INVALID', portalUrl:ERP_withLoginParam_(ERP_getPortalUrl_()) };
  ERP_markLogout_(auth.email, Date.now());
  try { ERP_logLogin_(auth.email, 'LOGOUT_FROM_' + ERP_GLOBAL_CFG.MODULE_CODE, paspor || '', 'SUCCESS', 'Logout dari modul'); } catch(e) {}
  try { ERP_bumpGlobalHeartbeat_('Logout ' + auth.email + ' from ' + ERP_GLOBAL_CFG.MODULE_CODE); } catch(e) {}
  return { success:true, ok:true, portalUrl:ERP_withLoginParam_(ERP_getPortalUrl_()), message:'Logout berhasil.' };
}

function ERP_touchGlobalChange(reason, emailOp, pasporOp) {
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth.allowed) throw new Error('Akses ditolak: ' + (auth.reason || 'SESSION_INVALID'));
  return ERP_markDataChanged_(reason || ('Change from ' + ERP_GLOBAL_CFG.MODULE_CODE + ' by ' + auth.email));
}
function ERP_markDataChanged_(reason) { var hb = ERP_bumpGlobalHeartbeat_(reason || ('Data changed from ' + ERP_GLOBAL_CFG.MODULE_CODE)); return { success:true, heartbeat:hb }; }
function ERP_mutation_(fnName) { try { ERP_markDataChanged_((fnName || 'Mutation') + ' @ ' + ERP_GLOBAL_CFG.MODULE_CODE); } catch(e) {} }

function TEST_erpOmniSecurityHeartbeat(email, paspor) {
  var auth = ERP_securityCheck_(email || ERP_userEmail_(), paspor || '', !!paspor);
  var hb = ERP_readGlobalHeartbeat_();
  return { success:true, moduleCode:ERP_GLOBAL_CFG.MODULE_CODE, auth:auth, heartbeat:hb, portalUrl:ERP_getPortalUrl_(), note:'v1.5 HMAC Flow Style + POS contract + finance handoff + retur reference-only alignment.' };
}

function ERP_securityCheck_(emailOp, pasporOp, passportRequired) {
  if (arguments.length === 2 && typeof pasporOp === 'boolean') {
    passportRequired = pasporOp;
    pasporOp = emailOp;
    emailOp = '';
  }
  emailOp = ERP_normEmail_(emailOp || ERP_userEmail_() || '');
  if (!emailOp) return { allowed:false, reason:'EMAIL_KOSONG', email:'' };

  var user = ERP_findUser_(emailOp);
  if (!user) return { allowed:false, reason:'USER_TIDAK_ADA_DI_MASTER_USER', email:emailOp };
  if (!ERP_isActive_(ERP_pick_(user, ['Status','Status_Akun','Aktif']))) return { allowed:false, reason:'USER_NONAKTIF', email:emailOp, status:ERP_pick_(user, ['Status','Status_Akun','Aktif']) || '' };

  pasporOp = ERP_clean_(pasporOp || '');
  if (passportRequired) {
    var pv = ERP_validatePassport_(emailOp, pasporOp);
    if (!pv.ok) return { allowed:false, reason:'PASPOR_' + pv.reason, email:emailOp, passportId:pasporOp };
  } else if (pasporOp) {
    var pv2 = ERP_validatePassport_(emailOp, pasporOp);
    if (!pv2.ok) return { allowed:false, reason:'PASPOR_' + pv2.reason, email:emailOp, passportId:pasporOp };
  }

  var role = ERP_pick_(user, ['Role','Jabatan','Hak_Akses','Akses']) || '';
  var department = ERP_pick_(user, ['Department','Departemen','Divisi']) || '';
  var allowedModules = ERP_pick_(user, ['Allowed_Modules','Allowed Modules','Module_Access','Hak_Modul','Akses_Modul','Modul']) || '';
  var isAdmin = ERP_key_(role).indexOf('ADMIN') !== -1 || ERP_key_(department).indexOf('ADMIN') !== -1 || ERP_key_(allowedModules).indexOf('SUPERADMIN') !== -1 || ERP_key_(allowedModules).indexOf('ALL') !== -1;
  var can = isAdmin || ERP_userCanOpenModule_({ allowedModules:allowedModules, role:role, department:department }, ERP_GLOBAL_CFG.MODULE_CODE, 'Omnichannel Retail', OMNI_CFG.MODULE_ALIASES || []);
  return {
    allowed: can,
    reason: can ? 'OK' : 'MODULE_ACCESS_DENIED',
    email: emailOp,
    displayName: ERP_userDisplayName_(user, emailOp),
    role: role,
    department: department,
    allowedModules: allowedModules,
    isAdmin: isAdmin,
    passport: pasporOp,
    passportId: pasporOp
  };
}

function ERP_validatePassport_(email, paspor) {
  var p = ERP_parsePassport_(paspor);
  if (!p.stamp || !p.hash) return { ok:false, reason:'FORMAT_TIDAK_VALID' };
  if (p.hash !== ERP_hashPassport_(email, p.stamp)) return { ok:false, reason:'HASH_TIDAK_VALID' };
  if (Date.now() - p.stamp > ERP_GLOBAL_CFG.SESSION_TTL_MS) return { ok:false, reason:'EXPIRED' };
  var lastLogout = ERP_getLastLogoutStamp_(email);
  if (lastLogout && p.stamp < lastLogout) return { ok:false, reason:'GLOBAL_LOGOUT' };
  return { ok:true, stamp:p.stamp };
}
function ERP_parsePassport_(paspor) {
  var raw = ERP_clean_(paspor);
  var m = raw.match(/^(\d{10,}):([a-f0-9]{64})$/i);
  return m ? { stamp:Number(m[1]) || 0, hash:String(m[2] || '').toLowerCase() } : { stamp:0, hash:raw.toLowerCase() };
}
function ERP_hashPassport_(email, stamp) {
  var raw = ERP_normEmail_(email) + '|' + Number(stamp || 0) + '|' + ERP_GLOBAL_CFG.SHARED_SECRET;
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw)
    .map(function(b){ return (b < 0 ? b + 256 : b).toString(16).padStart(2, '0'); })
    .join('');
}
function ERP_sessionInfoFromToken_(email, paspor) {
  var p = ERP_parsePassport_(paspor);
  var lastLogout = ERP_getLastLogoutStamp_(email);
  return {
    loginAt: p.stamp ? ERP_formatDateTime_(new Date(p.stamp)) : '',
    expiresAt: p.stamp ? ERP_formatDateTime_(new Date(p.stamp + ERP_GLOBAL_CFG.SESSION_TTL_MS)) : '',
    lastLogoutAt: lastLogout ? ERP_formatDateTime_(new Date(lastLogout)) : '',
    ttlHours: Math.round(ERP_GLOBAL_CFG.SESSION_TTL_MS / 3600000)
  };
}

function ERP_findUser_(email) {
  var sh = ERP_master_().getSheetByName(ERP_GLOBAL_CFG.MASTER_USER_SHEET);
  if (!sh) throw new Error('Master_User tidak ditemukan.');
  var rows = ERP_readRows_(sh);
  email = ERP_normEmail_(email);
  for (var i=0; i<rows.length; i++) {
    var e = ERP_normEmail_(ERP_pick_(rows[i], ['Email','Email_Google','Gmail','Email_User','User_Email','Username']));
    if (e === email) return rows[i];
  }
  return null;
}
function ERP_userDisplayName_(user, email) {
  return ERP_clean_(ERP_pick_(user || {}, ['Display_Name','Display Name','Nama','Nama_User','Nama User','Nama_Lengkap','Nama Lengkap','Name','User_Name','Username'])) || ERP_clean_(email);
}
function ERP_userCanOpenModule_(auth, code, name, extraAliases) {
  var fields = [auth.allowedModules, auth.role, auth.department].map(ERP_key_).join('|');
  if (fields.indexOf('ALL') !== -1 || fields.indexOf('SUPERADMIN') !== -1) return true;
  var targets = [code, name || ''].concat(extraAliases || []).map(ERP_key_);
  return targets.some(function(t){ return t && fields.indexOf(t) !== -1; });
}
function ERP_canOpenModule_(user, code) { return ERP_userCanOpenModule_({ allowedModules:user.Allowed_Modules || user.Module_Access || user.Hak_Modul || '', role:user.Role || '', department:user.Department || user.Departemen || '' }, code, code); }

function ERP_getLastLogoutStamp_(email) {
  try {
    var user = ERP_findUser_(email);
    if (!user) return 0;
    var raw = ERP_pick_(user, ['Last_Logout_At','Logout_At','Global_Logout_At','LastLogoutAt']);
    var d = ERP_parseDate_(raw);
    return d ? d.getTime() : 0;
  } catch(e) { return 0; }
}
function ERP_markLogout_(email, stamp) {
  try {
    var sh = ERP_master_().getSheetByName(ERP_GLOBAL_CFG.MASTER_USER_SHEET);
    if (!sh) return;
    var vals = sh.getDataRange().getValues();
    if (vals.length < 2) return;
    var map = ERP_headerMap_(vals[0]);
    var cEmail = ERP_col_(map, ['Email','Email_Google','Gmail','Email_User','User_Email','Username'], false);
    if (cEmail < 0) return;
    for (var r=1; r<vals.length; r++) {
      if (ERP_normEmail_(vals[r][cEmail]) !== ERP_normEmail_(email)) continue;
      var patches = { Last_Logout_At:new Date(stamp || Date.now()), Logout_Reason:'USER_LOGOUT_FROM_' + ERP_GLOBAL_CFG.MODULE_CODE };
      Object.keys(patches).forEach(function(k){ var c = ERP_col_(map, [k], false); if (c >= 0) sh.getRange(r+1, c+1).setValue(patches[k]); });
      return;
    }
  } catch(e) {}
}

function ERP_readGlobalHeartbeat_() {
  try {
    var sh = ERP_master_().getSheetByName(ERP_GLOBAL_CFG.MASTER_MODULE_SHEET);
    if (!sh) return { version:'0', updatedAt:'', notes:'Master_Module tidak ditemukan' };
    var version = String(sh.getRange(ERP_GLOBAL_CFG.HEARTBEAT_CELL).getValue() || '0');
    return {
      version: version,
      updatedAt: ERP_formatDateTime_(sh.getRange(ERP_GLOBAL_CFG.HEARTBEAT_UPDATED_CELL).getValue()),
      notes: String(sh.getRange(ERP_GLOBAL_CFG.HEARTBEAT_NOTES_CELL).getValue() || '')
    };
  } catch(e) { return { version:'0', updatedAt:'', notes:e.message || String(e) }; }
}
function ERP_bumpGlobalHeartbeat_(notes) {
  var sh = ERP_master_().getSheetByName(ERP_GLOBAL_CFG.MASTER_MODULE_SHEET);
  if (!sh) throw new Error('Master_Module tidak ditemukan untuk heartbeat.');
  var now = Date.now();
  sh.getRange(ERP_GLOBAL_CFG.HEARTBEAT_CELL).setValue(now);
  sh.getRange(ERP_GLOBAL_CFG.HEARTBEAT_UPDATED_CELL).setValue(new Date());
  sh.getRange(ERP_GLOBAL_CFG.HEARTBEAT_NOTES_CELL).setValue(notes || ('Update from ' + ERP_GLOBAL_CFG.MODULE_CODE));
  return ERP_readGlobalHeartbeat_();
}

function ERP_getPortalUrl_() {
  try {
    var links = ERP_readModuleLinksRaw_();
    for (var i=0; i<links.length; i++) {
      var code = ERP_key_(links[i].code), name = ERP_key_(links[i].name);
      if (ERP_GLOBAL_CFG.PORTAL_CODES.indexOf(code) !== -1 || name.indexOf('PORTAL') !== -1 || name.indexOf('BERANDA') !== -1) return links[i].url;
    }
  } catch(e) {}
  return '';
}
function ERP_withLoginParam_(url) {
  url = ERP_clean_(url);
  if (!url) return '';
  var sep = url.indexOf('?') === -1 ? '?' : '&';
  return url + sep + 'login=1';
}
function ERP_appendPassportToUrl_(url, auth, paspor) {
  url = ERP_clean_(url);
  if (!url) return '';
  var sep = url.indexOf('?') === -1 ? '?' : '&';
  return url + sep + 'vouch=' + encodeURIComponent(auth.email || '') + '&paspor=' + encodeURIComponent(paspor || auth.passport || auth.passportId || '') + '&passport=' + encodeURIComponent(paspor || auth.passport || auth.passportId || '') + '&from=' + encodeURIComponent(ERP_GLOBAL_CFG.MODULE_CODE);
}
function ERP_readModuleLinksRaw_() {
  var sh = ERP_master_().getSheetByName(ERP_GLOBAL_CFG.MASTER_MODULE_SHEET);
  if (!sh) return [];
  var rows = ERP_readRows_(sh);
  return rows.map(function(r){
    return { code:ERP_clean_(r.Module_Code || r.Code || ''), name:ERP_clean_(r.Module_Name || r.Name || r.Nama || ''), url:ERP_clean_(r.Web_App_URL || r.WebApp_URL || r.URL || ''), status:ERP_clean_(r.Status || '') };
  }).filter(function(x){ return x.code && x.url; });
}
function ERP_logLogin_(email,action,pid,status,notes){try{var ss=ERP_master_();var sh=ss.getSheetByName(ERP_GLOBAL_CFG.LOG_LOGIN_SHEET)||ss.insertSheet(ERP_GLOBAL_CFG.LOG_LOGIN_SHEET);var h=['Timestamp','Email','Display_Name','Action','Passport_ID','Status','User_Agent','Notes'];if(sh.getLastRow()===0)sh.getRange(1,1,1,h.length).setValues([h]);sh.appendRow([new Date(),email,'',action,pid,status,'',notes||'']);}catch(e){} }
function ERP_master_(){return SpreadsheetApp.openById(ERP_GLOBAL_CFG.MASTER_SPREADSHEET_ID);}
function ERP_userEmail_(){try{return ERP_normEmail_(Session.getActiveUser().getEmail());}catch(e){return '';}}
function ERP_clean_(v){return String(v===null||v===undefined?'':v).trim();}
function ERP_normEmail_(v){return ERP_clean_(v).toLowerCase();}
function ERP_key_(v){return ERP_clean_(v).toUpperCase().replace(/[^A-Z0-9]/g,'');}
function ERP_isActive_(v){var s=ERP_key_(v);if(!s)return true;return ['ACTIVE','AKTIF','ON','TRUE','YES','ENABLED','NEWCORE','NEW_CORE'].indexOf(s)!==-1;}
function ERP_parseDate_(v){if(v instanceof Date)return v;var d=new Date(v);return isNaN(d.getTime())?null:d;}
function ERP_formatDateTime_(v){var d=ERP_parseDate_(v);return d?Utilities.formatDate(d,ERP_GLOBAL_CFG.TZ,'yyyy-MM-dd HH:mm:ss'):'';}
function ERP_headerMap_(headers){var m={};for(var i=0;i<headers.length;i++){var k=ERP_key_(headers[i]);if(k)m[k]=i;}return m;}
function ERP_col_(map,names,required){names=Array.isArray(names)?names:[names];for(var i=0;i<names.length;i++){var k=ERP_key_(names[i]);if(map[k]!==undefined)return map[k];}if(required)throw new Error('Header tidak ditemukan: '+names.join('/'));return -1;}
function ERP_pick_(obj, aliases) { var m = {}; Object.keys(obj || {}).forEach(function(k){ m[ERP_key_(k)] = obj[k]; }); for (var i=0; i<(aliases || []).length; i++) { var key = ERP_key_(aliases[i]); if (m[key] !== undefined) return m[key]; } return ''; }
function ERP_readRows_(sh){var vals=sh.getDataRange().getValues();if(vals.length<2)return[];var headers=vals[0].map(ERP_clean_);return vals.slice(1).filter(function(r){return r.some(function(c){return c!==''&&c!==null;});}).map(function(r){var o={};headers.forEach(function(h,i){if(h)o[h]=r[i];});return o;});}
function ERP_escapeHtml_(s){return String(s||'').replace(/[&<>'"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c];});}


/* =========================
 * v1.5.2 ORDER COGS READY
 * - Omni_Order menyimpan COGS per order line agar Finance bisa pisah:
 *   Selesai => Pendapatan + HPP
 *   Sudah Dikirim => Persediaan Barang Dalam Pengiriman
 *   Harga 0 => Biaya Sample Affiliate lawan Persediaan
 * ========================= */

function OMNI_prepareOrderCogsContext_() {
  var ctx = { ok:false, whSs:null, itemLookup:null, costIndex:null, syncedAt: nowText_(), error:'' };
  try {
    ctx.whSs = OMNI_openGudangSpreadsheet_();
    ctx.itemLookup = OMNI_buildStockItemLookup_();
    ctx.costIndex = OMNI_buildStockCostPeriodIndex_(ctx.whSs);
    ctx.ok = true;
  } catch (e) {
    ctx.error = e && e.message ? e.message : String(e);
  }
  return ctx;
}

function OMNI_buildStockCostPeriodIndex_(whSs) {
  var out = {};
  if (!whSs) return out;
  var sh = whSs.getSheetByName('Stock_Cost_Period');
  if (!sh || sh.getLastRow() < 2) return out;
  var info = headerInfo_(sh);
  var cPeriod = col_(info, ['Period', 'Cost_Period'], -1);
  var cId = col_(info, ['Item_ID', 'Item ID'], -1);
  var cName = col_(info, ['Item_Name', 'Item Name', 'Nama Item', 'Item'], -1);
  var cProv = col_(info, ['Unit_Cost_Provisional', 'Unit Cost Provisional'], -1);
  var cFinal = col_(info, ['Unit_Cost_Final', 'Unit Cost Final'], -1);
  var cStatus = col_(info, ['Cost_Status', 'Cost Status'], -1);
  var cSrc = col_(info, ['Source_Module', 'Source Module'], -1);
  var cSrcId = col_(info, ['Source_ID', 'Source ID'], -1);
  var cSync = col_(info, ['Synced_At', 'Cost_Synced_At'], -1);
  var cDel = col_(info, ['Is_Deleted', 'Is Deleted'], -1);
  var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  vals.forEach(function(r) {
    var del = cDel !== -1 ? String(r[cDel] || '').toUpperCase() : '';
    if (['TRUE','YES','YA','1','DELETED'].indexOf(del) !== -1) return;
    var period = cPeriod !== -1 ? String(r[cPeriod] || '').trim().substring(0, 7) : '';
    if (!period) return;
    var id = cId !== -1 ? String(r[cId] || '').trim() : '';
    var name = cName !== -1 ? String(r[cName] || '').trim() : '';
    if (!id && !name) return;
    var status = cStatus !== -1 ? String(r[cStatus] || 'PROVISIONAL').toUpperCase().trim() : 'PROVISIONAL';
    var obj = {
      Period: period,
      Item_ID: id,
      Item_Name: name,
      Unit_Cost_Provisional: cProv !== -1 ? toNumber_(r[cProv]) : 0,
      Unit_Cost_Final: cFinal !== -1 ? toNumber_(r[cFinal]) : 0,
      Cost_Status: status === 'FINAL' ? 'FINAL' : 'PROVISIONAL',
      Cost_Source: (cSrc !== -1 ? String(r[cSrc] || 'STOCK_COST_PERIOD') : 'STOCK_COST_PERIOD') + (cSrcId !== -1 && r[cSrcId] ? '|' + r[cSrcId] : ''),
      Cost_Synced_At: cSync !== -1 && r[cSync] ? r[cSync] : nowText_()
    };
    function put(k) {
      if (!k) return;
      var key = period + '|' + normalize_(k);
      if (!out[key] || obj.Cost_Status === 'FINAL') out[key] = obj;
    }
    put(id); put(name);
  });
  return out;
}

function OMNI_findStockItemByName_(lookup, itemName) {
  lookup = lookup || {};
  var name = String(itemName || '').trim();
  if (!name || name.toUpperCase() === 'UNMAPPED') return null;
  return (lookup.byName && lookup.byName[normalize_(name)]) || (lookup.byDisplay && lookup.byDisplay[normalize_(name)]) || null;
}

function OMNI_resolveOrderCogs_(ctx, itemName, qty, dateValue, totalSales) {
  qty = toNumber_(qty);
  var __ms = parseDateMs_(dateValue);
  var dateObj = __ms ? new Date(__ms) : new Date();
  var period = Utilities.formatDate(dateObj, TZ, 'yyyy-MM');
  var item = OMNI_findStockItemByName_(ctx && ctx.itemLookup, itemName) || { Item_ID:'', Item_Name:String(itemName || '').trim(), Default_Cost:0 };
  var row = null;
  if (ctx && ctx.costIndex) row = ctx.costIndex[period + '|' + normalize_(item.Item_ID)] || ctx.costIndex[period + '|' + normalize_(item.Item_Name)] || ctx.costIndex[period + '|' + normalize_(itemName)];
  var status = row ? String(row.Cost_Status || 'PROVISIONAL').toUpperCase() : 'PROVISIONAL';
  var unit = 0;
  if (row && status === 'FINAL' && toNumber_(row.Unit_Cost_Final) > 0) unit = toNumber_(row.Unit_Cost_Final);
  if (!unit && row && toNumber_(row.Unit_Cost_Provisional) > 0) unit = toNumber_(row.Unit_Cost_Provisional);
  if (!unit && item && toNumber_(item.Default_Cost) > 0) unit = toNumber_(item.Default_Cost);
  var value = qty > 0 ? qty * unit : 0;
  var bucket = (toNumber_(totalSales) <= 0 && qty > 0 && value > 0) ? 'SAMPLE_AFFILIATE' : 'SALES';
  return {
    Unit_Cost: unit,
    COGS_Value: value,
    Cost_Period: period,
    Cost_Status: status === 'FINAL' ? 'FINAL' : 'PROVISIONAL',
    Cost_Source: row ? row.Cost_Source : (unit ? 'MASTER_ITEM_DEFAULT_COST' : 'NO_COST'),
    Cost_Synced_At: row ? (row.Cost_Synced_At || nowText_()) : nowText_(),
    Finance_Bucket: bucket
  };
}

function OMNI_applyOrderCogsToRow_(row, info, ctx, itemName, qty, dateValue, totalSales) {
  var cost = OMNI_resolveOrderCogs_(ctx || {}, itemName, qty, dateValue, totalSales);
  setRowValue_(row, info, 'Unit_Cost', cost.Unit_Cost);
  setRowValue_(row, info, 'COGS_Value', cost.COGS_Value);
  setRowValue_(row, info, 'Cost_Period', cost.Cost_Period);
  setRowValue_(row, info, 'Cost_Status', cost.Cost_Status);
  setRowValue_(row, info, 'Cost_Source', cost.Cost_Source);
  setRowValue_(row, info, 'Cost_Synced_At', cost.Cost_Synced_At);
  setRowValue_(row, info, 'Finance_Bucket', cost.Finance_Bucket);
  return cost;
}

function SYNC_omniOrderCogsFromGudang(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'SYNC_omniOrderCogsFromGudang');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success:false, error:'Server sibuk.' }; }
  try {
    var ss = getActiveOmni_();
    ensureSheetWithHeaders_(ss, OMNI_SHEET, OMNI_HEADERS);
    var t = readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
    if (!t.sheet || t.rows.length === 0) return { success:true, total:0, updated:0 };
    var info = t.info, ctx = OMNI_prepareOrderCogsContext_(), updates = [], stat = { success:true, total:t.rows.length, updated:0, noCost:0, sample:0 };
    var cItem = col_(info, ['Item Gudang', 'Internal_Item_Name'], -1);
    var cQty = col_(info, ['Qty', 'Qty Gudang'], -1);
    var cTanggal = col_(info, ['Tanggal', 'Tanggal Key'], -1);
    var cTotal = col_(info, ['Total', 'Subtotal'], -1);
    var cDel = col_(info, ['Is_Deleted', 'Is Deleted'], -1);
    t.rows.forEach(function(r, idx) {
      if (cDel !== -1 && ['TRUE','YES','YA','1','DELETED'].indexOf(String(r[cDel] || '').toUpperCase()) !== -1) return;
      var row = r.slice(0, info.headers.length);
      while (row.length < info.headers.length) row.push('');
      var item = cItem !== -1 ? String(row[cItem] || '').trim() : '';
      var qty = cQty !== -1 ? toNumber_(row[cQty]) : 0;
      var total = cTotal !== -1 ? toNumber_(row[cTotal]) : 0;
      var dateVal = cTanggal !== -1 ? row[cTanggal] : new Date();
      var cost = OMNI_applyOrderCogsToRow_(row, info, ctx, item, qty, dateVal, total);
      if (!cost.Unit_Cost) stat.noCost++;
      if (cost.Finance_Bucket === 'SAMPLE_AFFILIATE') stat.sample++;
      updates.push({ rowNumber: idx + 2, row: row });
    });
    stat.updated = writeChangedRows_(t.sheet, updates, info.headers.length);
    SpreadsheetApp.flush();
    stat.dailySummary = OMNI_rebuildOrderDailySummary_(null);
    OMNI_touchMutation_('SYNC_omniOrderCogsFromGudang');
    return stat;
  } catch(e) {
    logError_('SYNC_omniOrderCogsFromGudang', e, {});
    return { success:false, error:e.message || String(e) };
  } finally { lock.releaseLock(); }
}

function TEST_omniOrderCogsDebug() {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniOrderCogsDebug');
  var ss = getActiveOmni_();
  var t = readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
  var info = t.info;
  var out = { success:true, total:t.rows.length, withCogs:0, sample:0, noCost:0, sampleRows:[] };
  t.rows.forEach(function(r){
    var cogs = toNumber_(getRowValueAny_(r, info, ['COGS_Value']));
    var bucket = String(getRowValueAny_(r, info, ['Finance_Bucket']) || '');
    if (cogs > 0) out.withCogs++;
    if (bucket === 'SAMPLE_AFFILIATE') { out.sample++; if (out.sampleRows.length < 10) out.sampleRows.push({ order:getRowValueAny_(r, info, ['No Pesanan']), item:getRowValueAny_(r, info, ['Item Gudang']), qty:getRowValueAny_(r, info, ['Qty']), cogs:cogs }); }
    if (!cogs && toNumber_(getRowValueAny_(r, info, ['Qty'])) > 0 && String(getRowValueAny_(r, info, ['Item Gudang']) || '').toUpperCase() !== 'UNMAPPED') out.noCost++;
  });
  return out;
}