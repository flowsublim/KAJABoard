
// =================================================================================
// ERP CV KIRAL - MODUL PRODUKSI
// Legacy UI + New DB Adapter v0.9.8 Stock Cost ID Format Fix
// =================================================================================

var MASTER_SPREADSHEET_ID = "1bbtCMQfK5p_2c5GzIkTIrcIPcPsm3Wjh_R8PfAagu6I";

var PROD_CFG = {
  VERSION: "PROD_v0.9.8_STOCK_COST_ID_FORMAT_FIX",
  MODULE_CODE: "PROD",
  SESSION_TTL_MS: 6 * 60 * 60 * 1000,
  SHARED_SECRET: "CV_KIRAL_FLOW_SUBLIM_STYLE_FIXED_SECRET_2026_KIRAL",
  MASTER_USER_SHEET: "Master_User",
  MASTER_MODULE_SHEET: "Master_Module",
  HEARTBEAT_CELL: "J1",
  HEARTBEAT_UPDATED_CELL: "J2",
  HEARTBEAT_NOTES_CELL: "J3",
  PORTAL_CODES: ["PORTAL", "PRTL", "HOME", "BERANDA"],
  TZ: "Asia/Jakarta",
  MODULE_ALIASES: ["PROD", "PRODUKSI", "PRODUCTION", "MODUL PRODUKSI"],
  PURCH_MODULE_ALIASES: ["PURCH", "PUR", "PRC", "PURCHASING", "PEMBELIAN", "PURCHASE", "MODUL PURCHASING", "MODUL PEMBELIAN", "MODUL PURCHASE", "PURCHASING / PEMBELIAN"],
  GUDANG_MODULE_ALIASES: ["WH", "GUDANG", "WAREHOUSE", "MODUL GUDANG"],
  PROD_SPREADSHEET_ID_OVERRIDE: "",
  GUDANG_SPREADSHEET_ID_OVERRIDE: "",
  WAREHOUSE_CODE: "MAIN"
};

// Alias kompatibilitas agar helper Flow-style hanya memakai satu sumber konfigurasi.
// Hotfix ini memperbaiki ReferenceError: PROD_FLOW_CFG is not defined tanpa menyentuh logic produksi.
var PROD_FLOW_CFG = PROD_CFG;

var PROD_LOCAL_SHEETS = {
  Data_Produksi: ["Tanggal","SPK","Proses","PIC","Bahan","Qty Bahan","Produk","Qty","Sistem Upah","Nilai Bahan","Upah Borongan","Biaya Ekstra","Catatan","HPP","Trx_ID","Created_At","Created_By","Updated_At","Updated_By","Is_Deleted"],
  Master_PIC: ["Nama PIC","Status"],
  Master_Tarif: ["Proses","Produk","Tarif"],
  Data_SPK: ["Tanggal","SPK","Status","Bahan","Jalur","Item","Reserved","Deadline","Vendor","Qty","ARSIP SPK SELESAI"],
  Data_Pengeluaran: ["Tanggal","Kategori","Keterangan","Nominal","Created_At","Created_By","Is_Deleted"]
};

var PROD_STOCK_MOVEMENT_HEADERS = [
  "Movement_ID", "Tx_Key", "Tanggal", "Source_Date", "Item_ID", "Item_Name", "Item_Category", "Item_Type", "Unit", "Warehouse_Code", "Direction",
  "Movement_Type", "Qty", "Unit_Cost", "Total_Cost", "SPK_ID", "Cost_Period", "Cost_Status", "Cost_Source",
  "Unit_Cost_Provisional", "Value_Provisional", "Unit_Cost_Final", "Value_Final", "Cost_Synced_At", "Cost_Locked_At", "Closed_At", "Closed_By",
  "Source_Module", "Source_ID", "Source_Line_ID", "Ref_No", "Batch_ID", "External_Ref", "Status", "Notes", "Created_At", "Created_By", "Is_Deleted"
];

var PROD_STOCK_COST_PERIOD_HEADERS = [
  "Period", "Item_ID", "Item_Name", "Unit_Cost_Provisional", "Unit_Cost_Final", "Cost_Status",
  "Source_Module", "Source_ID", "Synced_At", "Synced_By", "Notes", "Is_Deleted"
];

var PROD_CONTEXT_USER_EMAIL = "";
function PROD_setContextUser_(email) { PROD_CONTEXT_USER_EMAIL = PROD_normEmail_(email); return PROD_CONTEXT_USER_EMAIL; }
function PROD_userEmail_() { return PROD_CONTEXT_USER_EMAIL || ""; }
function PROD_now_() { return new Date(); }
function PROD_uid_(prefix) { return (prefix || "ID") + "-" + Utilities.formatDate(new Date(), Session.getScriptTimeZone() || "Asia/Jakarta", "yyMMddHHmmss") + "-" + Math.floor(Math.random()*100000); }
function PROD_norm_(v) { return String(v == null ? "" : v).trim(); }
function PROD_key_(v) { return PROD_norm_(v).toUpperCase().replace(/[^A-Z0-9]/g, ""); }
function PROD_isActiveStatus_(status) {
  var s = PROD_key_(status);
  if (!s) return true;
  return ["INACTIVE","NONAKTIF","DISABLED","OFF","FALSE","STOP","STOPPED","ARCHIVE","ARSIP"].indexOf(s) === -1;
}
function PROD_toNumber_(v) {
  if (v === null || v === undefined || v === "") return 0;
  if (typeof v === "number") return isNaN(v) ? 0 : v;
  var s = String(v).trim();
  if (!s) return 0;
  var neg = /^\s*-/.test(s) || /\(.*\)/.test(s);
  s = s.replace(/Rp/gi, "").replace(/\s/g, "").replace(/[^0-9,.\-]/g, "").replace(/-/g, "");
  if (!s) return 0;
  var hasComma = s.indexOf(",") !== -1;
  var hasDot = s.indexOf(".") !== -1;
  if (hasComma && hasDot) {
    // Format Indonesia: 1.234,56. Format US legacy: 1,234.56.
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) s = s.replace(/\./g, "").replace(/,/g, ".");
    else s = s.replace(/,/g, "");
  } else if (hasComma) {
    var partsC = s.split(",");
    var lastC = partsC[partsC.length - 1] || "";
    if (partsC.length === 2 && lastC.length > 0 && lastC.length <= 2) s = partsC[0].replace(/\./g, "") + "." + lastC;
    else s = s.replace(/,/g, "");
  } else if (hasDot) {
    var partsD = s.split(".");
    var lastD = partsD[partsD.length - 1] || "";
    // Standar Indonesia: titik = pemisah ribuan. Jadi 28.500 harus menjadi 28500, bukan 28.5.
    if (partsD.length > 2 || lastD.length === 3) s = s.replace(/\./g, "");
    // Kompatibilitas angka legacy decimal-dot: 12.5 / 12.50 tetap dibaca sebagai desimal.
  }
  var n = parseFloat(s);
  if (isNaN(n)) return 0;
  return neg ? -Math.abs(n) : n;
}
// Alias kompatibilitas untuk kode legacy yang sempat memanggil PROD_toNumber tanpa underscore.
function PROD_toNumber(v) { return PROD_toNumber_(v); }
function PROD_extractSpreadsheetId_(value) {
  var s = PROD_norm_(value);
  if (!s) return "";
  if (/^[a-zA-Z0-9-_]{25,}$/.test(s) && s.indexOf("/") === -1) return s;
  var m = s.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return m ? m[1] : "";
}
function PROD_headerMap_(headers) {
  var map = {};
  for (var i=0; i<headers.length; i++) {
    var k = PROD_key_(headers[i]);
    if (k) map[k] = i;
  }
  return map;
}
function PROD_col_(map, names, fallbackIndex) {
  names = Array.isArray(names) ? names : [names];
  for (var i=0; i<names.length; i++) {
    var k = PROD_key_(names[i]);
    if (map[k] !== undefined) return map[k];
  }
  return fallbackIndex === undefined ? -1 : fallbackIndex;
}
function PROD_openMasterSs_() { return SpreadsheetApp.openById(MASTER_SPREADSHEET_ID); }
function PROD_openModuleSpreadsheet_(aliases) {
  aliases = aliases || [];
  var aliasClean = aliases.map(PROD_key_);
  var masterSs = PROD_openMasterSs_();
  var sh = masterSs.getSheetByName("Master_Module");
  if (!sh) throw new Error("Sheet Master_Module tidak ditemukan di Master Database.");
  var values = sh.getDataRange().getValues();
  if (values.length < 2) throw new Error("Master_Module masih kosong.");
  var map = PROD_headerMap_(values[0]);
  var cCode = PROD_col_(map, ["Module_Code", "Module Code", "Kode Modul", "Code"], -1);
  var cName = PROD_col_(map, ["Module_Name", "Module Name", "Nama Modul", "Name"], -1);
  var cId = PROD_col_(map, ["Spreadsheet_ID", "Spreadsheet ID", "ID Spreadsheet", "Sheet ID", "ID"], -1);
  var cSheetUrl = PROD_col_(map, ["Spreadsheet_URL", "Spreadsheet URL", "URL Spreadsheet", "GSheet URL"], -1);
  var cStatus = PROD_col_(map, ["Status"], -1);
  if (cCode === -1 && cName === -1) throw new Error("Header Module_Code / Module_Name tidak ditemukan di Master_Module.");
  if (cId === -1 && cSheetUrl === -1) throw new Error("Header Spreadsheet_ID / Spreadsheet_URL tidak ditemukan di Master_Module.");
  var candidates = [];
  for (var r=1; r<values.length; r++) {
    var row = values[r];
    var codeRaw = cCode !== -1 ? row[cCode] : "";
    var nameRaw = cName !== -1 ? row[cName] : "";
    var code = PROD_key_(codeRaw), name = PROD_key_(nameRaw);
    var active = PROD_isActiveStatus_(cStatus === -1 ? "" : row[cStatus]);
    candidates.push("row " + (r+1) + " code=" + codeRaw + " name=" + nameRaw + " active=" + active);
    if (!active) continue;
    var matched = aliasClean.some(function(a) { return code === a || name === a || code.indexOf(a) !== -1 || name.indexOf(a) !== -1 || (code && a.indexOf(code) !== -1); });
    if (!matched) continue;
    var id = "";
    if (cId !== -1) id = PROD_extractSpreadsheetId_(row[cId]);
    if (!id && cSheetUrl !== -1) id = PROD_extractSpreadsheetId_(row[cSheetUrl]);
    if (!id) throw new Error("Spreadsheet_ID kosong untuk modul: " + codeRaw + " / " + nameRaw);
    return SpreadsheetApp.openById(id);
  }
  throw new Error("Modul tidak ditemukan di Master_Module. Dicari: " + aliases.join(", ") + "\n" + candidates.join("\n"));
}
function PROD_selfSs_() {
  if (PROD_CFG.PROD_SPREADSHEET_ID_OVERRIDE) return SpreadsheetApp.openById(PROD_CFG.PROD_SPREADSHEET_ID_OVERRIDE);
  try { return PROD_openModuleSpreadsheet_(PROD_CFG.MODULE_ALIASES); } catch(e) {
    var active = SpreadsheetApp.getActiveSpreadsheet();
    if (active) return active;
    throw e;
  }
}
function PROD_gudangSs_() {
  if (PROD_CFG.GUDANG_SPREADSHEET_ID_OVERRIDE) return SpreadsheetApp.openById(PROD_CFG.GUDANG_SPREADSHEET_ID_OVERRIDE);
  return PROD_openModuleSpreadsheet_(PROD_CFG.GUDANG_MODULE_ALIASES);
}
function PROD_purchSs_() { return PROD_openModuleSpreadsheet_(PROD_CFG.PURCH_MODULE_ALIASES); }

function PROD_ensureSheetHeaders_(ss, sheetName, headers) {
  var sh = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    sh.setFrozenRows(1);
    return sh;
  }
  var existing = sh.getRange(1,1,1,Math.max(sh.getLastColumn(),1)).getValues()[0];
  var existingKeys = existing.map(PROD_key_);
  var toAppend = [];
  headers.forEach(function(h) { if (existingKeys.indexOf(PROD_key_(h)) === -1) toAppend.push(h); });
  if (toAppend.length) sh.getRange(1, existing.length + 1, 1, toAppend.length).setValues([toAppend]);
  sh.setFrozenRows(1);
  return sh;
}
// getSheetWithMap legacy duplicate dihapus; definisi aktif ada di bagian UTILITY FUNGSI.

function PROD_rowObject_(headers, row) {
  var obj = {};
  for (var i=0; i<headers.length; i++) obj[String(headers[i] || "").trim()] = row[i];
  return obj;
}
function PROD_makeRow_(headers, obj) {
  var map = PROD_headerMap_(headers);
  var row = new Array(headers.length).fill("");
  Object.keys(obj).forEach(function(k) {
    var idx = PROD_col_(map, [k], -1);
    if (idx !== -1) row[idx] = obj[k];
  });
  return row;
}

