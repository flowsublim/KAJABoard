/** Rekonsiliasi Bank: CSV/PDF import, matching, linking. */

// Konstanta rekonsiliasi wajib berada di modul Recon, bukan file debug.
var FIN_BANK_STATEMENT_SHEET_ALIASES = ['Bank_Statement','Bank Statement','BankStatement','Bank_Rekonsiliasi','Rekonsiliasi_Bank','Mutasi_Bank','Bank Mutation','Mutasi Bank'];
var FIN_BANK_STATEMENT_HEADERS = [
  'Import_ID','Tx_Key','Upload_At','Date_Key','Bank_Account','Direction','Amount','Description','Ref_No','Balance',
  'Source_File','Row_No','Match_Status','Matched_Jurnal_Key','Match_Method','Matched_At','Matched_By','Notes','Created_By','Is_Deleted'
];
var FIN_BANK_RECON_EXTRA_HEADERS = [];
var FIN_JURNAL_RECON_HEADERS = ['Bank_Tx_Key','Recon_Status','Recon_At','Recon_By'];

function FIN_findBankStatementSheet_() {
  var ss = FIN_selfSs_();
  var exact = ss.getSheetByName('Bank_Statement');
  var best = exact || null;
  var bestRows = exact ? Math.max(0, exact.getLastRow() - 1) : -1;
  FIN_BANK_STATEMENT_SHEET_ALIASES.forEach(function(name){
    var sh = ss.getSheetByName(name);
    if (!sh) return;
    var rows = Math.max(0, sh.getLastRow() - 1);
    if (!best || rows > bestRows) { best = sh; bestRows = rows; }
  });
  return best;
}

function FIN_bankStatementMeta_(sh) {
  sh = sh || FIN_bankStatementSheet_();
  return {
    sheetName: sh.getName(),
    lastRow: sh.getLastRow(),
    lastCol: sh.getLastColumn(),
    dataRows: Math.max(0, sh.getLastRow() - 1)
  };
}

/* v1.7.1 cleanup: setup + reader Bank_Statement memakai definisi terpadu di blok v1.7.1 bawah. */

function FIN_parseBankStatementCsv_(csvText) {
  var delimiter = FIN_detectCsvDelimiter_(csvText);
  var data = Utilities.parseCsv(csvText, delimiter);
  data = (data || []).filter(function(r){ return (r || []).join('').trim() !== ''; });
  if (!data.length) return { delimiter:delimiter, rows:[] };
  var headerRowIdx = FIN_detectBankCsvHeaderRow_(data);
  var headers = (data[headerRowIdx] || []).map(function(h){ return String(h || '').trim(); });
  var aliases = FIN_bankCsvAliasMap_(headers);
  var defaultYear = FIN_bankCsvPeriodYear_(data) || (new Date()).getFullYear();
  var rows = [];
  for (var i = headerRowIdx + 1; i < data.length; i++) {
    var r = data[i] || [];
    if (!r.join('').trim()) continue;
    var rawDate = FIN_csvPick_(r, aliases.date);
    var dateKey = FIN_bankDateKeyFromRaw_(rawDate, defaultYear);
    if (!dateKey) continue;
    var desc = FIN_csvPick_(r, aliases.description);
    var ref = FIN_csvPick_(r, aliases.ref);
    var rawDebit = FIN_csvPick_(r, aliases.debit);
    var rawCredit = FIN_csvPick_(r, aliases.credit);
    var rawAmount = FIN_csvPick_(r, aliases.amount);
    var rawBalance = FIN_csvPick_(r, aliases.balance);
    var rawType = FIN_csvPick_(r, aliases.type);

    var dirInfo = FIN_bankAmountDirection_(rawAmount, rawType, desc);
    var debit = FIN_toNumber_(rawDebit);
    var credit = FIN_toNumber_(rawCredit);
    var amount = FIN_toNumber_(rawAmount);
    var typeKey = FIN_cleanKey_(rawType);

    if (!debit && !credit && amount) {
      if (amount < 0 || dirInfo.direction === 'KELUAR' || typeKey === 'D' || typeKey === 'DEBIT' || typeKey === 'KELUAR' || typeKey === 'DB') debit = Math.abs(amount);
      else if (dirInfo.direction === 'MASUK' || typeKey === 'C' || typeKey === 'CREDIT' || typeKey === 'KREDIT' || typeKey === 'MASUK' || typeKey === 'CR') credit = Math.abs(amount);
      else credit = Math.abs(amount);
    }
    if (!debit && !credit) continue;
    rows.push({
      rowNo: i + 1,
      dateKey: dateKey,
      rawDate: rawDate,
      description: desc || ref || 'Mutasi bank',
      refNo: ref,
      debit: debit,
      credit: credit,
      balance: FIN_toNumber_(rawBalance),
      rawDescription: desc,
      rawDebit: rawDebit,
      rawCredit: rawCredit,
      rawAmount: rawAmount,
      rawBalance: rawBalance
    });
  }
  return { delimiter:delimiter, rows:rows, defaultYear:defaultYear };
}

function FIN_bankCsvPeriodYear_(data) {
  var scan = (data || []).slice(0, 12).map(function(r){ return (r || []).join(' '); }).join(' ');
  var matches = scan.match(/(?:19|20)\d{2}/g) || [];
  if (matches.length) return Number(matches[0]);
  return 0;
}

function FIN_bankDateKeyFromRaw_(rawDate, defaultYear) {
  if (rawDate instanceof Date || typeof rawDate === 'number') return FIN_dateKeySafe_(rawDate);
  var s = String(rawDate || '').trim();
  if (!s) return '';

  var mIso = s.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})/);
  if (mIso) return mIso[1] + '-' + ('0' + Number(mIso[2])).slice(-2) + '-' + ('0' + Number(mIso[3])).slice(-2);

  var mFull = s.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})/);
  if (mFull) {
    var yy = Number(mFull[3]);
    if (yy < 100) yy += 2000;
    return yy + '-' + ('0' + Number(mFull[2])).slice(-2) + '-' + ('0' + Number(mFull[1])).slice(-2);
  }

  // Format BCA e-statement: 01/06 tanpa tahun, tahun ada di baris Periode file CSV.
  var mShort = s.match(/^(\d{1,2})[\/-](\d{1,2})(?:\s|$)/);
  if (mShort && defaultYear) {
    return Number(defaultYear) + '-' + ('0' + Number(mShort[2])).slice(-2) + '-' + ('0' + Number(mShort[1])).slice(-2);
  }
  return FIN_dateKeySafe_(s);
}

function FIN_bankAmountDirection_(rawAmount, rawType, rawDescription) {
  var joined = String(rawAmount || '') + ' ' + String(rawType || '') + ' ' + String(rawDescription || '');
  var upper = joined.toUpperCase();
  // BCA: kolom Jumlah berisi "10,039,966.00 CR" atau "15,000,000.00 DB".
  if (/(^|[^A-Z])(DB|DEBET|DEBIT|KELUAR)([^A-Z]|$)/.test(upper)) return { direction:'KELUAR', marker:'DB' };
  if (/(^|[^A-Z])(CR|CREDIT|KREDIT|MASUK)([^A-Z]|$)/.test(upper)) return { direction:'MASUK', marker:'CR' };
  return { direction:'', marker:'' };
}

function FIN_detectCsvDelimiter_(txt) {
  var first = String(txt || '').split(/\r?\n/).slice(0, 5).join('\n');
  var candidates = [';', ',', '\t', '|'];
  var best = ';', bestCount = -1;
  candidates.forEach(function(d){ var pattern = d === '\t' ? '\\t' : '\\' + d; var re = new RegExp(pattern, 'g'); var m = first.match(re); var c = m ? m.length : 0; if (c > bestCount) { best = d; bestCount = c; } });
  return best;
}

function FIN_bankCsvAliasMap_(headers) {
  function idx(names){
    var wanted = names.map(FIN_cleanKey_);
    for (var i=0; i<headers.length; i++) {
      var h = FIN_cleanKey_(headers[i]);
      if (wanted.indexOf(h) !== -1) return i;
    }
    for (var j=0; j<headers.length; j++) {
      var hj = FIN_cleanKey_(headers[j]);
      for (var k=0; k<wanted.length; k++) if (hj.indexOf(wanted[k]) !== -1 || wanted[k].indexOf(hj) !== -1) return j;
    }
    return -1;
  }
  return {
    date: idx(['Tanggal','Date','Tgl','Tanggal Transaksi','Transaction Date','Posting Date','Value Date']),
    description: idx(['Keterangan','Deskripsi','Description','Uraian','Remark','Remarks','Berita','Mutasi']),
    ref: idx(['Ref','No Ref','No. Ref','Reference','Nomor Referensi','Transaction ID','ID Transaksi']),
    debit: idx(['Debit','Debet','Keluar','Withdrawal','Mutasi Debit','Debit Amount']),
    credit: idx(['Kredit','Credit','Masuk','Deposit','Mutasi Kredit','Credit Amount']),
    amount: idx(['Amount','Jumlah','Nominal','Nilai','Mutation','Mutasi Amount','Transaction Amount']),
    balance: idx(['Saldo','Balance','Running Balance','Saldo Akhir']),
    type: idx(['Type','Tipe','D/K','Dr/Cr','Debit/Credit','DC'])
  };
}

function FIN_csvPick_(row, idx) { return idx === undefined || idx < 0 ? '' : String(row[idx] === undefined || row[idx] === null ? '' : row[idx]).trim(); }

function FIN_bankStatementTxKey_(bank, dateKey, desc, ref, debit, credit, balance, fileName, rowNo) {
  var raw = ['BANKSTMT', bank, dateKey, ref, desc, debit, credit, balance, fileName, rowNo].join('|');
  return Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, raw)).substring(0, 32);
}

