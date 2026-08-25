# KAJABoard Phase 0 Readiness and Review

> **AUTHORITATIVE UPDATE (25 August 2026): ACTUAL EVIDENCE AUDIT COMPLETE; OWNER APPROVED FOR PHASE 0 CLOSURE.** Section 8 supersedes all former source-missing/blocker conclusions. Phase 0 passes; Phase 1 still requires a separate explicit start instruction.

**Current authoritative status:** ACCEPTED - PHASE 0 CLOSED; PHASE 1 NOT STARTED.  

**Phase:** 0 — Source Freeze & Functional Audit  
**Status:** DRAFT — DOCUMENT SET PRESENT; SOURCE-FREEZE GATE BLOCKED  
**Baseline date:** 25 August 2026  
**Scope:** review control for the required Phase 0 artifacts and official evidence manifest; this document does not itself start Django implementation.

## 1. Current readiness outcome

All nine required Phase 0 artifacts are present. The function inventory copied into Project Plan §40 is fully represented and classified: 96 of 96 names, comprising 13 `RETAIN`, 52 `UPGRADE`, and 31 `REMOVE-DEADCODE` decisions.

This is **plan-inventory coverage only**. The repository does not contain the actual SMB GAS/UI source, accepted patch files, Sheet schemas/formulas, representative data, deployed-version inventory, triggers, or accepted print samples. It is therefore not possible to prove that the 96 plan-listed names are the complete legacy endpoint/use-case population or to verify the inferred call sites, validations, reads, writes, stock effects, accounting effects, and exception paths.

Phase 0 is ready for structured evidence intake and stakeholder review, but it is not accepted. Phase 1 remains prohibited.

## 2. Required artifact status

| Required artifact | Present | Current review purpose | Acceptance blocker |
|---|---:|---|---|
| `KAJABoard_Business_Process_Map.md` | Yes | End-to-end business flows and locked invariants | Missing legacy workflow/action evidence and open transaction semantics |
| `KAJABoard_Module_Ownership.md` | Yes | Sole-ledger boundaries and domain decision rights | Missing stewards, approval matrix, QC routing, and verified cross-writes |
| `KAJABoard_Data_Dictionary.md` | Yes | Canonical conceptual vocabulary and sources of truth | Missing Sheet/column/formula mapping and representative data |
| `KAJABoard_Event_Matrix.md` | Yes | Operational, Warehouse, and Finance event contracts | Missing actual triggers/payloads plus open timing/valuation/disposition rules |
| `KAJABoard_Workflow_Status_Matrix.md` | Yes | Locked and proposed controlled states/transitions | Missing actual status strings, UI guards, approval and failure states |
| `KAJABoard_Legacy_Endpoint_UseCase_Matrix.md` | Yes | 96 plan-listed functions classified with target outcomes/tests | Actual legacy function/use-case population is unavailable |
| `KAJABoard_Functional_Parity_Register.md` | Yes | Consolidated capabilities, acceptance evidence, and decisions | All rows remain globally source-blocked; no stakeholder acceptance recorded |
| `KAJABoard_Architecture.md` | Yes | Target modular-monolith and ownership baseline | Legacy integrations and several operational policies remain unresolved |
| `KAJABoard_UI_Design_System.md` | Yes | Interaction, state visibility, error, print, and accessibility baseline | Missing legacy UI/prints, branding, roles, devices, and terminology approval |

## 3. Evidence freeze intake manifest

The supplied legacy package should be read-only, version-identifiable, and safe to audit. Secrets, credentials, personal data, and production IDs may be redacted, but redaction must preserve field shape and relationships.

### 3.1 GAS and UI source

For Penjualan, Purchasing, Produksi, Omnichannel, and Gudang provide:

- every `.gs`, HTML, JavaScript, CSS, manifest, print template, and shared library version;
- the deployed GAS version and deployment identifier or a redacted stable reference;
- installable, edit, change, form-submit, and time-driven trigger inventory;
- public functions, private helpers containing business rules, and UI `google.script.run` call sites;
- module navigation/bootstrap behavior and any cache/property-service usage;
- generated documents, exports, email/download actions, and report side effects.

### 3.2 Accepted decisions and patches

