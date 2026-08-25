// =================================================================================
// ERP CV KIRAL - BACKEND MODUL GUDANG
// Legacy UI + Stock_Movement Adapter v2.6 Summary PR + Lazy Detail
// Fokus: loading awal PR membaca summary produk Omni; detail/aksi Pack-Tidak Pack tetap validasi Omni_Order raw.
// =================================================================================

var MASTER_SPREADSHEET_ID = "1bbtCMQfK5p_2c5GzIkTIrcIPcPsm3Wjh_R8PfAagu6I";
// Opsional hardcode sementara kalau routing Master_Module belum stabil. Isi ID GSheet Omnichannel saja, bukan Web App URL.
var OMNI_SPREADSHEET_ID_OVERRIDE = "";
var TZ = "Asia/Jakarta";
var CACHE_SECONDS = 300;
var WRITE_CHUNK_SIZE = 1000;
var MUTASI_RETURN_LIMIT = 1200;
var OMNI_LOOKBACK_DAYS = 365; // v1.7: Dashboard PR agregat per item, Tarikan detail per tanggal+toko
var OMNI_MODULE_CODES = ["OMNI", "OMNICHANNEL", "RETAIL", "RETAIL_OMNI"];
var OMNI_DAILY_PRODUCT_SHEET = "Omni_Order_Daily_Product";
var OMNI_WAREHOUSE_SUMMARY_VERSION = "OMNI_WAREHOUSE_SUMMARY_V1";

var GUDANG_CFG = {
  VERSION: "GUDANG_v2.6_SUMMARY_PR_LAZY_DETAIL",
  MASTER_SPREADSHEET_ID: MASTER_SPREADSHEET_ID,
  MODULE_CODE: "WH",
  MODULE_ALIASES: ["WH", "GUDANG", "WAREHOUSE", "MODUL GUDANG", "STOCK", "INVENTORY"],
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

var SHEET_STOCK_MOVEMENT = "Stock_Movement";
var SHEET_STOCK_AUDIT = "Stock_Audit";
var SHEET_STOCK_OPNAME = "Stock_Opname";
var SHEET_STOCK_CUTOFF = "Stock_Cutoff";
var SHEET_STOCK_COST_PERIOD = "Stock_Cost_Period";
var SHEET_OMNI_ACTION_LOG = "Omni_Action_Log";

var STOCK_MOVEMENT_HEADERS = [
  "Movement_ID", "Tx_Key", "Tanggal", "Source_Date", "Item_ID", "Item_Name", "Item_Category", "Item_Type", "Unit",
  "Warehouse_Code", "Direction", "Movement_Type", "Qty", "Unit_Cost",
  "Cost_Period", "Cost_Status", "Unit_Cost_Provisional", "Value_Provisional", "Unit_Cost_Final", "Value_Final",
  "Cost_Source", "Cost_Synced_At", "Closed_At", "Closed_By",
  "Source_Module", "Source_ID", "Source_Line_ID", "Ref_No", "Batch_ID", "External_Ref", "Notes", "Status", "Created_At", "Created_By", "Is_Deleted"
];

var STOCK_CONTRACT_VERSION = "WH_STOCK_MOVEMENT_CONTRACT_V2";
var STOCK_COST_VERSION = "WH_COGS_COST_SNAPSHOT_V1";
var STOCK_DIRECTIONS = ["IN", "OUT"];
var STOCK_MOVEMENT_TYPES = [
  "PURCHASE_IN", "SALES_OUT", "SJ_OUT", "OMNI_OUT", "POS_OUT", "RETURN_IN", "RETURN_OUT",
  "PROD_IN", "PROD_USAGE", "INTERNAL_USAGE", "TRANSFER_IN", "TRANSFER_OUT",
  "OPNAME_ADJUSTMENT", "OPNAME", "MANUAL_IN", "MANUAL_OUT", "MANUAL"
];

var STOCK_AUDIT_HEADERS = [
  "Audit_ID", "Timestamp", "Tx_Key", "Movement_ID", "Status", "Created_By", "Notes"
];

var STOCK_OPNAME_HEADERS = [
  "Opname_ID", "Opname_Date", "Item_ID", "Item_Name", "Warehouse_Code", "System_Qty",
  "Physical_Qty", "Diff_Qty", "Reason", "Status", "Created_At", "Created_By", "Posted_Movement_ID", "Notes"
];

var STOCK_CUTOFF_HEADERS = [
  "Cutoff_ID", "Cutoff_Date", "Cost_Period", "Item_ID", "Item_Name", "Warehouse_Code", "Qty_Cutoff",
  "Unit_Cost", "Value_Cutoff", "Cost_Status", "Cost_Source", "Source", "Created_At", "Created_By", "Notes"
];

var STOCK_COST_PERIOD_HEADERS = [
  "Cost_ID", "Period", "Item_ID", "Item_Name", "Unit_Cost_Provisional", "Unit_Cost_Final",
  "Cost_Status", "Source_Module", "Source_ID", "Synced_At", "Synced_By", "Closed_At", "Closed_By", "Notes", "Is_Deleted"
];

var OMNI_ACTION_LOG_HEADERS = [
  "Action_ID", "Tx_Key", "Tanggal", "Source_Date", "Toko", "Item_Name", "Action_Type", "Qty",
  "Source_ID", "Source_Line_ID", "Ref_No", "Batch_ID", "External_Ref", "Notes", "Status",
  "Created_At", "Created_By", "Is_Deleted"
];

var LOG_ERROR_HEADERS = [
  "Error_ID", "Timestamp", "Module_Code", "Function_Name", "Error_Message", "Payload_JSON", "User_Email", "Status"
];

// =========================== WEB APP + SECURITY ===========================

function doGet(e) {
  var auth = ERP_doGetAccess_(e);
  if (!auth.allowed) return ERP_forbiddenOutput_(auth);

  var tpl = HtmlService.createTemplateFromFile('Index');
  tpl.ERP_PASSPORT = auth.passport || ((e && e.parameter && (e.parameter.paspor || e.parameter.passport || e.parameter.token)) || '');
  tpl.ERP_PORTAL_URL = ERP_getPortalUrl_();
  tpl.ERP_USER_EMAIL = auth.email || '';
  tpl.ERP_DISPLAY_NAME = auth.displayName || auth.email || '';
  tpl.GUDANG_BOOTSTRAP = {
    moduleCode: GUDANG_CFG.MODULE_CODE,
    version: GUDANG_CFG.VERSION,
    email: tpl.ERP_USER_EMAIL,
    displayName: tpl.ERP_DISPLAY_NAME,
    passport: tpl.ERP_PASSPORT,
    paspor: tpl.ERP_PASSPORT,
    portalUrl: tpl.ERP_PORTAL_URL
  };

  return tpl.evaluate()
    .setTitle('ERP Gudang - CV KIRAL')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

function hasGudangAccess_(email) {
  try {
    var master = openMaster_();
    var sh = master.getSheetByName("Master_User");
    if (!sh || sh.getLastRow() <= 1) return true;

    var t = readTable_(master, "Master_User", null, { noCreate: true });
    var cEmail = col_(t.info, ["Email", "User_Email", "Email User"], -1);
    var cStatus = col_(t.info, ["Status"], -1);
    var hasConfiguredUser = false;

    for (var i = 0; i < t.rows.length; i++) {
      var rowEmail = cEmail !== -1 ? String(t.rows[i][cEmail] || "").trim().toLowerCase() : "";
      var status = cStatus !== -1 ? String(t.rows[i][cStatus] || "ACTIVE").trim().toUpperCase() : "ACTIVE";
      if (rowEmail) hasConfiguredUser = true;
      if (email && rowEmail === email && status !== "INACTIVE" && status !== "NONAKTIF" && status !== "BLOCKED") return true;
    }
    return !hasConfiguredUser;
  } catch (e) {
    return true;
  }
}

// =========================== SETUP ===========================

function SETUP_installGudangStockMovementAdapter() {
  var ss = getActiveGudang_();
  ensureSheetWithHeaders_(ss, SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS);
  ensureSheetWithHeaders_(ss, SHEET_STOCK_AUDIT, STOCK_AUDIT_HEADERS);
  ensureSheetWithHeaders_(ss, SHEET_STOCK_OPNAME, STOCK_OPNAME_HEADERS);
  ensureSheetWithHeaders_(ss, SHEET_STOCK_CUTOFF, STOCK_CUTOFF_HEADERS);
  ensureSheetWithHeaders_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS);
  ensureSheetWithHeaders_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS);
  try {
    ensureSheetWithHeaders_(openMaster_(), "Log_Error", LOG_ERROR_HEADERS);
    updateMasterModuleLink_("WH", "Gudang", ss.getId(), ss.getUrl(), "NEW_CORE");
  } catch (e) {}
  return TEST_gudangStockMovementAdapter();
}

function TEST_gudangStockMovementAdapter() {
  var out = { success: true, version: GUDANG_CFG.VERSION, contractVersion: STOCK_CONTRACT_VERSION, checks: [] };
  try {
    var ss = getActiveGudang_();
    ensureSheetWithHeaders_(ss, SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS);
    requireHeaders_(ss, SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS);
    out.checks.push("✅ Stock_Movement aman dan siap jadi sumber stok + contract v2 + COGS snapshot.");

    requireHeaders_(ss, SHEET_STOCK_AUDIT, STOCK_AUDIT_HEADERS);
    out.checks.push("✅ Stock_Audit aman.");

    ensureSheetWithHeaders_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS);
    requireHeaders_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS);
    out.checks.push("✅ Stock_Cost_Period aman untuk HPP provisional/final dari Produksi/Finance.");

    ensureSheetWithHeaders_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS);
    requireHeaders_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS);
    out.checks.push("✅ Omni_Action_Log aman untuk aksi batal/tidak pack.");

    var master = openMaster_();
    requireHeaders_(master, "Master_Item", ["Item_ID", "Item_Name", "Item_Type", "Category", ["Sub_Category", "Subcategory", "Sub Category", "Sub-Kategori", "Sub Kategori"], "Min_Stock"]);
    out.checks.push("✅ Master_Item terbaca dari Master Database.");

    var omniInfo = getModuleInfo_("OMNI");
    if (omniInfo && omniInfo.Spreadsheet_ID) {
      out.checks.push("✅ Link Omnichannel ditemukan di Master_Module.");
    } else {
      out.checks.push("⚠️ Link Omnichannel belum ada. Tarikan Omni akan kosong sampai Master_Module OMNI diisi.");
    }

    out.gudangSpreadsheetId = ss.getId();
    out.masterSpreadsheetId = MASTER_SPREADSHEET_ID;
  } catch (e) {
    out.success = false;
    out.error = e.message;
    logError_("TEST_gudangStockMovementAdapter", e, {});
  }
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

// =========================== CORE HELPERS ===========================

function openMaster_() { return SpreadsheetApp.openById(MASTER_SPREADSHEET_ID); }
function getActiveGudang_() { return SpreadsheetApp.getActiveSpreadsheet(); }
function userEmail_() { return Session.getActiveUser().getEmail() || "unknown"; }
function nowText_() { return Utilities.formatDate(new Date(), TZ, "dd/MM/yyyy HH:mm:ss"); }
function dateOnlyText_(d) { var x = parseDate_(d) || new Date(); return Utilities.formatDate(x, TZ, "dd/MM/yyyy"); }
function uuid_(prefix) { return prefix + "-" + Utilities.getUuid().slice(0, 8).toUpperCase(); }

function escapeServer_(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;").replace(/'/g, "&#39;");
}

function normalizeHeader_(h) { return String(h || "").trim().toLowerCase(); }

function getHeaderInfo_(sheet) {
  var lastCol = Math.max(1, sheet.getLastColumn());
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(function(h) { return String(h || "").trim(); });
  var map = {};
  headers.forEach(function(h, i) { if (h) map[normalizeHeader_(h)] = i; });
  return { headers: headers, map: map };
}

function col_(info, names, fallback) {
  names = Array.isArray(names) ? names : [names];
  for (var i = 0; i < names.length; i++) {
    var key = normalizeHeader_(names[i]);
    if (info.map[key] !== undefined) return info.map[key];
  }
  return fallback;
}

function ensureSheetWithHeaders_(ss, sheetName, headers) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) sh = ss.insertSheet(sheetName);
  if (sh.getLastRow() === 0) sh.appendRow(headers);

  var info = getHeaderInfo_(sh);
  var existing = info.headers.slice();
  var changed = false;

  headers.forEach(function(h) {
    if (col_(info, h, -1) === -1) {
      existing.push(h);
      changed = true;
    }
  });

  if (changed || sh.getLastRow() === 1) {
    sh.getRange(1, 1, 1, existing.length).setValues([existing]);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, existing.length).setFontWeight("bold");
  }
  return sh;
}

function requireHeaders_(ss, sheetName, headers) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) throw new Error("Sheet tidak ditemukan: " + sheetName);
  var info = getHeaderInfo_(sh);
  var missing = [];
  (headers || []).forEach(function(h) {
    var aliases = Array.isArray(h) ? h : [h];
    if (col_(info, aliases, -1) === -1) missing.push(aliases[0]);
  });
  if (missing.length) throw new Error("Header kurang di " + sheetName + ": " + missing.join(", "));
  return true;
}

function readTable_(ss, sheetName, requiredHeaders, opt) {
  opt = opt || {};
  var sh = ss.getSheetByName(sheetName);
  if (!sh) {
    if (opt.noCreate) return { sheet: null, info: { headers: [], map: {} }, rows: [], values: [] };
    sh = ensureSheetWithHeaders_(ss, sheetName, requiredHeaders || []);
  }
  if (requiredHeaders && requiredHeaders.length) requireHeaders_(ss, sheetName, requiredHeaders);

  var info = getHeaderInfo_(sh);
  var lastRow = sh.getLastRow();
  var lastCol = sh.getLastColumn();
  var rows = lastRow > 1 ? sh.getRange(2, 1, lastRow - 1, lastCol).getValues() : [];
  return { sheet: sh, info: info, rows: rows, values: rows, lastRow: lastRow, lastCol: lastCol };
}

function appendRowsByHeader_(ss, sheetName, headers, objects) {
  if (!objects || !objects.length) return 0;
  var sh = ensureSheetWithHeaders_(ss, sheetName, headers);
  var info = getHeaderInfo_(sh);
  var rows = objects.map(function(obj) {
    return info.headers.map(function(h) { return obj[h] !== undefined ? obj[h] : ""; });
  });
  for (var i = 0; i < rows.length; i += WRITE_CHUNK_SIZE) {
    var chunk = rows.slice(i, i + WRITE_CHUNK_SIZE);
    sh.getRange(sh.getLastRow() + 1, 1, chunk.length, info.headers.length).setValues(chunk);
  }
  return objects.length;
}

function toNumber_(value) {
  if (value === null || value === undefined || value === "") return 0;
  if (typeof value === "number") return isFinite(value) ? value : 0;
  var s = String(value).trim();
  if (!s) return 0;
  s = s.replace(/[Rp\s]/gi, "").replace(/[^\d,.\-]/g, "");
  if (!s || s === "-" || s === "." || s === ",") return 0;
  var lastComma = s.lastIndexOf(",");
  var lastDot = s.lastIndexOf(".");
  if (lastComma !== -1 && lastDot !== -1) {
    var dec = lastComma > lastDot ? "," : ".";
    var thou = dec === "," ? "." : ",";
    s = s.split(thou).join("").replace(dec, ".");
    return parseFloat(s) || 0;
  }
  if (lastComma !== -1) {
    var cp = s.split(",");
    if (cp.length === 2 && (cp[1] || "").length <= 2) s = cp[0] + "." + cp[1];
    else s = cp.join("");
    return parseFloat(s) || 0;
  }
  if (lastDot !== -1) {
    var dp = s.split(".");
    if (dp.length > 2) s = dp.join("");
    return parseFloat(s) || 0;
  }
  return parseFloat(s) || 0;
}

function parseDate_(value) {
  if (!value) return null;
  if (value instanceof Date && !isNaN(value.getTime())) return value;
  var s = String(value).trim();
  if (!s) return null;

  var m1 = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})(?:\s+(\d{1,2}):(\d{1,2}))?/);
  if (m1) return new Date(parseInt(m1[3], 10), parseInt(m1[2], 10) - 1, parseInt(m1[1], 10), parseInt(m1[4] || "0", 10), parseInt(m1[5] || "0", 10));

  var m2 = s.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})(?:\s+(\d{1,2}):(\d{1,2}))?/);
  if (m2) return new Date(parseInt(m2[1], 10), parseInt(m2[2], 10) - 1, parseInt(m2[3], 10), parseInt(m2[4] || "0", 10), parseInt(m2[5] || "0", 10));

  var d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function dateKey_(value) {
  var d = parseDate_(value);
  if (!d) return "";
  return Utilities.formatDate(d, TZ, "yyyy-MM-dd");
}

function formatDateDisplay_(value) {
  var d = parseDate_(value);
  if (!d) return String(value || "");
  return Utilities.formatDate(d, TZ, "dd/MM/yyyy");
}

