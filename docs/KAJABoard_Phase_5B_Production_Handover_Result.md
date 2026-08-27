# KAJABoard Phase 5B — Production Handover Result

## Completed

- Added Production-owned `ProductionWarehouseHandover` and stable multi-output lines.
- Added DRAFT → READY_FOR_GUDANG (Siap Gudang), partial handover, line-level reversal, and idempotent readiness transitions.
- Added Production handover list/detail, modal actions, print preview, sidebar child, and routing smoke coverage.

## Models

- `ProductionWarehouseHandover`
- `ProductionWarehouseHandoverLine`
- `ProductionWarehouseHandoverLineReversal`

All use UUID identities, Decimal quantity, `PROTECT` lineage, constraints, and named indexes.

## Partial handover and WIP

Available Handover is calculated per WorkOrderOutput:

`Posted QC − active READY handover − active Reject QC`

Multiple lines for the same output are aggregated before marking a handover ready. Partial releases can therefore occur across many handover documents without one output offsetting another.

## Line reversal

READY lines are immutable. A correction appends a reversal against one stable original line, with a reason, actor, timestamp, audit record, and idempotency key. Sibling lines remain active. The Phase 6 Warehouse-result guard has a dedicated service-boundary extension point.

## Warehouse candidate

`warehouse_receipt_candidates()` provides deterministic `PROD_HANDOVER|<handover-line UUID>` rows for Warehouse. It includes SPK/output/project/sales/item/snapshot/quantity/date lineage, marks the source `READY_FOR_GUDANG`, and returns `unit_cost=None`, `cost_status=UNAVAILABLE`.

It creates no Warehouse receipt, StockMovement, StockBalance, reservation, accepted quantity, or valuation.

## Production completion readiness

The selector evaluates every output independently. It reports cut/sew/qc/reject/handover quantities, stage availability, target variance, and a Production-owned readiness result. Readiness requires per-output conservation:

`Cut = READY handover + Reject Cut + Reject Sew + Reject QC`

and zero remaining sewing, QC, and handover WIP. It does not mutate Purchasing WorkOrder planning history and does not claim Warehouse acceptance.

## Permissions and UI

Standard Django view/add/change permissions apply to handovers, with explicit `ready_productionwarehousehandover` and `reverse_productionhandoverline` permissions. Legal-entity scoped selectors remain authoritative. The Production sidebar now presents WIP Produksi and permission-aware Setor Gudang.

## Migration

- `apps/production/migrations/0002_productionwarehousehandover_and_more.py`

## Tests

Coverage includes partial handover, same-output aggregate validation, multi-output entries, output isolation, readiness, QC reversal safety, reject/handover shared availability, line reversal/idempotency, cost-unavailable Warehouse candidates, and route/sidebar authorization.

## Boundaries

- Warehouse acceptance still unavailable.
- No stock mutation or accepted quantity is fabricated.
- No final HPP/COGM or Finance posting.
- No WorkOrder planning-state rewrite.
- Legacy baseline unchanged.

## Deferred

- Warehouse acceptance / stock receipt / Phase 6
- formal Quality inspection / Phase 6
- labor/tariff / Phase 5C
- direct extra cost / Phase 5C
- overhead allocation / Phase 5C
- HPP/COGM / Phase 5C
- CPO fee / Phase 6
