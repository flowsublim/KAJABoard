# KAJABoard Phase 2B Operational Master Result

**Phase:** 2B — Numbering + Store / Channel + External SKU Mapping  
**Execution date:** 25 August 2026  
**Status:** IMPLEMENTED — AWAITING OWNER REVIEW  
**Phase 2C status:** NOT STARTED

## 1. Implemented scope

Phase 2B adds only the operational master/configuration required by later transaction modules:

- legal-entity-aware `DocumentSequence` configuration;
- locked `DocumentSequenceState` counters per reset period;
- immutable `DocumentNumberAllocation` records for final allocated numbers;
- controlled numbering templates, prefix, padding, starting number, and reset mode;
- non-consuming number preview and retry-safe allocation request keys;
- stable effective `Store` / sales-channel identity;
- external account and retained alias resolution without display-name identity dependence;
- optional Finance dimension/revenue mapping hook strings without posting behavior;
- exact Store + external SKU + variation mapping to canonical `catalog.Item`;
- positive Decimal conversion quantity as an explicit package factor for later snapshotting;
- effective-period overlap prevention, historical as-of selectors, access scope, audit, and lifecycle services;
- responsive Master/Settings lists, filters, pagination, create/edit, preview, and lifecycle screens.

No business document, import batch, order, stock effect, accounting effect, or payment is created.

## 2. Numbering architecture and contract

### Models

- `DocumentSequence` stores one effective configuration version for a Legal Entity and stable
  document type.
- `DocumentSequenceState` stores the last allocated value for a configuration/reset-period key.
- `DocumentNumberAllocation` records the final number, sequence value, business date, actor, and
  optional request key.

Supported reset modes are `NEVER`, `YEARLY`, `MONTHLY`, and `DAILY`. Supported controlled tokens are:

```text
{prefix} {yyyy} {yy} {mm} {dd} {yyyymmdd} {yymmdd} {seq}
```

Exactly one `{seq}` token is required. Sequence padding is a separate validated field. Unsupported
tokens, format specifications, escaped braces, invalid periods, and overlapping configuration
versions are rejected.

Allocation locks the Legal Entity, effective configuration, and period state inside
`transaction.atomic()`. Database constraints make the final number unique within its Legal Entity
and make each configuration/period/value unique. A nonblank request key is unique per Legal Entity
and document type; retrying the same key/date returns the original allocation without incrementing.

Preview reads the current state but creates neither a state row nor an allocation. It is explicitly
informational and does not reserve a number.

After a series has allocated a number, its prefix/template/padding/start/reset/effective start cannot
be silently reformatted. The configuration must be ended and a new non-overlapping effective version
created.

## 3. Store / channel architecture and contract

`Store` has a stable UUID, Legal Entity, optional Business Unit, stable code, stable channel/platform
key, display name, external account identifier, aliases, optional Finance hook keys, effective period,
and active state.

Legal Entity, Store code, and channel are stable identity fields after creation. Renaming a Store or
changing an external account retains the former values as aliases, so existing external identities
remain resolvable to the same stable Store ID. Effective Store selectors enforce the accepted Legal
Entity membership scope. Historical inactive Stores remain resolvable for dates inside their former
effective period.

Finance hook fields are configuration references only. They do not select a COA, generate a journal,
recognize revenue, or create a marketplace balance.

## 4. External SKU mapping architecture and contract

`ExternalSKUMap` maps exactly:

```text
Store + normalized external SKU + normalized variation + effective period
→ canonical catalog.Item + conversion quantity
```

The Store and Item must belong to the same Legal Entity. Their effective periods must cover the
complete mapping period. An effective current mapping cannot reference an inactive Store or Item.
Overlapping ranges for the same mapping scope are rejected while holding the Store row lock.

Store, external SKU, and external variation are stable mapping-scope fields. Once a mapping is
effective, Item, conversion quantity, and effective start cannot be repointed in place. End the old
mapping and create a new effective version. This preserves deterministic historical as-of resolution.

