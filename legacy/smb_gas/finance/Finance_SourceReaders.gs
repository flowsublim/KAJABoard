/** Read-only source readers: Penjualan, Purchasing, Omni, Settlement. */

function FIN_sumDpUsageForInvoice_(journals, invoiceNo) {
  var refKey = FIN_cleanKey_(invoiceNo);
  if (!refKey) return 0;
  return (journals || []).reduce(function(sum, j) {
    if (FIN_cleanKey_(j.noReferensi) !== refKey) return sum;
    if (!FIN_accountMatch_(j.akunDebit, ['UANGMUKAPENJUALAN', 'DPCUSTOMER', 'DPPELANGGAN'])) return sum;
    if (!FIN_accountMatch_(j.akunKredit, ['PIUTANG'])) return sum;
    return sum + FIN_toNumber_(j.nominal);
  }, 0);
}

function FIN_inferDpForInvoice_(journals, invoiceNo, noPo, customer, nilaiInvoice, dpCol) {
  dpCol = FIN_toNumber_(dpCol);
  if (dpCol > 0) return Math.min(dpCol, FIN_toNumber_(nilaiInvoice));
  var used = FIN_sumDpUsageForInvoice_(journals, invoiceNo);
  if (used > 0) return Math.min(used, FIN_toNumber_(nilaiInvoice));
  var masukByPo = FIN_sumDpMasukForPo_(journals, noPo, customer);
  if (masukByPo > 0) return Math.min(masukByPo, FIN_toNumber_(nilaiInvoice));
  return 0;
}

function FIN_sumInvoiceCashPayments_(journals, invoiceNo) {
  var refKey = FIN_cleanKey_(invoiceNo);
  return (journals || []).reduce(function(sum, j) {
    if (FIN_cleanKey_(j.noReferensi) !== refKey) return sum;
    var tipe = FIN_cleanKey_(j.tipeTransaksi);
    if (tipe.indexOf('PEMAKAIANDP') !== -1 || tipe.indexOf('DPINVOICE') !== -1) return sum;
    if (!FIN_accountMatch_(j.akunKredit, ['PIUTANG'])) return sum;
    if (!FIN_accountLooksCash_(j.akunDebit)) return sum;
    return sum + FIN_toNumber_(j.nominal);
  }, 0);
}



/* =========================
 * OMNI FINANCE HANDOFF v1.5
 * ========================= */

function FIN_emptyOmniFinance_() {
  return {
    periodKey: '',
    receivables: [],
    marketplaceSales: [],
    posSales: [],
    settlements: [],
    marketplaceFeeRows: [],
    adjustments: [],
    returns: [],
    revenueRows: [],
    summary: { marketplaceGross: 0, marketplaceOutstanding: 0, posGross: 0, posOutstanding: 0, settlementNet: 0, settlementFees: 0, adminFeeRecognitionBasis: 'ORDER_DATE' }
  };
}

function FIN_buildRevenueRowsFromInvoices_(rows, periodKey) {
  var map = {};
  (rows || []).forEach(function(inv) {
    if (!inv.tanggalKey || inv.tanggalKey.indexOf(periodKey) !== 0) return;
    var akun = inv.akunPendapatan || 'Pendapatan';
    var source = inv.source || '';
    var key = akun + '||' + source;
    if (!map[key]) map[key] = { akun: akun, source: source, nominal: 0 };
    map[key].nominal += FIN_toNumber_(inv.nilaiInvoice);
  });
  return Object.keys(map).map(function(k){ return map[k]; });
}

function FIN_buildOmniJournalCandidates_(omni, periodKey) {
  omni = omni || FIN_emptyOmniFinance_();
  var piutangMarket = FIN_accountNameByCandidates_(['Piutang Marketplace'], 'Piutang Marketplace');
  var piutangKonv = FIN_accountNameByCandidates_(['Piutang Konvensional'], 'Piutang Konvensional');
  var rows = [];

  (omni.receivables || []).forEach(function(x) {
    if (!x.tanggalKey || x.tanggalKey.indexOf(periodKey) !== 0) return;
    var isMarket = x.source === 'MARKETPLACE';
    var sourceKey = (isMarket ? 'OMNI_SALE_' : 'OMNI_POS_SALE_') + FIN_cleanKey_(x.invoiceNo);
    var nominal = FIN_toNumber_(x.nilaiInvoice);
    if (nominal <= 0) return;
    rows.push({
      'Tanggal': x.tanggalKey,
      'Tipe Transaksi': isMarket ? 'PENJUALAN_MARKETPLACE_SELESAI' : 'PENJUALAN_POS',
      'No. Referensi': x.invoiceNo,
      'Nama Kontak': x.customer,
      'Keterangan': (isMarket ? 'Penjualan marketplace selesai ' : 'Penjualan POS ') + x.invoiceNo,
      'Akun Debit': isMarket ? piutangMarket : piutangKonv,
      'Akun Kredit': x.akunPendapatan || (isMarket ? FIN_revenueAccountForStore_(x.store) : FIN_accountNameByCandidates_(['Konvensional'], 'Konvensional')),
      'Nominal': nominal,
      'Operator': 'AUTO_OMNI_FINANCE_SYNC',
      'Source_Key': sourceKey,
      'Auto_Flag': 'AUTO'
    });
  });

  (omni.settlements || []).forEach(function(s) {
    var ref = s.noPesanan || '';
    if (!ref) return;
    var akunSaldo = FIN_cashAccountForStore_(s.store);
    var net = FIN_toNumber_(s.net);
    if (net > 0) {
      var skNet = 'OMNI_SETTLE_NET_' + FIN_cleanKey_(ref);
      rows.push({
        'Tanggal': s.tanggalKey,
        'Tipe Transaksi': 'PENCAIRAN_MARKETPLACE',
        'No. Referensi': ref,
        'Nama Kontak': 'Marketplace - ' + (s.store || ''),
        'Keterangan': 'Pencairan marketplace ' + ref,
        'Akun Debit': akunSaldo,
        'Akun Kredit': piutangMarket,
        'Nominal': net,
        'Operator': 'AUTO_OMNI_FINANCE_SYNC',
        'Source_Key': skNet,
        'Auto_Flag': 'AUTO'
      });
    }

    [
      ['admin', s.admin, FIN_adminFeeAccountForStore_(s.store)],
      ['layanan', s.layanan, FIN_feeAccountByCandidates_(['Biaya Layanan Marketplace', 'Biaya Admin ' + (s.store || ''), 'Biaya Administrasi Bank'])],
      ['affiliate', s.affiliate, FIN_feeAccountByCandidates_(['Biaya Komisi Affiliate', 'Komisi Affiliate'])],
      ['ongkir', s.ongkir, FIN_feeAccountByCandidates_(['Biaya Pengiriman', 'Ongkir Penjual'])]
    ].forEach(function(f) {
      var n = FIN_toNumber_(f[1]);
      if (n <= 0) return;
      var sk = 'OMNI_SETTLE_FEE_' + f[0].toUpperCase() + '_' + FIN_cleanKey_(ref);
      rows.push({
        'Tanggal': s.tanggalKey,
        'Tipe Transaksi': 'BIAYA_MARKETPLACE',
        'No. Referensi': ref,
        'Nama Kontak': 'Marketplace - ' + (s.store || ''),
        'Keterangan': 'Biaya marketplace ' + f[0] + ' ' + ref,
        'Akun Debit': f[2],
        'Akun Kredit': piutangMarket,
        'Nominal': n,
        'Operator': 'AUTO_OMNI_FINANCE_SYNC',
        'Source_Key': sk,
        'Auto_Flag': 'AUTO'
      });
    });
  });

  return rows;
}

