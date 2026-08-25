# KAJABoard Logical Data Dictionary

> **AUTHORITATIVE UPDATE (25 August 2026): OWNER APPROVED FOR PHASE 0 CLOSURE.** Actual Sheet fields were audited and translated into canonical concepts in section 13; section 14 resolves the former conceptual blockers. This is still not a model/migration specification.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — conceptual vocabulary only  
**Status:** DRAFT FOR REVIEW — NOT A DJANGO MODEL OR MIGRATION SPECIFICATION  
**Source boundary:** Project Plan v2.0 and `AGENTS.md`; legacy Sheets/columns are unavailable.

## 1. Conventions

| Term | Definition |
|---|---|
| Stable ID | Immutable application identifier; display code/name may change without breaking lineage. |
| Document number | Human-facing, unique within an approved series/scope; not the relational primary key. |
| Source key | Deterministic unique key for one business effect, used to prevent duplicate posting. |
| Idempotency key | Client/request/import key allowing a safely retried command to return the original result. |
| Snapshot | Historical copy of transaction-relevant master values at the time of business action/posting. |
| Effective dating | `Effective_From`/`Effective_To` and active state determine which configuration applies on a transaction date. |
| Transaction date | Business/economic date; distinct from created, imported, posted, settled, paid, or completed timestamps. |
| Posted | Validated, authorized, immutable business effect included in the owned ledger. |
| Reversed | Original remains visible and a linked controlled correction neutralizes its effect. |
| Money | Currency amount rounded at the accounting layer to whole Rupiah unless an approved rule says otherwise. |
| Quantity | Decimal precision controlled by UOM; never assumed whole. |

All critical entities include stable ID, created/updated timestamps and actors, state, audit linkage, source/reference fields, and optimistic/concurrency metadata where required. Posted historical records cannot cascade-delete silently.

## 2. Core, organization, and configuration

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| LegalEntity | Organization | `LegalEntity_ID`; legal identifier unique | Legal name, address, NPWP/NITKU, PKP status, currency, timezone, active/effective dates. Initial entity: PT KAJA VASTRALOKA KREASINDO. |
| BusinessUnit | Organization | `BusinessUnit_ID`, code unique | Brand/unit name, legal entity, active state, document identity. |
| Department | Organization | `Department_ID`, code unique | Name, parent, business unit, active state. |
| CostCenter | Organization | `CostCenter_ID`, code unique/effective | Name; canonical initial codes `PRODUCTION`, `WAREHOUSE`, `OFFICE`, `SALES_MARKETING`, `GENERAL`; production-overhead eligibility; active/effective dates. |
| Warehouse | Organization | `Warehouse_ID`, code unique | Name, legal entity/business unit, address, default flag, negative-stock policy reference, active state. |
| Location | Warehouse/master | `Location_ID`; warehouse + code unique | Warehouse, bin/location code, type, active state. |
| User | Accounts | `User_ID`; username/email unique | Authentication identity, active/locked/2FA state, employee link. |
| Employee | Accounts/Organization | `Employee_ID`; employee code unique | Name, position, department, cost center, active dates. |
| Role | Accounts | `Role_ID`; code unique | Name, permissions, segregation attributes. |
| PermissionGrant | Accounts | role/user + action + scope unique | Domain action, data-scope type/value, effective dates. |
| ApprovalRule | Core | `ApprovalRule_ID`; context/priority/effective unique | Document/event, threshold/dimension, steps, approver role/scope, segregation, effective dates. |
| ApprovalInstance | Core | `Approval_ID`; source + version unique | Source record, requested/approved/rejected actors/dates, reason, step, final outcome. |
| AuditEntry | Core | `Audit_ID` | Entity/record/action, before/after, changed fields, user, timestamp, reason, source, approval, request/idempotency key. Append-only. |
| IdempotencyRecord | Core | scope + idempotency key unique | Request hash, actor, started/completed time, result reference, status, error/repair metadata. |
| DocumentSequence | Core | series/scope/period unique | Prefix, next value, reset policy, legal/business unit scope, locking metadata. |
| Attachment | Core | `Attachment_ID`; checksum optional unique in scope | Source entity/record, filename, media type, size, checksum, storage key, uploaded by/time, authorization scope. |
| SystemSetting | Master Data | setting key + scope + effective date unique | Typed value, legal/business unit scope, effective dates, active, changed/approved by. |

