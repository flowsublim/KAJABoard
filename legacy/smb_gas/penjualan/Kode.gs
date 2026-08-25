// =================================================================================
// ERP CV KIRAL - BACKEND MODUL PENJUALAN (Legacy UI + New DB Adapter v0.9 DP NO DOUBLE)
// =================================================================================

var SALES_CFG = {
  VERSION: "SALES_v1.6_PRINT_MODAL_TRX_STYLE",
  MASTER_SPREADSHEET_ID: "1bbtCMQfK5p_2c5GzIkTIrcIPcPsm3Wjh_R8PfAagu6I",
  MODULE_CODE: "SALES",
  MODULE_ALIASES: ["SALES", "PENJUALAN", "TRX", "TRANSAKSI", "MODUL PENJUALAN"],
  GUDANG_MODULE_ALIASES: ["WH", "GUDANG", "WAREHOUSE", "MODUL GUDANG"],
  FINANCE_MODULE_ALIASES: ["FIN", "FINANCE", "KEUANGAN", "MODUL FINANCE"],
  SALES_SPREADSHEET_ID_OVERRIDE: "",
  CACHE_SECONDS: 300,
  SESSION_TTL_MS: 6 * 60 * 60 * 1000,
  SHARED_SECRET: "CV_KIRAL_FLOW_SUBLIM_STYLE_FIXED_SECRET_2026_KIRAL",
  HEARTBEAT_CELL: "J1",
  HEARTBEAT_UPDATED_CELL: "J2",
  HEARTBEAT_NOTES_CELL: "J3",
  MASTER_USER_SHEET: "Master_User",
  MASTER_MODULE_SHEET: "Master_Module",
  LOG_LOGIN_SHEET: "Log_Login",
  PORTAL_CODES: ["PORTAL", "PRTL", "HOME", "BERANDA"],
  TZ: "Asia/Jakarta"
};

function doGet(e) {
  var erpPortalAuth = ERP_doGetAccess_(e);
  if (!erpPortalAuth.allowed) return ERP_forbiddenOutput_(erpPortalAuth);

  var emailAktif = (erpPortalAuth && erpPortalAuth.email) ? erpPortalAuth.email : SALES_userEmail_();
  if (!SALES_hasModuleAccess_(emailAktif)) {
    var htmlTolak = `
      <div style="font-family: Arial, sans-serif; text-align: center; margin-top: 15vh; background-color: #f8fafc; padding: 50px; border-radius: 20px; max-width: 650px; margin-left: auto; margin-right: auto; box-shadow: 0 10px 25px rgba(0,0,0,0.1);">
        <div style="font-size: 80px; margin-bottom: 20px;">⛔</div>
        <h1 style="color: #ef4444; margin-bottom: 10px;">AKSES DITOLAK</h1>
        <p style="color: #334155; font-size: 18px;">Email <b>${emailAktif || "(kosong)"}</b> tidak memiliki akses ke Modul Penjualan.</p>
        <p style="color: #64748b; font-size: 14px; margin-top: 30px;">Pastikan user ada di Master_User dengan Role ADMIN atau Status ACTIVE.</p>
      </div>`;
    return HtmlService.createHtmlOutput(htmlTolak).setTitle("Akses Ditolak - CV Kiral");
  }

  var tpl = HtmlService.createTemplateFromFile('Index');
  tpl.ERP_PASSPORT = erpPortalAuth.passport || ((e && e.parameter && e.parameter.passport) || '');
  tpl.ERP_PORTAL_URL = ERP_getPortalUrl_();
  tpl.ERP_USER_EMAIL = (erpPortalAuth && erpPortalAuth.email) ? erpPortalAuth.email : SALES_userEmail_();
  tpl.ERP_DISPLAY_NAME = (erpPortalAuth && erpPortalAuth.displayName) ? erpPortalAuth.displayName : ((erpPortalAuth && erpPortalAuth.email) || '');
  tpl.SALES_BOOTSTRAP = {
    moduleCode: SALES_CFG.MODULE_CODE,
    version: SALES_CFG.VERSION,
    email: tpl.ERP_USER_EMAIL,
    displayName: tpl.ERP_DISPLAY_NAME,
    passport: tpl.ERP_PASSPORT,
    paspor: tpl.ERP_PASSPORT,
    portalUrl: tpl.ERP_PORTAL_URL
  };
  return tpl.evaluate()
    .setTitle('ERP - Modul Penjualan')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

// =================================================================================
// UTILITIES
// =================================================================================

function SALES_userEmail_() {
  try { return (Session.getActiveUser().getEmail() || "").toLowerCase().trim(); }
  catch(e) { return ""; }
}

function SALES_now_() { return new Date(); }

function SALES_clean_(v) { return String(v == null ? "" : v).trim(); }
function SALES_cleanKey_(v) { return SALES_clean_(v).toUpperCase().replace(/[^A-Z0-9]/g, ""); }
function SALES_normHeader_(v) { return SALES_clean_(v).toLowerCase().replace(/\s+/g, "_"); }

function SALES_toNumber_(value) {
  if (typeof value === 'number') return isFinite(value) ? value : 0;
  if (value == null || value === '') return 0;
  var s = String(value).trim().replace(/Rp|IDR|\s/gi, '');
  if (!s) return 0;
  var hasComma = s.indexOf(',') !== -1;
  var hasDot = s.indexOf('.') !== -1;
  if (hasComma && hasDot) {
    if (s.lastIndexOf(',') > s.lastIndexOf('.')) s = s.replace(/\./g, '').replace(',', '.');
    else s = s.replace(/,/g, '');
  } else if (hasComma) {
    var parts = s.split(',');
    if (parts.length === 2 && parts[1].length <= 3) s = parts[0].replace(/\./g, '') + '.' + parts[1];
    else s = s.replace(/,/g, '');
  } else if (hasDot) {
    var dparts = s.split('.');
    if (dparts.length > 2 && dparts[dparts.length - 1].length === 3) s = s.replace(/\./g, '');
  }
  var n = Number(s);
  return isFinite(n) ? n : 0;
}

function formatRupiah(angka) {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(Math.round(SALES_toNumber_(angka)));
}

function formatTgl(dStr) {
  if(!dStr) return "-";
  var d = dStr instanceof Date ? dStr : new Date(dStr);
  if(isNaN(d.getTime())) return "-";
  return Utilities.formatDate(d, Session.getScriptTimeZone(), "dd/MM/yyyy");
}

function formatInputTgl(dStr) {
  if(!dStr) return "";
  var d = dStr instanceof Date ? dStr : new Date(dStr);
  if(isNaN(d.getTime())) return "";
  return Utilities.formatDate(d, Session.getScriptTimeZone(), "yyyy-MM-dd");
}

function sanitizeStr(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;")
    .trim();
}

function SALES_isActiveStatus_(status) {
  var s = SALES_cleanKey_(status);
  if (!s) return true;
  var inactive = ["INACTIVE", "NONAKTIF", "DISABLED", "OFF", "FALSE", "STOP", "STOPPED", "ARCHIVE", "ARSIP"];
  return inactive.indexOf(s) === -1;
}

function SALES_extractSpreadsheetId_(value) {
  var s = SALES_clean_(value);
  if (!s) return "";
  if (/^[a-zA-Z0-9-_]{25,}$/.test(s) && s.indexOf('/') === -1) return s;
  var m = s.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return m ? m[1] : "";
}

function SALES_headerMap_(headers) {
  var map = {};
  headers.forEach(function(h, i) {
    var k = SALES_normHeader_(h);
    if (k) map[k] = i;
  });
  return map;
}

function SALES_expandHeaderAliases_(name) {
  var n = SALES_normHeader_(name);
  var aliases = [n];
  var dict = {
    "nama_modul": ["module_name", "modul", "nama"],
    "nama": ["name", "item_name", "nama_item", "nama_barang", "nama_produk", "customer_name", "nama_customer", "nama_konsumen", "display_name"],
    "link": ["web_app_url", "url_web_app", "url", "webapp"],
    "url": ["web_app_url", "url_web_app", "link", "webapp"],
    "module_code": ["kode_modul", "code"],
    "spreadsheet_id": ["id_spreadsheet", "id_sheet", "sheet_id", "id"],
    "spreadsheet_url": ["url_spreadsheet", "gsheet_url"],
    "kontak": ["phone", "no_hp", "telepon", "whatsapp", "wa", "contact"],
    "alamat": ["address", "alamat_lengkap"],
    "kategori": ["category"],
    "sub_kategori": ["sub_category", "subkategori", "sub"],
    "nama_item": ["item_name", "nama_barang", "nama_produk", "internal_item_name", "item", "produk", "name", "nama"],
    "harga": ["price", "harga_jual", "harga_satuan", "hpp"],
    "status": ["state"],
    "tanggal": ["tgl", "date", "order_date", "invoice_date"],
    "qty": ["jumlah", "quantity", "pcs"],
    "customer": ["pelanggan", "customer_name", "nama_customer", "nama_konsumen"],
    "catatan": ["notes", "note", "keterangan"],
    "deadline": ["batas_waktu", "due_date"],
    "ekspedisi": ["kurir", "expedition", "shipping"],
    "no_po": ["nomor_po", "po_no", "order_no"],
    "no_sj": ["nomor_sj", "sj_no", "delivery_no"],
    "no_invoice": ["nomor_invoice", "invoice_no", "no_inv"],
    "ref_transaksi": ["referensi", "ref", "ref_po", "reference"],
    "ref_po": ["referensi_po", "ref_transaksi", "reference_po"],
    "ref_sj": ["referensi_sj", "delivery_ref", "sj_ref"],
    "nominal_bayar": ["bayar", "nominal", "amount", "jumlah_bayar"],
    "tipe": ["type", "jenis"]
  };
  if (dict[n]) aliases = aliases.concat(dict[n]);
  return aliases;
}

function SALES_col_(map, headerNames, fallbackIndex) {
  var names = Array.isArray(headerNames) ? headerNames : [headerNames];
  for (var k = 0; k < names.length; k++) {
    var aliases = SALES_expandHeaderAliases_(names[k]);
    for (var a = 0; a < aliases.length; a++) {
      if (map[aliases[a]] !== undefined) return map[aliases[a]];
    }
  }
  return fallbackIndex;
}

function SALES_masterSs_() { return SpreadsheetApp.openById(SALES_CFG.MASTER_SPREADSHEET_ID); }

function SALES_openModuleSpreadsheet_(aliases) {
  aliases = aliases || SALES_CFG.MODULE_ALIASES;
  var aliasClean = aliases.map(SALES_cleanKey_);
  var sh = SALES_masterSs_().getSheetByName("Master_Module");
  if (!sh) throw new Error("Sheet Master_Module tidak ditemukan di Master Database.");
  var values = sh.getDataRange().getValues();
  if (values.length < 2) throw new Error("Master_Module masih kosong.");
  var map = SALES_headerMap_(values[0]);
  var cCode = SALES_col_(map, ["Module_Code", "Kode Modul", "Code"], -1);
  var cName = SALES_col_(map, ["Module_Name", "Nama Modul", "Name"], -1);
  var cId = SALES_col_(map, ["Spreadsheet_ID", "ID Spreadsheet"], -1);
  var cUrl = SALES_col_(map, ["Spreadsheet_URL", "URL Spreadsheet"], -1);
  var cStatus = SALES_col_(map, ["Status"], -1);

  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var code = cCode !== -1 ? SALES_cleanKey_(row[cCode]) : "";
    var name = cName !== -1 ? SALES_cleanKey_(row[cName]) : "";
    var status = cStatus !== -1 ? row[cStatus] : "";
    if (!SALES_isActiveStatus_(status)) continue;
    var matched = aliasClean.some(function(a) { return code === a || name === a || code.indexOf(a) !== -1 || name.indexOf(a) !== -1; });
    if (!matched) continue;
    var id = cId !== -1 ? SALES_extractSpreadsheetId_(row[cId]) : "";
    if (!id && cUrl !== -1) id = SALES_extractSpreadsheetId_(row[cUrl]);
    if (!id) throw new Error("Spreadsheet_ID kosong untuk modul penjualan: " + (row[cCode] || row[cName]));
    return SpreadsheetApp.openById(id);
  }
  throw new Error("Modul Penjualan tidak ditemukan di Master_Module. Dicari: " + aliases.join(", "));
}

function SALES_salesSs_() {
  if (SALES_CFG.SALES_SPREADSHEET_ID_OVERRIDE) return SpreadsheetApp.openById(SALES_CFG.SALES_SPREADSHEET_ID_OVERRIDE);
  try { return SALES_openModuleSpreadsheet_(SALES_CFG.MODULE_ALIASES); }
  catch(e) {
    // Saat development bound script, fallback ke active spreadsheet.
    var active = SpreadsheetApp.getActiveSpreadsheet();
    if (active) return active;
    throw e;
  }
}


