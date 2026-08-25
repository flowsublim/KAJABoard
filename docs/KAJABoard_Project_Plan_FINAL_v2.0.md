# KAJABoard — Project Plan FINAL

**Versi Dokumen:** 2.0 FINAL  
**Tanggal Baseline:** 25 Agustus 2026  
**Status:** **LOCKED BASELINE — siap menjadi acuan implementasi**  
**Produk:** KAJABoard  
**Pemilik Sistem:** PT KAJA VASTRALOKA KREASINDO  
**Primary Business Benchmark / Source of Truth:** SMB versi Google Apps Script + Google Sheets  
**Target Technology:** Python 3.13 + Django 5.2 LTS + PostgreSQL  
**Target Deployment Awal:** PythonAnywhere Paid, traditional WSGI  
**UI Baseline:** Django Templates + HTMX + Alpine.js secukupnya + Bootstrap/Tabler + custom KAJA design tokens  
**Architecture Style:** Modular Monolith  
**Production Database:** PostgreSQL  
**Legacy SMB Position After Go-Live:** read-only archive / migration reference

---

# 0. STATUS DOKUMEN DAN CHANGE CONTROL

Dokumen ini menggantikan **KAJABoard_Project_Plan_v1.0.md** sebagai baseline pembangunan KAJABoard.

Mulai versi ini berlaku prinsip **Functional Parity Lock**:

> Seluruh workflow, rule, validation, calculation, source linkage, document relationship, integration behavior, stock effect, accounting effect, reconciliation behavior, dan exception handling yang sudah diterima pada SMB wajib tercakup di KAJABoard.

Yang **tidak** wajib dipertahankan dari SMB GAS:

- nama function GAS;
- nama endpoint `google.script.run`;
- nama sheet;
- posisi kolom;
- struktur file GAS;
- cara cache GAS;
- format HTML lama;
- layout UI lama;
- helper teknis;
- workaround spreadsheet;
- direct cross-spreadsheet read/write;
- mekanisme passport GAS;
- fungsi dead code;
- fallback legacy yang tidak memiliki business purpose.

Yang **wajib** dipertahankan adalah **business outcome** dan **business control**.

Contoh:

```text
GAS:
simpanPackingOmni()
→ append Stock_Movement / DB_Mutasi
```

boleh berubah menjadi:

```text
Django:
OmniPackingService
→ WarehouseIssueService
→ InventoryMovement
```

selama hasil bisnisnya tetap:
- user Gudang memilih qty yang di-pack;
- qty tidak boleh melebihi demand/stok yang sah;
- stok keluar satu kali;
- source order/store/item dapat ditelusuri;
- retry tidak membuat stock OUT ganda.

Setiap perubahan business rule setelah dokumen ini harus melalui:

1. Change Request;
2. alasan perubahan;
3. modul terdampak;
4. migration impact;
5. accounting/stock impact;
6. test scenario baru;
7. update versi Project Plan / Functional Specification.

---

# 1. TUJUAN KAJABOARD

KAJABoard adalah sistem manajemen bisnis internal khusus **PT KAJA VASTRALOKA KREASINDO**.

KAJABoard bukan porting baris-per-baris dari SMB GAS. Sistem dibangun ulang untuk:

1. mempertahankan seluruh proses SMB yang sudah terbukti digunakan;
2. menghilangkan ketergantungan Google Sheets sebagai database produksi;
3. memperjelas ownership antar domain;
4. meningkatkan auditability;
5. mengurangi hardcode;
6. mengurangi duplicate logic;
7. menghilangkan cross-module write yang tidak terkendali;
8. membuat Finance berbasis event + COA Mapping;
9. membuat stock ledger tunggal;
10. membuat workflow dan state transition eksplisit;
11. meningkatkan performa;
12. mempermudah deploy dan maintenance;
13. memberikan UI yang lebih modern dan responsif;
14. menghasilkan laporan yang drill-down ke sumber;
15. mempermudah migration/import Excel;
16. mendukung kebutuhan KAJA B2B, marketplace, produksi internal, maklun, warehouse, finance, tax, dan management reporting.

---

# 2. SOURCE OF TRUTH DAN URUTAN OTORITAS

Jika ada perbedaan antar sumber, urutan otoritas adalah:

1. **Keputusan bisnis terbaru yang disetujui KAJA**
2. **Business rule SMB GAS yang sudah diterima**
3. **Patch/audit SMB terakhir yang sudah diterima**
4. **Regulasi, standar akuntansi, dan perpajakan**
5. **Project Plan KAJABoard ini**
6. **Odoo / SAP Business One / Accurate / Xero sebagai benchmark**
7. software lain sebagai inspirasi terbatas

Legacy code yang jelas merupakan bug, dead code, workaround, atau keterbatasan Google Sheets **tidak otomatis menjadi rule KAJABoard**.

Tetapi tidak boleh ada function/use case legacy yang dibuang hanya karena namanya terlihat teknis. Phase 0 wajib memetakan:

```text
Legacy Function / Endpoint
→ Business Use Case
→ Business Rule
→ Target Django Service/View
→ Test Scenario
→ Status: RETAIN / UPGRADE / REMOVE-DEADCODE
```

Endpoint parity **bukan** target. Functional parity adalah target.

---

# 3. BENCHMARK EKSTERNAL

## 3.1 Odoo

Diadopsi secara selektif:
- modular ERP;
- analytic accounting;
- project profitability;
- budget vs actual;
- configurable commission;
- subcontracting;
- inventory valuation;
- workflow/state oriented process;
- report drill-down.

Tidak diadopsi penuh:
- website builder;
- ecosystem app yang tidak relevan;
- no-code Studio;
- seluruh modul generik.

## 3.2 SAP Business One

Diadopsi:
- Business Partner core;
- document lineage;
- approval matrix;
- committed cost;
- multidimensional cost control;
- project/cost center;
- audit-friendly document flow.

Tidak perlu meniru full SAP MRP/configuration complexity.

## 3.3 Accurate Online

Diadopsi sebagai benchmark lokal:
- accounting Indonesia;
- inventory;
- fixed assets;
- manufacturing;
- stock opname;
- project/department;
- marketplace practicality;
- report export;
- tax readiness.

Business process KAJA tetap mengikuti SMB bila berbeda.

## 3.4 Xero

Diadopsi:
- clean report UX;
- tracking-style analytics;
- project profitability;
- comparison;
- report snapshot/publish;
- finance dashboard yang mudah dibaca.

---

# 4. ARSITEKTUR TARGET YANG DIKUNCI

## 4.1 Technology Stack

```text
Python 3.13
Django 5.2 LTS
PostgreSQL
Django Templates
HTMX
Alpine.js secukupnya
Bootstrap 5 / Tabler foundation
Chart.js
WSGI
PythonAnywhere Paid
```

React/SPA **bukan baseline awal**. React hanya dipertimbangkan kemudian bila ada kebutuhan UI yang benar-benar tidak efisien dengan HTMX/Alpine.

Alasan:
- deployment lebih sederhana;
- satu application stack;
- session/auth lebih sederhana;
- form validation server-side kuat;
- maintenance lebih ringan;
- business logic tidak perlu diduplikasi frontend/backend;
- cocok untuk ERP internal dengan workflow dan relational transaction yang kompleks.

## 4.2 Modular Monolith

Target apps:

```text
kajaboard/
├── config/
├── core/
│   ├── audit/
│   ├── workflow/
│   ├── approvals/
│   ├── documents/
│   ├── notifications/
│   ├── data_exchange/
│   └── idempotency/
├── accounts/
├── organization/
├── partners/
├── catalog/
├── masterdata/
├── sales/
├── projects/
├── incentives/
├── purchasing/
├── production/
├── warehouse/
├── quality/
├── omnichannel/
├── finance/
├── tax/
├── analytics/
└── reports/
```

Business logic lintas model ditempatkan di **service/application layer**, bukan tersebar di:
- view;
- template;
- model `save()`;
- signal;
- JavaScript;
- generic `utils.py`.

## 4.3 Domain Ownership

| Domain | Owner |
|---|---|
| User, Role, Permission | Core/Accounts |
| Company, Master, Mapping | Master Data |
| Customer/Vendor | Business Partner |
| Sales Order/Invoice Source | Sales |
| SPK Procurement/Maklun | Purchasing |
| WIP/Internal Production | Production |
| Physical Stock Ledger | Warehouse |
| QC Decisions | Quality |
| Marketplace Order/Settlement Source | Omnichannel |
| Journal/AR/AP/Cash/Bank | Finance |
| Tax rules/export | Tax |
| Project profitability | Projects/Analytics |
| Fee/Commission | Incentives |

**Warehouse adalah sole owner physical stock movement.**

**Finance adalah sole owner accounting journal, AR/AP settlement, cash/bank, fixed asset ledger, depreciation, dan closing.**

Modul lain menghasilkan source document/event/candidate.

---

# 5. CORE PLATFORM

Wajib tersedia:

- authentication;
- user;
- employee;
- role;
- permission;
- data scope;
- secure session;
- 2FA untuk role kritis;
- audit trail;
- activity timeline;
- notification;
- My Work;
- assignment;
- approval engine;
- workflow state machine;
- document numbering;
- attachment;
- comment;
- document lineage;
- idempotency;
- system setting;
- feature flag seperlunya;
- changelog;
- contextual help;
- exception/repair log untuk integrasi.

Permission model:

```text
Role + Action + Data Scope
```

