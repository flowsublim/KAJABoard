/** Report engine: dashboard, laba rugi, neraca, COGM/COGS. */

function FIN_emptyCogmCogs_(monthKey, note) {
  return {
    periodKey: monthKey || Utilities.formatDate(new Date(), FIN_CFG.TZ, 'yyyy-MM'),
    sourceMode: 'DEFERRED_FAST_LOAD',
    note: note || 'COGM/COGS belum dimuat.',
    rows: [],
    inventory: { bahanQty: 0, bahanValue: 0, wipQty: 0, wipValue: 0, barangJadiQty: 0, barangJadiValue: 0 },
    cogs: { qty: 0, nominal: 0 },
    cogmRows: [],
    spkRows: [],
    totalCogmFinished: 0,
    totalWip: 0,
    hutangUpahProduksiVirtual: 0,
    deferred: true
  };
}

function FIN_getPurchasingPayablesForReport_() {
  var bills = FIN_getPurchasingBills_();
  var map = {};
  bills.forEach(function(b) {
    var key = [b.source, FIN_cleanKey_(b.ref), FIN_cleanKey_(b.vendor)].join('|');
    if (!map[key]) {
      map[key] = { source: b.source, ref: b.ref, vendor: b.vendor, tanggal: b.tanggal, tanggalKey: b.tanggalKey, kategori: b.kategori, totalHutang: 0, akunHutang: b.akunHutang, debitAccounts: [], lineCount: 0 };
    }
    map[key].totalHutang += FIN_toNumber_(b.totalHutang);
    map[key].lineCount += FIN_toNumber_(b.lineCount) || 0;
    if (map[key].debitAccounts.indexOf(b.debitAccount) === -1) map[key].debitAccounts.push(b.debitAccount);
    if (String(b.tanggalKey || '') && (!map[key].tanggalKey || String(b.tanggalKey) < String(map[key].tanggalKey))) {
      map[key].tanggalKey = b.tanggalKey;
      map[key].tanggal = b.tanggal;
    }
  });
  return Object.keys(map).map(function(k) { return map[k]; }).sort(function(a, b) { return String(b.tanggalKey).localeCompare(String(a.tanggalKey)); });
}

function FIN_calcNeracaMvp_(cashBalance, totalPiutang, totalHutang, totalDpOpen, valuation) {
  valuation = valuation || {};
  var persediaan = valuation.inventory || {};
  var hutangUpahProduksi = FIN_toNumber_(valuation.hutangUpahProduksiVirtual);
  var marketplacePiutang = Math.max(FIN_toNumber_(valuation.marketplaceReceivableValue), 0);
  var piutangLain = Math.max(FIN_toNumber_(totalPiutang) - marketplacePiutang, 0);

  var aset = [
    { kelompok: 'ASET', akun: 'Kas / Bank', saldo: FIN_toNumber_(cashBalance) },
    { kelompok: 'ASET', akun: 'Piutang Usaha', saldo: piutangLain },
    { kelompok: 'ASET', akun: 'Piutang Marketplace', saldo: marketplacePiutang, source: 'Omni_Order_Daily_Store.Completed_Unsettled_Sales as-of' },
    { kelompok: 'ASET', akun: 'Persediaan Bahan + Packaging', saldo: FIN_toNumber_(persediaan.bahanValue) },
    { kelompok: 'ASET', akun: 'WIP / Barang Setengah Jadi', saldo: FIN_toNumber_(persediaan.wipValue) },
    { kelompok: 'ASET', akun: 'Persediaan Barang Jadi', saldo: FIN_toNumber_(persediaan.barangJadiValue) },
    { kelompok: 'ASET', akun: 'Persediaan Barang Dalam Pengiriman', saldo: FIN_toNumber_(valuation.inTransitValue), source: 'Omni status Sudah Dikirim as-of' }
  ].filter(function(x){
    return x.saldo !== 0 || x.akun === 'Kas / Bank' || x.akun === 'Piutang Usaha';
  });

  // Saldo toko tampil per akun agar perpindahan Db Bank / Cr Saldo Toko terlihat jelas.
  (valuation.marketplaceSaldoRows || []).forEach(function(r) {
    var saldo = FIN_toNumber_(r.nominal);
    if (!saldo) return;
    var account = String(r.akun || r.label || 'Saldo Marketplace').trim();
    var existing = aset.filter(function(x) { return FIN_cleanKey_(x.akun) === FIN_cleanKey_(account); })[0];
    if (existing) existing.saldo += saldo;
    else aset.push({ kelompok:'ASET', akun:account, saldo:saldo, source:r.source || 'Settlement as-of' });
  });

  var liabilitas = [
    { kelompok: 'LIABILITAS', akun: 'Hutang Usaha + Maklun', saldo: totalHutang },
    { kelompok: 'LIABILITAS', akun: 'Uang Muka Penjualan / DP Customer', saldo: totalDpOpen },
    { kelompok: 'LIABILITAS', akun: 'Hutang Upah Produksi (virtual)', saldo: hutangUpahProduksi }
  ].filter(function(x){ return x.saldo !== 0 || x.akun !== 'Hutang Upah Produksi (virtual)'; });

  var totalAset = FIN_sum_(aset, 'saldo');
  var totalLiabilitas = FIN_sum_(liabilitas, 'saldo');
  var ekuitas = [{ kelompok: 'EKUITAS', akun: 'Ekuitas / Saldo Berjalan MVP', saldo: totalAset - totalLiabilitas }];
  return {
    aset: aset,
    liabilitas: liabilitas,
    ekuitas: ekuitas,
    totalAset: totalAset,
    totalLiabilitas: totalLiabilitas,
    totalEkuitas: totalAset - totalLiabilitas,
    balanceCheck: 0,
    sourceMode: 'SOURCE_MODULE_VALUATION_ASOF',
    asOfDate: valuation.balanceAsOfDate || '',
    marketplacePiutang: marketplacePiutang,
    marketplaceSaldo: FIN_toNumber_(valuation.marketplaceSaldoValue),
    inTransitValue: FIN_toNumber_(valuation.inTransitValue)
  };
}

function FIN_getCogmCogsMvp_(journals, monthKey) {
  return FIN_getCogmCogsEngine_(journals, monthKey);
}