function PROD_formatPeriod_(dateValue) {
  var d = PROD_parseDate_(dateValue) || new Date();
  return Utilities.formatDate(d, PROD_CFG.TZ || "Asia/Jakarta", "yyyy-MM");
}
function PROD_parseDate_(v) {
  if (v instanceof Date && !isNaN(v.getTime())) return v;
  if (typeof v === "number" && isFinite(v)) return new Date(Math.round((v - 25569) * 86400 * 1000));
  var s = PROD_norm_(v);
  if (!s) return null;
  var m = s.match(/^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})/);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  var d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}
function PROD_toSheetNumber_(v) {
  var n = PROD_toNumber_(v);
  return isNaN(n) ? 0 : n;
}
function PROD_stockTxKey_(m) {
  var source = PROD_norm_(m.Source_ID || "");
  var line = PROD_norm_(m.Source_Line_ID || "");
  var type = PROD_norm_(m.Movement_Type || "PRODUCTION");
  var item = PROD_norm_(m.Item_Name || m.itemName || "");
  return PROD_norm_(m.Tx_Key || ["PROD", source, line, type, item].join("|"));
}
function PROD_formatCostColumns_(sh) {
  try {
    if (!sh || sh.getLastRow() < 2) return;
    var headers = sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0];
    var map = PROD_headerMap_(headers);
    ["Qty", "Unit_Cost", "Total_Cost", "Unit_Cost_Provisional", "Value_Provisional", "Unit_Cost_Final", "Value_Final"].forEach(function(h) {
      var c = PROD_col_(map, [h], -1);
      if (c !== -1) sh.getRange(2, c + 1, Math.max(sh.getLastRow() - 1, 1), 1).setNumberFormat("#,##0.00");
    });
  } catch(e) {}
}
function PROD_trySetIndonesianLocale_(ss) {
  try {
    if (ss && ss.setSpreadsheetLocale) ss.setSpreadsheetLocale("id_ID");
  } catch(e) {}
}

function PROD_readMasterItems_() {
  var ss = PROD_openMasterSs_();
  var sh = ss.getSheetByName("Master_Item");
  if (!sh) return [];
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return [];
  var headers = values[0];
  var map = PROD_headerMap_(headers);
  var cId = PROD_col_(map, ["Item_ID", "Item ID", "ID"], -1);
  var cName = PROD_col_(map, ["Item_Name", "Nama_Item", "Nama Item", "Nama_Barang", "Nama Barang", "Nama_Produk", "Nama Produk", "Internal_Item_Name", "Item", "Produk"], -1);
  var cType = PROD_col_(map, ["Item_Type", "Item Type", "Tipe Item", "Jenis Item"], -1);
  var cCat = PROD_col_(map, ["Category", "Kategori", "Item_Category", "Item Category"], -1);
  var cSub = PROD_col_(map, ["Subcategory", "Sub_Category", "Sub Category", "Sub-Kategori", "Sub Kategori"], -1);
  var cUnit = PROD_col_(map, ["Unit", "Satuan", "UOM"], -1);
  var cStatus = PROD_col_(map, ["Status"], -1);
  var res = [];
  if (cName === -1) return res;
  for (var r=1; r<values.length; r++) {
    var row = values[r];
    if (!PROD_isActiveStatus_(cStatus === -1 ? "" : row[cStatus])) continue;
    var name = PROD_norm_(row[cName]);
    if (!name) continue;
    res.push({ id: cId === -1 ? "" : PROD_norm_(row[cId]), name: name, type: PROD_norm_(cType === -1 ? "" : row[cType]), category: PROD_norm_(cCat === -1 ? "" : row[cCat]), subcategory: PROD_norm_(cSub === -1 ? "" : row[cSub]), unit: cUnit === -1 ? "" : PROD_norm_(row[cUnit]) });
  }
  return res;
}
function PROD_findItem_(name) {
  var key = PROD_key_(name);
  var items = PROD_readMasterItems_();
  for (var i=0; i<items.length; i++) if (PROD_key_(items[i].name) === key) return items[i];
  return null;
}
function PROD_stockMovementSheet_() {
  var gudang = PROD_gudangSs_();
  PROD_trySetIndonesianLocale_(gudang);
  var sh = PROD_ensureSheetHeaders_(gudang, "Stock_Movement", PROD_STOCK_MOVEMENT_HEADERS);
  PROD_formatCostColumns_(sh);
  return sh;
}
function PROD_stockCostPeriodSheet_() {
  var gudang = PROD_gudangSs_();
  PROD_trySetIndonesianLocale_(gudang);
  var sh = PROD_ensureSheetHeaders_(gudang, "Stock_Cost_Period", PROD_STOCK_COST_PERIOD_HEADERS);
  PROD_formatCostColumns_(sh);
  return sh;
}
function PROD_appendMovement_(m) {
  var sh = PROD_stockMovementSheet_();
  var headers = sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0];
  var map = PROD_headerMap_(headers);
  var item = PROD_findItem_(m.Item_Name || m.itemName || "") || {};
  var qty = PROD_toSheetNumber_(m.Qty);
  var unitCost = PROD_toSheetNumber_(m.Unit_Cost);
  var totalCost = PROD_toSheetNumber_(m.Total_Cost);
  if (!totalCost && qty && unitCost) totalCost = qty * unitCost;
  var status = PROD_norm_(m.Cost_Status || "PROVISIONAL").toUpperCase();
  var isFinal = status === "FINAL" || status === "CLOSED" || status === "LOCKED";
  if (status === "ESTIMATED") status = "PROVISIONAL";
  var txKey = PROD_stockTxKey_(m);

  // Idempotency ringan: request dobel dengan Tx_Key sama tidak menulis ulang jika baris lama belum dihapus.
  var cTx = PROD_col_(map, ["Tx_Key"], -1), cDel = PROD_col_(map, ["Is_Deleted"], -1);
  if (cTx !== -1 && txKey && sh.getLastRow() > 1) {
    var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    for (var r=0; r<vals.length; r++) {
      if (PROD_norm_(vals[r][cTx]) === txKey && (cDel === -1 || PROD_key_(vals[r][cDel]) !== "TRUE")) return;
    }
  }

  var obj = {
    Movement_ID: m.Movement_ID || PROD_uid_("MOV"),
    Tx_Key: txKey,
    Tanggal: m.Tanggal || new Date(),
    Source_Date: m.Source_Date || m.Tanggal || new Date(),
    Item_ID: m.Item_ID || item.id || "",
    Item_Name: m.Item_Name || item.name || m.itemName || "",
    Item_Category: m.Item_Category || item.category || item.subcategory || "",
    Item_Type: m.Item_Type || item.type || "",
    Unit: m.Unit || item.unit || "",
    Warehouse_Code: m.Warehouse_Code || PROD_CFG.WAREHOUSE_CODE,
    Direction: m.Direction || "OUT",
    Movement_Type: m.Movement_Type || "PRODUCTION",
    Qty: qty,
    Unit_Cost: unitCost,
    Total_Cost: totalCost,
    SPK_ID: m.SPK_ID || m.Ref_No || "",
    Cost_Period: m.Cost_Period || PROD_formatPeriod_(m.Tanggal || new Date()),
    Cost_Status: status,
    Cost_Source: m.Cost_Source || "PROD_COST_SNAPSHOT",
    Unit_Cost_Provisional: m.Unit_Cost_Provisional !== undefined ? PROD_toSheetNumber_(m.Unit_Cost_Provisional) : unitCost,
    Value_Provisional: m.Value_Provisional !== undefined ? PROD_toSheetNumber_(m.Value_Provisional) : totalCost,
    Unit_Cost_Final: m.Unit_Cost_Final !== undefined ? PROD_toSheetNumber_(m.Unit_Cost_Final) : (isFinal ? unitCost : ""),
    Value_Final: m.Value_Final !== undefined ? PROD_toSheetNumber_(m.Value_Final) : (isFinal ? totalCost : ""),
    Cost_Synced_At: m.Cost_Synced_At || (isFinal ? new Date() : ""),
    Cost_Locked_At: m.Cost_Locked_At || "",
    Closed_At: m.Closed_At || "",
    Closed_By: m.Closed_By || "",
    Source_Module: m.Source_Module || "PROD",
    Source_ID: m.Source_ID || "",
    Source_Line_ID: m.Source_Line_ID || "",
    Ref_No: m.Ref_No || "",
    Batch_ID: m.Batch_ID || m.SPK_ID || m.Ref_No || "",
    External_Ref: m.External_Ref || "",
    Status: m.Status || "POSTED",
    Notes: m.Notes || "",
    Created_At: m.Created_At || new Date(),
    Created_By: m.Created_By || PROD_userEmail_(),
    Is_Deleted: m.Is_Deleted || false
  };
  sh.appendRow(PROD_makeRow_(headers, obj));
  PROD_formatCostColumns_(sh);
}
function PROD_voidMovementsBySource_(sourceId, note) {
  if (!sourceId) return 0;
  var sh = PROD_stockMovementSheet_();
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return 0;
  var map = PROD_headerMap_(values[0]);
  var cSource = PROD_col_(map, ["Source_ID"], -1), cMod = PROD_col_(map, ["Source_Module"], -1), cDel = PROD_col_(map, ["Is_Deleted"], -1), cNotes = PROD_col_(map, ["Notes"], -1);
  if (cSource === -1 || cDel === -1) return 0;
  var count = 0;
  for (var r=1; r<values.length; r++) {
    if (PROD_norm_(values[r][cSource]) === PROD_norm_(sourceId) && (cMod === -1 || PROD_key_(values[r][cMod]) === "PROD")) {
      sh.getRange(r+1, cDel+1).setValue(true);
      if (cNotes !== -1) sh.getRange(r+1, cNotes+1).setValue((values[r][cNotes] || "") + " | VOID: " + (note || "update/delete produksi"));
      count++;
    }
  }
  return count;
}
function PROD_stockBalance_(itemName, excludeSourceId) {
  var sh;
  try { sh = PROD_stockMovementSheet_(); } catch(e) { return 0; }
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return 0;
  var map = PROD_headerMap_(values[0]);
  var cItem = PROD_col_(map, ["Item_Name", "Item Name"], -1), cDir = PROD_col_(map, ["Direction"], -1), cQty = PROD_col_(map, ["Qty"], -1), cDel = PROD_col_(map, ["Is_Deleted"], -1), cSource = PROD_col_(map, ["Source_ID"], -1);
  if (cItem === -1 || cDir === -1 || cQty === -1) return 0;
  var key = PROD_key_(itemName), bal = 0;
  for (var r=1; r<values.length; r++) {
    if (cDel !== -1 && PROD_key_(values[r][cDel]) === "TRUE") continue;
    if (excludeSourceId && cSource !== -1 && PROD_norm_(values[r][cSource]) === PROD_norm_(excludeSourceId)) continue;
    if (PROD_key_(values[r][cItem]) !== key) continue;
    var q = PROD_toNumber_(values[r][cQty]);
    var dir = PROD_key_(values[r][cDir]);
    if (dir === "IN") bal += q;
    else if (dir === "OUT") bal -= q;
  }
  return bal;
}
function PROD_avgCost_(itemName) {
  var sh;
  try { sh = PROD_stockMovementSheet_(); } catch(e) { return 0; }
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return 0;
  var map = PROD_headerMap_(values[0]);
  var cItem = PROD_col_(map, ["Item_Name"], -1), cDir = PROD_col_(map, ["Direction"], -1), cQty = PROD_col_(map, ["Qty"], -1), cCost = PROD_col_(map, ["Unit_Cost"], -1), cDel = PROD_col_(map, ["Is_Deleted"], -1);
  if (cItem === -1 || cDir === -1 || cQty === -1 || cCost === -1) return 0;
  var key = PROD_key_(itemName), qty = 0, val = 0;
  for (var r=1; r<values.length; r++) {
    if (cDel !== -1 && PROD_key_(values[r][cDel]) === "TRUE") continue;
    if (PROD_key_(values[r][cItem]) !== key) continue;
    if (PROD_key_(values[r][cDir]) !== "IN") continue;
    var q = PROD_toNumber_(values[r][cQty]);
    var cost = PROD_toNumber_(values[r][cCost]);
    if (q > 0 && cost > 0) { qty += q; val += q * cost; }
  }
  return qty > 0 ? val / qty : 0;
}

function doGet(e) {
  var params = (e && e.parameter) || {};
  var auth = PROD_doGetAccess_(params);
  if (!auth.allowed) return PROD_forbiddenOutput_(auth);

  var tpl = HtmlService.createTemplateFromFile('Index');
  tpl.ERP_PASSPORT = auth.passport || params.paspor || params.passport || '';
  tpl.ERP_USER_EMAIL = auth.email || params.vouch || '';
  tpl.ERP_PORTAL_URL = PROD_getPortalUrl_();
  tpl.ERP_DISPLAY_NAME = auth.displayName || auth.email || '';
  return tpl.evaluate()
    .setTitle('ERP - Modul Produksi')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}


