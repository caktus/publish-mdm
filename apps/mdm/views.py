import json

import structlog
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.publish_mdm.nav import Breadcrumbs

from .forms import (
    FirmwareSnapshotForm,
    PolicyApplicationFormSet,
    PolicyEditForm,
    PolicyNameForm,
    PolicyVariableFormSet,
)
from .mdms import get_active_mdm_instance
from .models import Device, Policy, PolicyApplication, PolicyVariable

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Firmware snapshot (existing API view)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    api_key = settings.MDM_FIRMWARE_API_KEY
    if api_key:
        auth_header = request.headers.get("authorization", "")
        if auth_header != f"Bearer {api_key}":
            return HttpResponse(status=401)
    else:
        logger.warning(
            "firmware_snapshot_view: MDM_FIRMWARE_API_KEY not configured; endpoint is unauthenticated",
            remote_addr=request.META.get("REMOTE_ADDR"),
        )
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_policy_or_404(policy_id, organization):
    """Fetch a Policy scoped to the current organization, or raise 404."""
    return get_object_or_404(Policy, pk=policy_id, organization=organization)


def _get_org_variables(organization):
    """Return all PolicyVariables for an org — both org-scoped and fleet-scoped."""
    return PolicyVariable.objects.filter(
        Q(org=organization) | Q(fleet__organization=organization)
    ).select_related("fleet")


def _push_policy_to_mdm(policy):
    """Push a policy and any device-specific child policies to the MDM.

    Errors are logged but not raised so they don't interrupt the view response.
    For Android Enterprise, each enrolled device has its own device-specific policy
    (fleet{id}_{device_id}) that must be updated independently of the base policy.
    We always attempt to push device-specific policies even if the base policy
    update fails, because the device may be on the device-specific policy only.
    """
    active_mdm = get_active_mdm_instance()
    if not active_mdm:
        return
    try:
        active_mdm.create_or_update_policy(policy)
    except Exception:
        logger.error("Failed to push base policy to MDM", policy=policy, exc_info=True)
    for device in Device.objects.filter(
        fleet__policy=policy,
        raw_mdm_device__policyName__endswith=F("device_id"),
    ).select_related("fleet__policy"):
        try:
            active_mdm.push_device_config(device)
        except Exception:
            logger.error("Failed to push device config to MDM", device=device, exc_info=True)


# ---------------------------------------------------------------------------
# Policy editor views
# ---------------------------------------------------------------------------


@login_required
def policy_list(request, organization_slug):
    """List all policies for the current organization."""
    policies = Policy.objects.filter(organization=request.organization)
    context = {
        "policies": policies,
        "show_policy_id": settings.ACTIVE_MDM["name"] != "Android Enterprise",
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("Policies", "mdm:policy-list")],
        ),
    }
    return render(request, "mdm/policy_list.html", context)


@login_required
def policy_add(request, organization_slug):
    """Create a new policy."""
    if request.method == "POST":
        form = PolicyNameForm(request.POST)
        if form.is_valid():
            policy = form.save(commit=False)
            policy.mdm = settings.ACTIVE_MDM["name"]
            policy.policy_id = f"policy_{policy.name.lower().replace(' ', '_')}_{Policy.objects.filter(organization=request.organization).count() + 1}"
            policy.organization = request.organization
            policy.save()
            PolicyApplication.objects.create(
                policy=policy,
                package_name=policy.odk_collect_package,
                install_type="FORCE_INSTALLED",
                order=0,
            )
            _push_policy_to_mdm(policy)
            messages.success(request, f"Policy '{policy.name}' created.")
            return redirect("mdm:policy-edit", organization_slug, policy.pk)
    else:
        form = PolicyNameForm()
    context = {
        "form": form,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Policies", "mdm:policy-list"),
                ("Add Policy", "mdm:policy-add"),
            ],
        ),
    }
    return render(request, "mdm/policy_add.html", context)


@login_required
def policy_edit(request, organization_slug, policy_id):
    """Edit a policy: all fields, applications, and variables in a single form."""
    policy = _get_policy_or_404(policy_id, request.organization)
    organization = request.organization

    if request.method == "POST":
        form = PolicyEditForm(request.POST, instance=policy)
        app_formset = PolicyApplicationFormSet(request.POST, instance=policy, prefix="apps")
        var_formset = PolicyVariableFormSet(
            request.POST,
            queryset=_get_org_variables(organization),
            prefix="vars",
            organization=organization,
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
                if not var.pk:
                    var.org = organization
                var.save()
            for var in var_formset.deleted_objects:
                var.delete()
            _push_policy_to_mdm(policy)
            messages.success(request, "Policy saved.")
            return redirect("mdm:policy-edit", organization_slug, policy.pk)
    else:
        form = PolicyEditForm(instance=policy)
        app_formset = PolicyApplicationFormSet(instance=policy, prefix="apps")
        var_formset = PolicyVariableFormSet(
            queryset=_get_org_variables(organization),
            prefix="vars",
            organization=organization,
        )

    context = {
        "policy": policy,
        "form": form,
        "app_formset": app_formset,
        "var_formset": var_formset,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Policies", "mdm:policy-list"),
                (policy.name, "mdm:policy-edit", [policy.pk]),
            ],
        ),
    }
    return render(request, "mdm/policy_form.html", context)


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
        _push_policy_to_mdm(policy)
    return render(
        request,
        "mdm/partials/policy_managed_config_form.html",
        {"policy": policy, "app": app, "saved": saved, "error": error},
    )
