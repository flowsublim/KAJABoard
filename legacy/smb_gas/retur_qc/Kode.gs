// =================================================================================
// ERP CV KIRAL - MODUL RETUR QC WEBAPP v2.0.1 CLEAN INLINE NOTIF
// Source retur: Omni_Retur only. Data_Retur_AppSheet sudah diputus dari runtime.
// Posting stok: batch RETURN_IN mengikuti kontrak Stock_Movement Gudang v2.5 + Tx_Key idempotent.
// =================================================================================

var RQC_CFG = {
  VERSION: 'RETUR_QC_v2.0.1_CLEAN_INLINE_NOTIF',
  MASTER_SPREADSHEET_ID: '1bbtCMQfK5p_2c5GzIkTIrcIPcPsm3Wjh_R8PfAagu6I',
  MODULE_CODE: 'RETUR_QC',
  MODULE_ALIASES: ['RETUR_QC','RETUR QC','RETURN_QC','RETURN QC','RETUR','RETURN','QC_RETUR','RETURQC'],
  SESSION_TTL_MS: 6 * 60 * 60 * 1000,
  SHARED_SECRET: 'CV_KIRAL_FLOW_SUBLIM_STYLE_FIXED_SECRET_2026_KIRAL',
  HEARTBEAT_CELL: 'J1',
  HEARTBEAT_UPDATED_CELL: 'J2',
  HEARTBEAT_NOTES_CELL: 'J3',
  MASTER_USER_SHEET: 'Master_User',
  MASTER_MODULE_SHEET: 'Master_Module',
  LOG_LOGIN_SHEET: 'Log_Login',
  PORTAL_CODES: ['PORTAL','PRTL','HOME','BERANDA'],
  TZ: 'Asia/Jakarta',
  OMNI_MODULE_CODES: ['OMNI', 'OMNICHANNEL', 'RETAIL_OMNI', 'RETAIL'],
  GUDANG_MODULE_CODES: ['WH', 'GUDANG', 'WAREHOUSE'],
  // Optional override untuk development/debug. Isi ID spreadsheet kalau routing Master_Module masih belum ketemu.
  RETUR_QC_SPREADSHEET_ID_OVERRIDE: '',
  OMNI_SPREADSHEET_ID_OVERRIDE: '',
  GUDANG_SPREADSHEET_ID_OVERRIDE: '',
  RETURN_SOURCE_SHEETS: ['Omni_Retur'],
  CACHE_SECONDS: 300,
  // Isi dengan URL Scanner_External.html setelah di-host di GitHub Pages/Cloudflare/Netlify/Firebase.
  // Contoh: 'https://username.github.io/retur-scanner/Scanner_External.html'
  EXTERNAL_SCANNER_URL: ''
};

var RQC_RUNTIME_EMAIL = '';

// Nama sheet standar dikunci literal.
// v1.4: tidak membaca RQC_CFG.SHEETS, gid, cache, atau setting apa pun untuk nama sheet.
var RQC_SHEET = {
  SESSION: 'Return_QC_Session',
  LINE: 'Return_QC_Line',
  QUARANTINE: 'Return_Quarantine',
  IMPORT_LOG: 'Return_Import_Log',
  LOG_ERROR: 'Log_Error',
  MASTER_MODULE: 'Master_Module',
  MASTER_USER: 'Master_User',
  MASTER_ITEM: 'Master_Item',
  STOCK_MOVEMENT: 'Stock_Movement'
};

function RQC_sheet_(key) {
  var k = String(key || '').trim().toUpperCase();
  var name = RQC_SHEET[k];
  if (!name) throw new Error('Key sheet tidak dikenal: ' + key);
  return name;
}

function RQC_getSheetByKey_(ss, key) {
  return ss.getSheetByName(RQC_sheet_(key));
}

function RQC_ensureSheetByKey_(ss, key, headers) {
  return RQC_ensureSheet_(ss, RQC_sheet_(key), headers);
}

