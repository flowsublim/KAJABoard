/** Operasional Finance: jurnal, kas/bank, piutang, hutang, COA. */

function FIN_simpanJurnal(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};

  var nominal = FIN_toNumber_(payload.nominal);
  if (nominal <= 0) throw new Error('Nominal jurnal harus lebih dari 0.');
  if (!payload.akunDebit) throw new Error('Akun debit wajib diisi.');
  if (!payload.akunKredit) throw new Error('Akun kredit wajib diisi.');
  if (String(payload.akunDebit).trim() === String(payload.akunKredit).trim()) throw new Error('Akun debit dan kredit tidak boleh sama.');

  var row = {
    'Tanggal': FIN_dateKey_(payload.tanggal || new Date()),
    'Tipe Transaksi': payload.tipeTransaksi || 'JURNAL_MANUAL',
    'No. Referensi': payload.noReferensi || FIN_makeRef_('JRN'),
    'Nama Kontak': payload.namaKontak || '',
    'Keterangan': payload.keterangan || '',
    'Akun Debit': payload.akunDebit,
    'Akun Kredit': payload.akunKredit,
    'Nominal': nominal,
    'Operator': auth.email,
    'Source_Key': payload.sourceKey || FIN_makeSourceKey_('MANUAL'),
    'Auto_Flag': payload.autoFlag || 'MANUAL'
  };
  FIN_appendJurnal_(row);
  return { success: true, message: 'Jurnal tersimpan.', row: row };
}

function FIN_terimaPembayaranInvoice(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};

  var invoiceNo = String(payload.invoiceNo || '').trim();
  var nominal = FIN_toNumber_(payload.nominal);
  var bank = String(payload.akunKasBank || '').trim() || FIN_defaultCashAccount_();
  if (!invoiceNo) throw new Error('No invoice wajib diisi.');
  if (nominal <= 0) throw new Error('Nominal pembayaran harus lebih dari 0.');

  var inv = FIN_findSalesInvoiceByNo_(invoiceNo);
  if (!inv) throw new Error('Invoice tidak ditemukan di Modul Penjualan: ' + invoiceNo);

  var sourceKey = FIN_makeSourceKey_('SALES_PAY_' + invoiceNo);
  FIN_appendJurnal_({
    'Tanggal': FIN_dateKey_(payload.tanggal || new Date()),
    'Tipe Transaksi': 'PEMBAYARAN_INVOICE',
    'No. Referensi': invoiceNo,
    'Nama Kontak': payload.namaKontak || inv.customer || '',
    'Keterangan': payload.keterangan || ('Pembayaran invoice ' + invoiceNo),
    'Akun Debit': bank,
    'Akun Kredit': payload.akunKredit || payload.akunLawan || FIN_defaultAccountByGroup_('PIUTANG', 'Piutang Konvensional'),
    'Nominal': nominal,
    'Operator': auth.email,
    'Source_Key': sourceKey,
    'Auto_Flag': 'FINANCE'
  });

  var updated = FIN_updateSalesInvoicePayment_(invoiceNo, nominal, auth.email);
  return { success: true, message: 'Pembayaran invoice tercatat.', invoice: updated };
}

function FIN_catatDPCustomer(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};

  var customer = String(payload.namaKontak || payload.customer || '').trim();
  var nominal = FIN_toNumber_(payload.nominal);
  var bank = String(payload.akunKasBank || '').trim() || FIN_defaultCashAccount_();
  var ref = String(payload.noReferensi || payload.noPo || '').trim() || FIN_makeRef_('DP');
  if (!customer) throw new Error('Nama customer wajib diisi.');
  if (nominal <= 0) throw new Error('Nominal DP harus lebih dari 0.');

  FIN_appendJurnal_({
    'Tanggal': FIN_dateKey_(payload.tanggal || new Date()),
    'Tipe Transaksi': 'DP_CUSTOMER',
    'No. Referensi': ref,
    'Nama Kontak': customer,
    'Keterangan': payload.keterangan || ('DP customer ' + customer + (payload.noPo ? ' / PO ' + payload.noPo : '')),
    'Akun Debit': bank,
    'Akun Kredit': 'Uang Muka Penjualan',
    'Nominal': nominal,
    'Operator': auth.email,
    'Source_Key': FIN_makeSourceKey_('DP_' + ref),
    'Auto_Flag': 'FINANCE'
  });
  return { success: true, message: 'DP customer tercatat.', ref: ref };
}