function FIN_bankStatementFindByTxKey_(txKey) {
  var sh = FIN_bankStatementSheet_();
  var table = FIN_readSheetTable_(sh);
  var key = String(txKey || '').trim();
  for (var i=0; i<(table.rows || []).length; i++) {
    if (String(FIN_val_(table.rows[i], ['Tx_Key']) || '').trim() === key) return { sheet:sh, table:table, row:table.rows[i] };
  }
  return null;
}

function FIN_jurnalMatchKey_(j) {
  var sk = String(j && j.sourceKey || '').trim();
  if (sk) return sk;
  return 'JRNROW:' + String(j && j.rowNumber || '');
}

function FIN_findJurnalByMatchKey_(jurnalKey) {
  var key = String(jurnalKey || '').trim();
  var rows = FIN_getJurnalRows_();
  for (var i=0; i<rows.length; i++) {
    if (FIN_jurnalMatchKey_(rows[i]) === key) return rows[i];
  }
  if (key.indexOf('JRNROW:') === 0) {
    var rn = Number(key.replace('JRNROW:', ''));
    for (var j=0; j<rows.length; j++) if (Number(rows[j].rowNumber) === rn) return rows[j];
  }
  return null;
}

function FIN_bankReconDirectionFromJurnal_(j) {
  var isIn = FIN_accountLooksCash_(j.akunDebit);
  var isOut = FIN_accountLooksCash_(j.akunKredit);
  return isIn ? 'MASUK' : isOut ? 'KELUAR' : '';
}

function FIN_bankReconBankMatch_(bankA, bankB) {
  var a = FIN_cleanKey_(bankA), b = FIN_cleanKey_(bankB);
  if (!a || !b) return false;
  return a === b || a.indexOf(b) !== -1 || b.indexOf(a) !== -1;
}

function FIN_dateDiffDays_(a, b) {
  var da = FIN_parseDate_(a), db = FIN_parseDate_(b);
  if (!da || !db) return 9999;
  return Math.round(Math.abs(da.getTime() - db.getTime()) / 86400000);
}


/* =========================
 * v1.8.7 - BANK RECON POPUP + MULTI JOURNAL MATCH
 * Satu mutasi bank dapat dicocokkan ke beberapa baris Data_Jurnal.
 * Relasi disimpan terpisah di Bank_Recon_Link agar Bank_Statement tetap compact.
 * ========================= */
var FIN_BANK_RECON_LINK_SHEET = 'Bank_Recon_Link';
var FIN_BANK_RECON_LINK_HEADERS = [
  'Link_ID','Recon_Group','Bank_Tx_Key','Jurnal_Key','Jurnal_Row','Direction','Amount',
  'Bank_Account','Statement_Date','Match_Method','Matched_At','Matched_By','Status','Notes'
];

function FIN_bankReconLinkSheet_() {
  var ss = FIN_selfSs_();
  var sh = ss.getSheetByName(FIN_BANK_RECON_LINK_SHEET);
  if (!sh) sh = ss.insertSheet(FIN_BANK_RECON_LINK_SHEET);
  FIN_ensureColumns_(sh, FIN_BANK_RECON_LINK_HEADERS);
  if (sh.getLastRow() === 0) sh.getRange(1,1,1,FIN_BANK_RECON_LINK_HEADERS.length).setValues([FIN_BANK_RECON_LINK_HEADERS]);
  sh.setFrozenRows(1);
  try {
    var hm = FIN_readSheetTable_(sh).map || {};
    ['Link_ID','Recon_Group','Bank_Tx_Key','Jurnal_Key','Direction','Bank_Account','Statement_Date','Match_Method','Matched_At','Matched_By','Status','Notes'].forEach(function(h){
      var c = hm[FIN_headerKey_(h)];
      if (c !== undefined) sh.getRange(1,c+1,Math.max(sh.getMaxRows(),2),1).setNumberFormat('@');
    });
    ['Amount'].forEach(function(h){ var c=hm[FIN_headerKey_(h)]; if(c !== undefined) sh.getRange(2,c+1,Math.max(sh.getMaxRows()-1,1),1).setNumberFormat('#,##0.00'); });
  } catch(e) {}
  return sh;
}

function FIN_setupBankReconMultiLink_() {
  var sh = FIN_bankReconLinkSheet_();
  var jsh = FIN_selfSs_().getSheetByName(FIN_CFG.SHEET_JURNAL);
  if (jsh) FIN_ensureColumns_(jsh, FIN_JURNAL_RECON_HEADERS);
  return sh;
}

function FIN_bankReconLinkRows_() {
  var sh = FIN_setupBankReconMultiLink_();
  return FIN_readSheetTable_(sh).rows || [];
}

function FIN_activeBankReconLinkMaps_() {
  var byTx = {}, byJurnal = {};
  FIN_bankReconLinkRows_().forEach(function(r){
    var status = FIN_cleanKey_(FIN_val_(r,['Status']) || 'ACTIVE');
    if (status && status !== 'ACTIVE') return;
    var tx = String(FIN_val_(r,['Bank_Tx_Key']) || '').trim();
    var jk = String(FIN_val_(r,['Jurnal_Key']) || '').trim();
    if (!tx || !jk) return;
    var item = {
      rowNumber:r._rowNumber,
      linkId:String(FIN_val_(r,['Link_ID']) || ''),
      reconGroup:String(FIN_val_(r,['Recon_Group']) || ''),
      txKey:tx,
      jurnalKey:jk,
      jurnalRow:Number(FIN_val_(r,['Jurnal_Row']) || 0),
      direction:String(FIN_val_(r,['Direction']) || ''),
      amount:FIN_toNumber_(FIN_val_(r,['Amount'])),
      bankAccount:String(FIN_val_(r,['Bank_Account']) || ''),
      statementDate:String(FIN_val_(r,['Statement_Date']) || ''),
      method:String(FIN_val_(r,['Match_Method']) || ''),
      matchedAt:String(FIN_val_(r,['Matched_At']) || ''),
      matchedBy:String(FIN_val_(r,['Matched_By']) || '')
    };
    if (!byTx[tx]) byTx[tx] = [];
    byTx[tx].push(item);
    byJurnal[jk] = item;
  });
  return { byTx:byTx, byJurnal:byJurnal };
}

function FIN_reconGroupId_() {
  return 'BRG-' + Utilities.formatDate(new Date(), ERP_GLOBAL_CFG.TZ || Session.getScriptTimeZone(), 'yyMMdd-HHmmss') + '-' + Utilities.getUuid().replace(/-/g,'').substring(0,8);
}

function FIN_reconLinkId_(txKey,jurnalKey) {
  var raw = [txKey,jurnalKey,new Date().getTime(),Utilities.getUuid()].join('|');
  return 'BRL-' + Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,raw)).replace(/=+$/,'').substring(0,20);
}

function FIN_setJurnalReconState_(jurnalKey, txKey, status, authEmail, whenText) {
  var j = FIN_findJurnalByMatchKey_(jurnalKey);
  if (!j || !j.rowNumber) return;
  var sh = FIN_selfSs_().getSheetByName(FIN_CFG.SHEET_JURNAL);
  if (!sh) return;
  FIN_ensureColumns_(sh, FIN_JURNAL_RECON_HEADERS);
  FIN_setByHeader_(sh, j.rowNumber, 'Bank_Tx_Key', txKey || '');
  FIN_setByHeader_(sh, j.rowNumber, 'Recon_Status', status || '');
  FIN_setByHeader_(sh, j.rowNumber, 'Recon_At', whenText || '');
  FIN_setByHeader_(sh, j.rowNumber, 'Recon_By', authEmail || '');
}

function FIN_migrateLegacyBankReconLinks_() {
  var linkSh = FIN_setupBankReconMultiLink_();
  var maps = FIN_activeBankReconLinkMaps_();
  var bankSh = FIN_bankStatementSheet_();
  var bankRows = FIN_readSheetTable_(bankSh).rows || [];
  var out = [];
  bankRows.forEach(function(r){
    var tx = String(FIN_val_(r,['Tx_Key']) || '').trim();
    var jk = String(FIN_val_(r,['Matched_Jurnal_Key']) || '').trim();
    var status = FIN_cleanKey_(FIN_val_(r,['Match_Status']) || '');
    if (!tx || !jk || status !== 'MATCHED' || /^MULTI:/i.test(jk) || maps.byJurnal[jk]) return;
    var j = FIN_findJurnalByMatchKey_(jk);
    if (!j) return;
    var direction = FIN_bankReconDirectionFromJurnal_(j);
    var now = String(FIN_val_(r,['Matched_At']) || FIN_displayDateTime_(new Date()));
    out.push({
      'Link_ID':FIN_reconLinkId_(tx,jk), 'Recon_Group':'LEGACY-' + tx.substring(0,12),
      'Bank_Tx_Key':tx, 'Jurnal_Key':jk, 'Jurnal_Row':j.rowNumber,
      'Direction':direction, 'Amount':FIN_toNumber_(j.nominal),
      'Bank_Account':String(FIN_val_(r,['Bank_Account']) || ''),
      'Statement_Date':String(FIN_val_(r,['Date_Key']) || ''),
      'Match_Method':String(FIN_val_(r,['Match_Method']) || 'LEGACY'),
      'Matched_At':now, 'Matched_By':String(FIN_val_(r,['Matched_By']) || ''),
      'Status':'ACTIVE', 'Notes':'Migrasi link rekonsiliasi lama.'
    });
  });
  if (out.length) FIN_appendObjectsByHeaders_(linkSh, FIN_BANK_RECON_LINK_HEADERS, out);
  return out.length;
}

