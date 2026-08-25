# KAJABoard Functional Parity Register

> **AUTHORITATIVE UPDATE (25 August 2026): ACTUAL SMB EVIDENCE AUDITED AND OWNER APPROVED.** Section 13 contains the evidence delta and owner-approved resolutions. Register total: 105 rows. Phase 0 is approved for closure; Phase 1 still requires an explicit start instruction.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — Source Freeze & Functional Audit  
**Status:** DRAFT — PLAN COVERAGE MAPPED; LEGACY VERIFICATION BLOCKED  
**Scope rule:** functional outcome and control are preserved; GAS names, endpoints, Sheets, UI layout, and technical helpers need not be preserved.

## 1. Status vocabulary

| Status | Meaning |
|---|---|
| `MAPPED-PLAN` | Project Plan/AGENTS business outcome is mapped to target ownership, event/state, and an acceptance test. |
| `UNRESOLVED` | A material business decision is missing or conflicting; recommended interpretation is recorded. |
| `SOURCE-BLOCKED` | Plan mapping exists, but actual SMB source/patch/UI/Sheet behavior cannot be verified. |
| `ACCEPTED` | Reserved for stakeholder-reviewed Phase 0 rows after source delta audit; no row currently has this status. |

Every row is also `SOURCE-BLOCKED` globally until the missing legacy freeze is supplied. The row status below highlights whether plan-level behavior itself is clear.

## 2. Core and master configuration

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-CORE-001 | Role + Action + Data Scope controls every sensitive action. | Plan §§5,27; AGENTS Security | Core/Accounts permission service; server-side checks | Overrides cannot bypass Warehouse/Finance owner permissions | Permission tests for view/post/approve/close/export and data scope | `MAPPED-PLAN` |
| FP-CORE-002 | Critical action audit captures before/after, fields, actor, time, reason, source, approval, request/idempotency key. | Plan §29; AGENTS Audit | Append-only Core audit contract | Posted ledger history retained | Create/update/transition/reversal audit tests | `MAPPED-PLAN` |
| FP-CORE-003 | Critical commands are idempotent; retry cannot duplicate stock, journal, import, payment, POS, or accrual. | Plan §28; AGENTS Idempotency | Core idempotency + domain unique source constraints | One physical/accounting effect per source | Same key/same payload returns result; different payload conflicts | `MAPPED-PLAN` |
| FP-CORE-004 | Historical transactions retain meaning after master changes. | Plan §§6,48 | Stable IDs, effective dating, snapshots | Old stock/cost/journal remains unchanged | Supersede master then reproduce old document/report | `MAPPED-PLAN` |
| FP-CORE-005 | Critical states reject illegal transitions; posted records use correction/reversal. | Plan §§29,31,48 | Owned service state machines | No silent posted ledger delete | Illegal transition and reversal lineage tests | `MAPPED-PLAN` |
| FP-MST-001 | One canonical BusinessPartner supports Customer/Vendor/Subcontractor/etc roles. | Plan §6.2 | Partners master; role-specific UI | Finance/operations reference stable Partner | Role, duplicate, inactive, historical snapshot tests | `MAPPED-PLAN` |
| FP-MST-002 | Canonical Item/SKU/Material/UOM with transaction snapshots. | Plan §§6.3,48 | Catalog master | Warehouse alone owns quantities | Active eligibility, UOM precision, historical item tests | `UNRESOLVED` |
| FP-MST-003 | Purchase Category explicitly carries `INVENTORY/ASSET/EXPENSE/SERVICE/MAKLUN`, Cost Center, flags and mapping key. | Plan §§6.5,10.1; AGENTS | Master Data + Purchasing snapshot | No name-substring accounting logic | Five-treatment routing tests | `MAPPED-PLAN` |
| FP-MST-004 | COA Mapping resolves exact dimension then DEFAULT, priority/effective account, and snapshots selection. | Plan §§6.7,15.2 | Finance mapping resolver | No operational COA hardcode | Exact/fallback/effective/inactive/missing mapping tests | `MAPPED-PLAN` |
| FP-MST-005 | Stable Store ID and exact SKU/variation mapping; conversion effective and snapshotted. | Plan §§6.8–6.9,14 | Master/Omni | Warehouse/Finance use canonical dimensions | Rename Store, variation collision, mapping change history tests | `MAPPED-PLAN` |