function FIN_getStockMovementRows_() {
  var rows = [];
  try {
    var ss = FIN_getGudangSs_();
    var sh = ss.getSheetByName('Stock_Movement');
    if (!sh) return [];
    var table = FIN_readSheetTable_(sh);
    table.rows.forEach(function(r, idx) {
      if (FIN_isDeletedRow_(r)) return;
      var tgl = FIN_parseDate_(FIN_val_(r, ['Movement_Date', 'Movement Date', 'Tanggal', 'Date']));
      var srcRaw = FIN_val_(r, ['Source_Date', 'Source Date']);
      var srcDate = srcRaw ? FIN_parseDate_(srcRaw) : tgl;
      rows.push({
        rowNumber: idx + 2,
        txKey: FIN_val_(r, ['Tx_Key', 'Tx Key', 'Transaction_Key']),
        tanggal: FIN_displayDate_(tgl),
        tanggalKey: FIN_dateKey_(tgl),
        sourceDate: FIN_displayDate_(srcDate),
        sourceDateKey: FIN_dateKey_(srcDate),
        itemId: FIN_val_(r, ['Item_ID', 'Item ID']),
        itemName: FIN_val_(r, ['Item_Name', 'Item Name', 'Nama Item', 'Item']),
        itemCategory: FIN_val_(r, ['Item_Category', 'Item Category', 'Kategori Item', 'Category']),
        itemType: FIN_val_(r, ['Item_Type', 'Item Type', 'Tipe Item', 'Jenis Item']),
        unit: FIN_val_(r, ['Unit', 'Satuan']),
        warehouseCode: FIN_val_(r, ['Warehouse_Code', 'Warehouse Code', 'Gudang']),
        direction: FIN_val_(r, ['Direction', 'Arah']),
        movementType: FIN_val_(r, ['Movement_Type', 'Movement Type', 'Tipe Movement', 'Type']),
        qty: FIN_toNumber_(FIN_val_(r, ['Qty', 'Quantity', 'Jumlah'])),
        unitCost: FIN_toNumber_(FIN_val_(r, ['Unit_Cost', 'Unit Cost', 'Harga', 'HPP'])),
        totalCost: FIN_toNumber_(FIN_val_(r, ['Total_Cost', 'Total Cost', 'Total_Value', 'Total Value', 'Nilai', 'Total HPP'])),
        spkId: FIN_val_(r, ['SPK_ID', 'SPK ID', 'SPK']),
        costPeriod: FIN_val_(r, ['Cost_Period', 'Cost Period', 'Period']),
        costStatus: FIN_val_(r, ['Cost_Status', 'Cost Status']),
        unitCostProvisional: FIN_toNumber_(FIN_val_(r, ['Unit_Cost_Provisional', 'Unit Cost Provisional', 'Unit_Cost_Prov'])),
        valueProvisional: FIN_toNumber_(FIN_val_(r, ['Value_Provisional', 'Value Provisional', 'Total_Provisional'])),
        unitCostFinal: FIN_toNumber_(FIN_val_(r, ['Unit_Cost_Final', 'Unit Cost Final'])),
        valueFinal: FIN_toNumber_(FIN_val_(r, ['Value_Final', 'Value Final', 'Total_Final'])),
        costSource: FIN_val_(r, ['Cost_Source', 'Cost Source']),
        costSyncedAt: FIN_val_(r, ['Cost_Synced_At', 'Cost Synced At']),
        costLockedAt: FIN_val_(r, ['Cost_Locked_At', 'Cost Locked At']),
        closedAt: FIN_val_(r, ['Closed_At', 'Closed At']),
        closedBy: FIN_val_(r, ['Closed_By', 'Closed By']),
        sourceModule: FIN_val_(r, ['Source_Module', 'Source Module']),
        sourceId: FIN_val_(r, ['Source_ID', 'Source ID']),
        sourceLineId: FIN_val_(r, ['Source_Line_ID', 'Source Line ID']),
        refNo: FIN_val_(r, ['Ref_No', 'Ref No', 'No Referensi']),
        batchId: FIN_val_(r, ['Batch_ID', 'Batch ID']),
        externalRef: FIN_val_(r, ['External_Ref', 'External Ref']),
        status: FIN_val_(r, ['Status']),
        notes: FIN_val_(r, ['Notes', 'Catatan']),
        isDeleted: false
      });
    });
  } catch (err) {}
  return rows;
}

function FIN_getMovementCostPeriod_(m, fallbackMonth) {
  var p = String(m && m.costPeriod || '').trim();
  if (p) return p.substring(0, 7);
  var d = String((m && (m.sourceDateKey || m.tanggalKey)) || '').trim();
  return d ? d.substring(0, 7) : (fallbackMonth || '');
}

function FIN_pickMovementCost_(m, latestCost, opts) {
  opts = opts || {};
  latestCost = latestCost || {};
  var q = Math.abs(FIN_toNumber_(m && m.qty));
  var status = String((m && m.costStatus) || '').trim();
  var isFinal = FIN_isFinalCostStatus_(status);
  var unit = 0;
  var value = 0;
  var source = '';

  if (isFinal && FIN_toNumber_(m.valueFinal) > 0) {
    value = FIN_toNumber_(m.valueFinal);
    unit = FIN_toNumber_(m.unitCostFinal) || (q ? value / q : 0);
    source = 'VALUE_FINAL';
  } else if (isFinal && FIN_toNumber_(m.unitCostFinal) > 0) {
    unit = FIN_toNumber_(m.unitCostFinal);
    value = q * unit;
    source = 'UNIT_FINAL';
  } else if (FIN_toNumber_(m.valueProvisional) > 0) {
    value = FIN_toNumber_(m.valueProvisional);
    unit = FIN_toNumber_(m.unitCostProvisional) || (q ? value / q : 0);
    source = 'VALUE_PROVISIONAL';
  } else if (FIN_toNumber_(m.unitCostProvisional) > 0) {
    unit = FIN_toNumber_(m.unitCostProvisional);
    value = q * unit;
    source = 'UNIT_PROVISIONAL';
  } else if (FIN_toNumber_(m.totalCost) > 0) {
    value = FIN_toNumber_(m.totalCost);
    unit = FIN_toNumber_(m.unitCost) || (q ? value / q : 0);
    source = 'LEGACY_TOTAL_COST';
  } else if (FIN_toNumber_(m.unitCost) > 0) {
    unit = FIN_toNumber_(m.unitCost);
    value = q * unit;
    source = 'LEGACY_UNIT_COST';
  } else {
    var latest = latestCost[FIN_cleanKey_(m && m.itemName)] || null;
    if (latest && FIN_toNumber_(latest.cost) > 0) {
      unit = FIN_toNumber_(latest.cost);
      value = q * unit;
      source = 'LATEST_IN_COST_FALLBACK';
      if (!status && latest.costStatus) status = latest.costStatus;
    }
  }

  if (!status) status = isFinal ? 'FINAL' : (source ? 'PROVISIONAL' : 'UNKNOWN');
  return { unitCost: unit, value: value, status: status, source: source || 'NO_COST', qty: q };
}

function FIN_isCogsOutMovement_(m) {
  var type = FIN_cleanKey_(m && m.movementType);
  return type === 'OMNIOUT' || type === 'SALESOUT' || type === 'SJOUT' || type === 'POSOUT';
}