function FIN_bankReconTxObject_(r) {
  var amount = FIN_toNumber_(FIN_val_(r,['Amount'])) || FIN_toNumber_(FIN_val_(r,['Debit'])) || FIN_toNumber_(FIN_val_(r,['Credit']));
  return {
    txKey:String(FIN_val_(r,['Tx_Key']) || '').trim(),
    dateKey:String(FIN_val_(r,['Date_Key']) || FIN_dateKeySafe_(FIN_val_(r,['Statement_Date'])) || '').substring(0,10),
    statementDate:FIN_displayDate_(FIN_val_(r,['Date_Key']) || FIN_val_(r,['Statement_Date'])),
    bankAccount:String(FIN_val_(r,['Bank_Account']) || ''),
    description:String(FIN_val_(r,['Description']) || ''),
    refNo:String(FIN_val_(r,['Ref_No']) || ''),
    direction:String(FIN_val_(r,['Direction']) || '').toUpperCase(),
    amount:amount,
    matchStatus:String(FIN_val_(r,['Match_Status']) || 'UNMATCHED'),
    matchedJurnalKey:String(FIN_val_(r,['Matched_Jurnal_Key']) || '')
  };
}


function FIN_findBankReconCandidates(payload, emailOp, pasporOp) {
  FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  FIN_setupBankReconLinkColumns_();
  FIN_setupBankReconMultiLink_();
  var found = FIN_bankStatementFindByTxKey_(payload.txKey);
  if (!found) throw new Error('Mutasi bank tidak ditemukan. Refresh rekonsiliasi bank.');
  var tx = FIN_bankReconTxObject_(found.row);
  if (!tx.amount) throw new Error('Nominal mutasi bank kosong atau tidak valid.');
  var maxDays = Math.max(0, Math.min(Number(payload.maxDays || 60), 365));
  var maps = FIN_activeBankReconLinkMaps_();
  var selectedLinks = maps.byTx[tx.txKey] || [];
  var selectedKeys = selectedLinks.map(function(x){ return x.jurnalKey; });
  var selectedMap = {};
  selectedKeys.forEach(function(k){ selectedMap[k] = true; });
  var qDesc = FIN_cleanKey_([tx.description,tx.refNo].join(' '));
  var candidates = [];
  FIN_getJurnalRows_().forEach(function(j){
    if (!FIN_accountLooksCash_(j.akunDebit) && !FIN_accountLooksCash_(j.akunKredit)) return;
    var dir = FIN_bankReconDirectionFromJurnal_(j);
    if (tx.direction && dir && tx.direction !== dir) return;
    var amount = FIN_toNumber_(j.nominal);
    if (!amount || amount > tx.amount + 0.01) return;
    var days = FIN_dateDiffDays_(tx.dateKey,j.tanggalKey);
    if (days > maxDays && !selectedMap[FIN_jurnalMatchKey_(j)]) return;
    var jurnalKey = FIN_jurnalMatchKey_(j);
    var used = maps.byJurnal[jurnalKey];
    if (used && used.txKey !== tx.txKey) return;
    var bank = dir === 'MASUK' ? j.akunDebit : j.akunKredit;
    var bankMatch = FIN_bankReconBankMatch_(tx.bankAccount,bank);
    var jDesc = FIN_cleanKey_([j.noReferensi,j.namaKontak,j.keterangan,j.akunLawan].join(' '));
    var textMatch = !!(qDesc && jDesc && (qDesc.indexOf(jDesc) !== -1 || jDesc.indexOf(qDesc.substring(0,Math.min(12,qDesc.length))) !== -1));
    var exactAmount = Math.abs(amount - tx.amount) <= 0.01;
    var score = Math.max(0,40 - days) + (bankMatch ? 30 : 0) + (textMatch ? 15 : 0) + (exactAmount ? 40 : 0) + (selectedMap[jurnalKey] ? 100 : 0);
    candidates.push({
      jurnalKey:jurnalKey,rowNumber:j.rowNumber,tanggal:j.tanggal,tanggalKey:j.tanggalKey,tipe:dir,
      noReferensi:j.noReferensi,namaKontak:j.namaKontak,akunKasBank:bank,
      akunLawan:dir === 'MASUK' ? j.akunKredit : j.akunDebit,keterangan:j.keterangan,
      nominal:amount,score:score,dateDiff:days,bankMatch:bankMatch ? 'YA' : 'TIDAK',selected:!!selectedMap[jurnalKey]
    });
  });
  candidates.sort(function(a,b){
    if (!!a.selected !== !!b.selected) return a.selected ? -1 : 1;
    return Number(b.score || 0) - Number(a.score || 0) || String(b.tanggalKey || '').localeCompare(String(a.tanggalKey || ''));
  });
  return { success:true,version:FIN_CFG.VERSION,tx:tx,candidates:candidates.slice(0,500),selectedKeys:selectedKeys,selectedTotal:selectedLinks.reduce(function(t,x){ return t + FIN_toNumber_(x.amount); },0) };
}


function FIN_linkBankStatementToJurnalsCore_(payload, auth) {
  payload = payload || {};
  auth = auth || FIN_RUNTIME_AUTH || FIN_requireAccess_();
  var txKey = String(payload.txKey || '').trim();
  var jurnalKeys = (payload.jurnalKeys || []).map(function(x){ return String(x || '').trim(); }).filter(Boolean);
  jurnalKeys = jurnalKeys.filter(function(x,i,a){ return a.indexOf(x) === i; });
  if (!txKey) throw new Error('Tx_Key mutasi bank wajib ada.');
  if (!jurnalKeys.length) throw new Error('Pilih minimal satu transaksi Finance.');
  FIN_setupBankReconLinkColumns_();
  FIN_setupBankReconMultiLink_();
  var lock = LockService.getDocumentLock();
  lock.waitLock(30000);
  try {
    var found = FIN_bankStatementFindByTxKey_(txKey);
    if (!found) throw new Error('Mutasi bank tidak ditemukan.');
    var tx = FIN_bankReconTxObject_(found.row);
    var maps = FIN_activeBankReconLinkMaps_();
    var journals = jurnalKeys.map(function(k){
      var used = maps.byJurnal[k];
      if (used && used.txKey !== txKey) throw new Error('Transaksi ' + k + ' sudah dicocokkan ke mutasi bank lain.');
      var j = FIN_findJurnalByMatchKey_(k);
      if (!j) throw new Error('Transaksi Finance tidak ditemukan: ' + k);
      var dir = FIN_bankReconDirectionFromJurnal_(j);
      if (!dir || dir !== tx.direction) throw new Error('Arah transaksi tidak sesuai untuk ' + (j.noReferensi || k) + '.');
      if (!FIN_accountLooksCash_(j.akunDebit) && !FIN_accountLooksCash_(j.akunKredit)) throw new Error('Transaksi bukan jurnal kas/bank: ' + (j.noReferensi || k));
      return { key:k,row:j.rowNumber,j:j,direction:dir,amount:FIN_toNumber_(j.nominal),bank:dir === 'MASUK' ? j.akunDebit : j.akunKredit };
    });
    var total = journals.reduce(function(t,x){ return t + x.amount; },0);
    if (Math.abs(total - tx.amount) > 0.01) throw new Error('Total transaksi terpilih ' + total + ' tidak sama dengan nominal mutasi bank ' + tx.amount + '.');

    var now = FIN_displayDateTime_(new Date());
    var group = FIN_reconGroupId_();
    var linkSh = FIN_bankReconLinkSheet_();
    var oldLinks = maps.byTx[txKey] || [];
    oldLinks.forEach(function(x){
      FIN_setByHeader_(linkSh,x.rowNumber,'Status','INACTIVE');
      FIN_setByHeader_(linkSh,x.rowNumber,'Notes','Diganti pencocokan pada ' + now + ' oleh ' + auth.email);
      if (jurnalKeys.indexOf(x.jurnalKey) === -1) FIN_setJurnalReconState_(x.jurnalKey,'','','','');
    });

    var rows = journals.map(function(x){ return {
      'Link_ID':FIN_reconLinkId_(txKey,x.key),'Recon_Group':group,'Bank_Tx_Key':txKey,
      'Jurnal_Key':x.key,'Jurnal_Row':x.row,'Direction':x.direction,'Amount':x.amount,
      'Bank_Account':tx.bankAccount,'Statement_Date':tx.dateKey,
      'Match_Method':payload.method || (journals.length > 1 ? 'MANUAL_MULTI' : 'MANUAL'),
      'Matched_At':now,'Matched_By':auth.email,'Status':'ACTIVE','Notes':payload.notes || ''
    }; });
    FIN_appendObjectsByHeaders_(linkSh,FIN_BANK_RECON_LINK_HEADERS,rows);
    journals.forEach(function(x){ FIN_setJurnalReconState_(x.key,txKey,'MATCHED',auth.email,now); });

    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Match_Status','MATCHED');
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Matched_Jurnal_Key',journals.length === 1 ? journals[0].key : ('MULTI:' + journals.length));
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Match_Method',payload.method || (journals.length > 1 ? 'MANUAL_MULTI' : 'MANUAL'));
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Matched_At',now);
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Matched_By',auth.email);
    FIN_touchMutation_('Bank recon matched ' + txKey + ' -> ' + journals.length + ' journals');
    return { success:true,message:'Mutasi bank cocok dengan ' + journals.length + ' transaksi Finance.',txKey:txKey,jurnalKeys:jurnalKeys,total:total,reconGroup:group };
  } finally { lock.releaseLock(); }
}

function FIN_linkBankStatementToJurnals(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  return FIN_linkBankStatementToJurnalsCore_(payload || {}, auth);
}

function FIN_linkBankStatementToJurnal(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  return FIN_linkBankStatementToJurnalsCore_({
    txKey:payload.txKey,
    jurnalKeys:[payload.jurnalKey],
    method:payload.method || 'MANUAL',
    notes:payload.notes || ''
  }, auth);
}