Contoh:
- Warehouse.View
- Warehouse.PostReceipt
- Warehouse.PostIssue
- Warehouse.AdjustStock
- Finance.ViewJournal
- Finance.PostJournal
- Finance.ClosePeriod
- Tax.ExportCoretax
- Purchasing.Approve
- Production.PostWork
- Omni.ImportOrder

---

# 6. MASTER DATA — FOUNDATION WAJIB

Master Data bukan sekadar CRUD. Master menjadi **configuration source of truth**.

## 6.1 Company & Organization

- Company Profile
- Legal Entity
- Business Unit / Brand
- Department
- Cost Center
- Warehouse
- Location
- Employee
- Position
- Role
- approval hierarchy
- default company settings
- document identity/letterhead
- bank/rekening display data bila diperlukan untuk dokumen

Initial legal entity:
**PT KAJA VASTRALOKA KREASINDO**

## 6.2 Business Partner

Satu entity `BusinessPartner` dapat memiliki role:

- Customer
- Vendor
- Subcontractor
- Marketplace Partner
- Other

Fields minimum:
- Partner ID
- name
- legal name
- address
- phone
- email
- PIC
- NPWP/NITKU
- bank account
- payment terms
- credit terms
- credit limit
- status
- risk flags
- notes
- attachments

UI tetap dapat memisahkan Customer dan Vendor.

## 6.3 Product / SKU / Material

Product/SKU:
- SKU ID/code
- name
- category/subcategory
- item type
- UOM
- product/variant relationship
- sales flag
- purchase flag
- production flag
- inventory flag
- tax category
- minimum stock
- lead time
- preferred supplier
- valuation method
- current reference cost
- active/inactive

Material:
- material code
- name
- category
- UOM
- inventory settings
- purchase settings
- production usage
- conversion if needed.

Historical master changes wajib menggunakan:
- effective dating; dan/atau
- transaction snapshot.

## 6.4 Cost Center

Minimum canonical cost centers:

```text
PRODUCTION
WAREHOUSE
OFFICE
SALES_MARKETING
GENERAL
```

Cost Center dapat bertambah tanpa perubahan source code.

Cost Center digunakan untuk:
- expense classification;
- service classification;
- profitability;
- budget;
- overhead;
- financial analysis;
- project allocation.

## 6.5 Purchase Category

`PurchaseCategory` wajib memiliki metadata accounting, bukan hanya nama.

Fields:
- Category ID
- Category Code
- Category Name
- Accounting Treatment
- Cost Center
- Inventory Type
- Asset Class
- Snapshot Production
- Default Accounting Mapping Key
- Effective Date bila relevan
- Status

Allowed `AccountingTreatment`:

```text
INVENTORY
ASSET
EXPENSE
SERVICE
MAKLUN
```

Rules:
1. `INVENTORY` berpotensi menghasilkan inventory receipt.
2. `ASSET` menghasilkan fixed-asset acquisition candidate, bukan inventory stock.
3. `EXPENSE` wajib Cost Center.
4. `SERVICE` wajib Cost Center.
5. `MAKLUN` mengikuti subcontract/work-order treatment.
6. `SnapshotProduction = TRUE` hanya boleh untuk `EXPENSE` atau `SERVICE`.
7. `SnapshotProduction = TRUE` hanya boleh bila Cost Center = production-overhead eligible.
8. Bahan, aksesoris, packaging inventory, barang jadi, mesin, asset, inventaris, dan maklun tidak boleh salah masuk production overhead hanya karena nama kategorinya mengandung kata “Produksi”.

Dengan demikian KAJABoard **tidak boleh menentukan accounting behavior dari substring nama kategori**.

## 6.6 COA

Master COA minimum:
- COA ID
- Account Code
- Account Name
- Account Type
- Report Group
- Report Subgroup
- Normal Balance
- Parent Account
- Level
- Header Flag
- Manual Journal Allowed
- Cash/Bank Flag
- Control Account Flag
- Active
- effective date bila diperlukan

## 6.7 COA Mapping

Finance **dilarang hardcode nama/kode akun untuk auto-journal**.

Model mapping satu baris per accounting role:

```text
Mapping_ID
Module_Code
Event_Code
Dimension_Type
Dimension_Value
Line_Role
DC
COA_Code
Priority
Effective_From
Effective_To
Is_Active
```

Dimension minimum:
- DEFAULT
- STORE
- PURCHASE_CATEGORY
- COST_CENTER
- PAYMENT_METHOD
- TAX
- BUSINESS_UNIT
- PROJECT bila diperlukan

Resolver:
1. mencari mapping exact dimension;
2. fallback ke DEFAULT;
3. priority menentukan candidate bila terdapat rule bertingkat;
4. account harus aktif pada tanggal transaksi;
5. resolved mapping disnapshot pada journal line untuk audit.

## 6.8 Store Mapping

Store memiliki ID stabil.

Contoh:

```text
STORE-KIRAL-SHOPEE-01
STORE-KIRAL-TIKTOK-01
```

Nama display toko boleh berubah tanpa merusak accounting mapping.

Fields:
- Store ID
- Store Code
- Display Name
- Marketplace
- external alias / BigSeller store name
- business unit/brand
- active
- finance dimension
- warehouse fulfillment settings bila diperlukan.

## 6.9 SKU Mapping

Mapping marketplace tidak boleh bergantung hanya pada label display.

Minimum:
- Mapping ID
- marketplace
- store/channel optional
- marketplace SKU
- marketplace product
- variation
- internal Item ID
- mapping type
- conversion qty
- effective date
- status

Mapping exact harus mempertimbangkan variation bila tersedia.

## 6.10 System Setting

Minimum:
- timezone;
- default currency;
- fiscal year;
- tax settings;
- default warehouse;
- document numbering;
- approval setting;
- cost/inventory policy;
- report version;
- integration setting;
- import setting;
- company defaults.

Master configuration dapat dikelola menggunakan Django Admin pada fase awal, lalu custom UI dibuat untuk master yang sering dipakai user.

---

# 7. SALES / PENJUALAN — FUNCTIONAL PARITY LOCK

Referensi SMB memiliki flow utama:
**PO → Surat Jalan → Invoice → Piutang/SOA**, dengan master customer/item, print document, partial delivery, dan status link antar dokumen.

## 7.1 Sales Documents

Minimum:
- quotation/proforma bila diperlukan;
- Sales Order / PO customer;
- Sales Order Lines;
- Delivery / Surat Jalan;
- Delivery Lines;
- Invoice Source;
- Invoice Lines;
- return/credit-note source;
- customer ledger presentation;
- SOA.

Setiap line mempunyai stable line ID.

## 7.2 Sales Order Rules

- No dokumen unik.
- Customer wajib valid.
- Item harus berasal dari master aktif.
- Qty > 0.
- Harga dapat mengikuti master tetapi snapshot saat transaksi.
- Pajak/diskon/ongkir merupakan line/charge yang terstruktur.
- Deadline dapat disimpan.
- Document history tidak bergantung pada master current value.
- PO dapat berisi banyak item.
- edit terhadap posted/fulfilled transaction dibatasi oleh state.
- perubahan penting tercatat audit.

## 7.3 Partial Fulfillment / Surat Jalan

SMB mendukung pengiriman sebagian.

KAJABoard wajib:
- memilih item/line yang akan dikirim;
- qty delivery tidak boleh melebihi sisa yang belum dikirim;
- satu Sales Order dapat mempunyai lebih dari satu Surat Jalan;
- satu item dapat dikirim parsial beberapa kali;
- remaining quantity dihitung dari posted delivery;
- delivery menjadi source Warehouse OUT;
- void/reversal delivery mengoreksi stock melalui controlled reversal;
- stock OUT tidak dibuat oleh UI Sales secara langsung.

Flow:

```text
Sales Delivery POST
→ Warehouse Goods Issue Candidate
→ Warehouse validates/reserves/posts OUT
→ Delivery fulfillment updated
```

## 7.4 Invoice

- invoice dapat terkait PO/Sales Order;
- invoice dapat mengambil item dari source yang sesuai;
- lineage harus jelas;
- invoice total menggunakan snapshot qty/price/tax/discount;
- invoice posted menghasilkan Finance source event;
- Sales **tidak mencatat pembayaran**;
- payment status dibaca dari Finance;
- Invoice tidak boleh membuat cash/bank entry sendiri.

## 7.5 Piutang & SOA

Sales UI boleh menampilkan:
- total invoice;
- payment received;
- outstanding;
- overdue;
- detail invoice;
- related Sales Orders;
- payment history dari Finance.

Tetapi AR ledger owner tetap Finance.

## 7.6 Customer 360

Commercial:
- YTD sales
- lifetime sales
- gross profit
- margin
- AOV
- frequency
- last order
- top SKU

Finance:
- outstanding
- overdue
- DSO/payment days
- credit limit
- available credit

Operations:
- open order
- active project
- production
- reserved stock
- ready to deliver
- return/QC

Relationship:
- PIC
- salesperson
- notes
- attachments
- timeline

## 7.7 Sales Printing

KAJABoard harus mempertahankan business capability untuk:
- Proforma Invoice
- Invoice
- Surat Jalan
- Shipping Label
- Statement of Account

Company/brand/letterhead berasal dari master, bukan hardcode.

Print/PDF layout boleh didesain ulang.

---

# 8. PROJECT / CONTRACT MANAGEMENT

Project dipakai untuk:
- B2B custom;
- tender/pengadaan;
- large/custom order;
- customer-specific production;
- profitability tracking.

