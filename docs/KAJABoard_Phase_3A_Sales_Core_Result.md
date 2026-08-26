# KAJABoard Phase 3A Sales Core Result

**Phase:** 3A - Sales Core  
**Branch:** main  
**Checkpoint base:** phase-2c-pass  
**Status:** Ready for owner review; not committed, pushed, or tagged.

## Completed

- Added canonical `SalesOrder` and stable `SalesOrderLine` commercial source records.
- Added configured, atomic `SALES_ORDER` numbering allocation with create/confirm idempotency support.
- Added Decimal line/order calculation, discount and explicit tax-rate snapshots, freight, and immutable confirmation snapshots.
- Added controlled `DRAFT`, `CONFIRMED`, `ON_HOLD`, and `CANCELLED` service transitions.
- Added future credit-context and confirmed-line handoff contracts without creating Finance or Warehouse effects.
- Added scoped operational Sales Order list, draft/header/line editor, detail, confirm, hold/release, and cancel screens.

## Files changed

- `apps/sales/**`
- `templates/sales/**`
- `config/settings/base.py`
- `config/urls.py`
- `templates/base.html`
- `templates/master/workspace.html`
- `static/css/kajaboard.css`
- `apps/core/tests/test_master_ui.py`
- `apps/channels/tests/test_ui.py`

## Migrations

- `apps/sales/migrations/0001_initial.py`

No accepted Phase 1, Phase 2A, Phase 2B, or Phase 2C migration was modified.

## Tests run

- `python manage.py check`
- `pytest -q`
- `ruff check .`
- `ruff format --check .`
- `git diff --check`
- `python manage.py makemigrations --check --dry-run`
- Fresh SQLite migration from zero with `python manage.py migrate --noinput`
- Legacy manifest verification: 50 files and aggregate SHA-256
  `66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2`

## Business rules verified

- Customer has an effective `CUSTOMER` role and belongs to the Sales Order legal entity.
- Items are effective, sales eligible, and in the same legal entity.
- Quantity is positive, price/discount/tax are non-negative, and totals use Decimal rounding.
- Configured number allocation is immutable, unique, and retry-safe.
- Confirmed documents snapshot commercial master values and cannot be commercially edited.
- Illegal transitions are rejected; hold/release and cancellation require controlled actions and audit evidence.
- Future downstream consumers can select confirmed stable lines with full ordered quantity as the current requirement.
- Credit hook exposes only master credit limit; it does not fabricate Finance exposure.
- No stock, warehouse, journal, GL, AR, payment, or revenue records are created.

## Unresolved

- Delivery/partial fulfillment, invoice source documents, customer 360, and Finance exposure remain later-phase work.
- Tax rates are explicit commercial snapshots only; statutory tax automation and tax posting are deferred.

## Risks / follow-up

- Phase 3B must maintain remaining fulfillment per stable Sales Order line and emit only Warehouse-owned issue candidates.
- Phase 3C must obtain outstanding exposure from Finance and apply approved hold/override controls.
- Future invoice services must retain Sales Order source snapshots and follow the approved delivery-first basis.

## Explicit confirmations

- Phase 3B and Phase 3C were not implemented.
- No stock transaction was implemented.
- No journal, GL, AR, or payment was implemented.
- No historical migration was modified.
- `legacy/smb_gas/` remains unchanged.
