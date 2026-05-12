"""
PolicySerializer: assembles a valid AMAPI enterprises.policies dict
from normalized Policy, PolicyApplication, and PolicyVariable data.

Receives pre-fetched policy data as arguments.  A single incidental ORM call
may occur when ``get_callback_domain()`` falls through to the ``Site`` model,
but this only happens when neither ``ANDROID_ENTERPRISE_CALLBACK_DOMAIN`` nor
``ALLOWED_HOSTS`` is configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from string import Template
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from apps.mdm.models import Device, Policy, PolicyApplication, PolicyVariable

from apps.mdm.utils import get_callback_domain

FIRMWARE_APP_PACKAGE = "com.publishmdm.agent"

# Controls how the firmware companion app is installed on managed devices.
# Valid values (from Android Management API):
#   - FORCE_INSTALLED (default, prod): Always installed; cannot be uninstalled by user
#   - AVAILABLE (local dev): User can install/uninstall via Play Store
#   - OPTIONAL: Device can install if desired
#   - REQUIRED_FOR_SETUP: Required before device setup completes
# For local development, set to AVAILABLE to allow testing without forcing installation.
FIRMWARE_APP_INSTALL_TYPE_VALID = {"FORCE_INSTALLED", "AVAILABLE", "OPTIONAL", "REQUIRED_FOR_SETUP"}
FIRMWARE_APP_INSTALL_TYPE = os.getenv("FIRMWARE_APP_INSTALL_TYPE", "FORCE_INSTALLED")

logger = structlog.get_logger()

if FIRMWARE_APP_INSTALL_TYPE not in FIRMWARE_APP_INSTALL_TYPE_VALID:
    logger.warning(
        "Invalid FIRMWARE_APP_INSTALL_TYPE; using default",
        invalid_value=FIRMWARE_APP_INSTALL_TYPE,
        valid_values=sorted(FIRMWARE_APP_INSTALL_TYPE_VALID),
    )
    FIRMWARE_APP_INSTALL_TYPE = "FORCE_INSTALLED"

# Play Store track IDs that are accessible on devices for this app.
# Add internal/closed testing track IDs here as needed.
PUBLISH_MDM_AGENT_TRACK_IDS: list[str] = [
    # Closed testing track:
    # https://play.google.com/console/u/0/developers/7481408635650691303/app/4972886268045285910/tracks/4699961510397865384?tab=testers
    "4699961510397865384",
]


@dataclass
class PolicySerializer:
    """Assembles clean AMAPI JSON from normalized policy models."""

    policy: Policy
    applications: list[PolicyApplication] = field(default_factory=list)
    variables: list[PolicyVariable] = field(default_factory=list)
    device: Device | None = None

    def to_dict(self) -> dict:
        result = {}

        apps = self._build_applications()
        if apps:
            result["applications"] = apps

        password_policies = self._build_password_policies()
        if password_policies:
            result["passwordPolicies"] = password_policies

        vpn = self._build_vpn()
        if vpn:
            result["alwaysOnVpnPackage"] = vpn

        advanced_security = self._build_advanced_security()
        if advanced_security:
            result["advancedSecurityOverrides"] = advanced_security

        # Kiosk
        if self.policy.kiosk_custom_launcher_enabled:
            result["kioskCustomLauncherEnabled"] = True
        kiosk_customization = {}
        if self.policy.kiosk_power_button_actions != "POWER_BUTTON_ACTIONS_UNSPECIFIED":
            kiosk_customization["powerButtonActions"] = self.policy.kiosk_power_button_actions
        if self.policy.kiosk_system_error_warnings != "SYSTEM_ERROR_WARNINGS_UNSPECIFIED":
            kiosk_customization["systemErrorWarnings"] = self.policy.kiosk_system_error_warnings
        if self.policy.kiosk_system_navigation != "SYSTEM_NAVIGATION_UNSPECIFIED":
            kiosk_customization["systemNavigation"] = self.policy.kiosk_system_navigation
        if self.policy.kiosk_status_bar != "STATUS_BAR_UNSPECIFIED":
            kiosk_customization["statusBar"] = self.policy.kiosk_status_bar
        if self.policy.kiosk_device_settings != "DEVICE_SETTINGS_UNSPECIFIED":
            kiosk_customization["deviceSettings"] = self.policy.kiosk_device_settings
        if kiosk_customization:
            result["kioskCustomization"] = kiosk_customization

        if self.policy.location_mode not in ("", "LOCATION_MODE_UNSPECIFIED"):
            result["locationMode"] = self.policy.location_mode

        connectivity = self._build_device_connectivity_management()
        if connectivity:
            result["deviceConnectivityManagement"] = connectivity

        result["statusReportingSettings"] = self._build_status_reporting_settings()

        # Resolve variable placeholders in all string values
        merged_vars = self._merge_variables()
        self._resolve_variables(result, merged_vars)

        return result

    def _build_applications(self) -> list[dict]:
        apps = []

        # ODK Collect is always first — use install_type from the pinned PolicyApplication row
        pinned_app = next(
            (a for a in self.applications if a.package_name == self.policy.odk_collect_package),
            None,
        )
        raw_install_type = pinned_app.install_type if pinned_app else "FORCE_INSTALLED"
        odk_app = {
            "packageName": self.policy.odk_collect_package,
            "installType": raw_install_type,
        }
        if pinned_app and pinned_app.default_permission_policy not in (
            "",
            "PERMISSION_POLICY_UNSPECIFIED",
        ):
            odk_app["defaultPermissionPolicy"] = pinned_app.default_permission_policy
        # Inject managed configuration from device's app user QR code at push time
        if self.device:
            qr_code_string = self.device.get_odk_collect_qr_code_string()
            if qr_code_string:
                device_id_template = self.policy.odk_collect_device_id_template
                managed_config = {"settings_json": qr_code_string}
                if device_id_template:
                    managed_config["device_id"] = device_id_template
                odk_app["managedConfiguration"] = managed_config
        apps.append(odk_app)

        # Firmware agent app is always pinned — force-installed, permissions always
        # granted, high-priority auto-update.  Not user-configurable.
        # Note: COMPANION_APP role prevents user uninstall and data clearing regardless
        # of installType, so it is omitted when installType is AVAILABLE (local dev).
        firmware_entry: dict = {
            "packageName": FIRMWARE_APP_PACKAGE,
            "installType": FIRMWARE_APP_INSTALL_TYPE,
            "defaultPermissionPolicy": "GRANT",
            "autoUpdateMode": "AUTO_UPDATE_HIGH_PRIORITY",
        }
        # For production, use COMPANION_APP role to prevent user uninstall and data
        # clearing of the firmware agent. Leaving this set in local development
        # prevents the developer from uninstalling the app for testing local APK builds.
        if FIRMWARE_APP_INSTALL_TYPE == "FORCE_INSTALLED":
            firmware_entry["roles"] = [{"roleType": "COMPANION_APP"}]
        if PUBLISH_MDM_AGENT_TRACK_IDS:
            firmware_entry["accessibleTrackIds"] = PUBLISH_MDM_AGENT_TRACK_IDS
        managed_config: dict = {"base_url": f"https://{get_callback_domain()}/mdm/api/firmware/"}
        if self.device and self.device.device_id:
            managed_config["device_identifier"] = self.device.device_id
        firmware_entry["managedConfiguration"] = managed_config
        logger.debug("Adding firmware agent app to policy", managed_config=managed_config)
        apps.append(firmware_entry)

        for app in self.applications:
            if app.package_name in (self.policy.odk_collect_package, FIRMWARE_APP_PACKAGE):
                # Both ODK Collect and the firmware app are handled above; skip duplicates
                continue
            entry = {
                "packageName": app.package_name,
                "installType": app.install_type,
            }
            if app.default_permission_policy not in ("", "PERMISSION_POLICY_UNSPECIFIED"):
                entry["defaultPermissionPolicy"] = app.default_permission_policy
            if app.disabled:
                entry["disabled"] = True
            if app.managed_configuration is not None:
                entry["managedConfiguration"] = app.managed_configuration
            apps.append(entry)

        return apps

    def _build_password_policies(self) -> list[dict]:
        policies = []

        device_policy = self._build_scope_password(
            "SCOPE_DEVICE",
            {
                "quality": self.policy.device_password_quality,
                "min_length": self.policy.device_password_min_length,
                "require_unlock": self.policy.device_password_require_unlock,
            },
        )
        if device_policy:
            policies.append(device_policy)

        work_policy = self._build_scope_password(
            "SCOPE_PROFILE",
            {
                "quality": self.policy.work_password_quality,
                "min_length": self.policy.work_password_min_length,
                "require_unlock": self.policy.work_password_require_unlock,
            },
        )
        if work_policy:
            policies.append(work_policy)

        return policies

    def _build_scope_password(self, scope: str, fields: dict) -> dict | None:
        quality = fields["quality"]
        if not quality or quality == "PASSWORD_QUALITY_UNSPECIFIED":
            return None
        entry = {
            "passwordScope": scope,
            "passwordQuality": quality,
        }
        if fields["min_length"]:
            entry["passwordMinimumLength"] = fields["min_length"]
        require_unlock = fields["require_unlock"]
        if require_unlock and require_unlock != "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED":
            entry["requirePasswordUnlock"] = require_unlock
        return entry

    def _build_vpn(self) -> dict | None:
        if not self.policy.vpn_package_name:
            return None
        return {
            "packageName": self.policy.vpn_package_name,
            "lockdownEnabled": self.policy.vpn_lockdown,
        }

    def _build_advanced_security(self) -> dict | None:
        ds = self.policy.developer_settings
        if not ds:
            return None
        return {"developerSettings": ds}

    def _build_status_reporting_settings(self) -> dict:
        p = self.policy
        return {
            "applicationReportsEnabled": p.status_report_application_reports_enabled,
            "deviceSettingsEnabled": p.status_report_device_settings_enabled,
            "softwareInfoEnabled": p.status_report_software_info_enabled,
            "memoryInfoEnabled": p.status_report_memory_info_enabled,
            "networkInfoEnabled": p.status_report_network_info_enabled,
            "displayInfoEnabled": p.status_report_display_info_enabled,
            "powerManagementEventsEnabled": p.status_report_power_management_events_enabled,
            "hardwareStatusEnabled": p.status_report_hardware_status_enabled,
            "systemPropertiesEnabled": p.status_report_system_properties_enabled,
            "commonCriteriaModeEnabled": p.status_report_common_criteria_mode_enabled,
        }

    def _build_device_connectivity_management(self) -> dict | None:
        p = self.policy
        result = {}
        if p.connectivity_usb_data_access not in ("", "USB_DATA_ACCESS_UNSPECIFIED"):
            result["usbDataAccess"] = p.connectivity_usb_data_access
        if p.connectivity_configure_wifi not in ("", "CONFIGURE_WIFI_UNSPECIFIED"):
            result["configureWifi"] = p.connectivity_configure_wifi
        if p.connectivity_tethering_settings not in ("", "TETHERING_SETTINGS_UNSPECIFIED"):
            result["tetheringSettings"] = p.connectivity_tethering_settings
        if p.connectivity_wifi_direct_settings not in ("", "WIFI_DIRECT_SETTINGS_UNSPECIFIED"):
            result["wifiDirectSettings"] = p.connectivity_wifi_direct_settings
        return result or None

    def _merge_variables(self) -> dict[str, str]:
        """Merge variables: fleet-level wins over policy-level for the same key."""
        merged: dict[str, str] = {}

        def _effective_value(var) -> str:
            if var.is_encrypted and var.value_encrypted:
                return var.value_encrypted
            return var.value

        # Policy-level first
        for var in self.variables:
            if var.scope == "policy":
                merged[var.key] = _effective_value(var)

        # Fleet-level overrides
        for var in self.variables:
            if var.scope == "fleet":
                merged[var.key] = _effective_value(var)

        # Built-in system variables from device (accessible as {{ imei }}, {{ serial_number }}, etc.)
        if self.device:
            merged["app_user_name"] = self.device.app_user_name or ""
            merged["device_id"] = self.device.device_id or ""
            try:
                hardware_info = (self.device.raw_mdm_device or {}).get("hardwareInfo", {})
                merged["imei"] = hardware_info.get("imei", "")
            except (AttributeError, TypeError):
                pass
            merged["serial_number"] = self.device.serial_number or ""

        return merged

    def _resolve_variables(self, obj, variables: dict[str, str]):
        """Deep-walk a dict/list and resolve {{ variable_name }} placeholders in strings."""
        if isinstance(obj, dict):
            for key in obj:
                if isinstance(obj[key], str):
                    obj[key] = self._substitute(obj[key], variables)
                elif isinstance(obj[key], dict | list):
                    self._resolve_variables(obj[key], variables)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    obj[i] = self._substitute(item, variables)
                elif isinstance(item, dict | list):
                    self._resolve_variables(item, variables)

    def _substitute(self, value: str, variables: dict[str, str]) -> str:
        return Template(value).safe_substitute(variables)
