from config import dagster

import pytest


@pytest.mark.parametrize(
    "dagster_url, expected",
    [
        ("http://localhost:3000", True),
        ("http://dagster.publish-mdm.svc.cluster.local:3030", True),
        (None, False),
        ("", False),
    ],
)
def test_dagster_enabled(settings, dagster_url, expected):
    """Test if Dagster is enabled based on the settings."""
    settings.DAGSTER_URL = dagster_url
    assert dagster.dagster_enabled() == expected, "Dagster enabled state mismatch"


@pytest.mark.parametrize(
    "dagster_url, expected",
    [
        (
            "http://localhost:3000",
            {"hostname": "localhost", "port_number": 3000, "use_https": False},
        ),
        (
            "http://dagster.publish-mdm.svc.cluster.local:3030",
            {
                "hostname": "dagster.publish-mdm.svc.cluster.local",
                "port_number": 3030,
                "use_https": False,
            },
        ),
        (
            "https://example.com:443",
            {"hostname": "example.com", "port_number": 443, "use_https": True},
        ),
    ],
)
def test_parse_dagster_url(settings, dagster_url, expected):
    """Test parsing of Dagster URL."""
    settings.DAGSTER_URL = dagster_url
    result = dagster.parse_dagster_url(dagster_url)
    assert result == expected, f"Parsed result mismatch for {dagster_url}"


def test_parse_dagster_url_invalid(settings):
    """Test parsing of an invalid Dagster URL."""
    settings.DAGSTER_URL = "invalid-url"
    with pytest.raises(ValueError, match="Invalid Dagster URL"):
        dagster.parse_dagster_url(settings.DAGSTER_URL)


def test_trigger_dagster_job(settings, mocker):
    """Test triggering a Dagster job."""
    settings.DAGSTER_URL = "http://localhost:3000"
    mock_client = mocker.patch("config.dagster.DagsterGraphQLClient")
    mock_client.return_value.submit_job_execution.return_value = "run_123"
    run_id = dagster.trigger_dagster_job("job_name", {"key": "value"})
    assert run_id == "run_123", "Run ID mismatch after triggering Dagster job"
    mock_client.assert_called_once_with(hostname="localhost", port_number=3000, use_https=False)


def test_trigger_dagster_job_not_enabled(settings, mocker):
    """Test triggering a Dagster job when Dagster is not enabled."""
    settings.DAGSTER_URL = None
    mock_client = mocker.patch("config.dagster.DagsterGraphQLClient")
    run_id = dagster.trigger_dagster_job("job_name", {"key": "value"})
    assert run_id == "", "Run ID should be empty when Dagster is not enabled"
    mock_client.assert_not_called()  # Ensure no client was created


def test_trigger_dagster_job_error(settings, mocker):
    """Test error handling when triggering a Dagster job."""
    settings.DAGSTER_URL = "http://localhost:3000"
    mock_client = mocker.patch("config.dagster.DagsterGraphQLClient")
    mock_client.return_value.submit_job_execution.side_effect = dagster.DagsterGraphQLClientError(
        "Job submission failed"
    )

    with pytest.raises(dagster.DagsterGraphQLClientError, match="Job submission failed"):
        dagster.trigger_dagster_job("job_name", {"key": "value"})

    mock_client.assert_called_once_with(hostname="localhost", port_number=3000, use_https=False)
