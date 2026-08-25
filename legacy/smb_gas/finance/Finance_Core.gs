/** Core security, bootstrap, module routing, shared helpers. */

function FIN_currentEmail_() {
  return String(Session.getActiveUser().getEmail() || '').trim().toLowerCase();
}

function FIN_checkAccess_() {
  var email = FIN_currentEmail_();
  if (!email) return { allowed: false, email: '', reason: 'Email login kosong. Deploy Web App jangan anonymous.' };

  try {
    var ss = FIN_masterSs_();
    var sh = ss.getSheetByName('Master_User');
    if (!sh) return { allowed: false, email: email, reason: 'Sheet Master_User tidak ditemukan.' };

    var table = FIN_readSheetTable_(sh);
    if (!table.rows.length) return { allowed: false, email: email, reason: 'Master_User kosong.' };

    var allowedAliases = FIN_CFG.MODULE_ALIASES.map(FIN_cleanKey_);
    for (var i = 0; i < table.rows.length; i++) {
      var row = table.rows[i];
      var userEmail = FIN_normEmail_(FIN_val_(row, ['Email', 'User_Email', 'User Email']));
      if (userEmail !== email) continue;

      var status = FIN_cleanKey_(FIN_val_(row, ['Status']));
      var active = ['ACTIVE', 'AKTIF', 'ON', 'TRUE', 'YES', 'ENABLED'].indexOf(status) !== -1;
      if (!active) return { allowed: false, email: email, reason: 'User ditemukan tapi status tidak aktif: ' + status, matchedUser: row };

      var role = FIN_cleanKey_(FIN_val_(row, ['Role']));
      var dept = FIN_cleanKey_(FIN_val_(row, ['Department', 'Departemen']));
      var allowedModulesRaw = String(FIN_val_(row, ['Allowed_Modules', 'Allowed Modules', 'Module_Access', 'Module Access']) || '');
      var allowedModules = allowedModulesRaw.split(/[;,|]/).map(FIN_cleanKey_).filter(Boolean);

      if (role === 'ADMIN' || role === 'SUPERADMIN' || role === 'SUPER_ADMIN') {
        return { allowed: true, email: email, reason: 'ADMIN', matchedUser: row };
      }
      if (dept === 'ADMIN') {
        return { allowed: true, email: email, reason: 'Department ADMIN', matchedUser: row };
      }
      if (allowedModules.indexOf('ALL') !== -1) {
        return { allowed: true, email: email, reason: 'Allowed_Modules=ALL', matchedUser: row };
      }
      if (allowedModules.some(function(x) { return allowedAliases.indexOf(x) !== -1; })) {
        return { allowed: true, email: email, reason: 'Allowed_Modules cocok', matchedUser: row };
      }
      if (allowedAliases.indexOf(role) !== -1 || allowedAliases.indexOf(dept) !== -1) {
        return { allowed: true, email: email, reason: 'Role/Department cocok modul', matchedUser: row };
      }

      return { allowed: false, email: email, reason: 'User aktif tapi tidak punya akses FIN/FINANCE.', matchedUser: row };
    }

    return { allowed: false, email: email, reason: 'Email tidak ditemukan di Master_User.' };
  } catch (err) {
    return { allowed: false, email: email, reason: 'Security error: ' + err.message };
  }
}

function FIN_requireAccess_() {
  var auth = FIN_checkAccess_();
  if (!auth.allowed) throw new Error('Akses ditolak: ' + auth.reason);
  return auth;
}

function FIN_masterSs_() {
  return SpreadsheetApp.openById(FIN_CFG.MASTER_SPREADSHEET_ID);
}

function FIN_selfSs_() {
  try {
    return FIN_openModuleSpreadsheet_(FIN_CFG.MODULE_ALIASES);
  } catch (err) {
    // Saat setup pertama, row Master_Module mungkin belum dibuat. Fallback hanya untuk editor/script bound.
    return SpreadsheetApp.getActiveSpreadsheet();
  }
}

function FIN_getSalesSs_() {
  return FIN_openModuleSpreadsheet_(['SALES', 'PENJUALAN']);
}

function FIN_getPurchSs_() {
  return FIN_openModuleSpreadsheet_(['PURCH', 'PURCHASING', 'PEMBELIAN', 'BELANJA']);
}

function FIN_getProdSs_() {
  return FIN_openModuleSpreadsheet_(['PROD', 'PRODUKSI']);
}

function FIN_getGudangSs_() {
  return FIN_openModuleSpreadsheet_(['WH', 'GUDANG', 'WAREHOUSE']);
}

function FIN_getOmniSs_() {
  return FIN_openModuleSpreadsheet_(['OMNI', 'OMNICHANNEL', 'MARKETPLACE', 'BIGSELLER']);
}

function FIN_openModuleSpreadsheet_(aliases) {
  aliases = (aliases || []).map(FIN_cleanKey_);

  var masterSs = FIN_masterSs_();
  var sh = masterSs.getSheetByName('Master_Module');
  if (!sh) throw new Error('Sheet Master_Module tidak ditemukan di Master Database.');

  var table = FIN_readSheetTable_(sh);
  if (!table.rows.length) throw new Error('Master_Module kosong.');

  var debugRows = [];
  for (var i = 0; i < table.rows.length; i++) {
    var row = table.rows[i];
    var codeRaw = FIN_val_(row, ['Module_Code', 'Module Code', 'Kode Modul', 'Code']);
    var nameRaw = FIN_val_(row, ['Module_Name', 'Module Name', 'Nama Modul', 'Name']);
    var statusRaw = FIN_val_(row, ['Status']);

    var code = FIN_cleanKey_(codeRaw);
    var name = FIN_cleanKey_(nameRaw);
    var active = FIN_isModuleActive_(statusRaw);
    debugRows.push('row ' + (i + 2) + ' code=' + codeRaw + ' name=' + nameRaw + ' status=' + statusRaw + ' active=' + active);

    if (!active) continue;
    var matched = aliases.some(function(a) {
      return code === a || name === a || code.indexOf(a) !== -1 || name.indexOf(a) !== -1 || a.indexOf(code) !== -1;
    });
    if (!matched) continue;

    var id = FIN_extractSpreadsheetId_(FIN_val_(row, ['Spreadsheet_ID', 'Spreadsheet ID', 'ID Spreadsheet', 'Sheet ID']));
    if (!id) id = FIN_extractSpreadsheetId_(FIN_val_(row, ['Spreadsheet_URL', 'Spreadsheet URL', 'URL Spreadsheet']));
    if (!id) throw new Error('Spreadsheet_ID kosong untuk modul ' + codeRaw + ' / ' + nameRaw);
    return SpreadsheetApp.openById(id);
  }

  throw new Error('Modul tidak ditemukan di Master_Module. Dicari: ' + aliases.join(', ') + '\n' + debugRows.join('\n'));
}