## 3. Sales, project, and commercial parity

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-SAL-001 | Preserve `Sales Order/PO → partial Delivery/SJ → Invoice → AR/SOA → Payment`. | Plan §7; AGENTS Sales | Sales documents plus Warehouse/Finance contracts | Sales never posts stock/payment ledger | Golden B2B lineage scenario | `MAPPED-PLAN` |
| FP-SAL-002 | Order has unique number, active customer/item, qty > 0, stable lines and price/tax/discount/charge snapshots. | Plan §§7.1–7.2 | Sales command service | No direct ledger effect at draft | Validation, duplicate, snapshot tests | `MAPPED-PLAN` |
| FP-SAL-003 | Partial delivery per line; qty cannot exceed posted remaining; multiple SJ per order. | Plan §7.3; AGENTS | Sales fulfillment service | Delivery emits Warehouse OUT candidate | Concurrency and partial/reversal tests | `MAPPED-PLAN` |
| FP-SAL-004 | Delivery correction uses Warehouse controlled reversal. | Plan §7.3 | Sales request + Warehouse reversal | Physical issue owner remains Warehouse | Posted delivery cannot delete; reversal restores remaining | `MAPPED-PLAN` |
| FP-SAL-005 | Invoice retains source lineage and amount snapshots; payment status comes from Finance. | Plan §§7.4–7.5 | Sales invoice source + Finance AR | Finance posts journal/AR/payment | Source-total/AR/SOA reconciliation | `UNRESOLVED` |
| FP-SAL-006 | Preserve Proforma, Invoice, Surat Jalan, Shipping Label, and SOA; master letterhead. | Plan §7.7 | Sales/Reports rendering | Read-only output | Content, authorization, snapshot and PDF tests | `MAPPED-PLAN` |
| FP-SAL-007 | Customer 360 composes commercial, Finance, operational and relationship data without copying ledgers. | Plan §7.6 | Sales/Analytics read model | Read-only Finance/Warehouse facts | KPI drill-down and data-scope tests | `MAPPED-PLAN` |
| FP-SAL-008 | Project supports B2B/custom progress and traceable budget/committed/actual/forecast/profitability. | Plan §§8,18–19 | Projects/Analytics | Source events remain owned | Golden project profitability reconciliation | `MAPPED-PLAN` |
| FP-SAL-009 | Credit limit/overdue hold and explicit authorized override. | Plan §34 | Sales reads Finance exposure; Core approval | No ledger overwrite | Warning/hold/override permission/reason tests | `MAPPED-PLAN` |

## 4. Purchasing and procurement parity

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-PUR-001 | Explicit treatment snapshot routes every purchase line. | Plan §§10.1,48 | Purchasing command/routing service | Candidate/event only | Five-treatment matrix regression | `MAPPED-PLAN` |
| FP-PUR-002 | ASSET never becomes inventory; produces Finance acquisition candidate/AP. | Plan §10.1; AGENTS | Purchasing → Finance | No Warehouse movement | Critical asset-no-stock test | `MAPPED-PLAN` |
| FP-PUR-003 | EXPENSE/SERVICE require Cost Center and do not become stock. | Plan §10.1; AGENTS | Purchasing validation → Finance | No Warehouse movement | Missing Cost Center rejected | `MAPPED-PLAN` |
| FP-PUR-004 | Production overhead only for EXPENSE/SERVICE + production-eligible Cost Center + flag true. | Plan §§10.6,48; AGENTS | Purchasing/Finance source → Production snapshot | Inventory/assets/maklun excluded | Office excluded; eligible cost enters once | `MAPPED-PLAN` |
| FP-PUR-005 | SPK supports internal/external, multiple outputs, explicit material-output pair, due date/vendor/instructions/attachments and partial fulfillment. | Plan §10.2 | Purchasing/Production SPK domain | No direct ledgers | Stable line and material-output lineage tests | `MAPPED-PLAN` |
| FP-PUR-006 | Kirim Bahan cannot exceed authorized/available qty and Warehouse posts OUT. | Plan §10.3 | Purchasing candidate → Warehouse | Warehouse sole OUT | Insufficient/duplicate/trace tests | `MAPPED-PLAN` |
| FP-PUR-007 | Terima Maklun supports finished goods, variant-specific and shared service, partial outputs and cost allocation. | Plan §10.4 | Purchasing/Quality → Warehouse/Finance | Accepted IN only; AP/cost Finance | Partial receipt and cost allocation tests | `UNRESOLVED` |
| FP-PUR-008 | Purchasing creates vendor/maklun payable source but never pays cash/bank. | Plan §10.5; AGENTS | Purchasing → Finance AP | Finance owns payment | Payment does not duplicate accrued expense | `MAPPED-PLAN` |
| FP-PUR-009 | Purchasing history, SPK print/PDF, SPK/maklun/AP display survive redesign. | Plan §40 inventory | Purchasing read/print; Finance AP selector | Reports read-only | Source reconciliation and access tests | `SOURCE-BLOCKED` |

