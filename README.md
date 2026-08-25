# KAJABoard

KAJABoard is the Django modular-monolith rebuild of the SMB system for **PT KAJA VASTRALOKA KREASINDO**. The accepted Google Apps Script and Google Sheets implementation is preserved as business-behavior evidence, not as code to port literally.

## Current status

- Phase 0: **PASS — owner approved for closure**
- Phase 1 foundation: implemented and validated; see `docs/KAJABoard_Phase_1_Foundation_Result.md`
- Phase 2: **not started and not authorized**
- Legacy evidence baseline: 50 immutable files under `legacy/smb_gas/`

The official evidence aggregate SHA-256 is:

`66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2`

## Foundation stack

- Python 3.13
- Django 5.2 LTS
- PostgreSQL in production
- SQLite as the explicit local/test convenience backend
- pytest and pytest-django
- Ruff linting and formatting
- PythonAnywhere Paid / WSGI as the initial deployment target

No Sales, Purchasing, Warehouse, Production, Finance, Omnichannel, POS, QC, Return, or other operational business module has been implemented in Phase 1.

## Read first

1. `AGENTS.md`
2. `docs/KAJABoard_Project_Plan_FINAL_v2.0.md`
3. all current Phase 0 documents under `docs/`
4. `docs/KAJABoard_Phase_1_Foundation_Result.md`
5. relevant immutable evidence under `legacy/smb_gas/`

Phase 0 decisions remain authoritative. Warehouse is the sole physical-stock ledger owner; Finance is the sole accounting owner; automated journal accounts must resolve through Master COA Mapping.

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

The local settings module defaults to SQLite. Copy the variable names from `.env.example` into the shell or hosting environment when configuration is needed; the project deliberately does not auto-load `.env` files.

Useful checks:

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\pytest.exe
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
```

Health endpoints:

- `/health/live/` confirms that the Django process responds without a database query.
- `/health/ready/` performs one constant-time database connectivity query.

## Configuration

Settings are split into:

- `config.settings.local`
- `config.settings.test`
- `config.settings.production`

Production settings fail closed when the secret key, allowed hosts, or PostgreSQL connection values are missing. PythonAnywhere must set `DJANGO_SETTINGS_MODULE=config.settings.production` and the required environment variables before loading `config.wsgi.application`.

## Repository layout

```text
apps/
  accounts/       Custom email-authenticated user foundation
  core/           Audit, idempotency, posted-history, and health primitives
  organizations/  Minimal legal-entity membership scope
config/            Django settings, URL, WSGI, and ASGI configuration
docs/              Accepted analysis and implementation results
legacy/smb_gas/    Immutable SMB GAS Legacy Evidence Baseline
requirements/      Runtime and development dependencies
```

## Development discipline

Read → plan → implement narrowly → migrate → test → inspect the diff → verify legacy integrity.

Do not begin a later phase without explicit owner authorization.