function FIN_unlinkBankStatement(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var txKey = String(payload.txKey || '').trim();
  if (!txKey) throw new Error('Tx_Key mutasi bank wajib ada.');
  FIN_setupBankReconLinkColumns_();
  FIN_setupBankReconMultiLink_();
  var lock = LockService.getDocumentLock();
  lock.waitLock(30000);
  try {
    var found = FIN_bankStatementFindByTxKey_(txKey);
    if (!found) throw new Error('Mutasi bank tidak ditemukan.');
    var now = FIN_displayDateTime_(new Date());
    var maps = FIN_activeBankReconLinkMaps_();
    var links = maps.byTx[txKey] || [];
    var linkSh = FIN_bankReconLinkSheet_();
    links.forEach(function(x){
      FIN_setByHeader_(linkSh,x.rowNumber,'Status','INACTIVE');
      FIN_setByHeader_(linkSh,x.rowNumber,'Notes','Dibatalkan pada ' + now + ' oleh ' + auth.email);
      FIN_setJurnalReconState_(x.jurnalKey,'','','','');
    });
    if (!links.length) {
      var legacy = String(FIN_val_(found.row,['Matched_Jurnal_Key']) || '').trim();
      if (legacy && !/^MULTI:/i.test(legacy)) FIN_setJurnalReconState_(legacy,'','','','');
    }
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Match_Status','UNMATCHED');
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Matched_Jurnal_Key','');
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Match_Method','');
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Matched_At','');
    FIN_setByHeader_(found.sheet,found.row._rowNumber,'Matched_By','');
    FIN_touchMutation_('Bank recon unmatched ' + txKey + ' by ' + auth.email);
    return { success:true,message:'Pencocokan dibatalkan untuk ' + links.length + ' transaksi.',txKey:txKey,unlinked:links.length };
  } finally { lock.releaseLock(); }
}

function FIN_createJurnalFromBankStatement(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  FIN_setupBankReconLinkColumns_();
  FIN_setupBankReconMultiLink_();
  var txKey = String(payload.txKey || '').trim();
  var akunLawan = String(payload.akunLawan || '').trim();
  if (!txKey) throw new Error('Tx_Key mutasi bank wajib ada.');
  if (!akunLawan) throw new Error('Akun lawan wajib dipilih.');
  var found = FIN_bankStatementFindByTxKey_(txKey);
  if (!found) throw new Error('Mutasi bank tidak ditemukan.');
  var activeLinks = FIN_activeBankReconLinkMaps_().byTx[txKey] || [];
  if (activeLinks.length) throw new Error('Mutasi bank ini sudah dicocokkan. Refresh daftar rekonsiliasi.');

  var r = found.row;
  var direction = String(FIN_val_(r, ['Direction']) || '').toUpperCase();
  if (direction !== 'MASUK' && direction !== 'KELUAR') throw new Error('Arah mutasi bank tidak valid.');
  var bank = String(FIN_val_(r, ['Bank_Account']) || '').trim() || FIN_defaultCashAccount_();
  if (FIN_cleanKey_(bank) === FIN_cleanKey_(akunLawan)) throw new Error('Akun lawan tidak boleh sama dengan akun bank.');
  var amount = FIN_toNumber_(FIN_val_(r, ['Amount'])) || FIN_toNumber_(FIN_val_(r, ['Debit'])) || FIN_toNumber_(FIN_val_(r, ['Credit']));
  if (!amount) throw new Error('Nominal mutasi bank kosong.');
  var dateKey = String(FIN_val_(r, ['Date_Key']) || FIN_dateKeySafe_(FIN_val_(r, ['Statement_Date'])) || FIN_dateKeySafe_(new Date())).substring(0, 10);
  var ref = String(payload.noReferensi || FIN_val_(r, ['Ref_No']) || ('BANK-' + txKey.substring(0, 8))).trim();
  var sourceKey = 'BANKSTMT_' + txKey;
  var inferredType = direction === 'MASUK' && FIN_accountMatch_(akunLawan, ['PIUTANG'])
    ? 'PEMBAYARAN_INVOICE'
    : (direction === 'KELUAR' && FIN_accountMatch_(akunLawan, ['HUTANG']) ? 'PEMBAYARAN_HUTANG' : (direction === 'KELUAR' ? 'BANK_KELUAR' : 'BANK_MASUK'));
  var row = {
    'Tanggal': dateKey,
    'Tipe Transaksi': payload.tipeTransaksi || inferredType,
    'No. Referensi': ref,
    'Nama Kontak': payload.namaKontak || '',
    'Keterangan': payload.keterangan || FIN_val_(r, ['Description']) || 'Jurnal dari mutasi bank',
    'Akun Debit': direction === 'KELUAR' ? akunLawan : bank,
    'Akun Kredit': direction === 'KELUAR' ? bank : akunLawan,
    'Nominal': amount,
    'Operator': auth.email,
    'Source_Key': sourceKey,
    'Auto_Flag': 'BANK_RECON_MANUAL',
    'Updated_At': FIN_displayDateTime_(new Date()),
    'Updated_By': auth.email,
    'Is_Deleted': ''
  };

  var writeMode = FIN_upsertJurnalBySourceKey_(sourceKey, row);
  try {
    var result = FIN_linkBankStatementToJurnalsCore_({
      txKey:txKey,
      jurnalKeys:[sourceKey],
      method:'CREATE_FROM_BANK',
      notes:'Jurnal dibuat dari popup rekonsiliasi bank.'
    }, auth);
    result.message = 'Jurnal dibuat dan langsung dicocokkan ke mutasi bank.';
    result.row = row;
    result.jurnalKey = sourceKey;
    result.writeMode = writeMode;
    if (inferredType === 'PEMBAYARAN_INVOICE' && ref && typeof FIN_resyncSalesInvoicePaymentFromJournals_ === 'function') {
      try { result.invoiceSync = FIN_resyncSalesInvoicePaymentFromJournals_(ref, auth.email); }
      catch (syncErr) { result.invoiceSyncWarning = syncErr.message || String(syncErr); }
    }
    return result;
  } catch (err) {
    if (writeMode === 'APPEND') {
      try {
        var rec = FIN_findJurnalRecordForMutation_(sourceKey);
        FIN_setByHeader_(rec.sheet, rec.rowNumber, 'Is_Deleted', 'TRUE');
        FIN_setByHeader_(rec.sheet, rec.rowNumber, 'Deleted_At', FIN_displayDateTime_(new Date()));
        FIN_setByHeader_(rec.sheet, rec.rowNumber, 'Deleted_By', auth.email);
        FIN_setByHeader_(rec.sheet, rec.rowNumber, 'Delete_Reason', 'Rollback karena gagal link mutasi bank: ' + (err.message || err));
      } catch (rollbackErr) {}
    }
    throw err;
  }
}

function FIN_autoMatchBankStatements(filter, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  filter = filter || {};
  var pass = arguments[arguments.length - 1] || '';
  var data = FIN_getBankStatementData(Object.assign({}, filter, { bankReconMode:filter.bankReconMode || 'PERIOD' }), auth.email, pass);
  var matched = 0, skipped = 0;
  (data.rows || []).forEach(function(r){
    if (FIN_cleanKey_(r.matchStatus || '') === 'MATCHED') return;
    try {
      var c = FIN_findBankReconCandidates({ txKey:r.txKey }, auth.email, pass);
      var exact = (c.candidates || []).filter(function(x){ return Number(x.score || 0) >= 92; });
      if (exact.length === 1) {
        FIN_linkBankStatementToJurnals({ txKey:r.txKey, jurnalKeys:[exact[0].jurnalKey], method:'AUTO' }, auth.email, pass);
        matched++;
      } else skipped++;
    } catch(e) { skipped++; }
  });
  return { success:true, matched:matched, skipped:skipped, message:'Auto match selesai. Match: ' + matched + ', dilewati: ' + skipped };
}

function FIN_bankStatementSheet_() {
  var ss = FIN_selfSs_();
  var sh = FIN_findBankStatementSheet_();
  if (!sh) sh = ss.insertSheet('Bank_Statement');
  FIN_ensureColumns_(sh, FIN_BANK_STATEMENT_HEADERS);
  FIN_applyBankStatementCompactFormats_(sh);
  return sh;
}

function FIN_applyBankStatementCompactFormats_(sh) {
  sh = sh || FIN_bankStatementSheet_();
  if (!sh || sh.getLastColumn() < 1) return;
  var table = FIN_readSheetTable_(sh);
  function setFmt(name, fmt) {
    var idx = table.map && table.map[FIN_headerKey_(name)];
    if (idx === undefined || idx === null) return;
    var rows = Math.max(1, sh.getMaxRows() - 1);
    sh.getRange(2, idx + 1, rows, 1).setNumberFormat(fmt);
  }
  ['Import_ID','Tx_Key','Upload_At','Date_Key','Bank_Account','Direction','Description','Ref_No','Source_File','Match_Status','Matched_Jurnal_Key','Match_Method','Matched_At','Matched_By','Notes','Created_By','Is_Deleted'].forEach(function(h){ setFmt(h, '@'); });
  ['Amount','Balance'].forEach(function(h){ setFmt(h, '#,##0.00'); });
  ['Row_No'].forEach(function(h){ setFmt(h, '0'); });
}

function FIN_setupBankReconLinkColumns_() {
  FIN_bankStatementSheet_();
  var j = FIN_selfSs_().getSheetByName(FIN_CFG.SHEET_JURNAL);
  if (j) FIN_ensureColumns_(j, FIN_JURNAL_RECON_HEADERS);
}

function FIN_bankStatementInferYear_(r) {
  var vals = [
    FIN_val_(r, ['Upload_At']), FIN_val_(r, ['Import_Date']), FIN_val_(r, ['Created_At']),
    FIN_val_(r, ['Source_File']), FIN_val_(r, ['Notes'])
  ].join(' ');
  var m = String(vals || '').match(/(?:19|20)\d{2}/);
  if (m) return Number(m[0]);
  return (new Date()).getFullYear();
}

function FIN_bankDateKeyLooksBad_(key) {
  key = String(key || '').trim();
  var m = key.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return true;
  var yy = Number(m[1]);
  return yy < 2020 || yy > ((new Date()).getFullYear() + 1);
}

