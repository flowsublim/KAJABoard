# KAJABoard — Phase 9A1 Result Document

**Document Title**: Project Profitability Source Contracts + Core Read Model
**Phase**: Phase 9 — Commercial Intelligence & Generic Incentive Engine
**Sub-checkpoint**: 9A1 (Source Contracts + Core Read Model)
**Date**: 2026-09-03
**Status**: COMPLETE / PASS
**Target Worktree**: `C:\KAJABoard`
**Base Commit**: `75600af3ceede608a3d0e02cb298e0179dbb8140` (`phase-8-pass`)

---

## 1. Sub-checkpoint 9A1 Scope & Architectural Decisions

Sub-checkpoint 9A1 delivers the authoritative source contract and read model for Project Profitability without introducing duplicate accounting ledgers or operational side effects.

### Core Architecture & Separation of Concerns:
- **Finance Ownership**: Finance is the sole ledger authority. Recognized revenue is derived strictly from posted `JournalEntry` records with `line_role="REVENUE"`. Commercial sales order totals and invoice drafts are exposed as commercial values, never conflated with recognized accounting revenue.
- **Warehouse Ownership**: Physical consumption costs originate strictly from posted `InternalConsumptionLine` records owned by Warehouse.
- **Purchasing Ownership**: Procurement commitments are derived strictly from confirmed `PurchaseOrder` lines and are computed net of warehouse-fulfilled receipts to eliminate double-counting. Subcontract costs originate from accepted `SubcontractReceiptCostLine` records.
- **Production Ownership**: Direct labor costs and posted production extra costs (daily wages and direct overheads) with explicit project lineage are included, netting out any reversed entries.
- **Projects Read Model**: The Projects module acts solely as an analytics and planning aggregator. Read selectors execute zero writes to accounting, inventory, payments, purchasing, or production records.

---

## 2. Source Authority Decisions Matrix

| Profitability Component | Authoritative Domain | Source Models & Constraints | Availability & Netting Policy |
| :--- | :--- | :--- | :--- |
| **Recognized Revenue** | Finance | `JournalEntry` (`source_module="SALES"`, `source_document_type="SalesInvoice"`, `state="POSTED"`) & `JournalLine` (`line_role="REVENUE"`) | Credits minus debits. If invoices exist but are not yet posted to Finance, revenue is `PENDING_SOURCE` (`reason="CONFIRMED_INVOICES_AWAITING_FINANCE_POSTING"`). If no invoices exist, recognized revenue is `0`. |
| **Commercial Sales Order Value** | Sales | `SalesOrder` (`state__in=[CONFIRMED, ON_HOLD, CLOSED]`, `project_link__project=project`) | Grand total sum of linked orders. Explicitly marked as commercial metric, not recognized revenue. |
| **Commercial Invoice Value** | Sales | `SalesInvoiceLine` (`sales_invoice__state="CONFIRMED"`, `sales_invoice__document_kind="INVOICE"`) | Distinct invoice grand total sum. Authoritative commercial source value. |
| **Budget Value & Reconciliation** | Projects | `Project.budget_total` (header) & `ProjectBudgetLine` (`is_active=True`) | Exposes `header_total`, `active_lines_total`, `status` (`MATCH`, `DIFFERENCE`, or `NO_LINES`), `line_count`, and `difference`. Neither value is silently overwritten. |
| **Committed Cost** | Purchasing | `PurchaseOrder` (`state="CONFIRMED"`, `project=project`) & `PurchaseOrderLine` | INVENTORY lines: remaining commitment equals `max(0, quantity - received_quantity) * unit_price` via explicit `WarehousePurchaseReceiptLine.purchase_order_line` FK. Non-inventory treatments (MAKLUN, EXPENSE, SERVICE, ASSET) lack explicit fulfillment lineage and evaluate to `PENDING_SOURCE`. If any line is PENDING_SOURCE, total committed cost is `None` (`PENDING_SOURCE`). Zero orders: `None` (`PENDING_SOURCE`). |
| **Actual Cost** | Warehouse, Purchasing, Production | `InternalConsumptionLine` (`state="POSTED"`, `project=project`), `SubcontractReceiptCostLine` (`state="ACCEPTED"`), `ProductionLaborCost` (`reversed_at__isnull=True`), `ProductionDirectExtraCost` (`state="POSTED"`, `reversed_at__isnull=True`) | Sum of authoritative components. Reversed entries are excluded. If any active consumption line lacks unit valuation, actual cost returns `None` (`PENDING_SOURCE`). Empty project: `None` (`PENDING_SOURCE`). |
| **Forecast Cost** | Projects | `ProjectForecastLine` (`is_active=True`, `project=project`) | Explicit management planning value representing total expected cost by category. `AUTHORITATIVE_AVAILABLE` when active lines exist; `PENDING_SOURCE` when zero active lines exist. Not inferred from actual/committed/budget. |
| **Incentives (CPO Fee & Sales Fee)** | Incentives / Sales | Deferred to Phase 9B generic engine | Always `None` (`PENDING_SOURCE`). |
| **Projected Profit & Margin** | Derived Selector | Calculated only when revenue and costs are authoritative | If any required component is `PENDING_SOURCE`, projected profit and margin evaluate to `None`. |

