/**
 * Finance v1.9.0 - Omni Daily Summary Reader
 *
 * Jalur utama:
 * - Omni_Order_Daily_Store      : penjualan, piutang belum cair, COGS, in-transit, sample.
 * - Omni_Order_Daily_Product    : detail produk ringkas untuk audit/report berikutnya.
 * - Omni_Settlement_Daily_Store : saldo marketplace/kas berdasarkan tanggal pencairan.
 * - Biaya admin + layanan          : diakui berdasarkan tanggal order dari Omni_Order_Daily_Store.
 *
 * Data mentah tetap dipertahankan sebagai audit source dan fallback bila summary belum siap.
 */

var FIN_OMNI_DAILY_ORDER_STORE_SHEET = 'Omni_Order_Daily_Store';
var FIN_OMNI_DAILY_ORDER_PRODUCT_SHEET = 'Omni_Order_Daily_Product';
var FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET = 'Omni_Settlement_Daily_Store';
var FIN_OMNI_DAILY_VERSION_PREFIX = 'OMNI_SUMMARY_V3';

function FIN_sheetHasData_(sh) {
  return !!(sh && sh.getLastRow && sh.getLastRow() > 1);
}

function FIN_dailySummaryTable_(ss, sheetName, requiredHeaders) {
  var sh = ss && ss.getSheetByName(sheetName);
  var out = { sheet: sh, sheetName: sheetName, table: null, ready: false, missingHeaders: [], versions: [] };
  if (!sh) {
    out.missingHeaders = (requiredHeaders || []).slice();
    return out;
  }
  var table = FIN_readSheetTable_(sh);
  out.table = table;
  out.missingHeaders = (requiredHeaders || []).filter(function(h) {
    return table.map[FIN_headerKey_(h)] === undefined;
  });
  var versionMap = {};
  (table.rows || []).forEach(function(r) {
    var v = String(FIN_val_(r, ['Summary_Version', 'Summary Version']) || '').trim();
    if (v) versionMap[v] = true;
  });
  out.versions = Object.keys(versionMap);
  out.ready = out.missingHeaders.length === 0;
  return out;
}

function FIN_dailySummaryVersionOk_(info) {
  if (!info || !info.ready) return false;
  if (!info.table || !info.table.rows.length) return true;
  if (!info.versions || !info.versions.length) return false;
  // Seluruh baris harus berasal dari kontrak summary yang kompatibel.
  // Jika versi lama dan baru tercampur, fallback ke raw lebih aman daripada menjumlahkan data ganda/stale.
  return info.versions.every(function(v) {
    return String(v || '').indexOf(FIN_OMNI_DAILY_VERSION_PREFIX) === 0;
  });
}

function FIN_makeDailySummaryRef_(prefix, dateKey, store) {
  return [prefix, String(dateKey || '').replace(/-/g, ''), FIN_cleanKey_(store || 'MARKETPLACE')].join('-');
}

