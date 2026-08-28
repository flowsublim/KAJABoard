# KAJABoard Phase 6B - Quality Framework / QC Authorization

## Completed

Phase 6B adds a reusable Quality decision framework in `apps/quality/`.
`QualityInspection` is a UUID-based document with stable source-line identities,
immutable posted quantities, inspector snapshots, evidence metadata, reasons,
audit events, and append-only line/document reversal lineage.

The document workflow is `DRAFT -> POSTED -> REVERSED`. Result is quantity based
per line: `PASS`, `HOLD`, `REJECT`, or `REWORK`. Mixed lines retain all quantity
splits and are not forced into one result. `LEGACY_UNMAPPED` is accepted only as
an imported ambiguous disposition; it is review-only and can never authorize
Warehouse or count as PASS.

Quality does not write physical stock. Warehouse remains the sole physical
ledger owner and Finance remains untouched by this phase.

## Production finished goods integration

Production `ProductionWarehouseHandoverLine` remains the source of the exact
ready quantity. The Quality queue reports ready, inspected, pending, PASS, HOLD,
REJECT, REWORK, and Warehouse-accepted quantities per handover line/output.
Multiple partial inspections are allowed, but source-line locking prevents the
combined posted inspected quantity from exceeding that line's READY quantity.

Warehouse production receipt posting now consumes the public Quality PASS
authorization contract. New Production finished-goods receipt lines cannot be
added or posted above `remaining_pass_quantity`; HOLD, REJECT, REWORK, and
LEGACY_UNMAPPED quantities are never normal receipt authorization. Existing
posted Phase 6A receipts remain historical pre-Quality records; no fake PASS
inspection is backfilled.

Warehouse receipt posting locks source lines and re-reads authorization inside
the transaction, so concurrent receipts cannot jointly consume more PASS than
authorized. Quality posting creates no `StockMovement`; only the Warehouse
receipt service creates physical IN.

## Result boundaries

- PASS authorizes normal downstream Warehouse disposition only.
- HOLD remains source-present but availability-blocked. No quarantine location
  or fabricated quarantine movement was introduced.
- REJECT records the Quality decision and source lineage only. Scrap,
  return-to-production, loss accounting, and stock OUT remain future approved
  dispositions.
- REWORK exposes `QUALITY_REWORK|<quality-line-uuid>` with legal entity,
  WorkOrder/output when available, Item, quantity, reason, and active status.
  Production WIP is not silently mutated.
- Production reject entries remain distinct from Quality REJECT entries.

## Other source readiness

Accepted `SubcontractReceiptOutputLine` records can create exact
`SUBCONTRACT_RECEIPT` Quality inspections with receipt/output/Item lineage and
PASS authorization. Full Warehouse maklun receipt posting is not claimed
complete because that Warehouse flow is not yet implemented.

Source-neutral return contracts support `CUSTOMER_RETURN` and
`MARKETPLACE_RETURN` without inventing missing return models. Registration or a
PASS decision alone creates no stock movement; future `RETURN_IN` remains a
Warehouse-owned flow.

Supplier incoming, random-inspection UI, and return end-to-end workflows are
not claimed complete merely because the extensible inspection types exist.

## Reasons, inspector, and corrections

`QualityReason` supplies scoped stable codes with result applicability. HOLD,
REJECT, and REWORK require a reason; posted lines snapshot the code/text.
Inspector identity reuses Accounts `Employee`, with legal-entity validation and
posted display snapshots. Optional photo/file handling is limited to evidence
reference/metadata because no document-management subsystem exists yet.

Posted inspection lines are immutable. Reversal retains the original and
creates append-only reversal evidence. Reversal is blocked when a downstream
Warehouse receipt has already consumed PASS quantity, preventing unsupported
stock acceptance. Replacement is a separate inspection/line and does not edit
siblings.

## UI and permissions

Quality adds permission-aware routes for Ringkasan Quality, Inspeksi, Antrian
Produksi, draft creation, posting, and correction/reversal. Dashboard, list,
detail, and queue GETs are read-only. Mutations are service calls and modal-
compatible routes; backend permissions and legal-entity scope remain
authoritative. The sidebar and Home module card show only when the user has
Quality view permission.

## Migration and verification

- `apps/quality/migrations/0001_initial.py`
- No historical Warehouse, Production, Purchasing, Accounts, Sales, or legacy
  files were modified.
- Quality services use transactions, source-line locks, stable UUIDs,
  idempotent posting/reversal claims, and audit events.
- Phase 6B tests cover mixed and partial quantities, source capacity,
  Warehouse PASS limits, reversal dependency guard, LEGACY_UNMAPPED review,
  rework contract, subcontract readiness, route permissions, and GET
  non-posting behavior.

## Deferred

Full customer/marketplace return processing, Warehouse `RETURN_IN`, supplier
incoming, quarantine locations, scrap movements, Production rework WIP
reinjection, supplier return, stock opname, generic adjustments, Sales Delivery
OUT, marketplace packing, POS, CPO fee, and all Finance journals/AP/payments
remain later-phase work. Quality is an authorization and decision owner; it is
not a stock or Finance posting owner.