function getCacheJson_(key) {
  try {
    var raw = CacheService.getScriptCache().get(key);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

function putCacheJson_(key, val, seconds) {
  try { CacheService.getScriptCache().put(key, JSON.stringify(val), seconds || CACHE_SECONDS); } catch (e) {}
}

function clearMasterCache_() {
  try {
    CacheService.getScriptCache().remove("MASTER_MODULES_V1");
    CacheService.getScriptCache().remove("MASTER_MODULES_V2");
    CacheService.getScriptCache().remove("MASTER_ITEMS_V1");
    CacheService.getScriptCache().remove("WH_MASTER_SKU_MAP_V14");
    CacheService.getScriptCache().remove("WH_MASTER_SKU_MAP_V21");
  } catch(e) {}
}

function logError_(fn, error, payload) {
  try {
    var row = {
      Error_ID: uuid_("ERR"),
      Timestamp: nowText_(),
      Module_Code: "WH",
      Function_Name: fn,
      Error_Message: error && error.message ? error.message : String(error),
      Payload_JSON: JSON.stringify(payload || {}).slice(0, 45000),
      User_Email: userEmail_(),
      Status: "OPEN"
    };
    appendRowsByHeader_(openMaster_(), "Log_Error", LOG_ERROR_HEADERS, [row]);
  } catch (e) {}
}

// =========================== MASTER + MODULES ===========================

function getMasterItems_() {
  var cached = getCacheJson_("MASTER_ITEMS_V1");
  if (cached) return cached;

  var t = readTable_(openMaster_(), "Master_Item", ["Item_ID", "Item_Name", "Item_Type", "Category", ["Sub_Category", "Subcategory", "Sub Category", "Sub-Kategori", "Sub Kategori"], "Min_Stock"], { noCreate: true });
  var cId = col_(t.info, "Item_ID", -1);
  var cCode = col_(t.info, "Item_Code", -1);
  var cName = col_(t.info, "Item_Name", -1);
  var cType = col_(t.info, "Item_Type", -1);
  var cCat = col_(t.info, "Category", -1);
  var cSub = col_(t.info, ["Sub_Category", "Subcategory", "Sub Category", "Sub-Kategori", "Sub Kategori"], -1);
  var cUnit = col_(t.info, "Unit", -1);
  var cMin = col_(t.info, "Min_Stock", -1);
  var cCost = col_(t.info, "Default_Cost", -1);
  var cStatus = col_(t.info, "Status", -1);

  var out = [];
  t.rows.forEach(function(r) {
    var status = cStatus !== -1 ? String(r[cStatus] || "ACTIVE").trim().toUpperCase() : "ACTIVE";
    if (status === "INACTIVE" || status === "NONAKTIF" || status === "BLOCKED") return;
    var id = cId !== -1 ? String(r[cId] || "").trim() : "";
    var name = cName !== -1 ? String(r[cName] || "").trim() : "";
    if (!id || !name) return;
    out.push({
      Item_ID: id,
      Item_Code: cCode !== -1 ? String(r[cCode] || "").trim() : "",
      Item_Name: name,
      Item_Type: cType !== -1 ? String(r[cType] || "").trim().toUpperCase() : "",
      Category: cCat !== -1 ? String(r[cCat] || "").trim() : "Umum",
      Sub_Category: cSub !== -1 ? String(r[cSub] || "").trim() : "Umum",
      Subcategory: cSub !== -1 ? String(r[cSub] || "").trim() : "Umum",
      Unit: cUnit !== -1 ? String(r[cUnit] || "").trim() : "Pcs",
      Min_Stock: cMin !== -1 ? toNumber_(r[cMin]) : 0,
      Default_Cost: cCost !== -1 ? toNumber_(r[cCost]) : 0
    });
  });
  putCacheJson_("MASTER_ITEMS_V1", out);
  return out;
}

function buildItemLookup_() {
  var items = getMasterItems_();
  var byId = {}, byName = {}, bySub = {};
  items.forEach(function(it) {
    byId[it.Item_ID] = it;
    byName[it.Item_Name] = it;
    var key = String(it.Sub_Category || "").trim();
    if (key && key !== "Umum") {
      if (!bySub[key]) bySub[key] = [];
      bySub[key].push(it);
    }
  });
  return { items: items, byId: byId, byName: byName, bySub: bySub };
}

function normalizeSkuKey_(value) {
  return String(value || "").trim().toUpperCase().replace(/\s+/g, " ");
}


function putWhSkuMapKey_(map, key, payload) {
  key = normalizeSkuKey_(key);
  if (!key) return;
  var prev = map[key];
  if (prev && prev.item && prev.item !== payload.item) {
    map[key] = { __ambiguous: true, item: "", isi: 1, mappingType: "AMBIGUOUS", source: "AMBIGUOUS" };
    return;
  }
  if (!prev || !prev.__ambiguous) map[key] = payload;
}

function getWhSkuMapValue_(map, keys) {
  for (var i = 0; i < (keys || []).length; i++) {
    var k = normalizeSkuKey_(keys[i]);
    if (!k) continue;
    var found = map[k];
    if (found && !found.__ambiguous && found.item) return found;
  }
  return null;
}

function firstNonEmptyText_(values) {
  for (var i = 0; i < values.length; i++) {
    var v = values[i];
    if (v !== null && v !== undefined && String(v).trim() !== "") return String(v).trim();
  }
  return "";
}

function firstPositiveNumber_(values) {
  for (var i = 0; i < values.length; i++) {
    var n = toNumber_(values[i]);
    if (n > 0) return n;
  }
  return 0;
}


// Mapping cadangan untuk Gudang: kalau Omni_Order masih kosong di kolom Item Gudang / Qty Gudang,
// Gudang tetap bisa menerjemahkan SKU / produk+varian dari Master_SKU_Map tanpa rewrite ribuan baris Omni_Order.
function getWhMasterSkuMap_() {
  var cached = getCacheJson_("WH_MASTER_SKU_MAP_V21");
  if (cached) return cached;

  var map = {};
  try {
    var lookup = buildItemLookup_();
    var t = readTable_(openMaster_(), "Master_SKU_Map", null, { noCreate: true });
    if (!t.sheet) {
      putCacheJson_("WH_MASTER_SKU_MAP_V21", map);
      return map;
    }

    var cSku = col_(t.info, ["Marketplace_SKU", "SKU BigSeller", "SKU", "SKU_Marketplace", "Nomor Referensi SKU"], -1);
    var cProduct = col_(t.info, ["Marketplace_Product_Name", "Product_Name", "Nama Produk", "Product Name", "Nama Produk BigSeller"], -1);
    var cVariation = col_(t.info, ["Marketplace_Variation", "Variation", "Variasi", "Nama Variasi", "Varian", "Variant"], -1);
    var cItemId = col_(t.info, ["Internal_Item_ID", "Item_ID", "Target_Item_ID"], -1);
    var cItemName = col_(t.info, ["Internal_Item_Name", "Item Gudang", "Item_Gudang", "Nama Item", "Target_Item_Name"], -1);
    var cTargetSub = col_(t.info, ["Target_Sub_Category", "Mapped_Sub_Category", "Sub_Category", "Subcategory", "Sub Category", "Sub Kategori", "Sub-Kategori"], -1);
    var cTargetCat = col_(t.info, ["Target_Category", "Mapped_Category", "Category", "Kategori"], -1);
    var cConv = col_(t.info, ["Conversion_Qty", "Conversion Qty", "Isi", "Isi Paket", "Qty Konversi"], -1);
    var cMapType = col_(t.info, ["Mapping_Type", "Map_Type", "Tipe Mapping"], -1);
    var cStatus = col_(t.info, ["Status"], -1);

    t.rows.forEach(function(r) {
      var status = cStatus !== -1 ? String(r[cStatus] || "ACTIVE").trim().toUpperCase() : "ACTIVE";
      if (status === "INACTIVE" || status === "NONAKTIF" || status === "BLOCKED") return;

      var sku = cSku !== -1 ? String(r[cSku] || "").trim() : "";
      var product = cProduct !== -1 ? String(r[cProduct] || "").trim() : "";
      var variation = cVariation !== -1 ? String(r[cVariation] || "").trim() : "";
      var mapType = cMapType !== -1 ? String(r[cMapType] || "").trim().toUpperCase() : "";
      var itemName = cItemName !== -1 ? String(r[cItemName] || "").trim() : "";
      var itemId = cItemId !== -1 ? String(r[cItemId] || "").trim() : "";
      var targetSub = cTargetSub !== -1 ? String(r[cTargetSub] || "").trim() : "";
      var targetCat = cTargetCat !== -1 ? String(r[cTargetCat] || "").trim() : "";

      var target = "";
      // Untuk paket/bundling/sub-kategori, Gudang butuh nama sub-kategori sebagai induk tarikan.
      if ((mapType.indexOf("SUB") !== -1 || mapType.indexOf("BUNDLE") !== -1 || mapType.indexOf("PAKET") !== -1) && targetSub) target = targetSub;
      if (!target && itemName) target = itemName;
      if (!target && itemId && lookup.byId[itemId]) target = lookup.byId[itemId].Item_Name;
      if (!target && targetSub) target = targetSub;
      if (!target && targetCat) target = targetCat;
      if (!target || target.toUpperCase() === "UNMAPPED") return;

      var payload = {
        item: target,
        isi: cConv !== -1 ? (toNumber_(r[cConv]) || 1) : 1,
        mappingType: mapType || (targetSub && target === targetSub ? "SUB_CATEGORY" : "ITEM"),
        sku: sku,
        product: product,
        variation: variation,
        source: "Master_SKU_Map"
      };

      // Prioritas pencarian Gudang: SKU, SKU+varian, produk+varian, lalu varian saja.
      // Varian saja dipakai untuk kasus SKU marketplace kosong seperti arahan Omni sebelumnya.
      putWhSkuMapKey_(map, sku, payload);
      if (sku && variation) putWhSkuMapKey_(map, sku + "|" + variation, payload);
      if (product && variation) putWhSkuMapKey_(map, product + "|" + variation, payload);
      if (!sku && variation) putWhSkuMapKey_(map, variation, payload);
      if (!sku && product) putWhSkuMapKey_(map, product, payload);
    });
  } catch (e) {
    logError_("getWhMasterSkuMap_", e, {});
  }

  putCacheJson_("WH_MASTER_SKU_MAP_V21", map);
  return map;
}

function parseOmniOrderDateOnly_(value) {
  if (!value) return null;
  if (value instanceof Date && !isNaN(value.getTime())) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  var s = String(value).trim();
  if (!s) return null;
  var datePart = s.split(" ")[0].trim();

  var ymd = datePart.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})$/);
  if (ymd) return new Date(parseInt(ymd[1], 10), parseInt(ymd[2], 10) - 1, parseInt(ymd[3], 10));

  var slash = datePart.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
  if (slash) {
    var a = parseInt(slash[1], 10);
    var b = parseInt(slash[2], 10);
    var y = parseInt(slash[3], 10);
    var d, m;
    if (a > 12) { d = a; m = b; }       // DD/MM/YYYY
    else if (b > 12) { d = b; m = a; }  // M/DD/YYYY
    else { d = b; m = a; }              // Ambigu: BigSeller/GSheet sering tampil M/D/YYYY seperti screenshot
    return new Date(y, m - 1, d);
  }

  var fallback = new Date(s);
  if (isNaN(fallback.getTime())) return null;
  return new Date(fallback.getFullYear(), fallback.getMonth(), fallback.getDate());
}


function extractSpreadsheetId_(value) {
  var s = String(value || "").trim();
  if (!s) return "";
  var m = s.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (m && m[1]) return m[1];
  m = s.match(/[?&]id=([a-zA-Z0-9-_]+)/);
  if (m && m[1]) return m[1];
  if (/^[a-zA-Z0-9-_]{25,}$/.test(s)) return s;
  return "";
}

function isWebAppUrl_(url) {
  var s = String(url || "").trim();
  return /^https:\/\/script\.google\.com\/macros\/s\//i.test(s) || /^https:\/\/script\.googleusercontent\.com\/macros\//i.test(s);
}

function getMasterModules_() {
  var modules = getCacheJson_("MASTER_MODULES_V2");
  if (modules) return modules;
  modules = [];
  try {
    var t = readTable_(openMaster_(), "Master_Module", null, { noCreate: true });
    if (t.sheet) {
      var cCode = col_(t.info, "Module_Code", -1);
      var cName = col_(t.info, "Module_Name", -1);
      var cId = col_(t.info, "Spreadsheet_ID", -1);
      var cSheetUrl = col_(t.info, "Spreadsheet_URL", -1);
      var cWeb = col_(t.info, "Web_App_URL", -1);
      var cStatus = col_(t.info, "Status", -1);
      var cNotes = col_(t.info, "Notes", -1);
      t.rows.forEach(function(r) {
        var rawId = cId !== -1 ? String(r[cId] || "").trim() : "";
        var sheetUrl = cSheetUrl !== -1 ? String(r[cSheetUrl] || "").trim() : "";
        var webUrl = cWeb !== -1 ? String(r[cWeb] || "").trim() : "";
        modules.push({
          Module_Code: cCode !== -1 ? String(r[cCode] || "").trim().toUpperCase() : "",
          Module_Name: cName !== -1 ? String(r[cName] || "").trim() : "",
          Spreadsheet_ID: extractSpreadsheetId_(rawId) || extractSpreadsheetId_(sheetUrl),
          Spreadsheet_ID_Raw: rawId,
          Spreadsheet_URL: sheetUrl,
          Web_App_URL: webUrl,
          Status: cStatus !== -1 ? String(r[cStatus] || "").trim().toUpperCase() : "",
          Notes: cNotes !== -1 ? String(r[cNotes] || "").trim() : ""
        });
      });
    }
  } catch (e) {
    logError_("getMasterModules_", e, {});
  }
  putCacheJson_("MASTER_MODULES_V2", modules);
  return modules;
}

function getModuleInfo_(moduleCodeOrKeyword) {
  var modules = getMasterModules_();
  var key = String(moduleCodeOrKeyword || "").trim().toUpperCase();
  if (!key) return null;
  for (var i = 0; i < modules.length; i++) {
    var m = modules[i];
    if (m.Module_Code === key) return m;
  }
  for (var j = 0; j < modules.length; j++) {
    var n = modules[j];
    if (String(n.Module_Name || "").toUpperCase().indexOf(key) !== -1) return n;
  }
  return null;
}

function getModuleInfoAny_(codes) {
  codes = Array.isArray(codes) ? codes : [codes];
  for (var i = 0; i < codes.length; i++) {
    var info = getModuleInfo_(codes[i]);
    if (info && info.Spreadsheet_ID) return info;
  }
  return null;
}

function getOmniModuleInfo_() {
  var info = getModuleInfoAny_(OMNI_MODULE_CODES);
  if (info) return info;
  var modules = getMasterModules_();
  for (var i = 0; i < modules.length; i++) {
    var name = (String(modules[i].Module_Code || "") + " " + String(modules[i].Module_Name || "")).toUpperCase();
    if ((name.indexOf("OMNI") !== -1 || name.indexOf("RETAIL") !== -1) && modules[i].Spreadsheet_ID) return modules[i];
  }
  return null;
}

function openModuleSpreadsheet_(moduleCode) {
  if (moduleCode === "MASTER") return openMaster_();
  if (moduleCode === "WH") return getActiveGudang_();
  var info = moduleCode === "OMNI" ? getOmniModuleInfo_() : getModuleInfo_(moduleCode);
  if (!info || !info.Spreadsheet_ID) throw new Error("Spreadsheet_ID module " + moduleCode + " belum diset di Master_Module. Header wajib: Module_Code, Module_Name, Spreadsheet_ID, Spreadsheet_URL, Web_App_URL, Status, Notes.");
  return SpreadsheetApp.openById(info.Spreadsheet_ID);
}

function updateMasterModuleLink_(code, name, id, url, status) {
  var ss = openMaster_();
  var sh = ensureSheetWithHeaders_(ss, "Master_Module", ["Module_Code", "Module_Name", "Spreadsheet_ID", "Spreadsheet_URL", "Web_App_URL", "Status", "Notes"]);
  var info = getHeaderInfo_(sh);
  var cCode = col_(info, "Module_Code", -1);
  var cName = col_(info, "Module_Name", -1);
  var cId = col_(info, "Spreadsheet_ID", -1);
  var cUrl = col_(info, "Spreadsheet_URL", -1);
  var cStatus = col_(info, "Status", -1);
  var rows = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues() : [];
  var targetRow = -1;
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i][cCode] || "").trim().toUpperCase() === code) { targetRow = i + 2; break; }
  }
  if (targetRow === -1) {
    var obj = { Module_Code: code, Module_Name: name, Spreadsheet_ID: id, Spreadsheet_URL: url, Status: status, Notes: "Updated by Gudang v2.2" };
    appendRowsByHeader_(ss, "Master_Module", ["Module_Code", "Module_Name", "Spreadsheet_ID", "Spreadsheet_URL", "Web_App_URL", "Status", "Notes"], [obj]);
  } else {
    if (cName !== -1) sh.getRange(targetRow, cName + 1).setValue(name);
    if (cId !== -1) sh.getRange(targetRow, cId + 1).setValue(id);
    if (cUrl !== -1) sh.getRange(targetRow, cUrl + 1).setValue(url);
    if (cStatus !== -1) sh.getRange(targetRow, cStatus + 1).setValue(status);
  }
  clearMasterCache_();
}

// =========================== MENU LINK ===========================
// Implementasi aktif berada pada Flow Security block di bagian akhir file.

// =========================== COST / COGS HELPERS ===========================

function normalizeCostPeriod_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) return Utilities.formatDate(value, TZ, "yyyy-MM");
  var s = normalizeStockText_(value || "");
  if (!s) return Utilities.formatDate(new Date(), TZ, "yyyy-MM");
  var m = s.match(/^(\d{4})[-\/](\d{1,2})(?:[-\/]\d{1,2})?/);
  if (m) return m[1] + "-" + ("0" + m[2]).slice(-2);
  var d = parseDate_(s);
  return d ? Utilities.formatDate(d, TZ, "yyyy-MM") : Utilities.formatDate(new Date(), TZ, "yyyy-MM");
}

function normalizeCostStatus_(value, fallback) {
  var s = normalizeStockCode_(value || fallback || "PROVISIONAL");
  if (["FINAL", "CLOSED", "LOCKED"].indexOf(s) !== -1) return "FINAL";
  if (["PROVISIONAL", "ESTIMATE", "ESTIMATED", "OPEN", "DRAFT"].indexOf(s) !== -1) return "PROVISIONAL";
  return fallback || "PROVISIONAL";
}

function readStockCostPeriod_() {
  var ss = getActiveGudang_();
  ensureSheetWithHeaders_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS);
  var t = readTable_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS, { noCreate: false });
  var info = t.info;
  var c = {
    costId: col_(info, "Cost_ID", -1), period: col_(info, "Period", -1), itemId: col_(info, "Item_ID", -1), itemName: col_(info, "Item_Name", -1),
    prov: col_(info, "Unit_Cost_Provisional", -1), final: col_(info, "Unit_Cost_Final", -1), status: col_(info, "Cost_Status", -1),
    sourceModule: col_(info, "Source_Module", -1), sourceId: col_(info, "Source_ID", -1), syncedAt: col_(info, "Synced_At", -1), syncedBy: col_(info, "Synced_By", -1),
    closedAt: col_(info, "Closed_At", -1), closedBy: col_(info, "Closed_By", -1), notes: col_(info, "Notes", -1), deleted: col_(info, "Is_Deleted", -1)
  };
  var rows = [];
  var byKey = {}, byNameKey = {};
  t.rows.forEach(function(r, idx) {
    var del = c.deleted !== -1 ? normalizeStockCode_(r[c.deleted]) : "";
    if (del === "TRUE" || del === "YA" || del === "1") return;
    var period = c.period !== -1 ? normalizeCostPeriod_(r[c.period]) : "";
    var itemId = c.itemId !== -1 ? normalizeStockText_(r[c.itemId]) : "";
    var itemName = c.itemName !== -1 ? normalizeStockText_(r[c.itemName]) : "";
    if (!period || (!itemId && !itemName)) return;
    var status = normalizeCostStatus_(c.status !== -1 ? r[c.status] : "PROVISIONAL", "PROVISIONAL");
    var obj = {
      __rowNumber: idx + 2,
      Cost_ID: c.costId !== -1 ? normalizeStockText_(r[c.costId]) : "",
      Period: period,
      Item_ID: itemId,
      Item_Name: itemName,
      Unit_Cost_Provisional: c.prov !== -1 ? toNumber_(r[c.prov]) : 0,
      Unit_Cost_Final: c.final !== -1 ? toNumber_(r[c.final]) : 0,
      Cost_Status: status,
      Source_Module: c.sourceModule !== -1 ? normalizeStockCode_(r[c.sourceModule]) : "",
      Source_ID: c.sourceId !== -1 ? normalizeStockText_(r[c.sourceId]) : "",
      Synced_At: c.syncedAt !== -1 ? r[c.syncedAt] : "",
      Synced_By: c.syncedBy !== -1 ? normalizeStockText_(r[c.syncedBy]) : "",
      Closed_At: c.closedAt !== -1 ? r[c.closedAt] : "",
      Closed_By: c.closedBy !== -1 ? normalizeStockText_(r[c.closedBy]) : "",
      Notes: c.notes !== -1 ? normalizeStockText_(r[c.notes]) : ""
    };
    rows.push(obj);
    var key = itemId + "|" + period;
    var nameKey = normalizeStockText_(itemName).toUpperCase() + "|" + period;
    function prefer(cur, next) {
      if (!cur) return next;
      if (cur.Cost_Status !== "FINAL" && next.Cost_Status === "FINAL") return next;
      if ((cur.Unit_Cost_Final || 0) <= 0 && (next.Unit_Cost_Final || 0) > 0) return next;
      return next.__rowNumber > cur.__rowNumber ? next : cur;
    }
    if (itemId) byKey[key] = prefer(byKey[key], obj);
    if (itemName) byNameKey[nameKey] = prefer(byNameKey[nameKey], obj);
  });
  return { rows: rows, byKey: byKey, byNameKey: byNameKey, headers: info.headers, info: info, sheet: t.sheet };
}

function findStockCostRow_(costData, item, period) {
  costData = costData || readStockCostPeriod_();
  period = normalizeCostPeriod_(period || new Date());
  var itemId = item && item.Item_ID ? item.Item_ID : "";
  var itemName = item && item.Item_Name ? item.Item_Name : "";
  var row = itemId ? costData.byKey[itemId + "|" + period] : null;
  if (!row && itemName) row = costData.byNameKey[normalizeStockText_(itemName).toUpperCase() + "|" + period];
  if (row) return row;

  // Fallback ringan: ambil cost periode terakhir sebelum/sama dengan periode target untuk item yang sama.
  var candidates = (costData.rows || []).filter(function(x) {
    var matchItem = (itemId && x.Item_ID === itemId) || (itemName && normalizeStockText_(x.Item_Name).toUpperCase() === normalizeStockText_(itemName).toUpperCase());
    return matchItem && x.Period <= period;
  }).sort(function(a, b) { return a.Period < b.Period ? 1 : -1; });
  return candidates[0] || null;
}