function FIN_getStockCutoffRows_() {
  var rows = [];
  try {
    var ss = FIN_getGudangSs_();
    var sh = ss.getSheetByName('Stock_Cutoff');
    if (!sh) return rows;
    var table = FIN_readSheetTable_(sh);
    table.rows.forEach(function(r, idx) {
      if (FIN_isDeletedRow_(r)) return;
      var cutoffDate = FIN_parseDate_(FIN_val_(r, ['Cutoff_Date', 'Cutoff Date', 'Tanggal', 'Date']));
      var qty = FIN_toNumber_(FIN_val_(r, ['Qty_Cutoff', 'Qty Cutoff', 'Stock_Qty', 'Qty', 'Stok']));
      var unitCost = FIN_toNumber_(FIN_val_(r, ['Unit_Cost', 'Unit Cost', 'Avg_Cost', 'Average_Cost', 'HPP', 'Cost']));
      var value = FIN_toNumber_(FIN_val_(r, ['Value_Cutoff', 'Value Cutoff', 'Total_Value', 'Total Value', 'Nilai_Cutoff', 'Nilai Stok', 'Nilai']));
      if (!value && qty && unitCost) value = qty * unitCost;
      rows.push({
        rowNumber: idx + 2,
        cutoffId: FIN_val_(r, ['Cutoff_ID', 'Cutoff ID']),
        cutoffDate: FIN_displayDate_(cutoffDate),
        cutoffDateKey: FIN_dateKey_(cutoffDate),
        costPeriod: String(FIN_val_(r, ['Cost_Period', 'Cost Period', 'Period']) || '').trim(),
        itemId: FIN_val_(r, ['Item_ID', 'Item ID']),
        itemName: FIN_val_(r, ['Item_Name', 'Item Name', 'Nama Item', 'Item']),
        warehouseCode: FIN_val_(r, ['Warehouse_Code', 'Warehouse Code', 'Gudang']),
        qty: qty,
        unitCost: unitCost,
        value: value,
        costStatus: FIN_val_(r, ['Cost_Status', 'Cost Status']),
        costSource: FIN_val_(r, ['Cost_Source', 'Cost Source', 'Source']),
        source: FIN_val_(r, ['Source']),
        createdAt: FIN_val_(r, ['Created_At', 'Created At']),
        createdBy: FIN_val_(r, ['Created_By', 'Created By']),
        notes: FIN_val_(r, ['Notes', 'Catatan'])
      });
    });
  } catch (err) {}
  return rows;
}

function FIN_latestCutoffByItem_(cutoffRows) {
  var map = {};
  (cutoffRows || []).forEach(function(c) {
    var k = FIN_cleanKey_(c.itemName || c.itemId);
    if (!k) return;
    var d = String(c.cutoffDateKey || '');
    if (!map[k] || d > String(map[k].cutoffDateKey || '')) map[k] = c;
  });
  return map;
}

function FIN_itemStockClass_(itemName, itemId, itemType, itemCategory, itemMap) {
  var item = itemMap[FIN_cleanKey_(itemName)] || itemMap[FIN_cleanKey_(itemId)] || {};
  var type = FIN_cleanKey_(itemType || item.type || itemCategory || '');
  if (type === 'BAHAN' || type === 'PACKAGING' || type === 'BAHANBAKU') return 'BAHAN';
  if (type === 'BARANGJADI' || type === 'BARANG_JADI' || type === 'FINISHEDGOODS') return 'BARANG_JADI';
  return '';
}

function FIN_calcInventoryValueFromStock_(stockRows, itemMap, latestCost, spkRows) {
  itemMap = itemMap || {};
  latestCost = latestCost || {};
  var bahanQty = 0, bahanValue = 0, barangJadiQty = 0, barangJadiValue = 0;
  var cutoffRows = FIN_getStockCutoffRows_();
  var latestCutoff = FIN_latestCutoffByItem_(cutoffRows);
  var hasCutoff = Object.keys(latestCutoff).length > 0;
  var cutoffApplied = 0;
  var cutoffLatestDate = '';
  var byItemCutoffDate = {};

  // Stock_Cutoff menyimpan total nilai stok: Value_Cutoff.
  // Unit_Cost di cutoff adalah harga rata-rata/unit, jadi tidak boleh dipakai sebagai total persediaan.
  Object.keys(latestCutoff).forEach(function(k) {
    var c = latestCutoff[k];
    var klass = FIN_itemStockClass_(c.itemName, c.itemId, '', '', itemMap);
    if (!klass) return;
    var q = FIN_toNumber_(c.qty);
    var v = FIN_toNumber_(c.value);
    if (!v && q) v = q * FIN_toNumber_(c.unitCost);
    if (klass === 'BAHAN') { bahanQty += q; bahanValue += v; }
    if (klass === 'BARANG_JADI') { barangJadiQty += q; barangJadiValue += v; }
    byItemCutoffDate[k] = String(c.cutoffDateKey || '');
    if (String(c.cutoffDateKey || '') > cutoffLatestDate) cutoffLatestDate = String(c.cutoffDateKey || '');
    cutoffApplied++;
  });

  (stockRows || []).forEach(function(m) {
    if (m.isDeleted) return;
    var itemKey = FIN_cleanKey_(m.itemName || m.itemId);
    if (hasCutoff) {
      var itemCutoffDate = byItemCutoffDate[itemKey] || '';
      if (itemCutoffDate && String(m.tanggalKey || m.sourceDateKey || '') <= itemCutoffDate) return;
    }
    var klass = FIN_itemStockClass_(m.itemName, m.itemId, m.itemType, m.itemCategory, itemMap);
    if (!klass) return;

    var dir = FIN_cleanKey_(m.direction);
    var sign = dir === 'OUT' ? -1 : 1;
    if (dir !== 'IN' && dir !== 'OUT') sign = FIN_cleanKey_(m.movementType).indexOf('OUT') !== -1 ? -1 : 1;
    var qtyAbs = Math.abs(FIN_toNumber_(m.qty));
    var qty = sign * qtyAbs;
    var costPack = FIN_pickMovementCost_(m, latestCost, { preferFinal: true });
    var valAbs = FIN_toNumber_(costPack.value);
    if (!valAbs) {
      var item = itemMap[FIN_cleanKey_(m.itemName)] || {};
      valAbs = qtyAbs * (FIN_toNumber_(costPack.unitCost) || FIN_toNumber_(item.defaultCost) || 0);
    }
    var val = sign * valAbs;
    if (klass === 'BAHAN') { bahanQty += qty; bahanValue += val; }
    if (klass === 'BARANG_JADI') { barangJadiQty += qty; barangJadiValue += val; }
  });
  var wipValue = FIN_sum_(spkRows || [], 'wipEnding');
  return {
    bahanQty: bahanQty,
    bahanValue: bahanValue,
    wipValue: wipValue,
    barangJadiQty: barangJadiQty,
    barangJadiValue: barangJadiValue,
    valuationSource: hasCutoff ? 'STOCK_CUTOFF_PLUS_MOVEMENT_AFTER_CUTOFF' : 'STOCK_MOVEMENT_FROM_BEGINNING',
    cutoffApplied: cutoffApplied,
    cutoffLatestDate: cutoffLatestDate,
    note: hasCutoff ? 'Persediaan memakai Stock_Cutoff.Value_Cutoff sebagai total nilai stok, lalu ditambah/kurang movement setelah cutoff.' : 'Belum ada Stock_Cutoff; persediaan dihitung dari Stock_Movement.'
  };
}

function FIN_isSellingExpenseAccount_(akun) {
  var k = FIN_cleanKey_(akun);
  return k.indexOf('ONGKOSKIRIM') !== -1 || k.indexOf('ONGKIR') !== -1 || k.indexOf('PACKING') !== -1 || k.indexOf('IKLAN') !== -1 || k.indexOf('PEMASARAN') !== -1 || k.indexOf('AFFILIATE') !== -1 || k.indexOf('KOMISIPENJUALAN') !== -1 || k.indexOf('SAMPLE') !== -1;
}

