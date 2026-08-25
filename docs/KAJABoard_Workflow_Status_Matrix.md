# KAJABoard Workflow and Status Matrix

> **AUTHORITATIVE UPDATE (25 August 2026): OWNER APPROVED FOR PHASE 0 CLOSURE.** Section 7 inventories actual status evidence; sections 7.1-8 contain the accepted canonical decisions. No implementation has started.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — functional state vocabulary  
**Status:** DRAFT FOR REVIEW  
**Important:** Project Plan states are locked where explicitly given. Other state sets below are conservative target concepts and remain `PROPOSED` until matched to the missing legacy source and accepted by business owners.

## 1. State-control rules

- Critical state is a controlled choice, never arbitrary text.
- Every transition is performed in the owning service with permission, data scope, validation, actor/time, reason where required, audit, and idempotency.
- Posted/accepted/financially effective records are immutable. Correction uses linked reversal, adjustment, return, credit note, or approved reopen—not silent delete.
- A source domain cannot claim a Warehouse or Finance effect succeeded before the owner returns a durable result; pending/repair states must be visible.
- State labels presented in a composed UI may include owned substates (for example Sales source status plus Finance payment status) without copying or competing with the owner ledger.

## 2. Locked state sets

### 2.1 SPK

| Current | Allowed next | Guard / side effect | Owner | Correction rule |
|---|---|---|---|---|
| `DRAFT` | `SUBMITTED`, `VOID` | Required vendor/type/output/material-output data valid | Purchasing for external; Production/Purchasing contract for internal | Draft may be edited; void audited |
| `SUBMITTED` | `APPROVED`, `DRAFT`, `VOID` | Approval outcome and segregation | Approval owner | Reject/back-to-draft requires reason |
| `APPROVED` | `IN_PROGRESS`, `VOID` | Approved source immutable except controlled change | Owning SPK domain | Void only if no effective child postings or via full reversal plan |
| `IN_PROGRESS` | `PARTIALLY_COMPLETED`, `READY_FOR_WAREHOUSE`, `COMPLETED`, `VOID` | Valid item-level WIP; actual progress exists | Production/Purchasing by type | Posted lines corrected individually |
| `PARTIALLY_COMPLETED` | `IN_PROGRESS`, `READY_FOR_WAREHOUSE`, `COMPLETED`, `VOID` | Some output accepted; remaining open | Owning SPK domain | Cannot erase accepted receipts |
| `READY_FOR_WAREHOUSE` | `PARTIALLY_COMPLETED`, `COMPLETED`, `IN_PROGRESS` | Handover lines within item-level available qty | Production | Warehouse acceptance is a separate state/result |
| `COMPLETED` | no normal transition; controlled reopen/adjustment only | Every output item: completion conservation satisfied and all intermediate WIP zero | Owning SPK domain + approval | Never aggregate-surplus close; linked correction only |
| `VOID` | no normal transition | No unhandled effective stock/accounting child remains | Owning domain | Retained in audit/history |

### 2.2 Stock movement

| Current | Allowed next | Guard / side effect | Owner | Correction rule |
|---|---|---|---|---|
| `DRAFT` | `PENDING`, cancelled concept | Complete source context and positive qty | Warehouse | Draft may be discarded under audit policy |
| `PENDING` | `POSTED`, rejected/cancelled concept | Unique source, permission, valid Item/UOM/warehouse/date, stock sufficient for OUT, costing valid | Warehouse | Retry with same key returns same result |
| `POSTED` | `REVERSED` | Included in stock and valuation; source notified | Warehouse | Original immutable; reversal movement linked |
| `REVERSED` | no direct edit | Original and correction both retained | Warehouse | Further correction is another controlled adjustment |

The plan explicitly lists `DRAFT`, `PENDING`, `POSTED`, `REVERSED`; rejected/cancelled handling is unresolved rather than silently added to the canonical enum.

### 2.3 QC result

