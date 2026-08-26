# KAJABoard Phase 4A Purchasing Core Result

## Completed
- Added canonical Purchase Order and stable Purchase Order Line commercial records with configured `PURCHASE_ORDER` numbering, vendor role validation, Decimal totals, explicit state control, and audit events.
- Purchase Category classification is snapshotted from explicit master metadata at line creation; no behavior uses category names.
- Confirmed lines expose committed-cost read sources and treatment-filtered downstream source contracts.
- Added modal-first Pembelian list/detail/create/line/action UI and a permission-aware operational Purchasing sidebar child.

## Files changed
- `apps/purchasing/` models, services, selectors, views, forms, URLs, templates, migration, and tests; sidebar and Phase 4A documentation.

## Migrations
- `apps/purchasing/migrations/0002_phase_4a.py`
- No historical migration was modified.

## Tests
- `python manage.py check`
- Focused Purchasing tests plus full repository gate.

## Business rules verified
- Vendor is the canonical Business Partner with effective VENDOR role.
- Purchase Category routing is explicit and snapshotted: INVENTORY, ASSET, EXPENSE, SERVICE, and MAKLUN.
- EXPENSE/SERVICE require the master Cost Center; production snapshot remains master-rule driven.
- Confirmed Purchase Orders are commercial commitments; cancelled orders no longer expose active commitments.

## Candidate contracts
- `committed_cost_sources()` returns line-stable confirmed commercial commitments.
- Treatment-filtered sources support future Warehouse receipt, Fixed Asset, AP/expense/service, and production-overhead owners without writing their records.

## Unresolved
- Purchase Request is not implemented because no accepted Phase 4A use case requires it.
- Warehouse receipt, fixed asset register, AP, journal, payment, SPK, Kirim Bahan, and Terima Maklun remain future owner work.

## Risks / follow-up
- Purchasing has no physical stock ledger, payment ledger, Warehouse movement, Finance journal/AP/payment, or Phase 4B/4C workflow.
- Modal/toast/sidebar foundation is reused. Legacy baseline remains unchanged.