function FIN_sumReceivableCredits_(journals, refNo, accountCandidates) {
  var ref = FIN_cleanKey_(refNo);
  if (!ref) return 0;
  return (journals || []).reduce(function(sum, j) {
    if (FIN_cleanKey_(j.noReferensi) !== ref) return sum;
    if (!FIN_accountMatch_(j.akunKredit, accountCandidates || ['PIUTANG'])) return sum;
    var src = FIN_cleanKey_(j.sourceKey || '');
    if (src.indexOf('SALE') !== -1 && src.indexOf('SETTLE') === -1) return sum;
    return sum + FIN_toNumber_(j.nominal);
  }, 0);
}

function FIN_cashAccountForStore_(store) {
  return FIN_saldoMarketplaceAccountForStore_(store);
}

function FIN_adminFeeAccountForStore_(store) {
  return FIN_adminMarketplaceAccountForStore_(store);
}

function FIN_isOmniCancelStatus_(status) {
  var s = FIN_cleanKey_(status);
  if (!s) return false;
  return s.indexOf('BATAL') !== -1 || s.indexOf('CANCEL') !== -1 || s.indexOf('RETUR') !== -1 || s.indexOf('RETURN') !== -1 || s.indexOf('GAGAL') !== -1;
}

function FIN_isOmniCompletedStatus_(status) {
  var s = FIN_cleanKey_(status);
  if (!s) return false;
  if (FIN_isOmniCancelStatus_(s)) return false;
  return s.indexOf('SELESAI') !== -1 || s.indexOf('COMPLETED') !== -1 || s.indexOf('DONE') !== -1 || s.indexOf('DELIVERED') !== -1;
}

function FIN_getSalesInvoices_(journalsArg) {
  var rows = [];
  try {
    var ss = FIN_getSalesSs_();
    var sh = ss.getSheetByName('Data_Invoice');
    if (!sh) return [];
    var table = FIN_readSheetTable_(sh);
    var journals = journalsArg || FIN_getJurnalRows_();

    table.rows.forEach(function(r, idx) {
      var invoiceNo = String(FIN_val_(r, ['No Invoice', 'No_Invoice', 'Nomor Invoice', 'Invoice_No', 'Invoice No']) || '').trim();
      if (!invoiceNo) return;
      var customer = FIN_val_(r, ['Nama Customer', 'Customer', 'Nama Konsumen', 'Konsumen', 'Nama_Kontak']);
      var tanggal = FIN_parseDate_(FIN_val_(r, ['Tanggal Invoice', 'Tanggal_Invoice', 'Tanggal', 'Tgl Invoice']));
      var subtotal = FIN_toNumber_(FIN_val_(r, ['Subtotal_PO', 'Subtotal PO', 'Subtotal', 'Sub Total']));
      var ongkir = FIN_toNumber_(FIN_val_(r, ['Ongkos_Kirim', 'Ongkos Kirim', 'Ongkir']));
      var grandRaw = FIN_toNumber_(FIN_val_(r, ['Grand_Total', 'Grand Total', 'Nilai Invoice', 'Total Invoice', 'Total']));
      var nilaiInvoice = grandRaw || (subtotal + ongkir);
      var noPo = FIN_val_(r, ['Ref PO', 'Ref_PO', 'No PO', 'No_PO', 'Nomor PO', 'PO_No']);
    var dpCol = FIN_toNumber_(FIN_val_(r, ['Total_DP_Terpotong', 'Total DP Terpotong', 'DP_Terpotong', 'DP Terpotong', 'DP']));
    var dp = FIN_inferDpForInvoice_(journals, invoiceNo, noPo, customer, nilaiInvoice, dpCol);
      var terbayarCol = FIN_toNumber_(FIN_val_(r, ['Terbayar_Finance', 'Terbayar Finance', 'Terbayar', 'Total_Terbayar']));
      var terbayarJurnal = FIN_sumInvoiceCashPayments_(journals, invoiceNo);
      var terbayar = Math.max(terbayarCol, terbayarJurnal);
      var sisa = Math.max(nilaiInvoice - dp - terbayar, 0);
      var status = sisa <= 0 ? 'LUNAS' : (terbayar > 0 || dp > 0 ? 'PARSIAL' : 'BELUM BAYAR');

      rows.push({
        rowNumber: idx + 2,
        invoiceNo: invoiceNo,
        noPo: FIN_val_(r, ['No PO', 'No_PO', 'Nomor PO', 'PO_No']),
        customer: customer,
        jenisPesanan: FIN_val_(r, ['Jenis Pesanan', 'Jenis_Pesanan', 'Jenis']),
        tanggal: FIN_displayDate_(tanggal),
        tanggalKey: FIN_dateKey_(tanggal),
        subtotal: subtotal,
        ongkir: ongkir,
        nilaiInvoice: nilaiInvoice,
        dpTerpotong: dp,
        terbayar: terbayar,
        sisaTagihan: sisa,
        statusPembayaran: status,
        source: 'KONVENSIONAL',
        akunPiutang: FIN_accountNameByCandidates_(['Piutang Konvensional'], 'Piutang Konvensional'),
        akunPendapatan: FIN_revenueAccountForSalesType_(FIN_val_(r, ['Jenis Pesanan', 'Jenis_Pesanan', 'Jenis'])),
        revenueBucket: 'KONVENSIONAL'
      });
    });
  } catch (err) {
    // Source belum siap tidak boleh mematikan Finance UI.
  }
  rows.sort(function(a, b) { return String(b.tanggalKey).localeCompare(String(a.tanggalKey)); });
  return rows;
}

function FIN_findSalesInvoiceByNo_(invoiceNo) {
  var invoices = FIN_getSalesInvoices_();
  var key = FIN_cleanKey_(invoiceNo);
  for (var i = 0; i < invoices.length; i++) {
    if (FIN_cleanKey_(invoices[i].invoiceNo) === key) return invoices[i];
  }
  return null;
}

function FIN_updateSalesInvoicePayment_(invoiceNo, nominal, operator) {
  var ss = FIN_getSalesSs_();
  var sh = ss.getSheetByName('Data_Invoice');
  if (!sh) throw new Error('Data_Invoice tidak ditemukan di Modul Penjualan.');
  FIN_ensureColumns_(sh, ['Terbayar_Finance', 'Sisa_Tagihan', 'Status_Pembayaran', 'Payment_Updated_At', 'Payment_Updated_By']);
  var table = FIN_readSheetTable_(sh);
  var targetRow = -1;
  var invoiceObj = null;
  for (var i = 0; i < table.rows.length; i++) {
    var no = String(FIN_val_(table.rows[i], ['No Invoice', 'No_Invoice', 'Nomor Invoice', 'Invoice_No', 'Invoice No']) || '').trim();
    if (FIN_cleanKey_(no) === FIN_cleanKey_(invoiceNo)) {
      targetRow = i + 2;
      invoiceObj = table.rows[i];
      break;
    }
  }
  if (targetRow === -1) throw new Error('Invoice tidak ditemukan saat update pembayaran: ' + invoiceNo);

  var currentPaid = FIN_toNumber_(FIN_val_(invoiceObj, ['Terbayar_Finance', 'Terbayar Finance', 'Terbayar']));
  var subtotal = FIN_toNumber_(FIN_val_(invoiceObj, ['Subtotal_PO', 'Subtotal PO', 'Subtotal', 'Sub Total']));
  var ongkir = FIN_toNumber_(FIN_val_(invoiceObj, ['Ongkos_Kirim', 'Ongkos Kirim', 'Ongkir']));
  var grandRaw = FIN_toNumber_(FIN_val_(invoiceObj, ['Grand_Total', 'Grand Total', 'Nilai Invoice', 'Total Invoice', 'Total']));
  var nilaiInvoice = grandRaw || (subtotal + ongkir);
  var refPOForDp = FIN_val_(invoiceObj, ['Ref PO', 'Ref_PO', 'No PO', 'No_PO', 'Nomor PO', 'PO_No']);
  var dpCol = FIN_toNumber_(FIN_val_(invoiceObj, ['Total_DP_Terpotong', 'Total DP Terpotong', 'DP_Terpotong', 'DP Terpotong', 'DP']));
  var dp = FIN_inferDpForInvoice_(FIN_getJurnalRows_(), invoiceNo, refPOForDp, FIN_val_(invoiceObj, ['Nama Customer', 'Customer', 'Nama Konsumen', 'Konsumen', 'Nama_Kontak']), nilaiInvoice, dpCol);
  var newPaid = currentPaid + FIN_toNumber_(nominal);
  var sisa = Math.max(nilaiInvoice - dp - newPaid, 0);
  var status = sisa <= 0 ? 'LUNAS' : (newPaid > 0 || dp > 0 ? 'PARSIAL' : 'BELUM BAYAR');

  FIN_setByHeader_(sh, targetRow, 'Terbayar_Finance', newPaid);
  FIN_setByHeader_(sh, targetRow, 'Sisa_Tagihan', sisa);
  FIN_setByHeader_(sh, targetRow, 'Status_Pembayaran', status);
  FIN_setByHeader_(sh, targetRow, 'Payment_Updated_At', FIN_displayDateTime_(new Date()));
  FIN_setByHeader_(sh, targetRow, 'Payment_Updated_By', operator || FIN_currentEmail_());

  return { invoiceNo: invoiceNo, nilaiInvoice: nilaiInvoice, dpTerpotong: dp, terbayarFinance: newPaid, sisaTagihan: sisa, statusPembayaran: status };
}


