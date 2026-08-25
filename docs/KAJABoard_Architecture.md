# KAJABoard Target Architecture

> **AUTHORITATIVE UPDATE (25 August 2026): OWNER APPROVED FOR PHASE 0 CLOSURE.** Actual evidence and owner decisions confirm the modular-monolith baseline; sections 16-17 define the binding foundation boundaries.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — architecture baseline only  
**Status:** DRAFT FOR REVIEW — NO DJANGO IMPLEMENTATION AUTHORIZED  
**Style:** Django modular monolith, PostgreSQL, server-rendered HTML/HTMX, PythonAnywhere Paid/WSGI

## 1. Architecture outcome

KAJABoard replaces spreadsheet-as-database and uncontrolled cross-module writes with one modular application and explicit ownership:

```text
Users / Imports / Scheduled Commands
                │
         Django views/forms
                │
     Application services / workflows
        ┌───────┴────────┐
        │                │
Operational domains   Core controls
        │                │
        ├── candidates/events ──→ Warehouse (physical stock)
        └── business events ────→ Finance (accounting)
                │
             PostgreSQL
                │
      selectors/read models/reports
```

The architecture preserves accepted business results, not GAS functions, Sheet names/columns, or legacy UI structure.

## 2. Locked technology and deployment

| Concern | Baseline |
|---|---|
| Runtime/framework | Python 3.13 + Django 5.2 LTS |
| Production database | PostgreSQL; sole production source of truth |
| Web UI | Django Templates + HTMX + limited Alpine.js + Bootstrap 5/Tabler + KAJA tokens |
| Charts | Chart.js |
| Application style | Modular monolith; traditional WSGI |
| Initial hosting | PythonAnywhere Paid, custom domain, HTTPS, virtualenv, static/media configuration |
| Background work | Scheduled tasks/management commands only where useful; no ASGI/WebSocket dependency |
| Legacy after cutover | Read-only archive/migration reference after accepted reconciliation |

React, microservices, WebSocket dependency, direct marketplace/bank automation, and autonomous AI ledger mutation are outside the v1 baseline.

## 3. Module map and dependencies

```text
kajaboard/
├── config/
├── core/
│   ├── audit/
│   ├── workflow/
│   ├── approvals/
│   ├── documents/
│   ├── notifications/
│   ├── data_exchange/
│   └── idempotency/
├── accounts/
├── organization/
├── partners/
├── catalog/
├── masterdata/
├── sales/
├── projects/
├── incentives/
├── purchasing/
├── production/
├── warehouse/
├── quality/
├── omnichannel/
├── finance/
├── tax/
├── analytics/
└── reports/
```

### 3.1 Dependency rules

- Core controls are shared infrastructure and must not contain domain-specific posting logic.
- Master domains provide stable/effective configuration; transaction domains snapshot relevant values.
- Operational domains may reference stable master IDs and call published application contracts.
- Warehouse is the only writer of physical StockMovement and inventory quantity projection.
- Finance is the only writer of Journal/GL/AR/AP/cash/bank/marketplace balance/fixed asset/depreciation/closing.
- Quality owns the decision, not the movement.
- Reports/analytics query trusted sources and never mutate a ledger.
- Cross-domain behavior uses explicit service/event contracts; models are not modified through another domain's private helpers.
- Circular imports and “generic utils” containing business rules are prohibited.

## 4. Internal module structure

Preferred future shape, to be created only after Phase 0 acceptance:

```text
apps/<domain>/
├── models.py
├── services/
├── selectors/
├── forms/
├── views/
├── urls.py
├── admin.py
├── tests/
└── migrations/
```

| Layer | Responsibility | Prohibited |
|---|---|---|
| Views/forms | HTTP boundary, parsing, CSRF, server validation presentation, permissions, command invocation, response | Ledger rules, multi-model transaction logic, account selection |
| Application services | Business validation, state transition, atomic workflow, locking, idempotency, audit, owned contracts | UI formatting, hidden generic dispatch, cross-domain direct writes |
| Models/constraints | Persist owned facts, stable keys, unique/check/FK constraints, indexes | Workflow in `save()`, side-effect signals, hardcoded operational COA |
| Selectors | Bounded, optimized, permission-aware queries/read projections | Business mutation or posting |
| Templates/HTMX/Alpine | Render and interaction enhancement | Authoritative validation/calculation/state transitions |
| Reports/analytics | Reconciled read models and drill-down | Posting on view/generation |

## 5. Transaction and consistency model

### 5.1 Atomic commands

Critical commands run inside `transaction.atomic()` and lock contention-sensitive rows with `select_for_update()` or equivalent DB constraints. Examples include stock posting, fulfillment remaining qty, production WIP consumption, payment allocation, journal posting, mapping resolution at post time, POS, and sequence allocation.

