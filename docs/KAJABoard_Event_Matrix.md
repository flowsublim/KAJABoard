# KAJABoard Event Matrix

> **AUTHORITATIVE UPDATE (25 August 2026): OWNER APPROVED FOR PHASE 0 CLOSURE.** Section 11 maps actual legacy writes to owned events; section 12 records the resolved event contracts. Legacy direct Sheet writes are evidence of triggers, not target ownership.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — functional contracts  
**Status:** DRAFT FOR REVIEW — event names may be refined, coverage may not shrink  
**Accounting rule:** exact accounts are always resolved by Finance from effective Master COA Mapping.

## 1. Event contract standard

Every critical event/candidate includes `Event_Code`, schema version, legal entity, source module/type/ID/line ID/key, transaction date, canonical dimensions, qty/UOM and/or amount/currency, source snapshots, actor, approval reference, idempotency key, and reversal/correlation reference where applicable.

Three effects must remain distinct:

1. an operational source document or state change;
2. a Warehouse candidate/result that can change physical quantity only when Warehouse posts it;
3. a Finance business event/result that can change accounting only when Finance posts it.

Delivery, distributed transaction, or outbox mechanics are Phase 1+ technical decisions. The modular monolith may call services atomically, but ownership and unique source posting still apply.

## 2. Sales and project events

| Event / candidate | Producer → consumer | Trigger and minimum context | Physical stock effect | Finance effect / line-role intent | Idempotency / target outcome |
|---|---|---|---|---|---|
| `SALES_ORDER_APPROVED` | Sales → Projects/Purchasing/Production/Warehouse read models | Approved order; customer/project, stable lines, item/qty/terms snapshots | None; may create demand/reservation only | Committed/revenue forecast only; no journal by viewing/approval unless separately approved policy | `SalesOrder_ID + approval version`; order `APPROVED` |
| `SALES_DELIVERY_REQUESTED` | Sales → Warehouse | Delivery post request; source order/delivery lines, qty ≤ remaining, warehouse/date | Candidate only | None until owned stock/COGS policy event | Unique per delivery line/effect; Warehouse `PENDING` |
| `SALES_DELIVERY_POSTED` | Warehouse result → Sales/Finance | Posted B2B issue with movement IDs, qty/value/date | Warehouse OUT | Representative event may drive inventory/COGS mapping; no Sales hardcode | Warehouse movement source key; delivery fulfillment updates |
| `SALES_DELIVERY_REVERSED` | Warehouse → Sales/Finance | Controlled reversal of posted delivery issue | Linked compensating stock effect | Linked accounting reversal/adjustment | Original movement + reversal version |
| `SALES_INVOICE_POSTED` | Sales → Finance | Posted invoice source with customer, due date, line amounts/tax/discount/project | None | AR plus mapped revenue/tax/discount roles | Invoice source key unique; Finance journal and AR item |
| `SALES_CREDIT_NOTE` | Sales → Finance | Approved credit/correction linked to original invoice/return | None directly; return stock is separate | Mapped AR/revenue/tax adjustment; original remains | Credit note source key; immutable follow-up |
| `SALES_RETURN_ACCEPTED` | Quality/Sales → Warehouse and Finance | Final accepted return, original delivery/invoice, Item/qty/value | Warehouse return-receipt candidate; only POSTED IN changes stock | Mapped credit/refund and inventory/COGS adjustment as applicable | Inspection/disposition source key |
| `CUSTOMER_PAYMENT` | Finance command → Finance | Approved payment, customer, tender/bank, allocations | None | Clear AR to mapped cash/bank; no new revenue | Payment external/internal source key |
| `PROJECT_CLOSED` | Projects → Incentives/Analytics | All approved closure gates met; cost/revenue snapshots | None | No automatic posting unless an approved mapped event | Project + closure version |

## 3. Purchasing and subcontract events

