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

    def test_get_request_initialization(self, rf):
        request = rf.get("/api/firmware/", {"version": "unknown", "device_id": "12345"})
        form = FirmwareSnapshotForm(request=request)
        assert form.is_valid(), form.errors
        assert form.data["serial_number"] == "12345"

    def test_post_request_initialization(self, rf):
        request = rf.post("/api/firmware/", {"version": "unknown", "device_id": "12345"})
        form = FirmwareSnapshotForm(request=request)
        assert form.is_valid(), form.errors
        assert form.data["serial_number"] == "12345"

    def test_clean_with_alternatives(self, rf):
        request = rf.get(
            "/api/firmware/",
            {"version": "unknown", "alternatives": "1.0.0,2.0.0", "device_id": "12345"},
        )
        form = FirmwareSnapshotForm(request=request)
        assert form.is_valid()
        assert form.cleaned_data["version"] == "1.0.0"

    def test_clean_without_alternatives(self, rf):
        request = rf.get("/api/firmware/", {"version": "unknown", "device_id": "12345"})
        form = FirmwareSnapshotForm(request=request)
        assert form.is_valid()

    @pytest.mark.django_db
    def test_save_with_existing_device(self, rf):
        device = DeviceFactory(
            serial_number="12345", raw_mdm_device={"user_id": "123", "nickname": "test"}
        )
        request = rf.post("/api/firmware/", {"serial_number": "12345", "version": "1.0.0"})
        form = FirmwareSnapshotForm(request=request)
        form.is_valid()
        instance = form.save()
        assert instance.device == device

    @pytest.mark.django_db
    def test_save_without_existing_device(self, rf):
        request = rf.post("/api/firmware/", {"serial_number": "12345", "version": "1.0.0"})
        form = FirmwareSnapshotForm(request=request)
        form.is_valid()
        instance = form.save()
        assert instance.device is None

    @pytest.mark.django_db
    def test_empty_get_doesnt_save(self, rf):
        request = rf.get("/api/firmware/")
        form = FirmwareSnapshotForm(request=request)
        assert form.is_valid() is False

    @pytest.mark.django_db
    def test_empty_post_doesnt_save(self, rf):
        request = rf.post("/api/firmware/")
        form = FirmwareSnapshotForm(request=request)
        assert form.is_valid() is False