- accepted patch/audit files with date, author/approver, and applicability;
- a precedence record where more than one patch changes the same behavior;
- known defects, operational workarounds, exceptions, and intentionally retired use cases;
- evidence for the accepted newer Sales, Purchasing, Production, Omni/POS, Warehouse, Master, and accounting behavior referenced by the Project Plan.

### 3.3 Sheets and data behavior

For every referenced workbook/tab provide:

- workbook/module purpose and owning team;
- tab names, headers, data types as observed, key/composite-key assumptions, null/blank conventions, and status values;
- formulas, array formulas, named ranges, protected ranges, validations, filters, and lookup tables;
- cross-workbook reads/writes and external IDs with secrets redacted;
- representative redacted rows for normal, partial, duplicate/retry, correction, return, and exception cases;
- known historical anomalies and manual reconciliation steps.

### 3.4 Operating evidence

- role/action/data-scope and maker/checker practice;
- document numbering and approval thresholds;
- accepted samples for Proforma, Invoice, Surat Jalan, Shipping Label, SOA, SPK/PDF, and material reports;
- representative BigSeller order, settlement, payout, return, and adjustment files;
- POS tenders, cash-session, void/return, tax/discount, device, printer/scanner, connectivity, and retry practice;
- transaction volumes, peak file sizes, reporting periods, and close/cutoff practice;
- KAJA brand assets, terminology, and required print fields.

### 3.5 Freeze record

Record the following before analysis begins:

| Field | Required value |
|---|---|
| Freeze ID | Stable identifier for this accepted legacy evidence package |
| Extracted at | Timestamp and timezone |
| Extracted by / approved by | Named custodian and business approver |
| Source project/version | Module, GAS project, deployed version, patch level |
| File manifest | Relative path, size, SHA-256, evidence classification |
| Workbook manifest | Redacted stable workbook reference, tabs, schema export SHA-256 |
| Redactions | What was removed or transformed and whether behavior/relationships remain auditable |
| Known omissions | Explicit missing source, version, file, sample, or operational evidence |

Do not commit credentials, access tokens, private keys, or unredacted sensitive business/personal data.

## 4. Source-audit execution sequence

1. Validate the evidence manifest, hashes, versions, omissions, and patch precedence.
2. Inventory every module, file, public function, trigger, UI action, formula-driven action, print/export, and manual use case.
3. Build `UI action → endpoint/function → reads → writes → validation → stock effect → accounting effect → exception` call paths.
4. Diff the actual inventory against the 96 plan-listed rows. Add and classify every delta; do not delete an existing row silently.
5. Verify each current `REMOVE-DEADCODE` decision has no hidden business behavior or side effect.
6. Reconcile legacy Sheet/status/source fields to the Data Dictionary and Workflow Status Matrix without treating spreadsheet structure as target architecture.
7. Reconcile every physical effect to a Warehouse event and every accounting effect to a Finance event using Master COA Mapping.
8. Update the Functional Parity Register with verified evidence, suspected defects, accepted upgrades, and concrete acceptance tests.
9. Obtain domain-owner review and disposition every blocking unresolved decision.
10. Re-run the Phase 0 gate checklist and record formal acceptance or remaining blockers.

## 5. Consolidated decision workstreams

The Functional Parity Register contains 12 consolidated unresolved decision families. Artifact-specific unresolved rows provide additional trace detail; they are not 12 independent approvals per document.

| Workstream | Consolidated IDs | Required decision owner(s) | Minimum evidence / outcome |
|---|---|---|---|
| Legacy completeness and precedence | `U-FP-001` | System owner + each domain owner | Accepted hashed freeze, call graph, patch precedence, all deltas classified |
| B2B invoice/revenue/COGS basis | `U-FP-002` | Sales + Finance + Warehouse | Allowed invoice sources, event dates, amount basis, exceptions, reversal behavior |
| Item/UOM/lot scope | `U-FP-003` | Catalog + Warehouse + Production + Finance | UOM precision/conversion; explicit lot/serial/expiry scope decision |
| Maklun allocation and acceptance | `U-FP-004` | Purchasing + Production + Quality + Warehouse + Finance | Shared-cost formula, rounding, QC/receipt/AP timing, correction behavior |
| Inventory valuation and backdating | `U-FP-005` | Warehouse + Finance | Effective valuation policy, ordered sequence, backdate/reversal/revaluation and closed-period treatment |
| QC and disposition | `U-FP-006` | Quality + Warehouse + Purchasing + Production + Finance | Inspection policy and quantity/cost/event route for PASS/HOLD/REJECT/REWORK/scrap/disposal |
| Marketplace completion/revenue basis | `U-FP-007` | Omnichannel + Finance + Tax | Raw-to-completed status mapping and gross/tax/discount amount definition per channel |
| Settlement and payout matching | `U-FP-008` | Omnichannel + Finance | Field roles/signs, IDs, tolerances, partial/split/difference and payout matching |
| POS controls | `U-FP-009` | Omnichannel + Warehouse + Finance + Tax | Tender/tax/discount/session/void/return/offline/retry control matrix |
| Production overhead allocation | `U-FP-010` | Purchasing + Production + Finance | Allocation bases, period/SPK/output windows, rounding, version and reversal propagation |
| Authorization and document control | `U-FP-011` | Management + Core + all domain owners | Roles/scopes, series, thresholds, maker/checker, overrides and segregation |
| Tax/regulatory verification | `U-FP-012` | Finance + Tax | Authoritative implementation-date rules and signed accounting/tax treatment |