## 3. Partners and catalog

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| BusinessPartner | Partners | `Partner_ID`; partner code unique | Display/legal name, roles, address/contact/PIC, tax identity, bank display data, payment/credit terms, credit limit, status/risk flags, notes. |
| PartnerRole | Partners | partner + role type unique/effective | `CUSTOMER`, `VENDOR`, `SUBCONTRACTOR`, `MARKETPLACE_PARTNER`, `OTHER`; effective/active state. |
| Item | Catalog | `Item_ID`; SKU/item code unique | Name, type, category/subcategory, UOM, parent product/variant, sales/purchase/production/inventory/tax flags, valuation method, reference cost, min stock, lead time, preferred vendor, active/effective state. |
| ItemVariant | Catalog | `Variant_ID`; product + variant code unique | Parent item/product, attribute values, canonical sellable/stock item link. |
| UOM | Catalog | `UOM_ID`; code unique | Name, quantity precision, dimension/category, base conversion where approved. |
| PurchaseCategory | Master Data | `PurchaseCategory_ID`; code/effective unique | Name; `AccountingTreatment`; default Cost Center; inventory type; asset class; `SnapshotProduction`; accounting mapping key; tax profile; active/effective dates. |
| Store | Master Data | `Store_ID`; code unique | Display name, marketplace, external aliases, business unit/brand, Finance dimension, fulfillment settings, active state. |
| SKUMap | Master Data / Omni | `SKUMap_ID`; marketplace + store scope + SKU + product/variation + effective range unique | External SKU/product/variation, internal Item, mapping type, conversion qty, active/effective dates. Exact variation is preferred. |
| COAAccount | Finance master | `COA_ID`; account code/effective unique | Name, account type, statement groups, normal balance, parent/level/header, manual-post flag, cash/bank/control flags, active/effective dates. |
| COAMapping | Finance master | `Mapping_ID`; resolution dimensions/priority/effective range controlled unique | Module, Event Code, Dimension Type/Value, Line Role, DC, COA, priority, effective dates, active. |
| TaxProfile | Tax | `TaxProfile_ID`; code/effective unique | Tax type/code/rate/base, input/output role, mapping key, Coretax metadata, active/effective dates. |

### 3.1 AccountingTreatment

| Value | Stock behavior | Accounting/operational behavior |
|---|---|---|
| `INVENTORY` | Warehouse receipt candidate; only posted Warehouse IN changes stock. | Inventory valuation/AP source. |
| `ASSET` | Never physical inventory stock. | Fixed-asset acquisition candidate and AP; class/value/date/department or Cost Center snapshot required. |
| `EXPENSE` | No stock. | Cost Center required; expense/AP. Eligible for production overhead only with production-eligible Cost Center and `SnapshotProduction = TRUE`. |
| `SERVICE` | No stock. | Cost Center required; service expense/AP; same strict overhead gate. |
| `MAKLUN` | Material OUT and accepted output IN only through Warehouse. | SPK/subcontract cost and AP; not generic overhead. |

## 4. Sales and projects

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| SalesOrder | Sales | `SalesOrder_ID`; document number unique in series | Customer, optional project, order/customer-PO dates/numbers, deadline, currency, terms snapshots, salesperson, status, totals, approval/audit. |
| SalesOrderLine | Sales | `SalesOrderLine_ID`; document + line sequence unique | Item, description/UOM snapshots, ordered qty, price/tax/discount/charge snapshots, promised date, project/output reference, fulfillment state. |
| SalesDelivery | Sales | `Delivery_ID`; document number and idempotency source unique | Sales order/customer/project, delivery date/address, status, Warehouse request/result, print metadata. |
| SalesDeliveryLine | Sales | `DeliveryLine_ID`; delivery + source order line unique per intended split | Source order line, Item/UOM snapshots, qty requested/posted/reversed, remaining calculation, Warehouse movement reference. |
| SalesInvoiceSource | Sales | `SalesInvoice_ID`; invoice number/source key unique | Customer, source lineage, invoice date/due date, currency/terms, totals, posting state, Finance event reference. This is not the AR ledger. |
| SalesInvoiceLine | Sales | `SalesInvoiceLine_ID` | Source order/delivery line as allowed, Item/description, qty/price/tax/discount/charge snapshots, amount. |
| Project | Projects | `Project_ID`; project code unique | Customer, contract/order, owner/salesperson, target date, status, budget/margin target, business dimensions. |
| ProjectBudget | Projects | project + period + account/category + Cost Center unique | Budget, version, approved state; committed/actual/forecast are derived from traceable sources. |
| CreditOverride | Sales/Core | customer + source request/version unique | Exposure snapshot, limit/overdue state, override permission, approver, reason, effective action. |

Derived Sales values such as delivered, remaining, invoiced, paid, outstanding, and overdue come from posted source documents and Finance subledgers; they are not freely editable counters.

