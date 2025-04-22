import json
import pytest
from apps.mdm.forms import FirmwareSnapshotForm
from tests.mdm.factories import DeviceFactory


class TestFirmwareSnapshotForm:
    TINYMDM_ENV_VARS = ("TINYMDM_APIKEY_PUBLIC", "TINYMDM_APIKEY_SECRET", "TINYMDM_ACCOUNT_ID")

    @pytest.fixture(autouse=True)
    def del_tinymdm_env_vars(self, monkeypatch):
        """Delete environment variables for TinyMDM API credentials, if they exist."""
        for var in self.TINYMDM_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

    def test_post_request_initialization(self):
        json_data = {"version": "unknown", "deviceIdentifier": "12345"}
        form = FirmwareSnapshotForm(json_data=json_data)
        assert form.is_valid(), form.errors
        assert form.data["serial_number"] == "12345"

    @pytest.mark.django_db
    def test_save_with_existing_device(self):
        device = DeviceFactory(
            serial_number="12345", raw_mdm_device={"user_id": "123", "nickname": "test"}
        )
        json_data = {"serialNumber": "12345", "version": "1.0.0"}
        form = FirmwareSnapshotForm(json_data=json_data)
        form.is_valid()
        instance = form.save()
        assert instance.device == device

    @pytest.mark.django_db
    def test_save_without_existing_device(self):
        json_data = {"serialNumber": "12345", "version": "1.0.0"}
        form = FirmwareSnapshotForm(json_data=json_data)
        form.is_valid()
        instance = form.save()
        assert instance.device is None

    @pytest.mark.django_db
    def test_empty_post_doesnt_save(self):
        form = FirmwareSnapshotForm(json_data={})
        assert form.is_valid() is False