| Result | Meaning | Allowed progression | Stock rule | Finance rule |
|---|---|---|---|---|
| `HOLD` | Inspected quantity awaits final decision/information | `PASS`, `REJECT`, or `REWORK` through an approved final decision | No final movement merely from HOLD | No final adjustment merely from HOLD |
| `PASS` | Accepted under inspection policy | Terminal for that decision version | May emit Warehouse receipt/return candidate; Warehouse must post | May emit correlated accounting event after source/stock rule |
| `REJECT` | Not accepted | Terminal or controlled new reinspection after disposition | No receipt unless separate approved recovery path; supplier return/disposal may emit movement | Loss/vendor/customer adjustment follows approved disposition mapping |
| `REWORK` | Requires rework and reinspection | Rework task → new inspection decision | No final stock receipt merely from REWORK | Cost treatment unresolved/configured |

### 2.4 Fiscal period

| Current | Allowed next | Guard | Posting behavior | Owner |
|---|---|---|---|---|
| `OPEN` | `SOFT_CLOSE` | Period-end process begins | Normal authorized posting allowed | Finance |
| `SOFT_CLOSE` | `OPEN`, `FINANCE_REVIEW` | Preliminary reconciliations/checklist | Restricted by approved policy | Finance |
| `FINANCE_REVIEW` | `SOFT_CLOSE`, `CLOSED` | Stock, AR/AP, bank, marketplace, depreciation, tax checks | Finance-review corrections only | Finance |
| `CLOSED` | approved reopen, `TAX_FILED` | Close approved and logged | Reject normal postings | Finance + approver |
| `TAX_FILED` | `LOCKED`, exceptional approved correction route | Filing/reference recorded | Highly restricted | Finance/Tax |
| `LOCKED` | exceptional controlled reopen only | Senior approval, reason, impact analysis | Reject normal postings | Finance + designated authority |

### 2.5 Marketplace reconciliation

Workflow state:

| Current | Allowed next | Guard / meaning |
|---|---|---|
| `OPEN` | `PARTIAL`, `MATCHED`, `DIFFERENCE` | Completed/order/settlement/payout source awaits matching |
| `PARTIAL` | `MATCHED`, `DIFFERENCE`, `CLOSED` | Some amount matched; remainder traceable |
| `MATCHED` | `CLOSED`, `DIFFERENCE` after linked adjustment | Control and source agree within approved tolerance |
| `DIFFERENCE` | `PARTIAL`, `MATCHED`, `CLOSED` | Actionable explained/unexplained difference exists |
| `CLOSED` | approved reopen only | Resolution/explanation approved; source history retained |

Exception classification (orthogonal to workflow state): `COMPLETED_NOT_SETTLED`, `SETTLEMENT_MATCH`, `SETTLEMENT_PARTIAL`, `SETTLEMENT_DIFFERENCE`, `SETTLEMENT_WITHOUT_COMPLETED_ORDER`, `RETURN_AFTER_COMPLETION`, `COMPLETED_NEVER_PAID`, `PAYOUT_PENDING`, `PAYOUT_MATCH`, `UNMAPPED_SKU`, `UNMAPPED_STORE`.

### 2.6 Incentive

| Current | Allowed next | Guard / effect | Owner |
|---|---|---|---|
| `ESTIMATED` | `ACCRUED`, cancelled concept | Forecast only; no payable | Incentives |
| `ACCRUED` | `APPROVED`, `REVERSED` | Accepted trigger, effective rule/rate/basis/beneficiary snapshot | Incentives/Finance event |
| `APPROVED` | `PAYABLE`, `REVERSED` | Approval and margin/eligibility checks | Incentives approver |
| `PAYABLE` | `PAID`, `REVERSED` | Finance AP/payable exists | Finance owns settlement |
| `PAID` | `REVERSED` only via controlled correction | Cash/bank settlement posted; no duplicate fee expense | Finance |
| `REVERSED` | no edit | Original retained with reversal | Incentives/Finance |

