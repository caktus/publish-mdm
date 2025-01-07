APP_USER_ROLE_ID = 2

# Settings configuration for ODK Collect API.
# https://docs.getodk.org/collect-import-export/#list-of-keys-for-all-settings
# https://github.com/getodk/collect/blob/master/settings/src/main/resources/client-settings.schema.json
# Default value:
# {'admin': {},
#  'general': {'autosend': 'wifi_and_cellular',
#              'form_update_mode': 'match_exactly',
#              'server_url': 'https://myserver/v1/key/<snip>/projects/1'},
#  'project': {'color': '#795548', 'icon': 'T', 'name': 'test'}}
DEFAULT_COLLECT_SETTINGS = {
    "project": {
        "color": "#6ec1e4",
        "icon": "🇱🇾",
        # name added dynamically
    },
    "admin": {
        "admin_pw": "",
        # User access control to the main menu. The default value is true.
        "edit_saved": False,
        "send_finalized": False,
        "view_sent": False,
        "get_blank": False,
        "delete_saved": False,
        "qr_code_scanner": False,
        # Project settings > Access control > User Settings
        "change_server": False,
        "change_project_display": False,  # Hide Project settings > Project display
        "change_app_theme": False,
        # "change_app_language": Boolean,
        # "change_font_size": Boolean,
        "change_navigation": False,  # Hide Project settings > User Interface > Navigation
        "maps": False,  # Hide Disable Project settings > Maps
        # Form Management
        "form_update_mode": False,
        "periodic_form_updates_check": False,
        "automatic_update": False,
        "hide_old_form_versions": False,
        "change_autosend": False,
        "delete_after_send": False,
        "default_to_finalized": False,
        # Hide Project settings > Form management > Default to finalized. See default_completed to set.
        "change_constraint_behavior": False,
        "high_resolution": False,
        "image_size": False,
        "guidance_hint": False,
        "external_app_recording": False,
        "instance_form_sync": False,  # "Finalize forms on import"
        "change_form_metadata": False,  # Hide Project settings > User and device identity > Form metadata
        "analytics": False,
        # Project settings > Access control > Form Entry Settings
        "moving_backwards": True,
        "access_settings": False,  # Dropdown to settings while in form
        "change_language": True,
        "jump_to": False,
        "save_mid": False,  # "Save form"
        "save_as": False,  # "Name this form"
        "mark_as_finalized": False,  # "Mark form as finalized" (final screen in form)
    },
    "general": {
        # Server
        # "protocol": {"odk_default", "google_sheets"},
        # "server_url": String, # added dynamically
        # "username": String,
        # "password": String,
        "password": "",
        # "formlist_url": String,
        # "submission_url": String,
        # "selected_google_account": String,
        # "google_sheets_url": String,
        # User interface
        # "appTheme": {"light_theme", "dark_theme"},
        "app_language": "en",
        # BCP 47 language codes. The ones supported by Collect are: {"af", "am",
        # "ar", "bg", "bn", "ca", "cs", "da", "de", "en", "es", "et", "fa",
        # "fi", "fr", "hi", "in", "it", "ja", "ka", "km", "ln", "lo_LA", "lt",
        # "mg", "ml", "mr", "ms", "my", "ne_NP", "nl", "no", "pl", "ps", "pt",
        # "ro", "ru", "rw", "si", "sl", "so", "sq", "sr", "sv_SE", "sw",
        # "sw_KE", "te", "th_TH", "ti", "tl", "tr", "uk", "ur", "ur_PK", "vi",
        # "zh", "zu"},
        "font_size": "25",  # {13, 17, 21, 25, 29},
        # "navigation": {"swipe" ,"buttons" ,"swipe_buttons"},
        # Maps
        # "basemap_source": {"google", "mapbox", "osm", "usgs", "stamen", "carto"},
        # "google_map_style": {1, 2, 3, 4},
        # "mapbox_map_style": {"mapbox://styles/mapbox/light-v10", "mapbox://styles/mapbox/dark-v10", "mapbox://styles/mapbox/satellite-v9", "mapbox://styles/mapbox/satellite-streets-v11", "mapbox://styles/mapbox/outdoors-v11"},
        # "usgs_map_style": {"topographic", "hybrid", "satellite"},
        # "carto_map_style": {"positron", "dark_matter"},
        # "reference_layer": String, # Absolute path to mbtiles file
        # Form management
        "form_update_mode": "match_exactly",  # {"manual", "previously_downloaded", "match_exactly"},
        "periodic_form_updates_check": "every_one_hour",
        # {"every_fifteen_minutes", "every_one_hour", "every_six_hours", "every_24_hours"},
        # "automatic_update": Boolean,
        # "hide_old_form_versions": Boolean,
        "autosend": "wifi_and_cellular",  # {"off", "wifi_only", "cellular_only", "wifi_and_cellular"},
        "delete_send": False,
        "default_completed": True,
        # "constraint_behavior": {"on_swipe", "on_finalize"},
        # "high_resolution": Boolean,
        # "image_size": {"original", "small", "very_small", "medium", "large"},
        # "external_app_recording": Boolean,
        # "guidance_hint": {"no", "yes", "yes_collapsed"},
        # "instance_sync": Boolean,
        # User and device identity
        "analytics": True,
        # "metadata_username": String,
        # "metadata_phonenumber": String,
        # "metadata_email": String,
    },
}