function FIN_bayarHutang(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};

  var ref = String(payload.noReferensi || payload.ref || '').trim();
  var vendor = String(payload.namaKontak || payload.vendor || '').trim();
  var nominal = FIN_toNumber_(payload.nominal);
  var bank = String(payload.akunKasBank || '').trim() || FIN_defaultCashAccount_();
  var akunHutang = String(payload.akunHutang || '').trim() || 'Hutang Usaha';
  if (!ref) throw new Error('No referensi hutang wajib diisi.');
  if (nominal <= 0) throw new Error('Nominal pembayaran harus lebih dari 0.');

  FIN_appendJurnal_({
    'Tanggal': FIN_dateKey_(payload.tanggal || new Date()),
    'Tipe Transaksi': 'PEMBAYARAN_HUTANG',
    'No. Referensi': ref,
    'Nama Kontak': vendor,
    'Keterangan': payload.keterangan || ('Pembayaran hutang ' + ref),
    'Akun Debit': akunHutang,
    'Akun Kredit': bank,
    'Nominal': nominal,
    'Operator': auth.email,
    'Source_Key': FIN_makeSourceKey_('PAYABLE_' + ref),
    'Auto_Flag': 'FINANCE'
  });
  return { success: true, message: 'Pembayaran hutang tercatat.', ref: ref };
}

function FIN_catatPenerimaan(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var akunKredit = String(payload.akunKredit || payload.akunLawan || '').trim();
  var mode = FIN_cleanKey_(payload.mode || payload.tipePenerimaan || 'UMUM');

  if (mode === 'INVOICE' || payload.invoiceNo || FIN_accountMatch_(akunKredit, ['PIUTANG'])) {
    if (payload.invoiceNo) {
      return FIN_terimaPembayaranInvoice({
        tanggal: payload.tanggal,
        invoiceNo: payload.invoiceNo,
        akunKasBank: payload.akunKasBank,
        akunKredit: akunKredit,
        nominal: payload.nominal,
        namaKontak: payload.namaKontak,
        keterangan: payload.keterangan
      });
    }
  }

  if (mode === 'DP' || mode === 'DPCUSTOMER' || mode === 'DP_CUSTOMER' || FIN_accountMatch_(akunKredit, ['UANGMUKAPENJUALAN', 'DP_CUSTOMER'])) {
    return FIN_catatDPCustomer({
      tanggal: payload.tanggal,
      namaKontak: payload.namaKontak || payload.customer,
      akunKasBank: payload.akunKasBank,
      noReferensi: payload.noReferensi,
      noPo: payload.noPo,
      nominal: payload.nominal,
      keterangan: payload.keterangan
    });
  }

  return FIN_simpanJurnal({
    tanggal: payload.tanggal,
    tipeTransaksi: payload.tipeTransaksi || 'PENERIMAAN',
    noReferensi: payload.noReferensi,
    namaKontak: payload.namaKontak,
    keterangan: payload.keterangan || 'Penerimaan kas/bank',
    akunDebit: payload.akunKasBank || FIN_defaultCashAccount_(),
    akunKredit: akunKredit || FIN_defaultAccountByGroup_('PENDAPATAN', 'Konvensional'),
    nominal: payload.nominal,
    autoFlag: 'MANUAL_FINANCE'
  });
}

function FIN_catatDPMaklunCash_(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var vendor = String(payload.namaKontak || payload.vendor || payload.supplier || '').trim();
  var ref = String(payload.noReferensi || payload.ref || payload.noReferensiHutang || '').trim();
  var nominal = FIN_toNumber_(payload.nominal);
  var bank = String(payload.akunKasBank || '').trim() || FIN_defaultCashAccount_();
  var uangMuka = FIN_accountNameByCandidates_(['Uang Muka Pembelian'], 'Uang Muka Pembelian');
  if (!vendor) throw new Error('Supplier/Maklun wajib diisi untuk DP pembelian/maklun.');
  if (!ref) throw new Error('No PO/SPK/Nota/Ref wajib diisi untuk DP pembelian/maklun.');
  if (nominal <= 0) throw new Error('Nominal DP harus lebih dari 0.');

  FIN_appendJurnal_({
    'Tanggal': FIN_dateKey_(payload.tanggal || new Date()),
    'Tipe Transaksi': 'DP_PURCHASING_CASH',
    'No. Referensi': ref,
    'Nama Kontak': vendor,
    'Keterangan': payload.keterangan || ('DP pembelian/maklun ' + vendor + ' / Ref ' + ref),
    'Akun Debit': uangMuka,
    'Akun Kredit': bank,
    'Nominal': nominal,
    'Operator': auth.email,
    'Source_Key': FIN_makeSourceKey_('DP_PURCH_CASH_' + ref + '_' + vendor),
    'Auto_Flag': 'FINANCE'
  });
  return { success: true, message: 'DP pembelian/maklun tercatat.', ref: ref };
}

function FIN_catatPengeluaran(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var akunDebit = String(payload.akunDebit || payload.akunLawan || '').trim();
  if (FIN_accountMatch_(akunDebit, ['Uang Muka Pembelian', 'UANG_MUKA_PEMBELIAN'])) {
    payload.noReferensi = payload.noReferensi || payload.noReferensiHutang || payload.refHutang || payload.ref;
    return FIN_catatDPMaklunCash_(payload);
  }
  if (payload.noReferensiHutang || payload.refHutang || (payload.ref && FIN_accountMatch_(akunDebit, ['HUTANG']))) {
    payload.noReferensi = payload.noReferensi || payload.noReferensiHutang || payload.refHutang || payload.ref;
    payload.akunHutang = payload.akunHutang || akunDebit;
    return FIN_bayarHutang(payload);
  }
  return FIN_simpanJurnal({
    tanggal: payload.tanggal,
    tipeTransaksi: payload.tipeTransaksi || 'PENGELUARAN',
    noReferensi: payload.noReferensi,
    namaKontak: payload.namaKontak,
    keterangan: payload.keterangan || 'Pengeluaran kas/bank',
    akunDebit: akunDebit || FIN_defaultAccountByGroup_('ADM_UMUM', 'Biaya Operasional'),
    akunKredit: payload.akunKasBank || FIN_defaultCashAccount_(),
    nominal: payload.nominal,
    autoFlag: 'MANUAL_FINANCE'
  });
}

