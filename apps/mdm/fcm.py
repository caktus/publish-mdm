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
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not firebase_project_id:
        raise RuntimeError("FIREBASE_PROJECT_ID is not set")
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
    fcm_token: str,
    request_id: str = "",
    screen_stream_url: str = "",
) -> bool:
    """Send an FCM message that triggers the screen-share consent UI.

    The ``request_id`` is a server-generated UUID that the device uses in the
    challenge-response auth flow to obtain a session token for the WebSocket.
    ``screen_stream_url`` is passed to the device so it knows the WebSocket
    endpoint, though it will authenticate via challenge-response.

    Returns True on success, False (with a logged warning) on failure.
    """
    from firebase_admin import messaging  # noqa: PLC0415

    # Pure data message (no `notification` field) so that onMessageReceived is
    # always called on the device regardless of whether the app is in the
    # foreground or background.  If the message had a `notification` field,
    # Android would deliver it silently through the system tray when the app is
    # backgrounded and would NOT call onMessageReceived — meaning the device
    # would never receive the request_id or show the consent dialog.
    message = messaging.Message(
        data={
            "action": "start_screen_share",
            "request_id": request_id,
            "screen_stream_url": screen_stream_url,
        },
        android=messaging.AndroidConfig(
            priority="high",
        ),
        token=fcm_token,
    )
    try:
        msg_id = messaging.send(message, app=_get_app())
        logger.info(
            "FCM screen-share trigger sent",
            message_id=msg_id,
            token_prefix=fcm_token[:8],
        )
        return True
    except Exception:
        logger.warning("Failed to send FCM screen-share trigger", exc_info=True)
        return False