## 5. Purchasing and subcontracting

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| PurchaseDocument | Purchasing | `Purchase_ID`; document/vendor reference uniqueness controlled | Vendor, document/date/due date, currency, project, state, approval, total, terms/tax snapshots. |
| PurchaseLine | Purchasing | `PurchaseLine_ID`; document + line sequence unique | Item/service description; qty/UOM/price; Purchase Category; treatment/Cost Center/inventory type/asset class/production flag/tax/project snapshots; receipt/bill status. |
| PurchaseReceiptSource | Purchasing | `PurchaseReceipt_ID`; source key unique | Purchase/source line, vendor, date, qty, acceptance/QC state, valuation context, Warehouse candidate/result. |
| VendorBillSource | Purchasing | `VendorBillSource_ID`; source key unique | Vendor, purchase/maklun/expense source, amount/tax/due terms, Finance AP event state. Not a payment ledger. |
| SPK | Purchasing/Production by type | `SPK_ID`; SPK number unique | Internal/external type, optional Sales Order/project, vendor, due date, instructions, attachments, status, partial completion. |
| SPKOutput | Purchasing/Production | `SPKOutput_ID`; SPK + output line unique | Output Item, target qty/UOM, item note/reference image, acceptance and completion summaries derived by Item. |
| SPKMaterialOutputLink | Purchasing/Production | `SPKMaterialOutputLink_ID`; SPK/material line/output link unique | Material Item, output item, planned qty/conversion, issue allowance; prevents ambiguous HPP lineage. |
| MaterialSend | Purchasing | `MaterialSend_ID`; source key unique | SPK/vendor/date/reference/status; Warehouse issue candidate. |
| MaterialSendLine | Purchasing | `MaterialSendLine_ID` | SPK material/output link, Item, qty, cost snapshot, Warehouse movement reference. |
| MaklunReceipt | Purchasing | `MaklunReceipt_ID`; source key unique | SPK/vendor/date/receipt type/state, QC/acceptance, Warehouse candidate, Finance cost/AP source. |
| MaklunReceiptLine | Purchasing | `MaklunReceiptLine_ID` | Output Item, accepted/rejected qty, specific service cost, shared allocation, other eligible cost, supplied material value. |
| ProductionOverheadSource | Purchasing/Finance | source module + source line + source key unique | Category, treatment, Cost Center, amount, status, posted date, reversal, metadata. Only eligible active/posted/non-reversed rows enter Production snapshot. |

## 6. Production and quality

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| ProductionWorkEntry | Production | `WorkEntry_ID`; idempotency/source key unique | SPK, date, PIC, process, status, batch metadata. |
| ProductionWorkLine | Production | `WorkLine_ID`; never inferred only from batch | SPK output Item, process, qty, available-before snapshot, tariff/direct-labor amount, note, correction/reversal reference. |
| ProductionReject | Production/Quality | `RejectLine_ID`; source key unique | SPK/output Item, stage (`CUT`,`SEW`,`QC`), qty, reason, disposition, QC reference, valuation/cost context. |
| ProductionTariff | Master/Production | `Tariff_ID`; process/context/effective dates unique | Wage method, rate, UOM/basis, effective dates, active/approved state. Snapshot on work line. |
| ProductionExtraCost | Production | `ExtraCost_ID`; source key unique | SPK/output/project, category, amount, payable party, direct-cost eligibility, Finance event, settlement state. Payment does not recreate cost. |
| ProductionOverheadSnapshot | Production | source key + allocation target/version unique | Original source metadata, eligible amount, allocation rule/basis, SPK/output/period target, posted/reversed state. |
| ProductionCostSnapshot | Production | `CostSnapshot_ID`; SPK/output/version unique | Material, labor, extra direct, overhead, subcontract, other approved components, allocation and rounding, accepted output denominator, approval/post state. |
| ProductionWarehouseHandover | Production | `Handover_ID`; source key unique | SPK, date, state, partial flag, requested/accepted/rejected totals, Warehouse receipt result. |
| HandoverLine | Production | `HandoverLine_ID` | SPK output Item, qty requested/accepted/rejected, unit-cost snapshot/cost reference, Warehouse movement. |
| QCInspection | Quality | `Inspection_ID`; source + inspection sequence unique | Source type/ID/line, Item, qty offered/inspected/accepted/rejected/rework/hold, result, reason, photos, inspector, timestamps, final state. |
| QCDisposition | Quality | `Disposition_ID`; inspection + decision version unique | `PASS`,`HOLD`,`REJECT`,`REWORK`, approved action, Warehouse/Finance candidate reference, reason. |

Production WIP balances are derived by SPK output Item from posted, non-reversed work/reject/handover lines; no aggregate editable WIP balance is authoritative.