---

## 3. Whole-Rupiah and Pending-Source Handling Rules

1. **Whole-Rupiah Accounting**: All internal financial and commercial currency values are held as exact `Decimal` with whole-Rupiah integrity. Margin percentages are formatted to two decimal places (`Decimal("0.01")`).
2. **Strict Definition of Zero vs PENDING_SOURCE**:
   - `0`: The authoritative source exists, has been processed, and the verified result is zero (e.g., project with 0 issued invoices has recognized revenue `0`).
   - `PENDING_SOURCE` (`None`): An authoritative source is either pending entry, awaiting upstream posting, or deferred to a later sub-checkpoint (e.g. empty projects, unposted invoices, unvalued consumptions, forecast cost, and incentives). `PENDING_SOURCE` is never converted to zero.
3. **Auditability & Traceability**: Each metric component encapsulates `MetricComponent` and `CostCategoryItem` structures containing `availability`, `domain`, `record_count`, `source_model`, and human-explainable `reason` codes.

---

## 4. Backward Compatibility

- **`apps.projects.selectors.projects`**: Maintained exact backwards compatibility for existing imports of `ProjectProfitability` and `project_profitability`.
- **Existing Views & Templates**: `project_detail` and templates accessing `profitability.commercial_order_value`, `profitability.commercial_invoice_source_value`, `profitability.budget_value`, and `profitability.data_complete` continue to work without modification.
- **Existing Tests**: Phase 3C tests in `apps/projects/tests/test_projects.py` pass cleanly.

---

## 5. Migration Status

- **Schema Changes**: None.
- **Migration Files Created**: None.
- **Validation**: `python manage.py makemigrations --check --dry-run` reports `No changes detected`.

---

## 6. Verification & Test Evidence

### Test Suites Executed:
1. `apps/projects/tests/test_projects.py` (2 tests, Phase 3C baseline)
2. `apps/projects/tests/test_phase_9a1.py` (12 tests, Phase 9A1 complete suite):
   - `test_1_empty_project_unavailable_actual_and_forecast_remain_pending_source` (PASS)
   - `test_2_commercial_sales_order_is_not_automatically_recognized_revenue` (PASS)
   - `test_3_budget_header_and_lines_behavior_deterministic_and_explainable` (PASS)
   - `test_4_budget_mismatch_is_visible_rather_than_silently_corrected` (PASS)
   - `test_5_confirmed_procurement_commitment_included_authoritatively` (PASS)
   - `test_6_partial_actualized_commitment_does_not_double_count_fulfilled_cost` (PASS)
   - `test_7_authoritative_actual_cost_sources_with_explicit_lineage` (PASS)
   - `test_8_cancelled_void_and_draft_sources_are_excluded` (PASS)
   - `test_9_reversal_correction_is_netted_out` (PASS)
   - `test_10_missing_project_lineage_is_never_assigned_by_inference` (PASS)
   - `test_11_profit_and_margin_calculated_only_when_components_authoritative` (PASS)
   - `test_12_selector_read_safety_creates_zero_accounting_or_operational_records` (PASS)

