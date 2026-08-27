# KAJABoard Phase 6A - Warehouse Inventory Core

## Completed

Added the Warehouse module as the sole owner of physical inventory effects.
`StockMovement` is immutable posted physical history with source lineage,
monotonic posting sequence, idempotency, reversal support, and explicit
valuation status. `InventoryValuationState` is a Warehouse projection used for
concurrency-safe quantity and weighted-average valuation.

Internal Production integrations are implemented for material issue requests
and READY_FOR_GUDANG finished-goods receipt candidates. Both support partial
documents, stable source identity, entity/line validation, idempotent posting,
negative-stock protection, and append-only reversal history. A receipt with no
authoritative Production cost enters physical quantity as PENDING_VALUATION;
unknown cost is never stored as zero.

Production actual material-cost and Warehouse accepted-quantity selectors are
read-only integration contracts. Explicit receipt valuation finalization is
available only for an authoritative READY Production cost snapshot. No module
other than Warehouse writes StockMovement.

## UI and permissions

Added permission-aware Warehouse routes for Ringkasan Gudang, Stok,
Pergerakan Stok, Issue Bahan Produksi, and Terima Hasil Produksi. GET/report
pages do not create movements, receipts, issues, or valuation changes.

## Migration and tests

- `apps/warehouse/migrations/0001_initial.py`
- Fresh SQLite migration from zero passed.
- Full suite: **178 passed**.
- Django check, Ruff, diff check, and migration drift check passed.

## Boundaries and deferred work

Warehouse is the physical ledger owner; Production, Purchasing, Sales, and
Finance do not write stock. No formal Quality decisions, Sales/POS/returns,
stock opname, generic adjustments, Finance journal/AP/payment, or unsupported
Warehouse workflows are claimed complete. Pending valuation remains explicit;
Production HPP and Warehouse valuation are not fabricated from reference cost.