// =================================================================================
// BRIDGE SURAT JALAN -> STOCK_MOVEMENT GUDANG
// =================================================================================

var SALES_STOCK_MOVEMENT_HEADERS = [
  "Movement_ID", "Tanggal", "Item_ID", "Item_Name", "Warehouse_Code", "Direction",
  "Movement_Type", "Qty", "Unit_Cost", "Source_Module", "Source_ID", "Source_Line_ID",
  "Ref_No", "Notes", "Created_At", "Created_By", "Is_Deleted"
];

function SALES_gudangSs_() {
  return SALES_openModuleSpreadsheet_(SALES_CFG.GUDANG_MODULE_ALIASES || ["WH", "GUDANG", "WAREHOUSE"]);
}

function SALES_financeSs_() {
  return SALES_openModuleSpreadsheet_(SALES_CFG.FINANCE_MODULE_ALIASES || ["FIN", "FINANCE", "KEUANGAN"]);
}

function SALES_nowText_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
}

function SALES_dateOnlyText_(v) {
  var d = v instanceof Date ? v : new Date(v || new Date());
  if (isNaN(d.getTime())) d = new Date();
  return Utilities.formatDate(d, Session.getScriptTimeZone(), "yyyy-MM-dd");
}

function SALES_safeIdPart_(s) {
  return (SALES_cleanKey_(s) || "SJ").slice(0, 35);
}

function SALES_makeSalesMovementId_(noSj, lineNo) {
  var ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMddHHmmss");
  return "SM-SALES-" + SALES_safeIdPart_(noSj) + "-" + ts + "-" + Utilities.formatString("%03d", lineNo || 1);
}

function SALES_ensureSheetHeaders_(ss, sheetName, headers) {
  var sh = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
  if (sh.getLastRow() === 0) {
    sh.appendRow(headers);
  } else {
    var lastCol = Math.max(1, sh.getLastColumn());
    var existing = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(String);
    var norm = existing.map(function(h) { return SALES_normHeader_(h); });
    var add = headers.filter(function(h) { return norm.indexOf(SALES_normHeader_(h)) === -1; });
    if (add.length) sh.getRange(1, existing.length + 1, 1, add.length).setValues([add]);
  }
  sh.getRange(1, 1, 1, sh.getLastColumn()).setFontWeight("bold").setBackground("#e0f2fe");
  sh.setFrozenRows(1);
  return sh;
}

function SALES_appendObjectsByHeader_(ss, sheetName, headers, objects) {
  if (!objects || !objects.length) return [];
  var sh = SALES_ensureSheetHeaders_(ss, sheetName, headers);
  var currentHeaders = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var map = SALES_headerMap_(currentHeaders);
  var rows = objects.map(function(obj) {
    var row = new Array(currentHeaders.length).fill("");
    Object.keys(obj).forEach(function(k) {
      var idx = SALES_col_(map, [k], -1);
      if (idx !== -1) row[idx] = obj[k];
    });
    return row;
  });
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, currentHeaders.length).setValues(rows);
  return objects;
}

function SALES_getMasterItemStockLookup_() {
  var sh = SALES_masterSs_().getSheetByName("Master_Item");
  if (!sh || sh.getLastRow() < 2) throw new Error("Master_Item kosong / tidak ditemukan di Master Database.");

  var values = sh.getDataRange().getValues();
  var map = SALES_headerMap_(values[0]);
  var cId = SALES_col_(map, ["Item_ID", "ID Item", "ID"], -1);
  var cName = SALES_col_(map, ["Item_Name", "Nama_Item", "Nama Item", "Nama_Barang", "Nama Barang", "Nama_Produk", "Nama Produk", "Internal_Item_Name", "Item", "Produk", "Nama"], -1);
  var cCost = SALES_col_(map, ["Default_Cost", "Unit_Cost", "HPP", "Harga_Beli", "Harga Beli", "Cost"], -1);
  var cStatus = SALES_col_(map, ["Status"], -1);

  if (cName === -1) throw new Error("Header nama item tidak ditemukan di Master_Item.");

  var byName = {};
  var items = [];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    if (!SALES_isActiveStatus_(cStatus === -1 ? "" : row[cStatus])) continue;
    var name = SALES_clean_(row[cName]);
    if (!name) continue;
    var item = {
      Item_ID: cId !== -1 ? SALES_clean_(row[cId]) : "",
      Item_Name: name,
      Unit_Cost: cCost !== -1 ? SALES_toNumber_(row[cCost]) : 0
    };
    if (!item.Item_ID) item.Item_ID = SALES_makeId_("ITEM");
    items.push(item);
    byName[SALES_cleanKey_(name)] = item;
    byName[name.toLowerCase()] = item;
  }
  return { items: items, byName: byName };
}

function SALES_isStockItemName_(nama) {
  var n = SALES_clean_(nama);
  var k = SALES_cleanKey_(n);
  if (!k) return false;
  var skip = ["BIAYAONGKOSKIRIM", "ONGKIR", "POTONGANDISKON", "DISKON"];
  if (skip.indexOf(k) !== -1) return false;
  if (k.indexOf("PAJAKPPN") === 0 || k.indexOf("PPN") === 0) return false;
  return true;
}

function SALES_prepareSjStockMovementRows_(d, items) {
  var lookup = SALES_getMasterItemStockLookup_();
  var rows = [];
  var lineNo = 1;
  (items || []).forEach(function(i) {
    var nama = SALES_clean_(i.nama);
    if (!SALES_isStockItemName_(nama)) return;
    var qty = SALES_toNumber_(i.qty);
    if (qty <= 0) return;

    var item = lookup.byName[SALES_cleanKey_(nama)] || lookup.byName[nama.toLowerCase()];
    if (!item) throw new Error("Item SJ belum ada di Master_Item / beda nama: " + nama);

    rows.push({
      Movement_ID: SALES_makeSalesMovementId_(d.no, lineNo),
      Tanggal: SALES_dateOnlyText_(d.tgl),
      Item_ID: item.Item_ID,
      Item_Name: item.Item_Name,
      Warehouse_Code: "MAIN",
      Direction: "OUT",
      Movement_Type: "SALES_OUT",
      Qty: qty,
      Unit_Cost: item.Unit_Cost || 0,
      Source_Module: "SALES",
      Source_ID: SALES_clean_(d.no),
      Source_Line_ID: SALES_clean_(d.ref || "") + "|" + lineNo,
      Ref_No: SALES_clean_(d.no),
      Notes: "Surat Jalan Penjualan - menunggu validasi fisik Gudang | PO: " + SALES_clean_(d.ref || "-") + " | Customer: " + SALES_clean_(d.cust || "-") + " | Ekspedisi: " + SALES_clean_(d.eks || "-"),
      Created_At: SALES_nowText_(),
      Created_By: SALES_userEmail_(),
      Is_Deleted: false
    });
    lineNo++;
  });
  if (!rows.length) throw new Error("Tidak ada item stok valid untuk ditembak ke Stock_Movement.");
  return rows;
}

function SALES_postSjToStockMovement_(d, items, preparedRows) {
  try { ERP_mutation_('SALES_postSjToStockMovement_'); } catch(e) {}

  var gudangSs = SALES_gudangSs_();
  var rows = preparedRows || SALES_prepareSjStockMovementRows_(d, items);

  // Anti dobel: kalau No SJ yang sama pernah tertulis, void dulu lalu tulis ulang.
  SALES_voidSjStockMovement_(d.no, "REPOST_FROM_SALES");

  SALES_appendObjectsByHeader_(gudangSs, "Stock_Movement", SALES_STOCK_MOVEMENT_HEADERS, rows);
  return { success: true, inserted: rows.length, movementType: "SALES_OUT", auditStatus: "PENDING" };
}

function SALES_voidSjStockMovement_(noSj, reason) {
  noSj = SALES_clean_(noSj);
  if (!noSj) return { success: true, voided: 0 };

  var gudangSs = SALES_gudangSs_();
  var sh = SALES_ensureSheetHeaders_(gudangSs, "Stock_Movement", SALES_STOCK_MOVEMENT_HEADERS);
  if (sh.getLastRow() < 2) return { success: true, voided: 0 };

  var values = sh.getDataRange().getValues();
  var map = SALES_headerMap_(values[0]);
  var cSourceModule = SALES_col_(map, ["Source_Module"], -1);
  var cSourceId = SALES_col_(map, ["Source_ID"], -1);
  var cRefNo = SALES_col_(map, ["Ref_No"], -1);
  var cDel = SALES_col_(map, ["Is_Deleted"], -1);
  var cNotes = SALES_col_(map, ["Notes"], -1);
  if (cDel === -1) throw new Error("Header Is_Deleted tidak ditemukan di Stock_Movement Gudang.");

  var noKey = SALES_cleanKey_(noSj);
  var now = SALES_nowText_();
  var count = 0;
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var srcModule = cSourceModule !== -1 ? SALES_cleanKey_(row[cSourceModule]) : "";
    var srcId = cSourceId !== -1 ? SALES_cleanKey_(row[cSourceId]) : "";
    var refNo = cRefNo !== -1 ? SALES_cleanKey_(row[cRefNo]) : "";
    var del = SALES_cleanKey_(row[cDel]);
    if (del === "TRUE" || del === "YA" || del === "1") continue;
    if (srcModule === "SALES" && (srcId === noKey || refNo === noKey)) {
      sh.getRange(r + 1, cDel + 1).setValue(true);
      if (cNotes !== -1) {
        var oldNote = SALES_clean_(row[cNotes]);
        sh.getRange(r + 1, cNotes + 1).setValue(oldNote + " | VOID " + now + " " + SALES_clean_(reason || "VOID_FROM_SALES"));
      }
      count++;
    }
  }
  return { success: true, voided: count };
}

function SETUP_installSalesStockBridge() {
  var gudangSs = SALES_gudangSs_();
  var sh = SALES_ensureSheetHeaders_(gudangSs, "Stock_Movement", SALES_STOCK_MOVEMENT_HEADERS);
  return {
    success: true,
    gudangSpreadsheet: gudangSs.getName(),
    gudangSpreadsheetId: gudangSs.getId(),
    stockMovementSheet: sh.getName(),
    rows: sh.getLastRow(),
    headers: sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
  };
}

function TEST_salesGudangRouting() {
  var gudangSs = SALES_gudangSs_();
  var sh = gudangSs.getSheetByName("Stock_Movement");
  return {
    success: true,
    salesVersion: SALES_CFG.VERSION,
    gudangSpreadsheet: gudangSs.getName(),
    gudangSpreadsheetId: gudangSs.getId(),
    stockMovementFound: !!sh,
    stockMovementRows: sh ? sh.getLastRow() : 0,
    stockMovementHeaders: sh ? sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0] : []
  };
}

function TEST_salesStockBridgeDebug() {
  var lookup = SALES_getMasterItemStockLookup_();
  var gudang = TEST_salesGudangRouting();
  return {
    success: true,
    gudang: gudang,
    masterItemsLoaded: lookup.items.length,
    sampleItems: lookup.items.slice(0, 10)
  };
}

function SALES_isMasterSheet_(sheetName) {
  var s = SALES_cleanKey_(sheetName);
  return s.indexOf("MASTER") === 0 || s === "DATASETUP" || s === "SETUPPERUSAHAAN";
}

function SALES_getSheet_(sheetName) {
  var aliases = {
    "Master_Modul": "Master_Module",
    "Master_Module": "Master_Module",
    "Data_Setup": "Data_Setup",
    "Setup_Perusahaan": "Data_Setup"
  };
  var targetName = aliases[sheetName] || sheetName;
  var ssList = [];
  if (SALES_isMasterSheet_(targetName)) ssList = [SALES_masterSs_(), SALES_salesSs_()];
  else ssList = [SALES_salesSs_(), SALES_masterSs_()];

  for (var i = 0; i < ssList.length; i++) {
    var sh = ssList[i].getSheetByName(targetName);
    if (sh) return sh;
    // fallback aliases for old names
    if (targetName === "Master_Customer") {
      sh = ssList[i].getSheetByName("Master_Customer") || ssList[i].getSheetByName("Master_Pelanggan");
      if (sh) return sh;
    }
    if (targetName === "Master_Ekspedisi") {
      sh = ssList[i].getSheetByName("Master_Ekspedisi") || ssList[i].getSheetByName("Master_Expedition") || ssList[i].getSheetByName("Master_Kurir");
      if (sh) return sh;
    }
  }
  return null;
}

function getSheetWithMap(sheetName) {
  var s = SALES_getSheet_(sheetName);
  if(!s) return null;
  var data = s.getDataRange().getValues();
  var headers = data.length > 0 ? data[0] : [];
  var map = SALES_headerMap_(headers);
  var c = function(headerNames, fallbackIndex) { return SALES_col_(map, headerNames, fallbackIndex); };
  return { rows: data.length > 1 ? data.slice(1) : [], c: c, sheet: s, headers: headers, fullData: data };
}

