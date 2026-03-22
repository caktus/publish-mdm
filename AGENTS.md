# Publish MDM — Agent Instructions

## Project Setup

- **Python env**: `uv`-managed. Use `uv run <cmd>` for all commands — no manual venv activation needed.
- **Run dev server**: `uv run manage.py runserver` (port 8000).
- **Settings**: test suite uses `config.settings.test` (set via `--ds` in `pyproject.toml`).

## Running Tests

```bash
uv run pytest             # runs tests/ with coverage; config in pyproject.toml
uv run pytest -x -q       # stop on first failure, quiet output
```

## Docker Sandbox

The project is mounted at the same path as on the host. The sandbox uses the default
`.venv` directory.

```bash
# One-time setup: install Postgres and create the DB
sudo service postgresql start
sudo -u postgres psql -c "CREATE ROLE agent LOGIN CREATEDB;"
sudo -u postgres createdb -O agent publish_mdm

# Run migrations (only needed once, or after new migrations are added)
DATABASE_URL=postgresql://agent@/publish_mdm \
  uv run manage.py migrate --settings=config.settings.test

# Run tests
DATABASE_URL=postgresql://agent@/publish_mdm uv run pytest -x -q --no-cov
```

`--no-cov` avoids a SQLite corruption error when both host and sandbox write to `.coverage`.

## Pre-commit

Pre-commit runs ruff (lint + format), prettier (CSS/JS/YAML/MD), djlint
(Django templates), trailing-whitespace, end-of-file-fixer, and a
missing-migrations check. **Always run pre-commit before committing**:

```bash
uv run pre-commit run --all-files
```

Key hooks that touch generated/edited files:

- `ruff-format` reformats Python (line length 100).
- `djlint-reformat-django` reformats Django HTML templates; run it before
  reading template diffs or the changes will show as conflicts.
- `prettier` reformats YAML, CSS, JS, and Markdown.

## Browser Testing (playwright-cli)

Skills are installed at `.claude/skills/playwright-cli/SKILL.md` — consult them for usage.

### Updating Skills

To update all installed skills (playwright-cli and others) to their latest versions:

```bash
playwright-cli install --skills
```

This command will refresh skill definitions and ensure you have the latest versions of all
available skills in `.claude/skills/`. Run this after pulling changes or when skills appear
out of date.

## Browser Testing in Sandbox (Playwright)

Use `playwright-cli` for headless browser testing when running in the Docker sandbox.
Skills are installed at `.claude/skills/playwright-cli/SKILL.md` — consult them for usage.

**One-time setup** (install globally; browsers live in `~/.cache/ms-playwright`, separate from host):

```bash
npm install -g @playwright/cli@latest
# Install Chromium — use the playwright binary bundled with playwright-cli:
"$(npm root -g)/@playwright/cli/node_modules/.bin/playwright" install chromium
```