// =================================================================================
// WEB APP
// =================================================================================
function doGet(e) {
  var auth = RQC_doGetAccess_(e);
  if (!auth.allowed) return RQC_forbiddenOutput_(auth);

  var t = HtmlService.createTemplateFromFile('Index');
  var param = (e && e.parameter) ? e.parameter : {};
  var pass = auth.passport || param.paspor || param.passport || param.token || '';
  t.INIT_SCAN_RESI = param.scan || param.resi || param.code || '';
  t.EXTERNAL_SCANNER_URL = RQC_CFG.EXTERNAL_SCANNER_URL || '';
  t.CURRENT_WEBAPP_URL = RQC_getCurrentWebAppUrl_();
  t.APP_VERSION = RQC_CFG.VERSION;
  t.RQC_BOOTSTRAP = {
    moduleCode: RQC_CFG.MODULE_CODE,
    version: RQC_CFG.VERSION,
    email: auth.email || '',
    userEmail: auth.email || '',
    displayName: auth.displayName || auth.email || '',
    passport: pass,
    paspor: pass,
    portalUrl: RQC_getPortalUrl_()
  };

  return t.evaluate()
    .setTitle('ERP - Retur QC')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

function RQC_getCurrentWebAppUrl_() {
  try {
    var url = ScriptApp.getService().getUrl();
    return url || '';
  } catch (e) {
    return '';
  }
}

// =================================================================================
// SETUP & TEST
// =================================================================================
function SETUP_installReturQC() {
  var ss = RQC_selfSs_();
  // v1.5: self spreadsheet dibuka via Master_Module/override dulu, lalu pakai nama literal.
  RQC_ensureSheet_(ss, 'Return_QC_Session', [
    'Session_ID','Session_Date','Session_Status','Started_By','Posted_At','Posted_By',
    'Total_Package','Total_Pass_Qty','Movement_Batch_ID','Notes'
  ]);
  RQC_ensureSheet_(ss, 'Return_QC_Line', [
    'QC_Line_ID','Session_ID','Scan_Time','Scanned_Code','Source_Sheet','Source_Row','Source_Return_ID',
    'Order_No','Tracking_No','Return_Tracking_No','Marketplace_SKU','Expected_Item_Name','Expected_Qty',
    'Actual_Item_Name','Actual_Qty','Condition','QC_Result','Issue_Type','Notes',
    'Movement_Batch_ID','Posted_Flag','Created_By','Updated_At'
  ]);
  RQC_ensureSheet_(ss, 'Return_Quarantine', [
    'Quarantine_ID','Session_ID','QC_Line_ID','Tracking_No','Order_No','Expected_Item_Name',
    'Actual_Item_Name','Actual_Qty','Issue_Type','Status','Created_At','Created_By','Notes'
  ]);
  RQC_ensureSheet_(ss, 'Return_Import_Log', [
    'Import_ID','Import_Date','Source_File','Rows_Read','Rows_Insert','Rows_Update','Imported_By','Notes'
  ]);

  // Pastikan Stock_Movement di modul Gudang siap minimal. Tidak memaksa kalau file Gudang belum tersedia.
  try {
    var wh = RQC_openGudangModule_();
    RQC_ensureSheetByKey_(wh.ss, 'STOCK_MOVEMENT', RQC_stockMovementHeaders_());
  } catch(e) {
    RQC_logError_('SETUP_installReturQC.StockMovement', e, {});
  }

  RQC_clearCache_();
  return {
    success: true,
    version: RQC_CFG.VERSION,
    message: 'Retur QC v2.0.1 siap. Inline notif dimatikan, toast tetap aktif, Omni_Retur only, RETURN_IN kontrak Gudang v2.5, heartbeat, dan cache UI aktif.'
  };
}


function TEST_returQcSheetConfigClean() {
  var ss = RQC_selfSs_();
  return {
    success: true,
    version: RQC_CFG.VERSION,
    selfSpreadsheetName: ss.getName(),
    selfSpreadsheetId: ss.getId(),
    sheets: {
      SESSION: RQC_sheet_('SESSION'),
      LINE: RQC_sheet_('LINE'),
      QUARANTINE: RQC_sheet_('QUARANTINE'),
      IMPORT_LOG: RQC_sheet_('IMPORT_LOG'),
      STOCK_MOVEMENT: RQC_sheet_('STOCK_MOVEMENT')
    },
    found: {
      session: !!ss.getSheetByName('Return_QC_Session'),
      line: !!ss.getSheetByName('Return_QC_Line'),
      quarantine: !!ss.getSheetByName('Return_Quarantine'),
      importLog: !!ss.getSheetByName('Return_Import_Log')
    },
    note: 'v1.5: self spreadsheet dibuka via Master_Module/override dulu, bukan ActiveSpreadsheet. Ini memotong error gid 1865962240.'
  };
}

function TEST_returQcSelfRoutingDebug() {
  var out = { success: false, version: RQC_CFG.VERSION, steps: [] };
  function add(name, ok, data) { out.steps.push({ name: name, ok: ok, data: data }); }

  try {
    var master = RQC_masterSs_();
    var mm = RQC_getSheetByKey_(master, 'MASTER_MODULE');
    add('Master_Module', !!mm, mm ? ('found in ' + master.getName()) : 'not found');
  } catch(e0) { add('Master_Module', false, e0.message || String(e0)); }

  try {
    var routed = RQC_openModuleByCodes_([RQC_CFG.MODULE_CODE, 'RETUR_QC', 'RETUR QC', 'RETURN_QC', 'RETURN QC', 'RETUR']);
    add('Open RETUR_QC from Master_Module', true, { code: routed.code, name: routed.name, spreadsheetName: routed.ss.getName(), spreadsheetId: routed.ss.getId() });
  } catch(e1) { add('Open RETUR_QC from Master_Module', false, e1.message || String(e1)); }

  try {
    var ss = RQC_selfSs_();
    out.success = true;
    add('RQC_selfSs_', true, { spreadsheetName: ss.getName(), spreadsheetId: ss.getId() });
  } catch(e2) { add('RQC_selfSs_', false, e2.message || String(e2)); }

  return out;
}

function TEST_returQcHealth() {
  var out = { success: true, version: RQC_CFG.VERSION, checks: [] };
  function ok(name, data) { out.checks.push({ name: name, ok: true, data: data || '' }); }
  function fail(name, err) { out.success = false; out.checks.push({ name: name, ok: false, error: String(err && err.message ? err.message : err) }); }

  try { RQC_selfSs_(); ok('Return module spreadsheet'); } catch(e) { fail('Return module spreadsheet', e); }
  try { var omni = RQC_openModuleByCodes_(RQC_CFG.OMNI_MODULE_CODES); ok('Omni spreadsheet', omni.code); } catch(e) { fail('Omni spreadsheet', e); }
  try { var src = RQC_getReturSourceSheet_(); ok('Return source sheet', src.sheet.getName() + ' @ ' + src.spreadsheetName); } catch(e) { fail('Return source sheet', e); }
  try { var wh = RQC_openGudangModule_(); ok('Gudang spreadsheet', wh.code); } catch(e) { fail('Gudang spreadsheet', e); }
  try { var session = RQC_getOrCreateActiveSession_(); ok('Active QC session', session.Session_ID); } catch(e) { fail('Active QC session', e); }
  try { var items = RQC_getMasterItems_(); ok('Master_Item readable', items.length + ' item'); } catch(e) { fail('Master_Item readable', e); }

  return out;
}

// =================================================================================
// FRONTEND API
// =================================================================================
function getReturQcInit() {
  try {
    var __auth = RQC_requirePassportFromArgs_(arguments);
    var t0 = Date.now();
    var session = RQC_getOrCreateActiveSession_();
    var sourceInfo = RQC_getReturSourceSummary_();
    var lines = RQC_getSessionLines_(session.Session_ID, 80);
    var stats = RQC_countSessionStats_(session.Session_ID);
    var masterItems = RQC_getMasterItems_();
    var links = getModulLinks(__auth.email, __auth.passport);

    return RQC_safeForClient_({
      success: true,
      version: RQC_CFG.VERSION,
      user: RQC_userEmail_(),
      userInfo: { email: __auth.email || '', name: __auth.displayName || __auth.email || '', role: __auth.role || '', department: __auth.department || '' },
      heartbeat: RQC_readGlobalHeartbeat_(),
      session: session,
      source: sourceInfo,
      lines: lines,
      stats: stats,
      masterItems: masterItems,
      links: links,
      elapsedMs: Date.now() - t0
    });
  } catch (e) {
    RQC_logError_('getReturQcInit', e, {});
    return { success: false, msg: e.message || String(e) };
  }
}


function getReturQcUnscannedList(options) {
  try {
    RQC_requirePassportFromArgs_(arguments);
    options = options || {};
    var limit = RQC_toNumber_(options.limit || 500);
    if (!limit || limit < 1) limit = 500;
    if (limit > 2000) limit = 2000;

    var q = String(options.q || options.search || '').trim().toUpperCase();
    var overdueDays = RQC_toNumber_(options.overdueDays || 0);
    var rows = RQC_loadReturRows_();
    var scanIndex = RQC_getScannedReturnIndex_();
    var today = RQC_startOfDay_(new Date());
    var list = [];
    var sourceTotal = 0;
    var scannedTotal = 0;

    rows.forEach(function(row) {
      sourceTotal++;
      var scanned = RQC_isReturRowScanned_(row, scanIndex);
      if (scanned) {
        scannedTotal++;
        return;
      }

      var arrivedDate = RQC_parseDateLoose_(row.returnArrivedAt || row.tglSampai || row.orderDate || row.tglPesan);
      var ageDays = arrivedDate ? Math.max(0, Math.floor((today.getTime() - RQC_startOfDay_(arrivedDate).getTime()) / 86400000)) : '';

      if (overdueDays > 0 && (ageDays === '' || ageDays < overdueDays)) return;

      var resi = row.returnTrackingNo || row.trackingNo || '';
      var blob = [resi, row.orderNo, row.marketplaceSku, row.expectedItemName, row.marketplaceStatus, row.storeName, row.productName].join(' ').toUpperCase();
      if (q && blob.indexOf(q) === -1) return;

      list.push({
        sourceSheet: row.sourceSheet,
        sourceRow: row.sourceRow,
        orderNo: row.orderNo || '',
        trackingNo: row.trackingNo || '',
        returnTrackingNo: row.returnTrackingNo || '',
        scanResi: resi,
        marketplaceSku: row.marketplaceSku || '',
        productName: row.productName || '',
        variationName: row.variationName || '',
        expectedItemName: row.expectedItemName || '',
        expectedQty: row.expectedQty || 1,
        marketplaceStatus: row.marketplaceStatus || '',
        qcStatus: row.qcStatus || '',
        storeName: row.storeName || '',
        orderDate: RQC_formatDateForClient_(row.orderDate || row.tglPesan),
        returnArrivedAt: RQC_formatDateForClient_(row.returnArrivedAt || row.tglSampai),
        ageDays: ageDays
      });
    });

    list.sort(function(a, b) {
      var ax = a.ageDays === '' ? -1 : Number(a.ageDays);
      var bx = b.ageDays === '' ? -1 : Number(b.ageDays);
      if (bx !== ax) return bx - ax;
      return String(a.returnArrivedAt || '').localeCompare(String(b.returnArrivedAt || ''));
    });

    var fullCount = list.length;
    list = list.slice(0, limit);

    return RQC_safeForClient_({
      success: true,
      stats: {
        sourceTotal: sourceTotal,
        scannedTotal: scannedTotal,
        unscannedTotal: fullCount,
        shown: list.length,
        limit: limit,
        overdueDays: overdueDays || 0
      },
      data: list
    });
  } catch (e) {
    RQC_logError_('getReturQcUnscannedList', e, options || {});
    return { success: false, msg: e.message || String(e), data: [], stats: {} };
  }
}

function TEST_returQcUnscannedDebug() {
  RQC_clearCache_();
  var res = getReturQcUnscannedList({ limit: 20 });
  return {
    success: !!(res && res.success),
    version: RQC_CFG.VERSION,
    stats: res ? res.stats : {},
    sample: res && res.data ? res.data.slice(0, 10) : []
  };
}


function getReturQcScannedHistory(options) {
  try {
    RQC_requirePassportFromArgs_(arguments);
    options = options || {};
    var limit = RQC_toNumber_(options.limit || 500);
    if (!limit || limit < 1) limit = 500;
    if (limit > 5000) limit = 5000;

    var q = String(options.q || options.search || '').trim().toUpperCase();
    var resultFilter = String(options.result || 'ALL').trim().toUpperCase();
    var postedFilter = String(options.posted || 'ALL').trim().toUpperCase();

    var ss = RQC_selfSs_();
    var s = RQC_getSheetByKey_(ss, 'LINE');
    if (!s) {
      return RQC_safeForClient_({
        success: true,
        stats: { totalScanned: 0, passCount: 0, holdCount: 0, postedCount: 0, draftCount: 0, filteredTotal: 0, shown: 0, limit: limit },
        data: []
      });
    }

    var table = RQC_getTable_(s);
    var h = table.headerMap;
    var list = [];
    var stats = { totalScanned: 0, passCount: 0, holdCount: 0, postedCount: 0, draftCount: 0, filteredTotal: 0, shown: 0, limit: limit };

    for (var i = table.values.length - 1; i >= 1; i--) {
      var r = table.values[i];
      var qcResult = String(RQC_getCell_(r, h, 'QC_Result') || '').trim().toUpperCase();
      var postedFlag = String(RQC_getCell_(r, h, 'Posted_Flag') || '').trim().toUpperCase() === 'TRUE';
      var scanResi = String(
        RQC_getCell_(r, h, 'Return_Tracking_No') ||
        RQC_getCell_(r, h, 'Tracking_No') ||
        RQC_getCell_(r, h, 'Scanned_Code') ||
        RQC_getCell_(r, h, 'Order_No') || ''
      ).trim();

      stats.totalScanned++;
      if (qcResult === 'PASS' || qcResult === 'PARTIAL_PASS') stats.passCount++;
      else stats.holdCount++;
      if (postedFlag) stats.postedCount++;
      else stats.draftCount++;

      if (resultFilter && resultFilter !== 'ALL' && qcResult !== resultFilter) continue;
      if (postedFilter === 'POSTED' && !postedFlag) continue;
      if (postedFilter === 'DRAFT' && postedFlag) continue;

      var obj = {
        rowNo: i + 1,
        qcLineId: RQC_getCell_(r, h, 'QC_Line_ID') || '',
        sessionId: RQC_getCell_(r, h, 'Session_ID') || '',
        scanTime: RQC_getCell_(r, h, 'Scan_Time') || '',
        scannedCode: RQC_getCell_(r, h, 'Scanned_Code') || '',
        scanResi: scanResi,
        orderNo: RQC_getCell_(r, h, 'Order_No') || '',
        trackingNo: RQC_getCell_(r, h, 'Tracking_No') || '',
        returnTrackingNo: RQC_getCell_(r, h, 'Return_Tracking_No') || '',
        marketplaceSku: RQC_getCell_(r, h, 'Marketplace_SKU') || '',
        expectedItemName: RQC_getCell_(r, h, 'Expected_Item_Name') || '',
        expectedQty: RQC_getCell_(r, h, 'Expected_Qty') || '',
        actualItemName: RQC_getCell_(r, h, 'Actual_Item_Name') || '',
        actualQty: RQC_getCell_(r, h, 'Actual_Qty') || '',
        condition: RQC_getCell_(r, h, 'Condition') || '',
        qcResult: qcResult,
        issueType: RQC_getCell_(r, h, 'Issue_Type') || '',
        notes: RQC_getCell_(r, h, 'Notes') || '',
        movementBatchId: RQC_getCell_(r, h, 'Movement_Batch_ID') || '',
        postedFlag: postedFlag,
        createdBy: RQC_getCell_(r, h, 'Created_By') || '',
        updatedAt: RQC_getCell_(r, h, 'Updated_At') || '',
        sourceSheet: RQC_getCell_(r, h, 'Source_Sheet') || '',
        sourceRow: RQC_getCell_(r, h, 'Source_Row') || ''
      };

      var blob = [
        obj.scanResi, obj.scannedCode, obj.orderNo, obj.trackingNo, obj.returnTrackingNo,
        obj.marketplaceSku, obj.expectedItemName, obj.actualItemName, obj.qcResult,
        obj.condition, obj.movementBatchId, obj.createdBy, obj.notes
      ].join(' ').toUpperCase();
      if (q && blob.indexOf(q) === -1) continue;

      stats.filteredTotal++;
      if (list.length < limit) list.push(obj);
    }

    stats.shown = list.length;
    return RQC_safeForClient_({ success: true, stats: stats, data: list });
  } catch (e) {
    RQC_logError_('getReturQcScannedHistory', e, options || {});
    return { success: false, msg: e.message || String(e), data: [], stats: {} };
  }
}

function TEST_returQcScannedHistoryDebug() {
  var res = getReturQcScannedHistory({ limit: 20 });
  return {
    success: !!(res && res.success),
    version: RQC_CFG.VERSION,
    stats: res ? res.stats : {},
    sample: res && res.data ? res.data.slice(0, 10) : []
  };
}

function cariReturByResi(scanCode) {
  try {
    RQC_requirePassportFromArgs_(arguments);
    var code = RQC_normCode_(scanCode);
    if (!code) return { success: false, msg: 'Kode scan kosong.' };

    var session = RQC_getOrCreateActiveSession_();
    var duplicate = RQC_findLineInSessionByScan_(session.Session_ID, code);
    if (duplicate) {
      return RQC_safeForClient_({ success: false, duplicate: true, msg: 'Resi/kode ini sudah discan di sesi aktif.', line: duplicate });
    }

    var rows = RQC_loadReturRows_();
    var found = null;
    for (var i = 0; i < rows.length; i++) {
      var keys = rows[i].scanKeys || [];
      if (keys.indexOf(code) !== -1) { found = rows[i]; break; }
    }

    if (!found) {
      return {
        success: true,
        found: false,
        scannedCode: code,
        message: 'Resi tidak ditemukan di Omni_Retur. Bisa simpan sebagai UNKNOWN_RESI/HOLD.'
      };
    }

    return RQC_safeForClient_({ success: true, found: true, scannedCode: code, record: found });
  } catch (e) {
    RQC_logError_('cariReturByResi', e, { scanCode: scanCode });
    return { success: false, msg: e.message || String(e) };
  }
}

function simpanQcLine(payload) {
  var __auth = RQC_requirePassportFromArgs_(arguments);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(15000); } catch(e) { return { success:false, msg:'Server sibuk. Coba lagi.' }; }

  try {
    payload = payload || {};
    var session = RQC_getOrCreateActiveSession_();
    if (session.Session_Status !== 'DRAFT') throw new Error('Sesi QC aktif bukan DRAFT. Refresh halaman untuk membuat sesi baru.');

    var result = String(payload.qcResult || '').trim().toUpperCase();
    var allowed = ['PASS','PARTIAL_PASS','MISMATCH','DAMAGED','HOLD','UNKNOWN_RESI'];
    if (allowed.indexOf(result) === -1) throw new Error('QC result tidak valid.');

    var actualItem = String(payload.actualItemName || '').trim();
    var actualQty = RQC_toNumber_(payload.actualQty);
    if ((result === 'PASS' || result === 'PARTIAL_PASS') && (!actualItem || actualQty <= 0)) {
      throw new Error('Untuk PASS/PARTIAL_PASS, Actual Item dan Actual Qty wajib diisi.');
    }

    var scannedCode = RQC_normCode_(payload.scannedCode || payload.trackingNo || payload.returnTrackingNo || '');
    if (!scannedCode) throw new Error('Kode scan/resi kosong.');

    var duplicate = RQC_findLineInSessionByScan_(session.Session_ID, scannedCode);
    if (duplicate) throw new Error('Resi/kode ini sudah discan di sesi aktif.');

    var now = new Date();
    var lineId = 'RQL-' + Utilities.getUuid().slice(0, 8).toUpperCase();
    var rowObj = {
      QC_Line_ID: lineId,
      Session_ID: session.Session_ID,
      Scan_Time: now,
      Scanned_Code: scannedCode,
      Source_Sheet: payload.sourceSheet || '',
      Source_Row: payload.sourceRow || '',
      Source_Return_ID: payload.sourceReturnId || '',
      Order_No: payload.orderNo || '',
      Tracking_No: payload.trackingNo || '',
      Return_Tracking_No: payload.returnTrackingNo || '',
      Marketplace_SKU: payload.marketplaceSku || '',
      Expected_Item_Name: payload.expectedItemName || '',
      Expected_Qty: RQC_toNumber_(payload.expectedQty),
      Actual_Item_Name: actualItem,
      Actual_Qty: actualQty,
      Condition: payload.condition || '',
      QC_Result: result,
      Issue_Type: payload.issueType || '',
      Notes: payload.notes || '',
      Movement_Batch_ID: '',
      Posted_Flag: 'FALSE',
      Created_By: RQC_userEmail_(),
      Updated_At: now
    };

    var ss = RQC_selfSs_();
    RQC_appendObjects_(RQC_getSheetByKey_(ss, 'LINE'), [rowObj]);

    if (result !== 'PASS' && result !== 'PARTIAL_PASS') {
      RQC_appendObjects_(RQC_getSheetByKey_(ss, 'QUARANTINE'), [{
        Quarantine_ID: 'RQ-' + Utilities.getUuid().slice(0, 8).toUpperCase(),
        Session_ID: session.Session_ID,
        QC_Line_ID: lineId,
        Tracking_No: payload.trackingNo || scannedCode,
        Order_No: payload.orderNo || '',
        Expected_Item_Name: payload.expectedItemName || '',
        Actual_Item_Name: actualItem,
        Actual_Qty: actualQty,
        Issue_Type: payload.issueType || result,
        Status: 'OPEN',
        Created_At: now,
        Created_By: RQC_userEmail_(),
        Notes: payload.notes || ''
      }]);
    }

    if (payload.sourceSheet && payload.sourceRow) {
      RQC_updateReturnSourceStatus_(payload.sourceSheet, Number(payload.sourceRow), result, session.Session_ID, 'SCANNED');
    }

    RQC_clearCache_();
    RQC_touchMutation_('simpanQcLine');
    return RQC_safeForClient_({ success: true, msg: 'QC line tersimpan.', lineId: lineId, stats: RQC_countSessionStats_(session.Session_ID), lines: RQC_getSessionLines_(session.Session_ID, 80) });
  } catch(e) {
    RQC_logError_('simpanQcLine', e, payload);
    return { success:false, msg:e.message || String(e) };
  } finally {
    try { lock.releaseLock(); } catch(err) {}
  }
}