function resolveMovementCost_(input, item, contract, opt) {
  opt = opt || {};
  var sourceDate = (contract && contract.Source_Date) || input.Source_Date || input.Tanggal || new Date();
  var period = normalizeCostPeriod_(input.Cost_Period || sourceDate || new Date());
  var qty = contract && contract.Qty ? contract.Qty : toNumber_(input.Qty || 0);
  var costData = opt.costData || readStockCostPeriod_();
  var costRow = findStockCostRow_(costData, item, period);

  var explicitStatus = input.Cost_Status ? normalizeCostStatus_(input.Cost_Status, "PROVISIONAL") : "";
  var inputFinal = toNumber_(input.Unit_Cost_Final || input.Final_Unit_Cost || 0);
  var inputProv = toNumber_(input.Unit_Cost_Provisional || input.Provisional_Unit_Cost || 0);
  var inputUnit = toNumber_(input.Unit_Cost || input.HPP || input.COGS_Unit_Cost || 0);

  var rowStatus = costRow ? normalizeCostStatus_(costRow.Cost_Status, "PROVISIONAL") : "PROVISIONAL";
  var rowFinal = costRow ? toNumber_(costRow.Unit_Cost_Final) : 0;
  var rowProv = costRow ? toNumber_(costRow.Unit_Cost_Provisional) : 0;

  var status = explicitStatus || (rowStatus === "FINAL" && rowFinal > 0 ? "FINAL" : "PROVISIONAL");
  var provCost = inputProv || inputUnit || rowProv || rowFinal || item.Default_Cost || 0;
  var finalCost = inputFinal || (status === "FINAL" ? (inputUnit || rowFinal || rowProv || item.Default_Cost || 0) : 0);

  // Kalau input Unit_Cost dikirim dengan status FINAL, anggap sebagai final snapshot.
  if (!finalCost && explicitStatus === "FINAL" && inputUnit > 0) finalCost = inputUnit;
  if (finalCost > 0) status = "FINAL";

  var unitCost = status === "FINAL" ? finalCost : provCost;
  var source = "MASTER_ITEM";
  if (costRow) source = (costRow.Source_Module || "STOCK_COST_PERIOD") + (costRow.Source_ID ? "|" + costRow.Source_ID : "");
  if (inputUnit || inputProv || inputFinal) source = normalizeStockText_(input.Cost_Source || input.Source_Module || "INPUT_COST");

  return {
    Cost_Period: period,
    Cost_Status: status,
    Unit_Cost: unitCost,
    Unit_Cost_Provisional: provCost,
    Value_Provisional: qty * provCost,
    Unit_Cost_Final: status === "FINAL" ? finalCost : "",
    Value_Final: status === "FINAL" ? qty * finalCost : "",
    Cost_Source: source,
    Cost_Synced_At: nowText_(),
    Closed_At: status === "FINAL" ? (input.Closed_At || "") : "",
    Closed_By: status === "FINAL" ? (input.Closed_By || "") : ""
  };
}

function cogsMovementType_(type) {
  type = normalizeStockCode_(type || "");
  return ["OMNI_OUT", "SALES_OUT", "SJ_OUT", "POS_OUT"].indexOf(type) !== -1;
}

// =========================== STOCK ENGINE ===========================

function normalizeStockText_(value) {
  return String(value === null || value === undefined ? "" : value).trim();
}

function normalizeStockCode_(value) {
  return normalizeStockText_(value).toUpperCase().replace(/\s+/g, "_");
}

function stockValueForKey_(value) {
  return normalizeStockText_(value).toUpperCase().replace(/\s+/g, " ");
}

function buildStockTxKey_(input, item, opt) {
  opt = opt || {};
  if (input && input.Tx_Key) return normalizeStockText_(input.Tx_Key);

  var sourceModule = normalizeStockCode_(input.Source_Module || "WH");
  var movementType = normalizeStockCode_(input.Movement_Type || "MANUAL");
  var sourceId = normalizeStockText_(input.Source_ID || "");
  var sourceLine = normalizeStockText_(input.Source_Line_ID || "");
  var refNo = normalizeStockText_(input.Ref_No || "");
  var direction = normalizeStockCode_(input.Direction || "");
  var itemId = item && item.Item_ID ? item.Item_ID : normalizeStockText_(input.Item_ID || input.Item_Name || "");
  var sourceDate = normalizeDateKeyForWarehouse_(input.Source_Date || input.Tanggal || "") || normalizeStockText_(input.Source_Date || input.Tanggal || "");

  // Untuk mutasi manual/opname lama, biarkan unique supaya user bisa input beberapa mutasi dengan nilai sama.
  var manualNoStableSource = sourceModule === "WH" && !sourceId && !sourceLine && !refNo;
  if (manualNoStableSource) return normalizeStockText_(input.Movement_ID || uuid_("TX"));

  return [
    STOCK_CONTRACT_VERSION,
    sourceModule,
    movementType,
    sourceId,
    sourceLine,
    refNo,
    direction,
    itemId,
    sourceDate,
    String(toNumber_(input.Qty || 0))
  ].map(stockValueForKey_).join("|");
}

function ensureStockContractInput_(input, item, idx) {
  input = input || {};
  var dir = normalizeStockCode_(input.Direction || "");
  if (STOCK_DIRECTIONS.indexOf(dir) === -1) throw new Error("Direction harus IN/OUT.");

  var qty = toNumber_(input.Qty);
  if (qty <= 0) throw new Error("Qty harus lebih dari 0.");

  var type = normalizeStockCode_(input.Movement_Type || "MANUAL");
  var sourceModule = normalizeStockCode_(input.Source_Module || "WH");
  var movementId = normalizeStockText_(input.Movement_ID || uuid_("SM"));
  var sourceDate = normalizeDateKeyForWarehouse_(input.Source_Date || input.Tanggal || "");
  var txKey = buildStockTxKey_(Object.assign({}, input, { Direction: dir, Movement_Type: type, Source_Module: sourceModule, Movement_ID: movementId, Source_Date: sourceDate }), item, { index: idx || 0 });

  return {
    Movement_ID: movementId,
    Tx_Key: txKey,
    Direction: dir,
    Movement_Type: type,
    Source_Module: sourceModule,
    Qty: qty,
    Source_Date: sourceDate,
    Source_ID: normalizeStockText_(input.Source_ID || ""),
    Source_Line_ID: normalizeStockText_(input.Source_Line_ID || ""),
    Ref_No: normalizeStockText_(input.Ref_No || ""),
    Batch_ID: normalizeStockText_(input.Batch_ID || ""),
    External_Ref: normalizeStockText_(input.External_Ref || ""),
    Status: normalizeStockText_(input.Status || "POSTED") || "POSTED"
  };
}

function readStockMovementKeySet_() {
  var sh = getActiveGudang_().getSheetByName(SHEET_STOCK_MOVEMENT);
  if (!sh || sh.getLastRow() < 2) return {};
  ensureSheetWithHeaders_(getActiveGudang_(), SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS);
  var info = getHeaderInfo_(sh);
  var cTx = col_(info, "Tx_Key", -1);
  var cMov = col_(info, "Movement_ID", -1);
  var cDeleted = col_(info, "Is_Deleted", -1);
  var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var out = {};
  vals.forEach(function(r) {
    var del = cDeleted !== -1 ? normalizeStockCode_(r[cDeleted]) : "";
    if (del === "TRUE" || del === "YA" || del === "1") return;
    var tx = cTx !== -1 ? normalizeStockText_(r[cTx]) : "";
    var mov = cMov !== -1 ? normalizeStockText_(r[cMov]) : "";
    if (tx) out[tx] = true;
    if (mov) out["MOVEMENT_ID|" + mov] = true;
  });
  return out;
}

function parseOmniSourceId_(sourceId) {
  var parts = normalizeStockText_(sourceId).split("|");
  if (parts.length >= 3 && normalizeStockCode_(parts[0]) === "OMNI") {
    var dateKey = normalizeDateKeyForWarehouse_(parts[1]) || normalizeStockText_(parts[1]);
    return {
      dateKey: dateKey,
      tgl: dateKey ? displayDateFromKey_(dateKey) : normalizeStockText_(parts[1]),
      toko: normalizeStockText_(parts.slice(2).join("|"))
    };
  }
  return { dateKey: "", tgl: "", toko: "" };
}

function buildOmniSourceId_(tglKey, toko) {
  return "OMNI|" + normalizeStockText_(tglKey) + "|" + normalizeStockText_(toko || "Toko Online");
}

function buildOmniSourceLine_(mode, groupName, itemName) {
  mode = normalizeStockCode_(mode || "ITEM");
  if (mode === "BUNDLE" || mode === "SUB_CATEGORY") return "BUNDLE|" + normalizeStockText_(groupName) + "|" + normalizeStockText_(itemName || "");
  return "ITEM|" + normalizeStockText_(groupName || itemName || "");
}

function parseOmniSourceLine_(line, refNo) {
  var s = normalizeStockText_(line);
  var parts = s.split("|");
  var ref = normalizeStockCode_(refNo || "");
  if (parts.length >= 2 && normalizeStockCode_(parts[0]) === "ITEM") return { mode: "ITEM", item: normalizeStockText_(parts.slice(1).join("|")), group: "" };
  if (parts.length >= 2 && normalizeStockCode_(parts[0]) === "BUNDLE") return { mode: "BUNDLE", group: normalizeStockText_(parts[1]), item: normalizeStockText_(parts.slice(2).join("|")) };
  if (ref.indexOf("BUNDLE") !== -1) return { mode: "BUNDLE", group: s, item: "" };
  return { mode: "ITEM", item: s, group: "" };
}

function readStockMovements_() {
  var ss = getActiveGudang_();
  ensureSheetWithHeaders_(ss, SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS);
  var t = readTable_(ss, SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS, { noCreate: false });
  var info = t.info;
  var c = {
    id: col_(info, "Movement_ID", -1), tx: col_(info, "Tx_Key", -1), tgl: col_(info, "Tanggal", -1), sourceDate: col_(info, "Source_Date", -1),
    itemId: col_(info, "Item_ID", -1), itemName: col_(info, "Item_Name", -1), itemCat: col_(info, "Item_Category", -1), itemType: col_(info, "Item_Type", -1), unit: col_(info, "Unit", -1),
    wh: col_(info, "Warehouse_Code", -1), dir: col_(info, "Direction", -1), type: col_(info, "Movement_Type", -1), qty: col_(info, "Qty", -1),
    cost: col_(info, "Unit_Cost", -1), costPeriod: col_(info, "Cost_Period", -1), costStatus: col_(info, "Cost_Status", -1),
    unitCostProv: col_(info, "Unit_Cost_Provisional", -1), valueProv: col_(info, "Value_Provisional", -1), unitCostFinal: col_(info, "Unit_Cost_Final", -1), valueFinal: col_(info, "Value_Final", -1),
    costSource: col_(info, "Cost_Source", -1), costSyncedAt: col_(info, "Cost_Synced_At", -1), closedAt: col_(info, "Closed_At", -1), closedBy: col_(info, "Closed_By", -1),
    sourceModule: col_(info, "Source_Module", -1), sourceId: col_(info, "Source_ID", -1), sourceLine: col_(info, "Source_Line_ID", -1),
    refNo: col_(info, "Ref_No", -1), batchId: col_(info, "Batch_ID", -1), externalRef: col_(info, "External_Ref", -1), notes: col_(info, "Notes", -1), status: col_(info, "Status", -1),
    createdAt: col_(info, "Created_At", -1), createdBy: col_(info, "Created_By", -1), deleted: col_(info, "Is_Deleted", -1)
  };
  var out = [];
  t.rows.forEach(function(r, idx) {
    var del = c.deleted !== -1 ? normalizeStockCode_(r[c.deleted]) : "";
    if (del === "TRUE" || del === "YA" || del === "1") return;
    var itemId = c.itemId !== -1 ? normalizeStockText_(r[c.itemId]) : "";
    var itemName = c.itemName !== -1 ? normalizeStockText_(r[c.itemName]) : "";
    if (!itemId && !itemName) return;
    out.push({
      __rowNumber: idx + 2,
      Movement_ID: c.id !== -1 ? normalizeStockText_(r[c.id]) : "",
      Tx_Key: c.tx !== -1 ? normalizeStockText_(r[c.tx]) : "",
      Tanggal: c.tgl !== -1 ? r[c.tgl] : "",
      Source_Date: c.sourceDate !== -1 ? normalizeStockText_(r[c.sourceDate]) : "",
      Item_ID: itemId,
      Item_Name: itemName,
      Item_Category: c.itemCat !== -1 ? normalizeStockText_(r[c.itemCat]) : "",
      Item_Type: c.itemType !== -1 ? normalizeStockText_(r[c.itemType]) : "",
      Unit: c.unit !== -1 ? normalizeStockText_(r[c.unit]) : "",
      Warehouse_Code: c.wh !== -1 ? normalizeStockText_(r[c.wh] || "MAIN") : "MAIN",
      Direction: c.dir !== -1 ? normalizeStockCode_(r[c.dir]) : "",
      Movement_Type: c.type !== -1 ? normalizeStockCode_(r[c.type]) : "",
      Qty: c.qty !== -1 ? toNumber_(r[c.qty]) : 0,
      Unit_Cost: c.cost !== -1 ? toNumber_(r[c.cost]) : 0,
      Cost_Period: c.costPeriod !== -1 ? normalizeStockText_(r[c.costPeriod]) : "",
      Cost_Status: c.costStatus !== -1 ? normalizeCostStatus_(r[c.costStatus], "PROVISIONAL") : "PROVISIONAL",
      Unit_Cost_Provisional: c.unitCostProv !== -1 ? toNumber_(r[c.unitCostProv]) : 0,
      Value_Provisional: c.valueProv !== -1 ? toNumber_(r[c.valueProv]) : 0,
      Unit_Cost_Final: c.unitCostFinal !== -1 ? toNumber_(r[c.unitCostFinal]) : 0,
      Value_Final: c.valueFinal !== -1 ? toNumber_(r[c.valueFinal]) : 0,
      Cost_Source: c.costSource !== -1 ? normalizeStockText_(r[c.costSource]) : "",
      Cost_Synced_At: c.costSyncedAt !== -1 ? r[c.costSyncedAt] : "",
      Closed_At: c.closedAt !== -1 ? r[c.closedAt] : "",
      Closed_By: c.closedBy !== -1 ? normalizeStockText_(r[c.closedBy]) : "",
      Source_Module: c.sourceModule !== -1 ? normalizeStockCode_(r[c.sourceModule]) : "",
      Source_ID: c.sourceId !== -1 ? normalizeStockText_(r[c.sourceId]) : "",
      Source_Line_ID: c.sourceLine !== -1 ? normalizeStockText_(r[c.sourceLine]) : "",
      Ref_No: c.refNo !== -1 ? normalizeStockText_(r[c.refNo]) : "",
      Batch_ID: c.batchId !== -1 ? normalizeStockText_(r[c.batchId]) : "",
      External_Ref: c.externalRef !== -1 ? normalizeStockText_(r[c.externalRef]) : "",
      Notes: c.notes !== -1 ? normalizeStockText_(r[c.notes]) : "",
      Status: c.status !== -1 ? normalizeStockText_(r[c.status]) : "POSTED",
      Created_At: c.createdAt !== -1 ? r[c.createdAt] : "",
      Created_By: c.createdBy !== -1 ? normalizeStockText_(r[c.createdBy]) : ""
    });
  });
  return out;
}

function getAuditLockMap_() {
  var map = {};
  var t = readTable_(getActiveGudang_(), SHEET_STOCK_AUDIT, STOCK_AUDIT_HEADERS, { noCreate: true });
  var cKey = col_(t.info, "Tx_Key", -1);
  var cStatus = col_(t.info, "Status", -1);
  t.rows.forEach(function(r) {
    var key = cKey !== -1 ? normalizeStockText_(r[cKey]) : "";
    var status = cStatus !== -1 ? normalizeStockCode_(r[cStatus] || "LOCKED") : "LOCKED";
    if (key && status !== "VOID") map[key] = true;
  });
  return map;
}

function buildBalance_(items, movements) {
  var balance = {}, lastCost = {};
  items.forEach(function(it) {
    balance[it.Item_ID] = 0;
    lastCost[it.Item_ID] = toNumber_(it.Default_Cost);
  });
  movements.forEach(function(m) {
    var id = m.Item_ID;
    if (!id || balance[id] === undefined) return;
    if (m.Direction === "IN") balance[id] += m.Qty;
    if (m.Direction === "OUT") balance[id] -= m.Qty;
    if (m.Unit_Cost_Final > 0) lastCost[id] = m.Unit_Cost_Final;
    else if (m.Unit_Cost_Provisional > 0) lastCost[id] = m.Unit_Cost_Provisional;
    else if (m.Unit_Cost > 0) lastCost[id] = m.Unit_Cost;
  });
  return { qty: balance, cost: lastCost };
}

function getCurrentStockQtyForItem_(itemId) {
  var lookup = buildItemLookup_();
  var bal = buildBalance_(lookup.items, readStockMovements_());
  return toNumber_(bal.qty[itemId] || 0);
}


function movementToUi_(m, itemLookup, auditMap) {
  var d = parseDate_(m.Tanggal || m.Created_At) || new Date();
  var txKey = normalizeStockText_(m.Tx_Key || m.Movement_ID || (m.Item_ID + "|" + d.getTime() + "|" + m.Direction + "|" + m.Qty));
  var type = normalizeStockCode_(m.Movement_Type || "");
  var stAudit = "PENDING";
  if (type === "OMNI_OUT" || type === "RETURN_IN" || type === "RETURN_OUT" || type === "OPNAME" || type === "OPNAME_ADJUSTMENT" || type === "INTERNAL_USAGE" || type === "POS_OUT" || type === "PROD_IN" || type === "PROD_USAGE" || type === "PURCHASE_IN" || type === "SALES_OUT" || type === "SJ_OUT") stAudit = "AUTO_OK";
  if (auditMap[txKey] || auditMap[m.Movement_ID]) stAudit = "MANUAL_OK";
  var it = m.Item_ID ? itemLookup.byId[m.Item_ID] : null;
  return {
    tglRawStr: Utilities.formatDate(d, TZ, "yyyy-MM-dd"),
    tgl: Utilities.formatDate(d, TZ, "dd/MM/yyyy"),
    nama: m.Item_Name || (it ? it.Item_Name : "-"),
    jenis: m.Direction,
    qty: m.Qty,
    ket: m.Notes || m.Ref_No || m.Movement_Type || m.Source_Module || "-",
    pic: m.Created_By || m.Source_Module || "Sistem",
    hpp: m.Unit_Cost || (it ? it.Default_Cost : 0),
    stAudit: stAudit,
    txKey: txKey
  };
}

function appendStockMovement_(input) {
  var lookup = buildItemLookup_();
  var item = input.Item_ID ? lookup.byId[input.Item_ID] : null;
  if (!item && input.Item_Name) item = lookup.byName[normalizeStockText_(input.Item_Name)];
  if (!item) throw new Error("Item tidak ditemukan di Master_Item: " + (input.Item_ID || input.Item_Name || ""));

  var contract = ensureStockContractInput_(input, item, 0);

  if (contract.Direction === "OUT" && input.Allow_Negative !== true) {
    var movs = readStockMovements_();
    var bal = buildBalance_(lookup.items, movs);
    var stok = bal.qty[item.Item_ID] || 0;
    if (contract.Qty > stok) throw new Error("Stok tidak cukup. Stok tersedia: " + stok);
  }

  var existing = readStockMovementKeySet_();
  if (existing[contract.Tx_Key] || existing["MOVEMENT_ID|" + contract.Movement_ID]) {
    throw new Error("Stock movement duplikat ditolak. Tx_Key: " + contract.Tx_Key);
  }

  var tgl = input.Tanggal ? parseDate_(input.Tanggal) : new Date();
  var cost = resolveMovementCost_(input, item, contract, {});
  var row = {
    Movement_ID: contract.Movement_ID,
    Tx_Key: contract.Tx_Key,
    Tanggal: dateOnlyText_(tgl),
    Source_Date: contract.Source_Date,
    Item_ID: item.Item_ID,
    Item_Name: item.Item_Name,
    Item_Category: item.Category || "",
    Item_Type: item.Item_Type || "",
    Unit: item.Unit || "",
    Warehouse_Code: input.Warehouse_Code || "MAIN",
    Direction: contract.Direction,
    Movement_Type: contract.Movement_Type,
    Qty: contract.Qty,
    Unit_Cost: cost.Unit_Cost,
    Cost_Period: cost.Cost_Period,
    Cost_Status: cost.Cost_Status,
    Unit_Cost_Provisional: cost.Unit_Cost_Provisional,
    Value_Provisional: cost.Value_Provisional,
    Unit_Cost_Final: cost.Unit_Cost_Final,
    Value_Final: cost.Value_Final,
    Cost_Source: cost.Cost_Source,
    Cost_Synced_At: cost.Cost_Synced_At,
    Closed_At: cost.Closed_At,
    Closed_By: cost.Closed_By,
    Source_Module: contract.Source_Module,
    Source_ID: contract.Source_ID,
    Source_Line_ID: contract.Source_Line_ID,
    Ref_No: contract.Ref_No,
    Batch_ID: contract.Batch_ID,
    External_Ref: contract.External_Ref,
    Notes: input.Notes || "",
    Status: contract.Status,
    Created_At: nowText_(),
    Created_By: input.Created_By || userEmail_(),
    Is_Deleted: false
  };
  appendRowsByHeader_(getActiveGudang_(), SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS, [row]);
  return row;
}

