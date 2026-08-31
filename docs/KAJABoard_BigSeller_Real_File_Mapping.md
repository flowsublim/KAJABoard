# BigSeller Real-File Compatibility Audit

Audit scope: the real BigSeller exports inspected for Phase 7A. The raw source
copies are not retained in the repository:

- `Order-Goods-all20260807125711532.xlsx`
- `Order-Return202608071215441.xlsx`

The sanitized regression fixtures are:

- `tests/fixtures/omnichannel/bigseller/order_goods_sample_sanitized.xlsx`
- `tests/fixtures/omnichannel/bigseller/order_return_sample_sanitized.xlsx`

They preserve the real headers, order, date format, numeric cell behavior, and
audited edge cases while replacing operational identifiers with synthetic
values. Buyer/customer content is blank because no Phase 7A business
requirement exists for PII.

Both workbooks have one worksheet named `sheet1`.

The sanitized Order Goods regression sample contains six synthetic rows,
including three physical rows for one order, `RED` and `BLUE` variations for
the same SKU, one blank variation, quantities `1`, `2`, and `10`, populated and
blank completion timestamps, and optional numeric placeholders. The sanitized
Return regression sample contains three synthetic rows, including one package
split across two SKUs, numeric `Jumlah` cells, TikTok and Shopee rows, and the
same blank identity/reason/refund/stock-addition fields observed in the source.

## Order Goods export

The workbook has 1,632 data rows and 18 columns. The exact header order is:

`Waktu Pesanan Dibuat`, `Nomor Pesanan`, `Status Pesanan`, `Nama Panggilan Toko BigSeller`, `SKU`, `Nama Variasi`, `Jumlah`, `Harga Satuan`, `Subtotal Produk`, `Harga Awal Produk`, `Jasa Kirim yang Dipilih Pembeli`, `Nomor Resi`, `Biaya Pengelolaan`, `Voucher`, `Voucher Toko`, `Waktu Pesanan Dikirim`, `Waktu Dikirim`, `Waktu Selesai`.

All populated cells are stored as strings, including quantity, amounts, dates, and timestamps; blank cells are absent/empty. Observed values include:

| Field | Observed behavior | Phase 7A treatment |
| --- | --- | --- |
| `Nomor Pesanan` | nonblank string; 1,605 distinct orders | required external order identity |
| `Nama Panggilan Toko BigSeller` | nonblank string; 8 distinct store names | required exact Store identifier; no guessing |
| Marketplace/channel | no marketplace column exists | optional; canonical channel comes from the resolved Store |
| `SKU` | nonblank string | required exact external SKU |
| `Nama Variasi` | 1,629 nonblank, 3 blank | optional exact variation; blank is an explicit empty variation key |
| `Jumlah` | strings `1`, `2`, and `10`; all positive | required Decimal marketplace quantity |
| `Subtotal Produk` | numeric strings or `--` | optional Decimal; `--` is treated as missing |
| Other amounts | numeric strings, blanks, or `--` | retained in row raw metadata; not used as Phase 7A accounting facts |
| `Waktu Pesanan Dibuat` | `01 Agu 2026 00:00` format; all 1,632 present | required Order Date; Indonesian month abbreviations supported |
| `Waktu Selesai` | same format; 64 present and 1,568 blank | optional Completion Date; never inferred |
| `Status Pesanan` | `Selesai`, `Sudah Dikirim`, `Dibatalkan`, `Menunggu Diproses`, `Menunggu Dicetak`, `Menunggu Pickup`, `Belum Dibayar`, `Pengembalian Barang & Dana`, `Batalkan Pengajuan` | raw status preserved; observed return/cancellation wording normalized for demand eligibility |
| `Nomor Resi` | string; 1,350 present and 282 blank | optional tracking snapshot |
| buyer/customer fields | none in this export | no customer PII stored |

### Order Goods parser contract

The parser uses normalized header names and never uses column positions. The real headers are covered by these explicit aliases:

