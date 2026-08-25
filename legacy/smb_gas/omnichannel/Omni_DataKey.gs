// =================================================================================
// ERP CV KIRAL - OMNI DATE KEY GUARD v1.6.2
// Menjaga seluruh Date Key sebagai text canonical yyyy-MM-dd dan mencegah swap hari/bulan.
// Raw date tetap disimpan untuk audit; summary hanya membaca key canonical.
// =================================================================================

var OMNI_DATEKEY_VERSION = 'OMNI_DATEKEY_V3_SETTLEMENT_SOURCE_FIRST';

function OMNI_pad2_(n) {
  n = parseInt(n, 10);
  return (n < 10 ? '0' : '') + n;
}

function OMNI_validDateParts_(y, m, d) {
  y = parseInt(y, 10); m = parseInt(m, 10); d = parseInt(d, 10);
  if (!y || y < 1900 || y > 2200 || m < 1 || m > 12 || d < 1 || d > 31) return false;
  var dt = new Date(y, m - 1, d, 12, 0, 0);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}

function OMNI_partsToDateKey_(y, m, d) {
  return OMNI_validDateParts_(y, m, d) ? (String(parseInt(y, 10)) + '-' + OMNI_pad2_(m) + '-' + OMNI_pad2_(d)) : '';
}

function OMNI_excelSerialDateKey_(value) {
  var n = Number(value);
  if (!isFinite(n) || n < 20000 || n > 100000) return '';
  var utcMs = Date.UTC(1899, 11, 30) + Math.floor(n) * 86400000;
  var d = new Date(utcMs);
  return OMNI_partsToDateKey_(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

function OMNI_monthIndexFromName_(name) {
  var map = {
    jan:1, januari:1, january:1,
    feb:2, februari:2, february:2,
    mar:3, maret:3, march:3,
    apr:4, april:4,
    mei:5, may:5,
    jun:6, juni:6, june:6,
    jul:7, juli:7, july:7,
    agu:8, agustus:8, aug:8, august:8,
    sep:9, september:9,
    okt:10, oktober:10, oct:10, october:10,
    nov:11, november:11,
    des:12, desember:12, dec:12, december:12
  };
  return map[String(name || '').toLowerCase()] || 0;
}

/**
 * Mengubah nilai tanggal menjadi yyyy-MM-dd secara deterministic.
 * preference hanya dipakai untuk format numerik ambigu 01/02/2026:
 * - DMY => 1 Februari 2026
 * - MDY => 2 Januari 2026
 */
function OMNI_dateKeyStrict_(value, preference) {
  preference = String(preference || 'DMY').toUpperCase() === 'MDY' ? 'MDY' : 'DMY';
  if (value === null || value === undefined || value === '') return '';

  if (value instanceof Date && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, TZ, 'yyyy-MM-dd');
  }

  if (typeof value === 'number') {
    var serial = OMNI_excelSerialDateKey_(value);
    if (serial) return serial;
    if (value > 100000000000) {
      var dtNum = new Date(value);
      return isNaN(dtNum.getTime()) ? '' : Utilities.formatDate(dtNum, TZ, 'yyyy-MM-dd');
    }
  }

  var s = String(value).trim().replace(/^'/, '');
  if (!s) return '';

  // ISO/canonical selalu diproses lebih dahulu agar tidak pernah tertukar.
  var iso = s.match(/^(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})(?:[T\s].*)?$/);
  if (iso) return OMNI_partsToDateKey_(iso[1], iso[2], iso[3]);

  // dd NamaBulan yyyy
  var namedDmy = s.match(/^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:[T\s].*)?$/);
  if (namedDmy) {
    var namedMonth = OMNI_monthIndexFromName_(namedDmy[2]);
    if (namedMonth) return OMNI_partsToDateKey_(namedDmy[3], namedMonth, namedDmy[1]);
  }

  // NamaBulan dd, yyyy
  var namedMdy = s.match(/^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})(?:[T\s].*)?$/);
  if (namedMdy) {
    var namedMonth2 = OMNI_monthIndexFromName_(namedMdy[1]);
    if (namedMonth2) return OMNI_partsToDateKey_(namedMdy[3], namedMonth2, namedMdy[2]);
  }

  // Ambil bagian tanggal pertama, jam diabaikan.
  var numeric = s.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{2}|\d{4})(?:[T\s].*)?$/);
  if (numeric) {
    var a = parseInt(numeric[1], 10);
    var b = parseInt(numeric[2], 10);
    var y = parseInt(numeric[3], 10);
    if (y < 100) y += y >= 70 ? 1900 : 2000;

    var day, month;
    if (a > 12 && b <= 12) {
      day = a; month = b; // pasti DMY
    } else if (b > 12 && a <= 12) {
      month = a; day = b; // pasti MDY
    } else if (preference === 'MDY') {
      month = a; day = b;
    } else {
      day = a; month = b;
    }
    return OMNI_partsToDateKey_(y, month, day);
  }

  return '';
}

