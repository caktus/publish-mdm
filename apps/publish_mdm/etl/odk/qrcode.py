import base64
import io
import json
import zlib
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFont, ImageOps

from apps.publish_mdm.utils import create_qr_code

from .constants import DEFAULT_COLLECT_SETTINGS
from .publish import ProjectAppUserAssignment

logger = structlog.getLogger(__name__)


def deep_merge(base: dict, overrides: dict) -> dict:
    """Return a new dict that is ``base`` deep-merged with ``overrides``.

    For each key in ``overrides``:
    - If the value is a dict and the corresponding value in ``base`` is also a
      dict, recurse.
    - Otherwise, the value from ``overrides`` wins.
    """
    result = base.copy()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_collect_settings(
    app_user: ProjectAppUserAssignment,
    base_url: str,
    project_id: int,
    project_name_prefix: str,
    language: str = "en",
    admin_pw: str = "",
    project_settings: dict | None = None,
):
    """Build Collect settings for the given app user.

    Args:
        project_settings: Optional project-level collect settings (from
            ``Project.collect_settings``).  These are deep-merged on top of
            ``DEFAULT_COLLECT_SETTINGS`` before the dynamic fields are applied,
            so dynamic fields (server_url, username, app_language, project name,
            admin_pw) always take precedence.
    """
    collect_settings = deep_merge(DEFAULT_COLLECT_SETTINGS, project_settings or {})

    # Dynamic fields always override project-provided values.
    if admin_pw:
        collect_settings["admin"]["admin_pw"] = admin_pw

    url = f"{base_url.rstrip('/')}/key/{app_user.token}/projects/{project_id}"
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
    project_settings: dict | None = None,
) -> tuple[io.BytesIO, dict]:
    """Generate a QR code as a PNG for the given app user."""

    # Build app user settings
    collect_settings = build_collect_settings(
        app_user=app_user,
        admin_pw=admin_pw,
        base_url=base_url,
        project_id=project_id,
        project_name_prefix=project_name_prefix,
        language=language,
        project_settings=project_settings,
    )

    # Generate QR code with segno
    qr_data = base64.b64encode(zlib.compress(json.dumps(collect_settings).encode("utf-8")))
    code_buffer = create_qr_code(qr_data)

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