function FIN_isAdminExpenseAccount_(akun) {
  var k = FIN_cleanKey_(akun);
  return k.indexOf('GAJI') !== -1 || k.indexOf('LISTRIKKANTOR') !== -1 || k.indexOf('TELEPON') !== -1 || k.indexOf('INTERNET') !== -1 || k.indexOf('BBM') !== -1 || k.indexOf('ATK') !== -1 || k.indexOf('KONSUMSI') !== -1 || k.indexOf('RUMAHTANGGA') !== -1 || k.indexOf('JASAPROFESIONAL') !== -1 || k.indexOf('PEMELIHARAANKENDARAAN') !== -1 || k.indexOf('LANGGANANSOFTWARE') !== -1 || k.indexOf('PERJALANANDINAS') !== -1 || k.indexOf('ADMINISTRASIBANK') !== -1 || k.indexOf('SELISIHBAYAR') !== -1;
}

function FIN_pickExpenseSection_(akun) {
  if (FIN_isSellingExpenseAccount_(akun)) return 'selling';
  if (FIN_isAdminExpenseAccount_(akun)) return 'admin';
  var k = FIN_cleanKey_(akun);
  if (k.indexOf('BIAYA') !== -1 || k.indexOf('BEBAN') !== -1) return 'admin';
  return '';
}

function FIN_calcCogsByBucketForLr_(cogmCogs, omniFinance) {
  var out = { rows: [], total: 0, finalValue: 0, provisionalValue: 0 };
  var map = {};
  var cogs = cogmCogs && cogmCogs.cogs ? cogmCogs.cogs : null;
  if (cogs) {
    (cogs.rows || []).forEach(function(r) {
      var mt = FIN_cleanKey_(r.movementType), bucket = 'Lain-lain';
      if (mt === 'POSOUT') bucket = 'POS';
      else if (mt === 'SALESOUT' || mt === 'SJOUT') bucket = 'Konvensional';
      else if (mt === 'OMNIOUT') return;
      FIN_addAmount_(map, bucket, r.nominal, { source: r.movementType, costStatus: r.costStatus || '' });
    });
    out.finalValue += FIN_toNumber_(cogs.finalValue);
    out.provisionalValue += FIN_toNumber_(cogs.provisionalValue);
  }
  (omniFinance && omniFinance.omniCogsRows || []).forEach(function(r) {
    FIN_addAmount_(map, r.store || 'Marketplace', r.nominal, { source: 'Omni_Order_Daily_Store.Completed_COGS', costStatus: r.costStatus || '' });
    var cs = FIN_cleanKey_(r.costStatus);
    if (cs === 'FINAL') out.finalValue += FIN_toNumber_(r.nominal);
    else if (cs === 'PROVISIONAL') out.provisionalValue += FIN_toNumber_(r.nominal);
  });
  out.rows = FIN_mapToRows_(map);
  out.total = FIN_sum_(out.rows, 'nominal');
  return out;
}

function FIN_calcLabaRugiMvp_(journals, invoices, monthKey) {
  var omni = FIN_emptyOmniFinance_();
  try { omni = FIN_getOmniFinanceDataDaily_(monthKey, journals || []); } catch (err) {}
  return FIN_calcLabaRugiSourceReader_(journals || [], invoices || [], monthKey, omni, null);
}

function FIN_latestCutoffByItemAsOf_(cutoffRows, periodKey) {
  var endKey = FIN_periodEndKey_(periodKey);
  var map = {};
  (cutoffRows || []).forEach(function(c) {
    var k = FIN_cleanKey_(c.itemName || c.itemId);
    if (!k) return;
    var d = String(c.cutoffDateKey || '');
    if (d && d > endKey) return;
    if (!map[k] || d > String(map[k].cutoffDateKey || '')) map[k] = c;
  });
  return map;
}

function FIN_calcInventoryValueFromStockAsOf_(stockRows, itemMap, latestCost, spkRows, periodKey) {
  itemMap = itemMap || {};
  latestCost = latestCost || {};
  periodKey = periodKey || Utilities.formatDate(new Date(), FIN_CFG.TZ, 'yyyy-MM');
  var endKey = FIN_periodEndKey_(periodKey);
  var bahanQty = 0, bahanValue = 0, barangJadiQty = 0, barangJadiValue = 0;
  var cutoffRows = FIN_getStockCutoffRows_();
  var latestCutoff = FIN_latestCutoffByItemAsOf_(cutoffRows, periodKey);
  var hasCutoff = Object.keys(latestCutoff).length > 0;
  var cutoffApplied = 0;
  var cutoffLatestDate = '';
  var byItemCutoffDate = {};

  Object.keys(latestCutoff).forEach(function(k) {
    var c = latestCutoff[k];
    var klass = FIN_itemStockClass_(c.itemName, c.itemId, '', '', itemMap);
    if (!klass) return;
    var q = FIN_toNumber_(c.qty);
    var v = FIN_toNumber_(c.value);
    if (!v && q) v = q * FIN_toNumber_(c.unitCost);
    if (klass === 'BAHAN') { bahanQty += q; bahanValue += v; }
    if (klass === 'BARANG_JADI') { barangJadiQty += q; barangJadiValue += v; }
    byItemCutoffDate[k] = String(c.cutoffDateKey || '');
    if (String(c.cutoffDateKey || '') > cutoffLatestDate) cutoffLatestDate = String(c.cutoffDateKey || '');
    cutoffApplied++;
  });

  (stockRows || []).forEach(function(m) {
    if (m.isDeleted) return;
    var txDate = String(m.tanggalKey || m.sourceDateKey || '');
    if (txDate && txDate > endKey) return;
    var itemKey = FIN_cleanKey_(m.itemName || m.itemId);
    if (hasCutoff) {
      var itemCutoffDate = byItemCutoffDate[itemKey] || '';
      if (itemCutoffDate && txDate && txDate <= itemCutoffDate) return;
    }
    var klass = FIN_itemStockClass_(m.itemName, m.itemId, m.itemType, m.itemCategory, itemMap);
    if (!klass) return;
    var dir = FIN_cleanKey_(m.direction);
    var sign = dir === 'OUT' ? -1 : 1;
    if (dir !== 'IN' && dir !== 'OUT') sign = FIN_cleanKey_(m.movementType).indexOf('OUT') !== -1 ? -1 : 1;
    var qtyAbs = Math.abs(FIN_toNumber_(m.qty));
    var qty = sign * qtyAbs;
    var costPack = FIN_pickMovementCost_(m, latestCost, { preferFinal: true });
    var valAbs = FIN_toNumber_(costPack.value);
    if (!valAbs) {
      var item = itemMap[FIN_cleanKey_(m.itemName)] || {};
      valAbs = qtyAbs * (FIN_toNumber_(costPack.unitCost) || FIN_toNumber_(item.defaultCost) || 0);
    }
    var val = sign * valAbs;
    if (klass === 'BAHAN') { bahanQty += qty; bahanValue += val; }
    if (klass === 'BARANG_JADI') { barangJadiQty += qty; barangJadiValue += val; }
  });
  return {
    periodKey: periodKey,
    asOfDate: endKey,
    bahanQty: bahanQty,
    bahanValue: bahanValue,
    wipValue: FIN_sum_(spkRows || [], 'wipEnding'),
    barangJadiQty: barangJadiQty,
    barangJadiValue: barangJadiValue,
    valuationSource: hasCutoff ? 'STOCK_CUTOFF_AS_OF_PERIOD_PLUS_MOVEMENT_AFTER_CUTOFF' : 'STOCK_MOVEMENT_FROM_BEGINNING_TO_PERIOD_END',
    cutoffApplied: cutoffApplied,
    cutoffLatestDate: cutoffLatestDate,
    note: hasCutoff ? 'Persediaan memakai Stock_Cutoff terakhir sampai akhir periode, lalu ditambah/kurang movement setelah cutoff sampai akhir periode.' : 'Belum ada Stock_Cutoff sampai periode ini; persediaan dihitung dari awal data sampai akhir periode.'
  };
}

