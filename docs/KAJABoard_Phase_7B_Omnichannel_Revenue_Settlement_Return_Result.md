# KAJABoard Phase 7B — Omnichannel Revenue, Settlement, Return, and Payout Source Result

Status: implemented as source events and Finance handoff candidates. This checkpoint does not implement Phase 7C POS or Phase 8 Finance posting.

## Scope and ownership

Phase 7B keeps source ownership in Omnichannel. It creates durable, auditable source records for completed-order revenue, settlement, fees, adjustments, returns/refunds, reconciliation, and payout handoff. It does not create `JournalEntry`, AR, cash/bank postings, payments, or Finance control-account balances. It does not create a `StockMovement` during an import or a read-only query.

Warehouse remains the only owner of physical inventory movements. A marketplace return can become a Warehouse `MARKETPLACE_RETURN_RECEIPT` only after a posted Quality inspection with `PASS`; the Warehouse service caps the receipt by both source return quantity and accepted Quality quantity. Return import itself has zero stock effect.

## Legacy evidence used

The accepted SMB implementation was reviewed in `legacy/smb_gas/omnichannel/Kode.gs`, `Omni_DataKey.gs`, `Omni_DailySummary.gs`, `legacy/smb_gas/finance/Finance_OmniDailySummary.gs`, and `Finance_MarketplaceBalance.gs`. The relevant evidence is:

- `OMNI_ORDER_COMPLETED` is separate from operational order summaries and uses completion/revenue date.
- settlement uses its own `Tgl Pencairan`, `Pendapatan Bersih`, and separate fee columns (`Biaya Admin`, `Biaya Layanan`, `Komisi Affiliate`, `Ongkir Penjual`); settlement is not a second revenue event.
- adjustments are typed source rows and must remain distinct.
- returns are read as commercial follow-up evidence; Quality controls acceptance and Warehouse controls physical receipt.
- payout is a later marketplace-balance-to-bank handoff, not revenue recognition.

No legacy customer data or raw production export contents are reproduced here.

## Revenue event rule

`create_revenue_event()` creates one immutable `OmniRevenueEvent` for an eligible `OmniOrder` only when:

1. normalized status is `COMPLETED`;
2. `completion_date` is present;
3. a canonical Store is resolved; and
4. the order-level event key is unique: `OMNI_REV|<Store UUID>|<external order number>`.

All physical order lines are aggregated once with `Decimal`. A missing eligible line subtotal remains `NULL` and puts the source in `BLOCKED_AMOUNT`; it is never converted to zero. Store/accounting readiness is reported as `BLOCKED_MAPPING` until the Phase 2C resolver can resolve the required `OMNI_ORDER_COMPLETED` receivable and revenue roles for the Store dimension. The candidate exposes the source components and mapping context without selecting a COA account or posting Finance.

`Waktu Pesanan Dibuat` remains the operational date. `Waktu Selesai` is the revenue source date. Settlement and payout dates are kept on their own source records, and a return date is kept on the return source.

## Settlement and fees

`OmniSettlementImportBatch` and `OmniSettlement` are separate from revenue. The parser uses explicit normalized header aliases, including the accepted SMB headers and canonical equivalents. Required settlement date is parsed using the existing Indonesian/date and numeric normalization rules. Unknown gross, refund, adjustment, or component values remain `NULL`.

Settlement identity includes event type, marketplace, Store source name, settlement reference (or source row), order reference, settlement date, and source row identity. Re-importing the same byte payload returns the existing batch. A materially changed row with the same source identity is preserved as a `SOURCE_CHANGED` conflict and does not overwrite the accepted row. Fees are separate `OmniSettlementFee` records and retain fee type, amount, source key, and raw row metadata.

Matching requires legal entity, canonical Store, marketplace scope, and external order reference. It does not match by amount or display name alone. One revenue event may have multiple settlement rows. Reconciliation reports `SETTLEMENT_PARTIAL` until settled-to-date reaches the known gross source amount, and reports `SETTLEMENT_OVER` if it exceeds it.

## Adjustments

