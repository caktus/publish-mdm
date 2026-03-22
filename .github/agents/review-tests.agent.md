---
description: >
  Orchestrate the complete four-phase test quality review (delete → coverage → bugfix → refactor)
  in sequence on the current branch. Works with any Django project using pytest or unittest.
  Handles environment setup and baseline, then delegates to specialist agents. Uses a typed
  JSON state contract to prevent phases from reverting each other's work.
name: review-tests
tools:
  # The coordinator needs read + write + terminal to:
  #   - initialize and update test-review-state.json
  #   - run validation commands between phases (tests, coverage)
  #   - ensure .gitignore entries exist
  # Specialist subagents have ["*"] for full access.
  - read
  - edit
  - terminal
  - search
  - todo
  - agent
agents:
  - review-tests-delete
  - review-tests-coverage
  - review-tests-bugfix
  - review-tests-refactor
---

You coordinate a four-phase test quality review. Phases run in strict sequence —
**delete → coverage → bugfix → refactor** — and share a typed JSON contract (`test-review-state.json`)
so no phase can revert the work of a prior one.

Each specialist agent reads the contract before acting and writes its results back before
returning. The coordinator validates the contract at every phase boundary before advancing.

## Inputs

| Input                           | Default      | Purpose                                        |
| ------------------------------- | ------------ | ---------------------------------------------- |
| `${input:testCommand}`          | _(required)_ | Command to run the test suite                  |
| `${input:lintCommand}`          | _(optional)_ | Lint/format check command (skipped if blank)   |
| `${input:appRoot:apps/}`        | `apps/`      | Directory containing production source modules |
| `${input:testRoot:tests/}`      | `tests/`     | Directory containing test files                |
| `${input:coverageThreshold:80}` | `80`         | Flag modules below this % coverage             |
| `${input:skipFiles:}`           | _(blank)_    | Comma-separated test files to skip             |
| `${input:focusPattern:}`        | _(blank)_    | Limit all passes to a specific app or glob     |

---

## Sample prompts

**pytest project (uv):**

```
Run the full review-tests workflow on this branch.
- testCommand: uv run pytest
- lintCommand: uv run pre-commit run --all-files
- appRoot: apps/
- testRoot: tests/
- coverageThreshold: 80
Make a granular commit after each change. When done, push and open a PR against main.
```

**unittest project (pip):**

```
Run the full review-tests workflow on this branch.
- testCommand: python manage.py test
- lintCommand: python -m flake8
- appRoot: myapp/
- testRoot: myapp/tests/
- coverageThreshold: 75
Make a granular commit after each change. When done, push and open a PR against main.
```

---

## Using in GitHub Copilot Cloud

When running as a GitHub Copilot Cloud agent (no interactive input dialog), include
configuration values directly in your issue description or prompt. Any values not
provided will be auto-detected in Phase 0 §0.

Example issue body:

```
Run the full review-tests workflow on this branch.
testCommand: uv run pytest
lintCommand: uv run pre-commit run --all-files
appRoot: apps/
testRoot: tests/
coverageThreshold: 80
Push when done and open a PR against main.
```

Read [AGENTS.md](../AGENTS.md) for this project's standard commands and conventions.

---

## Phase 0 — Environment setup and baseline

### 0. Resolve configuration

If running via VS Code, input variables (`${input:...}`) are filled by the dialog.
If running in GitHub Copilot Cloud or any non-interactive environment, read values
from the prompt/issue body, or auto-detect them:

- **testCommand**: check `pyproject.toml` for `[tool.pytest]` / `uv` presence, or
  `setup.cfg` / `manage.py` for Django's test runner. Default: `uv run pytest` if
  `pyproject.toml` contains `[tool.pytest.ini_options]`, else `python manage.py test`.
- **lintCommand**: check `.pre-commit-config.yaml` existence; if present, default to
  `uv run pre-commit run --all-files` (or `pre-commit run --all-files`). If absent,
  leave blank.
- **appRoot**: scan for a directory containing `apps.py` files one level down; default
  `apps/`.
- **testRoot**: look for a `tests/` directory; default `tests/`.
- **coverageThreshold**: default `80`.
- **skipFiles / focusPattern**: default blank.

Store resolved values for use throughout the workflow.

### 1. Set up environment (skip if already set up)

Install Python dependencies using the project's package manager:

```bash
# Adapt to your project: pip, uv, poetry, pipenv, etc.
# Examples:
#   pip install -r requirements.txt
#   uv sync
#   poetry install
```

Set required environment variables. Typical Django test setup:

```bash
export DJANGO_SETTINGS_MODULE=<your_test_settings_module>
export DATABASE_URL=<your_test_database_url>   # if using dj-database-url
```

Run database migrations:

```bash
python manage.py migrate   # or: uv run manage.py migrate, etc.
```

Verify Django is set up correctly:

```bash
python -c "import django; django.setup(); print('OK')"
```

Fix any setup errors before proceeding.

> **If `lintCommand` uses pre-commit and fails with a network/pip timeout** (common in
> sandboxed environments), fall back to running the individual formatters directly, e.g.:
> `uv run ruff check --fix <appRoot> <testRoot> && uv run ruff format <appRoot> <testRoot>`.
> Record the fallback used in the state contract under a `"lint_fallback"` key.

### 2. Run baseline

Run the test suite with coverage reporting. The exact command depends on your setup:

**pytest with pytest-cov:**

```bash
${input:testCommand} --cov=${input:appRoot:apps/} --cov-report=json:.coverage-report.json -q
```

**unittest / manage.py test with coverage.py:**

```bash
coverage run --source=${input:appRoot:apps/} manage.py test
coverage json -o .coverage-report.json
```

**If any tests fail, stop.** Report failures and do not proceed until the suite is green.

Read `.coverage-report.json` and extract:

- `totals.percent_covered` → baseline coverage %
- `totals.num_statements` → baseline statement count

### 3. Initialize the shared state contract

Write `test-review-state.json` in the repo root. Replace `<N>` and `<X.X>` with real values:

```json
{
  "schema_version": 1,
  "phases_completed": [],
  "baseline": {
    "test_count": "<N>",
    "coverage_percent": "<X.X>"
  },
  "current_coverage_percent": "<X.X>",
  "deleted_tests": [],
  "refactored_tests": [],
  "coverage_added": [],
  "bugfix_tests": []
}
```

**Schema for the arrays** — each specialist appends entries in these exact shapes:

```jsonc
// deleted_tests[] — written by delete specialist
{ "file": "tests/app/test_foo.py", "test": "test_bar",
  "criterion": "C1|C2|C3|C4", "reason": "one sentence" }

// refactored_tests[] — written by delete specialist (deferred) and refactor specialist
{ "file": "tests/app/test_foo.py", "test": "test_bar",
  "criterion": "C1|C2|C3|C4", "phase": "delete|refactor",
  "status": "pending|done",
  "behaviors_covered": ["sentence describing what the test now verifies"] }

// coverage_added[] — written by coverage specialist
{ "file": "tests/app/test_new.py", "test": "test_baz",
  "production_module": "apps/app/models.py", "lines_covered": "L42-48",
  "mutation_verified": true }

// bugfix_tests[] — written by bugfix specialist
{ "file": "tests/app/test_models.py", "test": "test_save_raises_when_required_field_is_none",
  "production_module": "apps/app/models.py",
  "classification": "PROVEN|DENIED", "bug_confirmed": true,
  "fix_applied": true, "description": "one sentence" }
```

Ensure both `test-review-state.json` and `.coverage-report.json` are in `.gitignore`.

### 4. Record todos

Use `#tool:todos` to record: "Phase 1 — Pruning (delete)", "Phase 2 — Expansion (coverage)", "Phase 3 — Debugging (bugfix)", "Phase 4 — Refactoring (refactor)".

---

## Phase 1 — Pruning (Delete)

Mark "Phase 1 — Pruning (delete)" in-progress.

Invoke `review-tests-delete` as a subagent. Pass these values:

```
STATE_FILE    = test-review-state.json
TEST_CMD      = ${input:testCommand}
LINT_CMD      = ${input:lintCommand}
APP_ROOT      = ${input:appRoot:apps/}
TEST_ROOT     = ${input:testRoot:tests/}
SKIP_FILES    = ${input:skipFiles:}
FOCUS_PATTERN = ${input:focusPattern:}
```

**Wait for completion.**

**Validate the handoff — all three checks must pass before continuing:**

1. Read `test-review-state.json`. Assert `"delete"` is in `phases_completed` and `deleted_tests` is a valid array.
2. Run `${input:testCommand} -q --tb=no`. All tests must pass.
3. Run coverage as in Phase 0 §2. Read `totals.percent_covered` from `.coverage-report.json`. Assert ≥ baseline.

If the coordinator lacks a terminal tool, delegate validation to a one-shot subagent that runs
the commands and returns pass/fail with the coverage percentage.

If any check fails, **stop and report to the user**. Do not continue to Phase 2.

Update `current_coverage_percent` in the state file. Mark "Phase 1 — Pruning (delete)" completed.