function FIN_getOmniOrderDailyData_(ss, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var info = FIN_dailySummaryTable_(ss, FIN_OMNI_DAILY_ORDER_STORE_SHEET, [
    'Date_Key', 'Store_Name', 'Completed_Sales', 'Completed_Unsettled_Sales',
    'Completed_COGS', 'In_Transit_COGS', 'Sample_Cost',
    'Completed_Sample_Cost', 'In_Transit_Sample_Cost',
    'Admin_Fee', 'Service_Fee', 'Summary_Version'
  ]);
  var rawSh = ss && ss.getSheetByName('Omni_Order');
  var hasRaw = FIN_sheetHasData_(rawSh);
  var hasSummary = !!(info.table && info.table.rows && info.table.rows.length);
  var ready = FIN_dailySummaryVersionOk_(info) && (!hasRaw || hasSummary);
  var out = {
    ready: ready,
    sourceMode: 'OMNI_DAILY_SUMMARY_V3',
    sheetName: FIN_OMNI_DAILY_ORDER_STORE_SHEET,
    missingHeaders: info.missingHeaders || [],
    versions: info.versions || [],
    receivables: [],
    salesRows: [],
    gross: 0,
    outstanding: 0,
    outstandingByStoreRows: [],
    dateBuckets: [],
    omniCogsRows: [],
    inTransitRows: [],
    sampleAffiliateRows: [],
    productRows: [],
    marketplaceFeeRows: [],
    adminByStoreRows: [],
    adminMarketplace: 0,
    sourceRowCount: 0
  };
  if (!ready) return out;

  var storeOutstanding = {};
  var adminOrderDateMap = {};
  (info.table.rows || []).forEach(function(r) {
    var tglKey = FIN_dateKeyFromAny_(FIN_val_(r, ['Date_Key', 'Tanggal Key']));
    if (!FIN_isDateKeyInRange_(tglKey, range)) return;
    var store = FIN_storeNameClean_(FIN_val_(r, ['Store_Name', 'Toko', 'Store']));
    var completedSales = FIN_toNumber_(FIN_val_(r, ['Completed_Sales']));
    var completedUnsettled = FIN_toNumber_(FIN_val_(r, ['Completed_Unsettled_Sales']));
    var completedCogs = FIN_toNumber_(FIN_val_(r, ['Completed_COGS']));
    var inTransitCogs = FIN_toNumber_(FIN_val_(r, ['In_Transit_COGS']));
    var sampleCost = FIN_toNumber_(FIN_val_(r, ['Sample_Cost']));
    var completedSample = FIN_toNumber_(FIN_val_(r, ['Completed_Sample_Cost']));
    var transitSample = FIN_toNumber_(FIN_val_(r, ['In_Transit_Sample_Cost']));
    var completedOrderCount = FIN_toNumber_(FIN_val_(r, ['Completed_Order_Count']));
    var itemQty = FIN_toNumber_(FIN_val_(r, ['Item_Qty']));
    var sourceRows = FIN_toNumber_(FIN_val_(r, ['Source_Row_Count']));
    var adminFee = FIN_toNumber_(FIN_val_(r, ['Admin_Fee']));
    var serviceFee = FIN_toNumber_(FIN_val_(r, ['Service_Fee']));
    var adminMarketplace = adminFee + serviceFee;
    out.sourceRowCount += sourceRows;

    if (adminMarketplace > 0) {
      var adminAccount = FIN_adminMarketplaceAccountForStore_(store);
      FIN_addAmount_(adminOrderDateMap, adminAccount, adminMarketplace, {
        source: FIN_OMNI_DAILY_ORDER_STORE_SHEET + '.Admin_Fee + Service_Fee',
        recognitionDate: 'ORDER_DATE',
        tanggalKey: tglKey,
        store: store,
        akun: adminAccount,
        label: adminAccount
      });
      out.marketplaceFeeRows.push({
        tanggal: FIN_displayDate_(FIN_parseDate_(tglKey)),
        tanggalKey: tglKey,
        store: store,
        admin: adminFee,
        layanan: serviceFee,
        adminMarketplace: adminMarketplace,
        fees: adminMarketplace,
        adminAccount: adminAccount,
        sourceSheet: FIN_OMNI_DAILY_ORDER_STORE_SHEET,
        recognitionDate: 'ORDER_DATE'
      });
      out.adminMarketplace += adminMarketplace;
    }

    if (completedSales > 0) {
      out.gross += completedSales;
      out.salesRows.push({
        tanggalKey: tglKey,
        store: store,
        orderNo: FIN_makeDailySummaryRef_('OMNI-SALE', tglKey, store),
        status: 'SELESAI',
        settlementStatus: completedUnsettled > 0 ? 'MIXED/BELUM CAIR' : 'SUDAH CAIR',
        qty: itemQty,
        orderCount: completedOrderCount,
        total: completedSales,
        akunPendapatan: FIN_revenueAccountForStore_(store),
        source: FIN_OMNI_DAILY_ORDER_STORE_SHEET
      });
    }

    if (completedUnsettled > 0) {
      var ref = FIN_makeDailySummaryRef_('MP', tglKey, store);
      out.receivables.push({
        invoiceNo: ref,
        noPo: 'OMNI-BELUM-CAIR',
        customer: 'Marketplace - ' + store,
        store: store,
        jenisPesanan: 'MARKETPLACE',
        tanggal: FIN_displayDate_(FIN_parseDate_(tglKey)),
        tanggalKey: tglKey,
        nilaiInvoice: completedUnsettled,
        qty: '',
        orderCount: '',
        statusRaw: 'BELUM CAIR',
        akunPiutang: FIN_accountNameByCandidates_(['Piutang Marketplace'], 'Piutang Marketplace'),
        akunPendapatan: FIN_revenueAccountForStore_(store),
        source: 'MARKETPLACE',
        sourceSheet: FIN_OMNI_DAILY_ORDER_STORE_SHEET,
        revenueBucket: store,
        settlementStatus: 'BELUM CAIR',
        settlementNet: 0,
        settlementFees: 0,
        subtotal: completedUnsettled,
        ongkir: 0,
        dpTerpotong: 0,
        terbayar: 0,
        sisaTagihan: completedUnsettled,
        statusPembayaran: 'BELUM CAIR',
        keterangan: 'Order selesai belum cair - daily summary tanggal/toko',
        note: 'Grouped from Omni_Order_Daily_Store.Completed_Unsettled_Sales'
      });
      storeOutstanding[store] = (storeOutstanding[store] || 0) + completedUnsettled;
    }

    var salesCogs = Math.max(completedCogs - completedSample, 0);
    if (salesCogs > 0) {
      out.omniCogsRows.push({
        tanggalKey: tglKey,
        store: store,
        orderNo: FIN_makeDailySummaryRef_('OMNI-COGS', tglKey, store),
        status: 'SELESAI',
        item: 'Daily summary ' + store,
        qty: '',
        nominal: salesCogs,
        costStatus: 'SUMMARY_AGGREGATED',
        costSource: FIN_OMNI_DAILY_ORDER_STORE_SHEET + '.Completed_COGS - Completed_Sample_Cost',
        movementType: 'OMNI_DAILY_COGS',
        source: FIN_OMNI_DAILY_ORDER_STORE_SHEET
      });
    }

    var transitCogsNet = Math.max(inTransitCogs - transitSample, 0);
    if (transitCogsNet > 0) {
      out.inTransitRows.push({
        tanggalKey: tglKey,
        store: store,
        orderNo: FIN_makeDailySummaryRef_('OMNI-TRANSIT', tglKey, store),
        status: 'DALAM PENGIRIMAN',
        item: 'Daily summary ' + store,
        qty: '',
        nominal: transitCogsNet,
        akun: 'Persediaan Barang Dalam Pengiriman',
        costStatus: 'SUMMARY_AGGREGATED',
        costSource: FIN_OMNI_DAILY_ORDER_STORE_SHEET + '.In_Transit_COGS - In_Transit_Sample_Cost',
        movementType: 'OMNI_DAILY_IN_TRANSIT',
        source: FIN_OMNI_DAILY_ORDER_STORE_SHEET
      });
    }

    if (sampleCost > 0) {
      out.sampleAffiliateRows.push({
        tanggalKey: tglKey,
        store: store,
        orderNo: FIN_makeDailySummaryRef_('OMNI-SAMPLE', tglKey, store),
        status: 'SAMPLE_AFFILIATE',
        item: 'Sample affiliate ' + store,
        qty: '',
        nominal: sampleCost,
        akun: FIN_sampleAffiliateAccount_(),
        costStatus: 'SUMMARY_AGGREGATED',
        costSource: FIN_OMNI_DAILY_ORDER_STORE_SHEET + '.Sample_Cost',
        movementType: 'OMNI_DAILY_SAMPLE',
        source: FIN_OMNI_DAILY_ORDER_STORE_SHEET
      });
    }

    out.dateBuckets.push({
      tanggalKey: tglKey,
      store: store,
      completedSales: completedSales,
      completedUnsettledSales: completedUnsettled,
      completedCogs: salesCogs,
      inTransitCogs: transitCogsNet,
      sampleCost: sampleCost
    });
  });

  out.adminByStoreRows = FIN_mapToRows_(adminOrderDateMap).filter(function(x) {
    return FIN_toNumber_(x.nominal) !== 0;
  });
  out.receivables.sort(function(a, b) {
    return String(b.tanggalKey).localeCompare(String(a.tanggalKey)) || String(a.store).localeCompare(String(b.store));
  });
  out.outstanding = FIN_sum_(out.receivables, 'sisaTagihan');
  out.outstandingByStoreRows = Object.keys(storeOutstanding).map(function(store) {
    var value = FIN_toNumber_(storeOutstanding[store]);
    return {
      store: store,
      customer: 'Marketplace - ' + store,
      invoiceNo: 'MP-' + FIN_cleanKey_(store || 'MARKETPLACE'),
      source: 'MARKETPLACE',
      sourceSheet: FIN_OMNI_DAILY_ORDER_STORE_SHEET,
      statusPembayaran: 'BELUM CAIR',
      sisaTagihan: value,
      nilaiInvoice: value
    };
  }).sort(function(a, b) { return FIN_toNumber_(b.sisaTagihan) - FIN_toNumber_(a.sisaTagihan); });

  var productInfo = FIN_dailySummaryTable_(ss, FIN_OMNI_DAILY_ORDER_PRODUCT_SHEET, [
    'Date_Key', 'Store_Name', 'Internal_Item_Name', 'Completed_Qty', 'Completed_Sales',
    'Completed_COGS', 'In_Transit_COGS', 'Sample_Cost', 'Summary_Version'
  ]);
  if (FIN_dailySummaryVersionOk_(productInfo)) {
    (productInfo.table.rows || []).forEach(function(r) {
      var key = FIN_dateKeyFromAny_(FIN_val_(r, ['Date_Key']));
      if (!FIN_isDateKeyInRange_(key, range)) return;
      out.productRows.push({
        tanggalKey: key,
        store: FIN_storeNameClean_(FIN_val_(r, ['Store_Name'])),
        item: FIN_val_(r, ['Internal_Item_Name']),
        completedQty: FIN_toNumber_(FIN_val_(r, ['Completed_Qty'])),
        completedSales: FIN_toNumber_(FIN_val_(r, ['Completed_Sales'])),
        completedCogs: FIN_toNumber_(FIN_val_(r, ['Completed_COGS'])),
        inTransitCogs: FIN_toNumber_(FIN_val_(r, ['In_Transit_COGS'])),
        sampleCost: FIN_toNumber_(FIN_val_(r, ['Sample_Cost'])),
        source: FIN_OMNI_DAILY_ORDER_PRODUCT_SHEET
      });
    });
  }
  return out;
}

