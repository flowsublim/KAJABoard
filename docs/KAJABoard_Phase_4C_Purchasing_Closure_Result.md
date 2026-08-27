# KAJABoard Phase 4C - Purchasing Closure

## Completed
- Read-only procurement Finance source and payable readiness for accepted subcontract service costs.
- Finance mapping is resolved only through the Finance resolver; unresolved configuration is `BLOCKED_MAPPING`.
- Production-overhead purchase source contract and truthful vendor analytics selector.
- Project profitability now presents confirmed purchasing commitment separately from unavailable actual cost.
- Vendor Analytics summary and legal-entity-scoped detail/drill-down use authoritative Purchasing sources only.
- Purchase Order, SPK, Kirim Bahan, and Terima Maklun provide modal print previews without `target="_blank"`.

## Boundary
- PO confirmation is commitment, not AP, receipt, asset, or expense posting.
- Accepted maklun service costs provide payable-source evidence only; no AP row is persisted.
- JASA_UMUM remains unallocated.

## Migrations
- None. This closure is selector/read-contract integration only.

## Verification
- Vendor Analytics summary/detail/drill-down and PO, SPK, Kirim Bahan, and Terima Maklun modal previews are covered by focused regression tests.
- Final suite: 158 passed. No `target="_blank"` is used by the Purchasing preview templates.

## Deferred
- Warehouse posting and costing; AP/vendor bill/journal/payment; Production WIP and overhead/HPP allocation; shared service allocation; vendor payment/quality metrics.

No physical stock mutation, AP, journal, payment, Production WIP, or final HPP is implemented. Legacy baseline remains unchanged.
