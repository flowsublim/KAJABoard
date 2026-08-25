# KAJABoard Phase 1 Foundation Result

**Phase:** 1 — Foundation  
**Execution date:** 25 August 2026  
**Status:** COMPLETE — VALIDATED  
**Phase 0 authority:** `PHASE 0 GATE = PASS`; owner/stakeholder approved for Phase 0 closure  
**Phase 2 status:** NOT STARTED; explicit owner authorization still required

## 1. Scope result

Phase 1 establishes the technical foundation for the approved Django modular monolith. It does not implement an operational business module or posting workflow.

Implemented:

- Django 5.2 project bootstrap with local, test, and fail-closed production settings;
- environment-only secret and production database configuration;
- PostgreSQL production backend configuration and explicit SQLite local/test convenience;
- UUID-based custom user with normalized email authentication;
- minimal legal-entity and user-membership access scope;
- append-oriented audit records and an explicit audit-write service;
- database-backed idempotency claim/result records and application services;
- explicit posted-history state/correction vocabulary and edit guard;
- inexpensive liveness and database readiness endpoints;
- Django admin registration appropriate to each foundation record;
- initial migrations, focused regression tests, Ruff tooling, and Linux CI checks.

Explicitly not implemented: Sales, Purchasing, Production, Warehouse, Finance, Omnichannel, POS, QC/Returns, marketplace mapping/import, posting, journal, stock movement, HPP, tax, print, dashboards, or other Phase 2+ behavior.

## 2. Project and application structure

| Area | Files / responsibility |
|---|---|
| Project entry points | `manage.py`; `config/urls.py`; `config/wsgi.py`; `config/asgi.py` |
| Settings | `config/settings/base.py`, `local.py`, `test.py`, `production.py` |
| Accounts | `apps/accounts/` — custom user, manager, admin, migration, tests |
| Core | `apps/core/` — audit, idempotency, posting conventions, health, admin, tests |
| Organizations | `apps/organizations/` — legal entity, membership, admin, migration, tests |
| Dependencies/tooling | `requirements/base.txt`, `requirements/dev.txt`, `pyproject.toml`, `.env.example` |
| Continuous validation | `.github/workflows/ci.yml` |

## 3. Implementation-level architecture decisions

### 3.1 Settings and deployment boundary

- `manage.py` defaults to local settings; WSGI/ASGI default to production settings so a direct deployment load fails closed unless explicitly configured.
- Production requires a non-empty secret key, allowed hosts, and PostgreSQL connection variables. `DEBUG` is always false and secure cookie/HTTPS/HSTS settings are enabled.
- `.env.example` is a variable contract only. The application does not implicitly read local files or add a secret-loading package.
- SQLite is allowed only as an explicit development/test convenience. PostgreSQL remains the production source of truth.
- Windows ARM64 lacks an available `psycopg-binary` wheel. Dependency markers therefore use pure Psycopg on that local platform and binary Psycopg on normal Linux/CI/deployment platforms.

### 3.2 Identity and access scope

- `accounts.User` exists in the initial migration, before any application migration could lock the default Django user.
- A generated UUID is the stable internal identity. Email is the login field, is normalized by the manager, and has both normal and case-insensitive database uniqueness enforcement.
- Active/inactive, staff, superuser, Django groups, and Django permissions use the standard, reviewed Django mechanisms.
- `LegalEntity` and `OrganizationMembership` are the only organization/access models. Business-unit hierarchy, stores/channels, permission thresholds, and detailed data scopes remain deferred instead of being guessed.

### 3.3 Audit foundation

- `AuditEvent` captures actor, action, target, time, source, correlation/reference, reason, approval reference, idempotency key, before/after state, changed fields, and contextual metadata.
- Audit creation uses the explicit `record_audit_event()` service.
- Instance update/delete and queryset update/delete are rejected, the actor relationship is protected, and the Django admin is inspection-only. This covers ordinary application workflows without hidden signals or generic save middleware.
- Direct privileged database manipulation cannot be prevented by application code; database access remains an operational least-privilege responsibility.

### 3.4 Idempotency foundation

- `(namespace, key)` has a database unique constraint.
- A deterministic SHA-256 request hash detects reuse of the same key for a different payload.
- Claim, completion, and failure services use atomic transactions; existing rows are locked before state/result handling.
- Retrying a completed same-payload operation returns the original persisted result. A changed payload raises an explicit conflict.
- A check constraint keeps `IN_PROGRESS` records unfinished and requires a finish timestamp for `COMPLETED`/`FAILED` records.

### 3.5 Posted-history convention

- Foundation vocabulary is `DRAFT`, `POSTED`, `REVERSED`, with correction types `REVERSAL`, `ADJUSTMENT`, and `REVALUATION`.
- `ensure_record_is_mutable()` permits in-place edits only for draft state. Future domain services and database constraints must apply this convention to their explicit models.
- No generic posting model, signal, journal, stock record, or Phase 2 workflow was created.