## 6. Review order and sign-off record

Review in dependency order so later decisions do not rely on unsettled ownership or data meaning:

1. source freeze, legacy endpoint/use-case matrix, and patch precedence;
2. business process map and module ownership;
3. data dictionary and workflow/status matrix;
4. event matrix and accounting/stock boundaries;
5. functional parity register and acceptance-test coverage;
6. architecture and UI design system;
7. consolidated Phase 0 gate review.

| Review area | Required reviewer(s) | Status | Evidence / decision reference |
|---|---|---|---|
| Legacy source completeness | System owner + module custodians | `PENDING` | Not supplied |
| Sales / Projects | Sales owner + Finance/Warehouse consultees | `PENDING` | — |
| Purchasing / Maklun | Purchasing owner + Production/Quality/Finance/Warehouse | `PENDING` | — |
| Production / HPP | Production owner + Warehouse/Finance | `PENDING` | — |
| Warehouse / Inventory | Warehouse owner + Finance/Quality | `PENDING` | — |
| Omnichannel / POS | Omni/POS owner + Warehouse/Finance/Tax | `PENDING` | — |
| Finance / Tax / Closing | Finance and Tax owners | `PENDING` | — |
| Core permissions / approvals | Management + security/system owner | `PENDING` | — |
| UI / print / terminology | Business users + brand/document owner | `PENDING` | — |
| Final Phase 0 gate | Authorized business/system sponsor | `PENDING` | — |

Allowed review statuses are `PENDING`, `IN_REVIEW`, `CHANGES_REQUIRED`, and `ACCEPTED`. An `ACCEPTED` entry requires a named reviewer, date, and evidence/decision reference.

## 7. Phase 0 gate checklist

- [x] Nine required Phase 0 documents exist.
- [x] All 96 Project Plan §40 function names have a provisional `RETAIN`, `UPGRADE`, or `REMOVE-DEADCODE` classification.
- [x] Warehouse is the sole physical stock owner in every target artifact.
- [x] Finance is the sole accounting owner and auto-journals use Master COA Mapping.
- [x] Critical accepted Sales, Purchasing, Production, Warehouse, Omni, POS, return, idempotency, audit, and correction rules are mapped at plan level.
- [ ] Actual legacy GAS/UI/trigger/formula/manual-use-case inventory is frozen and hashed.
- [ ] Accepted patch versions and precedence are frozen.
- [ ] Every actual endpoint/use case is classified; all `REMOVE-DEADCODE` decisions are verified.
- [ ] Legacy Sheets/fields/statuses/formulas/cross-writes are mapped to canonical concepts.
- [ ] Stock and accounting effects are verified against actual source behavior.
- [ ] Required reports/prints/import/export/manual exceptions are verified.
- [ ] Blocking unresolved business decisions are approved and referenced.
- [ ] All nine artifacts have named stakeholder acceptance.
- [ ] Final Phase 0 gate acceptance is recorded.

## 8. Actual-evidence readiness review

### 8.1 Evidence audited