### Summary Results:
- **Total Tests Run**: 14 tests across `test_projects.py` and `test_phase_9a1.py`.
- **Pass Rate**: 100% (14 passed in 57.17s).
- **System Check**: `python manage.py check` reports 0 issues.
- **Linter & Formatter**: `ruff check` and `ruff format` passed with 0 errors.
- **Git Diff Hygiene**: `git diff --check` passed with 0 errors.

---

## 7. Next Steps: Sub-checkpoint 9A2 Readiness

Sub-checkpoint 9A1 is completed, verified, and ready for review.
The project is strictly prepared for **Sub-checkpoint 9A2** (Forecast Planning Layer & Project Budget Versioning), which will implement:
1. The forecast cost planning algorithm based on budget remaining vs committed/actual execution.
2. Budget line revisions and version history.
3. Enhanced projected profit calculations once forecast components become authoritative.

---

## 8. Mini Review & Corrections 9A1R / 9A1R2: Revenue Reversal Netting & MAKLUN Lineage Discovery

### 8.1 Recognized Revenue Reversal Netting Mechanism
- **Finance Engine Invariants**: In KAJABoard Finance (`apps/finance/services/posting.py`), journal reversal does not delete or edit posted history. Instead:
  1. The original `JournalEntry` transitions to `state = JournalState.REVERSED`.
  2. A new reversal `JournalEntry` is created with `state = JournalState.POSTED` and `reversal_of = original_entry`.
  3. All `JournalLine` roles are preserved, while debit and credit amounts are inverted.
  4. Both entries retain `source_module = "SALES"`, `source_document_type = "SalesInvoice"`, and `source_document_id = invoice.pk`.
- **Selector Netting Implementation**:
  - The selector queries all journals matching `source_document_id__in=invoice_ids` with `state__in=(JournalState.POSTED, JournalState.REVERSED)`.
  - Net recognized revenue is computed strictly as `credit_sum - debit_sum` across lines with `line_role = "REVENUE"`.
  - **Single Active Journal**: Cr 10,000,000 - Dr 0 = **10,000,000** (`AUTHORITATIVE_AVAILABLE`).
  - **Reversed Journal**: Cr 10,000,000 (original) - Dr 10,000,000 (reversal) = **0** (`AUTHORITATIVE_AVAILABLE`). Net economic revenue correctly evaluates to zero, eliminating negative revenue artifacts (e.g. -10,000,000).
  - **Cross-Project Lineage Isolation**: Invoices and journals belonging to other projects are excluded via strict project-linked sales order scoping (`source_sales_order_line__sales_order__project_link__project = project`).

### 8.2 MAKLUN Lineage Discovery & Bounded Contract (9A1R2)
A bounded inspection was performed across all Purchasing models (`PurchaseOrder`, `PurchaseOrderLine`, `WorkOrder`, `SubcontractReceipt`, `SubcontractReceiptCostLine`):
- **Exact Source Boundary Discovered**:
  - `WarehousePurchaseReceiptLine` maintains a direct FK (`purchase_order_line`) to `PurchaseOrderLine`. This provides explicit line-level lineage for `INVENTORY` purchases.
  - In contrast, subcontract execution models (`WorkOrder`, `SubcontractReceipt`, `SubcontractReceiptCostLine`) have **no direct FK, no source line id, no immutable linking model, and no unique source key** connecting them to a `PurchaseOrderLine`.
  - Merely sharing `project`, `vendor`, `treatment = "MAKLUN"`, dates, or amounts does **not** constitute authoritative proof of fulfillment.
