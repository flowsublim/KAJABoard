# KAJABoard Module Ownership

> **AUTHORITATIVE UPDATE (25 August 2026): OWNER APPROVED FOR PHASE 0 CLOSURE.** Section 9 is the actual cross-write audit. The target ownership table and section 10 decisions are normative; legacy direct writes are evidence to migrate, not ownership precedent.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — Source Freeze & Functional Audit  
**Status:** DRAFT FOR REVIEW  
**Rule:** a domain may request another domain's effect, but may not write that domain's ledger.

## 1. Ownership model

| Domain | Owns / system of record | May emit or consume | Must not do |
|---|---|---|---|
| Core / Accounts | Users, employees, roles, permissions, data scope, sessions, audit trail, idempotency records, approvals, workflow definitions, document numbering, attachments, notifications | Authorize and audit every domain action | Decide operational business outcomes or post stock/accounting |
| Organization / Master Data | Company, legal entity, business units, departments, warehouses/locations master, cost centers, purchase categories, tax profiles, system settings | Supply canonical IDs and effective configuration | Own transactional stock, cost, AR/AP, or journals |
| Partners | BusinessPartner and role snapshots for customer/vendor/subcontractor/marketplace partner | Customer/vendor eligibility and historical partner snapshot | Maintain Sales/Buying ledgers or Finance balances |
| Catalog | Product, item, SKU, material, UOM, variant relation, sales/purchase/production/inventory flags, valuation policy | Canonical Item IDs for every operational line | Store on-hand stock as a competing ledger |
| Sales | Sales order/customer PO, lines, delivery source document, invoice source, commercial terms, sales prints | Emit delivery and invoice events; read Finance AR/payment and Warehouse fulfillment | Post physical OUT; write cash/bank/payment/AR journal |
| Projects | Project/contract context, budget targets, commercial progress, project dimensions | Aggregate committed/actual/revenue/cost sources | Repost source transactions or journals |
| Incentives | Effective-dated rules, accrual candidates/ledger, beneficiaries, snapshots, approval state | Consume accepted receipt/invoice/payment/project events; emit payable/accounting event | Hardcode accounts; alter Warehouse receipt or Sales invoice |
| Purchasing | Purchase documents/lines, explicit accounting-treatment snapshot, SPK procurement/maklun, material distribution request, maklun receipt source, vendor bill/payable source, purchasing prints | Emit Warehouse receipt/issue candidates, Finance AP/asset/expense events, Production overhead snapshots | Post stock; pay vendor; write journals; infer treatment from category name |
| Production | Internal WIP stages, stable work lines, rejects, labor, direct extra cost, overhead snapshots, HPP/COGM source, handover | Request material issue; emit handover and cost/accounting candidates | Post finished-goods stock; pay wages; write journals |
| Warehouse | Sole physical StockMovement ledger, reservations/availability, posted receipt/issue/reversal, stock balance projection, inventory costing/valuation subledger, opname/adjustment, packing execution | Consume approved movement candidates; emit valuation/accounting and acceptance results | Recognize revenue, create AP/AR/payment, hardcode journal accounts |
| Quality | Inspection, PASS/HOLD/REJECT/REWORK decision, disposition source and evidence | Authorize accepted return/receipt candidates; emit financial disposition candidate | Directly change stock; post journals |
| Omnichannel | Import batches, raw orders/lines, exact SKU/variation and Store mapping snapshot, demand, completion events, settlement/payout/return/adjustment sources, reconciliation evidence, POS source | Request Warehouse packing/POS issue; emit Finance revenue/settlement/payout/return events | Post stock directly; post journal; use settlement date as revenue date |
| Finance | Sole Journal/GL, AR/AP, cash/bank, payment, marketplace AR/balance, inventory accounting, fixed assets/depreciation, period close, financial statements | Resolve events through Master COA Mapping; expose balances/read models | Change operational source history; invent stock quantities; let reports create postings |
| Tax | Tax configuration, fiscal classification/reconciliation, controlled export artifacts | Consume commercial and Finance source facts | File unattended in v1; mutate source journals through reporting |
| Analytics / Reports | Read models, KPIs, reconciliations, report definitions, snapshots/archives, drill-down | Read trusted operational and financial sources | Become a source ledger or post on page view |
| Data Exchange | Versioned templates/adapters, upload metadata, validation preview, import result/error log | Invoke authorized domain services after confirmation | Bypass domain validation or write ledgers directly |

## 2. Sole-ledger boundaries

### 2.1 Physical inventory