function FIN_isModuleActive_(status) {
  var s = FIN_cleanKey_(status);
  if (!s) return true;
  var inactive = ['INACTIVE', 'NONAKTIF', 'DISABLED', 'OFF', 'FALSE', 'STOP', 'STOPPED', 'ARCHIVE', 'ARSIP'];
  return inactive.indexOf(s) === -1;
}

function FIN_extractSpreadsheetId_(value) {
  var s = String(value || '').trim();
  if (!s) return '';
  if (/^[a-zA-Z0-9-_]{25,}$/.test(s) && s.indexOf('/') === -1) return s;
  var m = s.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return m ? m[1] : '';
}

/* =========================
 * SETUP & TESTS
 * ========================= */

function FIN_getBootstrap(emailOp, pasporOp) {
  var auth = FIN_requirePassport_(emailOp, pasporOp);
  var hb = ERP_readGlobalHeartbeat_();
  return {
    success: true,
    auth: { email: auth.email, displayName: auth.displayName || auth.email, reason: auth.reason, role: auth.role || '', department: auth.department || '' },
    user: { email: auth.email, name: auth.displayName || auth.email, role: auth.role || '', department: auth.department || '' },
    moduleCode: FIN_CFG.MODULE_CODE,
    version: FIN_CFG.VERSION,
    heartbeat: hb,
    portalUrl: ERP_withLoginParam_(ERP_getPortalUrl_()),
    passport: pasporOp || auth.passport || auth.passportId || '',
    paspor: pasporOp || auth.passport || auth.passportId || '',
    moduleLinks: FIN_getModuleLinks_(auth, pasporOp || auth.passport || auth.passportId || ''),
    coa: FIN_getCoa_(),
    defaultTanggal: FIN_dateKey_(new Date())
  };
}

function FIN_sumDpMasukForPo_(journals, noPo, customer) {
  var refKey = FIN_cleanKey_(noPo);
  if (!refKey) return 0;
  return (journals || []).reduce(function(sum, j) {
    if (FIN_cleanKey_(j.noReferensi) !== refKey) return sum;
    if (!FIN_accountMatch_(j.akunKredit, ['UANGMUKAPENJUALAN', 'DPCUSTOMER', 'DPPELANGGAN'])) return sum;
    if (customer && j.namaKontak && FIN_cleanKey_(j.namaKontak) !== FIN_cleanKey_(customer)) return sum;
    return sum + FIN_toNumber_(j.nominal);
  }, 0);
}

