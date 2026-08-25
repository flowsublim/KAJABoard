# KAJABoard Phase 2A Master Foundation Result

**Phase:** 2A — Organization + Partners + Catalog + Master UI Foundation  
**Execution date:** 25 August 2026  
**Status:** IMPLEMENTED — AWAITING OWNER REVIEW  
**Phase 2B / 2C status:** NOT STARTED

## 1. Implemented scope

Phase 2A adds only canonical master data and the minimum authenticated Master / Settings workspace:

- extension of the accepted `LegalEntity` identity and tax/reporting fields;
- `BusinessUnit`, `Department`, `CostCenter`, and Warehouse master records;
- canonical `BusinessPartner` with effective multi-role assignments;
- `UOM`, classification-only `ItemCategory`, and canonical `Item` identities;
- Item-to-parent variant relationships without a second SKU or stock identity;
- explicit item eligibility flags and tax/valuation configuration hooks;
- opt-in effective periods, protected relationships, constraints, and indexed selectors;
- explicit, atomic service-layer create/edit/activate/deactivate and partner-role mutations;
- append-oriented audit evidence using the accepted Phase 1 audit service;
- organization-membership-scoped selectors and Django model-permission-checked views;
- read-only Django Admin inspection for Phase 2A masters;
- responsive server-rendered Master workspace, lists, forms, lifecycle actions, and authentication UI.

Warehouse in this phase is master data only. No physical quantity, balance, receipt, issue, costing,
reservation, or StockMovement exists.

## 2. Historical safety and as-of contract

Phase 2A masters use stable UUIDs plus `effective_from`, nullable `effective_to`, and `is_active`.
Selectors exist for effective legal entities, Cost Centers, warehouses, partners/roles, and Items.
The database rejects an effective end before its start. Deactivation ends the effective interval and
retains the row; protected references prevent silent deletion of related master history.

Later transaction services must select configuration as of the business transaction date and snapshot
the fields needed to explain the document after master changes. Minimum snapshot guidance:

| Master source | Later transaction snapshot |
|---|---|
| Legal Entity | legal/display name, address/document identity, NPWP/NITKU, PKP status, reporting currency, timezone |
| Business Unit / Department / Cost Center | stable ID, code, display name, and applicable eligibility/configuration flags |
| Warehouse | stable ID, code, name, and document/fulfillment address where relevant |
| Business Partner | stable ID/code, role used, display/legal name, tax identity, address/contact/PIC, payment and credit terms, and credit limit where relevant |
| Item / UOM | stable Item/UOM IDs, code/name, UOM code and applicable precision, eligibility, tax/valuation reference, variant description, price/cost reference only when the accepted transaction rule uses it |

Reference cost and selling price remain master defaults only. Later transactions must snapshot an
accepted transaction price/cost; changing a master default must never recalculate posted history.

## 3. Explicit behavior boundaries

- Cost Center category and name do not make a cost production overhead. The separate
  `is_production_overhead_eligible` configuration is the only Phase 2A eligibility fact; the later
  Purchasing three-part gate remains mandatory.
- Item kind, category, subcategory, and names do not control inventory or accounting behavior.
  Sales/purchase/production/inventory eligibility is explicit.
- Item category is classification only.
- A variant remains a canonical Item related to an optional parent Item; it does not create another
  quantity or valuation ledger.
- A customer and vendor are roles of one `BusinessPartner`; no competing Customer/Supplier tables exist.
- No UOM conversion table is implemented. Cross-dimension conversion is therefore impossible in 2A.
- Tax identifier fields are normalized conservatively; no speculative NPWP/NITKU format or tax
  calculation is enforced.
- No automated journal, COA, Purchase Category, Store, SKU Mapping, document numbering, or transaction
  state machine is present.

## 4. Phase 1 carry-forward disposition

The accepted Phase 1 migration files remain unchanged. Phase 2A supplies the previously deferred
minimum application shell only for Master / Settings operation. These Phase 1 plan capabilities remain
deferred until an accepted use case requires them:

- detailed roles, action thresholds, segregation, and business-unit data scope;
- generic approvals;
- notifications and My Work;
- attachments and comments;
- operational document/numbering engine;
- generic transaction workflow/state machinery;
- background jobs and repair queues;
- 2FA and deployment monitoring work.

The application shell must not be interpreted as authorization for those systems.

## 5. Deferred / unresolved gates

- `Location` is not implemented. It remains a later Warehouse master decision because no accepted
  location/bin behavior is needed by Phase 2A and inventory behavior must not be invented.
- Exact UOM precision policy by dimension/category remains a later business gate. Phase 2A stores a
  configurable precision value and implements no conversion.
- Named master stewards, maker/checker responsibilities, and detailed data scopes remain unresolved;
  Django model permissions plus the accepted Legal Entity membership scope are the current boundary.
- Exact NPWP/NITKU validation and tax calculation remain deferred to the tax implementation gate.
- Final KAJA brand assets, typography, and packaged Bootstrap/Tabler component assets remain a UI design
  decision; Phase 2A uses the accepted semantic tokens and a small local responsive stylesheet.
- Import/export adapters are not implemented in 2A.

## 6. Prohibited Phase 2B / 2C and transaction scope

Not implemented: Purchase Category, Accounting Treatment routing, Store, SKU Mapping, COA, COA
Mapping, Finance resolver, DocumentSequence, tax calculation, Sales Order, purchase transaction, SPK,
Production, StockMovement, Warehouse receipt/issue, QC transaction, Omnichannel order, POS, Journal,
AR/AP, Payment, Project transaction, or incentive accrual.

## 7. Migration boundary

Phase 2A creates only new migrations:

- `apps/organizations/migrations/0002_businessunit_costcenter_department_warehouse_and_more.py`
- `apps/partners/migrations/0001_initial.py`
- `apps/catalog/migrations/0001_initial.py`

The accepted Phase 1 `0001_initial.py` migrations in Accounts, Core, and Organizations are unchanged.
