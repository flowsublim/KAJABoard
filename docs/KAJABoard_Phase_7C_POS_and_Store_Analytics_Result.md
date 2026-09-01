# KAJABoard Phase 7C — POS and Store Analytics Result

## Scope and source evidence

Phase 7C closes the POS and source-analytics work of Phase 7. It uses the
accepted SMB POS evidence in `legacy/smb_gas/omnichannel/Kode.gs`: a POS
document has date, document number, payment method, item, quantity, price,
total, and an immediate `POS_OUT` stock action. The legacy menu also exposed
`Tunai` and `QRIS` as its observed tender choices and a single payment method
per sale. Phase 7C retains that supported single-tender rule; it does not
invent split tender. Its legacy category/subcategory/name lookup is upgraded
to a strict canonical Item reference because a category or display label is
not a physical-stock identity.

No legacy file is changed. The implementation is source and operational
control only; it does not create Finance journals, AR/AP, cash/bank ledgers,
or Finance payments.

## POS document and state machine

`PosSale` and `PosSaleLine` are immutable source documents after posting.
States are `DRAFT`, `POSTED`, `REVERSED`, and `CANCELLED`. A draft has no
stock or final Finance candidate. Posting validates an active, sales-eligible,
inventory-eligible canonical Item effective on the transaction date, a valid
Store and Warehouse, positive Decimal quantity, and explicit price snapshot.

`POSTED` is atomic: Warehouse is called for an immediate `POS_SALE_ISSUE` OUT
for each source line, Warehouse valuation is copied as the COGS snapshot, and
the POS source candidates are created in the same transaction. A Warehouse
failure leaves the sale in draft with no source movement or candidate.
Retries are protected by document/source keys, database constraints, locks,
and Warehouse idempotency. Negative stock remains Warehouse validation.

## Tender, cash session, and Finance boundary

`PosTender` records one observed legacy-style tender per sale: `CASH`, `QRIS`,
or an explicitly referenced configured `OTHER` method. Its total must equal
the POS payable amount. Cash requires an open Store cash session.

`PosCashSession` is an operational source/control record only. It records
opening cash, accepted POS cash tenders, recorded cash refunds, expected cash,
counted cash, and frozen variance at close. It has open/closed state,
idempotent close lineage, and cannot accept later cash POS posting after
close. The expected source amount is not represented as a Finance cash ledger.

Future Finance candidates are durable `PosFinanceSource` records, with
mapping readiness resolved through Phase 2C: `POS_SALE_REVENUE`, `POS_COGS`,
`POS_TENDER`, `POS_REVERSAL`, `POS_RETURN`, `POS_REFUND`, and
`POS_CASH_VARIANCE`. Missing mapping is `BLOCKED_MAPPING`; no transactional
COA is hardcoded and no JournalEntry is created.

## Reversal and separate POS return

A posted POS sale is not edited. `PosSaleReversal` preserves the original,
creates a compensating Warehouse `POS_SALE_REVERSAL` movement, and creates
reversal candidate lineage. A repeat reversal is idempotent/blocked by its
unique original-sale relation.

`PosReturn` and `PosReturnLine` are a separate commercial source document
linked to original POS sale lines. They cap cumulative source return quantity
at the original sold quantity and independently retain source, inspected,
Quality accepted, Warehouse received, and refunded quantities. Return
registration and refund recording create zero StockMovement.

The only physical route is:

`POS Return Source → Quality CUSTOMER_RETURN inspection → posted PASS → Warehouse POS_RETURN_RECEIPT`.

The Warehouse service locks the return line and caps receipt by both source
return and Quality PASS quantities. HOLD, REJECT, and REWORK do not restore
available stock. Original sale and revenue source history remain intact.

## Store/channel/SKU analytics

The read-only analytics selector combines source facts, with drill-down IDs,
for legal entity, Store/channel, period, and canonical Item where available:

- marketplace operational orders by **Order Date**;
- marketplace completion revenue by **Completion Date**;
- settlement, fee, adjustment, return/refund, and payout on their own source dates;
- POS posted revenue/units and Warehouse-authoritative COGS on POS transaction date;
- separate POS and marketplace return quantities.

Settlement and payout are never additional revenue. Return/refund does not
erase original revenue. Gross-profit source is shown only when revenue,
Warehouse COGS, and attributable fee facts are all authoritative. Unknown
facts remain unavailable/pending rather than becoming zero.

## Tests and migrations

Phase 7C regression tests cover strict Item validity, atomic posting failure,
immediate Warehouse OUT and cost snapshot, retry idempotency, negative-stock
protection, cash-session close control, reversal lineage, separate
Quality-gated POS returns, return caps, and analytics source accounting.

New migrations add the Phase 7C Omnichannel source records and the three
Warehouse movement types. Historical migrations are unchanged. Finance
posting, AR/AP, cash/bank ledgers, period close, tax, and all Phase 8 work are
explicitly deferred.

## Phase 7 closure

Phase 7 is operationally complete when the regression gate confirms: Phase 7A
BigSeller idempotency and Order Date semantics, Phase 7B Completion Date and
settlement/return boundaries, and Phase 7C strict Item, atomic Warehouse,
Quality, cash-source, and analytics rules. Phase 8 remains a separate Finance
implementation phase.
