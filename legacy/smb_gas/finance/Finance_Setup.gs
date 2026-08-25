/** Setup / migration helpers. */

function SETUP_installFinanceModule() {
  var ss = FIN_selfSs_();
  FIN_ensureSheet_(ss, FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
  FIN_ensureSheet_(ss, FIN_CFG.SHEET_LOCK, FIN_HEADERS.LOCK);
  FIN_ensureMasterCOA_();
  return { success: true, spreadsheetName: ss.getName(), spreadsheetId: ss.getId(), message: 'Finance setup selesai. v1.1 Light Valuation Reader aktif.' };
}

function FIN_ensureMasterCOA_() {
  var ss = FIN_masterSs_();
  var sh = FIN_ensureSheet_(ss, 'Master_COA', FIN_HEADERS.COA);

  // COA disimpan di sheet Master_COA supaya fleksibel diedit manual.
  // v0.4: seed COA wajib header-based, mengikuti header existing Master_COA.
  // Ini mencegah kasus Account_Code nyasar ke COA_ID seperti v0.3.
  FIN_repairCorruptCoaImportRows_(sh);
  FIN_seedDefaultCoaByHeader_(sh);
  return sh;
}

function FIN_makeCoaObject_(row) {
  var code = String(row[0] || '').trim();
  var name = String(row[1] || '').trim();
  var type = String(row[2] || '').trim();
  var group = String(row[3] || '').trim();
  var normal = String(row[4] || '').trim();
  var status = String(row[5] || '').trim() || 'ACTIVE';
  var notes = String(row[6] || '').trim() || 'Import COA KIRAL';
  return {
    COA_ID: 'COA-' + code,
    Account_Code: code,
    Account_Name: name,
    Account_Type: type,
    Normal_Balance: normal,
    Parent_Code: '',
    Is_Posting: true,
    Status: status,
    Notes: notes,
    Account_Group: group
  };
}

function FIN_seedDefaultCoaByHeader_(sh) {
  FIN_ensureColumns_(sh, FIN_HEADERS.COA);
  var table = FIN_readSheetTable_(sh);
  var existing = {};
  table.rows.forEach(function(r) {
    var code = String(FIN_val_(r, ['Account_Code', 'Kode Akun']) || '').trim();
    var name = FIN_cleanKey_(FIN_val_(r, ['Account_Name', 'Nama Akun']));
    if (code) existing['CODE:' + code] = true;
    if (name) existing['NAME:' + name] = true;
  });

  var appended = 0;
  FIN_DEFAULT_COA.forEach(function(row) {
    var obj = FIN_makeCoaObject_(row);
    var nameKey = FIN_cleanKey_(obj.Account_Name);
    if (obj.Account_Code && existing['CODE:' + obj.Account_Code]) return;
    if (!obj.Account_Code && nameKey && existing['NAME:' + nameKey]) return;
    FIN_appendObjectByHeaders_(sh, FIN_HEADERS.COA, obj);
    if (obj.Account_Code) existing['CODE:' + obj.Account_Code] = true;
    if (nameKey) existing['NAME:' + nameKey] = true;
    appended++;
  });
  return appended;
}

function FIN_repairCorruptCoaImportRows_(sh) {
  // Hapus row hasil import v0.3 yang bergeser kolom:
  // COA_ID=1101, Account_Code=Kas Kecil, Account_Name=ASET, dst.
  var table = FIN_readSheetTable_(sh);
  var deleteRows = [];
  table.rows.forEach(function(r) {
    var coaId = String(FIN_val_(r, ['COA_ID']) || '').trim();
    var accCode = String(FIN_val_(r, ['Account_Code']) || '').trim();
    var accName = String(FIN_val_(r, ['Account_Name']) || '').trim();
    var notes = String(FIN_val_(r, ['Notes']) || '').trim();
    var isBadShift = /^\d{4,}$/.test(coaId) && accCode && !/^\d{3,}$/.test(accCode) && /^(ASET|LIABILITAS|EKUITAS|MODAL|PENDAPATAN|BEBAN|HPP|COGS|EXPENSE|ASSET)$/i.test(accName);
    var isBadImportNoteShift = /^\d{4,}$/.test(coaId) && !notes && String(FIN_val_(r, ['Is_Posting']) || '').indexOf('Import COA KIRAL') !== -1;
    if (isBadShift || isBadImportNoteShift) deleteRows.push(r._rowNumber);
  });
  deleteRows.sort(function(a, b) { return b - a; }).forEach(function(rowNo) { sh.deleteRow(rowNo); });
  return deleteRows.length;
}

function FIX_financeCoaKiralRepairSafe() {
  var sh = FIN_ensureSheet_(FIN_masterSs_(), 'Master_COA', FIN_HEADERS.COA);
  var removed = FIN_repairCorruptCoaImportRows_(sh);
  var appended = FIN_seedDefaultCoaByHeader_(sh);
  return { success: true, mode: 'SAFE_REPAIR', removedCorruptRows: removed, appendedMissingCoa: appended, lastRow: sh.getLastRow(), headers: sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0] };
}

