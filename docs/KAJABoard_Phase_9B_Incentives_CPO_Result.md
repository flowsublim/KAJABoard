# KAJABoard Phase 9B: Generic Incentive Engine & CPO Finished Goods Fee

**Status:** COMPLETED (Sub-checkpoints 9B1, 9B2A, 9B2B, & 9B3 Passed)  
**Apps Affected:** `apps/incentives`, `apps/production`, `apps/projects`, `apps/finance`  
**Baseline HEAD:** `13393ea0acc2dd2b929a51c5da3c2a1aa7ab7214`  

---

## 1. Executive Summary & Domain Authority

Phase 9B introduces the **Generic Incentive Engine**, an operational ledger and calculation engine shared across:
1. **CPO Finished Goods Fee** (Chief Production Officer / Production SPV fee upon finished goods receipt into warehouse);
2. **Sales Commission / Sales Fee** (commercial sales incentives, to be specialized in Phase 9C).

### Authority & Precedence
- **Project Plan Sections 32 & 33**: The Generic Incentive Engine manages effective-dated rules, deterministic rule selection, calculation evaluation, and immutable accruals.
- **Finance Boundary**: Finance remains the **sole accounting owner**. The incentive engine does **not** create or mutate `JournalEntry`, `JournalLine`, `PayableEntry`, `Payment`, `Cash`, or `Bank` records.
- **Warehouse Boundary**: Warehouse is the **sole owner of physical stock**. Warehouse receipts emit operational completion candidates, but the incentive engine does not alter stock movements or inventory valuation.
- **Whole-Rupiah Accounting**: All monetary accruals are strictly whole Rupiah. Fractional-Rupiah calculation results are rejected explicitly rather than silently rounded.

---

## 2. Bounded Legacy Findings (`legacy/smb_gas/`)

A bounded read-only discovery of legacy SMB GAS code confirmed:
1. **Fee SPV / Setor Gudang**: In `legacy/smb_gas/produksi/Index.html` (lines 216, 375), the production process option is explicitly named:
   ```html
   <option value="Setor Gudang" class="fw-bold text-success">Setor Gudang (Fee SPV)</option>
   ```
2. **Master Tarif Produksi**: In `legacy/smb_gas/produksi/Index.html` (lines 208â€“229) and `Kode.gs` (lines 740, 761):
   - Rates were configured per process (`Setor Gudang`) and product (`item.produk` / Item scope).
   - Rate format was Rp / Pcs (`PER_UNIT`).
   - Beneficiary was identified via production PIC (`row[cOutPic] = d.pic`).
   - Calculation was: `item.qty * (tarifMap[d.proses + "|" + item.produk] || 0)`.
3. **No Automatic Ledger / Accrual State**: The legacy system did not persist an immutable accrual ledger or payment state for SPV fees; fees were calculated on-the-fly from production submission records.
4. **Sales Commission**: Legacy references to commission appeared only as platform affiliate fees in omnichannel settlements (`Komisi Affiliate`), confirming that internal sales commission was not yet formalized in legacy GAS.

---

## 3. Incentive Domain Architecture (`apps/incentives/`)

The domain is structured as follows:
```
apps/incentives/
â”œâ”€â”€ apps.py
â”œâ”€â”€ models.py
â”œâ”€â”€ selectors/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ rules.py
â”‚   â”œâ”€â”€ evaluation.py
â”‚   â””â”€â”€ cpo.py
â”œâ”€â”€ services/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ rules.py
â”‚   â”œâ”€â”€ accruals.py
â”‚   â””â”€â”€ cpo.py
â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ test_phase_9b1.py
â”‚   â””â”€â”€ test_phase_9b2a.py
â””â”€â”€ migrations/
    â””â”€â”€ 0001_initial.py
```

---

## 4. IncentiveRule Contract & Effective Dating