function FIN_upsertJurnalBySourceKey_(sourceKey, obj) {
  var sh = FIN_ensureSheet_(FIN_selfSs_(), FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
  var table = FIN_readSheetTable_(sh);
  var targetRow = 0;
  table.rows.forEach(function(r) {
    if (String(FIN_val_(r, ['Source_Key']) || '').trim() === sourceKey) targetRow = r._rowNumber;
  });
  obj.Source_Key = sourceKey;
  obj['Source_Key'] = sourceKey;
  if (!targetRow) {
    FIN_appendObjectByHeaders_(sh, FIN_HEADERS.JURNAL, obj);
    return 'APPEND';
  }
  FIN_HEADERS.JURNAL.forEach(function(h) { if (obj[h] !== undefined) FIN_setByHeader_(sh, targetRow, h, obj[h]); });
  return 'UPDATE';
}

function FIN_accountNameByCandidates_(candidates, fallback) {
  candidates = candidates || [];
  var coa = FIN_getCoa_();
  for (var i = 0; i < candidates.length; i++) {
    var target = FIN_cleanKey_(candidates[i]);
    for (var j = 0; j < coa.length; j++) {
      var nameKey = FIN_cleanKey_(coa[j].name);
      if (nameKey === target || nameKey.indexOf(target) !== -1 || target.indexOf(nameKey) !== -1) return coa[j].name;
    }
  }
  return fallback || (candidates[0] || '');
}

function FIN_batchUpsertJournalsBySourceKey_(rows, options) {
  options = options || {};
  rows = rows || [];
  var sh = FIN_ensureSheet_(FIN_selfSs_(), FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
  FIN_ensureColumns_(sh, FIN_HEADERS.JURNAL);
  var table = FIN_readSheetTable_(sh);
  var existing = {};
  table.rows.forEach(function(r) {
    var sk = String(FIN_val_(r, ['Source_Key']) || '').trim();
    if (sk) existing[sk] = r._rowNumber;
  });

  var appendObjs = [];
  var updateObjs = [];
  var skipped = 0;
  var processedWrites = 0;
  var limit = Math.max(0, FIN_toNumber_(options.limit || 0));
  var limited = false;

  rows.forEach(function(obj) {
    if (limited) return;
    var sk = String(obj.Source_Key || obj['Source_Key'] || '').trim();
    if (!sk) return;
    obj.Source_Key = sk;
    obj['Source_Key'] = sk;
    var rowNo = existing[sk];
    if (rowNo) {
      if (options.updateExisting === true) {
        if (limit && processedWrites >= limit) { limited = true; return; }
        updateObjs.push({ rowNumber: rowNo, obj: obj });
        processedWrites++;
      } else {
        skipped++;
      }
      return;
    }
    if (limit && processedWrites >= limit) { limited = true; return; }
    appendObjs.push(obj);
    existing[sk] = -1;
    processedWrites++;
  });

  if (appendObjs.length) {
    var values = appendObjs.map(function(obj) { return FIN_HEADERS.JURNAL.map(function(h) { return obj[h] !== undefined ? obj[h] : ''; }); });
    sh.getRange(sh.getLastRow() + 1, 1, values.length, FIN_HEADERS.JURNAL.length).setValues(values);
  }

  updateObjs.forEach(function(u) {
    var values = FIN_HEADERS.JURNAL.map(function(h) { return u.obj[h] !== undefined ? u.obj[h] : ''; });
    sh.getRange(u.rowNumber, 1, 1, FIN_HEADERS.JURNAL.length).setValues([values]);
  });

  return {
    synced: appendObjs.length + updateObjs.length,
    appended: appendObjs.length,
    updated: updateObjs.length,
    skippedExisting: skipped,
    limited: limited,
    remainingApprox: limited ? Math.max(rows.length - skipped - appendObjs.length - updateObjs.length, 0) : 0
  };
}

function FIN_feeAccountByCandidates_(candidates) {
  return FIN_accountNameByCandidates_(candidates || ['Biaya Administrasi Bank'], 'Biaya Administrasi Bank');
}

function FIN_isDeletedValue_(v) {
  var s = FIN_cleanKey_(v);
  return s === 'TRUE' || s === 'YA' || s === 'Y' || s === '1' || s === 'DELETED';
}

function FIN_purchRefKey_(source, ref, vendor, debitAccount) {
  return 'PURCH_BILL_' + FIN_cleanKey_(source) + '_' + FIN_cleanKey_(ref) + '_' + FIN_cleanKey_(vendor) + '_' + FIN_cleanKey_(debitAccount).slice(0, 30);
}

function FIN_purchaseDebitAccount_(source, kategori, itemName) {
  var k = FIN_cleanKey_([kategori, itemName].join(' '));
  if (FIN_cleanKey_(source) === 'MAKLUN') {
    if (k.indexOf('JAHIT') !== -1) return FIN_accountNameByCandidates_(['Biaya Jahit', 'Biaya Jahit Kiral'], 'Biaya Jahit');
    if (k.indexOf('SUBLIM') !== -1) return FIN_accountNameByCandidates_(['Biaya Sublim', 'Biaya Sublim Kiral'], 'Biaya Sublim');
    if (k.indexOf('SABLON') !== -1) return FIN_accountNameByCandidates_(['Biaya Sablon', 'Biaya Sablon Kiral'], 'Biaya Sablon');
    if (k.indexOf('BORDIR') !== -1) return FIN_accountNameByCandidates_(['Biaya Bordir', 'Biaya Bordir Kiral'], 'Biaya Bordir');
    if (k.indexOf('POTONG') !== -1) return FIN_accountNameByCandidates_(['Biaya Potong', 'Biaya Potong Kiral'], 'Biaya Potong');
    return FIN_accountNameByCandidates_(['HPP', 'Biaya Jahit', 'Biaya Maklun'], 'HPP');
  }
  if (k.indexOf('PACKAGING') !== -1 || k.indexOf('PACKING') !== -1 || k.indexOf('VERPACK') !== -1 || k.indexOf('AKSESORIS') !== -1) {
    return FIN_accountNameByCandidates_(['Persediaan Verpacking', 'Persediaan Verpacking Kiral'], 'Persediaan Verpacking');
  }
  if (k.indexOf('BAHAN') !== -1 || k.indexOf('KAIN') !== -1 || k.indexOf('TINTA') !== -1 || k.indexOf('PAPER') !== -1 || k.indexOf('KERTAS') !== -1) {
    return FIN_accountNameByCandidates_(['Persediaan Bahan Baku', 'Persediaan Bahan Baku Kiral'], 'Persediaan Bahan Baku');
  }
  if (k.indexOf('MESIN') !== -1) return FIN_accountNameByCandidates_(['Mesin'], 'Mesin');
  if (k.indexOf('PERALATANPRODUKSI') !== -1) return FIN_accountNameByCandidates_(['Peralatan Produksi'], 'Peralatan Produksi');
  if (k.indexOf('PERALATAN') !== -1 || k.indexOf('ATK') !== -1) return FIN_accountNameByCandidates_(['Biaya Peralatan/ATK', 'Peralatan Kantor'], 'Biaya Peralatan/ATK');
  if (k.indexOf('KONSUMSI') !== -1) return FIN_accountNameByCandidates_(['Biaya Konsumsi'], 'Biaya Konsumsi');
  if (k.indexOf('LISTRIK') !== -1) return FIN_accountNameByCandidates_(['Biaya Listrik Produksi', 'Biaya Listrik Kantor'], 'Biaya Listrik Produksi');
  if (k.indexOf('PERBAIKAN') !== -1 || k.indexOf('MAINTENANCE') !== -1 || k.indexOf('PEMELIHARAAN') !== -1) return FIN_accountNameByCandidates_(['Biaya Pemeliharaan Mesin', 'Biaya Pemeliharaan Peralatan Prod.', 'Biaya Pemeliharaan Kendaraan'], 'Biaya Pemeliharaan Mesin');
  return FIN_accountNameByCandidates_(['Biaya Perlengkapan Produksi', 'Biaya Peralatan/ATK'], 'Biaya Perlengkapan Produksi');
}

function FIN_isDeletedRow_(r) {
  var val = FIN_val_(r, ['Is_Deleted', 'Deleted', 'Is Deleted']);
  return ['TRUE', 'YES', 'YA', 'Y', '1', 'DELETED'].indexOf(FIN_cleanKey_(val)) !== -1;
}

function FIN_inventoryCreditAccountForMaterial_(kategori, itemName) {
  var k = FIN_cleanKey_([kategori, itemName].join(' '));
  if (k.indexOf('PACKAGING') !== -1 || k.indexOf('PACKING') !== -1 || k.indexOf('VERPACK') !== -1 || k.indexOf('AKSESORIS') !== -1) {
    return FIN_accountNameByCandidates_(['Persediaan Verpacking', 'Persediaan Verpacking Kiral'], 'Persediaan Verpacking');
  }
  return FIN_accountNameByCandidates_(['Persediaan Bahan Baku', 'Persediaan Bahan Baku Kiral'], 'Persediaan Bahan Baku');
}

function FIN_purchaseAdvanceMatch_(j, vendor, ref) {
  if (!FIN_accountMatch_(j.akunDebit, ['Uang Muka Pembelian', 'UANG_MUKA_PEMBELIAN'])) return false;
  if (!vendor || FIN_cleanKey_(j.namaKontak) !== FIN_cleanKey_(vendor)) return false;
  if (!ref) return false;
  return FIN_cleanKey_(j.noReferensi) === FIN_cleanKey_(ref);
}

function FIN_getModuleLinks_(auth, paspor) {
  try {
    auth = auth || FIN_RUNTIME_AUTH || FIN_requireAccess_();
    paspor = paspor || auth.passport || auth.passportId || '';
    var sh = FIN_masterSs_().getSheetByName('Master_Module');
    if (!sh) return [];
    var table = FIN_readSheetTable_(sh);
    return table.rows.map(function(r) {
      var url = FIN_val_(r, ['Web_App_URL', 'Web App URL']);
      return {
        code: FIN_val_(r, ['Module_Code']),
        name: FIN_val_(r, ['Module_Name']),
        nama: FIN_val_(r, ['Module_Name']),
        url: ERP_appendPassportToUrl_(url, auth, paspor),
        status: FIN_val_(r, ['Status'])
      };
    }).filter(function(x) { return x.url && FIN_isModuleActive_(x.status); });
  } catch (err) {
    return [];
  }
}

/* =========================
 * CALCULATIONS
 * ========================= */

function FIN_getMasterItemTypeMap_() {
  var map = {};
  try {
    var sh = FIN_masterSs_().getSheetByName('Master_Item');
    if (!sh) return map;
    var t = FIN_readSheetTable_(sh);
    t.rows.forEach(function(r) {
      var name = String(FIN_val_(r, ['Item_Name', 'Nama_Item', 'Nama Item', 'Nama_Barang', 'Nama Barang', 'Nama_Produk', 'Nama Produk', 'Internal_Item_Name', 'Item', 'Produk']) || '').trim();
      if (!name) return;
      map[FIN_cleanKey_(name)] = {
        name: name,
        type: FIN_cleanKey_(FIN_val_(r, ['Item_Type', 'Item Type', 'Tipe Item', 'Jenis Item'])),
        defaultCost: FIN_toNumber_(FIN_val_(r, ['Default_Cost', 'Unit_Cost', 'HPP', 'Harga_Beli', 'Harga Beli', 'Cost']))
      };
    });
  } catch (err) {}
  return map;
}

function FIN_getProduksiRows_() {
  var rows = [];
  try {
    var ss = FIN_getProdSs_();
    var sh = ss.getSheetByName('Data_Produksi');
    if (!sh) return rows;
    var t = FIN_readSheetTable_(sh);
    t.rows.forEach(function(r) {
      if (FIN_isDeletedRow_(r)) return;
      var tgl = FIN_parseDate_(FIN_val_(r, ['Tanggal', 'Tgl']));
      rows.push({
        tanggal: FIN_displayDate_(tgl),
        tanggalKey: FIN_dateKey_(tgl),
        spk: String(FIN_val_(r, ['SPK', 'No SPK']) || '').trim(),
        proses: FIN_val_(r, ['Proses']),
        pic: FIN_val_(r, ['PIC']),
        bahan: FIN_val_(r, ['Bahan']),
        qtyBahan: FIN_toNumber_(FIN_val_(r, ['Qty Bahan', 'Qty_Bahan'])),
        produk: FIN_val_(r, ['Produk', 'Item']),
        qty: FIN_toNumber_(FIN_val_(r, ['Qty', 'Jumlah'])),
        nilaiBahan: FIN_toNumber_(FIN_val_(r, ['Nilai Bahan', 'Nilai_Bahan'])),
        upahBorongan: FIN_toNumber_(FIN_val_(r, ['Upah Borongan', 'Upah_Borongan'])),
        overhead: FIN_toNumber_(FIN_val_(r, ['Biaya Ekstra', 'Biaya Tambahan', 'Overhead']))
      });
    });
  } catch (err) {}
  return rows;
}

function FIN_latestItemCostMap_(stockRows) {
  var map = {};
  (stockRows || []).forEach(function(m) {
    var k = FIN_cleanKey_(m.itemName);
    var costPack = FIN_pickMovementCost_(m, null, { preferFinal: true });
    var cost = FIN_toNumber_(costPack.unitCost) || FIN_toNumber_(m.unitCostFinal) || FIN_toNumber_(m.unitCostProvisional) || FIN_toNumber_(m.unitCost);
    if (!k || cost <= 0) return;
    var type = FIN_cleanKey_(m.movementType);
    if (type.indexOf('IN') !== -1 || FIN_cleanKey_(m.direction) === 'IN') {
      if (!map[k] || String(m.tanggalKey) >= String(map[k].tanggalKey || '')) {
        map[k] = { cost: cost, tanggalKey: m.tanggalKey, costStatus: costPack.status || m.costStatus || '' };
      }
    }
  });
  return map;
}

function FIN_isFinalCostStatus_(status) {
  return FIN_cleanKey_(status) === 'FINAL';
}

function FIN_calcHutangUpahProduksiVirtual_(prodRows, journals) {
  var totalUpah = (prodRows || []).reduce(function(sum, r) { return sum + FIN_toNumber_(r.upahBorongan); }, 0);
  var paid = (journals || []).reduce(function(sum, j) {
    var debit = FIN_cleanKey_(j.akunDebit);
    if (debit.indexOf('HUTANGGAJI') !== -1 || debit.indexOf('HUTANGUPAH') !== -1 || debit.indexOf('HUTANGOPERATOR') !== -1) return sum + FIN_toNumber_(j.nominal);
    return sum;
  }, 0);
  return Math.max(totalUpah - paid, 0);
}

function FIN_sum_(rows, field) {
  return (rows || []).reduce(function(sum, x) { return sum + FIN_toNumber_(x[field]); }, 0);
}

/* =========================
 * SHEET HELPERS
 * ========================= */

function FIN_ensureSheet_(ss, name, headers) {
  var sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (headers && headers.length) {
    if (sh.getLastRow() === 0 || sh.getLastColumn() === 0) {
      sh.getRange(1, 1, 1, headers.length).setValues([headers]);
      sh.setFrozenRows(1);
    } else {
      FIN_ensureColumns_(sh, headers);
    }
  }
  return sh;
}

function FIN_ensureColumns_(sh, columns) {
  columns = columns || [];
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, columns.length).setValues([columns]);
    sh.setFrozenRows(1);
    return;
  }
  var lastCol = Math.max(sh.getLastColumn(), 1);
  var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  var keys = headers.map(FIN_headerKey_);
  columns.forEach(function(c) {
    if (keys.indexOf(FIN_headerKey_(c)) === -1) {
      sh.getRange(1, sh.getLastColumn() + 1).setValue(c);
      keys.push(FIN_headerKey_(c));
    }
  });
  sh.setFrozenRows(1);
}

