import pytest
from apps.mdm.forms import FirmwareSnapshotForm
from tests.mdm.factories import DeviceFactory


class TestFirmwareSnapshotForm:
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


@pytest.mark.django_db
class TestFirmwareSnapshotFormVersionExtraction:
    def test_version_with_brackets_stripped(self):
        """clean() strips brackets from ro.product.version when present."""
        data = {
            "deviceIdentifier": "SN12345",
            "buildInfo": {"buildPropContent": {"[ro.product.version]": "[1.2.3]"}},
            "versionInfo": {},
        }
        from apps.mdm.forms import FirmwareSnapshotForm

        form = FirmwareSnapshotForm(json_data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["version"] == "1.2.3"

    def test_version_from_alternatives_when_build_info_empty(self):
        """clean() falls back to versionInfo.alternatives[0] when buildInfo has no version."""
        data = {
            "deviceIdentifier": "SN12345",
            "buildInfo": {"buildPropContent": {}},
            "versionInfo": {"alternatives": ["2.0.0", "1.9.9"]},
        }
        from apps.mdm.forms import FirmwareSnapshotForm

        form = FirmwareSnapshotForm(json_data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["version"] == "2.0.0"
