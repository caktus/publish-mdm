import base64
import datetime as dt
import hashlib
import json
import secrets
import time
import uuid

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db.models import Count, Max, Q
from django.http import Http404, HttpResponse, JsonResponse
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
    DeviceAuthChallenge,
    EnrollmentToken,
    Policy,
    PolicyApplication,
    PolicyVariable,
    PolicyVariableScope,
    ScreenShareAuditLog,
    ScreenShareSession,
)
from .serializers import FIRMWARE_APP_PACKAGE
from .tables import EnrollmentTokenTable, PolicyTable
from .utils import get_callback_domain

logger = structlog.get_logger()

CHALLENGE_TTL_SECONDS = 60
SESSION_TTL_SECONDS = 60
TIMESTAMP_SKEW_SECONDS = 30


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_ip(request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _is_rate_limited(scope: str, key: str, limit: int, window_seconds: int) -> bool:
    cache_key = f"mdm-auth-rl:{scope}:{key}"
    if cache.add(cache_key, 1, timeout=window_seconds):
        return False
    try:
        count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window_seconds)
        return False
    return count > limit


def _audit_event(event_type: str, request, device: Device | None = None, **metadata) -> None:
    ScreenShareAuditLog.objects.create(
        event_type=event_type,
        device=device,
        actor=request.user
        if getattr(request, "user", None) and request.user.is_authenticated
        else None,
        ip_address=_client_ip(request) or None,
        metadata_json=metadata or {},
    )


def _load_ec_public_key(public_key_pem: str):
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except ValueError:
        return None
    if not isinstance(key, ec.EllipticCurvePublicKey):
        return None
    return key


def _find_device(identifier: str, **extra_filters):
    """Look up a device by device_id or serial_number.

    The companion app sends its managed-config ``device_identifier`` value
    which may resolve to either ``Device.device_id`` (MDM identifier) or
    ``Device.serial_number`` depending on the policy variable template.
    """
    device = Device.objects.filter(device_id=identifier, **extra_filters).first()
    if device:
        return device
    return Device.objects.filter(serial_number=identifier, **extra_filters).first()