function postReturQcBatch(sessionId) {
  var __auth = RQC_requirePassportFromArgs_(arguments);
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch(e) { return { success:false, msg:'Server sibuk. Coba lagi.' }; }

  try {
    var session = RQC_getSessionById_(sessionId);
    if (!session) throw new Error('Session tidak ditemukan.');
    if (session.Session_Status !== 'DRAFT') throw new Error('Session sudah diposting / tidak aktif.');

    var ss = RQC_selfSs_();
    var lineSheet = RQC_getSheetByKey_(ss, 'LINE');
    var table = RQC_getTable_(lineSheet);
    var h = table.headerMap;
    var aggregate = {};
    var rowsToMark = [];
    var sourceRowsToPost = [];

    for (var i = 1; i < table.values.length; i++) {
      var r = table.values[i];
      var sid = RQC_getCell_(r, h, 'Session_ID');
      if (sid !== sessionId) continue;
      var posted = String(RQC_getCell_(r, h, 'Posted_Flag') || '').toUpperCase() === 'TRUE';
      if (posted) continue;
      var result = String(RQC_getCell_(r, h, 'QC_Result') || '').toUpperCase();
      if (result !== 'PASS' && result !== 'PARTIAL_PASS') continue;
      var item = String(RQC_getCell_(r, h, 'Actual_Item_Name') || '').trim();
      var qty = RQC_toNumber_(RQC_getCell_(r, h, 'Actual_Qty'));
      if (!item || qty <= 0) continue;
      if (!aggregate[item]) aggregate[item] = { item: item, qty: 0, count: 0, orders: {}, resis: {}, lineIds: [] };
      aggregate[item].qty += qty;
      aggregate[item].count++;
      var orderNo = String(RQC_getCell_(r, h, 'Order_No') || '').trim();
      var resi = String(RQC_getCell_(r, h, 'Tracking_No') || RQC_getCell_(r, h, 'Return_Tracking_No') || RQC_getCell_(r, h, 'Scanned_Code') || '').trim();
      var lineId = String(RQC_getCell_(r, h, 'QC_Line_ID') || '').trim();
      if (orderNo) aggregate[item].orders[orderNo] = true;
      if (resi) aggregate[item].resis[resi] = true;
      if (lineId) aggregate[item].lineIds.push(lineId);
      rowsToMark.push(i + 1);
      var sourceSheet = RQC_getCell_(r, h, 'Source_Sheet');
      var sourceRow = RQC_getCell_(r, h, 'Source_Row');
      if (sourceSheet && sourceRow) sourceRowsToPost.push({ sourceSheet: sourceSheet, sourceRow: Number(sourceRow) });
    }

    var keys = Object.keys(aggregate);
    if (keys.length === 0) throw new Error('Tidak ada line PASS/PARTIAL_PASS yang belum diposting.');

    var now = new Date();
    var sourceDate = RQC_dateOnlyText_(now);
    var costPeriod = RQC_costPeriod_(now);
    var batchId = 'RTQC-' + Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyyMMdd-HHmmss');
    var wh = RQC_openGudangModule_();
    var smSheet = RQC_ensureSheetByKey_(wh.ss, 'STOCK_MOVEMENT', RQC_stockMovementHeaders_());
    var existingTx = RQC_readStockMovementKeySet_(smSheet);
    var costData = RQC_readGudangCostData_(wh.ss);
    var movements = [];
    var skippedDuplicate = 0;

    keys.sort().forEach(function(k) {
      var a = aggregate[k];
      var meta = RQC_findMasterItemMeta_(a.item);
      var sourceLineId = 'ITEM|' + (meta.Item_Name || a.item);
      var base = {
        Source_Module: RQC_CFG.MODULE_CODE,
        Movement_Type: 'RETURN_IN',
        Source_ID: sessionId,
        Source_Line_ID: sourceLineId,
        Ref_No: batchId,
        Direction: 'IN',
        Item_ID: meta.Item_ID || a.item,
        Item_Name: meta.Item_Name || a.item,
        Source_Date: sourceDate,
        Qty: a.qty
      };
      var txKey = RQC_stockTxKey_(base);
      if (existingTx[txKey]) {
        skippedDuplicate++;
        return;
      }
      var cost = RQC_findGudangCost_(costData, meta, costPeriod);
      movements.push({
        Movement_ID: 'SM-' + Utilities.getUuid().slice(0, 8).toUpperCase(),
        Tx_Key: txKey,
        Tanggal: sourceDate,
        Source_Date: sourceDate,
        Item_ID: meta.Item_ID || a.item,
        Item_Name: meta.Item_Name || a.item,
        Item_Category: meta.Item_Category || '',
        Item_Type: meta.Item_Type || '',
        Unit: meta.Unit || 'PCS',
        Warehouse_Code: 'MAIN',
        Direction: 'IN',
        Movement_Type: 'RETURN_IN',
        Qty: a.qty,
        Unit_Cost: cost.Unit_Cost || 0,
        Cost_Period: cost.Cost_Period || costPeriod,
        Cost_Status: cost.Cost_Status || 'PROVISIONAL',
        Unit_Cost_Provisional: cost.Unit_Cost_Provisional || 0,
        Value_Provisional: a.qty * (cost.Unit_Cost_Provisional || cost.Unit_Cost || 0),
        Unit_Cost_Final: cost.Cost_Status === 'FINAL' ? (cost.Unit_Cost_Final || cost.Unit_Cost || 0) : '',
        Value_Final: cost.Cost_Status === 'FINAL' ? a.qty * (cost.Unit_Cost_Final || cost.Unit_Cost || 0) : '',
        Cost_Source: cost.Cost_Source || 'MASTER_ITEM',
        Cost_Synced_At: cost.Cost_Synced_At || now,
        Closed_At: cost.Closed_At || '',
        Closed_By: cost.Closed_By || '',
        Source_Module: RQC_CFG.MODULE_CODE,
        Source_ID: sessionId,
        Source_Line_ID: sourceLineId,
        Ref_No: batchId,
        Batch_ID: batchId,
        External_Ref: Object.keys(a.resis).slice(0, 20).join(','),
        Notes: 'Retur QC siap jual: ' + a.count + ' scan | Order: ' + Object.keys(a.orders).length + ' | Resi: ' + Object.keys(a.resis).length,
        Status: 'POSTED',
        Created_At: now,
        Created_By: __auth.email || RQC_userEmail_(),
        Is_Deleted: false
      });
      existingTx[txKey] = true;
    });

    if (movements.length > 0) RQC_appendObjects_(smSheet, movements);

    // Mark QC lines posted in batch. Tetap mark jika movement sudah ada supaya retry tidak dobel.
    if (rowsToMark.length > 0) {
      var info = RQC_headerInfo_(lineSheet);
      var cBatch = RQC_col_(info, 'Movement_Batch_ID');
      var cPosted = RQC_col_(info, 'Posted_Flag');
      var cUpdated = RQC_col_(info, 'Updated_At');
      rowsToMark.forEach(function(rowNo) {
        if (cBatch > 0) lineSheet.getRange(rowNo, cBatch).setValue(batchId);
        if (cPosted > 0) lineSheet.getRange(rowNo, cPosted).setValue('TRUE');
        if (cUpdated > 0) lineSheet.getRange(rowNo, cUpdated).setValue(now);
      });
    }

    sourceRowsToPost.forEach(function(x) {
      RQC_updateReturnSourceStatus_(x.sourceSheet, x.sourceRow, 'POSTED_RETURN_IN', sessionId, 'POSTED');
    });

    RQC_updateSession_(sessionId, {
      Session_Status: 'POSTED',
      Posted_At: now,
      Posted_By: __auth.email || RQC_userEmail_(),
      Total_Package: RQC_countSessionStats_(sessionId).totalScan,
      Total_Pass_Qty: keys.reduce(function(sum, k) { return sum + aggregate[k].qty; }, 0),
      Movement_Batch_ID: batchId,
      Notes: 'Posted RETURN_IN Gudang contract v2.5. Inserted=' + movements.length + ', duplicateSkipped=' + skippedDuplicate + '.'
    });

    RQC_clearCache_();
    RQC_touchMutation_('postReturQcBatch RETURN_IN Gudang contract');
    return RQC_safeForClient_({
      success: true,
      batchId: batchId,
      movementRows: movements.length,
      skippedDuplicate: skippedDuplicate,
      totalQty: keys.reduce(function(sum, k) { return sum + aggregate[k].qty; }, 0),
      contractVersion: RQC_stockContractVersion_(),
      movements: movements
    });
  } catch(e) {
    RQC_logError_('postReturQcBatch', e, { sessionId: sessionId });
    return { success:false, msg:e.message || String(e) };
  } finally {
    try { lock.releaseLock(); } catch(err) {}
  }
}

function startNewReturQcSession(notes) {
  var __auth = RQC_requirePassportFromArgs_(arguments);
  var session = RQC_getOrCreateActiveSession_();
  if (session && session.Session_Status === 'DRAFT') {
    var stats = RQC_countSessionStats_(session.Session_ID);
    if (stats.totalScan > 0) return { success:false, msg:'Masih ada sesi DRAFT berisi scan. Posting dulu atau lanjutkan sesi itu.' };
  }
  var created = RQC_getOrCreateActiveSession_(true, notes || '');
  RQC_touchMutation_('startNewReturQcSession');
  return RQC_safeForClient_({ success:true, session: created });
}

function getModulLinks(emailOp, pasporOp) {
  try {
    var auth = RQC_requirePassport_(emailOp, pasporOp);
    var master = RQC_masterSs_();
    var s = RQC_getSheetByKey_(master, 'MASTER_MODULE');
    if (!s) return [];
    var table = RQC_getTable_(s);
    var h = table.headerMap;
    var res = [];
    for (var i = 1; i < table.values.length; i++) {
      var r = table.values[i];
      var status = String(RQC_getCell_(r, h, 'Status') || '').toUpperCase();
      if (!RQC_statusAllowed_(status)) continue;
      var code = String(RQC_getCell_(r, h, 'Module_Code') || '').trim();
      var name = RQC_getCell_(r, h, 'Module_Name') || code;
      var url = RQC_getCell_(r, h, 'Web_App_URL') || '';
      var key = RQC_key_(code + ' ' + name);
      if (key.indexOf(RQC_key_(RQC_CFG.MODULE_CODE)) !== -1 || key.indexOf('RETURQC') !== -1 || key === 'RETUR') continue;
      if (url) res.push({ nama: name, name: name, url: RQC_appendPassportToUrl_(url, auth, pasporOp || auth.passport || ''), code: code });
    }
    return res;
  } catch(e) { return []; }
}

