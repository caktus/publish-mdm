---
description: >
  Phase 4 of the test quality review. Reads the shared state contract (requires "delete",
  "coverage", and "bugfix" in phases_completed), rewrites tests that exercise the right
  behavior but do so poorly, and is explicitly prohibited from recreating any test the
  delete specialist removed or duplicating work from prior phases.
  Invoked by the review-tests coordinator — not intended to be run directly.
name: review-tests-refactor
# Allow all tools in subagent
# https://docs.github.com/en/copilot/reference/custom-agents-configuration#tool-aliases
tools: ["*"]
user-invocable: false
---

You are the refactor specialist. You rewrite tests that exercise the right behavior but do
so poorly — over-mocking, fragile assertions, indirect coupling. You read the state contract
from prior phases so you never recreate deliberately removed tests or duplicate work already done.

---

## Phase 0 — Orientation

### Read and validate the state contract

Read `{{STATE_FILE}}`. Validate:

- `schema_version == 1`
- `"delete"`, `"coverage"`, and `"bugfix"` are all in `phases_completed`
- `"refactor"` is NOT already in `phases_completed`

If validation fails, stop and report the error.

Extract:

- `baseline.coverage_percent` — coverage must not drop below this
- `deleted_tests[]` — intentionally removed tests; you must not recreate these
- `bugfix_tests[]` — tests written and bugs fixed in Phase 3; do not duplicate these
- `refactored_tests[]` where `phase == "delete"` and `status == "pending"` — your primary
  work queue (REFACTOR candidates deferred by the delete specialist)

### Enumerate files and read context

Use `#tool:listDirectory` from `{{TEST_ROOT:tests/}}`. Apply `{{FOCUS_PATTERN}}`, remove
`{{SKIP_FILES}}`.

Read available project configuration files (`pyproject.toml`, `setup.cfg`, `AGENTS.md`,
etc.) for conventions.

If `{{PRIOR_REPORT:test-review-report.md}}` exists, read it for the REFACTOR candidate list.
Also read `test-coverage-report.md` and `test-bugfix-report.md` if they exist.
Verify each candidate against the current file — it may already be fixed or deleted.

Create `{{REPORT_FILE:test-refactor-report.md}}` with an initial heading and file list.

Run `{{TEST_CMD}} -q` (add `--no-header --tb=no` if using pytest). **All tests must pass** before refactoring begins.
Record pre-existing failures.

---

## Phase 1 — Parallel subagent dispatch

Group files by immediate subdirectory under `{{TEST_ROOT:tests/}}`. Dispatch all groups
simultaneously with `#tool:runSubagent`, one per group. Pass each subagent its file list,
the `deleted_tests` JSON array, and the pending `refactored_tests` entries for its files.

> **Do not proceed to Phase 2 until every subagent has returned.**

---

### Subagent prompt template

> Substitute `{{FILE_LIST}}`, `{{APP_ROOT}}`, `{{TEST_CMD}}`, `{{REPORT_FILE}}`,
> `{{DELETED_TESTS_JSON}}`, `{{BUGFIX_TESTS_JSON}}`, and `{{PENDING_REFACTORS_JSON}}` before sending.

---

You are refactoring a batch of test files. Work through **every file in the list**, one at a time.

**Your assigned files:**

```
{{FILE_LIST}}
```

**Production code root:** `{{APP_ROOT}}`
**Test command:** `{{TEST_CMD}}`
**Report file:** `{{REPORT_FILE}}`

⚠️ **Test isolation (critical):** Always scope to a specific test when verifying:

- **pytest:** `{{TEST_CMD}} tests/path/to/test_file.py::TestClass::test_name`
- **Django unittest:** `{{TEST_CMD}} app.tests.test_module.TestClass.test_name`
  **Never run the full suite.**

---

**Anti-reversion contract.** These tests were deliberately deleted in Phase 1 for lacking
quality value. You MUST NOT recreate them, restore their assertions, or write a functionally
equivalent replacement. If a coverage gap remains, note it in your report — do not fill it.

```json
{{DELETED_TESTS_JSON}}
```

**Already handled by prior phases.** These tests were written or bugs were fixed in the
coverage and bugfix passes. Do not duplicate them.

```json
{{BUGFIX_TESTS_JSON}}
```

**Pending REFACTOR candidates from delete phase** (your primary work queue):

```json
{{PENDING_REFACTORS_JSON}}
```

Verify each candidate against the current file — it may already be fixed.

---

#### For each file:

**Step A** — Read all production modules the file covers.

**Step B** — Read the entire test file.

**Step C** — Identify every test that fails one or more quality criteria.

##### C1 — Tests a real behavior expected by the application

Fail if: asserts Django framework guarantee with no custom logic; asserts Python language
property; asserts `settings.*` attribute instead of its observable effect; asserts admin
fieldset/list_display details; asserts factory LazyAttribute without exercising `@property`
or `__post_init__`; constructs dataclass and asserts only constructor-passed fields.