function FIN_getOmniSettlementDailyMap_(ss, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var info = FIN_dailySummaryTable_(ss, FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET, [
    'Settlement_Date_Key', 'Store_Name', 'Net_Settlement', 'Admin_Fee',
    'Service_Fee', 'Affiliate_Fee', 'Seller_Shipping', 'Summary_Version'
  ]);
  var rawSh = FIN_getSheetByCandidateNames_(ss, ['Omni_Settlement', 'Settlement_Omni', 'Settlement_OMNI', 'Settlement Omni']);
  var hasRaw = FIN_sheetHasData_(rawSh);
  var hasSummary = !!(info.table && info.table.rows && info.table.rows.length);
  var ready = FIN_dailySummaryVersionOk_(info) && (!hasRaw || hasSummary);
  var out = {
    ready: ready,
    sourceMode: 'OMNI_SETTLEMENT_DAILY_SUMMARY_V3',
    byOrder: {},
    rows: [],
    sheetName: FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET,
    missingHeaders: info.missingHeaders || [],
    versions: info.versions || [],
    summary: {
      gross: 0,
      net: 0,
      fees: 0,
      adminMarketplace: 0,
      affiliate: 0,
      ongkir: 0,
      settlementCount: 0,
      saldoByStoreRows: [],
      adminByStoreRows: [],
      affiliateByStoreRows: []
    }
  };
  if (!ready) return out;

  var saldoMap = {}, adminMap = {}, affiliateMap = {};
  (info.table.rows || []).forEach(function(r) {
    var tglKey = FIN_dateKeyFromAny_(FIN_val_(r, ['Settlement_Date_Key', 'Tanggal Key']));
    if (!FIN_isDateKeyInRange_(tglKey, range)) return;
    var store = FIN_storeNameClean_(FIN_val_(r, ['Store_Name', 'Toko', 'Store']));
    var net = FIN_toNumber_(FIN_val_(r, ['Net_Settlement']));
    var admin = FIN_toNumber_(FIN_val_(r, ['Admin_Fee']));
    var layanan = FIN_toNumber_(FIN_val_(r, ['Service_Fee']));
    var affiliate = FIN_toNumber_(FIN_val_(r, ['Affiliate_Fee']));
    var ongkir = FIN_toNumber_(FIN_val_(r, ['Seller_Shipping']));
    var gross = FIN_toNumber_(FIN_val_(r, ['Gross_Settlement'])) || (net + admin + layanan + affiliate + ongkir);
    var count = FIN_toNumber_(FIN_val_(r, ['Settlement_Count']));
    var adminMarketplace = admin + layanan;
    var saldoAcc = FIN_saldoMarketplaceAccountForStore_(store);
    var adminAcc = FIN_adminMarketplaceAccountForStore_(store);

    FIN_addAmount_(saldoMap, saldoAcc, net, {
      source: FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET + '.Net_Settlement', store: store, akun: saldoAcc, label: saldoAcc
    });
    FIN_addAmount_(adminMap, adminAcc, adminMarketplace, {
      source: FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET + '.Admin_Fee + Service_Fee', store: store, akun: adminAcc, label: adminAcc
    });
    if (affiliate) {
      FIN_addAmount_(affiliateMap, 'Affiliate ' + store, affiliate, {
        source: FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET + '.Affiliate_Fee', store: store,
        akun: 'Affiliate ' + store, label: 'Affiliate ' + store
      });
    }

    out.summary.gross += gross;
    out.summary.net += net;
    out.summary.fees += adminMarketplace;
    out.summary.adminMarketplace += adminMarketplace;
    out.summary.affiliate += affiliate;
    out.summary.ongkir += ongkir;
    out.summary.settlementCount += count;
    out.rows.push({
      tanggal: FIN_displayDate_(FIN_parseDate_(tglKey)),
      tanggalKey: tglKey,
      store: store,
      noPesanan: FIN_makeDailySummaryRef_('SETTLE', tglKey, store),
      settlementCount: count,
      gross: gross,
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
      sourceSheet: FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET
    });
  });
  out.summary.saldoByStoreRows = FIN_mapToRows_(saldoMap).filter(function(x) { return FIN_toNumber_(x.nominal) !== 0; });
  out.summary.adminByStoreRows = FIN_mapToRows_(adminMap).filter(function(x) { return FIN_toNumber_(x.nominal) !== 0; });
  out.summary.affiliateByStoreRows = FIN_mapToRows_(affiliateMap).filter(function(x) { return FIN_toNumber_(x.nominal) !== 0; });
  return out;
}