function FIN_resyncSalesInvoicePaymentFromJournals_(invoiceNo, operator) {
  invoiceNo = String(invoiceNo || '').trim();
  if (!invoiceNo) return null;
  var ss = FIN_getSalesSs_();
  var sh = ss.getSheetByName('Data_Invoice');
  if (!sh) throw new Error('Data_Invoice tidak ditemukan di Modul Penjualan.');
  FIN_ensureColumns_(sh, ['Terbayar_Finance', 'Sisa_Tagihan', 'Status_Pembayaran', 'Payment_Updated_At', 'Payment_Updated_By']);
  var table = FIN_readSheetTable_(sh);
  var targetRow = -1, invoiceObj = null;
  for (var i = 0; i < (table.rows || []).length; i++) {
    var no = String(FIN_val_(table.rows[i], ['No Invoice', 'No_Invoice', 'Nomor Invoice', 'Invoice_No', 'Invoice No']) || '').trim();
    if (FIN_cleanKey_(no) === FIN_cleanKey_(invoiceNo)) {
      targetRow = table.rows[i]._rowNumber || (i + 2);
      invoiceObj = table.rows[i];
      break;
    }
  }
  if (targetRow === -1) return null;

  var journals = FIN_getJurnalRows_();
  var paid = FIN_sumInvoiceCashPayments_(journals, invoiceNo);
  var subtotal = FIN_toNumber_(FIN_val_(invoiceObj, ['Subtotal_PO', 'Subtotal PO', 'Subtotal', 'Sub Total']));
  var ongkir = FIN_toNumber_(FIN_val_(invoiceObj, ['Ongkos_Kirim', 'Ongkos Kirim', 'Ongkir']));
  var grandRaw = FIN_toNumber_(FIN_val_(invoiceObj, ['Grand_Total', 'Grand Total', 'Nilai Invoice', 'Total Invoice', 'Total']));
  var nilaiInvoice = grandRaw || (subtotal + ongkir);
  var refPOForDp = FIN_val_(invoiceObj, ['Ref PO', 'Ref_PO', 'No PO', 'No_PO', 'Nomor PO', 'PO_No']);
  var dpCol = FIN_toNumber_(FIN_val_(invoiceObj, ['Total_DP_Terpotong', 'Total DP Terpotong', 'DP_Terpotong', 'DP Terpotong', 'DP']));
  var customer = FIN_val_(invoiceObj, ['Nama Customer', 'Customer', 'Nama Konsumen', 'Konsumen', 'Nama_Kontak']);
  var dp = FIN_inferDpForInvoice_(journals, invoiceNo, refPOForDp, customer, nilaiInvoice, dpCol);
  var sisa = Math.max(nilaiInvoice - dp - paid, 0);
  var status = sisa <= 0 ? 'LUNAS' : (paid > 0 || dp > 0 ? 'PARSIAL' : 'BELUM BAYAR');

  FIN_setByHeader_(sh, targetRow, 'Terbayar_Finance', paid);
  FIN_setByHeader_(sh, targetRow, 'Sisa_Tagihan', sisa);
  FIN_setByHeader_(sh, targetRow, 'Status_Pembayaran', status);
  FIN_setByHeader_(sh, targetRow, 'Payment_Updated_At', FIN_displayDateTime_(new Date()));
  FIN_setByHeader_(sh, targetRow, 'Payment_Updated_By', operator || FIN_currentEmail_());
  return { invoiceNo:invoiceNo, terbayarFinance:paid, sisaTagihan:sisa, statusPembayaran:status };
}


/* =========================
 * PURCHASING PAYABLE SYNC v0.8
 * ========================= */

function FIN_pushPurchBillGroup_(map, bill) {
  if (!bill.ref || !bill.vendor || FIN_toNumber_(bill.total) <= 0) return;
  var key = [bill.source, FIN_cleanKey_(bill.ref), FIN_cleanKey_(bill.vendor), FIN_cleanKey_(bill.debitAccount)].join('|');
  if (!map[key]) {
    map[key] = {
      source: bill.source,
      ref: bill.ref,
      vendor: bill.vendor,
      tanggalKey: bill.tanggalKey,
      tanggal: bill.tanggal,
      kategori: bill.kategori,
      totalHutang: 0,
      debitAccount: bill.debitAccount,
      akunHutang: bill.akunHutang,
      lineCount: 0,
      spk: bill.spk || '',
      spkList: []
    };
  }
  map[key].totalHutang += FIN_toNumber_(bill.total);
  map[key].lineCount++;
  if (bill.spk && map[key].spkList.indexOf(String(bill.spk)) === -1) map[key].spkList.push(String(bill.spk));
  if (!map[key].spk && bill.spk) map[key].spk = bill.spk;
  if (String(bill.tanggalKey || '') && (!map[key].tanggalKey || String(bill.tanggalKey) < String(map[key].tanggalKey))) {
    map[key].tanggalKey = bill.tanggalKey;
    map[key].tanggal = bill.tanggal;
  }
}

