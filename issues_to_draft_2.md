# Prompt #2

Copied from: https://caktusgroup.slack.com/archives/C082BKPU98D/p1765228363270489

Publish MDM - Android Management API Support

- Initial Android Management API support
- Add self-service flow for enrolling a new enterprise
- Add button to send email with work profile enrollment link
- Add support for wiping devices remotely
- Add support for CLEAR_APP_DATA command for ODK Collect app (to erase app data between field sessions - a way to start fresh with a new Collect project)
- Implement companion app to push device location and firmware details to Publish MDM (via launchApp SetupAction?)
- Implement user interface for some basic/common settings in the policy JSON
- Add support for private play console managed iframe (https://developers.google.com/android/management/reference/rest/v1/enterprises.webTokens)
- Documentation updated
- Workflows designed

Assumptions:
- Device geolocation via MDM not supported (separate app needed)
- No custom background image support
- May not be possible to configure device language via MDM (would need to be customized in the firmware)
- Only basic MDM settings will be possible without developer intervention
- Remote screensharing on the device will not be supported

Notes:
- Need to test flashing and re-enrolling the same device (duplicate serial number)

**Sample prompt for creating issues:** Use the #issue_write tool to create these issues in the caktus/publish-mdm repo, except for the ops issue which should go in the caktus/app.publishmdm.com repo. All issues should be added to the Publish MDM board and tagged/labeled appropriately.


> **Coverage note**: "Implement user interface for some basic/common settings in the policy JSON" and "Add support for private play console managed iframe" are both covered by `feat(mdm): MVP form-based policy editor for Android Management API` in `issues_to_draft.md`. "Workflows designed" is addressed as part of the documentation issue below.

# feat: proof of concept Android companion app for geolocation data

## Background
A lightweight Android companion app (potentially derived from the firmware app) would collect device GPS coordinates and push them to the Publish MDM backend, enriching `Device` records with location data.

## Scope (PoC only)

### Backend Changes
1. **Add location fields to `Device`** (`apps/mdm/models.py`): `latitude = DecimalField(null=True, blank=True, max_digits=9, decimal_places=6)`, `longitude = DecimalField(null=True, blank=True, max_digits=9, decimal_places=6)`, `location_updated_at = DateTimeField(null=True, blank=True)`. Create migration.

2. **New REST endpoint**: `POST /api/devices/{device_id}/location/` — accepts `{"lat": ..., "lon": ..., "timestamp": ...}`. Authenticate via a device-scoped token (use `device_id` + a shared secret from the MDM policy context, or introduce a simple API key stored in the policy JSON). Validate and update `Device` fields. Use DRF `APIView` or function-based view.

3. **New URL**: add to `config/urls.py` or a new `apps/mdm/api_urls.py`.

### Android App
1. **New Android project** (Kotlin, MVVM) or fork of the firmware app.
2. **FusedLocationProviderClient** (Google Play Services) for GPS polling.
3. **Retrofit** HTTP client calling the backend endpoint above.
4. **Configuration**: backend URL and device ID injected via Android Managed Config (already supported via MDM policy JSON).
5. **Permissions**: `ACCESS_FINE_LOCATION`, `INTERNET`.
6. **Schedule**: `WorkManager` periodic task (e.g., every 15 minutes).

## Key Files
- `apps/mdm/models.py` — `Device`
- `apps/mdm/api_urls.py` (new)
- `config/urls.py`
- Android project (separate repo or `android/` subdirectory)

## Verification
- Simulate a POST from curl; confirm `Device.latitude/longitude` updated.
- Run Android app on emulator; confirm location data reaches backend.

---

# feat(mdm): add enterprise_id to Organization for per-org Android enterprise management

## Background
`AndroidEnterprise` currently uses a single global `ANDROID_ENTERPRISE_ID` environment variable, meaning all organizations share one Android enterprise. Each `Organization` must own its enterprise so that device policies, enrollment tokens, and managed app configurations are fully scoped and isolated per org. This is a prerequisite for the self-service enterprise enrollment flow.

## Implementation Steps

1. **Add `enterprise_id` to `Organization`** (`apps/publish_mdm/models.py`):
   ```python
   enterprise_id = models.CharField(
       max_length=255, blank=True, default="",
       help_text="Android Management API enterprise ID, e.g. 'LC04aq3gkk'. "
                 "Set automatically by the self-service enrollment flow.",
   )
   ```
   Create and run migration (no data migration needed — `default=""` covers existing rows).

2. **Make `AndroidEnterprise` org-aware** (`apps/mdm/mdms/android_enterprise.py`):
   - Add an `organization` parameter to `__init__`.
   - Replace the hardcoded `os.getenv("ANDROID_ENTERPRISE_ID")` lookup with a property:
     ```python
     @property
     def enterprise_id(self):
         if self.organization and self.organization.enterprise_id:
             return self.organization.enterprise_id
         fallback = os.getenv("ANDROID_ENTERPRISE_ID", "")
         if fallback:
             import structlog
             structlog.get_logger().warning(
                 "android_enterprise.deprecated_global_enterprise_id",
                 organization=getattr(self.organization, "slug", None),
             )
         return fallback
     ```
   - Update `build_enterprise_name()` to call `self.enterprise_id`.

3. **Update `get_active_mdm_instance()`** (wherever it lives in `apps/mdm/`): accept an optional `organization` kwarg and forward it to the MDM class constructor.

4. **Update all callers** of `get_active_mdm_instance()` in `apps/publish_mdm/views.py` and Celery tasks to pass `organization=request.organization` (or the relevant org object).

5. **Update `Organization` admin** (`apps/publish_mdm/admin.py`): add `enterprise_id` to `readonly_fields` (or `fields`) on `OrganizationAdmin`.

## Key Files
- `apps/publish_mdm/models.py` — `Organization`
- `apps/mdm/mdms/android_enterprise.py` — `AndroidEnterprise`
- `apps/publish_mdm/admin.py` — `OrganizationAdmin`
- All views/tasks that construct the active MDM instance

## Verification
- Set `enterprise_id` on two orgs with different values; confirm MDM API calls use each org's enterprise ID and devices do not appear cross-org.
- Leave `enterprise_id` blank on a third org; confirm the global `ANDROID_ENTERPRISE_ID` env-var fallback is used and a deprecation warning is logged.
- Run the existing test suite; confirm no regressions.

---

# feat(mdm): add self-service enterprise enrollment flow

## Background
Creating an Android enterprise requires manually setting `ANDROID_ENTERPRISE_ID`. Org admins should be able to provision their own enterprise through the Publish MDM UI using the [Android Management API enterprise creation flow](https://developers.google.com/android/management/create-enterprise), avoiding developer intervention on every new deployment. This depends on the `enterprise_id` field added in the previous issue.

## Implementation Steps

The AMAPI enterprise creation flow has three steps:
1. Create a signup URL via `signupUrls.create` — returns a `name` (for later) and a redirect `url`.
2. Redirect the admin to the Google sign-up URL so they approve the enterprise creation.
3. Google redirects back with an `enterpriseToken` query param; exchange it via `enterprises.create`.

### Backend

1. **Add `get_signup_url(callback_url)` to `AndroidEnterprise`** (`apps/mdm/mdms/android_enterprise.py`):
   ```python
   def get_signup_url(self, callback_url: str) -> dict:
       return self.client.signupUrls().create(
           projectId=settings.ANDROID_ENTERPRISE_PROJECT_ID,
           callbackUrl=callback_url,
       ).execute()
   ```

2. **Add `create_enterprise(signup_name, enterprise_token, display_name)` to `AndroidEnterprise`**:
   ```python
   def create_enterprise(self, signup_name: str, enterprise_token: str, display_name: str) -> dict:
       return self.client.enterprises().create(
           projectId=settings.ANDROID_ENTERPRISE_PROJECT_ID,
           signupUrlName=signup_name,
           enterpriseToken=enterprise_token,
           body={"enterpriseDisplayName": display_name},
       ).execute()
   ```

3. **Add `enterprise_setup(request, organization_slug)` view** (`apps/publish_mdm/views.py`): `@login_required` + org membership check. On GET, calls `get_signup_url(callback_url=request.build_absolute_uri(reverse("publish_mdm:enterprise-callback", kwargs=...)))`, stores the returned `name` as `request.session["amapi_signup_name"]`, and redirects to the Google signup URL.

4. **Add `enterprise_callback(request, organization_slug)` view** (`apps/publish_mdm/views.py`): `@login_required`. Reads `enterpriseToken` from `request.GET`. Validates `request.GET.get("signupName")` matches `request.session.get("amapi_signup_name")` — return 400 if mismatch (CSRF-style protection). Calls `create_enterprise(...)`, extracts the returned enterprise `name` field (format: `enterprises/LC…`), strips the `enterprises/` prefix to get the enterprise ID, saves it to `organization.enterprise_id`. Redirects to the organization home with a success Django message.

5. **Add a settings key** to `config/settings/base.py`:
   ```python
   ANDROID_ENTERPRISE_PROJECT_ID = os.getenv("ANDROID_ENTERPRISE_PROJECT_ID", "")
   ```

6. **Add URLs** (`apps/publish_mdm/urls.py`):
   ```python
   path("o/<slug:organization_slug>/enterprise/setup/", views.enterprise_setup, name="enterprise-setup"),
   path("o/<slug:organization_slug>/enterprise/callback/", views.enterprise_callback, name="enterprise-callback"),
   ```

7. **Add a "Set up Android Enterprise" card** to the organization home or devices page. The card is shown only when `organization.enterprise_id` is blank and the active MDM is Android Enterprise.

## Key Files
- `apps/mdm/mdms/android_enterprise.py` — `get_signup_url`, `create_enterprise`
- `apps/publish_mdm/views.py` — `enterprise_setup`, `enterprise_callback`
- `apps/publish_mdm/urls.py`
- `config/settings/base.py` — `ANDROID_ENTERPRISE_PROJECT_ID`
- `config/templates/publish_mdm/` — "Set up Android Enterprise" UI

## Verification
- With `organization.enterprise_id` blank, click "Set up Android Enterprise"; confirm redirect to Google signup.
- Complete the signup flow; confirm `organization.enterprise_id` is saved and the setup button disappears.
- Simulate a `signupName` mismatch (tamper the session); confirm 400 is returned.
- Confirm `ANDROID_ENTERPRISE_PROJECT_ID` is documented in the README environment variable table.

---

# feat(mdm): add button to send work profile enrollment link by email

## Background
Device admins currently have to share the enrollment QR code image out-of-band. An "Email enrollment link" feature lets admins send the `Fleet.enrollment_url` (already a property on `Fleet`, format: `https://enterprise.google.com/android/enroll?et=<token>`) directly to a recipient's email, enabling device enrollment without physical QR code access. This is Android Enterprise-only (TinyMDM uses a different enrollment flow).

## Implementation Steps

1. **Create `SendEnrollmentLinkForm`** (`apps/publish_mdm/forms.py`):
   ```python
   class SendEnrollmentLinkForm(PlatformFormMixin, forms.Form):
       email = forms.EmailField(label="Recipient email address")
   ```

2. **Add `send_enrollment_link(request, organization_slug, fleet_id)` view** (`apps/publish_mdm/views.py`): accepts GET (renders the inline form) and POST (sends the email). Decorated with `@login_required`. On POST, validates form, sends email via Django's `send_mail`, returns an HTMX fragment replacing the form area with `"Enrollment link sent to <email>"`. On error, returns the form with inline error messages.

3. **Create email templates**:
   - `config/templates/email/enrollment_link.txt` — plain-text body with the enrollment URL.
   - `config/templates/email/enrollment_link.html` — HTML body with a call-to-action button linking to `fleet.enrollment_url`.
   - Subject: `"Enroll your Android device in {{ organization.name }}"`.

4. **Add URL** (`apps/publish_mdm/urls.py`):
   ```python
   path("o/<slug:organization_slug>/fleet/<int:fleet_id>/send-enrollment-link/", views.send_enrollment_link, name="fleet-send-enrollment-link"),
   ```

5. **Add the button to the fleet edit template** (`config/templates/publish_mdm/`): below the QR code image, add an HTMX-powered inline section:
   ```html
   <button hx-get="{% url 'publish_mdm:fleet-send-enrollment-link' ... %}" hx-target="#enrollment-link-form" hx-swap="innerHTML">
     Email enrollment link
   </button>
   <div id="enrollment-link-form"></div>
   ```
   Only show the button when `fleet.enrollment_url` is non-empty and the active MDM is Android Enterprise.

## Key Files
- `apps/publish_mdm/forms.py` — `SendEnrollmentLinkForm`
- `apps/publish_mdm/views.py` — `send_enrollment_link`
- `apps/publish_mdm/urls.py`
- `config/templates/email/enrollment_link.txt` (new)
- `config/templates/email/enrollment_link.html` (new)
- `config/templates/publish_mdm/` — fleet edit template

## Verification
- On the fleet page for an Android Enterprise fleet with a valid enrollment token, confirm the "Email enrollment link" button is visible.
- Submit a valid email address; confirm an inline success message appears without a page reload.
- Check the inbox; confirm the email subject matches and the body contains the correct `fleet.enrollment_url`.
- Submit an invalid email; confirm inline validation error is shown.
- For a TinyMDM fleet, confirm the button is absent.

---

# feat(mdm): add remote wipe support for Android Enterprise devices

## Background
Devices may need to be remotely wiped when decommissioned, lost, or stolen, or to erase sensitive data after a field deployment. The Android Management API supports a `WIPE` device command via [`devices.issueCommand`](https://developers.google.com/android/management/reference/rest/v1/enterprises.devices/issueCommand), which performs a factory reset of the device. This is a destructive, irreversible operation that requires an explicit confirmation step in the UI.

## Implementation Steps

1. **Add `wipe_device(device)` to `AndroidEnterprise`** (`apps/mdm/mdms/android_enterprise.py`):
   ```python
   def wipe_device(self, device):
       return self.client.enterprises().devices().issueCommand(
           name=f"enterprises/{self.enterprise_id}/devices/{device.device_id}",
           body={"type": "WIPE"},
       ).execute()
   ```

2. **Add `wipe_device` stub to the base `MDM` class**: raise `NotImplementedError` by default. For `TinyMDM`, check whether TinyMDM already has a wipe endpoint — implement if so, otherwise raise a user-friendly `MDMCommandNotSupportedError`.

3. **Add `wipe_device(request, organization_slug, device_pk)` view** (`apps/publish_mdm/views.py`):
   - GET: returns an HTMX modal fragment with a strongly worded confirmation: *"This will permanently erase ALL data on the device and cannot be undone."* and a red "Wipe device" confirm button.
   - POST: calls `get_active_mdm_instance(organization=request.organization).wipe_device(device)`, adds a Django messages success notification, returns an HTMX response that closes the modal and optionally refreshes the device row. On `MDMCommandNotSupportedError`, return an informative error fragment without a 500.

4. **Add URL** (`apps/publish_mdm/urls.py`):
   ```python
   path("o/<slug:organization_slug>/devices/<int:device_pk>/wipe/", views.wipe_device, name="device-wipe"),
   ```

5. **Add "Wipe device" button** to the device list row and/or device detail template. Mark it visually as a destructive action (red styling). The button fires `hx-get` to load the confirmation modal, which then `hx-post`s to confirm.

## Key Files
- `apps/mdm/mdms/android_enterprise.py` — `wipe_device`
- `apps/mdm/mdms/` — base `MDM` class
- `apps/publish_mdm/views.py` — `wipe_device`
- `apps/publish_mdm/urls.py`
- `config/templates/publish_mdm/` — device list/detail and modal templates

## Verification
- Click "Wipe device" on a connected AE device; confirm a confirmation modal with a warning appears.
- Confirm the wipe; confirm the AMAPI command is issued and the device begins a factory reset.
- Confirm the device row updates (e.g. shows "Wipe pending") on the next sync.
- Click "Wipe device" on a TinyMDM device; confirm a clear "Not supported" error message is shown, not a 500.

---

# feat(mdm): add CLEAR_APP_DATA command for ODK Collect to erase app data between field sessions

## Background
After a field data collection session, ODK Collect retains form submissions and project data on the device. Administrators need a way to reset the app to a clean state for the next deployment without wiping the entire device. The Android Management API [`CLEAR_APP_DATA` command](https://developers.google.com/android/management/reference/rest/v1/enterprises.devices/issueCommand) clears all data for specified package names while leaving the rest of the device intact. This should default to clearing `org.odk.collect.android` (ODK Collect).

## Implementation Steps

1. **Add `clear_app_data(device, package_names=None)` to `AndroidEnterprise`** (`apps/mdm/mdms/android_enterprise.py`):
   ```python
   ODK_COLLECT_PACKAGE = "org.odk.collect.android"

   def clear_app_data(self, device, package_names=None):
       if package_names is None:
           package_names = [self.ODK_COLLECT_PACKAGE]
       return self.client.enterprises().devices().issueCommand(
           name=f"enterprises/{self.enterprise_id}/devices/{device.device_id}",
           body={
               "type": "CLEAR_APP_DATA",
               "clearAppsDataParams": {"packageNames": package_names},
           },
       ).execute()
   ```

2. **Add `clear_app_data` stub to the base `MDM` class**: same pattern as `wipe_device` — raise `NotImplementedError` or `MDMCommandNotSupportedError`.

3. **Add `clear_odk_data(request, organization_slug, device_pk)` view** (`apps/publish_mdm/views.py`):
   - GET: returns an HTMX modal fragment with a confirmation: *"This will clear all ODK Collect data on the device, including saved forms. The device will not be wiped."*
   - POST: calls `get_active_mdm_instance(organization=request.organization).clear_app_data(device)`, returns success/error HTMX responses mirroring the `wipe_device` view.

4. **Add URL** (`apps/publish_mdm/urls.py`):
   ```python
   path("o/<slug:organization_slug>/devices/<int:device_pk>/clear-odk-data/", views.clear_odk_data, name="device-clear-odk-data"),
   ```

5. **Add "Clear ODK Collect data" button** to the device detail template. Distinguish visually from "Wipe device" — use amber/warning styling (less severe), with separate modal copy emphasizing the device stays operational.

## Key Files
- `apps/mdm/mdms/android_enterprise.py` — `clear_app_data`, `ODK_COLLECT_PACKAGE`
- `apps/mdm/mdms/` — base `MDM` class
- `apps/publish_mdm/views.py` — `clear_odk_data`
- `apps/publish_mdm/urls.py`
- `config/templates/publish_mdm/` — device detail and modal templates

## Verification
- On a device running ODK Collect with saved forms, click "Clear ODK Collect data"; confirm the confirmation modal appears with the correct copy (not the wipe warning).
- Confirm; confirm the AMAPI command is sent and ODK Collect data (forms, projects, settings) is erased while other apps are unaffected.
- Confirm the device remains enrolled and fully operational after the command.
- On a TinyMDM device, confirm a "Not supported" message rather than a 500 error.

---

# docs: update documentation for Android Management API features and workflows

## Background
The Android Management API integration introduces a new enterprise setup process, device management capabilities, and operational workflows (enrollment, wipe, app data reset) that must be documented for Publish MDM operators and developers. This issue covers both technical reference docs and field-facing runbooks.

## Implementation Steps

1. **Update `README.md`** — add an "Android Management API" section with:
   - Prerequisites: Google Cloud project, AMAPI enabled, service account created with `androidmanagement.admin` scope, service account key file placed on the server.
   - Environment variables: `ANDROID_ENTERPRISE_PROJECT_ID`, `ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE`, `ANDROID_ENTERPRISE_ID` (legacy fallback, deprecated in favour of the self-service enrollment flow).
   - Step-by-step guide for running the self-service enterprise enrollment flow for a new organization.
   - How to enroll a device (QR code method and email-link method).
   - Quick links to the wipe and ODK data-clear runbooks below.

2. **Add `docs/src/android-enterprise-setup.rst`** (or `.md` if the project already uses MyST): architecture overview of the `AndroidEnterprise` client, the `enterprise_id` per-org field, credential management, and how `Policy.get_policy_data()` merges `json_template` with `policy_config`.

3. **Add `docs/src/runbooks/enrollment-checklist.rst`**: pre-deployment device enrollment steps — create fleet, generate QR code, email link to field coordinator, verify device appears in Publish MDM devices list.

4. **Add `docs/src/runbooks/field-session-reset.rst`**: field session reset procedure using the "Clear ODK Collect data" command, including verification steps to confirm app data is cleared before the device is reused for a new project.

5. **Add `docs/src/runbooks/emergency-wipe.rst`**: emergency wipe procedure, prerequisites, how to confirm wipe completion, and re-enrollment steps for the wiped device.

6. **Update `docs/src/index.rst`** to include the new pages in the `toctree`.

## Key Files
- `README.md`
- `docs/src/android-enterprise-setup.rst` (new)
- `docs/src/runbooks/enrollment-checklist.rst` (new)
- `docs/src/runbooks/field-session-reset.rst` (new)
- `docs/src/runbooks/emergency-wipe.rst` (new)
- `docs/src/index.rst`

## Verification
- A new operator can set up an Android enterprise for a fresh organization by following the README alone.
- A field coordinator unfamiliar with Publish MDM can find and execute the field session reset runbook without developer assistance.
- `make html` in `docs/` builds without warnings.