Project:
- Project ID
- Customer
- Contract/Sales Order
- Owner
- Salesperson
- target date
- status
- budget
- margin target

Progress:
- sales confirmed
- procurement
- production
- warehouse receipt
- delivery
- invoicing
- collection

Profitability:
- Revenue
- Budget
- Committed Cost
- Actual Cost
- Forecast
- CPO Fee
- Sales Fee
- Final Profit
- Margin %

Cost Breakdown:
- Material
- Purchasing
- Maklun
- Internal Production
- Labor
- Freight
- Packaging
- CPO Fee
- Direct Overhead
- Allocated Overhead
- Other

---

# 9. SALES COMMISSION / INCENTIVE

Generic Incentive Engine digunakan untuk Sales Fee dan CPO Fee.

Trigger options:
- Finished Goods Accepted
- Invoice Posted
- Invoice Paid
- Project Closed
- Approved Custom Event

Calculation:
- Per Unit
- % Revenue
- % Margin/Profit
- Fixed
- Tiered
- Approved Formula

Sales fee initial direction:
- profit-based;
- configurable minimum margin;
- configurable trigger;
- effective-dated rate;
- snapshot at accrual.

States:
- Estimated
- Accrued
- Approved
- Payable
- Paid
- Reversed

---

# 10. PURCHASING & PROCUREMENT — FUNCTIONAL PARITY LOCK

Purchasing mempertahankan workflow SMB:
- belanja umum/bahan;
- supplier/vendor;
- SPK;
- distribusi/kirim bahan;
- terima hasil maklun;
- supplier payable source;
- hutang maklun source;
- HPP source;
- document print;
- linkage ke Sales/Project bila ada.

## 10.1 Purchasing Transaction Classification

Setiap purchase line harus mengetahui:
- Purchase Category;
- Accounting Treatment snapshot;
- Cost Center snapshot;
- Inventory Type;
- Asset Class;
- Production Snapshot flag;
- Tax profile;
- Project/Contract bila terkait.

Behavior berdasarkan **AccountingTreatment**, bukan nama kategori.

### INVENTORY

- barang/bahan yang memang menjadi inventory;
- purchase receipt menghasilkan Warehouse Receipt Candidate;
- valuation source ikut dikirim;
- actual stock hanya berubah saat Warehouse post receipt.

### ASSET

- tidak menjadi inventory stock;
- menghasilkan Fixed Asset Acquisition Candidate;
- menyimpan asset class, acquisition value, date, department/cost center;
- Finance membentuk fixed asset register dan depreciation.

### EXPENSE

- wajib Cost Center;
- menjadi expense/AP source;
- tidak masuk stock;
- bila Cost Center Production dan SnapshotProduction true → menjadi source Production Overhead Snapshot.

### SERVICE

- wajib Cost Center;
- expense/service/AP source;
- treatment produksi mengikuti Cost Center + SnapshotProduction;
- tidak masuk stock.

### MAKLUN

- terkait SPK/work order/subcontract;
- biaya melekat pada work order/output sesuai rule;
- bukan generic office overhead;
- dapat menjadi AP source;
- receipt output masuk melalui Warehouse receipt setelah acceptance.

## 10.2 SPK / Work Order

SPK adalah work order dan cost-linking reference.

Wajib mendukung:
- internal production;
- external/subcontract/maklun;
- reference Sales Order/Project optional;
- material-output pair;
- multiple output items;
- qty target per output;
- due date;
- vendor bila external;
- instructions;
- item-specific notes;
- attachment/reference image;
- status;
- partial fulfillment.

Material-output pair harus eksplisit agar HPP dan traceability tidak ambigu.

## 10.3 Kirim Bahan

- source SPK;
- vendor/subcontractor;
- material/item;
- qty;
- cost snapshot;
- date;
- reference.
- qty tidak boleh melebihi material yang tersedia/diizinkan;
- Warehouse adalah owner stock issue.
- Purchasing membuat request/candidate, Warehouse post OUT.
- material sent menjadi WIP/subcontract trace.

## 10.4 Terima Maklun

Mendukung:
- Barang Jadi;
- Jasa Spesifik Varian;
- Jasa Umum/Pukul Rata;
- partial receipt;
- qty per output;
- vendor;
- cost;
- source SPK.

HPP external/subcontract:
- material supplied value;
- specific service cost;
- shared/general service allocation;
- other eligible costs;
- qty accepted.

Actual stock IN hanya melalui Warehouse receipt.

## 10.5 Purchasing Payment Boundary

Purchasing **tidak mencatat pembayaran cash/bank**.

Purchasing menghasilkan:
- supplier payable source;
- vendor bill source;
- maklun payable source.

Finance memproses:
- payment;
- bank/cash;
- settlement;
- journal.

## 10.6 Production Overhead Snapshot

Production overhead source dari Purchasing hanya bila:

```text
AccountingTreatment ∈ {EXPENSE, SERVICE}
AND CostCenter = PRODUCTION eligible
AND SnapshotProduction = TRUE
```

Yang tidak boleh menjadi production overhead:
- inventory material;
- bahan baku;
- accessories inventory;
- packaging inventory;
- finished goods;
- maklun principal cost;
- machine;
- equipment asset;
- asset/inventaris.

Snapshot ke Produksi menyimpan metadata source dan tidak bergantung pada master yang bisa berubah.

---

# 11. PRODUCTION & SUBCONTRACTING — FUNCTIONAL PARITY LOCK

## 11.1 Internal Production Stages

SMB reference memiliki stage:
- Potong;
- Jahit;
- QC & Packing;
- Setor Gudang;
- Reject Potong;
- Reject Jahit;
- Reject QC;
- Tugas Umum/Non-SPK bila diperlukan.

KAJABoard dapat memperbaiki nama/state, tetapi hubungan kuantitasnya wajib dipertahankan.

## 11.2 WIP Validation

Per output item:

```text
Available for Sewing
= Cut Qty - Sew Qty - Reject Cut

Available for QC
= Sew Qty - QC Qty - Reject Sew

Available for Warehouse Handover
= QC Qty - Warehouse Handover Qty - Reject QC
```

Input tidak boleh melebihi available WIP tahap sebelumnya.

Validation harus item-level, bukan total SPK global.

## 11.3 Multiple Item Entry & Line Identity

User boleh input beberapa item dalam satu transaksi untuk kecepatan.

Tetapi setiap line wajib memiliki stable `Line_ID`.

Edit/delete/correction bekerja pada line yang dipilih, bukan menghapus seluruh transaksi hanya karena satu batch dibuat sekaligus.

Posted correction menggunakan controlled correction/reversal sesuai state.

## 11.4 SPK Completion Rule

SPK tidak boleh ditutup hanya karena total qty aggregate cocok.

Untuk **setiap output product**:

```text
Cut Qty
= Accepted/Handover to Warehouse Qty
+ Reject Qty
```

dan seluruh WIP intermediate harus nol.

Satu output berlebih tidak boleh menutupi kekurangan output lain.

## 11.5 Material Consumption & Cost

Material cost menggunakan cost snapshot sesuai inventory costing policy pada transaction date.

Baseline direction:
- running weighted average untuk inventory yang menggunakan moving/weighted average;
- transaction date sensitive;
- source warehouse movement traceable;
- money dibulatkan whole Rupiah pada accounting layer;
- quantity boleh fractional sesuai UOM.

## 11.6 Labor

Production menyimpan:
- PIC;
- process;
- qty;
- tariff snapshot;
- direct labor amount;
- wage system;
- source SPK/output.

Tarif master yang berubah kemudian tidak mengubah histori.

## 11.7 Biaya Ekstra

`Biaya Ekstra` adalah biaya langsung/lokal seperti:
- makan operator;
- upah harian;
- dana talang aksesoris;
- biaya operator lain yang memang terkait pekerjaan.

Biaya tersebut:
- masuk HPP sesuai rule;
- dapat membentuk `Hutang Upah` / payable source;
- **pembayaran Hutang Upah oleh Finance bukan overhead baru**.

Tidak boleh double count antara accrual cost dan settlement payment.

## 11.8 Production Overhead Snapshot

Produksi memiliki source overhead snapshot dari Purchasing dan/atau Finance.

Snapshot minimum:
- source module;
- source document;
- source line;
- source key;
- category;
- accounting treatment;
- cost center;
- amount;
- status;
- posted date;
- reversal state;
- metadata.

Hanya active/POSTED dan tidak reversed/deleted yang dihitung.

Finance direct production overhead dapat menjadi source snapshot.

Settlement atas existing payable **tidak membuat overhead baru**.

## 11.9 HPP / COGM

HPP produksi dapat terdiri dari:
- material;
- direct labor;
- eligible direct extra cost;
- eligible production overhead;
- subcontract cost bila relevan;
- other approved production cost.

Allocation rule harus configurable dan auditable.

HPP source tidak boleh dihitung ulang secara berbeda hanya karena user membuka report.

## 11.10 Production → Warehouse

Production tidak langsung memiliki stock ledger.

Saat selesai:

```text
Production
→ ProductionWarehouseHandover
→ READY_FOR_GUDANG
→ Warehouse Receipt
→ POSTED stock IN
```

Handover dapat parsial.

Warehouse acceptance menentukan accepted qty.

---

# 12. WAREHOUSE & INVENTORY — FUNCTIONAL PARITY LOCK

Warehouse adalah **single physical inventory ledger owner**.