### Conceptual Model: `IncentiveRule`
- **Fields**:
  - `legal_entity` (FK, `on_delete=PROTECT`)
  - `code` (Unique per legal entity)
  - `name`
  - `incentive_type`: `CPO_FEE`, `SALES_COMMISSION`
  - `trigger_type`: `FINISHED_GOODS_ACCEPTED`, `INVOICE_POSTED`, `INVOICE_PAID`, `PROJECT_CLOSED`, `APPROVED_CUSTOM_EVENT`
  - `calculation_method`: `PER_UNIT`, `PERCENT_REVENUE`, `PERCENT_MARGIN_PROFIT`, `FIXED`, `TIERED`, `APPROVED_FORMULA`
  - `rate_value` (Decimal, non-negative)
  - `currency` (Default `"IDR"`)
  - `effective_from` (Date)
  - `effective_to` (Date, optional)
  - `item` (Optional FK to `Item`, supporting Item-scoped rates without silent fallback)
  - `is_active` (Boolean)
- **Deterministic Overlap Control**:
  - Active rules matching the exact same `(legal_entity, incentive_type, trigger_type, item)` cannot have overlapping effective date ranges.
  - Overlapping configurations are rejected during rule creation/update and evaluate to `AMBIGUOUS_RULE` if present.

### Calculation Method Scope (Phase 9B1)
- **Supported & Executable**:
  - `PER_UNIT`: `basis_quantity Ã— rate_value` (whole Rupiah enforced).
  - `FIXED`: `rate_value` (whole Rupiah enforced).
- **Preserved Vocabulary / Deferred Evaluation**:
  - `PERCENT_REVENUE`, `PERCENT_MARGIN_PROFIT`, `TIERED`, `APPROVED_FORMULA` return `UNSUPPORTED_METHOD` with an explicit reason code. No arbitrary expression evaluation is guessed.

---

## 5. Pure Evaluation Contract (`evaluate_incentive`)

`evaluate_incentive(...)` is a pure read-only selector:
- Accepts `legal_entity`, `incentive_type`, `trigger_type`, `business_date`, `basis_quantity`, `basis_amount`, `beneficiary`, `item`, `project`.
- Evaluates rule resolution and calculation method.
- **Zero DB Side-Effects**: Creates 0 journals, 0 payments, 0 stock movements, and 0 accrual rows.
- **Explicit Result Statuses**:
  - `READY`: Calculation succeeded with exact whole Rupiah.
  - `NO_RULE`: No active rule found for effective date and scope.
  - `AMBIGUOUS_RULE`: Multiple overlapping active rules found.
  - `INVALID_BENEFICIARY`: Beneficiary missing or invalid.
  - `UNSUPPORTED_METHOD`: Deferred calculation method encountered.
  - `FRACTIONAL_AMOUNT`: Result has fractional subunits (< 1 IDR).

---

## 6. Immutable Accrual Ledger (`IncentiveAccrual`)

- Created via `accrue_incentive(...)` with strict idempotency key enforcement.
- Holds frozen snapshots: `rate_value_snapshot`, `basis_quantity`, `basis_amount`, `beneficiary_code_snapshot`, `beneficiary_name_snapshot`.
- State starts at `ACCRUED`.

---

## 7. State Machine & Reversal Contract

### State Transitions (Phase 9B1)
- Initial state upon accrual: **`ACCRUED`**.
- Explicit service approval: `approve_incentive_accrual(accrual, actor=actor)` transitions `ACCRUED` â†’ **`APPROVED`**.
  - `APPROVED` state does **not** create Finance journals or payables.
- Terminal states `PAYABLE` and `PAID` are reserved for future Finance integration.
- Illegal transitions are strictly rejected.

### Controlled Reversal (`IncentiveAccrualReversal`)
- Accruals in `ACCRUED` or `APPROVED` state can be reversed via `reverse_incentive_accrual(accrual, actor=actor, reason=reason)`.
- Non-empty `reason` is required.
- Creates an explicit one-to-one `IncentiveAccrualReversal` record capturing `reason`, `reversed_by`, and `reversed_at`.
- State becomes **`REVERSED`**.
- Original rate, basis, beneficiary, and amount snapshots remain completely intact.
- Duplicate reversals are blocked.

---

## 8. Sub-checkpoint 9B2A: CPO Finished Goods Fee â€” Authoritative Source, Beneficiary & Accrual