function SALES_getSetupData_() {
  var setupData = {};
  var sh = SALES_getSheet_("Data_Setup");
  if (!sh) return setupData;
  var vals = sh.getDataRange().getValues();
  for (var i = 0; i < vals.length; i++) {
    if (vals[i][0]) setupData[String(vals[i][0]).trim().toLowerCase()] = String(vals[i][1] || "").trim();
  }
  return setupData;
}

function SALES_getCompanyProfiles_() {
  var companies = [];
  var masterSs = SALES_masterSs_();
  var sh = masterSs.getSheetByName("Master_Company") || masterSs.getSheetByName("Master_Perusahaan") || masterSs.getSheetByName("Master_Identitas_Perusahaan");

  if (sh && sh.getLastRow() > 1) {
    var values = sh.getDataRange().getValues();
    var map = SALES_headerMap_(values[0]);
    var cId = SALES_col_(map, ["Company_ID", "Company ID", "Kode", "Kode_Perusahaan", "ID"], -1);
    var cName = SALES_col_(map, ["Company_Name", "Nama_Perusahaan", "Nama Perusahaan", "Nama", "Name"], -1);
    var cAddress = SALES_col_(map, ["Address", "Alamat", "Alamat_Perusahaan", "Alamat Lengkap"], -1);
    var cPhone = SALES_col_(map, ["Phone", "No_HP", "No HP", "No_Telp", "Telepon", "Whatsapp", "WA"], -1);
    var cBank = SALES_col_(map, ["Bank_Account", "No_Rekening", "No Rekening", "Rekening", "Info_Rekening", "Bank"], -1);
    var cLogo = SALES_col_(map, ["Logo_URL", "Logo URL", "Logo", "URL_Logo", "Logo_Link", "Link_Logo"], -1);
    var cStatus = SALES_col_(map, ["Status"], -1);
    var cSort = SALES_col_(map, ["Sort_Order", "Urutan", "Order", "No_Urut"], -1);

    for (var r = 1; r < values.length; r++) {
      var row = values[r];
      var name = cName !== -1 ? SALES_clean_(row[cName]) : "";
      if (!name) continue;
      if (!SALES_isActiveStatus_(cStatus === -1 ? "" : row[cStatus])) continue;
      var id = cId !== -1 ? SALES_clean_(row[cId]) : "";
      if (!id) id = name;
      companies.push({
        id: id,
        nama: name,
        alamat: cAddress !== -1 ? SALES_clean_(row[cAddress]) : "",
        noHp: cPhone !== -1 ? SALES_clean_(row[cPhone]) : "",
        rekening: cBank !== -1 ? SALES_clean_(row[cBank]) : "",
        logo: cLogo !== -1 ? SALES_clean_(row[cLogo]) : "",
        sort: cSort !== -1 ? SALES_toNumber_(row[cSort]) : (r + 1)
      });
    }
    companies.sort(function(a, b) { return (a.sort || 999) - (b.sort || 999) || a.nama.localeCompare(b.nama); });
  }

  // Fallback agar cetak lama tetap jalan kalau Master_Company belum diisi.
  if (companies.length === 0) {
    var setup = SALES_getSetupData_();
    companies.push({
      id: "KAMPUNG_JAHIT",
      nama: setup["nama kampung jahit"] || setup["nama"] || "KAMPUNG JAHIT",
      alamat: setup["alamat kampung jahit"] || setup["alamat"] || "",
      noHp: setup["no hp kampung jahit"] || setup["no hp"] || setup["telepon"] || "",
      rekening: setup["rekening kampung jahit"] || setup["rekening"] || "",
      logo: setup["logo kampung jahit"] || setup["logo"] || "",
      sort: 1
    });
    companies.push({
      id: "CV_KIRAL",
      nama: setup["nama cv kiral"] || "CV KIRAL",
      alamat: setup["alamat cv kiral"] || setup["alamat"] || "",
      noHp: setup["no hp cv kiral"] || setup["no hp"] || setup["telepon"] || "",
      rekening: setup["rekening cv kiral"] || setup["rekening"] || "",
      logo: setup["logo cv kiral"] || "",
      sort: 2
    });
  }

  return companies;
}

function SETUP_installSalesCompanyMaster() {
  var ss = SALES_masterSs_();
  var sh = ss.getSheetByName("Master_Company") || ss.insertSheet("Master_Company");
  var headers = ["Company_ID", "Company_Name", "Address", "Phone", "Bank_Account", "Logo_URL", "Status", "Sort_Order", "Notes"];
  if (sh.getLastRow() === 0) {
    sh.appendRow(headers);
    sh.appendRow(["KAMPUNG_JAHIT", "Kampung Jahit", "Isi alamat Kampung Jahit", "Isi no HP", "Isi rekening / bank", "Isi URL logo", "ACTIVE", 1, "Default B2B biasa"]);
    sh.appendRow(["CV_KIRAL", "CV Kiral", "Isi alamat CV Kiral", "Isi no HP", "Isi rekening / bank", "Isi URL logo", "ACTIVE", 2, "Corporate besar"]);
  } else {
    var existing = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(String);
    var norm = existing.map(function(x) { return SALES_normHeader_(x); });
    var add = headers.filter(function(h) { return norm.indexOf(SALES_normHeader_(h)) === -1; });
    if (add.length) sh.getRange(1, existing.length + 1, 1, add.length).setValues([add]);
  }
  sh.getRange(1, 1, 1, sh.getLastColumn()).setFontWeight("bold").setBackground("#dcfce3");
  sh.setFrozenRows(1);
  return { success: true, sheet: sh.getName(), spreadsheet: ss.getName(), rows: sh.getLastRow(), headers: sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0] };
}

function TEST_salesCompanyProfilesDebug() {
  return {
    success: true,
    version: SALES_CFG.VERSION,
    masterSpreadsheet: SALES_masterSs_().getName(),
    masterSpreadsheetId: SALES_masterSs_().getId(),
    profiles: SALES_getCompanyProfiles_()
  };
}


function SALES_hasModuleAccess_(email) {
  return SALES_securityCheck_(email).allowed;
}

function SALES_secAliases_() {
  var arr = (SALES_CFG && SALES_CFG.MODULE_ALIASES) ? SALES_CFG.MODULE_ALIASES.slice() : [];
  ['SALES','PENJUALAN','TRX','TRANSAKSI','MODUL_PENJUALAN'].forEach(function(x){ arr.push(x); });
  return arr;
}
function SALES_secActive_(v) {
  var s = SALES_cleanKey_(v);
  return ['ACTIVE','AKTIF','ON','TRUE','YES','ENABLED'].indexOf(s) !== -1;
}
function SALES_securityCheck_(email) {
  var result = {
    allowed: false,
    reason: '',
    email: SALES_clean_(email).toLowerCase(),
    moduleAliases: SALES_secAliases_(),
    masterUserFound: false,
    rowsChecked: 0,
    matchedUser: null
  };
  if (!result.email) {
    result.reason = 'Email login kosong. Pastikan deploy Web App: Execute as me, akses hanya user login/domain.';
    return result;
  }
  try {
    var sh = SpreadsheetApp.openById(SALES_CFG.MASTER_SPREADSHEET_ID).getSheetByName('Master_User');
    if (!sh || sh.getLastRow() < 2) { result.reason = 'Master_User belum ada atau belum berisi user.'; return result; }
    result.masterUserFound = true;
    var values = sh.getDataRange().getValues();
    var map = SALES_headerMap_(values[0]);
    var cEmail = SALES_col_(map, ['Email','User_Email','User Email','Username'], -1);
    var cRole = SALES_col_(map, ['Role','Roles','User_Role'], -1);
    var cDept = SALES_col_(map, ['Department','Departemen','Dept'], -1);
    var cStatus = SALES_col_(map, ['Status','User_Status'], -1);
    var cAllowed = SALES_col_(map, ['Allowed_Modules','Allowed Modules','Module_Access','Akses_Modul','Akses Modul','Modules','Module','Modul'], -1);
    if (cEmail === -1) { result.reason = 'Header Email tidak ditemukan di Master_User.'; return result; }
    if (cStatus === -1) { result.reason = 'Header Status tidak ditemukan di Master_User.'; return result; }
    var aliases = SALES_secAliases_().map(SALES_cleanKey_);
    for (var r=1; r<values.length; r++) {
      var row = values[r];
      var rowEmail = SALES_clean_(row[cEmail]).toLowerCase();
      if (!rowEmail) continue;
      result.rowsChecked++;
      if (rowEmail !== result.email) continue;
      var statusRaw = row[cStatus];
      var roleRaw = cRole === -1 ? '' : row[cRole];
      var deptRaw = cDept === -1 ? '' : row[cDept];
      var allowedRaw = cAllowed === -1 ? '' : row[cAllowed];
      var role = SALES_cleanKey_(roleRaw), dept = SALES_cleanKey_(deptRaw), allowed = SALES_cleanKey_(allowedRaw);
      result.matchedUser = { row: r+1, status: statusRaw, role: roleRaw, department: deptRaw, allowedModules: allowedRaw };
      if (!SALES_secActive_(statusRaw)) { result.reason = 'User ditemukan tapi Status tidak aktif: ' + statusRaw; return result; }
      if (role.indexOf('ADMIN') !== -1 || dept === 'ADMIN') { result.allowed = true; result.reason = 'ADMIN'; return result; }
      if (allowed === 'ALL' || allowed.indexOf('ALL') !== -1) { result.allowed = true; result.reason = 'Allowed_Modules=ALL'; return result; }
      for (var a=0; a<aliases.length; a++) {
        var key = aliases[a];
        if ((role && role.indexOf(key) !== -1) || (dept && dept.indexOf(key) !== -1) || (allowed && allowed.indexOf(key) !== -1)) {
          result.allowed = true; result.reason = 'Role/Department/Allowed_Modules cocok: ' + key; return result;
        }
      }
      result.reason = 'User aktif, tapi Role/Department/Allowed_Modules belum mengizinkan Penjualan.';
      return result;
    }
    result.reason = 'Email tidak ditemukan di Master_User.';
    return result;
  } catch(e) {
    result.reason = 'Security check error: ' + (e && e.message ? e.message : e);
    return result;
  }
}

function TEST_salesSecurityDebug() {
  return SALES_securityCheck_(SALES_userEmail_());
}

function SALES_logError_(fn, err, payload) {
  try {
    var ss = SALES_masterSs_();
    var sh = ss.getSheetByName("Log_Error");
    if (!sh) {
      sh = ss.insertSheet("Log_Error");
      sh.appendRow(["Timestamp", "Module_Code", "Function_Name", "Error_Message", "Payload_JSON", "User_Email", "Status"]);
    }
    sh.appendRow([new Date(), SALES_CFG.MODULE_CODE, fn, err && err.message ? err.message : String(err), JSON.stringify(payload || {}).slice(0, 5000), SALES_userEmail_(), "NEW"]);
  } catch(e) {}
}

function SALES_clearCache_() {
  CacheService.getScriptCache().removeAll(["SALES_MASTER_ITEMS", "SALES_MASTER_CUSTOMERS"]);
  return "OK";
}

function SETUP_installSalesAdapter() {
  var ss = SALES_salesSs_();
  var sheets = {
    "Data_PO": ["Tanggal", "No PO", "Customer", "Nama Item", "Qty", "Harga", "Total", "Catatan", "Deadline", "Status", "Created_At", "Created_By", "Updated_At", "Updated_By", "Is_Deleted"],
    "Data_SuratJalan": ["Tanggal", "No SJ", "Ref Transaksi", "Customer", "Nama Item", "Qty", "Ekspedisi", "Created_At", "Created_By", "Updated_At", "Updated_By", "Is_Deleted"],
    "Data_Invoice": ["Tanggal", "No Invoice", "Ref PO", "Customer", "Nama Item", "Qty", "Harga", "Total", "Catatan", "Ref SJ", "Ongkos_Kirim", "Total_DP_Terpotong", "Terbayar_Finance", "Created_At", "Created_By", "Updated_At", "Updated_By", "Is_Deleted"],
    "Data_Pembayaran": ["Tanggal", "Customer", "Ref", "Nominal Bayar", "Tipe", "Keterangan", "Created_At", "Created_By", "Is_Deleted"],
    "Master_Ekspedisi": ["Nama", "Status", "Notes"]
  };
  Object.keys(sheets).forEach(function(name) {
    var sh = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sh.getLastRow() === 0) sh.appendRow(sheets[name]);
    else {
      var existing = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(String);
      var add = sheets[name].filter(function(h) { return existing.map(function(x){ return SALES_normHeader_(x); }).indexOf(SALES_normHeader_(h)) === -1; });
      if (add.length) sh.getRange(1, existing.length + 1, 1, add.length).setValues([add]);
    }
    sh.getRange(1, 1, 1, sh.getLastColumn()).setFontWeight("bold").setBackground("#e0f2fe");
    sh.setFrozenRows(1);
  });
  SETUP_installSalesCompanyMaster();
  var stockBridge = null;
  try { stockBridge = SETUP_installSalesStockBridge(); } catch(e) { stockBridge = { success: false, error: e.message }; }
  return { success: true, message: "Sales adapter installed", spreadsheet: ss.getName(), id: ss.getId(), companyMaster: "Master_Company", stockBridge: stockBridge };
}