## 12.1 Stock Movement Model

Minimum:
- Movement ID
- Item
- Warehouse
- Direction IN/OUT
- Qty
- UOM
- Unit Cost
- Value
- Source Module
- Source Type
- Source ID
- Source Line ID
- Source Key
- Transaction Date
- Posting Date
- Status
- Reversal Reference
- Created/Posted By

Only movement:

```text
Status = POSTED
AND not reversed/deleted
```

masuk stock balance.

## 12.2 Source Movement

Minimum sources:

### IN
- Purchase Inventory Receipt
- Production Finished Goods Receipt
- Maklun Receipt
- Customer Return / Marketplace Return setelah QC accepted
- Stock Opname Gain
- Approved Positive Adjustment
- Opening Stock

### OUT
- B2B Sales Delivery
- Marketplace Packing/Fulfillment
- POS Sale
- Material Issue to Internal Production
- Material Send to Maklun
- Supplier Return
- Internal Consumption (box/label/material sesuai rule)
- Stock Opname Loss
- Approved Negative Adjustment

## 12.3 No Double Posting

Setiap stock posting memiliki unique source key.

Retry, double-click, import ulang, atau service retry tidak boleh membuat movement kedua.

## 12.4 Negative Stock

Default:
- tidak boleh negative stock.

Override hanya bila explicit policy + permission + audit, bila suatu hari benar-benar diperlukan.

## 12.5 Stock Opname

Stock opname bukan “menambah stok tiba-tiba”.

Flow:
1. system qty;
2. counted physical qty;
3. variance;
4. approval jika diperlukan;
5. adjustment movement sebesar selisih;
6. reason/audit;
7. reconciliation.

## 12.6 Marketplace Demand / Packing

Marketplace order **tidak langsung mengurangi stok saat import**.

Flow:

```text
Omni Order
→ Demand / Fulfillment Requirement
→ Warehouse queue
→ Pack / partial pack
→ Stock OUT
```

Rules:
- qty pack <= remaining demand;
- qty pack <= available stock;
- partial allowed;
- grouped/subcategory demand harus dipecah ke actual item/variant sebelum stock posting;
- source store/order/date dapat ditelusuri;
- shortage menghasilkan backorder/PR signal;
- stock movement hanya actual item.

## 12.7 POS

POS adalah bagian scope v1 karena merupakan business logic SMB.

Rule:
- POS user memilih **ITEM**, bukan subcategory;
- price dapat default dari master tetapi snapshot;
- qty > 0;
- transaction record harus tersimpan;
- stock issue harus terjadi atomik/idempotent;
- apabila stock posting gagal, transaksi tidak boleh tampak sukses tanpa repair state;
- COGS memakai inventory cost yang berlaku;
- POS stock OUT terjadi segera setelah sale posted.

Target Django flow:

```text
POST POS Sale
→ validate item/stock
→ create POS document
→ WarehouseIssueService
→ COGS source
→ Finance revenue/payment event
→ COMMIT atomically
```

## 12.8 Retur Penjualan / Marketplace

Return imported/registered **tidak otomatis menjadi stock IN**.

Flow:

```text
Return Request / Marketplace Return
→ QC
→ PASS/Accepted
→ Warehouse RETURN_IN
```

Reject/disposed/rework mempunyai treatment terpisah.

## 12.9 Supplier Return

Supplier return adalah stock OUT dan harus terkait:
- supplier;
- purchase source;
- item;
- qty;
- reason;
- valuation;
- Finance debit/credit note source.

## 12.10 Internal Consumption

Pemakaian internal seperti box/label:
- item;
- qty;
- purpose;
- cost center/project optional;
- stock OUT;
- accounting event ke Finance.

## 12.11 Costing

Baseline:
- running weighted average untuk category yang ditetapkan moving/weighted-average;
- period cost table boleh digunakan sebagai accelerator/report snapshot, bukan source truth yang berbeda;
- cost calculation harus transaction-order aware;
- reversal memperbaiki valuation secara controlled.

---

# 13. QUALITY / RETUR QC

QC adalah framework, bukan hanya retur marketplace.

Result:
- PASS
- HOLD
- REJECT
- REWORK

Use cases:
- incoming supplier;
- maklun receipt;
- internal finished goods;
- customer return;
- marketplace return;
- random inspection.

QC record:
- source;
- item;
- qty;
- inspected qty;
- accepted;
- rejected;
- rework;
- reason;
- photo;
- inspector;
- timestamp;
- notes.

Stock tidak berubah hanya karena return file diimport.

Warehouse movement terjadi berdasarkan keputusan QC final.

---

# 14. OMNICHANNEL — FUNCTIONAL PARITY LOCK

Omnichannel mencakup:
- BigSeller order import;
- multi-store;
- SKU mapping;
- store mapping;
- operational dashboard;
- demand to Warehouse;
- settlement;
- marketplace fees;
- adjustments;
- returns/refunds;
- POS;
- reconciliation;
- profitability by store/channel/SKU.

## 14.1 Order Import

Support:
- XLSX;
- CSV bila diperlukan;
- drag/drop/upload;
- preview;
- validation;
- warning;
- duplicate detection;
- import batch log;
- checksum/file metadata;
- idempotent re-import.

Minimum source fields:
- order created time;
- completion time;
- order number;
- status;
- store external name;
- SKU;
- product;
- variation;
- marketplace raw qty;
- conversion qty;
- internal qty;
- subtotal;
- tracking/resi;
- other fields needed for reconciliation.

## 14.2 Order Identity

Exact order line key harus mempertimbangkan:

```text
Order Number + SKU + Variation
```

Blank variation legacy dapat memiliki controlled fallback, tetapi satu variation tidak boleh menimpa variation lain.

## 14.3 Quantity Mapping

Simpan:
- `Marketplace_Qty` = raw source;
- `Conversion_Qty` = mapping snapshot;
- `Internal_Qty = Marketplace_Qty × Conversion_Qty`.

Bila mapping berubah, histori import harus tetap dapat direkonstruksi.

## 14.4 Store Mapping

External store name:
→ Store ID canonical.

Finance/warehouse/project analytics memakai Store ID, bukan display name sebagai key utama.

## 14.5 Operational Date vs Revenue Date

Order mempunyai dua tanggal penting:

### Order Date
`Waktu Pesanan Dibuat`

Digunakan untuk:
- operational order dashboard;
- demand;
- order volume;
- warehouse queue;
- order-day analysis.

### Completion Date
`Waktu Selesai`

Digunakan untuk:
- revenue recognition;
- receivable recognition;
- Finance/reporting income period.

Order dibuat 31 Juli dan selesai 3 Agustus:
- operational order = Juli;
- revenue = Agustus.

## 14.6 Operational Summaries

Konsep summary dipertahankan:

```text
OrderDailyStore
→ Date Key = order date

OrderDailyProduct
→ Date Key = order date
```

Digunakan untuk operation/warehouse/report acceleration.

Completed status di operational summary **bukan** sumber pengakuan pendapatan accounting.

## 14.7 Revenue Recognition Summary/Event

Dedicated completion/revenue source:

```text
RevenueDailyStore
→ Completion Date Key = Waktu Selesai
```

Revenue event hanya valid bila:
- status mencapai completed/eligible final state;
- `Waktu Selesai` valid;
- event belum pernah dibuat.

Event key contoh:

```text
OMNI_REV|STORE_ID|ORDER_NUMBER
```

Revenue history tidak boleh hilang bila kemudian terjadi return/refund.

## 14.8 Revenue Accounting Contract

Pada order selesai:

```text
Dr Piutang Marketplace - [Store]
    Cr Pendapatan Marketplace - [Store]
```

Finance menentukan COA dari Master COA Mapping.

Omni tidak hardcode account.

Amount baseline:
- gross product revenue berdasarkan eligible order subtotal yang telah didefinisikan;
- aggregation per order mencegah double line accounting;
- tax/discount treatment mengikuti configured accounting rule.

## 14.9 Settlement

Settlement adalah event terpisah dari revenue.

File settlement:
- diimport;
- dipreview;
- divalidasi;
- aggregated per Store + Order;
- duplicate/idempotency guarded;
- fee components disimpan terstruktur.

Minimum role:
- net marketplace balance;
- admin fee;
- affiliate fee;
- sample/program fee;
- seller shipping fee;
- ads fee;
- other marketplace adjustment with mapped role;
- receivable settlement.

Accounting concept:

```text
Dr Saldo Marketplace - [Store]
Dr Biaya Admin - [Store]
Dr Biaya Affiliate - [Store]
Dr Biaya Sample/Program - [Store]
Dr Biaya Ongkos Kirim - [Store]
Dr Biaya Iklan - [Store]
Dr/Cr Penyesuaian Marketplace - [Store] bila relevan
    Cr Piutang Marketplace - [Store]
```

Exact journal lines resolved by Master COA Mapping.

Settlement dapat:
- match penuh;
- partial;
- split;
- adjusted.

Tidak boleh menghapus original revenue event.

## 14.10 Payout to Bank

Ketika saldo marketplace benar-benar dicairkan ke bank:

```text
Dr Bank
    Cr Saldo Marketplace - [Store]
```

Dengan demikian neraca membedakan:
- completed but unsettled → Piutang Marketplace;
- settled but not yet banked → Saldo Marketplace;
- banked → Bank.

## 14.11 Reconciliation Status