| Module | Files | Version/patch evidence |
|---|---:|---|
| Portal/auth | 4 | Portal v0.7 shared-secret clean |
| Master Data | 4 | Lean v0.2 core/database/numbering/stock service |
| Sales | 6 | Sales v1.6 print modal; DP no-double backend patch |
| Purchasing | 5 | v0.9.7 Production external read fix; v0.8 full-order COGM |
| Production | 4 | v0.9.8 stock cost ID format fix |
| Warehouse | 4 | v2.6 summary PR/lazy detail; stock contract V2/cost snapshot V1 |
| Quality/Return QC | 4 | v2.0.1 clean; Omni_Retur-only; return contract notes |
| Omnichannel/POS | 6 | v1.6.5 exact shipped; summary v1.6.4/V3; date key v1.6.2 |
| Finance/reporting | 12 | v1.9.3.4; daily reader v1.9.0; recon v1.8.7/v1.8.5 |
| Package README | 1 | evidence-use instruction only |
| **Total** | **50** | 49 module files + README |

The current read-only package is owner-designated as the official **SMB GAS Legacy Evidence Baseline**. Exact historical deployment provenance is not required. `KAJABoard_SMB_GAS_Legacy_Evidence_Manifest.md` records all 50 paths, byte lengths, SHA-256 values, the aggregate manifest hash and approved precedence. No trigger definition is included, so no schedule is inferred.

### 8.2 Function audit and classification

| Measure | Result |
|---|---:|
| Named server top-level declarations | 1,214 |
| Public declarations | 257 |
| Private declarations | 957 |
| Business-control private declarations flagged/reviewed | 532 |
| Named UI top-level declarations at column zero | 217 |
| Public declarations not present in the provisional 96-row inventory | 169 |

Evidence-based public declaration disposition: **39 RETAIN, 107 UPGRADE, 111 REMOVE-DEADCODE**. The large removal count consists chiefly of tests, GAS entry/template/display helpers and setup/adapters; it does not remove their business outcomes. The five changed classifications from the overlapping provisional inventory are recorded in the endpoint matrix.

### 8.3 Functional parity accounting

| Measure | Count |
|---|---:|
| Previous register rows | 77 |
| New evidence rows | 28 |
| Corrected interpretations | 18 |
| Removed/merged | 0 |
| **Total register rows** | **105** |

### 8.4 Accepted/newer patch behavior verified

- Portal v0.7 cuts runtime dependence on a passport Sheet, but embeds a shared secret in code.
- Sales DP no-double distinguishes PO DP from invoice application journal; newer Sales print modal/title flow supersedes overlapping older print UI.
- Purchasing item filters use `Master_Item.Item_Type`; v0.9.7 reads Production externally; v0.8 preserves FULL_ORDER versus CMT/maklun cost source; duplicate old `tambahMasterItem` is already removed.
- Production v0.9.8 aliases/fixes stock-cost ID configuration and preserves reject-stage parsing/item-safe availability.
- Warehouse v2.6 uses summary PR with lazy detail/raw fallback; contract V2 provides source key, lock and negative-stock guard.
- Omni v1.6.5 recognizes exact transit status `Sudah Dikirim`; summary V3 is source-first/date-key versioned; runtime return source is `Omni_Retur` only.
- Return QC v2.0.1 disables problematic inline notification behavior and posts only PASS/PARTIAL_PASS accepted quantities at batch post.
- Finance latest `FIN_sync*` endpoints are explicitly source-reader-only; bank reconciliation v1.8.7 supports multi-journal matching and v1.8.5 verifies PDF totals/count/balance before write.

### 8.5 Legacy bugs/workarounds requiring upgrade or removal

- Hardcoded shared secret, spreadsheet IDs, copied security helpers and broad role substring checks.
- Full-table scans, row-number identity, delete/rebuild edits, cross-spreadsheet non-atomic writes and void/reappend correction.
- Direct stock writes from Sales, Purchasing, Production, Return QC and POS.
- Aggregate Sales/Production closure that allows one item surplus to hide another shortage.
- Category/name substring purchase treatment and automated-account inference.
- Production broad monthly expense allocation and posted cost overwrite.
- Omni missing completion timestamp, incomplete persisted quantity triplet, return key without variation and POS subcategory-to-last-item bug.
- Finance random payment source keys, editable/soft-deletable posted-like journals, disabled auto-posting, reports derived from operational Sheets and hardcoded/name-based account resolution.
- Broken/duplicated `downloadSPKPDF`; destructive COA reset; alias-only repair endpoint; migration-only AppSheet return source.
- No scheduled triggers are evidenced despite rebuild/sync function names.