---

## Phase 2 — Expansion (Coverage)

Mark "Phase 2 — Expansion (coverage)" in-progress.

Invoke `review-tests-coverage` as a subagent with the same parameter set plus:

```
COVERAGE_THRESHOLD = ${input:coverageThreshold:80}
```

**Wait for completion.**

**Validate the handoff — all three checks must pass before continuing:**

1. Read `test-review-state.json`. Assert `"coverage"` is in `phases_completed` and `coverage_added` is a valid array.
2. Run `${input:testCommand} -q --tb=no`. All tests must pass.
3. Run coverage as in Phase 0 §2. Read `totals.percent_covered` from `.coverage-report.json`. Assert ≥ baseline.

If the coordinator lacks a terminal tool, delegate validation to a one-shot subagent that runs
the commands and returns pass/fail with the coverage percentage.

If any check fails, **stop and report to the user**. Do not continue to Phase 3.

Update `current_coverage_percent`. Mark "Phase 2 — Expansion (coverage)" completed.

---

## Phase 3 — Debugging (Bug-fix)

Mark "Phase 3 — Debugging (bugfix)" in-progress.

Invoke `review-tests-bugfix` as a subagent with the same parameter set as Phase 1.

**Wait for completion.**

**Validate the handoff — all three checks must pass before continuing:**

1. Read `test-review-state.json`. Assert `"bugfix"` is in `phases_completed` and `bugfix_tests` is a valid array.
2. Run `${input:testCommand} -q --tb=no`. All tests must pass.
3. Run coverage as in Phase 0 §2. Read `totals.percent_covered` from `.coverage-report.json`. Assert ≥ baseline.

If the coordinator lacks a terminal tool, delegate validation to a one-shot subagent that runs
the commands and returns pass/fail with the coverage percentage.

If any check fails, **stop and report to the user**. Do not continue to Phase 4.

Update `current_coverage_percent`. Mark "Phase 3 — Debugging (bugfix)" completed.

---

## Phase 4 — Refactoring (Refactor)

Mark "Phase 4 — Refactoring (refactor)" in-progress.

Invoke `review-tests-refactor` as a subagent with the same parameter set as Phase 1.

**Wait for completion.**

**Validate the handoff — all three checks must pass before continuing:**

1. Read `test-review-state.json`. Assert `"refactor"` is in `phases_completed`.
2. Run `${input:testCommand} -q --tb=no`. All tests must pass.
3. Run coverage as in Phase 0 §2. Read `totals.percent_covered` from `.coverage-report.json`. Assert ≥ baseline.

If the coordinator lacks a terminal tool, delegate validation to a one-shot subagent that runs
the commands and returns pass/fail with the coverage percentage.

If any check fails, **stop and report to the user**.

Re-run the coverage command from Phase 0 §2 with JSON output. Read `totals.percent_covered`
from the refreshed `.coverage-report.json` and write it as `"final_coverage_percent"` in the state file.

---

## Phase 5 — Push and PR

Push the current branch to origin:

```bash
git push -u origin HEAD
```

Then open a PR against the branch specified in the user's prompt. The PR title should be:

```
test: automated test quality review — pruning, expansion, debugging, refactoring
```

The PR body should include:

```markdown
## Test Quality Review

This PR was generated by the automated `review-tests` workflow across four phases.

### Summary

Baseline coverage: X% → Final coverage: X%

| Phase       | Tests removed | Tests rewritten | Tests added | Bugs found | Bugs fixed |
| ----------- | ------------- | --------------- | ----------- | ---------- | ---------- |
| Pruning     | N             | N (deferred)    | —           | N          | N          |
| Expansion   | —             | —               | N           | N          | N          |
| Debugging   | —             | —               | N           | N          | N          |
| Refactoring | —             | N               | —           | N          | N          |

### Production bugs found and fixed

<list>

### Notable deletions

<list rationale for significant cuts>

### Coverage gaps remaining

<any gaps that could not be safely tested>
```

---

## Phase 6 — Summary

Report to the user:

```
## Test Quality Review — Complete

Baseline coverage : X%   →   Final coverage : X%

| Phase    | Tests removed | Tests rewritten | Tests added | Bugs found | Bugs fixed |
| -------- | ------------- | --------------- | ----------- | ---------- | ---------- |
| Delete   | N             | N (deferred)    | —           | N          | N          |
| Coverage | —             | —               | N           | N          | N          |
| Bug-fix  | —             | —               | N           | N          | N          |
| Refactor | —             | N               | —           | N          | N          |
```

List any production bugs found and fixed across all four phases.