function FIN_readSheetTable_(sh) {
  var lastRow = sh.getLastRow();
  var lastCol = sh.getLastColumn();
  if (lastRow < 1 || lastCol < 1) return { headers: [], rows: [], map: {} };
  var values = sh.getRange(1, 1, lastRow, lastCol).getValues();
  var headers = values[0].map(function(h) { return String(h || '').trim(); });
  var map = {};
  headers.forEach(function(h, i) { var k = FIN_headerKey_(h); if (k) map[k] = i; });
  var rows = [];
  for (var r = 1; r < values.length; r++) {
    var rowObj = { _rowNumber: r + 1, _raw: values[r], _headers: headers, _map: map };
    var hasValue = false;
    for (var c = 0; c < headers.length; c++) {
      var val = values[r][c];
      if (val !== '' && val !== null && val !== undefined) hasValue = true;
      rowObj[FIN_headerKey_(headers[c])] = val;
    }
    if (hasValue) rows.push(rowObj);
  }
  return { headers: headers, rows: rows, map: map, values: values };
}

function FIN_appendObjectByHeaders_(sh, headers, obj) {
  FIN_ensureColumns_(sh, headers);
  var table = FIN_readSheetTable_(sh);
  var row = table.headers.map(function(h) {
    return obj[h] !== undefined ? obj[h] : obj[FIN_headerKey_(h)] !== undefined ? obj[FIN_headerKey_(h)] : '';
  });
  sh.appendRow(row);
}

