# AGENTS.md — KAJABoard

## Project Identity
Project: **KAJABoard**
Company: **PT KAJA VASTRALOKA KREASINDO**
Architecture: **Django Modular Monolith**
Backend: **Python 3.13 + Django 5.2 LTS**
Database: **PostgreSQL**
Frontend baseline: **Django Templates + HTMX + Alpine.js + Bootstrap/Tabler**
Deployment target: **PythonAnywhere Paid / WSGI**

Primary business benchmark: accepted **SMB Google Apps Script + Google Sheets** implementation and accepted patches.

Legacy code is business-behavior evidence, not a coding-style template.

## Mandatory Reading Before Any Work
Read first:
1. `docs/KAJABoard_Project_Plan_FINAL_v2.0.md`
2. all relevant files in `docs/`
3. relevant source/reference files under `legacy/smb_gas/`
4. existing tests and service-layer code for the affected domain.

If sources conflict, precedence:
1. latest accepted business decision;
2. accepted SMB rule / accepted patch;
3. KAJABoard Project Plan;
4. legacy implementation detail.

Do not silently invent behavior.

## Functional Parity, Not Endpoint Parity
The following may change:
- GAS function names;
- `google.script.run` endpoints;
- sheet names and columns;
- HTML/JS layout;
- helper names;
- file structure;
- database schema;
- caching/auth implementation.

The following must be preserved unless explicitly changed:
- workflow;
- validation;
- calculations;
- document relationships;
- stock effects;
- accounting effects;
- partial fulfillment;
- reconciliation;
- exception handling;
- accepted reports/prints;
- source traceability.

Every legacy endpoint/use case must be classified:
`RETAIN`, `UPGRADE`, or `REMOVE-DEADCODE`.
`REMOVE-DEADCODE` requires explicit justification.

## Domain Ownership
### Warehouse
Warehouse is the sole owner of physical inventory movement.

Other modules emit candidates/events:
- Sales Delivery → Warehouse Goods Issue
- Purchase Receipt → Warehouse Goods Receipt
- Production Finished Goods → ProductionWarehouseHandover → Warehouse Receipt
- Omni Packing → Warehouse Goods Issue
- POS Sale → Warehouse Goods Issue
- QC Accepted Return → Warehouse Return Receipt

### Finance
Finance is the sole owner of:
- journals;
- GL;
- AR/AP;
- cash/bank;
- marketplace balance;
- fixed assets;
- depreciation;
- closing.

Operational modules emit business events/source documents only.

## No Hardcoded COA
Automated journals must use:
`Business Event → Accounting Context → Master COA Mapping → Finance Resolver → Journal`

Allowed hardcode:
- stable Event_Code;
- stable Line_Role;
- controlled state identifiers.

Never hardcode transactional COA codes/names in operational modules.

## Purchasing Rules
Allowed AccountingTreatment:
- INVENTORY
- ASSET
- EXPENSE
- SERVICE
- MAKLUN

Rules:
- ASSET never becomes inventory stock.
- EXPENSE/SERVICE require Cost Center.
- MAKLUN follows subcontract/work-order flow.
- Production overhead only if:
  `EXPENSE/SERVICE + production-eligible Cost Center + SnapshotProduction = TRUE`.
- Never infer treatment using category-name substring matching.

## Production Rules
Use stable line IDs.
WIP must be item-safe.

Per output:
- Available Sewing = Cut - Sew - Reject Cut
- Available QC = Sew - QC - Reject Sew
- Available Warehouse = QC - Handover - Reject QC

SPK may close only when every output item individually fulfills completion rules.
One item's surplus cannot hide another item's shortage.

HPP may include:
- material;
- direct labor;
- eligible extra direct cost;
- production overhead;
- subcontract cost;
- approved production cost.

Payment of an accrued payable must not create expense twice.

## Omnichannel Rules
Order-line identity:
`Order Number + SKU + Variation`

Persist:
- Marketplace_Qty
- Conversion_Qty
- Internal_Qty

Dates:
- `Waktu Pesanan Dibuat` = operational date
- `Waktu Selesai` = revenue-recognition date
- settlement date ≠ revenue date

Completed marketplace order:
- Dr Marketplace Receivable - Store
- Cr Marketplace Revenue - Store
Exact COA comes from mapping.

Settlement is separate from revenue recognition.
Payout moves Marketplace Balance to Bank.
Return/refund does not erase original revenue history.
Stock return happens only after QC acceptance.

POS:
- strict internal Item;
- qty > 0;
- price snapshot;
- atomic/idempotent stock issue;
- COGS from inventory costing;
- Finance event emitted.

## Sales Rules
Preserve:
`Sales Order/PO → Partial Delivery/Surat Jalan → Invoice → AR/SOA → Payment`

Partial delivery is mandatory.
Delivery qty cannot exceed remaining qty.
Sales does not own payment ledger.
Finance owns payment and AR.

## QC / Return Rules
QC results:
`PASS`, `HOLD`, `REJECT`, `REWORK`

Return import/registration alone must not modify physical stock.
Only accepted outcome may create Warehouse RETURN_IN.