function FIN_bankStatementDateKeyFromRow_(r) {
  var year = FIN_bankStatementInferYear_(r);
  var raw = FIN_val_(r, ['Raw_Date']);
  var key = raw ? FIN_bankDateKeyFromRaw_(raw, year) : '';
  if (!key || FIN_bankDateKeyLooksBad_(key)) {
    key = FIN_bankDateKeyFromRaw_(FIN_val_(r, ['Date_Key','Tanggal Key','Tanggal_Key']), year) || key;
  }
  if (!key || FIN_bankDateKeyLooksBad_(key)) {
    key = FIN_bankDateKeyFromRaw_(FIN_val_(r, ['Statement_Date','Tanggal','Date']), year) || key;
  }
  if (!key || FIN_bankDateKeyLooksBad_(key)) key = FIN_dateKeySafe_(new Date());
  return String(key || '').substring(0, 10);
}

function FIN_bankStatementMoneyFromRow_(r) {
  var rawAmount = FIN_val_(r, ['Raw_Amount','Jumlah','Nominal']);
  var rawType = FIN_val_(r, ['Raw_Type','Type','Tipe']);
  var rawDesc = FIN_val_(r, ['Raw_Description','Description','Keterangan']);
  var dirInfo = FIN_bankAmountDirection_(rawAmount, rawType, rawDesc);
  var debit = Math.abs(FIN_toNumber_(FIN_val_(r, ['Debit','Debet','Keluar','Raw_Debit'])) || 0);
  var credit = Math.abs(FIN_toNumber_(FIN_val_(r, ['Credit','Kredit','Masuk','Raw_Credit'])) || 0);
  var amount = Math.abs(FIN_toNumber_(FIN_val_(r, ['Amount','Jumlah','Nominal','Raw_Amount'])) || 0);
  var direction = String(FIN_val_(r, ['Direction','Tipe','Jenis']) || '').trim().toUpperCase();
  if (direction !== 'MASUK' && direction !== 'KELUAR') direction = dirInfo.direction || '';
  if (!direction) direction = credit > 0 ? 'MASUK' : debit > 0 ? 'KELUAR' : '';
  if (!amount) amount = credit || debit || 0;
  if (!debit && !credit && amount) {
    if (direction === 'KELUAR') debit = amount;
    else if (direction === 'MASUK') credit = amount;
  }
  return { direction:direction, amount:amount, debit:debit, credit:credit };
}

function FIN_bankStatementCompactObjectFromRow_(r) {
  var money = FIN_bankStatementMoneyFromRow_(r);
  var dateKey = FIN_bankStatementDateKeyFromRow_(r);
  return {
    'Import_ID': FIN_val_(r, ['Import_ID']) || '',
    'Tx_Key': FIN_val_(r, ['Tx_Key']) || FIN_bankStatementTxKey_(FIN_val_(r, ['Bank_Account']), dateKey, FIN_val_(r, ['Description','Raw_Description']), FIN_val_(r, ['Ref_No']), money.direction === 'KELUAR' ? money.amount : 0, money.direction === 'MASUK' ? money.amount : 0, FIN_val_(r, ['Balance','Raw_Balance']), FIN_val_(r, ['Source_File']), FIN_val_(r, ['Row_No'])),
    'Upload_At': FIN_val_(r, ['Upload_At']) || FIN_displayDateTime_(new Date()),
    'Date_Key': dateKey,
    'Bank_Account': FIN_val_(r, ['Bank_Account']) || FIN_defaultCashAccount_(),
    'Direction': money.direction,
    'Amount': money.amount,
    'Description': FIN_val_(r, ['Description','Raw_Description','Keterangan']) || 'Mutasi bank',
    'Ref_No': FIN_val_(r, ['Ref_No']) || '',
    'Balance': FIN_toNumber_(FIN_val_(r, ['Balance','Raw_Balance'])) || 0,
    'Source_File': FIN_val_(r, ['Source_File']) || '',
    'Row_No': FIN_toNumber_(FIN_val_(r, ['Row_No'])) || '',
    'Match_Status': FIN_val_(r, ['Match_Status']) || (FIN_val_(r, ['Matched_Jurnal_Key']) ? 'MATCHED' : 'UNMATCHED'),
    'Matched_Jurnal_Key': FIN_val_(r, ['Matched_Jurnal_Key']) || '',
    'Match_Method': FIN_val_(r, ['Match_Method']) || '',
    'Matched_At': FIN_val_(r, ['Matched_At']) || '',
    'Matched_By': FIN_val_(r, ['Matched_By']) || '',
    'Notes': FIN_val_(r, ['Notes']) || '',
    'Created_By': FIN_val_(r, ['Created_By']) || '',
    'Is_Deleted': FIN_val_(r, ['Is_Deleted']) || ''
  };
}

function FIN_importBankStatementParsed_(parsed, payload, auth, sourceType) {
  payload = payload || {};
  parsed = parsed || { rows:[] };
  if (!parsed.rows || !parsed.rows.length) throw new Error('File tidak berisi baris mutasi yang bisa dibaca.');
  var bankAccount = String(payload.bankAccount || '').trim() || FIN_defaultCashAccount_();
  var fileName = String(payload.fileName || 'bank_statement').trim();
  var importDate = FIN_dateKeySafe_(payload.importDate || new Date());
  var notes = String(payload.notes || '').trim();
  var importId = FIN_makeRef_('BST');

  var sh = FIN_bankStatementSheet_();
  var table = FIN_readSheetTable_(sh);
  var existing = {};
  (table.rows || []).forEach(function(r){ var k = String(FIN_val_(r, ['Tx_Key']) || '').trim(); if (k) existing[k] = true; });

  var uploadAt = FIN_displayDateTime_(new Date());
  var out = [];
  var skipped = 0;
  parsed.rows.forEach(function(row){
    var dateKey = String(row.dateKey || importDate).substring(0, 10);
    var debit = Math.abs(FIN_toNumber_(row.debit) || 0);
    var credit = Math.abs(FIN_toNumber_(row.credit) || 0);
    if (!debit && !credit) return;
    var txKey = FIN_bankStatementTxKey_(bankAccount, dateKey, row.description, row.refNo, debit, credit, row.balance, fileName, row.rowNo);
    if (existing[txKey]) { skipped++; return; }
    existing[txKey] = true;
    out.push({
      'Import_ID': importId,
      'Tx_Key': txKey,
      'Upload_At': uploadAt,
      'Date_Key': dateKey,
      'Bank_Account': bankAccount,
      'Direction': credit > 0 ? 'MASUK' : debit > 0 ? 'KELUAR' : '',
      'Amount': credit > 0 ? credit : debit,
      'Description': row.description || 'Mutasi bank',
      'Ref_No': row.refNo || '',
      'Balance': FIN_toNumber_(row.balance) || 0,
      'Source_File': fileName,
      'Row_No': row.rowNo || '',
      'Match_Status': 'UNMATCHED',
      'Matched_Jurnal_Key': '',
      'Match_Method': '',
      'Matched_At': '',
      'Matched_By': '',
      'Notes': notes || (parsed.verified ? 'PDF_VERIFIED' : (sourceType ? ('Import ' + sourceType) : '')),
      'Created_By': auth.email,
      'Is_Deleted': ''
    });
  });
  FIN_applyBankStatementCompactFormats_(sh);
  if (out.length) FIN_appendObjectsByHeaders_(sh, FIN_BANK_STATEMENT_HEADERS, out);
  FIN_applyBankStatementCompactFormats_(sh);
  FIN_touchMutation_('Import Bank_Statement ' + (sourceType || '') + ' compact ' + importId + ' by ' + auth.email);
  return {
    success:true,
    importId:importId,
    imported:out.length,
    skipped:skipped,
    totalParsed:parsed.rows.length,
    delimiter:parsed.delimiter || '',
    sourceType:sourceType || '',
    verified:!!parsed.verified,
    validation:parsed.validation || null,
    message:(sourceType || 'File') + ' bank terimport ke Bank_Statement compact: ' + out.length + ' baris' + (parsed.verified ? ' (terverifikasi)' : '') + '. Tidak masuk Data_Jurnal.'
  };
}

function FIN_importBankStatementCsv(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var csvText = String(payload.csvText || payload.content || '').replace(/^\uFEFF/, '');
  if (!csvText.trim()) throw new Error('Isi CSV kosong/tidak terbaca.');
  var parsed = FIN_parseBankStatementCsv_(csvText);
  return FIN_importBankStatementParsed_(parsed, payload, auth, 'CSV');
}

function FIN_importBankStatementFile(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var fileName = String(payload.fileName || '').trim();
  var lower = fileName.toLowerCase();
  var fileType = String(payload.fileType || '').toUpperCase();
  var mime = String(payload.mimeType || '').toLowerCase();
  if (fileType === 'PDF' || lower.slice(-4) === '.pdf' || mime === 'application/pdf') {
    return FIN_importBankStatementPdf(payload, auth.email, arguments[arguments.length - 1] || '');
  }
  // TXT diperlakukan seperti CSV karena parser sudah auto-detect delimiter.
  return FIN_importBankStatementCsv(payload, auth.email, arguments[arguments.length - 1] || '');
}

function FIN_importBankStatementPdf(payload, emailOp, pasporOp) {
  var auth = FIN_requirePassportFromArgs_(arguments);
  payload = payload || {};
  var parsed;
  if (payload.pdfLayout) {
    parsed = FIN_parseBankStatementPdfLayout_(payload.pdfLayout);
  } else {
    var text = String(payload.pdfText || payload.text || '').trim();
    if (!text) text = FIN_extractTextFromBankPdf_(payload);
    parsed = FIN_parseBankStatementText_(text);
  }
  parsed = FIN_finalizeVerifiedBankPdf_(parsed);
  return FIN_importBankStatementParsed_(parsed, payload, auth, 'PDF_VERIFIED');
}