function OMNI_inferDateOrder_(values, fallback) {
  fallback = String(fallback || 'DMY').toUpperCase() === 'MDY' ? 'MDY' : 'DMY';
  var dmyEvidence = 0;
  var mdyEvidence = 0;
  var ambiguous = 0;
  var inspected = 0;

  (values || []).forEach(function(value) {
    if (value === null || value === undefined || value === '' || value instanceof Date || typeof value === 'number') return;
    var s = String(value).trim();
    if (/^\d{4}[-\/.]/.test(s)) return;
    var m = s.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](?:\d{2}|\d{4})/);
    if (!m) return;
    inspected++;
    var a = parseInt(m[1], 10);
    var b = parseInt(m[2], 10);
    if (a > 12 && b <= 12) dmyEvidence++;
    else if (b > 12 && a <= 12) mdyEvidence++;
    else ambiguous++;
  });

  var order = fallback;
  if (dmyEvidence > 0 && mdyEvidence === 0) order = 'DMY';
  else if (mdyEvidence > 0 && dmyEvidence === 0) order = 'MDY';
  else if (dmyEvidence !== mdyEvidence) order = dmyEvidence > mdyEvidence ? 'DMY' : 'MDY';

  return {
    order: order,
    fallback: fallback,
    dmyEvidence: dmyEvidence,
    mdyEvidence: mdyEvidence,
    ambiguous: ambiguous,
    inspected: inspected,
    mixed: dmyEvidence > 0 && mdyEvidence > 0
  };
}

function OMNI_canonicalKeyFromSource_(keyValue, rawValue, preference) {
  var keyString = String(keyValue === null || keyValue === undefined ? '' : keyValue).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(keyString)) return keyString;
  var fromKey = OMNI_dateKeyStrict_(keyValue, preference);
  if (fromKey) return fromKey;
  return OMNI_dateKeyStrict_(rawValue, preference);
}

/**
 * Settlement khusus memakai tanggal sumber sebagai sumber kebenaran.
 * `tglCair` dari client disimpan dalam format tampilan Indonesia dd/MM/yyyy.
 * Key yang sudah dikirim client tidak boleh mengalahkan raw date karena dapat
 * membawa hasil inferensi MDY yang salah untuk nilai ambigu seperti 12/03/2026.
 */
function OMNI_settlementDateKeyFromPayload_(payload) {
  var p = payload || {};
  var raw = p.tglCair || p['Tgl Pencairan'] || p.tgl || p.date || '';
  var fromRaw = OMNI_dateKeyStrict_(raw, 'DMY');
  if (fromRaw) return fromRaw;
  return OMNI_dateKeyStrict_(p.tglCairKey || p.tglKey || '', 'DMY');
}

/**
 * Membaca row settlement existing dengan raw-date-first.
 * Ini sengaja berbeda dari OMNI_canonicalKeyFromSource_ yang key-first.
 */
function OMNI_settlementDateKeyFromRow_(rawValue, keyValue) {
  var fromRaw = OMNI_dateKeyStrict_(rawValue, 'DMY');
  if (fromRaw) return fromRaw;
  return OMNI_dateKeyStrict_(keyValue, 'DMY');
}

