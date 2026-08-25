# KAJABoard Business Process Map

> **AUTHORITATIVE UPDATE (25 August 2026): ACTUAL SMB GAS EVIDENCE AUDITED AND OWNER APPROVED.** Source-absence statements below are historical. Sections 17-18 contain the accepted process decisions and Phase 0 closure.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — Source Freeze & Functional Audit  
**Status:** DRAFT — REVIEW BLOCKED BY MISSING LEGACY SOURCE  
**Baseline date:** 25 August 2026  
**Company:** PT KAJA VASTRALOKA KREASINDO

## 1. Purpose and evidence boundary

This document maps the business outcomes that KAJABoard must preserve. It is a functional map, not a Django design or a promise to preserve GAS endpoints, Sheets, or legacy screens.

Evidence used:

1. `AGENTS.md` (SHA-256 `D89650E9A9D559B2EA79046297A6516D42BC68DC6F4819EEBF9F91225CD2002A`);
2. `KAJABoard_Project_Plan_FINAL_v2.0.md` (SHA-256 `249752A0F05E860D305B284A03102FB93BFEB059347A910F0C2560C386709F8F`);
3. repository `README.md` (SHA-256 `DBC9971EC515C5B5345F1D8381B0AC52E455B0891F9C4C9694D4688A7A5C4978`);
4. `legacy/smb_gas/README.md` (SHA-256 `6FBF59E98A4890BAB871C733A69614171882711A6A26749C19B086C01CF3EFA6`).

The legacy module directories contain only `.gitkeep` files. No GAS, HTML, JavaScript, CSS, print template, accepted patch, Sheet schema, sample workbook, or test fixture was available. Consequently, the process map below is authoritative only to the extent defined by the locked Project Plan and `AGENTS.md`; it is not a source-code-verified freeze of actual SMB behavior.

## 2. Cross-domain invariants

| Invariant | Required outcome |
|---|---|
| Functional parity | Preserve accepted workflow, validation, calculation, lineage, stock/accounting effects, reconciliation, exceptions, and needed prints/reports; endpoint parity is not required. |
| Physical stock | Warehouse alone posts physical quantity movements. Other domains issue candidates or requests. |
| Accounting | Finance alone posts journals, maintains AR/AP, cash/bank, marketplace balances, fixed assets, depreciation, and closing. |
| Account resolution | `Business Event → Accounting Context → Master COA Mapping → Finance Resolver → Journal`; no transactional COA hardcode. |
| Historical meaning | Stable IDs plus effective dating and/or transaction snapshots prevent later master changes from rewriting history. |
| Critical writes | Atomic, idempotent, permission-checked, audited, source-linked, and state-controlled. |
| Corrections | Posted records use reversal/adjustment; no silent deletion or overwrite. |
| Reports | Read trusted ledgers/read models and drill down to source; viewing a report never creates a posting. |

## 3. Level-0 operating model

```text
Master configuration and organization
    ↓
Commercial demand (B2B / marketplace / POS / project)
    ↓
Procurement and production planning (purchase / internal / maklun)
    ↓
Quality decision and Warehouse posting
    ↓
Delivery, completion, invoicing, settlement, payment
    ↓
Finance ledgers, reconciliation, closing, reporting, analytics
```

Master Data supplies canonical partners, items, warehouses, cost centers, stores, purchase categories, tax profiles, COA, and effective-dated mappings. It configures behavior but does not own operational ledgers.

## 4. B2B sales, project, delivery, invoice, and collection

```text
Customer / Project
→ Sales Order or customer PO
→ optional procurement / internal production / maklun
→ stock-ready signal
→ partial Delivery / Surat Jalan POST request
→ Warehouse Goods Issue POSTED
→ Invoice POSTED
→ Finance AR and journal
→ Finance customer payment and settlement
→ SOA / Customer 360 / project profitability
```

