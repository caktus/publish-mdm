# Test Review Report — Delete Phase

**Date:** 2025-07-25  
**Focus:** `tests/mdm/`  
**Baseline:** 200 tests, 55.7% coverage

## Files Reviewed

- `tests/mdm/test_admin.py` (554 lines)
- `tests/mdm/test_android_enterprise.py` (540 lines)
- `tests/mdm/test_forms.py` (35 lines)
- `tests/mdm/test_import_export.py` (187 lines)
- `tests/mdm/test_models.py` (150 lines)
- `tests/mdm/test_serializers.py` (223 lines)
- `tests/mdm/test_tinymdm.py` (540 lines)
- `tests/mdm/test_views.py` (561 lines)

---

## tests/mdm/test_forms.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_post_request_initialization` | — | n/a (KEEP) | KEEP | Verifies FirmwareSnapshotForm maps `deviceIdentifier` → `serial_number` and validates |
| `test_save_with_existing_device` | — | n/a (KEEP) | KEEP | Verifies form.save() links to an existing Device by serial_number |
| `test_save_without_existing_device` | — | n/a (KEEP) | KEEP | Verifies form.save() with no matching device sets instance.device = None |
| `test_empty_post_doesnt_save` | — | n/a (KEEP) | KEEP | Verifies that empty JSON body returns is_valid() == False |

---

## tests/mdm/test_models.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_fleet_save_without_mdm_env_vars` | — | n/a (KEEP) | KEEP | Verifies pull_devices() is NOT called when MDM env vars absent |
| `test_fleet_save_with_mdm_env_vars` | — | n/a (KEEP) | KEEP | Verifies pull_devices() IS called when MDM env vars present |
| `test_device_save_without_mdm_env_vars` | — | n/a (KEEP) | KEEP | Verifies push_device_config() is NOT called when env vars absent |
| `test_device_save_with_mdm_env_vars` | — | n/a (KEEP) | KEEP | Verifies push_device_config() IS called when env vars present |
| `test_fleet_group_name` | — | n/a (KEEP) | KEEP | Exercises Fleet.group_name @property |
| `test_policy_get_default` | — | n/a (KEEP) | KEEP | Exercises Policy.get_default() three-branch logic |
| `test_get_policy_data` | — | n/a (KEEP) | KEEP | Comprehensive test of Policy.get_policy_data() across multiple scenarios |
| `test_fleet_enroll_token_expired` | — | n/a (KEEP) | KEEP | Tests Fleet.enroll_token_expired @property for three date cases |
| `test_fleet_enrollment_url` | — | n/a (KEEP) | KEEP | Tests Fleet.enrollment_url @property across both MDM types |

---

## tests/mdm/test_serializers.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_basic_policy` | — | n/a (KEEP) | KEEP | Verifies default PolicySerializer output includes ODK Collect app |
| `test_password_policies` | — | n/a (KEEP) | KEEP | Verifies both device/work password policy entries with all fields |
| `test_no_password_policy_when_unspecified` | — | n/a (KEEP) | KEEP | Verifies PASSWORD_QUALITY_UNSPECIFIED omits passwordPolicies key |
| `test_vpn` | — | n/a (KEEP) | KEEP | Verifies alwaysOnVpnPackage produced from vpn fields |
| `test_no_vpn_when_empty` | — | n/a (KEEP) | KEEP | Verifies empty vpn_package_name omits alwaysOnVpnPackage key |
| `test_developer_settings_allowed` | — | n/a (KEEP) | KEEP | Verifies advancedSecurityOverrides produced when developer settings allowed |
| `test_developer_settings_disabled` | — | n/a (KEEP) | KEEP | Verifies disabled developer settings omit advancedSecurityOverrides key |
| `test_applications` | — | n/a (KEEP) | KEEP | Verifies explicit application rows appear in output list |
| `test_variable_substitution` | — | n/a (KEEP) | KEEP | Verifies {{ var }} template substitution in managed_configuration |
| `test_fleet_variable_overrides_org` | — | n/a (KEEP) | KEEP | Verifies fleet-level variable takes precedence over org-level same key |
| `test_device_system_variables` | — | n/a (KEEP) | KEEP | Verifies device.imei and device.serial_number system variables resolved |
| `test_odk_collect_always_first` | — | n/a (KEEP) | KEEP | Verifies ODK Collect app is always first in the applications list |
| `test_unresolved_variable_preserved` | — | n/a (KEEP) | KEEP | Verifies unknown {{ var }} is left as-is in output |