function FIN_defaultCashAccount_() {
  var coa = FIN_getCoa_();
  for (var i = 0; i < coa.length; i++) {
    if (FIN_cleanKey_(coa[i].group) === 'KASBANK') return coa[i].name;
  }
  return 'Kas Kecil';
}

function FIN_defaultAccountByGroup_(groupKey, fallbackName) {
  var target = FIN_cleanKey_(groupKey);
  var coa = FIN_getCoa_();
  for (var i = 0; i < coa.length; i++) {
    if (FIN_cleanKey_(coa[i].group) === target) return coa[i].name;
  }
  for (var j = 0; j < coa.length; j++) {
    if (FIN_cleanKey_(coa[j].name).indexOf(FIN_cleanKey_(fallbackName)) !== -1) return coa[j].name;
  }
  return fallbackName;
}

function FIN_saveCoa(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var code = String(payload.code || payload.Account_Code || '').trim();
  var name = String(payload.name || payload.Account_Name || '').trim();
  if (!code) throw new Error('Kode akun wajib diisi.');
  if (!name) throw new Error('Nama akun wajib diisi.');

  var obj = {
    COA_ID: String(payload.id || payload.COA_ID || '').trim() || ('COA-' + code),
    Account_Code: code,
    Account_Name: name,
    Account_Type: String(payload.type || payload.Account_Type || '').trim() || 'ASSET',
    Normal_Balance: String(payload.normalBalance || payload.Normal_Balance || '').trim() || 'DEBIT',
    Parent_Code: String(payload.parentCode || payload.Parent_Code || '').trim(),
    Is_Posting: payload.isPosting === false || String(payload.isPosting).toUpperCase() === 'FALSE' ? false : true,
    Status: String(payload.status || payload.Status || '').trim() || 'ACTIVE',
    Notes: String(payload.notes || payload.Notes || '').trim(),
    Account_Group: String(payload.group || payload.Account_Group || '').trim()
  };

  var sh = FIN_ensureSheet_(FIN_masterSs_(), 'Master_COA', FIN_HEADERS.COA);
  var table = FIN_readSheetTable_(sh);
  var targetRow = Number(payload.rowNumber || 0);

  table.rows.forEach(function(r) {
    var rowNo = r._rowNumber;
    var existingCode = String(FIN_val_(r, ['Account_Code']) || '').trim();
    var existingName = FIN_cleanKey_(FIN_val_(r, ['Account_Name']));
    if (targetRow && rowNo === targetRow) return;
    if (existingCode && existingCode === code && FIN_isModuleActive_(FIN_val_(r, ['Status']))) {
      throw new Error('Kode akun sudah dipakai: ' + code);
    }
    if (existingName && existingName === FIN_cleanKey_(name) && FIN_isModuleActive_(FIN_val_(r, ['Status']))) {
      throw new Error('Nama akun sudah dipakai: ' + name);
    }
  });

  if (!targetRow) {
    FIN_appendObjectByHeaders_(sh, FIN_HEADERS.COA, obj);
    FIN_RUNTIME_COA_CACHE = null;
    FIN_touchMutation_('Master_COA ditambahkan');
    return { success: true, message: 'COA ditambahkan.', coa: obj };
  }

  Object.keys(obj).forEach(function(h) { FIN_setByHeader_(sh, targetRow, h, obj[h]); });
  FIN_RUNTIME_COA_CACHE = null;
  FIN_touchMutation_('Master_COA diperbarui');
  return { success: true, message: 'COA diperbarui.', coa: obj };
}

function FIN_deleteCoa(payload) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var rowNumber = Number(payload.rowNumber || 0);
  if (!rowNumber) throw new Error('Row COA tidak valid.');
  var sh = FIN_ensureSheet_(FIN_masterSs_(), 'Master_COA', FIN_HEADERS.COA);
  FIN_setByHeader_(sh, rowNumber, 'Status', 'INACTIVE');
  FIN_setByHeader_(sh, rowNumber, 'Notes', 'Dihapus dari WebApp Finance oleh ' + (auth.email || FIN_currentEmail_()) + ' pada ' + FIN_displayDateTime_(new Date()));
  FIN_touchMutation_('Master_COA dinonaktifkan');
  return { success: true, message: 'COA dihapus/nonaktifkan.' };
}