## 3. Proposed operational state sets

These states translate plan-defined workflows into a reviewable vocabulary; they do not claim to reproduce unavailable SMB strings.

### 3.1 Sales order

| State (`PROPOSED`) | Entry guard | Allowed next / business meaning |
|---|---|---|
| `DRAFT` | Customer/item/qty may still be edited | `SUBMITTED`, `VOID` |
| `SUBMITTED` | Required commercial fields valid | `APPROVED`, `DRAFT`, `VOID` |
| `APPROVED` | Approval/credit gates pass | `PARTIALLY_FULFILLED`, `FULFILLED`, `ON_HOLD`, `VOID` |
| `ON_HOLD` | Credit/operational reason and owner recorded | `APPROVED`, `VOID` |
| `PARTIALLY_FULFILLED` | At least one posted delivery; remaining > 0 | `FULFILLED`, `ON_HOLD`, controlled cancellation of remainder |
| `FULFILLED` | All lines fulfilled by posted, non-reversed deliveries | `CLOSED` when commercial obligations complete |
| `CLOSED` | Invoice/closure policy satisfied | Controlled reopen only |
| `VOID` | No unhandled posted child effect | Terminal/history retained |

Invoice/payment status must not be collapsed into Sales order state. Sales reads Finance `unposted/open/partial/paid/overdue` projections.

### 3.2 Sales delivery

| State (`PROPOSED`) | Entry guard | Owned relationship |
|---|---|---|
| `DRAFT` | Lines selected; qty may be edited | Sales-owned |
| `SUBMITTED` | Qty ≤ remaining by source line | Sales/approval |
| `PENDING_WAREHOUSE` | Idempotent issue request accepted | Sales source waits for Warehouse |
| `POSTED` | All required Warehouse movements posted | Composite display; Warehouse movement remains authoritative |
| `PARTIALLY_POSTED` | Some lines posted, explicit repair/remaining state | No false full success |
| `REVERSED` | Linked Warehouse reversal complete | Original retained |
| `VOID` | Only before effect or after complete reversal | Audited |

### 3.3 Sales invoice source

| State (`PROPOSED`) | Entry guard | Finance relationship |
|---|---|---|
| `DRAFT` | Source lines/totals editable | No AR |
| `SUBMITTED` | Totals and lineage valid | Approval pending |
| `POSTING` | Finance event accepted/pending | Expose repair status if needed |
| `POSTED` | Finance journal/AR durably posted | Source immutable |
| `CREDITED` / `REVERSED` | Linked approved correction posted | Original retained |
| `VOID` | No Finance effect or complete controlled reversal | Audited |

Payment states (`UNPAID`, `PARTIAL`, `PAID`, `OVERDUE`) are Finance-derived views, not editable Sales states.

### 3.4 Purchase document / vendor source

| State (`PROPOSED`) | Entry guard | Allowed next / routing |
|---|---|---|
| `DRAFT` | Lines include valid category/treatment snapshots | `SUBMITTED`, `VOID` |
| `SUBMITTED` | Treatment validation and required Cost Center/asset/SPK context pass | `APPROVED`, `DRAFT`, `VOID` |
| `APPROVED` | Approval/budget gates pass | `PARTIALLY_RECEIVED`, `RECEIVED`, `BILLED`, `CLOSED`, `VOID` as applicable |
| `PARTIALLY_RECEIVED` | Some Warehouse receipt results posted for inventory/maklun | `RECEIVED`, controlled remainder close |
| `RECEIVED` | Required accepted receipt qty posted | `BILLED`, `CLOSED` |
| `BILLED` | Finance AP source posted | Payment remains Finance-owned |
| `CLOSED` | Receipt/bill/commitment obligations resolved | Controlled reopen only |
| `VOID` | No unhandled stock/AP/asset effect | Terminal/history retained |

