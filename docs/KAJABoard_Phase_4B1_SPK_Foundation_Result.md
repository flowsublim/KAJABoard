# KAJABoard Phase 4B1 - SPK Foundation Result

## Completed

- Canonical SPK/Work Order planning records with configured `WORK_ORDER` numbering.
- INTERNAL and SUBCONTRACT types, effective vendor validation, Sales Order/Project lineage, and controlled `DRAFT -> SUBMITTED -> APPROVED -> VOID` lifecycle.
- Multiple stable output lines and explicit per-output material allocations with nullable reference-cost snapshots.
- Future Production and Subcontract read selectors for approved SPKs only.
- Permission-scoped SPK list/detail, modal forms/actions, and modal print preview.

## Models

- `WorkOrder`, `WorkOrderOutput`, and `WorkOrderMaterialAllocation` in `purchasing`.
- Each allocation links one material quantity directly to one output line. There is no flat material-only SPK list.

## State Machine

- Draft records are editable; submitted and approved planning is frozen.
- Approval requires output lines and valid subcontract vendor/lineage.
- Void requires a reason and retains the historical record.

## Future Contracts

- Approved INTERNAL SPKs are exposed as Production planning sources.
- Approved SUBCONTRACT SPKs are exposed as sources for the later 4B2 dispatch/receipt work.

## Files Changed

- `apps/purchasing/models.py`, `services/work_orders.py`, selectors, forms, views, URLs, templates, sidebar, and modal routing.
- `apps/purchasing/tests/test_work_orders.py`.

## Migrations

- `apps/purchasing/migrations/0003_phase_4b1.py` only. No accepted historical migration was changed.

## Tests

- Focused SPK tests cover type/vendor validation, idempotent creation, multiple outputs, explicit pairing, approved immutability, void control, and future selectors.

## Deferred

- No Kirim Bahan, Terima Maklun, Warehouse issue/receipt candidate, physical stock mutation, Production WIP, HPP allocation, supplier payable, Finance AP/journal/payment, or attachment subsystem is implemented.
- Reference image/attachment support is deferred because no reusable attachment foundation exists.

Legacy baseline remains unchanged.