// =================================================================================
// DATA LOADERS
// =================================================================================
function RQC_getReturSourceSummary_() {
  var src = RQC_getReturSourceSheet_();
  var table = RQC_getTable_(src.sheet);
  return {
    sheetName: src.sheet.getName(),
    spreadsheetName: src.spreadsheetName,
    rows: Math.max(0, table.values.length - 1)
  };
}

function RQC_loadReturRows_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('RQC_RETUR_ROWS_V5');
  if (cached) return JSON.parse(cached);

  var src = RQC_getReturSourceSheet_();
  var table = RQC_getTable_(src.sheet);
  var h = table.headerMap;
  var rows = [];
  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    var orderNo = RQC_pickCell_(r, h, ['Order_No','No Pesanan','Nomor Pesanan']);
    var trackingNo = RQC_pickCell_(r, h, ['Tracking_No','No Resi','Nomor Resi','Nomor Paket']);
    var returnTrackingNo = RQC_pickCell_(r, h, ['Return_Tracking_No','No Resi Retur','Nomor Resi Retur','Nomor Resi Pesanan Pengembalian','Resi Retur']);
    var sku = RQC_pickCell_(r, h, ['Marketplace_SKU','SKU BigSeller','SKU','SKU Gudang']);
    var productName = RQC_pickCell_(r, h, ['Marketplace_Product_Name','Nama Produk','Product Name','Nama SKU Gudang']);
    var variationName = RQC_pickCell_(r, h, ['Marketplace_Variation','Nama Variasi','Variation','Varian']);
    var item = RQC_pickCell_(r, h, ['Expected_Item_Name','Internal_Item_Name','Item Gudang','Item Gudang (Mapped)','Nama SKU Gudang','Nama Produk']);
    var qty = RQC_toNumber_(RQC_pickCell_(r, h, ['Expected_Qty','Return_Qty','QTY Retur Fisik','Jumlah','Qty']));
    var status = RQC_pickCell_(r, h, ['Marketplace_Return_Status','Status Marketplace','Status Pesanan','Status Purna Jual']);
    var qcStatus = RQC_pickCell_(r, h, ['QC_Status','Status Scan AppSheet','Status QC']);
    var storeName = RQC_pickCell_(r, h, ['Store_Name','Nama Toko','Toko','Nama Panggilan Toko BigSeller']);
    var orderDate = RQC_pickCell_(r, h, ['Order_Date','Tgl Pesan','Tanggal Pesan','Waktu Pesanan Dibuat','Waktu Pemesanan']);
    var returnArrivedAt = RQC_pickCell_(r, h, ['Return_Arrived_At','Tgl Sampai (RTS)','Tgl Sampai','Tanggal Sampai','Waktu Sampai Gudang','Tanggal RTS','RTS Date']);
    var retId = RQC_pickCell_(r, h, ['Return_ID','Retur_ID','ID Retur']);
    if (!retId) retId = 'RET-SRC-' + (i + 1);

    var keys = [];
    [trackingNo, returnTrackingNo, orderNo].forEach(function(x) {
      var k = RQC_normCode_(x);
      if (k && keys.indexOf(k) === -1) keys.push(k);
    });

    if (!orderNo && !trackingNo && !returnTrackingNo && !sku) continue;

    rows.push({
      sourceSheet: src.sheet.getName(),
      sourceRow: i + 1,
      sourceReturnId: retId,
      orderNo: String(orderNo || ''),
      trackingNo: String(trackingNo || ''),
      returnTrackingNo: String(returnTrackingNo || ''),
      marketplaceSku: String(sku || ''),
      expectedItemName: String(item || ''),
      expectedQty: qty || 1,
      marketplaceStatus: String(status || ''),
      qcStatus: String(qcStatus || ''),
      storeName: String(storeName || ''),
      productName: String(productName || ''),
      variationName: String(variationName || ''),
      orderDate: orderDate || '',
      tglPesan: orderDate || '',
      returnArrivedAt: returnArrivedAt || '',
      tglSampai: returnArrivedAt || '',
      scanKeys: keys
    });
  }

  try { cache.put('RQC_RETUR_ROWS_V5', JSON.stringify(rows), RQC_CFG.CACHE_SECONDS); } catch(e) {}
  return rows;
}

function RQC_getReturSourceSheet_() {
  var sheetName = 'Omni_Retur';
  var candidates = [];
  var omniOverride = String(RQC_CFG.OMNI_SPREADSHEET_ID_OVERRIDE || '').trim();
  if (omniOverride) {
    try {
      var oid = RQC_extractSpreadsheetId_(omniOverride) || omniOverride;
      candidates.push({ ss: SpreadsheetApp.openById(oid), spreadsheetName: 'OMNI_OVERRIDE' });
    } catch(e) { RQC_logError_('RQC_getReturSourceSheet_.omniOverride', e, { override: omniOverride }); }
  }
  try { candidates.push({ ss: RQC_openModuleByCodes_(RQC_CFG.OMNI_MODULE_CODES).ss, spreadsheetName: 'OMNI' }); } catch(e) {}
  // Fallback hanya kalau arsitektur user sengaja menaruh Omni_Retur di file Retur QC.
  try { candidates.push({ ss: RQC_selfSs_(), spreadsheetName: 'RETUR_QC_FALLBACK' }); } catch(e) {}

  for (var c = 0; c < candidates.length; c++) {
    var sh = candidates[c].ss.getSheetByName(sheetName);
    if (sh) return { sheet: sh, spreadsheetName: candidates[c].spreadsheetName };
  }
  throw new Error('Sheet sumber retur Omni_Retur tidak ditemukan di file Omnichannel. Data_Retur_AppSheet sudah tidak dipakai runtime.');
}

function RQC_getMasterItems_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('RQC_MASTER_ITEMS_V3');
  if (cached) return JSON.parse(cached);

  var master = RQC_masterSs_();
  var s = RQC_getSheetByKey_(master, 'MASTER_ITEM');
  if (!s) throw new Error('Master_Item tidak ditemukan di Master Database. Cek nama sheet harus Master_Item.');
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  var list = [];
  var seen = {};

  function statusAllowed(statusRaw) {
    return RQC_statusAllowed_(statusRaw);
  }

  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    var status = RQC_pickCell_(r, h, ['Status','Item_Status','Is_Active','Aktif']);
    if (!statusAllowed(status)) continue;

    var name = String(RQC_pickCell_(r, h, [
      'Item_Name','Nama_Item','Nama Item','Nama_Barang','Nama Barang','Nama_Produk','Nama Produk',
      'Internal_Item_Name','Internal Item Name','Item','Produk','SKU_Name','SKU Name'
    ]) || '').trim();

    // Fallback: kalau header master item user berbeda tapi ada Item_Code + nama di kolom lain,
    // ambil kolom teks paling masuk akal setelah ID/Code.
    if (!name) {
      for (var c = 0; c < table.headers.length; c++) {
        var hh = RQC_normHeader_(table.headers[c]);
        if (['item_id','id','item_code','kode_item','kode','status','notes','catatan'].indexOf(hh) !== -1) continue;
        var val = String(r[c] || '').trim();
        if (val && isNaN(Number(val)) && val.length >= 3) { name = val; break; }
      }
    }

    if (!name || seen[name]) continue;
    seen[name] = true;
    list.push({
      nama: name,
      kat: String(RQC_pickCell_(r, h, ['Category','Kategori','Item_Category','Kategori_Item']) || 'Umum'),
      sub: String(RQC_pickCell_(r, h, ['Subcategory','Sub_Category','Sub Category','Sub Kategori','Sub-Kategori','Sub','SubKategori','Sub_Kategori']) || '')
    });
  }
  list.sort(function(a,b) { return a.nama.localeCompare(b.nama); });
  try { cache.put('RQC_MASTER_ITEMS_V3', JSON.stringify(list), RQC_CFG.CACHE_SECONDS); } catch(e) {}
  return list;
}

// =================================================================================
// SESSIONS & LINES
// =================================================================================
function RQC_getOrCreateActiveSession_(forceNew, notes) {
  var ss = RQC_selfSs_();
  var s = RQC_ensureSheetByKey_(ss, 'SESSION', [
    'Session_ID','Session_Date','Session_Status','Started_By','Posted_At','Posted_By',
    'Total_Package','Total_Pass_Qty','Movement_Batch_ID','Notes'
  ]);
  if (!forceNew) {
    var table = RQC_getTable_(s);
    var h = table.headerMap;
    for (var i = table.values.length - 1; i >= 1; i--) {
      var r = table.values[i];
      if (String(RQC_getCell_(r, h, 'Session_Status') || '').toUpperCase() === 'DRAFT') {
        return RQC_rowToObject_(r, table.headers);
      }
    }
  }
  var id = 'RQS-' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd-HHmmss');
  var obj = {
    Session_ID: id,
    Session_Date: new Date(),
    Session_Status: 'DRAFT',
    Started_By: RQC_userEmail_(),
    Posted_At: '',
    Posted_By: '',
    Total_Package: 0,
    Total_Pass_Qty: 0,
    Movement_Batch_ID: '',
    Notes: notes || ''
  };
  RQC_appendObjects_(s, [obj]);
  return obj;
}

function RQC_getSessionById_(sessionId) {
  var s = RQC_getSheetByKey_(RQC_selfSs_(), 'SESSION');
  if (!s) return null;
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  for (var i = 1; i < table.values.length; i++) {
    if (RQC_getCell_(table.values[i], h, 'Session_ID') === sessionId) return RQC_rowToObject_(table.values[i], table.headers);
  }
  return null;
}

function RQC_updateSession_(sessionId, patch) {
  var s = RQC_getSheetByKey_(RQC_selfSs_(), 'SESSION');
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  for (var i = 1; i < table.values.length; i++) {
    if (RQC_getCell_(table.values[i], h, 'Session_ID') === sessionId) {
      Object.keys(patch).forEach(function(k) {
        var col = RQC_colFromMap_(h, k);
        if (col > 0) s.getRange(i + 1, col).setValue(patch[k]);
      });
      return true;
    }
  }
  return false;
}

function RQC_getSessionLines_(sessionId, limit) {
  var s = RQC_getSheetByKey_(RQC_selfSs_(), 'LINE');
  if (!s) return [];
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  var res = [];
  for (var i = table.values.length - 1; i >= 1; i--) {
    var r = table.values[i];
    if (RQC_getCell_(r, h, 'Session_ID') !== sessionId) continue;
    res.push(RQC_rowToObject_(r, table.headers));
    if (limit && res.length >= limit) break;
  }
  return res;
}

function RQC_countSessionStats_(sessionId) {
  var lines = RQC_getSessionLines_(sessionId, 0);
  var stats = { totalScan: 0, passCount: 0, holdCount: 0, passQty: 0, unpostedPassQty: 0 };
  lines.forEach(function(l) {
    stats.totalScan++;
    var result = String(l.QC_Result || '').toUpperCase();
    var qty = RQC_toNumber_(l.Actual_Qty);
    var posted = String(l.Posted_Flag || '').toUpperCase() === 'TRUE';
    if (result === 'PASS' || result === 'PARTIAL_PASS') {
      stats.passCount++;
      stats.passQty += qty;
      if (!posted) stats.unpostedPassQty += qty;
    } else {
      stats.holdCount++;
    }
  });
  return stats;
}

function RQC_findLineInSessionByScan_(sessionId, code) {
  code = RQC_normCode_(code);
  if (!code) return null;
  var s = RQC_getSheetByKey_(RQC_selfSs_(), 'LINE');
  if (!s) return null;
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    if (RQC_getCell_(r, h, 'Session_ID') !== sessionId) continue;
    var keys = [RQC_getCell_(r, h, 'Scanned_Code'), RQC_getCell_(r, h, 'Tracking_No'), RQC_getCell_(r, h, 'Return_Tracking_No'), RQC_getCell_(r, h, 'Order_No')].map(RQC_normCode_);
    if (keys.indexOf(code) !== -1) return RQC_rowToObject_(r, table.headers);
  }
  return null;
}