One state may be insufficient for receipt and billing axes; target design should keep orthogonal fulfillment and Finance statuses rather than creating ambiguous combined strings.

### 3.5 Production work entry and handover

| Entity | State (`PROPOSED`) | Guard / next |
|---|---|---|
| Work entry | `DRAFT` | Lines editable before post |
| Work entry | `POSTED` | Per-item WIP availability valid; stable lines immutable |
| Work entry | `REVERSED` | Linked line-level correction; siblings unaffected |
| Handover | `DRAFT` | Qty planned |
| Handover | `READY_FOR_GUDANG` | Qty ≤ available Warehouse WIP per output Item |
| Handover | `PARTIALLY_ACCEPTED` | Warehouse accepted some lines/qty |
| Handover | `ACCEPTED` | Warehouse posted all accepted receipt effects |
| Handover | `REJECTED` | Warehouse/QC did not accept; reason and next action present |
| Handover | `REVERSED` | Linked Warehouse reversal complete |

### 3.6 Stock opname / adjustment

| State (`PROPOSED`) | Guard / effect |
|---|---|
| `DRAFT` | Count scope prepared; no movement |
| `COUNTING` | Physical counts captured; system snapshot controlled |
| `REVIEW` | Variances and reasons visible; no arbitrary overwrite |
| `APPROVED` | Required approval complete |
| `POSTED` | Only variance movements posted idempotently |
| `REVERSED` | Linked adjustment reversals retained |
| `VOID` | No posted variance or complete reversal |

### 3.7 Omnichannel import and order

| Entity | State (`PROPOSED`) | Guard / effect |
|---|---|---|
| Import batch | `UPLOADED` | File metadata/checksum captured |
| Import batch | `VALIDATED_WITH_ERRORS` | Confirmation blocked until fatal errors resolved |
| Import batch | `READY_TO_IMPORT` | Preview accepted; warnings visible |
| Import batch | `IMPORTED` | Idempotent domain writes complete |
| Import batch | `PARTIAL_FAILED` | Some rows require explicit repair; no silent success |
| Import batch | `REVERSED` | Only through controlled compensating actions where allowed |
| Omni order | `UNMAPPED` | Store/SKU/variation mapping incomplete; no actual Item stock effect |
| Omni order | `DEMAND_READY` | Mapped order lines create Warehouse demand |
| Omni order | `PARTIALLY_PACKED` | Some internal qty issued |
| Omni order | `PACKED` | Demand fully issued; does not itself mean revenue recognized |
| Omni order | `COMPLETED` | Eligible final external state + valid completion time; one revenue event |
| Omni order | `RETURN_OR_ADJUSTMENT_PENDING` | Immutable follow-up exists; completed history remains |

Raw marketplace statuses must be retained separately from normalized operational/accounting status.

### 3.8 Settlement and payout

| Entity | State (`PROPOSED`) | Guard / effect |
|---|---|---|
| Settlement batch | `UPLOADED` → `VALIDATED` → `IMPORTED` | Preview, structured roles, source identity, idempotency |
| Settlement order | `UNMATCHED`, `PARTIAL`, `MATCHED`, `DIFFERENCE` | Match completed AR per Store+Order; never create revenue |
| Settlement order | `POSTED` | Finance settlement journal/balance effect complete |
| Payout | `PENDING`, `MATCHED`, `POSTED`, `DIFFERENCE`, `REVERSED` | Move marketplace balance to bank only when Finance posts |

### 3.9 Return/refund

| State (`PROPOSED`) | Guard / effect |
|---|---|
| `REGISTERED` | Original source/order/invoice captured; no stock effect |
| `AWAITING_ITEM` | Physical item not yet received/identified; no stock effect |
| `QC_PENDING` | Inspection requested |
| `HOLD`, `REJECTED`, `REWORK` | Mirrors controlled QC result; no accepted return IN |
| `ACCEPTED` | QC PASS; emits Warehouse return candidate |
| `STOCK_POSTED` | Warehouse RETURN_IN posted |
| `FINANCIALLY_ADJUSTED` | Finance credit/refund/adjustment posted; original revenue retained |
| `CLOSED` | Stock/financial/reconciliation obligations resolved or explicitly not applicable |