## 7. Warehouse and inventory valuation

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| StockMovement | Warehouse | `Movement_ID`; source key unique | Item, warehouse/location, `IN`/`OUT`, qty/UOM, unit cost/value, source module/type/ID/line/key, transaction/posting dates, state, reversal reference, created/posted actors. |
| StockReservation | Warehouse | `Reservation_ID`; source line/state uniqueness | Item, warehouse, source demand, qty reserved/released/fulfilled, expiry and state. Does not equal physical movement. |
| StockBalance | Warehouse projection | Item + warehouse/location unique | Posted IN minus OUT, reserved/available quantities, last movement. Rebuildable from ledger; not independent source truth. |
| InventoryCostLayer/Sequence | Warehouse valuation | item + warehouse + ordered movement unique | Movement, before/after qty/value, unit cost, policy snapshot, calculation version; supports transaction-order-aware weighted average. |
| InventoryValuationSnapshot | Warehouse/Finance read model | item/warehouse/period/version unique | Qty/value derived from posted movements and costing; reconciles to Finance GL. |
| StockOpname | Warehouse | `Opname_ID`; warehouse/date/session unique | Freeze/count scope, system snapshot date, count status, approval, reason. |
| StockOpnameLine | Warehouse | `OpnameLine_ID`; opname + item/location unique | System qty, counted qty, variance, reason, approved adjustment movement. |
| StockAdjustment | Warehouse | `Adjustment_ID`; source key unique | Positive/negative reason, approval, item/warehouse/qty, valuation, posted/reversed movement. |
| InternalConsumption | Source business/Warehouse result | `Consumption_ID`; source key unique | Item, qty, purpose, Cost Center/project, request/approval, Warehouse issue, Finance event. |

## 8. Omnichannel and POS

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| ImportBatch | Data Exchange/domain | `Batch_ID`; import type + checksum/idempotency controlled | Source filename/system, template version, checksum, user/timestamps, total/success/skipped/warning/failed, error log, confirmed state. |
| OmniOrder | Omnichannel | `OmniOrder_ID`; marketplace/store/order number unique | Canonical Store, external order number/status, `Waktu Pesanan Dibuat`, `Waktu Selesai`, tracking/resi, totals, reconciliation state. |
| OmniOrderLine | Omnichannel | `OmniOrderLine_ID`; order number + external SKU + variation unique | Raw product/SKU/variation, internal Item, `Marketplace_Qty`, `Conversion_Qty`, `Internal_Qty`, mapping snapshot, subtotal and relevant source amounts. |
| OmniDemand | Omnichannel | `Demand_ID`; source order line unique/versioned | Item/store/order, required qty, packed/remaining derived qty, operational date, shortage/backorder state. |
| OmniPacking | Omnichannel/Warehouse execution | `Packing_ID`; source key unique | Store/order/date, state, Warehouse issue result. |
| OmniPackingLine | Omnichannel | `PackingLine_ID` | Demand/order line, actual Item/variant, qty, Warehouse movement, allocation source. |
| OmniRevenueEvent | Omnichannel source | `RevenueEvent_ID`; recommended `OMNI_REV\|Store_ID\|Order_Number` unique | Eligible completed state, valid completion date, gross basis/tax/discount snapshots, Finance result; immutable after posting except linked adjustment. |
| Settlement | Omnichannel | `Settlement_ID`; source file/external settlement identity unique | Store, settlement date, file/batch, matching state, totals, Finance result. |
| SettlementOrder | Omnichannel | settlement + Store + order + split sequence unique | Order, receivable clearing amount, net balance, structured fee roles, adjustments, match difference/status. |
| MarketplacePayout | Omnichannel/Finance source | `Payout_ID`; external payout/source key unique | Store, payout date, marketplace balance amount, target bank/payment reference, matching state, Finance result. |
| OmniReturn | Omnichannel | `Return_ID`; external return/order/item identity unique | Original order/line, Store, return/refund dates, qty/amount/reason, QC state, Finance adjustment state. Original revenue remains. |
| OmniAdjustment | Omnichannel | composite source/order/store/type/line identity unique | Adjustment type, sign/amount, date, reason, source batch, Finance role/result. Different types cannot overwrite. |
| POSSale | Omnichannel | `POSSale_ID`; receipt/source/idempotency key unique | Store/channel, date/time, customer optional, tender snapshot, subtotal/tax/discount/total, post/repair/void state, Warehouse and Finance results. |
| POSLine | Omnichannel | `POSLine_ID`; sale + line sequence unique | Strict internal Item, qty > 0, UOM, price snapshot, tax/discount, COGS reference, Warehouse movement. |
| POSTender | Omnichannel/Finance source | `POSTender_ID` | Payment method, amount, reference, mapped context; Finance owns cash/bank/payment accounting. |

Omni operational summaries use order-created date. Revenue summaries/events use completion date. Neither summary is an editable ledger.

## 9. Finance, incentives, tax, and reporting