function FIN_getPurchasingBills_() {
  var outMap = {};
  try {
    var ss = FIN_getPurchSs_();
    var shBeli = ss.getSheetByName('Data_Pembelian');
    if (shBeli) {
      var tBeli = FIN_readSheetTable_(shBeli);
      tBeli.rows.forEach(function(r) {
        if (FIN_isDeletedRow_(r)) return;
        var ref = String(FIN_val_(r, ['Nota', 'No Nota', 'No Pembelian', 'No Referensi', 'Trx_ID', 'ID']) || '').trim();
        var vendor = String(FIN_val_(r, ['Vendor', 'Supplier', 'Nama Supplier', 'Nama Vendor', 'Nama Kontak']) || '').trim();
        var kategori = FIN_val_(r, ['Kategori', 'Tipe Belanja', 'Jenis Belanja']);
        var item = FIN_val_(r, ['Item', 'Nama Item', 'Barang']);
        var tanggalRaw = FIN_val_(r, ['Tanggal', 'Tgl', 'Tanggal Pembelian']);
        var total = FIN_toNumber_(FIN_val_(r, ['Total', 'Subtotal', 'Nilai', 'Grand_Total', 'Grand Total']));
        var debit = FIN_purchaseDebitAccount_('PEMBELIAN', kategori, item);
        FIN_pushPurchBillGroup_(outMap, { source: 'PEMBELIAN', ref: ref, vendor: vendor, kategori: kategori, total: total, debitAccount: debit, akunHutang: 'Hutang Usaha', tanggalKey: FIN_dateKey_(FIN_parseDate_(tanggalRaw)), tanggal: FIN_displayDate_(FIN_parseDate_(tanggalRaw)) });
      });
    }
    var shMaklun = ss.getSheetByName('Data_Maklun');
    if (shMaklun) {
      var tMaklun = FIN_readSheetTable_(shMaklun);
      tMaklun.rows.forEach(function(r) {
        if (FIN_isDeletedRow_(r)) return;
        var ref = String(FIN_val_(r, ['Nota', 'No Maklun', 'No WO', 'No Referensi', 'Trx_ID', 'ID']) || '').trim();
        var vendor = String(FIN_val_(r, ['Vendor', 'Maklun', 'Nama Maklun', 'Supplier', 'Nama Kontak']) || '').trim();
        var kategori = FIN_val_(r, ['Kategori', 'Tipe', 'Jenis Maklun']);
        var item = FIN_val_(r, ['Item', 'Nama Item', 'Barang Jadi']);
        var tanggalRaw = FIN_val_(r, ['Tanggal', 'Tgl', 'Tanggal Terima']);
        var spk = String(FIN_val_(r, ['SPK', 'No SPK', 'No_SPK']) || '').trim();
        var total = FIN_toNumber_(FIN_val_(r, ['Total', 'Total_Upah', 'Total Upah', 'Tagihan', 'Grand_Total', 'Grand Total']));
        var debit = FIN_purchaseDebitAccount_('MAKLUN', kategori, item);
        FIN_pushPurchBillGroup_(outMap, { source: 'MAKLUN', ref: ref, vendor: vendor, spk: spk, kategori: kategori || 'Maklun', total: total, debitAccount: debit, akunHutang: 'Hutang Maklun', tanggalKey: FIN_dateKey_(FIN_parseDate_(tanggalRaw)), tanggal: FIN_displayDate_(FIN_parseDate_(tanggalRaw)) });
      });
    }
  } catch (err) {}
  var rows = Object.keys(outMap).map(function(k) { return outMap[k]; });
  rows.forEach(function(b) {
    b.sourceKey = FIN_purchRefKey_(b.source, b.ref, b.vendor, b.debitAccount);
  });
  rows.sort(function(a, b) { return String(b.tanggalKey).localeCompare(String(a.tanggalKey)); });
  return rows;
}

function FIN_isMaklunMaterialDpType_(tipe) {
  var t = FIN_cleanKey_(tipe);
  return t.indexOf('DPPOTONGTAGIHAN') !== -1 || t.indexOf('UANGMUKA') !== -1 || t.indexOf('DP') !== -1;
}

function FIN_getMaklunMaterialDpRows_() {
  var rows = [];
  try {
    var ss = FIN_getPurchSs_();
    var sh = ss.getSheetByName('Distribusi_Maklun');
    if (!sh) return rows;
    var table = FIN_readSheetTable_(sh);
    table.rows.forEach(function(r, idx) {
      if (FIN_isDeletedRow_(r)) return;
      var tipe = FIN_val_(r, ['Status_Akuntansi', 'Status Akuntansi', 'Tipe']);
      if (!FIN_isMaklunMaterialDpType_(tipe)) return;
      var ref = String(FIN_val_(r, ['SPK', 'No SPK', 'No_SPK']) || '').trim();
      var vendor = String(FIN_val_(r, ['Maklun', 'Vendor', 'Supplier', 'Nama Kontak']) || '').trim();
      var item = String(FIN_val_(r, ['Item', 'Bahan', 'Nama Item']) || '').trim();
      var kategori = String(FIN_val_(r, ['Kategori', 'Jenis']) || '').trim();
      var nominal = FIN_toNumber_(FIN_val_(r, ['Total', 'Nilai', 'Nominal']));
      var tanggalRaw = FIN_val_(r, ['Tanggal', 'Tgl', 'Tanggal Kirim']);
      var trx = String(FIN_val_(r, ['Trx_ID', 'Trx ID', 'ID']) || '').trim() || [ref, vendor, item, idx + 2].join('|');
      if (!ref || !vendor || !item || nominal <= 0) return;
      rows.push({
        ref: ref,
        vendor: vendor,
        item: item,
        kategori: kategori,
        nominal: nominal,
        tanggalKey: FIN_dateKey_(FIN_parseDate_(tanggalRaw)),
        tanggal: FIN_displayDate_(FIN_parseDate_(tanggalRaw)),
        creditAccount: FIN_inventoryCreditAccountForMaterial_(kategori, item),
        sourceKey: 'PURCH_MAKLUN_MATERIAL_DP_' + FIN_cleanKey_(trx)
      });
    });
  } catch (err) {}
  rows.sort(function(a, b) { return String(a.tanggalKey).localeCompare(String(b.tanggalKey)); });
  return rows;
}

function FIN_sumPurchaseAdvances_(journals, vendor, refs) {
  refs = (refs || []).filter(function(x) { return String(x || '').trim(); });
  var seen = {};
  return (journals || []).reduce(function(sum, j) {
    for (var i = 0; i < refs.length; i++) {
      if (FIN_purchaseAdvanceMatch_(j, vendor, refs[i])) {
        var key = String(j.sourceKey || '') || [j.tanggalKey, j.noReferensi, j.namaKontak, j.akunDebit, j.akunKredit, j.nominal, j.keterangan].join('|');
        if (seen[key]) return sum;
        seen[key] = true;
        return sum + FIN_toNumber_(j.nominal);
      }
    }
    return sum;
  }, 0);
}

function FIN_getSalesPoRows_() {
  var rows = [];
  try {
    var ss = FIN_getSalesSs_();
    var sh = ss.getSheetByName('Data_PO');
    if (!sh) return [];
    var table = FIN_readSheetTable_(sh);
    table.rows.forEach(function(r, idx) {
      var noPo = String(FIN_val_(r, ['No PO', 'No_PO', 'Nomor PO', 'PO_No', 'No. PO']) || '').trim();
      if (!noPo) return;
      var tanggal = FIN_parseDate_(FIN_val_(r, ['Tanggal', 'Tanggal PO', 'Tgl PO', 'Tgl']));
      var customer = FIN_val_(r, ['Nama Customer', 'Customer', 'Nama Konsumen', 'Konsumen', 'Nama_Kontak']);
      var total = FIN_toNumber_(FIN_val_(r, ['Grand_Total', 'Grand Total', 'Total Nilai', 'Total', 'Subtotal']));
      rows.push({
        rowNumber: idx + 2,
        noPo: noPo,
        tanggal: FIN_displayDate_(tanggal),
        tanggalKey: FIN_dateKey_(tanggal),
        customer: customer,
        total: total,
        status: FIN_val_(r, ['Status', 'Status PO', 'Status_Pesanan'])
      });
    });
  } catch (err) {}
  rows.sort(function(a, b) { return String(b.tanggalKey).localeCompare(String(a.tanggalKey)); });
  return rows;
}

