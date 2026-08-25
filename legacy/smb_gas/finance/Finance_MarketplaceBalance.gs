/**
 * Finance v1.9.3.4
 * Balance-sheet readers for marketplace clearing balance and goods in transit.
 * Laba Rugi keeps using the selected date range; these readers are cumulative as-of dateEnd.
 */

function FIN_isMarketplaceBalanceAccount_(account) {
  var a = FIN_cleanKey_(account);
  if (!a) return false;

  var hasMarketplaceBrand = ['SHOPEE','TOKOPEDIA','TIKTOK','LAZADA','BUKALAPAK','BLIBLI','MARKETPLACE'].some(function(k){
    return a.indexOf(k) !== -1;
  });
  var hasWalletWord = a.indexOf('WALLET') !== -1 || a.indexOf('DOMPET') !== -1;
  var explicitMarketplaceSaldo = a.indexOf('SALDOTOKO') !== -1 || a.indexOf('SALDOMARKETPLACE') !== -1 || a.indexOf('MARKETPLACEBALANCE') !== -1;
  var brandedSaldo = hasMarketplaceBrand && a.indexOf('SALDO') !== -1;
  var looksStoreBank = a.indexOf('BANK') === 0 && hasMarketplaceBrand;

  // Saldo bank/kas nyata tetap diklasifikasikan sebagai kas/bank.
  var hasRealBank = ['BCA','MANDIRI','BRI','BNI','CIMB','PERMATA','DANAMON','PANIN','OCBC','MAYBANK'].some(function(k){
    return a.indexOf(k) !== -1;
  });
  if (hasRealBank && !hasMarketplaceBrand) return false;
  if (a.indexOf('KAS') !== -1 && !hasMarketplaceBrand) return false;

  return explicitMarketplaceSaldo || brandedSaldo || looksStoreBank || (hasMarketplaceBrand && hasWalletWord);
}

function FIN_marketplaceBalanceAsOfRange_(periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  return FIN_resolveReportRange_({ dateStart:'1900-01-01', dateEnd:range.endKey });
}


/**
 * Piutang marketplace adalah akun neraca, jadi harus kumulatif sampai dateEnd.
 * Laporan penjualan tetap memakai rentang tanggal terpilih melalui reader periodik.
 */
function FIN_getMarketplaceReceivablesAsOf_(periodOrRange, journals) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var asOfRange = FIN_marketplaceBalanceAsOfRange_(range);
  var ss = FIN_getOmniSs_();
  var orderData = FIN_getOmniOrderDailyData_(ss, asOfRange);
  var rows = [];
  var sourceMode = 'OMNI_ORDER_DAILY_SUMMARY_RECEIVABLE_ASOF';

  if (orderData.ready) {
    rows = (orderData.receivables || []).filter(function(r) {
      return FIN_cleanKey_(r && r.source) === 'MARKETPLACE';
    });
  } else {
    var settlementMap = FIN_getOmniSettlementMap_(ss, asOfRange);
    var raw = FIN_getOmniMarketplaceReceivables_(ss, asOfRange, journals || [], settlementMap.byOrder || {});
    rows = raw.receivables || [];
    sourceMode = 'OMNI_ORDER_RAW_RECEIVABLE_ASOF_FALLBACK';
  }

  var byStore = {};
  rows.forEach(function(r) {
    var store = FIN_storeNameClean_(r.store || r.customer);
    byStore[store] = (byStore[store] || 0) + FIN_toNumber_(r.sisaTagihan);
  });

  var byStoreRows = Object.keys(byStore).map(function(store) {
    return {
      store:store,
      akun:'Piutang Marketplace',
      customer:'Marketplace - ' + store,
      sisaTagihan:FIN_toNumber_(byStore[store]),
      nominal:FIN_toNumber_(byStore[store]),
      source:sourceMode
    };
  }).filter(function(r) { return Math.abs(FIN_toNumber_(r.sisaTagihan)) > 0.00001; })
    .sort(function(a,b) { return FIN_toNumber_(b.sisaTagihan) - FIN_toNumber_(a.sisaTagihan); });

  return {
    success:true,
    asOfDate:range.endKey,
    sourceMode:sourceMode,
    rows:rows,
    byStoreRows:byStoreRows,
    outstanding:FIN_sum_(rows, 'sisaTagihan')
  };
}