Only Warehouse can create, post, reverse, or value a physical movement. Candidate ownership remains with the source domain.

| Source domain and action | Candidate/request | Warehouse-owned result |
|---|---|---|
| Sales posts delivery | B2B goods-issue candidate by delivery line | Posted OUT or rejected/pending result |
| Purchasing receives inventory | Purchase receipt candidate | Posted IN |
| Purchasing sends maklun material | Subcontract material-issue candidate | Posted OUT |
| Purchasing accepts maklun output | Maklun receipt candidate | Posted IN |
| Production requests material | Internal material-issue candidate | Posted OUT |
| Production hands over finished goods | ProductionWarehouseHandover | Accepted/posted IN |
| Omnichannel packs demand | Packing issue candidate | Posted OUT |
| POS sale posts | POS issue request within atomic orchestration | Posted OUT or entire sale fails/repair state |
| Quality accepts customer/marketplace return | Return receipt candidate | Posted RETURN_IN |
| Purchasing approves supplier return | Supplier-return issue candidate | Posted OUT |
| Business unit consumes supplies | Internal-consumption candidate | Posted OUT |

No operational table's `stock`, `qty_on_hand`, or imported summary may supersede posted Warehouse movements.

### 2.2 Accounting

Only Finance resolves and posts accounting. The operational domain owns business facts and their event context.

| Source domain | Business fact | Finance-owned result |
|---|---|---|
| Sales | Invoice posted, credit note, customer return source | AR, revenue/tax/discount journal, adjustment |
| Purchasing | Inventory/asset/expense/service/maklun vendor source | AP, asset candidate/capitalization, expense/inventory accounting |
| Production | Labor, extra cost, overhead, finished-goods cost, reject | Payable/cost/WIP/inventory accounting according to mapping |
| Warehouse | Posted movement and valuation | Inventory/COGS/variance accounting event |
| Omnichannel | Completed order, settlement, payout, refund, adjustment, POS | Marketplace AR/revenue, balance/fees, bank transfer, reversal/adjustment, tender accounting |
| Incentives | Approved accrual/payment eligibility | Expense/payable and settlement through mapping |

Operational code may hardcode stable `Event_Code`, `Line_Role`, and controlled states only. Account codes/names and transactional debit/credit selection are Finance mapping responsibilities.

## 3. Master configuration ownership

| Configuration | Steward | Consumed by | Snapshot/effective-date requirement |
|---|---|---|---|
| Business Partner | Partners | Sales, Purchasing, Projects, Finance | Legal/display/terms fields needed to explain history |
| Item/SKU/Material/UOM | Catalog | All operations, Warehouse, Finance | Item identity stable; qty precision and transaction descriptions snapshot as needed |
| Purchase Category | Master Data | Purchasing, Production, Finance | Treatment, Cost Center, flags, tax/accounting key snapshot per line |
| Cost Center | Organization | Purchasing, Production, Finance, Projects | Stable ID; eligibility and display effective-dated |
| Store | Master Data | Omnichannel, Warehouse, Finance, Analytics | Stable Store ID and finance dimension snapshot |
| SKU Mapping | Master Data / Omni steward | Omnichannel | Exact marketplace/store/SKU/variation mapping and conversion snapshot per import line |
| COA | Finance steward | Finance | Active/effective account validation; historical journal lines immutable |
| COA Mapping | Finance steward | Finance resolver | Selected mapping and context snapshot on journal lines |
| Tax configuration | Tax/Finance steward | Sales, Purchasing, Omni, Finance | Rate/profile/effective date snapshot |
| Incentive rule | Incentives steward | Incentives, Finance | Rule/rate/basis/beneficiary snapshot at accrual |
| Production tariff | Production/Master steward | Production, Finance | Tariff and wage method snapshot on work line |
| Inventory valuation policy | Finance + Warehouse approval | Warehouse, Finance | Effective-dated per item/category; never silently recost history |

## 4. Decision-rights matrix

`A` = accountable/owner, `R` = performs, `C` = consulted, `I` = informed/read-only.

| Decision or record | Source operations | Warehouse | Quality | Finance | Master/Core |
|---|---:|---:|---:|---:|---:|
| Customer order validity | A/R Sales | I | — | C credit exposure | C identity/permission |
| Purchase treatment | A/R Purchasing | I | — | C mapping/accounting | C category configuration |
| QC disposition | C | C | A/R | C | I |
| Physical receipt/issue/reversal | C candidate | A/R | C acceptance | I valuation event | C permission/policy |
| Stock opname count | C | A/R | C optional | I/C variance | C approval |
| Production stage/WIP | A/R Production | I | C | I | C tariff/item |
| Journal post/reversal | C source | C valuation source | C disposition | A/R | C permission/mapping master |
| AR/AP settlement | I | — | — | A/R | C permission |
| Marketplace completion fact | A/R Omni | I | — | C/consumer | C mappings |
| Period close/reopen | I | C reconciliation | I | A/R | C approval/audit |
| Report definition | C | C | C | A Finance reports | R Analytics/Tax as applicable |

