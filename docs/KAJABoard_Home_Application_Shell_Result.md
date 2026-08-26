# KAJABoard Home Application Shell Result

**Scope:** Authenticated application shell and Home only  
**Checkpoint base:** phase-3b-pass  
**Status:** Ready for owner review; not committed, pushed, or tagged.

## Completed

- Added authenticated KAJABoard Home / Beranda at `/`.
- Root now redirects unauthenticated users to the existing login page; successful login returns to Home through named auth settings.
- Moved the existing Master Workspace to `/settings/` without removing its master/configuration functions.
- Added permission-aware Home module cards for implemented Sales, Organization, Partners, Catalog, Channels, Purchasing configuration, Finance configuration, Tax configuration, and Data Exchange destinations.
- Added a small scoped Sales summary only when the user has the relevant read permission.
- Updated the shared sidebar into scalable `Beranda`, `Operasional`, and `Master & Konfigurasi` groups. It contains no future-module placeholders.

## Files changed

- `config/urls.py`, `config/settings/base.py`
- `apps/core/home_views.py`, `apps/core/home_urls.py`, `apps/core/tests/test_home_shell.py`
- `apps/organizations/urls.py`
- `templates/base.html`, `templates/core/home.html`
- `static/css/kajaboard.css`
- `docs/KAJABoard_Home_Application_Shell_Result.md`

## Tests

- Root unauthenticated redirect and successful login landing on Home.
- Home authentication requirement, superuser module visibility, restricted-user module visibility, and direct protected-route enforcement.
- Existing Master Workspace remains accessible at `/settings/` for authorized users.
- Full project quality gate is recorded after completion.

## Navigation behavior

- `/` is KAJABoard Home / Beranda.
- `/settings/` is the existing Master Workspace.
- Sidebar and Home include only current implemented modules and permitted destinations.
- Login/logout use named Django auth URLs and avoid a root/workspace redirect loop.

## Permission behavior

- Module cards and navigation are hidden when the associated read permission is absent.
- Superusers retain standard full Django permission visibility.
- Views remain protected by their existing backend permission and legal-entity scope checks; hidden navigation is not treated as authorization.

## Unresolved

- Active legal-entity selection is not introduced because the current foundation supports scoped membership but no selected-entity context.
- Future modules appear only after their owned implementation and permissions exist.

## Explicit confirmations

- No Phase 3C business logic was added.
- No business transaction model was added.
- No historical migration was modified and no migration was created.
- `legacy/smb_gas/` baseline remains unchanged.
