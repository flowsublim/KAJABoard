/**
 * MODUL FINANCE / KEUANGAN CV KIRAL
 * Version: v1.9.3.4 COGM Asset Separation
 * Stack: Google Apps Script + Google Sheets
 *
 * Prinsip desain:
 * - Data_Jurnal hanya untuk kas/bank dan jurnal penyesuaian/manual yang tidak punya source module.
 * - Laporan Finance membaca sheet modul terkait secara read-only; data source module tidak dipindahkan ke Data_Jurnal.
 * - Piutang dibaca dari Modul Penjualan/Omni + Data_Jurnal untuk pembayaran/penyesuaian saja.
 * - Hutang dibaca dari Modul Purchasing + Data_Jurnal untuk pembayaran/penyesuaian saja.
 * - Produksi nanti membaca Data_Jurnal Finance untuk BOP/overhead produksi.
 */

var FIN_CFG = {
  MASTER_SPREADSHEET_ID: '1bbtCMQfK5p_2c5GzIkTIrcIPcPsm3Wjh_R8PfAagu6I',
  MODULE_ALIASES: ['FIN', 'FINANCE', 'KEUANGAN'],
  MODULE_CODE: 'FIN',
  MODULE_NAME: 'Finance',
  VERSION: '1.9.3.4',
  SESSION_TTL_MS: 6 * 60 * 60 * 1000,
  SHARED_SECRET: 'CV_KIRAL_FLOW_SUBLIM_STYLE_FIXED_SECRET_2026_KIRAL',
  HEARTBEAT_CELL: 'J1',
  HEARTBEAT_UPDATED_CELL: 'J2',
  HEARTBEAT_NOTES_CELL: 'J3',
  MASTER_USER_SHEET: 'Master_User',
  MASTER_MODULE_SHEET: 'Master_Module',
  LOG_LOGIN_SHEET: 'Log_Login',
  PORTAL_CODES: ['PORTAL', 'PRTL', 'HOME', 'BERANDA'],
  SHEET_JURNAL: 'Data_Jurnal',
  SHEET_LOCK: 'Data_Lock_Period',
  TZ: Session.getScriptTimeZone() || 'Asia/Jakarta'
};

var ERP_GLOBAL_CFG = FIN_CFG;
var FIN_RUNTIME_AUTH = null;
var FIN_RUNTIME_COA_CACHE = null;

var FIN_HEADERS = {
  JURNAL: [
    'Tanggal',
    'Tipe Transaksi',
    'No. Referensi',
    'Nama Kontak',
    'Keterangan',
    'Akun Debit',
    'Akun Kredit',
    'Nominal',
    'Operator',
    'Source_Key',
    'Auto_Flag',
    'Updated_At',
    'Updated_By',
    'Is_Deleted',
    'Deleted_At',
    'Deleted_By',
    'Delete_Reason'
  ],
  LOCK: ['Period_Key', 'Start_Date', 'End_Date', 'Status', 'Locked_By', 'Locked_At', 'Notes'],
  COA: ['COA_ID', 'Account_Code', 'Account_Name', 'Account_Type', 'Normal_Balance', 'Parent_Code', 'Is_Posting', 'Status', 'Notes', 'Account_Group']
};