## 5. Production parity

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-PRD-001 | Preserve Cut, Sew, QC/Packing, Warehouse handover, stage rejects, and optional general/non-SPK task. | Plan §11.1 | Production work services | No direct stock until Warehouse | Process/state coverage tests | `MAPPED-PLAN` |
| FP-PRD-002 | Item-level WIP formulas prevent over-entry at every stage. | Plan §11.2; AGENTS | Production WIP validator | Prevents invalid handover/valuation | Three formula tests per output Item | `MAPPED-PLAN` |
| FP-PRD-003 | Multi-item entry uses stable line IDs; correcting one line never deletes siblings. | Plan §11.3; AGENTS | Production line service | Downstream sources remain traceable | Critical sibling preservation test | `MAPPED-PLAN` |
| FP-PRD-004 | SPK closes only when every output is complete and all intermediate WIP is zero. | Plan §11.4; AGENTS | SPK completion service | Accepted Warehouse qty is authoritative | Critical one-output-short rejection test | `MAPPED-PLAN` |
| FP-PRD-005 | Material cost is transaction-date-sensitive inventory cost snapshot. | Plan §11.5 | Warehouse costing → Production snapshot | Warehouse valuation authoritative | Weighted-average/date/reversal tests | `UNRESOLVED` |
| FP-PRD-006 | Labor stores PIC/process/qty/tariff/wage method snapshots. | Plan §11.6 | Production → Finance/HPP | Finance posts cost/payable | Later tariff change leaves history intact | `MAPPED-PLAN` |
| FP-PRD-007 | Eligible direct extra cost enters HPP/payable once; payment clears liability without new expense. | Plan §11.7; AGENTS | Production source → Finance | No stock by payment | Critical no-double-expense test | `MAPPED-PLAN` |
| FP-PRD-008 | Overhead snapshot is source-linked, active/posted/non-reversed, allocated audibly; settlement creates none. | Plan §§11.8–11.9 | Production HPP | No duplicate journal | Eligibility, reversal, allocation, report determinism | `MAPPED-PLAN` |
| FP-PRD-009 | Production stops at partial handover; Warehouse acceptance posts finished-goods IN. | Plan §11.10; AGENTS | Production → Warehouse | Warehouse sole IN | Handover retry/partial/reject tests | `MAPPED-PLAN` |
| FP-PRD-010 | WIP, production, HPP, and reject reports are item-safe, drillable, and read-only. | Plan §40 inventory | Production/Reports | No posting on view | Reconcile reports to source snapshots | `SOURCE-BLOCKED` |

## 6. Warehouse and quality parity

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-WHS-001 | One StockMovement ledger with source IDs/line/key, dates, qty/cost/value, state and reversal. | Plan §12.1; AGENTS | Warehouse | Finance consumes valuation event | Posted-only balance and lineage tests | `MAPPED-PLAN` |
| FP-WHS-002 | Accepted IN/OUT source catalog covers purchases, production, maklun, returns, delivery, Omni, POS, material, supplier return, consumption, opname, adjustment, opening. | Plan §12.2 | Warehouse typed services | No other stock writer | Each source integration test | `MAPPED-PLAN` |
| FP-WHS-003 | Unique source prevents double posting; negative stock disallowed by default. | Plan §§12.3–12.4; AGENTS | Warehouse constraints/locking | Protects valuation/accounting | Critical retry/concurrency/negative tests | `MAPPED-PLAN` |
| FP-WHS-004 | Stock opname posts approved variance, never arbitrary balance overwrite. | Plan §12.5; AGENTS | Warehouse count/adjustment | Finance gain/loss mapping | Count-review-approval-variance-reversal test | `MAPPED-PLAN` |
| FP-WHS-005 | Omni import creates demand; packing actual Item creates partial idempotent OUT within demand/stock. | Plan §12.6; AGENTS | Omni → Warehouse | Finance consumes COGS/value source | Demand/stock/variant/shortage tests | `MAPPED-PLAN` |
| FP-WHS-006 | Supplier return and internal consumption are traceable OUT plus Finance event. | Plan §§12.9–12.10 | Source → Warehouse → Finance | Typed mapped effects | Source/reason/valuation/idempotency tests | `MAPPED-PLAN` |
| FP-WHS-007 | Running weighted average where configured; ordered movement and controlled reversal. | Plan §12.11 | Warehouse valuation + Finance reconcile | One valuation truth | Cost sequence/backdate/reversal tests | `UNRESOLVED` |
| FP-QLT-001 | QC supports supplier, maklun, internal finished goods, customer/marketplace return, random inspection. | Plan §13 | Quality | Movement only after final decision | Source-type and mixed-result tests | `MAPPED-PLAN` |
| FP-QLT-002 | Results are PASS/HOLD/REJECT/REWORK; return registration alone never changes stock. | Plan §§13,12.8; AGENTS | Quality → Warehouse candidate | Finance adjustment separately owned | Critical return-no-stock-until-PASS test | `MAPPED-PLAN` |
| FP-QLT-003 | Reject/rework/disposal stock and accounting disposition is controlled and traceable. | Plan §13 | Quality/Warehouse/Finance | Owner-specific effects | Disposition matrix tests | `UNRESOLVED` |

