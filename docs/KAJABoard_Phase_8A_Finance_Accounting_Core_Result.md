# KAJABoard Phase 8A — Finance Accounting Core Result

## Scope and ownership

Phase 8A establishes the Finance-owned accounting core without moving physical
inventory, commercial source documents, or later cash and settlement concerns
into Finance. Operational domains remain the source owners; Finance consumes
approved candidates through explicit services. Warehouse remains the sole
owner of `StockMovement`, inventory quantity, and valuation facts.

The implementation adds Finance-owned `JournalEntry`, `JournalLine`,
`ReceivableEntry`, and `PayableEntry` foundations. General Ledger is a
read-only projection of posted Journal Lines rather than a second mutable
ledger. Source keys, source document identity, event codes, accounting dates,
account snapshots, mapping snapshots, actor, and posting timestamp preserve
drill-down lineage.

## Posting and COA mapping

`post_journal` is the explicit atomic posting boundary. It requires balanced
whole-Rupiah lines, rejects meaningless or both-sided lines through service and
database constraints, and uses the existing Phase 2C Finance Mapping Resolver.
Transactional account codes, names, and IDs are not hardcoded. Missing or
ambiguous mapping blocks the operation as `BLOCKED_MAPPING` before journal or
subledger side effects are committed.

The legal-entity/source-key uniqueness constraint makes retries idempotent.
Resolved account and mapping facts are snapshotted on each Journal Line so a
later master-data change does not rewrite historical meaning. Posted history
is treated as immutable by the Finance service contract; corrections use
`reverse_journal`, which creates a linked compensating journal with swapped
debit and credit amounts and preserves original account/mapping evidence.
Reversal retry returns the existing compensating result. AR reversal entries
are created consistently; the same architecture is available for AP when an
approved payable source exists.

## Enabled source contracts

### Sales invoice

An eligible confirmed B2B Sales invoice candidate posts revenue and a
Finance-owned Receivable Entry atomically. The accounting date is the Sales
`invoice_date`, not `created_at`. Customer and invoice lineage are retained.

### Omnichannel completion

An eligible `OMNI_ORDER_COMPLETED` revenue event posts marketplace revenue and
a Store-context Receivable Entry atomically. The accounting date is
`Waktu Selesai` / Completion Date. Order Date remains an operational date and
is never substituted for revenue accounting. Settlement, payout, and later
return/refund events do not replace the original completion journal.

### Warehouse valuation

Finance consumes an authoritative posted Warehouse movement only when its
valuation status is ready and `total_value` is available. The exact Warehouse
valuation amount and transaction date are used; Finance does not recalculate
weighted average and creates no quantity ledger or `StockMovement`. An IN
valuation debits the semantic `INVENTORY` role and credits
`INVENTORY_OFFSET`; an OUT valuation reverses those semantic directions. Both
roles still resolve through COA Mapping. Pending or unavailable valuation is
reported as `PENDING_SOURCE` and does not become a zero journal.

### POS boundary

Existing durable POS candidates are classified by the Phase 8A boundary.
Revenue, COGS, and tender candidates remain deferred where a balanced entry
would require Cash, Bank, Payment, or tender-clearing semantics. No balancing
cash/bank account is invented. Warehouse-authoritative POS valuation can be
consumed through the Warehouse valuation contract when its facts and mappings
are complete.

## AR, AP, GL, and reconciliation

AR retains customer or marketplace Store debtor context, original/open amount,
currency, accounting date, journal, and source lineage. Clearing and payment
are not part of Phase 8A.

AP has a durable Finance-owned foundation and read page, but no operational
payable adapter is enabled because the repository has no approved vendor bill
or accrual source contract. A **CONFIRMED Purchase Order is a commercial
commitment only** and creates neither Journal Entry nor Payable Entry. The UI
and reconciliation report this unavailable source explicitly rather than
presenting fabricated zero business activity.

The read-only reconciliation selector reports:

- posted journal debit versus credit;
- AR control-role net amount versus Receivable Entry detail;
- AP as pending until an approved operational payable source exists;
- inventory-role GL value versus authoritative Warehouse valuation sources.

Statuses are `MATCH`, `DIFFERENCE`, and `PENDING_SOURCE`; mapping failures are
blocked before posting as `BLOCKED_MAPPING`. Read selectors and report GETs
never create accounting entries.

## Operational UI and permissions

The Operasional sidebar now contains Finance: Journal, General Ledger,
Accounts Receivable, Accounts Payable, and Reconciliation. These full-page
read views use legal-entity scoping and the existing journal/subledger
selectors. Finance Configuration remains separately under Master &
Konfigurasi with Chart of Accounts and COA Mapping. Route-specific namespaces
prevent both parents from opening together.

The pages use `view_journalentry`, `view_gl`, `view_ar`, `view_ap`, and
`view_reconciliation`. Existing `post_journal` and `reverse_journal`
permissions remain service/action controls; this closure does not add manual
posting forms.

## Migration and tests

`finance.0002_journalentry_journalline_payableentry_and_more` adds the journal
and subledger models, source uniqueness, balance and line-side constraints,
reversal linkage, and Finance operational permissions. Historical migrations
are unchanged.

Focused Phase 8A tests cover posting, mapping failure, idempotency, reversal,
Sales and Omnichannel adapters, Completion Date, Warehouse valuation and
pending valuation, POS deferral, Purchase Order non-AP behavior, selectors,
reconciliation, permission-aware navigation, route separation, source
rendering, and side-effect-free GETs.

## Explicitly deferred

Phase 8A does not implement operational Purchasing payable sources, Payment,
Cash, Bank, marketplace settlement accounting, Marketplace Balance, payout
accounting, Fixed Assets, depreciation, wage payable, period close/reopen,
bank reconciliation, financial statements, or tax export. These remain Phase
8B/8C or later work and are not represented as completed accounting facts.