| Step | Business control | Owner and hand-off |
|---|---|---|
| Capture order | Unique document; active customer/item; qty > 0; price/tax/discount/charge snapshots; stable line IDs. | Sales owns order and lines. |
| Credit/project context | Credit warning/hold and explicit override; optional project, owner, deadline, budget, and margin target. | Sales/Projects read Finance exposure. |
| Fulfill partially | User selects lines and quantities; each delivery qty ≤ line remaining qty; multiple deliveries per order allowed. | Sales posts delivery source; Warehouse validates/reserves/posts OUT. |
| Correct delivery | Posted stock is never erased; a controlled reversal corrects the Warehouse movement and fulfillment. | Sales requests; Warehouse reverses its movement. |
| Invoice | Traceable to order/delivery as defined; total snapshots qty/price/tax/discount. | Sales owns invoice source; Finance consumes `SALES_INVOICE_POSTED`. |
| Collect | Sales displays payment/outstanding/overdue but does not write payment or cash/bank. | Finance owns AR and payment. |
| Print/report | Proforma, invoice, Surat Jalan, shipping label, SOA; letterhead comes from master. | Sales renders source documents; SOA reads Finance. |

## 5. Purchasing and procurement routing

```text
Purchase requirement / approved commitment
→ purchase line with explicit AccountingTreatment snapshot
├─ INVENTORY → Warehouse Receipt Candidate → Warehouse IN → Finance valuation/AP
├─ ASSET → Finance Asset Acquisition Candidate + AP (no stock)
├─ EXPENSE → Finance expense/AP (Cost Center required)
├─ SERVICE → Finance service/AP (Cost Center required)
└─ MAKLUN → SPK/subcontract flow → accepted output → Warehouse IN + Finance AP/cost
```

Every purchase line snapshots Purchase Category, `AccountingTreatment`, Cost Center, inventory/asset context, production snapshot flag, tax profile, and optional project. Category-name substring matching is prohibited.

Production overhead eligibility is exactly:

```text
AccountingTreatment in {EXPENSE, SERVICE}
AND production-eligible Cost Center
AND SnapshotProduction = TRUE
```

Inventory, raw materials, accessories, packaging inventory, finished goods, maklun principal cost, machines, equipment, and other assets cannot become production overhead through naming heuristics.

Purchasing creates vendor bill/payable sources but never writes payment, cash, or bank. Payment of an accrued payable settles the liability and must not create the expense again.

## 6. SPK, internal production, and HPP

```text
Approved SPK with explicit material-output pairs
→ material request
→ Warehouse material issue
→ CUT
→ SEW
→ QC / PACKING
→ ProductionWarehouseHandover (partial allowed)
→ Warehouse acceptance and finished-goods receipt
→ auditable HPP/COGM + CPO fee candidate
```

Per output item, not per aggregate SPK:

```text
Available Sewing   = Cut - Sew - Reject Cut
Available QC       = Sew - QC - Reject Sew
Available Warehouse= QC - Handover - Reject QC
```

Each posted production line has a stable line ID. Multi-item entry is allowed, but editing or correcting one line must not delete siblings. SPK may close only when every output individually satisfies completion and all intermediate WIP is zero; surplus on one item cannot conceal shortage on another.

HPP can include material cost snapshot, direct labor tariff snapshot, eligible direct extra cost, eligible production overhead snapshot, subcontract cost, and other approved production cost. Allocation is configurable, auditable, and deterministic. Opening a report cannot recalculate or post a different HPP.

## 7. External production / maklun

```text
SPK external + vendor + output targets
→ material-send request
→ Warehouse material OUT
→ vendor WIP trace
→ partial receipt by output
→ QC/acceptance where required
→ Warehouse maklun receipt IN
→ specific/shared service allocation
→ Finance maklun payable
```

Material sent cannot exceed authorized/available quantity. Receipts support finished goods, variant-specific service, and general/pukul-rata service. Cost includes supplied material value, specific service, allocated shared service, other eligible costs, and accepted quantity. Purchasing never writes the actual stock ledger.

## 8. Warehouse and inventory

Warehouse maintains the only physical stock ledger. Only `POSTED`, non-reversed movements affect balance.

| Direction | Accepted sources |
|---|---|
| IN | Purchase inventory receipt; production finished-goods receipt; maklun receipt; QC-accepted customer/marketplace return; opname gain; approved positive adjustment; opening stock. |
| OUT | B2B delivery; marketplace packing; POS sale; internal production material issue; maklun material send; supplier return; internal consumption; opname loss; approved negative adjustment. |

Controls:

- unique source key prevents double-click, retry, and reimport duplicates;
- no negative stock by default; any future override requires explicit policy, permission, reason, and audit;
- stock opname compares system vs counted quantity and posts only the approved variance;
- costing is transaction-order-aware, with running weighted average where configured;
- reversal is controlled and corrects both quantity and valuation;
- line-level source, warehouse, item, dates, actor, cost, and reversal lineage remain traceable.