function FIN_getOmniFinanceDataDaily_(periodOrRange, journals) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var ss = FIN_getOmniSs_();
  var orderData = FIN_getOmniOrderDailyData_(ss, range);

  if (!orderData.ready) {
    var legacy = FIN_getOmniFinanceData_(range, journals || []);
    legacy.sourceMode = 'OMNI_RAW_FALLBACK';
    legacy.dailySummaryReady = false;
    legacy.dailySummaryWarning = 'Omni_Order_Daily_Store belum siap. Missing headers: ' + (orderData.missingHeaders || []).join(', ');
    legacy.dailySummaryVersions = orderData.versions || [];
    return legacy;
  }

  var settlementMap = FIN_getOmniSettlementDailyMap_(ss, range);
  var settlementFallback = false;
  if (!settlementMap.ready) {
    settlementMap = FIN_getOmniSettlementMap_(ss, range);
    settlementMap.sourceMode = 'OMNI_SETTLEMENT_RAW_FALLBACK';
    settlementMap.ready = false;
    settlementFallback = true;
  }

  var out = FIN_emptyOmniFinance_();
  out.periodKey = range.periodKey;
  out.dateStart = range.startKey;
  out.dateEnd = range.endKey;
  out.sourceMode = settlementFallback ? 'OMNI_DAILY_ORDER_RAW_SETTLEMENT_FALLBACK' : 'OMNI_DAILY_SUMMARY_V3';
  out.dailySummaryReady = !settlementFallback;
  out.dailySummaryVersions = orderData.versions || [];
  out.settlementSummaryVersions = settlementMap.versions || [];
  out.settlementSourceSheet = settlementMap.sheetName || FIN_OMNI_DAILY_SETTLEMENT_STORE_SHEET;
  out.settlements = settlementMap.rows || [];
  out.marketplaceFeeRows = orderData.marketplaceFeeRows || [];
  out.adjustments = FIN_getOmniAdjustmentRows_(ss, range);
  out.returns = FIN_getOmniReturnRows_(ss, range);

  var posData = FIN_getOmniPosReceivables_(ss, range, journals || []);
  out.receivables = (orderData.receivables || []).concat(posData.receivables || []);
  out.marketplaceSales = orderData.salesRows || [];
  out.posSales = posData.salesRows || [];
  out.omniCogsRows = orderData.omniCogsRows || [];
  out.inTransitRows = orderData.inTransitRows || [];
  out.sampleAffiliateRows = orderData.sampleAffiliateRows || [];
  out.omniProductRows = orderData.productRows || [];
  out.outstandingByStoreRows = orderData.outstandingByStoreRows || [];
  out.revenueRows = FIN_buildRevenueRowsFromInvoices_(out.receivables, range.periodKey);
  out.summary = {
    marketplaceGross: FIN_toNumber_(orderData.gross),
    marketplaceOutstanding: FIN_toNumber_(orderData.outstanding),
    marketplaceReceivableGroups: (orderData.receivables || []).length,
    marketplaceOutstandingByStoreRows: orderData.outstandingByStoreRows || [],
    marketplaceDateBuckets: orderData.dateBuckets || [],
    posGross: FIN_toNumber_(posData.gross),
    posOutstanding: FIN_toNumber_(posData.outstanding),
    settlementGross: FIN_toNumber_(settlementMap.summary && settlementMap.summary.gross),
    settlementNet: FIN_toNumber_(settlementMap.summary && settlementMap.summary.net),
    // Saldo marketplace mengikuti tanggal pencairan; biaya admin mengikuti tanggal order.
    settlementFees: FIN_toNumber_(orderData.adminMarketplace),
    settlementAdminMarketplace: FIN_toNumber_(orderData.adminMarketplace),
    adminFeeRecognitionBasis: 'ORDER_DATE',
    settlementAffiliate: FIN_toNumber_(settlementMap.summary && settlementMap.summary.affiliate),
    settlementOngkir: FIN_toNumber_(settlementMap.summary && settlementMap.summary.ongkir),
    settlementCount: FIN_toNumber_(settlementMap.summary && settlementMap.summary.settlementCount),
    saldoByStoreRows: (settlementMap.summary && settlementMap.summary.saldoByStoreRows) || [],
    adminByStoreRows: orderData.adminByStoreRows || [],
    affiliateByStoreRows: (settlementMap.summary && settlementMap.summary.affiliateByStoreRows) || [],
    adjustmentTotal: FIN_sum_(out.adjustments, 'nilai'),
    returnQty: FIN_sum_(out.returns, 'qty'),
    inTransitValue: FIN_sum_(out.inTransitRows, 'nominal'),
    sampleAffiliateValue: FIN_sum_(out.sampleAffiliateRows, 'nominal'),
    omniOrderCogs: FIN_sum_(out.omniCogsRows, 'nominal'),
    sourceRowCount: FIN_toNumber_(orderData.sourceRowCount)
  };
  return out;
}

