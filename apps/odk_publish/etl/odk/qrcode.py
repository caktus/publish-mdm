import base64
import io
import json
import zlib
import structlog
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .constants import DEFAULT_COLLECT_SETTINGS
from .publish import ProjectAppUserAssignment


logger = structlog.getLogger(__name__)


def build_collect_settings(
    app_user: ProjectAppUserAssignment,
    base_url: str,
    project_id: int,
    project_name_prefix: str,
    language: str = "en",
    admin_pw: str = "",
):
    """Build Collect settings for the given app user."""
    collect_settings = DEFAULT_COLLECT_SETTINGS.copy()

    if admin_pw:
        collect_settings["admin_pw"] = str(admin_pw) if admin_pw else ""

    # Customize settings
    url = f"{base_url.rstrip("/")}/key/{app_user.token}/projects/{project_id}"
    collect_settings["general"]["server_url"] = url
    collect_settings["general"]["username"] = app_user.displayName
    collect_settings["general"]["app_language"] = language
    project_name = f"{project_name_prefix}: {app_user.displayName} ({language})"
    collect_settings["project"]["name"] = project_name

    return collect_settings


def create_app_user_qrcode(
    app_user: ProjectAppUserAssignment,
    admin_pw: str,
    base_url: str,
    project_id: int,
    project_name_prefix: str,
    language: str = "en",
) -> tuple[io.BytesIO, dict]:
    """Generate a QR code as a PNG for the given app user."""
    
    admin_pw = str(admin_pw) if admin_pw else ""
    
    # Build app user settings
    collect_settings = build_collect_settings(
        app_user=app_user,
        admin_pw=admin_pw,
        base_url=base_url,
        project_id=project_id,
        project_name_prefix=project_name_prefix,
        language=language,
    )

    # Generate QR code with segno
    qr_data = base64.b64encode(zlib.compress(json.dumps(collect_settings).encode("utf-8")))
    code = segno.make(qr_data, micro=False)
    code_buffer = io.BytesIO()
    code.save(code_buffer, scale=4, kind="png")

    # Add text to QR code with PIL
    png = Image.open(code_buffer)
    png = png.convert("RGB")
    text_anchor = png.height
    png = ImageOps.expand(png, border=(0, 0, 0, 30), fill=(255, 255, 255))
    draw = ImageDraw.Draw(png)
    font = ImageFont.truetype(Path(__file__).parent / "Roboto-Regular.ttf", 24)
    label = f"{app_user.displayName}-{language}"
    draw.text((20, text_anchor - 10), label, font=font, fill=(0, 0, 0))
    png_buffer = io.BytesIO()
    png.save(png_buffer, format="PNG")
    logger.info("Generated QR code", app_user=app_user.displayName, qr_code=label)
    return png_buffer, collect_settings
