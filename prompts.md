# Prompt 6

Implement the following bug fixes and feature improvements on this branch and commit the changes. Follow the instructions in AGENTS.md and use the skills available in this repo to work efficiently. Ensure all UI changes are verified via playwright-cli and that elements actually render on the page. Unit tests and pre-commit must pass before committing.

# Prompt 5

Task: Execute the full review-tests workflow on this branch--focusing ONLY on the new code added in this branch--sequentially through these four phases:

1. **Pruning:** Delete low-value or redundant tests.
2. **Expansion:** Add coverage for untested edge cases.
3. **Debugging:** Identify and fix bugs revealed by the tests.
4. **Refactoring:** Improve the architecture and readability of existing tests.

Parameters:

- testCommand: uv run pytest
- lintCommand: uv run pre-commit run --all-files
- appRoot: apps/
- testRoot: tests/
- coverageThreshold: 99

Granular Committing Protocol (Mandatory):
Do not wait until the end of a phase to commit. You must follow a "Commit-per-Logical-Change" strategy:

- **Phase 1 (Pruning):** Commit after each individual test file or logical test suite is deleted.
- **Phase 2 (Expansion):** Commit after each new test case or functional coverage block is added.
- **Phase 3 (Debugging):** Commit after each specific bug fix (one commit per bug).
- **Phase 4 (Refactoring):** Commit after each discrete refactoring step (e.g., "extracted helper method," "renamed variables for clarity").

Commit Message Requirements:
Each commit must use Conventional Commits format (e.g., `test:`, `fix:`, `refactor:`, `chore:`) and include a detailed body explaining what was changed and why.

Final Action: Once all phases are complete, ensure the tests pass and the changes that you made are committed, but not pushed.

# Prompt 4

Implement the following bug fixes and feature improvements on this branch and commit the changes. Follow the instructions in AGENTS.md and use the skills available in this repo to work efficiently. Ensure all UI changes are verified via playwright-cli and that elements actually render on the page. Unit tests and pre-commit must pass before committing.

- The closing of the managed configuration modal is still clunky; the background changes immediately, but the modal is still there and hangs around a little too long. Rethink this user experience to make it clear what happened and ensure the modal closes quickly (but not too quickly) so the user (a) knows it was saved and (b) isn't left with the impression there is a bug.
- Adding duplicate variables raises an integrityError, which is good this is enforced in the DB. However, we need to catch these in the form clean methods and present a friendly error to the user. Add unit tests to reproduce this with both policy- and fleet-level variables to ensure the keys are unique for the given variable type (and fleet, if specified) within a policy. Do not change the existing unique constrants, only add form clean logic to catch the integrity errors before they happen.

# Prompt 3

Implement the following bug fixes and feature improvements on this branch and commit the changes:

- The managed configuration modal no longer disappears after saving (the background turns white again, but the modal doesn't close). It should stay open just long enough to give the user feedback that the value saved, then close smoothly.
- In the policy variables, it's odd to say the variables have "Org" scope when they exist only for this policy. Rename the "Org" / "Organization" scope to "Policy" (and ensure the underlying behavior is consistent with this label).

Ensure all UI changes are verified via playwright-cli and that elements actually render on the page. Unit tests and pre-commit must pass before committing.

# Prompt 2

Implement the following bug fixes and feature improvements on this branch and commit the changes:

- Investigate how organization-level tenancy is handled permission-wise in this project, and update AGENTS.md to clarify this for future tasks.
- Implement the changes/improvements noted to the policy editor views in this branch (in particular, I don't think "staff" permissions should be required)
- Convert the flowbite_docs.txt to a skill for future agents to use, focusing on the features in flowbite that are most relevant to this project
- Double check the kiosk implementation; my memory is that the custom launcher is a separate thing where you have to provide your own launcher. We just want to allow using the built-in kiosk launcher for now.
- Note that detailed policy edtiro applies only to Android EMM; for TInyMDM, they would just enter the ID of the poilcy on the TinyMDM side (investigate and confirm this)

Ensure all UI changes are verified via playwright-cli and that elements actually render on the page. Unit tests and pre-commit must pass before committing.

# Prompt 1

Implement the following bug fixes and feature improvements on this branch and commit the changes:

- The "Saved" message is malformed: "\u2713 Saved"
- When changing the package name of ODK Collect, the package name in the list view doesn't update until a page reload. It needs to be swapped with HTMX
- The green check mark when changing values in an app row is barely visible, and also makes the row jump left. Let's come up with another effect to show that an element has been saved, keeping the effect as close as possible to the element in question (for example a highlight that fades). A green check mark right next to the element that fades and doesn't adjust the overall layout of the page would also be fine.
- When clicking save in a managed configuration modal, the modal should close
- Let's add a button to copy the variable "code" ("{{ variable_name }}") for each policy variable
- Let's move password policy between the policy name and applications
- Let's add another section (between Always-on VPN and Developer Options) to support various options in the Kiosk Mode settings of the AMAPI api (see https://developers.google.com/android/management/reference/rest/v1/enterprises.policies#KioskCustomization and related configuration)
- Update the GitHub issue #99 with the new details of the implementation

Ensure all UI changes are verified via playwright-cli and that elements actually render on the page. Unit tests and pre-commit must pass before committing.