---

## tests/mdm/test_import_export.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_export` | — | n/a (KEEP) | KEEP | Verifies DeviceResource export has correct columns and all Device rows |
| `test_valid_import` | — | n/a (KEEP) | KEEP | Verifies full import lifecycle: update, fleet change, create, skip |
| `test_invalid_import` | — | n/a (KEEP) | KEEP | Verifies validation and non-existent-FK errors are surfaced correctly |
| `test_valid_import_dry_run` | — | n/a (KEEP) | KEEP | Verifies push_device_config() only fires on confirmed import (not dry run) |

---

## tests/mdm/test_admin.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_confirm_import_with_no_errors` | — | n/a (KEEP) | KEEP | Verifies happy-path admin import confirmation with 1 new + 2 updated devices |
| `test_confirm_import_with_errors` | — | n/a (KEEP) | KEEP | Verifies partial-error import shows per-row errors and still saves valid rows |
| `test_device_save` | — | n/a (KEEP) | KEEP | Verifies push_device_config() called on admin save; MDM error shown to user |
| `test_new_fleet` | — | n/a (KEEP) | KEEP | Verifies add_group_to_policy() called on fleet creation; MDM error shown |
| `test_existing_fleet` | — | n/a (KEEP) | KEEP | Verifies add_group_to_policy() called only when policy changes |
| `test_delete_fleet_successful` | — | n/a (KEEP) | KEEP | Verifies fleet deleted when delete_group() returns True |
| `test_delete_fleet_no_api_credentials` | — | n/a (KEEP) | KEEP | Verifies fleet NOT deleted when MDM not configured |
| `test_delete_fleet_has_devices` | — | n/a (KEEP) | KEEP | Verifies fleet NOT deleted when delete_group() returns False |
| `test_delete_fleet_api_error` | — | n/a (KEEP) | KEEP | Verifies fleet NOT deleted and error message shown on API error |
| `test_delete_selected_fully_successful` | — | n/a (KEEP) | KEEP | Verifies bulk delete_selected action deletes all targeted fleets |
| `test_delete_selected_failures` | — | n/a (KEEP) | KEEP | Verifies partial bulk delete: has-devices and API errors handled correctly |
| `test_delete_selected_no_api_credentials` | — | n/a (KEEP) | KEEP | Verifies bulk delete_selected is a no-op when MDM not configured |
| `test_fleet_save` | — | n/a (KEEP) | KEEP | Verifies pull_devices() called on admin fleet save; MDM error shown |
| `test_new_policy` | — | n/a (KEEP) | KEEP | Verifies create_or_update_policy() called for new policy (if MDM supports it) |
| `test_existing_policy` | — | n/a (KEEP) | KEEP | Verifies policy and per-device pushes on policy edit (AE path) |

---

