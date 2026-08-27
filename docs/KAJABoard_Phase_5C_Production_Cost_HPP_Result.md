# KAJABoard Phase 5C - Production Cost / HPP Result

## Completed

Phase 5C provides an Accounts-owned Employee/PIC identity, effective-dated
Production tariffs, immutable labor cost snapshots, output-specific direct
extra costs, trusted overhead snapshots with monthly CUT_QTY allocation,
JASA_UMUM allocation read contract, Finance cost candidates, and explicit
versioned HPP/COGM snapshots.

## Rules and readiness

- PIECE_RATE is quantity times the dated tariff; missing tariff blocks posting.
- NO_WAGE is explicit and stores an intentional zero.
- Posted labor and direct cost sources are immutable; corrections append a
  reversal and replacement with reason, actor, timestamp, and idempotency.
- Confirmed PO lines are commitment-only (ELIGIBLE_COMMITMENT / NOT_POSTED).
  Actual overhead requires an active POSTED EXPENSE/SERVICE source,
  production-eligible cost center, and SnapshotProduction=true.
- CUT_QTY_MONTHLY allocates each source independently by active posted CUT
  quantity, with deterministic residual reconciliation and no-driver block.
- JASA_UMUM is allocated per accepted subcontract receipt by accepted output
  quantity; specific service remains tied to its output.
- Material reference cost is not material actual. Warehouse actual material and
  accepted finished-goods quantity are unavailable, so final COGM and unit HPP
  remain None with status INCOMPLETE.
- HPP reports are read-only. Snapshot creation/rebuild is an explicit action.

## UI and permissions

Implemented Production routes and permission-aware sidebar children: WIP
Produksi, Setor Gudang, Tarif Produksi, Biaya Langsung, and HPP / COGM.
Tariff and direct-cost mutations use modal forms; HPP is a read-only report with
an explicit snapshot action.

## Migrations

- `apps/accounts/migrations/0002_employee.py`
- `apps/production/migrations/0003_productionworkentry_employee_and_more.py`
- `apps/production/migrations/0004_productiondirectextracostreversal_and_more.py`
- `apps/production/migrations/0005_productiondirectextracostreversal_replacement_and_more.py`
- `apps/production/migrations/0006_productionoverheadsnapshot_accounting_treatment_snapshot_and_more.py`

## Tests

Full suite: 175 passed. Django, Ruff, diff, migration-drift, and fresh SQLite
migration checks passed.

## Boundaries and deferred work

No StockMovement, StockBalance, Warehouse receipt/accepted quantity, Quality
decision, Finance journal/AP/payment, cash/bank, or CPO fee is created.
Deferred downstream work is Warehouse actual valuation and finished-goods
acceptance (Phase 6), formal Quality inspection (Phase 6), inventory
valuation/revaluation integration, Finance journal/AP/payment consumption, and
CPO fee (Phase 6). Purchasing history and the legacy baseline are unchanged.