| Entity | Owner | Stable key / uniqueness | Minimum business fields and meaning |
|---|---|---|---|
| BusinessEventInbox | Finance | source module + event code + source key unique | Event schema/context, transaction date, dimensions, amounts/qty, source hash, received/processed/error state. |
| JournalEntry | Finance | `Journal_ID`; source posting key unique | Journal number/date/period, source event/document, description, state, reversal reference, total debit/credit, mapping version, actor/approval. |
| JournalLine | Finance | `JournalLine_ID`; journal + line sequence unique | COA, Debit/Credit amount, Line Role, mapping snapshot, partner/store/project/Cost Center/business unit/tax dimensions, source line. |
| ARItem | Finance | `ARItem_ID`; source key unique | Customer/store control party, invoice/revenue source, original/open amount, due date, currency, state, journal lineage. |
| APItem | Finance | `APItem_ID`; source key unique | Vendor/payee, bill/accrual source, original/open amount, due date, currency, state, journal lineage. |
| Payment | Finance | `Payment_ID`; external/internal source key unique | Party, date, method, cash/bank account context, amount, allocation state, approval, journal. |
| PaymentAllocation | Finance | payment + AR/AP item + sequence unique | Applied amount, discount/write-off/FX context if approved, remaining amount. |
| MarketplaceBalanceItem | Finance | source settlement/payout line key unique | Store, settlement/payout source, increase/decrease, open balance, journal lineage. |
| FixedAsset | Finance | `Asset_ID`; asset number/source acquisition unique | Asset class, description, acquisition source/value/date, Cost Center/project, useful life, residual value, method, capitalization/disposal state. |
| DepreciationEntry | Finance | asset + period + version unique | Basis, period, amount, accumulated depreciation, journal, reversal state. |
| FiscalPeriod | Finance | legal entity + fiscal year/period unique | Start/end, `OPEN`,`SOFT_CLOSE`,`FINANCE_REVIEW`,`CLOSED`,`TAX_FILED`,`LOCKED`, close/reopen approvals. |
| ReconciliationRun | Finance/Warehouse by type | type + period/as-of + version unique | Scope, source totals, control totals, differences, exception records, actor/time/status. |
| IncentiveRule | Incentives | rule code + effective range/version unique | Trigger, formula/basis, rate/tier, minimum margin, beneficiary rule, accounting key, approval. |
| IncentiveAccrual | Incentives | trigger source + rule version + beneficiary unique | Source event, qty/revenue/margin basis snapshots, rate, amount, beneficiary, estimated/accrued/approved/payable/paid/reversed state. |
| ReportDefinition | Reports/Finance/Tax | report + version + effective dates unique | Statement/section/category/subcategory/order/normal balance/cash-flow/fiscal classifications. |
| ReportSnapshot | Reports | report + parameters + generation version/time unique | Company/period/filters, generated by, source cutoffs, definition/app version, output files/checksum; no posting behavior. |

## 10. Controlled values

| Field family | Allowed or minimum values |
|---|---|
| QC result | `PASS`, `HOLD`, `REJECT`, `REWORK` |
| Stock direction | `IN`, `OUT` |
| Stock movement state | `DRAFT`, `PENDING`, `POSTED`, `REVERSED` |
| SPK state | `DRAFT`, `SUBMITTED`, `APPROVED`, `IN_PROGRESS`, `PARTIALLY_COMPLETED`, `READY_FOR_WAREHOUSE`, `COMPLETED`, `VOID` |
| Marketplace reconciliation concept | `COMPLETED_NOT_SETTLED`, `SETTLEMENT_MATCH`, `SETTLEMENT_PARTIAL`, `SETTLEMENT_DIFFERENCE`, `SETTLEMENT_WITHOUT_COMPLETED_ORDER`, `RETURN_AFTER_COMPLETION`, `COMPLETED_NEVER_PAID`, `PAYOUT_PENDING`, `PAYOUT_MATCH`, `UNMAPPED_SKU`, `UNMAPPED_STORE` |
| Reconciliation workflow | `OPEN`, `PARTIAL`, `MATCHED`, `DIFFERENCE`, `CLOSED` |
| Period | `OPEN`, `SOFT_CLOSE`, `FINANCE_REVIEW`, `CLOSED`, `TAX_FILED`, `LOCKED` |
| Incentive | `ESTIMATED`, `ACCRUED`, `APPROVED`, `PAYABLE`, `PAID`, `REVERSED` |
| Purchase treatment | `INVENTORY`, `ASSET`, `EXPENSE`, `SERVICE`, `MAKLUN` |

Additional state values require an accepted business decision and an updated Workflow Status Matrix; free-form critical statuses are prohibited.

## 11. Derived calculations and sources of truth

| Measure | Definition / source |
|---|---|
| Sales remaining delivery qty | Ordered qty minus posted, non-reversed delivery qty by stable order line. |
| Available Sewing | Cut − Sew − Reject Cut, per SPK output Item. |
| Available QC | Sew − QC − Reject Sew, per SPK output Item. |
| Available Warehouse | QC − handover − Reject QC, per SPK output Item. |
| Internal marketplace qty | `Marketplace_Qty × Conversion_Qty` from import-line snapshot. |
| Physical on hand | Sum of posted, non-reversed Warehouse IN minus OUT by Item/warehouse/location. |
| Available stock | On hand minus active reservations, subject to policy; never an imported summary. |
| Moving weighted-average cost | Transaction-order-aware posted value/quantity calculation under the item's effective valuation policy. |
| AR/AP outstanding | Original subledger item minus posted allocations/credit/reversal. |
| Marketplace receivable | Completed revenue AR minus matched settlement clearing. |
| Marketplace balance | Matched settlement net balance/adjustments minus payouts. |
| Production HPP | Approved material + labor + eligible direct extra + eligible overhead + subcontract + other approved cost, allocated and snapshotted. |
| Project actual/committed | Traceable posted/approved source events; not manually typed summary. |