function TEST_financeOmniDailySummaryReader(filter) {
  FIN_requireAccess_();
  var range = FIN_resolveReportRange_(filter || {});
  var data = FIN_getOmniFinanceDataDaily_(range, FIN_getJurnalRows_());
  return {
    success: true,
    version: FIN_CFG.VERSION,
    range: range,
    sourceMode: data.sourceMode,
    dailySummaryReady: data.dailySummaryReady,
    orderSummaryVersions: data.dailySummaryVersions || [],
    settlementSummaryVersions: data.settlementSummaryVersions || [],
    settlementSourceSheet: data.settlementSourceSheet || '',
    summary: data.summary,
    rowCounts: {
      marketplaceSales: (data.marketplaceSales || []).length,
      marketplaceReceivables: (data.receivables || []).filter(function(x) { return x.source === 'MARKETPLACE'; }).length,
      cogs: (data.omniCogsRows || []).length,
      inTransit: (data.inTransitRows || []).length,
      sample: (data.sampleAffiliateRows || []).length,
      marketplaceFeeOrderDate: (data.marketplaceFeeRows || []).length,
      settlement: (data.settlements || []).length,
      product: (data.omniProductRows || []).length
    },
    sample: {
      sales: (data.marketplaceSales || []).slice(0, 5),
      receivables: (data.receivables || []).filter(function(x) { return x.source === 'MARKETPLACE'; }).slice(0, 5),
      settlements: (data.settlements || []).slice(0, 5)
    }
  };
}