function TEST_salesAdapterHealth() {
  var salesSs = SALES_salesSs_();
  var masterSs = SALES_masterSs_();
  var out = {
    success: true,
    version: SALES_CFG.VERSION,
    user: SALES_userEmail_(),
    access: SALES_hasModuleAccess_(SALES_userEmail_()),
    salesSpreadsheet: salesSs.getName(),
    salesSpreadsheetId: salesSs.getId(),
    masterSpreadsheet: masterSs.getName(),
    masterSpreadsheetId: masterSs.getId(),
    sheets: {}
  };
  ["Data_PO", "Data_SuratJalan", "Data_Invoice", "Data_Pembayaran", "Master_Item", "Master_Customer", "Master_Company", "Master_Module", "Master_User"].forEach(function(name) {
    var sh = SALES_getSheet_(name);
    out.sheets[name] = sh ? { found: true, source: sh.getParent().getName(), rows: sh.getLastRow(), cols: sh.getLastColumn() } : { found: false };
  });
  try { out.gudangStockMovement = TEST_salesGudangRouting(); } catch(e) { out.gudangStockMovement = { success: false, error: e.message }; }
  return out;
}


function SALES_accountMatch_(accountName, candidates) {
  var key = SALES_cleanKey_(accountName);
  return (candidates || []).some(function(c) { return key.indexOf(SALES_cleanKey_(c)) !== -1; });
}

function SALES_accountLooksCash_(accountName) {
  return SALES_accountMatch_(accountName, ['KAS', 'BANK', 'GIRO', 'SALDO', 'AYAT SILANG', 'POS SEMENTARA']);
}

function SALES_findMapKey_(mapObj, key) {
  var target = SALES_cleanKey_(key);
  for (var k in mapObj) {
    if (SALES_cleanKey_(k) === target) return k;
  }
  return '';
}

function SALES_getFinanceJournalRows_() {
  var out = [];
  try {
    var ss = SALES_financeSs_();
    var sh = ss.getSheetByName('Data_Jurnal');
    if (!sh) return [];
    var values = sh.getDataRange().getValues();
    if (values.length < 2) return [];
    var map = SALES_headerMap_(values[0]);
    function col(names, fb){ return SALES_col_(map, names, fb); }
    var cTgl = col(['Tanggal'], 0), cTipe = col(['Tipe Transaksi'], 1), cRef = col(['No. Referensi','No Referensi','No_Referensi'], 2);
    var cKontak = col(['Nama Kontak','Customer','Nama Customer','Nama Konsumen'], 3), cKet = col(['Keterangan'], 4);
    var cDebit = col(['Akun Debit'], 5), cKredit = col(['Akun Kredit'], 6), cNom = col(['Nominal'], 7), cSrc = col(['Source_Key'], 9);
    for (var i=1; i<values.length; i++) {
      var r = values[i];
      out.push({
        tanggal: r[cTgl],
        tanggalStr: r[cTgl] ? r[cTgl].toString() : '',
        tipe: r[cTipe],
        ref: r[cRef] ? r[cRef].toString().trim() : '',
        kontak: r[cKontak] ? r[cKontak].toString().trim() : '',
        keterangan: r[cKet],
        debit: r[cDebit],
        kredit: r[cKredit],
        nominal: SALES_toNumber_(r[cNom]),
        sourceKey: r[cSrc]
      });
    }
  } catch(e) {}
  return out;
}

function SALES_applyFinanceJournalsToMaps_(mapPO, mapINV, mapPiutang, poToInvMap, refBayarAll) {
  var journals = SALES_getFinanceJournalRows_();
  if (!journals.length) return { applied: 0, journals: 0, dpMasukInfoOnly: 0, dpTerpakai: 0, pembayaranInvoice: 0 };

  // v0.9: kunci utama agar DP tidak double count.
  // DP masuk (Dr Kas/Bank, Cr Uang Muka Penjualan) hanya melekat ke PO.
  // DP terpakai invoice (Dr Uang Muka Penjualan, Cr Piutang) yang mengurangi invoice.
  var dpUsageByInv = {};
  journals.forEach(function(j) {
    if (j.nominal <= 0 || !j.ref) return;
    if (SALES_accountMatch_(j.debit, ['UANG MUKA PENJUALAN', 'UANGMUKAPENJUALAN', 'DP CUSTOMER']) && SALES_accountMatch_(j.kredit, ['PIUTANG'])) {
      var invKey = SALES_cleanKey_(j.ref);
      dpUsageByInv[invKey] = (dpUsageByInv[invKey] || 0) + j.nominal;
    }
  });

  function getInvoiceNoFromPoRef_(poRef) {
    if (!poRef) return '';
    var raw = String(poRef || '').trim();
    return poToInvMap[SALES_cleanKey_(raw)] || poToInvMap[raw.toUpperCase()] || poToInvMap[raw] || '';
  }

  function ensurePiutang(cust){
    cust = cust || '(Tanpa Nama)';
    if(!mapPiutang[cust]) mapPiutang[cust] = { cust: cust, tTagihan: 0, tBayar: 0, details: {}, ledger: [] };
    if(!mapPiutang[cust].ledger) mapPiutang[cust].ledger = [];
    return mapPiutang[cust];
  }

  function addLedgerInfo(cust, ref, ket, tglRaw, nominal) {
    var mc = ensurePiutang(cust);
    mc.ledger.push({ no: ref, tagihan: 0, bayar: 0, nominalInfo: nominal || 0, ket: ket, tglRaw: tglRaw || '' });
  }

  function applyBayar(cust, ref, nominal, ket, tglRaw){
    var mc = ensurePiutang(cust);
    mc.tBayar += nominal;
    var dKey = SALES_findMapKey_(mc.details, ref);
    if(dKey && mc.details[dKey]) mc.details[dKey].bayar += nominal;
    else mc.details[ref + '_PAY_FIN_' + Utilities.getUuid().slice(0,8)] = { no: ref, tagihan: 0, bayar: nominal, ket: ket, tglRaw: tglRaw || '' };
    mc.ledger.push({ no: ref, tagihan: 0, bayar: nominal, ket: ket, tglRaw: tglRaw || '' });
  }

  var applied = 0, dpMasukInfoOnly = 0, dpTerpakai = 0, pembayaranInvoice = 0, dpFallbackInvoice = 0;
  journals.forEach(function(j) {
    if (j.nominal <= 0 || !j.ref) return;
    var poKey = SALES_findMapKey_(mapPO, j.ref);
    var invKey = SALES_findMapKey_(mapINV, j.ref);
    var invFromPo = getInvoiceNoFromPoRef_(j.ref);
    var invFromPoKey = invFromPo ? SALES_findMapKey_(mapINV, invFromPo) : '';

    var isDpMasuk = SALES_accountMatch_(j.kredit, ['UANG MUKA PENJUALAN', 'UANGMUKAPENJUALAN', 'DP CUSTOMER']);
    var isDpTerpakai = SALES_accountMatch_(j.debit, ['UANG MUKA PENJUALAN', 'UANGMUKAPENJUALAN', 'DP CUSTOMER']) && SALES_accountMatch_(j.kredit, ['PIUTANG']);
    var isInvoiceCashPayment = SALES_accountLooksCash_(j.debit) && SALES_accountMatch_(j.kredit, ['PIUTANG']);

    if (isDpMasuk) {
      if (poKey) {
        mapPO[poKey].totalDP += j.nominal;
        if (!refBayarAll.includes(poKey)) refBayarAll.push(poKey);

        // Kalau PO sudah jadi invoice, DP masuk TIDAK dihitung sebagai pembayaran invoice.
        // Invoice hanya berkurang dari jurnal PEMA KAIAN_DP_INVOICE.
        // Fallback hanya dipakai kalau Finance belum membuat jurnal pemakaian DP.
        if (invFromPoKey) {
          var invClean = SALES_cleanKey_(invFromPoKey);
          if (!dpUsageByInv[invClean]) {
            mapINV[invFromPoKey].totalDP += j.nominal;
            applyBayar(mapINV[invFromPoKey].cust || j.kontak || mapPO[poKey].cust, invFromPoKey, j.nominal, 'DP Terpakai Finance (fallback dari PO)', j.tanggalStr);
            dpFallbackInvoice++;
          } else {
            addLedgerInfo(mapPO[poKey].cust || j.kontak, poKey, 'DP Masuk PO - sudah dipakai di invoice', j.tanggalStr, j.nominal);
            dpMasukInfoOnly++;
          }
        } else {
          // PO belum invoice: boleh tampil sebagai DP PO aktif.
          applyBayar(mapPO[poKey].cust || j.kontak, poKey, j.nominal, 'DP Masuk Finance', j.tanggalStr);
        }
        applied++;
      }
      return;
    }

    if (isDpTerpakai) {
      var dInvKey = invKey || invFromPoKey;
      if (dInvKey) {
        mapINV[dInvKey].totalDP += j.nominal;
        applyBayar(mapINV[dInvKey].cust || j.kontak, dInvKey, j.nominal, 'DP Terpakai Finance', j.tanggalStr);
        applied++;
        dpTerpakai++;
      }
      return;
    }

    if (isInvoiceCashPayment) {
      var pInvKey = invKey || invFromPoKey;
      if (pInvKey) {
        applyBayar(mapINV[pInvKey].cust || j.kontak, pInvKey, j.nominal, 'Pembayaran Finance', j.tanggalStr);
        applied++;
        pembayaranInvoice++;
      }
    }
  });
  return { applied: applied, journals: journals.length, dpMasukInfoOnly: dpMasukInfoOnly, dpTerpakai: dpTerpakai, pembayaranInvoice: pembayaranInvoice, dpFallbackInvoice: dpFallbackInvoice };
}


// ================= FLOW STYLE UI AUTH BRIDGE =================
function SALES_requirePassport_(emailOp, pasporOp) {
  emailOp = SALES_clean_(emailOp || '').toLowerCase();
  pasporOp = SALES_clean_(pasporOp || '');
  if (!emailOp || !pasporOp) {
    throw new Error('Sesi Penjualan tidak lengkap. Masuk ulang dari Portal.');
  }
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth || !auth.allowed) {
    throw new Error('Akses Penjualan ditolak: ' + (auth && auth.reason ? auth.reason : 'UNKNOWN'));
  }
  var authEmail = SALES_clean_(auth.email || '').toLowerCase();
  if (authEmail && emailOp && authEmail !== emailOp) {
    throw new Error('Passport tidak cocok dengan email aktif. Masuk ulang dari Portal.');
  }
  return auth;
}

function SALES_touchMutation_(fnName) {
  try { ERP_mutation_(fnName || 'SALES_MUTATION'); } catch(e) {}
}