/* =========================
 * v1.8.8 - EDIT / SOFT DELETE DATA_JURNAL
 * Riwayat Arus Kas dan Jurnal memakai sumber baris yang sama.
 * Baris yang sudah direkonsiliasi harus dibatalkan link-nya terlebih dahulu.
 * ========================= */

function FIN_findJurnalRecordForMutation_(jurnalKey) {
  var key = String(jurnalKey || '').trim();
  if (!key) throw new Error('Kunci jurnal tidak valid.');
  var sh = FIN_ensureSheet_(FIN_selfSs_(), FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
  FIN_ensureColumns_(sh, FIN_HEADERS.JURNAL);
  var table = FIN_readSheetTable_(sh);
  var rowNumber = 0, rowObj = null;
  for (var i = 0; i < (table.rows || []).length; i++) {
    var r = table.rows[i];
    var rn = Number(r._rowNumber || (i + 2));
    var sk = String(FIN_val_(r, ['Source_Key']) || '').trim();
    if ((sk && sk === key) || key === ('JRNROW:' + rn)) {
      rowNumber = rn;
      rowObj = r;
      break;
    }
  }
  if (!rowObj) throw new Error('Jurnal tidak ditemukan atau sudah dihapus.');
  if (FIN_isDeletedValue_(FIN_val_(rowObj, ['Is_Deleted']))) throw new Error('Jurnal sudah dihapus.');
  return { sheet: sh, table: table, rowNumber: rowNumber, row: rowObj, jurnalKey: key };
}

function FIN_jurnalRecordToObject_(record) {
  var r = record.row;
  var sourceKey = String(FIN_val_(r, ['Source_Key']) || '').trim();
  var bankTxKey = String(FIN_val_(r, ['Bank_Tx_Key']) || '').trim();
  var reconStatus = String(FIN_val_(r, ['Recon_Status']) || '').trim();
  return {
    rowNumber: record.rowNumber,
    jurnalKey: sourceKey || ('JRNROW:' + record.rowNumber),
    sourceKey: sourceKey,
    tanggal: FIN_dateKey_(FIN_parseDate_(FIN_val_(r, ['Tanggal']))),
    tipeTransaksi: String(FIN_val_(r, ['Tipe Transaksi']) || ''),
    noReferensi: String(FIN_val_(r, ['No. Referensi', 'No Referensi', 'No_Referensi']) || ''),
    namaKontak: String(FIN_val_(r, ['Nama Kontak']) || ''),
    keterangan: String(FIN_val_(r, ['Keterangan']) || ''),
    akunDebit: String(FIN_val_(r, ['Akun Debit']) || ''),
    akunKredit: String(FIN_val_(r, ['Akun Kredit']) || ''),
    nominal: FIN_toNumber_(FIN_val_(r, ['Nominal'])),
    operator: String(FIN_val_(r, ['Operator']) || ''),
    autoFlag: String(FIN_val_(r, ['Auto_Flag']) || ''),
    bankTxKey: bankTxKey,
    reconStatus: reconStatus,
    isReconciled: !!bankTxKey || FIN_cleanKey_(reconStatus) === 'MATCHED'
  };
}

function FIN_jurnalHasActiveRecon_(jurnalKey, record) {
  var row = record && record.row ? record.row : null;
  if (row) {
    if (String(FIN_val_(row, ['Bank_Tx_Key']) || '').trim()) return true;
    if (FIN_cleanKey_(FIN_val_(row, ['Recon_Status']) || '') === 'MATCHED') return true;
  }
  try {
    if (typeof FIN_activeBankReconLinkMaps_ === 'function') {
      var maps = FIN_activeBankReconLinkMaps_();
      if (maps && maps.byJurnal && maps.byJurnal[String(jurnalKey || '').trim()]) return true;
    }
  } catch (e) {}
  return false;
}

function FIN_isInvoicePaymentJournalObject_(j) {
  if (!j) return false;
  return FIN_accountLooksCash_(j.akunDebit) && FIN_accountMatch_(j.akunKredit, ['PIUTANG']);
}

function FIN_syncInvoiceRefsAfterJournalMutation_(refs, operator) {
  var seen = {}, warnings = [];
  (refs || []).forEach(function(ref){
    ref = String(ref || '').trim();
    var key = FIN_cleanKey_(ref);
    if (!key || seen[key]) return;
    seen[key] = true;
    try {
      if (typeof FIN_resyncSalesInvoicePaymentFromJournals_ === 'function') {
        FIN_resyncSalesInvoicePaymentFromJournals_(ref, operator || FIN_currentEmail_());
      }
    } catch (e) {
      warnings.push('Pembayaran invoice ' + ref + ' belum tersinkron: ' + (e.message || e));
    }
  });
  return warnings;
}

function FIN_getJurnalDetail(payload, emailOp, pasporOp) {
  FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var record = FIN_findJurnalRecordForMutation_(payload.jurnalKey || payload.sourceKey || payload.key);
  return { success: true, row: FIN_jurnalRecordToObject_(record) };
}

function FIN_updateJurnal(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var key = String(payload.jurnalKey || payload.sourceKey || payload.key || '').trim();
  var record = FIN_findJurnalRecordForMutation_(key);
  if (FIN_jurnalHasActiveRecon_(key, record)) throw new Error('Jurnal sudah dicocokkan dengan mutasi bank. Batalkan rekonsiliasi terlebih dahulu sebelum mengedit.');

  var oldObj = FIN_jurnalRecordToObject_(record);
  var tanggal = String(payload.tanggal || '').trim();
  var akunDebit = String(payload.akunDebit || '').trim();
  var akunKredit = String(payload.akunKredit || '').trim();
  var nominal = FIN_toNumber_(payload.nominal);
  if (!tanggal) throw new Error('Tanggal jurnal wajib diisi.');
  if (!akunDebit || !akunKredit) throw new Error('Akun debit dan kredit wajib diisi.');
  if (FIN_cleanKey_(akunDebit) === FIN_cleanKey_(akunKredit)) throw new Error('Akun debit dan kredit tidak boleh sama.');
  if (nominal <= 0) throw new Error('Nominal jurnal harus lebih dari 0.');

  var updates = {
    'Tanggal': FIN_dateKey_(tanggal),
    'Tipe Transaksi': String(payload.tipeTransaksi || oldObj.tipeTransaksi || 'JURNAL_MANUAL').trim(),
    'No. Referensi': String(payload.noReferensi || '').trim(),
    'Nama Kontak': String(payload.namaKontak || '').trim(),
    'Keterangan': String(payload.keterangan || '').trim(),
    'Akun Debit': akunDebit,
    'Akun Kredit': akunKredit,
    'Nominal': nominal,
    'Updated_At': FIN_displayDateTime_(new Date()),
    'Updated_By': auth.email,
    'Is_Deleted': ''
  };
  Object.keys(updates).forEach(function(h){ FIN_setByHeader_(record.sheet, record.rowNumber, h, updates[h]); });

  var newObj = {
    noReferensi: updates['No. Referensi'], akunDebit: akunDebit, akunKredit: akunKredit,
    nominal: nominal, tipeTransaksi: updates['Tipe Transaksi']
  };
  var invoiceRefs = [];
  if (FIN_isInvoicePaymentJournalObject_(oldObj)) invoiceRefs.push(oldObj.noReferensi);
  if (FIN_isInvoicePaymentJournalObject_(newObj)) invoiceRefs.push(newObj.noReferensi);
  var syncWarnings = FIN_syncInvoiceRefsAfterJournalMutation_(invoiceRefs, auth.email);
  FIN_touchMutation_('Jurnal edited ' + key + ' by ' + auth.email);
  return { success: true, message: syncWarnings.length ? ('Jurnal diperbarui. ' + syncWarnings.join(' | ')) : 'Jurnal berhasil diperbarui.', jurnalKey: key, warnings:syncWarnings };
}

function FIN_deleteJurnal(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var key = String(payload.jurnalKey || payload.sourceKey || payload.key || '').trim();
  var record = FIN_findJurnalRecordForMutation_(key);
  if (FIN_jurnalHasActiveRecon_(key, record)) throw new Error('Jurnal sudah dicocokkan dengan mutasi bank. Batalkan rekonsiliasi terlebih dahulu sebelum menghapus.');
  var oldObj = FIN_jurnalRecordToObject_(record);
  var now = FIN_displayDateTime_(new Date());
  FIN_setByHeader_(record.sheet, record.rowNumber, 'Is_Deleted', 'TRUE');
  FIN_setByHeader_(record.sheet, record.rowNumber, 'Deleted_At', now);
  FIN_setByHeader_(record.sheet, record.rowNumber, 'Deleted_By', auth.email);
  FIN_setByHeader_(record.sheet, record.rowNumber, 'Delete_Reason', String(payload.reason || 'Dihapus dari WebApp Finance').trim());
  FIN_setByHeader_(record.sheet, record.rowNumber, 'Updated_At', now);
  FIN_setByHeader_(record.sheet, record.rowNumber, 'Updated_By', auth.email);
  var syncWarnings = FIN_isInvoicePaymentJournalObject_(oldObj) ? FIN_syncInvoiceRefsAfterJournalMutation_([oldObj.noReferensi], auth.email) : [];
  FIN_touchMutation_('Jurnal soft deleted ' + key + ' by ' + auth.email);
  return { success: true, message: syncWarnings.length ? ('Jurnal dihapus dari riwayat. ' + syncWarnings.join(' | ')) : 'Jurnal dihapus dari riwayat. Data audit tetap tersimpan.', jurnalKey: key, warnings:syncWarnings };
}

function FIN_getJurnalRows_() {
  var ss = FIN_selfSs_();
  var sh = ss.getSheetByName(FIN_CFG.SHEET_JURNAL);
  if (!sh) return [];
  FIN_ensureColumns_(sh, FIN_HEADERS.JURNAL);
  var table = FIN_readSheetTable_(sh);
  var rows = table.rows.map(function(r, idx) {
    if (FIN_isDeletedValue_(FIN_val_(r, ['Is_Deleted', 'Deleted', 'Is Deleted']))) return null;
    var tgl = FIN_parseDate_(FIN_val_(r, ['Tanggal']));
    var nominal = FIN_toNumber_(FIN_val_(r, ['Nominal']));
    var sourceKey = String(FIN_val_(r, ['Source_Key']) || '').trim();
    var rowNumber = r._rowNumber || (idx + 2);
    var bankTxKey = String(FIN_val_(r, ['Bank_Tx_Key']) || '').trim();
    var reconStatus = String(FIN_val_(r, ['Recon_Status']) || '').trim();
    return {
      rowNumber: rowNumber,
      jurnalKey: sourceKey || ('JRNROW:' + rowNumber),
      tanggal: FIN_displayDate_(tgl),
      tanggalKey: FIN_dateKey_(tgl),
      tipeTransaksi: FIN_val_(r, ['Tipe Transaksi']),
      noReferensi: FIN_val_(r, ['No. Referensi', 'No Referensi', 'No_Referensi']),
      namaKontak: FIN_val_(r, ['Nama Kontak']),
      keterangan: FIN_val_(r, ['Keterangan']),
      akunDebit: FIN_val_(r, ['Akun Debit']),
      akunKredit: FIN_val_(r, ['Akun Kredit']),
      nominal: nominal,
      operator: FIN_val_(r, ['Operator']),
      sourceKey: sourceKey,
      autoFlag: FIN_val_(r, ['Auto_Flag']),
      updatedAt: FIN_val_(r, ['Updated_At']),
      updatedBy: FIN_val_(r, ['Updated_By']),
      bankTxKey: bankTxKey,
      reconStatus: reconStatus,
      isReconciled: !!bankTxKey || FIN_cleanKey_(reconStatus) === 'MATCHED'
    };
  }).filter(function(x){ return !!x; });
  rows.sort(function(a, b) { return String(b.tanggalKey).localeCompare(String(a.tanggalKey)) || Number(b.rowNumber) - Number(a.rowNumber); });
  return rows;
}

function FIN_getHutangRows_() {
  var rows = [];
  var journals = FIN_getJurnalRows_();
  var payables = FIN_getPurchasingPayablesForReport_();
  payables.forEach(function(p, idx) {
    var paid = p.akunHutang === 'Hutang Maklun'
      ? FIN_sumJournalForRef_(journals, p.ref, ['Hutang Maklun'], null)
      : FIN_sumJournalForRef_(journals, p.ref, ['Hutang Usaha'], null);
    var sisa = Math.max(FIN_toNumber_(p.totalHutang) - paid, 0);
    rows.push({
      source: p.source,
      rowNumber: idx + 2,
      ref: p.ref,
      tanggal: p.tanggal,
      tanggalKey: p.tanggalKey,
      vendor: p.vendor,
      kategori: p.source === 'MAKLUN' ? 'Maklun' : p.kategori,
      totalHutang: FIN_toNumber_(p.totalHutang),
      terbayar: paid,
      sisaHutang: sisa,
      akunHutang: p.akunHutang,
      akunDebit: p.debitAccounts.join(', '),
      status: sisa <= 0 ? 'LUNAS' : (paid > 0 ? 'PARSIAL' : 'BELUM BAYAR'),
      lineCount: p.lineCount
    });
  });
  rows.sort(function(a, b) {
    var al = a.sisaHutang <= 0 ? 1 : 0;
    var bl = b.sisaHutang <= 0 ? 1 : 0;
    if (al !== bl) return al - bl;
    return String(a.tanggalKey).localeCompare(String(b.tanggalKey));
  });
  return rows;
}

function FIN_getDPCustomerRows_(invoices, journals) {
  var map = {};
  journals.forEach(function(j) {
    var customer = String(j.namaKontak || '').trim() || '(Tanpa nama)';
    if (!map[customer]) map[customer] = { customer: customer, dpMasuk: 0, dpTerpakai: 0, saldoDp: 0, refs: [] };
    if (FIN_accountMatch_(j.akunKredit, ['UANGMUKAPENJUALAN', 'DPCUSTOMER', 'DPPELANGGAN'])) {
      map[customer].dpMasuk += FIN_toNumber_(j.nominal);
      map[customer].refs.push(j.noReferensi);
    }
    if (FIN_accountMatch_(j.akunDebit, ['UANGMUKAPENJUALAN', 'DPCUSTOMER', 'DPPELANGGAN'])) {
      map[customer].dpTerpakai += FIN_toNumber_(j.nominal);
    }
  });

  invoices.forEach(function(inv) {
    var customer = String(inv.customer || '').trim() || '(Tanpa nama)';
    var dp = FIN_toNumber_(inv.dpTerpotong);
    if (dp <= 0) return;
    var dpSourceKey = 'SALES_INV_' + FIN_cleanKey_(inv.invoiceNo) + '_DP';
    var alreadyJurnal = journals.some(function(j) { return String(j.sourceKey || '').trim() === dpSourceKey; });
    if (alreadyJurnal) return;
    if (!map[customer]) map[customer] = { customer: customer, dpMasuk: 0, dpTerpakai: 0, saldoDp: 0, refs: [] };
    // Fallback jika jurnal pemakaian DP belum tersinkron. Setelah v0.5 normalnya sudah ada jurnal AUTO.
    map[customer].dpTerpakai += dp;
  });

  return Object.keys(map).map(function(k) {
    var x = map[k];
    x.saldoDp = Math.max(FIN_toNumber_(x.dpMasuk) - FIN_toNumber_(x.dpTerpakai), 0);
    return x;
  }).filter(function(x) { return x.dpMasuk || x.dpTerpakai || x.saldoDp; }).sort(function(a, b) { return b.saldoDp - a.saldoDp; });
}

function FIN_getCoa_() {
  if (FIN_RUNTIME_COA_CACHE) return FIN_RUNTIME_COA_CACHE;
  var sh = FIN_ensureMasterCOA_();
  var table = FIN_readSheetTable_(sh);
  FIN_RUNTIME_COA_CACHE = table.rows.map(function(r) {
    return {
      rowNumber: r._rowNumber,
      id: FIN_val_(r, ['COA_ID']),
      code: FIN_val_(r, ['Account_Code', 'Kode Akun']),
      name: FIN_val_(r, ['Account_Name', 'Nama Akun']),
      type: FIN_val_(r, ['Account_Type', 'Tipe Akun']),
      group: FIN_val_(r, ['Account_Group', 'Grup Akun']),
      normalBalance: FIN_val_(r, ['Normal_Balance', 'Saldo Normal']),
      parentCode: FIN_val_(r, ['Parent_Code']),
      isPosting: FIN_val_(r, ['Is_Posting']),
      status: FIN_val_(r, ['Status']),
      notes: FIN_val_(r, ['Notes']),
      isDeleted: FIN_val_(r, ['Is_Deleted'])
    };
  }).filter(function(x) {
    return x.name && FIN_isModuleActive_(x.status);
  });
  return FIN_RUNTIME_COA_CACHE;
}

function FIN_getArusKasRows_(journals) {
  return (journals || []).filter(function(j) {
    return FIN_accountLooksCash_(j.akunDebit) || FIN_accountLooksCash_(j.akunKredit);
  }).map(function(j) {
    var isIn = FIN_accountLooksCash_(j.akunDebit);
    return {
      rowNumber: j.rowNumber,
      jurnalKey: j.jurnalKey || FIN_jurnalMatchKey_(j),
      sourceKey: j.sourceKey || '',
      tanggal: j.tanggal,
      tanggalKey: j.tanggalKey,
      tipe: isIn ? 'MASUK' : 'KELUAR',
      tipeTransaksi: j.tipeTransaksi,
      noReferensi: j.noReferensi,
      namaKontak: j.namaKontak,
      akunKasBank: isIn ? j.akunDebit : j.akunKredit,
      akunLawan: isIn ? j.akunKredit : j.akunDebit,
      akunDebit: j.akunDebit,
      akunKredit: j.akunKredit,
      nominal: FIN_toNumber_(j.nominal),
      keterangan: j.keterangan,
      operator: j.operator,
      autoFlag: j.autoFlag,
      bankTxKey: j.bankTxKey || '',
      reconStatus: j.reconStatus || '',
      isReconciled: !!j.isReconciled,
      masuk: isIn ? FIN_toNumber_(j.nominal) : 0,
      keluar: isIn ? 0 : FIN_toNumber_(j.nominal),
      saldoNet: isIn ? FIN_toNumber_(j.nominal) : -FIN_toNumber_(j.nominal)
    };
  });
}

function FIN_calcCoaBalances_(journals, coa) {
  var map = {};
  (coa || []).forEach(function(a) {
    var key = FIN_cleanKey_(a.name);
    if (!key) return;
    map[key] = {
      code: a.code,
      name: a.name,
      type: a.type,
      group: a.group,
      normalBalance: a.normalBalance || 'DEBIT',
      debit: 0,
      credit: 0,
      saldo: 0
    };
  });
  function ensure(name) {
    var key = FIN_cleanKey_(name);
    if (!key) return null;
    if (!map[key]) map[key] = { code: '', name: name, type: '', group: '', normalBalance: 'DEBIT', debit: 0, credit: 0, saldo: 0 };
    return map[key];
  }
  (journals || []).forEach(function(j) {
    var d = ensure(j.akunDebit); if (d) d.debit += FIN_toNumber_(j.nominal);
    var c = ensure(j.akunKredit); if (c) c.credit += FIN_toNumber_(j.nominal);
  });
  return Object.keys(map).map(function(k) {
    var x = map[k];
    var normal = FIN_cleanKey_(x.normalBalance || 'DEBIT');
    x.saldo = normal === 'KREDIT' ? x.credit - x.debit : x.debit - x.credit;
    return x;
  }).filter(function(x) { return x.debit || x.credit || x.saldo; }).sort(function(a, b) { return String(a.type + a.group + a.name).localeCompare(String(b.type + b.group + b.name)); });
}

function FIN_appendJurnal_(obj) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var ss = FIN_selfSs_();
    var sh = FIN_ensureSheet_(ss, FIN_CFG.SHEET_JURNAL, FIN_HEADERS.JURNAL);
    FIN_appendObjectByHeaders_(sh, FIN_HEADERS.JURNAL, obj);
  } finally {
    lock.releaseLock();
  }
}

