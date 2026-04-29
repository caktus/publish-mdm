import base64
import contextlib
import datetime as dt
import json

import structlog
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, F, Max, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_tables2.config import RequestConfig

from apps.publish_mdm.models import AndroidEnterpriseAccount
from apps.publish_mdm.nav import Breadcrumbs
from apps.publish_mdm.utils import create_qr_code
from config.dagster import trigger_dagster_job

from .forms import (
    EnrollmentTokenCreateForm,
    FirmwareSnapshotForm,
    PolicyApplicationFormSet,
    PolicyEditForm,
    PolicyNameForm,
    PolicyTinyMDMForm,
    PolicyVariableFormSet,
)
from .mdms import get_active_mdm_instance
from .models import (
    Device,
    EnrollmentToken,
    Policy,
    PolicyApplication,
    PolicyVariable,
    PolicyVariableScope,
)
from .tables import EnrollmentTokenTable, PolicyTable

logger = structlog.get_logger()


@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    if not request.body:
        return HttpResponse(status=400)
    try:
        json_data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    form = FirmwareSnapshotForm(json_data=json_data)

    if form.is_valid():
        form.save()
        return HttpResponse(status=201)
    else:
        logger.error("Firmware snapshot validation failed", errors=form.errors)
        return HttpResponse(status=400)


@csrf_exempt
@require_POST
def amapi_notifications_view(request):
    """Handle push notifications from AMAPI via Google Cloud Pub/Sub.

    Google Cloud Pub/Sub delivers messages as HTTP POST requests to this endpoint.
    Each message contains a base64-encoded Device resource in the ``data`` field
    and a ``notificationType`` attribute.

    Authentication is performed by comparing the ``token`` query parameter
    against the ``ANDROID_ENTERPRISE_PUBSUB_TOKEN`` Django setting.  All
    requests are rejected if the setting is not configured.

    Returns HTTP 204 on success so that Pub/Sub acknowledges the message and
    does not retry.
    """
    secret_token = settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN
    if not secret_token:
        logger.warning("AMAPI notification rejected: ANDROID_ENTERPRISE_PUBSUB_TOKEN is not set")
        return HttpResponse(status=403)

    # The push subscription URL should include ?token=<secret>
    request_token = request.GET.get("token", "")
    if not (request_token and request_token == secret_token):
        logger.warning("AMAPI notification received with invalid or missing token")
        return HttpResponse(status=403)

    if not request.body:
        return HttpResponse(status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("AMAPI notification body is not valid JSON")
        return HttpResponse(status=400)

    message = body.get("message", {})
    notification_type = message.get("attributes", {}).get("notificationType", "")
    data_b64 = message.get("data", "")

    if not data_b64:
        logger.warning(
            "AMAPI notification received without data payload",
            notification_type=notification_type,
        )
        return HttpResponse(status=204)

    try:
        device_data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        logger.error("Failed to decode AMAPI notification data payload")
        return HttpResponse(status=400)

    logger.info(
        "AMAPI notification received",
        notification_type=notification_type,
        device_name=device_data.get("name"),
    )
    device_name = device_data.get("name", "")
    enterprise_name = "/".join(device_name.split("/")[:2])
    account = AndroidEnterpriseAccount.objects.filter(enterprise_name=enterprise_name).first()
    if account:
        mdm = get_active_mdm_instance(organization=account.organization)
    else:
        mdm = None

    if not (mdm and mdm.name == "Android Enterprise"):
        logger.warning(
            "Unknown enterprise or active MDM is not Android Enterprise. Ignoring",
            enterprise_name=enterprise_name,
            enterprise_account=account,
            mdm=mdm,
            notification_type=notification_type,
        )
    elif notification_type in ("ENROLLMENT", "STATUS_REPORT") and device_data.get(
        "name", ""
    ).startswith(mdm.enterprise_name):
        mdm.handle_device_notification(device_data, notification_type)
    else:
        logger.info(
            "Ignoring notification",
            notification_type=notification_type,
            device_name=device_data.get("name"),
        )

    return HttpResponse(status=204)


def _get_policy_or_404(policy_id, organization):
    """Fetch a Policy scoped to the current organization, or raise 404."""
    return get_object_or_404(Policy, pk=policy_id, organization=organization)


def _get_policy_variables(policy):
    """Return all PolicyVariables for a policy — both policy-scoped and fleet-scoped."""
    return PolicyVariable.objects.filter(
        Q(policy=policy) | Q(fleet__policy=policy, fleet__organization=policy.organization)
    ).select_related("fleet")


def _push_policy_to_mdm(policy, request):
    """Push a policy and any device-specific child policies to the MDM.

    Errors are logged but not raised so they don't interrupt the view response.
    For Android Enterprise, each enrolled device has its own device-specific policy
    (fleet{id}_{device_id}) that must be updated independently of the base policy.
    We always attempt to push device-specific policies even if the base policy
    update fails, because the device may be on the device-specific policy only.

    The base policy push (single API call) is always synchronous.  The
    per-device child-policy pushes (one call per enrolled device) are
    offloaded to Dagster so they don't block the view.
    """
    active_mdm = get_active_mdm_instance(organization=policy.organization)
    warning = (
        "Your policy has been saved, but we encountered an issue syncing it to your devices. "
        "Please try saving again, or contact support if the problem continues."
    )
    if not active_mdm:
        logger.warning(
            "Skipping policy push: MDM is not configured. "
            "Check that an MDM is properly configured for the organization.",
            organization=policy.organization,
            active_mdm_name=policy.organization.mdm,
            policy=policy,
        )
        messages.warning(request, warning)
        return
    try:
        active_mdm.create_or_update_policy(policy)
    except Exception:
        logger.error("Failed to push base policy to MDM", policy=policy, exc_info=True)
    child_devices = Device.objects.filter(
        fleet__policy=policy,
        raw_mdm_device__policyName__endswith=F("device_id"),
    )
    device_pks = list(child_devices.values_list("pk", flat=True))
    if not device_pks:
        return
    run_config = {"ops": {"push_mdm_device_config": {"config": {"device_pks": device_pks}}}}
    try:
        trigger_dagster_job(job_name="mdm_job", run_config=run_config)
    except Exception:
        logger.error(
            "Failed to trigger Dagster mdm_job for child policies",
            policy=policy,
            exc_info=True,
        )
        messages.warning(request, warning)


# ---------------------------------------------------------------------------
# Policy editor views
# ---------------------------------------------------------------------------


@login_required
def policy_list(request, organization_slug):
    """List all policies for the current organization."""
    policies = Policy.objects.filter(organization=request.organization).annotate(
        fleet_count=Count("fleets")
    )
    exclude = ("policy_id",) if request.organization.mdm == "Android Enterprise" else ()
    table = PolicyTable(data=policies, exclude=exclude)
    RequestConfig(request, paginate=False).configure(table)
    context = {
        "table": table,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("Policies", "mdm:policy-list")],
        ),
    }
    return render(request, "mdm/policy_list.html", context)