function FIN_setByHeader_(sh, rowNumber, headerName, value) {
  var table = FIN_readSheetTable_(sh);
  var idx = table.map[FIN_headerKey_(headerName)];
  if (idx === undefined) {
    FIN_ensureColumns_(sh, [headerName]);
    table = FIN_readSheetTable_(sh);
    idx = table.map[FIN_headerKey_(headerName)];
  }
  sh.getRange(rowNumber, idx + 1).setValue(value);
}

function FIN_val_(row, names) {
  names = Array.isArray(names) ? names : [names];
  for (var i = 0; i < names.length; i++) {
    var k = FIN_headerKey_(names[i]);
    if (row[k] !== undefined && row[k] !== null && row[k] !== '') return row[k];
  }
  return '';
}

/* =========================
 * FORMAT HELPERS
 * ========================= */

function FIN_norm_(v) { return String(v === null || v === undefined ? '' : v).trim(); }

function FIN_normEmail_(v) { return FIN_norm_(v).toLowerCase(); }

function FIN_cleanKey_(v) { return FIN_norm_(v).toUpperCase().replace(/[^A-Z0-9]/g, ''); }

function FIN_headerKey_(v) { return FIN_norm_(v).toUpperCase().replace(/[^A-Z0-9]/g, ''); }

function FIN_toNumber_(value) {
  if (typeof value === 'number') return isNaN(value) ? 0 : value;
  if (value instanceof Date) return 0;
  var s = String(value || '').trim();
  if (!s) return 0;
  s = s.replace(/[^0-9,.-]/g, '');
  if (!s || s === '-' || s === ',' || s === '.') return 0;

  var lastComma = s.lastIndexOf(',');
  var lastDot = s.lastIndexOf('.');
  if (lastComma !== -1 && lastDot !== -1) {
    if (lastComma > lastDot) {
      s = s.replace(/\./g, '').replace(',', '.');
    } else {
      s = s.replace(/,/g, '');
    }
  } else if (lastComma !== -1) {
    var partsC = s.split(',');
    if (partsC.length === 2 && partsC[1].length <= 2) s = partsC[0].replace(/\./g, '') + '.' + partsC[1];
    else s = s.replace(/,/g, '');
  } else if (lastDot !== -1) {
    var partsD = s.split('.');
    if (partsD.length > 2) s = s.replace(/\./g, '');
  }
  var n = Number(s);
  return isNaN(n) ? 0 : n;
}

function FIN_parseDate_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) return value;
  if (!value) return new Date();
  var s = String(value).trim();
  if (!s) return new Date();

  var d = new Date(s);
  if (!isNaN(d.getTime())) return d;

  var m = s.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})/);
  if (m) {
    var day = Number(m[1]);
    var month = Number(m[2]) - 1;
    var year = Number(m[3]);
    if (year < 100) year += 2000;
    return new Date(year, month, day);
  }
  return new Date();
}

function FIN_dateKey_(value) {
  var d = FIN_parseDate_(value);
  return Utilities.formatDate(d, FIN_CFG.TZ, 'yyyy-MM-dd');
}

function FIN_displayDate_(value) {
  var d = FIN_parseDate_(value);
  return Utilities.formatDate(d, FIN_CFG.TZ, 'dd/MM/yyyy');
}

function FIN_displayDateTime_(value) {
  var d = FIN_parseDate_(value);
  return Utilities.formatDate(d, FIN_CFG.TZ, 'dd/MM/yyyy HH:mm:ss');
}

function FIN_makeRef_(prefix) {
  return String(prefix || 'REF') + '-' + Utilities.formatDate(new Date(), FIN_CFG.TZ, 'yyMMdd-HHmmss');
}

function FIN_makeSourceKey_(prefix) {
  return String(prefix || 'SRC').replace(/\s+/g, '_') + '|' + Utilities.getUuid();
}

function FIN_escapeHtml_(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function FIN_requirePassport_(emailOp, pasporOp) {
  emailOp = ERP_normEmail_(emailOp || '');
  pasporOp = ERP_clean_(pasporOp || '');
  if (!emailOp || !pasporOp) throw new Error('Sesi Finance tidak lengkap. Masuk ulang dari Portal.');
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth || !auth.allowed) throw new Error('Akses Finance ditolak: ' + (auth && auth.reason ? auth.reason : 'UNKNOWN'));
  if (auth.email && emailOp && ERP_normEmail_(auth.email) !== emailOp) throw new Error('Passport tidak cocok dengan email aktif. Masuk ulang dari Portal.');
  FIN_RUNTIME_AUTH = auth;
  return auth;
}