Minimum exception statuses/concepts:
- COMPLETED_NOT_SETTLED
- SETTLEMENT_MATCH
- SETTLEMENT_PARTIAL
- SETTLEMENT_DIFFERENCE
- SETTLEMENT_WITHOUT_COMPLETED_ORDER
- RETURN_AFTER_COMPLETION
- COMPLETED_NEVER_PAID
- PAYOUT_PENDING
- PAYOUT_MATCH
- UNMAPPED_SKU
- UNMAPPED_STORE

Dashboard exception harus actionable.

## 14.12 Return / Refund

Return/refund adalah immutable follow-up event.

Jangan:
- menimpa sejarah seolah revenue tidak pernah terjadi;
- menghapus completed event.

Flow:
```text
Revenue Recognized
→ Return/Refund Event
→ QC/Return Treatment
→ Financial Adjustment/Credit
→ Settlement Reconciliation
```

Actual stock return tetap melalui QC → Warehouse.

## 14.13 Adjustment

Adjustment memiliki composite identity yang cukup untuk mencegah:
- adjustment type berbeda saling overwrite;
- repeated import menciptakan duplicate.

Adjustment harus selalu dapat merujuk order/store/source file bila tersedia.

## 14.14 POS

POS tetap bagian Omnichannel scope:
- strict ITEM selection;
- store/channel POS;
- price snapshot;
- stock immediate issue;
- cash/payment source to Finance;
- COGS source;
- audit and idempotency.

---

# 15. FINANCE & ACCOUNTING — FUNCTIONAL PARITY + UPGRADE

Finance menjadi accounting engine KAJABoard.

## 15.1 Finance Ownership

Finance memiliki:
- Journal Entry
- Journal Lines
- General Ledger
- AR
- AP
- Cash
- Bank
- Payment
- Marketplace Balance
- Settlement Accounting
- Fixed Assets
- Depreciation
- Inventory Accounting
- Accrual
- Prepaid/deferral bila diperlukan
- Closing
- Financial Statements
- Management financial views
- Tax accounting layer

## 15.2 Event → COA Mapping

Pattern:

```text
Business Event
→ Accounting Context
→ Master COA Mapping
→ Journal Candidate
→ Validate
→ Post
```

Auto-journal tidak boleh berisi akun hardcode tersebar di modul.

## 15.3 Representative Event Codes

### Sales
- SALES_INVOICE_POSTED
- SALES_DELIVERY_POSTED
- SALES_RETURN_ACCEPTED
- SALES_CREDIT_NOTE
- CUSTOMER_PAYMENT

### Purchasing
- PURCH_INVENTORY_PURCHASE
- PURCH_ASSET_PURCHASE
- PURCH_EXPENSE_PURCHASE
- PURCH_SERVICE_PURCHASE
- PURCH_MAKLUN_PAYABLE
- PURCH_PRODUCTION_OVERHEAD
- PURCH_WAREHOUSE_OVERHEAD
- PURCH_OFFICE_OVERHEAD
- SUPPLIER_RETURN

### Production
- PROD_DIRECT_LABOR
- PROD_EXTRA_OPERATOR_COST
- PROD_OVERHEAD
- PROD_FINISHED_GOODS_ACCEPTED
- PROD_REJECT

### Warehouse
- STOCK_RECEIPT
- STOCK_ISSUE
- STOCK_OPNAME_GAIN
- STOCK_OPNAME_LOSS
- STOCK_ADJUSTMENT
- INTERNAL_CONSUMPTION

### Omni
- OMNI_ORDER_COMPLETED
- OMNI_SETTLEMENT
- OMNI_PAYOUT
- OMNI_RETURN
- OMNI_ADJUSTMENT
- OMNI_POS_SALE

Event code boleh disempurnakan saat technical design tetapi business coverage tidak boleh berkurang.

## 15.4 AR

AR sources:
- B2B invoice;
- marketplace completed revenue;
- other approved receivable source.

Control account harus reconcile dengan detail.

## 15.5 AP

AP sources:
- purchase/vendor bill;
- maklun payable;
- wage payable;
- approved expense/service purchase;
- other liabilities.

Payment tidak menciptakan expense kedua bila expense sudah accrued.

## 15.6 Marketplace Control Accounts

Per Store dapat memiliki mapping:
- Piutang Marketplace;
- Saldo Marketplace;
- Revenue;
- Admin Fee;
- Affiliate Fee;
- Sample/Program Fee;
- Shipping Fee;
- Ads Fee;
- Adjustment.

Store ID menjadi dimension mapping.

## 15.7 Fixed Assets

Asset purchase source:
- acquisition candidate;
- asset class;
- value;
- acquisition date;
- cost center;
- project optional.

Finance:
- capitalization;
- asset register;
- useful life;
- residual value;
- depreciation method;
- depreciation schedule;
- disposal;
- impairment/adjustment if relevant.

## 15.8 Inventory Accounting

Physical quantity owner = Warehouse.

Finance consumes valuation/accounting events.

Target reconciliation:
```text
Inventory GL
= Inventory Valuation Subledger
```

Tidak ada dua ledger quantity yang bersaing.

## 15.9 Journal Rules

- Debit = Credit;
- unique source posting;
- posted journal immutable;
- reversal for correction;
- period validation;
- audit;
- source link;
- actor;
- timestamp;
- mapping snapshot;
- analytical dimensions.

---

# 16. FINANCIAL REPORTING

Core:
- Journal
- General Ledger
- Trial Balance
- Partner Ledger
- AR Aging
- AP Aging
- Statement of Financial Position
- Profit & Loss
- Cash Flow
- Changes in Equity
- Inventory Valuation
- Fixed Asset Register
- Depreciation Schedule
- Marketplace Receivable Reconciliation
- Marketplace Balance Reconciliation
- Project Profitability
- Budget vs Actual

Principle:
**No Unexplained Number.**

Drilldown:

```text
Report
→ Account
→ Journal Line
→ Journal
→ Source Event
→ Source Document
```

---

# 17. PSAK-READY REPORT ENGINE

Financial statement definition dipisahkan dari account master.

Mapping:
- Statement
- Section
- Category
- Subcategory
- Display Order
- Normal Balance
- Cash Flow Classification
- Fiscal Classification
- Effective Date
- Version

Report definition dapat berubah tanpa mengubah journal histori.

Project Plan mempertahankan kesiapan terhadap PSAK yang relevan pada tanggal implementasi; aturan/regulasi harus diverifikasi ulang saat modul Finance/Reporting dibangun.

---

# 18. MANAGEMENT ANALYTICS

## Customer
- sales;
- margin;
- lifetime;
- overdue;
- concentration;
- order frequency;
- project;
- returns;
- payment behavior.

## Vendor/Subcontractor
- purchase value;
- open PO;
- AP;
- lead time;
- on-time delivery;
- reject rate;
- return rate;
- price trend;
- maklun performance.

## SKU
- sales;
- margin;
- inventory turnover;
- stock aging;
- return rate;
- CPO fee;
- project usage.

## Project
- budget;
- committed;
- actual;
- forecast;
- margin;
- delivery;
- billing;
- collection;
- sales commission.

## Store
- gross revenue;
- completed revenue;
- outstanding receivable;
- settlement;
- marketplace balance;
- fees;
- return/refund;
- ads;
- contribution margin;
- exception orders.

---

# 19. BUDGET & COMMITTED COST

Budget dimensions:
- period;
- account;
- cost center;
- business unit;
- project.

Measures:
- Budget
- Committed
- Actual
- Forecast
- Remaining
- Variance
- Variance %

Committed examples:
- approved Purchase Order;
- SPK maklun berjalan;
- approved purchase request;
- production commitment not yet actual.

Budget threshold dapat memicu warning/approval.

---

# 20. QUALITY OF ACCOUNTING AND STOCK RECONCILIATION

Automated integrity checks:

### Accounting
- Debit = Credit
- Trial Balance balanced
- AR control = AR detail
- AP control = AP detail
- Marketplace AR control = order reconciliation
- Marketplace balance = settlement less payout
- Bank subledger reconcile
- Inventory GL = inventory valuation
- opening = prior closing where applicable

### Stock
- movement ledger = balance
- no duplicate source
- no illegal negative stock
- receipt/issue linkage
- warehouse handover reconciliation
- purchase receipt reconciliation
- marketplace packing reconciliation
- return QC reconciliation

---

# 21. TAX CENTER

Commercial accounting dan tax layer dipisahkan.

Master:
- NPWP
- NITKU
- PKP status
- tax code
- rate
- effective date
- tax base
- account mapping
- Coretax reference

Scope:
- PPN
- withholding tax relevant
- payable/credit
- fiscal asset
- fiscal depreciation
- fiscal reconciliation
- supporting schedule
- controlled Coretax/XML export where applicable.

Tidak melakukan unattended automated filing sebagai requirement v1.

---

# 22. PERIOD CLOSING

States:
- OPEN
- SOFT_CLOSE
- FINANCE_REVIEW
- CLOSED
- TAX_FILED
- LOCKED

Rules:
- transaction date validated;
- closed period rejects normal posting;
- reopen restricted;
- approval + reason required;
- controlled prior-period correction;
- closing checklist;
- closing log;
- stock and finance reconciliation.

Warehouse legacy cutoff behavior diterjemahkan menjadi controlled opening/closing balance mechanism, bukan menulis saldo cutoff ke master item sebagai workaround.

---

# 23. IMPORT / EXPORT CENTER

## 23.1 Migration Principle

