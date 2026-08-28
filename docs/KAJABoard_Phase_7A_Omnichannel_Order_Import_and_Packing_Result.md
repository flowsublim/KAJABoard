# KAJABoard Phase 7A — Omnichannel Order Import and Warehouse Packing

Status: implemented on the clean `phase-6-pass` baseline. No commit, push, or tag was created.

## Scope

Phase 7A establishes the operational Omnichannel base only:

`BigSeller XLSX/CSV → durable source batch/rows → exact Store and SKU mapping snapshots → OmniOrder/OmniOrderLine → Warehouse demand → OmniPacking → Warehouse StockMovement OUT`.

Marketplace import itself does not reduce stock. Packing reduces stock only through the Warehouse posting service. Omnichannel never creates `StockMovement` directly.

## Legacy evidence used

The review covered the actual SMB files `legacy/smb_gas/omnichannel/{Kode.gs,JS.html,Index.html,CSS.html,Omni_DailySummary.gs,Omni_DataKey.gs}` and linked Warehouse/Finance readers. Relevant parity decisions were:

| Legacy function/use case | Phase 7A treatment | Django target |
| --- | --- | --- |
| `prosesImportOmni` / BigSeller order upload | UPGRADE: header-driven durable XLSX/CSV preview and explicit commit; no report-time stock or COGS mutation | `services.imports.preview_bigseller_import`, `commit_bigseller_import` |
| `aggregatePayloadImportClient` and `aggregateOrderRows_` | RETAIN: order + SKU + variation identity and aggregation | `OmniOrderLine` unique scope |
| `getStoreMap_`, `resolveStoreName_` | UPGRADE: exact canonical Store resolution with legal-entity and effective-date scope | Channels `Store`, import resolver |
| `getSkuMap_`, `resolveSkuMapping_`, `simpanMappingBaru` | UPGRADE: exact SKU/variation lookup and immutable transaction snapshot; master ownership remains Channels | Channels `ExternalSKUMap`, `mapping_snapshot` |
| `Omni_rebuildOrderDailySummary_`, `getLaporanRetail` | UPGRADE: read-only Order Date summary; completed status is operational, not revenue | `order_daily_store_summary` |
| Gudang `getTarikanOmniGudang` / `simpanPackingOmni` | UPGRADE: line-level demand, partial packing, shortage visibility, and Warehouse-owned atomic OUT | `warehouse_demand`, `services.packing`, `warehouse.post_stock_movement` |

Spreadsheet-specific cache, sheet rewrites, grouped/subcategory posting, direct cross-spreadsheet stock writes, and legacy zero-cost fallbacks were not reproduced.

## Canonical identity and snapshots

An order identity is scoped by legal entity, marketplace, exact external store identity, and external order number. An order line is uniquely scoped by:

`Order + normalized external SKU + normalized exact variation`.

Blank variation is a real empty variation key; it cannot collide with a named variation. Store snapshots retain Store ID, code, display name, channel, and effective date. SKU snapshots retain mapping ID, store scope, external SKU/variation, canonical Item, conversion, and effective date.

The quantity contract is Decimal and persisted without destroying the source values:

`Marketplace_Qty = raw source`, `Conversion_Qty = mapping snapshot`, `Internal_Qty = Marketplace_Qty × Conversion_Qty`.

Unmapped Store/SKU rows remain in the import batch and become non-packable canonical order records where order date and quantity are valid. No Item is guessed from a display name.

## Dates and statuses

The parser preserves raw status and maps the SMB-supported concepts (`completed/selesai/delivered`, `cancel/batal/gagal`, `return/retur`, `refund`, and processing states) into a separate normalized operational status. `Waktu Pesanan Dibuat` drives demand and the read-only daily operational summary. `Waktu Selesai` is retained for the later 7B revenue event and is never substituted with Order Date.

## Import and exceptions

XLSX is parsed using the Python standard library ZIP/XML reader; CSV is supported because the legacy flow already used row dictionaries and the repository has CSV exchange infrastructure. Required headers are matched by explicit header names, not column positions. Missing headers fail clearly. Invalid quantity/date, duplicate source-row identities, unmapped Store/SKU, and inactive mapping are retained as actionable row exceptions. Same legal entity, source type, and file hash replay the same batch. The commit is idempotent and source identity is stable across re-imports, including Store aliases that resolve to the same canonical Store.

If a source changes after physical packing, Warehouse history is preserved and an open `SOURCE_CHANGED` exception is recorded. A later cancellation never silently reverses physical OUT and does not fabricate a return receipt.

## Warehouse demand and packing

Only mapped canonical Items with positive Internal Qty enter `warehouse_demand`. Demand reports required, packed, remaining, available stock, valuation readiness, and shortage. Cancelled/returned/refunded orders and source-change lines are excluded from new demand.

Packing is Omnichannel-owned as an operational document, but its physical effect is delegated to Warehouse `post_stock_movement` with movement type `OMNI_PACKING`, source type `OMNI_PACKING`, and source key `OMNI_PACK|<packing-line UUID>`. The existing Warehouse locks, weighted-average costing, valuation readiness, negative-stock protection, posting sequence, and idempotency remain authoritative. Warehouse movement stores the immutable unit cost and total value used for the issue; no Finance journal or COGS journal is created in 7A.

## Finance and return boundary

Phase 7A creates no JournalEntry, AR, AP, Payment, bank transaction, marketplace balance, settlement, or revenue event. Completion-date revenue, settlement/payout, marketplace fees, full return/refund, adjustments, reconciliation, POS, and final store analytics remain Phase 7B/7C or the later Finance boundary. Return import does not create `RETURN_IN`; the future path remains Quality acceptance followed by Warehouse return receipt.

## UI, security, and audit

Permission-aware full-page surfaces are provided for Ringkasan Omni, Import BigSeller, Pesanan, Antrian Gudang, Packing, and Exception Mapping. Upload, commit, draft creation, and posting are mutation actions; posting requires the Omnichannel packing permission and delegates stock to Warehouse. Legal-entity selectors and backend queryset scoping are authoritative. Import preview and all GET pages are read-only with respect to orders, packing, stock, and finance facts. Import, commit, mapping exception, packing creation, and packing posting are audited.

## Migrations and tests

New migrations only:

- `apps/omnichannel/migrations/0001_initial.py`
- `apps/omnichannel/migrations/0002_remove_omniorderline_omni_order_line_conversion_positive_and_more.py`
- `apps/omnichannel/migrations/0003_alter_omniimportrow_mapping_status_and_more.py`
- `apps/warehouse/migrations/0003_alter_stockmovement_movement_type.py` (new `OMNI_PACKING` choice)

The Phase 7A test module verifies exact variations, quantity and date snapshots, XLSX parsing, same-file re-import idempotency, unmapped retention, zero movement on import, Warehouse-only packing OUT, partial/repeated packing limits, shortage, cancellation-after-packing exception, and permission-aware read-only routes. The complete gate also covers the existing Warehouse, Quality, Production, Purchasing, Sales, Channels, Home, and migration suites.

## Deferred Phase 7 scope

Not implemented here: completion-date revenue/AR, settlement and fees, payout/bank handoff, marketplace return/refund and adjustment workflows, settlement reconciliation, POS, and final store profitability analytics. Phase 7 remains open for 7B/7C; this document does not redefine the locked Project Plan.