function FIN_requirePassportFromArgs_(args) {
  var a = Array.prototype.slice.call(args || []);
  var maybeEmail = a.length >= 2 ? a[a.length - 2] : '';
  var maybePass = a.length >= 1 ? a[a.length - 1] : '';

  // v1.7.3: jangan anggap payload tunggal sebagai passport.
  // Beberapa wrapper seperti FIN_catatPenerimaan/FIN_catatPengeluaran sudah validasi session,
  // lalu memanggil FIN_simpanJurnal(payload) secara internal. Pada kondisi itu arguments hanya
  // berisi 1 object payload; versi lama keliru membaca object payload sebagai paspor dan error
  // "Sesi Finance tidak lengkap". Auth pair hanya valid kalau dua argumen terakhir berupa string.
  var hasAuthPair = a.length >= 2 &&
    (typeof maybeEmail === 'string' || maybeEmail instanceof String) &&
    (typeof maybePass === 'string' || maybePass instanceof String) &&
    (String(maybeEmail).trim() || String(maybePass).trim());

  if (hasAuthPair) return FIN_requirePassport_(maybeEmail, maybePass);
  if (FIN_RUNTIME_AUTH && FIN_RUNTIME_AUTH.allowed) return FIN_RUNTIME_AUTH;
  // Editor/manual fallback: tetap cek Master_User + hak akses FIN, tapi tidak butuh passport.
  var auth = FIN_requireAccess_();
  FIN_RUNTIME_AUTH = auth;
  return auth;
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
  return HtmlService.createHtmlOutput('<base target="_top"><div style="font-family:Arial,sans-serif;text-align:center;margin-top:13vh;background:#f8fafc;padding:48px;border-radius:22px;max-width:680px;margin-left:auto;margin-right:auto;box-shadow:0 10px 25px rgba(0,0,0,.12)"><div style="font-size:78px">⛔</div><h1 style="color:#ef4444">AKSES / SESSION DITOLAK</h1><p>Alasan: <b>'+ERP_escapeHtml_(auth && auth.reason || 'UNKNOWN')+'</b></p><p>Email: <b>'+ERP_escapeHtml_(auth && auth.email || '(kosong)')+'</b></p><p>Silakan masuk dari Portal/Beranda supaya passport session valid.</p>'+btn+'</div>').setTitle('Akses Ditolak');
}

function ERP_globalHeartbeat(clientVersion, emailOp, pasporOp) {
  if (arguments.length >= 4) {
    clientVersion = arguments[1];
    emailOp = arguments[2];
    pasporOp = arguments[3] || arguments[0] || '';
  }
  var auth = ERP_securityCheck_(emailOp, pasporOp, true);
  if (!auth.allowed) return { ok:false, success:false, reason:auth.reason || 'SESSION_INVALID', shouldLogout:true, portalUrl:ERP_withLoginParam_(ERP_getPortalUrl_()) };
  FIN_RUNTIME_AUTH = auth;
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

function FIN_touchMutation_(reason) { try { ERP_markDataChanged_(reason || ('Mutation from ' + ERP_GLOBAL_CFG.MODULE_CODE)); } catch(e) {} }

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
  var can = isAdmin || ERP_userCanOpenModule_({ allowedModules:allowedModules, role:role, department:department }, ERP_GLOBAL_CFG.MODULE_CODE, ERP_GLOBAL_CFG.MODULE_NAME, FIN_CFG.MODULE_ALIASES || []);
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
 * v1.5.2 SOURCE READER OVERRIDES
 * Data_Jurnal tidak lagi menjadi tempat pemindahan data Sales/Purchasing/Omni.
 * Data_Jurnal hanya untuk kas/bank dan jurnal penyesuaian/manual.
 * ========================= */

function FIN_isSourceAutoJournal_(j) {
  var flag = FIN_cleanKey_(j && (j.autoFlag || j.Auto_Flag || ''));
  var sk = FIN_cleanKey_(j && (j.sourceKey || j.Source_Key || ''));
  var op = FIN_cleanKey_(j && (j.operator || j.Operator || ''));
  if (flag === 'AUTO') return true;
  if (op.indexOf('AUTO') !== -1) return true;
  return sk.indexOf('SALESINV') === 0 || sk.indexOf('OMNI') === 0 || sk.indexOf('PURCH') === 0 || sk.indexOf('PROD') === 0 || sk.indexOf('WH') === 0;
}

function FIN_manualJournalsOnly_(journals) {
  return (journals || []).filter(function(j) { return !FIN_isSourceAutoJournal_(j); });
}

function FIN_mapToRows_(map) {
  return Object.keys(map || {}).map(function(k) { return map[k]; }).filter(function(x) { return Math.abs(FIN_toNumber_(x.nominal)) > 0.00001; }).sort(function(a,b){ return String(a.akun || a.label).localeCompare(String(b.akun || b.label)); });
}

function FIN_sectionRow_(label, nominal, source) { return { label: label, akun: label, nominal: FIN_toNumber_(nominal), source: source || '' }; }

function FIN_groupRefundDiscountRows_(adjustments, returnsRows) {
  var total = 0;
  (adjustments || []).forEach(function(a) {
    var k = FIN_cleanKey_([a.jenis, a.ref].join(' '));
    if (k.indexOf('REFUND') !== -1 || k.indexOf('DISKON') !== -1 || k.indexOf('RETUR') !== -1 || k.indexOf('RETURN') !== -1) total += Math.abs(FIN_toNumber_(a.nilai));
  });
  // Omni_Retur saat ini menjadi referensi marketplace/QC; nilai refund final tetap menunggu settlement/adjustment.
  return total ? [FIN_sectionRow_('Refund/Diskon Penjualan', total, 'Data_Keuangan_Penyesuaian')] : [FIN_sectionRow_('Refund/Diskon Penjualan', 0, 'Omni_Retur reference / Settlement adjustment')];
}

function FIN_resolvePeriodKey_(filter) { return FIN_resolveReportRange_(filter || {}).periodKey; }

function FIN_periodEndKey_(periodOrRange) { return FIN_rangeFromPeriodArg_(periodOrRange).endKey; }

function FIN_filterRowsThroughPeriod_(rows, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  return (rows || []).filter(function(r){ var k = FIN_rowDateKey_(r); return !k || k <= range.endKey; });
}

function FIN_filterRowsInPeriod_(rows, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  return (rows || []).filter(function(r){ return FIN_isDateKeyInRange_(FIN_rowDateKey_(r), range); });
}

function FIN_reportLabel_(range) {
  range = FIN_rangeFromPeriodArg_(range);
  if (range.startKey === range.periodKey + '-01' && range.endKey === FIN_periodEndKey_(range.periodKey)) return range.periodKey;
  return range.startKey + ' s.d. ' + range.endKey;
}

function FIN_getFinanceHeavyData(filter) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  filter = filter || {};
  var range = FIN_resolveReportRange_(filter), warnings = [], journals = [], invoices = [], hutang = [], dpCustomers = [], omniFinance = FIN_emptyOmniFinance_(), omniReceivablesAsOf = { rows:[], marketplaceOutstanding:0, posOutstanding:0, totalOutstanding:0 };
  try { journals = FIN_getJurnalRows_(); } catch (e1) { warnings.push({ source: 'Data_Jurnal', message: e1.message || String(e1) }); }
  var journalsAsOf = FIN_filterRowsThroughPeriod_(journals, range);
  try { invoices = FIN_filterRowsThroughPeriod_(FIN_getSalesInvoices_(journalsAsOf), range); } catch (e2) { warnings.push({ source: 'Data_Invoice', message: e2.message || String(e2) }); }
  try { omniFinance = FIN_getOmniFinanceDataDaily_(range, journalsAsOf); omniReceivablesAsOf = FIN_getOmniReceivablesAsOf_(range, journalsAsOf); invoices = invoices.concat(omniReceivablesAsOf.rows || []); } catch (eOmni) { warnings.push({ source: 'Omni Finance Handoff', message: eOmni.message || String(eOmni) }); }
  try { hutang = FIN_filterRowsThroughPeriod_(FIN_getHutangRows_(), range); } catch (e3) { warnings.push({ source: 'Purchasing Payables', message: e3.message || String(e3) }); }
  try { dpCustomers = FIN_getDPCustomerRows_(invoices, journalsAsOf); } catch (e4) { warnings.push({ source: 'DP Customer', message: e4.message || String(e4) }); }
  var cashBalance = FIN_calcCashBalance_(journalsAsOf), totalPiutang = FIN_sum_(invoices, 'sisaTagihan'), totalHutang = FIN_sum_(hutang, 'sisaHutang'), totalDpOpen = FIN_sum_(dpCustomers, 'saldoDp'), cogmCogs;
  try { cogmCogs = FIN_getCogmCogsEngine_(journalsAsOf, range); } catch (e5) { warnings.push({ source: 'Gudang/Produksi COGM COGS', message: e5.message || String(e5) }); cogmCogs = FIN_emptyCogmCogs_(range.periodKey, 'Gagal memuat COGM/COGS: ' + (e5.message || e5)); }
  try { FIN_applyMarketplaceAndTransitAsOf_(cogmCogs, journalsAsOf, range); } catch (eBal) { warnings.push({ source: 'Marketplace Balance / Transit As-Of', message: eBal.message || String(eBal) }); }
  var neraca = FIN_calcNeracaMvp_(cashBalance, totalPiutang, totalHutang, totalDpOpen, cogmCogs), labaRugi = FIN_calcLabaRugiSourceReader_(journals, invoices, range, omniFinance, cogmCogs);
  return { success: true, version: FIN_CFG.VERSION, mode: 'HEAVY_ONLY', heavyLoaded: true, generatedAt: FIN_displayDateTime_(new Date()), periodKey: range.periodKey, dateStart: range.startKey, dateEnd: range.endKey, periodLabel: FIN_reportLabel_(range), sourceWarnings: warnings, cogmCogs: cogmCogs, neraca: neraca, labaRugi: labaRugi };
}