function FIN_extractTextFromBankPdf_(payload) {
  payload = payload || {};
  var fileName = String(payload.fileName || 'bank_statement.pdf').trim();
  var base64 = String(payload.base64 || payload.fileBase64 || '').replace(/^data:application\/pdf;base64,/, '').trim();
  if (!base64) throw new Error('PDF belum terbaca. Upload ulang file PDF atau gunakan CSV.');
  if (typeof Drive === 'undefined' || !Drive.Files) {
    throw new Error('Import PDF membutuhkan Advanced Google Service: Drive API. Aktifkan Services > Drive API di Apps Script, atau upload mutasi bank dalam format CSV.');
  }
  var tmpId = '';
  try {
    var bytes = Utilities.base64Decode(base64);
    var blob = Utilities.newBlob(bytes, 'application/pdf', fileName);
    var created = FIN_driveCreateGoogleDocFromPdf_(blob, fileName);
    tmpId = created && created.id;
    if (!tmpId) throw new Error('Drive OCR/konversi tidak mengembalikan file hasil konversi.');
    Utilities.sleep(1200);
    var text = DocumentApp.openById(tmpId).getBody().getText();
    if (tmpId) DriveApp.getFileById(tmpId).setTrashed(true);
    if (!String(text || '').trim()) throw new Error('PDF berhasil dibaca tetapi teks mutasi kosong. Gunakan CSV jika PDF berupa scan/gambar yang tidak terbaca OCR.');
    return text;
  } catch (err) {
    try { if (tmpId) DriveApp.getFileById(tmpId).setTrashed(true); } catch(e) {}
    throw new Error('Gagal membaca PDF mutasi bank: ' + (err && err.message ? err.message : err));
  }
}

function FIN_driveCreateGoogleDocFromPdf_(blob, fileName) {
  var baseName = 'FIN_BANK_OCR_' + Date.now() + '_' + String(fileName || 'bank_statement.pdf');
  // Apps Script Advanced Drive Service bisa berada di Drive API v2 atau v3.
  // v2 memakai Files.insert(), v3 memakai Files.create(). Pakai yang tersedia.
  if (Drive.Files && typeof Drive.Files.create === 'function') {
    return Drive.Files.create(
      { name: baseName, mimeType: 'application/vnd.google-apps.document' },
      blob,
      { ocrLanguage: 'id' }
    );
  }
  if (Drive.Files && typeof Drive.Files.insert === 'function') {
    return Drive.Files.insert(
      { title: baseName, mimeType: 'application/vnd.google-apps.document' },
      blob,
      { ocr: true, ocrLanguage: 'id', convert: true }
    );
  }
  throw new Error('Drive API aktif, tetapi method Files.create/Files.insert tidak tersedia. Aktifkan Advanced Google Service Drive API ulang.');
}

/**
 * Ambil tahun periode dari teks mutasi bank/PDF.
 * Mendukung contoh:
 * - PERIODE : JANUARI 2026
 * - Periode : 01/06/2026 - 30/06/2026
 * - Period January 2026
 * Fallback terakhir: tahun 19xx/20xx pertama pada bagian awal dokumen.
 */
function FIN_bankTextPeriodYear_(lines) {
  var scan = (lines || []).slice(0, 120).join(' ').replace(/\s+/g, ' ').trim();
  if (!scan) return 0;

  // Rentang/full date setelah kata periode/from-to.
  var mFullDate = scan.match(/(?:PERIODE|PERIOD|DARI|FROM|SAMPAI|TO)[^\d]{0,40}\d{1,2}[\/-]\d{1,2}[\/-]((?:19|20)\d{2})/i);
  if (mFullDate) return Number(mFullDate[1]);

  // Nama bulan Indonesia/Inggris, contoh "PERIODE : JANUARI 2026".
  var months = '(?:JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER|OKTOBER|NOVEMBER|DESEMBER|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|OCTOBER|DECEMBER)';
  var mMonthYear = scan.match(new RegExp('(?:PERIODE|PERIOD)?[^A-Z0-9]{0,20}' + months + '[^0-9]{0,10}((?:19|20)\\d{2})', 'i'));
  if (mMonthYear) return Number(mMonthYear[1]);

  var years = scan.match(/(?:19|20)\d{2}/g) || [];
  return years.length ? Number(years[0]) : 0;
}

function FIN_parseBankStatementText_(text) {
  text = String(text || '').replace(/\r/g, '\n');
  var lines = text.split('\n').map(function(x){ return String(x || '').trim(); }).filter(Boolean);
  var defaultYear = FIN_bankTextPeriodYear_(lines) || (new Date()).getFullYear();
  var rows = FIN_parseBankStatementTextBlocks_(lines, defaultYear);
  // Fallback untuk format PDF/TXT yang ternyata satu transaksi per baris.
  if (!rows.length) {
    rows = lines.map(function(line, idx){ return FIN_parseBankStatementTextLine_(line, defaultYear, idx + 1); }).filter(Boolean);
  }
  return { delimiter:'TEXT/PDF', rows:rows, defaultYear:defaultYear, summary:FIN_bankPdfSummaryFromText_(text) };
}

function FIN_parseBankStatementTextBlocks_(lines, defaultYear) {
  var out = [];
  var current = null;
  function flush_() {
    if (!current || !current.lines || !current.lines.length) return;
    var row = FIN_parseBankStatementTextBlock_(current.lines, defaultYear, current.rowNo);
    if (row) out.push(row);
  }
  (lines || []).forEach(function(line, idx){
    var clean = String(line || '').trim();
    if (!clean) return;
    if (FIN_bankPdfNoiseLine_(clean)) return;
    var startsWithDate = /^\d{1,2}[\/-]\d{1,2}(?:[\/-]\d{2,4})?\b/.test(clean);
    if (startsWithDate) {
      // Baris saldo dan total periode bukan mutasi transaksi.
      if (/SALDO\s+(AWAL|AKHIR)|MUTASI\s+(CR|DB)/i.test(clean)) return;
      flush_();
      current = { rowNo: idx + 1, lines: [clean] };
    } else if (current) {
      current.lines.push(clean);
    }
  });
  flush_();
  return out;
}

function FIN_bankPdfNoiseLine_(line) {
  var u = String(line || '').toUpperCase();
  if (/^(REKENING|KCP|SIDIK PERMANA|MARGAASIH|DESA |KP |BANDUNG|INDONESIA|NO\. REKENING|HALAMAN|PERIODE|MATA UANG|CATATAN|TANGGAL\s+KETERANGAN|BERSAMBUNG)/.test(u)) return true;
  if (/NASABAH|LAPORAN MUTASI|BCA BERHAK|KOREKSI/.test(u)) return true;
  if (/^\d+\s*\/\s*\d+$/.test(u)) return true;
  if (/^[•\-]+$/.test(u)) return true;
  return false;
}

function FIN_parseBankStatementTextBlock_(blockLines, defaultYear, rowNo) {
  var full = (blockLines || []).join(' ').replace(/\s+/g, ' ').trim();
  if (!full) return null;
  var dateMatch = full.match(/^\d{1,2}[\/-]\d{1,2}(?:[\/-]\d{2,4})?/);
  if (!dateMatch) return null;
  var dateKey = FIN_bankDateKeyFromRaw_(dateMatch[0], defaultYear);
  if (!dateKey) return null;
  var upper = full.toUpperCase();
  if (/SALDO\s+(AWAL|AKHIR)|MUTASI\s+(CR|DB)/.test(upper)) return null;
  var explicitDb = /\b(DB|DEBET|DEBIT|KELUAR)\b/.test(upper);
  var explicitCr = /\b(CR|CREDIT|KREDIT|MASUK)\b/.test(upper);
  var direction = explicitDb ? 'KELUAR' : 'MASUK';
  if (!explicitDb && explicitCr) direction = 'MASUK';

  var dbcr = FIN_bankAmountMarkerMatches_(full);
  var amount = 0;
  var balance = 0;
  if (dbcr.length) {
    var chosen = dbcr[dbcr.length - 1];
    direction = chosen.marker === 'DB' ? 'KELUAR' : 'MASUK';
    amount = Math.abs(FIN_toNumber_(chosen.amount));
    balance = FIN_toNumber_(chosen.balance);
  } else {
    var nums = FIN_bankTextNumberTokens_(full).map(function(x){ return x.text; });
    nums = nums.filter(function(x){ return FIN_toNumber_(x) !== 0; });
    if (!nums.length) return null;
    if (nums.length >= 2 && FIN_bankBlockLooksLikeHasBalance_(full)) {
      amount = Math.abs(FIN_toNumber_(nums[nums.length - 2]));
      balance = FIN_toNumber_(nums[nums.length - 1]);
    } else {
      amount = Math.abs(FIN_toNumber_(nums[nums.length - 1]));
      balance = 0;
    }
  }
  if (!amount) return null;
  var desc = full.replace(dateMatch[0], ' ');
  FIN_bankTextNumberTokens_(desc).forEach(function(tok){
    desc = desc.replace(tok.text, ' ');
  });
  desc = desc.replace(/\b(DB|DEBET|DEBIT|D\s?B|KELUAR|CR|CREDIT|KREDIT|C\s?R|MASUK)\b/ig, ' ')
             .replace(/\s+/g, ' ').trim();
  if (!desc) desc = 'Mutasi bank';
  return {
    rowNo: rowNo,
    dateKey: dateKey,
    description: desc,
    refNo: FIN_bankTextRefNo_(full),
    debit: direction === 'KELUAR' ? amount : 0,
    credit: direction === 'MASUK' ? amount : 0,
    balance: balance
  };
}

function FIN_bankAmountMarkerMatches_(s) {
  var out = [];
  var re = /((?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{2})?)\s*(DB|CR)\b(?:\s+((?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{2})?))?/ig;
  var m;
  while ((m = re.exec(String(s || ''))) !== null) {
    out.push({ amount: m[1], marker: String(m[2] || '').toUpperCase(), balance: m[3] || '' });
  }
  return out;
}

