# Intro/original prompt (DOT NOT CREATE ISSUE FOR THIS)

Prompt: Review the code repository and create dev-ready plans to implement the following features, scripts, infrastructure changes, and bug fixes. Use Conventional Commit syntax for the issue titles (https://www.conventionalcommits.org/en/v1.0.0/#summary). Update this file with the plan for each issue, Including a "#" level header (with subheaders under that for issue detail).

- Default Fleet App User: Investigate and implement a feature to assign a default app user to a fleet, enabling immediate pushing of Collect settings upon device enrollment.

- Organization Setup Automation: Develop a script or management command using the Central API to automate the creation of new organizations, projects, and users for long-term testers.

- Allow users to edit the MDM policy JSON (Android Management API)

- Proof of concept Android companion app for geolocation data (Based on the android firmware app?

- Add a foreign key from Policy to Organization
    - Maybe we could also add a ticket to add a foreign key from Policy to Organization , with the default policy JSON for new organizations defined in the code? So each organization would have its own default policy and could choose from different policies on the fleet (instead of having that be admin-only). I forget if there was a reason we left it site-wide (or if that was just a remnant from TinyMDM/HNEC).
    - The data migration could just create a copy of the current default policy for each organization that exists. (edited)

- Add ability to edit attachments on the frontend

- Configuring S3 for ODK Central (Digital Ocean Spaces)

- Display bug: projects dropdown doesn't scroll when list grows long

# Prompt #2

Copied from: https://caktusgroup.slack.com/archives/C082BKPU98D/p1765228363270489

Publish MDM - Android Management API Support

- Initial Android Management API support
- Add self-service flow for enrolling a new enterprise
- Add button to send email with work profile enrollment link
- Add support for wiping devices remotely
- Add support for CLEAR_APP_DATA command for ODK Collect app (to erase voter data after a polling event - a way to start fresh with a new Collect project)
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

---
# feat(mdm): add default app user to Fleet for immediate Collect settings push on enrollment

## Background
When a device enrolls into a fleet, it has no `app_user_name` assigned. The `Device.get_odk_collect_qr_code_string()` method requires `app_user_name` to be set to push ODK Collect settings. A default app user on the fleet would allow settings to be pushed immediately without a human manually assigning one.

## Implementation Steps

1. **Add `default_app_user` FK to `Fleet`** (`apps/mdm/models.py`): nullable, `blank=True`, FK → `AppUser` (`apps/publish_mdm/models.py`), `on_delete=SET_NULL`, `related_name="default_fleet_set"`. Add help text: "If set, newly enrolled devices are automatically assigned this app user."

2. **Create and run migration** (`apps/mdm/migrations/`): standard `makemigrations` nullable FK, no data migration needed.

3. **Auto-assign on enrollment** (`Device.save()`): after `super().save()`, before `push_to_mdm` check, add: if `app_user_name` is empty and `fleet.default_app_user_id` is set, set `self.app_user_name = self.fleet.default_app_user.name` and call `.save(update_fields=["app_user_name"])`. This ensures pull flows from the MDM sync also trigger the assignment.

4. **Update `FleetEditForm`** (`apps/publish_mdm/forms.py`): add `default_app_user` to `fields`. Use a `Select` widget with `attrs={"hx-trigger": "change"}` if dynamic filtering is wanted. Queryset: `AppUser.objects.filter(project=instance.project)`. Guard against `instance.project` being None.

5. **Update `FleetAddForm`**: add `default_app_user` to `fields`.

6. **Update fleet edit/add templates** to show the new field.

## Key Files
- `apps/mdm/models.py` — `Device.save()`, `Fleet`
- `apps/publish_mdm/forms.py` — `FleetEditForm`, `FleetAddForm`
- `apps/publish_mdm/views.py` — `add_fleet`, `edit_fleet`

## Verification
- Enroll a new device into a fleet with `default_app_user` set; confirm `device.app_user_name` is auto-populated.
- Confirm `push_device_config` fires with the correct app user QR code data (the project appears in ODK Collect without further action in the Publish MDM web interface).
- Confirm no regression for fleets with `default_app_user=None`.

---

# feat(publish_mdm): add management command for automated organization setup via Central API

## Background
Onboarding long-term testers requires a repeatable script to create an `Organization`, `CentralServer`, Project (via ODK Central API), and a Central **web user** scoped to that project — all in one step. Currently done manually via admin. App users (ODK Collect mobile users) are created separately by end users through the Publish MDM UI.

## Implementation Steps

1. **Create `apps/publish_mdm/management/commands/setup_organization.py`**: subclass `BaseCommand`. Local DB writes wrapped in `transaction.atomic`; Central API calls happen outside the transaction so partial failures are surfaced clearly.

2. **CLI arguments** (all required unless noted):
   - `--org-name` (str, required) — Organization display name
   - `--org-slug` (str, required) — Organization URL slug
   - `--central-server-pk` (int, required) — PK of an existing `CentralServer` record in the database. The credentials stored on that server (username/password) must belong to an ODK Central **Administrator** account, as the command creates projects and web users on Central's behalf.
   - `--project-name` (str, required) — Name for the new ODK Central project (always created, never reused)
   - `--web-user-email` (str, optional) — Email address for a new Central web user to create and assign to the project (default to `publish-mdm+<org-slug>@caktusgroup.com` if unset)
   - `--invite-email` (str, optional) — Email address to send a Publish MDM organization invitation to (the recipient does not need to have an existing account; `OrganizationInvitation.create()` + `send_invitation()` will be used)

3. **handle() steps**:
   a. Fetch the admin `CentralServer` via `CentralServer.decrypted.get(pk=central_server_pk)` — use the `decrypted` manager so credentials are readable. This server is used **only** for admin-authenticated API calls; its `base_url` is reused for the new organization's server (see step f).
   b. Create `Organization(name=org_name, slug=org_slug)` and save.
   c. Use `PublishMDMClient(central_server=admin_server, project_id=None)` context manager to authenticate as the admin.
   d. **Create the ODK Central project** via `POST /v1/projects`:
      ```
      client.session.post(f"{admin_server.base_url}/v1/projects", json={"name": project_name})
      ```
      Capture the returned `id` as `central_id`.
   e. If `--web-user-email` provided:
      - **Create the Central web user** via `POST /v1/users`. Generate a random 32-character password with `get_random_string(32)`. Request body: `{"email": web_user_email, "password": generated_password}`. Capture the returned `id` as `actor_id`.
        ```
        POST /v1/users
        {"email": "user@example.com", "password": "<generated>"}
        ```
      - **Assign the web user to the project** as a `manager` — the only supported role for web users in this command. Central accepts the role system name in the URL path (per the [Roles API](https://docs.getodk.org/central-api-accounts-and-users/#getting-role-details)):
        ```
        POST /v1/projects/{central_id}/assignments/manager/{actor_id}
        ```
      - **Create a new `CentralServer`** for the new organization, using the newly created user's credentials and the same `base_url` as the admin server: `CentralServer(base_url=admin_server.base_url, organization=organization, username=web_user_email, password=generated_password)`. The new `CentralServer` is what the organization will use to interact with Central going forward.
   f. Create local `Project(name=project_name, central_id=central_id, central_server=new_central_server, organization=organization)` and save. (If `--web-user-email` was not provided, fall back to linking the project to the admin server, with a warning.)
   g. If `--invite-email` provided:
      - Create `OrganizationInvitation.create(email=invite_email, organization=organization)` (no inviter in management command context).
      - Call `invitation.send_invitation(request=None, **ctx_overrides)` — note: `send_invitation` needs a `request` to build the invite URL via `request.build_absolute_uri()`. In the management command, construct the invite URL manually using `django.contrib.sites.models.Site.objects.get_current().domain` and Django's `reverse()`, then call `get_invitations_adapter().send_mail(...)` directly, mirroring `OrganizationInvitation.send_invitation()` without the `request` dependency.
   h. Log each step with `structlog`. Surface all Central API HTTP errors with response body.

   If existing code in the repo provides any of the above functionality, favor using it rather than duplicating the code.

4. **Note on pyODK coverage**: pyODK has no endpoint for Central web users or project creation. Use `client.session` (an authenticated `requests.Session`) directly — the same pattern used in `PublishMDMClient`'s health check at `apps/publish_mdm/etl/odk/client.py` (`client.session.get("users/current")`).

## ODK Central API Endpoints Used
| Step | Method | Endpoint |
|------|--------|----------|
| Create project | `POST` | `/v1/projects` — body: `{"name": "..."}` |
| Create web user | `POST` | `/v1/users` — body: `{"email": "...", "password": "..."}` |
| Assign user to project | `POST` | `/v1/projects/{projectId}/assignments/manager/{actorId}` |

## Key Files
- `apps/publish_mdm/management/commands/setup_organization.py` (new)
- `apps/publish_mdm/etl/odk/client.py` — `PublishMDMClient` (authenticated `client.session`)
- `apps/publish_mdm/models.py` — `Organization`, `CentralServer` (`decrypted` manager), `Project`, `OrganizationInvitation`

## Verification
- Run against a test ODK Central instance; confirm `Organization`, `Project`, and a new `CentralServer` (with the web user's credentials) are all created locally with the correct `central_id` and `base_url`.
- Run with `--web-user-email`; confirm: user exists in Central (`GET /v1/users?q=<email>`), has the correct project role (`GET /v1/projects/{id}/assignments`), and the new `CentralServer.username` matches the web user email.
- Confirm the new `CentralServer` (not the admin server) is linked to the new `Project`.
- Run with `--invite-email`; confirm invitation email is sent and `OrganizationInvitation` record exists.
- Confirm no app users are created by the command — those remain the end user's responsibility via the Publish MDM UI.
- Template for the management command that needs to be run added to the `README` to easily copy/paste

---

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

# feat(mdm): add Organization FK to Policy and per-organization default policies

## Background
`Policy` is currently global/site-wide with a `default_policy` boolean and `unique_default_policy` constraint. The goal is to scope policies per-organization so each org has its own default policy, and fleet admins can choose from their org's policies rather than relying on admin-only setup.

## Implementation Steps

1. **Add `organization` FK to `Policy`** (`apps/mdm/models.py`): nullable initially (`null=True, blank=True`), FK → `Organization`, `on_delete=CASCADE`, `related_name="policies"`.

2. **Update `unique_default_policy` constraint**: replace the site-wide `UniqueConstraint(["default_policy", "mdm"], condition=Q(default_policy=True))` with `UniqueConstraint(["organization", "default_policy", "mdm"], condition=Q(default_policy=True), name="unique_default_policy_per_org")`.

3. **Data migration** (`apps/mdm/migrations/`): for each existing `Organization`, duplicate the current default `Policy` (copying `name`, `policy_id`, `json_template`, `mdm`) and set `organization=org` and `default_policy=True` on the copy. Set `organization` on the original global policy to `None` or delete it after migration completes.

4. **Update `PolicyManager.get_queryset()`**: add `organization` filter. Update `Policy.get_default(cls, organization)` to accept the org and filter by it.

5. **Update `FleetEditForm`** (`apps/publish_mdm/forms.py`): add `policy` field with `queryset=organization.policies.all()`. Update `FleetAddForm` similarly, removing the hardcoded `Policy.get_default()` call in `add_fleet` view.

6. **Update `add_fleet` view** (`apps/publish_mdm/views.py`): pass `organization`-scoped default policy instead of global `Policy.get_default()`.

7. **Update `PolicyManager`**: add `organization` param to filter correctly.

## Key Files
- `apps/mdm/models.py` — `Policy`, `PolicyManager`, `Fleet`
- `apps/mdm/migrations/` — new migration + data migration
- `apps/publish_mdm/forms.py` — `FleetEditForm`, `FleetAddForm`
- `apps/publish_mdm/views.py` — `add_fleet`, `edit_fleet`

## Verification
- Confirm each organization has its own default policy after data migration.
- Confirm Fleet add/edit shows only org-scoped policies.
- Confirm `Policy.get_default(organization=org)` returns the correct per-org policy.
- Run existing tests; confirm no regressions.

---

Prompt: Come up with an initial MVP for a form-based policy editor based on the JSON specification in the Android Management API documentation (https://developers.google.com/android/management/reference/rest/v1/enterprises.policies). The interface should allow the user to edit important parts of the policy that are relevant to Publish MDM, such as applications, managed configurations for those applications via the iframe (see https://developers.google.com/android/management/managed-configurations-iframe, https://developers.google.com/android/management/reference/rest/v1/enterprises.webTokens), password policy, always on VPN, whether or not developer tools are allowed, but should not try to be a generic and fully functional MDM application at this stage. Update the issue highlighted with the specification for the new scope of work.


# feat(mdm): MVP form-based policy editor for Android Management API

## Background
MDM policy JSON templates are currently only editable in the Django admin as raw JSON. Rather than exposing a raw JSON textarea, users should be able to edit the most operationally relevant policy settings through a structured, section-based form. This is an MVP scoped to the subset of the [Android Management API `enterprises.policies` resource](https://developers.google.com/android/management/reference/rest/v1/enterprises.policies) that matters most for Publish MDM deployments.

This depends on Issue #5 (Policy → Organization FK) for per-org scoping; access is restricted to staff/admin users in the interim.

## Policy Sections in Scope (MVP)

| Section | AMAPI Fields |
|---|---|
| **Policy name** | `Policy.name` (model field only) |
| **Applications** | `applications[].packageName`, `applications[].installType`, `applications[].disabled` |
| **Managed configurations** | `applications[].managedConfiguration` — via Play iframe (see §7 below) |
| **Password policy** | `passwordPolicies[].passwordScope`, `passwordPolicies[].passwordQuality`, `passwordPolicies[].passwordMinimumLength`, `passwordPolicies[].requirePasswordUnlock` |
| **Always-on VPN** | `alwaysOnVpnPackage.packageName`, `alwaysOnVpnPackage.lockdownEnabled` |
| **Developer options** | `advancedSecurityOverrides.developerOptions` |

All other keys present in `json_template` are preserved on save (round-trip safe; see §2).

## Implementation Steps

### 1. Add `policy_config` JSONField to `Policy` (`apps/mdm/models.py`)

`json_template` uses Django template syntax (e.g. `{{ tailscale_auth_key }}`), so it cannot be parsed directly as JSON. Add a companion field:

```python
policy_config = models.JSONField(
    default=dict,
    blank=True,
    help_text="Structured policy overrides managed via the form editor. Merged into the rendered json_template on push.",
)
```

Create and run the migration (no data migration needed; `default=dict` covers existing rows).

### 2. Update `Policy.get_policy_data()` to deep-merge `policy_config`

After rendering `json_template` to a dict, merge `policy_config` overtop using the rules below. If `json_template` is empty/invalid, use `policy_config` alone.

**Merge rules:**
- `applications`: merge by `packageName`. For each entry in `policy_config["applications"]`, update the matching entry in the base list (if found) or append it. Entries present only in the base template are kept as-is.
- `passwordPolicies`: merge by `passwordScope`. Same update-or-append logic.
- `alwaysOnVpnPackage`, `advancedSecurityOverrides`: shallow dict merge; `policy_config` wins for any key it supplies.

```python
def get_policy_data(self, **kwargs):
    base = {}
    if self.json_template:
        template = Template(self.json_template)
        rendered = template.render(Context(kwargs))
        try:
            base = json.loads(rendered)
        except json.JSONDecodeError:
            pass
    if self.policy_config:
        base = _deep_merge_policy(base, self.policy_config)
    return base or None
```

Implement `_deep_merge_policy(base, overrides)` as a module-level helper in `apps/mdm/models.py`.

### 3. Create forms (`apps/publish_mdm/forms.py`)

#### `ApplicationPolicyForm`
Plain `forms.Form` for one application entry:
```python
class ApplicationPolicyForm(PlatformFormMixin, forms.Form):
    package_name = forms.CharField(label="Package name", max_length=255)
    install_type = forms.ChoiceField(choices=[
        ("FORCE_INSTALLED", "Force installed"),
        ("PREINSTALLED", "Pre-installed"),
        ("AVAILABLE", "Available"),
        ("KIOSK", "Kiosk"),
        ("BLOCKED", "Blocked"),
    ])
    disabled = forms.BooleanField(required=False, label="Disabled")
```

Wire up as:
```python
ApplicationPolicyFormSet = formset_factory(
    ApplicationPolicyForm, extra=1, can_delete=True
)
```

#### `PasswordPolicyForm`
```python
class PasswordPolicyForm(PlatformFormMixin, forms.Form):
    password_scope = forms.ChoiceField(choices=[
        ("SCOPE_DEVICE", "Device"),
        ("SCOPE_PROFILE", "Work profile"),
    ])
    password_quality = forms.ChoiceField(choices=[
        ("PASSWORD_QUALITY_UNSPECIFIED", "Unspecified"),
        ("SOMETHING", "Something"),
        ("NUMERIC", "Numeric"),
        ("NUMERIC_COMPLEX", "Numeric complex"),
        ("ALPHABETIC", "Alphabetic"),
        ("ALPHANUMERIC", "Alphanumeric"),
        ("COMPLEX", "Complex"),
        ("BIOMETRIC_WEAK", "Biometric (weak)"),
    ])
    password_minimum_length = forms.IntegerField(
        min_value=0, max_value=16, required=False, label="Minimum length"
    )
    require_password_unlock = forms.ChoiceField(required=False, choices=[
        ("USE_DEFAULT_DEVICE_TIMEOUT", "Default device timeout"),
        ("REQUIRE_EVERY_DAY", "Every day"),
    ])
```

One `PasswordPolicyForm` per scope. Use `formset_factory` (no `can_delete` needed for MVP — device/profile scopes are fixed).

#### `VpnAlwaysOnForm`
```python
class VpnAlwaysOnForm(PlatformFormMixin, forms.Form):
    vpn_package_name = forms.CharField(
        required=False, label="VPN package name",
        help_text="e.g. net.openvpn.openvpn. Leave blank to disable always-on VPN."
    )
    vpn_lockdown_enabled = forms.BooleanField(
        required=False, label="Lockdown (block traffic if VPN disconnects)"
    )
```

#### `GeneralPolicySettingsForm`
```python
class GeneralPolicySettingsForm(PlatformFormMixin, forms.Form):
    developer_options = forms.ChoiceField(
        label="Developer options",
        choices=[
            ("DEVELOPER_OPTIONS_DISALLOWED", "Disallowed"),
            ("DEVELOPER_OPTIONS_ALLOWED", "Allowed"),
        ],
    )
```

#### `PolicyNameForm`
```python
class PolicyNameForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Policy
        fields = ["name"]
```

All forms follow the existing `PlatformFormMixin` pattern for consistent widget styling.

### 4. Add views (`apps/publish_mdm/views.py`)

#### `policy_list(request, organization_slug)`
- Require `@login_required` + `@staff_member_required`.
- Until Issue #5 lands: `policies = Policy.objects.all()`.
- Renders `publish_mdm/policy_list.html` with `{"policies": policies}`.

#### `edit_policy(request, organization_slug, policy_id=None)`
- Require `@login_required` + `@staff_member_required`.
- Fetch `policy = get_object_or_404(Policy, pk=policy_id)` when editing; create a blank `Policy(mdm=settings.ACTIVE_MDM["name"])` when adding.
- On GET: populate all forms from `policy.policy_config` (and `policy.name`).
- On POST: validate all forms; on success call `_save_policy_config(policy, forms)` which serializes validated form data back into `policy.policy_config` and calls `policy.save(update_fields=["name", "policy_config"])`. Redirect to `policy_list` on success.
- Pass all form instances plus `policy` to template context.
- Pattern: mirror `change_form_template` view.

#### `get_managed_config_token(request, organization_slug, policy_id, package_name)`
- Require `@login_required` + `@staff_member_required`.
- HTMX endpoint (returns an HTML fragment).
- Calls `AndroidManagementClient.enterprises().webTokens().create(parent=enterprise_name, body={"permissions": ["MANAGED_CONFIGURATIONS"]})` using the credentials from `settings.ANDROID_MANAGEMENT_API` (or however the AMAPI client is initialized in the project).
- Returns a small HTML snippet containing an `<iframe>` pointed at `https://play.google.com/managed/mcm?token={token}&packageName={package_name}` sized to roughly 600×500 px.
- The iframe, when saved by the user, writes managed configuration directly to the Android Management API (no further backend action needed). After closing the iframe, the frontend should trigger a reload of the managed config display area for that app row.

If `AndroidManagementClient` is not yet available in the codebase, stub out this view behind a `MANAGED_CONFIGS_IFRAME_ENABLED` feature flag in settings (default `False`) and display a "Not configured" message in its place.

### 5. Add URL patterns (`apps/publish_mdm/urls.py`)

```python
path("o/<slug:organization_slug>/policies/", views.policy_list, name="policy-list"),
path("o/<slug:organization_slug>/policies/add/", views.edit_policy, name="add-policy"),
path("o/<slug:organization_slug>/policies/<int:policy_id>/edit/", views.edit_policy, name="edit-policy"),
path(
    "o/<slug:organization_slug>/policies/<int:policy_id>/apps/<str:package_name>/mcm-token/",
    views.get_managed_config_token,
    name="policy-mcm-token",
),
```

### 6. Create templates (`config/templates/publish_mdm/`)

#### `policy_list.html`
- Extends `base.html` (follow existing list page patterns, e.g. `app_user_list.html`).
- Table with columns: **Name**, **Default**, **MDM**, **Actions** (Edit link).
- "Add Policy" button linking to `add-policy`.

#### `policy_form.html`
- Extends `base.html`.
- Tabbed or card-based layout with one card per section:
  1. **Policy Name** — `PolicyNameForm`
  2. **Applications** — `ApplicationPolicyFormSet` rendered as a table with one row per app; "Add app" button clones the last empty row via the existing `TOTAL_FORMS` JS pattern. Each app row has a "Configure" button that fires an HTMX GET to `policy-mcm-token` and renders the returned iframe snippet in a modal.
  3. **Password Policy** — `PasswordPolicyFormSet` with one row per scope (Device / Work Profile).
  4. **Always-On VPN** — `VpnAlwaysOnForm`.
  5. **Developer Options** — `GeneralPolicySettingsForm`.
- Single `<form>` wrapping all sections; one **Save** button at the bottom.
- Display non-field form errors at the top of each section card.

### 7. Managed configurations iframe (detail)

Reference: [Managed Configurations iframe](https://developers.google.com/android/management/managed-configurations-iframe) and [`enterprises.webTokens`](https://developers.google.com/android/management/reference/rest/v1/enterprises.webTokens).

The iframe approach:
1. User clicks **Configure** on an application row → HTMX get fires `get_managed_config_token`.
2. Backend creates a short-lived webToken scoped to `MANAGED_CONFIGURATIONS` permission.
3. Backend returns an HTML snippet: `<iframe src="https://play.google.com/managed/mcm?token=TOKEN&packageName=PKG&locale=en_US" width="600" height="500" frameborder="0"></iframe>`.
4. Frontend displays the iframe in a modal (Flowbite modal pattern already used in the project).
5. The iframe's "Save" action writes managed config directly to Android Management API — no second backend call is needed.
6. On modal close, the current `managedConfiguration` value for that app (from `policy_config`) is NOT automatically updated (the iframe writes to AMAPI directly). To keep `policy_config` in sync, the view should optionally accept a `managedConfiguration` JSON POST from a parent-page JS listener on the `message` event emitted by the iframe; see the iframe docs for the `postMessage` API. This sync step can be deferred to a follow-up if complex.

### 8. Add sidebar link (`config/templates/includes/sidebar.html`)

Add a "Policies" link to the org-level `<ul>` immediately after the "Fleets" entry:

```html
<li>
  <a href="{% url 'publish_mdm:policy-list' organization_slug=organization.slug %}"
     class="...">Policies</a>
</li>
```

Apply the active-state class logic consistently with the other sidebar links.

### 9. Access control

- All views: `@login_required` + `@staff_member_required` (from `django.contrib.admin.views.decorators`) until Issue #5 ships.
- The `get_managed_config_token` view additionally validates that `policy_id` belongs to data accessible to the org (even as staff, no cross-org token issuance).

## Key Files
- `apps/mdm/models.py` — `Policy.policy_config`, `Policy.get_policy_data()`, `_deep_merge_policy()`
- `apps/mdm/migrations/` — new migration for `policy_config` field
- `apps/publish_mdm/forms.py` — `PolicyNameForm`, `ApplicationPolicyForm`, `ApplicationPolicyFormSet`, `PasswordPolicyForm`, `VpnAlwaysOnForm`, `GeneralPolicySettingsForm`
- `apps/publish_mdm/views.py` — `policy_list`, `edit_policy`, `get_managed_config_token`
- `apps/publish_mdm/urls.py`
- `config/templates/publish_mdm/policy_list.html` (new)
- `config/templates/publish_mdm/policy_form.html` (new)
- `config/templates/includes/sidebar.html`

## Verification
- Log in as staff; navigate to `/o/<slug>/policies/` — confirm all policies are listed.
- Click **Edit** on a policy; confirm all sections render with current `policy_config` values pre-filled.
- Add an application (`com.example.app`, Force installed), set developer options to Allowed, set a numeric password policy; save. Confirm `policy.policy_config` contains the expected JSON and that `policy.get_policy_data()` returns a merged dict retaining any existing template variables.
- Set `json_template` to a policy JSON with a `{{ tailscale_auth_key }}` interpolation; confirm the merge preserves both the template-rendered keys and the `policy_config` overrides.
- Click **Configure** on an application row (with `MANAGED_CONFIGS_IFRAME_ENABLED = True` and valid AMAPI credentials); confirm the iframe appears in a modal.
- Confirm existing device push flow still works: `push_device_config` calls `policy.get_policy_data(device=device, tailscale_auth_key=...)` and the result is a valid policy dict.

---

# feat(publish_mdm): add frontend views for managing ProjectAttachments

## Background
`ProjectAttachment` records (media/CSV files referenced in XLSForms) are currently managed only via the Django admin `TabularInline`. Users need a self-service frontend to upload, rename, and delete attachments per project.

## Implementation Steps

1. **Create `ProjectAttachmentForm` and `ProjectAttachmentFormSet`** (`apps/publish_mdm/forms.py`): follow the exact pattern used for `ProjectTemplateVariableFormSet`:
   ```python
   class ProjectAttachmentForm(PlatformFormMixin, forms.ModelForm):
       class Meta:
           model = ProjectAttachment
           fields = ["name", "file"]
           widgets = {"name": TextInput, "file": ClearableFileInput}

   ProjectAttachmentFormSet = forms.models.inlineformset_factory(
       Project, ProjectAttachment, form=ProjectAttachmentForm, extra=1
   )
   ProjectAttachmentFormSet.deletion_widget = CheckboxInput
   ```
   In `ProjectAttachmentForm.clean()`, validate that `name` is unique within the project (excluding the current instance).

2. **Extend `change_project` view** (`apps/publish_mdm/views.py`): add the formset alongside the existing `variables_formset`, bound to the project instance. On `POST`, validate both formsets together. On save, delete any files for removed rows (`attachment.file.delete(save=False)`) before calling `attachments_formset.save()`. Pass `attachments_formset` to the template context.

3. **Update `change_project.html`** (`config/templates/publish_mdm/change_project.html`): add a second formset table for attachments following the same `variables_formset` inline table pattern already in that template. Include a file input column and the existing JS `TOTAL_FORMS` clone logic (copy the block already present for `variables_formset`).

4. No new URL patterns or separate pages are required — attachment management lives entirely on the existing **Edit Project** page (`o/<slug>/<int:odk_project_pk>/edit/`).

## Key Files
- `apps/publish_mdm/forms.py` — `ProjectAttachmentForm`, `ProjectAttachmentFormSet`
- `apps/publish_mdm/views.py` — `change_project` (extend, do not add new views)
- `config/templates/publish_mdm/change_project.html` — add attachment formset table

## Verification
A QA tester can reach attachment management by navigating to any project and clicking **Edit Project** in the sidebar (the pencil icon under the project switcher). From that page they should be able to:
- Upload a new attachment (name + file) and save; confirm the file appears in media storage (`project/{id}/attachment/{filename}`) and is listed in the form on reload.
- Change the attachment name without re-uploading the file; confirm the name updates in the DB.
- Check the delete checkbox next to an existing attachment and save; confirm the record is removed from the DB and the file is deleted from storage.
- Confirm existing attachments are still resolved correctly during form publishing (the `attachment_paths_for_upload()` context manager in `apps/publish_mdm/etl/`).

---

# ops(infra): configure ODK Central S3 storage with Digital Ocean Spaces

## Background
ODK Central currently stores form and submission attachments in its database. Configuring S3-compatible storage (DO Spaces) offloads blobs from the database, reducing database size and cost. Reference: [ODK Central docs — Using S3-compatible Storage](https://docs.getodk.org/central-install-digital-ocean/#using-s3-compatible-storage).

## Verification
- Form/submission attachments appear in the DO Spaces bucket.
- Existing blobs are removed from the Postgres database (document if this is not the case).

Note to agent: This issue needs to be created in the `app.publishmdm.com` repo.

---

# fix(ui): make projects dropdown scrollable when list grows long

## Background
The sidebar project switcher dropdown in `config/templates/includes/sidebar.html` renders all available projects without a max height or scroll, so a long project list overflows the viewport.

## Fix

**File**: `config/templates/includes/sidebar.html`, line ~148

Change the `dropdownProjectName` `<div>` class from:

```html
class="hidden z-10 w-60 bg-white rounded divide-y divide-gray-100 shadow dark:bg-gray-700 dark:divide-gray-600"
```

To:

```html
class="hidden z-10 w-60 max-h-64 overflow-y-auto bg-white rounded divide-y divide-gray-100 shadow dark:bg-gray-700 dark:divide-gray-600"
```

The `max-h-64` (16rem) limit and `overflow-y-auto` are standard Tailwind/Flowbite patterns used elsewhere in this codebase.

## Verification
- Add 10+ projects to a test organization; confirm dropdown scrolls instead of overflowing.
- Confirm Flowbite dropdown positioning still works correctly after the change.