/* =========================
 * v1.6.2 REVENUE ACCOUNT + OMNI DATEKEY FIX
 * - Akun pendapatan marketplace wajib memilih COA bertipe PENDAPATAN, bukan akun saldo/kas marketplace.
 * - Filter Omni_Order untuk laporan/piutang memakai header Tanggal Key bila ada, supaya aman dari format tanggal+jam.
 * - Rows laporan punya label tetap supaya POS / nama toko tidak berubah menjadi akun kas/bank.
 * ========================= */

function FIN_addAmount_(map, key, amount, meta) {
  key = String(key || '').trim() || 'Lain-lain';
  if (!map[key]) {
    var base = { label: key, akun: key, nominal: 0 };
    var m = meta || {};
    Object.keys(m).forEach(function(k) { base[k] = m[k]; });
    if (!base.label) base.label = key;
    if (!base.akun) base.akun = key;
    map[key] = base;
  }
  map[key].nominal += FIN_toNumber_(amount);
  return map[key];
}

function FIN_accountNameByCandidatesFiltered_(candidates, fallback, opt) {
  candidates = candidates || [];
  opt = opt || {};
  var coa = FIN_getCoa_();
  var typeWant = opt.type ? FIN_cleanKey_(opt.type) : '';
  var groupWant = opt.group ? FIN_cleanKey_(opt.group) : '';
  var denyNamePrefixes = (opt.denyNamePrefixes || []).map(function(x){ return FIN_cleanKey_(x); });
  var filtered = coa.filter(function(a) {
    if (!a || !a.name) return false;
    if (typeWant && FIN_cleanKey_(a.type) !== typeWant) return false;
    if (groupWant && FIN_cleanKey_(a.group) !== groupWant) return false;
    var nk = FIN_cleanKey_(a.name);
    for (var i=0; i<denyNamePrefixes.length; i++) {
      if (nk.indexOf(denyNamePrefixes[i]) === 0) return false;
    }
    return true;
  });
  for (var i = 0; i < candidates.length; i++) {
    var target = FIN_cleanKey_(candidates[i]);
    if (!target) continue;
    for (var j = 0; j < filtered.length; j++) {
      var nameKey = FIN_cleanKey_(filtered[j].name);
      if (nameKey === target) return filtered[j].name;
    }
  }
  for (var ii = 0; ii < candidates.length; ii++) {
    var target2 = FIN_cleanKey_(candidates[ii]);
    if (!target2) continue;
    for (var jj = 0; jj < filtered.length; jj++) {
      var nameKey2 = FIN_cleanKey_(filtered[jj].name);
      if (nameKey2.indexOf(target2) !== -1 || target2.indexOf(nameKey2) !== -1) return filtered[jj].name;
    }
  }
  return fallback || (candidates[0] || '');
}

function FIN_posRevenueAccount_() {
  return FIN_accountNameByCandidatesFiltered_(['POS', 'Penjualan POS', 'Pendapatan POS', 'Konvensional'], 'Konvensional', { type: 'PENDAPATAN', denyNamePrefixes: ['Saldo', 'Pos Sementara'] });
}

function FIN_dateKeySafe_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, FIN_CFG.TZ, 'yyyy-MM-dd');
  }
  if (value === null || value === undefined || value === '') return '';

  // Google Sheets kadang mengembalikan date key sebagai serial number jika format cell bukan teks.
  if (typeof value === 'number' && isFinite(value)) {
    // Serial date Google Sheets: 25569 = 1970-01-01.
    if (value > 20000 && value < 80000) {
      var ms = Math.round((value - 25569) * 86400 * 1000);
      return Utilities.formatDate(new Date(ms), FIN_CFG.TZ, 'yyyy-MM-dd');
    }
  }

  var s = String(value || '').trim();
  if (!s) return '';

  // Ambil yyyy-mm-dd / yyyy/mm/dd walaupun ada jam di belakang.
  var mIso = s.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})/);
  if (mIso) {
    return mIso[1] + '-' + ('0' + Number(mIso[2])).slice(-2) + '-' + ('0' + Number(mIso[3])).slice(-2);
  }

  // Format tampilan Indonesia dd/mm/yyyy atau dd-mm-yyyy.
  var mId = s.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})/);
  if (mId) {
    var yy = Number(mId[3]);
    if (yy < 100) yy += 2000;
    return yy + '-' + ('0' + Number(mId[2])).slice(-2) + '-' + ('0' + Number(mId[1])).slice(-2);
  }

  var parsed = FIN_parseDate_(s);
  if (parsed && !isNaN(parsed.getTime())) return Utilities.formatDate(parsed, FIN_CFG.TZ, 'yyyy-MM-dd');
  return '';
}

