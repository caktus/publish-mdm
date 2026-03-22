import json

import structlog
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.publish_mdm.nav import Breadcrumbs

from .forms import (
    DeveloperSettingsForm,
    FirmwareSnapshotForm,
    KioskModeForm,
    OdkCollectPackageForm,
    PasswordPolicyForm,
    PolicyApplicationAddForm,
    PolicyApplicationForm,
    PolicyNameForm,
    PolicyVariableForm,
    VPNForm,
)
from .models import Policy, PolicyApplication, PolicyVariable

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Firmware snapshot (existing API view)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    api_key = settings.MDM_FIRMWARE_API_KEY
    if not api_key:
        # No API key configured — reject all requests rather than silently
        # accepting unauthenticated writes (VULN-001).
        logger.error(
            "firmware_snapshot_view: MDM_FIRMWARE_API_KEY not configured; rejecting request",
            remote_addr=request.META.get("REMOTE_ADDR"),
        )
        return HttpResponse(status=401)
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header != f"Bearer {api_key}":
        return HttpResponse(status=401)
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


def _build_app_forms(policy):
    """Build a list of (app, form) tuples for all applications on a policy."""
    return [
        (app, PolicyApplicationForm(instance=app, prefix=f"app_{app.pk}"))
        for app in policy.applications.order_by("order", "pk")
    ]


def _applications_context(policy, add_app_form=None):
    """Build the common context for the policy applications section partial."""
    return {
        "policy": policy,
        "app_forms": _build_app_forms(policy),
        "add_app_form": add_app_form if add_app_form is not None else PolicyApplicationAddForm(),
        "odk_package_form": OdkCollectPackageForm(instance=policy),
    }


def _variables_context(policy, organization, variable_form=None):
    """Build the common context for the policy variables section partial."""
    return {
        "policy": policy,
        "variables": _get_org_variables(organization),
        "variable_form": variable_form
        if variable_form is not None
        else PolicyVariableForm(organization=organization),
    }


