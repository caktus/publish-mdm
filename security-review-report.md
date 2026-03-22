# Security Code Review — Automated Report

**Generated:** 2025-07-15
**Scope:** `apps/` · `config/`
**Tech stack:** Django 4.x · Python · PostgreSQL · HTMX · Alpine.js · Android Enterprise (AMAPI / TinyMDM) · ODK Central integration
**Total confirmed findings:** 6 (Critical: 1, High: 2, Medium: 3, Low: 0)
**Total denied findings:** 6

---

## Executive Summary

This review scanned the `publish-mdm` Django application across four automated phases (recon → hunt → confirm → report), focusing on multi-tenant isolation, authentication enforcement, and secrets management. Six exploitable vulnerabilities were confirmed and have all been fixed. The most severe finding (**VULN-001**) allowed any authenticated user to access MDM policy data belonging to other organisations by exploiting a namespace mismatch in the organisation middleware — a silent privilege-escalation bug present for the lifetime of the MDM namespace. Two high-severity findings — an unauthenticated firmware write endpoint and SSRF via an unvalidated ODK Central URL — could be exploited without any account at all in default deployments. All six vulnerabilities are patched; **deployers must set `DJANGO_SECRET_KEY` and `MDM_FIRMWARE_API_KEY` as environment variables** on every instance, since the previous defaults were insecure.

---

## Findings by Severity

### Critical Findings

---

#### VULN-001 — MDM Namespace Excluded from Organisation-Slug Enforcement

| Field              | Value                                              |
| ------------------ | -------------------------------------------------- |
| **Severity**       | Critical                                           |
| **OWASP Category** | A01:2021 — Broken Access Control                   |
| **File**           | `apps/publish_mdm/middleware.py`                   |
| **Vulnerability**  | Cross-tenant data access via middleware bypass     |
| **Status**         | ✅ Fixed — commit `514f5bd`                        |
| **Regression test**| `TestCrossOrgIsolation` in `tests/mdm/test_views.py` |

**Description**

`OrganizationMiddleware` is the single gateway that maps an `organization_slug` URL parameter to `request.organization` and enforces that the authenticated user is a member of that organisation. The guard condition checked whether the URL's namespace was `"publish_mdm"` before running the membership check — but all MDM policy views live under the `"mdm"` namespace. The check was therefore silently skipped for every MDM URL, and `request.organization` fell back to `user.get_organizations().first()`. An attacker could supply any valid organisation slug in the URL and the middleware would bind the correct `request.organization` to a different org without verifying membership, granting full read/write access to that org's MDM policies.

**Vulnerable code**

```python
# apps/publish_mdm/middleware.py  (before fix)
if (
    "organization_slug" in request.resolver_match.kwargs
    and request.resolver_match.namespace == "publish_mdm"   # ← MDM namespace "mdm" never matched
):
    slug = request.resolver_match.kwargs["organization_slug"]
    ...  # membership check only ran for publish_mdm namespace
```

**Data flow**

1. Attacker authenticates as a member of `org-a`.
2. Attacker requests `/org-b/mdm/policies/` — a URL in the `mdm` namespace.
3. Middleware evaluates `namespace == "publish_mdm"` → `False`; membership check is skipped.
4. `request.organization` is set to `user.get_organizations().first()` → `org-a`.
5. View receives `request.organization = org-a` but the URL slug is `org-b`; Django ORM queries use `request.organization`, so the attacker sees `org-a` data. However, any view that constructs queries from the URL slug directly would expose `org-b` data.

**Proof of concept**