**Start the dev server first** (required; test settings don't include debug_toolbar URLs):

```bash
DATABASE_URL=postgresql://agent@/publish_mdm \
  DJANGO_DEBUG=True ALLOWED_HOSTS=localhost \
  uv run manage.py runserver 8000 --settings=config.settings.dev --noreload &
```

**Open the browser** with `--browser=chromium` (no system Chrome in the sandbox):

```bash
playwright-cli open --browser=chromium http://localhost:8000/admin/login/
```

All subsequent `playwright-cli` commands target the open session as on the host.

- Login via `/admin/login/` (not Google OAuth).
- Organization slug required for most app URLs: `/o/<slug>/...`
- Get the slug from the DB: `uv run manage.py shell -c "from apps.publish_mdm.models import Organization; [print(o.slug) for o in Organization.objects.all()]"`
- Populate sample data: `uv run manage.py populate_sample_odk_data --settings=config.settings.dev`
- HTMX partial responses swap DOM fragments; after clicking Save buttons check
  that the surrounding section is still intact (missing context variables cause
  the replaced fragment to lose unrelated form inputs).

### node_modules separation

`playwright-cli` is a global npm install — its files live outside the project (
`$(npm root -g)`) and are naturally separate between host and sandbox.

The project's local `node_modules` (Tailwind, Parcel, etc.) contain platform-specific
native binaries and **must not be shared** between macOS (host) and Linux (sandbox).
Use `.npm-sandbox/` as the sandbox:

```bash
# One-time setup in the sandbox (symlinks package.json so npm install reads it):
mkdir -p .npm-sandbox
ln -sf ../package.json .npm-sandbox/package.json
npm install --prefix .npm-sandbox
# Run npm scripts via the sandbox node_modules:
.npm-sandbox/node_modules/.bin/tailwindcss -i config/assets/styles/tailwind-entry.css \
  -o config/static/css/main.css --minify
```

`.npm-sandbox/` is in `.gitignore`; the host's `node_modules/` is unaffected.

## Organization Tenancy and Permissions

### How multi-tenancy works

All app URLs are org-scoped: `/o/<slug>/...`. Access is enforced by two middleware
classes in `apps/publish_mdm/middleware.py`:

1. **`OrganizationMiddleware`** — runs on every request, sets `request.organization` by
   looking up the `organization_slug` URL kwarg from the authenticated user's org
   memberships (`request.user.get_organizations()`). Returns **404** if the slug doesn't
   belong to the user, so **org isolation is guaranteed at the URL layer**. No view-level
   org check is needed; if `request.organization` is set, the user is a member.

2. **`ODKProjectMiddleware`** — sets `request.odk_project` from the `odk_project_pk` URL
   kwarg, scoped to the current org's projects.

### Organization model

- `Organization` (`apps/publish_mdm/models.py`) has a `ManyToManyField` to `User` —
  no separate "OrganizationUser" role model.
- There is **no admin/editor role distinction within an org** — all org members have
  equal access. Additional elevated privileges are controlled via Django's site-wide
  flags: `user.is_staff` (for staff-only features) and `user.is_superuser` (e.g., access
  to all organizations and certain restricted org pages).

### Permission pattern in views

All org-scoped application views use `@login_required` (or the equivalent mixin). Org
scoping is free via the middleware. Public signup/invite endpoints (for example,
`RequestOrganizationInvite`) are intentionally unauthenticated and must enforce any
required permissions explicitly. For features that should be restricted to staff only
(site-wide admin tasks), add:

```python
if not request.user.is_staff:
    return redirect("publish_mdm:organization-home", organization_slug)
```

**Policy editor views** are accessible to all org members (no `is_staff` check). Each
`Policy` has an `organization` FK; queries are scoped to `request.organization`.

### Policy model tenancy

`Policy` (`apps/mdm/models.py`) has:

- `organization` FK → `publish_mdm.Organization` (nullable for legacy rows)
- `mdm` field — either `"Android Enterprise"` or `"TinyMDM"`
- `PolicyManager` filters by `settings.ACTIVE_MDM["name"]`

Policy views scope queries via `Policy.objects.filter(organization=request.organization)`.
The `get_object_or_404` pattern in HTMX sub-views includes `organization=request.organization`
to prevent cross-org access.

### TinyMDM vs Android Enterprise policies

The `Policy` model is shared between both MDMs (differentiated by the `mdm` field):

- **Android Enterprise (AMAPI)**: the full policy editor (password, VPN, kiosk,
  applications, variables) is used. `PolicySerializer.to_dict()` generates AMAPI JSON.
- **TinyMDM**: only `name` and `policy_id` are relevant. `policy_id` is the ID of the
  pre-configured policy in TinyMDM's console — users enter this ID and TinyMDM manages
  all policy configuration on its own side. The normalized AMAPI fields are stored but
  not used.

The default MDM (`settings.ACTIVE_MDM`) defaults to TinyMDM. Set
`ACTIVE_MDM_NAME=Android Enterprise` and
`ACTIVE_MDM_CLASS=apps.mdm.mdms.AndroidEnterprise` to switch.

## Skills

- **`playwright-cli`** — browser automation: `.claude/skills/playwright-cli/SKILL.md`
- **`flowbite`** — UI component patterns (toggle switches, modals, badges, auto-save
  HTMX forms, Alpine.js, etc.): `.claude/skills/flowbite/SKILL.md`

## Key Conventions

- `Breadcrumbs.from_items()` requires a non-None string `viewname` for every
  crumb — passing `None` raises a Pydantic `ValidationError`.
- HTMX views that re-render a section partial must include **all** context
  variables the partial (and any `{% include %}` sub-partials) need.
- **`views.py` is ~1650 lines** — never use the `edit` tool on it (it empties the
  file). Always use Python `str.replace()` via bash:

  ```bash
  python3 -c "
  with open('apps/publish_mdm/views.py') as f: c = f.read()
  c = c.replace('OLD', 'NEW')
  with open('apps/publish_mdm/views.py', 'w') as f: f.write(c)
  "
  ```

- HTMX event names are camelCase (`htmx:afterRequest`). HTML lowercases attribute
  names, so `hx-on:htmx:afterRequest` becomes `hx-on:htmx:afterrequest` in the DOM
  and never matches. Use inline `<script>` tags in HTMX responses instead.
- **`hx-swap="innerHTML"`** (not `outerHTML`) when the target element's `id` is
  reused for future swaps — `outerHTML` removes the element and destroys its ID.

## Review-Tests Workflow

Project-specific parameters when running the `review-tests` agents:

```
testCommand:        DATABASE_URL=postgresql://agent@/publish_mdm uv run pytest --no-cov
lintCommand:        uv run pre-commit run --all-files
appRoot:            apps/
testRoot:           tests/
coverageThreshold:  80
```

### Coverage command (for coordinator validation steps)

```bash
DATABASE_URL=postgresql://agent@/publish_mdm uv run pytest \
  --cov=apps/ --cov-report=json:.coverage-report.json -q tests/
```

### Pre-commit fallback (when network is unavailable)

```bash
uv run ruff check --fix apps/ tests/ && uv run ruff format apps/ tests/
uv run djlint --reformat config/templates/
```

### Sandbox notes

- Use `--no-cov` in the regular test command to avoid SQLite `.coverage` file corruption
  when both the host and sandbox share the filesystem.
- `DATABASE_URL=postgresql://agent@/publish_mdm` is always required in the sandbox.
- The PostgreSQL service must be running: `sudo service postgresql start`.
- Migrations only need to be run once per sandbox session:
  `DATABASE_URL=postgresql://agent@/publish_mdm uv run manage.py migrate --settings=config.settings.test`