function FIN_bankBlockLooksLikeHasBalance_(full) {
  // PDF BCA biasanya menampilkan saldo setelah nilai mutasi pada akhir blok.
  // Kalau angka terakhir berada dekat akhir teks, anggap itu saldo.
  var tokens = FIN_bankTextNumberTokens_(full);
  if (tokens.length < 2) return false;
  var last = tokens[tokens.length - 1];
  return (String(full || '').length - (last.index || 0)) < 30;
}

function FIN_parseBankStatementTextLine_(line, defaultYear, rowNo) {
  var dateMatch = line.match(/\b\d{1,2}[\/-]\d{1,2}(?:[\/-]\d{2,4})?\b|\b(?:19|20)\d{2}[\/-]\d{1,2}[\/-]\d{1,2}\b/);
  if (!dateMatch) return null;
  return FIN_parseBankStatementTextBlock_([line], defaultYear, rowNo);
}

function FIN_bankTextNumberTokens_(s) {
  var out = [];
  var re = /(?:^|\s)([-+]?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|[-+]?\d+(?:[.,]\d{2}))(?:\s|$)/g;
  var m;
  while ((m = re.exec(String(s || ''))) !== null) {
    out.push({ text:String(m[1] || '').trim(), index:m.index });
  }
  return out;
}

function FIN_bankTextRefNo_(line) {
  var m = String(line || '').match(/\b(?:FTSCY|WS|TRX|REF|ID)[A-Z0-9\/\-_.]*\b/i);
  return m ? m[0] : '';
}


/* ================= PDF LAYOUT VERIFIED IMPORT v1.8.5 ================= */

function FIN_pdfLayoutObject_(layout) {
  if (!layout) return { pages:[] };
  if (typeof layout === 'string') {
    try { layout = JSON.parse(layout); } catch (e) { throw new Error('Struktur PDF tidak valid. Upload ulang file.'); }
  }
  return layout && layout.pages ? layout : { pages:[] };
}

function FIN_pdfLayoutRowText_(row) {
  return ((row && row.cells) || []).map(function(c){ return String(c && c.t || '').trim(); }).filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}

function FIN_pdfMoneyText_(value) {
  var s = String(value || '').trim();
  return /^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})$/.test(s) ? s : '';
}

function FIN_pdfPlainNumericText_(value) {
  return /^\d+(?:\.\d{2})?$/.test(String(value || '').trim());
}

function FIN_pdfCellsInRange_(row, minX, maxX) {
  return ((row && row.cells) || []).filter(function(c){
    var x = Number(c && c.x || 0);
    return x >= minX && x < maxX;
  });
}

function FIN_pdfLayoutSummary_(pages) {
  var result = { opening:0, closing:0, crTotal:0, crCount:0, dbTotal:0, dbCount:0 };
  (pages || []).forEach(function(page){
    (page.rows || []).forEach(function(row){
      var text = FIN_pdfLayoutRowText_(row);
      var key = FIN_cleanKey_(text);
      if (!key) return;
      var monies = ((row && row.cells) || []).map(function(c){ return FIN_pdfMoneyText_(c.t); }).filter(Boolean);
      var integers = ((row && row.cells) || []).map(function(c){ return String(c && c.t || '').trim(); }).filter(function(t){ return /^\d+$/.test(t); });
      if (key.indexOf('SALDOAWAL') !== -1 && monies.length) result.opening = FIN_toNumber_(monies[monies.length - 1]);
      if (key.indexOf('SALDOAKHIR') !== -1 && monies.length) result.closing = FIN_toNumber_(monies[monies.length - 1]);
      if (key.indexOf('MUTASICR') !== -1) {
        if (monies.length) result.crTotal = FIN_toNumber_(monies[monies.length - 1]);
        if (integers.length) result.crCount = Number(integers[integers.length - 1]) || 0;
      }
      if (key.indexOf('MUTASIDB') !== -1) {
        if (monies.length) result.dbTotal = FIN_toNumber_(monies[monies.length - 1]);
        if (integers.length) result.dbCount = Number(integers[integers.length - 1]) || 0;
      }
    });
  });
  return result;
}

function FIN_bankPdfSummaryFromText_(text) {
  var flat = String(text || '').replace(/\r/g, ' ').replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
  var out = { opening:0, closing:0, crTotal:0, crCount:0, dbTotal:0, dbCount:0 };
  function money(re){ var m = flat.match(re); return m ? FIN_toNumber_(m[1]) : 0; }
  function count(re){ var m = flat.match(re); return m ? Number(m[1]) || 0 : 0; }
  out.opening = money(/SALDO\s+AWAL\s*:?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2}))/i);
  out.closing = money(/SALDO\s+AKHIR\s*:?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2}))/i);
  out.crTotal = money(/MUTASI\s+CR\s*:?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2}))/i);
  out.dbTotal = money(/MUTASI\s+DB\s*:?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2}))/i);
  out.crCount = count(/MUTASI\s+CR\s*:?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})\s+(\d+)/i);
  out.dbCount = count(/MUTASI\s+DB\s*:?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})\s+(\d+)/i);
  return out;
}

function FIN_pdfLayoutPeriodYear_(pages) {
  var lines = [];
  (pages || []).slice(0, 3).forEach(function(page){
    (page.rows || []).slice(0, 80).forEach(function(row){ lines.push(FIN_pdfLayoutRowText_(row)); });
  });
  return FIN_bankTextPeriodYear_(lines) || (new Date()).getFullYear();
}

function FIN_pdfRowDate_(row, pageWidth) {
  var maxDateX = Number(pageWidth || 595) * 0.15;
  var cells = FIN_pdfCellsInRange_(row, 0, maxDateX);
  for (var i=0; i<cells.length; i++) {
    var t = String(cells[i].t || '').trim();
    if (/^\d{1,2}[\/-]\d{1,2}$/.test(t)) return t;
  }
  return '';
}

function FIN_pdfRowHasSummary_(row) {
  var key = FIN_cleanKey_(FIN_pdfLayoutRowText_(row));
  return key.indexOf('MUTASICR') !== -1 || key.indexOf('MUTASIDB') !== -1 || key.indexOf('SALDOAKHIR') !== -1 || (key.indexOf('SALDOAWAL') !== -1 && !FIN_pdfRowDate_(row, 595));
}

function FIN_pdfDescriptionChunk_(row, pageWidth, amount) {
  var w = Number(pageWidth || 595);
  var cells = FIN_pdfCellsInRange_(row, w * 0.13, w * 0.60);
  var text = cells.map(function(c){ return String(c.t || '').trim(); }).filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  if (/^(?:REKENING|KCP|NO\.?\s*REKENING|HALAMAN|PERIODE|MATA\s+UANG|CATATAN|TANGGAL\s+KETERANGAN|BERSAMBUNG)/i.test(text)) return '';
  if (/^\d+(?:\.\d{2})?$/.test(text) && Math.abs(FIN_toNumber_(text) - Number(amount || 0)) < 0.01) return '';
  return text;
}

function FIN_pdfRefNo_(description) {
  var s = String(description || '');
  var m = s.match(/\b\d{4}\/[A-Z0-9]+\/[A-Z0-9._-]+\b/i);
  if (m) return m[0];
  m = s.match(/\b(?:FTSCY|FTFVA|WS|BIF|TRX|REF|ID)[A-Z0-9\/\-_.]*\b/i);
  return m ? m[0] : '';
}

function FIN_parseBankStatementPdfLayout_(layout) {
  layout = FIN_pdfLayoutObject_(layout);
  var pages = layout.pages || [];
  if (!pages.length) throw new Error('Struktur halaman PDF kosong. Upload ulang file.');
  var year = FIN_pdfLayoutPeriodYear_(pages);
  var summary = FIN_pdfLayoutSummary_(pages);
  var rows = [];
  var seq = 0;

  pages.forEach(function(page){
    var pageWidth = Number(page.width || 595);
    var pageRows = page.rows || [];
    var starts = [];
    pageRows.forEach(function(row, idx){
      var rawDate = FIN_pdfRowDate_(row, pageWidth);
      if (rawDate) starts.push({ idx:idx, rawDate:rawDate });
    });

    starts.forEach(function(start, startIdx){
      var row = pageRows[start.idx];
      var end = startIdx + 1 < starts.length ? starts[startIdx + 1].idx : pageRows.length;
      var startText = FIN_pdfLayoutRowText_(row);
      if (/SALDO\s+AWAL/i.test(startText)) return;

      var amountCells = FIN_pdfCellsInRange_(row, pageWidth * 0.60, pageWidth * 0.82);
      var amountText = '';
      for (var ai=0; ai<amountCells.length; ai++) {
        amountText = FIN_pdfMoneyText_(amountCells[ai].t);
        if (amountText) break;
      }
      var amount = Math.abs(FIN_toNumber_(amountText));
      if (!amount) return;

      var amountZone = amountCells.map(function(c){ return String(c.t || ''); }).join(' ').toUpperCase();
      var headerZone = FIN_pdfDescriptionChunk_(row, pageWidth, amount).toUpperCase();
      var direction = /\bDB\b/.test(amountZone) || /\bDEBIT\b/.test(headerZone) ? 'KELUAR' : 'MASUK';

      var balanceCells = FIN_pdfCellsInRange_(row, pageWidth * 0.82, pageWidth + 1);
      var printedBalance = 0;
      balanceCells.forEach(function(c){ var mt = FIN_pdfMoneyText_(c.t); if (mt) printedBalance = FIN_toNumber_(mt); });

      var descParts = [];
      var firstDesc = FIN_pdfDescriptionChunk_(row, pageWidth, amount);
      if (firstDesc) descParts.push(firstDesc);
      for (var ri=start.idx + 1; ri<end; ri++) {
        if (FIN_pdfRowHasSummary_(pageRows[ri])) break;
        var chunk = FIN_pdfDescriptionChunk_(pageRows[ri], pageWidth, amount);
        if (chunk) descParts.push(chunk);
      }
      var description = descParts.join(' ').replace(/\s+/g, ' ').trim();
      description = description.replace(/\b(?:SALDO\s+AWAL|SALDO\s+AKHIR|MUTASI\s+CR|MUTASI\s+DB)\b.*$/i, '').trim();
      if (!description) description = 'Mutasi bank';

      seq++;
      rows.push({
        rowNo:seq,
        pageNo:Number(page.page || 0),
        dateKey:FIN_bankDateKeyFromRaw_(start.rawDate, year),
        description:description,
        refNo:FIN_pdfRefNo_(description),
        debit:direction === 'KELUAR' ? amount : 0,
        credit:direction === 'MASUK' ? amount : 0,
        balance:0,
        printedBalance:printedBalance
      });
    });
  });

  return { delimiter:'PDFJS_LAYOUT', rows:rows, defaultYear:year, summary:summary, engine:String(layout.engine || 'PDFJS_LAYOUT') };
}