Tidak membuat satu-off migration script yang hanya bekerja untuk satu struktur sheet.

Migration menggunakan versioned Excel templates/import adapters.

## 23.2 Import Flow

```text
Download Template
→ Fill / Select Source
→ Upload
→ Parse
→ Validate
→ Preview
→ Warning/Error
→ Confirm
→ Import Batch
→ Reconcile
```

## 23.3 Import Batch

- Batch ID
- type
- source filename
- source system
- template version
- checksum
- user
- upload time
- processed time
- total
- success
- skipped
- warning
- failed
- error log.

## 23.4 Initial Migration Data

- Business Partner
- Customer
- Vendor
- Store
- SKU
- SKU Mapping
- Material
- Purchase Category
- Cost Center
- COA
- COA Mapping
- Opening Trial Balance
- Opening Stock
- AR Outstanding
- AP Outstanding
- Marketplace outstanding
- Marketplace balance if any
- Fixed Assets
- Active Projects
- Open Sales Orders
- Open SPK
- WIP
- other open operational commitment as needed

Legacy transaction can remain read-only rather than recreated as active workflow.

---

# 24. REPORT EXPORT & ARCHIVE

Formal reports:
- XLSX
- PDF

Workbook may contain:
- Summary
- Detail
- Supporting Schedule
- Report Info

Report metadata:
- report name
- company
- period
- filters
- generated by
- timestamp
- KAJABoard version
- report definition version

Month/year-end archive pack:
- Trial Balance
- General Ledger
- Balance Sheet
- P&L
- Cash Flow
- Equity
- AR/AP Aging
- Inventory Valuation
- Fixed Assets
- Project Profitability
- Budget vs Actual
- Tax schedules
- Closing Summary
- marketplace reconciliation.

---

# 25. UI / UX DESIGN SYSTEM

UI **boleh berubah total dari GAS**, selama business capability tidak hilang.

Goals:
- modern;
- clean;
- KAJA identity;
- responsive;
- low cognitive load;
- quick action oriented;
- keyboard-friendly where useful;
- mobile approval/monitoring friendly;
- desktop finance/reconciliation friendly.

Desktop:
- collapsible sidebar;
- topbar;
- breadcrumbs;
- global search;
- notification;
- quick actions.

Mobile:
- offcanvas/bottom nav;
- touch actions;
- adaptive card/list;
- sticky action.

Operational patterns:
- tables;
- cards;
- Kanban only where it improves workflow;
- modal/offcanvas;
- bulk action;
- preview before posting;
- exception badges.

Django Admin:
- technical/config master first;
- **not** main operational UI.

---

# 26. PERFORMANCE RULES

PostgreSQL/Django implementation:

- indexed key fields;
- pagination;
- bounded queries;
- `select_related`;
- `prefetch_related`;
- avoid N+1;
- bulk insert/update for import;
- transaction batching;
- cache only read/derived config;
- never cache as ledger source truth;
- report aggregation optimized;
- generated summary/materialized strategy only where needed;
- row locks for stock/payment/posting;
- no full-table read per transaction.

Master COA/Mapping does **not** require GAS-style full sheet scan. PostgreSQL indexed lookup is the normal path.

Frequently used configuration may be cached safely, but posting always validates effective/active mapping.

---

# 27. SECURITY RULES

- Django secure password hashing;
- CSRF;
- secure cookies/session;
- `DEBUG=False`;
- environment secrets;
- least privilege;
- data scopes;
- 2FA critical role;
- rate limiting/login protection;
- audit log;
- upload validation;
- attachment authorization;
- no secrets in Git;
- financial report permission;
- admin action logging;
- approval segregation where appropriate.

---

# 28. IDEMPOTENCY

Mandatory for:
- stock receipt;
- stock issue;
- warehouse handover;
- B2B delivery;
- invoice post;
- payment;
- journal;
- marketplace order import;
- settlement import;
- adjustment import;
- return import;
- POS;
- approval critical action;
- CPO fee accrual;
- Sales commission accrual.

A request may be retried safely.

---

# 29. AUDIT TRAIL

Minimum:
- entity;
- record;
- action;
- before/after;
- changed fields;
- user;
- timestamp;
- request/session;
- reason;
- source;
- approval reference where applicable.

Transaksi posted tidak “dihapus” hanya karena audit log tersedia.

---

# 30. DOCUMENT LINEAGE

Setiap dokumen penting dapat ditelusuri.

Examples:

```text
B2B:
Customer/Project
→ Sales Order
→ SPK/Purchase
→ Production/Maklun
→ Warehouse
→ Delivery
→ Invoice
→ AR
→ Payment
→ Journal
```

```text
Marketplace:
Import Batch
→ Omni Order
→ SKU/Store Mapping
→ Warehouse Demand
→ Packing
→ Stock OUT
→ Completion Revenue
→ AR Marketplace
→ Settlement
→ Marketplace Balance
→ Payout
→ Bank
```

```text
Return:
Order/Sales
→ Return
→ QC
→ Warehouse Movement
→ Finance Adjustment
→ Reconciliation
```

---

# 31. STATE MACHINE

Arbitrary status string tidak diperbolehkan untuk state kritis.

Example SPK:
- DRAFT
- SUBMITTED
- APPROVED
- IN_PROGRESS
- PARTIALLY_COMPLETED
- READY_FOR_WAREHOUSE
- COMPLETED
- VOID

Example stock movement:
- DRAFT
- PENDING
- POSTED
- REVERSED

Example marketplace reconciliation:
- OPEN
- PARTIAL
- MATCHED
- DIFFERENCE
- CLOSED

Illegal transition ditolak oleh service layer.

---

# 32. GENERIC INCENTIVE ENGINE

Fee CPO dan Sales Commission berbagi engine.

Effective-dated rule.

At accrual:
- rule selected;
- rate snapshot;
- calculation basis snapshot;
- beneficiary snapshot;
- source event;
- amount;
- state.

Perubahan master tidak mengubah histori.

---

# 33. CPO FINISHED GOODS FEE

Trigger:
`Finished Goods Receipt POSTED + Accepted Qty`.

Formula default:
```text
Accepted Qty × Effective Rate Snapshot
```

Tidak dihitung dari qty produced yang belum diterima Warehouse/QC.

Ledger:
- receipt;
- SKU;
- project;
- qty;
- rate;
- amount;
- beneficiary;
- accrual date;
- status;
- settlement.

Accounting treatment dipetakan Finance, tidak hardcode di Warehouse.

---

# 34. CREDIT CONTROL

Customer:
- Credit Limit
- Outstanding
- Overdue
- Available Credit
- Average Collection
- Hold/Warning state

Override:
- explicit permission;
- approval;
- reason;
- audit.

---

# 35. DEPLOYMENT — PYTHONANYWHERE

Target awal:
- paid plan;
- WSGI Django;
- custom domain;
- HTTPS;
- virtualenv;
- PostgreSQL;
- static/media configuration;
- environment secrets;
- application/error logs;
- DB backups;
- scheduled tasks;
- management commands.

Core KAJABoard tidak bergantung pada WebSocket/ASGI.

Scheduled tasks boleh digunakan untuk:
- reminders;
- reconciliation suggestions;
- periodic report snapshot;
- depreciation run/suggestion;
- maintenance;
- backup.

**Financial posting tidak boleh terjadi hanya karena report/dashboard dibuka.**

---

# 36. BACKUP & DISASTER RECOVERY

Minimum:
- daily database backup;
- off-platform backup periodically;
- attachment/media backup;
- backup before production deployment;
- backup before structural migration;
- tested restore;
- retention policy;
- restore runbook.

Backup yang tidak pernah diuji restore belum dianggap cukup.

---

# 37. TESTING STRATEGY

## 37.1 Unit Tests
- validation;
- accounting mapping;
- costing;
- WIP;
- state transitions;
- commission;
- fee;
- tax;
- settlement;
- reconciliation.

## 37.2 Integration Tests
- Sales → Warehouse
- Purchasing → Warehouse
- Purchasing → Production Overhead
- Purchasing → Finance
- Production → Warehouse
- Warehouse → Finance
- Omni → Warehouse
- Omni → Finance
- Return → QC → Warehouse → Finance
- Project profitability.

## 37.3 Golden Scenarios

### Scenario A — B2B/Project
Sales → Project → Purchasing → Production/Maklun → Warehouse → CPO Fee → Delivery → Invoice → AR → Payment → Profitability → Sales Fee → Financial Report.

### Scenario B — Marketplace
Import Order → Mapping → Warehouse Demand → Pack → Stock OUT → Order Completion → Revenue/AR → Settlement/Fees → Marketplace Balance → Payout → Bank → Return/Adjustment → Reconciliation → Store Profitability.

### Scenario C — POS
POS Sale → Item validation → Stock OUT → COGS → Revenue/Payment → Daily report.

### Scenario D — Purchase Asset
Purchase → ASSET classification → Vendor Payable → Asset Candidate → Finance Capitalization → Depreciation.

### Scenario E — Production Overhead
Purchase EXPENSE/SERVICE + PRODUCTION CC → AP → Production overhead snapshot → HPP → payment settlement without double expense.

### Scenario F — Return
Return source → QC → accepted/reject/rework → stock effect → finance effect → reconciliation.

### Scenario G — Period Close
Reconcile stock/AR/AP/bank/marketplace → depreciation → inventory valuation → tax → close → financial statements → archive.

---

# 38. DATA MIGRATION & CUTOVER

Preferred cutoff:
- clean month start/year start when practical.