### 3.10 POS

| State (`PROPOSED`) | Guard / effect |
|---|---|
| `DRAFT` | Strict Item lines, qty, price/tender being entered |
| `POSTING` | Atomic stock and Finance orchestration in progress |
| `POSTED` | Sale plus Warehouse issue and required Finance event durable |
| `REPAIR_REQUIRED` | Only if infrastructure prevents full atomicity; visible and non-final |
| `VOIDED` / `RETURNED` | Linked approved reversal/return; original retained |

## 4. Finance posting states (`PROPOSED`)

| Entity | States | Critical guards |
|---|---|---|
| Business event inbox | `RECEIVED`, `VALIDATING`, `READY`, `POSTED`, `ERROR`, `REVERSED` | Unique source, schema/context, active mapping, open period |
| Journal | `DRAFT`, `PENDING_APPROVAL`, `POSTED`, `REVERSED` | Debit=Credit; source unique; mapping snapshot; actor/approval; posted immutable |
| AR/AP item | `OPEN`, `PARTIAL`, `SETTLED`, `OVERDUE`, `CREDITED`, `REVERSED` | Derived from posted allocations/due date; payment cannot create source expense/revenue |
| Payment | `DRAFT`, `PENDING_APPROVAL`, `POSTED`, `REVERSED` | Allocation ≤ open item; bank/cash context; unique source; period/permission |
| Fixed asset | `CANDIDATE`, `CAPITALIZED`, `ACTIVE`, `FULLY_DEPRECIATED`, `DISPOSED`, `REVERSED` | ASSET source only; approved class/life/method; no inventory stock |

## 5. Illegal transition examples

| Illegal action | Reason |
|---|---|
| `DRAFT → POSTED` while bypassing required approval | Violates controlled workflow and segregation. |
| Delete a `POSTED` StockMovement or Journal | Destroys traceability and reconciliation. |
| Mark delivery `POSTED` before Warehouse result | Sales does not own physical issue. |
| Mark invoice paid in Sales | Finance owns payment and AR. |
| Close SPK from aggregate total while one output is short | WIP/completion must be item-safe. |
| Complete Omni revenue without valid `Waktu Selesai` | Wrong recognition date. |
| Settlement `IMPORTED → revenue recognized` | Settlement is not revenue. |
| Return `REGISTERED → stock posted` without QC PASS | Return registration does not change physical stock. |
| Change purchase treatment after effective downstream postings | Rewrites historical meaning; use controlled correction. |
| Reopen `LOCKED` period without explicit authority/reason | Breaks period integrity. |

## 6. UNRESOLVED status decisions

| ID | Question / source conflict | Affected modules | Stock impact | Accounting impact | Recommended interpretation |
|---|---|---|---|---|---|
| U-STS-001 | Actual legacy status strings, transitions, UI guards, and fallback statuses are unavailable. | All | Unknown movement gating. | Unknown posting/payment gating. | Extract from source and Sheets; map each value to canonical or `REMOVE-DEADCODE` before acceptance. |
| U-STS-002 | Required approval steps and rejection/cancellation state names are not specified. | All transactions/Core | Unauthorized stock risk. | Unauthorized journal/payment risk. | Approve maker/checker matrix and only then finalize enums. |
| U-STS-003 | Sales order closure versus cancellation of unfulfilled remainder is undefined. | Sales, Warehouse, Projects | Reservation/demand release affected. | Committed/revenue forecast affected. | Use explicit approved remainder cancellation, never silently set fulfilled. |
| U-STS-004 | Purchase receipt and vendor billing are orthogonal but legacy may combine them. | Purchasing, Warehouse, Finance | Receipt state affected. | AP timing affected. | Model separate fulfillment and Finance status projections. |
| U-STS-005 | External marketplace statuses eligible for normalized `COMPLETED` are not listed per channel. | Omnichannel, Finance | Packing lifecycle correlation. | Revenue completeness/timing. | Configure and effective-date raw→normalized status mapping. |
| U-STS-006 | QC partial decisions (some PASS/some REJECT/REWORK) need a document-level status convention. | Quality, Warehouse, Finance | Partial receipt/return affected. | Partial adjustments affected. | Keep quantities/result per inspection line and derive document summary; do not lose mixed outcomes. |
| U-STS-007 | Failure/repair states for multi-domain synchronous commands are not defined. | Sales, Purchasing, Production, Omni, Warehouse, Finance | Orphan movement risk. | Orphan journal risk. | Prefer atomic transaction in modular monolith; otherwise durable explicit repair/outbox states. |