## 7. Omnichannel and POS parity

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-OMN-001 | XLSX/CSV import has preview, validation, warnings, duplicate detection, checksum/log and idempotent reimport. | Plan §14.1 | Data Exchange/Omni | Import alone posts neither ledger | Same-file/reordered/error-row tests | `MAPPED-PLAN` |
| FP-OMN-002 | Exact line identity is Order Number + SKU + Variation; controlled blank fallback cannot merge variants. | Plan §14.2; AGENTS | Omnichannel | Correct Item demand/source | Critical variation collision test | `MAPPED-PLAN` |
| FP-OMN-003 | Persist raw marketplace qty, conversion snapshot and internal qty. | Plan §14.3; AGENTS | Omnichannel | Warehouse uses actual internal qty | Mapping change leaves import reconstructable | `MAPPED-PLAN` |
| FP-OMN-004 | Stable Store Mapping drives Warehouse/Finance/analytics dimensions. | Plan §14.4 | Master/Omni | Exact COA via Store dimension | Store rename/alias/effective mapping tests | `MAPPED-PLAN` |
| FP-OMN-005 | Order-created time is operational date; completion time is revenue date. | Plan §§14.5–14.7; AGENTS | Omni summaries and completion event | No stock implication | 31 July order/3 August completion critical test | `MAPPED-PLAN` |
| FP-OMN-006 | Completed order produces one immutable revenue/marketplace AR event per Store; Finance maps accounts. | Plan §§14.7–14.8; AGENTS | Omni → Finance | No hardcoded COA | Duplicate completion/date/aggregation/mapping tests | `MAPPED-PLAN` |
| FP-OMN-007 | Settlement is separate: aggregate Store+Order, structured fees, partial/split/difference; no revenue again. | Plan §14.9; AGENTS | Omni → Finance | No stock | Critical settlement-no-revenue test | `UNRESOLVED` |
| FP-OMN-008 | Payout moves marketplace balance to bank, distinct from AR and revenue. | Plan §14.10 | Omni/Finance | No stock | Balance/payout/retry/reconcile tests | `MAPPED-PLAN` |
| FP-OMN-009 | Reconciliation exposes actionable missing/mismatch/unmapped/return/payout statuses. | Plan §14.11 | Omni/Finance Analytics | Read-only exception engine | Each exception fixture/drill-down | `MAPPED-PLAN` |
| FP-OMN-010 | Return/refund preserves original revenue, adds follow-up Finance event, and stock waits for QC. | Plan §14.12; AGENTS | Omni → Quality/Warehouse/Finance | Accepted return only IN | Critical history/no-early-stock tests | `MAPPED-PLAN` |
| FP-OMN-011 | Typed adjustment composite identity prevents overwrite/duplicate and links order/store/file. | Plan §14.13 | Omni → Finance | Separate physical event if any | Different types/reimport/composite key tests | `MAPPED-PLAN` |
| FP-POS-001 | POS requires actual internal Item, qty > 0, price snapshot, and stock validation. | Plan §§12.7,14.14; AGENTS | Omni POS | Warehouse issue | Critical strict-Item/qty/price test | `MAPPED-PLAN` |
| FP-POS-002 | POS sale, Warehouse issue, COGS and Finance event succeed atomically/idempotently or show repair state. | Plan §12.7; AGENTS | Omni orchestration; owned services | Immediate OUT; mapped revenue/tender/COGS | Failure injection and retry tests | `MAPPED-PLAN` |
| FP-POS-003 | POS return/void, tender, tax, session and offline/retry controls preserve history. | Not fully specified | Omni/Warehouse/Finance/Tax | Reversal/return owned | Approved control-matrix tests | `UNRESOLVED` |

## 8. Finance, reporting, incentives, closing, and migration parity