@login_required
def policy_add(request, organization_slug):
    """Create a new policy."""
    active_mdm = get_active_mdm_instance(organization=request.organization)
    if not active_mdm:
        messages.error(
            request, "Sorry, cannot create a policy at this time. Please try again later."
        )
        return redirect("mdm:policy-list", organization_slug)
    is_tinymdm = request.organization.mdm == "TinyMDM"
    FormClass = PolicyTinyMDMForm if is_tinymdm else PolicyNameForm
    if request.method == "POST":
        form = FormClass(request.POST)
        if form.is_valid():
            policy = form.save(commit=False)
            policy.organization = request.organization
            if not is_tinymdm:
                # For AMAPI, auto-generate policy_id; for TinyMDM it is user-provided via the form.
                # Create a random policy ID to avoid collisions.
                policy.policy_id = f"policy_{get_random_string(20)}"
            policy.save()
            if not is_tinymdm:
                PolicyApplication.objects.create(
                    policy=policy,
                    package_name=policy.odk_collect_package,
                    install_type="FORCE_INSTALLED",
                    order=0,
                )
                _push_policy_to_mdm(policy, request)
            messages.success(request, f"Policy '{policy.name}' created.")
            if is_tinymdm:
                return redirect("mdm:policy-list", organization_slug)
            return redirect("mdm:policy-edit", organization_slug, policy.pk)
    else:
        form = FormClass()
    context = {
        "form": form,
        "is_tinymdm": is_tinymdm,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Policies", "mdm:policy-list"),
                ("Add Policy", "mdm:policy-add"),
            ],
        ),
    }
    return render(request, "mdm/policy_add.html", context)


def _handle_tinymdm_policy_edit(request, policy):
    """Handle TinyMDM policy edit (name and policy_id only).

    Returns a redirect on success, or a 2-tuple (context dict and template name) on GET/invalid POST.
    """
    if request.method == "POST":
        form = PolicyTinyMDMForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, "Policy saved.")
            return redirect("mdm:policy-edit", request.organization.slug, policy.pk)
    else:
        form = PolicyTinyMDMForm(instance=policy)
    return {"form": form}, "mdm/policy_tinymdm_form.html"


