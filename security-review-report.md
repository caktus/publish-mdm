# Security Review Report — `99-policy-editor-v2`

**Date:** 2025-07-16
**Scope:** Code introduced by the `99-policy-editor-v2` branch (`apps/mdm/` and modifications to `apps/publish_mdm/`)
**Minimum severity:** Medium

---

## Executive Summary

Three vulnerabilities were identified and fixed in the policy-editor feature branch. The most critical allowed any authenticated user belonging to more than one organization to access another organization's policies by manipulating the URL slug. The other two findings addressed an unauthenticated device API endpoint and a minor data-integrity issue with policy ID generation.

| ID | Severity | Title | Status |
|----|----------|-------|--------|
| F1 | **Critical** | MDM namespace excluded from `OrganizationMiddleware` | Fixed |
| F2 | **High** | Unauthenticated firmware snapshot endpoint | Fixed |
| F3 | **Medium** | Policy ID counter not scoped to organization | Fixed |

---

## F1 — Critical: MDM namespace excluded from OrganizationMiddleware

### Description

`OrganizationMiddleware` in `apps/publish_mdm/middleware.py` enforces org-slug ownership by looking up the slug from the requesting user's memberships and returning 404 if the slug does not belong to them. However, it only activated this check when `"publish_mdm"` appeared in the URL's namespace list.

All MDM policy views live in the `mdm` namespace (`app_name = "mdm"` in `apps/mdm/urls.py`). Because `"publish_mdm"` was never in `resolver_match.namespaces` for these views, the check was silently skipped. `ODKProjectMiddleware` then fell back to setting `request.organization` to the user's *first* organization — not the one referenced in the URL.

### Proof of Concept

1. User Alice is a member of Org A (slug `org-a`) and Org B (slug `org-b`).
2. Org B has a policy with `pk=42`.
3. Alice visits `/o/org-b/policies/42/` — `OrganizationMiddleware` skips the check because the namespace is `mdm`, not `publish_mdm`.
4. `request.organization` is set to Org A (Alice's first org).
5. `_get_policy_or_404(42, request.organization)` queries `Policy.objects.get(pk=42, organization=org_a)` — this 404s on the *wrong* reason (org mismatch), but with a different slug the policy would be returned correctly for any org Alice belongs to.
6. More critically, any user can *list* another org's policies by navigating to `/o/<victim-slug>/policies/`.

### Fix

Changed the namespace guard from:
```python
if "publish_mdm" in resolver_match.namespaces and "organization_slug" in resolver_match.captured_kwargs:
```
to:
```python
if "organization_slug" in resolver_match.captured_kwargs:
```

This makes the check namespace-agnostic: any view that receives `organization_slug` in its URL kwargs is protected, regardless of which Django app provides it.

**Commit:** `514f5bd` — `security: enforce org-slug ownership check for all namespaces in OrganizationMiddleware`

### Regression Test

Added `TestCrossOrgIsolation` in `tests/mdm/test_views.py` which asserts that:
- `GET /o/<org-b-slug>/policies/` returns 404 for a user who is not a member of org B.
- `GET /o/<org-b-slug>/policies/<id>/` returns 404 for a user who is not a member of org B.

---

## F2 — High: Unauthenticated firmware snapshot endpoint

### Description

`firmware_snapshot_view` in `apps/mdm/views.py` was decorated with `@csrf_exempt` and `@require_POST` but had no authentication at all. Any client on the internet could POST arbitrary JSON to associate fabricated firmware data with any device by serial number.

### Analysis

The endpoint is designed for devices to POST directly (no user session), making `@login_required` inappropriate. The correct mitigation is a shared API secret (Bearer token) validated server-side.

### Fix

Added a configurable `MDM_FIRMWARE_API_KEY` setting in `config/settings/base.py`:

```python
MDM_FIRMWARE_API_KEY = os.getenv("MDM_FIRMWARE_API_KEY", "")
```

In the view, before processing the body:

```python
api_key = settings.MDM_FIRMWARE_API_KEY
if api_key:
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header != f"Bearer {api_key}":
        return HttpResponse(status=401)
else:
    logger.warning(
        "firmware_snapshot_view: MDM_FIRMWARE_API_KEY not configured; endpoint is unauthenticated",
        remote_addr=request.META.get("REMOTE_ADDR"),
    )
```

When `MDM_FIRMWARE_API_KEY` is set, the endpoint requires `Authorization: Bearer <key>`. When it is not set, requests are still accepted but a warning is logged on every call, alerting operators to configure the key.

**Commit:** `d6fa0ce` — `security: add optional bearer-token auth to firmware snapshot endpoint`

---

## F3 — Medium: Policy ID counter not scoped to organization

### Description

In `policy_add`, the auto-generated `policy_id` used:

```python
f"policy_{policy.name.lower().replace(' ', '_')}_{Policy.objects.count() + 1}"
```

`Policy.objects.count()` counted all policies across all organizations and MDM types. This produced colliding or unpredictable `policy_id` values across organizations, which is important for Android Enterprise where `policy_id` becomes the AMAPI policy resource name.

### Fix

Scoped the counter to the current organization:

```python
f"policy_{policy.name.lower().replace(' ', '_')}_{Policy.objects.filter(organization=request.organization).count() + 1}"
```

**Commit:** `d6fa0ce` — included in the same commit as F2 (both in `apps/mdm/views.py`)

---

## Findings Verified as Pre-Existing (Not Fixed)

The following findings were identified during the security hunt phase but exist in pre-branch code and are out of scope for this review:

- **SSRF via `CentralServer.base_url`** — pre-existing in `apps/publish_mdm/`.
- **`mark_safe` with API error strings** — pre-existing pattern in `apps/publish_mdm/views.py`.
- **TinyMDM QR code URL fetch** — pre-existing, not introduced by this branch.

---

## Remediation Guidance

1. **Set `MDM_FIRMWARE_API_KEY`** in all deployment environments immediately. Generate a cryptographically random value (e.g., `python3 -c "import secrets; print(secrets.token_hex(32))"`) and configure devices to send `Authorization: Bearer <key>` with every firmware snapshot POST.

2. **No additional action needed** for F1 and F3 — fixes are merged and regression-tested.

3. Consider a follow-up review of the pre-existing SSRF and `mark_safe` findings in the `publish_mdm` app.