function FIN_sumJournalForRef_(journals, ref, debitAliases, creditAliases) {
  var refKey = FIN_cleanKey_(ref);
  if (!refKey) return 0;
  return journals.reduce(function(sum, j) {
    if (FIN_cleanKey_(j.noReferensi) !== refKey) return sum;
    var ok = true;
    if (debitAliases && debitAliases.length) ok = FIN_accountMatch_(j.akunDebit, debitAliases);
    if (creditAliases && creditAliases.length) ok = FIN_accountMatch_(j.akunKredit, creditAliases);
    return ok ? sum + FIN_toNumber_(j.nominal) : sum;
  }, 0);
}

function FIN_accountMatch_(account, aliases) {
  var a = FIN_cleanKey_(account);
  aliases = aliases || [];
  return aliases.some(function(x) {
    var k = FIN_cleanKey_(x);
    return a === k || a.indexOf(k) !== -1 || k.indexOf(a) !== -1;
  });
}

function FIN_calcCashBalance_(journals) {
  return journals.reduce(function(sum, j) {
    var debitCash = FIN_accountLooksCash_(j.akunDebit);
    var creditCash = FIN_accountLooksCash_(j.akunKredit);
    if (debitCash) sum += FIN_toNumber_(j.nominal);
    if (creditCash) sum -= FIN_toNumber_(j.nominal);
    return sum;
  }, 0);
}