## tests/mdm/test_tinymdm.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_env_variables_not_set` | — | n/a (KEEP) | KEEP | Verifies TinyMDM.is_configured is False when no env vars |
| `test_env_variables_set` | — | n/a (KEEP) | KEEP | Verifies TinyMDM.session is a Session instance when env vars present |
| `test_pull_devices` | — | n/a (KEEP) | KEEP | End-to-end: API response → DB upsert, snapshots, apps, fleets |
| `test_push_device_config` | — | n/a (KEEP) | KEEP | Verifies user-update, group-add, and optional message API calls |
| `test_push_device_config_new_device` | — | n/a (KEEP) | KEEP | Verifies push_device_config() does not crash when raw_mdm_device is None |
| `test_sync_fleet` | — | n/a (KEEP) | KEEP | Verifies pull_devices + per-device push for devices with app_user_name set |
| `test_sync_fleet_with_push_config_false` | — | n/a (KEEP) | KEEP | Verifies push_config=False suppresses push_device_config calls |
| `test_sync_fleets` | C2, C3 | Yes — sole cover of TinyMDM.sync_fleets() | REFACTOR | C3: patches internal `sync_fleet` collaborator. C2: `call_list_args` is a typo (should be `call_args_list`) so the per-call assertion loop never executes; the test passes vacuously regardless of which fleets are passed. Should use `call_args_list` and verify each call's first argument is a fleet from Fleet.objects. |
| `test_create_group` | — | n/a (KEEP) | KEEP | Verifies create_group() POSTs correct body and sets fleet.mdm_group_id |
| `test_add_group_to_policy` | — | n/a (KEEP) | KEEP | Verifies add_group_to_policy() POSTs to correct URL |
| `test_get_enrollment_qr_code` | — | n/a (KEEP) | KEEP | Verifies QR code URL fetched and image downloaded into fleet.enroll_qr_code |
| `test_delete_group_successful` | — | n/a (KEEP) | KEEP | Verifies delete_group() returns True when no devices in DB or MDM |
| `test_delete_group_fails_if_devices_in_db` | — | n/a (KEEP) | KEEP | Verifies delete_group() returns False if DB has devices for fleet |
| `test_delete_group_fails_if_devices_in_tinymdm` | — | n/a (KEEP) | KEEP | Verifies delete_group() returns False if TinyMDM reports devices in group |
| `test_delete_group_succeeds_if_does_not_exist_in_tinymdm` | — | n/a (KEEP) | KEEP | Verifies 404 from TinyMDM means group doesn't exist → True returned |
| `test_create_user` | — | n/a (KEEP) | KEEP | Verifies create_user() POSTs correct body and adds user to group |
| `test_request` | — | n/a (KEEP) | KEEP | Verifies request() raises HTTPError with api_error attribute on non-2xx responses |
| `test_check_license_limit` | — | n/a (KEEP) | KEEP | Verifies check_license_limit() returns (limit, enrolled) tuple |
| `test_max_request_retries` | — | n/a (KEEP) | KEEP | Verifies POST retried only on 429; GET retried on 429/500 (up to 6 requests) |
| `test_request_retries_until_success` | — | n/a (KEEP) | KEEP | Verifies retry stops early on successful response |

---

## tests/mdm/test_android_enterprise.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `test_env_variables_not_set` | — | n/a (KEEP) | KEEP | Verifies AndroidEnterprise.is_configured False without env vars |
| `test_env_variables_set` | — | n/a (KEEP) | KEEP | Verifies is_configured True and enterprise_name formatted correctly |
| `test_pull_devices` | — | n/a (KEEP) | KEEP | Full pull: snapshots, apps, battery, provisioning-state filter, fleet scoping |
| `test_get_devices` | — | n/a (KEEP) | KEEP | Verifies get_devices() caching — subsequent calls skip API request |
| `test_sync_fleet` | — | n/a (KEEP) | KEEP | Verifies pull + targeted per-device push for devices with app_user_name |
| `test_sync_fleet_with_push_config_false` | — | n/a (KEEP) | KEEP | Verifies push suppressed when push_config=False |
| `test_sync_fleets` | C2, C3 | Yes — sole cover of AndroidEnterprise.sync_fleets() | REFACTOR | Same typo bug as TinyMDM version: `call_list_args` never iterates, so per-fleet assertions are vacuous. Should use `call_args_list`. |
| `test_get_enrollment_qr_code` | — | n/a (KEEP) | KEEP | Verifies enrollment token API call, QR code stored, expiry/value set on fleet |
| `test_delete_group` | — | n/a (KEEP) | KEEP | Verifies AE delete_group() returns True (no-group MDM), False if DB has devices |
| `test_execute` | — | n/a (KEEP) | KEEP | Verifies execute() raises HttpError with api_error attribute on non-2xx |
| `test_create_or_update_policy` | — | n/a (KEEP) | KEEP | Verifies create_or_update_policy() skips API when no data; sends policy body |
| `test_push_device_config` | — | n/a (KEEP) | KEEP | Verifies policy-patch + device-patch + old-policy-delete calls per scenario |
| `test_push_device_config_no_api_requests` | — | n/a (KEEP) | KEEP | Verifies no API calls when raw_mdm_device is None or policy data unavailable |