| ID | Capability / accepted outcome | Evidence | Target ownership / upgrade | Stock / accounting boundary | Acceptance evidence required | Status |
|---|---|---|---|---|---|---|
| FP-FIN-001 | Finance alone owns journal/GL/AR/AP/cash/bank/marketplace/fixed asset/depreciation/closing. | Plan §15.1; AGENTS | Finance | Warehouse remains qty owner | Cross-write architecture tests/review | `MAPPED-PLAN` |
| FP-FIN-002 | Event → context → mapping → candidate → validate → post; no hardcoded transactional account. | Plan §15.2; AGENTS | Finance resolver/poster | Operational modules emit facts only | Static review plus resolver tests | `MAPPED-PLAN` |
| FP-FIN-003 | Journals balance, source-post once, immutable after post, validate period, snapshot mapping and link source. | Plan §15.9; AGENTS | Finance | Valuation events source-linked | Debit/credit, duplicate, closed-period, reversal tests | `MAPPED-PLAN` |
| FP-FIN-004 | AR/AP controls reconcile to detail; payments settle without duplicating original revenue/expense. | Plan §§15.4–15.5,20 | Finance | No physical stock | Critical accrued-payment test and control reconciliation | `MAPPED-PLAN` |
| FP-FIN-005 | Marketplace AR and balance remain distinct through completion, settlement and payout. | Plan §15.6 | Finance | No physical stock | Order-to-payout reconciliation | `MAPPED-PLAN` |
| FP-FIN-006 | Asset purchase becomes asset register/depreciation, never inventory. | Plan §15.7 | Finance | No Warehouse movement | Golden asset acquisition/depreciation test | `MAPPED-PLAN` |
| FP-FIN-007 | Inventory GL reconciles to Warehouse valuation; no competing quantity ledger. | Plan §15.8 | Warehouse qty/value source; Finance GL | Explicit owner boundary | Period reconciliation and drill-down | `MAPPED-PLAN` |
| FP-RPT-001 | Financial/management reports drill Report→Account→Journal Line→Journal→Event→Document; no unexplained number. | Plan §§16–18 | Finance/Analytics/Reports | Read-only | Totals reconcile and drill-down authorization | `MAPPED-PLAN` |
| FP-RPT-002 | Report definitions are versioned/effective and report view/generation never posts. | Plan §§17,24,35 | Reports/Finance/Tax | No ledger effect | Report side-effect test and archive metadata | `MAPPED-PLAN` |
| FP-INC-001 | Effective-dated generic incentive snapshots trigger, rate, basis, beneficiary; states through reversal. | Plan §§9,32 | Incentives → Finance | No stock except source acceptance | Rule/version/duplicate/reversal tests | `MAPPED-PLAN` |
| FP-INC-002 | CPO fee uses posted accepted finished-goods qty × effective rate snapshot. | Plan §33 | Warehouse event → Incentives → Finance | Receipt is source, not produced qty | Accepted-vs-produced/duplicate test | `MAPPED-PLAN` |
| FP-CLS-001 | Close progresses OPEN→SOFT_CLOSE→FINANCE_REVIEW→CLOSED→TAX_FILED→LOCKED; restricted reopen. | Plan §22 | Finance/Core | Warehouse validates periods/cutoff | Posting reject/reopen approval/audit tests | `MAPPED-PLAN` |
| FP-CLS-002 | Warehouse cutoff becomes controlled opening/closing balance, not master-item overwrite. | Plan §22 | Warehouse/Finance | Opening stock is typed movement | Close/opening reconciliation | `MAPPED-PLAN` |
| FP-IMP-001 | Versioned import flow is upload→validate→preview→confirm→batch→reconcile. | Plan §23 | Data Exchange + domain services | Cannot bypass owner services | Error/warning/checksum/idempotency tests | `MAPPED-PLAN` |
| FP-MIG-001 | Cutover reconciles TB, qty/value, AR/AP, bank, marketplace, fixed assets, commitments and tax before SMB read-only. | Plan §§38,46 | Migration/Finance/Warehouse/business owners | Both ledgers reconcile | Signed cutover reconciliation pack | `MAPPED-PLAN` |

## 9. Coverage summary

| Domain group | Register rows | Plan-level mapped | Unresolved | Source-blocked-specific |
|---|---:|---:|---:|---:|
| Core/Master | 10 | 9 | 1 | 0 |
| Sales/Project | 9 | 8 | 1 | 0 |
| Purchasing | 9 | 7 | 1 | 1 |
| Production | 10 | 8 | 1 | 1 |
| Warehouse/Quality | 10 | 8 | 2 | 0 |
| Omnichannel/POS | 14 | 12 | 2 | 0 |
| Finance/Reports/Incentives/Closing/Migration | 15 | 15 | 0 | 0 |
| **Total** | **77** | **67** | **8** | **2** |

All 77 rows are globally source-blocked even when plan-level status is mapped. The endpoint matrix separately classifies all 96 names in Project Plan §40.

## 10. Unresolved decisions register