function FIN_getPurchasingSpkMap_() {
  var map = {};
  try {
    var ss = FIN_getPurchSs_();
    var sh = ss.getSheetByName('Data_SPK');
    if (!sh) return map;
    var t = FIN_readSheetTable_(sh);
    t.rows.forEach(function(r) {
      if (FIN_isDeletedRow_(r)) return;
      var spk = String(FIN_val_(r, ['SPK', 'No SPK', 'No_SPK']) || '').trim();
      if (!spk) return;
      var k = FIN_cleanKey_(spk);
      if (!map[k]) map[k] = { spk: spk, jalur: FIN_val_(r, ['Jalur', 'Rute']), status: FIN_val_(r, ['Status']), targetQty: 0, vendor: FIN_val_(r, ['Vendor', 'Maklun']) };
      map[k].targetQty += FIN_toNumber_(FIN_val_(r, ['Qty', 'Target']));
      if (!map[k].jalur) map[k].jalur = FIN_val_(r, ['Jalur', 'Rute']);
      if (!map[k].status) map[k].status = FIN_val_(r, ['Status']);
    });
  } catch (err) {}
  return map;
}

function FIN_getPurchasingDistribusiRows_() {
  var rows = [];
  try {
    var ss = FIN_getPurchSs_();
    var sh = ss.getSheetByName('Distribusi_Maklun');
    if (!sh) return rows;
    var t = FIN_readSheetTable_(sh);
    t.rows.forEach(function(r) {
      if (FIN_isDeletedRow_(r)) return;
      var tgl = FIN_parseDate_(FIN_val_(r, ['Tanggal', 'Tgl', 'Tanggal Kirim']));
      rows.push({
        tanggal: FIN_displayDate_(tgl),
        tanggalKey: FIN_dateKey_(tgl),
        spk: String(FIN_val_(r, ['SPK', 'No SPK', 'No_SPK']) || '').trim(),
        vendor: FIN_val_(r, ['Maklun', 'Vendor', 'Supplier', 'Nama Kontak']),
        statusAkuntansi: FIN_val_(r, ['Status_Akuntansi', 'Status Akuntansi', 'Tipe']),
        kategori: FIN_val_(r, ['Kategori', 'Jenis']),
        item: FIN_val_(r, ['Item', 'Bahan', 'Nama Item']),
        qty: FIN_toNumber_(FIN_val_(r, ['Qty', 'Quantity', 'Jumlah'])),
        total: FIN_toNumber_(FIN_val_(r, ['Total', 'Nilai', 'Nominal'])),
        trxId: FIN_val_(r, ['Trx_ID', 'Trx ID', 'ID'])
      });
    });
  } catch (err) {}
  return rows;
}

function FIN_getPurchasingMaklunRows_() {
  var rows = [];
  try {
    var ss = FIN_getPurchSs_();
    var sh = ss.getSheetByName('Data_Maklun');
    if (!sh) return rows;
    var t = FIN_readSheetTable_(sh);
    t.rows.forEach(function(r) {
      if (FIN_isDeletedRow_(r)) return;
      var tgl = FIN_parseDate_(FIN_val_(r, ['Tanggal', 'Tgl', 'Tanggal Nota']));
      var qty = FIN_toNumber_(FIN_val_(r, ['Qty', 'Quantity', 'Jumlah']));
      var harga = FIN_toNumber_(FIN_val_(r, ['Harga', 'Harga Satuan', 'Unit Cost']));
      var total = FIN_toNumber_(FIN_val_(r, ['Total', 'Nilai', 'Nominal']));
      if (!total && qty && harga) total = qty * harga;
      rows.push({
        tanggal: FIN_displayDate_(tgl),
        tanggalKey: FIN_dateKey_(tgl),
        ref: String(FIN_val_(r, ['Nota', 'No Maklun', 'No WO', 'No Referensi', 'Trx_ID', 'ID']) || '').trim(),
        spk: String(FIN_val_(r, ['SPK', 'No SPK', 'No_SPK']) || '').trim(),
        vendor: FIN_val_(r, ['Vendor', 'Maklun', 'Nama Maklun', 'Supplier', 'Nama Kontak']),
        kategori: FIN_val_(r, ['Kategori', 'Tipe', 'Jenis Maklun']),
        item: FIN_val_(r, ['Item', 'Produk', 'Nama Item']),
        qty: qty,
        harga: harga,
        total: total
      });
    });
  } catch (err) {}
  return rows;
}

function FIN_groupMarketplaceFeesByStore_(settlements) {
  var map = {};
  (settlements || []).forEach(function(s) {
    var store = FIN_storeNameClean_(s.store);
    var amount = FIN_toNumber_(s.adminMarketplace);
    if (!amount) amount = FIN_toNumber_(s.admin) + FIN_toNumber_(s.layanan);
    if (amount > 0) {
      var akun = s.adminAccount || FIN_adminMarketplaceAccountForStore_(store);
      FIN_addAmount_(map, akun, amount, { source: s.sourceSheet || 'Omni_Order_Daily_Store: Biaya Admin + Biaya Layanan (tanggal order)', store: store, akun: akun, label: akun, recognitionDate: s.recognitionDate || 'ORDER_DATE' });
    }
  });
  return FIN_mapToRows_(map);
}

function FIN_isOmniBelumCairStatus_(status) {
  var s = FIN_cleanKey_(status);
  return s === 'BELUMCAIR' || s === 'UNCLEARED' || s === 'UNSETTLED' || s === 'NOTSETTLED' || (s.indexOf('BELUM') !== -1 && s.indexOf('CAIR') !== -1);
}

function FIN_makeMarketplaceReceivableNo_(tglKey, store) {
  return 'MP-' + String(tglKey || '').replace(/[^0-9]/g, '') + '-' + FIN_cleanKey_(store || 'MARKETPLACE').slice(0, 20);
}