- **Contract Decision (Case B)**:
  - Because no explicit persisted lineage connects `PurchaseOrderLine` to subcontract receipts, MAKLUN remaining commitment cannot be authoritatively calculated by subtracting project-level receipt costs.
  - MAKLUN remaining commitment evaluates to **`PENDING_SOURCE`** (`amount = None`) with `reason = "INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_MAKLUN"`.
  - Two MAKLUN commitments within the same project do not reduce one another or get subtracted by unrelated project-level subcontract receipts.

### 8.3 Purchase Order Accounting Treatment Authority Matrix

| Treatment | Authoritative Lineage Source | Remaining Commitment Computation | Availability & Behavior |
| :--- | :--- | :--- | :--- |
| **`INVENTORY`** | `WarehousePurchaseReceiptLine` (`receipt.state == WarehouseDocumentState.POSTED`, direct `purchase_order_line` FK) | `max(0, quantity - received_quantity) * unit_price` | `AUTHORITATIVE_AVAILABLE`. Line-level fulfillment is strictly tracked by Warehouse receipts. |
| **`MAKLUN`** | None connecting `PurchaseOrderLine` to `SubcontractReceipt` | N/A | `PENDING_SOURCE` (`reason="INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_MAKLUN"`). No explicit PO-line receipt lineage exists in repository. |
| **`EXPENSE`** | None in current repository | N/A | `PENDING_SOURCE` (`reason="INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_EXPENSE"`). No vendor bills or expense fulfillment tracking documents exist. |
| **`SERVICE`** | None in current repository | N/A | `PENDING_SOURCE` (`reason="INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_SERVICE"`). No service acceptance records exist. |
| **`ASSET`** | Balance Sheet Capital Expenditure | N/A | `PENDING_SOURCE` / Excluded. Per AGENTS.md, asset purchases never become inventory stock or project operational expense. |

### 8.4 Coexistence of Authoritative Actual Cost and PENDING_SOURCE Commitment
- **Actual MAKLUN Cost**: Authoritatively tracked via accepted `SubcontractReceiptCostLine -> WorkOrder -> Project`.
  - Evaluates to **`AUTHORITATIVE_AVAILABLE`** with exact sum of accepted subcontract receipt cost lines.
- **Remaining MAKLUN Commitment**: Evaluates to **`PENDING_SOURCE`** (`amount = None`) until explicit PO-line fulfillment lineage is added to the data model.
- **Aggregate Committed Cost**: If any confirmed line on the project lacks explicit fulfillment lineage (`MAKLUN`, `EXPENSE`, `SERVICE`), aggregate `committed_cost` evaluates to **`None` (`PENDING_SOURCE`)**. Total committed cost is never silently converted to a guessed number.

### 8.5 Extended Regression Test Coverage (19 Tests Total)
- `test_13_recognized_revenue_original_journal_correct_positive_amount` (PASS): Confirms positive recognized revenue (10,000,000) for confirmed invoice with posted Finance journal.
- `test_14_recognized_revenue_full_reversal_evaluates_to_zero` (PASS): Confirms that upon journal reversal, net revenue evaluates to `0` and does NOT produce negative revenue (-10,000,000).
- `test_15_unrelated_project_reversal_is_excluded` (PASS): Confirms that reversals on separate projects have zero impact on the target project's recognized revenue.
- `test_16_maklun_commitment_without_explicit_lineage_is_pending_source_and_preserves_actual_cost` (PASS): Proves that:
  1. Two MAKLUN commitments within the same project do not reduce one another through unrelated subcontract receipt costs.
  2. MAKLUN committed component evaluates to `PENDING_SOURCE` (`amount = None`, `reason="INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_MAKLUN"`).
  3. Accepted `SubcontractReceiptCostLine` records remain authoritative actual MAKLUN cost (`2,000,000.00`, `AUTHORITATIVE_AVAILABLE`) through `WorkOrder -> Project` lineage.