function appendStockMovementsBatch_(inputs) {
  if (!inputs || !inputs.length) return [];
  var lookup = buildItemLookup_();
  var now = nowText_();
  var existing = readStockMovementKeySet_();
  var batchKeys = {};
  var stockNeed = {};
  var costData = readStockCostPeriod_();
  var rows = inputs.map(function(input, idx) {
    var item = input.Item_ID ? lookup.byId[input.Item_ID] : null;
    if (!item && input.Item_Name) item = lookup.byName[normalizeStockText_(input.Item_Name)];
    if (!item) throw new Error("Item tidak ditemukan di Master_Item: " + (input.Item_ID || input.Item_Name || ""));

    var contract = ensureStockContractInput_(input, item, idx);
    if (existing[contract.Tx_Key] || existing["MOVEMENT_ID|" + contract.Movement_ID] || batchKeys[contract.Tx_Key]) {
      throw new Error("Stock movement duplikat ditolak. Tx_Key: " + contract.Tx_Key);
    }
    batchKeys[contract.Tx_Key] = true;
    if (contract.Direction === "OUT" && input.Allow_Negative !== true) stockNeed[item.Item_ID] = (stockNeed[item.Item_ID] || 0) + contract.Qty;

    var tgl = input.Tanggal ? parseDate_(input.Tanggal) : new Date();
    var cost = resolveMovementCost_(input, item, contract, { costData: costData });
    return {
      Movement_ID: contract.Movement_ID,
      Tx_Key: contract.Tx_Key,
      Tanggal: dateOnlyText_(tgl),
      Source_Date: contract.Source_Date,
      Item_ID: item.Item_ID,
      Item_Name: item.Item_Name,
      Item_Category: item.Category || "",
      Item_Type: item.Item_Type || "",
      Unit: item.Unit || "",
      Warehouse_Code: input.Warehouse_Code || "MAIN",
      Direction: contract.Direction,
      Movement_Type: contract.Movement_Type,
      Qty: contract.Qty,
      Unit_Cost: cost.Unit_Cost,
      Cost_Period: cost.Cost_Period,
      Cost_Status: cost.Cost_Status,
      Unit_Cost_Provisional: cost.Unit_Cost_Provisional,
      Value_Provisional: cost.Value_Provisional,
      Unit_Cost_Final: cost.Unit_Cost_Final,
      Value_Final: cost.Value_Final,
      Cost_Source: cost.Cost_Source,
      Cost_Synced_At: cost.Cost_Synced_At,
      Closed_At: cost.Closed_At,
      Closed_By: cost.Closed_By,
      Source_Module: contract.Source_Module,
      Source_ID: contract.Source_ID,
      Source_Line_ID: contract.Source_Line_ID,
      Ref_No: contract.Ref_No,
      Batch_ID: contract.Batch_ID,
      External_Ref: contract.External_Ref,
      Notes: input.Notes || "",
      Status: contract.Status,
      Created_At: now,
      Created_By: input.Created_By || userEmail_(),
      Is_Deleted: false
    };
  });

  if (Object.keys(stockNeed).length) {
    var bal = buildBalance_(lookup.items, readStockMovements_());
    Object.keys(stockNeed).forEach(function(itemId) {
      var item = lookup.byId[itemId];
      var stok = bal.qty[itemId] || 0;
      if (stockNeed[itemId] > stok) throw new Error("Stok tidak cukup untuk " + (item ? item.Item_Name : itemId) + ". Stok tersedia: " + stok + ", diminta: " + stockNeed[itemId]);
    });
  }

  appendRowsByHeader_(getActiveGudang_(), SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS, rows);
  return rows;
}

// Public-ish contract endpoint untuk modul lain yang butuh post movement lewat WebApp Gudang.
// Payload bisa object tunggal atau array. Tetap wajib passport user aktif.
function postStockMovementsContract(payload, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var list = Array.isArray(payload) ? payload : [payload];
    list = list.filter(function(x) { return x; }).map(function(x) {
      x.Created_By = x.Created_By || __auth.email;
      return x;
    });
    if (!list.length) throw new Error("Payload stock movement kosong.");
    var rows = list.length === 1 ? [appendStockMovement_(list[0])] : appendStockMovementsBatch_(list);
    GUDANG_touchMutation_("postStockMovementsContract");
    return { success: true, inserted: rows.length, contractVersion: STOCK_CONTRACT_VERSION, rows: rows };
  } catch (e) {
    logError_("postStockMovementsContract", e, { payload: payload });
    return { success: false, msg: e.message, contractVersion: STOCK_CONTRACT_VERSION };
  } finally { lock.releaseLock(); }
}


// Endpoint khusus untuk Modul Retur QC: hanya barang yang sudah QC dan siap jual lagi yang ditembak ke Gudang.
// Payload contoh:
// { batchId:"RTQC-001", refNo:"RESI/RETUR", sourceDate:"2026-07-08", items:[{Item_Name:"Celana L", Qty:2, Unit_Cost:0}] }
function postReturQcReadyToStock(payload, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    payload = payload || {};
    var items = Array.isArray(payload.items) ? payload.items : (Array.isArray(payload) ? payload : []);
    if (!items.length && (payload.Item_ID || payload.Item_Name || payload.nama)) items = [payload];
    if (!items.length) throw new Error("Payload Retur QC kosong. Kirim items siap jual.");

    var batchId = normalizeStockText_(payload.batchId || payload.Batch_ID || payload.Return_Batch_ID || payload.Ref_No || payload.refNo || uuid_("RTQC"));
    var sourceDate = normalizeDateKeyForWarehouse_(payload.sourceDate || payload.Source_Date || payload.tanggal || payload.Tanggal || new Date()) || dateOnlyText_(new Date());
    var sourceId = normalizeStockText_(payload.Source_ID || payload.sourceId || ("RETUR_QC|" + batchId));
    var refNo = normalizeStockText_(payload.Ref_No || payload.refNo || batchId);

    var rowsIn = items.map(function(it) {
      var itemName = normalizeStockText_(it.Item_Name || it.itemName || it.nama || it.Nama_Item || "");
      var itemId = normalizeStockText_(it.Item_ID || it.itemId || "");
      var qty = toNumber_(it.Qty || it.qty || it.Qty_Siap_Jual || it.qtySiapJual || 0);
      if (qty <= 0) throw new Error("Qty Retur QC harus lebih dari 0 untuk item: " + (itemName || itemId));
      return {
        Tanggal: new Date(),
        Source_Date: sourceDate,
        Item_ID: itemId,
        Item_Name: itemName,
        Direction: "IN",
        Movement_Type: "RETURN_IN",
        Qty: qty,
        Unit_Cost: toNumber_(it.Unit_Cost || it.unitCost || 0),
        Source_Module: "RETUR_QC",
        Source_ID: sourceId,
        Source_Line_ID: normalizeStockText_(it.Source_Line_ID || it.sourceLineId || buildOmniSourceLine_("ITEM", itemName || itemId)),
        Ref_No: refNo,
        Batch_ID: batchId,
        External_Ref: normalizeStockText_(it.External_Ref || it.externalRef || payload.External_Ref || payload.externalRef || ""),
        Notes: normalizeStockText_(it.Notes || it.notes || payload.Notes || payload.notes || "Retur QC siap jual"),
        Created_By: __auth.email
      };
    });

    var rows = rowsIn.length === 1 ? [appendStockMovement_(rowsIn[0])] : appendStockMovementsBatch_(rowsIn);
    GUDANG_touchMutation_("postReturQcReadyToStock");
    return { success: true, inserted: rows.length, rows: rows, contractVersion: STOCK_CONTRACT_VERSION };
  } catch (e) {
    logError_("postReturQcReadyToStock", e, { payload: payload });
    return { success: false, msg: e.message, contractVersion: STOCK_CONTRACT_VERSION };
  } finally { lock.releaseLock(); }
}


// Endpoint untuk Produksi/Finance mengirim HPP per item per bulan ke Gudang.
// Payload contoh:
// { period:"2026-07", costStatus:"PROVISIONAL", sourceId:"PROD-SYNC-2026-07", items:[{Item_Name:"Celana L", Unit_Cost:42500}] }
// Saat closing, Finance bisa kirim costStatus FINAL atau Unit_Cost_Final.
function syncStockCostPeriod(payload, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    payload = payload || {};
    var items = Array.isArray(payload.items) ? payload.items : (Array.isArray(payload) ? payload : []);
    if (!items.length && (payload.Item_ID || payload.Item_Name || payload.nama)) items = [payload];
    if (!items.length) throw new Error("Payload HPP kosong. Kirim items biaya per item.");

    var defaultPeriod = normalizeCostPeriod_(payload.period || payload.Period || payload.Cost_Period || new Date());
    var defaultStatus = normalizeCostStatus_(payload.costStatus || payload.Cost_Status || "PROVISIONAL", "PROVISIONAL");
    var sourceModule = normalizeStockCode_(payload.sourceModule || payload.Source_Module || "PROD");
    var sourceId = normalizeStockText_(payload.sourceId || payload.Source_ID || payload.refNo || payload.Ref_No || (sourceModule + "|" + defaultPeriod));
    var now = nowText_();
    var lookup = buildItemLookup_();
    var ss = getActiveGudang_();
    var sh = ensureSheetWithHeaders_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS);
    var info = getHeaderInfo_(sh);
    var data = readStockCostPeriod_();
    var values = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues() : [];
    var updates = 0, inserts = [];

    function setCell(rowArr, header, value) {
      var c = col_(info, header, -1);
      if (c !== -1) rowArr[c] = value;
    }

    items.forEach(function(raw) {
      var itemId = normalizeStockText_(raw.Item_ID || raw.itemId || "");
      var itemName = normalizeStockText_(raw.Item_Name || raw.itemName || raw.nama || raw.Nama_Item || "");
      var item = itemId ? lookup.byId[itemId] : null;
      if (!item && itemName) item = lookup.byName[itemName];
      if (!item) throw new Error("Item HPP tidak ditemukan di Master_Item: " + (itemId || itemName));
      var period = normalizeCostPeriod_(raw.Period || raw.period || raw.Cost_Period || defaultPeriod);
      var status = normalizeCostStatus_(raw.Cost_Status || raw.costStatus || defaultStatus, defaultStatus);
      var unitProv = toNumber_(raw.Unit_Cost_Provisional || raw.unitCostProvisional || raw.Unit_Cost || raw.unitCost || raw.HPP || raw.hpp || 0);
      var unitFinal = toNumber_(raw.Unit_Cost_Final || raw.unitCostFinal || (status === "FINAL" ? (raw.Unit_Cost || raw.unitCost || raw.HPP || raw.hpp || 0) : 0));
      if (status === "FINAL" && unitFinal <= 0 && unitProv > 0) unitFinal = unitProv;
      if (unitProv <= 0 && unitFinal > 0) unitProv = unitFinal;
      if (unitProv <= 0 && unitFinal <= 0) throw new Error("Unit cost HPP kosong untuk " + item.Item_Name);

      var existing = data.byKey[item.Item_ID + "|" + period] || data.byNameKey[normalizeStockText_(item.Item_Name).toUpperCase() + "|" + period];
      if (existing && existing.__rowNumber) {
        var arr = values[existing.__rowNumber - 2];
        setCell(arr, "Cost_ID", existing.Cost_ID || uuid_("COST"));
        setCell(arr, "Period", period);
        setCell(arr, "Item_ID", item.Item_ID);
        setCell(arr, "Item_Name", item.Item_Name);
        setCell(arr, "Unit_Cost_Provisional", unitProv);
        if (status === "FINAL") setCell(arr, "Unit_Cost_Final", unitFinal);
        setCell(arr, "Cost_Status", status);
        setCell(arr, "Source_Module", sourceModule);
        setCell(arr, "Source_ID", sourceId);
        setCell(arr, "Synced_At", now);
        setCell(arr, "Synced_By", __auth.email);
        if (status === "FINAL") {
          setCell(arr, "Closed_At", now);
          setCell(arr, "Closed_By", __auth.email);
        }
        setCell(arr, "Notes", normalizeStockText_(raw.Notes || raw.notes || payload.Notes || payload.notes || "HPP sync"));
        setCell(arr, "Is_Deleted", false);
        updates++;
      } else {
        inserts.push({
          Cost_ID: uuid_("COST"), Period: period, Item_ID: item.Item_ID, Item_Name: item.Item_Name,
          Unit_Cost_Provisional: unitProv, Unit_Cost_Final: status === "FINAL" ? unitFinal : "",
          Cost_Status: status, Source_Module: sourceModule, Source_ID: sourceId,
          Synced_At: now, Synced_By: __auth.email,
          Closed_At: status === "FINAL" ? now : "", Closed_By: status === "FINAL" ? __auth.email : "",
          Notes: normalizeStockText_(raw.Notes || raw.notes || payload.Notes || payload.notes || "HPP sync"), Is_Deleted: false
        });
      }
    });

    if (values.length) sh.getRange(2, 1, values.length, info.headers.length).setValues(values);
    if (inserts.length) appendRowsByHeader_(ss, SHEET_STOCK_COST_PERIOD, STOCK_COST_PERIOD_HEADERS, inserts);
    GUDANG_touchMutation_("syncStockCostPeriod");
    return { success: true, version: STOCK_COST_VERSION, period: defaultPeriod, status: defaultStatus, updated: updates, inserted: inserts.length };
  } catch (e) {
    logError_("syncStockCostPeriod", e, { payload: payload });
    return { success: false, msg: e.message, version: STOCK_COST_VERSION };
  } finally { lock.releaseLock(); }
}

// Finance memicu closing COGS bulanan dari Gudang.
// Fungsi ini membaca Stock_Cost_Period FINAL, lalu mengunci cost movement OUT (OMNI_OUT/SALES_OUT/SJ_OUT) pada period tersebut.
function financeCloseCogsPeriod(period, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var targetPeriod = normalizeCostPeriod_(period || new Date());
    var ss = getActiveGudang_();
    var sh = ensureSheetWithHeaders_(ss, SHEET_STOCK_MOVEMENT, STOCK_MOVEMENT_HEADERS);
    var info = getHeaderInfo_(sh);
    var data = readStockCostPeriod_();
    var lookup = buildItemLookup_();
    var lastRow = sh.getLastRow();
    if (lastRow < 2) return { success: true, period: targetPeriod, finalized: 0, skipped: 0, msg: "Belum ada Stock_Movement." };

    var values = sh.getRange(2, 1, lastRow - 1, sh.getLastColumn()).getValues();
    function ci(h) { return col_(info, h, -1); }
    var c = {
      tgl: ci("Tanggal"), srcDate: ci("Source_Date"), itemId: ci("Item_ID"), itemName: ci("Item_Name"), dir: ci("Direction"), type: ci("Movement_Type"), qty: ci("Qty"), unit: ci("Unit_Cost"),
      cp: ci("Cost_Period"), cs: ci("Cost_Status"), ucp: ci("Unit_Cost_Provisional"), vp: ci("Value_Provisional"), ucf: ci("Unit_Cost_Final"), vf: ci("Value_Final"),
      source: ci("Cost_Source"), synced: ci("Cost_Synced_At"), closedAt: ci("Closed_At"), closedBy: ci("Closed_By"), deleted: ci("Is_Deleted")
    };
    var now = nowText_();
    var finalized = 0, skipped = 0, valueFinalTotal = 0, valueProvTotal = 0;

    values.forEach(function(r) {
      var del = c.deleted !== -1 ? normalizeStockCode_(r[c.deleted]) : "";
      if (del === "TRUE" || del === "YA" || del === "1") return;
      var dir = c.dir !== -1 ? normalizeStockCode_(r[c.dir]) : "";
      var type = c.type !== -1 ? normalizeStockCode_(r[c.type]) : "";
      if (dir !== "OUT" || !cogsMovementType_(type)) return;
      var rowPeriod = normalizeCostPeriod_((c.cp !== -1 ? r[c.cp] : "") || (c.srcDate !== -1 ? r[c.srcDate] : "") || (c.tgl !== -1 ? r[c.tgl] : ""));
      if (rowPeriod !== targetPeriod) return;
      var itemId = c.itemId !== -1 ? normalizeStockText_(r[c.itemId]) : "";
      var itemName = c.itemName !== -1 ? normalizeStockText_(r[c.itemName]) : "";
      var item = itemId ? lookup.byId[itemId] : null;
      if (!item && itemName) item = lookup.byName[itemName];
      if (!item) { skipped++; return; }
      var costRow = findStockCostRow_(data, item, targetPeriod);
      var finalCost = costRow && normalizeCostStatus_(costRow.Cost_Status, "PROVISIONAL") === "FINAL" ? toNumber_(costRow.Unit_Cost_Final || costRow.Unit_Cost_Provisional) : 0;
      if (finalCost <= 0) { skipped++; return; }
      var qty = c.qty !== -1 ? toNumber_(r[c.qty]) : 0;
      var prevUnit = c.unit !== -1 ? toNumber_(r[c.unit]) : 0;
      var provUnit = c.ucp !== -1 ? toNumber_(r[c.ucp]) : 0;
      if (provUnit <= 0) provUnit = prevUnit || finalCost;
      var provValue = qty * provUnit;
      var finalValue = qty * finalCost;
      if (c.cp !== -1) r[c.cp] = targetPeriod;
      if (c.cs !== -1) r[c.cs] = "FINAL";
      if (c.unit !== -1) r[c.unit] = finalCost;
      if (c.ucp !== -1) r[c.ucp] = provUnit;
      if (c.vp !== -1) r[c.vp] = provValue;
      if (c.ucf !== -1) r[c.ucf] = finalCost;
      if (c.vf !== -1) r[c.vf] = finalValue;
      if (c.source !== -1) r[c.source] = (costRow.Source_Module || "STOCK_COST_PERIOD") + (costRow.Source_ID ? "|" + costRow.Source_ID : "");
      if (c.synced !== -1) r[c.synced] = now;
      if (c.closedAt !== -1) r[c.closedAt] = now;
      if (c.closedBy !== -1) r[c.closedBy] = __auth.email;
      finalized++;
      valueFinalTotal += finalValue;
      valueProvTotal += provValue;
    });

    sh.getRange(2, 1, values.length, info.headers.length).setValues(values);
    GUDANG_touchMutation_("financeCloseCogsPeriod");
    return {
      success: true,
      version: STOCK_COST_VERSION,
      period: targetPeriod,
      finalized: finalized,
      skipped: skipped,
      cogsFinal: valueFinalTotal,
      cogsProvisionalBeforeClose: valueProvTotal,
      adjustment: valueFinalTotal - valueProvTotal,
      msg: "Closing COGS Gudang selesai untuk " + targetPeriod + ". Finalized: " + finalized + ", skipped: " + skipped
    };
  } catch (e) {
    logError_("financeCloseCogsPeriod", e, { period: period });
    return { success: false, msg: e.message, version: STOCK_COST_VERSION };
  } finally { lock.releaseLock(); }
}