A safe command pattern:

```text
authenticate + authorize
→ claim idempotency key
→ lock owned aggregate/control rows
→ re-read authoritative state
→ validate state, qty, amount, period, mapping
→ persist source/effect
→ persist audit and result
→ commit
```

Client/UI validation is convenience only; all controls execute on the server.

### 5.2 Idempotency and uniqueness

The database enforces unique source effects for stock, invoice post, journal, payment, marketplace import/settlement/adjustment/return, POS, handover/delivery, and incentive accrual. Retrying the identical key/payload returns the original result. Reusing a key with a different payload is a conflict and is audited.

### 5.3 Multi-domain orchestration

In the single PostgreSQL modular monolith, synchronous application services may share an atomic transaction while each domain still writes only its owned records. Where external files, scheduled work, or future asynchronous handling prevents atomic completion, use a durable inbox/outbox/repair state; never report success while a required stock/accounting effect is silently missing.

## 6. Warehouse architecture

```text
Source document/candidate
→ Warehouse validates source uniqueness, state, Item/UOM, warehouse, qty, stock and date
→ StockMovement PENDING
→ costing/valuation
→ StockMovement POSTED
→ source result + Finance valuation event
```

Only posted, non-reversed movements enter balance. `StockBalance` and availability are rebuildable projections, not competing truth. Every movement has source module/type/ID/line/key, transaction and posting dates, qty/UOM, unit cost/value, warehouse/location, actor and reversal link.

Default negative stock is rejected under row lock. A future override needs explicit approved policy, separate permission, reason, and audit. Stock opname posts only variance. A reversal preserves original rows and corrects ordered valuation in a controlled manner.

## 7. Finance architecture

```text
Operational Business Event
→ Finance inbox / command
→ validate source uniqueness and period
→ build Accounting Context
→ resolve effective Master COA Mapping
→ balanced Journal Candidate
→ approval (where required)
→ immutable Journal POSTED
→ GL and owned subledgers
```

Operational modules may define stable Event Codes and Line Roles; they do not choose COA codes/names. The resolver evaluates exact dimensions, controlled DEFAULT fallback, priority, effective dates, account activity, and mapping eligibility. Selected mapping context is snapshotted on journal lines.

Finance guarantees Debit = Credit, unique source posting, immutable posted journals, linked reversal, period validation, source traceability, analytical dimensions, and reconciliation of AR/AP/marketplace/inventory/bank/fixed-asset controls.

## 8. State, approval, correction, and audit

Critical aggregates use explicit transition services based on the Workflow Status Matrix. Transitions include expected current state/version to prevent lost updates. Approval rules are effective-dated and respect segregation of duties. Overrides require permission, approval/reason, and audit.

Draft data may be edited or voided under policy. Once a stock/accounting/business effect is posted, later correction creates a linked reversal, credit/return, or adjustment. Cascade deletion of posted history is prohibited.

Audit is append-only and records entity, record, action, before/after, fields, actor, time, request/session, reason, source, approval, and idempotency key.

## 9. Import and migration architecture

```text
Versioned template/source adapter
→ upload metadata + checksum
→ parse into staging rows
→ validate and map canonical IDs
→ preview errors/warnings
→ explicit confirm
→ domain services and idempotency
→ batch results
→ reconciliation
```

Import adapters normalize source variation without becoming alternative business logic. They cannot write stock or journals directly. File size/type/content are validated, and error logs do not expose secrets.

Initial migration covers master/config, opening balances, stock qty/value, AR/AP, marketplace controls, fixed assets, active projects, open orders/SPKs/WIP and commitments. Legacy history may remain read-only; open items must reconcile before cutover.

## 10. Query, performance, and caching

- Index canonical IDs, document/source keys, foreign keys, state/date, Store/order/SKU/variation identity, mapping resolution dimensions/effective dates, and reconciliation fields.
- Use pagination and bounded filters for all operational histories/reports.
- Use `select_related`/`prefetch_related` to prevent N+1; use bulk operations for validated imports.
- Re-read critical posting configuration and effective dates even when configuration caches exist.
- Cache only safe read/derived configuration. Cache is never a ledger or stock truth.
- Summary/materialized read models may accelerate reports but must reconcile and be rebuildable.
- Avoid full-table reads per request and GAS-style full-sheet scanning.

## 11. Security architecture