def _handle_amapi_policy_edit(request, policy):
    """Handle Android Enterprise (AMAPI) policy edit: full form with apps and variables.

    Returns a redirect on success, or a 2-tuple (context dict and template name) on GET/invalid POST.
    """
    if request.method == "POST":
        form = PolicyEditForm(request.POST, instance=policy)
        app_formset = PolicyApplicationFormSet(request.POST, instance=policy, prefix="apps")
        var_formset = PolicyVariableFormSet(
            request.POST,
            queryset=_get_policy_variables(policy),
            prefix="vars",
            organization=request.organization,
            policy=policy,
        )
        if form.is_valid() and app_formset.is_valid() and var_formset.is_valid():
            policy = form.save()
            # save(commit=False) returns unsaved instances and populates deleted_objects
            apps_to_save = app_formset.save(commit=False)
            for app in app_formset.deleted_objects:
                app.delete()
            # Assign sequential order to new apps (order defaults to 0, which would
            # wrongly match the pinned ODK app check on the next save)
            current_max = policy.applications.aggregate(m=Max("order"))["m"] or 0
            new_idx = 0
            for app in apps_to_save:
                if not app.pk:
                    new_idx += 1
                    app.order = current_max + new_idx
                app.save()
            # Keep the pinned ODK app in sync with the policy's odk_collect_package
            odk_app = policy.applications.filter(
                order=0, package_name=policy.odk_collect_package
            ).first()
            if not odk_app:
                odk_app = policy.applications.filter(order=0).first()
            if odk_app and odk_app.package_name != policy.odk_collect_package:
                odk_app.package_name = policy.odk_collect_package
                odk_app.save()
            variables = var_formset.save(commit=False)
            for var in variables:
                if var.scope == PolicyVariableScope.POLICY:
                    var.policy = policy
                    var.fleet = None
                elif var.scope == PolicyVariableScope.FLEET:
                    var.policy = None
                # Move plaintext value to encrypted field if is_encrypted is toggled
                if var.is_encrypted and var.value:
                    var.value_encrypted = var.value
                    var.value = ""
                elif not var.is_encrypted:
                    var.value_encrypted = None
                var.save()
            for var in var_formset.deleted_objects:
                var.delete()
            messages.success(request, "Policy saved.")
            _push_policy_to_mdm(policy, request)
            return redirect("mdm:policy-edit", request.organization.slug, policy.pk)
    else:
        form = PolicyEditForm(instance=policy)
        app_formset = PolicyApplicationFormSet(instance=policy, prefix="apps")
        var_formset = PolicyVariableFormSet(
            queryset=_get_policy_variables(policy),
            prefix="vars",
            organization=request.organization,
            policy=policy,
        )
    return {
        "form": form,
        "app_formset": app_formset,
        "var_formset": var_formset,
    }, "mdm/policy_form.html"


@login_required
def policy_edit(request, organization_slug, policy_id):
    """Edit a policy: dispatches to MDM-specific handlers for TinyMDM and AMAPI."""
    policy = _get_policy_or_404(policy_id, request.organization)

    if request.organization.mdm == "TinyMDM":
        handler = _handle_tinymdm_policy_edit
    else:
        handler = _handle_amapi_policy_edit

    result = handler(request, policy)

    if isinstance(result, HttpResponse):
        return result

    extra_context, template = result
    context = {
        "policy": policy,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Policies", "mdm:policy-list"),
                (policy.name, "mdm:policy-edit", [policy.pk]),
            ],
        ),
        **extra_context,
    }
    return render(request, template, context)


@login_required
def policy_save_managed_config(request, organization_slug, policy_id, app_id):
    """HTMX: save managed configuration JSON for a policy application."""
    policy = _get_policy_or_404(policy_id, request.organization)
    app = get_object_or_404(PolicyApplication, pk=app_id, policy=policy)
    error = None
    saved = False
    config_json = request.POST.get("managed_configuration", "").strip()
    if config_json:
        try:
            app.managed_configuration = json.loads(config_json)
            app.save(update_fields=["managed_configuration"])
            saved = True
        except json.JSONDecodeError as e:
            error = f"Invalid JSON: {e}"
    else:
        app.managed_configuration = None
        app.save(update_fields=["managed_configuration"])
        saved = True
    if saved:
        _push_policy_to_mdm(policy, request)
    return render(
        request,
        "mdm/partials/policy_managed_config_form.html",
        {"policy": policy, "app": app, "saved": saved, "error": error},
    )


@login_required
def enrollment_token_list(request, organization_slug):
    """List all enrollment tokens for the current organization."""
    if request.organization.mdm != "Android Enterprise":
        raise Http404
    tokens = EnrollmentToken.objects.filter(organization=request.organization).select_related(
        "fleet", "created_by", "organization"
    )
    table = EnrollmentTokenTable(data=tokens)
    RequestConfig(request, paginate=False).configure(table)
    context = {
        "table": table,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Devices", "publish_mdm:devices-list"),
                ("Enrollment Tokens", "mdm:enrollment-token-list"),
            ],
        ),
    }
    return render(request, "mdm/enrollment_token_list.html", context)