// Finance bisa baca COGS bersih dari endpoint ini: final jika sudah closing, provisional untuk bulan berjalan.
function getCogsForFinance(period, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  try {
    var targetPeriod = normalizeCostPeriod_(period || new Date());
    var rows = [];
    var totals = { OMNI_OUT: 0, SALES_OUT: 0, SJ_OUT: 0, TOTAL: 0, provisionalRows: 0, finalRows: 0 };
    readStockMovements_().forEach(function(m) {
      if (m.Direction !== "OUT" || !cogsMovementType_(m.Movement_Type)) return;
      var p = normalizeCostPeriod_(m.Cost_Period || m.Source_Date || m.Tanggal || new Date());
      if (p !== targetPeriod) return;
      var status = normalizeCostStatus_(m.Cost_Status, "PROVISIONAL");
      var val = status === "FINAL" && toNumber_(m.Value_Final) > 0 ? toNumber_(m.Value_Final) : (toNumber_(m.Value_Provisional) || (toNumber_(m.Qty) * toNumber_(m.Unit_Cost)));
      var unit = status === "FINAL" && toNumber_(m.Unit_Cost_Final) > 0 ? toNumber_(m.Unit_Cost_Final) : (toNumber_(m.Unit_Cost_Provisional) || toNumber_(m.Unit_Cost));
      rows.push({
        Period: targetPeriod,
        Movement_ID: m.Movement_ID,
        Tx_Key: m.Tx_Key,
        Tanggal: m.Tanggal,
        Source_Date: m.Source_Date,
        Source_Module: m.Source_Module,
        Source_ID: m.Source_ID,
        Source_Line_ID: m.Source_Line_ID,
        Movement_Type: m.Movement_Type,
        Item_ID: m.Item_ID,
        Item_Name: m.Item_Name,
        Qty: m.Qty,
        Unit_Cost: unit,
        COGS_Value: val,
        Cost_Status: status,
        Cost_Source: m.Cost_Source,
        Closed_At: m.Closed_At
      });
      totals[m.Movement_Type] = (totals[m.Movement_Type] || 0) + val;
      totals.TOTAL += val;
      if (status === "FINAL") totals.finalRows++; else totals.provisionalRows++;
    });
    return { success: true, version: STOCK_COST_VERSION, period: targetPeriod, rows: rows, totals: totals, requestedBy: __auth.email };
  } catch (e) {
    logError_("getCogsForFinance", e, { period: period });
    return { success: false, msg: e.message, version: STOCK_COST_VERSION };
  }
}

// =========================== OMNI TARIKAN ===========================

function getOmniSpreadsheetInfo_() {
  var hard = extractSpreadsheetId_(OMNI_SPREADSHEET_ID_OVERRIDE);
  if (hard) {
    return {
      Module_Code: "OMNI_HARDCODED",
      Module_Name: "Omnichannel Hardcoded Override",
      Spreadsheet_ID: hard,
      Source: "OMNI_SPREADSHEET_ID_OVERRIDE"
    };
  }
  var info = getOmniModuleInfo_();
  if (info && info.Spreadsheet_ID) {
    info.Source = "Master_Module";
    return info;
  }
  return null;
}

function cellDebugValue_(v) {
  if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, TZ, "yyyy-MM-dd HH:mm:ss");
  if (v === null || v === undefined) return "";
  return String(v).slice(0, 180);
}



function isCancelLikeStatusGudang_(status) {
  var s = String(status || "").toLowerCase();
  return s.indexOf("batal") !== -1 || s.indexOf("cancel") !== -1 || s.indexOf("retur") !== -1 || s.indexOf("return") !== -1 || s.indexOf("gagal") !== -1 || s.indexOf("failed") !== -1;
}


function readOmniWarehouseSummary_() {
  var debug = {
    mode: "OMNI_SUMMARY_PR_LAZY_DETAIL",
    ready: false,
    source: "",
    moduleCode: "",
    moduleName: "",
    spreadsheetIdMasked: "",
    sheetFound: false,
    sheetLastRow: 0,
    summaryRows: 0,
    readyRows: 0,
    skipDate: 0,
    skipEmpty: 0,
    versionMismatchRows: 0,
    minDate: "",
    version: OMNI_WAREHOUSE_SUMMARY_VERSION,
    error: ""
  };

  try {
    var omniInfo = getOmniSpreadsheetInfo_();
    if (!omniInfo || !omniInfo.Spreadsheet_ID) throw new Error("Spreadsheet Omnichannel belum ketemu.");
    debug.source = omniInfo.Source || "";
    debug.moduleCode = omniInfo.Module_Code || "";
    debug.moduleName = omniInfo.Module_Name || "";
    debug.spreadsheetIdMasked = String(omniInfo.Spreadsheet_ID).slice(0, 8) + "..." + String(omniInfo.Spreadsheet_ID).slice(-6);

    var ss = SpreadsheetApp.openById(omniInfo.Spreadsheet_ID);
    var t = readTable_(ss, OMNI_DAILY_PRODUCT_SHEET, null, { noCreate: true });
    if (!t.sheet) throw new Error("Sheet " + OMNI_DAILY_PRODUCT_SHEET + " belum ada. Pasang Omni v1.6.4 lalu rebuild summary.");
    debug.sheetFound = true;
    debug.sheetLastRow = t.lastRow || (t.rows.length + 1);
    debug.summaryRows = t.rows.length;

    var cDate = col_(t.info, ["Date_Key"], -1);
    var cStore = col_(t.info, ["Store_Name"], -1);
    var cItem = col_(t.info, ["Internal_Item_Name"], -1);
    var cDemand = col_(t.info, ["Warehouse_Demand_Qty"], -1);
    var cNormal = col_(t.info, ["Warehouse_Normal_Qty"], -1);
    var cCancel = col_(t.info, ["Warehouse_Cancel_Qty"], -1);
    var cOrderCount = col_(t.info, ["Warehouse_Order_Count"], -1);
    var cNormalOrders = col_(t.info, ["Warehouse_Normal_Order_Count"], -1);
    var cCancelOrders = col_(t.info, ["Warehouse_Cancel_Order_Count"], -1);
    var cMapType = col_(t.info, ["Warehouse_Mapping_Type"], -1);
    var cVersion = col_(t.info, ["Warehouse_Summary_Version"], -1);

    var missing = [];
    [
      [cDate, "Date_Key"], [cStore, "Store_Name"], [cItem, "Internal_Item_Name"],
      [cDemand, "Warehouse_Demand_Qty"], [cNormal, "Warehouse_Normal_Qty"],
      [cCancel, "Warehouse_Cancel_Qty"], [cOrderCount, "Warehouse_Order_Count"], [cNormalOrders, "Warehouse_Normal_Order_Count"],
      [cCancelOrders, "Warehouse_Cancel_Order_Count"], [cMapType, "Warehouse_Mapping_Type"],
      [cVersion, "Warehouse_Summary_Version"]
    ].forEach(function(x) { if (x[0] === -1) missing.push(x[1]); });
    if (missing.length) throw new Error("Summary Omni belum kompatibel. Header kurang: " + missing.join(", "));

    var minDate = new Date();
    minDate.setDate(minDate.getDate() - OMNI_LOOKBACK_DAYS);
    minDate.setHours(0, 0, 0, 0);
    var minKey = Utilities.formatDate(minDate, TZ, "yyyy-MM-dd");
    debug.minDate = minKey;

    var out = [];
    t.rows.forEach(function(r) {
      var dateKey = normalizeDateKeyForWarehouse_(r[cDate]);
      var store = String(r[cStore] || "").trim();
      var item = String(r[cItem] || "").trim();
      if (!dateKey || !store || !item) { debug.skipEmpty++; return; }

      var version = String(r[cVersion] || "").trim();
      if (version !== OMNI_WAREHOUSE_SUMMARY_VERSION) { debug.versionMismatchRows++; return; }
      if (dateKey < minKey) { debug.skipDate++; return; }

      var normalQty = toNumber_(r[cNormal]);
      var cancelQty = toNumber_(r[cCancel]);
      var demandQty = toNumber_(r[cDemand]);
      if (Math.abs(demandQty - (normalQty + cancelQty)) > 0.000001) demandQty = normalQty + cancelQty;
      if (demandQty <= 0) return;

      out.push({
        tgl: displayDateFromKey_(dateKey),
        tglKey: dateKey,
        toko: store,
        nama: item,
        qty: demandQty,
        normalQty: normalQty,
        cancelLikeQty: cancelQty,
        orderCount: toNumber_(r[cOrderCount]),
        cancelLikeOrders: toNumber_(r[cCancelOrders]),
        mappingType: String(r[cMapType] || "").trim(),
        mappingSource: OMNI_DAILY_PRODUCT_SHEET,
        warehouseSummaryVersion: version
      });
      debug.readyRows++;
    });

    if (debug.versionMismatchRows > 0) {
      throw new Error("Summary Omni masih versi lama pada " + debug.versionMismatchRows + " baris. Jalankan SETUP_installOmniDailySummary() di Omni v1.6.4.");
    }

    debug.ready = true;
    readOmniWarehouseSummary_._lastDebug = debug;
    return { ready: true, rows: out, debug: debug };
  } catch (e) {
    debug.error = e && e.message ? e.message : String(e);
    readOmniWarehouseSummary_._lastDebug = debug;
    logError_("readOmniWarehouseSummary_", e, debug);
    return { ready: false, rows: [], debug: debug };
  }
}

function buildOmniDemandFromRawRows_(omniRows) {
  var demand = {};
  (omniRows || []).forEach(function(o) {
    var key = (o.tglKey || o.tgl) + "|" + o.toko + "|" + o.nama;
    if (!demand[key]) {
      demand[key] = {
        tgl: o.tgl, toko: o.toko, nama: o.nama, qty: 0, mappingType: o.mappingType || "",
        tglKey: o.tglKey || "", orderCount: 0, orderMap: {}, cancelLikeQty: 0,
        cancelLikeOrders: 0, normalQty: 0, statusMap: {}, mappingSourceMap: {}
      };
    }
    demand[key].qty += o.qty;
    if (o.cancelLike) demand[key].cancelLikeQty += o.qty; else demand[key].normalQty += o.qty;
    var statusKey = String(o.status || (o.cancelLike ? "BATAL/RETUR" : "NORMAL")).trim() || "NORMAL";
    demand[key].statusMap[statusKey] = (demand[key].statusMap[statusKey] || 0) + o.qty;
    var mapSrc = String(o.mappingSource || "-").trim() || "-";
    demand[key].mappingSourceMap[mapSrc] = true;
    if (!demand[key].orderMap[o.no]) {
      demand[key].orderMap[o.no] = true;
      demand[key].orderCount++;
      if (o.cancelLike) demand[key].cancelLikeOrders++;
    }
  });
  return demand;
}

function buildOmniDemandFromSummaryRows_(summaryRows) {
  var demand = {};
  (summaryRows || []).forEach(function(o) {
    var key = (o.tglKey || o.tgl) + "|" + o.toko + "|" + o.nama;
    if (!demand[key]) {
      demand[key] = {
        tgl: o.tgl, toko: o.toko, nama: o.nama, qty: 0, mappingType: o.mappingType || "",
        tglKey: o.tglKey || "", orderCount: 0, cancelLikeQty: 0, cancelLikeOrders: 0,
        normalQty: 0, statusMap: {}, mappingSourceMap: {}
      };
    }
    var d = demand[key];
    d.qty += toNumber_(o.qty);
    d.normalQty += toNumber_(o.normalQty);
    d.cancelLikeQty += toNumber_(o.cancelLikeQty);
    d.orderCount += toNumber_(o.orderCount);
    d.cancelLikeOrders += toNumber_(o.cancelLikeOrders);
    if (!d.mappingType && o.mappingType) d.mappingType = o.mappingType;
    if (toNumber_(o.normalQty) > 0) d.statusMap.NORMAL = (d.statusMap.NORMAL || 0) + toNumber_(o.normalQty);
    if (toNumber_(o.cancelLikeQty) > 0) d.statusMap["BATAL/RETUR"] = (d.statusMap["BATAL/RETUR"] || 0) + toNumber_(o.cancelLikeQty);
    d.mappingSourceMap[OMNI_DAILY_PRODUCT_SHEET] = true;
  });
  return demand;
}

function buildGudangOmniOutputs_(demand, ctx, includeTarikan) {
  ctx = ctx || {};
  var lookup = ctx.lookup;
  var bal = ctx.bal;
  var mapAnakSubKategori = ctx.mapAnakSubKategori || {};
  var mapStokFisikGrouped = ctx.mapStokFisikGrouped || {};
  var omniConsumptionMaps = buildOmniConsumptionMaps_(ctx.movements || [], ctx.omniActionLogs || []);
  var tarikan = [];
  var prAgg = {};
  var remainingGroupCount = 0;

  Object.keys(demand || {}).forEach(function(k) {
    var d = demand[k];
    var anak = mapAnakSubKategori[d.nama] || [];
    var typeCode = normalizeStockCode_(d.mappingType || "");
    var isSubKategori = anak.length > 0 || typeCode === "SUB_CATEGORY" || typeCode === "BUNDLE" || typeCode === "PAKET";
    var isDirectItem = !isSubKategori && lookup.byName[d.nama];
    var isGroup = isSubKategori;

    var packKey = d.toko + "|" + d.nama + "|" + d.tgl;
    var packedQty = isGroup ? (omniConsumptionMaps.bundlePack[packKey] || 0) : (omniConsumptionMaps.normalPack[packKey] || 0);
    var cancelClearedQty = isGroup ? (omniConsumptionMaps.bundleCancel[packKey] || 0) : (omniConsumptionMaps.normalCancel[packKey] || 0);
    var packedAppliedToCancel = Math.max(0, packedQty - (d.normalQty || 0));
    var normalRemaining = Math.max(0, (d.normalQty || 0) - packedQty);
    var cancelRemaining = Math.max(0, (d.cancelLikeQty || 0) - cancelClearedQty - packedAppliedToCancel);
    var sisa = Math.max(0, normalRemaining + cancelRemaining);
    if (sisa <= 0) return;
    remainingGroupCount++;

    var fisik = 0;
    if (isGroup) fisik = mapStokFisikGrouped[d.nama] || 0;
    else if (isDirectItem) fisik = bal.qty[lookup.byName[d.nama].Item_ID] || 0;

    var rincianAnak = anak.map(function(a) {
      var it = lookup.byName[a.nama];
      return { nama: a.nama, stok: it ? (bal.qty[it.Item_ID] || 0) : 0 };
    });

    if (includeTarikan) {
      tarikan.push({
        tgl: d.tgl, tglKey: d.tglKey || "", toko: d.toko, nama: d.nama, butuh: sisa,
        fisik: fisik, isGroup: isGroup, anak: rincianAnak, orderCount: d.orderCount || 0,
        cancelLikeOrders: d.cancelLikeOrders || 0, cancelLikeQty: d.cancelLikeQty || 0,
        cancelRemainingQty: cancelRemaining, cancelClearedQty: cancelClearedQty,
        normalQty: d.normalQty || 0, normalRemainingQty: normalRemaining,
        hasCancelLike: cancelRemaining > 0,
        statusSummary: Object.keys(d.statusMap || {}).map(function(sk){ return sk + ": " + d.statusMap[sk]; }).join(" / "),
        mappingSources: Object.keys(d.mappingSourceMap || {}).join(" / "), totalOrderQty: d.qty,
        packedQty: packedQty, consumedQty: packedQty + cancelClearedQty
      });
    }

    if (!prAgg[d.nama]) {
      prAgg[d.nama] = {
        toko: "Produksi/Maklun", nama: d.nama, butuh: 0, fisik: fisik, pr: 0, alokasi: 0,
        orderCount: 0, cancelLikeQty: 0, cancelLikeOrders: 0
      };
    }
    prAgg[d.nama].butuh += sisa;
    prAgg[d.nama].alokasi += 1;
    prAgg[d.nama].orderCount += d.orderCount || 0;
    prAgg[d.nama].cancelLikeQty += cancelRemaining || 0;
    prAgg[d.nama].cancelLikeOrders += cancelRemaining > 0 ? (d.cancelLikeOrders || 0) : 0;
    prAgg[d.nama].fisik = Math.max(prAgg[d.nama].fisik || 0, fisik || 0);
  });

  var pr = Object.keys(prAgg).map(function(nama) {
    var p = prAgg[nama];
    p.pr = Math.max(0, (p.butuh || 0) - (p.fisik || 0));
    return p;
  }).filter(function(p) { return p.pr > 0; });

  tarikan.sort(function(a,b) { return (a.tgl+a.toko+a.nama).localeCompare(b.tgl+b.toko+b.nama); });
  pr.sort(function(a,b) { return b.pr - a.pr; });
  return { pr: pr, tarikanOmni: tarikan, tarikanCountEstimate: remainingGroupCount };
}

