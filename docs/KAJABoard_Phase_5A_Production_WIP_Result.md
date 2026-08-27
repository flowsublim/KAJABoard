# KAJABoard Phase 5A — Production WIP Result

## Completed

- Added the `production` modular Django domain for internal WIP only.
- Consumes only same-entity, `APPROVED` `INTERNAL` Work Orders and their stable WorkOrderOutput identities.
- Added Potong (`CUT`), Jahit (`SEW`), and QC & Packing (`QC_PACKING`) work entries, plus stage-specific reject entries.
- Added production sidebar, WIP list/detail pages, and modal-triggered mutation entry points.

## Models

- `ProductionWorkEntry` / immutable posted `ProductionWorkLine`
- `ProductionRejectEntry` / immutable posted `ProductionRejectLine`
- one-to-one, append-only work/reject line reversal records

All business records use UUID identities, Decimal quantities, explicit constraints, and `PROTECT` relationships.

## Stages and WIP formulas

- Available Sewing = posted Cut − posted Sew − active Reject Cut
- Available QC = posted Sew − posted QC − active Reject Sew
- QC-ready = posted QC − active Reject QC

All calculations and posting validation are per stable WorkOrderOutput. Multi-line requests for one output are aggregated before validation.

## Reject design

Reject quantities are positive, reason-required records at CUT, SEW, or QC_PACKING. They change only derived production WIP. They do not create a Warehouse transaction, stock mutation, loss journal, or Quality decision.

## Multi-item and correction design

One work or reject entry supports multiple output lines. Posted lines cannot be edited through services. A correction creates a reversal tied to exactly one original line; sibling lines remain posted. Reversal recalculates locked WIP and refuses a change that would overconsume a downstream stage.

## Material issue candidate

`material_issue_candidates()` exposes a deterministic `PROD_MATERIAL_REQ|<allocation UUID>` read contract from approved internal WorkOrder material allocations. It includes lineage, snapshots, planned quantity, nullable reference cost, and active state. It does not reserve or issue physical inventory.

## Permissions and UI

The domain supplies view/add/change defaults plus explicit post and line-reversal permissions for work and rejects. Queries use legal-entity scope. The Production sidebar appears only for users with Production view permission; direct routes retain permission denial.

## Files changed

- `apps/production/` domain, services, selectors, forms, routes, tests, and migration
- application settings/routes, home module cards, and permission-aware sidebar
- Phase 5A result document

## Migrations

- `apps/production/migrations/0001_initial.py`

## Tests

Focused coverage verifies source eligibility, item-level WIP, multi-line aggregate validation, rejects, material candidate context, sibling-safe reversal, idempotency, routing/sidebar permission boundaries, and no resulting physical/financial behavior in the production service path.

## Deferred

- ProductionWarehouseHandover / Phase 5B
- Warehouse acceptance / Phase 6
- labor/tariff / Phase 5C
- direct extra cost / Phase 5C
- overhead allocation / Phase 5C
- HPP/COGM / Phase 5C
- formal Quality inspection / Phase 6

Only INTERNAL SPK is consumed; WIP is item-level and stable-line-based. No physical stock mutation, Finance posting, Handover transaction, or final HPP exists. No historical migration was modified and the legacy baseline remains unchanged.