- `test_17_non_inventory_treatment_with_insufficient_fulfillment_lineage_becomes_pending_source` (PASS): Confirms that non-inventory treatments lacking fulfillment models (such as `EXPENSE`) evaluate to `PENDING_SOURCE` rather than guessing a full balance.

### 8.6 Verification Summary
- **Test Suite**: 19 tests passed (2 in `test_projects.py`, 17 in `test_phase_9a1.py`) in 58.84s.
- **Django Checks**: `manage.py check` passed with 0 issues.
- **Migrations Check**: `manage.py makemigrations --check --dry-run` passed with no changes detected.
- **Linter & Formatter**: `ruff check` and `ruff format --check` passed cleanly across `apps/projects`.
- **Git Diff Hygiene**: `git diff --check` clean with 0 errors.


---

## 9. Sub-Checkpoint 9A2A: Project Forecast Planning + Variance Core

### 9.1 Explicit Forecast Planning Semantics
- **Definition**: In KAJABoard Phase 9A2A, forecast represents **"Management's current expected TOTAL COST for the Project, captured explicitly by category."**
- **Strict Separation of Facts**:
  - Forecast is **NOT accounting**.
  - Forecast is **NOT actual cost**.
  - Forecast is **NOT committed cost**.
  - Forecast is **NOT inventory valuation**.
  - Forecast is **NOT a journal**.
  - Forecast is **NOT an inferred or auto-calculated balance** (e.g. not `actual + committed`, `budget - actual`, or `PO total`).
- **Domain Ownership**:
  - Forecast lines are strictly owned by the **Projects** domain via `ProjectForecastLine`.
  - **Finance** remains the sole owner of accounting journals, ledgers, and revenue recognition.
  - **Warehouse** remains the sole owner of physical stock movements and internal consumptions.
  - **Purchasing** remains the owner of procurement commitments and subcontract receipt costs.
  - **Production** remains the owner of labor allocations and direct extra costs.
  - Forecast services and read selectors produce **zero writes** to Finance, Warehouse, Purchasing, or Production ledgers.

### 9.2 Forecast Data Model (`ProjectForecastLine`)
Persisted in `apps/projects/models.py`:
- `project`: ForeignKey to `Project` (`related_name="forecast_lines"`).
- `category`: CharField reusing canonical `ProjectBudgetCategory.choices` (no duplicate category enums).
- `description`: CharField(max_length=255) normalized string.
- `amount`: Non-negative DecimalField(max_digits=18, decimal_places=2) with CheckConstraint (`amount >= 0`). Represents current expected total cost for the line.
- `cost_center`, `purchase_category`, `item`: Optional ForeignKey dimensions, strictly validated against the project's legal entity.
- `notes`: TextField for operational notes.
- `is_active`: BooleanField (default `True`). Inactive lines are excluded from forecast totals.

### 9.3 Forecast Edit Controls & Service Invariants
Implemented in `apps/projects/services/projects.py`:
- **Allowed Project States**: Forecast modification is allowed only when `project.state in {DRAFT, ACTIVE, ON_HOLD}`.
- **Terminal States Blocked**: Attempts to add, update, or remove forecast lines on `COMPLETED` or `CANCELLED` projects are strictly rejected with `ValidationError`.
- **Reason Enforcement**:
  - `DRAFT`: Line creation follows initial budget behavior (reason optional).
  - `ACTIVE` and `ON_HOLD`: Line creation **requires** an explicit non-empty `reason`.
  - Modification and removal **always require** an explicit non-empty `reason` across all editable states.
- **Audit Logging**: Every create, update, and delete triggers an immutable `AuditEvent` (`projects.projectforecastline.created`, `projects.projectforecastline.updated`, `projects.projectforecastline.removed`).