Move:
- active master;
- mappings;
- opening balances;
- stock qty/value;
- AR/AP;
- marketplace receivable/balance;
- fixed assets;
- active projects;
- open operational commitments;
- WIP;
- open SPK.

Must reconcile:
- Trial Balance;
- Stock Qty;
- Stock Value;
- AR;
- AP;
- Cash/Bank;
- Marketplace AR;
- Marketplace Balance;
- Fixed Asset NBV;
- Project commitments;
- tax balances.

SMB becomes read-only archive after accepted cutover.

---

# 39. IMPLEMENTATION PHASES — FINAL

## PHASE 0 — Source Freeze & Functional Audit

**Goal:** freeze actual SMB business behavior.

Activities:
- inventory every GAS module;
- inventory every public endpoint/function;
- map UI action → endpoint → business rule;
- map tables/sheets;
- map statuses;
- map validation;
- map stock sources;
- map accounting sources;
- map cross-module reads/writes;
- map print/report capabilities;
- compare legacy reference vs accepted latest patches;
- identify bugs/workarounds/dead code;
- resolve precedence;
- create functional parity register.

Deliverables:
1. `KAJABoard_Business_Process_Map.md`
2. `KAJABoard_Module_Ownership.md`
3. `KAJABoard_Data_Dictionary.md`
4. `KAJABoard_Event_Matrix.md`
5. `KAJABoard_Workflow_Status_Matrix.md`
6. `KAJABoard_Legacy_Endpoint_UseCase_Matrix.md`
7. `KAJABoard_Functional_Parity_Register.md`
8. `KAJABoard_Architecture.md`
9. `KAJABoard_UI_Design_System.md`

**Gate:** no business endpoint/use case left unclassified.

## PHASE 1 — Django Foundation

- repository;
- Python/Django;
- PostgreSQL;
- environment;
- auth;
- role;
- permission;
- audit;
- state machine;
- idempotency;
- document engine;
- app shell;
- responsive foundation;
- Django Admin.

Gate:
- authentication secure;
- role/data scope tests pass;
- deployable staging.

## PHASE 2 — Master Data & Configuration

- organization;
- Business Partner;
- Customer/Vendor;
- SKU/Material;
- UOM;
- Warehouse;
- Cost Center;
- Purchase Category;
- Accounting Treatment;
- Store;
- SKU Mapping;
- COA;
- COA Mapping;
- Finance mapping resolver;
- numbering;
- tax identity;
- import/export base.

Gate:
- no transaction module requires hardcoded account;
- master snapshots/effective dating defined.

## PHASE 3 — Sales + Customer 360 + Project

- Sales Order/PO;
- item lines;
- customer;
- partial delivery candidate;
- delivery lineage;
- invoice source;
- SOA/read Finance balances;
- print documents;
- project;
- credit control;
- Customer 360.

Gate:
- B2B reference scenario complete sampai demand/procurement handoff.

## PHASE 4 — Purchasing & Procurement

- purchase request/order if used;
- purchase transaction;
- Purchase Category classification;
- INVENTORY/ASSET/EXPENSE/SERVICE/MAKLUN routing;
- SPK;
- material-output pair;
- Kirim Bahan;
- Terima Maklun;
- supplier payable source;
- committed cost;
- production overhead snapshot source;
- vendor analytics;
- print SPK/document.

Gate:
- Purchasing tidak memiliki payment ledger;
- Purchasing tidak memiliki physical stock ledger;
- accounting classification is explicit.

## PHASE 5 — Production

- internal WIP;
- Potong/Jahit/QC/Handover stages;
- rejects;
- line-level edit/correction;
- multiple-item input;
- labor;
- extra cost;
- overhead snapshots;
- HPP/COGM;
- item-level SPK completion;
- ProductionWarehouseHandover.

Gate:
- no item can overconsume previous-stage WIP;
- SPK close rule item-safe;
- Production stops at warehouse handover.

## PHASE 6 — Warehouse + QC + CPO Fee

- unified StockMovement;
- receipt;
- issue;
- purchase receipt;
- production receipt;
- sales issue;
- material issue;
- maklun issue/receipt;
- opname;
- adjustment;
- supplier return;
- customer return;
- QC framework;
- CPO fee trigger;
- inventory costing;
- backorder/shortage.

Gate:
- Warehouse proven sole stock owner;
- no duplicate movement;
- reconciliation pass.

## PHASE 7 — Omnichannel + POS

- BigSeller import;
- raw qty;
- mapping snapshot;
- exact variation key;
- Store Mapping;
- SKU Mapping;
- order-date summary;
- completion-date revenue event;
- Warehouse demand;
- packing;
- return/refund;
- settlement;
- adjustment;
- marketplace reconciliation;
- payout handoff;
- POS strict item;
- POS stock issue integration;
- store analytics.

Gate:
- operational date and revenue date separated;
- reimport idempotent;
- settlement does not replace revenue history;
- return does not erase revenue history.

## PHASE 8 — Finance Operational

- Journal;
- GL;
- AR;
- AP;
- Cash;
- Bank;
- Marketplace AR;
- Marketplace Balance;
- Payment;
- Settlement accounting;
- event mapping;
- inventory accounting;
- fixed asset;
- depreciation;
- wage payable;
- period controls;
- bank reconciliation.

Gate:
- debit=credit;
- subledger/control reconciliation pass;
- no hardcoded transactional COA.

## PHASE 9 — Project Profitability + Incentives + Budget

- actual;
- committed;
- forecast;
- CPO fee;
- Sales commission;
- project margin;
- budget;
- variance;
- analytics.

Gate:
- manually verified project example reconciles.

## PHASE 10 — Reporting + Tax

- full financial reports;
- management report;
- report drill-down;
- report snapshot/publish;
- tax center;
- fiscal reconciliation;
- Coretax export support;
- Excel/PDF archive.

Gate:
- reports reconcile to ledger.

## PHASE 11 — Closing + Executive Analytics

- period close;
- lock;
- reopen control;
- archive pack;
- executive KPIs;
- CCC;
- concentration;
- profitability comparison;
- report history.

## PHASE 12 — Migration + UAT + Go-Live

- PythonAnywhere production;
- PostgreSQL;
- custom domain;
- HTTPS;
- backup;
- logging;
- migration templates;
- opening balance;
- open document migration;
- reconciliation;
- user training;
- UAT;
- go-live;
- SMB read-only transition.

---

# 40. LEGACY FUNCTION / ENDPOINT INVENTORY — TRACEABILITY ONLY

Nama berikut **bukan target endpoint Django**. Daftar ini hanya memastikan tidak ada business function yang hilang saat Phase 0.

## Penjualan — reference public functions

```text
doGet
include
formatRupiah
formatTgl
formatInputTgl
sanitizeStr
getSheetWithMap
getInitData
tambahMasterCustomer
tambahMasterItem
getItemsByRef
getItemsFromSJ
getSisaItemKirim
getDetailTransaksi
hapusDataMaster
cekDanUpdateStatusPO
simpanDataMaster
updateStatusPO
```

Mapping target mencakup:
- bootstrap/list data;
- master customer/item shortcut;
- source item retrieval;
- remaining delivery qty;
- detail/edit;
- void/delete control;
- PO/SJ/Invoice save;
- status update.

## Purchasing — reference public functions

```text
doGet
include
formatTglLokal
formatTglInput
formatRupiah
getSheetWithMap
getMasterData
getRiwayatTransaksi
updateAtauSimpanPembelian
updateAtauSimpanDistribusi
updateAtauSimpanSPK
updateStatusSPK
hapusDataTransaksi
tambahMasterBahan
getDetailPrintSPK
downloadSPKPDF
getRekapSPK
getRekapMaklunPO
getRekapHutangUsaha
tambahMasterItem
```

Mapping target mencakup:
- master context;
- purchase history;
- purchase save;
- material distribution;
- SPK;
- maklun;
- status;
- delete/void;
- print;
- HPP/status dashboard;
- AP display source.

## Produksi — reference public functions

```text
doGet
include
sanitizeStr
formatTgl
formatInputTgl
formatRupiah
getSheetWithMap
getArsipSelesai
getModulLinks
getDaftarPIC
getDataSPK
_cekKetersediaanWIP
_cekSisaBahanBaku
_getHargaBahanPerPcs
_getTarifMap
simpanDataProduksi
hapusDataProduksi
cekDanTutupSPK
syncHppGudang
getDashboardWIP
getLaporanProduksi
getLaporanHPP
getMasterData
simpanMasterPIC
editMasterPIC
hapusMasterPIC
simpanMasterTarif
editMasterTarif
hapusMasterTarif
getMasterBahanList
getLaporanReject
```

Master PIC/tariff capability akan dipindahkan ke appropriate Master/config layer bila lebih tepat, tetapi function bisnisnya tidak boleh hilang.

## Omnichannel — reference public functions

```text
doGet
include
getSheetWithMap
getModulLinks
prosesImportOmni
getDataMappingSKU
simpanMappingBaru
getMenuPOS
formatInputTglPOS
simpanPOS
getLaporanRetail
prosesImportRetur
getDaftarTokoDinamis
prosesImportKeuangan
getLaporanBiaya
```

Ditambah business rules dari audited Omni terbaru:
- exact variation identity;
- raw marketplace qty;
- conversion snapshot;
- strict item POS;
- settlement aggregation;
- completion-time revenue recognition;
- RevenueDailyStore;
- immutable revenue event;
- return/adjustment separation.