function FIN_getOmniSettlementMap_(ss, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var sh = FIN_getSheetByCandidateNames_(ss, ['Omni_Settlement', 'Settlement_Omni', 'Settlement_OMNI', 'Settlement Omni']);
  var out = {
    byOrder: {},
    rows: [],
    sheetName: sh ? sh.getName() : '',
    summary: {
      net: 0,
      fees: 0,
      adminMarketplace: 0,
      affiliate: 0,
      ongkir: 0,
      saldoByStoreRows: [],
      adminByStoreRows: [],
      affiliateByStoreRows: []
    }
  };
  if (!sh) return out;

  var table = FIN_readSheetTable_(sh);
  var saldoMap = {}, adminMap = {}, affiliateMap = {};

  table.rows.forEach(function(r) {
    if (FIN_isDeletedValue_(FIN_val_(r, ['Is_Deleted', 'Is Deleted']))) return;
    var tglKey = FIN_settlementDateKey_(r);
    var tgl = FIN_parseDate_(tglKey || FIN_val_(r, ['Tgl Pencairan', 'Tanggal Cair', 'Tanggal Pencairan', 'Tanggal', 'Date']));
    var no = String(FIN_val_(r, ['No Pesanan', 'No_Pesanan', 'Order_ID', 'Order ID', 'ID Pesanan']) || '').trim();
    var store = FIN_storeNameClean_(FIN_val_(r, ['Toko', 'Store', 'Nama Toko', 'Nama_Toko', 'Marketplace']));

    var net = FIN_toNumber_(FIN_val_(r, ['Pendapatan Bersih', 'Pendapatan_Bersih', 'Net', 'Net Settlement', 'Total Pencairan']));
    var admin = FIN_toNumber_(FIN_val_(r, ['Biaya Admin', 'Biaya_Admin', 'Admin Fee']));
    var layanan = FIN_toNumber_(FIN_val_(r, ['Biaya Layanan', 'Biaya_Layanan', 'Service Fee']));
    var affiliate = FIN_toNumber_(FIN_val_(r, ['Komisi Affiliate', 'Komisi_Affiliate', 'Biaya Affiliate', 'Biaya_Affiliate', 'Affiliate Fee']));
    var ongkir = FIN_toNumber_(FIN_val_(r, ['Ongkir Penjual', 'Ongkir_Penjual', 'Biaya Ongkir', 'Ongkir']));
    var adminMarketplace = admin + layanan;

    if (no) {
      var k = FIN_cleanKey_(no);
      if (!out.byOrder[k]) out.byOrder[k] = { net: 0, fees: 0, adminMarketplace: 0, affiliate: 0, ongkir: 0, paid: 0, store: store, tglKey: tglKey };
      out.byOrder[k].net += net;
      out.byOrder[k].fees += adminMarketplace;
      out.byOrder[k].adminMarketplace += adminMarketplace;
      out.byOrder[k].affiliate += affiliate;
      out.byOrder[k].ongkir += ongkir;
      out.byOrder[k].paid += net + adminMarketplace;
    }

    if (!FIN_isDateKeyInRange_(tglKey, range)) return;

    var saldoAcc = FIN_saldoMarketplaceAccountForStore_(store);
    var adminAcc = FIN_adminMarketplaceAccountForStore_(store);
    FIN_addAmount_(saldoMap, saldoAcc, net, { source: sh.getName() + '.Pendapatan Bersih', store: store, akun: saldoAcc, label: saldoAcc });
    FIN_addAmount_(adminMap, adminAcc, adminMarketplace, { source: sh.getName() + '.Biaya Admin + Biaya Layanan', store: store, akun: adminAcc, label: adminAcc });
    if (affiliate) FIN_addAmount_(affiliateMap, 'Affiliate ' + store, affiliate, { source: sh.getName() + '.Affiliate', store: store, akun: 'Affiliate ' + store, label: 'Affiliate ' + store });

    out.summary.net += net;
    out.summary.fees += adminMarketplace;
    out.summary.adminMarketplace += adminMarketplace;
    out.summary.affiliate += affiliate;
    out.summary.ongkir += ongkir;
    out.rows.push({
      tanggal: FIN_displayDate_(tgl),
      tanggalKey: tglKey,
      store: store,
      noPesanan: no,
      net: net,
      pendapatanBersih: net,
      admin: admin,
      layanan: layanan,
      adminMarketplace: adminMarketplace,
      affiliate: affiliate,
      ongkir: ongkir,
      fees: adminMarketplace,
      saldoAccount: saldoAcc,
      adminAccount: adminAcc,
      sourceSheet: sh.getName()
    });
  });

  out.summary.saldoByStoreRows = FIN_mapToRows_(saldoMap).filter(function(x){ return FIN_toNumber_(x.nominal) !== 0; });
  out.summary.adminByStoreRows = FIN_mapToRows_(adminMap).filter(function(x){ return FIN_toNumber_(x.nominal) !== 0; });
  out.summary.affiliateByStoreRows = FIN_mapToRows_(affiliateMap).filter(function(x){ return FIN_toNumber_(x.nominal) !== 0; });
  return out;
}

function FIN_getOmniAdjustmentRows_(ss, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var sh = ss.getSheetByName('Data_Keuangan_Penyesuaian');
  if (!sh) return [];
  var table = FIN_readSheetTable_(sh);
  return table.rows.map(function(r){ var tgl = FIN_parseDate_(FIN_val_(r, ['Tgl Penyesuaian', 'Tanggal'])); return { tanggal: FIN_displayDate_(tgl), tanggalKey: FIN_dateKey_(tgl), store: FIN_val_(r, ['Toko']), noPesanan: FIN_val_(r, ['ID Pesanan Terkait', 'No Pesanan']), jenis: FIN_val_(r, ['Jenis Transaksi']), ref: FIN_val_(r, ['Nomor Penyesuaian']), nilai: FIN_toNumber_(FIN_val_(r, ['Nilai Penyesuaian (Rp)', 'Nilai'])) }; }).filter(function(x){ return FIN_isDateKeyInRange_(x.tanggalKey, range); });
}

function FIN_getOmniReturnRows_(ss, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var sh = ss.getSheetByName('Omni_Retur');
  if (!sh) return [];
  var table = FIN_readSheetTable_(sh);
  return table.rows.map(function(r){ var tgl = FIN_parseDate_(FIN_val_(r, ['Tgl Sampai (RTS)', 'Tgl Pesan', 'Tanggal'])); return { tanggal: FIN_displayDate_(tgl), tanggalKey: FIN_dateKey_(tgl), noPesanan: FIN_val_(r, ['No Pesanan']), resi: FIN_val_(r, ['No Resi']), sku: FIN_val_(r, ['SKU BigSeller', 'SKU']), item: FIN_val_(r, ['Item Gudang (Mapped)', 'Item Gudang']), qty: FIN_toNumber_(FIN_val_(r, ['QTY Retur Fisik', 'Qty'])), statusMarketplace: FIN_val_(r, ['Status Marketplace']), financeStatus: FIN_val_(r, ['Finance_Status']) || 'REFERENCE_ONLY' }; }).filter(function(x){ return FIN_isDateKeyInRange_(x.tanggalKey, range); });
}

function FIN_revenueAccountForSalesType_(jenis) {
  var s = String(jenis || '').trim();
  if (s) {
    var acc = FIN_accountNameByCandidatesFiltered_([s, 'Penjualan ' + s, 'Pendapatan ' + s], '', { type: 'PENDAPATAN' });
    if (acc) return acc;
  }
  return FIN_accountNameByCandidatesFiltered_(['Konvensional', 'Penjualan Konvensional', 'Pendapatan Konvensional'], 'Konvensional', { type: 'PENDAPATAN' });
}

function FIN_revenueAccountForStore_(store) {
  store = String(store || '').trim();
  var normalized = store.replace(/\s+/g, ' ');
  var candidates = [normalized, 'Pendapatan ' + normalized, 'Penjualan ' + normalized];
  var acc = FIN_accountNameByCandidatesFiltered_(candidates, '', { type: 'PENDAPATAN', denyNamePrefixes: ['Saldo'] });
  if (acc) return acc;
  return FIN_accountNameByCandidatesFiltered_(['Pendapatan Marketplace', 'Marketplace', 'Konvensional'], 'Pendapatan Marketplace', { type: 'PENDAPATAN', denyNamePrefixes: ['Saldo'] });
}