### 9.4 Read Contract & Variance Facts
Extended in `apps/projects/selectors/profitability.py`:
- **Availability Rule**:
  - If project has zero active forecast lines: `forecast_cost = None` (`PENDING_SOURCE`, reason `"NO_ACTIVE_PROJECT_FORECAST_LINES"`). It is **never** silently defaulted to `0`.
  - If active forecast lines exist: `forecast_cost = sum(active_forecast_lines)` (`AUTHORITATIVE_AVAILABLE`).
- **Variance Facts**:
  1. **Budget vs Forecast (`variance_budget_forecast`)**:
     - Formula: `budget_value - forecast_cost`
     - Available only when forecast is `AUTHORITATIVE_AVAILABLE`.
     - Positive = forecast is under budget; Zero = forecast equals budget; Negative = forecast exceeds budget.
  2. **Budget vs Actual (`variance_budget_actual`)**:
     - Formula: `budget_value - actual_cost`
     - Available only when actual is `AUTHORITATIVE_AVAILABLE`.
  3. **Forecast vs Actual (`remaining_to_forecast`)**:
     - Formula: `forecast_cost - actual_cost`
     - Available only when both forecast and actual are authoritative. Analytical variance only; never treated as an accounting adjustment.
  4. **Cost Exposure (`current_cost_exposure`)**:
     - Formula: `actual_cost + committed_cost`
     - Available only when **both** actual and committed are `AUTHORITATIVE_AVAILABLE`.
     - If committed is `PENDING_SOURCE`, exposure remains strictly `PENDING_SOURCE` (committed is never silently treated as 0).
- **Projected Profit & Margin**:
  - `projected_profit = recognized_revenue - forecast_cost`
  - Computed only when both `recognized_revenue` and `forecast_cost` are authoritative.
  - `projected_margin_percent = (projected_profit / recognized_revenue) * 100` (quantized to 2 decimal places).
  - Calculated only when `recognized_revenue > 0`. If `recognized_revenue == 0`, margin percent evaluates safely to `None` to prevent `ZeroDivisionError`.
  - Commercial Sales Order value is **never** substituted for recognized revenue.
- **Deferred Items**:
  - `CPO Fee` and `Sales Fee` remain strictly `PENDING_SOURCE` until Phase 9B generic incentive engine.
  - UI template integration is deferred to Sub-checkpoint 9A2B (minimum form `ProjectForecastLineForm` provided in 9A2A).


---

## 10. Sub-Checkpoint 9A2B: Project Profitability + Forecast UI + Phase 9A Readiness

### 10.1 Budget Authority Gating for Derived Variances
- **Discrepancy Protection**: When `Project.budget_total` (header) and active `ProjectBudgetLine` sum differ (`status == "DIFFERENCE"`), derived variance metrics (`variance_budget_forecast` and `variance_budget_actual`) must **never silently choose** between header and lines.
- **Authority Contract**:
  - `budget_status == "MATCH"`: Budget is `AUTHORITATIVE_AVAILABLE` for variance calculations (`header_total == active_lines_total`).
  - `budget_status == "NO_LINES"` and `header_total == 0`: Budget is authoritatively `0`, allowing variance calculation against zero budget.
  - `budget_status == "DIFFERENCE"`: Variances evaluate strictly to **`PENDING_SOURCE`** (`None`).
  - `budget_status == "NO_LINES"` and `header_total != 0`: Header contains an unexplained nonzero value; variances evaluate strictly to **`PENDING_SOURCE`** (`None`).
  - Raw reconciliation facts (`header_total`, `active_lines_total`, `status`, `difference`) remain unaltered so discrepancies are immediately visible and explainable to management.

