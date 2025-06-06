from django.conf import settings
from dagster_graphql import DagsterGraphQLClient, DagsterGraphQLClientError
import structlog
import urllib.parse as urlparse


logger = structlog.get_logger(__name__)


def dagster_enabled() -> bool:
    """Check if Dagster is enabled in the settings."""
    return bool(settings.DAGSTER_URL)


def parse_dagster_url(dagster_url: str) -> dict:
    """Parse the Dagster URL to extract the connection options."""
    split_result = urlparse.urlsplit(dagster_url)
    if not split_result.hostname:
        raise ValueError(f"Invalid Dagster URL: {dagster_url}")
    return {
        "hostname": split_result.hostname,
        "port_number": split_result.port or 3000,
        "use_https": split_result.scheme == "https",
    }


def trigger_dagster_job(job_name: str, run_config: dict) -> str:
    """Trigger a Dagster job with the specified run configuration.

    Returns:
        new_run_id: The ID of the newly created run.
    """
    if not dagster_enabled():
        logger.warning("Dagster is not enabled, skipping job trigger")
        return ""
    config = parse_dagster_url(settings.DAGSTER_URL)
    client = DagsterGraphQLClient(
        hostname=config["hostname"],
        port_number=config["port_number"],
        use_https=config["use_https"],
    )
    try:
        new_run_id: str = client.submit_job_execution(job_name, run_config=run_config)
        logger.info("Dagster job triggered successfully", job_name=job_name, run_id=new_run_id)
    except DagsterGraphQLClientError as exc:
        logger.error("Failed to trigger Dagster job", job_name=job_name, error=str(exc))
        raise exc
    return new_run_id