`OmniAdjustmentSource` preserves legal entity, Store, marketplace, order, optional settlement, typed adjustment, amount, date, source row, and raw metadata. The deterministic source identity includes reference/source row, adjustment type, and order, so different adjustment types on one order remain distinct. Identical retries return the original source; changed data for the same identity raises a reviewable validation error. No adjustment posts Finance directly.

## Real BigSeller Return mapping

The sanitized regression fixture mirrors the audited real export: 42 columns, numeric `Jumlah`, TikTok/Shopee examples, Store/order/package/SKU linkage, no Variation column, blank observed aftersales/refund/reason/stock-addition fields, and a package split across multiple SKU rows. `ID Purna Jual` is retained as blank source evidence where blank; no fake global return ID is generated.

Each imported row receives technical provenance `OMNI_RETURN|ROW:<source row>`, scoped by legal entity and import batch. If a future source populates `ID Purna Jual`, it can be retained as the preferred external identifier, but it does not replace source-row provenance. Return linkage uses legal entity + canonical Store + marketplace + external order number, then exact SKU. Because Variation is absent, multiple original lines with the same SKU resolve to `AMBIGUOUS_ORDER_LINE`; the importer never guesses a variation or Item.

Return fields are kept separate: source/requested quantity, inspected quantity, Quality accepted quantity, Warehouse returned quantity, refunded quantity, and authoritative refund amount. Marketplace statuses are evidence only; they are not interpreted as Quality `PASS` or a posted stock receipt.

## Quality and Warehouse boundary

An unambiguous mapped return may create a draft `MARKETPLACE_RETURN` Quality candidate. It does not create a Quality result. A formal posted Quality result remains one of `PASS`, `HOLD`, `REJECT`, `REWORK`, or `LEGACY_UNMAPPED`. Only posted `PASS` quantity can call the Warehouse-owned return receipt adapter. A receipt is idempotent, cannot exceed source quantity or accepted PASS quantity, and uses pending valuation rather than inventing zero cost when outbound valuation is unavailable.

Return/refund source remains a follow-up to the original revenue event. It never deletes or rewrites the original revenue history. A refund amount may be unknown, and physical return and commercial refund may occur independently.

## Reconciliation and payout handoff

Read-only reconciliation groups source amounts by Store and exposes completed revenue, settled source amount, unsettled source amount, fees, returns, refunds, adjustments, payout amount, unpaid marketplace-balance source amount, and actionable exceptions. Unknown financial components remain `NULL`/review rather than fabricated zeroes. The source states include completed-not-settled, settlement match/partial/unmatched/over, source changed, return/refund pending, payout pending/match, ambiguous return line, unmatched payout, and blocked mapping.

`OmniPayoutSource` stores Store, marketplace, payout reference/date/amount/currency, settlement references, source provenance, and reconciliation state. Exact settlement-reference total matching produces `PAYOUT_MATCH`; partial, unmatched, or over/under amounts remain pending/review. A payout is a Finance handoff candidate only; no Bank transaction or journal is created. Retries are unique by legal entity, payout reference, and source row identity.

## Finance boundary and candidates

Candidates are exposed for `OMNI_ORDER_COMPLETED`, `OMNI_SETTLEMENT`, and `OMNI_RETURN`. They include legal entity, Store, marketplace, order/source identifiers, applicable source date, amount components, currency, mapping keys/context, and source lineage. Actual journals, AR, marketplace balance control account, bank, payment, period close, and tax posting remain deferred to Phase 8. Missing mapping blocks posting readiness and never falls back to an arbitrary COA.

## Tests and migration

Phase 7A sanitized real-file tests remain in place. Phase 7B tests cover completion-date revenue, missing completion/status/store gates, order-level multi-line aggregation, idempotency, source-change conflicts, settlement fees and partial settlement, real return schema and row identity, absent Variation ambiguity, Quality `PASS` to Warehouse `RETURN_IN`, adjustment identity, and payout retry. The full project quality gate is run before checkpoint handoff.

New migrations add Phase 7B source models and the Warehouse return movement choice. Historical migrations `0001`–`0003` are not modified. No Finance posting schema is introduced.

## Deferred Phase 7C

POS, final Phase 7 analytics closure, and any Finance operational posting remain explicitly deferred. No POS navigation or POS workflow is included in this phase.