def _save_policy_section(request, policy, form_class, template, form_key):
    """Handle the common HTMX save-section pattern: validate, save, re-render partial.

    Used by policy_save_password, policy_save_vpn, policy_save_developer, and
    policy_save_kiosk which all follow the same structure.
    """
    form = form_class(request.POST, instance=policy)
    if form.is_valid():
        form.save()
        ctx = {"policy": policy, form_key: form_class(instance=policy), "saved": True}
    else:
        ctx = {"policy": policy, form_key: form}
    return render(request, template, ctx)


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
    """Main policy editor page with all sections."""
    policy = _get_policy_or_404(policy_id, request.organization)
    variables = _get_org_variables(request.organization)
    context = {
        "policy": policy,
        "name_form": PolicyNameForm(instance=policy),
        "odk_package_form": OdkCollectPackageForm(instance=policy),
        "app_forms": _build_app_forms(policy),
        "add_app_form": PolicyApplicationAddForm(),
        "password_form": PasswordPolicyForm(instance=policy),
        "vpn_form": VPNForm(instance=policy),
        "kiosk_form": KioskModeForm(instance=policy),
        "developer_form": DeveloperSettingsForm(instance=policy),
        "variables": variables,
        "variable_form": PolicyVariableForm(organization=request.organization),
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
def policy_save_name(request, organization_slug, policy_id):
    """HTMX: save policy name."""
    policy = _get_policy_or_404(policy_id, request.organization)
    form = PolicyNameForm(request.POST, instance=policy)
    if form.is_valid():
        form.save()
        return render(
            request,
            "mdm/partials/policy_name_section.html",
            {"policy": policy, "name_form": PolicyNameForm(instance=policy), "saved": True},
        )
    return render(
        request,
        "mdm/partials/policy_name_section.html",
        {"policy": policy, "name_form": form},
    )


@login_required
def policy_save_odk_package(request, organization_slug, policy_id):
    """HTMX: save ODK Collect package name override."""
    policy = _get_policy_or_404(policy_id, request.organization)
    form = OdkCollectPackageForm(request.POST, instance=policy)
    if form.is_valid():
        form.save()
        odk_app = policy.applications.filter(order=0).first()
        if odk_app:
            odk_app.package_name = policy.odk_collect_package
            odk_app.save()
        return render(
            request,
            "mdm/partials/policy_odk_package.html",
            {
                "policy": policy,
                "odk_package_form": OdkCollectPackageForm(instance=policy),
                "odk_package_saved": True,
            },
        )
    return render(
        request,
        "mdm/partials/policy_odk_package.html",
        {"policy": policy, "odk_package_form": form},
    )


@login_required
def policy_add_application(request, organization_slug, policy_id):
    """HTMX: add a new application to the policy."""
    policy = _get_policy_or_404(policy_id, request.organization)
    form = PolicyApplicationAddForm(request.POST, policy=policy)
    if form.is_valid():
        app = form.save(commit=False)
        app.policy = policy
        app.order = policy.applications.count()
        app.save()
        return render(
            request,
            "mdm/partials/policy_applications_section.html",
            {**_applications_context(policy), "saved": True},
        )
    return render(
        request,
        "mdm/partials/policy_applications_section.html",
        _applications_context(policy, add_app_form=form),
    )


@login_required
def policy_save_application(request, organization_slug, policy_id, app_id):
    """HTMX: save a single application row."""
    policy = _get_policy_or_404(policy_id, request.organization)
    app = get_object_or_404(PolicyApplication, pk=app_id, policy=policy)
    form = PolicyApplicationForm(request.POST, instance=app, prefix=f"app_{app.pk}")
    if form.is_valid():
        form.save()
        return render(
            request,
            "mdm/partials/policy_app_row.html",
            {
                "policy": policy,
                "app": app,
                "app_form": PolicyApplicationForm(instance=app, prefix=f"app_{app.pk}"),
                "saved": True,
            },
        )
    return render(
        request,
        "mdm/partials/policy_app_row.html",
        {"policy": policy, "app": app, "app_form": form},
    )


@login_required
def policy_delete_application(request, organization_slug, policy_id, app_id):
    """HTMX: delete an application row."""
    policy = _get_policy_or_404(policy_id, request.organization)
    app = get_object_or_404(PolicyApplication, pk=app_id, policy=policy)
    if app.package_name == policy.odk_collect_package and app.order == 0:
        return HttpResponse(status=403)
    app.delete()
    return render(
        request,
        "mdm/partials/policy_applications_section.html",
        _applications_context(policy),
    )


@login_required
def policy_save_password(request, organization_slug, policy_id):
    """HTMX: save password policy section."""
    policy = _get_policy_or_404(policy_id, request.organization)
    return _save_policy_section(
        request,
        policy,
        PasswordPolicyForm,
        "mdm/partials/policy_password_section.html",
        "password_form",
    )


@login_required
def policy_save_vpn(request, organization_slug, policy_id):
    """HTMX: save VPN section."""
    policy = _get_policy_or_404(policy_id, request.organization)
    return _save_policy_section(
        request, policy, VPNForm, "mdm/partials/policy_vpn_section.html", "vpn_form"
    )


@login_required
def policy_save_developer(request, organization_slug, policy_id):
    """HTMX: save developer settings section."""
    policy = _get_policy_or_404(policy_id, request.organization)
    return _save_policy_section(
        request,
        policy,
        DeveloperSettingsForm,
        "mdm/partials/policy_developer_section.html",
        "developer_form",
    )


@login_required
def policy_save_kiosk(request, organization_slug, policy_id):
    """HTMX: save kiosk mode settings."""
    policy = _get_policy_or_404(policy_id, request.organization)
    return _save_policy_section(
        request, policy, KioskModeForm, "mdm/partials/policy_kiosk_section.html", "kiosk_form"
    )


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
    return render(
        request,
        "mdm/partials/policy_managed_config_form.html",
        {"policy": policy, "app": app, "saved": saved, "error": error},
    )


@login_required
def policy_add_variable(request, organization_slug, policy_id):
    """HTMX: add a new policy variable."""
    policy = _get_policy_or_404(policy_id, request.organization)
    form = PolicyVariableForm(request.POST, organization=request.organization)
    form.instance.org = request.organization
    if form.is_valid():
        form.save()
        return render(
            request,
            "mdm/partials/policy_variables_section.html",
            {**_variables_context(policy, request.organization), "saved": True},
        )
    return render(
        request,
        "mdm/partials/policy_variables_section.html",
        _variables_context(policy, request.organization, variable_form=form),
    )


@login_required
def policy_delete_variable(request, organization_slug, policy_id, var_id):
    """HTMX: delete a policy variable."""
    policy = _get_policy_or_404(policy_id, request.organization)
    variable = get_object_or_404(
        PolicyVariable,
        Q(org=request.organization) | Q(fleet__organization=request.organization),
        pk=var_id,
    )
    variable.delete()
    return render(
        request,
        "mdm/partials/policy_variables_section.html",
        _variables_context(policy, request.organization),
    )