| ID | Question / conflict | Affected modules | Stock impact | Accounting impact | Recommended interpretation pending approval |
|---|---|---|---|---|---|
| U-FP-001 | Missing actual source/accepted patch/UI/Sheet baseline prevents proof of completeness and behavior. | All | Unknown stock sources/bugs. | Unknown accounting sources/bugs. | Obtain and hash source freeze; delta-audit every function, trigger, formula and UI action. |
| U-FP-002 | B2B invoiceable basis and revenue/COGS timing are not fully specified. | Sales, Warehouse, Finance | Delivery/value correlation. | AR/revenue/COGS timing. | Approve ordered/delivered/milestone/exception bases and event dates. |
| U-FP-003 | UOM conversions/precision and lot/serial/expiry scope are not defined. | Catalog, Purchasing, Production, Warehouse, Sales | Fundamental quantity identity. | Valuation rounding/traceability. | Explicitly approve baseline before Phase 2. |
| U-FP-004 | Maklun shared-cost allocation and acceptance/QC timing lack formulas. | Purchasing, Quality, Warehouse, Production, Finance | Receipt qty/timing. | HPP/AP allocation. | Approve allocation basis, rounding, acceptance and reversal behavior. |
| U-FP-005 | Weighted-average backdating, negative sequence, reversal propagation, and revaluation policy are incomplete. | Warehouse, Finance, Production | Quantity order/correction. | Inventory/COGS/HPP changes. | Approve transaction-order and closed-period revaluation policy. |
| U-FP-006 | QC applicability and reject/rework/scrap/disposal disposition matrix are incomplete. | Purchasing, Production, Quality, Warehouse, Finance | Receipt/issue route. | Loss/recovery/AP/AR roles. | Configure QC policy plus controlled disposition events. |
| U-FP-007 | Marketplace completed statuses and gross revenue/tax/discount basis are absent per channel. | Omni, Finance, Tax | None directly. | Revenue completeness/amount/timing. | Freeze examples and approve raw-status/amount mapping. |
| U-FP-008 | Settlement field roles, signs, tolerances, split/partial matching and payout IDs are absent. | Omni, Finance | None. | Fees/AR/balance/bank reconciliation. | Normalize representative files into approved event roles. |
| U-FP-009 | POS tender, tax, discount, cash-session, void/return and offline/retry rules are incomplete. | Omni, Warehouse, Finance, Tax | Reversal/return integrity. | Tender/revenue/tax/cash integrity. | Approve POS control matrix while preserving strict Item and atomic issue. |
| U-FP-010 | Overhead allocation bases, periods and SPK/output eligibility windows are not locked. | Purchasing, Production, Finance | None directly. | HPP and expense/WIP allocation. | Approve auditable rule versions and reversal propagation. |
| U-FP-011 | Approval thresholds, roles/data scopes, document series, and segregation are not supplied. | Core and all domains | Unauthorized movement risk. | Unauthorized posting/payment/close risk. | Capture current accepted authorization matrix before Phase 1 review. |
| U-FP-012 | Tax rules/regulatory details require implementation-date verification. | Sales, Purchasing, Omni, Finance, Tax | Landed/valuation context possible. | Tax accounting/reporting/fiscal assets. | Verify authoritative regulations and obtain Finance/Tax sign-off in planned phase. |

## 11. Suspected bugs/dead code and unmapped scope

See `KAJABoard_Legacy_Endpoint_UseCase_Matrix.md` §8 for the function-level risk hypotheses. Most notable are generic deletes, aggregate SPK closure, direct Production→Warehouse sync, cross-spreadsheet cutoff/ETL, manual generic mutation, return-import stock effects, settlement/revenue conflation, SKU variation collision, non-strict POS item selection, and current-master HPP.

Plan-listed unmapped functions: **0 of 96**. Actual legacy functions/use cases not mapped: **unknown**, because the source population is unavailable. Plan domains without a §40 source inventory—Finance, Master, Quality, Projects, Incentives, Tax, Analytics/Reports, Core—are mapped only at capability level.

## 13. Actual-evidence parity delta

The original 77 rows remain conceptual requirements. The following 28 rows capture behaviors and conflicts that could only be established from the supplied package. `VERIFIED-RETAIN` means source confirms the business outcome; `VERIFIED-UPGRADE` means the capability remains but the implementation/control must change; `BLOCKER` requires a decision before Phase 1.