function FIN_getOmniPosReceivables_(ss, periodOrRange, journals) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var sh = ss.getSheetByName('Omni_POS_Sales');
  if (!sh) return { receivables: [], salesRows: [], gross: 0, outstanding: 0 };
  var table = FIN_readSheetTable_(sh), group = {}, salesRows = [];
  table.rows.forEach(function(r) {
    if (FIN_isDeletedValue_(FIN_val_(r, ['Is_Deleted', 'Is Deleted']))) return;
    var no = String(FIN_val_(r, ['No_POS', 'No POS', 'POS_No']) || '').trim();
    if (!no) return;
    var rawKey = String(FIN_val_(r, ['Tanggal Key', 'Tanggal_Key', 'Date_Key']) || '').trim();
    var tgl = FIN_parseDate_(FIN_val_(r, ['Tanggal', 'Date']));
    var tglKey = rawKey ? rawKey.substring(0, 10) : FIN_dateKey_(tgl);
    if (!FIN_isDateKeyInRange_(tglKey, range)) return;
    var total = FIN_toNumber_(FIN_val_(r, ['Total', 'Gross_Sales']));
    var qty = FIN_toNumber_(FIN_val_(r, ['Qty', 'Quantity']));
    if (!group[no]) group[no] = { invoiceNo: no, noPo: 'POS', customer: 'POS', store: 'POS', jenisPesanan: 'POS', tanggal: FIN_displayDate_(tglKey), tanggalKey: tglKey, nilaiInvoice: 0, qty: 0, akunPiutang: FIN_accountNameByCandidates_(['Piutang Konvensional'], 'Piutang Konvensional'), akunPendapatan: FIN_posRevenueAccount_(), source: 'POS', revenueBucket: 'POS' };
    group[no].nilaiInvoice += total; group[no].qty += qty;
    salesRows.push({ tanggalKey: tglKey, noPos: no, item: FIN_val_(r, ['Item_Name', 'Item Name']), qty: qty, total: total, akunPendapatan: FIN_posRevenueAccount_() });
  });
  var rows = [], gross = 0, outstanding = 0;
  Object.keys(group).forEach(function(no){ var x = group[no]; var paid = Math.min(x.nilaiInvoice, FIN_sumReceivableCredits_(journals, x.invoiceNo, ['Piutang Konvensional'])); var sisa = Math.max(x.nilaiInvoice - paid, 0); x.subtotal = x.nilaiInvoice; x.ongkir = 0; x.dpTerpotong = 0; x.terbayar = paid; x.sisaTagihan = sisa; x.statusPembayaran = sisa <= 0 ? 'LUNAS' : (paid > 0 ? 'PARSIAL' : 'BELUM BAYAR'); gross += x.nilaiInvoice; outstanding += sisa; rows.push(x); });
  rows.sort(function(a,b){ return String(b.tanggalKey).localeCompare(String(a.tanggalKey)); });
  return { receivables: rows, salesRows: salesRows, gross: gross, outstanding: outstanding };
}

function FIN_getOmniMarketplaceReceivables_(ss, periodOrRange, journals, settlementByOrder) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var sh = ss.getSheetByName('Omni_Order');
  if (!sh) return { receivables: [], salesRows: [], gross: 0, outstanding: 0, outstandingByStoreRows: [], omniCogsRows: [], inTransitRows: [], sampleAffiliateRows: [] };
  var table = FIN_readSheetTable_(sh), receivableGroup = {}, storeOutstanding = {}, salesRows = [], gross = 0, omniCogsRows = [], inTransitRows = [], sampleAffiliateRows = [], marketplaceFeeRows = [], feeOrderSeen = {};
  table.rows.forEach(function(r) {
    if (FIN_isDeletedValue_(FIN_val_(r, ['Is_Deleted', 'Is Deleted']))) return;
    var status = FIN_val_(r, ['Status']);
    if (FIN_isOmniCancelStatus_(status)) return;
    var tglKey = FIN_dateKeyFromAny_(FIN_val_(r, ['Tanggal Key', 'Tanggal_Key', 'Date_Key', 'Order_Date_Key']));
    if (!tglKey) tglKey = FIN_dateKeyFromAny_(FIN_val_(r, ['Tanggal', 'Order Date', 'Tanggal Pesanan']));
    if (!FIN_isDateKeyInRange_(tglKey, range)) return;
    var no = String(FIN_val_(r, ['No Pesanan', 'No_Pesanan', 'Order_ID', 'Order ID']) || '').trim();
    if (!no) return;
    var store = String(FIN_val_(r, ['Toko', 'Store', 'Nama Toko']) || 'Marketplace').trim();
    var item = FIN_val_(r, ['Item Gudang', 'Item_Gudang', 'Internal_Item_Name']);
    var sku = FIN_val_(r, ['SKU']);
    var total = FIN_toNumber_(FIN_val_(r, ['Total', 'Gross_Sales', 'Subtotal', 'Harga Jual']));
    var qty = FIN_toNumber_(FIN_val_(r, ['Qty', 'Quantity']));
    var unitCost = FIN_omniOrderUnitCost_(r);
    var cogsValue = FIN_omniOrderCogsValue_(r);
    var settlementStatus = FIN_val_(r, ['Settlement Status', 'Settlement_Status', 'Status Pencairan', 'Pencairan']);
    var costStatus = FIN_val_(r, ['Cost_Status', 'Cost Status']);
    var baseCostRow = { tanggalKey: tglKey, store: store, orderNo: no, status: status, settlementStatus: settlementStatus, item: item, sku: sku, qty: qty, unitCost: unitCost, nominal: cogsValue, costStatus: costStatus, costSource: FIN_val_(r, ['Cost_Source', 'Cost Source']) || 'Omni_Order.COGS_Value', movementType: 'OMNI_ORDER_COGS' };

    // Fallback raw: biaya settlement tetap diatribusikan ke tanggal order, satu kali per order.
    var feeKey = FIN_cleanKey_(store) + '|' + FIN_cleanKey_(no);
    var settlementForOrder = (settlementByOrder || {})[FIN_cleanKey_(no)] || null;
    if (!feeOrderSeen[feeKey] && settlementForOrder) {
      feeOrderSeen[feeKey] = true;
      var adminMarketplace = FIN_toNumber_(settlementForOrder.adminMarketplace);
      if (!adminMarketplace) adminMarketplace = FIN_toNumber_(settlementForOrder.fees);
      if (adminMarketplace > 0) {
        marketplaceFeeRows.push({
          tanggal: FIN_displayDate_(FIN_parseDate_(tglKey)),
          tanggalKey: tglKey,
          store: store,
          noPesanan: no,
          admin: adminMarketplace,
          layanan: 0,
          adminMarketplace: adminMarketplace,
          fees: adminMarketplace,
          adminAccount: FIN_adminMarketplaceAccountForStore_(store),
          sourceSheet: 'Omni_Order + Omni_Settlement',
          recognitionDate: 'ORDER_DATE'
        });
      }
    }

    if (FIN_isOmniSampleAffiliateRow_(r)) {
      sampleAffiliateRows.push(Object.assign({}, baseCostRow, { akun: FIN_sampleAffiliateAccount_(), source: 'Omni_Order SAMPLE_AFFILIATE' }));
      return;
    }
    if (FIN_isOmniCompletedStatus_(status)) {
      if (total > 0) {
        gross += total;
        salesRows.push({ tanggalKey: tglKey, store: store, orderNo: no, status: status, settlementStatus: settlementStatus, item: item, sku: sku, qty: qty, total: total, akunPendapatan: FIN_revenueAccountForStore_(store) });
      }
      if (cogsValue > 0) omniCogsRows.push(baseCostRow);
    } else if (FIN_isOmniInTransitStatus_(status)) {
      if (cogsValue > 0) inTransitRows.push(Object.assign({}, baseCostRow, { akun: 'Persediaan Barang Dalam Pengiriman' }));
    }

    if (!FIN_isOmniCompletedStatus_(status)) return;
    if (total <= 0) return;
    if (!FIN_isOmniBelumCairStatus_(settlementStatus)) return;
    var key = tglKey + '|' + FIN_cleanKey_(store || 'Marketplace');
    if (!receivableGroup[key]) {
      receivableGroup[key] = { invoiceNo: FIN_makeMarketplaceReceivableNo_(tglKey, store), noPo: 'OMNI-BELUM-CAIR', customer: 'Marketplace - ' + store, store: store, jenisPesanan: 'MARKETPLACE', tanggal: FIN_displayDate_(FIN_parseDate_(tglKey)), tanggalKey: tglKey, nilaiInvoice: 0, qty: 0, orderCount: 0, orderMap: {}, statusRaw: 'BELUM CAIR', akunPiutang: FIN_accountNameByCandidates_(['Piutang Marketplace'], 'Piutang Marketplace'), akunPendapatan: FIN_revenueAccountForStore_(store), source: 'MARKETPLACE', revenueBucket: store, settlementStatus: 'BELUM CAIR', settlementNet: 0, settlementFees: 0, subtotal: 0, ongkir: 0, dpTerpotong: 0, terbayar: 0, sisaTagihan: 0, statusPembayaran: 'BELUM CAIR', note: 'Grouped from Omni_Order by Tanggal + Toko + Settlement Status BELUM CAIR' };
    }
    var g = receivableGroup[key];
    g.nilaiInvoice += total; g.subtotal += total; g.sisaTagihan += total; g.qty += qty;
    if (!g.orderMap[no]) { g.orderMap[no] = true; g.orderCount += 1; }
    FIN_addAmount_(storeOutstanding, store, total, { source: 'Omni_Order', settlementStatus: 'BELUM CAIR' });
  });
  var rows = Object.keys(receivableGroup).map(function(k){ var x = receivableGroup[k]; x.orderCount = x.orderCount || Object.keys(x.orderMap || {}).length; x.keterangan = (x.orderCount || 0) + ' order belum cair'; delete x.orderMap; return x; });
  rows.sort(function(a,b){ return String(b.tanggalKey).localeCompare(String(a.tanggalKey)) || String(a.store).localeCompare(String(b.store)); });
  var storeRows = Object.keys(storeOutstanding).map(function(store){ var v = FIN_toNumber_(storeOutstanding[store] && storeOutstanding[store].nominal !== undefined ? storeOutstanding[store].nominal : storeOutstanding[store]); return { store: store, customer: 'Marketplace - ' + store, invoiceNo: 'MP-' + FIN_cleanKey_(store || 'MARKETPLACE'), source: 'MARKETPLACE', statusPembayaran: 'BELUM CAIR', sisaTagihan: v, nilaiInvoice: v }; }).sort(function(a,b){ return FIN_toNumber_(b.sisaTagihan) - FIN_toNumber_(a.sisaTagihan); });
  return { receivables: rows, salesRows: salesRows, gross: gross, outstanding: FIN_sum_(rows, 'sisaTagihan'), outstandingByStoreRows: storeRows, omniCogsRows: omniCogsRows, inTransitRows: inTransitRows, sampleAffiliateRows: sampleAffiliateRows, marketplaceFeeRows: marketplaceFeeRows };
}