@csrf_exempt
@require_POST
def device_sync_policy_view(request):
    """Trigger a policy re-push for a device.

    Accepts ``device_id`` in the JSON body.  If the device has an active auth
    key the request is currently accepted without signature verification (the
    client *should* send signed requests once full signed-request support is
    added, but for now we accept plain ``device_id`` regardless of key state).
    """
    if _is_rate_limited("sync-policy-ip", _client_ip(request), limit=10, window_seconds=60):
        return HttpResponse(status=429)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    device_id = body.get("device_id", "").strip()
    if not device_id or len(device_id) > 255:
        return HttpResponse(status=400)

    device = _find_device(device_id)
    if not device:
        return HttpResponse(status=404)

    mdm = get_active_mdm_instance(organization=device.fleet.organization)
    if mdm:
        try:
            mdm.push_device_config(device)
        except Exception:
            logger.exception("push_device_config failed", device=device)
            return HttpResponse(status=502)

    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def device_fcm_token_view(request):
    """Register an FCM token for a device.

    Accepts authentication via either:
    - ``device_id`` — identifies the device by its MDM device ID (requires key to be registered)
    - ``screen_stream_token`` — legacy auth (will be removed)
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    fcm_token = body.get("fcm_token", "").strip()
    if not fcm_token or len(fcm_token) > 256:
        return HttpResponse(status=400)

    device_id = body.get("device_id", "").strip()
    screen_stream_token = body.get("screen_stream_token", "").strip()

    if device_id:
        if len(device_id) > 255:
            return HttpResponse(status=400)
        device = _find_device(device_id, auth_key_state="active")
        if not device:
            return HttpResponse(status=404)
        device.fcm_token = fcm_token
        device.save(update_fields=["fcm_token"])
        updated = True
    elif screen_stream_token:
        if len(screen_stream_token) > 64:
            return HttpResponse(status=400)
        updated = Device.objects.filter(screen_stream_token=screen_stream_token).update(
            fcm_token=fcm_token
        )
    else:
        return HttpResponse(status=400)

    if not updated:
        return HttpResponse(status=404)

    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def device_register_key_view(request):
    if _is_rate_limited("register-key-ip", _client_ip(request), limit=20, window_seconds=60):
        return HttpResponse(status=429)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    device_id = body.get("device_id", "").strip()
    bind_code = body.get("bind_code", "").strip()
    public_key_pem = body.get("public_key_pem", "").strip()
    package_name = body.get("package_name", "").strip()
    fcm_token = body.get("fcm_token", "").strip()

    if not device_id or not public_key_pem or not package_name:
        return HttpResponse(status=400)
    if len(device_id) > 255 or len(public_key_pem) > 8192:
        return HttpResponse(status=400)
    if package_name != FIRMWARE_APP_PACKAGE:
        return HttpResponse(status=403)

    device = _find_device(device_id)
    if not device:
        logger.warning("Device not found during key registration", device_id=device_id)
        return HttpResponse(status=404)

    # Validate bind_code if provided; otherwise allow direct registration
    # (suitable for development — production should always require a bind code).
    if bind_code:
        if len(bind_code) > 512:
            return HttpResponse(status=400)
        bind_code_hash = _sha256_hex(bind_code)
        bind_code_record = (
            DeviceBindCode.objects.filter(
                device=device,
                code_hash=bind_code_hash,
                used_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not bind_code_record or bind_code_record.expires_at <= now():
            _audit_event("register_key_invalid_bind_code", request, device=device)
            return HttpResponse(status=401)
    else:
        bind_code_record = None

    key = _load_ec_public_key(public_key_pem)
    if key is None:
        return HttpResponse(status=400)

    public_key_der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = hashlib.sha256(public_key_der).hexdigest()
    bound_at = now()

    update_fields = [
        "auth_public_key_pem",
        "auth_public_key_fingerprint",
        "auth_key_bound_at",
        "auth_key_version",
        "auth_key_state",
    ]

    device.auth_public_key_pem = public_key_pem
    device.auth_public_key_fingerprint = fingerprint
    device.auth_key_bound_at = bound_at
    device.auth_key_version = max(0, device.auth_key_version) + 1
    device.auth_key_state = "active"

    if fcm_token and len(fcm_token) <= 256:
        device.fcm_token = fcm_token
        update_fields.append("fcm_token")

    device.save(update_fields=update_fields)

    if bind_code_record:
        bind_code_record.used_at = bound_at
        bind_code_record.save(update_fields=["used_at"])

    _audit_event(
        "register_key_success",
        request,
        device=device,
        key_fingerprint=fingerprint,
        key_version=device.auth_key_version,
    )
    return JsonResponse(
        {
            "key_fingerprint": fingerprint,
            "key_version": device.auth_key_version,
            "bound_at": bound_at.isoformat(),
        },
        status=201,
    )


@csrf_exempt
@require_POST
def device_auth_challenge_view(request):
    if _is_rate_limited("auth-challenge-ip", _client_ip(request), limit=60, window_seconds=60):
        return HttpResponse(status=429)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    device_id = body.get("device_id", "").strip()
    request_id = body.get("request_id", "").strip()
    if not device_id or not request_id:
        return HttpResponse(status=400)
    if len(device_id) > 255 or len(request_id) > 64:
        return HttpResponse(status=400)

    device = _find_device(device_id, auth_key_state="active")
    if not device or not device.auth_public_key_pem:
        return HttpResponse(status=404)

    challenge_id = uuid.uuid4()
    challenge = DeviceAuthChallenge.objects.create(
        challenge_id=challenge_id,
        device=device,
        request_id=request_id,
        nonce=secrets.token_urlsafe(32),
        expires_at=now() + dt.timedelta(seconds=CHALLENGE_TTL_SECONDS),
    )

    _audit_event(
        "auth_challenge_issued",
        request,
        device=device,
        challenge_id=str(challenge.challenge_id),
        request_id=request_id,
    )

    return JsonResponse(
        {
            "challenge_id": str(challenge.challenge_id),
            "nonce": challenge.nonce,
            "expires_at": challenge.expires_at.isoformat(),
        }
    )


@csrf_exempt
@require_POST
def device_auth_verify_view(request):
    if _is_rate_limited("auth-verify-ip", _client_ip(request), limit=120, window_seconds=60):
        return HttpResponse(status=429)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    challenge_id_raw = str(body.get("challenge_id", "")).strip()
    device_id = body.get("device_id", "").strip()
    request_id = body.get("request_id", "").strip()
    timestamp_raw = str(body.get("timestamp", "")).strip()
    signature_b64 = body.get("signature_b64", "").strip()

    if (
        not challenge_id_raw
        or not device_id
        or not request_id
        or not timestamp_raw
        or not signature_b64
    ):
        return HttpResponse(status=400)

    try:
        challenge_uuid = uuid.UUID(challenge_id_raw)
    except ValueError:
        return HttpResponse(status=400)

    challenge = (
        DeviceAuthChallenge.objects.select_related("device")
        .filter(
            challenge_id=challenge_uuid,
            request_id=request_id,
        )
        .filter(Q(device__device_id=device_id) | Q(device__serial_number=device_id))
        .first()
    )
    if not challenge:
        return HttpResponse(status=404)
    if challenge.used_at is not None:
        return HttpResponse(status=409)
    if challenge.expires_at <= now():
        return HttpResponse(status=410)

    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        return HttpResponse(status=400)

    now_ts = int(time.time())
    if abs(now_ts - timestamp) > TIMESTAMP_SKEW_SECONDS:
        return HttpResponse(status=400)

    public_key = _load_ec_public_key(challenge.device.auth_public_key_pem)
    if public_key is None:
        return HttpResponse(status=401)

    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except ValueError:
        return HttpResponse(status=400)

    payload = f"{challenge_id_raw}.{request_id}.{device_id}.{timestamp_raw}".encode()
    try:
        public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        _audit_event(
            "auth_verify_invalid_signature",
            request,
            device=challenge.device,
            challenge_id=challenge_id_raw,
            request_id=request_id,
        )
        return HttpResponse(status=401)

    used_at = now()
    challenge.used_at = used_at
    challenge.save(update_fields=["used_at"])

    session_token = secrets.token_urlsafe(32)
    expires_at = used_at + dt.timedelta(seconds=SESSION_TTL_SECONDS)
    session = ScreenShareSession.objects.create(
        session_id=uuid.uuid4(),
        token_hash=_sha256_hex(session_token),
        device=challenge.device,
        request_id=request_id,
        expires_at=expires_at,
    )

    _audit_event(
        "auth_verify_success",
        request,
        device=challenge.device,
        challenge_id=challenge_id_raw,
        request_id=request_id,
        session_id=str(session.session_id),
    )

    # Build the WebSocket URL the device should connect to for streaming.
    stream_url = f"wss://{get_callback_domain()}/ws/devices/screen-publish/{session_token}/"

    return JsonResponse(
        {
            "session_token": session_token,
            "session_id": str(session.session_id),
            "expires_at": expires_at.isoformat(),
            "stream_url": stream_url,
        }
    )


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
        raw_mdm_device__isnull=False,
    )
    device_pks = list(child_devices.values_list("pk", flat=True))
    if not device_pks:
        logger.debug(
            "No enrolled devices found for policy; skipping per-device push",
            policy=policy,
        )
        return
    logger.debug(
        "Queuing per-device config push via Dagster",
        policy=policy,
        device_count=len(device_pks),
        device_pks=device_pks,
    )
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

            # Parse expiry timestamp from AMAPI response; fall back to approx local calculation.
            # AMAPI returns ISO 8601 with a trailing "Z" (UTC); normalize to "+00:00" so
            # fromisoformat() parses it correctly on Python < 3.11.
            token.expires_at = expires_at_approx
            if expiry_str := token_data.get("expirationTimestamp"):
                try:
                    token.expires_at = dt.datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(
                        "Failed to parse expiration timestamp from AMAPI response",
                        expiry_str=expiry_str,
                    )
            token.token_value = token_data.get("value", "")
            token.token_resource_name = token_data.get("name", "")
            token.created_by = request.user
            if qr_code_str := token_data.get("qrCode"):
                qr_image = create_qr_code(qr_code_str)
                token.qr_code.save(
                    f"token_{token.fleet.pk}_{get_random_string(12)}.png",
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