| Event / candidate | Producer → consumer | Trigger and minimum context | Physical stock effect | Finance effect / line-role intent | Idempotency / target outcome |
|---|---|---|---|---|---|
| `PURCH_INVENTORY_RECEIPT_REQUESTED` | Purchasing → Warehouse | Accepted/authorized `INVENTORY` line; Item/warehouse/qty/value source | Candidate only | None until receipt result/vendor event | Purchase receipt line source key |
| `PURCH_INVENTORY_PURCHASE` | Purchasing/Warehouse result → Finance | Vendor source plus posted/accepted inventory receipt and valuation context | Already Warehouse IN | Mapped inventory/AP/tax/charge roles | Purchase line/bill/receipt policy-specific unique source |
| `PURCH_ASSET_PURCHASE` | Purchasing → Finance | `ASSET` line; class/value/date/Cost Center/project; no Item stock route | None, always | Mapped fixed-asset acquisition/AP/tax roles | Vendor source line key; asset candidate/register |
| `PURCH_EXPENSE_PURCHASE` | Purchasing → Finance | `EXPENSE`; Cost Center required; tax/project snapshots | None | Mapped expense/AP/tax roles | Vendor source line key |
| `PURCH_SERVICE_PURCHASE` | Purchasing → Finance | `SERVICE`; Cost Center required | None | Mapped service expense/AP/tax roles | Vendor source line key |
| `PURCH_MAKLUN_PAYABLE` | Purchasing → Finance | Approved vendor service/output cost tied to SPK/receipt | None by this event | Mapped subcontract cost/AP/tax roles | Maklun receipt/vendor source key |
| `PURCH_PRODUCTION_OVERHEAD` | Purchasing/Finance → Production and Finance | Posted EXPENSE/SERVICE + eligible production Cost Center + flag true | None | Original expense/AP is posted once; source becomes eligible HPP snapshot, not another expense on payment | Original source line key; snapshot unique |
| `PURCH_WAREHOUSE_OVERHEAD` | Purchasing → Finance | Eligible Warehouse Cost Center expense/service | None | Mapped warehouse expense/AP | Source line key |
| `PURCH_OFFICE_OVERHEAD` | Purchasing → Finance | Office/general expense/service | None | Mapped office/general expense/AP; excluded from Production HPP | Source line key |
| `MATERIAL_ISSUE_INTERNAL_REQUESTED` | Production → Warehouse | Approved SPK material requirement and available allowance | Candidate only | None until posted issue event | SPK/material/output/request key |
| `MATERIAL_SEND_MAKLUN_REQUESTED` | Purchasing → Warehouse | Approved SPK/vendor material send; qty within authorization | Candidate only | None until posted issue/value event | MaterialSendLine source key |
| `MAKLUN_RECEIPT_REQUESTED` | Purchasing/Quality → Warehouse | Accepted output per SPK/output/vendor, partial allowed | Candidate only | Payable handled separately from physical receipt as configured | MaklunReceiptLine + acceptance version |
| `SUPPLIER_RETURN_REQUESTED` | Purchasing/Quality → Warehouse | Approved return to vendor; original purchase, Item/qty/reason | Candidate only | Debit/credit source emitted separately/on result | SupplierReturnLine source key |
| `SUPPLIER_RETURN` | Warehouse/Purchasing → Finance | Posted supplier-return OUT with value and vendor source | Warehouse OUT | Mapped inventory/AP or vendor credit roles | Warehouse movement source key |
| `VENDOR_PAYMENT` | Finance command → Finance | Approved payment and AP allocations | None | Clear AP to mapped cash/bank; never recreate expense | Payment source key |

## 4. Production and Warehouse events