function FIN_accountLooksCash_(account) {
  var a = FIN_cleanKey_(account);
  if (!a || FIN_isMarketplaceBalanceAccount_(account)) return false;
  // Kata SALDO saja bukan kas/bank. Contoh: Saldo Shopee adalah clearing account marketplace.
  return a.indexOf('KAS') !== -1 || a.indexOf('BANK') !== -1 || a.indexOf('BCA') !== -1 || a.indexOf('MANDIRI') !== -1 || a.indexOf('BRI') !== -1 || a.indexOf('BNI') !== -1 || a.indexOf('GIRO') !== -1;
}

function FIN_calcExpenseMtd_(journals, monthKey) {
  return journals.reduce(function(sum, j) {
    if (!j.tanggalKey || j.tanggalKey.indexOf(monthKey) !== 0) return sum;
    var debit = FIN_cleanKey_(j.akunDebit);
    var credit = FIN_cleanKey_(j.akunKredit);
    if (debit.indexOf('BIAYA') !== -1 || debit.indexOf('BEBAN') !== -1 || debit.indexOf('HPP') !== -1) sum += FIN_toNumber_(j.nominal);
    if (credit.indexOf('BIAYA') !== -1 || credit.indexOf('BEBAN') !== -1 || credit.indexOf('HPP') !== -1) sum -= FIN_toNumber_(j.nominal);
    return sum;
  }, 0);
}