## 7. Actual legacy status inventory and mapping

| Domain/entity | Actual legacy values/derivation | Canonical disposition | Control finding |
|---|---|---|---|
| Portal session | valid HMAC until TTL; logout timestamp; heartbeat version mismatch | `ACTIVE`, `EXPIRED`, `LOGGED_OUT` | Preserve outcome; centralize. |
| Master rows | `ACTIVE` plus broad inactive/deleted conventions | `DRAFT`, `ACTIVE`, `INACTIVE`, `SUPERSEDED` | Soft-delete conventions are inconsistent; effective dating required. |
| Sales PO | UI/manual arbitrary status; auto aggregate completion | `DRAFT`, `APPROVED`, `PARTIALLY_FULFILLED`, `FULFILLED`, `CANCELLED` | Per-line fulfillment, no free text. |
| Sales delivery | row existence/void behavior, not a robust controlled state | `DRAFT`, `REQUESTED`, `PARTIALLY_POSTED`, `POSTED`, `REVERSED`, `CANCELLED` | Warehouse result determines posting state. |
| Sales invoice/payment | derived outstanding/paid; local paid fields | invoice `DRAFT/POSTED/REVERSED`; Finance `OPEN/PARTIAL/PAID` | Commercial and Finance states stay separate. |
| Purchase receipt/AP | row existence and Finance-derived outstanding | receipt candidate/post result separated from `OPEN/PARTIAL/PAID` AP | Treatment comes from explicit mapped snapshot; unmapped legacy staging cannot advance. |
| SPK/work order | arbitrary manually supplied status and archive/finished filters | controlled `DRAFT/OPEN/IN_PROGRESS/READY_FOR_WAREHOUSE/PARTIALLY_COMPLETED/COMPLETED/CANCELLED` | Item-safe completion mandatory. |
| Production transaction | process labels Potong/Jahit/QC/Setor Gudang plus stage rejects | controlled stage entries and per-output availability; entry `POSTED/REVERSED` | Stage quantity cannot exceed item availability. |
| Production cost | provisional/final-like cost status | `PROVISIONAL`, `FINAL`, `REVALUED`; period `OPEN/CLOSED` | Never overwrite posted meaning. |
| Warehouse movement | Direction IN/OUT and active/void-like rows; contract posted on append | `PENDING`, `POSTED`, `REVERSED`, `REJECTED` | Source unique; negative rejected. |
| Opname | counted/audited evidence and variance movement | `DRAFT`, `COUNTED`, `SUBMITTED`, `APPROVED`, `POSTED`, `REVERSED` | Variance only. |
| Omni raw order | multiple channel statuses; exact transit patch `Sudah Dikirim`; completed normalization in reports | preserve raw status + effective MarketplaceStatusMap normalized `IMPORTED/READY_TO_PACK/PARTIALLY_PACKED/PACKED/SHIPPED/COMPLETED/CANCELLED/RETURNED` | Revenue requires normalized COMPLETED and valid Waktu Selesai. |
| Settlement | linked/paid-like source values and daily summary state | `IMPORTED`, `MATCHED`, `PARTIALLY_MATCHED`, `SETTLED`, `EXCEPTION`, `REVERSED`; payout separate | Settlement never creates revenue again. |
| Return registration | imported/scanned/source-status fields | `REGISTERED`, `IN_QC`, `QC_DECIDED`, `ACCEPTED`, `REJECTED`, `RECEIPT_PENDING`, `RECEIVED` | Registration is non-stock. |
| QC line | `PASS`, `PARTIAL_PASS`, `MISMATCH`, `DAMAGED`, `HOLD`, `UNKNOWN_RESI` | runtime `PASS`, `HOLD`, `REJECT`, `REWORK`; migration-only `LEGACY_UNMAPPED`; document summary derived | Unsafe legacy mapping preserves raw value, requires review and cannot post. |
| QC session | `DRAFT`, `POSTED` | `DRAFT`, `IN_PROGRESS`, `READY_TO_POST`, `POSTED`, `CLOSED` | One active session rule requires approval. |
| POS sale | append success; no explicit void/return/session states | `DRAFT`, `POSTING`, `POSTED`, `FAILED`, `CANCELLED`, `REVERSED`; return is separate | Draft may cancel; posted only reverses; original history retained. |
| POS return | absent as separate state source | `DRAFT`, `SUBMITTED`, `QC_PENDING`, `ACCEPTED`, `REJECTED`, `POSTED`, `REVERSED` | Separate document/event; stock return follows accepted policy. |
| POS cash session | absent | `OPEN`, `CLOSED` | Cash tender requires applicable OPEN session; closing records expected, actual and variance. |
| Legacy purchase staging | absent explicit mapping state | `UNMAPPED`, `MAPPED`, `REJECTED`, `ACCEPTED` | `UNMAPPED` cannot create operational or ledger records. |
| Journal | active row; editable; soft-deleted; reconciled guard partly applied | `DRAFT`, `POSTED`, `REVERSED`; reconciliation separate | Posted cannot be edited/deleted. |
| Bank transaction | `UNMATCHED`, `MATCHED`; links `ACTIVE` | `UNMATCHED`, `PARTIALLY_MATCHED`, `MATCHED`, `EXCLUDED`; link `ACTIVE/REVERSED` | One-to-many matching preserved. |
| Import/rebuild job | success/error response only; summary version/freshness | `PENDING`, `RUNNING`, `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED`, `SUPERSEDED` | Explicit job/audit state needed; no schedule evidenced. |