| Event / candidate | Producer → consumer | Trigger and minimum context | Physical stock effect | Finance effect / line-role intent | Idempotency / target outcome |
|---|---|---|---|---|---|
| `PROD_WORK_POSTED` | Production → Production read model | Valid item-level stage entry with stable line, qty within WIP | None | Labor/cost events are separate or correlated | WorkLine idempotency key; WIP stage advances |
| `PROD_DIRECT_LABOR` | Production → Finance/HPP | Posted work line with PIC/process/qty/tariff snapshot | None | Mapped direct labor cost/payable; included once in HPP | WorkLine + cost role unique |
| `PROD_EXTRA_OPERATOR_COST` | Production → Finance/HPP | Approved direct extra cost/payee/SPK/output | None | Mapped cost/payable; settlement later clears liability only | ExtraCost source key |
| `PROD_OVERHEAD` | Production overhead snapshot → HPP/Finance read | Eligible posted, non-reversed source allocated under approved rule | None | Cost already represented by original posting; allocation supports HPP and any approved WIP transfer, not duplicate expense | Source + allocation target/version unique |
| `PROD_REJECT` | Production/Quality → Warehouse/Finance as disposition requires | Stage-specific reject with Item/qty/reason/disposition | No movement until approved Warehouse disposition | Mapped WIP/loss/recovery role when disposition defined | RejectLine + disposition version |
| `PROD_HANDOVER_READY` | Production → Warehouse | Partial/full handover; Item qty ≤ available Warehouse WIP, cost snapshot | Candidate only | None until accepted receipt | HandoverLine source key; `READY_FOR_GUDANG` concept |
| `PROD_FINISHED_GOODS_ACCEPTED` | Warehouse → Production/Finance/Incentives | Accepted and posted finished-goods receipt | Warehouse IN | Mapped WIP/finished-goods inventory roles; triggers CPO fee basis | Posted receipt movement key |
| `STOCK_RECEIPT` | Warehouse → Finance/source domain | Any posted, non-reversed IN with valuation/source | Warehouse IN | Mapped valuation/accounting by source context | Source key unique at DB; movement `POSTED` |
| `STOCK_ISSUE` | Warehouse → Finance/source domain | Any posted, non-reversed OUT with valuation/source | Warehouse OUT | Mapped inventory/COGS/WIP/expense role by source | Source key unique |
| `STOCK_MOVEMENT_REVERSED` | Warehouse → Finance/source domain | Authorized correction linked to original movement | Compensating effect; original retained | Finance reversal/adjustment linked to original | Original + reversal sequence |
| `STOCK_OPNAME_GAIN` | Warehouse → Finance | Approved counted variance > 0 | Warehouse IN variance | Mapped inventory variance gain role | OpnameLine adjustment source key |
| `STOCK_OPNAME_LOSS` | Warehouse → Finance | Approved counted variance < 0 | Warehouse OUT variance | Mapped inventory variance loss role | OpnameLine adjustment source key |
| `STOCK_ADJUSTMENT` | Warehouse → Finance | Approved positive/negative adjustment, reason and valuation | Warehouse IN/OUT | Mapped adjustment role | Adjustment source key |
| `INTERNAL_CONSUMPTION` | Warehouse/source unit → Finance | Posted use of box/label/material with purpose and Cost Center/project | Warehouse OUT | Mapped expense/consumption role | Consumption line movement key |

## 5. Quality and return events

| Event / candidate | Producer → consumer | Trigger and minimum context | Physical stock effect | Finance effect / line-role intent | Idempotency / target outcome |
|---|---|---|---|---|---|
| `QC_INSPECTION_FINALIZED` | Quality → source domain | Inspected/accepted/rejected/rework/hold quantities and evidence | None by itself | None by itself | Inspection decision version unique |
| `QC_RETURN_ACCEPTED` | Quality → Warehouse | Final PASS/accepted customer/marketplace return | Warehouse RETURN_IN candidate | Finance return event is correlated but separately owned | Inspection/disposition key |
| `QC_RECEIPT_ACCEPTED` | Quality → Warehouse | Final accepted purchase/maklun/production receipt where policy requires | Warehouse receipt candidate | Accounting consumes posted result/source | Inspection/disposition key |
| `QC_REJECT_DISPOSITION` | Quality → Warehouse/Finance | Approved reject/disposal/return/rework route | Only subsequent owned movement changes stock | Mapped loss/recovery/vendor/customer adjustment after rule approval | Disposition action key |

## 6. Omnichannel and POS events

