from django.conf import settings

# Dynamic per-app-user settings that are not stored on CollectSettings.
# Also includes admin_pw which is gotten from template variables.
DYNAMIC_COLLECT_SETTINGS: dict[str, set[str]] = {
    "general": {"server_url", "username"},
    "project": {"name"},
    "admin": {"admin_pw"},
}


def get_default_collect_settings_field_values() -> dict:
    """Return flat ``CollectSettings`` field kwargs from the ``DEFAULT_COLLECT_SETTINGS`` setting.

    Reads the nested ODK Collect settings dict from ``settings.DEFAULT_COLLECT_SETTINGS``
    and flattens it using ``section.key`` → ``{section}_{key}``.  Dynamic per-app-user
    settings (see ``DYNAMIC_COLLECT_SETTINGS``) are excluded.

    Returns an empty dict when ``DEFAULT_COLLECT_SETTINGS`` is not configured or is not a dict.

    Example (given ``DEFAULT_COLLECT_SETTINGS = {"general": {"app_language": "en",
    "font_size": "25"}, "admin": {"admin_pw": "secret", "edit_saved": False}}``):

        get_default_collect_settings_field_values()
        # → {"general_app_language": "en", "general_font_size": "25",
        #    "admin_edit_saved": False}
        # (admin_pw is excluded as a dynamic settings)
    """
    if not isinstance(settings.DEFAULT_COLLECT_SETTINGS, dict):
        return {}
    fields: dict = {}
    for section, keys in settings.DEFAULT_COLLECT_SETTINGS.items():
        if not isinstance(keys, dict):
            continue
        skip = DYNAMIC_COLLECT_SETTINGS.get(section, set())
        for key, value in keys.items():
            if key in skip:
                continue
            fields[f"{section}_{key}"] = value
    return fields