### 7.1 Owner-approved status decisions

- Raw marketplace status is preserved and resolved through effective-dated `MarketplaceStatusMap`; only normalized `COMPLETED` with valid Waktu Selesai is revenue-eligible.
- Operational QC exposes only PASS/HOLD/REJECT/REWORK. `LEGACY_UNMAPPED` is a migration review state, never a normal runtime result.
- Sales invoice basis is `DELIVERY` by default or `SALES_ORDER_EXCEPTION` after explicit permission/reason/audit. Proforma remains non-posting.
- Posted cost state is immutable. Open-period correction uses reversal/revaluation/adjustment; locked-period correction is posted in an authorized open period with original references.
- POS tender is explicit; cash tender requires an OPEN cash session; posted sale correction is `REVERSED`, not destructive edit.
- Free-text/arbitrary status writes in legacy Sales and Purchasing remain `UPGRADE`, not accepted state-machine behavior.

The exact formula attached to a future Production shared-cost allocation rule is a **DEFERRED IMPLEMENTATION DETAIL** and does not add a new foundation state.

## 8. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** Controlled state architecture is sufficient for Phase 1 foundation work. Phase 1 has not started.

## 9. Historical provisional phase gate (superseded)

No state enum should be implemented from this draft. First reconcile proposed states with the actual legacy state inventory, approve the unresolved transition/approval rules, and update this matrix to `ACCEPTED`.