| Event / candidate | Producer → consumer | Trigger and minimum context | Physical stock effect | Finance effect / line-role intent | Idempotency / target outcome |
|---|---|---|---|---|---|
| `OMNI_ORDER_IMPORTED` | Omnichannel → demand/read models | Valid import line; Store + order + SKU + variation; raw/conversion/internal qty snapshots | None | None | Batch + exact order-line key; reimport updates only under controlled rule |
| `OMNI_DEMAND_READY` | Omnichannel → Warehouse | Mapped internal Item demand dated by order-created time | Reservation/queue only | None | One active demand per imported order line/version |
| `OMNI_PACKING_REQUESTED` | Omnichannel/Warehouse UI → Warehouse | Actual Item/variant, pack qty ≤ demand and stock; partial allowed | Candidate only | None | PackingLine source key |
| `OMNI_PACKING_POSTED` | Warehouse → Omnichannel/Finance | Posted issue linked to Store/order/Item/date | Warehouse OUT | Inventory/COGS accounting candidate by mapped event/context | Movement source key |
| `OMNI_ORDER_COMPLETED` | Omnichannel → Finance | Eligible final status and valid `Waktu Selesai`; gross basis by order; Store | None | Dr mapped Marketplace Receivable–Store; Cr mapped Marketplace Revenue–Store plus configured roles | Recommended `OMNI_REV\|Store_ID\|Order_Number`; one revenue event |
| `OMNI_SETTLEMENT` | Omnichannel → Finance | Valid aggregated Store + Order settlement, structured fees/net/adjustments | None | Clear mapped marketplace AR; mapped balance, admin/affiliate/sample/shipping/ads/adjustment roles; never revenue again | Source file identity + Store + Order + split/version |
| `OMNI_PAYOUT` | Omnichannel/Finance command → Finance | Matched payout from Store marketplace balance to bank | None | Dr mapped Bank / Cr mapped Marketplace Balance–Store | External payout/source key |
| `OMNI_RETURN` | Omnichannel/Quality → Finance and Warehouse via QC | Immutable return/refund linked to original order/revenue | No IN on import; accepted return later becomes Warehouse candidate | Mapped return/refund/AR/balance adjustment; original revenue retained | External return/order/item/type key |
| `OMNI_ADJUSTMENT` | Omnichannel → Finance | Typed signed adjustment linked to Store/order/source file | None unless separate physical event | Mapped Dr/Cr adjustment role | Composite source + Store + order + type + line identity |
| `OMNI_POS_SALE` | POS orchestration → Warehouse and Finance | Strict Item, qty > 0, price/tender snapshots, sufficient stock | Immediate atomic/idempotent Warehouse OUT | Mapped revenue/tax/tender plus COGS/inventory; exact roles from mapping | POS receipt/idempotency key; success only with durable effects |
| `OMNI_POS_VOID_OR_RETURN` | POS/Quality → Warehouse and Finance | Approved linked correction; return may require QC | Controlled reversal/accepted IN | Mapped linked reversal/return; original sale retained | Original POS + action sequence |

Operational order summaries use `Waktu Pesanan Dibuat`; `OMNI_ORDER_COMPLETED` uses `Waktu Selesai`; settlement and payout use their own dates.

## 7. Finance, incentive, and closing events