## 9. Quality and returns

```text
Return / inspection source
→ QC record
→ PASS | HOLD | REJECT | REWORK
├─ PASS/accepted → Warehouse RETURN_IN candidate → POSTED IN
├─ HOLD → no final stock effect
├─ REJECT → disposal/financial treatment to be explicitly approved
└─ REWORK → rework flow, then reinspection/final decision
→ Finance credit/refund/adjustment event as applicable
→ reconciliation
```

Importing or registering a return never changes physical stock. QC is also available for supplier receipt, maklun receipt, internal finished goods, and random inspection.

## 10. Omnichannel order-to-cash

```text
BigSeller XLSX/CSV import batch
→ validate Store Mapping + exact SKU/Variation Mapping
→ persist raw, conversion, and internal quantities
→ operational demand dated by Waktu Pesanan Dibuat
→ Warehouse queue
→ pack/partial pack
→ Warehouse stock OUT
→ completed event dated by Waktu Selesai
→ Finance marketplace AR + revenue
→ settlement import (fees + balance + AR clearing)
→ payout (marketplace balance → bank)
→ return/refund/adjustment as immutable follow-up
→ reconciliation and store profitability
```

Order-line identity is `Order Number + SKU + Variation`. A controlled fallback may exist for blank variation, but cannot merge distinct variants. The transaction stores `Marketplace_Qty`, `Conversion_Qty`, and calculated `Internal_Qty`; later mapping changes do not rewrite imported history.

Date semantics are locked:

| Date | Meaning |
|---|---|
| `Waktu Pesanan Dibuat` | Operational volume, demand, warehouse queue, and order-day analytics. |
| `Waktu Selesai` | Revenue and marketplace receivable recognition period. |
| Settlement date | Fee/clearing event date; never the revenue date. |
| Payout date | Marketplace balance to bank transfer date. |

Completed-order accounting concept is Dr Marketplace Receivable–Store / Cr Marketplace Revenue–Store. Settlement is a separate event that clears receivable into mapped marketplace balance and fee/adjustment roles. Payout moves mapped marketplace balance to mapped bank. Exact accounts always come from Master COA Mapping.

Return/refund never erases original completed revenue. It produces a follow-up financial event and physical return occurs only after QC acceptance.

## 11. Marketplace packing and shortage

Order import creates demand, not stock OUT. Warehouse may pack partially only when pack qty is within remaining demand and available stock. Grouped/subcategory demand must be allocated to actual internal item/variant before posting. Shortage creates an actionable backorder/procurement signal; it cannot be hidden by a generic SKU or summary quantity.

## 12. POS

```text
User selects active internal Item
→ qty > 0 + price/payment snapshots
→ validate stock
→ create POS sale
→ immediate idempotent Warehouse issue
→ COGS from inventory costing
→ Finance revenue/payment event
→ atomic commit or explicit repair state
```

POS cannot accept only a subcategory or unmapped external label. A failed stock posting cannot leave an apparently successful sale.

## 13. Finance, reconciliation, closing, and reporting

```text
Operational source event
→ accounting context
→ effective Master COA Mapping resolution
→ balanced journal candidate
→ period/source/permission validation
→ immutable POSTED journal
→ GL + subledgers
→ reconciliation
→ period close
→ drillable statements/archive
```

Finance owns AR, AP, cash, bank, marketplace AR/balance, inventory accounting, fixed assets, depreciation, and closing. A unique source posting, Debit = Credit, active/effective account validation, mapping snapshot, actor, analytical dimensions, and source lineage are mandatory.

Reconciliations include AR/AP controls, marketplace AR and balance, bank, Inventory GL vs valuation, stock ledger vs balance, purchase receipts, handovers, packing, and returns. Period states progress through `OPEN → SOFT_CLOSE → FINANCE_REVIEW → CLOSED → TAX_FILED → LOCKED`; reopening is restricted, approved, reasoned, and audited.

## 14. Import, migration, and cutover

All imports use versioned templates/adapters:

```text
Upload → parse → validate → preview → confirm → idempotent batch
→ results/error log → reconciliation
```

Cutover moves active master/configuration, opening balances, stock qty/value, AR/AP, marketplace controls, fixed assets, open projects/orders/SPKs/WIP and other open commitments. SMB becomes read-only only after trial balance, stock, AR/AP, cash/bank, marketplace, fixed-asset NBV, commitments, and tax balances reconcile.