### 10.2 Profitability & Forecast UI Presentation
Implemented in [`templates/projects/project_detail.html`](file:///C:/KAJABoard/templates/projects/project_detail.html):
- **Commercial Lineage**: Exposes Commercial Sales Order Value and Commercial Invoice Source Value with distinct order/invoice record counts.
- **Recognized Revenue & Cost**:
  - Displays Recognized Revenue (net of Finance reversals), Budget, Committed Cost, Actual Cost, and Forecast Cost.
  - **PENDING_SOURCE Presentation Rule**: `PENDING_SOURCE` is **never rendered as 0, Rp0, -, or blank**. It is rendered as an explicit visual badge (`PENDING SOURCE`) accompanied by the domain reason where available.
  - **Authoritative Zero Distinction**: A genuine authoritative zero (such as recognized revenue when no invoices exist, or budget when set to 0 with no lines) displays as `Rp0` / `IDR 0`.
- **Projected Profit & Margin**:
  - Renders Projected Profit (`recognized_revenue - forecast_cost`) and Projected Margin %.
  - If recognized revenue is zero, margin % avoids division by zero and displays `PENDING SOURCE`.
- **Derived Variances Panel**:
  - Displays Budget vs Forecast (annotated as Under budget / Exceeds budget / On budget), Budget vs Actual, Remaining to Forecast, and Current Cost Exposure (`actual + committed`).
- **Category Cost Breakdown**:
  - Compares Actual Cost, Committed Cost, and Forecast Cost across all canonical categories (`MATERIAL`, `PURCHASING`, `MAKLUN`, `INTERNAL_PRODUCTION`, `LABOR`, `FREIGHT`, `PACKAGING`, `CPO_FEE`, `SALES_FEE`, `DIRECT_OVERHEAD`, `ALLOCATED_OVERHEAD`, `OTHER`).
  - Strictly distinguishes authoritative amounts from `PENDING SOURCE`.

### 10.3 Forecast Planning UI & Lifecycle Controls
- **Forecast Table**: Lists active and inactive forecast lines with Category, Description, Cost Center, Amount, Status, and Action buttons (Edit / Remove).
- **Permission & Lifecycle Guard (`can_manage_forecast`)**:
  - Requires `projects.change_project` permission.
  - Allowed only for projects in `DRAFT`, `ACTIVE`, or `ON_HOLD` states.
  - For `COMPLETED` and `CANCELLED` projects, action buttons are hidden and views reject mutation attempts.
- **Dedicated Routes & Modals**:
  - `projects:forecast-add` (`<uuid:pk>/forecast/new/`)
  - `projects:forecast-edit` (`<uuid:pk>/forecast/<uuid:line_pk>/edit/`)
  - `projects:forecast-remove` (`<uuid:pk>/forecast/<uuid:line_pk>/remove/`)
- **Reason Enforcement**:
  - `DRAFT`: Create allowed without reason; update/remove require reason.
  - `ACTIVE` and `ON_HOLD`: Create, update, and remove strictly require an explicit non-empty reason.

### 10.4 GET Read-Safety & Stale Text Removal
- **Read-Safety**: GET requests to `project_detail`, `forecast_add`, `forecast_edit`, and `forecast_remove` produce **zero writes** to any operational, accounting, inventory, or purchasing ledgers.
- **Truthful Status Copy**: Old Phase 3 placeholder text ("Committed cost, actual cost, forecast, and profit are not available until their owning domains are implemented") has been completely removed and replaced with truthful Phase 9A status.

### 10.5 Explicit System Boundaries
- **Projects**: Owns commercial metadata, budget lines, forecast planning lines, and the read-only profitability selector.
- **Finance**: Sole owner of general ledger, journal entries, accounting periods, and revenue recognition. Formal financial statements remain deferred to **Phase 10**.
- **Warehouse**: Sole owner of physical stock movements and internal consumptions.
- **Purchasing**: Sole owner of purchase orders and subcontract receipts.
- **Incentive Engines**:
  - Generic Incentive Engine & **CPO Fee** rule engine: Deferred to **Phase 9B**.
  - **Sales Commission / Sales Fee** rule engine: Deferred to **Phase 9C**.