### Authoritative Operational Source & Field Name
- **Operational Trigger**: `WarehouseReceipt` with `state == WarehouseDocumentState.POSTED` and `source_module == "production"`, `source_type == "PRODUCTION_HANDOVER"`.
- **Authoritative Quantity**: `WarehouseReceiptLine.accepted_quantity` (strictly `accepted_quantity`, never `handover_quantity`, planned quantity, or rejected quantity).
- **Lineage**:
  `WarehouseReceiptLine` â†’ `WarehouseReceipt` â†’ `ProductionWarehouseHandover` â†’ `WorkOrder` â†’ `WorkOrderOutput` â†’ `Item`.
- **Project Lineage**: `WorkOrder.project` used strictly when explicitly linked; zero inference from customer, partner, or naming. If null, `accrual.project` remains null.

### Beneficiary Gap Resolution in Production
- Added `cpo_beneficiary` field to `ProductionWarehouseHandover` (`ForeignKey("accounts.Employee", on_delete=models.PROTECT, null=True, blank=True)`).
- Validated:
  - Must belong to the same legal entity.
  - Beneficiary employee must be active (`is_active=True`).
  - Beneficiary cannot be changed if any CPO fee accruals already exist for that handover (enforced both at model `clean()` and in service `update_handover_draft`).
- Migration generated: `apps/production/migrations/0007_productionwarehousehandover_cpo_beneficiary.py`.
- Form updated: `ProductionWarehouseHandoverForm` exposes `cpo_beneficiary` with active employees queryset.

### CPO Selector Contract (`apps/incentives/selectors/cpo.py`)
- Dataclass `CPOCandidate`:
  - `legal_entity`, `receipt_id`, `receipt_line_id`, `source_key`, `receipt_date`, `accepted_quantity`, `item`, `item_code`, `item_name`, `uom_code`, `work_order`, `output`, `project`, `beneficiary_id`, `beneficiary_code`, `beneficiary_name`, `beneficiary_type`, `status`, `existing_accrual`, `reason`.
- Functions:
  - `get_cpo_candidate_for_receipt_line(line)`: Evaluates candidate status (`READY`, `NOT_POSTED`, `INVALID_SOURCE`, `PENDING_BENEFICIARY`, `INVALID_BENEFICIARY`, `INACTIVE_BENEFICIARY`, `PENDING_REVERSAL`, `ALREADY_REVERSED`, `SOURCE_REVERSED`).
  - `get_cpo_candidates_for_receipt(receipt)`: Returns candidates for all lines.
  - `get_eligible_cpo_candidates(legal_entity, ...)`: Pure filter returning only `READY` candidates.
- **Rule Scope**: Exact item-specific rule matching (`item=cand.item`), strictly no silent generic fallback. If no rule is configured for the exact finished good, candidate evaluates with reason code.

### CPO Accrual & Reversal Services (`apps/incentives/services/cpo.py`)
- `accrue_cpo_fee_for_receipt_line(receipt_line, *, actor)`:
  - Enforces `READY` candidate status.
  - Creates idempotent `IncentiveAccrual` with deterministic source key:
    `CPO_FEE|warehouse|WAREHOUSE_RECEIPT_LINE|<receipt_line_id>`
  - Enforces whole Rupiah; blocks fractional amounts.
- `accrue_cpo_fees_for_receipt(receipt, *, actor)`: Batch processor.
- `reverse_cpo_fee_for_receipt_line(receipt_line, *, actor, reason)`: Idempotently creates `IncentiveAccrualReversal` and transitions accrual to `REVERSED`.
- `reverse_cpo_fees_for_receipt(receipt, *, actor, reason)`: Batch receipt reversal.

### Project Profitability Integration
- Updated `apps/projects/selectors/profitability.py`:
  - Read authoritative CPO fee from `IncentiveAccrual` with `project=project`, `incentive_type=IncentiveType.CPO_FEE`.
  - Net active accruals (`ACCRUED`, `APPROVED`, `PAYABLE`, `PAID`) minus reversals.
  - Category `ProjectBudgetCategory.CPO_FEE` transitions from `PENDING_SOURCE` to `AUTHORITATIVE_AVAILABLE` upon first accrual.
  - `ProjectBudgetCategory.SALES_FEE` remains strictly `PENDING_SOURCE`.
  - Profitability does not independently recalculate CPO from current rule Ã— quantity, preserving immutable accrual history.

