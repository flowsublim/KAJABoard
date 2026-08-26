# KAJABoard Phase 3B Delivery and Invoice Source Result

**Phase:** 3B - Sales Delivery, Partial Fulfillment, and Invoice Source  
**Branch:** main  
**Checkpoint base:** phase-3a-pass  
**Status:** Ready for owner review; not committed, pushed, or tagged.

## Completed

- Added canonical `SalesDelivery` / stable `SalesDeliveryLine` commercial Surat Jalan records with configured, atomic document numbering.
- Added partial fulfillment derived from valid `POSTED` delivery lines by stable `SalesOrderLine` identity. A Surat Jalan may aggregate confirmed lines from multiple Sales Orders for one legal entity/customer.
- Added controlled delivery `DRAFT -> POSTED -> CANCELLED` operations, locking source lines at post time. Posted delivery exposes deterministic Warehouse Goods Issue candidates only; cancelled posted delivery exposes a future Warehouse correction candidate.
- Added canonical `SalesInvoice` / stable `SalesInvoiceLine` commercial sources with delivery-based invoicing as the default, controlled Sales-Order invoice exception, and explicit non-posting Proforma.
- Added exact Invoice -> Delivery Line -> Sales Order Line lineage, Decimal totals/snapshots, availability controls, cancellation release, and a read-only future Finance candidate selector.
- Added scoped Sales Delivery and Invoice Source operational screens plus print-friendly Surat Jalan, Invoice, and Proforma HTML views.

## Files changed

- `apps/sales/models.py`, `admin.py`, `forms.py`, `views.py`, `urls.py`
- `apps/sales/services/deliveries.py`, `apps/sales/services/invoices.py`
- `apps/sales/selectors/deliveries.py` and Sales selector exports
- `apps/sales/migrations/0002_salesdelivery_salesdeliveryline_salesinvoice_and_more.py`
- `apps/sales/tests/test_delivery_invoice.py`, `apps/sales/tests/test_sales_ui.py`
- `templates/sales/*`, `templates/base.html`, `templates/master/workspace.html`
- `apps/core/tests/test_master_ui.py`, `apps/channels/tests/test_ui.py`

## Migrations

- Added `apps/sales/migrations/0002_salesdelivery_salesdeliveryline_salesinvoice_and_more.py`.
- New Phase 3B index and constraint names are PostgreSQL/Django-safe (30 characters or fewer).
- No accepted historical migration was modified.

## Tests run

- `python manage.py check`
- `pytest -q` - 134 passed
- `ruff check .`
- `ruff format --check .`
- `git diff --check`
- `python manage.py makemigrations --check --dry-run`
- Fresh SQLite migration from zero with `python manage.py migrate --noinput`

## Business rules verified

- Partial delivery, multiple partial deliveries, and exact stable Sales Order line lineage are supported.
- One Surat Jalan can include multiple Sales Orders for the same customer; mixed customer/entity sources are rejected.
- DRAFT delivery does not consume fulfillment; POSTED does; cancellation restores derived remaining quantity and preserves history.
- Delivery posting is idempotent and only makes deterministic Warehouse candidate data available. No stock mutation is performed.
- Delivery-based invoice is the default. Delivery invoice availability derives from posted delivery lines less valid confirmed invoice quantities.
- Sales-Order invoice is an explicit audited exception; Proforma is non-posting and does not consume invoice availability.
- Confirmed Delivery and Invoice source snapshots remain unchanged after master edits.
- Invoice confirmation exposes a Finance candidate only. No journal, AR, payment, or revenue record is created.
- Significant create, line change, post/confirm, and cancellation operations create append-only audit events.

## Unresolved

- Warehouse must later validate and post the issue/reversal candidates, including physical stock and reservation policy.
- Finance must later consume confirmed invoice candidates to create AR, journal, tax, revenue, and payment projections.
- Statutory tax automation remains deferred; Phase 3B preserves the accepted commercial tax snapshots only.

## Risks / follow-up

- Phase 3C remains responsible for Customer 360 and approved Finance exposure/credit-control integration.
- Warehouse and Finance should preserve the supplied deterministic source identities when their owned effects are implemented.

## Explicit confirmations

- Partial delivery is supported.
- Multiple Sales Orders for the same customer are supported in one Surat Jalan.
- Delivery lineage is exact.
- Delivery POST produces a Warehouse candidate only; no stock mutation exists.
- Delivery-based invoice is the default; Sales-Order invoice is a controlled exception.
- Proforma is non-posting.
- Invoice only exposes a Finance candidate; no journal, AR, payment, or revenue exists.
- Phase 3C is not implemented.
- No historical migration was modified.
- `legacy/smb_gas/` baseline remains unchanged.