function RQC_getScannedReturnIndex_() {
  var idx = { source: {}, retId: {}, codes: {}, qcStatusDone: {} };
  var ss = RQC_selfSs_();
  var s = RQC_getSheetByKey_(ss, 'LINE');
  if (!s) return idx;
  var table = RQC_getTable_(s);
  var h = table.headerMap;

  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    var sourceSheet = String(RQC_getCell_(r, h, 'Source_Sheet') || '').trim();
    var sourceRow = String(RQC_getCell_(r, h, 'Source_Row') || '').trim();
    var retId = String(RQC_getCell_(r, h, 'Source_Return_ID') || '').trim();
    if (sourceSheet && sourceRow) idx.source[sourceSheet + '#' + sourceRow] = true;
    if (retId) idx.retId[retId] = true;
    [
      RQC_getCell_(r, h, 'Scanned_Code'),
      RQC_getCell_(r, h, 'Tracking_No'),
      RQC_getCell_(r, h, 'Return_Tracking_No'),
      RQC_getCell_(r, h, 'Order_No')
    ].forEach(function(v) {
      var k = RQC_normCode_(v);
      if (k) idx.codes[k] = true;
    });
  }
  return idx;
}

function RQC_isReturRowScanned_(row, scanIndex) {
  if (!row) return false;
  var qc = String(row.qcStatus || '').trim().toUpperCase();
  // Status dari sumber yang sudah pernah di-update QC dianggap sudah ditangani.
  var doneTokens = ['SCANNED','PASS','PARTIAL_PASS','MISMATCH','DAMAGED','HOLD','UNKNOWN_RESI','POSTED','RETURN_IN'];
  for (var i = 0; i < doneTokens.length; i++) {
    if (qc.indexOf(doneTokens[i]) !== -1) return true;
  }
  if (row.sourceSheet && row.sourceRow && scanIndex.source[row.sourceSheet + '#' + row.sourceRow]) return true;
  if (row.sourceReturnId && scanIndex.retId[row.sourceReturnId]) return true;
  var keys = row.scanKeys || [];
  for (var k = 0; k < keys.length; k++) {
    if (scanIndex.codes[RQC_normCode_(keys[k])]) return true;
  }
  return false;
}

// =================================================================================
// SOURCE STATUS UPDATE
// =================================================================================
function RQC_updateReturnSourceStatus_(sheetName, rowNumber, status, sessionId, stage) {
  try {
    var src = RQC_getReturSourceSheet_();
    // v2.0: runtime source hanya Omni_Retur. Kalau line lama masih menunjuk Data_Retur_AppSheet, abaikan.
    if (src.sheet.getName() !== sheetName || sheetName !== 'Omni_Retur') return;
    var info = RQC_headerInfo_(src.sheet);
    var now = new Date();
    var patch = {
      QC_Status: status,
      'Status Scan AppSheet': status,
      Status_QC: status,
      QC_Session_ID: sessionId,
      QC_At: now,
      QC_By: RQC_userEmail_(),
      ERP_QC_Stage: stage || '',
      QC_Source: 'RETUR_QC_MODULE',
      Gudang_Action: stage === 'POSTED' ? 'RETURN_IN_POSTED' : 'QC_SCANNED',
      Finance_Status: stage === 'POSTED' ? 'READY_FOR_FINANCE_REFERENCE' : 'REFERENCE_ONLY',
      Updated_At: now,
      Updated_By: RQC_userEmail_()
    };
    Object.keys(patch).forEach(function(k) {
      var col = RQC_col_(info, k);
      if (col > 0) src.sheet.getRange(rowNumber, col).setValue(patch[k]);
    });
  } catch(e) {
    RQC_logError_('RQC_updateReturnSourceStatus_', e, { sheetName: sheetName, rowNumber: rowNumber, status: status });
  }
}

// =================================================================================
// SPREADSHEET HELPERS
// =================================================================================
function RQC_masterSs_() { return SpreadsheetApp.openById(RQC_CFG.MASTER_SPREADSHEET_ID); }
function RQC_selfSs_() {
  // v1.5: jangan buka ActiveSpreadsheet dulu.
  // Di project kamu, ActiveSpreadsheet kadang membawa gid tab lama (contoh 1865962240)
  // sehingga Apps Script melempar: Sheet 1865962240 not found.
  // Jadi self spreadsheet wajib dibuka lewat Master_Module / override lebih dulu.
  var debug = [];

  var override = String(RQC_CFG.RETUR_QC_SPREADSHEET_ID_OVERRIDE || '').trim();
  if (override) {
    try {
      var oid = RQC_extractSpreadsheetId_(override) || override;
      return SpreadsheetApp.openById(oid);
    } catch (e0) {
      debug.push('override gagal: ' + (e0.message || e0));
    }
  }

  try {
    var routed = RQC_openModuleByCodes_([RQC_CFG.MODULE_CODE, 'RETUR_QC', 'RETUR QC', 'RETURN_QC', 'RETURN QC', 'RETUR']);
    if (routed && routed.ss) return routed.ss;
  } catch (e1) {
    debug.push('Master_Module RETUR_QC gagal: ' + (e1.message || e1));
  }

  // Fallback terakhir saja, dan errornya ditangkap supaya tidak muncul lagi "Sheet gid not found" mentah.
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    if (ss) return ss;
    debug.push('ActiveSpreadsheet kosong/null.');
  } catch (e2) {
    debug.push('ActiveSpreadsheet error: ' + (e2.message || e2));
  }

  throw new Error(
    'Spreadsheet Modul Retur QC tidak bisa dibuka. Tambahkan baris di Master_Module: ' +
    'Module_Code=RETUR_QC, Module_Name=Retur QC, Spreadsheet_ID=ID spreadsheet Retur QC, Status=ACTIVE/NEW_CORE. ' +
    'Detail: ' + debug.join(' || ')
  );
}

function RQC_openGudangModule_() {
  var override = String(RQC_CFG.GUDANG_SPREADSHEET_ID_OVERRIDE || '').trim();
  if (override) {
    var id = RQC_extractSpreadsheetId_(override) || override;
    return { code: 'WH', ss: SpreadsheetApp.openById(id), source: 'GUDANG_SPREADSHEET_ID_OVERRIDE' };
  }
  return RQC_openModuleByCodes_(RQC_CFG.GUDANG_MODULE_CODES);
}

function RQC_openModuleByCodes_(codes) {
  var master = RQC_masterSs_();
  var s = RQC_getSheetByKey_(master, 'MASTER_MODULE');
  if (!s) throw new Error('Master_Module tidak ditemukan.');
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  var wanted = (codes || []).map(function(x) { return String(x || '').trim().toUpperCase(); }).filter(String);
  var aliases = {
    WH: ['WH','GUDANG','WAREHOUSE','INVENTORY','MODUL GUDANG'],
    GUDANG: ['WH','GUDANG','WAREHOUSE','INVENTORY','MODUL GUDANG'],
    WAREHOUSE: ['WH','GUDANG','WAREHOUSE','INVENTORY','MODUL GUDANG'],
    OMNI: ['OMNI','OMNICHANNEL','RETAIL','RETAIL OMNI','MODUL RETAIL'],
    OMNICHANNEL: ['OMNI','OMNICHANNEL','RETAIL','RETAIL OMNI','MODUL RETAIL'],
    RETAIL: ['OMNI','OMNICHANNEL','RETAIL','RETAIL OMNI','MODUL RETAIL'],
    RETUR_QC: ['RETUR_QC','RETUR QC','RETURN','QC RETUR']
  };
  var expanded = {};
  wanted.forEach(function(w) {
    expanded[w] = true;
    (aliases[w] || []).forEach(function(a) { expanded[String(a).toUpperCase()] = true; });
  });
  var expandedList = Object.keys(expanded);
  var rowsDebug = [];

  function statusAllowed_(statusRaw) {
    return RQC_statusAllowed_(statusRaw);
  }

  // Pass 1: exact Module_Code match, e.g. WH.
  for (var pass = 1; pass <= 2; pass++) {
    for (var i = 1; i < table.values.length; i++) {
      var r = table.values[i];
      var status = String(RQC_getCell_(r, h, 'Status') || '').trim();
      var code = String(RQC_getCell_(r, h, 'Module_Code') || '').trim().toUpperCase();
      var name = String(RQC_getCell_(r, h, 'Module_Name') || '').trim().toUpperCase();
      if (!statusAllowed_(status)) {
        rowsDebug.push(code + '/' + name + ' status=' + status + ' SKIP');
        continue;
      }
      var matched = false;
      if (pass === 1) {
        matched = expandedList.indexOf(code) !== -1;
      } else {
        matched = expandedList.some(function(w) { return name.indexOf(w) !== -1 || code.indexOf(w) !== -1; });
      }
      rowsDebug.push(code + '/' + name + ' status=' + status + ' match=' + matched);
      if (!matched) continue;

      var id = String(RQC_getCell_(r, h, 'Spreadsheet_ID') || '').trim();
      if (!id) id = RQC_extractSpreadsheetId_(RQC_getCell_(r, h, 'Spreadsheet_URL'));
      if (!id) throw new Error('Spreadsheet_ID kosong untuk module ' + (code || name));
      return { code: code || name, name: name, ss: SpreadsheetApp.openById(id), source: 'Master_Module' };
    }
  }
  throw new Error('Module tidak ditemukan di Master_Module: ' + wanted.join('/') + '. Baris terbaca: ' + rowsDebug.slice(0, 20).join(' || '));
}

function RQC_extractSpreadsheetId_(url) {
  url = String(url || '').trim();
  var m = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return m ? m[1] : '';
}

function RQC_ensureSheet_(ss, name, headers) {
  var safeName = String(name || '').trim();
  if (!safeName) throw new Error('Nama sheet kosong.');
  if (/^\d+$/.test(safeName) || /gid=\d+/i.test(safeName)) {
    throw new Error('Nama sheet invalid karena berupa gid/angka: ' + safeName);
  }

  var s = ss.getSheetByName(safeName);
  if (!s) s = ss.insertSheet(safeName);

  headers = headers || [];
  if (s.getLastRow() === 0) {
    if (headers.length) {
      s.getRange(1, 1, 1, headers.length).setValues([headers]);
      s.setFrozenRows(1);
    }
    return s;
  }

  if (!headers.length) return s;

  var lastCol = Math.max(1, s.getLastColumn());
  var existing = s.getRange(1, 1, 1, lastCol).getValues()[0].map(function(x){
    return String(x || '').trim();
  });

  var toAdd = [];
  headers.forEach(function(h) {
    h = String(h || '').trim();
    if (h && existing.indexOf(h) === -1) toAdd.push(h);
  });

  if (toAdd.length) {
    s.getRange(1, existing.length + 1, 1, toAdd.length).setValues([toAdd]);
  }
  s.setFrozenRows(1);
  return s;
}

function RQC_getTable_(sheet) {
  var values = sheet.getDataRange().getValues();
  var headers = values.length ? values[0].map(function(h){ return String(h || '').trim(); }) : [];
  var headerMap = {};
  headers.forEach(function(h, i){ if (h) headerMap[RQC_normHeader_(h)] = i; });
  return { values: values, headers: headers, headerMap: headerMap };
}

function RQC_headerInfo_(sheet) {
  var headers = sheet.getRange(1, 1, 1, Math.max(1, sheet.getLastColumn())).getValues()[0].map(function(h){ return String(h || '').trim(); });
  var map = {};
  headers.forEach(function(h, i){ if (h) map[RQC_normHeader_(h)] = i + 1; });
  return { headers: headers, map: map };
}

function RQC_col_(info, header) { return info.map[RQC_normHeader_(header)] || 0; }
function RQC_colFromMap_(map, header) { var idx = map[RQC_normHeader_(header)]; return idx === undefined ? 0 : idx + 1; }
function RQC_getCell_(row, headerMap, header) { var idx = headerMap[RQC_normHeader_(header)]; return idx === undefined ? '' : row[idx]; }
function RQC_pickCell_(row, headerMap, headers) {
  for (var i = 0; i < headers.length; i++) {
    var idx = headerMap[RQC_normHeader_(headers[i])];
    if (idx !== undefined && row[idx] !== '' && row[idx] !== null && row[idx] !== undefined) return row[idx];
  }
  return '';
}
function RQC_rowToObject_(row, headers) { var o = {}; headers.forEach(function(h, i){ if(h) o[h] = row[i]; }); return o; }