// ================= 1. LOAD DATA AWAL =================
function getInitData(startStr, endStr, custFilter, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  try {
    var pItem = getSheetWithMap("Master_Item"), pCust = getSheetWithMap("Master_Customer");
    var pEks = getSheetWithMap("Master_Ekspedisi"), pModul = getSheetWithMap("Master_Modul");
    var pPO = getSheetWithMap("Data_PO"), pSJ = getSheetWithMap("Data_SuratJalan");
    var pINV = getSheetWithMap("Data_Invoice"), pPay = getSheetWithMap("Data_Pembayaran");

    // --- SETUP PERUSAHAAN DARI MASTER DATABASE ---
    var setupData = SALES_getSetupData_();
    var companyProfiles = SALES_getCompanyProfiles_();
    // ----------------------------------------

    var startNum = null, endNum = null;
    if(startStr) { 
        var pStart = startStr.split('-'); 
        startNum = new Date(pStart[0], pStart[1] - 1, pStart[2], 0, 0, 0, 0).getTime(); 
    }
    if(endStr) { 
        var pEnd = endStr.split('-'); 
        endNum = new Date(pEnd[0], pEnd[1] - 1, pEnd[2], 23, 59, 59, 999).getTime(); 
    }

    var items = [], customers = [], eks = [], links = [], mapCustDetail = {};
    
    if(pItem) { 
       var cKat = pItem.c(["kategori"], 4);
       var cSub = pItem.c(["sub kategori", "sub-kategori", "sub"], 5);
       var cNm = pItem.c(["nama item", "nama", "item", "produk"], 2);

       pItem.rows.forEach(r => { 
          if(r[cNm]) {
             var itm = r[cNm].toString().trim();
             if(itm !== "Biaya Ongkos Kirim" && itm !== "") {
                var subKat = r[cSub] ? r[cSub].toString().trim() : "Umum";
                // Pastikan tidak ada duplikat masuk
                if(!items.some(x => x.nama === itm)) {
                    items.push({ sub: subKat, nama: itm }); 
                }
             }
          }
       });
    }
    if(pEks) { pEks.rows.forEach(r => { if(r[0]) eks.push(r[0].toString().trim()); }); }
    if(pModul) {
      try {
        links = getModulLinks(__auth.email, pasporOp || (__auth && __auth.passportId) || "");
      } catch(eLinks) {
        links = [];
      }
    }
    if(pCust) {
        var ccNm = pCust.c(["nama"], 0), ccKnt = pCust.c(["kontak"], 1), ccAlm = pCust.c(["alamat"], 2);
        pCust.rows.forEach(r => {
            if(r[ccNm]) {
                var cName = r[ccNm].toString().trim();
                customers.push({ nama: cName }); 
                mapCustDetail[cName] = { kontak: r[ccKnt]||"-", alamat: r[ccAlm]||"-" };
            }
        });
    }

    var mapPO = {}, mapSJ = {}, mapINV = {}, mapPiutang = {};
    var poAktifCustomerMap = {}, allDocCustomerMap = {}, allSjCustomerMap = {};
    var refBayarAll = [];

    // --- MAPPING PO ---
    if(pPO) {
        var cPoTgl = pPO.c(["tanggal", "tgl"], 0), cPoNo = pPO.c(["no po", "nomor po"], 1), cPoCust = pPO.c(["customer", "pelanggan"], 2), cPoItem = pPO.c(["nama item", "item"], 3), cPoQty = pPO.c(["qty", "jumlah"], 4), cPoHrg = pPO.c(["harga", "harga satuan"], 5), cPoTot = pPO.c(["total"], 6), cPoDead = pPO.c(["deadline", "batas waktu"], 8), cPoStat = pPO.c(["status"], 9);
        pPO.rows.forEach(row => {
          var n = row[cPoNo]; if(!n) return; n = n.toString().trim();
          var c = row[cPoCust] ? row[cPoCust].toString().trim() : "";
          var tglVal = row[cPoTgl]; var tglNum = new Date(tglVal).getTime() || 0;
          var dead = row[cPoDead] ? formatTgl(row[cPoDead]) : "-";
          var stat = row[cPoStat] ? row[cPoStat].toString() : "Aktif";

          if(!mapPO[n]) mapPO[n] = { no: n, tglNum: tglNum, tgl: formatTgl(tglVal), deadline: dead, cust: c, total: 0, status: stat, items: [], totalDP: 0 };
          var itemTot = SALES_toNumber_(row[cPoTot]);
          mapPO[n].total += itemTot;
          mapPO[n].items.push({ nama: row[cPoItem], qty: row[cPoQty], harga: SALES_toNumber_(row[cPoHrg]), total: itemTot });

          if(!refBayarAll.includes(n)) refBayarAll.push(n);
          if(!allDocCustomerMap[c]) allDocCustomerMap[c] = [];
          if(!allDocCustomerMap[c].includes(n)) allDocCustomerMap[c].push(n);

          if(stat !== 'Selesai') {
            if(!poAktifCustomerMap[c]) poAktifCustomerMap[c] = [];
            if(!poAktifCustomerMap[c].includes(n)) poAktifCustomerMap[c].push(n);
            
            var amanTglPO = tglVal ? tglVal.toString() : "";
            if(!mapPiutang[c]) mapPiutang[c] = { cust: c, tTagihan: 0, tBayar: 0, details: {}, ledger: [] };
            if(!mapPiutang[c].details[n]) mapPiutang[c].details[n] = { no: n, tagihan: 0, bayar: 0, ket: "Proforma (PO Aktif)", tglRaw: amanTglPO };
            mapPiutang[c].details[n].tagihan += itemTot;
            mapPiutang[c].tTagihan += itemTot;
          }
        });
    }

    // --- MAPPING SJ ---
    if(pSJ) {
        var cSjTgl = pSJ.c(["tanggal", "tgl"], 0), cSjNo = pSJ.c(["no sj", "nomor sj"], 1), cSjRef = pSJ.c(["ref transaksi", "referensi"], 2), cSjCust = pSJ.c(["customer", "pelanggan"], 3), cSjItem = pSJ.c(["nama item", "item"], 4), cSjQty = pSJ.c(["qty", "jumlah"], 5), cSjEks = pSJ.c(["ekspedisi", "kurir"], 6);
        pSJ.rows.forEach(row => {
          var ns = row[cSjNo]; if(!ns) return; ns = ns.toString().trim();
          var tglVal = row[cSjTgl]; var tglNum = new Date(tglVal).getTime() || 0;
          var cust = row[cSjCust].toString();
          if(!mapSJ[ns]) mapSJ[ns] = { no: ns, tglNum: tglNum, tgl: formatTgl(tglVal), ref: row[cSjRef]?row[cSjRef].toString():"-", cust: cust, eks: row[cSjEks]?row[cSjEks].toString():"-", items: [], totBarang: 0 };
          var qtySJ = SALES_toNumber_(row[cSjQty]);
          mapSJ[ns].totBarang += qtySJ;
          mapSJ[ns].items.push({ nama: row[cSjItem], qty: qtySJ });
          if(!allSjCustomerMap[cust]) allSjCustomerMap[cust] = [];
          if(!allSjCustomerMap[cust].includes(ns)) allSjCustomerMap[cust].push(ns);
        });
    }

    // --- MAPPING INVOICE ---
    var poToInvMap = {};
    if(pINV) {
        var cInvTgl = pINV.c(["tanggal", "tgl"], 0), cInvNo = pINV.c(["no invoice", "nomor invoice"], 1), cInvRef = pINV.c(["ref po", "referensi po"], 2), cInvCust = pINV.c(["customer", "pelanggan"], 3), cInvItem = pINV.c(["nama item", "item"], 4), cInvQty = pINV.c(["qty", "jumlah"], 5), cInvHrg = pINV.c(["harga"], 6), cInvTot = pINV.c(["total"], 7), cInvRefSj = pINV.c(["ref sj", "referensi sj"], 9);
        pINV.rows.forEach(row => {
          var ni = row[cInvNo]; if(!ni) return; ni = ni.toString().trim();
          var ci = row[cInvCust] ? row[cInvCust].toString().trim() : "";
          var tot = SALES_toNumber_(row[cInvTot]); 
          var tglVal = row[cInvTgl]; var tglNum = new Date(tglVal).getTime() || 0;
          var refPO = row[cInvRef]?row[cInvRef].toString():"-";
          if(!mapINV[ni]) mapINV[ni] = { no: ni, tglNum: tglNum, tgl: formatTgl(tglVal), ref: refPO, refSJ: row[cInvRefSj]?row[cInvRefSj].toString():"", cust: ci, total: 0, items: [], totalDP: 0 };
          mapINV[ni].total += tot; mapINV[ni].items.push({ nama: row[cInvItem], qty: row[cInvQty], harga: SALES_toNumber_(row[cInvHrg]), total: tot });

          if(!refBayarAll.includes(ni)) refBayarAll.push(ni);
          if(ni && refPO && refPO !== "-") {
            poToInvMap[String(refPO).trim().toUpperCase()] = ni;
            poToInvMap[SALES_cleanKey_(refPO)] = ni;
          }
          
          var amanTglINV = tglVal ? tglVal.toString() : "";
          if(!mapPiutang[ci]) mapPiutang[ci] = { cust: ci, tTagihan: 0, tBayar: 0, details: {}, ledger: [] };
          if(!mapPiutang[ci].details[ni]) mapPiutang[ci].details[ni] = { no: ni, tagihan: 0, bayar: 0, ket: "Invoice", tglRaw: amanTglINV };
          mapPiutang[ci].tTagihan += tot;
          mapPiutang[ci].details[ni].tagihan += tot;
        });
    }

    // --- MAPPING PEMBAYARAN & DP ---
    if(pPay) {
        var cPayTgl = pPay.c(["tanggal", "tgl"], 0), cPayRef = pPay.c(["no dokumen", "ref"], 1), cPayNominal = pPay.c(["nominal", "dibayar"], 2);
        pPay.rows.forEach(row => {
          var originalPayRef = row[cPayRef] ? row[cPayRef].toString().trim().toUpperCase() : "";
          if(!originalPayRef) return; 
          var rPay = poToInvMap[originalPayRef] ? poToInvMap[originalPayRef] : originalPayRef;
          var nom = parseFloat(row[cPayNominal])||0;
          var tglMurniStr = row[cPayTgl] ? row[cPayTgl].toString() : "";
          
          if(mapPO[originalPayRef]) mapPO[originalPayRef].totalDP += nom;
          if(mapINV[rPay]) mapINV[rPay].totalDP += nom;

          var custFound = "";
          for(var mk in mapINV) { if(mk.toUpperCase() === rPay) { custFound = mapINV[mk].cust; break; } }
          if(!custFound) { for(var mk in mapPO) { if(mk.toUpperCase() === rPay) { custFound = mapPO[mk].cust; break; } } }
          
          if(custFound) {
            if(!mapPiutang[custFound]) mapPiutang[custFound] = { cust: custFound, tTagihan: 0, tBayar: 0, details: {}, ledger: [] };
            mapPiutang[custFound].tBayar += nom;
            
            var originalRef = "";
            for(var dn in mapPiutang[custFound].details) { if(dn.toUpperCase() === rPay) { originalRef = dn; break; } }
            
            if(originalRef && mapPiutang[custFound].details[originalRef]) {
              mapPiutang[custFound].details[originalRef].bayar += nom;
            } else { 
              mapPiutang[custFound].details[rPay + "_PAY_" + Math.random()] = { no: originalPayRef, tagihan: 0, bayar: nom, ket: "Pembayaran", tglRaw: tglMurniStr };
            }

            if(!mapPiutang[custFound].ledger) mapPiutang[custFound].ledger = [];
            mapPiutang[custFound].ledger.push({ no: originalPayRef, tagihan: 0, bayar: nom, ket: "Pembayaran Masuk", tglRaw: tglMurniStr });
          }
        });
    }

    // --- MAPPING PEMBAYARAN & DP DARI FINANCE DATA_JURNAL ---
    var financeSyncInfo = SALES_applyFinanceJournalsToMaps_(mapPO, mapINV, mapPiutang, poToInvMap, refBayarAll);

    var invoicedSjList = [];
    for(var invRow in mapINV) {
        var refSjInv = mapINV[invRow].refSJ.toUpperCase();
        if(refSjInv) { refSjInv.split(",").forEach(s => { var cleanSj = s.trim(); if(cleanSj && !invoicedSjList.includes(cleanSj)) invoicedSjList.push(cleanSj); }); }
    }

    // === SORTING BARU DENGAN PRIORITAS STATUS ===

    var resSJ = Object.values(mapSJ)
        .filter(m => (!startNum || m.tglNum >= startNum) && (!endNum || m.tglNum <= endNum) && (!custFilter || m.cust.toLowerCase() === custFilter.toLowerCase()))
        .map(m => { 
            m.isDitagih = invoicedSjList.includes(m.no.toUpperCase());
            m.badgeTagih = m.isDitagih ? '<span class="badge bg-success">✅ Sudah Ditagih</span>' : '<span class="badge bg-danger">🔴 Belum Ditagih</span>'; 
            return m; 
        })
        .sort((a,b) => {
            var tagihA = a.isDitagih ? 1 : 0;
            var tagihB = b.isDitagih ? 1 : 0;
            if(tagihA !== tagihB) return tagihA - tagihB; // Belum (0) di atas Ditagih (1)
            return b.tglNum - a.tglNum; // Tanggal terbaru di atas
        });

    var resINV = Object.values(mapINV)
        .filter(m => (!startNum || m.tglNum >= startNum) && (!endNum || m.tglNum <= endNum) && (!custFilter || m.cust.toLowerCase() === custFilter.toLowerCase()))
        .map(m => {
            var invKey = m.no.toUpperCase(); var byr = 0;
            if(mapPiutang[m.cust] && mapPiutang[m.cust].details) { 
                for(var dk in mapPiutang[m.cust].details) { 
                    var upperDk = dk.toUpperCase();
                    if(upperDk === invKey || upperDk.startsWith(invKey + "_PAY_")) {
                        byr += mapPiutang[m.cust].details[dk].bayar; 
                    }
                } 
            }
            var sisa = m.total - byr;
            m.isLunas = sisa <= 0;
            var statColor = m.isLunas ? "bg-success" : (byr > 0 ? "bg-warning text-dark" : "bg-danger");
            m.totalRp = formatRupiah(m.total); 
            m.badgeHtml = `<span class="badge ${statColor}">${m.isLunas ? "Lunas" : (byr > 0 ? "Sebagian" : "Belum Bayar")}</span>`; 
            return m;
        })
        .sort((a,b) => {
            var lunasA = a.isLunas ? 1 : 0;
            var lunasB = b.isLunas ? 1 : 0;
            if(lunasA !== lunasB) return lunasA - lunasB; // Belum (0) di atas Lunas (1)
            return b.tglNum - a.tglNum;
        });

    var resPO = Object.values(mapPO)
        .filter(m => (!startNum || m.tglNum >= startNum) && (!endNum || m.tglNum <= endNum) && (!custFilter || m.cust.toLowerCase() === custFilter.toLowerCase()))
        .map(m => { m.totalRp = formatRupiah(m.total); return m; })
        .sort((a,b) => {
            var statA = (a.status === 'Selesai') ? 1 : 0;
            var statB = (b.status === 'Selesai') ? 1 : 0;
            if(statA !== statB) return statA - statB; // Aktif (0) di atas Selesai (1)
            return b.tglNum - a.tglNum;
        });
    
    // RAKIT DUAL PIUTANG
    var resPiutang = [];
    for(var cp in mapPiutang) {
      if(custFilter && cp.toLowerCase() !== custFilter.toLowerCase()) continue;
      var mc = mapPiutang[cp];
      var detWeb = [];
      var detPdf = [];

      for(var d in mc.details) {
        var md = mc.details[d];
        var sisa = (md.ket === "Invoice" || md.ket === "Proforma (PO Aktif)") ? md.tagihan : 0;
        detWeb.push({ no: md.no, ket: md.ket, tagihanRaw: md.tagihan, bayarRaw: md.bayar, tagihan: md.tagihan>0?formatRupiah(md.tagihan):"-", bayar: md.bayar>0?formatRupiah(md.bayar):"-", sisa: sisa>0?formatRupiah(sisa):"-", tglRaw: md.tglRaw, tglStr: md.tglRaw ? formatTgl(md.tglRaw) : "-" });
        if(md.ket === "Invoice" || md.ket === "Proforma (PO Aktif)") {
            detPdf.push({ no: md.no, ket: md.ket, tagihanRaw: md.tagihan, bayarRaw: 0, tglRaw: md.tglRaw, tglStr: md.tglRaw ? formatTgl(md.tglRaw) : "-" });
        }
      }
      
      if(mc.ledger) {
          mc.ledger.forEach(l => {
              detPdf.push({ no: l.no, ket: l.ket, tagihanRaw: 0, bayarRaw: l.bayar, tglRaw: l.tglRaw, tglStr: l.tglRaw ? formatTgl(l.tglRaw) : "-" });
          });
      }

      detWeb.sort((a,b) => new Date(a.tglRaw).getTime() - new Date(b.tglRaw).getTime());
      detPdf.sort((a,b) => new Date(a.tglRaw).getTime() - new Date(b.tglRaw).getTime());
      
      var tSisa = mc.tTagihan - mc.tBayar;
      if(mc.tTagihan > 0 || mc.tBayar > 0) {
          resPiutang.push({ 
              cust: mc.cust, tagihanStr: formatRupiah(mc.tTagihan), bayarStr: formatRupiah(mc.tBayar), sisaStr: formatRupiah(tSisa), tagihanRaw: mc.tTagihan, bayarRaw: mc.tBayar, 
              details: detWeb,       
              detailsPdf: detPdf     
          });
      }
    }

    // PASSING DATA SETUP KE FRONTEND
    return { error: null, setup: setupData, companyProfiles: companyProfiles, masterItems: items, ekspedisi: [...new Set(eks)], customers: customers, dataPO: resPO, dataSJ: resSJ, dataINV: resINV, dataPiutang: resPiutang.sort((a,b) => a.cust.localeCompare(b.cust)), poAktifCustomerMap: poAktifCustomerMap, allDocCustomerMap: allDocCustomerMap, allSjCustomerMap: allSjCustomerMap, listRefBayar: refBayarAll.reverse(), modulLinks: links, mapCustDetail: mapCustDetail, financeSyncInfo: financeSyncInfo, user: { email: __auth.email || '', name: __auth.displayName || __auth.email || '' }, passport: pasporOp || (__auth && __auth.passportId) || '' };
  } catch(e) { return { error: e.message }; }
}