### 8.6 Owner-approved resolution assessment

| ID | Owner-approved decision | Classification | Blocks Phase 1 |
|---|---|---|---:|
| U-EA-001 | Current hashed package is the official Legacy Evidence Baseline; exact production provenance unnecessary. | `RESOLVED` | No |
| U-EA-002 | Revenue requires valid Waktu Selesai, MarketplaceStatusMap normalized COMPLETED, unique source, and Store/accounting mapping; returns/refunds are separate events. | `RESOLVED` | No |
| U-EA-003 | Default delivery-based invoicing plus permissioned/audited Sales-Order exception; proforma non-posting/no AR. | `RESOLVED` | No |
| U-EA-004 | Runtime PASS/HOLD/REJECT/REWORK; unsafe migration mapping preserves raw value as review-only LEGACY_UNMAPPED. | `RESOLVED` | No |
| U-EA-005 | Explicit legacy category mapping to five treatments; no substring inference; unmapped staging blocked. | `RESOLVED` | No |
| U-EA-006 | Eligibility fixed by treatment + eligible Cost Center + SnapshotProduction; item attribution and allocation snapshot mandatory. | `RESOLVED`; exact shared formula deferred | No |
| U-EA-007 | Immutable posted history; open-period reversal/revaluation/adjustment; locked-period correction in authorized open period with original references. | `RESOLVED` | No |
| U-EA-008 | Strict atomic/idempotent POS with actual Item, snapshots, tender, reversal/return documents, and OPEN/CLOSED cash session. | `RESOLVED` | No |

### 8.6.1 Deferred implementation details

These are later-phase gates and are not Phase 1 blockers because the foundation architecture already supports their configuration/snapshots:

- exact shared SPK/production cost allocation formula and rounding basis, due before Production/HPP posting;
- channel-specific MarketplaceStatusMap contents, due before each channel import is activated;
- row-by-row legacy QC and purchase-category migration mappings, due before those staging rows are accepted;
- detailed approval thresholds, Role + Action + Data Scope assignments, and POS tender catalogue, due before corresponding actions are enabled;
- UOM precision, tax configuration, final brand tokens, device optimization and exact legal print formatting, due in their domain/UI implementation gates;
- operational schedules, volumes and retention settings for rebuild/import/report jobs, due before jobs are enabled.

### 8.6.2 Remaining true blockers

**None.** No unresolved architectural or business decision remains that changes Phase 1 foundation architecture.

### 8.7 Artifact status after audit

| Artifact | Evidence update |
|---|---|
| Business Process Map | Actual end-to-end/cross-module flows and exception paths added |
| Module Ownership | Direct stock/accounting cross-write inventory added |
| Data Dictionary | Actual fields translated into canonical entities, keys, snapshots and unresolved fields |
| Event Matrix | Actual write sequences mapped to owned target events/commands |
| Workflow Status Matrix | Actual status literals/derivations mapped to controlled target states |
| Legacy Endpoint Matrix | 50-file manifest, function counts, classifications, 56 use-case rows and dead-code/conflict registers added |
| Functional Parity Register | 28 evidence rows; total 105; 18 interpretations corrected |
| Architecture | Sole-ledger, atomicity, stable line, cache/job and immutable-cost constraints added |
| UI Design System | Actual actions, scanner, POS, bank recon and print inventory added |
| SMB GAS Legacy Evidence Manifest | Official 50-file baseline, per-file hashes, aggregate hash and precedence recorded |

### 8.8 Gate recommendation

**PHASE 0 GATE = PASS.**

**PASS - PHASE 0 CLOSED.**

The source package is audited, no named module remains unaudited, all public declarations/use-case clusters are classified, major flows and ownership violations are explicit, and all eight former blockers are resolved by authoritative owner decisions.

**Owner/Stakeholder Acceptance: APPROVED FOR PHASE 0 CLOSURE.**

Phase 1 foundation work is ready but must not start until the user gives a separate explicit Phase 1 authorization.

## 9. Historical provisional gate decision (superseded)

**Current decision: BLOCKED — REMAIN IN PHASE 0.**

Reason: the nine-document draft set and plan-level classification are present, but the actual SMB evidence population is missing and no stakeholder acceptance is recorded. No Django scaffold, app, model, migration, service, view, template, or implementation test should be started from this draft set.