function FIN_calcManualExpenseRows_(journals, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange), selling = {}, admin = {}, other = {};
  FIN_manualJournalsOnly_(journals || []).forEach(function(j) {
    if (!FIN_isDateKeyInRange_(j.tanggalKey, range)) return;
    var n = FIN_toNumber_(j.nominal), debitSection = FIN_pickExpenseSection_(j.akunDebit), creditSection = FIN_pickExpenseSection_(j.akunKredit);
    if (debitSection) FIN_addAmount_(debitSection === 'selling' ? selling : admin, j.akunDebit, n, { source: 'Data_Jurnal manual/kas-bank' });
    if (creditSection) FIN_addAmount_(creditSection === 'selling' ? selling : admin, j.akunKredit, -n, { source: 'Data_Jurnal manual/kas-bank' });
    if (!debitSection && !creditSection) {
      var dk = FIN_cleanKey_(j.akunDebit), ck = FIN_cleanKey_(j.akunKredit);
      if (dk.indexOf('BIAYA') !== -1 || dk.indexOf('BEBAN') !== -1 || ck.indexOf('BIAYA') !== -1 || ck.indexOf('BEBAN') !== -1) FIN_addAmount_(other, j.akunDebit || j.akunKredit || 'Beban Lain', dk.indexOf('BIAYA') !== -1 || dk.indexOf('BEBAN') !== -1 ? n : -n, { source: 'Data_Jurnal manual/kas-bank' });
    }
  });
  return { sellingRows: FIN_mapToRows_(selling), adminRows: FIN_mapToRows_(admin), otherRows: FIN_mapToRows_(other) };
}

function FIN_calcCogsFromGudangSnapshot_(stockRows, latestCost, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var qty = 0, nominal = 0, finalValue = 0, provisionalValue = 0, unknownValue = 0, rows = [], byType = {}, byStatus = {};
  (stockRows || []).forEach(function(m) {
    if (m.isDeleted) return;
    var txDate = String(m.sourceDateKey || m.tanggalKey || '').substring(0, 10);
    if (!FIN_isDateKeyInRange_(txDate, range)) return;
    if (!FIN_isCogsOutMovement_(m)) return;
    var q = Math.abs(FIN_toNumber_(m.qty)), costPack = FIN_pickMovementCost_(m, latestCost, { preferFinal: true }), n = FIN_toNumber_(costPack.value), unit = FIN_toNumber_(costPack.unitCost), statusKey = FIN_cleanKey_(costPack.status || m.costStatus || 'UNKNOWN') || 'UNKNOWN', typeKey = String(m.movementType || '').trim() || 'UNKNOWN';
    qty += q; nominal += n; byType[typeKey] = (byType[typeKey] || 0) + n; byStatus[statusKey] = (byStatus[statusKey] || 0) + n;
    if (statusKey === 'FINAL') finalValue += n; else if (statusKey === 'PROVISIONAL') provisionalValue += n; else unknownValue += n;
    rows.push({ tanggal: m.sourceDate || m.tanggal, costPeriod: FIN_getMovementCostPeriod_(m, range.periodKey), movementType: m.movementType, sourceModule: m.sourceModule, ref: m.refNo || m.sourceId || m.externalRef || m.txKey, item: m.itemName, qty: q, unitCost: unit, nominal: n, costStatus: costPack.status || m.costStatus || '', costSource: m.costSource || costPack.source || '', txKey: m.txKey || '' });
  });
  return { qty: qty, nominal: nominal, finalValue: finalValue, provisionalValue: provisionalValue, unknownValue: unknownValue, byType: byType, byStatus: byStatus, rows: rows.slice(0, 500), includedMovementTypes: ['OMNI_OUT','SALES_OUT','SJ_OUT','POS_OUT'] };
}

function FIN_calcCogsFromSalesOut_(stockRows, latestCost, periodOrRange) { return FIN_calcCogsFromGudangSnapshotNoOmni_(stockRows, latestCost, periodOrRange); }