function readOmniOrders_() {
  var debug = {
    mode: "OMNI_CANCEL_ACTION_PR_CLEAR",
    source: "",
    moduleCode: "",
    moduleName: "",
    spreadsheetIdMasked: "",
    sheetFound: false,
    sheetLastRow: 0,
    rawRows: 0,
    passedRows: 0,
    skipDeleted: 0,
    skipNoOrder: 0,
    skipNoItem: 0,
    skipQty: 0,
    skipDate: 0,
    skipCancelNoResi: 0,
    cancelLikeRows: 0,
    mappedDirectRows: 0,
    mappedFallbackRows: 0,
    mappedBySkuRows: 0,
    mappedByVariantRows: 0,
    ambiguousMappingRows: 0,
    readyRows: 0,
    minDate: "",
    headerIndex: {},
    sampleRawText: [],
    samplePassedText: [],
    error: ""
  };

  try {
    var omniInfo = getOmniSpreadsheetInfo_();
    if (!omniInfo || !omniInfo.Spreadsheet_ID) {
      throw new Error("Spreadsheet Omnichannel belum ketemu. Isi Master_Module baris OMNI atau isi OMNI_SPREADSHEET_ID_OVERRIDE di Kode.gs.");
    }
    debug.source = omniInfo.Source || "";
    debug.moduleCode = omniInfo.Module_Code || "";
    debug.moduleName = omniInfo.Module_Name || "";
    debug.spreadsheetIdMasked = String(omniInfo.Spreadsheet_ID).slice(0, 8) + "..." + String(omniInfo.Spreadsheet_ID).slice(-6);

    var ss = SpreadsheetApp.openById(omniInfo.Spreadsheet_ID);
    var t = readTable_(ss, "Omni_Order", null, { noCreate: true });
    if (!t.sheet) throw new Error("Sheet Omni_Order tidak ditemukan di spreadsheet Omni.");

    debug.sheetFound = true;
    debug.sheetLastRow = t.rows ? t.rows.length + 1 : 0;

    var cTglKey = col_(t.info, ["Tanggal Key", "Tanggal_Key", "Order_Date_Key", "Date_Key"], -1);
    var cTgl = col_(t.info, ["Tanggal", "Order_Date", "Tgl Pesanan", "Waktu Pesanan Dibuat"], -1);
    var cNo = col_(t.info, ["No Pesanan", "Order_No", "Nomor Pesanan", "No_Order"], -1);
    var cStatus = col_(t.info, ["Status", "Marketplace_Status", "Status Pesanan"], -1);
    var cToko = col_(t.info, ["Toko", "Store_Name", "Nama Toko", "Nama Panggilan Toko BigSeller"], -1);
    var cSku = col_(t.info, ["SKU", "Marketplace_SKU", "SKU BigSeller", "Nomor Referensi SKU"], -1);
    var cProduct = col_(t.info, ["Marketplace_Product_Name", "Product_Name", "Nama Produk", "Product Name", "Nama Produk BigSeller"], -1);
    var cVariation = col_(t.info, ["Marketplace_Variation", "Variation", "Variasi", "Nama Variasi", "Varian", "Variant"], -1);
    var cItem = col_(t.info, ["Item Gudang", "Item_Gudang", "Item Gudang (Mapped)", "Internal_Item_Name", "Internal Item Name"], -1);
    var cQtyGudang = col_(t.info, ["Qty Gudang", "QTY Gudang", "Qty_Gudang", "Internal_Qty"], -1);
    var cQtyRaw = col_(t.info, ["Qty", "Quantity", "Jumlah", "Jumlah Produk", "Qty Produk", "Jumlah Pembelian"], -1);
    var cResi = col_(t.info, ["No Resi", "Tracking_No", "Nomor Resi", "Resi"], -1);
    var cDeleted = col_(t.info, "Is_Deleted", -1);

    debug.headerIndex = { tanggalKey: cTglKey, tanggal: cTgl, noPesanan: cNo, status: cStatus, toko: cToko, sku: cSku, product: cProduct, variation: cVariation, itemGudang: cItem, qtyGudang: cQtyGudang, qtyRaw: cQtyRaw, resi: cResi, isDeleted: cDeleted };

    var missing = [];
    if (cNo === -1) missing.push("No Pesanan");
    if (cQtyGudang === -1 && cQtyRaw === -1) missing.push("Qty / Qty Gudang");
    if (cItem === -1 && cSku === -1 && cProduct === -1 && cVariation === -1) missing.push("Item Gudang / SKU / Produk / Varian");
    if (missing.length) throw new Error("Header Omni_Order kurang: " + missing.join(", ") + ". Jalankan setup/rebuild Omni atau lengkapi Master_SKU_Map.");

    var minDate = new Date();
    minDate.setDate(minDate.getDate() - OMNI_LOOKBACK_DAYS);
    minDate.setHours(0, 0, 0, 0);
    debug.minDate = Utilities.formatDate(minDate, TZ, "yyyy-MM-dd");

    var skuMap = getWhMasterSkuMap_();
    var out = [];
    t.rows.forEach(function(r) {
      debug.rawRows++;
      if (debug.sampleRawText.length < 5) {
        debug.sampleRawText.push({
          tanggalKey: cTglKey !== -1 ? cellDebugValue_(r[cTglKey]) : "",
          tanggal: cTgl !== -1 ? cellDebugValue_(r[cTgl]) : "",
          no: cNo !== -1 ? cellDebugValue_(r[cNo]) : "",
          status: cStatus !== -1 ? cellDebugValue_(r[cStatus]) : "",
          toko: cToko !== -1 ? cellDebugValue_(r[cToko]) : "",
          sku: cSku !== -1 ? cellDebugValue_(r[cSku]) : "",
          product: cProduct !== -1 ? cellDebugValue_(r[cProduct]) : "",
          variation: cVariation !== -1 ? cellDebugValue_(r[cVariation]) : "",
          item: cItem !== -1 ? cellDebugValue_(r[cItem]) : "",
          qtyGudang: cQtyGudang !== -1 ? cellDebugValue_(r[cQtyGudang]) : "",
          qtyRaw: cQtyRaw !== -1 ? cellDebugValue_(r[cQtyRaw]) : "",
          resi: cResi !== -1 ? cellDebugValue_(r[cResi]) : ""
        });
      }

      var del = cDeleted !== -1 ? String(r[cDeleted] || "").toUpperCase() : "";
      if (del === "TRUE" || del === "1" || del === "YA") { debug.skipDeleted++; return; }
      var no = String(r[cNo] || "").trim();
      if (!no) { debug.skipNoOrder++; return; }

      var sku = cSku !== -1 ? String(r[cSku] || "").trim() : "";
      var product = cProduct !== -1 ? String(r[cProduct] || "").trim() : "";
      var variation = cVariation !== -1 ? String(r[cVariation] || "").trim() : "";
      var directItem = cItem !== -1 ? String(r[cItem] || "").trim() : "";
      var item = directItem;
      var mappingType = "";
      var mappingSource = directItem && directItem.toUpperCase() !== "UNMAPPED" ? "Omni_Order" : "";
      var conv = 1;
      var fallback = null;

      // Coba mapping fallback walaupun Item Gudang ada, supaya Qty raw bisa dikonversi jika Qty Gudang belum tersedia.
      var lookupKeys = [];
      if (sku && variation) lookupKeys.push(sku + "|" + variation);
      if (sku) lookupKeys.push(sku);
      if (product && variation) lookupKeys.push(product + "|" + variation);
      if (!sku && variation) lookupKeys.push(variation);
      if (!sku && product) lookupKeys.push(product);
      fallback = getWhSkuMapValue_(skuMap, lookupKeys);

      if (!item || item.toUpperCase() === "UNMAPPED") {
        if (fallback) {
          item = fallback.item;
          mappingType = fallback.mappingType || "";
          mappingSource = fallback.source || "Master_SKU_Map";
          conv = fallback.isi || 1;
          debug.mappedFallbackRows++;
          if (sku) debug.mappedBySkuRows++; else debug.mappedByVariantRows++;
        } else {
          // Deteksi key ambiguous supaya pesan debug lebih jelas.
          var ambiguous = false;
          lookupKeys.forEach(function(k) { var v = skuMap[normalizeSkuKey_(k)]; if (v && v.__ambiguous) ambiguous = true; });
          if (ambiguous) debug.ambiguousMappingRows++;
          debug.skipNoItem++;
          return;
        }
      } else {
        debug.mappedDirectRows++;
        if (!mappingType && fallback && fallback.item === item) {
          mappingType = fallback.mappingType || "";
          if (cQtyGudang === -1) conv = fallback.isi || 1;
        }
      }

      var qtyBase = cQtyGudang !== -1 ? toNumber_(r[cQtyGudang]) : (cQtyRaw !== -1 ? toNumber_(r[cQtyRaw]) : 0);
      var qty = cQtyGudang !== -1 ? qtyBase : qtyBase * (conv || 1);
      if (qty <= 0) { debug.skipQty++; return; }

      var rawKey = cTglKey !== -1 ? String(r[cTglKey] || "").trim() : "";
      var tglKey = normalizeDateKeyForWarehouse_(rawKey || (cTgl !== -1 ? r[cTgl] : ""));
      var d = tglKey ? parseDate_(tglKey) : (cTgl !== -1 ? parseOmniOrderDateOnly_(r[cTgl]) : null);
      if (d && d.getTime() < minDate.getTime()) { debug.skipDate++; return; }
      var tglDisplay = tglKey ? displayDateFromKey_(tglKey) : (d ? Utilities.formatDate(d, TZ, "dd/MM/yyyy") : formatDateDisplay_(cTgl !== -1 ? r[cTgl] : new Date()));
      if (!tglKey && d) tglKey = Utilities.formatDate(d, TZ, "yyyy-MM-dd");

      var status = cStatus !== -1 ? String(r[cStatus] || "").trim() : "";
      var resi = cResi !== -1 ? String(r[cResi] || "").trim() : "";
      var cancelLike = isCancelLikeStatusGudang_(status);
      if (cancelLike) debug.cancelLikeRows++;
      // v2.1: batal/cancel/retur/gagal TIDAK difilter. Tetap muncul di tarikan agar Gudang bisa kontrol qty batal atau barang terlanjur pack.

      var rowOut = {
        tgl: tglDisplay,
        tglKey: tglKey,
        toko: cToko !== -1 ? String(r[cToko] || "Toko Online").trim() : "Toko Online",
        no: no,
        sku: sku,
        product: product,
        variation: variation,
        status: status,
        statusBucket: cancelLike ? "BATAL_RETUR" : "NORMAL",
        cancelLike: cancelLike,
        resi: resi,
        nama: item,
        qty: qty,
        rawQty: qtyBase,
        conversionQty: conv || 1,
        mappingType: mappingType,
        mappingSource: mappingSource
      };
      out.push(rowOut);
      debug.passedRows++;
      debug.readyRows++;
      if (debug.samplePassedText.length < 5) debug.samplePassedText.push({ tanggal: rowOut.tgl, no: rowOut.no, toko: rowOut.toko, sku: rowOut.sku, product: rowOut.product, variation: rowOut.variation, item: rowOut.nama, qty: rowOut.qty, status: rowOut.status, mappingSource: rowOut.mappingSource });
    });
    readOmniOrders_._lastDebug = debug;
    return out;
  } catch (e) {
    debug.error = e && e.message ? e.message : String(e);
    readOmniOrders_._lastDebug = debug;
    logError_("readOmniOrders_", e, debug);
    return [];
  }
}

function buildPackedMaps_(movements) {
  var normal = {}, bundle = {};
  movements.forEach(function(m) {
    if (m.Direction !== "OUT" || m.Movement_Type !== "OMNI_OUT") return;

    // v2.0: source contract menjadi sumber utama. Notes hanya fallback legacy.
    var src = parseOmniSourceId_(m.Source_ID || "");
    var line = parseOmniSourceLine_(m.Source_Line_ID || "", m.Ref_No || "");
    var toko = src.toko;
    var tgl = src.tgl;

    if (!toko || !tgl) {
      var notes = m.Notes || "";
      toko = toko || extractNotePart_(notes, "Toko:");
      tgl = tgl || extractNotePart_(notes, "Tgl:");
      if (!line.item && !line.group) {
        var itemLegacy = extractNotePart_(notes, "Item:");
        var indukLegacy = extractNotePart_(notes, "Induk:");
        if (indukLegacy) line = { mode: "BUNDLE", group: indukLegacy, item: itemLegacy || "" };
        else if (itemLegacy) line = { mode: "ITEM", item: itemLegacy, group: "" };
      }
    }

    if (line.mode === "BUNDLE" && line.group) {
      bundle[toko + "|" + line.group + "|" + tgl] = (bundle[toko + "|" + line.group + "|" + tgl] || 0) + m.Qty;
    } else if (line.item) {
      normal[toko + "|" + line.item + "|" + tgl] = (normal[toko + "|" + line.item + "|" + tgl] || 0) + m.Qty;
    }
  });
  return { normal: normal, bundle: bundle };
}

function extractNotePart_(notes, label) {
  var parts = String(notes || "").split("|");
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i].trim();
    if (p.indexOf(label) !== -1) return p.split(label)[1].trim();
  }
  return "";
}


function normalizeBool_(value) {
  if (value === true) return true;
  var s = normalizeStockCode_(value);
  return s === "TRUE" || s === "YA" || s === "YES" || s === "1" || s === "GROUP" || s === "BUNDLE" || s === "SUB_CATEGORY";
}

function buildOmniActionTxKey_(input) {
  input = input || {};
  if (input.Tx_Key) return normalizeStockText_(input.Tx_Key);
  return [
    "WH_OMNI_ACTION_V1",
    normalizeStockCode_(input.Action_Type || "ACTION"),
    normalizeStockText_(input.Source_ID || ""),
    normalizeStockText_(input.Source_Line_ID || ""),
    normalizeStockText_(input.Ref_No || ""),
    normalizeDateKeyForWarehouse_(input.Source_Date || input.Tanggal || "") || normalizeStockText_(input.Source_Date || input.Tanggal || ""),
    String(toNumber_(input.Qty || 0))
  ].map(stockValueForKey_).join("|");
}

function readOmniActionKeySet_() {
  var ss = getActiveGudang_();
  ensureSheetWithHeaders_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS);
  var t = readTable_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS, { noCreate: false });
  var cTx = col_(t.info, "Tx_Key", -1);
  var cAction = col_(t.info, "Action_ID", -1);
  var cDeleted = col_(t.info, "Is_Deleted", -1);
  var out = {};
  t.rows.forEach(function(r) {
    var del = cDeleted !== -1 ? normalizeStockCode_(r[cDeleted]) : "";
    if (del === "TRUE" || del === "YA" || del === "1") return;
    var tx = cTx !== -1 ? normalizeStockText_(r[cTx]) : "";
    var action = cAction !== -1 ? normalizeStockText_(r[cAction]) : "";
    if (tx) out[tx] = true;
    if (action) out["ACTION_ID|" + action] = true;
  });
  return out;
}

function appendOmniActionLog_(input) {
  input = input || {};
  var actionId = normalizeStockText_(input.Action_ID || uuid_("OA"));
  var sourceDate = normalizeDateKeyForWarehouse_(input.Source_Date || input.Tanggal || "");
  var obj = {
    Action_ID: actionId,
    Tx_Key: buildOmniActionTxKey_(Object.assign({}, input, { Action_ID: actionId, Source_Date: sourceDate })),
    Tanggal: input.Tanggal || new Date(),
    Source_Date: sourceDate,
    Toko: normalizeStockText_(input.Toko || ""),
    Item_Name: normalizeStockText_(input.Item_Name || ""),
    Action_Type: normalizeStockCode_(input.Action_Type || "OMNI_ACTION"),
    Qty: toNumber_(input.Qty || 0),
    Source_ID: normalizeStockText_(input.Source_ID || ""),
    Source_Line_ID: normalizeStockText_(input.Source_Line_ID || ""),
    Ref_No: normalizeStockText_(input.Ref_No || ""),
    Batch_ID: normalizeStockText_(input.Batch_ID || ""),
    External_Ref: normalizeStockText_(input.External_Ref || ""),
    Notes: normalizeStockText_(input.Notes || ""),
    Status: normalizeStockText_(input.Status || "POSTED") || "POSTED",
    Created_At: new Date(),
    Created_By: normalizeStockText_(input.Created_By || userEmail_()),
    Is_Deleted: ""
  };
  if (!obj.Item_Name) throw new Error("Item tarikan kosong.");
  if (obj.Qty <= 0) throw new Error("Qty aksi harus lebih dari 0.");
  var keys = readOmniActionKeySet_();
  if (keys[obj.Tx_Key]) return Object.assign({}, obj, { __duplicate: true });
  appendRowsByHeader_(getActiveGudang_(), SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS, [obj]);
  return obj;
}

function readOmniActionLogs_() {
  var ss = getActiveGudang_();
  ensureSheetWithHeaders_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS);
  var t = readTable_(ss, SHEET_OMNI_ACTION_LOG, OMNI_ACTION_LOG_HEADERS, { noCreate: false });
  var info = t.info;
  var c = {
    actionId: col_(info, "Action_ID", -1), tx: col_(info, "Tx_Key", -1), tgl: col_(info, "Tanggal", -1), sourceDate: col_(info, "Source_Date", -1),
    toko: col_(info, "Toko", -1), itemName: col_(info, "Item_Name", -1), actionType: col_(info, "Action_Type", -1), qty: col_(info, "Qty", -1),
    sourceId: col_(info, "Source_ID", -1), sourceLine: col_(info, "Source_Line_ID", -1), refNo: col_(info, "Ref_No", -1), batchId: col_(info, "Batch_ID", -1),
    externalRef: col_(info, "External_Ref", -1), notes: col_(info, "Notes", -1), status: col_(info, "Status", -1), createdAt: col_(info, "Created_At", -1), createdBy: col_(info, "Created_By", -1), deleted: col_(info, "Is_Deleted", -1)
  };
  var out = [];
  t.rows.forEach(function(r, idx) {
    var del = c.deleted !== -1 ? normalizeStockCode_(r[c.deleted]) : "";
    if (del === "TRUE" || del === "YA" || del === "1") return;
    out.push({
      __rowNumber: idx + 2,
      Action_ID: c.actionId !== -1 ? normalizeStockText_(r[c.actionId]) : "",
      Tx_Key: c.tx !== -1 ? normalizeStockText_(r[c.tx]) : "",
      Tanggal: c.tgl !== -1 ? r[c.tgl] : "",
      Source_Date: c.sourceDate !== -1 ? normalizeStockText_(r[c.sourceDate]) : "",
      Toko: c.toko !== -1 ? normalizeStockText_(r[c.toko]) : "",
      Item_Name: c.itemName !== -1 ? normalizeStockText_(r[c.itemName]) : "",
      Action_Type: c.actionType !== -1 ? normalizeStockCode_(r[c.actionType]) : "",
      Qty: c.qty !== -1 ? toNumber_(r[c.qty]) : 0,
      Source_ID: c.sourceId !== -1 ? normalizeStockText_(r[c.sourceId]) : "",
      Source_Line_ID: c.sourceLine !== -1 ? normalizeStockText_(r[c.sourceLine]) : "",
      Ref_No: c.refNo !== -1 ? normalizeStockText_(r[c.refNo]) : "",
      Batch_ID: c.batchId !== -1 ? normalizeStockText_(r[c.batchId]) : "",
      External_Ref: c.externalRef !== -1 ? normalizeStockText_(r[c.externalRef]) : "",
      Notes: c.notes !== -1 ? normalizeStockText_(r[c.notes]) : "",
      Status: c.status !== -1 ? normalizeStockText_(r[c.status]) : "POSTED",
      Created_At: c.createdAt !== -1 ? r[c.createdAt] : "",
      Created_By: c.createdBy !== -1 ? normalizeStockText_(r[c.createdBy]) : ""
    });
  });
  return out;
}

function buildOmniConsumptionMaps_(movements, actions) {
  var normalPack = {}, bundlePack = {}, normalCancel = {}, bundleCancel = {};
  (movements || []).forEach(function(m) {
    if (m.Direction !== "OUT" || m.Movement_Type !== "OMNI_OUT") return;
    var src = parseOmniSourceId_(m.Source_ID || "");
    var line = parseOmniSourceLine_(m.Source_Line_ID || "", m.Ref_No || "");
    var toko = src.toko;
    var tgl = src.tgl;
    if (!toko || !tgl) {
      var notes = m.Notes || "";
      toko = toko || extractNotePart_(notes, "Toko:");
      tgl = tgl || extractNotePart_(notes, "Tgl:");
      if (!line.item && !line.group) {
        var itemLegacy = extractNotePart_(notes, "Item:");
        var indukLegacy = extractNotePart_(notes, "Induk:");
        if (indukLegacy) line = { mode: "BUNDLE", group: indukLegacy, item: itemLegacy || "" };
        else if (itemLegacy) line = { mode: "ITEM", item: itemLegacy, group: "" };
      }
    }
    if (line.mode === "BUNDLE" && line.group) bundlePack[toko + "|" + line.group + "|" + tgl] = (bundlePack[toko + "|" + line.group + "|" + tgl] || 0) + m.Qty;
    else if (line.item) normalPack[toko + "|" + line.item + "|" + tgl] = (normalPack[toko + "|" + line.item + "|" + tgl] || 0) + m.Qty;
  });

  (actions || []).forEach(function(a) {
    if (normalizeStockCode_(a.Action_Type) !== "OMNI_CANCEL_CLEAR") return;
    var src = parseOmniSourceId_(a.Source_ID || "");
    var line = parseOmniSourceLine_(a.Source_Line_ID || "", a.Ref_No || "");
    var toko = src.toko || a.Toko || extractNotePart_(a.Notes || "", "Toko:");
    var tgl = src.tgl || (a.Source_Date ? displayDateFromKey_(a.Source_Date) : "") || extractNotePart_(a.Notes || "", "Tgl:");
    if (line.mode === "BUNDLE" && line.group) bundleCancel[toko + "|" + line.group + "|" + tgl] = (bundleCancel[toko + "|" + line.group + "|" + tgl] || 0) + a.Qty;
    else {
      var item = line.item || a.Item_Name;
      if (item) normalCancel[toko + "|" + item + "|" + tgl] = (normalCancel[toko + "|" + item + "|" + tgl] || 0) + a.Qty;
    }
  });

  var normalTotal = {}, bundleTotal = {};
  Object.keys(normalPack).forEach(function(k){ normalTotal[k] = (normalTotal[k] || 0) + normalPack[k]; });
  Object.keys(normalCancel).forEach(function(k){ normalTotal[k] = (normalTotal[k] || 0) + normalCancel[k]; });
  Object.keys(bundlePack).forEach(function(k){ bundleTotal[k] = (bundleTotal[k] || 0) + bundlePack[k]; });
  Object.keys(bundleCancel).forEach(function(k){ bundleTotal[k] = (bundleTotal[k] || 0) + bundleCancel[k]; });
  return { normalPack: normalPack, bundlePack: bundlePack, normalCancel: normalCancel, bundleCancel: bundleCancel, normalTotal: normalTotal, bundleTotal: bundleTotal };
}

// =========================== INIT DATA ===========================