function FIX_financeCoaKiralResetClean() {
  // Pakai ini hanya kalau mau Master_COA bersih 100% dari COA KIRAL.
  // Semua row lama dihapus, header dipertahankan/dibuat ulang.
  var sh = FIN_masterSs_().getSheetByName('Master_COA');
  if (!sh) sh = FIN_masterSs_().insertSheet('Master_COA');
  sh.clearContents();
  sh.getRange(1, 1, 1, FIN_HEADERS.COA.length).setValues([FIN_HEADERS.COA]);
  sh.setFrozenRows(1);
  var appended = FIN_seedDefaultCoaByHeader_(sh);
  return { success: true, mode: 'RESET_CLEAN', appendedCoa: appended, lastRow: sh.getLastRow(), headers: sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0] };
}

function SETUP_installFinanceBankReconAdapter() {
  var auth = ERP_securityCheck_(ERP_userEmail_(), '', false);
  if (!auth.allowed) throw new Error('Akses setup ditolak: ' + (auth.reason || 'UNKNOWN'));
  FIN_ensureSheet_(FIN_selfSs_(), FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
  FIN_bankStatementSheet_();
  FIN_setupBankReconLinkColumns_();
  FIN_setupBankReconMultiLink_();
  var migrated = FIN_migrateLegacyBankReconLinks_();
  return { success:true, migratedLegacyLinks:migrated, message:'Finance siap. Edit/hapus jurnal, multi-match, dan daftar rekonsiliasi UNMATCHED aktif.', version:FIN_CFG.VERSION };
}

function CLEANUP_compactBankStatementSheet() {
  var auth = ERP_securityCheck_(ERP_userEmail_(), '', false);
  if (!auth.allowed) throw new Error('Akses cleanup ditolak: ' + (auth.reason || 'UNKNOWN'));
  var ss = FIN_selfSs_();
  var sh = FIN_bankStatementSheet_();
  var table = FIN_readSheetTable_(sh);
  var oldRows = table.rows || [];
  var backupName = 'Backup_Bank_Statement_' + Utilities.formatDate(new Date(), ERP_GLOBAL_CFG.TZ || Session.getScriptTimeZone(), 'yyMMdd_HHmmss');
  if (sh.getLastRow() > 1 || sh.getLastColumn() > FIN_BANK_STATEMENT_HEADERS.length) {
    var bak = sh.copyTo(ss).setName(backupName.substring(0, 95));
    bak.hideSheet();
  }
  var rows = oldRows.map(FIN_bankStatementCompactObjectFromRow_).filter(function(o){ return o.Tx_Key || o.Description || o.Amount; });
  sh.clearContents();
  if (sh.getMaxColumns() < FIN_BANK_STATEMENT_HEADERS.length) sh.insertColumnsAfter(sh.getMaxColumns(), FIN_BANK_STATEMENT_HEADERS.length - sh.getMaxColumns());
  sh.getRange(1, 1, 1, FIN_BANK_STATEMENT_HEADERS.length).setValues([FIN_BANK_STATEMENT_HEADERS]);
  if (rows.length) {
    var values = rows.map(function(o){ return FIN_BANK_STATEMENT_HEADERS.map(function(h){ return o[h] !== undefined ? o[h] : ''; }); });
    sh.getRange(2, 1, values.length, FIN_BANK_STATEMENT_HEADERS.length).setValues(values);
  }
  var extra = sh.getMaxColumns() - FIN_BANK_STATEMENT_HEADERS.length;
  if (extra > 0) sh.deleteColumns(FIN_BANK_STATEMENT_HEADERS.length + 1, extra);
  FIN_applyBankStatementCompactFormats_(sh);
  FIN_touchMutation_('Compact Bank_Statement columns: ' + rows.length + ' rows');
  return { success:true, version:FIN_CFG.VERSION, compactHeaders:FIN_BANK_STATEMENT_HEADERS, rows:rows.length, backupSheet:backupName, message:'Bank_Statement sudah dikompres menjadi ' + FIN_BANK_STATEMENT_HEADERS.length + ' kolom. Backup lama disembunyikan: ' + backupName };
}

function REPAIR_bankStatementDatesAndDbCr() {
  var sh = FIN_bankStatementSheet_();
  var table = FIN_readSheetTable_(sh);
  if (!table.rows.length) return { success:true, repaired:0, message:'Bank_Statement kosong.' };
  var fixed = 0;
  table.rows.forEach(function(r){
    var obj = FIN_bankStatementCompactObjectFromRow_(r);
    var oldKey = String(FIN_val_(r, ['Date_Key']) || '').substring(0, 10);
    var oldDir = String(FIN_val_(r, ['Direction']) || '').toUpperCase();
    var oldAmount = FIN_toNumber_(FIN_val_(r, ['Amount']));
    var needs = FIN_bankDateKeyLooksBad_(oldKey) || oldKey !== obj.Date_Key || oldDir !== obj.Direction || Math.abs(oldAmount - FIN_toNumber_(obj.Amount)) > 0.01;
    if (!needs) return;
    FIN_BANK_STATEMENT_HEADERS.forEach(function(h){ if (h === 'Tx_Key') return; FIN_setByHeader_(sh, r._rowNumber, h, obj[h]); });
    fixed++;
  });
  FIN_applyBankStatementCompactFormats_(sh);
  if (fixed) FIN_touchMutation_('Repair Bank_Statement date/dbcr compact: ' + fixed + ' rows');
  return { success:true, repaired:fixed, message:'Repair Date_Key + Direction selesai: ' + fixed + ' baris.' };
}

function REPAIR_bankStatementDbCrDirections() {
  return REPAIR_bankStatementDatesAndDbCr();
}


function TEST_financeBankReconMultiMatchSetup() {
  var sh = FIN_setupBankReconMultiLink_();
  var table = FIN_readSheetTable_(sh);
  var maps = FIN_activeBankReconLinkMaps_();
  return {
    success:true,
    version:FIN_CFG.VERSION,
    sheetName:sh.getName(),
    headers:table.headers,
    activeTxCount:Object.keys(maps.byTx || {}).length,
    activeJournalCount:Object.keys(maps.byJurnal || {}).length,
    message:'Popup + backend multi-match siap.'
  };
}


function TEST_financeJurnalEditDeleteSetup() {
  var sh = FIN_ensureSheet_(FIN_selfSs_(), FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
  FIN_setupBankReconMultiLink_();
  var table = FIN_readSheetTable_(sh);
  return {
    success:true,
    version:FIN_CFG.VERSION,
    sheetName:sh.getName(),
    headers:table.headers,
    hasUpdatedAt:table.map[FIN_headerKey_('Updated_At')] !== undefined,
    hasIsDeleted:table.map[FIN_headerKey_('Is_Deleted')] !== undefined,
    hasBankTxKey:table.map[FIN_headerKey_('Bank_Tx_Key')] !== undefined,
    message:'Edit/hapus jurnal dan rekonsiliasi UNMATCHED siap.'
  };
}