## 15. Capability coverage by target phase

| Capability | Phase after review | Current Phase 0 result |
|---|---:|---|
| Core controls and master configuration | 1–2 | Business controls identified; implementation forbidden now. |
| B2B Sales / Project | 3 | Flow and boundaries mapped. |
| Purchasing / SPK / Maklun | 4 | Routing and ownership mapped. |
| Internal Production / HPP | 5 | Item-safe calculations and handover mapped. |
| Warehouse / QC / CPO | 6 | Sole-ledger and acceptance rules mapped. |
| Omnichannel / POS | 7 | date, identity, quantity, stock, and settlement rules mapped. |
| Finance | 8 | event/mapping/subledger controls mapped. |
| Profitability / incentive / budget | 9 | source outcomes mapped at plan level. |
| Reports / tax / closing | 10–11 | read-only reporting and closing controls mapped. |
| Migration / UAT / go-live | 12 | reconciliation scope mapped. |

## 16. UNRESOLVED process decisions

| ID | Question / source conflict | Affected modules | Stock impact | Accounting impact | Recommended interpretation pending approval |
|---|---|---|---|---|---|
| U-001 | Actual SMB source, accepted patches, UI files, Sheet schemas, and fixtures are absent. Are there additional workflows or exceptions beyond Project Plan §40? | All | Unknown sources may be missing. | Unknown events/mappings may be missing. | Obtain a read-only, hashable source freeze before accepting Phase 0. |
| U-002 | Exact B2B invoice basis is not locked: ordered qty, delivered qty, milestone, or approved exception. | Sales, Warehouse, Finance | May affect delivery linkage only. | Determines AR/revenue amount and timing. | Default to invoiceable source lines with explicit lineage; business owner must define allowed bases. |
| U-003 | QC checkpoints are listed broadly, but whether purchase/maklun/finished-goods receipt requires QC before Warehouse posting is not defined per item/category. | Purchasing, Production, Quality, Warehouse | Determines when IN is permitted. | May affect accrual/valuation timing. | Configure inspection policy by item/category/source; do not assume universal or optional QC. |
| U-004 | Reject/disposal/rework valuation and accounting are not specified. | Quality, Production, Warehouse, Finance | OUT/transfer/rework movements are unclear. | Loss, WIP, recovery, and liability treatment unclear. | Define approved disposition matrix before transaction design. |
| U-005 | Weighted-average scope and backdated transaction/revaluation policy are not fully defined. | Warehouse, Finance | Quantity unaffected; valuation sequence affected. | Inventory/COGS and closed-period correction affected. | Lock per-item valuation policy, backdate rule, and controlled revaluation behavior. |
| U-006 | Eligible marketplace completed statuses and gross-revenue subtotal/tax/discount definition are not enumerated. | Omnichannel, Finance, Tax | None directly. | Revenue/AR recognition completeness and amount. | Create channel-specific status and amount mapping master before import implementation. |
| U-007 | Settlement fee columns, sign conventions, partial/split matching tolerance, and payout identifiers are not supplied. | Omnichannel, Finance | None. | Clearing, fees, adjustments, and balance reconciliation. | Freeze representative files and approve normalized role/sign/tolerance rules. |
| U-008 | POS payment methods, tax, discount, return/void, offline/retry, and cash-session controls are not defined. | Omnichannel, Warehouse, Finance, Tax | Reversal and return flows affected. | Revenue, tender, cash, and tax treatment affected. | Define POS control matrix while retaining strict Item and atomic issue invariants. |
| U-009 | Production overhead allocation basis and period/SPK eligibility window are only described as configurable. | Purchasing, Production, Finance | None directly. | HPP and payable/expense allocation. | Approve allocation methods, rounding, source cutoffs, and reversal propagation. |
| U-010 | SPK final equality formula names aggregate Reject Qty, while stage-specific rejects exist; treatment of rework/recovery/scrap is not explicit. | Production, Quality, Warehouse, Finance | Finished and scrap quantities affected. | HPP/yield loss affected. | Define item-level quantity conservation using explicit reject/disposition buckets. |
| U-011 | Exact document numbering, approval thresholds, role/data scopes, and segregation of duties are not provided. | Core and all transactions | Unauthorized movement risk. | Unauthorized posting/close risk. | Capture current approval matrix and document series before Phase 1 acceptance. |
| U-012 | Tax behavior is intentionally high-level and must be verified at implementation date. | Sales, Purchasing, Finance, Tax | None directly. | Tax lines, reporting, fiscal depreciation. | Treat tax as unresolved configuration; verify regulation and obtain finance approval in Phase 10. |