function FIN_getCogmCogsEngine_(journals, periodOrRange) {
  journals = journals || FIN_getJurnalRows_();
  var range = FIN_rangeFromPeriodArg_(periodOrRange), stockRowsAll = FIN_getStockMovementRows_(), stockRowsAsOf = FIN_filterRowsThroughPeriod_(stockRowsAll, range), itemMap = FIN_getMasterItemTypeMap_(), latestCost = FIN_latestItemCostMap_(stockRowsAsOf), inventory = FIN_calcInventoryValueFromStockAsOf_(stockRowsAll, itemMap, latestCost, [], range), cogs = FIN_calcCogsFromSalesOut_(stockRowsAll, latestCost, range);
  var cogmRows = [], totalCogm = 0, wipIn = 0, wipOutToFinished = 0;
  stockRowsAsOf.forEach(function(m){
    if (m.isDeleted) return;
    var type = FIN_cleanKey_(m.movementType), qty = Math.abs(FIN_toNumber_(m.qty)), costPack = FIN_pickMovementCost_(m, latestCost, { preferFinal: true }), unit = FIN_toNumber_(costPack.unitCost), val = FIN_toNumber_(costPack.value) || qty * unit, txDate = String(m.sourceDateKey || m.tanggalKey || '').substring(0,10), inRange = FIN_isDateKeyInRange_(txDate, range);
    if (type.indexOf('PRODUCTIONMATERIALOUT') !== -1 || type.indexOf('MAKLUNWIPOUT') !== -1) wipIn += val;
    if (type.indexOf('PRODUCTIONIN') !== -1 || type.indexOf('MAKLUNIN') !== -1) {
      if (FIN_cleanKey_(m.costSource).indexOf('CMT') !== -1 || type.indexOf('PRODUCTIONIN') !== -1) wipOutToFinished += val;
      if (inRange) { totalCogm += val; cogmRows.push({ tanggal: m.sourceDate || m.tanggal, ref: m.refNo || m.spkId || m.sourceId, spk: m.spkId || m.refNo, item: m.itemName, movementType: m.movementType, qty: qty, unitCost: unit, totalCost: val, costStatus: m.costStatus || '', costSource: m.costSource || '' }); }
    }
  });
  var totalWip = Math.max(wipIn - wipOutToFinished, 0), prodRowsAsOf = FIN_filterRowsThroughPeriod_(FIN_getProduksiRows_(), range), hutangUpah = FIN_calcHutangUpahProduksiVirtual_(prodRowsAsOf, journals), totalUpahRange = FIN_filterRowsInPeriod_(prodRowsAsOf, range).reduce(function(sum, r){ return sum + FIN_toNumber_(r.upahBorongan); }, 0), label = FIN_reportLabel_(range);
  var out = { periodKey: range.periodKey, dateStart: range.startKey, dateEnd: range.endKey, sourceMode: 'GUDANG_COGS_SNAPSHOT_READER_DATE_RANGE_FILTER', note: 'COGM/COGS periode ' + label + '. Persediaan Neraca dihitung as-of ' + range.endKey + '. Jika belum ada Stock_Cutoff/closing, Finance fallback hitung movement dari awal sampai tanggal akhir.', rows: [ { komponen: 'Persediaan Bahan + Packaging', source: inventory.valuationSource, qty: inventory.bahanQty, nominal: inventory.bahanValue }, { komponen: 'WIP / Barang Setengah Jadi', source: 'Movement sampai tanggal akhir', qty: '', nominal: totalWip }, { komponen: 'Persediaan Barang Jadi', source: inventory.valuationSource, qty: inventory.barangJadiQty, nominal: inventory.barangJadiValue }, { komponen: 'COGM Finished Periode Ini', source: 'PRODUCTION_IN + MAKLUN_IN dalam rentang tanggal', qty: '', nominal: totalCogm }, { komponen: 'COGS Penjualan Periode Ini', source: 'SALES_OUT + SJ_OUT + POS_OUT dalam rentang tanggal; COGS online ditampilkan terpisah dari Omni daily summary', qty: cogs.qty, nominal: cogs.nominal }, { komponen: 'COGS FINAL', source: 'Stock_Movement.Value_Final', qty: '', nominal: cogs.finalValue }, { komponen: 'COGS PROVISIONAL', source: 'Stock_Movement.Value_Provisional / cost berjalan', qty: '', nominal: cogs.provisionalValue }, { komponen: 'Hutang Upah Produksi Virtual', source: 'Upah hasil kerja - pembayaran Hutang Gaji', qty: '', nominal: hutangUpah }, { komponen: 'Upah Produksi Periode Ini', source: 'Data_Produksi.Upah Borongan dalam rentang tanggal', qty: '', nominal: totalUpahRange } ], inventory: inventory, cogs: cogs, cogmRows: cogmRows.slice(0,500), totalCogmFinished: totalCogm, totalWip: totalWip, hutangUpahProduksiVirtual: hutangUpah, spkRows: cogmRows.slice(0,500) };
  try {
    var omni = FIN_getOmniFinanceDataDaily_(range, journals || []);
    out.omniOrderCogsRows = omni.omniCogsRows || [];
    out.inTransitRows = omni.inTransitRows || [];
    out.sampleAffiliateRows = omni.sampleAffiliateRows || [];
    out.inTransitValue = FIN_sum_(out.inTransitRows, 'nominal');
    out.sampleAffiliateValue = FIN_sum_(out.sampleAffiliateRows, 'nominal');
    var omniCogsValue = FIN_sum_(out.omniOrderCogsRows, 'nominal');
    out.rows.push({ komponen:'COGS Online dari Omni Daily Summary', source:'Omni_Order_Daily_Store.Completed_COGS', qty:'', nominal:omniCogsValue });
    out.rows.push({ komponen:'Persediaan Barang Dalam Pengiriman', source:'Omni_Order_Daily_Store.In_Transit_COGS', qty:'', nominal:out.inTransitValue });
    out.rows.push({ komponen:'Biaya Sample Affiliate dari Omni', source:'Omni_Order_Daily_Store.Sample_Cost', qty:'', nominal:out.sampleAffiliateValue });
  } catch (eOmni) {
    out.omniDailyWarning = eOmni && eOmni.message ? eOmni.message : String(eOmni);
  }
  try {
    FIN_applyMarketplaceAndTransitAsOf_(out, journals || [], range);
  } catch (eBalance) {
    out.marketplaceBalanceWarning = eBalance && eBalance.message ? eBalance.message : String(eBalance);
  }
  return out;
}