## 5. Cross-domain contracts

Every contract carries at minimum:

- stable source module/type/ID/line ID and unique source key;
- event/candidate type and schema version;
- business transaction date and posting/request timestamp;
- canonical company/business unit/project/store/partner/item/warehouse dimensions as relevant;
- qty/UOM or amount/currency with source snapshots;
- actor, approval reference, reason, attachments/evidence if applicable;
- idempotency key;
- reversal/correction reference;
- enough context for the receiving domain to validate independently.

Receiving services may reject invalid, duplicate, unauthorized, closed-period, unmapped, insufficient-stock, or illegal-state requests. A caller must not mark itself successfully posted until the owned downstream effect has a durable success result, or it must expose an explicit pending/repair state.

## 6. Forbidden cross-writes and required upgrade

| Suspected legacy pattern (source not supplied) | Target ownership correction |
|---|---|
| Sales UI/script appends stock mutation | Sales emits delivery candidate; Warehouse posts issue. |
| Purchasing script writes inventory receipt or payment ledger | Purchasing emits candidate/source; Warehouse or Finance owns effect. |
| Production `syncHppGudang` writes Warehouse HPP/stock sheet | Production emits accepted handover/cost source; Warehouse posts quantity and Finance consumes valuation. |
| Omni import reduces stock | Import creates demand only; packing/POS creates Warehouse issue. |
| Return import adds stock | QC acceptance emits return receipt candidate. |
| Settlement import creates/replaces revenue | Completion event dated `Waktu Selesai` creates revenue; settlement only clears AR and records fees/balance. |
| Report or dashboard performs sync/post | Replace with explicit command/service or scheduled reconciliation; reports remain read-only. |
| Generic delete removes posted source and downstream rows | Inactivate drafts where safe; use controlled void/reversal/adjustment after posting. |
| Category/store display text selects an account | Stable dimension → Master COA Mapping → Finance resolver. |

These are architecture conclusions from the accepted rules, not verified accusations about unavailable source code.

## 7. Role and permission boundary (minimum)

Critical actions need `Role + Action + Data Scope`, including view/post receipt, post issue, adjust stock, approve purchase, post production work, import Omni, post journal, pay, close/reopen period, manage mapping, and export financial/tax data. Sensitive overrides require a distinct permission, reason, approval, and audit record. Creator/approver/poster segregation must be finalized in the approval matrix.

## 8. UNRESOLVED ownership decisions

| ID | Question | Affected modules | Stock impact | Accounting impact | Recommended interpretation |
|---|---|---|---|---|---|
| U-OWN-001 | Who is the named business steward and approver for each master and mapping? | Master, all consumers | Bad item/warehouse policies can mispost stock. | Bad mapping can mispost accounts. | Assign owner, backup, maker/checker, and review cadence before Phase 2. |
| U-OWN-002 | Is QC mandatory before Warehouse receipt for each purchase, maklun, production, and return class? | Purchasing, Production, Quality, Warehouse | Determines permissible receipt state. | Determines accrual/valuation timing. | Configure inspection policy; Quality owns decision, Warehouse owns movement. |
| U-OWN-003 | Which service orchestrates the POS atomic boundary if Warehouse and Finance effects cannot share one database transaction in future deployment? | Omni, Warehouse, Finance | Sale/stock mismatch risk. | Sale/tender/journal mismatch risk. | In the modular monolith, use one application transaction plus durable repair/outbox semantics if asynchronous work is introduced. |
| U-OWN-004 | Who can approve negative-stock override, stock variance, prior-period correction, and period reopen? | Warehouse, Finance, Core | Quantity integrity risk. | Valuation/period integrity risk. | No override until a named approval and segregation matrix is accepted. |
| U-OWN-005 | Who owns commercial invoice status versus Finance posting/payment status labels shown in Sales? | Sales, Finance | None directly. | Duplicate/conflicting status risk. | Sales owns source lifecycle; Finance owns posting/payment lifecycle; UI composes both without copying ledgers. |

## 9. Actual legacy cross-write and ownership audit