---

## tests/mdm/test_views.py

| Test | Criterion failed | Unique lines covered? | Action | Notes |
|------|------------------|-----------------------|--------|-------|
| `TestPolicyList.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_list |
| `TestPolicyList.test_lists_org_policies` | — | n/a (KEEP) | KEEP | Verifies policies queryset is org-scoped; cross-org policy excluded |
| `TestPolicyAdd.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_add |
| `TestPolicyAdd.test_get` | — | n/a (KEEP) | KEEP | Verifies GET returns 200 with form in context |
| `TestPolicyAdd.test_valid_post_creates_policy_and_redirects` | — | n/a (KEEP) | KEEP | Verifies policy + default ODK app created; redirect to edit URL |
| `TestPolicyAdd.test_invalid_post_returns_form` | — | n/a (KEEP) | KEEP | Verifies empty name returns 200 with form errors |
| `TestPolicyEdit.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_edit |
| `TestPolicyEdit.test_get` | C4 | Yes — sole cover of policy_edit GET path (views.py L139–161) | REFACTOR | C4: asserts only HTTP 200 with no context assertion. Sole cover of the GET code path which builds name_form, password_form, vpn_form, kiosk_form, developer_form, variables, app_forms. Should assert at minimum that policy/name_form/app_forms appear in response.context. |
| `TestPolicyEdit.test_org_isolation` | — | n/a (KEEP) | KEEP | Verifies cross-org policy lookup yields 404 |
| `TestPolicySaveName.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_name |
| `TestPolicySaveName.test_valid_post_saves_and_returns_partial` | — | n/a (KEEP) | KEEP | Verifies name saved, context["saved"] is True |
| `TestPolicySaveName.test_invalid_post_returns_form_errors` | — | n/a (KEEP) | KEEP | Verifies empty name returns form errors in context |
| `TestPolicySaveName.test_org_isolation` | — | n/a (KEEP) | KEEP | Verifies cross-org policy yields 404 |
| `TestPolicySaveOdkPackage.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_odk_package |
| `TestPolicySaveOdkPackage.test_valid_post_saves_and_updates_pinned_app` | — | n/a (KEEP) | KEEP | Verifies policy.odk_collect_package saved and pinned app row updated |
| `TestPolicyAddApplication.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_add_application |
| `TestPolicyAddApplication.test_valid_post_adds_app` | — | n/a (KEEP) | KEEP | Verifies application count increases and context["saved"] is True |
| `TestPolicyAddApplication.test_invalid_post_returns_form_errors` | — | n/a (KEEP) | KEEP | Verifies empty package_name returns form errors |
| `TestPolicySaveApplication.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_application |
| `TestPolicySaveApplication.test_valid_post_saves_app` | — | n/a (KEEP) | KEEP | Verifies install_type updated and context["saved"] is True |
| `TestPolicySaveApplication.test_org_isolation` | — | n/a (KEEP) | KEEP | Verifies cross-org policy app edit yields 404 |
| `TestPolicyDeleteApplication.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_delete_application |
| `TestPolicyDeleteApplication.test_deletes_app` | — | n/a (KEEP) | KEEP | Verifies PolicyApplication deleted from DB |
| `TestPolicyDeleteApplication.test_cannot_delete_pinned_odk_collect_row` | — | n/a (KEEP) | KEEP | Verifies pinned ODK Collect row (order=0) returns 403 |
| `TestPolicySavePassword.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_password |
| `TestPolicySavePassword.test_valid_post_saves` | — | n/a (KEEP) | KEEP | Verifies device_password_quality saved and context["saved"] is True |
| `TestPolicySaveVPN.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_vpn |
| `TestPolicySaveVPN.test_valid_post_saves` | — | n/a (KEEP) | KEEP | Verifies vpn_package_name saved and context["saved"] is True |
| `TestPolicySaveDeveloper.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_developer |
| `TestPolicySaveDeveloper.test_valid_post_saves` | — | n/a (KEEP) | KEEP | Verifies developer_settings saved and context["saved"] is True |
| `TestPolicySaveKiosk.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_kiosk |
| `TestPolicySaveKiosk.test_valid_post_saves` | — | n/a (KEEP) | KEEP | Verifies kiosk_system_navigation saved and context["saved"] is True |
| `TestPolicySaveManagedConfig.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_save_managed_config |
| `TestPolicySaveManagedConfig.test_valid_json_saves` | — | n/a (KEEP) | KEEP | Verifies valid JSON saved to managed_configuration; saved/error context set |
| `TestPolicySaveManagedConfig.test_invalid_json_returns_error` | — | n/a (KEEP) | KEEP | Verifies invalid JSON sets context["error"] and context["saved"] is False |
| `TestPolicySaveManagedConfig.test_empty_config_clears_field` | — | n/a (KEEP) | KEEP | Verifies empty string clears managed_configuration to None |
| `TestPolicyAddVariable.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_add_variable |
| `TestPolicyAddVariable.test_valid_post_creates_variable` | — | n/a (KEEP) | KEEP | Verifies PolicyVariable created with correct key/org |
| `TestPolicyAddVariable.test_invalid_post_returns_form_errors` | — | n/a (KEEP) | KEEP | Verifies empty key returns form errors |
| `TestPolicyAddVariable.test_org_is_pre_set_on_form_instance` | — | n/a (KEEP) | KEEP | Verifies org is pre-set on form.instance before validation (model.clean() requirement) |
| `TestPolicyAddVariable.test_duplicate_policy_variable_raises_form_error` | — | n/a (KEEP) | KEEP | Verifies duplicate org-scoped key shows friendly form error |
| `TestPolicyAddVariable.test_duplicate_fleet_variable_raises_form_error` | — | n/a (KEEP) | KEEP | Verifies duplicate fleet-scoped key shows friendly form error |
| `TestPolicyAddVariable.test_same_key_different_scope_is_allowed` | — | n/a (KEEP) | KEEP | Verifies same key in org+fleet scopes is not a duplicate |
| `TestPolicyDeleteVariable.test_login_required` | — | n/a (KEEP) | KEEP | Verifies @login_required on policy_delete_variable |
| `TestPolicyDeleteVariable.test_deletes_variable` | — | n/a (KEEP) | KEEP | Verifies PolicyVariable deleted from DB |
| `TestPolicyDeleteVariable.test_org_isolation` | — | n/a (KEEP) | KEEP | Verifies cross-org policy lookup yields 404 before variable lookup |