| Control | Baseline |
|---|---|
| Authentication | Django secure password hashing, secure sessions/cookies, login protection; 2FA for critical roles |
| Authorization | Role + Action + Data Scope, checked server-side and in selectors |
| Web protection | CSRF, output escaping, validated forms, secure headers/cookies, `DEBUG=False` |
| Secrets | Environment configuration; no credentials/Sheet IDs/secrets committed |
| Uploads/attachments | Type/size/content validation, checksum, authorization at upload and download |
| Financial/stock authority | Least privilege, separate override permissions, maker/checker where approved |
| Audit/logging | Application/error/admin/approval/posting logs without exposing secrets |
| Data retention | No silent deletion of posted stock/accounting or their source documents |

## 12. Reporting and document lineage

Read paths must support:

```text
Report → Account/measure → owned ledger/read row → event → source document → line
```

Examples:

- B2B: Customer/Project → Order → SPK/Purchase → Production/Maklun → Warehouse → Delivery → Invoice → AR → Payment → Journal.
- Marketplace: Import Batch → Order/line mappings → demand → packing/OUT → completion revenue/AR → settlement/balance → payout/bank.
- Return: original order/delivery/invoice → return → QC → Warehouse effect → Finance adjustment → reconciliation.

Financial statement definitions and report snapshots are versioned separately from COA and journal history. Generating a report or dashboard cannot trigger posting.

## 13. Deployment, operations, and recovery

Environments are Local, Staging, and Production. Production release requires backup, dependency installation, migrations, static collection, smoke tests, application reload, critical scenario checks, and stock/financial health checks. A rollback/runbook is required.

Minimum operations include application/error logs, daily database backup, periodic off-platform backup, media backup, pre-release/pre-migration backup, retention, tested restore, and restore runbook. Scheduled tasks may send reminders, suggest reconciliation, generate report snapshots, propose depreciation, or perform maintenance—but Finance posting does not happen merely because a report is opened.

## 14. Required architectural tests (future phases)

| Area | Minimum proof |
|---|---|
| Ownership | Operational service cannot create StockMovement/Journal outside owned contract; architecture review/static checks |
| Concurrency | Simultaneous delivery/packing/POS/payment cannot overconsume qty/open amount |
| Idempotency | Repeat critical request produces one source/effect |
| State | Illegal transitions and direct posted edits fail |
| Mapping | Missing/inactive/ambiguous mapping blocks post; no hardcoded accounts |
| Historical snapshot | Later master/rate/mapping change does not alter old transaction |
| Reversal | Original remains, linked correction reconciles quantity/value/subledger |
| Reporting | Read-only and totals reconcile/drill down |
| Security | Data scope, CSRF, upload, attachment, critical permissions and override audit |
| Performance | Representative volumes use bounded indexed queries without N+1/full scans |

## 15. UNRESOLVED architecture decisions

| ID | Question / source conflict | Affected modules | Stock impact | Accounting impact | Recommendation pending approval |
|---|---|---|---|---|---|
| U-ARC-001 | Actual legacy integrations, triggers, Sheet formulas, caches and cross-writes are unavailable. | All legacy-linked domains | Hidden stock sources/cross-writes may be missed. | Hidden posting/mapping behavior may be missed. | Obtain source freeze and create legacy integration/dependency appendix. |
| U-ARC-002 | Deployment database provisioning, backup destination, media storage, monitoring and secrets process on PythonAnywhere are not specified. | Config/Core/Operations | Restore failure could lose stock history. | Restore failure could lose ledger history. | Finalize during Phase 1 deployment design; do not store secrets in repo. |
| U-ARC-003 | Background workload sizes and maximum import/report volumes are unknown. | Data Exchange, Omni, Finance, Reports | Long imports could leave requests pending; owned transaction rules still apply. | Long settlement/report runs may affect cutoff and reconciliation. | Gather representative/peak volumes and set explicit synchronous/batch limits. |
| U-ARC-004 | Approval/segregation/data-scope matrix is missing. | Core and all transactional domains | Unauthorized movements/overrides possible. | Unauthorized journals/payments/close possible. | Obtain current roles and approved thresholds before Foundation sign-off. |
| U-ARC-005 | Valuation, backdating, QC routing, tax and multi-currency decisions are incomplete. | Warehouse, Quality, Finance, Sales, Purchasing, Omni | Receipt/issue valuation and acceptance timing are incomplete. | Cost, tax, currency and closed-period semantics are incomplete. | Resolve in Phase 0 review; do not implement speculative fields/logic as accepted behavior. |
| U-ARC-006 | Whether future external APIs require asynchronous delivery is out of v1 scope. | Integration boundary/all event producers | Future delivery failures could desynchronize candidates. | Future delivery failures could delay posting. | Keep event contracts explicit and modular; do not introduce distributed complexity now. |

## 16. Actual-evidence architecture delta