function FIN_getOmniFinanceData_(periodOrRange, journals) {
  var ss = FIN_getOmniSs_();
  var out = FIN_emptyOmniFinance_();
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  out.periodKey = range.periodKey;
  out.dateStart = range.startKey;
  out.dateEnd = range.endKey;

  var settlementMap = FIN_getOmniSettlementMap_(ss, range);
  out.settlements = settlementMap.rows || [];
  out.settlementSourceSheet = settlementMap.sheetName || 'Omni_Settlement / Settlement_Omni';
  out.adjustments = FIN_getOmniAdjustmentRows_(ss, range);
  out.returns = FIN_getOmniReturnRows_(ss, range);

  var orderData = FIN_getOmniMarketplaceReceivables_(ss, range, journals || [], settlementMap.byOrder || {});
  var posData = FIN_getOmniPosReceivables_(ss, range, journals || []);
  out.receivables = (orderData.receivables || []).concat(posData.receivables || []);
  out.marketplaceSales = orderData.salesRows || [];
  out.posSales = posData.salesRows || [];
  out.omniCogsRows = orderData.omniCogsRows || [];
  out.inTransitRows = orderData.inTransitRows || [];
  out.sampleAffiliateRows = orderData.sampleAffiliateRows || [];
  out.marketplaceFeeRows = orderData.marketplaceFeeRows || [];
  out.outstandingByStoreRows = orderData.outstandingByStoreRows || [];
  out.revenueRows = FIN_buildRevenueRowsFromInvoices_(out.receivables, range.periodKey);
  var orderDateAdminRows = FIN_groupMarketplaceFeesByStore_(out.marketplaceFeeRows);
  var orderDateAdminTotal = FIN_sum_(orderDateAdminRows, 'nominal');

  out.summary = {
    marketplaceGross: FIN_toNumber_(orderData.gross),
    marketplaceOutstanding: FIN_toNumber_(orderData.outstanding),
    marketplaceReceivableGroups: (orderData.receivables || []).length,
    marketplaceOutstandingByStoreRows: orderData.outstandingByStoreRows || [],
    marketplaceDateBuckets: orderData.dateBuckets || [],
    posGross: FIN_toNumber_(posData.gross),
    posOutstanding: FIN_toNumber_(posData.outstanding),
    settlementNet: FIN_toNumber_(settlementMap.summary && settlementMap.summary.net),
    settlementFees: orderDateAdminTotal,
    settlementAdminMarketplace: orderDateAdminTotal,
    adminFeeRecognitionBasis: 'ORDER_DATE',
    settlementAffiliate: FIN_toNumber_(settlementMap.summary && settlementMap.summary.affiliate),
    settlementOngkir: FIN_toNumber_(settlementMap.summary && settlementMap.summary.ongkir),
    saldoByStoreRows: (settlementMap.summary && settlementMap.summary.saldoByStoreRows) || [],
    adminByStoreRows: orderDateAdminRows,
    affiliateByStoreRows: (settlementMap.summary && settlementMap.summary.affiliateByStoreRows) || [],
    adjustmentTotal: FIN_sum_(out.adjustments, 'nilai'),
    returnQty: FIN_sum_(out.returns, 'qty'),
    inTransitValue: FIN_sum_(out.inTransitRows, 'nominal'),
    sampleAffiliateValue: FIN_sum_(out.sampleAffiliateRows, 'nominal'),
    omniOrderCogs: FIN_sum_(out.omniCogsRows, 'nominal')
  };
  return out;
}

function FIN_isOmniInTransitStatus_(status) {
  var s = FIN_cleanKey_(status);
  if (!s || FIN_isOmniCancelStatus_(s) || FIN_isOmniCompletedStatus_(s)) return false;
  return s.indexOf('DIKIRIM') !== -1 || s.indexOf('KIRIM') !== -1 || s.indexOf('SHIPPED') !== -1 || s.indexOf('INTRANSIT') !== -1 || s.indexOf('ONDELIVERY') !== -1 || s.indexOf('DELIVERY') !== -1;
}

function FIN_isOmniSampleAffiliateRow_(r) {
  var bucket = FIN_cleanKey_(FIN_val_(r, ['Finance_Bucket', 'Finance Bucket']));
  var total = FIN_toNumber_(FIN_val_(r, ['Total', 'Gross_Sales', 'Subtotal', 'Harga Jual']));
  var cogs = FIN_omniOrderCogsValue_(r);
  return bucket === 'SAMPLEAFFILIATE' || (total <= 0 && cogs > 0);
}

function FIN_sampleAffiliateAccount_() {
  return FIN_accountNameByCandidates_(['Biaya Sample Affiliate', 'Biaya Sample Affiliate Kiral', 'Sample Affiliate'], 'Biaya Sample Affiliate');
}





function FIN_saldoMarketplaceAccountForStore_(store) {
  store = FIN_storeNameClean_(store);
  return FIN_accountNameByCandidatesFiltered_([
    'Saldo ' + store,
    store,
    'Bank ' + store,
    'Kas ' + store
  ], 'Saldo ' + store, { type: 'ASET' });
}

function FIN_adminMarketplaceAccountForStore_(store) {
  store = FIN_storeNameClean_(store);
  return FIN_accountNameByCandidatesFiltered_([
    'Biaya Admin ' + store,
    'Biaya Admin Marketplace ' + store,
    'Admin ' + store,
    'Admin Marketplace ' + store,
    'Biaya Marketplace ' + store,
    'Biaya Admin Marketplace',
    'Biaya Administrasi Bank'
  ], 'Biaya Admin ' + store, { type: 'BEBAN' });
}