| Canonical field | Supported header aliases | Real header | Parser requirement |
| --- | --- | --- | --- |
| order number | `Nomor Pesanan`, `No Pesanan`, `Order Number`, `Order No`, `No. Pesanan` | `Nomor Pesanan` | required |
| order date | `Waktu Pesanan Dibuat`, `Order Creation Time`, `Order Date`, `Tanggal Pesanan`, `Tanggal` | `Waktu Pesanan Dibuat` | required |
| store | `Nama Panggilan Toko BigSeller`, `Shop Name`, `Store Name`, `Toko` | `Nama Panggilan Toko BigSeller` | required |
| SKU | `SKU`, `Nomor Referensi SKU`, `Marketplace SKU` | `SKU` | required |
| quantity | `Jumlah`, `Quantity`, `Qty` | `Jumlah` | required |
| completion date | `Waktu Selesai`, `Completion Time`, `Completion Date`, `Tanggal Selesai` | `Waktu Selesai` | optional |
| status | `Status Pesanan`, `Order Status`, `Status` | `Status Pesanan` | optional; raw value preserved |
| marketplace | `Marketplace`, `Platform`, `Channel` | absent | optional; resolved Store channel is the fallback |
| product | `Nama Produk`, `Produk`, `Product Name`, `Marketplace Item Name` | absent | optional; no product-name inference |
| variation | `Nama Variasi`, `Variasi`, `Varian`, `Variation`, `Marketplace Variation` | `Nama Variasi` | optional; blank is an exact empty key |
| subtotal | `Subtotal Produk`, `Product Subtotal`, `Subtotal`, `Total` | `Subtotal Produk` | optional; `--` means missing |
| tracking | `Nomor Resi`, `Tracking Number`, `Tracking No`, `No Resi` | `Nomor Resi` | optional |

`Order Goods` date/time strings use `DD Agu YYYY HH:MM` in this fixture (for example, `01 Agu 2026 00:00`). The parser accepts the Indonesian abbreviated month vocabulary and stores the calendar date in the Phase 7A date snapshot; the original timestamp remains in `OmniImportRow.raw_data`. Numeric values are whole-number strings in the supplied export; `--` is a missing optional amount, not zero. No customer/buyer field is present.

The raw source row retains all real columns in `OmniImportRow.raw_data`, including `Harga Satuan`, `Harga Awal Produk`, `Jasa Kirim yang Dipilih Pembeli`, `Biaya Pengelolaan`, `Voucher`, `Voucher Toko`, `Waktu Pesanan Dikirim`, and `Waktu Dikirim`. These are needed as evidence for operational reconciliation and later Phase 7B revenue/settlement/return matching, but are not Phase 7A posting fields. No canonical model expansion is required now.

The export contains 23 orders with multiple physical rows, maximum four rows per order. No duplicate exact `(order, SKU, variation)` identities were found. `Nama Variasi` is therefore part of the identity even when it is blank; it must not be replaced by product display name.

The existing Phase 7A aliases already match the real Order Goods headers by name. The compatibility gaps were the Indonesian month abbreviations and BigSeller's `--` optional numeric placeholder.

## Return export

The workbook has 32 data rows and 42 columns. The exact header order is:

`Marketplace`, `Toko BigSeller`, `Metode Pembayaran`, `Pembeli`, `Gudang Asal`, `Gudang Penerima`, `Jenis Purna Jual`, `Jenis Pesanan`, `Nomor Paket`, `Nomor Pesanan`, `ID Purna Jual`, `Dana Pengembalian`, `Total Pesanan`, `Mata Uang`, `Nama Produk`, `SKU Toko`, `Harga Jual Produk`, `Nama SKU Gudang`, `SKU Gudang`, `Nomor SKU Gudang`, `Jumlah`, `Jumlah Penambahan Stok`, `Status Penambahan Stok`, `Jasa Kirim`, `Status Pesanan`, `Nomor Resi`, `Status Pengiriman Jasa Kirim`, `Status Purna Jual`, `Alasan Retur`, `Rincian Alasan Retur`, `Nomor Resi Pesanan Pengembalian`, `Status Pengembalian Jasa Kirim`, `Status Pengembalian`, `Waktu Pemesanan`, `Waktu Permintaan Purna Jual`, `Batas Waktu`, `Waktu Dikirim`, `Waktu Sampai Gudang`, `Waktu Penambahan Stok`, `Operator`, `Catatan untuk Penambahan Stok`, `Catatan Purna Jual`.

The `Jumlah` cells are numeric Excel cells (`t="n"`) with displayed values such as `1.0` and `2.0`; other populated cells are strings (`inlineStr`). Amounts are whole-number strings, and no decimal/currency symbol is present in the inspected values. All 32 rows are `Kembalikan Tidak Normal`, have `Status Pengembalian = Sudah Dikembalikan`, and have `Status Penambahan Stok = Stok Belum Ditambahkan`. `Waktu Sampai Gudang` is populated, while request, return-shipping, stock-addition, reason, and refund-amount fields are blank in this fixture.

All populated Return date/time fields use `DD <Indonesian abbreviated month> YYYY HH:MM` (for example, `05 Agu 2026 09:16` or `29 Jul 2026 06:35`). Counts are: `Waktu Pemesanan` 32, `Waktu Dikirim` 32, `Waktu Sampai Gudang` 32; `Waktu Permintaan Purna Jual`, `Batas Waktu`, and `Waktu Penambahan Stok` are all blank. There is no populated refund-date field in this export.