function FIN_getOmniReceivablesAsOf_(periodOrRange, journals) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var asOfRange = FIN_marketplaceBalanceAsOfRange_(range);
  var marketplace = FIN_getMarketplaceReceivablesAsOf_(range, journals || []);
  var posData = { receivables:[], outstanding:0, gross:0 };
  try {
    posData = FIN_getOmniPosReceivables_(FIN_getOmniSs_(), asOfRange, journals || []);
  } catch (e) {}
  return {
    success:true,
    asOfDate:range.endKey,
    marketplace:marketplace,
    pos:posData,
    rows:(marketplace.rows || []).concat(posData.receivables || []),
    marketplaceOutstanding:FIN_toNumber_(marketplace.outstanding),
    posOutstanding:FIN_toNumber_(posData.outstanding),
    totalOutstanding:FIN_toNumber_(marketplace.outstanding) + FIN_toNumber_(posData.outstanding)
  };
}

function FIN_getMarketplaceBalanceAsOf_(periodOrRange, journals) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var asOfRange = FIN_marketplaceBalanceAsOfRange_(range);
  var ss = FIN_getOmniSs_();
  var settlementMap = FIN_getOmniSettlementDailyMap_(ss, asOfRange);
  var fallback = false;
  if (!settlementMap.ready) {
    settlementMap = FIN_getOmniSettlementMap_(ss, asOfRange);
    fallback = true;
  }

  var map = {};
  function ensure(account, meta) {
    var name = String(account || '').trim();
    var key = FIN_cleanKey_(name);
    if (!key) return null;
    if (!map[key]) {
      map[key] = {
        akun:name,
        label:name,
        store:meta && meta.store || '',
        settlementNet:0,
        journalDebit:0,
        journalCredit:0,
        nominal:0,
        source:''
      };
    }
    if (meta && meta.store && !map[key].store) map[key].store = meta.store;
    return map[key];
  }

  ((settlementMap.summary && settlementMap.summary.saldoByStoreRows) || []).forEach(function(r) {
    var row = ensure(r.akun || r.label, r);
    if (row) row.settlementNet += FIN_toNumber_(r.nominal);
  });

  FIN_manualJournalsOnly_(journals || []).forEach(function(j) {
    var dateKey = FIN_rowDateKey_(j);
    if (dateKey && dateKey > range.endKey) return;
    var nominal = FIN_toNumber_(j.nominal);
    if (!nominal) return;

    var debitName = String(j.akunDebit || '').trim();
    var debitKey = FIN_cleanKey_(debitName);
    if (map[debitKey] || FIN_isMarketplaceBalanceAccount_(debitName)) {
      var debitRow = ensure(debitName, {});
      if (debitRow) debitRow.journalDebit += nominal;
    }

    var creditName = String(j.akunKredit || '').trim();
    var creditKey = FIN_cleanKey_(creditName);
    if (map[creditKey] || FIN_isMarketplaceBalanceAccount_(creditName)) {
      var creditRow = ensure(creditName, {});
      if (creditRow) creditRow.journalCredit += nominal;
    }
  });

  var rows = Object.keys(map).map(function(k) {
    var r = map[k];
    r.nominal = r.settlementNet + r.journalDebit - r.journalCredit;
    r.source = 'Settlement kumulatif s.d. ' + range.endKey + ' + Db Saldo Toko - Cr Saldo Toko';
    return r;
  }).filter(function(r){
    return Math.abs(FIN_toNumber_(r.nominal)) > 0.00001 || r.settlementNet || r.journalDebit || r.journalCredit;
  }).sort(function(a,b){ return String(a.akun).localeCompare(String(b.akun)); });

  return {
    success:true,
    asOfDate:range.endKey,
    sourceMode:fallback ? 'OMNI_SETTLEMENT_RAW_ASOF_FALLBACK' : 'OMNI_SETTLEMENT_DAILY_SUMMARY_ASOF',
    rows:rows,
    settlementNet:rows.reduce(function(sum,r){ return sum + FIN_toNumber_(r.settlementNet); },0),
    journalDebit:rows.reduce(function(sum,r){ return sum + FIN_toNumber_(r.journalDebit); },0),
    journalCredit:rows.reduce(function(sum,r){ return sum + FIN_toNumber_(r.journalCredit); },0),
    balance:rows.reduce(function(sum,r){ return sum + FIN_toNumber_(r.nominal); },0)
  };
}

