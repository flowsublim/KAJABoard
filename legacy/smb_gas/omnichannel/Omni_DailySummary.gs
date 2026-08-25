// =================================================================================
// ERP CV KIRAL - OMNI DAILY SUMMARY ENGINE v1.6.4
// Materialized daily summaries untuk dashboard Omni, Finance, dan akselerator PR Gudang.
// Sumber utama tetap Omni_Order / Omni_Settlement. Sheet summary hanya akselerator baca; aksi Gudang tetap validasi raw.
// =================================================================================

var OMNI_ORDER_DAILY_STORE_SHEET = 'Omni_Order_Daily_Store';
var OMNI_ORDER_DAILY_PRODUCT_SHEET = 'Omni_Order_Daily_Product';
var OMNI_SETTLEMENT_DAILY_STORE_SHEET = 'Omni_Settlement_Daily_Store';
var OMNI_SUMMARY_VERSION = 'OMNI_SUMMARY_V3_SETTLEMENT_DATEKEY_SOURCE_FIRST';
var OMNI_WAREHOUSE_SUMMARY_VERSION = 'OMNI_WAREHOUSE_SUMMARY_V1';

var OMNI_ORDER_DAILY_STORE_HEADERS = [
  'Summary_Key',
  'Group_Key',
  'Date_Key',
  'Marketplace',
  'Store_Name',
  'Order_Count',
  'Line_Count',
  'Item_Qty',
  'Gross_Sales',
  'Active_Sales',
  'Completed_Sales',
  'In_Transit_Sales',
  'Cancelled_Sales',
  'Completed_Order_Count',
  'In_Transit_Order_Count',
  'Cancelled_Order_Count',
  'Return_Order_Count',
  'COGS_Value',
  'Completed_COGS',
  'In_Transit_COGS',
  'Sample_Cost',
  'Completed_Sample_Cost',
  'In_Transit_Sample_Cost',
  'Settled_Sales',
  'Unsettled_Sales',
  'Completed_Settled_Sales',
  'Completed_Unsettled_Sales',
  'Settlement_Net',
  'Admin_Fee',
  'Service_Fee',
  'Affiliate_Fee',
  'Seller_Shipping',
  'Source_Row_Count',
  'Summary_Version',
  'Updated_At'
];

var OMNI_ORDER_DAILY_PRODUCT_HEADERS = [
  'Summary_Key',
  'Group_Key',
  'Date_Key',
  'Marketplace',
  'Store_Name',
  'Internal_Item_Name',
  'Order_Count',
  'Line_Count',
  'Item_Qty',
  'Gross_Sales',
  'Completed_Qty',
  'Completed_Sales',
  'In_Transit_Qty',
  'In_Transit_Sales',
  'COGS_Value',
  'Completed_COGS',
  'In_Transit_COGS',
  'Sample_Qty',
  'Sample_Cost',
  'Source_Row_Count',
  'Summary_Version',
  'Updated_At',
  'Warehouse_Demand_Qty',
  'Warehouse_Normal_Qty',
  'Warehouse_Cancel_Qty',
  'Warehouse_Order_Count',
  'Warehouse_Normal_Order_Count',
  'Warehouse_Cancel_Order_Count',
  'Warehouse_Mapping_Type',
  'Warehouse_Summary_Version'
];

var OMNI_SETTLEMENT_DAILY_STORE_HEADERS = [
  'Summary_Key',
  'Group_Key',
  'Settlement_Date_Key',
  'Marketplace',
  'Store_Name',
  'Settlement_Count',
  'Gross_Settlement',
  'Net_Settlement',
  'Admin_Fee',
  'Service_Fee',
  'Affiliate_Fee',
  'Seller_Shipping',
  'Source_Row_Count',
  'Summary_Version',
  'Updated_At'
];

function SETUP_installOmniDailySummary(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'SETUP_installOmniDailySummary');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success:false, error:'Server sibuk. Coba lagi.' }; }
  try {
    var ss = getActiveOmni_();
    ensureSheetWithHeaders_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
    OMNI_ensureDailySummarySheets_(ss);
    OMNI_prepareDateKeyColumns_(ss);
    var result = OMNI_rebuildAllDailySummary_();
    result.setup = true;
    return result;
  } catch (e) {
    logError_('SETUP_installOmniDailySummary', e, {});
    return { success:false, error:e.message || String(e) };
  } finally {
    lock.releaseLock();
  }
}

function OMNI_rebuildAllDailySummary(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'OMNI_rebuildAllDailySummary');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success:false, error:'Server sibuk. Coba lagi.' }; }
  try {
    return OMNI_rebuildAllDailySummary_();
  } catch (e) {
    logError_('OMNI_rebuildAllDailySummary', e, {});
    return { success:false, error:e.message || String(e) };
  } finally {
    lock.releaseLock();
  }
}

function OMNI_rebuildOrderDailySummary(dateFrom, dateTo, storeName, emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'OMNI_rebuildOrderDailySummary');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success:false, error:'Server sibuk. Coba lagi.' }; }
  try {
    var groups = OMNI_buildGroupFilter_(dateFrom, dateTo, storeName);
    return OMNI_rebuildOrderDailySummary_(groups);
  } catch (e) {
    logError_('OMNI_rebuildOrderDailySummary', e, { dateFrom:dateFrom, dateTo:dateTo, storeName:storeName });
    return { success:false, error:e.message || String(e) };
  } finally {
    lock.releaseLock();
  }
}

function OMNI_rebuildSettlementDailySummary(dateFrom, dateTo, storeName, emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'OMNI_rebuildSettlementDailySummary');
  var lock = LockService.getScriptLock();
  try { lock.waitLock(30000); } catch (e) { return { success:false, error:'Server sibuk. Coba lagi.' }; }
  try {
    var groups = OMNI_buildGroupFilter_(dateFrom, dateTo, storeName);
    return OMNI_rebuildSettlementDailySummary_(groups);
  } catch (e) {
    logError_('OMNI_rebuildSettlementDailySummary', e, { dateFrom:dateFrom, dateTo:dateTo, storeName:storeName });
    return { success:false, error:e.message || String(e) };
  } finally {
    lock.releaseLock();
  }
}