## 12. UNRESOLVED dictionary items

| ID | Question / missing evidence | Affected modules | Stock impact | Accounting impact | Recommended interpretation |
|---|---|---|---|---|---|
| U-DD-001 | Actual legacy Sheet/table/column names, types, keys, status strings, null conventions, and historical anomalies are unavailable. | All/migration | Cannot map source quantity fields safely. | Cannot map source monetary/control fields safely. | Obtain schemas plus representative redacted data; build a separate source-to-canonical mapping appendix. |
| U-DD-002 | Currency/multi-currency scope is not explicitly locked; default currency is implied. | Sales, Purchasing, Omni, Finance | Valuation currency issue possible. | FX and realized/unrealized treatment undefined. | Treat IDR/whole Rupiah as baseline only after business confirmation; backlog multi-currency unless accepted otherwise. |
| U-DD-003 | UOM conversions and allowable fractional precision per category are undefined. | Catalog, Purchasing, Production, Warehouse, Sales | Over/under-issue risk. | Valuation rounding risk. | Approve UOM conversion master and precision policy before transactional design. |
| U-DD-004 | Tax, charge, discount, freight, and marketplace gross-subtotal normalized fields/signs are not enumerated. | Sales, Purchasing, Omni, Finance, Tax | Landed cost may be affected. | Revenue/expense/tax amount affected. | Freeze examples and approve component dictionary before implementation. |
| U-DD-005 | Exact payment method, bank, marketplace payout, and external reference identities are missing. | Omni, Finance | None directly. | Duplicate payment/payout risk. | Define canonical external IDs and fallback composite keys per source. |
| U-DD-006 | Serial/lot/batch/expiry tracking is not stated. | Catalog, Warehouse, Quality, Production | Could materially change stock identity. | Valuation and traceability may change. | Confirm explicitly before Phase 2; do not invent lot tracking. |
| U-DD-007 | Return, reject, rework, scrap, and disposal reason/disposition vocabularies are missing. | Quality, Warehouse, Production, Finance | Movement routing unclear. | Loss/recovery account roles unclear. | Approve controlled reason and disposition masters. |

## 13. Actual-evidence source-to-concept dictionary

Classification tags: `BC` business-critical, `TL` technical legacy only, `DER` derived, `SNAP` historical snapshot, `SRC` source reference, `AUD` audit, `NORM` normalization candidate, `UNR` unresolved.