## Gudang — reference public functions

```text
doGet
include
getSpreadsheetIdDariMaster
fetchOmniExternal
getSheetWithMap
getModulLinks
getInitDataGudang
simpanPackingOmni
simpanPecahVarianBatch
simpanMutasiManual
simpanAuditFisikGudang
receptorTutupBukuDariPortal
```

Direct spreadsheet ETL/cutoff implementation akan diganti, tetapi preserved use cases:
- Omni demand;
- stock dashboard;
- pack;
- variant allocation;
- manual adjustment;
- physical verification;
- closing/cutoff.

---

# 41. FUNCTIONAL PARITY ACCEPTANCE MATRIX

Suatu modul hanya boleh dianggap **functional parity complete** bila:

1. semua legacy public use case sudah dipetakan;
2. semua accepted patch behavior sudah dipetakan;
3. semua business state punya target;
4. semua calculation punya unit test;
5. semua stock impact punya Warehouse event;
6. semua accounting impact punya Finance event;
7. semua print/report yang masih dibutuhkan tersedia;
8. semua import/export tersedia;
9. permission diterapkan;
10. duplicate/retry test pass;
11. correction/reversal test pass;
12. cross-module lineage pass;
13. no dead code known;
14. no temporary hardcode account;
15. no hidden spreadsheet dependency.

---

# 42. DEFINITION OF DONE — PER MODULE

Module belum selesai hanya karena UI terbuka.

Minimum:
- requirements implemented;
- responsive UI;
- permissions;
- validations;
- workflow/state;
- audit;
- idempotency;
- source linkage;
- ownership respected;
- unit tests;
- integration tests;
- migration/import;
- export/print if applicable;
- documentation;
- no known dead code;
- no unintended fallback;
- UAT pass;
- functional parity register complete.

---

# 43. RELEASE STRATEGY

Environments:
- Local
- Staging
- Production

Version:
`MAJOR.MINOR.PATCH`

Production release:
1. backup;
2. deploy;
3. dependencies;
4. migration;
5. collect static;
6. smoke;
7. reload;
8. critical scenario tests;
9. financial/stock health check.

Rollback/runbook required.

---

# 44. PRIMARY RISKS

## Scope Creep
Mitigation: locked functional parity + explicit backlog.

## Missing Legacy Logic
Mitigation: Legacy Endpoint → Use Case Matrix + parity register.

## Accounting Error
Mitigation: event mapping + transaction tests + reconciliation.

## Stock Integrity
Mitigation: sole Warehouse ledger + source key + row locks + reversal.

## Master Mapping Error
Mitigation: validation + effective date + preview + audit + mapping test.

## Migration Error
Mitigation: versioned import + preview + reconciliation.

## Historical Master Change
Mitigation: snapshot/effective dating.

## Marketplace Missing Order/Return
Mitigation: completion AR + settlement reconciliation + exception report.

## PythonAnywhere Limits
Mitigation:
- WSGI;
- PostgreSQL;
- optimize query;
- scheduled/background process only where needed;
- application remains portable to VPS.

---

# 45. OUT OF SCOPE / BACKLOG AFTER V1

- native Android/iOS;
- microservices;
- WebSocket dependency;
- full CRM marketing automation;
- full HRIS/payroll;
- e-commerce storefront;
- customer portal;
- vendor portal;
- full SAP MRP;
- AI that can mutate accounting/stock autonomously;
- complex OCR;
- multi-company consolidation;
- no-code builder;
- ML forecasting;
- external BI warehouse;
- bank API automation unless later approved;
- direct marketplace API automation unless later approved.

**POS is NOT backlog; POS is included in Omnichannel v1.**

---

# 46. SUCCESS CRITERIA

KAJABoard berhasil bila:

- user tidak bergantung pada Sheets sebagai production database;
- accepted SMB flow tetap tersedia;
- no missing business use case;
- duplicate critical posting prevented;
- stock traceable;
- journal traceable;
- accounting mapping configurable;
- Finance tidak hardcode COA transaksi;
- Purchasing classification explicit;
- Production HPP auditable;
- Warehouse sole stock owner;
- Omni completion revenue reconciles to settlement;
- marketplace outstanding dapat dideteksi;
- return tidak menghapus history;
- project profitability dipercaya;
- Customer 360 useful;
- CPO fee auditable;
- Sales commission explainable;
- reports reconcile;
- management drill-down;
- import/export reliable;
- desktop/mobile usable;
- period locking works;
- audit trail complete;
- deployment repeatable;
- backup restore tested;
- architecture maintainable.

---

# 47. FINAL ARCHITECTURE PRINCIPLE

```text
MASTER
├── Business Partner
├── Product/Material
├── Cost Center
├── Purchase Category
├── Store
├── SKU Mapping
├── COA
└── COA Mapping

OPERATIONS
Sales ──────────────┐
Purchasing ─────────┤
Production ─────────┤
Omnichannel ────────┼──→ Business Events / Candidates
Quality ────────────┤
                    │
                    ├──→ Warehouse = physical stock owner
                    │
                    └──→ Finance = accounting owner

WAREHOUSE
→ Stock Ledger
→ Costing
→ Physical Balance

FINANCE
→ Mapping Resolver
→ Journal
→ AR/AP
→ Cash/Bank
→ Marketplace Balance
→ Fixed Assets
→ Closing

ANALYTICS / REPORTS
→ read trusted subledgers
→ drill down to source
```

---

# 48. SPECIFIC NON-NEGOTIABLE RULES

1. UI GAS tidak harus dipertahankan.
2. Function/endpoint GAS tidak harus dipertahankan.
3. Nama sheet GAS tidak harus dipertahankan.
4. **Business rule SMB yang diterima wajib dipertahankan.**
5. Warehouse adalah sole stock owner.
6. Finance adalah sole accounting owner.
7. Master configuration menggantikan accounting hardcode.
8. Purchase category menentukan accounting treatment.
9. EXPENSE/SERVICE wajib Cost Center.
10. Production overhead hanya dari eligible expense/service + production cost center.
11. Asset purchase tidak masuk stock.
12. Payment tidak boleh menduplikasi expense/accrual.
13. Production completion item-level.
14. Production line memiliki stable ID.
15. Production handover tidak otomatis menjadi stock sebelum Warehouse posting.
16. Marketplace order import tidak otomatis stock OUT.
17. Marketplace packing membuat stock OUT.
18. POS strict Item dan immediate stock OUT.
19. Marketplace revenue diakui pada `Waktu Selesai`.
20. Order date tetap digunakan untuk operational metrics.
21. Settlement bukan tanggal revenue.
22. Completed marketplace order menghasilkan AR per Store.
23. Settlement mengurangi AR dan membentuk Marketplace Balance + fees.
24. Payout memindahkan Marketplace Balance ke Bank.
25. Return/refund tidak menghapus revenue history.
26. Return stock IN hanya setelah QC accepted.
27. Order/SKU/Variation identity tidak boleh saling overwrite.
28. Raw marketplace qty dan conversion snapshot disimpan.
29. Every critical import/posting is idempotent.
30. Posted transaction corrected with reversal/adjustment, not silent delete.
31. Report cannot create financial posting just by being viewed.
32. Historical master change tidak boleh mengubah transaksi lampau.
33. Whole-Rupiah accounting rounding; quantity follows UOM precision.
34. Every reported number must be explainable and drillable.

---

# 49. FIRST EXECUTION AFTER THIS PLAN

Urutan berikutnya:

1. Freeze seluruh SMB source/reference.
2. Buat `KAJABoard_Legacy_Endpoint_UseCase_Matrix.md`.
3. Buat `KAJABoard_Functional_Parity_Register.md`.
4. Finalize Data Dictionary.
5. Finalize State Matrix.
6. Finalize Event Matrix.
7. Finalize Module Ownership.
8. Build Django repository.
9. Implement Foundation + Master Data before transaction modules.

Tidak mulai menulis ulang modul transaksi secara acak sebelum Phase 0 register selesai.

---

# 50. REFERENCE BASELINE YANG HARUS DIAUDIT

## Legacy/reference UI + code
- Penjualan: Index / JS / CSS / Print / Kode
- Purchasing: Index / JS / CSS / Print / Kode
- Produksi: Index / JS / Kode
- Omnichannel: Index / JS / Kode
- Gudang: Index / JS / Kode

## Accepted newer business behavior
- audited Penjualan behavior;
- Purchasing SPK/material-output/maklun + strict production overhead;
- Produksi item-safe + running average + overhead snapshot;
- Omni audited mappings/idempotency/POS + completion revenue;
- Master Data configuration + COA Mapping + Purchase Category + Cost Center.

Reference code diperlakukan sebagai **functional evidence**, bukan target coding style.

---

# 51. FINAL SCOPE DECISION

KAJABoard adalah:

> **SMB business knowledge + KAJA-specific controls + configurable Master/Accounting + Django/PostgreSQL architecture + audit-grade Warehouse/Finance ownership + modern role-based UX.**

KAJABoard bukan clone Odoo, SAP, Accurate, Xero, atau GAS.

External ERP memberikan pattern yang matang.

SMB memberikan **actual KAJA workflow**.

KAJABoard harus mempertahankan yang sudah terbukti bekerja, menghapus kelemahan arsitekturnya, dan tidak kehilangan satu pun business capability hanya karena endpoint/UI/database direwrite.

---

**END — KAJABoard Project Plan FINAL v2.0**