function TEST_omniDailySummary(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniDailySummary');
  var ss = getActiveOmni_();
  OMNI_ensureDailySummarySheets_(ss);
  var rawOrder = readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
  var rawSettlement = readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  var orderStore = readTable_(ss, OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS);
  var orderProduct = readTable_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
  var settlementStore = readTable_(ss, OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS);
  var out = {
    success:true,
    version:OMNI_SUMMARY_VERSION,
    source:{ orderRows:rawOrder.rows.length, settlementRows:rawSettlement.rows.length },
    summary:{ orderStoreRows:orderStore.rows.length, orderProductRows:orderProduct.rows.length, settlementStoreRows:settlementStore.rows.length },
    ready:(rawOrder.rows.length === 0 || orderStore.rows.length > 0) && (rawSettlement.rows.length === 0 || settlementStore.rows.length > 0)
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

function OMNI_ensureDailySummarySheets_(ss) {
  ss = ss || getActiveOmni_();
  var shStore = ensureSheetWithHeaders_(ss, OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS);
  var shProduct = ensureSheetWithHeaders_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
  var shSettlement = ensureSheetWithHeaders_(ss, OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS);
  OMNI_setPlainTextColumnByHeader_(shStore, ['Date_Key']);
  OMNI_setPlainTextColumnByHeader_(shProduct, ['Date_Key']);
  OMNI_setPlainTextColumnByHeader_(shSettlement, ['Settlement_Date_Key']);
}

function OMNI_rebuildAllDailySummary_() {
  var started = new Date().getTime();
  var ss = getActiveOmni_();
  OMNI_ensureDailySummarySheets_(ss);
  var order = OMNI_rebuildOrderDailySummary_(null);
  var settlement = OMNI_rebuildSettlementDailySummary_(null);
  SpreadsheetApp.flush();
  cacheRemove_('OMNI_DAILY_SUMMARY_READY');
  cachePut_('OMNI_DAILY_SUMMARY_READY', { ready:true, at:nowText_() }, 21600);
  OMNI_touchMutation_('OMNI_rebuildAllDailySummary');
  return {
    success:!!(order.success && settlement.success),
    order:order,
    settlement:settlement,
    ms:new Date().getTime() - started
  };
}

function OMNI_rebuildOrderDailySummary_(groupFilter, sourceTable, context) {
  var ss = getActiveOmni_();
  OMNI_ensureDailySummarySheets_(ss);
  var built = OMNI_buildOrderDailyRows_(groupFilter, sourceTable, context);
  OMNI_replaceSummaryRows_(ss.getSheetByName(OMNI_ORDER_DAILY_STORE_SHEET), OMNI_ORDER_DAILY_STORE_HEADERS, built.storeRows, groupFilter);
  OMNI_replaceSummaryRows_(ss.getSheetByName(OMNI_ORDER_DAILY_PRODUCT_SHEET), OMNI_ORDER_DAILY_PRODUCT_HEADERS, built.productRows, groupFilter);
  return {
    success:true,
    groups:built.groupCount,
    orderStoreRows:built.storeRows.length,
    orderProductRows:built.productRows.length,
    sourceRows:built.sourceRows
  };
}

function OMNI_rebuildSettlementDailySummary_(groupFilter) {
  var ss = getActiveOmni_();
  OMNI_ensureDailySummarySheets_(ss);
  var built = OMNI_buildSettlementDailyRows_(groupFilter);
  OMNI_replaceSummaryRows_(ss.getSheetByName(OMNI_SETTLEMENT_DAILY_STORE_SHEET), OMNI_SETTLEMENT_DAILY_STORE_HEADERS, built.rows, groupFilter);
  return { success:true, groups:built.groupCount, rows:built.rows.length, sourceRows:built.sourceRows };
}


function OMNI_getWarehouseTargetTypeMap_(skuMap) {
  skuMap = skuMap || getSkuMap_();
  var out = {};
  Object.keys(skuMap || {}).forEach(function(k) {
    if (k.indexOf('__') === 0) return;
    var m = skuMap[k];
    if (!m || !m.item) return;
    var itemKey = normalize_(m.item);
    if (!itemKey) return;
    var type = String(m.mapType || 'UNKNOWN').toUpperCase();
    var current = out[itemKey] || '';
    if (type === 'SUB_CATEGORY' || type === 'BUNDLE' || type === 'PAKET') out[itemKey] = 'SUB_CATEGORY';
    else if (!current && type === 'ITEM') out[itemKey] = 'ITEM';
    else if (!current) out[itemKey] = type;
  });
  return out;
}

function OMNI_buildOrderDailyRows_(groupFilter, sourceTable, context) {
  var ss = getActiveOmni_();
  var t = sourceTable || readTable_(ss, OMNI_SHEET, OMNI_HEADERS);
  context = context || {};
  if (!t.sheet || !t.rows.length) return { storeRows:[], productRows:[], groupCount:0, sourceRows:0 };

  var info = t.info;
  var cDateKey = col_(info, ['Tanggal Key'], -1);
  var cDateRaw = col_(info, ['Tanggal'], -1);
  var cStore = col_(info, ['Toko'], -1);
  var cNo = col_(info, ['No Pesanan'], -1);
  var cStatus = col_(info, ['Status'], -1);
  var cItem = col_(info, ['Item Gudang','Internal_Item_Name'], -1);
  var cQty = col_(info, ['Qty','Qty Gudang'], -1);
  var cTotal = col_(info, ['Total','Subtotal'], -1);
  var cCogs = col_(info, ['COGS_Value'], -1);
  var cBucket = col_(info, ['Finance_Bucket'], -1);
  var cSet = col_(info, ['Settlement Status'], -1);
  var cDel = col_(info, ['Is_Deleted'], -1);

  var dateOrientationSample = [];
  if (cDateRaw !== -1) {
    for (var ds = 0; ds < t.rows.length && dateOrientationSample.length < 500; ds++) {
      if (t.rows[ds][cDateRaw] !== '' && t.rows[ds][cDateRaw] !== null && t.rows[ds][cDateRaw] !== undefined) {
        dateOrientationSample.push(t.rows[ds][cDateRaw]);
      }
    }
  }
  var orderDateOrientation = OMNI_inferDateOrder_(dateOrientationSample, 'DMY');
  var storeMap = context.storeMap || getStoreMap_();
  var warehouseTypeMap = context.warehouseTypeMap || OMNI_getWarehouseTargetTypeMap_(context.skuMap || null);
  var returSet = getReturOrderSet_();
  var settlementMap = getSettlementMap_();
  var orders = {};
  var products = {};
  var sourceRows = 0;

  t.rows.forEach(function(r) {
    if (isDeletedRow_(r, cDel)) return;
    var dateKey = OMNI_canonicalKeyFromSource_(cDateKey !== -1 ? r[cDateKey] : '', cDateRaw !== -1 ? r[cDateRaw] : '', orderDateOrientation.order);
    var store = cStore !== -1 ? String(r[cStore] || '').trim() : '';
    if (!dateKey || !store) return;
    var groupKey = OMNI_summaryGroupKey_(dateKey, store);
    if (!OMNI_groupFilterMatch_(groupFilter, groupKey, dateKey, store)) return;
    sourceRows++;

    var no = cNo !== -1 ? String(r[cNo] || '').trim() : '';
    var statusRaw = cStatus !== -1 ? String(r[cStatus] || '') : '';
    var item = cItem !== -1 ? String(r[cItem] || '').trim() : '';
    var qty = cQty !== -1 ? toNumber_(r[cQty]) : 0;
    var total = cTotal !== -1 ? toNumber_(r[cTotal]) : 0;
    var cogs = cCogs !== -1 ? toNumber_(r[cCogs]) : 0;
    var bucket = cBucket !== -1 ? String(r[cBucket] || '').toUpperCase().trim() : '';
    var settlementStatus = cSet !== -1 ? String(r[cSet] || '') : '';
    var platform = OMNI_marketplaceForStore_(storeMap, store);
    var orderKey = groupKey + '|' + normalize_(no || ('ROW-' + sourceRows));

    if (!orders[orderKey]) {
      orders[orderKey] = {
        groupKey:groupKey,
        dateKey:dateKey,
        store:store,
        platform:platform,
        no:no,
        status:statusRaw,
        lineCount:0,
        qty:0,
        total:0,
        cogs:0,
        sampleCost:0,
        settledStatus:settlementStatus,
        items:{}
      };
    }
    var o = orders[orderKey];
    if (statusRaw) o.status = statusRaw;
    if (settlementStatus) o.settledStatus = settlementStatus;
    o.lineCount++;
    o.qty += qty;
    o.total += total;
    o.cogs += cogs;
    if (bucket === 'SAMPLE_AFFILIATE') o.sampleCost += cogs;

    if (item && item.toUpperCase() !== 'UNMAPPED') {
      var productKey = groupKey + '|' + normalize_(item);
      if (!products[productKey]) {
        products[productKey] = {
          summaryKey:OMNI_summaryProductKey_(dateKey, store, item),
          groupKey:groupKey,
          dateKey:dateKey,
          platform:platform,
          store:store,
          item:item,
          activeOrderSet:{},
          warehouseOrderSet:{},
          warehouseNormalOrderSet:{},
          warehouseCancelOrderSet:{},
          warehouseMappingType:warehouseTypeMap[normalize_(item)] || classifyMappingTarget_(item, '') || 'UNKNOWN',
          lineCount:0,
          qty:0,
          warehouseNormalQty:0,
          warehouseCancelQty:0,
          sales:0,
          completedQty:0,
          completedSales:0,
          transitQty:0,
          transitSales:0,
          cogs:0,
          completedCogs:0,
          transitCogs:0,
          sampleQty:0,
          sampleCost:0,
          sourceRowCount:0
        };
      }
      var p = products[productKey];
      p.lineCount++;
      p.sourceRowCount++;
      p._rows = p._rows || [];
      p._rows.push({ qty:qty, total:total, cogs:cogs, bucket:bucket, status:statusRaw, no:no });
    }
  });

  var storeAgg = {};
  Object.keys(orders).forEach(function(k) {
    var o = orders[k];
    var isReturn = !!(o.no && returSet[o.no]);
    var isCancel = isCanceledStatus_(o.status) || isReturn;
    var isCompleted = isCompletedStatus_(o.status) && !isCancel;
    var isTransit = isShippedStatus_(o.status) && !isCancel;
    var settledObj = o.no ? settlementMap[o.store + '|' + o.no] : null;
    var isSettled = !!settledObj || normalize_(o.settledStatus).indexOf('sudah') === 0;

    if (!storeAgg[o.groupKey]) {
      storeAgg[o.groupKey] = {
        summaryKey:o.groupKey,
        groupKey:o.groupKey,
        dateKey:o.dateKey,
        platform:o.platform,
        store:o.store,
        orderCount:0,
        lineCount:0,
        qty:0,
        gross:0,
        active:0,
        completed:0,
        transit:0,
        cancelled:0,
        completedCount:0,
        transitCount:0,
        cancelledCount:0,
        returnCount:0,
        cogs:0,
        completedCogs:0,
        transitCogs:0,
        sampleCost:0,
        completedSampleCost:0,
        transitSampleCost:0,
        settledSales:0,
        unsettledSales:0,
        completedSettledSales:0,
        completedUnsettledSales:0,
        settlementNet:0,
        admin:0,
        service:0,
        affiliate:0,
        shipping:0,
        sourceRowCount:0
      };
    }
    var s = storeAgg[o.groupKey];
    s.orderCount++;
    s.lineCount += o.lineCount;
    s.sourceRowCount += o.lineCount;
    s.gross += o.total;
    if (isCancel) {
      s.cancelled += o.total;
      s.cancelledCount++;
      if (isReturn) s.returnCount++;
    } else {
      s.active += o.total;
      s.qty += o.qty;
      s.cogs += o.cogs;
      s.sampleCost += o.sampleCost;
      if (isCompleted) {
        s.completed += o.total;
        s.completedCount++;
        s.completedCogs += o.cogs;
        s.completedSampleCost += o.sampleCost;
      }
      if (isTransit) {
        s.transit += o.total;
        s.transitCount++;
        s.transitCogs += o.cogs;
        s.transitSampleCost += o.sampleCost;
      }
      if (isSettled) {
        s.settledSales += o.total;
        if (isCompleted) s.completedSettledSales += o.total;
      } else {
        s.unsettledSales += o.total;
        if (isCompleted) s.completedUnsettledSales += o.total;
      }
      if (settledObj) {
        s.settlementNet += toNumber_(settledObj.bersih);
        s.admin += toNumber_(settledObj.admin);
        s.service += toNumber_(settledObj.layanan);
        s.affiliate += toNumber_(settledObj.affiliate);
        s.shipping += toNumber_(settledObj.ongkir);
      }
    }
  });

  Object.keys(products).forEach(function(k) {
    var p = products[k];
    (p._rows || []).forEach(function(x) {
      var isReturn = !!(x.no && returSet[x.no]);
      var isFinanceCancel = isCanceledStatus_(x.status) || isReturn;
      // Gudang lama hanya melihat status pada Omni_Order; keberadaan row di Omni_Retur tidak otomatis mengubah PR.
      var isWarehouseCancel = isCancelLikeStatus_(x.status);

      // Kontrak Gudang hanya menghitung baris yang punya nomor pesanan, sama seperti reader raw Gudang.
      if (x.no) {
        if (!p.warehouseOrderSet[x.no]) {
          p.warehouseOrderSet[x.no] = true;
          if (isWarehouseCancel) p.warehouseCancelOrderSet[x.no] = true;
          else p.warehouseNormalOrderSet[x.no] = true;
        }
        if (isWarehouseCancel) p.warehouseCancelQty += x.qty;
        else p.warehouseNormalQty += x.qty;
      }

      // Kolom Finance lama tetap memakai aturan retur Finance; tidak diubah.
      if (isFinanceCancel) return;
      var isCompleted = isCompletedStatus_(x.status);
      var isTransit = isShippedStatus_(x.status);
      p.activeOrderSet[x.no || (p.groupKey + '|' + p.item + '|' + p.sourceRowCount)] = true;
      p.qty += x.qty;
      p.sales += x.total;
      p.cogs += x.cogs;
      if (isCompleted) {
        p.completedQty += x.qty;
        p.completedSales += x.total;
        p.completedCogs += x.cogs;
      } else if (isTransit) {
        p.transitQty += x.qty;
        p.transitSales += x.total;
        p.transitCogs += x.cogs;
      }
      if (x.bucket === 'SAMPLE_AFFILIATE') { p.sampleQty += x.qty; p.sampleCost += x.cogs; }
    });
    delete p._rows;
  });

  var updatedAt = nowText_();
  var storeRows = Object.keys(storeAgg).sort().map(function(k) {
    var x = storeAgg[k];
    return OMNI_objectToHeaderRow_(OMNI_ORDER_DAILY_STORE_HEADERS, {
      Summary_Key:x.summaryKey, Group_Key:x.groupKey, Date_Key:x.dateKey, Marketplace:x.platform, Store_Name:x.store,
      Order_Count:x.orderCount, Line_Count:x.lineCount, Item_Qty:x.qty, Gross_Sales:x.gross, Active_Sales:x.active,
      Completed_Sales:x.completed, In_Transit_Sales:x.transit, Cancelled_Sales:x.cancelled,
      Completed_Order_Count:x.completedCount, In_Transit_Order_Count:x.transitCount, Cancelled_Order_Count:x.cancelledCount,
      Return_Order_Count:x.returnCount, COGS_Value:x.cogs, Completed_COGS:x.completedCogs, In_Transit_COGS:x.transitCogs,
      Sample_Cost:x.sampleCost, Completed_Sample_Cost:x.completedSampleCost, In_Transit_Sample_Cost:x.transitSampleCost,
      Settled_Sales:x.settledSales, Unsettled_Sales:x.unsettledSales,
      Completed_Settled_Sales:x.completedSettledSales, Completed_Unsettled_Sales:x.completedUnsettledSales,
      Settlement_Net:x.settlementNet, Admin_Fee:x.admin, Service_Fee:x.service,
      Affiliate_Fee:x.affiliate, Seller_Shipping:x.shipping, Source_Row_Count:x.sourceRowCount,
      Summary_Version:OMNI_SUMMARY_VERSION, Updated_At:updatedAt
    });
  });

  var productRows = Object.keys(products).sort().map(function(k) {
    var x = products[k];
    var warehouseMappingType = String(x.warehouseMappingType || classifyMappingTarget_(x.item, '') || 'UNKNOWN').toUpperCase();
    if (warehouseMappingType === 'BUNDLE' || warehouseMappingType === 'PAKET') warehouseMappingType = 'SUB_CATEGORY';
    return OMNI_objectToHeaderRow_(OMNI_ORDER_DAILY_PRODUCT_HEADERS, {
      Summary_Key:x.summaryKey, Group_Key:x.groupKey, Date_Key:x.dateKey, Marketplace:x.platform, Store_Name:x.store,
      Internal_Item_Name:x.item, Order_Count:Object.keys(x.activeOrderSet).length, Line_Count:x.lineCount, Item_Qty:x.qty,
      Gross_Sales:x.sales, Completed_Qty:x.completedQty, Completed_Sales:x.completedSales,
      In_Transit_Qty:x.transitQty, In_Transit_Sales:x.transitSales, COGS_Value:x.cogs,
      Completed_COGS:x.completedCogs, In_Transit_COGS:x.transitCogs,
      Sample_Qty:x.sampleQty, Sample_Cost:x.sampleCost, Source_Row_Count:x.sourceRowCount,
      Warehouse_Demand_Qty:x.warehouseNormalQty + x.warehouseCancelQty,
      Warehouse_Normal_Qty:x.warehouseNormalQty,
      Warehouse_Cancel_Qty:x.warehouseCancelQty,
      Warehouse_Order_Count:Object.keys(x.warehouseOrderSet || {}).length,
      Warehouse_Normal_Order_Count:Object.keys(x.warehouseNormalOrderSet || {}).length,
      Warehouse_Cancel_Order_Count:Object.keys(x.warehouseCancelOrderSet || {}).length,
      Warehouse_Mapping_Type:warehouseMappingType, Warehouse_Summary_Version:OMNI_WAREHOUSE_SUMMARY_VERSION,
      Summary_Version:OMNI_SUMMARY_VERSION, Updated_At:updatedAt
    });
  });

  return { storeRows:storeRows, productRows:productRows, groupCount:Object.keys(storeAgg).length, sourceRows:sourceRows };
}


function TEST_omniTransitStatusRule(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniTransitStatusRule');
  var cases = [
    { status:'Sudah Dikirim', expected:true },
    { status:'  SUDAH   DIKIRIM  ', expected:true },
    { status:'Menunggu Diproses', expected:false },
    { status:'Siap Dikirim', expected:false },
    { status:'Menunggu Pickup', expected:false },
    { status:'Selesai', expected:false },
    { status:'Batal', expected:false }
  ].map(function(x) {
    var actual = isShippedStatus_(x.status);
    return { status:x.status, expected:x.expected, actual:actual, pass:actual === x.expected };
  });
  return {
    success: cases.every(function(x){ return x.pass; }),
    version: OMNI_CFG.VERSION,
    recognizedTransitStatus: 'Sudah Dikirim',
    cases: cases
  };
}

function TEST_omniWarehouseSummaryContract(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniWarehouseSummaryContract');
  var ss = getActiveOmni_();
  OMNI_ensureDailySummarySheets_(ss);
  var t = readTable_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
  var required = [
    'Date_Key','Store_Name','Internal_Item_Name','Warehouse_Demand_Qty','Warehouse_Normal_Qty',
    'Warehouse_Cancel_Qty','Warehouse_Order_Count','Warehouse_Normal_Order_Count','Warehouse_Cancel_Order_Count',
    'Warehouse_Mapping_Type','Warehouse_Summary_Version','Summary_Version'
  ];
  var missing = required.filter(function(h) { return col_(t.info, [h], -1) === -1; });
  var cVersion = col_(t.info, ['Warehouse_Summary_Version'], -1);
  var cDemand = col_(t.info, ['Warehouse_Demand_Qty'], -1);
  var cNormal = col_(t.info, ['Warehouse_Normal_Qty'], -1);
  var cCancel = col_(t.info, ['Warehouse_Cancel_Qty'], -1);
  var mismatch = 0;
  var versionMismatch = 0;
  t.rows.forEach(function(r) {
    if (Math.abs(toNumber_(r[cDemand]) - (toNumber_(r[cNormal]) + toNumber_(r[cCancel]))) > 0.000001) mismatch++;
    if (cVersion !== -1 && String(r[cVersion] || '') && String(r[cVersion] || '') !== OMNI_WAREHOUSE_SUMMARY_VERSION) versionMismatch++;
  });
  var out = {
    success: missing.length === 0 && mismatch === 0 && versionMismatch === 0,
    version: OMNI_WAREHOUSE_SUMMARY_VERSION,
    rows: t.rows.length,
    missingHeaders: missing,
    qtyMismatchRows: mismatch,
    versionMismatchRows: versionMismatch,
    contract: 'PR Gudang membaca summary; Pack/Tidak Pack tetap validasi Omni_Order raw.'
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

function OMNI_buildSettlementDailyRows_(groupFilter) {
  var ss = getActiveOmni_();
  var t = readTable_(ss, SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  if (!t.sheet || !t.rows.length) return { rows:[], groupCount:0, sourceRows:0 };
  var info = t.info;
  var cDateKey = col_(info, ['Tgl Pencairan Key'], -1);
  var cDateRaw = col_(info, ['Tgl Pencairan'], -1);
  var cStore = col_(info, ['Toko'], -1);
  var cNo = col_(info, ['No Pesanan'], -1);
  var cNet = col_(info, ['Pendapatan Bersih'], -1);
  var cAdmin = col_(info, ['Biaya Admin'], -1);
  var cService = col_(info, ['Biaya Layanan'], -1);
  var cAffiliate = col_(info, ['Komisi Affiliate'], -1);
  var cShipping = col_(info, ['Ongkir Penjual'], -1);
  var settlementDateOrientation = OMNI_inferDateOrder_(t.rows.map(function(r) { return cDateRaw !== -1 ? r[cDateRaw] : ''; }), 'DMY');
  var storeMap = getStoreMap_();
  var agg = {};
  var sourceRows = 0;

  t.rows.forEach(function(r) {
    var dateKey = OMNI_settlementDateKeyFromRow_(cDateRaw !== -1 ? r[cDateRaw] : '', cDateKey !== -1 ? r[cDateKey] : '');
    var store = cStore !== -1 ? String(r[cStore] || '').trim() : '';
    if (!dateKey || !store) return;
    var groupKey = OMNI_summaryGroupKey_(dateKey, store);
    if (!OMNI_groupFilterMatch_(groupFilter, groupKey, dateKey, store)) return;
    sourceRows++;
    if (!agg[groupKey]) {
      agg[groupKey] = {
        summaryKey:groupKey, groupKey:groupKey, dateKey:dateKey,
        platform:OMNI_marketplaceForStore_(storeMap, store), store:store,
        orderSet:{}, count:0, gross:0, net:0, admin:0, service:0, affiliate:0, shipping:0, sourceRowCount:0
      };
    }
    var x = agg[groupKey];
    var no = cNo !== -1 ? String(r[cNo] || '').trim() : '';
    if (no) x.orderSet[no] = true;
    x.count++;
    x.sourceRowCount++;
    var net = cNet !== -1 ? toNumber_(r[cNet]) : 0;
    var admin = cAdmin !== -1 ? toNumber_(r[cAdmin]) : 0;
    var service = cService !== -1 ? toNumber_(r[cService]) : 0;
    var affiliate = cAffiliate !== -1 ? toNumber_(r[cAffiliate]) : 0;
    var shipping = cShipping !== -1 ? toNumber_(r[cShipping]) : 0;
    x.net += net;
    x.admin += admin;
    x.service += service;
    x.affiliate += affiliate;
    x.shipping += shipping;
    x.gross += net + admin + service + affiliate + shipping;
  });

  var updatedAt = nowText_();
  var rows = Object.keys(agg).sort().map(function(k) {
    var x = agg[k];
    return OMNI_objectToHeaderRow_(OMNI_SETTLEMENT_DAILY_STORE_HEADERS, {
      Summary_Key:x.summaryKey, Group_Key:x.groupKey, Settlement_Date_Key:x.dateKey, Marketplace:x.platform,
      Store_Name:x.store, Settlement_Count:Object.keys(x.orderSet).length || x.count, Gross_Settlement:x.gross,
      Net_Settlement:x.net, Admin_Fee:x.admin, Service_Fee:x.service, Affiliate_Fee:x.affiliate,
      Seller_Shipping:x.shipping, Source_Row_Count:x.sourceRowCount, Summary_Version:OMNI_SUMMARY_VERSION, Updated_At:updatedAt
    });
  });
  return { rows:rows, groupCount:Object.keys(agg).length, sourceRows:sourceRows };
}

function OMNI_replaceSummaryRows_(sheet, headers, newRows, groupFilter) {
  if (!sheet) throw new Error('Sheet summary tidak ditemukan.');
  var width = headers.length;
  newRows = (newRows || []).map(function(r) { return r.slice(0, width); });

  // Full rebuild manual/repair: tetap rapikan seluruh sheet.
  if (!groupFilter) {
    newRows.sort(function(a, b) { return String(a[0] || '').localeCompare(String(b[0] || '')); });
    var fullLastRow = sheet.getLastRow();
    if (fullLastRow > 1) sheet.getRange(2, 1, fullLastRow - 1, Math.max(sheet.getLastColumn(), width)).clearContent();
    if (newRows.length) sheet.getRange(2, 1, newRows.length, width).setValues(newRows);
    return;
  }

  // Incremental rebuild: hanya timpa/bersihkan row milik group yang terdampak.
  // Ini menghindari clear + rewrite seluruh summary setiap upload status.
  var t = readTable_(sheet.getParent(), sheet.getName(), headers);
  var cGroup = col_(t.info, ['Group_Key'], -1);
  var slots = [];
  t.rows.forEach(function(r, idx) {
    var groupKey = cGroup !== -1 ? String(r[cGroup] || '') : '';
    if (OMNI_groupFilterMatchByKey_(groupFilter, groupKey)) slots.push(idx + 2);
  });

  newRows.sort(function(a, b) { return String(a[0] || '').localeCompare(String(b[0] || '')); });
  var reuse = Math.min(slots.length, newRows.length);
  var updates = [];
  for (var i = 0; i < reuse; i++) {
    updates.push({ rowNumber: slots[i], row: newRows[i] });
  }
  if (updates.length) writeChangedRows_(sheet, updates, width);

  if (newRows.length > reuse) {
    appendRowsChunked_(sheet, newRows.slice(reuse), width);
  }

  if (slots.length > reuse) {
    OMNI_clearSummaryRowNumbers_(sheet, slots.slice(reuse), width);
  }
}

function OMNI_clearSummaryRowNumbers_(sheet, rowNumbers, width) {
  if (!rowNumbers || !rowNumbers.length) return;
  rowNumbers.sort(function(a, b) { return a - b; });
  var start = rowNumbers[0];
  var last = start;
  for (var i = 1; i <= rowNumbers.length; i++) {
    var current = i < rowNumbers.length ? rowNumbers[i] : null;
    if (current !== null && current === last + 1) {
      last = current;
      continue;
    }
    sheet.getRange(start, 1, last - start + 1, width).clearContent();
    if (current !== null) {
      start = current;
      last = current;
    }
  }
}

function OMNI_readOrderDailyStore_(startStr, endStr) {
  OMNI_ensureSummaryReady_();
  var t = readTable_(getActiveOmni_(), OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS);
  return OMNI_filterSummaryByDate_(t, ['Date_Key'], startStr, endStr);
}

function OMNI_readOrderDailyProduct_(startStr, endStr) {
  OMNI_ensureSummaryReady_();
  var t = readTable_(getActiveOmni_(), OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
  return OMNI_filterSummaryByDate_(t, ['Date_Key'], startStr, endStr);
}

function OMNI_readSettlementDailyStore_(startStr, endStr) {
  OMNI_ensureSummaryReady_();
  var t = readTable_(getActiveOmni_(), OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS);
  return OMNI_filterSummaryByDate_(t, ['Settlement_Date_Key'], startStr, endStr);
}

function OMNI_ensureSummaryReady_() {
  var cached = cacheGet_('OMNI_DAILY_SUMMARY_READY');
  if (cached && cached.ready) return;
  var ss = getActiveOmni_();
  OMNI_ensureDailySummarySheets_(ss);
  var rawOrder = ss.getSheetByName(OMNI_SHEET);
  var sumOrder = ss.getSheetByName(OMNI_ORDER_DAILY_STORE_SHEET);
  var rawSettlement = ss.getSheetByName(SETTLEMENT_SHEET);
  var sumSettlement = ss.getSheetByName(OMNI_SETTLEMENT_DAILY_STORE_SHEET);
  var needOrder = rawOrder && rawOrder.getLastRow() > 1 && (!sumOrder || sumOrder.getLastRow() <= 1);
  var needSettlement = rawSettlement && rawSettlement.getLastRow() > 1 && (!sumSettlement || sumSettlement.getLastRow() <= 1);
  if (needOrder) OMNI_rebuildOrderDailySummary_(null);
  if (needSettlement) OMNI_rebuildSettlementDailySummary_(null);
  cachePut_('OMNI_DAILY_SUMMARY_READY', { ready:true, at:nowText_() }, 21600);
}

function OMNI_filterSummaryByDate_(table, dateAliases, startStr, endStr) {
  if (!table || !table.sheet) return { rows:[], info:null };
  var startKey = OMNI_dateKeyStrict_(startStr, 'DMY');
  var endKey = OMNI_dateKeyStrict_(endStr || startStr, 'DMY');
  var cDate = col_(table.info, dateAliases, -1);
  var rows = table.rows.filter(function(r) {
    var key = OMNI_dateKeyStrict_(cDate !== -1 ? r[cDate] : '', 'DMY');
    return key && (!startKey || key >= startKey) && (!endKey || key <= endKey);
  });
  return { rows:rows, info:table.info };
}

function OMNI_collectOrderGroupsFromPayload_(rows) {
  var out = {};
  (rows || []).forEach(function(p) {
    var dateKey = OMNI_dateKeyStrict_(p.tglKey || p.Tanggal_Key || p.tgl || p.Tanggal || p.date || p.Date || '', p.dateOrder || 'DMY');
    var storeRaw = p.toko || p.Toko || p.store || p.Store || '';
    var store = resolveStoreName_(storeRaw);
    if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  });
  return out;
}

function OMNI_collectSettlementGroupsFromPayload_(rows) {
  var out = {};
  (rows || []).forEach(function(p) {
    var dateKey = OMNI_settlementDateKeyFromPayload_(p);
    var store = String(p.toko || p.Toko || p.store || '').trim();
    if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  });
  return out;
}

function OMNI_collectOrderGroupsForOrderKeys_(rows) {
  var wanted = {};
  (rows || []).forEach(function(p) {
    var store = String(p.toko || p.Toko || '').trim();
    var no = String(p.no || p['No Pesanan'] || p.noPesanan || '').trim();
    if (store && no) wanted[store + '|' + no] = true;
  });
  return OMNI_findOrderGroupsByStoreOrderMap_(wanted);
}

function OMNI_collectOrderGroupsForOrderNumbers_(orderNumbers) {
  var wantedNo = {};
  (orderNumbers || []).forEach(function(no) { no = String(no || '').trim(); if (no) wantedNo[no] = true; });
  if (!Object.keys(wantedNo).length) return {};
  var t = readTable_(getActiveOmni_(), OMNI_SHEET, OMNI_HEADERS);
  var out = {};
  if (!t.sheet) return out;
  var cDate = col_(t.info, ['Tanggal Key','Tanggal'], -1);
  var cStore = col_(t.info, ['Toko'], -1);
  var cNo = col_(t.info, ['No Pesanan'], -1);
  t.rows.forEach(function(r) {
    var no = cNo !== -1 ? String(r[cNo] || '').trim() : '';
    if (!wantedNo[no]) return;
    var dateKey = OMNI_dateKeyFromAny_(cDate !== -1 ? r[cDate] : '');
    var store = cStore !== -1 ? String(r[cStore] || '').trim() : '';
    if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  });
  return out;
}

function OMNI_findOrderGroupsByStoreOrderMap_(wanted) {
  var out = {};
  if (!wanted || !Object.keys(wanted).length) return out;
  var t = readTable_(getActiveOmni_(), OMNI_SHEET, OMNI_HEADERS);
  if (!t.sheet) return out;
  var cDate = col_(t.info, ['Tanggal Key','Tanggal'], -1);
  var cStore = col_(t.info, ['Toko'], -1);
  var cNo = col_(t.info, ['No Pesanan'], -1);
  t.rows.forEach(function(r) {
    var store = cStore !== -1 ? String(r[cStore] || '').trim() : '';
    var no = cNo !== -1 ? String(r[cNo] || '').trim() : '';
    if (!wanted[store + '|' + no]) return;
    var dateKey = OMNI_dateKeyFromAny_(cDate !== -1 ? r[cDate] : '');
    if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  });
  return out;
}

function OMNI_mergeGroupFilters_() {
  var out = {};
  for (var i = 0; i < arguments.length; i++) {
    var x = arguments[i] || {};
    Object.keys(x).forEach(function(k) { out[k] = true; });
  }
  return out;
}

function OMNI_buildGroupFilter_(dateFrom, dateTo, storeName) {
  var start = dateFrom ? OMNI_dateKeyFromAny_(dateFrom) : '';
  var end = dateTo ? OMNI_dateKeyFromAny_(dateTo) : start;
  if (!start && !end && !storeName) return null;
  return { __range:true, start:start || '0000-00-00', end:end || '9999-99-99', store:normalize_(storeName || '') };
}

function OMNI_groupFilterMatch_(filter, groupKey, dateKey, store) {
  if (!filter) return true;
  if (filter.__range) {
    if (dateKey < filter.start || dateKey > filter.end) return false;
    if (filter.store && normalize_(store) !== filter.store) return false;
    return true;
  }
  return !!filter[groupKey];
}

function OMNI_groupFilterMatchByKey_(filter, groupKey) {
  if (!filter) return false;
  if (filter.__range) {
    var parts = String(groupKey || '').split('|');
    var dateKey = parts.shift() || '';
    var store = parts.join('|');
    return OMNI_groupFilterMatch_(filter, groupKey, dateKey, store);
  }
  return !!filter[groupKey];
}

function OMNI_dateKeyFromAny_(value, preference) {
  return OMNI_dateKeyStrict_(value, preference || 'DMY');
}

function OMNI_summaryGroupKey_(dateKey, store) {
  return String(dateKey || '').trim() + '|' + String(store || '').trim();
}

function OMNI_summaryProductKey_(dateKey, store, item) {
  return OMNI_summaryGroupKey_(dateKey, store) + '|' + String(item || '').trim();
}

function OMNI_marketplaceForStore_(storeMap, store) {
  var obj = (storeMap || {})[normalize_(store)] || null;
  return obj && obj.platform ? String(obj.platform).trim() : '';
}

function OMNI_objectToHeaderRow_(headers, obj) {
  return (headers || []).map(function(h) { return obj[h] !== undefined ? obj[h] : ''; });
}

function OMNI_collectOldOrderGroupsFromExisting_(existingMap, aggregatedRows, info) {
  var out = {};
  existingMap = existingMap || {};
  aggregatedRows = aggregatedRows || {};
  Object.keys(aggregatedRows).forEach(function(k) {
    var p = aggregatedRows[k] || {};
    var no = String(p.no || '').trim();
    var sku = marketplaceSkuFallback_(p.sku, p.productName || p.itemName, p.variation, no);
    var variation = String(p.variation || '').trim();
    var existing = existingMap[buildOrderIndexKey_(no, sku, variation)] || existingMap[no + '|' + sku];
    if (!existing || !existing.row) return;
    var dateKey = OMNI_dateKeyFromAny_(getRowValueAny_(existing.row, info, ['Tanggal Key','Tanggal']));
    var store = String(getRowValueAny_(existing.row, info, ['Toko']) || '').trim();
    if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  });
  return out;
}

function OMNI_collectOldSettlementGroupsForPayload_(rows) {
  var wanted = {};
  (rows || []).forEach(function(p) {
    var store = String(p.toko || p.Toko || '').trim();
    var no = String(p.no || p['No Pesanan'] || '').trim();
    if (store && no) wanted[store + '|' + no] = true;
  });
  var out = {};
  if (!Object.keys(wanted).length) return out;
  var t = readTable_(getActiveOmni_(), SETTLEMENT_SHEET, SETTLEMENT_HEADERS);
  if (!t.sheet) return out;
  var cDateKey = col_(t.info, ['Tgl Pencairan Key'], -1);
  var cDateRaw = col_(t.info, ['Tgl Pencairan'], -1);
  var cStore = col_(t.info, ['Toko'], -1);
  var cNo = col_(t.info, ['No Pesanan'], -1);
  t.rows.forEach(function(r) {
    var store = cStore !== -1 ? String(r[cStore] || '').trim() : '';
    var no = cNo !== -1 ? String(r[cNo] || '').trim() : '';
    if (!wanted[store + '|' + no]) return;
    var dateKey = OMNI_settlementDateKeyFromRow_(cDateRaw !== -1 ? r[cDateRaw] : '', cDateKey !== -1 ? r[cDateKey] : '');
    if (dateKey && store) out[OMNI_summaryGroupKey_(dateKey, store)] = true;
  });
  return out;
}

function TEST_omniDailySummaryAudit(emailOp, pasporOp) {
  OMNI_requirePassportOrEditor_(arguments, 'TEST_omniDailySummaryAudit');
  OMNI_ensureSummaryReady_();
  var ss = getActiveOmni_();
  var expectedOrder = OMNI_buildOrderDailyRows_(null);
  var expectedSettlement = OMNI_buildSettlementDailyRows_(null);
  var actualStore = readTable_(ss, OMNI_ORDER_DAILY_STORE_SHEET, OMNI_ORDER_DAILY_STORE_HEADERS);
  var actualProduct = readTable_(ss, OMNI_ORDER_DAILY_PRODUCT_SHEET, OMNI_ORDER_DAILY_PRODUCT_HEADERS);
  var actualSettlement = readTable_(ss, OMNI_SETTLEMENT_DAILY_STORE_SHEET, OMNI_SETTLEMENT_DAILY_STORE_HEADERS);

  var checks = [];
  function compare(name, expected, actual, tolerance) {
    tolerance = tolerance === undefined ? 0.01 : tolerance;
    var diff = toNumber_(actual) - toNumber_(expected);
    var ok = Math.abs(diff) <= tolerance;
    checks.push({ name:name, expected:expected, actual:actual, difference:diff, ok:ok });
    return ok;
  }

  compare('Order store row count', expectedOrder.storeRows.length, actualStore.rows.length, 0);
  compare('Order product row count', expectedOrder.productRows.length, actualProduct.rows.length, 0);
  compare('Settlement store row count', expectedSettlement.rows.length, actualSettlement.rows.length, 0);

  ['Gross_Sales','Active_Sales','Completed_Sales','In_Transit_Sales','Cancelled_Sales','Item_Qty','COGS_Value','Completed_COGS','In_Transit_COGS','Sample_Cost','Completed_Unsettled_Sales','Settlement_Net','Admin_Fee','Service_Fee','Affiliate_Fee','Seller_Shipping','Source_Row_Count'].forEach(function(h) {
    compare('Order store total ' + h,
      OMNI_sumHeaderFromMatrix_(OMNI_ORDER_DAILY_STORE_HEADERS, expectedOrder.storeRows, h),
      OMNI_sumHeaderFromTable_(actualStore, h));
  });

  ['Item_Qty','Gross_Sales','Completed_Sales','In_Transit_Sales','COGS_Value','Completed_COGS','In_Transit_COGS','Sample_Cost','Source_Row_Count'].forEach(function(h) {
    compare('Order product total ' + h,
      OMNI_sumHeaderFromMatrix_(OMNI_ORDER_DAILY_PRODUCT_HEADERS, expectedOrder.productRows, h),
      OMNI_sumHeaderFromTable_(actualProduct, h));
  });

  ['Gross_Settlement','Net_Settlement','Admin_Fee','Service_Fee','Affiliate_Fee','Seller_Shipping','Source_Row_Count'].forEach(function(h) {
    compare('Settlement total ' + h,
      OMNI_sumHeaderFromMatrix_(OMNI_SETTLEMENT_DAILY_STORE_HEADERS, expectedSettlement.rows, h),
      OMNI_sumHeaderFromTable_(actualSettlement, h));
  });

  var invalid = checks.filter(function(x){ return !x.ok; });
  var out = {
    success:invalid.length === 0,
    valid:invalid.length === 0,
    version:OMNI_SUMMARY_VERSION,
    checks:checks,
    differences:invalid,
    message:invalid.length ? 'Summary berbeda dari source. Jalankan OMNI_rebuildAllDailySummary().' : 'Daily summary cocok dengan source Omni.'
  };
  Logger.log(JSON.stringify(out, null, 2));
  return out;
}

function OMNI_sumHeaderFromMatrix_(headers, rows, header) {
  var idx = (headers || []).indexOf(header);
  if (idx === -1) return 0;
  return (rows || []).reduce(function(sum, r){ return sum + toNumber_(r[idx]); }, 0);
}

function OMNI_sumHeaderFromTable_(table, header) {
  if (!table || !table.info) return 0;
  var idx = col_(table.info, [header], -1);
  if (idx === -1) return 0;
  return (table.rows || []).reduce(function(sum, r){ return sum + toNumber_(r[idx]); }, 0);
}