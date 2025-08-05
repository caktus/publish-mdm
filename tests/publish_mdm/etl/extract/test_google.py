import pytest

from apps.publish_mdm.etl.google import (
    download_user_google_sheet,
    export_sheet_by_url,
    gspread_client,
)
from tests.publish_mdm.factories import FormTemplateFactory
from tests.users.factories import SocialTokenFactory, UserFactory


class TestDownloadUserGoogleSheet:
    """Test the download of user Google Sheets."""

    def test_gspread_client(self):
        """Test the creation of a gspread client."""
        gc = gspread_client(token="token", token_secret="token_secret")
        assert gc.http_client.auth.token == "token"
        assert gc.http_client.auth.refresh_token == "token_secret"

    def test_export_sheet_by_url(self, mocker):
        """Test the export of a Google Sheet by URL."""
        gc = gspread_client(token="token", token_secret="token_secret")
        mock_open_by_url = mocker.patch.object(gc, "open_by_url", return_value=mocker.MagicMock())
        mock_open_by_url.return_value.export.return_value = b"file content"
        content = export_sheet_by_url(
            gc=gc, sheet_url="https://docs.google.com/spreadsheets/d/1/edit"
        )
        assert content == b"file content"

    def test_download_user_google_sheet(self, mocker):
        """Test the download of a user Google Sheet."""
        mock_gspread_client = mocker.patch("apps.publish_mdm.etl.google.gspread_client")
        mock_gspread_client.return_value.open_by_url.return_value.export.return_value = (
            b"file content"
        )
        downloaded_file = download_user_google_sheet(
            token="token",
            token_secret="token_secret",
            sheet_url="https://docs.google.com/spreadsheets/d/1/edit",
            name="mysheet.xlsx",
        )
        assert downloaded_file.name == "mysheet.xlsx"
        assert downloaded_file.read() == b"file content"

    def test_form_template_download_user_google_sheet(self, mocker):
        """Test the download of a user Google Sheet from a FormTemplate."""
        user = UserFactory.build()
        token = SocialTokenFactory.build(token="token", token_secret="token_secret")
        form_template = FormTemplateFactory.build(form_id_base="staff_registration")
        mocker.patch.object(user, "get_google_social_token", return_value=token)
        mock_gspread_client = mocker.patch("apps.publish_mdm.etl.google.gspread_client")
        mock_gspread_client.return_value.open_by_url.return_value.export.return_value = (
            b"file content"
        )
        downloaded_file = form_template.download_user_google_sheet(user=user, name="mysheet.xlsx")
        assert downloaded_file.name == "mysheet.xlsx"
        assert downloaded_file.read() == b"file content"

    def test_form_template_download_user_google_sheet_no_token(self, mocker):
        """Test error raised if user has no Google token."""
        user = UserFactory.build()
        form_template = FormTemplateFactory.build(form_id_base="staff_registration")
        mocker.patch.object(user, "get_google_social_token", return_value=None)
        with pytest.raises(ValueError):
            form_template.download_user_google_sheet(user=user, name="mysheet.xlsx")