## 17. Actual-evidence process delta

| Flow | Source-confirmed behavior | Required KAJABoard correction |
|---|---|---|
| Portal -> modules | HMAC passport, 6-hour session, heartbeat refresh, module-role checks and logout stamp | Central Core auth/permission service; environment secret; action + data scope |
| Sales PO -> SJ -> invoice -> SOA | Full flow and partial-delivery UI/prints exist; SJ writes Warehouse sheet; Finance payments are read back | Default invoice basis is posted delivered-not-invoiced qty. Controlled direct-SO invoice requires permission/reason/audit and no stock. Proforma is non-posting/no AR. |
| Purchase -> receipt/AP | Purchase save may write stock and Finance derives AP; treatment inferred by category | Explicit legacy mapping to INVENTORY/ASSET/EXPENSE/SERVICE/MAKLUN; unmapped staging blocked; Warehouse receipt candidate; Finance AP event |
| SPK -> Kirim Bahan -> Production/Maklun -> receipt | Material-output pairing, distribution, FULL_ORDER/CMT and external Production progress exist | Stable lines; item-safe close; Warehouse movement ownership; eligible cost roles |
| Production stages -> handover | Cut/Sew/QC/Handover with stage rejects and item-safe availability exists | Handover candidate only; item-safe close; HPP eligibility requires treatment + eligible Cost Center + SnapshotProduction; allocation snapshot required |
| Omni import -> Warehouse pack | Order+SKU+Variation key, conversion mapping, summary/raw fallback and exact shipped patch exist | Preserve qty triplet; stable mapping snapshot; Warehouse-only OUT |
| Completed order -> settlement -> payout | Source readers separate sale and settlement conceptually | Valid Waktu Selesai + MarketplaceStatusMap normalized COMPLETED + unique source + Store/accounting map; Finance posts AR/revenue, settlement, then payout |
| Return import -> QC -> return receipt | Import/scan does not post stock; accepted batch posts RETURN_IN | Runtime PASS/HOLD/REJECT/REWORK; unsafe legacy values become review-only LEGACY_UNMAPPED; only accepted PASS qty reaches Warehouse |
| POS | Qty/price/stock checks, sale rows and COGS snapshot exist | Strict Item; explicit tender; atomic/idempotent stock + COGS + revenue/payment; reversal/return documents; OPEN/CLOSED cash session with variance |
| Finance -> reports/reconciliation | Manual entries, AR/AP payments, bank import/multi-match and financial prints exist; latest auto-sync is reader-only | Posted immutable GL is truth; Master COA Mapping; reports never substitute for posting |

### 17.1 Source-confirmed exception paths

- Edit/delete commonly voids and re-appends movements or rebuilds Sheet rows. The business correction capability remains, but target correction is reversal/adjustment with audit.
- Warehouse raw fallback protects Omni summary availability; target read caches require version/freshness signals and must remain non-ledger.
- Finance bank PDF import refuses writes unless transaction counts, CR/DB totals and closing balance reconcile; preserve this fail-closed behavior.
- Unknown return resi can be held/quarantined; it must never create stock until an accepted matched line exists.
- No scheduled trigger is present in the package; every rebuild/sync must be designed as an explicit job before any schedule is approved.

### 17.2 Owner-approved process closure

The eight former process blockers are resolved by the owner-approved decisions recorded in U-EA-001 through U-EA-008. Posted quantity/accounting history is immutable; corrections use traceable reversal/revaluation/adjustment, with locked-period corrections posted in an authorized open period. The current legacy package is the official hashed baseline.

The exact formula for allocating shared SPK/production cost is a **DEFERRED IMPLEMENTATION DETAIL** for the Production/HPP gate. It must be documented, versioned, and snapshotted before that feature posts cost, but it does not block Phase 1 foundation architecture.

## 18. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** Phase 1 is ready for a separate explicit start instruction and has not started.

## 19. Historical provisional phase gate (superseded)

This process map is ready for stakeholder review but cannot satisfy the Phase 0 source-freeze gate by itself. Phase 1 must not begin until the missing legacy baseline is supplied, delta-audited against these flows, all additional functions/use cases are classified, and business owners disposition the unresolved items that affect transaction semantics.