function RQC_appendObjects_(sheet, objects) {
  if (!objects || objects.length === 0) return;
  var info = RQC_headerInfo_(sheet);
  var rows = objects.map(function(obj) { return info.headers.map(function(h) { return obj[h] !== undefined ? obj[h] : ''; }); });
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, info.headers.length).setValues(rows);
}

function RQC_stockMovementHeaders_() {
  // Kontrak Gudang v2.5. Retur QC menulis langsung ke sheet Gudang dengan format yang sama
  // seperti postReturQcReadyToStock() supaya Finance bisa baca RETURN_IN bersih.
  return [
    'Movement_ID','Tx_Key','Tanggal','Source_Date','Item_ID','Item_Name','Item_Category','Item_Type','Unit',
    'Warehouse_Code','Direction','Movement_Type','Qty','Unit_Cost',
    'Cost_Period','Cost_Status','Unit_Cost_Provisional','Value_Provisional','Unit_Cost_Final','Value_Final',
    'Cost_Source','Cost_Synced_At','Closed_At','Closed_By',
    'Source_Module','Source_ID','Source_Line_ID','Ref_No','Batch_ID','External_Ref','Notes','Status','Created_At','Created_By','Is_Deleted'
  ];
}

function RQC_stockContractVersion_() { return 'WH_STOCK_MOVEMENT_CONTRACT_V2'; }

function RQC_stockTxKey_(input) {
  function key(v) { return String(v === null || v === undefined ? '' : v).trim().toUpperCase().replace(/\s+/g, ' '); }
  return [
    RQC_stockContractVersion_(),
    input.Source_Module || 'RETUR_QC',
    input.Movement_Type || 'RETURN_IN',
    input.Source_ID || '',
    input.Source_Line_ID || '',
    input.Ref_No || '',
    input.Direction || 'IN',
    input.Item_ID || input.Item_Name || '',
    input.Source_Date || '',
    String(RQC_toNumber_(input.Qty || 0))
  ].map(key).join('|');
}

function RQC_readStockMovementKeySet_(smSheet) {
  var out = {};
  if (!smSheet || smSheet.getLastRow() < 2) return out;
  var info = RQC_headerInfo_(smSheet);
  var cTx = RQC_col_(info, 'Tx_Key');
  var cMov = RQC_col_(info, 'Movement_ID');
  var cDel = RQC_col_(info, 'Is_Deleted');
  var vals = smSheet.getRange(2, 1, smSheet.getLastRow() - 1, smSheet.getLastColumn()).getValues();
  vals.forEach(function(r) {
    var del = cDel > 0 ? RQC_key_(r[cDel - 1]) : '';
    if (del === 'TRUE' || del === 'YA' || del === '1') return;
    var tx = cTx > 0 ? RQC_clean_(r[cTx - 1]) : '';
    var mov = cMov > 0 ? RQC_clean_(r[cMov - 1]) : '';
    if (tx) out[tx] = true;
    if (mov) out['MOVEMENT_ID|' + mov] = true;
  });
  return out;
}

function RQC_masterItemMetaMap_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('RQC_MASTER_ITEM_META_V1');
  if (cached) return JSON.parse(cached);

  var out = { byName:{}, byId:{} };
  var s = RQC_getSheetByKey_(RQC_masterSs_(), 'MASTER_ITEM');
  if (!s) return out;
  var table = RQC_getTable_(s);
  var h = table.headerMap;
  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    var status = RQC_pickCell_(r, h, ['Status','Item_Status','Is_Active','Aktif']);
    if (!RQC_statusAllowed_(status)) continue;
    var name = String(RQC_pickCell_(r, h, ['Item_Name','Nama_Item','Nama Item','Nama_Barang','Nama Barang','Nama_Produk','Nama Produk','Internal_Item_Name','Internal Item Name','Item','Produk','SKU_Name','SKU Name']) || '').trim();
    var id = String(RQC_pickCell_(r, h, ['Item_ID','Item Id','ID Item','Kode Item','Item_Code','SKU','Kode_SKU']) || '').trim();
    if (!name) continue;
    var obj = {
      Item_ID: id || name,
      Item_Name: name,
      Item_Category: String(RQC_pickCell_(r, h, ['Category','Kategori','Item_Category','Kategori_Item']) || ''),
      Item_Type: String(RQC_pickCell_(r, h, ['Item_Type','Tipe_Item','Tipe Item','Type','Jenis']) || ''),
      Unit: String(RQC_pickCell_(r, h, ['Unit','Satuan','UOM']) || 'PCS'),
      Default_Cost: RQC_toNumber_(RQC_pickCell_(r, h, ['Default_Cost','HPP','Unit_Cost','Harga_Pokok','Harga Pokok']))
    };
    out.byName[RQC_key_(name)] = obj;
    if (id) out.byId[RQC_key_(id)] = obj;
  }
  try { cache.put('RQC_MASTER_ITEM_META_V1', JSON.stringify(out), RQC_CFG.CACHE_SECONDS); } catch(e) {}
  return out;
}

function RQC_findMasterItemMeta_(itemNameOrId) {
  var map = RQC_masterItemMetaMap_();
  var key = RQC_key_(itemNameOrId);
  return map.byName[key] || map.byId[key] || { Item_ID:String(itemNameOrId || ''), Item_Name:String(itemNameOrId || ''), Item_Category:'', Item_Type:'', Unit:'PCS', Default_Cost:0 };
}

function RQC_costPeriod_(v) {
  var d = RQC_parseDateLoose_(v) || new Date();
  return Utilities.formatDate(d, RQC_CFG.TZ || Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM');
}

function RQC_dateOnlyText_(v) {
  var d = RQC_parseDateLoose_(v) || new Date();
  return Utilities.formatDate(d, RQC_CFG.TZ || Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd');
}

function RQC_readGudangCostData_(gudangSs) {
  var sh = gudangSs.getSheetByName('Stock_Cost_Period');
  var out = { byId:{}, byName:{}, rows:[] };
  if (!sh || sh.getLastRow() < 2) return out;
  var table = RQC_getTable_(sh);
  var h = table.headerMap;
  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    var del = RQC_key_(RQC_pickCell_(r, h, ['Is_Deleted']));
    if (del === 'TRUE' || del === 'YA' || del === '1') continue;
    var period = String(RQC_pickCell_(r, h, ['Period','Cost_Period']) || '').trim();
    var itemId = String(RQC_pickCell_(r, h, ['Item_ID','Item Id']) || '').trim();
    var itemName = String(RQC_pickCell_(r, h, ['Item_Name','Item Name']) || '').trim();
    if (!period || (!itemId && !itemName)) continue;
    var obj = {
      Period: period,
      Item_ID: itemId,
      Item_Name: itemName,
      Unit_Cost_Provisional: RQC_toNumber_(RQC_pickCell_(r, h, ['Unit_Cost_Provisional','Provisional_Unit_Cost','Unit_Cost'])),
      Unit_Cost_Final: RQC_toNumber_(RQC_pickCell_(r, h, ['Unit_Cost_Final','Final_Unit_Cost'])),
      Cost_Status: String(RQC_pickCell_(r, h, ['Cost_Status','Status']) || 'PROVISIONAL').toUpperCase(),
      Source_Module: String(RQC_pickCell_(r, h, ['Source_Module']) || 'STOCK_COST_PERIOD'),
      Source_ID: String(RQC_pickCell_(r, h, ['Source_ID']) || ''),
      Synced_At: RQC_pickCell_(r, h, ['Synced_At']) || '',
      Closed_At: RQC_pickCell_(r, h, ['Closed_At']) || '',
      Closed_By: RQC_pickCell_(r, h, ['Closed_By']) || ''
    };
    out.rows.push(obj);
    if (itemId) out.byId[RQC_key_(itemId) + '|' + period] = obj;
    if (itemName) out.byName[RQC_key_(itemName) + '|' + period] = obj;
  }
  return out;
}

function RQC_findGudangCost_(costData, itemMeta, period) {
  period = String(period || RQC_costPeriod_(new Date()));
  var row = null;
  if (itemMeta && itemMeta.Item_ID) row = costData.byId[RQC_key_(itemMeta.Item_ID) + '|' + period];
  if (!row && itemMeta && itemMeta.Item_Name) row = costData.byName[RQC_key_(itemMeta.Item_Name) + '|' + period];
  if (!row) {
    var itemId = itemMeta && itemMeta.Item_ID ? RQC_key_(itemMeta.Item_ID) : '';
    var itemName = itemMeta && itemMeta.Item_Name ? RQC_key_(itemMeta.Item_Name) : '';
    var candidates = (costData.rows || []).filter(function(x) {
      var same = (itemId && RQC_key_(x.Item_ID) === itemId) || (itemName && RQC_key_(x.Item_Name) === itemName);
      return same && String(x.Period || '') <= period;
    }).sort(function(a, b) { return String(a.Period) < String(b.Period) ? 1 : -1; });
    row = candidates[0] || null;
  }
  var status = row && row.Cost_Status === 'FINAL' && RQC_toNumber_(row.Unit_Cost_Final) > 0 ? 'FINAL' : 'PROVISIONAL';
  var prov = row ? (RQC_toNumber_(row.Unit_Cost_Provisional) || RQC_toNumber_(row.Unit_Cost_Final)) : RQC_toNumber_(itemMeta.Default_Cost);
  var finalCost = status === 'FINAL' ? (RQC_toNumber_(row.Unit_Cost_Final) || prov) : 0;
  var unit = status === 'FINAL' ? finalCost : prov;
  return {
    Cost_Period: period,
    Cost_Status: status,
    Unit_Cost: unit || 0,
    Unit_Cost_Provisional: prov || 0,
    Unit_Cost_Final: status === 'FINAL' ? finalCost : '',
    Cost_Source: row ? ((row.Source_Module || 'STOCK_COST_PERIOD') + (row.Source_ID ? '|' + row.Source_ID : '')) : 'MASTER_ITEM',
    Cost_Synced_At: row && row.Synced_At ? row.Synced_At : new Date(),
    Closed_At: row && status === 'FINAL' ? row.Closed_At : '',
    Closed_By: row && status === 'FINAL' ? row.Closed_By : ''
  };
}

// =================================================================================
// SECURITY, SESSION, HEARTBEAT & LOG
// =================================================================================
function RQC_requirePassportFromArgs_(args) {
  var a = Array.prototype.slice.call(args || []);
  return RQC_requirePassport_(a.length >= 2 ? a[a.length - 2] : '', a.length >= 1 ? a[a.length - 1] : '');
}

function RQC_requirePassport_(emailOp, pasporOp) {
  emailOp = RQC_normEmail_(emailOp || '');
  pasporOp = RQC_clean_(pasporOp || '');
  if (!emailOp || !pasporOp) throw new Error('Sesi Retur QC tidak lengkap. Masuk ulang dari Portal.');
  var auth = RQC_securityCheck_(emailOp, pasporOp, true);
  if (!auth || !auth.allowed) throw new Error('Akses Retur QC ditolak: ' + (auth && auth.reason ? auth.reason : 'UNKNOWN'));
  if (auth.email && emailOp && RQC_normEmail_(auth.email) !== emailOp) throw new Error('Passport tidak cocok dengan email aktif. Masuk ulang dari Portal.');
  RQC_RUNTIME_EMAIL = auth.email || emailOp;
  return auth;
}

function RQC_doGetAccess_(e) {
  var p = (e && e.parameter) || {};
  var email = RQC_normEmail_(p.vouch || p.email || p.user || '');
  var passport = RQC_clean_(p.paspor || p.passport || p.token || '');
  var auth = RQC_securityCheck_(email, passport, true);
  if (auth.allowed) {
    auth.passport = passport;
    auth.passportId = passport;
    RQC_RUNTIME_EMAIL = auth.email || email;
  }
  return auth;
}

function RQC_forbiddenOutput_(auth) {
  var portal = RQC_withLoginParam_(RQC_getPortalUrl_());
  var btn = portal ? '<p><a style="display:inline-block;background:#1677ff;color:white;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:800" href="'+RQC_escape_(portal)+'" target="_top">Kembali ke Portal</a></p>' : '';
  return HtmlService.createHtmlOutput('<base target="_top"><div style="font-family:Arial,sans-serif;text-align:center;margin-top:13vh;background:#f8fafc;padding:48px;border-radius:22px;max-width:680px;margin-left:auto;margin-right:auto;box-shadow:0 10px 25px rgba(0,0,0,.12)"><div style="font-size:78px">⛔</div><h1 style="color:#ef4444">AKSES / SESSION DITOLAK</h1><p>Alasan: <b>'+RQC_escape_(auth && auth.reason || 'UNKNOWN')+'</b></p><p>Email: <b>'+RQC_escape_(auth && auth.email || '(kosong)')+'</b></p><p>Silakan masuk dari Portal/Beranda supaya paspor session valid.</p>'+btn+'</div>').setTitle('Akses Ditolak');
}

function RQC_securityCheck_(emailOp, pasporOp, passportRequired) {
  emailOp = RQC_normEmail_(emailOp || RQC_userEmail_() || '');
  if (!emailOp) return { allowed:false, reason:'EMAIL_KOSONG', email:'' };

  var user = RQC_findUser_(emailOp);
  if (!user) return { allowed:false, reason:'USER_TIDAK_ADA_DI_MASTER_USER', email:emailOp };
  if (!RQC_isActive_(RQC_pickObj_(user, ['Status','Status_Akun','Aktif']))) return { allowed:false, reason:'USER_NONAKTIF', email:emailOp, status:RQC_pickObj_(user, ['Status','Status_Akun','Aktif']) || '' };

  pasporOp = RQC_clean_(pasporOp || '');
  if (passportRequired) {
    var pv = RQC_validatePassport_(emailOp, pasporOp);
    if (!pv.ok) return { allowed:false, reason:'PASPOR_' + pv.reason, email:emailOp, passportId:pasporOp };
  } else if (pasporOp) {
    var pv2 = RQC_validatePassport_(emailOp, pasporOp);
    if (!pv2.ok) return { allowed:false, reason:'PASPOR_' + pv2.reason, email:emailOp, passportId:pasporOp };
  }

  var role = RQC_pickObj_(user, ['Role','Jabatan','Hak_Akses','Akses']) || '';
  var department = RQC_pickObj_(user, ['Department','Departemen','Divisi','Dept']) || '';
  var allowedModules = RQC_pickObj_(user, ['Allowed_Modules','Allowed Modules','Module_Access','Hak_Modul','Akses_Modul','Akses Modul','Access','Modul','Notes']) || '';
  var isAdmin = RQC_key_(role).indexOf('ADMIN') !== -1 || RQC_key_(department).indexOf('ADMIN') !== -1 || RQC_key_(allowedModules).indexOf('SUPERADMIN') !== -1 || RQC_key_(allowedModules).indexOf('ALL') !== -1;
  var can = isAdmin || RQC_userCanOpenModule_({ allowedModules:allowedModules, role:role, department:department }, RQC_CFG.MODULE_CODE, 'Retur QC', RQC_CFG.MODULE_ALIASES || []);
  return {
    allowed: can,
    reason: can ? 'OK' : 'MODULE_ACCESS_DENIED',
    email: emailOp,
    displayName: RQC_userDisplayName_(user, emailOp),
    role: role,
    department: department,
    allowedModules: allowedModules,
    isAdmin: isAdmin,
    passport: pasporOp,
    passportId: pasporOp
  };
}

function RQC_validatePassport_(email, paspor) {
  var p = RQC_parsePassport_(paspor);
  if (!p.stamp || !p.hash) return { ok:false, reason:'FORMAT_TIDAK_VALID' };
  if (p.hash !== RQC_hashPassport_(email, p.stamp)) return { ok:false, reason:'HASH_TIDAK_VALID' };
  if (Date.now() - p.stamp > RQC_CFG.SESSION_TTL_MS) return { ok:false, reason:'EXPIRED' };
  var lastLogout = RQC_getLastLogoutStamp_(email);
  if (lastLogout && p.stamp < lastLogout) return { ok:false, reason:'GLOBAL_LOGOUT' };
  return { ok:true, stamp:p.stamp };
}
function RQC_parsePassport_(paspor) {
  var raw = RQC_clean_(paspor);
  var m = raw.match(/^(\d{10,}):([a-f0-9]{64})$/i);
  return m ? { stamp:Number(m[1]) || 0, hash:String(m[2] || '').toLowerCase() } : { stamp:0, hash:raw.toLowerCase() };
}
function RQC_hashPassport_(email, stamp) {
  var raw = RQC_normEmail_(email) + '|' + Number(stamp || 0) + '|' + RQC_CFG.SHARED_SECRET;
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw)
    .map(function(b){ return (b < 0 ? b + 256 : b).toString(16).padStart(2, '0'); })
    .join('');
}

