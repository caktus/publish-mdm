"""
CollectSettingsSerializer: assembles a valid ODK Collect settings dict
from the normalized per-field values stored on a Project.

No ORM calls — receives a pre-fetched Project instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.publish_mdm.models import Project


@dataclass
class CollectSettingsSerializer:
    """Assembles the nested ODK Collect settings dict from a Project's individual fields.

    The returned dict is suitable for passing to ``build_collect_settings()`` as
    ``project_settings``.  Dynamic fields (server_url, username, app_language,
    project.name, admin_pw) are intentionally absent — they are injected by
    ``build_collect_settings()`` and always take precedence.
    """

    project: Project

    def to_dict(self) -> dict:
        """Return the nested collect-settings dict derived from the project's fields."""
        p = self.project
        return {
            "project": {
                "color": p.collect_project_color,
                "icon": p.collect_project_icon,
            },
            "general": {
                "font_size": p.collect_general_font_size,
                "form_update_mode": p.collect_general_form_update_mode,
                "periodic_form_updates_check": p.collect_general_periodic_form_updates_check,
                "autosend": p.collect_general_autosend,
                "delete_send": p.collect_general_delete_send,
                "default_completed": p.collect_general_default_completed,
                "analytics": p.collect_general_analytics,
            },
            "admin": {
                # Main menu
                "edit_saved": p.collect_admin_edit_saved,
                "send_finalized": p.collect_admin_send_finalized,
                "view_sent": p.collect_admin_view_sent,
                "get_blank": p.collect_admin_get_blank,
                "delete_saved": p.collect_admin_delete_saved,
                "qr_code_scanner": p.collect_admin_qr_code_scanner,
                # Project settings access
                "change_server": p.collect_admin_change_server,
                "change_project_display": p.collect_admin_change_project_display,
                "change_app_theme": p.collect_admin_change_app_theme,
                "change_navigation": p.collect_admin_change_navigation,
                "maps": p.collect_admin_maps,
                # Form management access
                "form_update_mode": p.collect_admin_form_update_mode,
                "periodic_form_updates_check": p.collect_admin_periodic_form_updates_check,
                "automatic_update": p.collect_admin_automatic_update,
                "hide_old_form_versions": p.collect_admin_hide_old_form_versions,
                "change_autosend": p.collect_admin_change_autosend,
                "delete_after_send": p.collect_admin_delete_after_send,
                "default_to_finalized": p.collect_admin_default_to_finalized,
                "change_constraint_behavior": p.collect_admin_change_constraint_behavior,
                "high_resolution": p.collect_admin_high_resolution,
                "image_size": p.collect_admin_image_size,
                "guidance_hint": p.collect_admin_guidance_hint,
                "external_app_recording": p.collect_admin_external_app_recording,
                "instance_form_sync": p.collect_admin_instance_form_sync,
                "change_form_metadata": p.collect_admin_change_form_metadata,
                "analytics": p.collect_admin_analytics,
                # Form entry access
                "moving_backwards": p.collect_admin_moving_backwards,
                "access_settings": p.collect_admin_access_settings,
                "change_language": p.collect_admin_change_language,
                "jump_to": p.collect_admin_jump_to,
                "save_mid": p.collect_admin_save_mid,
                "save_as": p.collect_admin_save_as,
                "mark_as_finalized": p.collect_admin_mark_as_finalized,
            },
        }
