import structlog

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from google.oauth2.credentials import Credentials
from gspread import Client, HTTPClient
from gspread.utils import ExportFormat

logger = structlog.getLogger(__name__)


def gspread_client(token: str, token_secret: str) -> Client:
    """Manually create a Google Sheets client using the provided user's token and
    token_secret from django-allauth.
    """
    credentials = Credentials(
        token=token,
        refresh_token=token_secret,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    return Client(auth=credentials, http_client=HTTPClient)


def export_sheet_by_url(gc: Client, sheet_url: str) -> bytes:
    """Export a Google Sheet by URL to an Excel file byte string."""
    sheet = gc.open_by_url(url=sheet_url)
    return sheet.export(format=ExportFormat.EXCEL)


def download_user_google_sheet(
    token: str, token_secret: str, sheet_url: str, name: str
) -> SimpleUploadedFile:
    """Download a Google Sheet by URL and return a Django SimpleUploadedFile to use in
    a Django model FileField.
    """
    logger.info("Downloading Google Sheet", name=name)
    gc = gspread_client(token=token, token_secret=token_secret)
    content = export_sheet_by_url(gc=gc, sheet_url=sheet_url)
    return SimpleUploadedFile(
        name=name,
        content=content,
        content_type=ExportFormat.EXCEL,
    )