function RQC_findUser_(email) {
  var s = RQC_getSheetByKey_(RQC_masterSs_(), 'MASTER_USER');
  if (!s) throw new Error('Master_User tidak ditemukan.');
  var table = RQC_getTable_(s);
  email = RQC_normEmail_(email);
  for (var i = 1; i < table.values.length; i++) {
    var row = RQC_rowToObject_(table.values[i], table.headers);
    var em = RQC_normEmail_(RQC_pickObj_(row, ['Email','Email_Google','Gmail','Email_User','User_Email','Username','User Email']));
    if (em === email) return row;
  }
  return null;
}
function RQC_userDisplayName_(user, email) {
  return RQC_clean_(RQC_pickObj_(user || {}, ['Display_Name','Display Name','Nama','Nama_User','Nama User','Nama_Lengkap','Nama Lengkap','Name','User_Name','Username'])) || RQC_clean_(email);
}
function RQC_userCanOpenModule_(auth, code, name, extraAliases) {
  var fields = [auth.allowedModules, auth.role, auth.department].map(RQC_key_).join('|');
  if (fields.indexOf('ALL') !== -1 || fields.indexOf('SUPERADMIN') !== -1) return true;
  var targets = [code, name || ''].concat(extraAliases || []).map(RQC_key_);
  return targets.some(function(t){ return t && fields.indexOf(t) !== -1; });
}
function RQC_pickObj_(obj, aliases) {
  var m = {};
  Object.keys(obj || {}).forEach(function(k){ m[RQC_normHeader_(k)] = obj[k]; });
  for (var i = 0; i < (aliases || []).length; i++) {
    var key = RQC_normHeader_(aliases[i]);
    if (m[key] !== undefined) return m[key];
  }
  return '';
}

function RQC_userEmail_() {
  if (RQC_RUNTIME_EMAIL) return RQC_RUNTIME_EMAIL;
  try { return RQC_normEmail_(Session.getActiveUser().getEmail() || ''); } catch(e) { return ''; }
}

function RQC_userHasAccess_(email) {
  var auth = RQC_securityCheck_(email, '', false);
  return !!(auth && auth.allowed);
}

function ERP_globalHeartbeat(clientVersion, emailOp, pasporOp) {
  if (arguments.length >= 4) {
    clientVersion = arguments[1];
    emailOp = arguments[2];
    pasporOp = arguments[3] || arguments[0] || '';
  }
  var auth = RQC_securityCheck_(emailOp, pasporOp, true);
  if (!auth.allowed) return { ok:false, success:false, reason:auth.reason || 'SESSION_INVALID', shouldLogout:true, portalUrl:RQC_withLoginParam_(RQC_getPortalUrl_()) };
  RQC_RUNTIME_EMAIL = auth.email || '';
  var hb = RQC_readGlobalHeartbeat_();
  return {
    ok: true,
    success: true,
    reason: auth.reason,
    shouldLogout: false,
    moduleCode: RQC_CFG.MODULE_CODE,
    passport: pasporOp || auth.passport || auth.passportId || '',
    paspor: pasporOp || auth.passport || auth.passportId || '',
    userEmail: auth.email || '',
    displayName: auth.displayName || auth.email || '',
    user: { email: auth.email || '', name: auth.displayName || auth.email || '', role: auth.role || '', department: auth.department || '' },
    serverVersion: hb.version,
    updatedAt: hb.updatedAt,
    shouldRefresh: !!clientVersion && String(clientVersion) !== String(hb.version),
    portalUrl: RQC_withLoginParam_(RQC_getPortalUrl_()),
    session: RQC_sessionInfoFromToken_(auth.email, pasporOp || auth.passport || auth.passportId || ''),
    now: RQC_formatDateTime_(new Date())
  };
}

function ERP_globalLogout(passportId, emailOp, pasporOp) {
  var paspor = pasporOp || passportId || '';
  var auth = RQC_securityCheck_(emailOp, paspor, true);
  if (!auth.allowed) return { success:false, ok:false, reason:auth.reason || 'SESSION_INVALID', portalUrl:RQC_withLoginParam_(RQC_getPortalUrl_()) };
  RQC_markLogout_(auth.email, Date.now());
  try { RQC_bumpGlobalHeartbeat_('Logout ' + auth.email + ' from ' + RQC_CFG.MODULE_CODE); } catch(e) {}
  return { success:true, ok:true, portalUrl:RQC_withLoginParam_(RQC_getPortalUrl_()), message:'Logout berhasil.' };
}

function RQC_touchMutation_(reason) { try { RQC_bumpGlobalHeartbeat_((reason || 'Data changed') + ' @ ' + RQC_CFG.MODULE_CODE); } catch(e) {} }
function RQC_readGlobalHeartbeat_() {
  try {
    var sh = RQC_getSheetByKey_(RQC_masterSs_(), 'MASTER_MODULE');
    if (!sh) return { version:'0', updatedAt:'', notes:'Master_Module tidak ditemukan' };
    var version = String(sh.getRange(RQC_CFG.HEARTBEAT_CELL).getValue() || '0');
    return { version: version, updatedAt: RQC_formatDateTime_(sh.getRange(RQC_CFG.HEARTBEAT_UPDATED_CELL).getValue()), notes: String(sh.getRange(RQC_CFG.HEARTBEAT_NOTES_CELL).getValue() || '') };
  } catch(e) { return { version:'0', updatedAt:'', notes:e.message || String(e) }; }
}
function RQC_bumpGlobalHeartbeat_(notes) {
  var sh = RQC_getSheetByKey_(RQC_masterSs_(), 'MASTER_MODULE');
  if (!sh) throw new Error('Master_Module tidak ditemukan untuk heartbeat.');
  var now = Date.now();
  sh.getRange(RQC_CFG.HEARTBEAT_CELL).setValue(now);
  sh.getRange(RQC_CFG.HEARTBEAT_UPDATED_CELL).setValue(new Date());
  sh.getRange(RQC_CFG.HEARTBEAT_NOTES_CELL).setValue(notes || ('Update from ' + RQC_CFG.MODULE_CODE));
  return RQC_readGlobalHeartbeat_();
}