| Event / candidate | Producer → consumer | Trigger and minimum context | Physical stock effect | Finance effect / line-role intent | Idempotency / target outcome |
|---|---|---|---|---|---|
| `FIN_JOURNAL_POSTED` | Finance → GL/subledgers/source status | Balanced candidate, open period, unique source, resolved active mapping, permission | None | Immutable posted journal/lines and relevant subledger item | Event source posting key unique |
| `FIN_JOURNAL_REVERSED` | Finance → GL/subledgers/source status | Approved correction linked to original | None | Linked reversing journal; original retained | Original journal + reversal sequence |
| `FIN_PAYMENT_POSTED` | Finance → AR/AP/cash/bank/source | Approved allocation and bank/cash context | None | Settle AR/AP and move cash/bank; no duplicate expense/revenue | Payment source key |
| `FIN_ASSET_CAPITALIZED` | Finance → fixed-asset ledger | Approved asset acquisition candidate | None | Fixed asset/AP or clearing roles, register created | Acquisition source line key |
| `FIN_DEPRECIATION_POSTED` | Finance → GL/fixed asset | Approved schedule for open period | None | Mapped depreciation expense/accumulated depreciation | Asset + period + run version unique |
| `CPO_FEE_ACCRUED` | Incentives → Finance | Posted accepted finished-goods receipt qty × effective rate snapshot | None | Mapped fee expense/payable according to Finance mapping | Receipt + rule + beneficiary unique |
| `SALES_FEE_ACCRUED` | Incentives → Finance | Configured accepted trigger and basis/margin/rate snapshot | None | Mapped commission expense/payable | Trigger source + rule + beneficiary unique |
| `INCENTIVE_PAID` | Finance → Incentives | Payable settlement | None | Clear mapped payable to cash/bank; do not create fee expense again | Payment allocation source key |
| `PERIOD_STATUS_CHANGED` | Finance/Core → all posting services | Approved close/reopen/lock transition with reason | Determines allowed movement transaction dates | Determines allowed journal/payment dates | Legal entity + period + transition version |
| `RECONCILIATION_COMPLETED` | Finance/Warehouse → closing/reporting | Control/detail checks and exception disposition | None | No posting merely from report; corrections use explicit events | Reconciliation type + as-of + version |

## 8. Required mapping dimensions and line roles

Finance resolves an event using exact dimensions first and controlled `DEFAULT` fallback. Minimum dimension types are `STORE`, `PURCHASE_CATEGORY`, `COST_CENTER`, `PAYMENT_METHOD`, `TAX`, `BUSINESS_UNIT`, and optionally `PROJECT`. Representative line roles include receivable, payable, revenue, inventory, COGS/WIP, cash/bank, marketplace balance, marketplace fee types, tax, expense, asset cost, accumulated depreciation, variance, and adjustment.

The matrix intentionally does not assign COA codes or names. Debit/credit shown in marketplace concepts describes the accepted accounting outcome; configuration still chooses the exact accounts.

## 9. Event failure and retry rules

| Failure | Required behavior |
|---|---|
| Duplicate source/idempotency key with identical request | Return original durable result; create no second effect. |
| Same key with different payload | Reject as conflict and audit. |
| Missing/inactive mapping | Do not post journal; expose actionable exception/repair state. |
| Insufficient/invalid stock | Do not post movement; source remains pending/rejected, not falsely successful. |
| Closed/locked period | Reject normal posting; only approved controlled correction/reopen path. |
| Downstream error in atomic flow | Roll back all shared-transaction effects; otherwise persist explicit pending/repair/outbox state. |
| Reversal | Validate original, period, remaining allocations/stock and permissions; link both directions. |

## 10. UNRESOLVED event contracts

| ID | Question / missing evidence | Affected modules | Stock impact | Accounting impact | Recommended interpretation |
|---|---|---|---|---|---|
| U-EVT-001 | The actual legacy triggers, parameter payloads, and write sequences cannot be inspected. | All | Unknown duplicate/cross-write behavior. | Unknown posting sequence/hardcode. | Obtain source and UI call graph; add any missing business events before accepting this matrix. |
| U-EVT-002 | B2B revenue recognition timing and invoiceable basis are not explicit enough. | Sales, Finance | Delivery linkage may be required. | Revenue/AR timing and amount. | Treat `SALES_INVOICE_POSTED` as current plan event, pending business confirmation of allowed source basis. |
| U-EVT-003 | Whether purchase AP is recognized on purchase entry, vendor bill, receipt, QC acceptance, or configured three-way match is undefined. | Purchasing, Quality, Warehouse, Finance | Receipt timing may diverge. | AP/expense/inventory cutoff. | Approve recognition/matching policy per treatment before Phase 4/8. |
| U-EVT-004 | Reject/rework/scrap/supplier-return financial roles are incomplete. | Production, Quality, Warehouse, Finance | Movement/disposition routing. | WIP/loss/recovery/AP roles. | Define disposition-to-event matrix before implementation. |
| U-EVT-005 | Marketplace eligible statuses, amount basis, fee signs, tolerances, and tax roles are missing. | Omni, Finance, Tax | None directly. | Revenue/settlement reconciliation. | Use representative channel files and approved mapping tables; no heuristic posting. |
| U-EVT-006 | Sales delivery accounting may be COGS at delivery or another accepted trigger; plan lists representative event but does not lock timing. | Sales, Warehouse, Finance | OUT remains required. | Inventory/COGS timing. | Finance must approve policy; preserve separate delivery and invoice facts. |
| U-EVT-007 | Inventory valuation handling for backdated movement and reversal after later issues is undefined. | Warehouse, Finance | Quantity correction known; cost propagation unclear. | COGS/inventory revaluation entries unclear. | Lock ordered-cost and revaluation event policy before costing implementation. |