### Zero Finance & Stock Movement Boundary (Phase 9B2A Scope)
- CPO evaluation and accrual in 9B2A perform **zero** accounting or inventory movements:
  - `JournalEntry.objects.count() == 0`
  - `JournalLine.objects.count() == 0`
  - `PayableEntry.objects.count() == 0`
  - `Payment.objects.count() == 0`
  - `LiquidityEntry.objects.count() == 0`
  - `StockMovement.objects.count() == 0`

---

## 9. Sub-checkpoint 9B2B Implementation: CPO Finance Accounting, Payable & Payment

### Overview & Responsibilities
Sub-checkpoint 9B2B establishes the authoritative financial boundary between the Incentives domain and the Finance domain for CPO Finished Goods Fees:
- **Incentives Domain**: Sole owner of the business event, quantity calculation, and `IncentiveAccrual` lifecycle (`ACCRUED`, `APPROVED`, `REVERSED`).
- **Finance Domain**: Sole owner of the general ledger, accounting entries, `JournalEntry`, `PayableEntry`, `Payment`, and `IncentivePayablePosting`.

### Completeness Gate for Project Profitability
- In `apps/projects/selectors/profitability.py`, tightened CPO fee completeness verification:
  - Scans all economically active posted finished goods receipt lines (`WarehouseReceiptLine`) for the project.
  - If at least one eligible posted CPO source exists for a project, every active source line must have a valid `IncentiveAccrual` or valid reversal disposition.
  - If any active eligible line lacks an accrual (e.g. `PENDING_RULE`, `PENDING_BENEFICIARY`, `INVALID_BENEFICIARY`), the CPO fee category is marked `PENDING_SOURCE` with reason `INCOMPLETE_CPO_ACCRUAL_COVERAGE`.
  - Overall `actual_cost` propagates `PENDING_SOURCE` to prevent material cost understatements.
  - Partial CPO fee subtotals are never prematurely labeled authoritative.

### Finance Accounting Model (`IncentivePayablePosting`)
- Added `IncentivePostingState` (`POSTED`, `REVERSED`) and `IncentivePayablePosting` model in `apps/finance/models.py`.
- Migration created: `apps/finance/migrations/0009_incentivepayableposting.py`.
- Key fields:
  - `legal_entity`: FK to `LegalEntity`.
  - `incentive_accrual`: `OneToOneField` to `IncentiveAccrual` (ensures one authoritative accrual cannot generate multiple payable postings).
  - `source_key`: Unique deterministic idempotency key (`INCENTIVE_PAYABLE|<accrual_id>`).
  - `accounting_date`: Validated against active accounting periods.
  - `amount`: Whole Rupiah liability matching accrual amount.
  - `currency`: Default "IDR".
  - Beneficiary snapshots: `beneficiary_type`, `beneficiary_id`, `beneficiary_code_snapshot`, `beneficiary_name_snapshot`.
  - Lineage snapshots: `project_reference`, `source_reference`.
  - Finance references: `journal` (`OneToOneField` to `JournalEntry`), `payable_entry` (`OneToOneField` to `PayableEntry`).

### Dynamic COA Mapping & Resolution
- **Semantic Event**: `INCENTIVE_CPO_FEE_PAYABLE`.
- **Debit Line Role**: `CPO_FEE_COST` (Dr Expense / Cost).
- **Credit Line Role**: `INCENTIVE_PAYABLE` (Cr Liability Control Account).
- Fully resolved via `apps.finance.services.mappings.resolve_account_mapping`. Zero hardcoded account codes or IDs.
- Missing or ambiguous COA mapping atomically blocks journal and payable creation with rollback.

### Beneficiary & Partner Boundary
- CPO beneficiaries are internal Employees.
- `PayableEntry.partner` remains strictly `NULL`.
- No fake `BusinessPartner` records are generated, nor are Project customers or warehouse staff substituted.
- Full traceability is preserved via `IncentivePayablePosting` immutable snapshots.

