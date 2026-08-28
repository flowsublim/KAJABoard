# KAJABoard Phase 6C — Warehouse Operational Flows Result

Status: implemented for checkpoint review; no commit, push, or tag created.

## Scope completed

Phase 6C extends the Phase 6A `StockMovement` / `InventoryValuationState` ledger. All physical effects use the existing serialized Warehouse posting primitive, weighted-average costing, negative-stock protection, posting sequence, reversal, audit, and idempotency controls.

- Purchase INVENTORY receipt: only CONFIRMED PO lines with an explicit `AccountingTreatment=INVENTORY` snapshot are candidates. Partial and repeated receipt documents lock each PO line, preserve PO/category/vendor/entity/project lineage, and use the PO line unit-price valuation snapshot.
- Subcontract/maklun receipt: only physical inventory Items from ACCEPTED Purchasing receipt lines are eligible. Quality PASS authorization is required and is consumed per exact receipt line. JASA-only/service Items never create stock. A ready Production cost snapshot supplies cost; otherwise the receipt is safely `PENDING_VALUATION` with `None` cost/value.
- Sales Delivery issue: only POSTED Sales Delivery lines are candidates. Partial and repeated Warehouse issues are allowed up to the posted delivery quantity. Sales history is unchanged. OUT uses the current Warehouse average and stores immutable issue cost/value.
- Stock Opname: `StockCount` / `StockCountLine` snapshots system quantity and posting sequence. Counted-minus-snapshot variance creates `OPNAME_GAIN` or `OPNAME_LOSS`; zero variance creates no movement. Stale snapshots are blocked.
- Controlled adjustment: `InventoryAdjustment` / lines require reason, reference, approval permission, and authoritative valuation. Positive and negative changes are movement-backed and reversible.
- Internal consumption: `INTERNAL_CONSUMPTION` is distinct from `PRODUCTION_MATERIAL_ISSUE`, costs at current weighted average, and exposes a Finance candidate without creating a journal.
- Supplier return: `SUPPLIER_RETURN` is Warehouse OUT, costs at current weighted average, preserves supplier/PO/receipt lineage where available, and never posts a debit note.

## Costing and reconciliation

Known movement value is signed by direction when reconciling. Pending cost remains `None`, never zero. Reconciliation compares state quantity/value/status/last sequence to active movement history and is read-only; GETs do not repair balances or post accounting/stock effects.

Finance candidates are deterministic read contracts (`WAREHOUSE_PURCHASE_RECEIPT`, `WAREHOUSE_SUBCONTRACT_RECEIPT`, `WAREHOUSE_SALES_ISSUE`, `WAREHOUSE_INTERNAL_CONSUMPTION`, `WAREHOUSE_SUPPLIER_RETURN`, `WAREHOUSE_OPNAME_GAIN`, `WAREHOUSE_OPNAME_LOSS`, `WAREHOUSE_ADJUSTMENT`, and Warehouse reversals). They contain source lineage, movement, dimensions available from the operational source, valuation, date, and mapping-readiness metadata. Phase 6C creates no JournalEntry, GL, AP, AR, payment, cash, or bank record.

## Quality and ownership boundary

Quality creates and posts inspection dispositions only. Quality PASS is read by Warehouse as authorization; Quality never writes `StockMovement`. Purchasing, Sales, and Production expose source candidates only. Finance remains the accounting owner. Customer/Marketplace return-in is intentionally selector/service-ready only and has no competing Warehouse return business document.

## Concurrency and idempotency

PO line, Delivery line, source output/receipt line, and the Warehouse sequence/state are locked during posting. The same idempotency key and payload replays the original result; a conflicting payload is rejected. Posted documents are append-only and reversal creates a linked compensating movement using the original movement valuation. Negative stock is blocked for every Phase 6C OUT path.

## UI and permissions

Permission-aware Warehouse routes now expose dashboard, stock, movements, purchase receipts, subcontract receipts, sales issues, production issue/receipt, stock opname, internal consumption, adjustments, supplier returns, and reconciliation. Operational pages are read-only until their modal mutation forms are introduced; no Marketplace/POS placeholders are shown. Direct view access remains protected by Django authentication and model permissions. Print remains read-only and no GET route mutates state.

## Migration and tests

Added only `apps/warehouse/migrations/0002_alter_stockmovement_movement_type_and_more.py`; `warehouse/0001_initial.py` and every non-Warehouse historical migration remain unchanged. Fresh SQLite migration and `makemigrations --check --dry-run` are part of the release gate.

Phase 6C regression coverage includes purchase partial receipt/cost snapshot, Sales partial issue/COGS/history preservation, subcontract PASS limit and pending valuation, internal consumption, supplier return, stock-opname variance, and the existing Phase 6A/6B ownership/read-only tests.

## Phase 6 closure boundary

Phase 6 is eligible for closure after the complete automated gate passes, including Django check, full pytest, Ruff check/format, diff check, migration check, fresh SQLite migration, Warehouse/Quality routing, authenticated Home, and Phase 4/5/Sales/6A/6B regressions. Deferred to later phases: Marketplace packing/fulfillment and imports/returns, POS, canonical customer return-in, Finance journals/AP/AR/payment/cash/bank, incentive/CPO/sales commission, quarantine subsystem, and automatic Production rework WIP reinjection.
