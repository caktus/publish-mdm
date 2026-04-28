"""Firebase Cloud Messaging helpers.

Initialises the Firebase Admin SDK from the same service-account file used
for Android Enterprise (ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE) and exposes
a single helper for sending screen-share trigger messages.
"""

import os

import structlog

logger = structlog.get_logger(__name__)

_app = None


def _get_app():
    """Return (or lazily create) the firebase_admin App instance."""
    global _app
    if _app is not None:
        return _app

    import firebase_admin  # noqa: PLC0415
    from firebase_admin import credentials  # noqa: PLC0415

    service_account_file = os.getenv("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE")
    if not service_account_file:
        raise RuntimeError("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not set")

    cred = credentials.Certificate(service_account_file)
    # The service account lives in the Android Enterprise GCP project, but FCM
    # is in a separate Firebase project.  Override the project ID so the Admin
    # SDK sends messages to the correct project.
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID", "983889980424")
    try:
        _app = firebase_admin.get_app("publishmdm")
    except ValueError:
        _app = firebase_admin.initialize_app(
            cred,
            options={"projectId": firebase_project_id},
            name="publishmdm",
        )
    return _app


def send_start_screen_share(
    fcm_token: str, screen_stream_url: str = "", screen_stream_token: str = ""
) -> bool:
    """Send a data-only FCM message that triggers the screen-share consent UI.

    Includes screen_stream_url and screen_stream_token in the payload so the
    device can start the WebSocket immediately without waiting for the AMAPI
    managed-config push to propagate (which can take 20-30 seconds).

    Returns True on success, False (with a logged warning) on failure.
    """
    from firebase_admin import messaging  # noqa: PLC0415

    message = messaging.Message(
        notification=messaging.Notification(
            title="Screen share requested",
            body="An administrator wants to view this device\u2019s screen. Tap to allow.",
        ),
        data={
            "action": "start_screen_share",
            "screen_stream_url": screen_stream_url,
            "screen_stream_token": screen_stream_token,
        },
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="screen_share_request",
                click_action="com.publishmdm.firmwareapp.ACTION_SHOW_SCREEN_CONSENT",
            ),
        ),
        token=fcm_token,
    )
    try:
        msg_id = messaging.send(message, app=_get_app())
        logger.info(
            "FCM screen-share trigger sent: message_id=%s token_prefix=%s", msg_id, fcm_token[:8]
        )
        return True
    except Exception:
        logger.warning("Failed to send FCM screen-share trigger", exc_info=True)
        return False