### 3.6 Health checks

- `/health/live/` confirms request handling without a database call.
- `/health/ready/` performs only `SELECT 1` and returns HTTP 503 without disclosing exception detail when database access fails.

## 4. Models, constraints, and indexes

| Model | Purpose | Important integrity |
|---|---|---|
| `accounts.User` | Stable authentication identity | UUID PK; unique email; case-insensitive email unique constraint |
| `organizations.LegalEntity` | Legal/reporting boundary | UUID PK; case-insensitive unique code |
| `organizations.OrganizationMembership` | Minimal user/entity scope | UUID PK; unique user/entity pair; protected entity; entity/active index |
| `core.AuditEvent` | Append-oriented trace evidence | UUID PK; protected actor; action/correlation/time/idempotency indexes; target composite index; mutation guards |
| `core.IdempotencyRecord` | Retry-safe operation claim/result | UUID PK; unique namespace/key; finish-state check; namespace/status index |

Reusable `UUIDPrimaryKeyModel` and `TimeStampedModel` are deliberately small and opt-in. They do not impose speculative source, state, actor, or posting fields on every future table.

## 5. Migrations

Created and reviewed:

- `apps/accounts/migrations/0001_initial.py`
- `apps/core/migrations/0001_initial.py`
- `apps/organizations/migrations/0001_initial.py`

A new local SQLite database migrated from zero through all Django and Phase 1 migrations. No pre-existing or deployed migration history was rewritten. No placeholder operational table was created.

## 6. Testing and validation

Final local environment: Python 3.13.15, Django 5.2.17, pytest 9.1.1, pytest-django 4.14.0, Ruff 0.16.4.

| Command / validation | Result |
|---|---|
| `.venv\Scripts\python.exe manage.py check` | PASS — 0 issues |
| `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` | PASS — no changes detected |
| `.venv\Scripts\python.exe manage.py migrate --noinput` on a new database | PASS — all migrations applied |
| `.venv\Scripts\pytest.exe` | PASS — 32 tests |
| `.venv\Scripts\ruff.exe check .` | PASS |
| `.venv\Scripts\ruff.exe format --check .` | PASS |
| Production settings static assertions | PASS — PostgreSQL engine, `DEBUG=False`, hosts, secret, and secure cookies verified |
| Missing production secret regression test | PASS — settings fail closed |
| Foundation URL-name regression test | PASS — admin/liveness/readiness names resolve distinctly |
| Legacy evidence manifest verifier | PASS — 50/50 and aggregate match |

Coverage includes user creation, superuser validation, case-insensitive authentication/uniqueness, inactive authentication rejection, organization constraints/protection, audit append-only behavior, idempotency uniqueness/hash/replay/conflict/state constraints, posted-history edit guard, health success/failure, settings assumptions, system checks, and URL uniqueness.

The first optional local `check --deploy` attempt could not load PostgreSQL because Windows ARM64 has no binary wheel or installed `libpq`. This is not the application runtime target. The production configuration was statically validated locally, and Linux CI installs binary Psycopg and runs Django's production `--deploy` check.

## 7. Legacy evidence integrity

The final verifier checks every manifest path, byte size, and SHA-256, then reconstructs the documented aggregate.

- expected files: 50;
- actual files: 50;
- missing: 0;
- unexpected: 0;
- size mismatches: 0;
- SHA-256 mismatches: 0;
- aggregate: `66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2`;
- aggregate match: yes.

No file under `legacy/smb_gas/` was edited, renamed, deleted, regenerated, or reformatted.

## 8. Known limitations and deferred items

These are later-phase implementation details, not Phase 1 blockers:

- exact shared SPK/production cost allocation and rounding;
- marketplace status-map contents and operational import profiles;
- row-level legacy QC and purchase-category mappings;
- detailed roles, permission thresholds, segregation, and data scopes;
- business unit/store/channel hierarchy beyond the minimal legal-entity scope;
- POS tender catalogue and cash sessions;
- operational numbering, approval, attachment, notification, and job scheduling;
- operational audit retention and external monitoring;
- PostgreSQL service integration and PythonAnywhere deployment smoke testing;
- all operational business records and workflows.

Raw database administrators remain technically capable of changing audit data. Production database privileges, backups, monitoring, and restore drills must be completed during deployment work. This does not weaken the application-level append-only contract.

## 9. Acceptance

All required Phase 1 foundation work and local validation succeeded. Phase 0 decisions remain unchanged, the evidence baseline remains byte-identical, and Phase 2 work has not begun.

**PHASE 1 GATE = PASS**

**NEXT RECOMMENDED ACTION:** Request explicit owner authorization to begin Phase 2.