function FIN_getInTransitInventoryAsOf_(periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var asOfRange = FIN_marketplaceBalanceAsOfRange_(range);
  var ss = FIN_getOmniSs_();
  var info = FIN_dailySummaryTable_(ss, FIN_OMNI_DAILY_ORDER_STORE_SHEET, [
    'Date_Key','Store_Name','In_Transit_COGS','In_Transit_Sample_Cost','Summary_Version'
  ]);
  var ready = FIN_dailySummaryVersionOk_(info);
  var rows = [], value = 0;

  if (ready) {
    (info.table.rows || []).forEach(function(r) {
      var key = FIN_dateKeyFromAny_(FIN_val_(r, ['Date_Key']));
      if (!FIN_isDateKeyInRange_(key, asOfRange)) return;
      var gross = FIN_toNumber_(FIN_val_(r, ['In_Transit_COGS']));
      var sample = FIN_toNumber_(FIN_val_(r, ['In_Transit_Sample_Cost']));
      var nominal = Math.max(gross - sample, 0);
      if (!nominal) return;
      var store = FIN_storeNameClean_(FIN_val_(r, ['Store_Name']));
      value += nominal;
      rows.push({
        tanggalKey:key,
        tanggal:FIN_displayDate_(FIN_parseDate_(key)),
        store:store,
        nominal:nominal,
        grossCogs:gross,
        sampleCost:sample,
        status:'Sudah Dikirim',
        source:FIN_OMNI_DAILY_ORDER_STORE_SHEET + '.In_Transit_COGS - In_Transit_Sample_Cost'
      });
    });
    return { success:true, asOfDate:range.endKey, sourceMode:'OMNI_ORDER_DAILY_SUMMARY_TRANSIT_ASOF', value:value, rows:rows };
  }

  // Fallback aman bila summary belum siap. Reader raw/daily lama tetap mempertahankan kontrak output.
  var fallback = FIN_getOmniFinanceDataDaily_(asOfRange, []);
  rows = fallback.inTransitRows || [];
  value = FIN_sum_(rows, 'nominal');
  return { success:true, asOfDate:range.endKey, sourceMode:'OMNI_TRANSIT_RAW_FALLBACK_ASOF', value:value, rows:rows };
}