function OMNI_setPlainTextColumnByHeader_(sheet, aliases) {
  if (!sheet || sheet.getLastColumn() < 1) return -1;
  var info = headerInfo_(sheet);
  var idx = col_(info, aliases, -1);
  if (idx === -1) return -1;

  // Jangan format ulang seluruh kolom pada setiap import/rebuild.
  // Cukup cek satu sel probe; instalasi pertama akan memformat kolom yang tersedia.
  var probe = sheet.getRange(2, idx + 1, 1, 1);
  if (probe.getNumberFormat() === '@') return idx;

  var rows = Math.max(sheet.getMaxRows() - 1, 1);
  sheet.getRange(2, idx + 1, rows, 1).setNumberFormat('@');
  return idx;
}

function OMNI_prepareDateKeyColumns_(ss) {
  ss = ss || getActiveOmni_();
  var order = ensureSheetWithHeaders_(ss, OMNI_SHEET, OMNI_HEADERS);
  var settlement = ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  var sumStore = ensureSheetWithHeaders_(ss, OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS);
  var sumProduct = ensureSheetWithHeaders_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
  var sumSettlement = ensureSheetWithHeaders_(ss, OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS);

  OMNI_setPlainTextColumnByHeader_(order, ['Tanggal Key']);
  OMNI_setPlainTextColumnByHeader_(settlement, ['Tgl Pencairan Key']);
  OMNI_setPlainTextColumnByHeader_(sumStore, ['Date_Key']);
  OMNI_setPlainTextColumnByHeader_(sumProduct, ['Date_Key']);
  OMNI_setPlainTextColumnByHeader_(sumSettlement, ['Settlement_Date_Key']);
}

function SETUP_installOmniDateKeyGuard(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'SETUP_installOmniDateKeyGuard');
  var ss = getActiveOmni_();
  ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  OMNI_ensureDailySummarySheets_(ss);
  OMNI_prepareDateKeyColumns_(ss);
  return TEST_omniDateKeyAudit(emailOp, pasporOp);
}

function OMNI_collectDateAudit_(table, rawAliases, keyAliases, fallback) {
  if (!table || !table.sheet) return { rows:0, orientation:OMNI_inferDateOrder_([], fallback), invalidRaw:0, invalidKey:0, mismatch:0, samples:[] };
  var cRaw = col_(table.info, rawAliases, -1);
  var cKey = col_(table.info, keyAliases, -1);
  var rawValues = table.rows.map(function(r) { return cRaw !== -1 ? r[cRaw] : ''; });
  var orientation = OMNI_inferDateOrder_(rawValues, fallback);
  var out = { rows:table.rows.length, orientation:orientation, invalidRaw:0, invalidKey:0, mismatch:0, samples:[] };

  table.rows.forEach(function(r, idx) {
    var raw = cRaw !== -1 ? r[cRaw] : '';
    var current = cKey !== -1 ? r[cKey] : '';
    var expected = OMNI_dateKeyStrict_(raw, orientation.order);
    var actual = OMNI_canonicalKeyFromSource_(current, '', orientation.order);
    if (!expected) out.invalidRaw++;
    if (!actual) out.invalidKey++;
    if (expected && actual && expected !== actual) {
      out.mismatch++;
      if (out.samples.length < 20) out.samples.push({ row:idx + 2, raw:String(raw || ''), current:String(current || ''), expected:expected });
    }
  });
  return out;
}

function OMNI_collectSettlementDateAudit_(table) {
  if (!table || !table.sheet) return { rows:0, orientation:{order:'DMY', forced:true}, invalidRaw:0, invalidKey:0, mismatch:0, samples:[] };
  var cRaw = col_(table.info, ['Tgl Pencairan'], -1);
  var cKey = col_(table.info, ['Tgl Pencairan Key'], -1);
  var out = { rows:table.rows.length, orientation:{order:'DMY', forced:true}, invalidRaw:0, invalidKey:0, mismatch:0, samples:[] };
  table.rows.forEach(function(r, idx) {
    var raw = cRaw !== -1 ? r[cRaw] : '';
    var current = cKey !== -1 ? r[cKey] : '';
    var expected = OMNI_settlementDateKeyFromRow_(raw, '');
    var actual = OMNI_dateKeyStrict_(current, 'DMY');
    if (!expected) out.invalidRaw++;
    if (!actual) out.invalidKey++;
    if (expected && actual && expected !== actual) {
      out.mismatch++;
      if (out.samples.length < 20) out.samples.push({ row:idx + 2, raw:String(raw || ''), current:String(current || ''), expected:expected });
    }
  });
  return out;
}