| Conceptual entity.attribute | Legacy evidence | Tags | Identity / constraint / history requirement |
|---|---|---|---|
| User.external_email | Master_User/email | BC,SRC | normalized unique email; not the authorization key by itself |
| Session.passport_id/signature/expires_at/last_logout_at | HMAC token and Master_User logout fields | BC,AUD | unique token ID; secret external; immutable issued claims |
| Module.code/version/route | Master_Module + heartbeat cells | BC,SRC,TL | stable module code; deployed version evidence separate from runtime cache |
| Document.number | No PO/SJ/Invoice/SPK/POS and numbering sheet | BC,SRC | unique per approved series; never relational PK |
| BusinessPartner.id/roles/display_snapshot | customer/supplier/vendor names | BC,SNAP,NORM | stable partner ID; role uniqueness; transaction keeps name/address snapshots |
| Item.id/name/type/uom | Master_Item; `Item_Type` patch | BC | stable ID; unique business key; active/effective status |
| ItemMapping.external_sku/variation/internal_item_id/conversion_qty | Master_SKU_Map | BC,SRC,SNAP | effective unique key by channel/store/SKU/variation; strict internal Item FK |
| SalesOrder.id/number/status/customer_snapshot | Data_PO | BC,SRC,SNAP | stable ID + unique number; controlled state |
| SalesOrderLine.id/item_id/ordered_qty/price_snapshot | repeated Data_PO rows | BC,SNAP | stable line ID; unique within order; qty > 0 |
| Delivery.id/number/order_id/date/status | Surat Jalan rows | BC,SRC | unique number and idempotency key |
| DeliveryLine.id/order_line_id/qty | SJ item rows | BC,SRC | stable line; sum posted qty <= ordered remaining |
| Invoice.id/number/date/source_type/source_id/status | Data_Invoice | BC,SRC,UNR | unique source posting; invoiceable basis awaits decision |
| InvoiceLine.id/source_delivery_line_id/item_id/qty/price_snapshot | invoice item rows | BC,SNAP,UNR | stable line; source uniqueness; manual exception controlled |
| PurchaseDocument.id/number/vendor/treatment_snapshot | Data_Pembelian | BC,SNAP,NORM | explicit INVENTORY/ASSET/EXPENSE/SERVICE/MAKLUN; legacy category is migration input only |
| PurchaseLine.id/item_id/qty/price/cost_center_snapshot/production_snapshot | purchase rows | BC,SNAP | stable line; CC required for EXPENSE/SERVICE |
| WorkOrder.id/number/status | Data_SPK | BC,SRC | stable work-order ID; controlled state; item-safe close |
| WorkOrderOutput.id/item_id/planned_qty | SPK output rows | BC | stable line; completion per output |
| WorkOrderMaterial.id/output_line_id/material_id/required_qty | SPK material pair | BC | preserves material-output relation |
| SubcontractOrder.type/cost_source/price_snapshot | FULL_ORDER/CMT and Cost_Source | BC,SNAP | controlled type; immutable cost basis |
| ProductionEntry.id/transaction_line_id/work_order_output_id/stage | Trx_ID + repeated production rows | BC,NORM | new stable line ID required; stage controlled |
| ProductionEntry.qty/reject_stage/reject_qty/pic/tariff_snapshot | Data_Produksi | BC,SNAP | positive qty; stage availability invariant; PIC/tariff immutable snapshot |
| ProductionCost.material/direct_labor/extra_direct/overhead/subcontract | HPP calculations | BC,DER,UNR | each source line unique; eligibility and allocation versioned |
| ProductionWarehouseHandover.id/output_line_id/qty | Setor Gudang transaction | BC,SRC | unique source; no stock until Warehouse receipt |
| StockMovement.id/source_key/item_id/direction/qty/date/status | Stock_Movement + Tx_Key | BC,SRC,AUD | unique source key; posted immutable; IN/OUT/adjustment controlled |
| StockMovement.unit_cost/value/cost_status | COGS_Cost/Cost_Status-like fields | BC,SNAP | value snapshot; corrections by linked revaluation, not overwrite |
| StockBalance.item_id/warehouse_id/as_of | calculated from SM | DER | never independent writable ledger; indexed projection |
| Stocktake.id/physical_qty/book_qty/variance/reason/approval | opname/audit rows | BC,DER,AUD | variance movement unique to approved count |
| ReturnRegistration.id/external_order_no/sku/variation/resi | Omni_Retur | BC,SRC | natural key must include variation; legacy key omission is migration conflict |
| InspectionSession.id/status | Return_QC_Session DRAFT/POSTED | BC,AUD | one active session per operator/device policy |
| InspectionLine.id/return_id/result/accepted_qty/evidence | QC line/quarantine | BC,AUD,UNR | controlled target result; line quantities; source result snapshot |
| MarketplaceOrder.external_order_no/store/order_created_at/completed_at | Omni_Order | BC,SRC,UNR | external uniqueness with store/channel; completed_at absent in legacy |
| MarketplaceOrderLine.id/sku/variation/marketplace_qty/conversion_qty/internal_qty | import/mapping/return fields | BC,SRC,SNAP | unique Order+SKU+Variation; preserve all three quantities |
| MarketplaceSettlement.external_id/order_id/settlement_date/gross/net | settlement sheets | BC,SRC,SNAP | unique external/source composite; partial/split links supported |
| MarketplaceAdjustment.external_id/type/sign/amount/date | adjustment rows | BC,SRC | unique external adjustment; controlled line role |
| MarketplacePayout.external_id/payout_date/bank_id/amount | not explicit as distinct table | BC,SRC,UNR | required canonical entity; unique payout ref |
| PosSale.id/number/request_key/item_id/qty/price_snapshot/tender | Omni_POS_Sales | BC,SRC,SNAP,UNR | unique request/idempotency key; actual Item; atomic outcome |
| Journal.id/source_key/date/period/status | Data_Jurnal row concept | BC,SRC,AUD,NORM | unique source; target header with immutable posted state |
| JournalLine.id/journal_id/line_role/coa_mapping_version/debit/credit | debit/credit account columns | BC,SNAP,NORM | sum debit=credit; no hardcoded transaction COA |
| Receivable/Payable.source_document_id/outstanding/status | Finance-derived invoice/purchase views | BC,DER | Finance-owned subledger; unique source document |
| Payment.id/source_key/reference/amount/date/tender/bank | Finance payment functions | BC,SRC,AUD | unique request/source; amount <= remaining unless approved exception |
| BankStatementTransaction.tx_key/date/direction/amount/balance/import_id | Bank_Statement | BC,SRC,AUD | deterministic unique Tx_Key; raw import lineage retained |
| BankReconciliationLink.id/bank_tx_id/journal_id/amount/status | Bank_Recon_Link | BC,AUD | unique active journal use; one-to-many statement links allowed |
| AccountingContext.event_code/line_role/dimensions | absent; inferred account candidates | BC,NORM | required target input to effective Master COA Mapping |
| ReportCache.summary_version/source_updated_at | Omni summary V3 | DER,TL | rebuildable, versioned, never ledger truth |
| AuditRecord.entity/action/before/after/actor/reason/source/approval/request_key | scattered logs/timestamps | BC,AUD,NORM | append-only canonical audit requirement |