## 11. Actual-evidence event delta

| Target event / command | Actual legacy trigger/effect | Required payload additions and target result |
|---|---|---|
| `SALES_DELIVERY_REQUESTED` | Sales SJ save directly appends OUT; edit/delete voids source rows | stable order/delivery line IDs, remaining snapshot, request key -> Warehouse movement/result |
| `SALES_INVOICE_POST_REQUESTED` | Invoice saved from PO/SJ/manual; Finance later reads it | basis DELIVERY by default or approved SALES_ORDER_EXCEPTION; permission/reason/audit for exception; no stock effect -> Finance AR/journal |
| `PURCHASE_RECEIPT_REQUESTED` | Purchase/maklun save may directly append IN | explicit treatment; only INVENTORY/eligible subcontract output creates Warehouse candidate |
| `PURCHASE_PAYABLE_RECOGNITION_REQUESTED` | Finance derives AP from Purchasing Sheet/category | vendor bill/source line, treatment, amount, CC/project/production snapshots -> Finance AP/journal |
| `WORK_ORDER_MATERIAL_ISSUE_REQUESTED` | Distribution directly appends OUT | work-order material line, item, qty, warehouse, source key -> Warehouse issue |
| `PRODUCTION_STAGE_RECORDED` | Production saves Cut/Sew/QC/Handover rows | stable output line, stage qty/reject/PIC/tariff snapshot; no ledger side effect itself |
| `PRODUCTION_WAREHOUSE_HANDOVER_READY` | Setor Gudang directly appends FG IN | output line, accepted qty, HPP snapshot/version -> Warehouse receipt candidate |
| `RETURN_QC_DECIDED` | QC line sets actual result/quarantine | PASS/HOLD/REJECT/REWORK, accepted/rejected/rework qty, evidence and reason; LEGACY_UNMAPPED is migration review only |
| `WAREHOUSE_RETURN_RECEIPT_REQUESTED` | QC batch directly appends RETURN_IN | only accepted line qty; unique inspection/source key -> Warehouse receipt |
| `MARKETPLACE_ORDER_IMPORTED` | lock/upsert by Order+SKU+Variation | batch/row key, all three quantities, created/completed timestamps, mapping snapshot |
| `MARKETPLACE_ORDER_COMPLETED` | Finance report treats completed source as revenue using order date | valid Waktu Selesai + MarketplaceStatusMap normalized COMPLETED + unique unrecognized source + valid Store/accounting mapping -> Finance AR/revenue |
| `MARKETPLACE_SETTLEMENT_RECORDED` | settlement/adjustment upsert and source-derived balance | settlement external ID/date, linked order allocations, fee/adjustment line roles -> reduce AR/create balance |
| `MARKETPLACE_PAYOUT_RECORDED` | saldo-to-bank only represented by manual journal/formula test | payout ref/date, marketplace balance account context, bank -> Finance payout journal |
| `POS_CHECKOUT_REQUESTED` | Warehouse OUT is written before POS rows; Finance later reads POS | request key, Item, positive qty, price/cost snapshot, tender, warehouse, cash-session if cash -> atomic stock/COGS/revenue/payment result |
| `INVENTORY_COST_REVALUATION_REQUESTED` | Production/Warehouse overwrite posted movement cost | original movement/value, delta, reason, approval, period -> immutable adjustment/revaluation |
| `BANK_STATEMENT_IMPORTED` | verified CSV/TXT/PDF import to UNMATCHED | import/file hash, deterministic Tx_Key, raw lineage -> unmatched bank transaction |
| `BANK_RECONCILIATION_MATCHED` | one statement can link many journal rows | link amounts, method, actor, evidence -> immutable active links and reconciliation state |