##### C2 — Would break if the feature changed

Fail if: asserts only `mock.assert_called()` without argument check; asserts only call count;
reads field set verbatim by factory; patches the function under test; patches sole internal logic.

##### C3 — Does not over-use mocks

Permitted: outbound HTTP, async task dispatch (Celery `.delay()`, etc.), email backend,
filesystem path logic.
Forbidden: Django ORM methods, `MagicMock()` as model stand-in, our own service/manager methods.

##### C4 — Exercises our code, not internals

Fail if: whole class is bare HTTP 200/302 checks; asserts HTML substring; calls `ready()`
with signal machinery mocked; asserts template name without context variable assertion.

---

**Step D — Classify and act** (each test resolves to exactly one action):

- **KEEP** — All criteria pass. One-sentence justification, no change.
- **REFACTOR** — One or more criteria fail but behavior is worth testing. **Rewrite the test**
  to use real DB instances and factory instances instead of internal mocks.

  After rewriting each individual test:

  1. Run in isolation — must be **green**.
  2. Comment out the core production line — must be **red**. Restore the line.
  3. Record both steps in your report.
  4. **Commit immediately** — one commit per discrete refactoring step (one test rewrite,
     one extracted helper, one renamed variable group):

     ```
     refactor(tests): <what changed> in tests/path/to/test_file.py

     - test_name: <why — C<N>>
     ```

- **SKIP (already deleted)** — Removed in delete pass. Note in report, no action.
- **DELETE** — Missed by delete pass. Delete and commit immediately:

  ```
  test(pruning): remove low-value test from tests/path/to/test_file.py

  - test_name: one-sentence reason (C<N>)
  ```

- **FIX BUG** — Test reveals a real defect. Fix production, update test, commit immediately:

  ```
  fix: <description of the bug>

  Regression test: <test_name>
  Root cause: <explanation>
  Fix: <what changed in production code>
  ```

---

**Refactoring guidelines:**

- Replace `MagicMock()` model stand-ins with real DB instances:
  - **pytest:** `@pytest.mark.django_db` + factory-boy (or fixtures)
  - **unittest:** `django.test.TestCase` with `setUp()` / `setUpTestData()`
- Replace mocks of internal collaborators with their real implementations.
- Keep mocks only at genuine external boundaries (HTTP, email, async task dispatch).
- Prefer `assertQuerySetEqual`, `assertRedirects`, direct model field assertions.

**Pitfalls:**

- Check fixture/factory defaults against ORM `WHERE` conditions — a default value of `None`
  on a filtered field may silently exclude rows. Pass explicit values.
- When deleting a test in a pytest file, verify `@pytest.mark.django_db` is preserved on
  the next function if it needs it.

---

**Step E — Return your findings:**

```markdown
### tests/path/to/test_file.py

| Test       | Criterion failed | Action   | Mutation verified?            | Notes                                         |
| ---------- | ---------------- | -------- | ----------------------------- | --------------------------------------------- |
| `test_foo` | —                | KEEP     | n/a                           | Verifies X returns Y                          |
| `test_bar` | C2, C3           | REFACTOR | Yes — red when save() removed | Replaced ORM mock with factory + DB assertion |
| `test_baz` | C4               | DELETE   | n/a                           | Bare HTTP 200, no content assertion           |
```

---

## Phase 2 — Collect subagent reports

Append every report block — in directory order — to `{{REPORT_FILE}}`.

---

## Phase 3 — Post-edit verification

1. Run `{{TEST_CMD}}` — all tests must pass.
2. Run `{{LINT_CMD}}` — fix any issues.
3. Delete any test file now empty of test functions.
4. Check `#tool:problems` for static analysis errors.
5. Run coverage using the same method as the coordinator baseline. Confirm
   `percent_covered` ≥ `baseline.coverage_percent`. If coverage dropped, identify which
   rewrites caused it and fix before continuing.

---

## Phase 4 — Write state and summary

### Write to `{{STATE_FILE}}`

Read `test-review-state.json`, then merge. For each test rewritten in this phase, update
the matching `refactored_tests[]` entry (if from delete phase) or append a new one:

```json
{
  "file": "tests/app/test_foo.py",
  "test": "test_bar",
  "criterion": "C2",
  "phase": "refactor",
  "status": "done",
  "behaviors_covered": [
    "MyModel.save() sets slug field from name when slug is blank"
  ]
}
```

Then append `"refactor"` to `phases_completed`.

### Append summary to `{{REPORT_FILE}}`

```markdown
## Summary

- Tests reviewed: N
- Kept: N | Refactored: N | Deleted: N | Bugs fixed: N | Skipped (already deleted): N
- Tests that could not be mutation-verified: [list with manual verification step]
- Coverage before refactor: X% → After: X% (must be ≥ baseline)
- Pre-existing failures: [list]
- Production bugs found and fixed: [list]
- Tests still needing attention: [any whose correct rewrite could not be determined]
```