function FIN_finalizeVerifiedBankPdf_(parsed) {
  parsed = parsed || { rows:[] };
  var rows = parsed.rows || [];
  var s = parsed.summary || {};
  var required = Number(s.opening) && Number(s.closing) && Number(s.crCount) && Number(s.dbCount) && Number(s.crTotal) && Number(s.dbTotal);
  if (!required) {
    throw new Error('PDF tidak disimpan karena ringkasan SALDO AWAL/MUTASI CR/MUTASI DB/SALDO AKHIR tidak terbaca lengkap. Gunakan CSV atau PDF e-statement asli.');
  }

  var actualCrCount = 0, actualDbCount = 0, actualCrTotal = 0, actualDbTotal = 0;
  var lastDate = '';
  var running = Number(s.opening || 0);
  var printedMismatch = [];
  rows.forEach(function(r, idx){
    var dateKey = String(r.dateKey || '');
    if (lastDate && dateKey < lastDate) throw new Error('PDF tidak disimpan karena urutan tanggal transaksi tidak konsisten pada baris ' + (idx + 1) + '.');
    lastDate = dateKey;
    var debit = Math.abs(FIN_toNumber_(r.debit) || 0);
    var credit = Math.abs(FIN_toNumber_(r.credit) || 0);
    if (credit > 0) { actualCrCount++; actualCrTotal += credit; running += credit; }
    else if (debit > 0) { actualDbCount++; actualDbTotal += debit; running -= debit; }
    r.balance = Math.round(running * 100) / 100;
    var printed = FIN_toNumber_(r.printedBalance);
    if (printed && Math.abs(printed - r.balance) > 0.05) printedMismatch.push({ row:idx + 1, expected:r.balance, printed:printed });
  });

  function closeEnough(a,b){ return Math.abs(Number(a || 0) - Number(b || 0)) <= 0.05; }
  var errors = [];
  if (actualCrCount !== Number(s.crCount)) errors.push('CR ' + actualCrCount + '/' + s.crCount + ' transaksi');
  if (actualDbCount !== Number(s.dbCount)) errors.push('DB ' + actualDbCount + '/' + s.dbCount + ' transaksi');
  if (!closeEnough(actualCrTotal, s.crTotal)) errors.push('total CR ' + actualCrTotal + '/' + s.crTotal);
  if (!closeEnough(actualDbTotal, s.dbTotal)) errors.push('total DB ' + actualDbTotal + '/' + s.dbTotal);
  if (!closeEnough(running, s.closing)) errors.push('saldo akhir ' + running + '/' + s.closing);
  if (printedMismatch.length) errors.push('saldo cetak tidak cocok pada ' + printedMismatch.length + ' baris');
  if (errors.length) {
    throw new Error('PDF tidak disimpan karena verifikasi gagal: ' + errors.join('; ') + '. Tidak ada data yang ditulis ke Bank_Statement.');
  }

  parsed.validation = {
    verified:true,
    opening:Number(s.opening),
    closing:Number(s.closing),
    crCount:actualCrCount,
    dbCount:actualDbCount,
    crTotal:Math.round(actualCrTotal * 100) / 100,
    dbTotal:Math.round(actualDbTotal * 100) / 100
  };
  parsed.verified = true;
  return parsed;
}

function CLEANUP_removeLastUnmatchedPdfBankImport() {
  FIN_requireAccess_();
  var sh = FIN_bankStatementSheet_();
  var table = FIN_readSheetTable_(sh);
  var rows = (table.rows || []).filter(function(r){
    var source = String(FIN_val_(r, ['Source_File']) || '').toLowerCase();
    var status = FIN_cleanKey_(FIN_val_(r, ['Match_Status']) || 'UNMATCHED');
    return source.slice(-4) === '.pdf' && status !== 'MATCHED' && String(FIN_val_(r, ['Is_Deleted']) || '').toUpperCase() !== 'TRUE';
  });
  if (!rows.length) return { success:true, removed:0, message:'Tidak ada import PDF UNMATCHED yang bisa dibersihkan.' };
  rows.sort(function(a,b){ return Number(b._rowNumber || 0) - Number(a._rowNumber || 0); });
  var latestImport = String(FIN_val_(rows[0], ['Import_ID']) || '');
  var targets = rows.filter(function(r){ return String(FIN_val_(r, ['Import_ID']) || '') === latestImport; });
  targets.forEach(function(r){ sh.deleteRow(Number(r._rowNumber)); });
  FIN_touchMutation_('Cleanup last unmatched PDF bank import ' + latestImport);
  return { success:true, removed:targets.length, importId:latestImport, message:'Import PDF terakhir dibersihkan: ' + targets.length + ' baris.' };
}


function FIN_getBankStatementData(filter, emailOp, pasporOp) {
  FIN_requirePassportFromArgs_(arguments);
  filter = filter || {};
  var range = FIN_rangeFromPeriodArg_(filter);
  var mode = String(filter.bankReconMode || filter.reconMode || 'UNMATCHED').toUpperCase();
  var onlyUnmatched = mode.indexOf('UNMATCHED') !== -1;
  var periodOnly = mode === 'PERIOD' || mode === 'UNMATCHED_PERIOD';
  var sh = FIN_bankStatementSheet_();
  FIN_setupBankReconMultiLink_();
  var maps = FIN_activeBankReconLinkMaps_();
  var table = FIN_readSheetTable_(sh);
  var meta = FIN_bankStatementMeta_(sh);
  var rows = (table.rows || []).map(function(r){
    var obj = FIN_bankStatementCompactObjectFromRow_(r);
    var amount = FIN_toNumber_(obj.Amount);
    var links = maps.byTx[String(obj.Tx_Key || '').trim()] || [];
    var matchedTotal = links.reduce(function(t,x){ return t + FIN_toNumber_(x.amount); },0);
    var matched = links.length > 0 || FIN_cleanKey_(obj.Match_Status || '') === 'MATCHED';
    return {
      rowNumber:r._rowNumber,importId:obj.Import_ID,txKey:obj.Tx_Key,uploadAt:obj.Upload_At,
      dateKey:obj.Date_Key,statementDate:FIN_displayDate_(obj.Date_Key),bankAccount:obj.Bank_Account,
      description:obj.Description,refNo:obj.Ref_No,direction:obj.Direction,amount:amount,
      debit:obj.Direction === 'KELUAR' ? amount : 0,credit:obj.Direction === 'MASUK' ? amount : 0,
      keluar:obj.Direction === 'KELUAR' ? amount : 0,masuk:obj.Direction === 'MASUK' ? amount : 0,
      balance:FIN_toNumber_(obj.Balance),sourceFile:obj.Source_File,
      matchStatus:matched ? 'MATCHED' : 'UNMATCHED',matchedJurnalKey:obj.Matched_Jurnal_Key,
      matchedJurnalKeys:links.map(function(x){ return x.jurnalKey; }),matchedCount:links.length || (matched ? 1 : 0),
      matchedTotal:links.length ? matchedTotal : (matched ? amount : 0),
      matchMethod:obj.Match_Method,matchedAt:obj.Matched_At,matchedBy:obj.Matched_By,
      notes:obj.Notes,isDeleted:obj.Is_Deleted
    };
  }).filter(function(r){
    if (String(r.isDeleted || '').toUpperCase() === 'TRUE') return false;
    if (periodOnly && r.dateKey && !FIN_isDateKeyInRange_(r.dateKey,range)) return false;
    if (onlyUnmatched && FIN_cleanKey_(r.matchStatus || 'UNMATCHED') === 'MATCHED') return false;
    return true;
  });
  rows.sort(function(a,b){ return String(b.dateKey || '').localeCompare(String(a.dateKey || '')) || String(b.txKey || '').localeCompare(String(a.txKey || '')); });
  var totalMasuk = FIN_sum_(rows,'masuk'), totalKeluar = FIN_sum_(rows,'keluar');
  var unmatched = rows.filter(function(r){ return FIN_cleanKey_(r.matchStatus || 'UNMATCHED') !== 'MATCHED'; }).length;
  return { success:true,version:FIN_CFG.VERSION,mode:mode,dateStart:range.startKey,dateEnd:range.endKey,
    sourceSheet:meta.sheetName,sourceMeta:meta,headers:FIN_BANK_STATEMENT_HEADERS,rows:rows.slice(0,1000),
    summary:{ mode:mode,sourceSheet:meta.sheetName,sourceLastRow:meta.lastRow,sourceDataRows:meta.dataRows,totalRows:rows.length,
      returnedRows:Math.min(rows.length,1000),totalMasuk:totalMasuk,totalKeluar:totalKeluar,unmatched:unmatched,compactHeaders:FIN_BANK_STATEMENT_HEADERS.length }
  };
}