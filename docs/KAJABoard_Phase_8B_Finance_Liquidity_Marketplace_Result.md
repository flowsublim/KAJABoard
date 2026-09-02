# KAJABoard Phase 8B — Finance Liquidity and Marketplace Result

Finance owns immutable LiquidityEntry and MarketplaceBalanceEntry projections. LiquidityAccount is a configuration master; transactional accounts still resolve through Finance COA Mapping.

Enabled: customer receipt, vendor payment against existing AP only, allocation and reversal; POS receipt/refund/reversal/cash variance; marketplace settlement, explicit fees, AR clearing, return/refund follow-up, linked adjustment, payout to explicit Bank, and controlled reversals. Whole Rupiah, source identity, idempotency, and mapping resolution apply.

Completed marketplace revenue remains its original AR/revenue event. Settlement clears AR; payout moves Marketplace Balance to Bank. A payment against recognized AP never recreates expense. A confirmed Purchase Order is a commercial commitment, not AP or a payable.

POS cash session is Omnichannel operational evidence. Finance Cash is the LiquidityEntry ledger. The Bank page is an accounting ledger, not bank-statement reconciliation. Warehouse remains the owner of inventory and COGS valuation.

Reconciliation exposes Journal, AR, AP availability, Inventory, Liquidity, and Marketplace Balance subledger facts. No AP facts or opening balances are fabricated.

Deferred to 8C: fixed assets, depreciation, wage payable, period controls, bank statement reconciliation, and full financial statements.