### Finance Posting Service (`apps/finance/services/incentive_payables.py`)
- `post_incentive_payable(accrual, *, actor, accounting_date=None)`:
  - Locks `IncentiveAccrual`.
  - Verifies `incentive_type == CPO_FEE`, `state == APPROVED`, and not reversed.
  - Verifies whole Rupiah amount > 0.
  - Idempotent: existing postings return the original record without re-posting.
  - Validates accounting period: blocks if period is closed (`PERIOD_CLOSED`).
  - Creates balanced `JournalEntry` (Dr `CPO_FEE_COST`, Cr `INCENTIVE_PAYABLE`).
  - Creates `PayableEntry` with `open_amount == original_amount`.
  - Transitions `IncentiveAccrual`: `APPROVED` â†’ `PAYABLE`.
  - Records structured audit events.

### Payment Integration & Liability Settlement
- Reuses existing Finance `post_vendor_payment` infrastructure.
- Payment journal:
  - **Debit**: Original `INCENTIVE_PAYABLE` control account resolved via `incentive_payable_control_snapshot(payable)`.
  - **Credit**: `LIQUIDITY` account via liquidity mapping context.
- **Strictly No Duplicate Expense**: Payment settles liability only and never debits `CPO_FEE_COST` again.
- **State Synchronization (`sync_incentive_accrual_payment_state`)**:
  - Partial settlement: `open_amount > 0` â†’ accrual remains `PAYABLE`.
  - Full settlement: `open_amount == 0` â†’ accrual transitions `PAYABLE` â†’ `PAID`.
- **Payment Reversal (`reverse_payment`)**:
  - Restores `PayableEntry.open_amount`.
  - Synchronizes accrual: `PAID` â†’ `PAYABLE`.
  - Never recreates CPO expense.

### Source & Finance Reversal Semantics
- Extended `reverse_incentive_accrual` in `apps/incentives/services/accruals.py` to allow reversing accruals in `PAYABLE` and `PAID` states upon source reversal.
- `reverse_incentive_payable_posting(posting, *, actor, accounting_date=None)`:
  - **Unpaid Liability (`open_amount == original_amount`)**: Reverses original journal via `reverse_journal`, zeroes `payable.open_amount = 0`, and sets `posting.state = REVERSED`.
  - **Settled or Partially Settled Liability (`open_amount < original_amount`)**: Blocks atomically with `ValidationError("PAYABLE_ALREADY_SETTLED")`. Requires operators to reverse or resolve payments first before payable reversal can proceed.

### Finance Reconciliation Selector Contract (`apps/finance/selectors/incentive_payables.py`)
- Dataclass `IncentivePayableReconciliationItem`:
  - `accrual_id`, `business_state`, `has_finance_posting`, `posting_state`, `payable_original_amount`, `payable_open_amount`, `payment_status`, `source_reversed`, `accounting_reversal_required`, `accounting_posting_missing`, `reconciliation_status`, `beneficiary_type`, `beneficiary_id`, `beneficiary_code`, `beneficiary_name`, `project_reference`, `source_reference`.
- Evaluates reconciliation status: `PENDING_APPROVAL`, `APPROVED_NOT_POSTED`, `PAYABLE_OPEN`, `PARTIALLY_PAID`, `PAID`, `SOURCE_REVERSED_FINANCE_REVERSAL_PENDING`, `REVERSED`.

### Cross-Domain Safety
- Finance posting and payments generate **zero** `StockMovement` records.
- Finance posting generates zero additional `IncentiveAccrual` records.
- Read-only Project profitability evaluations generate zero Finance or Incentive writes.
- `ProjectBudgetCategory.SALES_FEE` remains strictly `PENDING_SOURCE`.
- Legacy SMB GAS codebase remains strictly byte-identical (50 files, aggregate SHA-256 `66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2`).

---

---

---

## 10. Sub-checkpoint 9B3 & 9B3R: Incentive Rule Configuration + CPO Operations + Quantity Fidelity & Lifecycle Ownership

### Quantity Fidelity & Source Precision
- **Authoritative Source Preservation**: `WarehouseReceiptLine.accepted_quantity` (up to 6 decimal places) is preserved exactly without 4-decimal quantization, rounding, or truncation.
- **Persistent Schema**: `IncentiveAccrual.basis_quantity` migrated to `DecimalField(max_digits=18, decimal_places=6)` via migration `0002_alter_incentiveaccrual_basis_quantity.py`.
- **Whole-Rupiah Validation**: Only the final calculated monetary result (`accepted_quantity * rate`) is subject to the whole-Rupiah rule. Any calculation yielding a fractional Rupiah result is strictly rejected with `NON_WHOLE_RUPIAH_RESULT`.