// ================= FUNGSI MASTER DATA DENGAN LOCK - v0.2 HEADER BASED =================
function SALES_getOrCreateMasterSheet_(sheetName, headers) {
  var ss = SALES_masterSs_();
  var sh = ss.getSheetByName(sheetName);
  if (!sh) {
    sh = ss.insertSheet(sheetName);
    sh.appendRow(headers);
    sh.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#dcfce3");
    sh.setFrozenRows(1);
  } else if (headers && headers.length) {
    var existing = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0];
    var map = SALES_headerMap_(existing);
    var add = headers.filter(function(h) { return SALES_findColForWrite_(map, [h]) === -1; });
    if (add.length) sh.getRange(1, existing.length + 1, 1, add.length).setValues([add]);
  }
  return sh;
}

function SALES_findColForWrite_(map, aliases) {
  aliases = Array.isArray(aliases) ? aliases : [aliases];
  for (var i = 0; i < aliases.length; i++) {
    var expanded = SALES_expandHeaderAliases_(aliases[i]);
    for (var j = 0; j < expanded.length; j++) {
      if (map[expanded[j]] !== undefined) return map[expanded[j]];
    }
  }
  return -1;
}

function SALES_setByAliases_(row, map, aliases, value) {
  var idx = SALES_findColForWrite_(map, aliases);
  if (idx !== -1) row[idx] = value;
  return idx;
}

function SALES_makeId_(prefix) {
  return prefix + "-" + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMddHHmmss") + "-" + Math.floor(Math.random() * 1000);
}

function SALES_duplicateExists_(sh, aliases, value) {
  value = SALES_clean_(value).toLowerCase();
  if (!value || sh.getLastRow() < 2) return false;
  var values = sh.getDataRange().getValues();
  var map = SALES_headerMap_(values[0]);
  var c = SALES_findColForWrite_(map, aliases);
  if (c === -1) return false;
  for (var r = 1; r < values.length; r++) {
    if (SALES_clean_(values[r][c]).toLowerCase() === value) return true;
  }
  return false;
}

function SALES_appendMasterRow_(sh, patch) {
  var headers = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0];
  var map = SALES_headerMap_(headers);
  var row = new Array(headers.length).fill("");
  Object.keys(patch).forEach(function(key) {
    SALES_setByAliases_(row, map, patch[key].aliases, patch[key].value);
  });
  sh.getRange(sh.getLastRow() + 1, 1, 1, row.length).setValues([row]);
}

function tambahMasterCustomer(d, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch(e) { return "ERROR: Server sibuk, coba lagi."; }

  try {
    d = d || {};
    var nama = sanitizeStr(d.nama || d.customer || "");
    var kontak = sanitizeStr(d.kontak || d.phone || "");
    var alamat = sanitizeStr(d.alamat || d.address || "");
    if (!nama) return "ERROR: Nama customer wajib diisi.";

    var sh = SALES_getOrCreateMasterSheet_("Master_Customer", [
      "Customer_ID", "Customer_Name", "Contact", "Address", "Customer_Code", "Status", "Updated_At", "Updated_By", "Notes"
    ]);

    if (SALES_duplicateExists_(sh, ["Customer_Name", "Nama Customer", "Nama", "Customer"], nama)) {
      return "ERROR: Customer sudah ada di Master_Customer.";
    }

    var code = nama.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 6) || "CUST";
    SALES_appendMasterRow_(sh, {
      id:      { aliases: ["Customer_ID", "ID", "Cust_ID"], value: SALES_makeId_("CUST") },
      name:    { aliases: ["Customer_Name", "Nama Customer", "Nama", "Customer", "Nama_Konsumen"], value: nama },
      contact: { aliases: ["Contact", "Kontak", "Phone", "No HP", "WA", "WhatsApp", "Telepon"], value: kontak },
      address: { aliases: ["Address", "Alamat", "Alamat Lengkap"], value: alamat },
      code:    { aliases: ["Customer_Code", "Kode Customer", "Kode", "Code"], value: code },
      status:  { aliases: ["Status"], value: "ACTIVE" },
      at:      { aliases: ["Updated_At", "Created_At", "Timestamp"], value: new Date() },
      by:      { aliases: ["Updated_By", "Created_By", "Operator"], value: __auth.email },
      notes:   { aliases: ["Notes", "Catatan", "Keterangan"], value: "Input dari Modul Penjualan" }
    });

    SALES_clearCache_();
    return "OK";
  } catch(e) {
    SALES_logError_("tambahMasterCustomer", e, d);
    return "ERROR: " + e.message;
  } finally { lock.releaseLock(); }
}

function tambahMasterItem(d, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch(e) { return "ERROR: Server sibuk, coba lagi."; }

  try {
    d = d || {};
    var kategori = sanitizeStr(d.kategori || d.category || "");
    var subKategori = sanitizeStr(d.subKategori || d.sub_kategori || d.subCategory || "");
    var nama = sanitizeStr(d.nama || d.namaItem || d.itemName || "");
    if (!kategori) return "ERROR: Kategori wajib diisi.";
    if (!nama) return "ERROR: Nama item wajib diisi.";

    var sh = SALES_getOrCreateMasterSheet_("Master_Item", [
      "Item_ID", "Item_Code", "Item_Name", "Category", "Sub_Category", "Item_Type", "Unit", "Harga_Jual", "Status", "Updated_At", "Updated_By", "Notes"
    ]);

    if (SALES_duplicateExists_(sh, ["Item_Name", "Nama Item", "Nama Barang", "Nama Produk", "Item", "Produk", "Nama"], nama)) {
      return "ERROR: Item sudah ada di Master_Item.";
    }

    var itemCode = nama.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 12) || "ITEM";
    SALES_appendMasterRow_(sh, {
      id:     { aliases: ["Item_ID", "ID", "ID Item"], value: SALES_makeId_("ITEM") },
      code:   { aliases: ["Item_Code", "Kode Item", "SKU", "Kode", "Code"], value: itemCode },
      name:   { aliases: ["Item_Name", "Nama Item", "Nama Barang", "Nama Produk", "Internal_Item_Name", "Item", "Produk", "Nama"], value: nama },
      cat:    { aliases: ["Category", "Kategori"], value: kategori },
      sub:    { aliases: ["Sub_Category", "Sub Kategori", "Sub-Kategori", "Sub", "Subkategori"], value: subKategori || "Umum" },
      type:   { aliases: ["Item_Type", "Item Type", "Tipe_Item", "Tipe Item"], value: "BARANG_JADI" },
      unit:   { aliases: ["Unit", "Satuan"], value: "PCS" },
      price:  { aliases: ["Harga_Jual", "Harga Jual", "Harga", "Price"], value: SALES_toNumber_(d.harga || 0) },
      status: { aliases: ["Status"], value: "ACTIVE" },
      at:     { aliases: ["Updated_At", "Created_At", "Timestamp"], value: new Date() },
      by:     { aliases: ["Updated_By", "Created_By", "Operator"], value: __auth.email },
      notes:  { aliases: ["Notes", "Catatan", "Keterangan"], value: "Input dari Modul Penjualan" }
    });

    SALES_clearCache_();
    return "OK";
  } catch(e) {
    SALES_logError_("tambahMasterItem", e, d);
    return "ERROR: " + e.message;
  } finally { lock.releaseLock(); }
}

function TEST_salesItemTypeWriteDebug() {
  var sh = SALES_getOrCreateMasterSheet_("Master_Item", [
    "Item_ID", "Item_Code", "Item_Name", "Category", "Sub_Category", "Item_Type", "Unit", "Harga_Jual", "Status", "Updated_At", "Updated_By", "Notes"
  ]);
  var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var map = SALES_headerMap_(headers);
  var cType = SALES_findColForWrite_(map, ["Item_Type", "Item Type", "Tipe_Item", "Tipe Item"]);
  return {
    success: cType !== -1,
    version: SALES_CFG.VERSION,
    masterItemSheet: sh.getName(),
    itemTypeHeaderFound: cType !== -1,
    itemTypeColumnNumber: cType === -1 ? null : cType + 1,
    headers: headers
  };
}

function TEST_salesMasterWriteDebug() {
  var masterSs = SALES_masterSs_();
  var c = masterSs.getSheetByName("Master_Customer");
  var i = masterSs.getSheetByName("Master_Item");
  return {
    success: true,
    masterSpreadsheet: masterSs.getName(),
    masterSpreadsheetId: masterSs.getId(),
    customer: c ? { found: true, rows: c.getLastRow(), headers: c.getRange(1, 1, 1, c.getLastColumn()).getValues()[0] } : { found: false },
    item: i ? { found: true, rows: i.getLastRow(), headers: i.getRange(1, 1, 1, i.getLastColumn()).getValues()[0] } : { found: false }
  };
}