function getInitDataGudang(emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  try {
    var started = new Date();
    var res = {
      success: true,
      bahan: [],
      jadi: [],
      pr: [],
      tarikanOmni: [],
      mutasi: [],
      dash: { lowBahan: 0, lowJadi: 0, totalAset: 0, totalPR: 0, totalPcsStok: 0 }
    };

    var lookup = buildItemLookup_();
    var movements = readStockMovements_();
    var auditMap = getAuditLockMap_();
    var bal = buildBalance_(lookup.items, movements);

    var rawBahan = [], rawJadi = [];
    var mapAnakSubKategori = {};
    var mapStokFisikGrouped = {};

    lookup.items.forEach(function(it) {
      var stok = bal.qty[it.Item_ID] || 0;
      var row = {
        id: it.Item_ID,
        nama: it.Item_Name,
        kat: it.Category || "Umum",
        sub: it.Sub_Category || "Umum",
        stok: stok,
        min: it.Min_Stock || 0,
        status: stok <= (it.Min_Stock || 0) ? "LOW" : "AMAN"
      };
      var type = String(it.Item_Type || "").toUpperCase();
      var isBahan = ["BAHAN", "RAW_MATERIAL", "AKSESORIS", "ACCESSORY", "PACKAGING", "CONSUMABLE"].indexOf(type) !== -1;
      var isJadi = ["BARANG_JADI", "FINISHED_GOODS", "BUNDLE"].indexOf(type) !== -1 || !isBahan;
      if (isBahan) {
        rawBahan.push(row);
        if (row.status === "LOW") res.dash.lowBahan++;
      } else if (isJadi) {
        rawJadi.push(row);
        if (row.status === "LOW") res.dash.lowJadi++;
        if (row.sub && row.sub !== "Umum") {
          if (!mapAnakSubKategori[row.sub]) mapAnakSubKategori[row.sub] = [];
          mapAnakSubKategori[row.sub].push({ nama: row.nama });
        }
      }
      if (stok > 0) {
        res.dash.totalPcsStok += stok;
        res.dash.totalAset += stok * (bal.cost[it.Item_ID] || it.Default_Cost || 0);
      }
    });

    rawBahan.sort(function(a,b){ return (a.kat+a.sub+a.nama).localeCompare(b.kat+b.sub+b.nama); });
    rawJadi.sort(function(a,b){ return (a.kat+a.sub+a.nama).localeCompare(b.kat+b.sub+b.nama); });
    res.bahan = rawBahan;
    res.jadi = rawJadi;

    rawJadi.forEach(function(i) {
      mapStokFisikGrouped[i.nama] = i.stok;
      if (i.sub && i.sub !== "Umum") mapStokFisikGrouped[i.sub] = (mapStokFisikGrouped[i.sub] || 0) + i.stok;
    });

    // v2.6: loading awal memakai summary produk Omni. Detail raw hanya dimuat saat tab Tarikan dibuka.
    var omniActionLogs = readOmniActionLogs_();
    var omniSummary = readOmniWarehouseSummary_();
    var omniRows = [];
    var demand = {};
    var omniDebug = omniSummary.debug || {};
    var sourceMode = "OMNI_DAILY_PRODUCT_SUMMARY";
    var includeTarikanOnInit = false;

    if (omniSummary.ready) {
      demand = buildOmniDemandFromSummaryRows_(omniSummary.rows);
    } else {
      // Fallback aman: sebelum Omni v1.6.4 selesai dipasang/rebuild, perilaku lama tetap berjalan.
      omniRows = readOmniOrders_();
      omniDebug = readOmniOrders_._lastDebug || omniDebug;
      demand = buildOmniDemandFromRawRows_(omniRows);
      sourceMode = "OMNI_ORDER_RAW_FALLBACK";
      includeTarikanOnInit = true;
    }

    var omniBuilt = buildGudangOmniOutputs_(demand, {
      lookup: lookup,
      bal: bal,
      mapAnakSubKategori: mapAnakSubKategori,
      mapStokFisikGrouped: mapStokFisikGrouped,
      movements: movements,
      omniActionLogs: omniActionLogs
    }, includeTarikanOnInit);

    res.pr = omniBuilt.pr;
    res.tarikanOmni = omniBuilt.tarikanOmni;
    res.dash.totalPR = res.pr.length;

    movements.sort(function(a,b) {
      var da = parseDate_(a.Tanggal || a.Created_At); var db = parseDate_(b.Tanggal || b.Created_At);
      return (db ? db.getTime() : 0) - (da ? da.getTime() : 0);
    });
    res.mutasi = movements.slice(0, MUTASI_RETURN_LIMIT).map(function(m) { return movementToUi_(m, lookup, auditMap); });

    res.meta = {
      elapsedMs: new Date().getTime() - started.getTime(),
      contractVersion: STOCK_CONTRACT_VERSION,
      costVersion: STOCK_COST_VERSION,
      movementCount: movements.length,
      omniActionCount: omniActionLogs.length,
      omniCount: omniSummary.ready ? omniSummary.rows.length : omniRows.length,
      omniRawCount: omniDebug.rawRows || 0,
      omniSummaryRows: omniDebug.summaryRows || 0,
      omniSheetLastRow: omniDebug.sheetLastRow || 0,
      omniSource: omniDebug.source || "",
      omniModuleCode: omniDebug.moduleCode || "",
      omniSkipDate: omniDebug.skipDate || 0,
      omniSkipNoItem: omniDebug.skipNoItem || 0,
      omniSkipQty: omniDebug.skipQty || 0,
      omniSkipCancelNoResi: omniDebug.skipCancelNoResi || 0,
      omniCancelLikeRows: omniDebug.cancelLikeRows || 0,
      omniMappedDirectRows: omniDebug.mappedDirectRows || 0,
      omniMappedFallbackRows: omniDebug.mappedFallbackRows || 0,
      omniMappedBySkuRows: omniDebug.mappedBySkuRows || 0,
      omniMappedByVariantRows: omniDebug.mappedByVariantRows || 0,
      omniAmbiguousMappingRows: omniDebug.ambiguousMappingRows || 0,
      omniReadyRows: omniDebug.readyRows || omniDebug.passedRows || 0,
      omniMode: sourceMode,
      omniSummaryReady: !!omniSummary.ready,
      omniSummaryVersion: omniDebug.version || "",
      tarikanLazy: !includeTarikanOnInit,
      tarikanCountEstimate: omniBuilt.tarikanCountEstimate || 0,
      omniError: omniDebug.error || ""
    };
    try { res.meta.heartbeat = ERP_readGlobalHeartbeat_(); } catch(e) { res.meta.heartbeat = { version: "", updatedAt: "", notes: e.message || String(e) }; }
    return res;
  } catch (e) {
    logError_("getInitDataGudang", e, {});
    return { success: false, msg: e.message };
  }
}


function getTarikanOmniGudang(emailOp, pasporOp) {
  GUDANG_requirePassport_(emailOp, pasporOp);
  try {
    var started = new Date();
    var lookup = buildItemLookup_();
    var movements = readStockMovements_();
    var bal = buildBalance_(lookup.items, movements);
    var omniActionLogs = readOmniActionLogs_();
    var mapAnakSubKategori = {};
    var mapStokFisikGrouped = {};

    lookup.items.forEach(function(it) {
      var type = String(it.Item_Type || "").toUpperCase();
      var isBahan = ["BAHAN", "RAW_MATERIAL", "AKSESORIS", "ACCESSORY", "PACKAGING", "CONSUMABLE"].indexOf(type) !== -1;
      if (isBahan) return;
      var stok = bal.qty[it.Item_ID] || 0;
      mapStokFisikGrouped[it.Item_Name] = stok;
      var sub = it.Sub_Category || "";
      if (sub && sub !== "Umum") {
        if (!mapAnakSubKategori[sub]) mapAnakSubKategori[sub] = [];
        mapAnakSubKategori[sub].push({ nama: it.Item_Name });
        mapStokFisikGrouped[sub] = (mapStokFisikGrouped[sub] || 0) + stok;
      }
    });

    var omniRows = readOmniOrders_();
    var built = buildGudangOmniOutputs_(buildOmniDemandFromRawRows_(omniRows), {
      lookup: lookup,
      bal: bal,
      mapAnakSubKategori: mapAnakSubKategori,
      mapStokFisikGrouped: mapStokFisikGrouped,
      movements: movements,
      omniActionLogs: omniActionLogs
    }, true);
    var debug = readOmniOrders_._lastDebug || {};
    return {
      success: true,
      tarikanOmni: built.tarikanOmni,
      meta: {
        elapsedMs: new Date().getTime() - started.getTime(),
        sourceMode: "OMNI_ORDER_RAW_LAZY_DETAIL",
        omniRawCount: debug.rawRows || 0,
        omniReadyRows: debug.readyRows || debug.passedRows || omniRows.length,
        omniCancelLikeRows: debug.cancelLikeRows || 0,
        omniError: debug.error || ""
      }
    };
  } catch (e) {
    logError_("getTarikanOmniGudang", e, {});
    return { success: false, msg: e.message || String(e), tarikanOmni: [] };
  }
}

function TEST_gudangOmniSummaryReader(emailOp, pasporOp) {
  GUDANG_requirePassport_(emailOp, pasporOp);
  var summary = readOmniWarehouseSummary_();
  var out = {
    success: !!summary.ready,
    expectedVersion: OMNI_WAREHOUSE_SUMMARY_VERSION,
    summaryRowsInLookback: summary.rows.length,
    debug: summary.debug,
    rule: "PR memakai summary; detail dan aksi tetap Omni_Order raw."
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}


function TEST_gudangOmniSummaryVsRaw(emailOp, pasporOp) {
  GUDANG_requirePassport_(emailOp, pasporOp);
  var started = new Date();
  var summary = readOmniWarehouseSummary_();
  if (!summary.ready) return { success:false, error:summary.debug && summary.debug.error || 'Summary belum siap.', debug:summary.debug };

  var lookup = buildItemLookup_();
  var movements = readStockMovements_();
  var bal = buildBalance_(lookup.items, movements);
  var actions = readOmniActionLogs_();
  var mapAnakSubKategori = {};
  var mapStokFisikGrouped = {};
  lookup.items.forEach(function(it) {
    var type = String(it.Item_Type || '').toUpperCase();
    var isBahan = ['BAHAN','RAW_MATERIAL','AKSESORIS','ACCESSORY','PACKAGING','CONSUMABLE'].indexOf(type) !== -1;
    if (isBahan) return;
    var stok = bal.qty[it.Item_ID] || 0;
    mapStokFisikGrouped[it.Item_Name] = stok;
    var sub = it.Sub_Category || '';
    if (sub && sub !== 'Umum') {
      if (!mapAnakSubKategori[sub]) mapAnakSubKategori[sub] = [];
      mapAnakSubKategori[sub].push({ nama:it.Item_Name });
      mapStokFisikGrouped[sub] = (mapStokFisikGrouped[sub] || 0) + stok;
    }
  });
  var ctx = {
    lookup:lookup, bal:bal, mapAnakSubKategori:mapAnakSubKategori,
    mapStokFisikGrouped:mapStokFisikGrouped, movements:movements, omniActionLogs:actions
  };
  var summaryOut = buildGudangOmniOutputs_(buildOmniDemandFromSummaryRows_(summary.rows), ctx, false);
  var rawRows = readOmniOrders_();
  var rawOut = buildGudangOmniOutputs_(buildOmniDemandFromRawRows_(rawRows), ctx, false);

  function indexPr_(rows) {
    var out = {};
    (rows || []).forEach(function(r) {
      out[r.nama] = {
        butuh:toNumber_(r.butuh), fisik:toNumber_(r.fisik), pr:toNumber_(r.pr),
        orderCount:toNumber_(r.orderCount), cancelLikeQty:toNumber_(r.cancelLikeQty)
      };
    });
    return out;
  }
  var a = indexPr_(summaryOut.pr);
  var b = indexPr_(rawOut.pr);
  var keys = {};
  Object.keys(a).forEach(function(k){ keys[k]=true; });
  Object.keys(b).forEach(function(k){ keys[k]=true; });
  var differences = [];
  Object.keys(keys).sort().forEach(function(k) {
    var x = a[k] || {butuh:0,fisik:0,pr:0,orderCount:0,cancelLikeQty:0};
    var y = b[k] || {butuh:0,fisik:0,pr:0,orderCount:0,cancelLikeQty:0};
    var fields = ['butuh','fisik','pr','orderCount','cancelLikeQty'];
    var diff = {};
    fields.forEach(function(f) { if (Math.abs(toNumber_(x[f]) - toNumber_(y[f])) > 0.000001) diff[f] = { summary:x[f], raw:y[f] }; });
    if (Object.keys(diff).length) differences.push({ item:k, fields:diff });
  });

  var out = {
    success:differences.length === 0 && summaryOut.tarikanCountEstimate === rawOut.tarikanCountEstimate,
    summaryVersion:OMNI_WAREHOUSE_SUMMARY_VERSION,
    summaryRows:summary.rows.length,
    rawRows:rawRows.length,
    summaryPrRows:summaryOut.pr.length,
    rawPrRows:rawOut.pr.length,
    summaryTarikanGroups:summaryOut.tarikanCountEstimate,
    rawTarikanGroups:rawOut.tarikanCountEstimate,
    differences:differences.slice(0,100),
    differenceCount:differences.length,
    elapsedMs:new Date().getTime() - started.getTime()
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}


function TEST_masterModuleRouting() {
  clearMasterCache_();
  var modules = getMasterModules_();
  var omni = getOmniModuleInfo_();
  var out = {
    success: !!(omni && omni.Spreadsheet_ID),
    expectedHeader: "Module_Code | Module_Name | Spreadsheet_ID | Spreadsheet_URL | Web_App_URL | Status | Notes",
    omniResolved: omni || null,
    omniHardcodeOverrideActive: !!extractSpreadsheetId_(OMNI_SPREADSHEET_ID_OVERRIDE),
    modules: modules.map(function(m) {
      return {
        Module_Code: m.Module_Code,
        Module_Name: m.Module_Name,
        Spreadsheet_ID: m.Spreadsheet_ID ? (m.Spreadsheet_ID.slice(0, 8) + "..." + m.Spreadsheet_ID.slice(-6)) : "",
        Spreadsheet_URL_OK: !!extractSpreadsheetId_(m.Spreadsheet_URL),
        Web_App_URL_OK: isWebAppUrl_(m.Web_App_URL),
        Status: m.Status
      };
    })
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

function TEST_tarikanOmniDariOrder() {
  clearMasterCache_();
  var out = TEST_masterModuleRouting();
  try {
    var omniInfo = getOmniSpreadsheetInfo_();
    if (!omniInfo || !omniInfo.Spreadsheet_ID) throw new Error("Routing OMNI belum ketemu. Isi Master_Module atau OMNI_SPREADSHEET_ID_OVERRIDE.");
    var ss = SpreadsheetApp.openById(omniInfo.Spreadsheet_ID);
    var t = readTable_(ss, "Omni_Order", null, { noCreate: true });
    if (!t.sheet) throw new Error("Sheet Omni_Order tidak ditemukan di file Omni.");
    out.omniSpreadsheetName = ss.getName();
    out.omniSheetLastRow = t.lastRow || 0;
    out.omniHeaders = t.info.headers;
    var cNo = col_(t.info, ["No Pesanan", "Order_No", "Nomor Pesanan"], -1);
    var cItem = col_(t.info, ["Item Gudang", "Item_Gudang", "Mapped_Sub_Category", "Target_Sub_Category", "Internal_Item_Name", "Nama Item", "Nama Barang", "Item_Name"], -1);
    var cQty = col_(t.info, ["Qty Gudang", "Qty_Gudang", "Internal_Qty", "Qty"], -1);
    var cTgl = col_(t.info, ["Tanggal", "Order_Date", "Tgl Pesanan", "Waktu Pesanan Dibuat"], -1);
    out.requiredColumnIndex = { noPesanan: cNo, itemGudang: cItem, qtyGudang: cQty, tanggal: cTgl };
    out.rawSample = t.rows.slice(0, 5).map(function(r) {
      return { No_Pesanan: cNo !== -1 ? cellDebugValue_(r[cNo]) : "", Item_Gudang: cItem !== -1 ? cellDebugValue_(r[cItem]) : "", Qty_Gudang: cQty !== -1 ? cellDebugValue_(r[cQty]) : "", Tanggal: cTgl !== -1 ? cellDebugValue_(r[cTgl]) : "" };
    });
    var rows = readOmniOrders_();
    var res = getInitDataGudang();
    out.success = true;
    out.readOmniDebug = readOmniOrders_._lastDebug || {};
    out.omniRowsReadAfterFilter = rows.length;
    out.tarikanCount = res.tarikanOmni ? res.tarikanOmni.length : 0;
    out.prCount = res.pr ? res.pr.length : 0;
    out.sampleTarikan = res.tarikanOmni ? res.tarikanOmni.slice(0, 10) : [];
    out.samplePR = res.pr ? res.pr.slice(0, 10) : [];
  } catch (e) {
    out.success = false;
    out.error = e.message;
    logError_("TEST_tarikanOmniDariOrder", e, out);
  }
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}


function normalizeDateKeyForWarehouse_(value) {
  if (!value) return "";
  if (value instanceof Date && !isNaN(value.getTime())) return Utilities.formatDate(value, TZ, "yyyy-MM-dd");
  var s = String(value || "").trim();
  if (!s) return "";
  var m = s.match(/^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})/);
  if (m) return m[1] + "-" + ("0" + m[2]).slice(-2) + "-" + ("0" + m[3]).slice(-2);
  var d = parseOmniOrderDateOnly_(s) || parseDate_(s);
  return d ? Utilities.formatDate(d, TZ, "yyyy-MM-dd") : "";
}

function displayDateFromKey_(key) {
  var m = String(key || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return String(key || "");
  return m[3] + "/" + m[2] + "/" + m[1];
}

function consumeOmniOrderRemaining_(namaItem, tglTarikan, namaToko, qtyPack, doWrite) {
  var qty = toNumber_(qtyPack);
  if (qty <= 0) return { success: false, msg: "Qty pack harus lebih dari 0." };

  var targetDateKey = normalizeDateKeyForWarehouse_(tglTarikan);
  var targetDisplay = targetDateKey ? displayDateFromKey_(targetDateKey) : String(tglTarikan || "").trim();
  var targetItem = String(namaItem || "").trim();
  var targetToko = String(namaToko || "").trim();

  var demand = 0;
  readOmniOrders_().forEach(function(o) {
    var okDate = targetDateKey ? (o.tglKey === targetDateKey) : (o.tgl === targetDisplay);
    if (okDate && String(o.toko || "").trim() === targetToko && String(o.nama || "").trim() === targetItem) demand += toNumber_(o.qty);
  });

  var maps = buildOmniConsumptionMaps_(readStockMovements_(), readOmniActionLogs_());
  var key = targetToko + "|" + targetItem + "|" + targetDisplay;
  var consumedQty = Math.max(toNumber_(maps.normalTotal[key]), toNumber_(maps.bundleTotal[key]));
  var packedQty = Math.max(toNumber_(maps.normalPack[key]), toNumber_(maps.bundlePack[key]));
  var cancelClearedQty = Math.max(toNumber_(maps.normalCancel[key]), toNumber_(maps.bundleCancel[key]));
  var available = Math.max(0, demand - consumedQty);

  if (available + 0.000001 < qty) {
    return { success: false, msg: "Sisa tarikan Omni tidak cukup. Demand: " + demand + ", sudah diproses: " + consumedQty + " (pack " + packedQty + ", batal " + cancelClearedQty + "), sisa: " + available + ", diminta: " + qty, available: available, requested: qty, demand: demand, packedQty: packedQty, cancelClearedQty: cancelClearedQty, consumedQty: consumedQty };
  }
  return { success: true, available: available, requested: qty, demand: demand, packedQty: packedQty, cancelClearedQty: cancelClearedQty, consumedQty: consumedQty, noOmniUpdate: true };
}

function validateBatchStockAvailability_(inputs) {
  var lookup = buildItemLookup_();
  var movements = readStockMovements_();
  var bal = buildBalance_(lookup.items, movements);
  var need = {};
  (inputs || []).forEach(function(input) {
    var item = input.Item_ID ? lookup.byId[input.Item_ID] : null;
    if (!item && input.Item_Name) item = lookup.byName[String(input.Item_Name || "").trim()];
    if (!item) throw new Error("Item tidak ditemukan di Master_Item: " + (input.Item_ID || input.Item_Name || ""));
    need[item.Item_ID] = (need[item.Item_ID] || 0) + toNumber_(input.Qty);
  });
  Object.keys(need).forEach(function(itemId) {
    var item = lookup.byId[itemId];
    var stok = bal.qty[itemId] || 0;
    if (need[itemId] > stok) throw new Error("Stok tidak cukup untuk " + item.Item_Name + ". Stok tersedia: " + stok + ", diminta: " + need[itemId]);
  });
  return true;
}

// =========================== ACTIONS ===========================

function simpanBatalOmni(namaItem, tglTarikan, qtyBatal, namaToko, isGroup, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var qty = toNumber_(qtyBatal);
    if (qty <= 0) throw new Error("Qty batal/tidak pack harus lebih dari 0.");

    var targetDateKey = normalizeDateKeyForWarehouse_(tglTarikan);
    var tglDisplay = targetDateKey ? displayDateFromKey_(targetDateKey) : String(tglTarikan || "").trim();
    var targetItem = String(namaItem || "").trim();
    var targetToko = String(namaToko || "").trim();
    var groupMode = normalizeBool_(isGroup);

    var demand = { totalQty: 0, normalQty: 0, cancelLikeQty: 0, cancelLikeOrders: 0, orderMap: {} };
    readOmniOrders_().forEach(function(o) {
      var okDate = targetDateKey ? (o.tglKey === targetDateKey) : (o.tgl === tglDisplay);
      if (!okDate || String(o.toko || "").trim() !== targetToko || String(o.nama || "").trim() !== targetItem) return;
      demand.totalQty += toNumber_(o.qty);
      if (o.cancelLike) {
        demand.cancelLikeQty += toNumber_(o.qty);
        if (!demand.orderMap[o.no]) { demand.orderMap[o.no] = true; demand.cancelLikeOrders++; }
      } else {
        demand.normalQty += toNumber_(o.qty);
      }
    });
    if (demand.cancelLikeQty <= 0) throw new Error("Tidak ada qty batal/retur/gagal yang bisa ditandai tidak pack untuk baris ini.");

    var maps = buildOmniConsumptionMaps_(readStockMovements_(), readOmniActionLogs_());
    var key = targetToko + "|" + targetItem + "|" + tglDisplay;
    var packedQty = groupMode ? (maps.bundlePack[key] || 0) : (maps.normalPack[key] || 0);
    var cancelClearedQty = groupMode ? (maps.bundleCancel[key] || 0) : (maps.normalCancel[key] || 0);
    var packedAppliedToCancel = Math.max(0, packedQty - (demand.normalQty || 0));
    var cancelRemaining = Math.max(0, (demand.cancelLikeQty || 0) - cancelClearedQty - packedAppliedToCancel);
    if (cancelRemaining + 0.000001 < qty) {
      throw new Error("Qty batal tersisa tidak cukup. Total batal: " + demand.cancelLikeQty + ", sudah dipack/ditandai: " + (cancelClearedQty + packedAppliedToCancel) + ", sisa batal: " + cancelRemaining + ", diminta: " + qty);
    }

    var tglKey = targetDateKey || normalizeDateKeyForWarehouse_(tglTarikan);
    var sourceId = buildOmniSourceId_(tglKey || normalizeStockText_(tglTarikan), namaToko);
    var sourceLineId = groupMode ? buildOmniSourceLine_("BUNDLE", namaItem, "") : buildOmniSourceLine_("ITEM", namaItem);
    var row = appendOmniActionLog_({
      Tanggal: new Date(),
      Source_Date: tglKey,
      Toko: namaToko,
      Item_Name: namaItem,
      Action_Type: "OMNI_CANCEL_CLEAR",
      Qty: qty,
      Source_ID: sourceId,
      Source_Line_ID: sourceLineId,
      Ref_No: (groupMode ? "BATAL-TIDAK-PACK-BUNDLE" : "BATAL-TIDAK-PACK") + "|PREV:" + cancelClearedQty,
      Batch_ID: "BATAL|" + normalizeStockText_(tglKey || tglTarikan) + "|" + normalizeStockText_(namaToko),
      External_Ref: namaToko + "|" + namaItem + "|" + tglDisplay,
      Notes: "Batal Omni tidak dipack | Toko: " + namaToko + " | Item: " + namaItem + " | Tgl: " + tglDisplay,
      Created_By: __auth.email
    });

    GUDANG_touchMutation_("simpanBatalOmni");
    return { success: true, action: row, remainingMode: "OMNI_ORDER_MINUS_PACK_AND_CANCEL", duplicate: !!row.__duplicate };
  } catch (e) {
    logError_("simpanBatalOmni", e, { namaItem: namaItem, tglTarikan: tglTarikan, qtyBatal: qtyBatal, namaToko: namaToko, isGroup: isGroup });
    return { success: false, msg: e.message };
  } finally { lock.releaseLock(); }
}

function simpanPackingOmni(namaItem, tglTarikan, qtyPacking, namaToko, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var qty = toNumber_(qtyPacking);
    var dry = consumeOmniOrderRemaining_(namaItem, tglTarikan, namaToko, qty, false);
    if (!dry.success) throw new Error(dry.msg || "Sisa tarikan Omni tidak cukup.");

    var tglKey = normalizeDateKeyForWarehouse_(tglTarikan);
    var tglDisplay = tglKey ? displayDateFromKey_(tglKey) : tglTarikan;
    var sourceId = buildOmniSourceId_(tglKey || normalizeStockText_(tglTarikan), namaToko);
    var sourceLineId = buildOmniSourceLine_("ITEM", namaItem);
    var row = appendStockMovement_({
      Tanggal: new Date(),
      Source_Date: tglKey || normalizeDateKeyForWarehouse_(tglTarikan),
      Item_Name: namaItem,
      Direction: "OUT",
      Movement_Type: "OMNI_OUT",
      Qty: qty,
      Source_Module: "OMNI",
      Source_ID: sourceId,
      Source_Line_ID: sourceLineId,
      Ref_No: "PACK-OMNI",
      External_Ref: namaToko + "|" + namaItem + "|" + tglDisplay,
      Notes: "Packing Omni | Toko: " + namaToko + " | Item: " + namaItem + " | Tgl: " + tglDisplay,
      Created_By: __auth.email
    });

    GUDANG_touchMutation_("simpanPackingOmni");
    return { success: true, movement: row, remainingMode: "OMNI_ORDER_MINUS_STOCK_MOVEMENT" };
  } catch (e) {
    logError_("simpanPackingOmni", e, { namaItem: namaItem, tglTarikan: tglTarikan, qtyPacking: qtyPacking, namaToko: namaToko });
    return { success: false, msg: e.message };
  } finally { lock.releaseLock(); }
}


function simpanPecahVarianBatch(subKategori, tglTarikan, arrayInputVarian, namaToko, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var inputs = [];
    var totalQty = 0;
    var tglKey = normalizeDateKeyForWarehouse_(tglTarikan);
    var tglDisplay = tglKey ? displayDateFromKey_(tglKey) : tglTarikan;

    (arrayInputVarian || []).forEach(function(item) {
      var qty = toNumber_(item.qty);
      if (qty > 0) {
        totalQty += qty;
        inputs.push({
          Tanggal: new Date(),
          Source_Date: tglKey || normalizeDateKeyForWarehouse_(tglTarikan),
          Item_Name: item.nama,
          Direction: "OUT",
          Movement_Type: "OMNI_OUT",
          Qty: qty,
          Source_Module: "OMNI",
          Source_ID: buildOmniSourceId_(tglKey || normalizeStockText_(tglTarikan), namaToko),
          Source_Line_ID: buildOmniSourceLine_("BUNDLE", subKategori, item.nama),
          Ref_No: "PACK-OMNI-BUNDLE",
          Batch_ID: "BUNDLE|" + normalizeStockText_(subKategori) + "|" + normalizeStockText_(tglKey || tglTarikan) + "|" + normalizeStockText_(namaToko),
          External_Ref: namaToko + "|" + subKategori + "|" + item.nama + "|" + tglDisplay,
          Notes: "Packing Omni | Toko: " + namaToko + " | Induk: " + subKategori + " | Varian: " + item.nama + " | Tgl: " + tglDisplay,
          Created_By: __auth.email
        });
      }
    });
    if (!inputs.length) throw new Error("Tidak ada varian yang diinput.");

    var dry = consumeOmniOrderRemaining_(subKategori, tglTarikan, namaToko, totalQty, false);
    if (!dry.success) throw new Error(dry.msg || "Sisa tarikan Omni tidak cukup.");

    validateBatchStockAvailability_(inputs);
    var rows = appendStockMovementsBatch_(inputs);
    GUDANG_touchMutation_("simpanPecahVarianBatch");
    return { success: true, inserted: rows.length, remainingMode: "OMNI_ORDER_MINUS_STOCK_MOVEMENT" };
  } catch (e) {
    logError_("simpanPecahVarianBatch", e, { subKategori: subKategori, tglTarikan: tglTarikan, arrayInputVarian: arrayInputVarian, namaToko: namaToko });
    return { success: false, msg: e.message };
  } finally { lock.releaseLock(); }
}