### Operational Dashboard (`/incentives/cpo/`)
- **GET Safety**: Pure read-only view. Causes 0 database mutations (0 accruals, 0 approvals, 0 postings, 0 journals, 0 stock movements).
- **Multi-Attribute Filters**: Filter by `legal_entity`, `project_id`, `item_id`, `employee_id` (CPO Beneficiary), and `status` (`PENDING_RULE`, `PENDING_BENEFICIARY`, `READY`, `ACCRUED`, `APPROVED`, `PAYABLE_OPEN`, `PARTIALLY_PAID`, `PAID`, `SOURCE_REVERSED_FINANCE_REVERSAL_PENDING`, `REVERSED`).
- **Authoritative Business Accrual Totals**: `ACCRUED` is an authoritative business accrual (goods accepted in warehouse, lineage established, beneficiary and item identified, quantity and rate frozen, whole Rupiah validated). The primary metric card `Total Akrual Tercatat (Recorded Business Accruals)` aggregates `ACCRUED, APPROVED, PAYABLE, PAID` (excluding `REVERSED` and candidates).
- **Finance Eligible Metric**: A separate narrower metric `Total Siap / Terposting Finance` explicitly aggregates `APPROVED, PAYABLE, PAID` (excluding `ACCRUED` pending operational approval).
- **End-to-End Lineage**: Displays explicit Operational source (`WarehouseReceiptLine` + accepted quantity), Beneficiary snapshot, Accrual status, Finance journal link (`JournalEntry`), and open liability balance (`PayableEntry.open_amount`).

### Project Completeness & Reconciliation
- **Distinction of Recorded Amount vs Complete Cost**: When filtered by project, if any active posted finished goods receipt line lacks an accrual, an explicit alert notifies operators that CPO coverage is incomplete (`INCOMPLETE_CPO_ACCRUAL_COVERAGE`). The subtotal is explicitly designated as recorded/accrued amount, distinct from complete Project CPO cost (which remains `PENDING_SOURCE` in Project Profitability).
- **Cost Invariance**: For complete projects, Project Profitability reconciles to the exact immutable business accrual amount. Progressing an accrual through `ACCRUED → APPROVED → PAYABLE → PAID` never changes the underlying project CPO cost. Only source/business reversal adjusts active CPO cost.

### Detailed Accrual Drilldown (`/incentives/cpo/<pk>/`)
- Displays frozen, immutable historical snapshots (`rate_snapshot`, exact `basis_quantity`, `basis_amount`, `currency_snapshot`, `beneficiary_code_snapshot`, `beneficiary_name_snapshot`).
- Completely resilient to subsequent master data mutations (Item renaming, employee edits, or rule date changes).
- Renders Finance posting lineage, journal reference, and payable payment progress.

### POST-Only Operational Actions
- **`cpo_accrue_action`** (`POST /incentives/cpo/accrue/<line_id>/`): Accrues CPO fee for an eligible `WarehouseReceiptLine` with exact source quantity. Strictly idempotent. Requires `incentives.add_incentiveaccrual`.
- **`cpo_approve_action`** (`POST /incentives/cpo/approve/<accrual_id>/`): Transitions accrual `ACCRUED` → `APPROVED`. Requires `incentives.change_incentiveaccrual`.
- **`cpo_post_payable_action`** (`POST /incentives/cpo/post-payable/<accrual_id>/`): Delegates to Finance service `post_incentive_payable`. Creates balanced journal, payable entry, and transitions accrual to `PAYABLE`. Requires `finance.post_journal`.
- **`cpo_reverse_finance_action`** (`POST /incentives/cpo/reverse-finance/<posting_id>/`): Delegates to Finance service `reverse_incentive_payable_posting`. Permitted only when `payable.open_amount == payable.original_amount`. Atomically blocks when settled. Requires `finance.reverse_journal`.