function FIN_getDashboardData(filter) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  filter = filter || {};
  var mode = FIN_cleanKey_(filter.mode || filter.scope || 'LITE'), isLite = mode === 'LITE' || mode === 'FAST' || mode === 'SUMMARY', includeHeavy = filter.includeHeavy === true || mode === 'FULL' || mode === 'HEAVY', range = FIN_resolveReportRange_(filter), warnings = [];
  var journals = [], invoices = [], hutang = [], dpCustomers = [], salesPOs = [], coa = [], omniFinance = FIN_emptyOmniFinance_(), omniReceivablesAsOf = { rows:[], marketplaceOutstanding:0, posOutstanding:0, totalOutstanding:0 };
  try { journals = FIN_getJurnalRows_(); } catch (e1) { warnings.push({ source: 'Data_Jurnal', message: e1.message || String(e1) }); }
  var journalsAsOf = FIN_filterRowsThroughPeriod_(journals, range), journalsInRange = FIN_filterRowsInPeriod_(journals, range);
  try { invoices = FIN_filterRowsThroughPeriod_(FIN_getSalesInvoices_(journalsAsOf), range); } catch (e2) { warnings.push({ source: 'Data_Invoice', message: e2.message || String(e2) }); }
  try { hutang = FIN_filterRowsThroughPeriod_(FIN_getHutangRows_(), range); } catch (e3) { warnings.push({ source: 'Purchasing Payables', message: e3.message || String(e3) }); }
  try { dpCustomers = FIN_getDPCustomerRows_(invoices, journalsAsOf); } catch (e4) { warnings.push({ source: 'DP Customer', message: e4.message || String(e4) }); }
  try { salesPOs = FIN_filterRowsThroughPeriod_(FIN_getSalesPoRows_(), range); } catch (e5) { warnings.push({ source: 'Data_PO', message: e5.message || String(e5) }); }
  try { coa = FIN_getCoa_(); } catch (e6) { warnings.push({ source: 'Master_COA', message: e6.message || String(e6) }); }
  try { omniFinance = FIN_getOmniFinanceDataDaily_(range, journalsAsOf); omniReceivablesAsOf = FIN_getOmniReceivablesAsOf_(range, journalsAsOf); invoices = invoices.concat(omniReceivablesAsOf.rows || []); } catch (eOmni) { warnings.push({ source: 'Omni Finance Handoff', message: eOmni && eOmni.message ? eOmni.message : String(eOmni) }); }
  var cashBalance = FIN_calcCashBalance_(journalsAsOf),
      totalInvoice = FIN_sum_(invoices, 'nilaiInvoice'),
      totalPiutang = FIN_sum_(invoices, 'sisaTagihan'),
      totalTerbayar = FIN_sum_(invoices, 'terbayar'),
      totalHutang = FIN_sum_(hutang, 'sisaHutang'),
      totalDpOpen = FIN_sum_(dpCustomers, 'saldoDp'),
      revenuePeriod = invoices.reduce(function(sum, x){ return FIN_isDateKeyInRange_(x.tanggalKey, range) ? sum + FIN_toNumber_(x.nilaiInvoice) : sum; }, 0),
      expensePeriod = FIN_calcManualExpenseRows_(journals, range),
      expenseTotal = FIN_sum_(expensePeriod.sellingRows, 'nominal') + FIN_sum_(expensePeriod.adminRows, 'nominal') + FIN_sum_(expensePeriod.otherRows, 'nominal'),
      arusKas = FIN_getArusKasRows_(journalsInRange),
      cogmCogs = includeHeavy ? FIN_getCogmCogsEngine_(journalsAsOf, range) : FIN_emptyCogmCogs_(range.periodKey, 'Mode cepat: HPP/COGS final dimuat saat tab Laba Rugi/COGM/Neraca dibuka.');
  try { FIN_applyMarketplaceAndTransitAsOf_(cogmCogs, journalsAsOf, range); } catch (eBalance) { warnings.push({ source:'Marketplace Balance / Transit As-Of', message:eBalance.message || String(eBalance) }); }
  var labaRugi = FIN_calcLabaRugiSourceReader_(journals, invoices, range, omniFinance, includeHeavy ? cogmCogs : null),
      neraca = FIN_calcNeracaMvp_(cashBalance, totalPiutang, totalHutang, totalDpOpen, cogmCogs),
      coaBalances = FIN_calcCoaBalances_(journalsAsOf, coa),
      journalLimit = FIN_toNumber_(filter.journalLimit) || (isLite ? 250 : 1000),
      arusKasLimit = FIN_toNumber_(filter.arusKasLimit) || (isLite ? 250 : 1000);
  return { success: true, version: FIN_CFG.VERSION, mode: includeHeavy ? 'FULL' : 'LITE', heavyLoaded: !!includeHeavy, generatedAt: FIN_displayDateTime_(new Date()), periodKey: range.periodKey, dateStart: range.startKey, dateEnd: range.endKey, periodLabel: FIN_reportLabel_(range), sourceWarnings: warnings, omniFinance: omniFinance, omniReceivablesAsOf: omniReceivablesAsOf, summary: { saldoKasBank: cashBalance, cashBalance: cashBalance, totalInvoice: totalInvoice, totalPiutang: totalPiutang, totalTerbayar: totalTerbayar, totalHutang: totalHutang, totalDpCustomer: totalDpOpen, totalDpOpen: totalDpOpen, revenueMtd: revenuePeriod, expenseMtd: expenseTotal, labaBersihMtd: labaRugi.labaOperasional, labaOperasionalMtd: labaRugi.labaOperasional, omniMarketplaceGross: omniFinance.summary.marketplaceGross || 0, omniMarketplaceOutstanding: omniReceivablesAsOf.marketplaceOutstanding || 0, omniPosOutstanding: omniReceivablesAsOf.posOutstanding || 0, omniPosGross: omniFinance.summary.posGross || 0, cogsMtd: labaRugi.hargaPokokPenjualan || 0, cogsFinalMtd: labaRugi.cogsFinal || 0, cogsProvisionalMtd: labaRugi.cogsProvisional || 0 }, invoices: invoices, hutang: hutang, dpCustomers: dpCustomers, salesPOs: salesPOs, jurnal: journalsInRange.slice(0, journalLimit), arusKas: arusKas.slice(0, arusKasLimit), labaRugi: labaRugi, neraca: neraca, cogmCogs: cogmCogs, coa: coa, coaBalances: coaBalances };
}

function FIN_calcLabaRugiSourceReader_(journals, invoices, periodOrRange, omniFinance, cogmCogs) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  omniFinance = omniFinance || FIN_emptyOmniFinance_();
  var konvMap = {}, onlineMap = {};
  (invoices || []).forEach(function(inv) {
    if (!FIN_isDateKeyInRange_(inv.tanggalKey, range)) return;
    var src = FIN_cleanKey_(inv.source), amount = FIN_toNumber_(inv.subtotal) || FIN_toNumber_(inv.nilaiInvoice);
    if (src === 'POS' || src === 'MARKETPLACE') return;
    FIN_addAmount_(konvMap, 'Konvensional', amount, { source: 'Data_Invoice', akun: FIN_revenueAccountForSalesType_(inv.jenisPesanan) });
  });
  (omniFinance.posSales || []).forEach(function(x){ if (FIN_isDateKeyInRange_(x.tanggalKey, range)) FIN_addAmount_(konvMap, 'POS', x.total, { source: 'Omni_POS_Sales', akun: FIN_accountNameByCandidates_(['Konvensional'], 'Konvensional') }); });
  (omniFinance.marketplaceSales || []).forEach(function(x){ if (FIN_isDateKeyInRange_(x.tanggalKey, range) && FIN_toNumber_(x.total) > 0) FIN_addAmount_(onlineMap, x.store || 'Marketplace', x.total, { source: 'Omni_Order', akun: FIN_revenueAccountForStore_(x.store) }); });
  var konvRows = FIN_mapToRows_(konvMap), onlineRows = FIN_mapToRows_(onlineMap), subtotalKonv = FIN_sum_(konvRows, 'nominal'), subtotalOnline = FIN_sum_(onlineRows, 'nominal'), totalPenjualan = subtotalKonv + subtotalOnline;
  // Biaya admin marketplace mengikuti tanggal order. Settlement tetap hanya untuk saldo toko/kas.
  var feeRows = FIN_groupMarketplaceFeesByStore_(omniFinance.marketplaceFeeRows || []), refundRows = FIN_groupRefundDiscountRows_(omniFinance.adjustments || [], omniFinance.returns || []), potonganRows = feeRows.concat(refundRows).filter(function(x){ return x.nominal || x.label === 'Refund/Diskon Penjualan' || x.akun === 'Refund/Diskon Penjualan'; });
  var totalPotongan = FIN_sum_(potonganRows, 'nominal'), pendapatanBersih = totalPenjualan - totalPotongan;
  var inventory = cogmCogs && cogmCogs.inventory ? cogmCogs.inventory : {}, cogsDetail = FIN_calcCogsByBucketForLr_(cogmCogs, omniFinance);
  var hppRows = [ FIN_sectionRow_('Persediaan Barang Jadi Awal', 0, 'Stock_Cutoff / closing sebelumnya (ready)'), FIN_sectionRow_('Pembelian Barang Jadi', 0, 'Purchasing barang jadi (reader-ready)'), FIN_sectionRow_('Harga Pokok Produksi', FIN_toNumber_(cogmCogs && cogmCogs.totalCogmFinished), 'Gudang PRODUCTION_IN / MAKLUN_IN cost snapshot'), FIN_sectionRow_('Persediaan Barang Jadi Akhir', FIN_toNumber_(inventory.barangJadiValue), 'Stock_Movement / Stock_Cutoff'), FIN_sectionRow_('Harga Pokok Penjualan', cogsDetail.total, 'Gudang konvensional/POS + Omni_Order COGS untuk status selesai') ];
  var exp = FIN_calcManualExpenseRows_(journals, range);
  (omniFinance.sampleAffiliateRows || []).forEach(function(r) { FIN_addAmount_(exp.sellingRows, FIN_sampleAffiliateAccount_(), r.nominal, { source: 'Omni_Order_Daily_Store.Sample_Cost', store: r.store }); });
  var totalBiayaPenjualan = FIN_sum_(exp.sellingRows, 'nominal'), totalBiayaAdmin = FIN_sum_(exp.adminRows, 'nominal'), totalBebanLain = FIN_sum_(exp.otherRows, 'nominal');
  var labaKotor = pendapatanBersih - cogsDetail.total, labaOperasional = labaKotor - totalBiayaPenjualan - totalBiayaAdmin - totalBebanLain;
  return { periodKey: range.periodKey, dateStart: range.startKey, dateEnd: range.endKey, mode: 'SOURCE_MODULE_DAILY_SUMMARY_READER', note: 'Penjualan, biaya admin, piutang, dan HPP marketplace mengikuti tanggal order dari Omni_Order_Daily_Store. Settlement_Date_Key hanya dipakai untuk saldo marketplace/kas. Data mentah hanya fallback bila summary belum siap.', penjualanKonvensionalRows: konvRows, penjualanOnlineRows: onlineRows, potonganPenjualanRows: potonganRows, hppRows: hppRows, cogsRows: cogsDetail.rows, biayaPenjualanRows: exp.sellingRows, biayaAdminRows: exp.adminRows, bebanLainRows: exp.otherRows, pendapatanRows: konvRows.concat(onlineRows), bebanRows: exp.sellingRows.concat(exp.adminRows).concat(exp.otherRows), subtotalPenjualanKonvensional: subtotalKonv, subtotalPenjualanOnline: subtotalOnline, totalPenjualan: totalPenjualan, totalPotonganPenjualan: totalPotongan, pendapatanBersih: pendapatanBersih, hargaPokokPenjualan: cogsDetail.total, cogsFinal: cogsDetail.finalValue, cogsProvisional: cogsDetail.provisionalValue, persediaanDalamPengiriman: FIN_sum_(omniFinance.inTransitRows || [], 'nominal'), sampleAffiliateValue: FIN_sum_(omniFinance.sampleAffiliateRows || [], 'nominal'), labaKotor: labaKotor, totalBiayaPenjualan: totalBiayaPenjualan, totalBiayaAdmin: totalBiayaAdmin, totalBebanLain: totalBebanLain, labaOperasional: labaOperasional, totalPendapatan: totalPenjualan, totalBeban: totalPotongan + cogsDetail.total + totalBiayaPenjualan + totalBiayaAdmin + totalBebanLain, labaBersih: labaOperasional };
}