function simpanMutasiManual(namaItem, jenisMutasi, qtyMutasi, keteranganMutasi, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var jenis = normalizeStockCode_(jenisMutasi || "");
    var ket = String(keteranganMutasi || "");
    var type = ket.indexOf("Pemakaian Internal") !== -1 ? "INTERNAL_USAGE" : "OPNAME";
    var uniqueRef = type + "|" + Utilities.getUuid().slice(0, 8).toUpperCase();
    var row = appendStockMovement_({
      Tanggal: new Date(),
      Source_Date: normalizeDateKeyForWarehouse_(new Date()),
      Item_Name: namaItem,
      Direction: jenis,
      Movement_Type: type,
      Qty: qtyMutasi,
      Source_Module: "WH",
      Source_ID: uniqueRef,
      Source_Line_ID: normalizeStockText_(namaItem),
      Ref_No: type,
      Notes: ket || type,
      Allow_Negative: type === "OPNAME",
      Created_By: __auth.email
    });
    GUDANG_touchMutation_("simpanMutasiManual");
    return { success: true, movement: row };
  } catch (e) {
    logError_("simpanMutasiManual", e, { namaItem: namaItem, jenisMutasi: jenisMutasi, qtyMutasi: qtyMutasi, keteranganMutasi: keteranganMutasi });
    return { success: false, msg: e.message };
  } finally { lock.releaseLock(); }
}

function simpanAuditFisikGudang(txKey, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  try {
    var row = {
      Audit_ID: uuid_("AUD"),
      Timestamp: nowText_(),
      Tx_Key: String(txKey || "").trim(),
      Movement_ID: String(txKey || "").trim(),
      Status: "LOCKED",
      Created_By: __auth.email,
      Notes: "Audit fisik dikunci dari UI Gudang"
    };
    if (!row.Tx_Key) throw new Error("Tx_Key kosong.");
    appendRowsByHeader_(getActiveGudang_(), SHEET_STOCK_AUDIT, STOCK_AUDIT_HEADERS, [row]);
    GUDANG_touchMutation_("simpanAuditFisikGudang");
    return { success: true };
  } catch (e) {
    logError_("simpanAuditFisikGudang", e, { txKey: txKey });
    return { success: false, msg: e.message };
  }
}

// Stock opname fisik: user isi stok fisik akhir, sistem hitung selisih otomatis.
// Jika ada selisih, sistem membuat movement OPNAME_ADJUSTMENT. Jika tidak ada selisih,
// tetap dibuat log Stock_Opname tanpa mengubah Stock_Movement.
function simpanStockOpnameFisik(namaItem, physicalQty, reason, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success: false, msg: "Server sibuk. Coba lagi." }; }
  try {
    var lookup = buildItemLookup_();
    var itemName = normalizeStockText_(namaItem || "");
    var item = lookup.byName[itemName] || lookup.byId[itemName];
    if (!item) throw new Error("Item tidak ditemukan di Master_Item: " + itemName);

    var fisik = toNumber_(physicalQty);
    if (fisik < 0) throw new Error("Stok fisik tidak boleh minus.");

    var sistem = getCurrentStockQtyForItem_(item.Item_ID);
    var diff = fisik - sistem;
    // hindari noise desimal kecil dari input formula/format lokal
    if (Math.abs(diff) < 0.000001) diff = 0;

    var opnameId = uuid_("OPN");
    var todayKey = normalizeDateKeyForWarehouse_(new Date()) || dateOnlyText_(new Date());
    var postedMovementId = "";
    var movement = null;
    var reasonText = normalizeStockText_(reason || "Stock opname fisik");

    if (diff !== 0) {
      var dir = diff > 0 ? "IN" : "OUT";
      var qtyAdj = Math.abs(diff);
      movement = appendStockMovement_({
        Tanggal: new Date(),
        Source_Date: todayKey,
        Item_ID: item.Item_ID,
        Item_Name: item.Item_Name,
        Direction: dir,
        Movement_Type: "OPNAME_ADJUSTMENT",
        Qty: qtyAdj,
        Unit_Cost: item.Default_Cost || 0,
        Source_Module: "WH",
        Source_ID: opnameId,
        Source_Line_ID: item.Item_ID,
        Ref_No: "OPNAME_ADJUSTMENT",
        Batch_ID: "OPNAME|" + todayKey,
        External_Ref: item.Item_Name,
        Notes: "Stock Opname Fisik | Sistem: " + sistem + " | Fisik: " + fisik + " | Selisih: " + diff + (reasonText ? " | " + reasonText : ""),
        Allow_Negative: true,
        Created_By: __auth.email
      });
      postedMovementId = movement.Movement_ID || "";
    }

    var opnameRow = {
      Opname_ID: opnameId,
      Opname_Date: todayKey,
      Item_ID: item.Item_ID,
      Item_Name: item.Item_Name,
      Warehouse_Code: "MAIN",
      System_Qty: sistem,
      Physical_Qty: fisik,
      Diff_Qty: diff,
      Reason: reasonText,
      Status: diff === 0 ? "POSTED_NO_DIFF" : "POSTED",
      Created_At: nowText_(),
      Created_By: __auth.email,
      Posted_Movement_ID: postedMovementId,
      Notes: diff === 0 ? "Stok fisik sama dengan sistem; tidak membuat movement." : "Membuat movement OPNAME_ADJUSTMENT."
    };
    appendRowsByHeader_(getActiveGudang_(), SHEET_STOCK_OPNAME, STOCK_OPNAME_HEADERS, [opnameRow]);
    GUDANG_touchMutation_("simpanStockOpnameFisik");
    return {
      success: true,
      opname: opnameRow,
      movement: movement,
      systemQty: sistem,
      physicalQty: fisik,
      diffQty: diff,
      msg: diff === 0 ? "Opname tersimpan. Tidak ada selisih stok." : "Opname tersimpan. Selisih " + diff + " sudah dibuat adjustment."
    };
  } catch (e) {
    logError_("simpanStockOpnameFisik", e, { namaItem: namaItem, physicalQty: physicalQty, reason: reason });
    return { success: false, msg: e.message };
  } finally { lock.releaseLock(); }
}

function receptorTutupBukuDariPortal(tglCutoffYYYYMMDD, emailOp, pasporOp) {
  var __auth = GUDANG_requirePassport_(emailOp, pasporOp);
  try {
    var dataLive = getInitDataGudang(emailOp, pasporOp);
    if (!dataLive.success) throw new Error(dataLive.msg || "Gagal baca data live.");
    var all = [].concat(dataLive.bahan || [], dataLive.jadi || []);
    var lookup = buildItemLookup_();
    var now = nowText_();
    var email = __auth.email;
    var cutoffDate = tglCutoffYYYYMMDD || dateOnlyText_(new Date());
    var costPeriod = normalizeCostPeriod_(normalizeDateKeyForWarehouse_(cutoffDate) || cutoffDate);
    var costData = readStockCostPeriod_();
    var rows = [];
    all.forEach(function(x) {
      var it = lookup.byName[x.nama];
      if (!it) return;
      var costRow = findStockCostRow_(costData, it, costPeriod);
      var status = costRow ? normalizeCostStatus_(costRow.Cost_Status, "PROVISIONAL") : "PROVISIONAL";
      var unitCost = costRow ? (status === "FINAL" && toNumber_(costRow.Unit_Cost_Final) > 0 ? toNumber_(costRow.Unit_Cost_Final) : toNumber_(costRow.Unit_Cost_Provisional || costRow.Unit_Cost_Final)) : (it.Default_Cost || 0);
      if (!unitCost) unitCost = it.Default_Cost || 0;
      rows.push({
        Cutoff_ID: uuid_("CUT"),
        Cutoff_Date: cutoffDate,
        Cost_Period: costPeriod,
        Item_ID: it.Item_ID,
        Item_Name: it.Item_Name,
        Warehouse_Code: "MAIN",
        Qty_Cutoff: x.stok,
        Unit_Cost: unitCost,
        Value_Cutoff: toNumber_(x.stok) * unitCost,
        Cost_Status: status,
        Cost_Source: costRow ? ((costRow.Source_Module || "STOCK_COST_PERIOD") + (costRow.Source_ID ? "|" + costRow.Source_ID : "")) : "MASTER_ITEM",
        Source: "PORTAL_TUTUP_BUKU",
        Created_At: now,
        Created_By: email,
        Notes: "Snapshot stok qty+nilai; tidak mengubah saldo. Koreksi fisik tetap lewat Stock Opname."
      });
    });
    appendRowsByHeader_(getActiveGudang_(), SHEET_STOCK_CUTOFF, STOCK_CUTOFF_HEADERS, rows);
    GUDANG_touchMutation_("receptorTutupBukuDariPortal");
    return { success: true, msg: "Snapshot Gudang berhasil disimpan pada " + (tglCutoffYYYYMMDD || dateOnlyText_(new Date())), count: rows.length };
  } catch (e) {
    logError_("receptorTutupBukuDariPortal", e, { tglCutoffYYYYMMDD: tglCutoffYYYYMMDD });
    return { success: false, msg: e.message };
  }
}



// ===== FLOW-STYLE SECURITY + NAV + HEARTBEAT SYNC v1.9 =====
// Seragam dengan Purchasing/Penjualan/Produksi: HMAC passport dari Portal, tanpa sheet Security_Passport.

var ERP_GLOBAL_CFG = {
  MASTER_SPREADSHEET_ID: GUDANG_CFG.MASTER_SPREADSHEET_ID,
  MODULE_CODE: GUDANG_CFG.MODULE_CODE,
  SESSION_TTL_MS: GUDANG_CFG.SESSION_TTL_MS,
  SHARED_SECRET: GUDANG_CFG.SHARED_SECRET,
  HEARTBEAT_CELL: GUDANG_CFG.HEARTBEAT_CELL,
  HEARTBEAT_UPDATED_CELL: GUDANG_CFG.HEARTBEAT_UPDATED_CELL,
  HEARTBEAT_NOTES_CELL: GUDANG_CFG.HEARTBEAT_NOTES_CELL,
  MASTER_USER_SHEET: GUDANG_CFG.MASTER_USER_SHEET,
  MASTER_MODULE_SHEET: GUDANG_CFG.MASTER_MODULE_SHEET,
  LOG_LOGIN_SHEET: GUDANG_CFG.LOG_LOGIN_SHEET,
  PORTAL_CODES: GUDANG_CFG.PORTAL_CODES,
  TZ: GUDANG_CFG.TZ || (Session.getScriptTimeZone() || 'Asia/Jakarta')
};

function GUDANG_requirePassport_(emailOp, pasporOp) {
  emailOp = ERP_normEmail_(emailOp || '');
  pasporOp = ERP_clean_(pasporOp || '');
  if (!emailOp || !pasporOp) throw new Error('Sesi Gudang tidak lengkap. Masuk ulang dari Portal.');
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth || !auth.allowed) throw new Error('Akses Gudang ditolak: ' + (auth && auth.reason ? auth.reason : 'UNKNOWN'));
  if (auth.email && emailOp && ERP_normEmail_(auth.email) !== emailOp) throw new Error('Passport tidak cocok dengan email aktif. Masuk ulang dari Portal.');
  return auth;
}

function GUDANG_touchMutation_(fnName) {
  try { ERP_mutation_(fnName || 'GUDANG_MUTATION'); } catch(e) {}
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

function TEST_erpGudangSecurityHeartbeat(email, paspor) {
  var auth = ERP_securityCheck_(email || ERP_userEmail_(), paspor || '', !!paspor);
  var hb = ERP_readGlobalHeartbeat_();
  return { success:true, moduleCode:ERP_GLOBAL_CFG.MODULE_CODE, auth:auth, heartbeat:hb, portalUrl:ERP_getPortalUrl_(), note:'v1.9 HMAC passport Flow Style + soft autorefresh heartbeat; tidak baca Security_Passport sheet.' };
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
  var can = isAdmin || ERP_userCanOpenModule_({ allowedModules:allowedModules, role:role, department:department }, ERP_GLOBAL_CFG.MODULE_CODE, 'Gudang Warehouse', GUDANG_CFG.MODULE_ALIASES || []);
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
function ERP_logLogin_(email,action,pid,status,notes){try{var ss=ERP_master_();var sh=ss.getSheetByName(ERP_GLOBAL_CFG.LOG_LOGIN_SHEET)||ss.insertSheet(ERP_GLOBAL_CFG.LOG_LOGIN_SHEET);var h=['Timestamp','Email','Display_Name','Action','Passport_ID','Status','User_Agent','Notes'];if(sh.getLastRow()===0)sh.getRange(1,1,1,h.length).setValues([h]);sh.appendRow([new Date(),email,'',action,pid,status,'',notes||'']);}catch(e){}}
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

function getModulLinks(emailOp, pasporOp) {
  var email = emailOp || '';
  var paspor = pasporOp || '';
  if (arguments.length === 1) {
    paspor = emailOp || '';
    email = '';
  }
  var auth = ERP_securityCheck_(email, paspor, true);
  if (!auth.allowed) return [];
  var links = ERP_readModuleLinksRaw_();
  var out = [];
  for (var i = 0; i < links.length; i++) {
    var m = links[i];
    var code = ERP_key_(m.code);
    if (!m.url || !ERP_isActive_(m.status)) continue;
    if (code === ERP_GLOBAL_CFG.MODULE_CODE || code === 'GUDANG' || code === 'WAREHOUSE') continue;
    if (!(auth.isAdmin || ERP_userCanOpenModule_(auth, m.code, m.name))) continue;
    out.push({ code: m.code, nama: m.name, name: m.name, url: ERP_appendPassportToUrl_(m.url, auth, paspor || auth.passport || auth.passportId || '') });
  }
  return out;
}