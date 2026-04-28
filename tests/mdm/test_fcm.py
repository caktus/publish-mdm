from unittest.mock import patch

from firebase_admin import messaging

from apps.mdm.fcm import send_start_screen_share


class TestSendStartScreenShare:
    """Tests for the send_start_screen_share FCM helper."""

    @patch("apps.mdm.fcm._get_app")
    def test_sends_message_with_correct_payload(self, mock_get_app):
        with patch.object(
            messaging, "send", return_value="projects/test/messages/123"
        ) as mock_send:
            result = send_start_screen_share(
                "device-fcm-token",
                screen_stream_url="wss://example.com/ws/screen/tok/",
                screen_stream_token="tok",
            )
        assert result is True
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]  # first positional arg is the Message object
        assert msg.data["action"] == "start_screen_share"
        assert msg.data["screen_stream_url"] == "wss://example.com/ws/screen/tok/"
        assert msg.data["screen_stream_token"] == "tok"
        assert msg.token == "device-fcm-token"

    @patch("apps.mdm.fcm._get_app")
    def test_returns_false_on_failure(self, mock_get_app):
        with patch.object(messaging, "send", side_effect=Exception("FCM unavailable")):
            result = send_start_screen_share("device-fcm-token")
        assert result is False