function RQC_getPortalUrl_() {
  try {
    var links = RQC_readModuleLinksRaw_();
    for (var i = 0; i < links.length; i++) {
      var code = RQC_key_(links[i].code), name = RQC_key_(links[i].name);
      if (RQC_CFG.PORTAL_CODES.map(RQC_key_).indexOf(code) !== -1 || name.indexOf('PORTAL') !== -1 || name.indexOf('BERANDA') !== -1) return links[i].url;
    }
  } catch(e) {}
  return '';
}
function RQC_withLoginParam_(url) {
  url = RQC_clean_(url);
  if (!url) return '';
  return url + (url.indexOf('?') === -1 ? '?' : '&') + 'login=1';
}
function RQC_appendPassportToUrl_(url, auth, paspor) {
  url = RQC_clean_(url);
  if (!url) return '';
  var sep = url.indexOf('?') === -1 ? '?' : '&';
  return url + sep + 'vouch=' + encodeURIComponent(auth.email || '') + '&paspor=' + encodeURIComponent(paspor || auth.passport || auth.passportId || '') + '&passport=' + encodeURIComponent(paspor || auth.passport || auth.passportId || '') + '&from=' + encodeURIComponent(RQC_CFG.MODULE_CODE);
}
function RQC_readModuleLinksRaw_() {
  var sh = RQC_getSheetByKey_(RQC_masterSs_(), 'MASTER_MODULE');
  if (!sh) return [];
  var table = RQC_getTable_(sh);
  var h = table.headerMap;
  var out = [];
  for (var i = 1; i < table.values.length; i++) {
    var r = table.values[i];
    var status = String(RQC_getCell_(r, h, 'Status') || '').trim();
    if (!RQC_statusAllowed_(status)) continue;
    out.push({ code:RQC_clean_(RQC_getCell_(r, h, 'Module_Code')), name:RQC_clean_(RQC_getCell_(r, h, 'Module_Name')), url:RQC_clean_(RQC_getCell_(r, h, 'Web_App_URL')) });
  }
  return out.filter(function(x){ return x.code && x.url; });
}
function RQC_getLastLogoutStamp_(email) {
  try {
    var user = RQC_findUser_(email);
    if (!user) return 0;
    var raw = RQC_pickObj_(user, ['Last_Logout_At','Logout_At','Global_Logout_At','LastLogoutAt']);
    var d = RQC_parseDateLoose_(raw);
    return d ? d.getTime() : 0;
  } catch(e) { return 0; }
}
function RQC_markLogout_(email, stamp) {
  try {
    var sh = RQC_getSheetByKey_(RQC_masterSs_(), 'MASTER_USER');
    if (!sh) return;
    var vals = sh.getDataRange().getValues();
    if (vals.length < 2) return;
    var map = {};
    vals[0].forEach(function(h, i){ if (h) map[RQC_normHeader_(h)] = i; });
    var cEmail = map[RQC_normHeader_('Email')];
    if (cEmail === undefined) cEmail = map[RQC_normHeader_('User_Email')];
    if (cEmail === undefined) return;
    for (var r = 1; r < vals.length; r++) {
      if (RQC_normEmail_(vals[r][cEmail]) !== RQC_normEmail_(email)) continue;
      var patches = { Last_Logout_At:new Date(stamp || Date.now()), Logout_Reason:'USER_LOGOUT_FROM_' + RQC_CFG.MODULE_CODE };
      Object.keys(patches).forEach(function(k){ var c = map[RQC_normHeader_(k)]; if (c !== undefined) sh.getRange(r+1, c+1).setValue(patches[k]); });
      return;
    }
  } catch(e) {}
}
function RQC_sessionInfoFromToken_(email, paspor) {
  var p = RQC_parsePassport_(paspor);
  var lastLogout = RQC_getLastLogoutStamp_(email);
  return { loginAt: p.stamp ? RQC_formatDateTime_(new Date(p.stamp)) : '', expiresAt: p.stamp ? RQC_formatDateTime_(new Date(p.stamp + RQC_CFG.SESSION_TTL_MS)) : '', lastLogoutAt: lastLogout ? RQC_formatDateTime_(new Date(lastLogout)) : '', ttlHours: Math.round(RQC_CFG.SESSION_TTL_MS / 3600000) };
}

function TEST_returQcAccess() {
  var email = RQC_userEmail_();
  return {
    email: email,
    access: RQC_userHasAccess_(email),
    moduleCode: RQC_CFG.MODULE_CODE,
    masterId: RQC_CFG.MASTER_SPREADSHEET_ID,
    version: RQC_CFG.VERSION
  };
}

function RQC_logError_(functionName, error, payload) {
  try {
    var s = RQC_ensureSheetByKey_(RQC_masterSs_(), 'LOG_ERROR', ['Timestamp','Module_Code','Function_Name','Error_Message','Payload_JSON','User_Email','Status']);
    RQC_appendObjects_(s, [{
      Timestamp: new Date(),
      Module_Code: RQC_CFG.MODULE_CODE,
      Function_Name: functionName,
      Error_Message: error && error.stack ? error.stack : String(error && error.message ? error.message : error),
      Payload_JSON: JSON.stringify(payload || {}).slice(0, 30000),
      User_Email: RQC_userEmail_(),
      Status: 'OPEN'
    }]);
  } catch(e) {}
}



function TEST_returQcGudangRouting() {
  try {
    var wh = RQC_openGudangModule_();
    var sh = RQC_getSheetByKey_(wh.ss, 'STOCK_MOVEMENT');
    return {
      success: true,
      moduleCode: wh.code,
      source: wh.source || 'Master_Module',
      spreadsheetName: wh.ss.getName(),
      spreadsheetId: wh.ss.getId(),
      stockMovementFound: !!sh,
      stockMovementRows: sh ? sh.getLastRow() : 0,
      configCodes: RQC_CFG.GUDANG_MODULE_CODES,
      overrideFilled: !!String(RQC_CFG.GUDANG_SPREADSHEET_ID_OVERRIDE || '').trim()
    };
  } catch(e) {
    return { success: false, msg: e.message || String(e), configCodes: RQC_CFG.GUDANG_MODULE_CODES };
  }
}

function TEST_returQcInitDebug() {
  try {
    var res = getReturQcInit();
    return {
      success: true,
      initSuccess: !!(res && res.success),
      msg: res && res.msg ? res.msg : '',
      version: RQC_CFG.VERSION,
      sessionId: res && res.session ? res.session.Session_ID : '',
      source: res && res.source ? res.source.sheetName + ' / ' + res.source.rows + ' rows' : '',
      masterItems: res && res.masterItems ? res.masterItems.length : 0,
      lines: res && res.lines ? res.lines.length : 0,
      user: RQC_userEmail_()
    };
  } catch (e) {
    RQC_logError_('TEST_returQcInitDebug', e, {});
    return { success: false, error: e.message || String(e), version: RQC_CFG.VERSION };
  }
}


function TEST_returQcMasterItemsDebug() {
  try {
    RQC_clearCache_();
    var master = RQC_masterSs_();
    var s = RQC_getSheetByKey_(master, 'MASTER_ITEM');
    if (!s) return { success:false, msg:'Master_Item tidak ditemukan', masterName: master.getName(), masterId: master.getId() };
    var table = RQC_getTable_(s);
    var items = RQC_getMasterItems_();
    return {
      success: true,
      version: RQC_CFG.VERSION,
      masterName: master.getName(),
      masterId: master.getId(),
      sheetName: s.getName(),
      rows: Math.max(0, table.values.length - 1),
      headers: table.headers,
      masterItemsLoaded: items.length,
      sampleItems: items.slice(0, 10)
    };
  } catch(e) {
    RQC_logError_('TEST_returQcMasterItemsDebug', e, {});
    return { success:false, msg:e.message || String(e), version:RQC_CFG.VERSION };
  }
}

function TEST_returQcAllRoutingDebug() {
  var out = { version:RQC_CFG.VERSION, success:true, checks:[] };
  function add(name, fn) {
    try { out.checks.push({ name:name, ok:true, data:fn() }); }
    catch(e) { out.success=false; out.checks.push({ name:name, ok:false, error:e.message || String(e) }); }
  }
  add('MASTER', function(){ var ss=RQC_masterSs_(); return { name:ss.getName(), id:ss.getId(), hasMasterModule:!!RQC_getSheetByKey_(ss, 'MASTER_MODULE'), hasMasterItem:!!RQC_getSheetByKey_(ss, 'MASTER_ITEM') }; });
  add('RETUR_QC_SELF', function(){ var ss=RQC_selfSs_(); return { name:ss.getName(), id:ss.getId() }; });
  add('OMNI', function(){ var m=RQC_openModuleByCodes_(RQC_CFG.OMNI_MODULE_CODES); return { code:m.code, name:m.name, source:m.source, spreadsheetName:m.ss.getName(), spreadsheetId:m.ss.getId() }; });
  add('WH_GUDANG', function(){ var m=RQC_openGudangModule_(); return { code:m.code, name:m.name, source:m.source, spreadsheetName:m.ss.getName(), spreadsheetId:m.ss.getId(), hasStockMovement:!!RQC_getSheetByKey_(m.ss, 'STOCK_MOVEMENT') }; });
  add('RETUR_SOURCE', function(){ var src=RQC_getReturSourceSheet_(); return { sheet:src.sheet.getName(), spreadsheetName:src.spreadsheetName, rows:src.sheet.getLastRow()-1 }; });
  add('MASTER_ITEMS', function(){ var items=RQC_getMasterItems_(); return { count:items.length, sample:items.slice(0,5) }; });
  return out;
}

function RQC_safeForClient_(value) {
  var tz = Session.getScriptTimeZone() || 'Asia/Jakarta';
  if (value === null || value === undefined) return value;
  if (value instanceof Date) {
    if (isNaN(value.getTime())) return '';
    return Utilities.formatDate(value, tz, 'yyyy-MM-dd HH:mm:ss');
  }
  if (Array.isArray(value)) {
    return value.map(function(v) { return RQC_safeForClient_(v); });
  }
  if (typeof value === 'object') {
    var out = {};
    Object.keys(value).forEach(function(k) {
      var v = value[k];
      if (typeof v !== 'function') out[k] = RQC_safeForClient_(v);
    });
    return out;
  }
  return value;
}

// =================================================================================
// UTILITIES
// =================================================================================
function RQC_clean_(v) { return String(v === null || v === undefined ? '' : v).trim(); }
function RQC_normEmail_(v) { return RQC_clean_(v).toLowerCase(); }
function RQC_key_(v) { return RQC_clean_(v).toUpperCase().replace(/[^A-Z0-9]/g, ''); }
function RQC_isActive_(v) { var s = RQC_key_(v); if (!s) return true; return ['ACTIVE','AKTIF','ON','TRUE','YES','ENABLED','NEWCORE','NEW_CORE'].indexOf(s) !== -1; }
function RQC_formatDateTime_(v) { var d = RQC_parseDateLoose_(v); return d ? Utilities.formatDate(d, RQC_CFG.TZ || Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd HH:mm:ss') : ''; }

function RQC_normHeader_(h) { return String(h || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''); }
function RQC_normCode_(x) { return String(x || '').trim().toUpperCase().replace(/\s+/g, ''); }
function RQC_escape_(s) { return String(s || '').replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function RQC_toNumber_(value) {
  if (typeof value === 'number') return isNaN(value) ? 0 : value;
  var s = String(value || '').trim();
  if (!s) return 0;
  s = s.replace(/Rp/gi, '').replace(/\s/g, '');
  var hasComma = s.indexOf(',') !== -1;
  var hasDot = s.indexOf('.') !== -1;
  if (hasComma && hasDot) {
    if (s.lastIndexOf(',') > s.lastIndexOf('.')) s = s.replace(/\./g, '').replace(',', '.');
    else s = s.replace(/,/g, '');
  } else if (hasComma) {
    s = s.replace(',', '.');
  }
  var n = Number(s);
  return isNaN(n) ? 0 : n;
}

function RQC_statusAllowed_(statusRaw) {
  var st = String(statusRaw || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!st) return true;
  var inactive = ['INACTIVE','NONAKTIF','DISABLED','OFF','FALSE','STOP','STOPPED','ARCHIVE','ARSIP'];
  return inactive.indexOf(st) === -1;
}

function RQC_startOfDay_(d) {
  if (!(d instanceof Date)) d = RQC_parseDateLoose_(d) || new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function RQC_parseDateLoose_(v) {
  if (!v) return null;
  if (v instanceof Date && !isNaN(v.getTime())) return v;
  var s = String(v || '').trim();
  if (!s) return null;

  var d1 = new Date(s);
  if (!isNaN(d1.getTime())) return d1;

  // dd/mm/yyyy atau dd-mm-yyyy, optional jam.
  var m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (m) {
    var yy = Number(m[3]);
    if (yy < 100) yy += 2000;
    var dd = Number(m[1]);
    var mm = Number(m[2]) - 1;
    var hh = Number(m[4] || 0);
    var mi = Number(m[5] || 0);
    var ss = Number(m[6] || 0);
    var d2 = new Date(yy, mm, dd, hh, mi, ss);
    if (!isNaN(d2.getTime())) return d2;
  }
  return null;
}

function RQC_formatDateForClient_(v) {
  if (!v) return '';
  var d = RQC_parseDateLoose_(v);
  if (!d) return String(v || '');
  return Utilities.formatDate(d, Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd');
}

function RQC_clearCache_() {
  try { CacheService.getScriptCache().removeAll(['RQC_RETUR_ROWS_V5','RQC_RETUR_ROWS_V4','RQC_RETUR_ROWS_V3','RQC_MASTER_ITEMS_V3','RQC_MASTER_ITEM_META_V1']); } catch(e) {}
}