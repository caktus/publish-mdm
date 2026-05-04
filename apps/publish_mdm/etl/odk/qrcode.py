import base64
import io
import json
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PIL import Image, ImageDraw, ImageFont, ImageOps

from apps.publish_mdm.utils import create_qr_code

from .collect_settings import CollectSettingsSerializer
from .publish import ProjectAppUserAssignment

if TYPE_CHECKING:
    from apps.publish_mdm.models import Project

logger = structlog.getLogger(__name__)


def build_collect_settings(
    project: "Project",
    app_user: ProjectAppUserAssignment,
    base_url: str,
) -> dict:
    """Build Collect settings for the given app user from a Project instance.

    All settings are sourced from the project's ``collect_*`` model fields via
    ``CollectSettingsSerializer``.  The only truly dynamic fields — those that
    depend on the individual app user assignment — are applied on top:

    * ``general.server_url`` — ODK Central URL + app user token
    * ``general.username``   — app user display name
    * ``project.name``       — ``"{project.name}: {displayName} ({language})"``
    """
    collect_settings = CollectSettingsSerializer(project=project).to_dict()

    url = f"{base_url.rstrip('/')}/key/{app_user.token}/projects/{project.central_id}"
    collect_settings["general"]["server_url"] = url
    collect_settings["general"]["username"] = app_user.displayName
    language = project.collect_general_app_language
    collect_settings["project"]["name"] = f"{project.name}: {app_user.displayName} ({language})"

    return collect_settings


def create_app_user_qrcode(
    project: "Project",
    app_user: ProjectAppUserAssignment,
    base_url: str,
) -> tuple[io.BytesIO, dict]:
    """Generate a QR code PNG for the given app user."""
    collect_settings = build_collect_settings(
        project=project,
        app_user=app_user,
        base_url=base_url,
    )

    qr_data = base64.b64encode(zlib.compress(json.dumps(collect_settings).encode("utf-8")))
    code_buffer = create_qr_code(qr_data)

    png = Image.open(code_buffer)
    png = png.convert("RGB")
    text_anchor = png.height
    png = ImageOps.expand(png, border=(0, 0, 0, 30), fill=(255, 255, 255))
    draw = ImageDraw.Draw(png)
    font = ImageFont.truetype(Path(__file__).parent / "Roboto-Regular.ttf", 24)
    language = project.collect_general_app_language
    label = f"{app_user.displayName}-{language}"
    draw.text((20, text_anchor - 10), label, font=font, fill=(0, 0, 0))
    png_buffer = io.BytesIO()
    png.save(png_buffer, format="PNG")
    logger.info("Generated QR code", app_user=app_user.displayName, qr_code=label)
    return png_buffer, collect_settings
