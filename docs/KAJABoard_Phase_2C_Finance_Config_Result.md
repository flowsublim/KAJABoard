# KAJABoard Phase 2C Finance Config Result

**Phase:** 2C - Finance Configuration + Tax + Import Base  
**Branch:** main  
**Checkpoint base:** phase-2b-pass  
**Status:** Ready for owner review; not committed, not pushed, not tagged.

## Completed

- Added `PurchaseCategory` master with explicit `AccountingTreatment`.
- Added Finance-owned COA master and COA Mapping configuration.
- Added deterministic read-only Finance mapping resolver.
- Added conservative tax registration/configuration foundation.
- Added non-transactional import/export base with COA CSV template, preview, replay detection, and confirm path.
- Extended Master / Settings shell with Purchase Category, COA, COA Mapping, Tax Registration, and Import Batch screens.
- Added admin registrations, service-layer mutations, selector-layer reads, audit events, effective dating, and access-scope filtering.

## Files changed

- `config/settings/base.py`
- `config/urls.py`
- `apps/organizations/views.py`
- `apps/core/tests/test_master_ui.py`
- `templates/master/workspace.html`
- `apps/purchasing/**`
- `apps/finance/**`
- `apps/tax/**`
- `apps/data_exchange/**`
- `templates/purchasing/**`
- `templates/finance/**`
- `templates/tax/**`
- `templates/data_exchange/**`

## Migrations

- `apps/purchasing/migrations/0001_initial.py`
- `apps/finance/migrations/0001_initial.py`
- `apps/tax/migrations/0001_initial.py`
- `apps/data_exchange/migrations/0001_initial.py`

No accepted Phase 1, Phase 2A, or Phase 2B migration was modified.

## Models

- `PurchaseCategory`
- `COAAccount`
- `COAMapping`
- `TaxRegistration`
- `ImportBatch`
- `ImportRowResult`

## Services / Selectors

- Purchase Category create/update/deactivate/reactivate and effective lookup.
- COA account create/update/deactivate/reactivate and effective lookup.
- COA Mapping create/update/deactivate/reactivate and deterministic resolver.
- Tax Registration create/update/deactivate/reactivate and effective subject lookup.
- COA CSV template, preview, replay-aware batch registration, confirm valid rows, and CSV export helper.

## UI

- Purchase Category list/create/edit/lifecycle.
- COA list/create/edit/lifecycle.
- COA Mapping list/create/edit/lifecycle.
- Tax Registration list/create/edit/lifecycle.
- Import Batch list, COA template download, upload/preview, detail, and confirm.

## Tests run

- `python manage.py check`
- `pytest -q`
- `ruff check .`
- `ruff format --check .`
- `git diff --check`
- `python manage.py makemigrations --check --dry-run`
- Fresh SQLite database migration from zero with `python manage.py migrate --noinput`

Browser runtime was attempted for UI validation, but no browser backend was available in this environment. UI coverage is verified by Django test-client route rendering and template compilation.

## Business rules verified

- `EXPENSE` and `SERVICE` Purchase Categories require a Cost Center.
- `ASSET` Purchase Category does not create stock behavior.
- `SnapshotProduction=True` is allowed only for `EXPENSE`/`SERVICE` with production-overhead-eligible Cost Center.
- Purchase Category behavior is never inferred from category name text.
- Purchase Category effective period overlap is rejected.
- Inactive historical Purchase Category remains resolvable for a valid prior date.
- COA hierarchy cycles are rejected.
- Header COA accounts cannot be posting accounts.
- Inactive historical COA remains resolvable for a valid prior date.
- A non-overlapping successor COA version with the same account code resolves by as-of date.
- COA Mapping exact dimension beats `DEFAULT`.
- COA Mapping priority is deterministic; ambiguity at winning priority fails loudly.
- Resolver rejects inactive/invalid accounts at the as-of date.
- COA Mapping overlapping priority scope is rejected.
- Resolver returns mapping/account metadata needed for future snapshotting.
- Tax Registration has exactly one subject and does not duplicate NPWP/NITKU fields.
- Tax Registration overlap is rejected and historical inactive registration remains resolvable.
- COA import preview does not mutate COA master.
- COA import replay is detected by checksum.
- COA import confirm mutates only valid rows.
- Repeated confirm calls return the recorded batch result without importing again.
- Access scope is enforced by LegalEntity membership selectors.
- Important service mutations produce audit events.
- Legacy baseline remains exactly 50 files with aggregate SHA-256
  `66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2`.

## Unresolved

- Exact Indonesian tax regulatory validation, rates, Coretax exports, VAT invoices, and tax filing workflows remain deferred to the tax implementation gate.
- Final event/line-role catalog is representative and will be tightened when each transaction module is implemented.
- COA import currently supports CSV only; XLSX is deferred until business-approved templates exist.
- Project dimension is configuration-capable in COA Mapping, but no Project model or transaction exists in Phase 2C.

## Risks / follow-up

- Future transaction services must snapshot resolved mapping ID, account ID/code, line role, DC, selected dimension, priority, and master values at posting time.
- Finance period controls, Journal/GL, AR/AP, cash/bank, fixed assets, and tax posting are still future phases.
- Purchase transaction implementation must consume `PurchaseCategory` snapshots and must not infer treatment from names.
- Import framework should stay small; future transactional imports need separate idempotency and reconciliation rules.

## Explicit confirmations

- Phase 3 was not implemented.
- No Sales Order, invoice, purchasing transaction, SPK, production, POS, omnichannel order, stock movement, warehouse ledger, JournalEntry, GL, AR/AP, payment, settlement, tax filing, or fixed-asset transaction was implemented.
- No stock transaction was implemented.
- No Journal/GL transaction was implemented.
- No historical migration was modified.
- `legacy/smb_gas/` was not modified.