function FIN_rangeFromPeriodArg_(periodOrRange) {
  if (periodOrRange && typeof periodOrRange === 'object' && (periodOrRange.startKey || periodOrRange.dateStart || periodOrRange.dateEnd || periodOrRange.start || periodOrRange.end)) return FIN_resolveReportRange_(periodOrRange);
  if (typeof periodOrRange === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(periodOrRange)) return FIN_resolveReportRange_({ dateStart: periodOrRange, dateEnd: periodOrRange });
  if (typeof periodOrRange === 'string' && /^\d{4}-\d{2}$/.test(periodOrRange)) return FIN_resolveReportRange_({ period: periodOrRange });
  return FIN_resolveReportRange_({});
}

function FIN_isDateKeyInRange_(key, range) {
  var k = FIN_dateKeySafe_(key);
  if (!k) return false;
  range = FIN_rangeFromPeriodArg_(range);
  return k >= range.startKey && k <= range.endKey;
}

function FIN_rowDateKey_(r) {
  var raw = (r && (r.tanggalKey || r.dateKey || r.sourceDateKey || r.cutoffDateKey || r.movementDateKey || r.tglKey)) || '';
  if (raw) return FIN_dateKeySafe_(raw);
  var d = r && (r.tanggal || r.date || r.sourceDate || r.movementDate || r.cutoffDate);
  return FIN_dateKeySafe_(d);
}

function FIN_omniOrderDateKey_(r) {
  var candidatesKey = ['Tanggal Key', 'Tanggal_Key', 'Date Key', 'Date_Key', 'Order Date Key', 'Order_Date_Key', 'TanggalKey'];
  for (var i = 0; i < candidatesKey.length; i++) {
    var v = FIN_val_(r, candidatesKey[i]);
    var k = FIN_dateKeySafe_(v);
    if (k) return k;
  }
  var candidatesDate = ['Tanggal', 'Order Date', 'Tanggal Pesanan', 'Created Time', 'Waktu Pesanan', 'Created_At', 'Updated_At'];
  for (var j = 0; j < candidatesDate.length; j++) {
    var vv = FIN_val_(r, candidatesDate[j]);
    var kk = FIN_dateKeySafe_(vv);
    if (kk) return kk;
  }
  return '';
}

function FIN_dateKeyFromAny_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) return Utilities.formatDate(value, FIN_CFG.TZ, 'yyyy-MM-dd');
  if (typeof value === 'number' && isFinite(value) && value > 20000) {
    var epoch = new Date(Date.UTC(1899, 11, 30));
    var d = new Date(epoch.getTime() + Math.floor(value) * 86400000);
    return Utilities.formatDate(d, FIN_CFG.TZ, 'yyyy-MM-dd');
  }
  var s = String(value || '').trim();
  if (!s) return '';
  var m = s.match(/^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})/);
  if (m) return m[1] + '-' + ('0' + Number(m[2])).slice(-2) + '-' + ('0' + Number(m[3])).slice(-2);
  m = s.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})/);
  if (m) {
    var y = Number(m[3]); if (y < 100) y += 2000;
    return y + '-' + ('0' + Number(m[2])).slice(-2) + '-' + ('0' + Number(m[1])).slice(-2);
  }
  var d2 = new Date(s);
  if (!isNaN(d2.getTime())) return Utilities.formatDate(d2, FIN_CFG.TZ, 'yyyy-MM-dd');
  return '';
}

function FIN_omniOrderUnitCost_(r) {
  var unit = FIN_toNumber_(FIN_val_(r, ['Unit_Cost', 'Unit Cost', 'HPP_Rata_Rata']));
  if (unit > 0) return unit;
  var qty = FIN_toNumber_(FIN_val_(r, ['Qty', 'Qty Gudang', 'Quantity']));
  var cogs = FIN_omniOrderCogsValue_(r);
  return qty > 0 ? cogs / qty : 0;
}

function FIN_getSheetByCandidateNames_(ss, names) {
  names = names || [];
  for (var i = 0; i < names.length; i++) {
    var sh = ss && ss.getSheetByName(names[i]);
    if (sh) return sh;
  }
  return null;
}

function FIN_storeNameClean_(store) {
  return String(store || '').replace(/\s+/g, ' ').trim() || 'Marketplace';
}

function FIN_settlementDateKey_(row) {
  var key = FIN_dateKeyFromAny_(FIN_val_(row, ['Tanggal Key', 'Tanggal_Key', 'Date_Key', 'Settlement_Date_Key']));
  if (key) return key;
  return FIN_dateKeyFromAny_(FIN_val_(row, ['Tgl Pencairan', 'Tanggal Cair', 'Tanggal Pencairan', 'Tanggal', 'Date']));
}





// v1.9.3: tidak memakai override berantai; FIN_calcNeracaMvp_ membaca valuation secara langsung.

function FIN_appendObjectsByHeaders_(sh, headers, objects) {
  objects = objects || [];
  if (!objects.length) return;
  FIN_ensureColumns_(sh, headers);
  var table = FIN_readSheetTable_(sh);
  var rows = objects.map(function(obj){
    return table.headers.map(function(h){ return obj[h] !== undefined ? obj[h] : obj[FIN_headerKey_(h)] !== undefined ? obj[FIN_headerKey_(h)] : ''; });
  });
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, table.headers.length).setValues(rows);
}

function FIN_detectBankCsvHeaderRow_(data) {
  var bestIdx = 0, bestScore = -1;
  for (var i = 0; i < Math.min(data.length, 10); i++) {
    var keys = (data[i] || []).map(FIN_cleanKey_).join('|');
    var score = 0;
    ['TANGGAL','DATE','KETERANGAN','DESCRIPTION','DEBET','DEBIT','KREDIT','CREDIT','JUMLAH','AMOUNT','SALDO','BALANCE'].forEach(function(k){ if (keys.indexOf(k) !== -1) score++; });
    if (score > bestScore) { bestScore = score; bestIdx = i; }
  }
  return bestIdx;
}