---

## Summary

- **Tests reviewed:** 200
- **Kept:** 197 | **Refactored (deferred):** 3 | **Deleted:** 0 | **Bugs fixed:** 0
- **Files deleted entirely:** none
- **Baseline coverage:** 55.7% → After delete: 55.7% (no deletions made)
- **Tests downgraded DELETE → REFACTOR due to unique coverage:** N/A (no DELETE candidates found)
- **Pre-existing failures:** none
- **Production bugs found and fixed:** none

### REFACTOR candidates (input for next phase)

1. **`tests/mdm/test_tinymdm.py::TestTinyMDM::test_sync_fleets`** — C2+C3  
   `call_list_args` is a typo for `call_args_list`; the per-fleet assertion loop never executes (MagicMock attribute iteration yields nothing). Also patches internal `sync_fleet` collaborator. Should use `call_args_list` and verify each call's argument is a Fleet from the queryset.

2. **`tests/mdm/test_android_enterprise.py::TestAndroidEnterprise::test_sync_fleets`** — C2+C3  
   Identical typo bug: `call_list_args` instead of `call_args_list`. Same fix applies.

3. **`tests/mdm/test_views.py::TestPolicyEdit::test_get`** — C4  
   Asserts only HTTP 200 — no context assertions. Sole cover of `policy_edit` GET path (views.py L139–161) which builds eight context keys including all form instances. Should assert at minimum: `assert "policy" in response.context`, `assert "name_form" in response.context`, `assert "app_forms" in response.context`.