function FIN_resolveReportRange_(filter) {
  filter = filter || {};
  var now = new Date();
  var defaultStart = new Date(now.getFullYear(), now.getMonth(), 1);
  var defaultEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  var rawStart = String(filter.dateStart || filter.startDate || filter.tanggalAwal || filter.start || '').trim();
  var rawEnd = String(filter.dateEnd || filter.endDate || filter.tanggalAkhir || filter.end || '').trim();
  var period = String(filter.period || filter.periodKey || filter.monthKey || '').trim();
  var startKey = FIN_dateKeySafe_(rawStart);
  var endKey = FIN_dateKeySafe_(rawEnd);

  if ((!startKey || !endKey) && /^\d{4}-\d{2}$/.test(period)) {
    var p = period.match(/^(\d{4})-(\d{2})$/);
    startKey = p[1] + '-' + p[2] + '-01';
    endKey = FIN_dateKeySafe_(new Date(Number(p[1]), Number(p[2]), 0));
  }
  if (!startKey) startKey = FIN_dateKeySafe_(defaultStart);
  if (!endKey) endKey = FIN_dateKeySafe_(defaultEnd);
  if (startKey > endKey) { var t = startKey; startKey = endKey; endKey = t; }
  return { startKey: startKey, endKey: endKey, dateStart: startKey, dateEnd: endKey, periodKey: startKey.substring(0, 7) };
}

function FIN_omniOrderCogsValue_(r) {
  var cogs = FIN_toNumber_(FIN_val_(r, ['COGS_Value', 'COGS Value', 'HPP', 'Total_Cost', 'Total Cost']));
  if (cogs > 0) return cogs;
  var qty = FIN_toNumber_(FIN_val_(r, ['Qty', 'Qty Gudang', 'Quantity']));
  var unit = FIN_toNumber_(FIN_val_(r, ['Unit_Cost', 'Unit Cost', 'HPP_Rata_Rata']));
  return qty > 0 && unit > 0 ? qty * unit : 0;
}

function FIN_calcCogsFromGudangSnapshotNoOmni_(stockRows, latestCost, periodOrRange) {
  var range = FIN_rangeFromPeriodArg_(periodOrRange);
  var qty = 0, nominal = 0, finalValue = 0, provisionalValue = 0, unknownValue = 0, rows = [], byType = {}, byStatus = {};
  (stockRows || []).forEach(function(m) {
    if (m.isDeleted) return;
    var txDate = String(m.sourceDateKey || m.tanggalKey || '').substring(0, 10);
    if (!FIN_isDateKeyInRange_(txDate, range)) return;
    if (!FIN_isCogsOutMovement_(m)) return;
    var typeClean = FIN_cleanKey_(m.movementType);
    if (typeClean === 'OMNIOUT') return; // Omni COGS dibaca dari Omni_Order agar status order bisa dipetakan.
    var q = Math.abs(FIN_toNumber_(m.qty)), costPack = FIN_pickMovementCost_(m, latestCost, { preferFinal: true }), n = FIN_toNumber_(costPack.value), unit = FIN_toNumber_(costPack.unitCost), statusKey = FIN_cleanKey_(costPack.status || m.costStatus || 'UNKNOWN') || 'UNKNOWN', typeKey = String(m.movementType || '').trim() || 'UNKNOWN';
    qty += q; nominal += n; byType[typeKey] = (byType[typeKey] || 0) + n; byStatus[statusKey] = (byStatus[statusKey] || 0) + n;
    if (statusKey === 'FINAL') finalValue += n; else if (statusKey === 'PROVISIONAL') provisionalValue += n; else unknownValue += n;
    rows.push({ tanggal: m.sourceDate || m.tanggal, costPeriod: FIN_getMovementCostPeriod_(m, range.periodKey), movementType: m.movementType, sourceModule: m.sourceModule, ref: m.refNo || m.sourceId || m.externalRef || m.txKey, item: m.itemName, qty: q, unitCost: unit, nominal: n, costStatus: costPack.status || m.costStatus || '', costSource: m.costSource || costPack.source || '', txKey: m.txKey || '' });
  });
  return { qty: qty, nominal: nominal, finalValue: finalValue, provisionalValue: provisionalValue, unknownValue: unknownValue, byType: byType, byStatus: byStatus, rows: rows.slice(0, 500), includedMovementTypes: ['SALES_OUT','SJ_OUT','POS_OUT'], excludedMovementTypes: ['OMNI_OUT'] };
}






// v1.9.3: transit dan saldo marketplace sudah diintegrasikan langsung ke FIN_calcNeracaMvp_.