### Lifecycle Ownership & Domain Boundaries
- **Incentives Domain Ownership**: Narrow services in `apps.incentives.services.accruals` own all `IncentiveAccrual` lifecycle transitions:
  - `mark_accrual_payable_from_finance(accrual, *, posting, actor)`: Validates that `posting.incentive_accrual_id == accrual.pk`, accrual is in `APPROVED` state, and transitions to `PAYABLE`.
  - `mark_accrual_paid_from_finance(accrual, *, posting, actor)`: Authoritatively queries `PayableEntry` from DB with `select_for_update()`, verifies `open_amount == 0`, and transitions `PAYABLE → PAID`.
  - `reopen_accrual_payable_from_finance(accrual, *, posting, actor)`: Authoritatively queries `PayableEntry` from DB with `select_for_update()`, verifies `open_amount > 0` after payment reversal, and transitions `PAID → PAYABLE`.
- **Finance Domain Ownership**: Finance remains the sole owner of accounting evidence (`IncentivePayablePosting`, `PayableEntry`, `Payment`, `PaymentAllocation`, `open_amount`). Finance calls the Incentives-owned lifecycle services, passing verified evidence.

### Semantic Payment Identity
- `post_incentive_payment` generates `Payment` with `source_document_type = "IncentivePayment"` and `source_module = "FINANCE"`.
- Sets `payment.partner = None` (preserves Employee beneficiary without creating fake vendors).
- Payment settlements never re-debit `CPO_FEE_COST` (strictly settles `INCENTIVE_PAYABLE` liability).

---

## 11. Verification & Test Suite Summary

### Test Suite Execution
- **Phase 9B3 Suite (`test_phase_9b3.py`)**: **26 passed** (100%)
  - `TestIncentiveRuleUI`: 7 tests passed.
  - `TestCPOOperationsUI`: 7 tests passed.
  - `TestCPODetailSnapshot`: 1 test passed.
  - `TestProductionBeneficiaryUI`: 1 test passed.
  - `TestProjectProfitabilityDrilldown`: 1 test passed.
  - `TestIncentivePaymentSemanticIdentity`: 2 tests passed.
  - `TestPhase9B3RQuantityFidelityAndLifecycle`: 6 tests passed (6-decimal quantity fidelity, whole-Rupiah calculation, fractional rejection, UI exact quantity, dashboard business accrual authority & totals, project completeness gating & cost invariance, lifecycle evidence validation).
  - `TestSMBGASIntegrity`: 1 test passed (50 files, aggregate SHA-256 preserved).
- **All Phase 9B Suites (`apps/incentives/tests/`)**: **92 passed** (100%)
  - Phase 9B1 (Core Generic Incentive Engine): 29 tests passed.
  - Phase 9B2A (CPO Source & Beneficiary): 18 tests passed.
  - Phase 9B2B (CPO Finance Accounting & Payables): 19 tests passed.
  - Phase 9B3/9B3R (CPO Operations UI, Fidelity & Lifecycle): 26 tests passed.
- **Finance & Projects Regression Suites**: **32 passed** (100%)
  - `test_phase_8b1.py`: 9 tests passed.
  - `test_phase_8c3a1.py`: 1 test passed.
  - `test_phase_8c3b1.py`: 2 tests passed.
  - `test_phase_9a2b.py`: 20 tests passed.
- **Focused Multi-App Suite Run**: **114 passed in 111s** across `test_phase_9b1.py`, `test_phase_9b2a.py`, `test_phase_9b2b.py`, `test_phase_9b3.py`, `test_phase_9a2b.py`, and `test_phase_8c3b1.py`.
- **Django Checks**: `python manage.py check` (0 issues), `makemigrations --check --dry-run` (0 changes).
- **Code Quality**: `ruff check` (0 errors) and `ruff format --check` (0 unformatted) passed cleanly.
- **Legacy SMB GAS**: 50 files intact, aggregate SHA-256 `66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2`.

---

## 12. Explicit Remaining Boundaries & Deferred Scope

The following boundaries remain strictly deferred:
1. **Phase 9C**: Sales Commission / Sales Fee authoritative trigger, commercial rules, and sales integration.
2. **Phase 10**: System-wide close and comprehensive audit reports.