function OMNI_collectSummaryDateAudit_(table, dateAliases) {
  if (!table || !table.sheet) return { rows:0, invalid:0, samples:[] };
  var cDate = col_(table.info, dateAliases, -1);
  var out = { rows:table.rows.length, invalid:0, samples:[] };
  table.rows.forEach(function(r, idx) {
    var raw = cDate !== -1 ? r[cDate] : '';
    var key = OMNI_dateKeyStrict_(raw, 'DMY');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(raw || '').trim()) || !key) {
      out.invalid++;
      if (out.samples.length < 20) out.samples.push({ row:idx + 2, value:String(raw || ''), normalized:key });
    }
  });
  return out;
}

function TEST_omniDateKeyAudit(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniDateKeyAudit');
  var ss = getActiveOmni_();
  ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  OMNI_ensureDailySummarySheets_(ss);

  var order = OMNI_collectDateAudit_(readTable_(ss, OMNI_SHEET, OMNI_HEADERS), ['Tanggal'], ['Tanggal Key'], 'DMY');
  var settlement = OMNI_collectSettlementDateAudit_(readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS));
  var summaryOrderStore = OMNI_collectSummaryDateAudit_(readTable_(ss, OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS), ['Date_Key']);
  var summaryOrderProduct = OMNI_collectSummaryDateAudit_(readTable_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS), ['Date_Key']);
  var summarySettlement = OMNI_collectSummaryDateAudit_(readTable_(ss, OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS), ['Settlement_Date_Key']);

  var sourceMismatch = order.mismatch + settlement.mismatch;
  var summaryInvalid = summaryOrderStore.invalid + summaryOrderProduct.invalid + summarySettlement.invalid;
  var diagnosis = sourceMismatch > 0
    ? 'Date Key sumber tidak konsisten dengan tanggal mentah; summary hanya meneruskan key yang salah.'
    : (summaryInvalid > 0
      ? 'Date Key sumber terlihat konsisten, tetapi kolom summary pernah terkonversi oleh format/locale sheet.'
      : 'Date Key sumber dan summary terlihat canonical.');

  var out = {
    success:true,
    version:OMNI_DATEKEY_VERSION,
    diagnosis:diagnosis,
    orderSource:order,
    settlementSource:settlement,
    summaries:{ orderStore:summaryOrderStore, orderProduct:summaryOrderProduct, settlementStore:summarySettlement },
    needsRepair:sourceMismatch > 0 || summaryInvalid > 0 || settlement.invalidKey > 0
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

function OMNI_rewriteDateKeyColumn_(table, rawAliases, keyAliases, fallback) {
  if (!table || !table.sheet) return { rows:0, changed:0, skipped:0, orientation:OMNI_inferDateOrder_([], fallback) };
  var cRaw = col_(table.info, rawAliases, -1);
  var cKey = col_(table.info, keyAliases, -1);
  if (cKey === -1) throw new Error('Kolom Date Key tidak ditemukan di ' + table.sheet.getName());

  var rawValues = table.rows.map(function(r) { return cRaw !== -1 ? r[cRaw] : ''; });
  var orientation = OMNI_inferDateOrder_(rawValues, fallback);
  var values = [];
  var changed = 0;
  var skipped = 0;

  table.rows.forEach(function(r) {
    var raw = cRaw !== -1 ? r[cRaw] : '';
    var current = r[cKey];
    var expected = OMNI_dateKeyStrict_(raw, orientation.order);
    if (!expected) {
      expected = OMNI_canonicalKeyFromSource_(current, '', orientation.order);
      skipped++;
    }
    var currentCanonical = OMNI_canonicalKeyFromSource_(current, '', orientation.order);
    if (expected && expected !== currentCanonical) changed++;
    values.push([expected || '']);
  });

  if (values.length) {
    var range = table.sheet.getRange(2, cKey + 1, values.length, 1);
    range.setNumberFormat('@');
    range.setValues(values);
  }
  return { rows:values.length, changed:changed, skipped:skipped, orientation:orientation };
}

function OMNI_rewriteSettlementDateKeyColumn_(table) {
  if (!table || !table.sheet) return { rows:0, changed:0, skipped:0, orientation:{order:'DMY', forced:true} };
  var cRaw = col_(table.info, ['Tgl Pencairan'], -1);
  var cKey = col_(table.info, ['Tgl Pencairan Key'], -1);
  if (cKey === -1) throw new Error('Kolom Tgl Pencairan Key tidak ditemukan di ' + table.sheet.getName());

  var values = [];
  var changed = 0;
  var skipped = 0;
  table.rows.forEach(function(r) {
    var raw = cRaw !== -1 ? r[cRaw] : '';
    var current = r[cKey];
    var expected = OMNI_settlementDateKeyFromRow_(raw, current);
    if (!OMNI_dateKeyStrict_(raw, 'DMY')) skipped++;
    var currentCanonical = OMNI_dateKeyStrict_(current, 'DMY');
    if (expected && expected !== currentCanonical) changed++;
    values.push([expected || '']);
  });

  if (values.length) {
    var range = table.sheet.getRange(2, cKey + 1, values.length, 1);
    range.setNumberFormat('@');
    range.setValues(values);
  }
  return { rows:values.length, changed:changed, skipped:skipped, orientation:{order:'DMY', forced:true} };
}

/**
 * Perbaikan cepat khusus settlement. Tidak menyentuh Omni_Order.
 * Setelah key sumber diperbaiki, hanya summary settlement yang dibangun ulang.
 */
function REPAIR_omniSettlementDateKeysAndSummary(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'REPAIR_omniSettlementDateKeysAndSummary');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { throw new Error('Server sibuk. Coba lagi.'); }
  try {
    var ss = getActiveOmni_();
    ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
    OMNI_ensureDailySummarySheets_(ss);
    OMNI_prepareDateKeyColumns_(ss);

    var settlement = OMNI_rewriteSettlementDateKeyColumn_(readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS));
    SpreadsheetApp.flush();
    var summary = OMNI_rebuildSettlementDailySummary_(null);
    OMNI_prepareDateKeyColumns_(ss);
    SpreadsheetApp.flush();
    cacheRemove_('OMNI_DAILY_SUMMARY_READY');

    var audit = OMNI_collectSettlementDateAudit_(readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS));
    var result = {
      success:true,
      version:OMNI_DATEKEY_VERSION,
      settlement:settlement,
      settlementSummary:summary,
      audit:audit,
      valid:audit.mismatch === 0 && audit.invalidKey === 0
    };
    Logger.log(JSON.stringify(result, null, 2));
    return result;
  } finally {
    lock.releaseLock();
  }
}