var FIN_DEFAULT_COA = [
  ["1101", "Kas Kecil", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1102", "Bank BCA 174", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1103", "Bank BCA 773", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1104", "Bank BCA STONEOUT", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1105", "Bank Mandiri", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1106", "Giro Masuk", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1107", "Saldo Lazada Broadwear", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1108", "Saldo Lazada Kiral", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1109", "Saldo Shopee Broadwear", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1110", "Saldo Shopee Grosir", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1111", "Saldo Shopee Kiral", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1112", "Saldo Shopee Red Carpet", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1113", "Saldo Shopee Stone Out", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1114", "Saldo Shopee Toko Topi Umum", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1115", "Saldo TikTok Broadwear", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1116", "Saldo TikTok Kiral", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1117", "Saldo TikTok Rafmos", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1118", "Saldo TIkTok Rogrs", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1119", "Saldo TikTok Stone Out", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1120", "Pos Sementara", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1121", "Ayat Silang", "ASET", "KAS_BANK", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1201", "Piutang Konvensional", "ASET", "PIUTANG", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1202", "Piutang Marketplace", "ASET", "PIUTANG", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1203", "Piutang Karyawan", "ASET", "PIUTANG", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1204", "Piutang Lain-Lain", "ASET", "PIUTANG", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1205", "Piutang Giro", "ASET", "PIUTANG", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1206", "Uang Muka Pembelian", "ASET", "UANG_MUKA_PEMBELIAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1301", "Bangunan Kantor", "ASET", "ASET_TETAP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1302", "Bangunan Produksi", "ASET", "ASET_TETAP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1303", "Peralatan Kantor", "ASET", "ASET_TETAP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1304", "Mesin", "ASET", "ASET_TETAP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1305", "Peralatan Produksi", "ASET", "ASET_TETAP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1401", "Persediaan Bahan Baku", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1402", "Persediaan Bahan Baku Kiral", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1403", "Persediaan Barang Setengah Jadi", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1404", "Persediaan Barang Setengah Jadi Kiral", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1405", "Persediaan Barang Jadi", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1406", "Persediaan Barang Jadi Kiral", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1407", "Persediaan Verpacking", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1408", "Persediaan Verpacking Kiral", "ASET", "PERSEDIAAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["1501", "Akm. Peny. Mesin", "ASET", "AKUMULASI_PENYUSUTAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["1502", "Akm. Peny. Peralatan Kantor", "ASET", "AKUMULASI_PENYUSUTAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2101", "Hutang Usaha", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2102", "Hutang Maklun", "LIABILITAS", "HUTANG_MAKLUN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2201", "Hutang Gaji", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2202", "Hutang Fee Manajemen", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2203", "Hutang Infaq Usaha", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2301", "Hutang Pihak Ketiga", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2302", "Hutang Pihak Ketiga - Sublim", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2303", "Hutang Pihak Ketiga - Bordir", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2401", "Hutang Giro", "LIABILITAS", "HUTANG", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["2501", "Uang Muka Penjualan", "LIABILITAS", "DP_CUSTOMER", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["3101", "Modal Pemilik", "EKUITAS", "MODAL", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["3102", "Prive Pemilik", "EKUITAS", "PRIVE", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["3201", "Laba Ditahan", "EKUITAS", "LABA", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["3202", "Laba Berjalan", "EKUITAS", "LABA", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4101", "Konvensional", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4102", "Reseller", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4103", "Penjualan Bahan", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4104", "Lazada Broadwear", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4105", "Lazada Kiral", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4106", "Shopee Broadwear", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4107", "Shopee Grosir", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4108", "Shopee Kiral", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4109", "Shopee Red Carpet", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4110", "Shopee Stone Out", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4111", "Shopee Toko Topi Umum", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4112", "TikTok Broadwear", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4113", "TikTok Kiral", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4114", "TikTok Rafmos", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4115", "TIkTok Rogrs", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4116", "TikTok Stone Out", "PENDAPATAN", "PENDAPATAN", "KREDIT", "ACTIVE", "Import COA KIRAL"],
  ["4301", "Diskon Penjualan", "PENDAPATAN", "DISKON_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5101", "Ongkos Kirim Pembelian Bahan", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5102", "Upah Operator Produksi", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5103", "Gaji Head Maklun", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5104", "Fee PIC Produksi", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5105", "Fee Head Produksi", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5106", "Biaya Potong", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5107", "Biaya Potong Kiral", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5108", "Biaya Sablon", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5109", "Biaya Sablon Kiral", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5110", "Biaya Sublim", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5111", "Biaya Sublim Kiral", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5112", "Biaya Bordir", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5113", "Biaya Bordir Kiral", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5114", "Biaya Jahit", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5115", "Biaya Jahit Kiral", "BEBAN", "HPP", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5116", "Biaya Pemeliharaan Mesin", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5117", "Biaya Pemeliharaan Bangunan Prod.", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5118", "Biaya Pemeliharaan Peralatan Prod.", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5119", "Biaya Listrik Produksi", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5120", "Biaya Perlengkapan Produksi", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5121", "Biaya Perlengkapan Prod. JH", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5122", "Biaya Perlengkapan Prod. Kiral", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5123", "Beban Peny. Bangunan Produksi", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5124", "Beban Peny. Mesin", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5125", "Beban Peny. Peralatan Prod.", "BEBAN", "BOP_PRODUKSI", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5201", "Ongkos Kirim Konvensional", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5202", "Ongkos Kirim Online", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5203", "Ongkos Kirim Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5204", "Biaya Packing Konvensional", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5205", "Biaya Packing Online", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5206", "Biaya Packing Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5207", "Biaya Pemasaran / Iklan", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5208", "Biaya Pemasaran / Iklan Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5209", "Biaya Sample Affiliate", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5210", "Biaya Sample Affiliate Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5211", "Biaya Komisi Affiliate", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5212", "Biaya Komisi Affiliate Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5213", "Biaya Komisi Penjualan", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5214", "Biaya Komisi Penjualan Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5215", "Biaya Admin Lazada Broadwear", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5216", "Biaya Admin Lazada Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5217", "Biaya Admin Shopee Broadwear", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5218", "Biaya Admin Shopee Grosir", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5219", "Biaya Admin Shopee Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5220", "Biaya Admin Shopee Red Carpet", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5221", "Biaya Admin Shopee Stone Out", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5222", "Biaya Admin Shopee Toko Topi Umum", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5223", "Biaya Admin TikTok Broadwear", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5224", "Biaya Admin TikTok Kiral", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5225", "Biaya Admin TikTok Rafmos", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5226", "Biaya Admin TIkTok Rogrs", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5227", "Biaya Admin TikTok Stone Out", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5228", "Refund/Diskon Penjualan", "BEBAN", "BEBAN_PENJUALAN", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5301", "Gaji Pemilik", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5302", "Gaji Karyawan", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5303", "Biaya Listrik Kantor", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5304", "Biaya Telepon & Internet", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5305", "Biaya BBM", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5306", "Biaya Peralatan/ATK", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5307", "Biaya Konsumsi", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5308", "Biaya Rumah Tangga", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5309", "Biaya Pengiriman", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5310", "Biaya Jasa Profesional", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5311", "Biaya Pemeliharaan Kendaraan", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5312", "Biaya Langganan Software", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5313", "Biaya Perjalanan Dinas", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5314", "Biaya Administrasi Bank", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5315", "Selisih Pembayaran", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5316", "Infaq Usaha", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"],
  ["5317", "Fee Manajemen", "BEBAN", "ADM_UMUM", "DEBIT", "ACTIVE", "Import COA KIRAL"]
];

// Entry point ringan. Detail fungsi dipisah ke file modular Finance_*.gs.

function doGet(e) {
  var auth = ERP_doGetAccess_(e);
  if (!auth.allowed) return ERP_forbiddenOutput_(auth);

  var t = HtmlService.createTemplateFromFile('Index');
  var pass = auth.passport || ((e && e.parameter && (e.parameter.paspor || e.parameter.passport || e.parameter.token)) || '');
  t.APP_TITLE = 'Finance';
  t.ERP_PASSPORT = pass;
  t.ERP_PORTAL_URL = ERP_getPortalUrl_();
  t.ERP_USER_EMAIL = auth.email || '';
  t.ERP_DISPLAY_NAME = auth.displayName || auth.email || '';
  t.FIN_BOOTSTRAP = {
    moduleCode: FIN_CFG.MODULE_CODE,
    version: FIN_CFG.VERSION,
    email: t.ERP_USER_EMAIL,
    userEmail: t.ERP_USER_EMAIL,
    displayName: t.ERP_DISPLAY_NAME,
    passport: pass,
    paspor: pass,
    portalUrl: t.ERP_PORTAL_URL
  };
  return t.evaluate()
    .setTitle('Finance CV Kiral')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

/* =========================
 * SECURITY & ROUTING
 * ========================= */