@login_required
def enrollment_token_create(request, organization_slug):
    """Create a new long-lived enrollment token via the MDM API."""
    if request.organization.mdm != "Android Enterprise":
        raise Http404
    if request.method == "POST":
        form = EnrollmentTokenCreateForm(request.POST, organization=request.organization)
        if form.is_valid():
            active_mdm = get_active_mdm_instance(organization=request.organization)
            if not active_mdm:
                messages.error(request, "MDM is not configured for this organization.")
                return redirect("mdm:enrollment-token-list", organization_slug)
            token = form.save(commit=False)
            token.organization = request.organization
            expiration_delta = form.cleaned_data["expiration"]
            # Compute the duration seconds based on the expiration relativedelta object
            base_time = now()
            expires_at_approx = base_time + expiration_delta
            duration_seconds = int((expires_at_approx - base_time).total_seconds())
            try:
                token_data = active_mdm.create_enrollment_token(
                    fleet=token.fleet,
                    duration_seconds=duration_seconds,
                    allow_personal_usage=token.allow_personal_usage,
                )
            except Exception:
                logger.exception("Failed to create enrollment token via MDM API")
                messages.error(
                    request,
                    "Failed to create enrollment token. Please try again or contact support.",
                )
                context = {
                    "form": form,
                    "breadcrumbs": Breadcrumbs.from_items(
                        request=request,
                        items=[
                            ("Devices", "publish_mdm:devices-list"),
                            ("Enrollment Tokens", "mdm:enrollment-token-list"),
                            ("Create Token", "mdm:enrollment-token-create"),
                        ],
                    ),
                }
                return render(request, "mdm/enrollment_token_create.html", context)

            # Parse expiry timestamp from AMAPI response; fall back to approx local calculation
            token.expires_at = expires_at_approx
            if expiry_str := token_data.get("expirationTimestamp"):
                with contextlib.suppress(ValueError):
                    token.expires_at = dt.datetime.fromisoformat(expiry_str)
            token.token_value = token_data.get("value", "")
            token.token_resource_name = token_data.get("name", "")
            token.created_by = request.user
            if qr_code_str := token_data.get("qrCode"):
                qr_image = create_qr_code(qr_code_str)
                token.qr_code.save(
                    f"token_{token.fleet.pk}_{token.token_value[:10]}.png",
                    ContentFile(qr_image.getvalue()),
                    save=False,
                )
            token.save()
            messages.success(request, f"Enrollment token '{token}' created successfully.")
            return redirect("mdm:enrollment-token-detail", organization_slug, token.pk)
    else:
        form = EnrollmentTokenCreateForm(organization=request.organization)

    context = {
        "form": form,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Devices", "publish_mdm:devices-list"),
                ("Enrollment Tokens", "mdm:enrollment-token-list"),
                ("Create Token", "mdm:enrollment-token-create"),
            ],
        ),
    }
    return render(request, "mdm/enrollment_token_create.html", context)


@login_required
def enrollment_token_detail(request, organization_slug, token_pk):
    """Show the detail page for an enrollment token."""
    if request.organization.mdm != "Android Enterprise":
        raise Http404
    token = get_object_or_404(
        EnrollmentToken.objects.select_related("fleet", "created_by"),
        pk=token_pk,
        organization=request.organization,
    )
    context = {
        "token": token,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Devices", "publish_mdm:devices-list"),
                ("Enrollment Tokens", "mdm:enrollment-token-list"),
                (str(token), "mdm:enrollment-token-detail", [token.pk]),
            ],
        ),
    }
    return render(request, "mdm/enrollment_token_detail.html", context)


@login_required
@require_POST
def enrollment_token_revoke(request, organization_slug, token_pk):
    """Revoke an enrollment token (POST only — confirmation shown via modal)."""
    if request.organization.mdm != "Android Enterprise":
        raise Http404
    token = get_object_or_404(EnrollmentToken, pk=token_pk, organization=request.organization)
    error = None
    active_mdm = get_active_mdm_instance(organization=request.organization)
    if not active_mdm:
        error = "The MDM is not configured, so the token could not be revoked in the MDM."
    elif not token.token_resource_name:
        logger.error(
            "Enrollment token is missing resource name; cannot revoke via MDM API",
            token_pk=token.pk,
        )
        error = "This token cannot be revoked in the MDM because it has no resource name."
    else:
        try:
            active_mdm.revoke_enrollment_token(token.token_resource_name)
        except Exception:
            logger.exception(
                "Failed to revoke enrollment token via MDM API",
                resource_name=token.token_resource_name,
            )
            error = "Failed to revoke the token from the MDM. Please try again."
    if error:
        messages.error(request, error)
        return redirect("mdm:enrollment-token-detail", organization_slug, token.pk)
    token.revoked_at = now()
    token.save(update_fields=["revoked_at"])
    messages.success(request, f"Enrollment token '{token}' has been revoked.")
    return redirect("mdm:enrollment-token-list", organization_slug)