function TEST_omniSettlementDateKeyAudit(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniSettlementDateKeyAudit');
  var ss = getActiveOmni_();
  var audit = OMNI_collectSettlementDateAudit_(readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS));
  var out = {
    success:true,
    version:OMNI_DATEKEY_VERSION,
    valid:audit.mismatch === 0 && audit.invalidKey === 0,
    settlement:audit
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

function REPAIR_omniDateKeysAndDailySummary(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'REPAIR_omniDateKeysAndDailySummary');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { throw new Error('Server sibuk. Coba lagi.'); }
  try {
    var ss = getActiveOmni_();
    ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
    OMNI_ensureDailySummarySheets_(ss);
    OMNI_prepareDateKeyColumns_(ss);

    var order = OMNI_rewriteDateKeyColumn_(readTable_(ss, OMNI_SHEET, OMNI_HEADERS), ['Tanggal'], ['Tanggal Key'], 'DMY');
    var settlement = OMNI_rewriteSettlementDateKeyColumn_(readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS));
    SpreadsheetApp.flush();
    var summary = OMNI_rebuildAllDailySummary_();
    OMNI_prepareDateKeyColumns_(ss);
    SpreadsheetApp.flush();
    cacheRemove_('OMNI_DAILY_SUMMARY_READY');

    var result = {
      success:true,
      version:OMNI_DATEKEY_VERSION,
      order:order,
      settlement:settlement,
      dailySummary:summary,
      audit:TEST_omniDateKeyAudit(emailOp, pasporOp)
    };
    Logger.log(JSON.stringify(result, null, 2));
    return result;
  } finally {
    lock.releaseLock();
  }
}