// ================= FUNGSI TARIK REFERENSI (OPTIMASI DINAMIS) =================
function getItemsByRef(ref, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  try {
    var pPO = getSheetWithMap("Data_PO"), pSJ = getSheetWithMap("Data_SuratJalan"), pPay = getSheetWithMap("Data_Pembayaran");
    var res = { ongkir: 0, diskon: 0, ppn: 0, dp: 0, sjList: [], items: [] };
    var mapKirim = {};
    
    if(pSJ) {
        var cSjNo = pSJ.c(["no sj"], 1), cSjRef = pSJ.c(["ref transaksi"], 2), cSjItem = pSJ.c(["nama item"], 4), cSjQty = pSJ.c(["qty"], 5);
        pSJ.rows.forEach(r => {
            if(r[cSjRef].toString().trim().toUpperCase() === ref.toString().trim().toUpperCase()) {
                var noSj = r[cSjNo].toString().trim();
                if(!res.sjList.includes(noSj)) res.sjList.push(noSj);
                var itemNm = r[cSjItem].toString().trim();
                if(!mapKirim[itemNm]) mapKirim[itemNm] = 0;
                mapKirim[itemNm] += SALES_toNumber_(r[cSjQty]);
            }
        });
    }

    if(pPay) {
        var cPyRef = pPay.c(["no dokumen", "ref"], 1), cPyNom = pPay.c(["nominal"], 2);
        pPay.rows.forEach(r => {
            if(r[cPyRef].toString().trim().toUpperCase() === ref.toString().trim().toUpperCase()) {
                res.dp += parseFloat(r[cPyNom]) || 0;
            }
        });
    }

    if(pPO) {
        var cPoNo = pPO.c(["no po"], 1), cPoItem = pPO.c(["nama item"], 3), cPoQty = pPO.c(["qty"], 4), cPoHrg = pPO.c(["harga"], 5), cPoTot = pPO.c(["total"], 6);
        pPO.rows.forEach(r => {
           if(r[cPoNo].toString().trim().toUpperCase() === ref.toString().trim().toUpperCase()) {
               var nm = r[cPoItem].toString().trim();
               if(nm === "Biaya Ongkos Kirim") res.ongkir = Math.abs(parseFloat(r[cPoTot]) || 0);
               else if(nm === "Potongan Diskon") res.diskon = Math.abs(parseFloat(r[cPoTot]) || 0);
               else if(nm.startsWith("Pajak PPN")) {
                   var match = nm.match(/\d+/);
                   if(match) res.ppn = parseInt(match[0]);
               } else {
                   res.items.push({ nama: nm, qty: r[cPoQty], harga: r[cPoHrg], qtyKirim: mapKirim[nm] || 0 });
               }
           }
        });
    }
    return res;
  } catch(e) { return { ongkir: 0, diskon: 0, ppn: 0, dp: 0, sjList: [], items: [] }; }
}

function getItemsFromSJ(refSJ, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  try {
    var pSJ = getSheetWithMap("Data_SuratJalan");
    var res = [];
    if(pSJ) {
        var cSjNo = pSJ.c(["no sj"], 1), cSjItem = pSJ.c(["nama item"], 4), cSjQty = pSJ.c(["qty"], 5);
        pSJ.rows.forEach(r => {
            if(r[cSjNo].toString().trim() === refSJ.toString().trim()) {
                res.push({ nama: r[cSjItem].toString().trim(), qty: r[cSjQty] });
            }
        });
    }
    return res;
  } catch(e) { return []; }
}

function getSisaItemKirim(ref, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  try {
    var pPO = getSheetWithMap("Data_PO"), pSJ = getSheetWithMap("Data_SuratJalan");
    var mapTarget = {};
    if(pPO) {
        var cPoNo = pPO.c(["no po"], 1), cPoItem = pPO.c(["nama item"], 3), cPoQty = pPO.c(["qty"], 4);
        pPO.rows.forEach(r => {
            var n = r[cPoItem].toString();
            if(n === "Biaya Ongkos Kirim" || n === "Potongan Diskon" || n.startsWith("Pajak PPN")) return;
            if(r[cPoNo].toString().trim() === ref) { 
                if(!mapTarget[n]) mapTarget[n]=0; mapTarget[n] += parseFloat(r[cPoQty])||0; 
            }
        });
    }
    var mapKirim = {};
    if(pSJ) {
        var cSjRef = pSJ.c(["ref transaksi"], 2), cSjItem = pSJ.c(["nama item"], 4), cSjQty = pSJ.c(["qty"], 5);
        pSJ.rows.forEach(r => {
            if(r[cSjRef].toString().trim() === ref) { 
                var n = r[cSjItem]; 
                if(!mapKirim[n]) mapKirim[n]=0; mapKirim[n] += parseFloat(r[cSjQty])||0; 
            }
        });
    }
    var res = [];
    for(var p in mapTarget) { 
        var sisa = mapTarget[p] - (mapKirim[p]||0);
        if(sisa > 0) res.push({ nama: p, sisa: sisa }); 
    }
    return res;
  } catch(e) { return []; }
}

function getDetailTransaksi(tipe, noRef, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  try {
    var res = { items: [] };
    if(tipe === "PO" || tipe === "INV") {
      var sheetName = tipe === "PO" ? "Data_PO" : "Data_Invoice";
      var pDoc = getSheetWithMap(sheetName);
      if(pDoc) {
          var cTgl = pDoc.c(["tanggal", "tgl"], 0);
          var cNo = pDoc.c(["no po", "no invoice"], 1);
          var cCust = pDoc.c(["customer"], tipe==="PO"?2:3);
          var cItem = pDoc.c(["nama item"], tipe==="PO"?3:4);
          var cQty = pDoc.c(["qty"], tipe==="PO"?4:5);
          var cHrg = pDoc.c(["harga"], tipe==="PO"?5:6);
          var cCat = pDoc.c(["catatan"], tipe==="PO"?7:8);
          var cDead = pDoc.c(["deadline"], 8);
          var cRef = pDoc.c(["ref po"], 2);
          var cRefSj = pDoc.c(["ref sj"], 9);

          pDoc.rows.forEach(r => {
             if(r[cNo].toString() === noRef) {
                if(!res.no) {
                    res.tgl = formatInputTgl(r[cTgl]);
                    res.no = noRef; 
                    res.cust = r[cCust]; 
                    res.catatan = r[cCat] || "";
                    if(tipe==="PO") res.deadline = formatInputTgl(r[cDead]);
                    if(tipe==="INV") { res.ref = r[cRef]; res.refSJ = r[cRefSj] || ""; }
                }
                res.items.push({ nama: r[cItem], qty: r[cQty], harga: r[cHrg] });
             }
          });
      }
    } else if(tipe === "SJ") {
      var pSJ = getSheetWithMap("Data_SuratJalan");
      if(pSJ) {
          var cTgl = pSJ.c(["tanggal"], 0), cNo = pSJ.c(["no sj"], 1), cRef = pSJ.c(["ref transaksi"], 2), cCust = pSJ.c(["customer"], 3), cItem = pSJ.c(["nama item"], 4), cQty = pSJ.c(["qty"], 5), cEks = pSJ.c(["ekspedisi"], 6);
          pSJ.rows.forEach(r => {
             if(r[cNo].toString() === noRef) {
                if(!res.no) { 
                    res.tgl = formatInputTgl(r[cTgl]);
                    res.no = noRef; res.ref = r[cRef]; res.cust = r[cCust]; res.eks = r[cEks];
                }
                res.items.push({ nama: r[cItem], qty: r[cQty] });
             }
          });
      }
    }
    return res;
  } catch(e) { return { error: e.message }; }
}

// ================= FUNGSI TULIS & HAPUS DINAMIS + LOCK SERVICE =================

function hapusDataMaster(tipe, noRef, skipLock, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  SALES_touchMutation_('hapusDataMaster');

  var lock;
  if (!skipLock) {
    lock = LockService.getScriptLock();
    try { lock.waitLock(15000); } catch(e) { return "ERROR: Server sibuk. Coba lagi."; }
  }

  try {
    var sheetName = tipe === "PO" ? "Data_PO" : (tipe === "SJ" ? "Data_SuratJalan" : "Data_Invoice");
    var sData = getSheetWithMap(sheetName);
    var idxNo = sData.c(["no po", "no sj", "no invoice", "no"], 1);
    var idxRef = sData.c(["ref transaksi", "referensi"], 2); // Khusus narik PO dari SJ
    
    var fullData = sData.fullData; 
    var newData = [];
    var hasDeleted = false;
    var poTerkaitUntukDiupdate = []; // Menyimpan memori PO mana yang harus dicek ulang
    
    for(var i = 0; i < fullData.length; i++) {
        if(i === 0) { newData.push(fullData[i]); continue; } 
        
        if(fullData[i][idxNo].toString().trim() !== noRef.toString().trim()) {
            newData.push(fullData[i]);
        } else {
            hasDeleted = true;
            // 💡 KUNCI: Jika SJ dihapus, catat Nomor PO-nya sebelum barisnya musnah
            if(tipe === "SJ") {
                var refPO = fullData[i][idxRef] ? fullData[i][idxRef].toString().trim() : "";
                if(refPO && !poTerkaitUntukDiupdate.includes(refPO)) poTerkaitUntukDiupdate.push(refPO);
            }
        }
    }
    
    if (hasDeleted) {
        sData.sheet.clearContents(); 
        if(newData.length > 0) {
            sData.sheet.getRange(1, 1, newData.length, newData[0].length).setValues(newData);
        }
        if (tipe === "SJ") {
            SALES_voidSjStockMovement_(noRef, "DELETE_SJ_FROM_SALES");
        }
    }
    
    SpreadsheetApp.flush(); // Segarkan database sebelum mengecek status PO
    
    // 💡 TRIGGER AUTO-UPDATE PO KEMBALI AKTIF (Jika ada SJ yang terhapus)
    if (poTerkaitUntukDiupdate.length > 0) {
        poTerkaitUntukDiupdate.forEach(po => cekDanUpdateStatusPO(po));
    }
    
    return "OK";
  } catch(e) { 
    return "ERROR: " + e.message;
  } finally {
    if (!skipLock && lock) lock.releaseLock();
  }
}

// FUNGSI AUTO-STATUS PO (DUA ARAH) SAAT SJ DIBUAT/DIHAPUS
function cekDanUpdateStatusPO(noPO) {
  try {
    var pPO = getSheetWithMap("Data_PO"), pSJ = getSheetWithMap("Data_SuratJalan");
    if(!pPO || !pSJ || !noPO) return;

    var qtyPO = 0, qtySJ = 0;
    var cPoNo = pPO.c(["no po"], 1), cPoItem = pPO.c(["nama item"], 3), cPoQty = pPO.c(["qty"], 4);
    var cPoStat = pPO.c(["status"], 9);
    
    // Hitung total QTY pesanan
    pPO.rows.forEach(r => {
        if(r[cPoNo].toString().trim().toUpperCase() === noPO.toString().trim().toUpperCase()) {
            var nm = r[cPoItem].toString();
            if(nm !== "Biaya Ongkos Kirim" && nm !== "Potongan Diskon" && !nm.startsWith("Pajak PPN")) {
                qtyPO += SALES_toNumber_(r[cPoQty]);
            }
        }
    });

    // Hitung total QTY SJ (yang tersisa di database)
    var cSjRef = pSJ.c(["ref transaksi"], 2), cSjQty = pSJ.c(["qty"], 5);
    pSJ.rows.forEach(r => {
        if(r[cSjRef].toString().trim().toUpperCase() === noPO.toString().trim().toUpperCase()) {
            qtySJ += SALES_toNumber_(r[cSjQty]);
        }
    });

    // 💡 LOGIKA DUA ARAH: SJ >= PO maka "Selesai", Jika kurang maka balik "Aktif"
    var statusBaru = (qtySJ >= qtyPO && qtyPO > 0) ? "Selesai" : "Aktif";
    
    var fullData = pPO.fullData;
    var isChanged = false;
    
    for(var i=1; i<fullData.length; i++){
        if(fullData[i][cPoNo].toString().trim().toUpperCase() === noPO.toString().trim().toUpperCase()) {
            if(fullData[i][cPoStat] !== statusBaru) {
                fullData[i][cPoStat] = statusBaru;
                isChanged = true;
            }
        }
    }
    
    // Simpan status terbaru ke database
    if (isChanged) pPO.sheet.getRange(1, 1, fullData.length, fullData[0].length).setValues(fullData);
    
  } catch(e) {} 
}