Resolution is strict and variation-aware. No product-name, subcategory, or fuzzy fallback is added in
Phase 2B. Later Omnichannel transactions must snapshot the mapping ID, Store ID, Item ID/code, raw
external SKU/variation, and conversion quantity used at import time.

## 5. Files and layers added

### Core numbering

- Core models and migration for sequence configuration, counter state, and final allocations.
- `apps/core/services/numbering.py` for validation, rendering, preview, configuration mutation, and
  allocation.
- `apps/core/selectors/numbering.py` for membership-scoped and effective configuration reads.
- numbering forms, permission-checked views, URL routes, templates, and read-only Admin inspection.

### Channels domain

- new `apps/channels/` application;
- Store and External SKU Map models;
- explicit atomic service-layer create/edit/activate/deactivate commands;
- selectors for lists, effective/as-of Store resolution, and exact external SKU resolution;
- forms, permission-checked views, URL routes, read-only Admin, and regression tests;
- responsive Store and SKU Mapping screens.

### Shared shell

- Phase 2B permission-aware navigation and workspace metrics;
- local stylesheet extension for number preview;
- pagination preserves Phase 2B filter parameters.

## 6. Migrations

Phase 2B adds only:

- `apps/core/migrations/0002_documentsequence_documentnumberallocation_and_more.py`
- `apps/channels/migrations/0001_initial.py`

Accepted Phase 1 and Phase 2A migration files are unchanged. A fresh database migration succeeds and
`makemigrations --check --dry-run` reports no pending changes.

## 7. Tests and quality evidence

The Phase 2B regression suite covers:

- supported templates and rejection of unsafe/invalid templates;
- preview does not create state or consume an allocation;
- daily and monthly reset behavior;
- deterministic increment and starting padding;
- request-key replay and date-conflict rejection;
- concurrent retrying allocation with unique final results;
- database rejection of a duplicate final number;
- configuration overlap prevention and post-allocation format immutability;
- Store normalization, aliases, rename continuity, audit, and historical resolution;
- Store identifier overlap prevention;
- exact variation-aware SKU scopes;
- mapping overlap rejection and effective-period coverage;
- historical old/new Item resolution;
- protection against cross-entity mappings and silent current remapping;
- Legal Entity membership scope and permission-aware UI actions;
- existing Phase 1 and Phase 2A regressions.

Final command results are reported in the owner completion response together with formatter, lint,
Django check, migration drift, fresh migration, diff check, and legacy checksum results.

## 8. Explicitly unresolved / deferred

- The owner-approved production list of document types, exact prefixes/formats, and starting values is
  not supplied; Phase 2B provides configuration and does not seed speculative series.
- Exact channel/platform vocabulary remains a normalized stable key rather than an invented closed
  enumeration.
- Blank-variation fallback, product-name fallback, and channel-specific import matching rules remain
  an Omnichannel implementation decision. Phase 2B resolution is strict.
- `conversion_quantity` is a mapping package factor only; no general UOM conversion engine exists.
- Store fulfillment Warehouse/bin settings remain deferred until the Warehouse gate.
- Finance hook values remain unresolved references until accepted COA Mapping and Finance resolver
  work; there is no accounting behavior here.
- No PostgreSQL service is available in the local Windows environment. Concurrency is protected by
  production row locks and database uniqueness, while the executable concurrent/retry test runs on
  the local SQLite test backend.
- Interactive browser inspection could not run because no browser backend was connected; Django UI
  route, permission, template compilation, and static-discovery tests remain the local evidence.

## 9. Strict boundary confirmation

Phase 2C was not implemented. Phase 2B does not contain Sales Order, Invoice, Purchasing, SPK,
Production, StockMovement, stock balance, Warehouse ledger/receipt/issue, Journal, AR/AP, Payment, POS
sale, Omnichannel import/order/settlement, return/QC transaction, tax posting, approval matrix, broad
import/export framework, UOM conversion engine, or warehouse location/bin behavior.

Warehouse remains master data only. Finance remains the sole future owner of accounting effects.