function include(filename) { return HtmlService.createHtmlOutputFromFile(filename).getContent(); }

// ================= UTILITY FUNGSI =================
function sanitizeStr(str) { 
  if (str == null) return "";
  return str.toString().replace(/</g, "&lt;").replace(/>/g, "&gt;").trim(); 
}
function formatTgl(dStr) { 
  if(!dStr) return "-"; var d = new Date(dStr);
  return ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth()+1)).slice(-2) + "/" + d.getFullYear();
}
function formatInputTgl(dStr) { 
  if(!dStr) return ""; var d = new Date(dStr); if(isNaN(d.getTime())) return "";
  return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
}
function formatRupiah(angka) { return "Rp " + Math.round(angka).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); }

function getSheetWithMap(sheetName, ssOpt) {
  var ss = ssOpt || PROD_selfSs_();
  var s = ss.getSheetByName(sheetName);
  if(!s) throw new Error("Sheet '" + sheetName + "' belum dibuat di " + ss.getName() + "!");
  var data = s.getDataRange().getValues();
  var headers = data.length > 0 ? data[0] : [];
  var map = PROD_headerMap_(headers);
  var c = function(headerNames, fallbackIndex) { return PROD_col_(map, headerNames, fallbackIndex); };
  return { rows: data.length > 1 ? data.slice(1) : [], c: c, sheet: s, headers: headers, map: map, ss: ss };
}


function getArsipSelesai() {
  try {
    var ss = PROD_selfSs_();
    var s = ss.getSheetByName("Data_SPK");
    if(!s) return [];
    var data = s.getRange("J:K").getValues(), res = [];
    for(var i=1; i<data.length; i++) {
      if(data[i][0]) res.push(data[i][0].toString().trim());
      if(data[i][1]) res.push(data[i][1].toString().trim());
    }
    return res.filter(function(v, idx, arr){ return v && arr.indexOf(v) === idx; });
  } catch(e) { return []; }
}


// ================= MASTER DATA UTAMA =================
function getModulLinks(emailOp, pasporOp) {
  try {
    var auth = PROD_requirePassport_(emailOp, pasporOp);
    var master = PROD_openMasterSs_();
    var sh = master.getSheetByName("Master_Module");
    if(!sh) return [];
    var values = sh.getDataRange().getValues();
    if(values.length < 2) return [];
    var map = PROD_headerMap_(values[0]);
    var cCode = PROD_col_(map, ["Module_Code", "Module Code", "Kode Modul", "Code"], -1);
    var cNama = PROD_col_(map, ["Module_Name", "Module Name", "Nama Modul", "Name"], -1);
    var cUrl = PROD_col_(map, ["Web_App_URL", "WebApp_URL", "URL_Web_Aktif", "URL", "Link"], -1);
    var cStatus = PROD_col_(map, ["Status"], -1);
    var list = [];
    for(var i=1; i<values.length; i++) {
      var row = values[i];
      if(!PROD_isActiveStatus_(cStatus === -1 ? "" : row[cStatus])) continue;
      var code = cCode === -1 ? '' : String(row[cCode] || '').trim();
      var nama = cNama === -1 ? code : String(row[cNama] || code).trim();
      var url = cUrl === -1 ? "" : String(row[cUrl] || '').trim();
      if(!nama || !url) continue;
      var moduleKey = PROD_key_(code || nama);
      var nameKey = PROD_key_(nama);
      if(moduleKey === PROD_key_(PROD_FLOW_CFG.MODULE_CODE) || nameKey.indexOf('PRODUKSI') !== -1) continue;
      var isPortal = PROD_FLOW_CFG.PORTAL_CODES.indexOf(moduleKey) !== -1 || nameKey.indexOf('PORTAL') !== -1 || nameKey.indexOf('BERANDA') !== -1;
      if (!isPortal && !auth.isAdmin && !PROD_userCanOpenModule_(auth, code, nama)) continue;
      var finalUrl = url;
      if (pasporOp) {
        var sep = finalUrl.indexOf('?') === -1 ? '?' : '&';
        finalUrl += sep + 'vouch=' + encodeURIComponent(auth.email || '') + '&paspor=' + encodeURIComponent(pasporOp || '') + '&passport=' + encodeURIComponent(pasporOp || '') + '&from=' + encodeURIComponent(PROD_FLOW_CFG.MODULE_CODE);
      }
      list.push({ kode: code, code: code, nama: nama, name: nama, url: finalUrl, isPortal: isPortal });
    }
    list.sort(function(a,b){
      if (a.isPortal && !b.isPortal) return 1;
      if (!a.isPortal && b.isPortal) return -1;
      return String(a.nama).localeCompare(String(b.nama));
    });
    return list;
  } catch(e) { return []; }
}


function getDaftarPIC() {
  try {
    var pPic = getSheetWithMap("Master_PIC");
    var cNama = pPic.c(["nama pic", "nama", "karyawan"], 0);
    var res = [];
    for(var i=0; i<pPic.rows.length; i++) { 
       var stat = pPic.rows[i][1] ? pPic.rows[i][1].toString().trim() : "Aktif";
       if(pPic.rows[i][cNama] && stat === "Aktif") res.push(pPic.rows[i][cNama].toString().trim());
    }
    return res;
  } catch(e) { return []; }
}

function PROD_readActiveSpkRows_() {
  var rowsOut = [];
  var errors = [];
  var arsipSelesai = getArsipSelesai();

  function consume_(pSPK, sourceName) {
    var cSpk = pSPK.c(["SPK", "No SPK", "No_SPK"], 1);
    var cStat = pSPK.c(["Status"], 2);
    var cBahan = pSPK.c(["Bahan", "Item Bahan", "Material"], 3);
    var cTipe = pSPK.c(["Jalur", "Tipe Produksi", "Kategori", "Jalur Produksi", "Rute"], 4);
    var cItem = pSPK.c(["Item", "Produk", "Barang Jadi", "Output"], 5);
    var cQty = pSPK.c(["Qty", "QTY", "Jumlah", "Qty Produksi", "Qty_Output", "Qty Output"], 9);
    var cDeleted = pSPK.c(["Is_Deleted", "Is Deleted", "Deleted"], -1);

    for (var i=0; i<pSPK.rows.length; i++) {
      var row = pSPK.rows[i];
      if (cDeleted !== -1 && PROD_key_(row[cDeleted]) === "TRUE") continue;

      var spkStr = row[cSpk] ? row[cSpk].toString().trim() : "";
      if (!spkStr || arsipSelesai.indexOf(spkStr) !== -1) continue;

      var statKey = PROD_key_(row[cStat] || "Aktif");
      if (["SELESAI","CLOSED","CLOSE","BATAL","CANCEL","VOID","ARSIP"].indexOf(statKey) !== -1) continue;

      var jalurKey = PROD_key_(row[cTipe] || "");
      // SPK dari Purchasing yang jalurnya kosong/Produksi/Internal tetap masuk Produksi.
      // SPK Maklun eksternal disisihkan supaya tidak tercampur WIP internal.
      var isMaklunOnly = jalurKey.indexOf("MAKLUN") !== -1 && jalurKey.indexOf("INTERNAL") === -1 && jalurKey.indexOf("PRODUKSI") === -1;
      if (isMaklunOnly) continue;

      var bahan = row[cBahan] ? row[cBahan].toString().trim() : "";
      var item = row[cItem] ? row[cItem].toString().trim() : "";
      if (!bahan || !item) continue;

      rowsOut.push({
        spk: spkStr,
        bahan: bahan,
        item: item,
        qty: cQty === -1 ? 0 : PROD_toNumber_(row[cQty]),
        source: sourceName || ""
      });
    }
  }

  try { consume_(getSheetWithMap("Data_SPK", PROD_purchSs_()), "Purchasing"); } catch(e) { errors.push("Purchasing: " + (e && e.message || e)); }
  if (rowsOut.length === 0) {
    try { consume_(getSheetWithMap("Data_SPK", PROD_selfSs_()), "Produksi Lokal"); } catch(e2) { errors.push("Produksi lokal: " + (e2 && e2.message || e2)); }
  }
  try { CacheService.getScriptCache().put('PROD_LAST_SPK_LOAD_DEBUG', JSON.stringify({ at: new Date().toISOString(), count: rowsOut.length, spkCount: rowsOut.reduce(function(m,r){m[r.spk]=1; return m;},{}), errors: errors }), 21600); } catch(e3) {}
  return rowsOut;
}

function getDataSPK() {
  var spkMap = {};
  var rows = PROD_readActiveSpkRows_();
  rows.forEach(function(r) {
    if (!spkMap[r.spk]) spkMap[r.spk] = {};
    if (!spkMap[r.spk][r.bahan]) spkMap[r.spk][r.bahan] = [];
    if (spkMap[r.spk][r.bahan].indexOf(r.item) === -1) spkMap[r.spk][r.bahan].push(r.item);
  });
  return spkMap;
}

function TEST_productionSpkSourceDebug(emailOp, pasporOp) {
  try { if (emailOp || pasporOp) PROD_requirePassport_(emailOp, pasporOp); } catch(e) {}
  var dbg = {};
  try { dbg.cache = JSON.parse(CacheService.getScriptCache().get('PROD_LAST_SPK_LOAD_DEBUG') || '{}'); } catch(e) { dbg.cache = {}; }
  var purchInfo = {};
  try {
    var ss = PROD_purchSs_();
    purchInfo.name = ss.getName();
    purchInfo.id = ss.getId();
    var sh = ss.getSheetByName('Data_SPK');
    purchInfo.dataSpkFound = !!sh;
    purchInfo.rows = sh ? Math.max(0, sh.getLastRow() - 1) : 0;
    purchInfo.headers = sh && sh.getLastColumn() ? sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0] : [];
  } catch(e2) { purchInfo.error = e2.message || String(e2); }
  var gudangInfo = {};
  try {
    var gs = PROD_gudangSs_();
    gudangInfo.name = gs.getName();
    gudangInfo.id = gs.getId();
    var sm = gs.getSheetByName('Stock_Movement');
    gudangInfo.stockMovementFound = !!sm;
    gudangInfo.rows = sm ? Math.max(0, sm.getLastRow() - 1) : 0;
    gudangInfo.headers = sm && sm.getLastColumn() ? sm.getRange(1,1,1,sm.getLastColumn()).getValues()[0] : [];
  } catch(e3) { gudangInfo.error = e3.message || String(e3); }
  return { success:true, version:PROD_CFG.VERSION, spkLoaded:Object.keys(getDataSPK()).length, spkSample:Object.keys(getDataSPK()).slice(0,10), purchasing:purchInfo, gudang:gudangInfo, lastLoad:dbg.cache || {} };
}


// Helper 1: Validasi dan Kalkulasi Sisa WIP
function _cekKetersediaanWIP(d, pProd) {
  if(d.proses === "Potong" || d.proses === "Tugas Umum (Non-SPK)") return null;
  var cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cProd = pProd.c(["produk"], 6), cQty = pProd.c(["qty"], 7);
  var wipMap = {};
  var rowLamaIndex = d.rowLama ? parseInt(d.rowLama) - 2 : -1;
  
  for(var j=0; j<pProd.rows.length; j++){
    if(j === rowLamaIndex) continue;
    var row = pProd.rows[j];
    if(row[cSpk] === d.spk) {
      var prod = row[cProd], proses = row[cProses], qty = PROD_toNumber(row[cQty]);
      if(!wipMap[prod]) wipMap[prod] = { potong: 0, jahit: 0, qc: 0, gudang: 0, rPotong: 0, rJahit: 0, rQC: 0 };
      // Urutan reject wajib lebih dulu supaya "Reject Jahit" tidak ikut terbaca sebagai Jahit normal.
      if(proses === "Reject Potong") wipMap[prod].rPotong += qty;
      else if(proses === "Reject Jahit") wipMap[prod].rJahit += qty;
      else if(proses === "Reject QC") wipMap[prod].rQC += qty;
      else if(proses === "Potong") wipMap[prod].potong += qty;
      else if(proses.indexOf("Jahit") !== -1) wipMap[prod].jahit += qty;
      else if(proses === "QC & Packing") wipMap[prod].qc += qty;
      else if(proses === "Setor Gudang") wipMap[prod].gudang += qty;
    }
  }

  var reqMap = {};
  d.items.forEach(i => { if(!reqMap[i.produk]) reqMap[i.produk] = 0; reqMap[i.produk] += i.qty; });
  for(var p in reqMap) {
    var wip = wipMap[p] || { potong: 0, jahit: 0, qc: 0, gudang: 0, rPotong: 0, rJahit: 0, rQC: 0 };
    var reqQty = reqMap[p];
    if(d.proses.includes("Jahit") || d.proses === "Reject Potong") {
      var avail = wip.potong - wip.jahit - wip.rPotong;
      if(reqQty > avail) return "❌ Gagal: QTY ("+reqQty+") melebihi Sisa WIP Potong ("+avail+") untuk " + p;
    } else if(d.proses === "QC & Packing" || d.proses === "Reject Jahit") {
      var avail = wip.jahit - wip.qc - wip.rJahit;
      if(reqQty > avail) return "❌ Gagal: QTY ("+reqQty+") melebihi Sisa WIP Jahit ("+avail+") untuk " + p;
    } else if(d.proses === "Setor Gudang" || d.proses === "Reject QC") {
      var avail = wip.qc - wip.gudang - wip.rQC;
      if(reqQty > avail) return "❌ Gagal: QTY ("+reqQty+") melebihi Sisa WIP QC ("+avail+") untuk " + p;
    }
  }
  return null; 
}