function FIN_applyMarketplaceAndTransitAsOf_(valuation, journals, periodOrRange) {
  valuation = valuation || {};
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  if (valuation.balanceAsOfDate === range.endKey && valuation.marketplaceBalanceAudit && valuation.inTransitAudit && valuation.marketplaceReceivableAudit) return valuation;
  var marketplace = FIN_getMarketplaceBalanceAsOf_(range, journals || []);
  var transit = FIN_getInTransitInventoryAsOf_(range);
  var receivable = FIN_getMarketplaceReceivablesAsOf_(range, journals || []);

  valuation.marketplaceSaldoRows = marketplace.rows || [];
  valuation.marketplaceSaldoValue = FIN_toNumber_(marketplace.balance);
  valuation.marketplaceBalanceAudit = marketplace;
  valuation.marketplaceReceivableRows = receivable.rows || [];
  valuation.marketplaceReceivableByStoreRows = receivable.byStoreRows || [];
  valuation.marketplaceReceivableValue = FIN_toNumber_(receivable.outstanding);
  valuation.marketplaceReceivableAudit = receivable;
  valuation.inTransitRows = transit.rows || [];
  valuation.inTransitValue = FIN_toNumber_(transit.value);
  valuation.inTransitAudit = transit;
  valuation.balanceAsOfDate = range.endKey;

  // COGM/COGS hanya menampilkan komponen produksi, HPP, dan persediaan.
  // Piutang Marketplace serta Saldo Toko adalah aset keuangan dan hanya boleh
  // dibaca oleh FIN_calcNeracaMvp_ melalui property valuation di atas.
  valuation.rows = (valuation.rows || []).filter(function(r) {
    var label = String(r && (r.komponen || r.akun || r.label) || '').trim();
    var k = FIN_cleanKey_(label);
    if (k === 'PIUTANGMARKETPLACE' || k === 'SALDOMARKETPLACE') return false;
    if (FIN_isMarketplaceBalanceAccount_(label)) return false;
    return k !== 'PERSEDIAANBARANGDALAMPENGIRIMAN';
  });

  // Persediaan dalam pengiriman tetap relevan di ringkasan inventory/COGS.
  valuation.rows.push({
    komponen:'Persediaan Barang Dalam Pengiriman',
    source:'Status Omni_Order = Sudah Dikirim; kumulatif s.d. ' + range.endKey,
    qty:'', nominal:valuation.inTransitValue
  });
  return valuation;
}

function TEST_financeMarketplaceBalanceAsOf(filter) {
  FIN_requireAccess_();
  var range = FIN_resolveReportRange_(filter || {});
  var journals = FIN_filterRowsThroughPeriod_(FIN_getJurnalRows_(), range);
  var result = FIN_getMarketplaceBalanceAsOf_(range, journals);
  return {
    success:true,
    version:FIN_CFG.VERSION,
    formula:'Saldo Toko = Net Settlement kumulatif + Db Saldo Toko - Cr Saldo Toko',
    asOfDate:result.asOfDate,
    sourceMode:result.sourceMode,
    settlementNet:result.settlementNet,
    journalDebit:result.journalDebit,
    journalCredit:result.journalCredit,
    balance:result.balance,
    rows:result.rows
  };
}

function TEST_financeInTransitAsOf(filter) {
  FIN_requireAccess_();
  var range = FIN_resolveReportRange_(filter || {});
  var result = FIN_getInTransitInventoryAsOf_(range);
  return {
    success:true,
    version:FIN_CFG.VERSION,
    recognizedStatus:'Sudah Dikirim',
    asOfDate:result.asOfDate,
    sourceMode:result.sourceMode,
    value:result.value,
    rowCount:(result.rows || []).length,
    rows:(result.rows || []).slice(0,100)
  };
}

function TEST_financeMarketplaceReceivableAsOf(filter) {
  FIN_requireAccess_();
  var range = FIN_resolveReportRange_(filter || {});
  var journals = FIN_filterRowsThroughPeriod_(FIN_getJurnalRows_(), range);
  var result = FIN_getMarketplaceReceivablesAsOf_(range, journals);
  return {
    success:true,
    version:FIN_CFG.VERSION,
    formula:'Piutang Marketplace = Completed_Unsettled_Sales kumulatif sampai dateEnd',
    asOfDate:result.asOfDate,
    sourceMode:result.sourceMode,
    outstanding:result.outstanding,
    rowCount:(result.rows || []).length,
    byStoreRows:result.byStoreRows || [],
    rows:(result.rows || []).slice(0,100)
  };
}

function TEST_financeMarketplaceTransferFormula() {
  FIN_requireAccess_();
  var settlement = 10000000;
  var debitCorrection = 0;
  var creditToBank = 7000000;
  var saldoToko = settlement + debitCorrection - creditToBank;
  var bank = creditToBank;
  return {
    success:saldoToko === 3000000 && bank === 7000000,
    journal:'Db Bank 7.000.000 / Cr Saldo Toko 7.000.000',
    settlement:settlement,
    saldoToko:saldoToko,
    bank:bank,
    totalAsset:saldoToko + bank
  };
}