### 13.1 Legacy-only and normalization findings

- Spreadsheet IDs, sheet names, row numbers, column indexes, `gid`, heartbeat cells, cached maps, public Drive photo URLs, HTML state globals and `google.script.run` names are `TL`; retain only migration/source lineage where needed.
- Repeated names for Item, customer, store, COA and cost center are normalization candidates. Historical documents must retain snapshots while foreign keys identify the canonical master.
- `Tanggal`, `Tanggal Key`, created/imported/settled/completed/posted dates are not interchangeable. The canonical attributes above must remain distinct.
- `Data_Jurnal` debit-account/credit-account columns are not a sufficient target journal structure; conceptual header/line normalization is required.
- Source row number can assist migration diagnostics but cannot become stable identity.

## 14. Owner-approved conceptual additions and resolutions

The `UNR` tags in section 13 for the subjects below are superseded by these approved concepts:

| Conceptual entity.attribute | Classification | Authoritative constraint |
|---|---|---|
| LegacyEvidenceBaseline.name/root/manifest_hash/file_hashes/approved_at | SRC,AUD | Current `legacy/smb_gas/` baseline is official; manifest is immutable and replacement requires approved delta. |
| MarketplaceStatusMap.channel/raw_status/normalized_status/effective_from/effective_to | BC,SNAP | Configurable mapping; accounting never hardcodes raw status. Only normalized COMPLETED is revenue-eligible. |
| MarketplaceRevenueRecognition.source_key/completed_at/store_mapping_id/recognized_at | BC,SRC,AUD | Valid Waktu Selesai, COMPLETED, unique source and valid Store/accounting mapping required. |
| SalesInvoice.basis | BC,SNAP | Controlled `DELIVERY` or `SALES_ORDER_EXCEPTION`; default is delivery. |
| SalesInvoice.exception_permission/reason/approved_by | BC,AUD | Required for direct SO basis; exception creates no stock effect. |
| ProformaInvoice.id/source_order_id/status | BC,SRC | Explicit non-posting commercial document; never creates AR/journal. |
| LegacyQcStatusMap.raw_value/canonical_result/review_status | BC,SRC,AUD | Canonical result is PASS/HOLD/REJECT/REWORK or migration-only LEGACY_UNMAPPED; raw value retained. |
| InspectionMigration.state | BC,AUD | `MAPPED` or `LEGACY_UNMAPPED`; unmapped rows require review and cannot post movement/accounting. |
| LegacyPurchaseTreatmentMap.legacy_category/treatment/effective_from | BC,SRC,SNAP | Explicit mapping to INVENTORY/ASSET/EXPENSE/SERVICE/MAKLUN; no substring inference. |
| PurchaseImportStaging.mapping_status | BC,AUD | `MAPPED`, `UNMAPPED`, `REJECTED`, `ACCEPTED`; unmapped rows cannot enter transactions. |
| ProductionCostAllocation.rule_code/rule_version/basis/snapshot | BC,SNAP | Item-specific cost retains item identity; shared cost requires documented versioned rule and historical allocation snapshot. |
| InventoryRevaluation.id/original_movement_id/original_period/correction_period/delta/reason/approval | BC,SRC,AUD | Never mutates original posting; correction period must be authorized/open; calculation deterministic. |
| PosSale.cost_snapshot/tender_method/status | BC,SNAP | Actual Item, positive qty, explicit tender, atomic/idempotent `POSTED`; draft may cancel, posted only reverses. |
| PosCashSession.id/operator/location/opened_at/closed_at/expected_cash/actual_cash/variance/status | BC,AUD | Controlled `OPEN`/`CLOSED`; one applicable open session for cash tender; close records variance. |
| PosReturn.id/original_sale_id/reason/status/source_key | BC,SRC,AUD | Separate return document/event; never deletes original sale. |
| PosReversal.id/original_sale_id/reason/approval/source_key | BC,SRC,AUD | Controlled correction for posted sale with owned Warehouse and Finance reversals. |

The exact shared-cost allocation formula/basis remains a **DEFERRED IMPLEMENTATION DETAIL** for the Production/HPP gate. The foundation must support versioned allocation rules and snapshots, so the later choice does not require a Phase 1 architecture change.

## 15. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** The conceptual vocabulary is sufficient for Phase 1 foundation design; physical models and migrations remain prohibited until Phase 1 is explicitly started.

## 16. Historical provisional phase gate (superseded)

This dictionary establishes canonical concepts for Phase 0 review. It is not permission to create tables or migrations. Physical source mapping cannot be finalized until the missing legacy schemas and representative data are supplied and reconciled.