| Legacy writer | Physical/accounting target | Actual behavior | Target owner | Required boundary |
|---|---|---|---|---|
| Sales | Warehouse `Stock_Movement` | SJ create/edit/delete appends or voids OUT rows | Warehouse | Sales delivery request -> Warehouse posted issue/reversal |
| Purchasing | Warehouse `Stock_Movement` | Purchase/maklun receipt IN and material distribution OUT | Warehouse | Treatment-aware receipt/issue candidates only |
| Production | Warehouse `Stock_Movement` | Potong OUT and Setor Gudang IN; edit void/reappend | Warehouse | Material issue and ProductionWarehouseHandover candidates |
| Return QC | Warehouse `Stock_Movement` | PASS/PARTIAL_PASS batch writes RETURN_IN directly | Warehouse | Quality acceptance -> Warehouse return receipt |
| Omni POS | Warehouse `Stock_Movement` | Stock OUT precedes POS sale rows | Warehouse | One atomic POS orchestration using Warehouse service |
| Warehouse | `Stock_Movement` | Strongest V2 contract plus manual/opname/packing writers | Warehouse | Consolidate all movement types behind one owned service |
| Sales/Purchasing | Finance `Data_Jurnal` | Read Finance payment rows by names/substrings; update local projections | Finance | Owned Finance selectors; no competing payment ledger |
| Finance | Sales/Purchasing operational Sheets | Payment functions update local paid/status cells | Finance for payment, operation for source document | Finance owns payment; projections updated through explicit result/read model |
| Finance reports | All operational Sheets | AR/AP/revenue/COGS derived directly because auto-sync is disabled | Finance | Post events to GL/AR/AP, then report from owned ledger/read models |
| Production/Warehouse | posted movement cost fields | HPP/cost close overwrites cost snapshots | Warehouse valuation + Finance correction | Immutable posting; revaluation/adjustment with source trace |

### 9.1 Ownership findings

1. The legacy package does not enforce Warehouse or Finance sole ownership globally even though the Warehouse V2 contract has useful controls.
2. `Stock_Movement` is the only evidenced physical quantity source, but five non-Warehouse modules write it directly.
3. Finance is a mixed manual journal plus source-reader/report system, not a complete posted GL. `FIN_syncSalesInvoiceJournals`, `FIN_syncPurchasingPayableJournals`, and `FIN_syncOmniFinanceJournals` are explicitly disabled/source-reader-only.
4. No operational category/name inference may cross the Finance resolver boundary in KAJABoard.
5. Report/UI projection cells are not ownership; they may be rebuilt from the owner ledger.

## 10. Owner-approved ownership decisions

| Capability | Operational owner | Ledger/effect owner | Binding rule |
|---|---|---|---|
| Marketplace completion/status mapping | Omnichannel | Finance for revenue/AR | Omni supplies valid Waktu Selesai, normalized COMPLETED and Store context; Finance uniquely recognizes source. |
| Sales direct-SO invoice exception | Sales | Finance for AR | Sales permission/reason/audit controls exception; no stock event; proforma remains non-posting. |
| Legacy QC migration | Quality | Warehouse only for accepted receipt | Quality owns PASS/HOLD/REJECT/REWORK and LEGACY_UNMAPPED review; only PASS accepted qty requests stock. |
| Legacy purchase-category mapping | Purchasing/Master Data | Warehouse/Finance consume treatment | Explicit five-treatment mapping is required before staging acceptance; no name inference. |
| Production shared-cost allocation | Production owns allocation context/snapshot | Finance owns accounting; Warehouse owns valuation movement | Exact formula is deferred to Production/HPP gate; item-specific costs cannot be pooled away. |
| Posted cost correction | Warehouse valuation + Finance accounting | Each owner posts its controlled correction | Never overwrite history; locked-period correction posts in an authorized open period with original references. |
| POS checkout and cash session | POS owns sale, tender capture and OPEN/CLOSED operational session | Warehouse owns stock/COGS source; Finance owns revenue/payment/cash/variance accounting | One atomic/idempotent checkout; posted correction by reversal; return is separate. |

Detailed named role assignments, thresholds and data scopes are implementation configuration under the established Core permission architecture. They must be approved before the relevant action is enabled, but do not block Phase 1 foundation work.

## 11. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** Ownership boundaries are sufficient for Phase 1 foundation architecture. Phase 1 has not started.

## 12. Historical provisional phase gate (superseded)

Ownership rules are sufficiently explicit for review, but not for Phase 1 acceptance until business stewards, approval thresholds, data scopes, QC routing, and the missing legacy cross-write inventory are confirmed.
