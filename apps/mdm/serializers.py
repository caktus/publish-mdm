"""
PolicySerializer: assembles a valid AMAPI enterprises.policies dict
from normalized Policy, PolicyApplication, and PolicyVariable data.

No ORM calls — receives pre-fetched data as arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.mdm.models import Device, Policy, PolicyApplication, PolicyVariable


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

        for app in self.applications:
            if app.package_name == self.policy.odk_collect_package:
                # ODK Collect is handled above; skip duplicate
                continue
            entry = {
                "packageName": app.package_name,
                "installType": app.install_type,
            }
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

    def _merge_variables(self) -> dict[str, str]:
        """Merge variables: fleet-level wins over org-level for the same key."""
        merged: dict[str, str] = {}

        # Org-level first
        for var in self.variables:
            if var.scope == "org":
                merged[var.key] = var.value

        # Fleet-level overrides
        for var in self.variables:
            if var.scope == "fleet":
                merged[var.key] = var.value

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