| ID | Capability / actual behavior | Source evidence | Target ownership / correction | Required regression evidence | Status |
|---|---|---|---|---|---|
| FP-EV-001 | HMAC passport, 6-hour TTL, logout invalidation, heartbeat refresh and module launch behavior exist. | Portal v0.7 and copied module security helpers | Core auth/session/permission; environment secret; no copied module security | token expiry/logout/role/data-scope | `VERIFIED-UPGRADE` |
| FP-EV-002 | Document number generation uses prefix/counter/date and evidenced daily reset. | Master Numbering | Core numbering with concurrency and approved series | concurrent unique number | `VERIFIED-UPGRADE` |
| FP-EV-003 | Generic stock service lacks source uniqueness/negative guard. | Master StockMovementService | Superseded by Warehouse-only posting contract | source cannot post twice; no negative | `VERIFIED-UPGRADE` |
| FP-EV-004 | Sales preserves PO -> SJ -> invoice -> SOA/payment projection and all key prints. | Sales backend/UI/print files | Sales commercial sources; Warehouse OUT; Finance AR/payment | end-to-end partial delivery/invoice/SOA | `VERIFIED-RETAIN` |
| FP-EV-005 | Sales delivery writes OUT directly and edit voids/reappends it. | Sales stock bridge | Sales emits request; Warehouse posts/reverses | retry/edit creates one owned effect | `VERIFIED-UPGRADE` |
| FP-EV-006 | Sales server does not authoritatively reject delivery above remaining. | Sales save/remaining UI | Enforce under lock in service layer | partial delivery cannot exceed remaining | `VERIFIED-UPGRADE` |
| FP-EV-007 | PO completion is aggregate, not item-safe. | `cekDanUpdateStatusPO` | Per stable line/item fulfillment | surplus cannot hide shortage | `VERIFIED-UPGRADE` |
| FP-EV-008 | Invoice accepts PO, SJ and manual sources. | Sales invoice UI/backend | Default delivery-based invoice; controlled Sales-Order exception requires permission, reason/audit, and no stock effect; proforma is non-posting/no AR | delivered-not-invoiced, controlled SO exception, proforma nonposting | `RESOLVED-OWNER-DECISION` |
| FP-EV-009 | DP no-double patch separates PO DP from invoice application journal. | Sales v0.9 DP comments/logic | Finance-owned application with source uniqueness | DP application once | `VERIFIED-RETAIN` |
| FP-EV-010 | Purchase accounting/stock behavior is inferred from category names. | Purchasing + Finance source readers | Explicit legacy-category mapping to five treatments; unmapped staging blocked; no substring inference | asset no stock; expense/service CC; unmapped blocked | `RESOLVED-OWNER-DECISION` |
| FP-EV-011 | SPK material-output pairs, Kirim Bahan, Terima Maklun and FULL_ORDER/CMT cost source exist. | Purchasing v0.8/v0.9.7 | Stable work-order lines; movement/AP candidates | pair preservation and partial flow | `VERIFIED-RETAIN` |
| FP-EV-012 | SPK edits delete/recreate all rows; Sales-pull UI may omit required material selector. | Purchasing backend/UI | Stable line IDs and transactional edit | sibling line not deleted | `VERIFIED-UPGRADE` |
| FP-EV-013 | Production WIP availability is item-safe and reject-stage aware. | `_cekKetersediaanWIP` | Preserve exact per-item formulas | all three availability formulas | `VERIFIED-RETAIN` |
| FP-EV-014 | Production close aggregates all outputs. | `cekDanTutupSPK` | Per-output completion | one output short blocks close | `VERIFIED-UPGRADE` |
| FP-EV-015 | Potong OUT and handover IN are directly written by Production. | Production stock helpers | Warehouse candidates; handover is not stock until receipt | ownership and idempotency | `VERIFIED-UPGRADE` |
| FP-EV-016 | Legacy HPP includes material, wage, broad extra cost and monthly expenses, then overwrites movement costs. | Production HPP/sync | EXPENSE/SERVICE + eligible Cost Center + SnapshotProduction; item-specific cost stays on item; shared cost stores rule/snapshot; payment never duplicates accrual | overhead once; office expense excluded; item allocation trace | `RESOLVED`; shared formula `DEFERRED IMPLEMENTATION DETAIL` |
| FP-EV-017 | Warehouse contract V2 provides Tx_Key duplicate guard, lock, positive qty and default negative-stock rejection. | Warehouse v2.6 | Sole physical ledger service; DB constraints | duplicate/concurrency/negative tests | `VERIFIED-RETAIN` |
| FP-EV-018 | Opname computes and posts a variance rather than replacing balance. | Warehouse opname | Preserve with approval/reason/reversal | variance not overwrite | `VERIFIED-RETAIN` |
| FP-EV-019 | Cost close can mutate existing posted OUT cost values. | Warehouse cost close | Never overwrite posted history; open-period correction uses deterministic reversal/revaluation/adjustment; locked-period correction posts in authorized open period with original references | immutable history, period authorization, traceable revaluation | `RESOLVED-OWNER-DECISION` |
| FP-EV-020 | QC import/scan does not change stock; batch accepted result does. | QC v2.0.1 | Preserve timing, route receipt through Warehouse | registration no stock; accepted only | `VERIFIED-RETAIN` |
| FP-EV-021 | QC actual statuses differ from locked target statuses. | QC backend | Runtime PASS/HOLD/REJECT/REWORK; unsafe legacy values retain raw value and enter review-only `LEGACY_UNMAPPED` migration state | deterministic migration map; unmapped never posts | `RESOLVED-OWNER-DECISION` |
| FP-EV-022 | Omni order key is Order Number + SKU + Variation and import is lock/upsert based. | Omni v1.6.5 | Preserve external identity and idempotent import batch/row | unchanged retry/no duplicate | `VERIFIED-RETAIN` |
| FP-EV-023 | Omni order storage does not preserve the complete qty triplet and has no completion timestamp. | Omni order headers/writers | Persist all three quantities and valid `Waktu Selesai`; configurable MarketplaceStatusMap supplies normalized status | quantity/date/status-map contract | `RESOLVED-OWNER-DECISION` |
| FP-EV-024 | Summary V3 is derived cache with raw fallback; exact transit status is `Sudah Dikirim`. | Omni summary v1.6.4 and Warehouse v2.6 | Cache never ledger; normalized status mapping | summary/raw parity | `VERIFIED-RETAIN` |
| FP-EV-025 | POS permits subcategory selection resolving to an arbitrary last item; stock and sale writes are not atomic/idempotent. | Omni POS helpers/save | Strict Item, positive qty, price/cost snapshot, explicit tender, atomic/idempotent post, reversal/return documents, and OPEN/CLOSED cash session with variance | required POS critical/control tests | `RESOLVED-OWNER-DECISION`; implementation remains `UPGRADE` |
| FP-EV-026 | Finance latest sync endpoints are reader-only and reports derive balances from operational sheets. | Finance Entry/Core/Readers/Report | Finance event ingestion and posted GL; reports read ledger/read models only | report=GL; report never posts | `VERIFIED-UPGRADE` |
| FP-EV-027 | Marketplace sale and settlement are conceptually separate, but revenue uses order date and remains derived, not posted. | Omni/Finance daily and marketplace readers | Revenue only for valid Waktu Selesai + normalized COMPLETED + unique source + valid Store/accounting mapping; return/refund is separate history-preserving event | no revenue twice; correct date/map; return preserves revenue | `RESOLVED-OWNER-DECISION` |
| FP-EV-028 | Bank import verifies PDF counts/totals/balances and reconciliation supports one-to-many matching. | Finance Recon v1.8.5/v1.8.7 | Preserve import/reconciliation outcomes with immutable links/audit | verified import/multi-match/no double use | `VERIFIED-RETAIN` |