The source audit confirms the architecture direction and adds these mandatory design constraints:

1. **One stock command boundary.** The Warehouse V2 contract's lock, deterministic source key, positive quantity and negative-stock guard are the behavioral seed. Sales, Purchasing, Production, QC and POS may not retain direct movement writers.
2. **One accounting ingestion boundary.** Finance source readers are not a GL. Operational events must resolve through Accounting Context + effective Master COA Mapping into immutable journal header/lines and owned AR/AP/cash/marketplace subledgers.
3. **Atomic modular-monolith orchestration.** POS and other synchronous cross-domain commands run in one PostgreSQL transaction where possible. The legacy pattern of writing stock then another spreadsheet is prohibited. Durable outbox is needed only if a later external boundary requires it.
4. **Stable transaction line identity.** Delete/recreate Sheet editing in Sales, Purchasing and Production proves line IDs cannot be inferred from row position, item name or document number.
5. **Command/query separation.** Summary rebuilds, COGS syncs, data repairs and reports are explicit commands/jobs; ordinary selectors and report refreshes cannot mutate ledger/source history.
6. **Immutable cost history.** Production/Warehouse cost sync may not overwrite posted movement value. Corrections require revaluation/adjustment documents and Finance effects with period validation.
7. **Versioned import adapters.** Omni imports require channel schema profiles, source-row identity, raw payload retention, completion timestamp, quantity triplet, mapping snapshot, and batch/row idempotency.
8. **Versioned read caches.** Omni summary V3/raw fallback demonstrates the need for cache schema version, source freshness, rebuild audit and safe fallback; cache never becomes ledger truth.
9. **Centralized auth/config.** Hardcoded spreadsheet IDs/shared HMAC secret and copied module security helpers are legacy deployment workarounds. Secrets are environment-managed; permission checks are server-side Role + Action + Data Scope.
10. **Audited maintenance jobs.** COA repair, bank compaction/date repair, Omni date repair and summary rebuild become explicit, permissioned, dry-run-capable migration/admin jobs if needed. Destructive reset helpers are not application features.

### 16.1 External/technical dependencies discovered

| Legacy dependency | Target treatment |
|---|---|
| Google Sheets cross-file routing via Master_Module | Replace with domain services/FKs; retain external source IDs for migration traceability. |
| Google Drive/public photo URLs and PDF conversion | Private validated media storage; document renderer; no public-by-default evidence. |
| Browser PDF.js CDN with Drive fallback for bank PDF | Pin/host approved parser or server-side library; preserve verified totals/count/balance contract. |
| Browser popup/iframe print | Server-rendered print views/PDF option while preserving A4/4x6 layouts. |
| HTML5 camera/scanner in Return QC | Progressive scanner component with manual fallback and duplicate guard. |
| No trigger definitions supplied | Do not assume cron. Every scheduled job requires explicit schedule, owner, retry and observability design. |

### 16.2 Owner-approved foundation contracts

The eight former blockers are resolved without requiring a different foundation architecture:

- the official baseline and hashes are fixed by `KAJABoard_SMB_GAS_Legacy_Evidence_Manifest.md`;
- import architecture supports effective `MarketplaceStatusMap`, valid Waktu Selesai, quantity triplet, Store/accounting mapping and unique revenue source;
- Sales invoice policy supports default delivery basis plus audited Sales-Order exception, while proforma remains outside Finance posting;
- migration staging supports deterministic legacy QC mapping with review-only `LEGACY_UNMAPPED` and explicit purchase-category treatment mapping;
- cost architecture supports item attribution, versioned shared allocation rules/snapshots, accrued-source uniqueness, and immutable revaluation documents;
- period architecture distinguishes OPEN from CLOSED/LOCKED and posts locked-period corrections into authorized open periods with original references;
- POS architecture includes actual Item, explicit tender, atomic/idempotent owned effects, reversal/return documents and OPEN/CLOSED cash sessions.

The exact shared SPK/production cost allocation formula is a **DEFERRED IMPLEMENTATION DETAIL** for the Production/HPP implementation gate. Because rule version, basis, per-item result and historical snapshot are already required, choosing the formula later does not require a Phase 1 foundation redesign.

## 17. Evidence-based phase gate

**PHASE 0 GATE = PASS. Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.** The architecture is ready for Phase 1 foundation work after a separate explicit authorization. No scaffold or application implementation has been started.

## 18. Historical provisional phase discipline (superseded)

This document describes the approved target direction only. No project scaffold, model, migration, endpoint, service, or deployment configuration has been created. Phase 1 remains prohibited until all Phase 0 artifacts are reviewed, the missing legacy baseline is audited, and the gate is explicitly accepted.