### 11.1 Idempotency/source-key evidence

| Area | Legacy evidence | Target decision |
|---|---|---|
| Warehouse contract | deterministic Tx_Key check under lock | Preserve and enforce with database unique source constraint. |
| Production/Return QC | lightweight/source Tx_Key; direct writers | Preserve semantic key but route through Warehouse. |
| Omni order/summary | composite key, locks, upsert/version | Preserve batch + row idempotency; include store/channel where needed. |
| Settlement/adjustment | source-first date/external references | Preserve external IDs and partial/split allocation identity. |
| Sales/Purchasing/Finance payments | timestamp/UUID or void/reappend | Replace with caller request key + unique source effect. |
| Reports | no write in readers, except explicit repair/sync jobs | Maintain strict query/command separation. |

No installed scheduler is evidenced. Any target periodic rebuild, depreciation, accrual or close job needs an explicit schedule/ownership decision; do not infer one from callable `REBUILD_`, `SYNC_`, or `REPAIR_` functions.

## 12. Owner-approved event contracts

| Event / command | Mandatory semantics | Posting effect |
|---|---|---|
| `PROFORMA_ISSUED` | References Sales Order and commercial snapshot | Non-posting; no stock, AR or journal. |
| `SALES_ORDER_INVOICE_EXCEPTION_APPROVED` | Permission, reason, approver/audit and invoiceable SO lines | Authorizes invoice source only; never moves stock. |
| `QC_LEGACY_MAPPING_REVIEW_REQUIRED` | Preserves raw legacy value and `LEGACY_UNMAPPED` state | No Warehouse or Finance event until reviewed. |
| `PURCHASE_TREATMENT_MAPPING_REQUIRED` | Unmapped legacy category remains in staging | Blocks transaction import only; no stock/accounting. |
| `PRODUCTION_SHARED_COST_ALLOCATED` | Versioned documented rule, basis and per-item allocation snapshot | Emits eligible cost source; formula chosen at Production/HPP gate. |
| `INVENTORY_REVALUATION_POSTED` | Original movement/source/period, deterministic delta, correction period, reason, approval | Open-period owned valuation/accounting correction; original posting unchanged. |
| `MARKETPLACE_RETURN_OR_REFUND_RECORDED` | References original completed order/revenue and follow-up date/amount | Separate reversal/adjustment event; original revenue history retained. |
| `POS_CASH_SESSION_OPENED` | Operator/location/opening cash and unique applicable open session | Operational session only. |
| `POS_CASH_SESSION_CLOSED` | Expected cash, actual cash, variance, actor and time | Finance posts controlled cash variance if mapped/approved. |
| `POS_SALE_REVERSED` | References posted sale, reason, permission and request key | Warehouse/Finance owned reversal; original sale remains. |
| `POS_RETURN_RECORDED` | Separate return document referencing original sale/item/qty | Stock return only through accepted return/QC policy; Finance adjustment separate. |

The exact shared-cost allocation formula is a **DEFERRED IMPLEMENTATION DETAIL**, not a Phase 1 blocker. The event contract already fixes versioning, item traceability, snapshots and no duplicate expense.

## 13. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** Event boundaries are sufficient for Phase 1 foundation work; Phase 1 has not started.

## 14. Historical provisional phase gate (superseded)

The event coverage is ready for functional review. It is not accepted until legacy source events/cross-writes are audited and the unresolved timing, amount, disposition, and valuation decisions are approved.