### 13.1 Register accounting

| Measure | Count |
|---|---:|
| Previous rows | 77 |
| New evidence rows | 28 |
| Corrected existing interpretations | 18 |
| Removed/merged rows | 0 |
| **Authoritative total** | **105** |

The 18 corrected interpretations concern: source availability; Warehouse contract strength; direct cross-module stock writes; Sales remaining/closure; invoice basis; DP application; explicit purchase treatment absence; SPK edit identity; Production WIP/close/HPP; QC status vocabulary; Omni quantity/date storage; POS item identity/atomicity; Finance reader-only sync; marketplace recognition date; and posted cost mutation.

### 13.2 Owner-approved closure decisions

The official baseline is the current read-only `legacy/smb_gas/` package identified by `KAJABoard_SMB_GAS_Legacy_Evidence_Manifest.md`. Exact historical deployment provenance is not required. All seven evidence rows formerly marked `BLOCKER`, plus the POS control-model gap, are resolved by owner decision. The exact shared-cost allocation formula is deferred to the Production/HPP implementation gate because it does not change Phase 1 foundation architecture.

## 14. Evidence-based acceptance gate

The actual source population is represented and the eight former blockers are resolved. **PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** Phase 1 is ready but must not start without an explicit instruction.

## 15. Historical provisional acceptance gate (superseded)

This register is not `ACCEPTED`. Phase 1 must not start until:

1. the actual SMB source and accepted patches are frozen and hashed;
2. the UI/function/Sheet/formula/trigger inventory is reconciled to the endpoint matrix;
3. additional use cases are added and classified;
4. material unresolved decisions are approved or explicitly deferred without blocking foundational semantics;
5. business owners review and sign off all nine Phase 0 artifacts.