function FIN_noAutoSyncResult_(name, period) {
  return {
    success: true,
    skipped: true,
    mode: 'SOURCE_READER_ONLY',
    periodKey: period || '',
    message: name + ' dinonaktifkan. Finance sekarang membaca langsung sheet modul sumber; Data_Jurnal hanya untuk kas/bank dan penyesuaian manual.'
  };
}

function FIN_syncSalesInvoiceJournals() {
  FIN_requirePassportFromArgs_(arguments);
  return FIN_noAutoSyncResult_('Sales invoice auto-journal sync');
}

function FIN_syncSalesInvoiceJournals_() { return FIN_noAutoSyncResult_('Sales invoice auto-journal sync'); }

function FIN_syncPurchasingPayableJournals() {
  FIN_requirePassportFromArgs_(arguments);
  return FIN_noAutoSyncResult_('Purchasing payable auto-journal sync');
}

function FIN_syncPurchasingPayableJournals_() { return FIN_noAutoSyncResult_('Purchasing payable auto-journal sync'); }

function FIN_syncMaklunMaterialDpJournals_() { return FIN_noAutoSyncResult_('Maklun material DP auto-journal sync'); }

function FIN_syncMaklunDpApplyJournals_(bills) { return FIN_noAutoSyncResult_('Maklun DP apply auto-journal sync'); }

function FIN_syncOmniFinanceJournals(period, emailOp, pasporOp) {
  FIN_requirePassportFromArgs_(arguments);
  var payload = (period && typeof period === 'object') ? period : { period: period };
  return FIN_syncOmniFinanceJournals_(payload.period || Utilities.formatDate(new Date(), FIN_CFG.TZ, 'yyyy-MM'), payload);
}

function FIN_syncOmniFinanceJournals_(period, options) {
  var periodKey = (typeof period === 'string' && /^\d{4}-\d{2}$/.test(period)) ? period : Utilities.formatDate(new Date(), FIN_CFG.TZ, 'yyyy-MM');
  return FIN_noAutoSyncResult_('Omni finance auto-journal sync', periodKey);
}