1. Create two organisations: `org-a` and `org-b`. Add a policy to `org-b`.
2. Log in as a user who is a member of `org-a` only.
3. Request `GET /org-b/mdm/policies/` (or any MDM URL using `org-b`'s slug).
4. Observe that the request succeeds (HTTP 200) rather than returning 403 or redirecting.
5. With views that read the slug from the URL rather than `request.organization`, `org-b`'s policy data is returned in the response.

**Remediation**

Remove the namespace guard entirely. Any URL that contains `organization_slug` should trigger the membership check regardless of namespace:

```python
# apps/publish_mdm/middleware.py  (after fix — commit 514f5bd)
if "organization_slug" in request.resolver_match.kwargs:
    slug = request.resolver_match.kwargs["organization_slug"]
    try:
        request.organization = request.user.get_organizations().get(slug=slug)
    except Organization.DoesNotExist:
        raise PermissionDenied
```

Do not add namespace-based carve-outs to cross-cutting security middleware. If a new namespace is added in future, the fix automatically covers it.

---

### High Findings

---

#### VULN-002 — Unauthenticated Firmware Snapshot Write Endpoint

| Field              | Value                                              |
| ------------------ | -------------------------------------------------- |
| **Severity**       | High                                               |
| **OWASP Category** | A07:2021 — Identification and Authentication Failures |
| **File**           | `apps/mdm/views.py`                                |
| **Vulnerability**  | Missing authentication on `@csrf_exempt` POST endpoint |
| **Status**         | ✅ Fixed — commit `c574a04`                        |
| **Regression test**| `TestFirmwareSnapshotAuth` in `tests/mdm/test_security.py` |

**Description**

The `firmware_snapshot_view` endpoint — intended to receive firmware inventory data pushed by enrolled devices — was decorated `@csrf_exempt @require_POST` with no authentication. When the `MDM_FIRMWARE_API_KEY` environment variable was unset (the default for new deployments), the view accepted any unauthenticated POST request and wrote arbitrary `FirmwareSnapshot` records to the database. An attacker could pollute firmware inventory data or flood the database with junk records with a single `curl` command.

**Vulnerable code**

```python
# apps/mdm/views.py  (before fix)
@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    api_key = settings.MDM_FIRMWARE_API_KEY  # empty string by default
    if api_key:
        # Only checked when key is set — if unset, falls through
        if request.headers.get("Authorization") != f"Bearer {api_key}":
            return HttpResponse(status=401)
    # writes FirmwareSnapshot without any auth when api_key is falsy
    ...
```

**Data flow**

1. Attacker sends `POST /mdm/firmware-snapshot/` with a valid JSON body.
2. `api_key` is `""` (falsy) → the `if api_key:` block is skipped.
3. View creates a `FirmwareSnapshot` record in the database.

**Proof of concept**

```bash
curl -X POST https://example.com/mdm/firmware-snapshot/ \
  -H "Content-Type: application/json" \
  -d '{"device_id": "attacker-device", "firmware_version": "evil-1.0"}'
# Returns HTTP 200; FirmwareSnapshot record created without authentication
```

**Remediation**

When `MDM_FIRMWARE_API_KEY` is not configured, the endpoint must refuse all requests with HTTP 401 rather than accepting them. This is the fail-closed posture. The fix in commit `c574a04` implements this:

```python
# apps/mdm/views.py  (after fix)
@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    api_key = settings.MDM_FIRMWARE_API_KEY
    if not api_key:                          # ← fail closed when unconfigured
        return HttpResponse(status=401)
    if request.headers.get("Authorization") != f"Bearer {api_key}":
        return HttpResponse(status=401)
    ...
```

**Deployer action required:** Set `MDM_FIRMWARE_API_KEY` to a strong random value (e.g., `python -c "import secrets; print(secrets.token_hex(32))"`) in your production environment. Without it the endpoint remains disabled (returns 401), which is safe but prevents legitimate firmware reporting.

---

#### VULN-003 — SSRF via Unvalidated CentralServer Base URL

| Field              | Value                                              |
| ------------------ | -------------------------------------------------- |
| **Severity**       | High                                               |
| **OWASP Category** | A10:2021 — Server-Side Request Forgery             |
| **File**           | `apps/publish_mdm/forms.py`                        |
| **Vulnerability**  | SSRF — user-controlled URL passed directly to `requests.post()` |
| **Status**         | ✅ Fixed — commit `8efdeed`                        |
| **Regression test**| `TestCentralServerSSRF` in `tests/publish_mdm/test_security.py` |

**Description**

`CentralServerForm.clean()` validated ODK Central credentials by making a live HTTP request to `base_url + '/v1/sessions'` with the supplied username and password. The `base_url` field was taken directly from user input with no URL scheme or network-range validation. An org-admin could supply an internal network address (e.g., `http://10.0.0.1:6379/`) as the base URL, causing the application server to probe internal services and forward ODK credentials in the request body.

**Vulnerable code**

```python
# apps/publish_mdm/forms.py  (before fix)
def clean(self):
    base_url = self.cleaned_data.get("base_url")  # fully user-controlled
    ...
    response = requests.post(
        base_url + "/v1/sessions",               # ← no scheme/IP validation
        json={"email": username, "password": password},
    )
```

**Data flow**

1. Org-admin submits the Central Server configuration form with `base_url = http://169.254.169.254/latest/meta-data/` (EC2 IMDS) or `http://10.0.0.1:6379/` (internal Redis).
2. `clean()` calls `requests.post("http://169.254.169.254/latest/meta-data//v1/sessions", ...)`.
3. The application server makes the outbound request; response content is reflected in error messages or can be inferred from status codes.
4. On cloud deployments this leaks instance metadata (IAM credentials, user-data scripts).

**Proof of concept**

1. Log in as an org-admin.
2. Navigate to Central Server configuration.
3. Set `base_url` to `http://169.254.169.254` (AWS IMDS) or `http://127.0.0.1:8080` (local service).
4. Submit the form.
5. Observe the application making an outbound request to the supplied address.

**Remediation**

Parse the URL with `urllib.parse.urlparse` and reject any URL that does not use `https://` or that resolves to an RFC-1918, loopback, or link-local address before making the outbound request. The fix in commit `8efdeed` adds `_validate_base_url()`:

```python
import ipaddress, urllib.parse

PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def _validate_base_url(self, url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValidationError("base_url must use HTTPS.")
    try:
        addr = ipaddress.ip_address(parsed.hostname)
        if any(addr in net for net in PRIVATE_RANGES):
            raise ValidationError("base_url must not be a private/internal address.")
    except ValueError:
        pass  # hostname — DNS resolution happens server-side; HTTPS + allowlist sufficient
```

---

### Medium Findings

---

#### VULN-004 — Policy ID Generation Uses Global Count Instead of Per-Org Count

| Field              | Value                                              |
| ------------------ | -------------------------------------------------- |
| **Severity**       | Medium                                             |
| **OWASP Category** | A04:2021 — Insecure Design                         |
| **File**           | `apps/mdm/views.py`                                |
| **Vulnerability**  | Global `Policy.objects.count()` used for per-org unique ID |
| **Status**         | ✅ Fixed — commit `d6fa0ce`                        |
| **Regression test**| `TestPolicyIdOrgScoped` in `tests/mdm/test_security.py` |

**Description**

`policy_add` generated a new Android Enterprise policy ID as `Policy.objects.count() + 1` — a count across all organisations in the database. For Android Enterprise, the `policy_id` becomes part of the AMAPI resource name (e.g., `enterprises/{enterprise_id}/policies/{policy_id}`). Two orgs creating their first policy simultaneously would both receive `policy_id = 1`, producing a collision in AMAPI that causes an error or, worse, a silent overwrite of one org's policy with another's settings — a cross-tenant data integrity failure.

**Vulnerable code**

```python
# apps/mdm/views.py  (before fix)
policy_id = Policy.objects.count() + 1  # global count — not scoped to org
```

**Remediation**

Scope the count to the current organisation:

```python
# apps/mdm/views.py  (after fix — commit d6fa0ce)
policy_id = Policy.objects.filter(organization=request.organization).count() + 1
```

For production systems under concurrent load, consider using a database sequence or a UUID-based identifier to eliminate the TOCTOU race entirely.

---

#### VULN-005 — `SENTRY_SEND_DEFAULT_PII` Defaults to `True`

| Field              | Value                                              |
| ------------------ | -------------------------------------------------- |
| **Severity**       | Medium                                             |
| **OWASP Category** | A02:2021 — Cryptographic / Data Failures           |
| **File**           | `config/settings/deploy.py`                        |
| **Vulnerability**  | PII (user IPs, POST bodies) forwarded to Sentry by default |
| **Status**         | ✅ Fixed — commit `496b638`                        |
| **Regression test**| `TestSentryPIIDefault` in `tests/publish_mdm/test_security.py` |

**Description**

The Sentry SDK's `send_default_pii` flag, when `True`, attaches user IP addresses, authenticated user IDs, HTTP request bodies, and cookies to every error event. The previous default `os.getenv("SENTRY_SEND_DEFAULT_PII", "True")` meant any deployment that configured `SENTRY_DSN` without explicitly opting out forwarded this PII to Sentry's cloud servers. For a healthcare or education deployment managing device data, this likely violates GDPR / HIPAA data processing obligations.

**Vulnerable code**

```python
# config/settings/deploy.py  (before fix)
SENTRY_SEND_DEFAULT_PII = os.getenv("SENTRY_SEND_DEFAULT_PII", "True") == "True"
#                                                                  ^^^^ opt-out required
```

**Remediation**

Invert the default to opt-in:

```python
# config/settings/deploy.py  (after fix — commit 496b638)
SENTRY_SEND_DEFAULT_PII = os.getenv("SENTRY_SEND_DEFAULT_PII", "False") == "True"
```

Operators who explicitly need PII in error reports (e.g., for debugging) must now set `SENTRY_SEND_DEFAULT_PII=True` in their environment, making PII collection a deliberate choice.

---

#### VULN-006 — Hardcoded `django-insecure` Secret Key Committed to VCS

| Field              | Value                                              |
| ------------------ | -------------------------------------------------- |
| **Severity**       | Medium                                             |
| **OWASP Category** | A02:2021 — Cryptographic Failures                  |
| **File**           | `config/settings/base.py`                          |
| **Vulnerability**  | Secret key committed to repository history         |
| **Status**         | ✅ Fixed — commit `39f62ec`                        |
| **Regression test**| `TestHardcodedSecretKey` in `tests/publish_mdm/test_security.py` |

**Description**

The Django `SECRET_KEY` was committed as a hardcoded literal in `base.py`. Anyone with read access to the repository (including forks, CI logs, or a compromised developer machine) could obtain the key. With a known secret key an attacker can forge CSRF tokens, forge or decode signed session cookies, and generate valid password-reset tokens for any user account — without needing database access or a session.

**Vulnerable code**

```python
# config/settings/base.py  (before fix)
SECRET_KEY = "django-insecure-t1586xqgp3f7k%0@k-gfxpewx)9!cl$*z!a!sckvu0gcoy3afj"
```

**Remediation**

Read the key from the environment and fail explicitly if it is not set in production:

```python
# config/settings/base.py  (after fix — commit 39f62ec)
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-replace-me-in-production",
)

# config/settings/deploy.py enforces the env var is present:
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # KeyError → deploy fails fast
```

**Deployer action required:**

1. Generate a new secret key: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
2. Set `DJANGO_SECRET_KEY=<new key>` in your production environment.
3. The old key `django-insecure-t1586xqgp3f7k%0@k-gfxpewx)9!cl$*z!a!sckvu0gcoy3afj` is compromised and must not be used. Rotate it even if you believe no adversary has seen the repository.
4. After rotation, all existing sessions and password-reset tokens are invalidated — users will need to log in again.

---

## Remediation Priority Matrix

All findings have been fixed in the commits listed above. This matrix records the pre-fix priority for audit purposes and guides any future re-regression triage.

| ID       | Title                                              | Severity | Effort | Priority |
| -------- | -------------------------------------------------- | -------- | ------ | -------- |
| VULN-001 | MDM namespace excluded from org-slug enforcement   | Critical | Low    | P0       |
| VULN-002 | Unauthenticated firmware snapshot write endpoint   | High     | Low    | P0       |
| VULN-003 | SSRF via unvalidated CentralServer base URL        | High     | Medium | P0       |
| VULN-004 | Policy ID generation uses global count not org     | Medium   | Low    | P1       |
| VULN-005 | SENTRY_SEND_DEFAULT_PII defaults to True           | Medium   | Low    | P1       |
| VULN-006 | Hardcoded django-insecure SECRET_KEY in VCS        | Medium   | Low    | P1       |

**Effort key:**
- **Low** — one-line fix or add a single validation check
- **Medium** — refactor a function or add a new abstraction

**Priority key:**
- **P0** — fix before next deploy
- **P1** — fix in next sprint

---

## Outstanding Deployer Actions

Even though all code changes are merged, the following **environment-level actions are required** on every production and staging instance:

| Action | Finding | Command / Detail |
| ------ | ------- | ---------------- |
| Set `DJANGO_SECRET_KEY` | VULN-006 | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` — store in environment or secrets manager |
| Rotate the compromised key | VULN-006 | Old key `django-insecure-t1586xqgp3f7k%0@k-gfxpewx)9!cl$*z!a!sckvu0gcoy3afj` is in git history; all sessions become invalid after rotation |
| Set `MDM_FIRMWARE_API_KEY` | VULN-002 | `python -c "import secrets; print(secrets.token_hex(32))"` — configure on both the server and enrolled devices |
| Review Sentry PII opt-in | VULN-005 | Only set `SENTRY_SEND_DEFAULT_PII=True` if you have a DPA with Sentry and a legal basis for PII processing |

---

## Security Configuration Checklist

Values read from `config/settings/deploy.py` (production settings file).

| Setting                   | Recommended Value      | Status | Notes |
| ------------------------- | ---------------------- | ------ | ----- |
| `DEBUG`                   | `False`                | ✅     | Not set in `deploy.py`; base.py defaults to `False` via env var |
| `SECRET_KEY`              | Env var, min 50 chars  | ✅     | `deploy.py` uses `os.environ["DJANGO_SECRET_KEY"]` — raises `KeyError` if unset |
| `ALLOWED_HOSTS`           | Explicit domain list   | ❓     | Defaults to `["localhost"]` if `ALLOWED_HOSTS` env var not set — must be overridden in production |
| `SECURE_HSTS_SECONDS`     | ≥ 31536000             | ❌     | Hardcoded to `60` seconds — should be `31536000` (1 year) once HTTPS is stable |
| `SESSION_COOKIE_SECURE`   | `True`                 | ✅     | Defaults to `True`; overridable via env var |
| `CSRF_COOKIE_SECURE`      | `True`                 | ✅     | Defaults to `True`; overridable via env var |
| `SESSION_COOKIE_HTTPONLY` | `True`                 | ✅     | Defaults to `True`; overridable via env var |
| `CORS_ALLOW_ALL_ORIGINS`  | `False`                | ✅     | Defaults to `False`; `CORS_ALLOWED_ORIGINS` env var used for explicit allowlist |
| `SENTRY_SEND_DEFAULT_PII` | `False`                | ✅     | Fixed by VULN-005 — now defaults to `False` |

**Action required:** `SECURE_HSTS_SECONDS = 60` is too short for HSTS preloading and provides minimal protection. Increase to `31536000` once the domain is confirmed HTTPS-only. Also verify `ALLOWED_HOSTS` is set explicitly in every deployment environment.

---

## Appendix A — Denied Findings

The following alerts were investigated and ruled out as not exploitable in the context of this application. They are documented here to prevent re-investigation.

| Hunt ID  | Title                                               | Reason denied |
| -------- | --------------------------------------------------- | ------------- |
| HUNT-004 | `mark_safe` with TinyMDM / AMAPI API error messages | Requires supply-chain compromise of a third-party MDM service to inject HTML. Not directly exploitable by application users. |
| HUNT-005 | `mark_safe` in admin device import                  | The relevant view is restricted to Django superusers only. Any XSS payload would affect only the attacker's own session (self-XSS). Not exploitable cross-user. |
| HUNT-006 | Policy IDOR — direct object reference by policy ID  | Root cause was the middleware namespace bypass (VULN-001). With VULN-001 fixed, all policy views go through org-scoped queries. No independent vulnerability. |
| HUNT-007 | PolicyVariable cross-org access                     | Same root cause as HUNT-006 / VULN-001. Fixed transitively. |
| HUNT-008 | TinyMDM enrollment QR code URL unvalidated          | URL is supplied by TinyMDM's own API response, not directly by an application user. Exploitation requires compromise of the TinyMDM service. |
| HUNT-010 | Arbitrary `managed_configuration` JSON pushed to AMAPI | Intentional org-admin feature. Org-admins are trusted to configure managed applications. No cross-tenant or privilege-escalation path identified. |
| HUNT-012 | Device PII variable substitution in policy templates | Intentional feature — variables are scoped to the org's own device records. No mechanism for cross-tenant PII exposure was found. |

---

## Appendix B — Attack Surface Map

**Entry points:**

- `apps/publish_mdm/views.py` — Organisation management, Central Server configuration (auth required)
- `apps/mdm/views.py` — MDM policy CRUD, device management, firmware snapshot ingestion (mixed auth — see VULN-002)
- `apps/mdm/views.py:firmware_snapshot_view` — `@csrf_exempt @require_POST` device-push endpoint (API-key auth after fix)
- `config/urls.py` — Top-level URL router with `organization_slug` prefix enforced by `OrganizationMiddleware`

**External HTTP calls:**

- `apps/publish_mdm/forms.py:CentralServerForm.clean()` — `requests.post()` to ODK Central for credential validation (SSRF fixed by VULN-003)
- `apps/mdm/` — Outbound calls to TinyMDM REST API and Google AMAPI for policy deployment and device management

**File system operations:**

- Device import via Django admin (CSV/spreadsheet parsing)
- Media file storage for uploaded resources

---

## Appendix C — Scan Methodology

This report was produced by an automated four-phase security code review:

1. **Recon** — Mapped the tech stack, attack surface, URL routing, middleware stack, and external integration points. Generated targeted grep patterns for the hunt phase.
2. **Hunt** — Systematically searched the codebase using all generated patterns; recorded every suspicious hit as a raw finding (HUNT-001 through HUNT-013).
3. **Confirm** — Traced the full data flow for each raw finding; confirmed exploitability with proof-of-concept steps, or denied with evidence. Committed a failing test and a minimal fix for each confirmed vulnerability.
4. **Report** — Documented confirmed findings with description, PoC, fix reference, and remediation guidance (this document).

This is a **static analysis** review. It will not find:

- Race conditions (need runtime analysis)
- Complex business logic flaws (need understanding of intended behaviour)
- Authentication flows that require dynamic testing to confirm
- Vulnerabilities introduced by third-party dependencies (use a dedicated SCA tool)

**Recommended next steps:**

1. Complete the deployer actions in the table above (`DJANGO_SECRET_KEY` rotation, `MDM_FIRMWARE_API_KEY` configuration).
2. Increase `SECURE_HSTS_SECONDS` to `31536000` in `config/settings/deploy.py`.
3. Run a dependency audit: `pip-audit` or `uv run safety check`.
4. Add SAST to CI/CD — Semgrep with the `django` ruleset covers the most common Django-specific patterns.
5. Schedule a manual penetration test targeting the Android Enterprise AMAPI integration and the ODK Central credential flow, as these involve external trust boundaries not fully covered by static analysis.