function simpanDataMaster(d, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  SALES_touchMutation_('simpanDataMaster');

  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch (e) { return "ERROR: Sistem sedang sibuk. Silakan coba lagi."; }

  try {
    d.tgl = sanitizeStr(d.tgl);
    d.no = sanitizeStr(d.no);
    d.cust = sanitizeStr(d.cust);
    d.catatan = sanitizeStr(d.catatan);
    d.deadline = d.deadline ? sanitizeStr(d.deadline) : "";
    d.ref = d.ref ? sanitizeStr(d.ref) : "";
    d.refSJ = d.refSJ ? sanitizeStr(d.refSJ) : "";
    d.eks = d.eks ? sanitizeStr(d.eks) : "";
    
    var validItems = [];
    d.items.forEach(function(i) {
       var cleanNama = sanitizeStr(i.nama);
       var cleanQty = SALES_toNumber_(i.qty);
       var cleanHarga = SALES_toNumber_(i.harga);

       if (cleanQty <= 0) return; 

       if (cleanNama === "Potongan Diskon") {
           cleanHarga = -Math.abs(cleanHarga);
       } else {
           cleanHarga = Math.abs(cleanHarga);
       }

       validItems.push({ nama: cleanNama, qty: cleanQty, harga: cleanHarga, total: cleanQty * cleanHarga });
    });
    
    if (validItems.length === 0) return "ERROR: Item barang kosong atau QTY tidak valid.";
    d.items = validItems;
    
    // PERBAIKAN POTENSI DUPLIKASI DATA
    if(d.mode === "edit" && d.noLama) { 
        var statusHapus = hapusDataMaster(d.tipe, d.noLama, true, __auth.email, pasporOp); 
        if (statusHapus.toString().indexOf("ERROR") > -1) {
            return "ERROR: Gagal memperbarui data karena " + statusHapus;
        }
    }

    if(d.tipe === "PO") {
      var sData = getSheetWithMap("Data_PO");
      var totalCol = Math.max(sData.headers.length, 10);
      var newRows = [];
      
      d.items.forEach(i => {
         var row = new Array(totalCol).fill("");
         row[sData.c(["tanggal", "tgl"], 0)] = d.tgl;
         row[sData.c(["no po", "nomor po"], 1)] = d.no;
         row[sData.c(["customer", "pelanggan"], 2)] = d.cust;
         row[sData.c(["nama item", "item"], 3)] = i.nama;
         row[sData.c(["qty", "jumlah"], 4)] = i.qty;
         row[sData.c(["harga", "harga satuan"], 5)] = i.harga;
         row[sData.c(["total"], 6)] = i.total; 
         row[sData.c(["catatan", "notes"], 7)] = d.catatan;
         row[sData.c(["deadline", "batas waktu"], 8)] = d.deadline;
         row[sData.c(["status"], 9)] = "Aktif";
         newRows.push(row);
      });
      if(newRows.length > 0) sData.sheet.getRange(sData.sheet.getLastRow() + 1, 1, newRows.length, totalCol).setValues(newRows);
      
    } else if (d.tipe === "SJ") {
      var sData = getSheetWithMap("Data_SuratJalan");
      // Validasi dan siapkan tembakan ke Stock_Movement Gudang lebih dulu.
      // Movement_Type SALES_OUT sengaja tidak AUTO_OK di Gudang, supaya staf Gudang validasi fisik.
      var stockMovementRows = SALES_prepareSjStockMovementRows_(d, d.items);
      var totalCol = Math.max(sData.headers.length, 7);
      var newRows = [];
      
      d.items.forEach(i => {
         var row = new Array(totalCol).fill("");
         row[sData.c(["tanggal", "tgl"], 0)] = d.tgl;
         row[sData.c(["no sj", "nomor sj"], 1)] = d.no;
         row[sData.c(["ref transaksi", "referensi"], 2)] = d.ref;
         row[sData.c(["customer", "pelanggan"], 3)] = d.cust;
         row[sData.c(["nama item", "item"], 4)] = i.nama;
         row[sData.c(["qty", "jumlah"], 5)] = i.qty;
         row[sData.c(["ekspedisi", "kurir"], 6)] = d.eks;
         newRows.push(row);
      });
      if(newRows.length > 0) {
        sData.sheet.getRange(sData.sheet.getLastRow() + 1, 1, newRows.length, totalCol).setValues(newRows);
        SALES_postSjToStockMovement_(d, d.items, stockMovementRows);
      }
      
    } else if (d.tipe === "INV") {
      var sData = getSheetWithMap("Data_Invoice");
      var totalCol = Math.max(sData.headers.length, 10);
      var newRows = [];
      
      d.items.forEach(i => {
         var row = new Array(totalCol).fill("");
         row[sData.c(["tanggal", "tgl"], 0)] = d.tgl;
         row[sData.c(["no invoice", "nomor invoice"], 1)] = d.no;
         row[sData.c(["ref po", "referensi po"], 2)] = d.ref;
         row[sData.c(["customer", "pelanggan"], 3)] = d.cust;
         row[sData.c(["nama item", "item"], 4)] = i.nama;
         row[sData.c(["qty", "jumlah"], 5)] = i.qty;
         row[sData.c(["harga"], 6)] = i.harga;
         row[sData.c(["total"], 7)] = i.total; 
         row[sData.c(["catatan", "notes"], 8)] = d.catatan;
         row[sData.c(["ref sj", "referensi sj"], 9)] = d.refSJ || "";
         newRows.push(row);
      });
      if(newRows.length > 0) sData.sheet.getRange(sData.sheet.getLastRow() + 1, 1, newRows.length, totalCol).setValues(newRows);
    }
    
    SpreadsheetApp.flush();
    
    if (d.tipe === "SJ" && d.ref) {
       cekDanUpdateStatusPO(d.ref);
    }

    return "OK";
  } catch(e) { 
    return "ERROR: " + e.message;
  } finally {
    lock.releaseLock();
  }
}

function updateStatusPO(noPO, status, emailOp, pasporOp) {
  var __auth = SALES_requirePassport_(emailOp, pasporOp);
  SALES_touchMutation_('updateStatusPO');

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch(e) { return "ERROR"; }

  try {
    var p = getSheetWithMap("Data_PO");
    var idxNo = p.c(["no po", "nomor po"], 1);
    var idxStat = p.c(["status"], 9) + 1;

    for(var i=0; i<p.rows.length; i++) { 
       if(p.rows[i][idxNo].toString() === noPO.toString()) {
          p.sheet.getRange(i+2, idxStat).setValue(status);
       }
    }
    SpreadsheetApp.flush();
  } finally { lock.releaseLock(); }
}

function TEST_salesFinanceSyncDebug() {
  var journals = SALES_getFinanceJournalRows_();
  var data = getInitData('', '', '');
  return {
    success: true,
    salesVersion: SALES_CFG.VERSION,
    financeJournalsLoaded: journals.length,
    sampleFinanceJournals: journals.slice(0, 10),
    financeSyncInfo: data.financeSyncInfo || null,
    sampleInvoices: (data.dataINV || []).slice(0, 10),
    samplePiutang: (data.dataPiutang || []).slice(0, 5)
  };
}

function TEST_salesDpNoDoubleDebug() {
  var data = getInitData('', '', '');
  return { success: true, version: SALES_CFG.VERSION, financeSyncInfo: data.financeSyncInfo || null, samplePiutang: (data.dataPiutang || []).slice(0, 10) };
}


// ===== FLOW-STYLE SECURITY + HEARTBEAT SYNC v1.4 =====
// Seragam dengan Purchasing/Produksi: HMAC passport dari Portal, bukan Security_Passport sheet.

var ERP_GLOBAL_CFG = {
  MASTER_SPREADSHEET_ID: SALES_CFG.MASTER_SPREADSHEET_ID,
  MODULE_CODE: SALES_CFG.MODULE_CODE,
  SESSION_TTL_MS: SALES_CFG.SESSION_TTL_MS,
  SHARED_SECRET: SALES_CFG.SHARED_SECRET,
  HEARTBEAT_CELL: SALES_CFG.HEARTBEAT_CELL,
  HEARTBEAT_UPDATED_CELL: SALES_CFG.HEARTBEAT_UPDATED_CELL,
  HEARTBEAT_NOTES_CELL: SALES_CFG.HEARTBEAT_NOTES_CELL,
  MASTER_USER_SHEET: SALES_CFG.MASTER_USER_SHEET,
  MASTER_MODULE_SHEET: SALES_CFG.MASTER_MODULE_SHEET,
  LOG_LOGIN_SHEET: SALES_CFG.LOG_LOGIN_SHEET,
  PORTAL_CODES: SALES_CFG.PORTAL_CODES,
  TZ: SALES_CFG.TZ || (Session.getScriptTimeZone() || 'Asia/Jakarta')
};

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
  // Kompatibel dengan call lama: ERP_globalHeartbeat(passportId, clientVersion, email, paspor)
  if (arguments.length >= 4) {
    clientVersion = arguments[1];
    emailOp = arguments[2];
    pasporOp = arguments[3] || arguments[0] || '';
  }
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth.allowed) return { ok:false, reason:auth.reason || 'SESSION_INVALID', shouldLogout:true, portalUrl:ERP_withLoginParam_(ERP_getPortalUrl_()) };
  var hb = ERP_readGlobalHeartbeat_();
  return {
    ok: true,
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
  // Kompatibel dengan call lama: ERP_globalLogout(passportId, email, paspor)
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

function TEST_erpGlobalSecurityHeartbeat(email, paspor) {
  var auth = ERP_securityCheck_(email || ERP_userEmail_(), paspor || '', !!paspor);
  var hb = ERP_readGlobalHeartbeat_();
  return { success:true, moduleCode:ERP_GLOBAL_CFG.MODULE_CODE, auth:auth, heartbeat:hb, portalUrl:ERP_getPortalUrl_(), note:'v1.4 HMAC passport Flow Style; tidak baca Security_Passport sheet.' };
}

function ERP_securityCheck_(emailOp, pasporOp, passportRequired) {
  // Backward compatibility: ERP_securityCheck_(paspor, true)
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
  var can = isAdmin || ERP_userCanOpenModule_({ allowedModules:allowedModules, role:role, department:department }, ERP_GLOBAL_CFG.MODULE_CODE, 'Penjualan Sales');
  return {
    allowed: can,
    reason: can ? (isAdmin ? 'ADMIN' : 'MODULE_ALLOWED') : 'MODULE_NOT_ALLOWED',
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
function ERP_userCanOpenModule_(auth, code, name) {
  var fields = [auth.allowedModules, auth.role, auth.department].map(ERP_key_).join('|');
  if (fields.indexOf('ALL') !== -1 || fields.indexOf('SUPERADMIN') !== -1) return true;
  var targets = [code].concat(SALES_CFG.MODULE_ALIASES || []).concat([name || '']).map(ERP_key_);
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
function ERP_isActive_(v){var s=ERP_key_(v);return ['ACTIVE','AKTIF','ON','TRUE','YES','ENABLED','NEWCORE','NEW_CORE'].indexOf(s)!==-1;}
function ERP_parseDate_(v){if(v instanceof Date)return v;var d=new Date(v);return isNaN(d.getTime())?null:d;}
function ERP_formatDateTime_(v){var d=ERP_parseDate_(v);return d?Utilities.formatDate(d,ERP_GLOBAL_CFG.TZ,'yyyy-MM-dd HH:mm:ss'):'';}
function ERP_headerMap_(headers){var m={};for(var i=0;i<headers.length;i++){var k=ERP_key_(headers[i]);if(k)m[k]=i;}return m;}
function ERP_col_(map,names,required){names=Array.isArray(names)?names:[names];for(var i=0;i<names.length;i++){var k=ERP_key_(names[i]);if(map[k]!==undefined)return map[k];}if(required)throw new Error('Header tidak ditemukan: '+names.join('/'));return -1;}
function ERP_pick_(obj, aliases) { var m = {}; Object.keys(obj || {}).forEach(function(k){ m[ERP_key_(k)] = obj[k]; }); for (var i=0; i<(aliases || []).length; i++) { var key = ERP_key_(aliases[i]); if (m[key] !== undefined) return m[key]; } return ''; }
function ERP_readRows_(sh){var vals=sh.getDataRange().getValues();if(vals.length<2)return[];var headers=vals[0].map(ERP_clean_);return vals.slice(1).filter(function(r){return r.some(function(c){return c!==''&&c!==null;});}).map(function(r){var o={};headers.forEach(function(h,i){if(h)o[h]=r[i];});return o;});}
function ERP_escapeHtml_(s){return String(s||'').replace(/[&<>'"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c];});}

// ===== ERP ACCESS-SAFE MODULE LINKS OVERRIDE v1.4 =====
function getModulLinks(emailOp, pasporOp) {
  // Kompatibel dengan call lama: getModulLinks(passport)
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
    if (code === ERP_GLOBAL_CFG.MODULE_CODE) continue;
    if (!(auth.isAdmin || ERP_userCanOpenModule_(auth, m.code, m.name))) continue;
    out.push({ code: m.code, nama: m.name, name: m.name, url: ERP_appendPassportToUrl_(m.url, auth, paspor || auth.passport || auth.passportId || '') });
  }
  return out;
}