# KAJABoard Phase 4B2 - Subcontract Flow Result

## Completed
- Kirim Bahan and Terima Maklun source transactions consume accepted 4B1 APPROVED SUBCONTRACT SPKs.
- Dispatch lines trace directly to `WorkOrderMaterialAllocation`; accepted output lines trace directly to `WorkOrderOutput`.
- Partial/repeated dispatch and receipt are derived from active confirmed/accepted records.

## Models and Migrations
- Added dispatch, receipt output, and controlled service-cost models in purchasing migration `0004_phase_4b2`.
- No 4B1 model or historical migration was redesigned or changed.

## Quantity and Cost Rules
- Over-dispatch and over-receipt are blocked under transactional row locks.
- `JASA_SPESIFIK_VARIAN` requires an output link; `JASA_UMUM` remains an unallocated shared source.
- Material reference cost can remain unavailable; it is never converted to zero.

## Warehouse Candidates
- Confirmed dispatch exposes deterministic `PURCH_MATL_ISSUE|<line-id>` sources.
- Accepted output exposes deterministic `PURCH_SUBCON_RECEIPT|<line-id>` sources.
- These are read contracts only: no physical stock mutation occurs.

## UI
- Purchasing sidebar now includes permission-scoped Kirim Bahan and Terima Maklun entries.
- Lists and details remain pages; create, line, and lifecycle actions use the existing modal/toast foundation.

## Tests
- Focused tests cover partial dispatch/receipt, allowance/remaining calculations, candidate identity, nullable cost, specific/shared service sources, and fulfillment status.

## Deferred
- Shared `JASA_UMUM` allocation, final HPP, supplier payable/AP, payment, Warehouse posting, Production WIP, and vendor analytics remain deferred to later phases.

No Finance journal/AP/payment, Production WIP, or physical Warehouse movement is created. Legacy baseline remains unchanged.