The buyer field is masked in the supplied file and is not a Phase 7A canonical field. It must not be imported merely because the column exists.

## Proposed Phase 7B return mapping

| BigSeller Return column | Proposed canonical field | Original-order linkage | Quality/Warehouse implication | Finance implication |
| --- | --- | --- | --- | --- |
| `Marketplace` | marketplace | scope with Store and order number | source scope only | settlement/refund source dimension later |
| `Toko BigSeller` | external Store identifier | resolve to canonical Store snapshot | no stock effect on import | Store accounting dimension later |
| `Nomor Pesanan` | external order number | match `(Store, marketplace, order number)` | preserve original outbound lineage | refund/reversal source later |
| `Nomor Paket` | marketplace/package reference | secondary shipment match | preserve logistics evidence | reconciliation reference later |
| `SKU Toko` | external SKU | match original order line SKU | exact mapping required | refund line source later |
| `SKU Gudang` / `Nomor SKU Gudang` | external warehouse SKU / external item reference | corroborating mapping only | resolve canonical Item through approved mapping; never name-guess | item dimension later |
| `Nama Produk` / `Nama SKU Gudang` | source display snapshots | not an identity key | display evidence only | not a posting key |
| `Jumlah` | requested return quantity | match original order line where possible | Quality inspection quantity; no automatic `RETURN_IN` | no journal in Phase 7A |
| `Jumlah Penambahan Stok` | accepted stock quantity | linked to return after QC | only Quality PASS then Warehouse `RETURN_IN` later | inventory/refund accounting later |
| `Status Penambahan Stok` | stock-addition source status | reconciliation state | never treat as a Warehouse posting | no accounting effect |
| `Status Purna Jual`, `Status Pengembalian`, `Status Pengiriman Jasa Kirim` | raw return/shipping statuses | source evidence | drives later QC eligibility, not a PASS decision | refund eligibility later |
| `Jenis Purna Jual`, `Alasan Retur`, `Rincian Alasan Retur` | return type/reason snapshots | source evidence | informs inspection; does not decide disposition | adjustment/refund policy later |
| `Waktu Pemesanan` | original order timestamp | order linkage evidence | not return receipt date | not revenue date |
| `Waktu Permintaan Purna Jual` | return requested timestamp | future return event date | return workflow timestamp | refund event timing later |
| `Waktu Sampai Gudang` | return-arrival timestamp | receipt evidence | candidate QC inspection date | not an accounting posting by itself |
| `Waktu Penambahan Stok` | stock-addition timestamp | later Warehouse result evidence | only after approved Warehouse receipt | inventory event date later |
| `Dana Pengembalian`, `Total Pesanan`, `Mata Uang` | refund amount / order amount / currency snapshots | commercial corroboration | no stock effect | Finance consumes only after policy and mapping |
| `ID Purna Jual` | return transaction identity | preferred deterministic key | idempotency key when populated | refund/reconciliation key later |

In this real fixture `ID Purna Jual` is blank in all 32 rows, as are `Dana Pengembalian`, return reasons, and the variation field is absent entirely. `Nomor Pesanan`, `Nomor Paket`, Store, marketplace, SKU, and quantity are available, but `Nomor Pesanan` and `Nomor Paket` are only 31-distinct across 32 rows. One order/package has two different SKU rows, so that repetition is a line split, not a duplicate return transaction. Phase 7B therefore needs a source-row identity plus a controlled composite fallback, and must not claim a globally unique return transaction until BigSeller supplies a stable ID or an owner-approved composite rule. A Return import must remain source/QC-ready and must create zero StockMovement until Quality acceptance and the Warehouse return service exist.

Deterministic linkage availability in this file is:

| Linkage requirement | Real-file evidence | Safe Phase 7B conclusion |
| --- | --- | --- |
| Store | `Toko BigSeller` populated in all 32 rows | available after exact Store resolution |
| Marketplace | `Marketplace` populated in all 32 rows (`TikTok`/`Shopee`) | available as source scope |
| Original order | `Nomor Pesanan` populated; 31 distinct values | available, but not unique by itself |
| SKU | `SKU Toko` populated in all 32 rows | available for exact line matching |
| Variation | no variation column | unavailable; never infer from product name |
| Quantity | `Jumlah` populated in all 32 rows | available as requested-return quantity |
| Return/refund transaction identity | `ID Purna Jual` blank in all rows | unavailable; use source-row identity pending approved fallback |
| Package/shipment evidence | `Nomor Paket` and `Nomor Resi` populated; 31 distinct package numbers | secondary matching evidence only |

## Scope decision

This audit patches Phase 7A Order Goods parsing only. No Return model, Return import, Quality decision, Warehouse `RETURN_IN`, refund, AR, journal, settlement, or payout behavior is implemented here.