// Helper 2: Validasi Sisa Stok Bahan Mentah di Gudang
function _cekSisaBahanBaku(namaBahan, rowLamaIndex, pProd, excludeSourceId) {
  if(!namaBahan) return 0;
  return PROD_stockBalance_(namaBahan, excludeSourceId || "");
}


function _getHargaBahanPerPcs(namaBahan) {
  if(!namaBahan) return 0;
  return PROD_avgCost_(namaBahan);
}


function _getTarifMap() {
  var tarifMap = {};
  try {
    var pTarif = getSheetWithMap("Master_Tarif");
    for(var j=0; j<pTarif.rows.length; j++) { 
      tarifMap[pTarif.rows[j][0] + "|" + pTarif.rows[j][1]] = PROD_toNumber(pTarif.rows[j][2]); 
    }
  } catch(e) {}
  return tarifMap;
}

function simpanDataProduksi(d) {
  try { ERP_mutation_('simpanDataProduksi'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch(e) { return "❌ Gagal: Server sibuk memproses antrean lain."; }
  var oldTrxId = "";
  try {
    var ss = PROD_selfSs_();
    d = d || {};
    d.tanggal = sanitizeStr(d.tanggal); d.spk = sanitizeStr(d.spk); d.proses = sanitizeStr(d.proses);
    d.pic = sanitizeStr(d.pic); d.bahan = d.bahan ? sanitizeStr(d.bahan) : ""; d.qtyBahan = PROD_toNumber_(d.qtyBahan);
    d.sistemUpah = sanitizeStr(d.sistemUpah || "borongan");
    d.biayaTambahan = PROD_toNumber_(d.biayaTambahan);
    d.catatan = d.catatan ? sanitizeStr(d.catatan) : "";
    var validItems = [];
    (d.items || []).forEach(function(i) {
       var cleanProd = sanitizeStr(i.produk); var cleanQty = PROD_toNumber_(i.qty);
       if(cleanProd && cleanQty > 0) validItems.push({produk: cleanProd, qty: cleanQty});
    });
    d.items = validItems;
    if(d.items.length === 0) return "❌ Gagal: Item hasil kerja kosong.";
    if(d.proses !== "Tugas Umum (Non-SPK)" && !d.spk) return "❌ Gagal: SPK wajib dipilih.";
    if(d.proses.indexOf("Reject") !== -1 && !d.catatan) return "❌ Gagal: Catatan reject wajib diisi.";

    var pProd = getSheetWithMap("Data_Produksi");
    var cTrxOld = pProd.c(["Trx_ID", "Trx ID"], -1);
    if(d.rowLama && cTrxOld !== -1) {
      oldTrxId = PROD_norm_(pProd.sheet.getRange(parseInt(d.rowLama), cTrxOld + 1).getValue());
    }
    var trxId = oldTrxId || PROD_uid_("PRD");

    var errorWIP = _cekKetersediaanWIP(d, pProd);
    if (errorWIP) return errorWIP;

    if (d.proses === "Potong" && d.bahan && d.qtyBahan > 0) {
      var sisaBahanDiGudang = _cekSisaBahanBaku(d.bahan, -1, pProd, trxId);
      if (d.qtyBahan > (sisaBahanDiGudang + 0.1)) return "❌ Gagal: QTY Bahan (" + d.qtyBahan + ") melebihi Stok Gudang tersedia (" + sisaBahanDiGudang.toFixed(2) + ") untuk " + d.bahan;
    }

    if(d.rowLama) {
      PROD_voidMovementsBySource_(trxId, "edit setoran produksi");
      var sEdit = ss.getSheetByName("Data_Produksi");
      sEdit.deleteRow(parseInt(d.rowLama));
      SpreadsheetApp.flush();
      pProd = getSheetWithMap("Data_Produksi");
    }

    var hargaBahan = (d.bahan && d.proses === "Potong") ? _getHargaBahanPerPcs(d.bahan) : 0;
    var tarifMap = _getTarifMap();
    var hppSnapshot = 0;
    if(d.proses === "Setor Gudang") {
      var dataHpp = getLaporanHPP();
      var targetHpp = dataHpp.find(function(x){ return String(x.spk || "").indexOf(d.spk) !== -1; });
      if(targetHpp) hppSnapshot = PROD_toNumber_(String(targetHpp.hppPerPcs || "").replace(/[^0-9,.\-]+/g,""));
    }

    var headers = pProd.headers;
    var cOutTgl = pProd.c(["tanggal", "tgl"], 0), cOutSpk = pProd.c(["spk"], 1), cOutProses = pProd.c(["proses"], 2), cOutPic = pProd.c(["pic"], 3), cOutBahan = pProd.c(["bahan"], 4), cOutQtyBhn = pProd.c(["qty bahan"], 5), cOutProd = pProd.c(["produk"], 6), cOutQty = pProd.c(["qty"], 7), cOutSistem = pProd.c(["sistem upah"], 8), cOutNilBhn = pProd.c(["nilai bahan"], 9), cOutBorong = pProd.c(["upah borongan"], 10), cOutEkstra = pProd.c(["biaya ekstra"], 11), cOutCatatan = pProd.c(["catatan", "alasan", "keterangan"], 12), cOutHpp = pProd.c(["hpp", "nilai perolehan", "harga pokok", "hpp / pcs"], 13);
    var cTrx = pProd.c(["Trx_ID", "Trx ID"], -1), cCreatedAt = pProd.c(["Created_At"], -1), cCreatedBy = pProd.c(["Created_By"], -1), cUpdatedAt = pProd.c(["Updated_At"], -1), cUpdatedBy = pProd.c(["Updated_By"], -1), cDeleted = pProd.c(["Is_Deleted"], -1);
    var totalCol = Math.max(headers.length, 20);
    var newRows = [], count = 0;
    var now = new Date(), email = PROD_userEmail_();

    for(var i=0; i<d.items.length; i++) {
      var item = d.items[i];
      var biayaEkstra = (i === 0) ? d.biayaTambahan : 0;
      var qtyKainFix = (i === 0 && d.proses === "Potong") ? d.qtyBahan : 0;
      var totalNilaiBahan = qtyKainFix * hargaBahan;
      var totalBorongan = 0;
      if(d.sistemUpah === "borongan" && d.proses !== "Tugas Umum (Non-SPK)" && d.proses.indexOf("Reject") === -1) totalBorongan = item.qty * (tarifMap[d.proses + "|" + item.produk] || 0);
      var row = new Array(totalCol).fill("");
      row[cOutTgl] = d.tanggal; row[cOutSpk] = d.spk; row[cOutProses] = d.proses;
      row[cOutPic] = d.pic; row[cOutBahan] = d.bahan; row[cOutQtyBhn] = qtyKainFix;
      row[cOutProd] = item.produk; row[cOutQty] = item.qty; row[cOutSistem] = d.sistemUpah;
      row[cOutNilBhn] = totalNilaiBahan; row[cOutBorong] = totalBorongan;
      row[cOutEkstra] = biayaEkstra; row[cOutCatatan] = d.catatan;
      row[cOutHpp] = (d.proses === "Setor Gudang") ? hppSnapshot : "";
      if(cTrx !== -1) row[cTrx] = trxId;
      if(cCreatedAt !== -1) row[cCreatedAt] = now;
      if(cCreatedBy !== -1) row[cCreatedBy] = email;
      if(cUpdatedAt !== -1) row[cUpdatedAt] = now;
      if(cUpdatedBy !== -1) row[cUpdatedBy] = email;
      if(cDeleted !== -1) row[cDeleted] = false;
      newRows.push(row); count++;
    }

    if(newRows.length > 0) {
      pProd.sheet.getRange(pProd.sheet.getLastRow() + 1, 1, newRows.length, totalCol).setValues(newRows);
      SpreadsheetApp.flush();
      if(pProd.sheet.getLastRow() > 1) pProd.sheet.getRange(2, 1, pProd.sheet.getLastRow() - 1, pProd.sheet.getLastColumn()).sort([{column: 1, ascending: true}]);
    }

    if(d.proses === "Potong" && d.bahan && d.qtyBahan > 0) {
      PROD_appendMovement_({ Tanggal: d.tanggal, Item_Name: d.bahan, Direction: "OUT", Movement_Type: "PRODUCTION_MATERIAL_OUT", Qty: d.qtyBahan, Unit_Cost: hargaBahan, Total_Cost: PROD_toNumber_(d.qtyBahan) * PROD_toNumber_(hargaBahan), SPK_ID: d.spk, Cost_Status: "PROVISIONAL", Cost_Source: "PROD_MATERIAL_USAGE", Source_Module: "PROD", Source_ID: trxId, Source_Line_ID: trxId + "-MAT", Ref_No: d.spk, Notes: "Pemakaian bahan produksi internal / potong" });
    }
    if(d.proses === "Setor Gudang") {
      d.items.forEach(function(item, idx) {
        PROD_appendMovement_({ Tanggal: d.tanggal, Item_Name: item.produk, Direction: "IN", Movement_Type: "PRODUCTION_IN", Qty: item.qty, Unit_Cost: hppSnapshot, Total_Cost: PROD_toNumber_(item.qty) * PROD_toNumber_(hppSnapshot), SPK_ID: d.spk, Cost_Status: "PROVISIONAL", Cost_Source: "PROD_COGM_PROVISIONAL", Source_Module: "PROD", Source_ID: trxId, Source_Line_ID: trxId + "-FG-" + (idx+1), Ref_No: d.spk, Notes: "Hasil produksi masuk gudang - cost provisional sampai closing" });
      });
    }

    if(d.spk && d.spk !== "-") cekDanTutupSPK(d.spk);
    return d.rowLama ? "✅ Data Diupdate! Stock_Movement produksi disesuaikan." : "✅ " + count + " Setoran Tersimpan! Stock_Movement produksi dibuat.";
  } catch(e) { return "❌ Gagal Fatal: " + e.message; }
  finally { lock.releaseLock(); }
}


function hapusDataProduksi(rowIndex) {
  try { ERP_mutation_('hapusDataProduksi'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch(e) { return "❌ Gagal: Server sibuk."; }
  try {
    var sProd = PROD_selfSs_().getSheetByName("Data_Produksi");
    var pProd = getSheetWithMap("Data_Produksi");
    var cSpk = pProd.c(["SPK"], 1), cTrx = pProd.c(["Trx_ID", "Trx ID"], -1);
    var deletedSpk = sProd.getRange(parseInt(rowIndex), cSpk + 1).getValue();
    var trxId = cTrx === -1 ? "" : sProd.getRange(parseInt(rowIndex), cTrx + 1).getValue();
    if(trxId) PROD_voidMovementsBySource_(trxId, "hapus setoran produksi");
    sProd.deleteRow(parseInt(rowIndex));
    SpreadsheetApp.flush();
    if(deletedSpk && deletedSpk !== "-") cekDanTutupSPK(deletedSpk);
    return "✅ Data setoran dihapus! Stock_Movement terkait di-void.";
  } catch(e) { return "❌ Gagal menghapus: " + e.message; }
  finally { lock.releaseLock(); }
}


function cekDanTutupSPK(targetSpk) {
  try {
    var targetStr = String(targetSpk || "").trim();
    if(!targetStr) return;
    var pProd = getSheetWithMap("Data_Produksi");
    var cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cQty = pProd.c(["qty"], 7), cDel = pProd.c(["Is_Deleted"], -1);
    var potong = 0, jahit = 0, qc = 0, gudang = 0, rPotong = 0, rJahit = 0, rQC = 0;
    for(var i=0; i<pProd.rows.length; i++) {
      if(cDel !== -1 && PROD_key_(pProd.rows[i][cDel]) === "TRUE") continue;
      if(String(pProd.rows[i][cSpk] || "").trim() === targetStr) {
        var p = String(pProd.rows[i][cProses] || "");
        var q = PROD_toNumber_(pProd.rows[i][cQty]);
        // Urutan reject wajib lebih dulu supaya "Reject Jahit" tidak ikut terbaca sebagai Jahit normal.
        if(p === "Reject Potong") rPotong += q;
        else if(p === "Reject Jahit") rJahit += q;
        else if(p === "Reject QC") rQC += q;
        else if(p === "Potong") potong += q;
        else if(p.indexOf("Jahit") !== -1) jahit += q;
        else if(p === "QC & Packing") qc += q;
        else if(p === "Setor Gudang") gudang += q;
      }
    }
    var sisaPotong = potong - jahit - rPotong;
    var sisaJahit = jahit - qc - rJahit;
    var sisaQC = qc - gudang - rQC;
    var plannedQty = 0;
    try {
      PROD_readActiveSpkRows_().forEach(function(r) {
        if(String(r.spk || "").trim() === targetStr) plannedQty += PROD_toNumber_(r.qty);
      });
    } catch(ePlan) {}
    var isSelesai = plannedQty > 0
      ? (gudang >= plannedQty && sisaPotong <= 0 && sisaJahit <= 0 && sisaQC <= 0)
      : (potong > 0 && sisaPotong <= 0 && sisaJahit <= 0 && sisaQC <= 0);
    var ss = PROD_selfSs_();
    var sSPK = ss.getSheetByName("Data_SPK") || ss.insertSheet("Data_SPK");
    if(sSPK.getLastRow() === 0) sSPK.getRange(1,1,1,PROD_LOCAL_SHEETS.Data_SPK.length).setValues([PROD_LOCAL_SHEETS.Data_SPK]);
    if(sSPK.getRange("J1").getValue() === "") sSPK.getRange("J1").setValue("ARSIP SPK SELESAI").setFontWeight("bold").setBackground("#0f172a").setFontColor("white");
    var dArsip = sSPK.getRange("J:J").getValues(), rowIndex = -1, lastRow = 1;
    for(var x=1; x<dArsip.length; x++) { if(dArsip[x][0]) { lastRow = x + 1; if(String(dArsip[x][0]).trim() === targetStr) rowIndex = x + 1; } }
    if(isSelesai && rowIndex === -1) sSPK.getRange(lastRow + 1, 10).setValue(targetStr);
    else if(!isSelesai && rowIndex !== -1) sSPK.getRange(rowIndex, 10).clearContent();
  } catch(e) {}
}



function PROD_syncStockCostPeriodFromRows_(pProd, hppMap) {
  var periodItem = {};
  var cTgl = pProd.c(["Tanggal", "Tgl", "Date"], 0);
  var cSpk = pProd.c(["SPK"], 1);
  var cProses = pProd.c(["Proses"], 2);
  var cProd = pProd.c(["Produk", "Item", "Barang Jadi"], 6);
  var cQty = pProd.c(["Qty", "Quantity"], 7);
  var cHpp = pProd.c(["HPP", "Nilai Perolehan", "Harga Pokok", "HPP / Pcs"], 13);
  var cDel = pProd.c(["Is_Deleted"], -1);
  for (var i=0; i<pProd.rows.length; i++) {
    var row = pProd.rows[i];
    if (cDel !== -1 && PROD_key_(row[cDel]) === "TRUE") continue;
    if (PROD_norm_(row[cProses]) !== "Setor Gudang") continue;
    var itemName = PROD_norm_(row[cProd]);
    var qty = PROD_toSheetNumber_(row[cQty]);
    if (!itemName || qty <= 0) continue;
    var spk = PROD_norm_(row[cSpk]);
    var hpp = PROD_toSheetNumber_(hppMap[spk] || row[cHpp]);
    if (hpp <= 0) continue;
    var period = PROD_formatPeriod_(row[cTgl]);
    var key = period + "|" + PROD_key_(itemName);
    if (!periodItem[key]) periodItem[key] = { period: period, itemName: itemName, qty: 0, value: 0, spk: {} };
    periodItem[key].qty += qty;
    periodItem[key].value += qty * hpp;
    if (spk) periodItem[key].spk[spk] = true;
  }

  var sh = PROD_stockCostPeriodSheet_();
  var headers = sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0];
  var map = PROD_headerMap_(headers);
  var cPeriod = PROD_col_(map, ["Period"], -1), cItem = PROD_col_(map, ["Item_Name"], -1), cDel2 = PROD_col_(map, ["Is_Deleted"], -1);
  var existing = {};
  if (sh.getLastRow() > 1 && cPeriod !== -1 && cItem !== -1) {
    var vals = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    for (var r=0; r<vals.length; r++) {
      if (cDel2 !== -1 && PROD_key_(vals[r][cDel2]) === "TRUE") continue;
      existing[PROD_norm_(vals[r][cPeriod]) + "|" + PROD_key_(vals[r][cItem])] = r + 2;
    }
  }
  var now = new Date(), email = PROD_userEmail_();
  var appendRows = [];
  Object.keys(periodItem).forEach(function(k) {
    var rec = periodItem[k];
    var unitCost = rec.qty > 0 ? rec.value / rec.qty : 0;
    var item = PROD_findItem_(rec.itemName) || {};
    var obj = {
      Period: rec.period,
      Item_ID: item.id || "",
      Item_Name: rec.itemName,
      Unit_Cost_Provisional: unitCost,
      Unit_Cost_Final: unitCost,
      Cost_Status: "FINAL",
      Source_Module: "PROD",
      Source_ID: Object.keys(rec.spk).join(", "),
      Synced_At: now,
      Synced_By: email,
      Notes: "Weighted average HPP produksi per item/periode dari Data_Produksi",
      Is_Deleted: false
    };
    var rowNo = existing[k];
    if (rowNo) sh.getRange(rowNo, 1, 1, headers.length).setValues([PROD_makeRow_(headers, obj)]);
    else appendRows.push(PROD_makeRow_(headers, obj));
  });
  if (appendRows.length) sh.getRange(sh.getLastRow() + 1, 1, appendRows.length, headers.length).setValues(appendRows);
  PROD_formatCostColumns_(sh);
  return Object.keys(periodItem).length;
}

function syncHppGudang() {
  try { ERP_mutation_('syncHppGudang'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(15000);
    var ss = PROD_selfSs_();
    var sProd = ss.getSheetByName("Data_Produksi");
    var dataHpp = getLaporanHPP();
    var hppMap = {};
    dataHpp.forEach(function(h) {
      var spkClean = String(h.spk || "").replace(/<[^>]+>/g, " ").split("(")[0].trim().split(" ")[0];
      var hppAngka = PROD_toNumber_(String(h.hppPerPcs || "").replace(/[^0-9,.\-]+/g,""));
      if(spkClean) hppMap[spkClean] = hppAngka;
    });
    var pProd = getSheetWithMap("Data_Produksi");
    var cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cHpp = pProd.c(["hpp", "nilai perolehan", "harga pokok", "hpp / pcs"], 13), cTrx = pProd.c(["Trx_ID"], -1);
    if(pProd.rows.length > 0) {
      var kolomHppLama = sProd.getRange(2, cHpp + 1, pProd.rows.length, 1).getValues();
      var adaPerubahan = false;
      for(var i=0; i<pProd.rows.length; i++) {
        if(pProd.rows[i][cProses] === "Setor Gudang") {
          var spk = String(pProd.rows[i][cSpk] || "").trim();
          var hppBaru = hppMap[spk] || 0;
          if(kolomHppLama[i][0] !== hppBaru) { kolomHppLama[i][0] = hppBaru; adaPerubahan = true; }
        } else if(kolomHppLama[i][0] !== "") { kolomHppLama[i][0] = ""; adaPerubahan = true; }
      }
      if(adaPerubahan) { sProd.getRange(2, cHpp + 1, pProd.rows.length, 1).setValues(kolomHppLama); SpreadsheetApp.flush(); }
    }
    // Update Unit_Cost movement PRODUCTION_IN berdasarkan HPP terbaru per SPK.
    try {
      var sh = PROD_stockMovementSheet_();
      var values = sh.getDataRange().getValues();
      var map = PROD_headerMap_(values[0]);
      var cType = PROD_col_(map, ["Movement_Type"], -1), cRef = PROD_col_(map, ["Ref_No"], -1), cCost = PROD_col_(map, ["Unit_Cost"], -1), cQty = PROD_col_(map, ["Qty"], -1), cTotal = PROD_col_(map, ["Total_Cost"], -1), cStatus = PROD_col_(map, ["Cost_Status"], -1), cLocked = PROD_col_(map, ["Cost_Locked_At"], -1), cDel = PROD_col_(map, ["Is_Deleted"], -1);
      var cCostPeriod = PROD_col_(map, ["Cost_Period"], -1), cUP = PROD_col_(map, ["Unit_Cost_Provisional"], -1), cVP = PROD_col_(map, ["Value_Provisional"], -1), cUF = PROD_col_(map, ["Unit_Cost_Final"], -1), cVF = PROD_col_(map, ["Value_Final"], -1), cCostSource = PROD_col_(map, ["Cost_Source"], -1), cSynced = PROD_col_(map, ["Cost_Synced_At"], -1), cTanggal = PROD_col_(map, ["Tanggal", "Source_Date"], -1);
      if(cType !== -1 && cRef !== -1 && cCost !== -1) {
        for(var r=1; r<values.length; r++) {
          if(cDel !== -1 && PROD_key_(values[r][cDel]) === "TRUE") continue;
          if(PROD_key_(values[r][cType]) === "PRODUCTIONIN") {
            var spkRef = String(values[r][cRef] || "").trim();
            var cost = hppMap[spkRef] || 0;
            if(cost) {
              var qtyMov = cQty !== -1 ? PROD_toSheetNumber_(values[r][cQty]) : 0;
              var totalMov = qtyMov * cost;
              sh.getRange(r+1, cCost+1).setValue(cost);
              if(cTotal !== -1) sh.getRange(r+1, cTotal+1).setValue(totalMov);
              if(cUP !== -1) sh.getRange(r+1, cUP+1).setValue(cost);
              if(cVP !== -1) sh.getRange(r+1, cVP+1).setValue(totalMov);
              if(cUF !== -1) sh.getRange(r+1, cUF+1).setValue(cost);
              if(cVF !== -1) sh.getRange(r+1, cVF+1).setValue(totalMov);
              if(cCostPeriod !== -1) sh.getRange(r+1, cCostPeriod+1).setValue(PROD_formatPeriod_(cTanggal !== -1 ? values[r][cTanggal] : new Date()));
              if(cStatus !== -1) sh.getRange(r+1, cStatus+1).setValue("FINAL");
              if(cCostSource !== -1) sh.getRange(r+1, cCostSource+1).setValue("PROD_COGM_FINAL");
              if(cSynced !== -1) sh.getRange(r+1, cSynced+1).setValue(new Date());
              if(cLocked !== -1) sh.getRange(r+1, cLocked+1).setValue(new Date());
            }
          }
        }
      }
    } catch(e2) {}
    var costRows = PROD_syncStockCostPeriodFromRows_(pProd, hppMap);
    try { PROD_formatCostColumns_(PROD_stockMovementSheet_()); } catch(eFmt) {}
    return "✅ HPP produksi, Unit_Cost/Total_Cost PRODUCTION_IN, dan Stock_Cost_Period berhasil disinkronkan (" + costRows + " item/periode).";
  } catch(e) { return "❌ Sinkronisasi HPP Gagal: " + e.message; }
  finally { lock.releaseLock(); }
}


// ================= BACA DATA LAPORAN =================
function getDashboardWIP(spkFilter) {
  try {
    var plannedRows = PROD_readActiveSpkRows_();
    var map = {};
    var listSpkUnik = [];

    function ensure_(spk, produk) {
      var key = String(spk || "").trim() + "|" + String(produk || "").trim();
      if (!map[key]) {
        map[key] = { spk: String(spk || "").trim(), produk: String(produk || "").trim(), planned: 0, potong: 0, jahit: 0, qc: 0, gudang: 0, rPotong: 0, rJahit: 0, rQC: 0 };
      }
      return map[key];
    }

    plannedRows.forEach(function(r) {
      if (!r.spk || !r.item) return;
      if (listSpkUnik.indexOf(r.spk) === -1) listSpkUnik.push(r.spk);
      var m = ensure_(r.spk, r.item);
      m.planned += PROD_toNumber_(r.qty);
    });

    var pProd = getSheetWithMap("Data_Produksi");
    var cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cProd = pProd.c(["produk"], 6), cQty = pProd.c(["qty"], 7), cDel = pProd.c(["Is_Deleted"], -1);
    for (var i=0; i<pProd.rows.length; i++) {
      if (cDel !== -1 && PROD_key_(pProd.rows[i][cDel]) === "TRUE") continue;
      var spk = String(pProd.rows[i][cSpk] || "").trim();
      if (!spk || spk === "-") continue;
      if (listSpkUnik.indexOf(spk) === -1) listSpkUnik.push(spk);
      var proses = String(pProd.rows[i][cProses] || "").trim();
      var item = String(pProd.rows[i][cProd] || "").trim();
      if (!item) continue;
      var qty = PROD_toNumber_(pProd.rows[i][cQty]);
      var m2 = ensure_(spk, item);

      // Urutan reject wajib lebih dulu supaya "Reject Jahit" tidak ikut terbaca sebagai "Jahit" normal.
      if (proses === "Reject Potong") m2.rPotong += qty;
      else if (proses === "Reject Jahit") m2.rJahit += qty;
      else if (proses === "Reject QC") m2.rQC += qty;
      else if (proses === "Potong") m2.potong += qty;
      else if (proses.indexOf("Jahit") !== -1) m2.jahit += qty;
      else if (proses === "QC & Packing") m2.qc += qty;
      else if (proses === "Setor Gudang") m2.gudang += qty;
    }

    var res = [];
    for (var k in map) {
      var m = map[k];
      if (spkFilter && m.spk.toLowerCase() !== String(spkFilter).toLowerCase()) continue;
      // Mapping WIP yang benar:
      // Potong: bahan OUT -> masuk Sisa Potong (siap Jahit)
      // Jahit:  Sisa Potong OUT -> masuk Sisa Jahit (siap QC)
      // QC:     Sisa Jahit OUT -> masuk Sisa QC (siap Setor Gudang)
      // Setor:  Sisa QC OUT -> masuk Barang Jadi/Gudang
      var sisaPotong = Math.max(m.potong - m.jahit - m.rPotong, 0);
      var sisaJahit = Math.max(m.jahit - m.qc - m.rJahit, 0);
      var sisaQC = Math.max(m.qc - m.gudang - m.rQC, 0);
      if (sisaPotong <= 0 && sisaJahit <= 0 && sisaQC <= 0 && m.gudang <= 0) continue;
      res.push({ spk: m.spk, produk: m.produk, sisaPotong: sisaPotong, sisaJahit: sisaJahit, sisaQC: sisaQC, selesai: m.gudang });
    }
    return { data: res.sort(function(a,b){ return (a.spk + a.produk).localeCompare(b.spk + b.produk); }), listSpk: listSpkUnik.sort() };
  } catch(e) {
    return { data: [], listSpk: [], error: e && e.message ? e.message : String(e) };
  }
}



function getLaporanProduksi(startStr, endStr) {
  try {
    var pProd = getSheetWithMap("Data_Produksi");
    var cTgl = pProd.c(["tanggal"], 0), cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cPic = pProd.c(["pic"], 3), cBahan = pProd.c(["bahan"], 4), cQtyBhn = pProd.c(["qty bahan"], 5), cItem = pProd.c(["produk"], 6), cQty = pProd.c(["qty"], 7), cSistem = pProd.c(["sistem upah"], 8), cBorong = pProd.c(["upah borongan"], 10), cBiaya = pProd.c(["biaya ekstra"], 11), cCatatan = pProd.c(["catatan", "alasan", "keterangan"], 12);
    
    var map = {}, grandTotal = 0, detailRiwayat = [];
    var start = startStr ? startStr : "";
    var end = endStr ? endStr : "";

    for(var i=0; i<pProd.rows.length; i++) {
      var row = pProd.rows[i], tglStr = row[cTgl];
      if(!tglStr) continue;
      
      // 💡 PERBAIKAN TIMEZONE: Gunakan perbandingan format string YYYY-MM-DD
      var rowTgl = formatInputTgl(tglStr); 
      if((start && rowTgl < start) || (end && rowTgl > end)) continue;
      
      var pic = row[cPic], spk = row[cSpk], proses = row[cProses], item = row[cItem], qty = PROD_toNumber(row[cQty]);
      var borongan = PROD_toNumber(row[cBorong]), biayaLain = PROD_toNumber(row[cBiaya]);
      var totalDuitBaris = borongan + biayaLain;
      
      detailRiwayat.push({ rowIndex: i + 2, tglStr: rowTgl, tglPrint: formatTgl(tglStr), pic: pic, spk: spk, proses: proses, item: item, qty: qty, bahan: row[cBahan], qtyBahan: row[cQtyBhn], sistemUpah: row[cSistem], biayaEkstra: biayaLain, catatan: row[cCatatan] || "", nominal: totalDuitBaris, rpFormat: formatRupiah(totalDuitBaris) });
      
      if(!map[pic]) map[pic] = { pic: pic, totalPcs: 0, borongan: 0, biayaLain: 0 };
      map[pic].totalPcs += qty; 
      map[pic].borongan += borongan;
      map[pic].biayaLain += biayaLain;
    }

    var res = [];
    for(var pic in map) {
      var m = map[pic], totalGaji = m.borongan + m.biayaLain;
      grandTotal += totalGaji;
      if(totalGaji > 0 || m.totalPcs > 0) {
          res.push({ pic: m.pic, totalPcs: m.totalPcs, borongan: formatRupiah(m.borongan), biayaLain: formatRupiah(m.biayaLain), totalGaji: formatRupiah(totalGaji), rawTotal: totalGaji });
      }
    }
    return { rekap: res.sort((a,b) => b.rawTotal - a.rawTotal), grandTotal: formatRupiah(grandTotal), details: detailRiwayat.reverse() };
  } catch(e) { 
      return { rekap: [], grandTotal: "Rp 0", details: [] };
  }
}

function getLaporanHPP() {
  try {
    var pProd = getSheetWithMap("Data_Produksi");
    var cTgl = pProd.c(["tanggal", "tgl"], 0), cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cQty = pProd.c(["qty"], 7), cNilaiBahan = pProd.c(["nilai bahan"], 9), cUpah = pProd.c(["upah borongan"], 10), cOverhead = pProd.c(["biaya ekstra", "overhead"], 11);
    
    var pSPK = null; try { pSPK = getSheetWithMap("Data_SPK"); } catch(e){}
    var pPeng = null; try { pPeng = getSheetWithMap("Data_Pengeluaran"); } catch(e){}

    var statusMap = {};
    if(pSPK) {
      var cSpkNo = pSPK.c(["spk", "no spk"], 1), cStat = pSPK.c(["status"], 2);
      for(var i=0; i<pSPK.rows.length; i++) { 
          if(pSPK.rows[i][cSpkNo]) statusMap[pSPK.rows[i][cSpkNo].toString().trim()] = pSPK.rows[i][cStat];
      }
    }

    var arsipSelesai = getArsipSelesai();
    var mapSPK = {}; 
    var monthMap = {};
    
    function getBulanThn(dStr) {
      if(!dStr) return null;
      var d = new Date(dStr); 
      if(isNaN(d.getTime())) return null;
      var m = d.getMonth() + 1;
      return d.getFullYear() + "-" + (m < 10 ? '0'+m : m);
    }

    for(var i=0; i<pProd.rows.length; i++) {
      var row = pProd.rows[i], tgl = row[cTgl], spk = row[cSpk], proses = row[cProses], qty = PROD_toNumber(row[cQty]); 
      var nilaiBahan = PROD_toNumber(row[cNilaiBahan]), upahBorongan = PROD_toNumber(row[cUpah]), inputOverhead = PROD_toNumber(row[cOverhead]);
      
      var mKey = getBulanThn(tgl); 
      if(!mKey) continue;
      
      if(!monthMap[mKey]) monthMap[mKey] = { totalPotongPabrik: 0, totalUangOverhead: 0 };
      monthMap[mKey].totalUangOverhead += inputOverhead;
      if(proses === "Potong") monthMap[mKey].totalPotongPabrik += qty;

      if(!spk || spk === "-") continue;
      var spkStr = spk.toString().trim();
      
      if(!mapSPK[spkStr]) mapSPK[spkStr] = { spk: spkStr, monthKey: mKey, totalPotongSPK: 0, totalGudangSPK: 0, totalRejectSPK: 0, nilaiBahan: 0, upahBorong: 0 };
      mapSPK[spkStr].nilaiBahan += nilaiBahan; 
      mapSPK[spkStr].upahBorong += upahBorongan;
      
      if(proses === "Potong") { 
          mapSPK[spkStr].totalPotongSPK += qty;
          mapSPK[spkStr].monthKey = mKey;
      } else if (proses === "Setor Gudang") { 
          mapSPK[spkStr].totalGudangSPK += qty;
      } else if (proses.includes("Reject")) { 
          mapSPK[spkStr].totalRejectSPK += qty;
      }
    }

    if(pPeng) {
      var cPTgl = pPeng.c(["tanggal", "tgl"], 0), cPNominal = pPeng.c(["nominal", "total"], 3);
      for(var j=0; j<pPeng.rows.length; j++) {
        var tglP = pPeng.rows[j][cPTgl], nominal = PROD_toNumber(pPeng.rows[j][cPNominal]);
        var mKey = getBulanThn(tglP);
        if(mKey) { 
            if(!monthMap[mKey]) monthMap[mKey] = { totalPotongPabrik: 0, totalUangOverhead: 0 };
            monthMap[mKey].totalUangOverhead += nominal;
        }
      }
    }

    var res = [];
    for(var k in mapSPK) {
      var m = mapSPK[k], statusSaatIni = statusMap[m.spk] || "Aktif", pembagiSPK = 1, labelPembagi = "", badgeStatus = "";
      if(statusSaatIni === "Selesai" || arsipSelesai.includes(m.spk)) statusSaatIni = "Selesai";
      
      if(statusSaatIni === "Selesai") {
        pembagiSPK = m.totalGudangSPK > 0 ? m.totalGudangSPK : 1;
        labelPembagi = `<br><small class="text-success fw-bold">(Actual Cost: ${pembagiSPK} Pcs Gudang)</small>`; 
        badgeStatus = `<br><span class="badge bg-success mt-1">Selesai</span>`;
      } else {
        pembagiSPK = m.totalPotongSPK > 0 ? m.totalPotongSPK : 1;
        labelPembagi = `<br><small class="text-secondary fw-bold">(Standard Cost: ${pembagiSPK} Pcs Potong)</small>`; 
        badgeStatus = `<br><span class="badge bg-primary mt-1">${statusSaatIni}</span>`;
      }
      
      var dataBulan = monthMap[m.monthKey] || { totalPotongPabrik: 1, totalUangOverhead: 0 };
      var pembagiPabrik = dataBulan.totalPotongPabrik > 0 ? dataBulan.totalPotongPabrik : 1;
      var tarifOverheadBulananPerPcs = dataBulan.totalUangOverhead / pembagiPabrik;
      var totalOverheadSPK = tarifOverheadBulananPerPcs * m.totalPotongSPK;
      
      var hppBahan = m.nilaiBahan / pembagiSPK, hppBorong = m.upahBorong / pembagiSPK, hppOverhead = totalOverheadSPK / pembagiSPK, hppTotal = hppBahan + hppBorong + hppOverhead;
      
      res.push({ spk: m.spk + badgeStatus + labelPembagi, bahanPcs: formatRupiah(hppBahan), upahPcs: formatRupiah(hppBorong), overheadPcs: formatRupiah(hppOverhead), hppPerPcs: formatRupiah(hppTotal) });
    }
    return res;
  } catch(e) { return []; }
}

// ================= CRUD PENGATURAN / MASTER DATA =================
function getMasterData() {
  try {
    var picSheet = getSheetWithMap("Master_PIC");
    var listPic = picSheet.rows.map(function(r, i){ return { id: i + 2, nama: r[0], status: r[1] ? r[1].toString().trim() : "Aktif" }; }).filter(function(x){ return x.nama; });
    var tarifSheet = getSheetWithMap("Master_Tarif");
    var listTarif = tarifSheet.rows.map(function(r, i){ return { id: i + 2, proses: r[0], produk: r[1], harga: r[2], formatHarga: formatRupiah(r[2]) }; }).filter(function(x){ return x.proses && x.produk; });
    var listItems = PROD_readMasterItems_().filter(function(x){ return x.type === "BARANGJADI"; }).map(function(x){ return x.name; });
    var uniqueItems = [];
    listItems.forEach(function(i) { if(uniqueItems.indexOf(i) === -1) uniqueItems.push(i); });
    uniqueItems.sort();
    return { pic: listPic, tarif: listTarif, items: uniqueItems };
  } catch(e) { return { pic: [], tarif: [], items: [] }; }
}


function simpanMasterPIC(nama) {
  try { ERP_mutation_('simpanMasterPIC'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch(e) { return "❌ Server sibuk"; }
  
  try {
    var sheet = PROD_selfSs_().getSheetByName("Master_PIC");
    if(sheet.getRange("B1").getValue() === "") sheet.getRange("B1").setValue("Status");
    
    // 💡 ANTI BUG: Cari baris kosong manual menghindari Array Formula
    var colValues = sheet.getRange("A:B").getValues();
    var lastRow = 0;
    for(var j = colValues.length - 1; j >= 0; j--) {
        if(colValues[j][0] !== "" || colValues[j][1] !== "") { lastRow = j + 1; break; }
    }
    if(lastRow === 0) lastRow = 1;
    
    sheet.getRange(lastRow + 1, 1, 1, 2).setValues([[sanitizeStr(nama), "Aktif"]]);
    return "✅ Karyawan berhasil ditambahkan!";
  } catch(e) { return "❌ Gagal: " + e.message; 
  } finally { lock.releaseLock(); }
}

function editMasterPIC(d) {
  try {
    var sheet = PROD_selfSs_().getSheetByName("Master_PIC");
    sheet.getRange(d.id, 1).setValue(sanitizeStr(d.nama));
    sheet.getRange(d.id, 2).setValue(sanitizeStr(d.status));
    return "✅ Data karyawan diupdate!";
  } catch(e) { return "❌ Gagal: " + e.message; }
}

function hapusMasterPIC(rowId) {
  try { ERP_mutation_('hapusMasterPIC'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch(e) { return "❌ Server sibuk"; }
  
  try { 
      PROD_selfSs_().getSheetByName("Master_PIC").deleteRow(rowId); 
      return "✅ Karyawan dihapus permanen!";
  } catch(e) { return "❌ Gagal: " + e.message; 
  } finally { lock.releaseLock(); }
}

function simpanMasterTarif(d) {
  try { ERP_mutation_('simpanMasterTarif'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch(e) { return "❌ Server sibuk"; }
  
  try {
    var sheet = PROD_selfSs_().getSheetByName("Master_Tarif");
    
    // 💡 ANTI BUG: Cari baris kosong manual menghindari Array Formula
    var colValues = sheet.getRange("A:C").getValues();
    var lastRow = 0;
    for(var j = colValues.length - 1; j >= 0; j--) {
        if(colValues[j][0] !== "" || colValues[j][1] !== "" || colValues[j][2] !== "") { lastRow = j + 1; break; }
    }
    if(lastRow === 0) lastRow = 1;
    
    sheet.getRange(lastRow + 1, 1, 1, 3).setValues([[sanitizeStr(d.proses), sanitizeStr(d.produk), PROD_toNumber(d.harga)]]);
    return "✅ Tarif berhasil ditambahkan!";
  } catch(e) { return "❌ Gagal: " + e.message; 
  } finally { lock.releaseLock(); }
}

function editMasterTarif(d) {
  try {
    var sheet = PROD_selfSs_().getSheetByName("Master_Tarif");
    sheet.getRange(d.id, 1).setValue(sanitizeStr(d.proses));
    sheet.getRange(d.id, 2).setValue(sanitizeStr(d.produk));
    sheet.getRange(d.id, 3).setValue(PROD_toNumber(d.harga));
    return "✅ Tarif berhasil diupdate!";
  } catch(e) { return "❌ Gagal: " + e.message; }
}

function hapusMasterTarif(rowId) {
  try { ERP_mutation_('hapusMasterTarif'); } catch(e) {}

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch(e) { return "❌ Server sibuk"; }
  
  try { 
      PROD_selfSs_().getSheetByName("Master_Tarif").deleteRow(rowId); 
      return "✅ Tarif dihapus permanen!";
  } catch(e) { return "❌ Gagal: " + e.message; 
  } finally { lock.releaseLock(); }
}

// ================= FUNGSI TARIK MASTER BAHAN (MODUL PRODUKSI) =================
function getMasterBahanList() {
  var list = [];
  try {
    var items = PROD_readMasterItems_();
    items.forEach(function(it) {
      if(it.type === "BAHAN" || it.type === "PACKAGING") {
        list.push({ kat: it.type === "BAHAN" ? "Bahan Baku" : "Aksesoris", sub: it.type, nama: it.name });
      }
    });
    list.sort(function(a,b){ return (a.sub + a.nama).localeCompare(b.sub + b.nama); });
  } catch(e) {}
  return list;
}


// ================= LAPORAN BARANG REJECT =================
function getLaporanReject(startStr, endStr) {
  try {
    var pProd = getSheetWithMap("Data_Produksi");
    var cTgl = pProd.c(["tanggal"], 0), cSpk = pProd.c(["spk"], 1), cProses = pProd.c(["proses"], 2), cPic = pProd.c(["pic"], 3), cBahan = pProd.c(["bahan"], 4), cQtyBhn = pProd.c(["qty bahan"], 5), cItem = pProd.c(["produk"], 6), cQty = pProd.c(["qty"], 7), cSistem = pProd.c(["sistem upah"], 8), cBiaya = pProd.c(["biaya ekstra"], 11), cCatatan = pProd.c(["catatan", "alasan", "keterangan"], 12);
    
    var start = startStr ? startStr : "";
    var end = endStr ? endStr : "";
    var res = [];

    for(var i=0; i<pProd.rows.length; i++) {
      var row = pProd.rows[i];
      var proses = row[cProses] ? row[cProses].toString() : "";
      
      if(proses.includes("Reject")) {
        var tglStr = row[cTgl];
        var rowTgl = formatInputTgl(tglStr); 
        if((start && rowTgl < start) || (end && rowTgl > end)) continue;
        
        res.push({
          rowIndex: i + 2, // 💡 KUNCI PENTING UNTUK EDIT/HAPUS
          tglStr: rowTgl,
          tglPrint: formatTgl(tglStr),
          spk: row[cSpk],
          proses: proses,
          pic: row[cPic],
          item: row[cItem],
          qty: PROD_toNumber(row[cQty]),
          bahan: row[cBahan] || "",
          qtyBahan: row[cQtyBhn] || 0,
          sistemUpah: row[cSistem] || "tanpa upah",
          biayaEkstra: PROD_toNumber(row[cBiaya]),
          catatan: row[cCatatan] || "-"
        });
      }
    }
    return res.reverse();
  } catch(e) { return []; }
}

// ================= SETUP & DEBUG TEST =================

function SETUP_installProduksiStockCostAdapter() {
  var gudang = PROD_gudangSs_();
  PROD_trySetIndonesianLocale_(gudang);
  var sm = PROD_ensureSheetHeaders_(gudang, "Stock_Movement", PROD_STOCK_MOVEMENT_HEADERS);
  var cp = PROD_ensureSheetHeaders_(gudang, "Stock_Cost_Period", PROD_STOCK_COST_PERIOD_HEADERS);
  PROD_formatCostColumns_(sm);
  PROD_formatCostColumns_(cp);
  return { success: true, version: PROD_CFG.VERSION, gudang: gudang.getName(), stockMovementHeaders: sm.getLastColumn(), stockCostPeriodHeaders: cp.getLastColumn() };
}
function TEST_produksiNumberParserDebug() {
  var samples = ["28.500", "1.234.567", "1.234,56", "1234,56", "12.5", "Rp 2.500.000", "2,500,000.50"];
  var out = {};
  samples.forEach(function(s) { out[s] = PROD_toNumber_(s); });
  return out;
}
function TEST_produksiStockCostWriteDebug() {
  var sh = PROD_stockMovementSheet_();
  var headers = sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0];
  var map = PROD_headerMap_(headers);
  return {
    version: PROD_CFG.VERSION,
    gudang: PROD_gudangSs_().getName(),
    parser: TEST_produksiNumberParserDebug(),
    hasTxKey: PROD_col_(map, ["Tx_Key"], -1) !== -1,
    hasValueProvisional: PROD_col_(map, ["Value_Provisional"], -1) !== -1,
    hasValueFinal: PROD_col_(map, ["Value_Final"], -1) !== -1,
    hasStockCostPeriod: !!PROD_gudangSs_().getSheetByName("Stock_Cost_Period")
  };
}

function SETUP_installProductionAdapter() {
  var ss = PROD_selfSs_();
  Object.keys(PROD_LOCAL_SHEETS).forEach(function(name) { PROD_ensureSheetHeaders_(ss, name, PROD_LOCAL_SHEETS[name]); });
  var gudangSs = PROD_gudangSs_();
  PROD_ensureSheetHeaders_(gudangSs, "Stock_Movement", PROD_STOCK_MOVEMENT_HEADERS);
  return { success: true, version: PROD_CFG.VERSION, produksiSpreadsheet: ss.getName(), produksiSpreadsheetId: ss.getId(), gudangSpreadsheet: gudangSs.getName(), gudangSpreadsheetId: gudangSs.getId(), sheets: Object.keys(PROD_LOCAL_SHEETS) };
}
function TEST_productionAdapterHealth() {
  var self = PROD_selfSs_();
  var gudang = PROD_gudangSs_();
  var items = PROD_readMasterItems_();
  var bahan = items.filter(function(x){ return x.type === "BAHAN" || x.type === "PACKAGING"; });
  var jadi = items.filter(function(x){ return x.type === "BARANGJADI"; });
  var spk = getDataSPK();
  return { success: true, version: PROD_CFG.VERSION, selfName: self.getName(), selfId: self.getId(), gudangName: gudang.getName(), gudangId: gudang.getId(), bahanPackagingLoaded: bahan.length, barangJadiLoaded: jadi.length, spkLoaded: Object.keys(spk).length, sampleBahan: bahan.slice(0,10), sampleBarangJadi: jadi.slice(0,10), sampleSPK: Object.keys(spk).slice(0,10) };
}
function TEST_productionStockBridgeDebug() {
  var gudangSs = PROD_gudangSs_();
  var sh = gudangSs.getSheetByName("Stock_Movement");
  return { success: true, gudangSpreadsheet: gudangSs.getName(), stockMovementFound: !!sh, headers: sh ? sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0] : [] };
}
function TEST_productionDropdownDebug() {
  return { bahanPackaging: getMasterBahanList().slice(0,30), barangJadi: getMasterData().items.slice(0,30), spk: Object.keys(getDataSPK()).slice(0,30) };
}


function PROD_doGetAccess_(params) {
  params = params || {};
  var email = PROD_normEmail_(params.vouch || params.email || params.user || '');
  var paspor = PROD_clean_(params.paspor || params.passport || params.token || '');
  var auth = PROD_securityCheck_(email, paspor, true);
  if (auth.allowed) {
    auth.passport = paspor;
    PROD_setContextUser_(auth.email);
  }
  return auth;
}

function PROD_forbiddenOutput_(auth) {
  var portal = PROD_getPortalUrl_();
  var btn = portal ? '<p><a style="display:inline-block;background:#1677ff;color:white;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:800" href="'+PROD_escapeHtml_(PROD_withLoginParam_(portal))+'" target="_top">Kembali ke Portal</a></p>' : '';
  return HtmlService.createHtmlOutput('<div style="font-family:Arial,sans-serif;text-align:center;margin-top:13vh;background:#f8fafc;padding:48px;border-radius:22px;max-width:680px;margin-left:auto;margin-right:auto;box-shadow:0 10px 25px rgba(0,0,0,.12)"><div style="font-size:78px">⛔</div><h1 style="color:#ef4444">AKSES / SESSION DITOLAK</h1><p>Alasan: <b>'+PROD_escapeHtml_(auth && auth.reason || 'UNKNOWN')+'</b></p><p>Email: <b>'+PROD_escapeHtml_(auth && auth.email || '(kosong)')+'</b></p><p>Silakan masuk dari Portal/Beranda supaya paspor session valid.</p>'+btn+'</div>').setTitle('Akses Ditolak');
}

function PROD_requirePassport_(emailOp, pasporOp) {
  var auth = PROD_securityCheck_(emailOp, pasporOp, true);
  if (!auth.allowed) throw new Error('Akses ditolak: ' + (auth.reason || 'UNKNOWN'));
  PROD_setContextUser_(auth.email);
  return auth;
}

function PROD_securityCheck_(email, paspor, passportRequired) {
  email = PROD_normEmail_(email || '');
  if (!email) return { allowed:false, reason:'EMAIL_KOSONG', email:'' };
  var user = PROD_findMasterUser_(email);
  if (!user) return { allowed:false, reason:'USER_TIDAK_ADA_DI_MASTER_USER', email:email };
  if (!PROD_isActiveStatus_(PROD_pick_(user, ['Status','Status_Akun','Aktif']))) return { allowed:false, reason:'USER_NONAKTIF', email:email, status:PROD_pick_(user, ['Status','Status_Akun','Aktif']) || '' };

  paspor = PROD_clean_(paspor);
  if (passportRequired) {
    var pv = PROD_validatePassport_(email, paspor);
    if (!pv.ok) return { allowed:false, reason:'PASPOR_' + pv.reason, email:email };
  } else if (paspor) {
    var pv2 = PROD_validatePassport_(email, paspor);
    if (!pv2.ok) return { allowed:false, reason:'PASPOR_' + pv2.reason, email:email };
  }

  var role = PROD_pick_(user, ['Role','Jabatan','Hak_Akses','Akses']) || '';
  var dept = PROD_pick_(user, ['Department','Departemen','Divisi']) || '';
  var allowedModules = PROD_pick_(user, ['Allowed_Modules','Allowed Modules','Module_Access','Hak_Modul','Akses_Modul','Modul']) || '';
  var isAdmin = PROD_key_(role).indexOf('ADMIN') !== -1 || PROD_key_(dept).indexOf('ADMIN') !== -1 || PROD_key_(allowedModules).indexOf('SUPERADMIN') !== -1 || PROD_key_(allowedModules).indexOf('ALL') !== -1;
  var can = isAdmin || PROD_userCanOpenModule_({allowedModules:allowedModules, role:role, department:dept}, PROD_FLOW_CFG.MODULE_CODE, 'Produksi');
  return {
    allowed: can,
    reason: can ? (isAdmin ? 'ADMIN' : 'MODULE_ALLOWED') : 'MODULE_NOT_ALLOWED',
    email: email,
    displayName: PROD_userDisplayName_(user, email),
    role: role,
    department: dept,
    allowedModules: allowedModules,
    isAdmin: isAdmin,
    passport: paspor
  };
}

function PROD_validatePassport_(email, paspor) {
  var p = PROD_parsePassport_(paspor);
  if (!p.stamp || !p.hash) return { ok:false, reason:'FORMAT_TIDAK_VALID' };
  if (p.hash !== PROD_hashPassport_(email, p.stamp)) return { ok:false, reason:'HASH_TIDAK_VALID' };
  if (Date.now() - p.stamp > PROD_FLOW_CFG.SESSION_TTL_MS) return { ok:false, reason:'EXPIRED' };
  var lastLogout = PROD_getLastLogoutStamp_(email);
  if (lastLogout && p.stamp < lastLogout) return { ok:false, reason:'GLOBAL_LOGOUT' };
  return { ok:true, stamp:p.stamp };
}

function PROD_parsePassport_(paspor) {
  var raw = PROD_clean_(paspor);
  var m = raw.match(/^(\d{10,}):([a-f0-9]{64})$/i);
  return m ? { stamp:Number(m[1]) || 0, hash:String(m[2] || '').toLowerCase() } : { stamp:0, hash:raw.toLowerCase() };
}

function PROD_hashPassport_(email, stamp) {
  var raw = PROD_normEmail_(email) + '|' + Number(stamp || 0) + '|' + PROD_FLOW_CFG.SHARED_SECRET;
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw)
    .map(function(b){ return (b < 0 ? b + 256 : b).toString(16).padStart(2, '0'); })
    .join('');
}

function PROD_findMasterUser_(email) {
  var sh = PROD_openMasterSs_().getSheetByName(PROD_FLOW_CFG.MASTER_USER_SHEET);
  if (!sh) throw new Error('Sheet Master_User tidak ditemukan.');
  var rows = PROD_readRowsObject_(sh);
  email = PROD_normEmail_(email);
  for (var i=0; i<rows.length; i++) {
    var rowEmail = PROD_normEmail_(PROD_pick_(rows[i], ['Email','Email_Google','Gmail','Email_User','User_Email','Username']));
    if (rowEmail === email) return rows[i];
  }
  return null;
}

function PROD_userDisplayName_(user, email) {
  return PROD_clean_(PROD_pick_(user, ['Display_Name','Display Name','Nama','Nama_User','Nama User','Name','User_Name','Username'])) || email;
}

function PROD_userCanOpenModule_(auth, code, name) {
  var fields = [auth.allowedModules, auth.role, auth.department].map(PROD_key_).join('|');
  if (fields.indexOf('ALL') !== -1 || fields.indexOf('SUPERADMIN') !== -1) return true;
  var targets = [code].concat(PROD_FLOW_CFG.MODULE_ALIASES).concat([name || '']).map(PROD_key_);
  return targets.some(function(t){ return t && fields.indexOf(t) !== -1; });
}

function PROD_globalHeartbeat(clientVersion, emailOp, pasporOp) {
  var auth = PROD_requirePassport_(emailOp, pasporOp);
  var hb = PROD_readGlobalHeartbeat_();
  return {
    ok: true,
    user: { email:auth.email, name:auth.displayName, role:auth.role, department:auth.department },
    serverVersion: hb.version,
    updatedAt: hb.updatedAt,
    shouldRefresh: !!clientVersion && String(clientVersion) !== String(hb.version),
    portalUrl: PROD_getPortalUrl_(),
    now: PROD_formatDateTimeFlow_(new Date())
  };
}

function PROD_logout(emailOp, pasporOp) {
  var auth = PROD_requirePassport_(emailOp, pasporOp);
  var stamp = Date.now();
  PROD_markLogout_(auth.email, stamp);
  try { SpreadsheetApp.flush(); } catch(e) {}
  PROD_bumpGlobalHeartbeat_('Logout ' + auth.email + ' from PROD');
  return { ok:true, success:true, message:'Logout berhasil.', email:auth.email, logoutAt:stamp, portalUrl:PROD_withLoginParam_(PROD_getPortalUrl_()) };
}


function PROD_touchGlobalChange(emailOp, pasporOp, notes) {
  var auth = PROD_requirePassport_(emailOp, pasporOp);
  var hb = PROD_bumpGlobalHeartbeat_(notes || ('Data changed from ' + PROD_FLOW_CFG.MODULE_CODE + ' by ' + auth.email));
  return { success:true, heartbeat:hb };
}

// Compatibility: fungsi legacy produksi masih memanggil ERP_mutation_ setelah write sukses.
function ERP_mutation_(fnName) {
  try { PROD_bumpGlobalHeartbeat_((fnName || 'Mutation') + ' @ ' + PROD_FLOW_CFG.MODULE_CODE); } catch(e) {}
}

function PROD_readGlobalHeartbeat_() {
  try {
    var sh = PROD_openMasterSs_().getSheetByName(PROD_FLOW_CFG.MASTER_MODULE_SHEET);
    if (!sh) return { version:'0', updatedAt:'', notes:'Master_Module tidak ditemukan' };
    var version = String(sh.getRange(PROD_FLOW_CFG.HEARTBEAT_CELL).getValue() || '0');
    return {
      version: version,
      updatedAt: PROD_formatDateTimeFlow_(sh.getRange(PROD_FLOW_CFG.HEARTBEAT_UPDATED_CELL).getValue()),
      notes: String(sh.getRange(PROD_FLOW_CFG.HEARTBEAT_NOTES_CELL).getValue() || '')
    };
  } catch(e) { return { version:'0', updatedAt:'', notes:e.message || String(e) }; }
}

function PROD_bumpGlobalHeartbeat_(notes) {
  var sh = PROD_openMasterSs_().getSheetByName(PROD_FLOW_CFG.MASTER_MODULE_SHEET);
  if (!sh) throw new Error('Master_Module tidak ditemukan untuk heartbeat.');
  var now = Date.now();
  sh.getRange(PROD_FLOW_CFG.HEARTBEAT_CELL).setValue(now);
  sh.getRange(PROD_FLOW_CFG.HEARTBEAT_UPDATED_CELL).setValue(new Date());
  sh.getRange(PROD_FLOW_CFG.HEARTBEAT_NOTES_CELL).setValue(notes || ('Update from ' + PROD_FLOW_CFG.MODULE_CODE));
  return PROD_readGlobalHeartbeat_();
}

function PROD_getPortalUrl_() {
  var links = PROD_readModuleLinksRaw_();
  for (var i = 0; i < links.length; i++) {
    var k = PROD_key_((links[i].code || '') + ' ' + (links[i].nama || ''));
    if (k.indexOf('PORTAL') !== -1 || k.indexOf('UTAMA') !== -1 || k.indexOf('BERANDA') !== -1 || k.indexOf('HOME') !== -1) return links[i].url;
  }
  return '';
}

function PROD_readModuleLinksRaw_() {
  var out = [];
  try {
    var sh = PROD_openMasterSs_().getSheetByName(PROD_FLOW_CFG.MASTER_MODULE_SHEET);
    if (!sh || sh.getLastRow() < 2) return out;
    var values = sh.getDataRange().getValues();
    var map = PROD_headerMap_(values[0]);
    var cCode = PROD_col_(map, ['Module_Code','Module Code','Kode_Modul','Kode Modul','Code'], -1);
    var cName = PROD_col_(map, ['Module_Name','Module Name','Nama_Modul','Nama Modul','Name','Nama'], -1);
    var cWeb = PROD_col_(map, ['Web_App_URL','Web App URL','WebApp_URL','WebApp URL','URL_Web_Aktif','URL','Link'], -1);
    var cStatus = PROD_col_(map, ['Status'], -1);
    for (var r = 1; r < values.length; r++) {
      var row = values[r];
      if (!PROD_isActiveStatus_(cStatus === -1 ? '' : row[cStatus])) continue;
      var code = cCode !== -1 ? PROD_clean_(row[cCode]) : '';
      var nm = cName !== -1 ? PROD_clean_(row[cName]) : code;
      var url = cWeb !== -1 ? PROD_clean_(row[cWeb]) : '';
      if (nm && url) out.push({ code:code, nama:nm, url:url });
    }
  } catch(e) {}
  return out;
}

function PROD_markLogout_(email, stamp) {
  var sh = PROD_openMasterSs_().getSheetByName(PROD_FLOW_CFG.MASTER_USER_SHEET);
  if (!sh) return;
  var vals = sh.getDataRange().getValues();
  if (vals.length < 1) return;
  var headers = vals[0];
  var map = PROD_headerMap_(headers);
  var cEmail = PROD_col_(map, ['Email','Email_Google','Gmail','Email_User','User_Email','Username'], -1);
  if (cEmail < 0) return;
  var cLogout = PROD_col_(map, ['Last_Logout_At','Global_Logout_At','Logout_At','Sesi_Terakhir_Logout'], -1);
  if (cLogout < 0) {
    cLogout = headers.length;
    sh.getRange(1, cLogout + 1).setValue('Last_Logout_At');
  }
  for (var r=1; r<vals.length; r++) {
    if (PROD_normEmail_(vals[r][cEmail]) !== PROD_normEmail_(email)) continue;
    sh.getRange(r+1, cLogout+1).setValue(Number(stamp || Date.now()));
    try { SpreadsheetApp.flush(); } catch(e) {}
    return;
  }
}

function PROD_getLastLogoutStamp_(email) {
  try {
    var user = PROD_findMasterUser_(email);
    if (!user) return 0;
    var v = PROD_pick_(user, ['Last_Logout_At','Global_Logout_At','Logout_At','Sesi_Terakhir_Logout']);
    if (!v) return 0;
    if (typeof v === 'number') return v;
    if (v instanceof Date) return v.getTime();
    var n = Number(v);
    if (!isNaN(n) && n > 0) return n;
    var d = new Date(v);
    return isNaN(d.getTime()) ? 0 : d.getTime();
  } catch(e) { return 0; }
}

function PROD_sessionInfoFromToken_(email, paspor) {
  var p = PROD_parsePassport_(paspor);
  var exp = p.stamp ? new Date(p.stamp + PROD_FLOW_CFG.SESSION_TTL_MS) : null;
  return {
    loginAt: p.stamp ? PROD_formatDateTimeFlow_(new Date(p.stamp)) : '',
    expiresAt: exp ? PROD_formatDateTimeFlow_(exp) : '',
    lastLogoutAt: PROD_getLastLogoutStamp_(email) ? PROD_formatDateTimeFlow_(new Date(PROD_getLastLogoutStamp_(email))) : '',
    ttlHours: Math.round(PROD_FLOW_CFG.SESSION_TTL_MS / 3600000)
  };
}

function PROD_readRowsObject_(sh) {
  var vals = sh.getDataRange().getValues();
  if (vals.length < 2) return [];
  var headers = vals[0].map(PROD_clean_);
  return vals.slice(1).filter(function(r){ return r.some(function(c){ return c !== '' && c !== null; }); }).map(function(r){
    var o = {};
    headers.forEach(function(h, i){ if (h) o[h] = r[i]; });
    return o;
  });
}

function PROD_pick_(obj, names) {
  names = Array.isArray(names) ? names : [names];
  for (var i=0; i<names.length; i++) {
    if (obj[names[i]] !== undefined && obj[names[i]] !== null && obj[names[i]] !== '') return obj[names[i]];
  }
  var keyMap = {};
  Object.keys(obj || {}).forEach(function(k){ keyMap[PROD_key_(k)] = obj[k]; });
  for (var j=0; j<names.length; j++) {
    var kk = PROD_key_(names[j]);
    if (keyMap[kk] !== undefined && keyMap[kk] !== null && keyMap[kk] !== '') return keyMap[kk];
  }
  return '';
}

function PROD_withLoginParam_(url){ url=PROD_clean_(url); if(!url)return ''; var sep=url.indexOf('?')===-1?'?':'&'; return url+sep+'login=1'; }
function PROD_clean_(v){ return String(v === null || v === undefined ? '' : v).trim(); }
function PROD_normEmail_(v){ return PROD_clean_(v).toLowerCase(); }
function PROD_formatDateTimeFlow_(v){ var d = (v instanceof Date) ? v : new Date(v); return isNaN(d.getTime()) ? '' : Utilities.formatDate(d, PROD_FLOW_CFG.TZ, 'yyyy-MM-dd HH:mm:ss'); }
function PROD_escapeHtml_(s){ return String(s||'').replace(/[&<>'"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c];}); }