## Accounting Integrity
Always enforce:
- Debit = Credit
- unique source posting
- posted journal immutability
- reversal/adjustment for correction
- period validation
- source traceability
- control-account reconciliation
- no duplicate expense on settlement
- reports must not create postings

## Inventory Integrity
Always enforce:
- unique source key
- idempotent stock receipt/issue
- no accidental duplicates
- no negative stock by default
- controlled reversal
- stock opname posts variance, not arbitrary overwrite
- inventory quantity comes from posted Warehouse movements

## Django Implementation Rules
Business logic belongs in service/application layer, not templates/JS/model save/signals.

Preferred structure:
`apps/<domain>/{models.py,services/,selectors/,forms/,views/,urls.py,admin.py,tests/,migrations/}`

Use:
- `transaction.atomic()`
- `select_for_update()` where concurrency matters
- DB constraints
- indexes
- idempotency keys
- explicit state transitions

Never rely on UI validation alone.

## Database Rules
PostgreSQL is production source of truth.
Use stable keys, FKs, unique constraints, indexes, audit timestamps, source IDs/keys.
Do not silently cascade-delete posted accounting/stock history.
Historical transaction meaning must not change when master data changes.

## Performance
Avoid:
- full-table scans per request
- N+1 queries
- repeated master mapping lookups
- excessive writes
- unbounded reports

Use:
- indexes
- select_related/prefetch_related
- bulk ops
- pagination
- safe configuration cache

Cache is not ledger source of truth.

## Security
Minimum:
- Django secure auth
- CSRF
- secure sessions/cookies
- DEBUG=False in prod
- env secrets
- least privilege
- role + action + data scope
- upload validation
- audit logging
- no secrets in Git

## Testing Is Mandatory
Required critical regression tests include:
- purchase asset does not create inventory stock
- office expense does not enter production HPP
- production expense enters HPP once
- production line edit does not delete sibling lines
- SPK cannot close when one output is short
- marketplace completed order uses completion date
- settlement does not create revenue again
- return does not delete original revenue
- POS requires internal item
- stock source cannot post twice
- partial delivery cannot exceed remaining qty
- payment does not duplicate accrued expense

No critical feature is complete without tests.

## Idempotency
Mandatory for:
- inventory receipt/issue
- warehouse handover
- delivery
- invoice posting
- payment
- journal posting
- marketplace import
- settlement/adjustment/return import
- POS
- incentive accrual
- approval-critical actions

## Audit Trail
For critical records capture:
- entity/record
- action
- before/after
- changed fields
- user
- timestamp
- reason
- source
- approval reference
- request/idempotency key

No silent delete for posted transactions.

## State Machines
Critical state must use controlled choices.
Illegal transition must be rejected in service layer.

## Code Quality
Before marking work complete:
1. run formatter/linter
2. run tests
3. inspect diff
4. inspect migrations
5. verify permissions
6. verify audit
7. verify idempotency
8. verify stock/accounting ownership
9. report known limitations

No commented-out dead implementation or temporary accounting/stock hardcode.

## Phase Discipline
Current starting phase:
`PHASE 0 — Source Freeze & Functional Audit`

Before Phase 1, create:
- `docs/KAJABoard_Business_Process_Map.md`
- `docs/KAJABoard_Module_Ownership.md`
- `docs/KAJABoard_Data_Dictionary.md`
- `docs/KAJABoard_Event_Matrix.md`
- `docs/KAJABoard_Workflow_Status_Matrix.md`
- `docs/KAJABoard_Legacy_Endpoint_UseCase_Matrix.md`
- `docs/KAJABoard_Functional_Parity_Register.md`
- `docs/KAJABoard_Architecture.md`
- `docs/KAJABoard_UI_Design_System.md`

Do not start Django implementation until Phase 0 is reviewed and accepted.

## Phase 0 Endpoint/Use-Case Register
For each legacy function/use case record:
- Legacy Module
- Legacy Function
- Triggered By
- Business Use Case
- Reads
- Writes
- Validation
- Stock Impact
- Accounting Impact
- Target Domain
- Target Service/View
- Target State Transition
- Target Test
- Decision
- Notes

## If Something Is Unclear
Do not guess silently.
Create an `UNRESOLVED` entry with:
- question
- source conflict
- affected modules
- stock impact
- accounting impact
- recommended interpretation

Continue other unblocked work.

## Completion Response Format
At the end of a Codex task report:
- Completed
- Files changed
- Migrations
- Tests run
- Business rules verified
- Unresolved
- Risks / follow-up

Never claim completion if required tests were not run.

## Final Non-Negotiables
1. Functional parity over endpoint parity.
2. Warehouse owns physical stock.
3. Finance owns accounting.
4. No hardcoded auto-journal COA.
5. Purchase accounting treatment is explicit.
6. Asset purchase does not become stock.
7. Expense/service requires Cost Center.
8. Production overhead is rule-driven.
9. Production is item-safe.
10. Marketplace revenue uses Waktu Selesai.
11. Settlement is not revenue recognition.
12. Return/refund preserves original revenue history.
13. POS uses actual internal Item.
14. Critical operations are idempotent.
15. Posted records use reversal/adjustment for correction.
16. Historical master changes do not rewrite history.
17. Reports do not create postings.
18. Every important number is explainable and traceable.
