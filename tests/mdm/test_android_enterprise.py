import datetime as dt
import json
from collections import namedtuple

import faker
import pytest
from django.contrib.sites.models import Site
from googleapiclient.errors import HttpError

from apps.mdm.mdms import AndroidEnterprise, MDMAPIError
from apps.mdm.mdms.android_enterprise import (
    ALL_SCOPES,
    ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT,
    PUBSUB_RESOURCE_NAME,
    MDMDevice,
)
from apps.mdm.models import Device, DeviceSnapshot
from tests.mdm import TestAndroidEnterpriseOnly
from tests.publish_mdm.factories import (
    AndroidEnterpriseAccountFactory,
    AppUserFactory,
    OrganizationFactory,
    ProjectFactory,
)

from .factories import DeviceFactory, FleetFactory, PolicyFactory

fake = faker.Faker()
MockAPIResponse = namedtuple(
    "MockAPIResponse",
    ["method_id", "content", "status_code", "expected_request_body"],
    defaults=[None, None, None],
)


@pytest.mark.django_db
class TestAndroidEnterprise(TestAndroidEnterpriseOnly):
    @pytest.fixture
    def fleet(self, organization):
        return FleetFactory(organization=organization)

    @pytest.fixture
    def devices(self, fleet):
        """Create 6 Devices, one with a blank device_id."""
        return [
            *DeviceFactory.create_batch(5, fleet=fleet),
            DeviceFactory(fleet=fleet, device_id=""),
        ]

    def get_fake_device_data(self):
        data = {
            "lastPolicySyncTime": fake.date_time(tzinfo=dt.UTC)
            .replace(microsecond=0)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hardwareInfo": {
                "manufacturer": fake.company(),
            },
            "managementMode": fake.random_element(["DEVICE_OWNER", "PROFILE_OWNER"]),
            "state": "ACTIVE",
        }
        # Some values that may or may not be present depending on the policy and/or the device type
        if fake.pybool():
            data["softwareInfo"] = {
                "androidVersion": fake.android_platform_token(),
            }
        if fake.pybool():
            event_type = fake.random_element(["BATTERY_LEVEL_COLLECTED", "ANOTHER_TYPE"])
            data["powerManagementEvents"] = [
                {
                    "createTime": "2025-07-09T00:48:50.346Z",
                    "eventType": event_type,
                    **(
                        {"batteryLevel": fake.pyint(0, 100)}
                        if event_type == "BATTERY_LEVEL_COLLECTED"
                        else {}
                    ),
                }
            ]
        if fake.pybool():
            data["applicationReports"] = [
                {
                    "packageName": f"org.{fake.word()}.{fake.word()}",
                    "displayName": fake.sentence(),
                    "versionCode": fake.pyint(),
                    "versionName": fake.word(),
                    "userFacingType": fake.random_element(["USER_FACING", "NOT USER_FACING"]),
                }
                for _ in range(5)
            ]
        return data

    def get_raw_mdm_device(self, device):
        """Create data for the Device.raw_mdm_device field based on other fields' values."""
        fake_data = self.get_fake_device_data()
        return {
            "name": device.name,
            "hardwareInfo": {
                "serialNumber": device.serial_number,
                **fake_data.pop("hardwareInfo"),
            },
            "enrollmentTokenData": json.dumps({"fleet": device.fleet_id}),
            **fake_data,
        }

    @pytest.fixture
    def devices_response(self, devices, fleet):
        """Mock response for a device listing API request."""
        # Existing devices, which should be updated in the DB
        existing_devices = []
        for device in devices:
            response = self.get_raw_mdm_device(device)
            if device.device_id:
                response["hardwareInfo"]["serialNumber"] = f"updated-{device.serial_number}"
            existing_devices.append(response)
        # New devices, which should be created in the DB
        new_devices = [
            self.get_raw_mdm_device(device) for device in DeviceFactory.build_batch(4, fleet=fleet)
        ]
        return existing_devices + new_devices

    @pytest.fixture
    def device(self, request, fleet):
        """Create one Device. If request.param is True, create an AppUser with
        the name in the device's app_user_name field and with qr_code_data set.
        """
        device = DeviceFactory.build(fleet=fleet)
        device.raw_mdm_device = self.get_raw_mdm_device(device)
        if request.param:
            AppUserFactory(
                name=device.app_user_name,
                project=fleet.project,
                qr_code_data={},
            )
        else:
            device.app_user_name = ""
        device.save()
        return device

    @pytest.fixture
    def fleets(self, fleet):
        return [*FleetFactory.create_batch(2, organization=fleet.organization), fleet]

    def test_mdm_not_configured(self, unconfigure_mdm):
        """Ensure AndroidEnterprise.is_configured property returns False if a service
        account file is not provided via the ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE
        env var and the organization doesn't have an enrolled AndroidEnterpriseAccount.
        """
        active_mdm = AndroidEnterprise(organization=OrganizationFactory())
        assert not active_mdm.is_configured
        assert not active_mdm
        with pytest.raises(
            ValueError, match="ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not configured"
        ):
            assert active_mdm.credentials

    def test_mdm_configured(self, organization):
        """Ensure AndroidEnterprise.is_configured property returns True when a service
        account file is provided via the ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE env var
        and the organization has an enrolled AndroidEnterpriseAccount.
        """
        active_mdm = AndroidEnterprise(organization=organization)
        assert active_mdm.is_configured
        assert active_mdm
        assert active_mdm.api
        assert active_mdm.pubsub_api
        assert active_mdm.enterprise_name == f"enterprises/{active_mdm.enterprise_id}"

    def test_mdm_partially_configured(self, organization, del_amapi_service_account_file):
        """If the organization has an enrolled AndroidEnterpriseAccount but a service
        account file is not provided, instantiating a AndroidEnterprise should raise a ValueError.
        """
        with pytest.raises(
            ValueError,
            match="credentials are not properly configured or service account file is missing",
        ):
            AndroidEnterprise(organization=organization)

    @pytest.mark.parametrize(
        "enterprise_name,expected_id",
        [
            # Account with a fully-enrolled enterprise_name
            ("enterprises/LC00lvvue0", "LC00lvvue0"),
            # Account exists but enrollment has not completed
            ("", None),
            # No AndroidEnterpriseAccount for the org at all
            (None, None),
        ],
    )
    def test_enterprise_id(
        self, set_amapi_service_account_file, enterprise_name, expected_id, mocker
    ):
        """enterprise_id is read from the org's AndroidEnterpriseAccount; returns None when unset."""
        organization = OrganizationFactory()
        if enterprise_name is not None:
            AndroidEnterpriseAccountFactory(
                organization=organization, enterprise_name=enterprise_name
            )
        mocker.patch.object(AndroidEnterprise, "is_configured", return_value=True)
        mdm = AndroidEnterprise(organization=organization)
        assert mdm.enterprise_id == expected_id

    def test_enterprise_id_no_organization(self):
        """enterprise_id is None when AndroidEnterprise is instantiated without an organization."""
        mdm = AndroidEnterprise(organization=None)
        assert mdm.enterprise_id is None

    @pytest.mark.parametrize("with_default_app_user", [False, True])
    def test_pull_devices(
        self,
        fleet,
        devices_response,
        fleets,
        devices,
        monkeypatch,
        with_default_app_user,
        caplog,
    ):
        """Ensures calling pull_devices() updates and creates Devices as expected."""
        if with_default_app_user:
            default_app_user = AppUserFactory(project=fleet.project)
            fleet.default_app_user = default_app_user
            fleet.save()

        active_mdm = AndroidEnterprise(organization=fleet.organization)

        # Existing devices in another fleet should not be updated
        not_in_fleet = [
            self.get_raw_mdm_device(d) for d in DeviceFactory.create_batch(2, fleet=fleets[0])
        ]
        # New devices enrolled in another fleet should not be created
        not_in_fleet += [
            self.get_raw_mdm_device(d) for d in DeviceFactory.build_batch(2, fleet=fleets[0])
        ]
        # New devices but enrollmentTokenData is not in the expected format,
        # so we can't tell which Fleet to add them to
        for index, d in enumerate(DeviceFactory.build_batch(2)):
            data = self.get_raw_mdm_device(d)
            if index:
                data["enrollmentTokenData"] = "invalid"
            else:
                data["enrollmentTokenData"] = "[]"
            not_in_fleet.append(data)
        # Devices currently still enrolling (state is "PROVISIONING") should not be created
        # and should not raise a KeyError due to missing lastPolicySyncTime
        provisioning_device = self.get_raw_mdm_device(DeviceFactory.build(fleet=fleet))
        provisioning_device.update({"state": "PROVISIONING"})
        del provisioning_device["lastPolicySyncTime"]

        full_devices_response = {"devices": devices_response + not_in_fleet + [provisioning_device]}
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("devices.list", full_devices_response)),
        )

        # Soft-deleted device should be skipped during update
        soft_deleted_device = DeviceFactory(fleet=fleet)
        soft_deleted_device.soft_delete()

        active_mdm.pull_devices(fleet)

        assert fleet.devices.count() == 10
        # 4 devices are new
        new_devices = fleet.devices.exclude(id__in=[i.id for i in devices])
        assert new_devices.count() == 4
        # New devices should have the fleet's default app user name, or blank if none is set
        expected_app_user_name = fleet.default_app_user.name if with_default_app_user else ""
        assert all(d.app_user_name == expected_app_user_name for d in new_devices)
        # Ensure the devices have the expected data from the API response
        db_devices = Device.objects.in_bulk(field_name="device_id")
        for device in devices_response:
            expected_device_id = device["name"].split("/")[-1]
            db_device = db_devices.get(expected_device_id)
            assert db_device
            assert db_device.serial_number == device["hardwareInfo"]["serialNumber"]
            assert db_device.name == device["name"]
            assert db_device.raw_mdm_device == device

            # Ensure a snapshot has been saved with the expected data
            snapshot = db_device.latest_snapshot
            assert snapshot is not None
            assert snapshot.mdm_device == db_device
            assert snapshot.raw_mdm_device == device
            assert snapshot.serial_number == device["hardwareInfo"]["serialNumber"]
            assert snapshot.name == device["name"]
            assert snapshot.last_sync == dt.datetime.fromisoformat(device["lastPolicySyncTime"])
            assert snapshot.manufacturer == device["hardwareInfo"]["manufacturer"]
            assert snapshot.enrollment_type == device["managementMode"]

            if sofware_info := device.get("softwareInfo"):
                assert snapshot.os_version == sofware_info["androidVersion"]

            if power_events := device.get("powerManagementEvents"):
                assert snapshot.battery_level == power_events[0].get("batteryLevel")

            if apps := device.get("applicationReports"):
                # Ensure the apps have been saved with the expected data
                assert {
                    tuple(i.values()) for i in apps if i.pop("userFacingType") == "USER_FACING"
                } == set(
                    snapshot.apps.values_list(
                        "package_name", "app_name", "version_code", "version_name"
                    )
                )
            else:
                assert not snapshot.apps.exists()

        expected_skip_msg = {
            "event": "Skipping device",
            "device": soft_deleted_device,
        }
        assert any(
            record
            for record in caplog.records
            if record.levelname == "DEBUG" and expected_skip_msg.items() <= record.msg.items()
        )

    def test_get_devices(self, mocker, monkeypatch, organization):
        """Ensures calling get_devices() downloads device data as expected."""
        active_mdm = AndroidEnterprise(organization=organization)
        full_devices_response = {"devices": [self.get_raw_mdm_device(DeviceFactory.build())]}
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("devices.list", full_devices_response)),
        )
        mock_execute = mocker.patch.object(active_mdm, "execute", wraps=active_mdm.execute)
        assert not hasattr(active_mdm, "_devices")

        devices = active_mdm.get_devices()

        # Ensure the caching works as expected
        # Subsequent get_devices() calls should not make an API request
        assert active_mdm._devices == devices
        active_mdm.get_devices()
        active_mdm.get_devices()
        mock_execute.assert_called_once()

    def test_sync_fleet(self, fleet, devices, mocker):
        """Ensure calling sync_fleet() calls pull_devices() for the specified fleet
        and push_device_config() for ALL devices in the fleet, regardless of whether
        app_user_name is set (every Android Enterprise device needs its own AMAPI policy).
        """
        # Make app_user_name blank for some devices
        fleet.devices.filter(id__in=[d.id for d in devices][:3]).update(app_user_name="")
        all_devices = list(fleet.devices.all())

        active_mdm = AndroidEnterprise(organization=fleet.organization)
        mock_pull_devices = mocker.patch.object(active_mdm, "pull_devices")
        mock_push_device_config = mocker.patch.object(active_mdm, "push_device_config")
        active_mdm.sync_fleet(fleet)

        mock_pull_devices.assert_called_once()
        # push_device_config should be called for ALL devices, including those
        # without an app_user_name, so each device gets its own AMAPI policy
        mock_push_device_config.assert_has_calls(
            [mocker.call(device=device) for device in all_devices],
            any_order=True,
        )
        assert mock_push_device_config.call_count == len(all_devices)

    def test_sync_fleet_with_push_config_false(self, fleet, devices, mocker):
        """Ensure calling sync_fleet() with push_config=False calls pull_devices()
        for the specified fleet but does not call push_device_config() for any device.
        """
        active_mdm = AndroidEnterprise(organization=fleet.organization)
        mock_pull_devices = mocker.patch.object(active_mdm, "pull_devices")
        mock_push_device_config = mocker.patch.object(active_mdm, "push_device_config")
        active_mdm.sync_fleet(fleet, push_config=False)

        mock_pull_devices.assert_called_once()
        mock_push_device_config.assert_not_called()

    def test_sync_fleets(self, fleets, mocker):
        """Ensure calling sync_fleets() calls sync_fleet() for all fleets."""
        active_mdm = AndroidEnterprise(organization=fleets[0].organization)
        # Create fleets in other orgs. These should not be synced
        FleetFactory.create_batch(2)
        mock_sync_fleet = mocker.patch.object(active_mdm, "sync_fleet")
        active_mdm.sync_fleets()

        assert mock_sync_fleet.call_count == len(fleets)
        called_fleets = [call.kwargs["fleet"] for call in mock_sync_fleet.call_args_list]
        assert set(called_fleets) == set(fleets)

    @pytest.mark.parametrize("new_fleet", [True, False])
    def test_get_enrollment_qr_code(self, monkeypatch, new_fleet, organization):
        """Ensures get_enrollment_qr_code() makes the expected API request and updates
        the fleet's enroll_qr_code, enroll_token_expires_at, and enroll_token_value
        if successful.
        """
        active_mdm = AndroidEnterprise(organization=organization)
        if new_fleet:
            project = ProjectFactory()
            fleet = FleetFactory.build(
                enroll_qr_code=None,
                project=project,
                organization=project.organization,
                policy=PolicyFactory(),
            )
            # We don't have a Fleet ID yet to set in additionalData, so we won't
            # check the request body
            expected_request_body = None
        else:
            fleet = FleetFactory(enroll_qr_code=None)
            expected_request_body = {
                "policyName": f"{active_mdm.enterprise_name}/policies/{fleet.policy.policy_id}",
                "additionalData": json.dumps({"fleet": fleet.pk}),
                "duration": f"{24 * 60 * 60}s",
                "allowPersonalUsage": "ALLOW_PERSONAL_USAGE_UNSPECIFIED",
            }
        value = fake.pystr()
        expiry = fake.date_time(tzinfo=dt.UTC).replace(microsecond=0)
        qr_code = {
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": "com.google.android.apps.work.clouddpc/.receivers.CloudDeviceAdminReceiver",
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": fake.pystr(),
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": "https://play.google.com/managed/downloadManagingApp?identifier=setup",
            "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
                "com.google.android.apps.work.clouddpc.EXTRA_ENROLLMENT_TOKEN": value
            },
        }
        enrollment_token_response = {
            "name": f"enterprises/{active_mdm.enterprise_id}/enrollmentTokens/{fake.pystr()}",
            "value": value,
            "expirationTimestamp": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "qrCode": json.dumps(qr_code),
        }
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse(
                    "enrollmentTokens.create",
                    enrollment_token_response,
                    None,
                    expected_request_body,
                )
            ),
        )

        active_mdm.get_enrollment_qr_code(fleet)

        assert fleet.enroll_qr_code is not None
        assert fleet.enroll_token_expires_at == expiry
        assert fleet.enroll_token_value == value

    def test_delete_group(self, fleet):
        """Ensure delete_group() returns False if a fleet has devices in the DB,
        True otherwise.
        """
        active_mdm = AndroidEnterprise()
        assert active_mdm.delete_group(fleet)

        DeviceFactory(fleet=fleet)
        assert not active_mdm.delete_group(fleet)

    @pytest.mark.parametrize("api_error", [(500, None), (499, {"error": {"message": "Reason"}})])
    @pytest.mark.parametrize("raise_exception", [True, False])
    def test_execute(self, monkeypatch, api_error, raise_exception, organization):
        """Test handling of API errors in the execute() function."""
        active_mdm = AndroidEnterprise(organization=organization)
        status_code, response_json = api_error
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("devices.list", response_json, status_code),
            ),
        )
        resource_method = (
            active_mdm.api.enterprises().devices().list(parent=active_mdm.enterprise_name)
        )
        expected_api_error = MDMAPIError(status_code=status_code, error_data=response_json)

        if raise_exception:
            # Should raise an exception with its api_error attribute set to an MDMAPIError object
            with pytest.raises(HttpError) as exc:
                active_mdm.execute(resource_method, raise_exception)
            assert exc.value.api_error == expected_api_error
        else:
            active_mdm.execute(resource_method, raise_exception)
            assert expected_api_error in active_mdm.api_errors

    def test_create_or_update_policy(self, monkeypatch, mocker, organization):
        """Ensure create_or_update_policy() makes the expected API request."""
        active_mdm = AndroidEnterprise(organization=organization)
        policy = PolicyFactory()
        mock_execute = mocker.patch.object(active_mdm, "execute", wraps=active_mdm.execute)

        # If Policy.get_policy_data() returns None, an API request to update the
        # policy should not be made
        mock_get_policy_data = mocker.patch.object(policy, "get_policy_data", return_value=None)
        active_mdm.create_or_update_policy(policy)
        mock_get_policy_data.assert_called_once()
        mock_execute.assert_not_called()

        policy_data = {
            "deviceOwnerLockScreenInfo": {
                "localizedMessages": {"en": fake.word()},
                "defaultMessage": fake.word(),
            }
        }
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("policies.patch", expected_request_body=policy_data)
            ),
        )
        mock_get_policy_data = mocker.patch.object(
            policy, "get_policy_data", return_value=policy_data
        )
        active_mdm.create_or_update_policy(policy)
        mock_get_policy_data.assert_called_once()
        mock_execute.assert_called_once()

    def test_create_enrollment_token_with_duration(self, monkeypatch, fleet):
        """create_enrollment_token() passes duration_seconds to the API."""
        active_mdm = AndroidEnterprise(organization=fleet.organization)
        token_response = {
            "name": "enterprises/test/enrollmentTokens/token1",
            "value": "tok123",
            "expirationTimestamp": "2026-01-01T00:00:00Z",
            "qrCode": '{"key": "value"}',
        }
        expected_body = {
            "policyName": f"{active_mdm.enterprise_name}/policies/{fleet.policy.policy_id}",
            "additionalData": json.dumps({"fleet": fleet.pk}),
            "duration": "2592000s",
            "allowPersonalUsage": "PERSONAL_USAGE_DISALLOWED",
        }
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("enrollmentTokens.create", token_response, None, expected_body)
            ),
        )
        result = active_mdm.create_enrollment_token(
            fleet, duration_seconds=2592000, allow_personal_usage="PERSONAL_USAGE_DISALLOWED"
        )
        assert result["value"] == "tok123"

    def test_revoke_enrollment_token(self, monkeypatch, organization):
        """revoke_enrollment_token() calls enrollmentTokens.delete."""
        active_mdm = AndroidEnterprise(organization=organization)
        resource_name = "enterprises/test/enrollmentTokens/abc123"
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("enrollmentTokens.delete", None, None)),
        )
        # Should not raise
        active_mdm.revoke_enrollment_token(resource_name)

    def test_revoke_enrollment_token_404_is_silent(self, monkeypatch, organization):
        """revoke_enrollment_token() handles 404 gracefully."""
        active_mdm = AndroidEnterprise(organization=organization)
        resource_name = "enterprises/test/enrollmentTokens/gone"
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("enrollmentTokens.delete", None, 404)),
        )
        # Should not raise
        active_mdm.revoke_enrollment_token(resource_name)

    def test_revoke_enrollment_token_other_errors_reraised(self, monkeypatch, organization):
        """revoke_enrollment_token() re-raises non-404 HttpErrors."""
        active_mdm = AndroidEnterprise(organization=organization)
        resource_name = "enterprises/test/enrollmentTokens/abc123"
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("enrollmentTokens.delete", None, 500)),
        )
        with pytest.raises(HttpError):
            active_mdm.revoke_enrollment_token(resource_name)

    @pytest.mark.parametrize("current_device_policy", ["own", "base", "other_fleet"])
    def test_push_device_config(
        self,
        fleet,
        monkeypatch,
        mocker,
        current_device_policy,
    ):
        """Ensures push_device_config() makes the expected API requests."""
        device = DeviceFactory.build(fleet=fleet)
        expected_policy_name = f"enterprises/test/policies/fleet{fleet.id}_{device.device_id}"
        if current_device_policy == "own":
            current_policy_name = expected_policy_name
        elif current_device_policy == "other_fleet":
            current_policy_name = (
                f"enterprises/test/policies/fleet{fleet.id + 1}_{device.device_id}"
            )
        else:
            current_policy_name = f"enterprises/test/policies/{fleet.policy.policy_id}"
        device.raw_mdm_device = {
            "policyName": current_policy_name,
            **self.get_raw_mdm_device(device),
        }
        device.save()
        active_mdm = AndroidEnterprise(organization=fleet.organization)
        mock_execute = mocker.patch.object(active_mdm, "execute", wraps=active_mdm.execute)
        policy_data = {
            "deviceOwnerLockScreenInfo": {
                "localizedMessages": {"en": fake.word()},
                "defaultMessage": fake.word(),
            }
        }
        mock_get_policy_data = mocker.patch.object(
            device.fleet.policy, "get_policy_data", return_value=policy_data
        )
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("policies.patch", expected_request_body=policy_data),
                MockAPIResponse(
                    "devices.patch",
                    device.raw_mdm_device | {"policyName": expected_policy_name},
                    expected_request_body={"policyName": expected_policy_name},
                ),
                MockAPIResponse("policies.delete"),
            ),
        )
        active_mdm.push_device_config(device)

        mock_get_policy_data.assert_called_once()

        if current_device_policy == "own":
            # Only one API request expected, to update the policy
            assert mock_execute.call_count == 1
        elif current_device_policy == "base":
            # Two API requests expected:
            # 1. create the policy
            # 2. update the device's policy name
            assert mock_execute.call_count == 2
        elif current_device_policy == "other_fleet":
            # One additional API request expected, to delete the current policy
            assert mock_execute.call_count == 3

        device.refresh_from_db()
        assert device.raw_mdm_device["policyName"] == expected_policy_name

    def test_push_device_config_no_api_requests(self, fleet, mocker):
        """Ensures push_device_config() does not make any API requests if
        Device.raw_mdm_device is not set (Device hasn't been pulled before)
        or policy data is not available.
        """
        device = DeviceFactory(fleet=fleet)
        active_mdm = AndroidEnterprise(organization=fleet.organization)
        mock_get_policy_data = mocker.patch.object(
            fleet.policy, "get_policy_data", return_value=None
        )
        mock_execute = mocker.patch.object(active_mdm, "execute")

        active_mdm.push_device_config(device)
        mock_get_policy_data.assert_not_called()
        mock_execute.assert_not_called()

        device.raw_mdm_device = self.get_raw_mdm_device(device)
        device.save()

        active_mdm.push_device_config(device)
        mock_get_policy_data.assert_called_once()
        mock_execute.assert_not_called()

    def test_get_devices_breaks_on_empty_response(self, mocker, organization):
        """get_devices() breaks out of the pagination loop when execute() returns
        an empty/falsy response instead of a dict with 'devices'."""
        active_mdm = AndroidEnterprise(organization=organization)
        mocker.patch.object(active_mdm, "execute", return_value=None)
        result = active_mdm.get_devices()
        assert result == []

    def test_update_existing_devices_soft_deletes_unmatched_device(self, fleet):
        """update_existing_devices() soft-deletes a device whose device_id is set but not
        found in the MDM response by ID — matched into the queryset via serial number only,
        then soft-deleted via bulk_update because the per-device ID lookup returns None."""
        # Our device has device_id that does NOT match the MDM device name suffix
        our_device = DeviceFactory(fleet=fleet, device_id="OUR-DEVICE-ID", serial_number="SN999")
        # MDM device name has a different ID suffix; serial_number matches our_device
        mdm_device = MDMDevice(
            {
                "name": "enterprises/test/devices/DIFFERENT-MDM-ID",
                "hardwareInfo": {
                    "serialNumber": "SN999",
                    "imei": "123456789",
                },
                "policyName": "enterprises/test/policies/base",
            }
        )
        active_mdm = AndroidEnterprise(organization=fleet.organization)
        active_mdm.update_existing_devices(fleet=fleet, mdm_devices=[mdm_device])
        # deleted_at is persisted to the DB
        our_device.refresh_from_db()
        assert our_device.is_deleted
        # Device is no longer visible via the default manager
        assert not Device.objects.filter(pk=our_device.pk).exists()

    def test_update_existing_devices_soft_deletes_reenrolled_device(self, fleet):
        """A device whose name appears in another MDM device's previousDeviceNames
        is soft-deleted (via bulk_update) rather than updated.
        """
        old_device = DeviceFactory(
            fleet=fleet,
            device_id="OLDID",
            name="enterprises/test/devices/OLDID",
            serial_number="SN-REENROLL",
        )
        new_mdm_device = MDMDevice(
            {
                "name": "enterprises/test/devices/NEWID",
                "hardwareInfo": {
                    "serialNumber": "SN-REENROLL",
                    "imei": "000000000",
                },
                "previousDeviceNames": ["enterprises/test/devices/OLDID"],
                "policyName": "enterprises/test/policies/base",
            }
        )
        active_mdm = AndroidEnterprise(organization=fleet.organization)
        active_mdm.update_existing_devices(fleet=fleet, mdm_devices=[new_mdm_device])
        old_device.refresh_from_db()
        assert old_device.is_deleted
        assert not Device.objects.filter(pk=old_device.pk).exists()

    def test_pubsub_topic_and_subscription_names(self, mocker, set_amapi_service_account_file):
        """pubsub_topic and pubsub_subscription are derived from the project_id and the ENVIRONMENT setting.
        The project_id is gotten from the service account file (it is "example-project"
        in the test service account file).
        """
        active_mdm = AndroidEnterprise()
        assert active_mdm.project_id == "example-project"
        assert (
            active_mdm.pubsub_topic
            == f"projects/{active_mdm.project_id}/topics/{PUBSUB_RESOURCE_NAME}-test"
        )
        assert (
            active_mdm.pubsub_subscription
            == f"projects/{active_mdm.project_id}/subscriptions/{PUBSUB_RESOURCE_NAME}-test"
        )

    def test_ensure_pubsub_topic_creates_topic(self, set_amapi_service_account_file, monkeypatch):
        """_ensure_pubsub_topic() creates the topic when it does not exist."""
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.create"),
                prefix="pubsub.projects.",
            ),
        )
        # Should not raise
        active_mdm._ensure_pubsub_topic()

    def test_ensure_pubsub_topic_already_exists(self, set_amapi_service_account_file, monkeypatch):
        """_ensure_pubsub_topic() silently ignores a 409 Conflict response."""
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.create", status_code=409),
                prefix="pubsub.projects.",
            ),
        )
        # Should not raise
        active_mdm._ensure_pubsub_topic()

    def test_ensure_pubsub_topic_reraises_other_errors(
        self, set_amapi_service_account_file, monkeypatch
    ):
        """_ensure_pubsub_topic() re-raises non-409 HttpErrors."""
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.create", status_code=403),
                prefix="pubsub.projects.",
            ),
        )
        with pytest.raises(HttpError):
            active_mdm._ensure_pubsub_topic()

    @pytest.mark.parametrize(
        "current_bindings",
        (
            # No publisher bindings
            [],
            [{"role": "roles/pubsub.viewer", "members": ["member1@example.com"]}],
            # Has publisher bindings, but not for the Android Device Policy
            [
                {"role": "roles/pubsub.publisher", "members": ["member1@example.com"]},
                {"role": "roles/pubsub.editor", "members": ["member2@example.com"]},
            ],
        ),
    )
    def test_grant_pubsub_publisher_adds_binding(
        self, set_amapi_service_account_file, monkeypatch, current_bindings
    ):
        """_grant_pubsub_publisher() writes the Android Device Policy (ADP) binding
        via setIamPolicy.
        """
        active_mdm = AndroidEnterprise()
        expected_member = f"serviceAccount:{ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT}"
        expected_bindings = current_bindings[:]
        for binding in expected_bindings:
            if binding["role"] == "roles/pubsub.publisher":
                binding["members"].append(expected_member)
                break
        else:
            expected_bindings = [
                *current_bindings,
                {"role": "roles/pubsub.publisher", "members": [expected_member]},
            ]
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.getIamPolicy", {"bindings": current_bindings}),
                MockAPIResponse(
                    "topics.setIamPolicy",
                    expected_request_body={"policy": {"bindings": expected_bindings}},
                ),
                prefix="pubsub.projects.",
            ),
        )
        # Should not raise; body mismatch would raise ValueError from RequestMockBuilder
        active_mdm._grant_pubsub_publisher()

    def test_grant_pubsub_publisher_already_granted(
        self, set_amapi_service_account_file, monkeypatch
    ):
        """_grant_pubsub_publisher() skips setIamPolicy when ADP already has publish rights.

        check_unexpected=True means calling setIamPolicy (which is absent from the
        responses dict) would raise ValueError, so a clean run proves it was not called.
        """
        active_mdm = AndroidEnterprise()
        member = f"serviceAccount:{ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT}"
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse(
                    "topics.getIamPolicy",
                    {"bindings": [{"role": "roles/pubsub.publisher", "members": [member]}]},
                ),
                # setIamPolicy intentionally absent — check_unexpected=True would raise if called
                prefix="pubsub.projects.",
            ),
        )
        active_mdm._grant_pubsub_publisher()

    def test_grant_pubsub_publisher_get_iam_policy_error(
        self, set_amapi_service_account_file, monkeypatch
    ):
        """_grant_pubsub_publisher() re-raises errors from getIamPolicy."""
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.getIamPolicy", status_code=403),
                prefix="pubsub.projects.",
            ),
        )
        with pytest.raises(HttpError):
            active_mdm._grant_pubsub_publisher()

    def test_grant_pubsub_publisher_set_iam_policy_error(
        self, set_amapi_service_account_file, monkeypatch
    ):
        """_grant_pubsub_publisher() re-raises errors from setIamPolicy."""
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.getIamPolicy", {"bindings": []}),
                MockAPIResponse("topics.setIamPolicy", status_code=403),
                prefix="pubsub.projects.",
            ),
        )
        with pytest.raises(HttpError):
            active_mdm._grant_pubsub_publisher()

    def test_ensure_pubsub_subscription_creates_subscription(
        self, set_amapi_service_account_file, monkeypatch
    ):
        """_ensure_pubsub_subscription() calls subscriptions.create with the expected body."""
        active_mdm = AndroidEnterprise()
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/"
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse(
                    "subscriptions.create",
                    expected_request_body={
                        "topic": active_mdm.pubsub_topic,
                        "pushConfig": {"pushEndpoint": push_endpoint},
                    },
                ),
                prefix="pubsub.projects.",
            ),
        )
        # Should not raise; body mismatch would raise ValueError from RequestMockBuilder
        active_mdm._ensure_pubsub_subscription(push_endpoint)

    def test_ensure_pubsub_subscription_already_exists(
        self, set_amapi_service_account_file, monkeypatch
    ):
        """_ensure_pubsub_subscription() calls modifyPushConfig on a 409 Conflict response."""
        active_mdm = AndroidEnterprise()
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/"
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("subscriptions.create", status_code=409),
                MockAPIResponse(
                    "subscriptions.modifyPushConfig",
                    expected_request_body={"pushConfig": {"pushEndpoint": push_endpoint}},
                ),
                prefix="pubsub.projects.",
            ),
        )
        # Should not raise; body mismatch on modifyPushConfig would raise ValueError
        active_mdm._ensure_pubsub_subscription(push_endpoint)

    def test_ensure_pubsub_subscription_error(self, set_amapi_service_account_file, monkeypatch):
        """_ensure_pubsub_subscription() re-raises an error if it's not a 409."""
        active_mdm = AndroidEnterprise()
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/"
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("subscriptions.create", status_code=403),
                prefix="pubsub.projects.",
            ),
        )
        with pytest.raises(HttpError):
            active_mdm._ensure_pubsub_subscription(push_endpoint)

    def test_configure_pubsub_full_flow(self, set_amapi_service_account_file, monkeypatch):
        """configure_pubsub() orchestrates the Pub/Sub infrastructure steps only.
        It does not patch the enterprise; that is done separately via patch_enterprise_pubsub().
        """
        active_mdm = AndroidEnterprise()
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/?token=secret"

        monkeypatch.setattr(active_mdm, "_build_push_endpoint", lambda domain=None: push_endpoint)
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.create"),
                MockAPIResponse(
                    "subscriptions.create",
                    expected_request_body={
                        "topic": active_mdm.pubsub_topic,
                        "pushConfig": {"pushEndpoint": push_endpoint},
                    },
                ),
                MockAPIResponse("topics.getIamPolicy", {"bindings": []}),
                MockAPIResponse("topics.setIamPolicy"),
                prefix="pubsub.projects.",
            ),
        )

        # Should return None and not touch the enterprises API
        result = active_mdm.configure_pubsub(push_endpoint_domain="example.com")
        assert result is None

    def test_patch_enterprise_pubsub(
        self, organization, set_amapi_service_account_file, mocker, monkeypatch
    ):
        """patch_enterprise_pubsub() sets pubsubTopic and enabledNotificationTypes when enabled."""
        mocker.patch.object(AndroidEnterprise, "pubsub_enabled", return_value=True)
        active_mdm = AndroidEnterprise(organization=organization)
        enterprise_patch_result = {
            "name": active_mdm.enterprise_name,
            "pubsubTopic": active_mdm.pubsub_topic,
            "enabledNotificationTypes": ["ENROLLMENT", "STATUS_REPORT"],
        }
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse(
                    "patch",
                    enterprise_patch_result,
                    expected_request_body={
                        "pubsubTopic": active_mdm.pubsub_topic,
                        "enabledNotificationTypes": ["ENROLLMENT", "STATUS_REPORT"],
                    },
                ),
            ),
        )

        result = active_mdm.patch_enterprise_pubsub()
        assert result == enterprise_patch_result

    def test_patch_enterprise_pubsub_clears_when_not_enabled(
        self, organization, set_amapi_service_account_file, mocker, monkeypatch
    ):
        """patch_enterprise_pubsub() clears pubsubTopic and enabledNotificationTypes when pubsub_enabled() is False.

        This covers both the case where the token is not set and where the topic does not yet exist.
        """
        mocker.patch.object(AndroidEnterprise, "pubsub_enabled", return_value=False)
        active_mdm = AndroidEnterprise(organization=organization)
        clear_result = {
            "name": active_mdm.enterprise_name,
            "pubsubTopic": "",
            "enabledNotificationTypes": [],
        }
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse(
                    "patch",
                    clear_result,
                    expected_request_body={
                        "pubsubTopic": "",
                        "enabledNotificationTypes": [],
                    },
                ),
            ),
        )

        result = active_mdm.patch_enterprise_pubsub()
        assert result == clear_result

    @pytest.mark.django_db
    def test_build_push_endpoint(self, set_amapi_service_account_file, settings):
        """_build_push_endpoint() falls back to the Site domain when no domain is supplied."""
        active_mdm = AndroidEnterprise()
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "mysecret"
        settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN = ""
        Site.objects.filter(pk=settings.SITE_ID).update(domain="app.example.com")
        endpoint = active_mdm._build_push_endpoint()
        assert endpoint == "https://app.example.com/mdm/api/amapi/notifications/?token=mysecret"

    @pytest.mark.django_db
    def test_build_push_endpoint_uses_callback_domain_setting(
        self, set_amapi_service_account_file, settings
    ):
        """_build_push_endpoint() uses ANDROID_ENTERPRISE_CALLBACK_DOMAIN over the Site domain."""
        active_mdm = AndroidEnterprise()
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "mysecret"
        settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN = "callback.example.com"
        Site.objects.filter(pk=settings.SITE_ID).update(domain="site.example.com")
        endpoint = active_mdm._build_push_endpoint()
        assert (
            endpoint == "https://callback.example.com/mdm/api/amapi/notifications/?token=mysecret"
        )

    @pytest.mark.django_db
    def test_build_push_endpoint_explicit_domain_overrides_callback_domain_setting(
        self, set_amapi_service_account_file, settings
    ):
        """_build_push_endpoint() explicit domain arg takes priority over ANDROID_ENTERPRISE_CALLBACK_DOMAIN."""
        active_mdm = AndroidEnterprise()
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "mysecret"
        settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN = "callback.example.com"
        endpoint = active_mdm._build_push_endpoint(domain="explicit.example.com")
        assert (
            endpoint == "https://explicit.example.com/mdm/api/amapi/notifications/?token=mysecret"
        )

    @pytest.mark.django_db
    def test_build_push_endpoint_with_domain(self, set_amapi_service_account_file, settings):
        """_build_push_endpoint() uses the supplied domain instead of the Site domain."""
        active_mdm = AndroidEnterprise()
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "mysecret"
        endpoint = active_mdm._build_push_endpoint(domain="override.example.com")
        assert (
            endpoint == "https://override.example.com/mdm/api/amapi/notifications/?token=mysecret"
        )

    @pytest.mark.django_db
    def test_build_push_endpoint_raises_when_token_not_set(
        self, set_amapi_service_account_file, settings
    ):
        """_build_push_endpoint() raises ValueError when ANDROID_ENTERPRISE_PUBSUB_TOKEN is unset."""
        active_mdm = AndroidEnterprise()
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        with pytest.raises(ValueError, match="ANDROID_ENTERPRISE_PUBSUB_TOKEN"):
            active_mdm._build_push_endpoint()

    def test_fleet_pk_from_enrollment_token_data_valid(self):
        """Returns the fleet pk when enrollmentTokenData contains a valid 'fleet' key."""
        device = MDMDevice(
            {
                "name": "enterprises/test/devices/abc",
                "enrollmentTokenData": json.dumps({"fleet": 99}),
            }
        )
        assert AndroidEnterprise._get_fleet_pk_from_enrollment_token_data(device) == 99

    def test_fleet_pk_from_enrollment_token_data_missing(self):
        """Returns None when enrollmentTokenData is absent."""
        device = MDMDevice({"name": "enterprises/test/devices/abc"})
        assert AndroidEnterprise._get_fleet_pk_from_enrollment_token_data(device) is None

    def test_fleet_pk_from_enrollment_token_data_invalid_json(self):
        """Returns None when enrollmentTokenData is not valid JSON."""
        device = MDMDevice(
            {"name": "enterprises/test/devices/abc", "enrollmentTokenData": "not-json"}
        )
        assert AndroidEnterprise._get_fleet_pk_from_enrollment_token_data(device) is None

    def test_fleet_pk_from_enrollment_token_data_not_dict(self):
        """Returns None when the parsed JSON is not a dict."""
        device = MDMDevice(
            {
                "name": "enterprises/test/devices/abc",
                "enrollmentTokenData": json.dumps([1, 2, 3]),
            }
        )
        assert AndroidEnterprise._get_fleet_pk_from_enrollment_token_data(device) is None

    def test_fleet_pk_from_enrollment_token_data_no_fleet_key(self):
        """Returns None when the parsed dict contains no 'fleet' key."""
        device = MDMDevice(
            {
                "name": "enterprises/test/devices/abc",
                "enrollmentTokenData": json.dumps({"other": "value"}),
            }
        )
        assert AndroidEnterprise._get_fleet_pk_from_enrollment_token_data(device) is None

    def test_handle_device_notification_routes_enrollment(self, mocker):
        """handle_device_notification() dispatches ENROLLMENT to _handle_enrollment_notification."""
        active_mdm = AndroidEnterprise()
        mock_enroll = mocker.patch.object(active_mdm, "_handle_enrollment_notification")
        mock_status = mocker.patch.object(active_mdm, "_handle_status_report_notification")
        active_mdm.handle_device_notification(
            {"name": "enterprises/test/devices/abc"}, "ENROLLMENT"
        )
        mock_enroll.assert_called_once()
        mock_status.assert_not_called()

    def test_handle_device_notification_routes_status_report(self, mocker):
        """handle_device_notification() dispatches STATUS_REPORT to _handle_status_report_notification."""
        active_mdm = AndroidEnterprise()
        mock_enroll = mocker.patch.object(active_mdm, "_handle_enrollment_notification")
        mock_status = mocker.patch.object(active_mdm, "_handle_status_report_notification")
        active_mdm.handle_device_notification(
            {"name": "enterprises/test/devices/abc"}, "STATUS_REPORT"
        )
        mock_status.assert_called_once()
        mock_enroll.assert_not_called()

    def test_handle_device_notification_ignores_unknown_type(self, mocker):
        """handle_device_notification() ignores unrecognised notification types."""
        active_mdm = AndroidEnterprise()
        mock_enroll = mocker.patch.object(active_mdm, "_handle_enrollment_notification")
        mock_status = mocker.patch.object(active_mdm, "_handle_status_report_notification")
        active_mdm.handle_device_notification({"name": "enterprises/test/devices/abc"}, "COMMAND")
        mock_enroll.assert_not_called()
        mock_status.assert_not_called()

    def test_handle_enrollment_notification_creates_device(self):
        """_handle_enrollment_notification() creates a new Device for an unknown device."""
        fleet = FleetFactory()
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": "enterprises/test/devices/newdev",
                "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
                "hardwareInfo": {"serialNumber": "SN-001"},
            }
        )
        active_mdm._handle_enrollment_notification(mdm_device)
        device = Device.objects.get(device_id="newdev")
        assert device.fleet == fleet
        assert device.serial_number == "SN-001"
        assert device.name == "enterprises/test/devices/newdev"

    def test_handle_enrollment_notification_updates_existing_device(self):
        """_handle_enrollment_notification() updates an existing Device record."""
        fleet = FleetFactory()
        existing = DeviceFactory(fleet=fleet, device_id="existdev", serial_number="OLD-SN")
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": "enterprises/test/devices/existdev",
                "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
                "hardwareInfo": {"serialNumber": "NEW-SN"},
            }
        )
        active_mdm._handle_enrollment_notification(mdm_device)
        existing.refresh_from_db()
        assert existing.serial_number == "NEW-SN"
        assert existing.name == "enterprises/test/devices/existdev"

    def test_handle_enrollment_notification_soft_deletes_previous_devices(self):
        """previousDeviceNames entries are soft-deleted after the new device is saved."""
        fleet = FleetFactory()
        old_device = DeviceFactory(
            fleet=fleet,
            device_id="olddev",
            name="enterprises/test/devices/olddev",
        )
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": "enterprises/test/devices/newdev",
                "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
                "hardwareInfo": {"serialNumber": "SN-NEW"},
                "previousDeviceNames": ["enterprises/test/devices/olddev"],
            }
        )
        active_mdm._handle_enrollment_notification(mdm_device)
        # New device created
        assert Device.objects.filter(device_id="newdev").exists()
        # Old device soft-deleted
        old_device.refresh_from_db()
        assert old_device.is_deleted
        assert not Device.objects.filter(pk=old_device.pk).exists()

    def test_handle_enrollment_notification_no_previous_devices(self):
        """When previousDeviceNames is absent, no extra deletions occur."""
        fleet = FleetFactory()
        unrelated = DeviceFactory(fleet=fleet)
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": "enterprises/test/devices/newdev2",
                "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
                "hardwareInfo": {"serialNumber": "SN-NEW2"},
            }
        )
        active_mdm._handle_enrollment_notification(mdm_device)
        unrelated.refresh_from_db()
        assert not unrelated.is_deleted

    def test_handle_enrollment_notification_skips_without_fleet(self):
        """_handle_enrollment_notification() does nothing when fleet cannot be determined."""
        active_mdm = AndroidEnterprise()
        initial_count = Device.objects.count()
        mdm_device = MDMDevice({"name": "enterprises/test/devices/orphan"})
        active_mdm._handle_enrollment_notification(mdm_device)
        assert Device.objects.count() == initial_count

    def test_handle_status_report_notification_updates_device(self):
        """_handle_status_report_notification() updates device fields."""
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="srdev",
            name="enterprises/test/devices/srdev",
            serial_number="OLD-SN",
        )
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": device.name,
                "state": "ACTIVE",
                "hardwareInfo": {"serialNumber": "NEW-SN"},
            }
        )
        active_mdm._handle_status_report_notification(mdm_device)
        device.refresh_from_db()
        assert device.serial_number == "NEW-SN"

    def test_handle_status_report_notification_skips_unknown_device(self):
        """_handle_status_report_notification() silently skips an unrecognised device."""
        active_mdm = AndroidEnterprise()
        initial_count = Device.objects.count()
        mdm_device = MDMDevice({"name": "enterprises/test/devices/unknown", "state": "ACTIVE"})
        active_mdm._handle_status_report_notification(mdm_device)
        assert Device.objects.count() == initial_count

    def test_handle_status_report_notification_creates_snapshot(self):
        """_handle_status_report_notification() creates a DeviceSnapshot when data is sufficient."""
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="snapdev",
            name="enterprises/test/devices/snapdev",
            app_user_name="",
        )
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": device.name,
                "state": "ACTIVE",
                "managementMode": "DEVICE_OWNER",
                "lastPolicySyncTime": "2024-01-01T12:00:00Z",
                "hardwareInfo": {"serialNumber": "SNAP-SN", "manufacturer": "Acme"},
            }
        )
        before = DeviceSnapshot.objects.count()
        active_mdm._handle_status_report_notification(mdm_device)
        assert DeviceSnapshot.objects.count() == before + 1

    def test_handle_status_report_notification_pushes_config_on_provisioning_to_active(
        self, mocker
    ):
        """_handle_status_report_notification() calls push_device_config when the device
        transitions PROVISIONING→ACTIVE, has an app_user_name, and lacks a device-specific
        policy."""
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="provdev",
            name="enterprises/test/devices/provdev",
            app_user_name="user1",
            raw_mdm_device={
                "name": "enterprises/test/devices/provdev",
                "state": "PROVISIONING",
                "policyName": "enterprises/test/policies/default",
            },
        )
        mock_push = mocker.patch.object(AndroidEnterprise, "push_device_config")
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": device.name,
                "state": "ACTIVE",
                "policyName": "enterprises/test/policies/default",
                "hardwareInfo": {"serialNumber": "PROV-SN"},
            }
        )
        active_mdm._handle_status_report_notification(mdm_device)
        mock_push.assert_called_once()

    def test_handle_status_report_notification_no_push_without_app_user_name(self, mocker):
        """_handle_status_report_notification() does not push config when app_user_name is empty."""
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="provdev2",
            name="enterprises/test/devices/provdev2",
            app_user_name="",
            raw_mdm_device={
                "name": "enterprises/test/devices/provdev2",
                "state": "PROVISIONING",
                "policyName": "enterprises/test/policies/default",
            },
        )
        mock_push = mocker.patch.object(AndroidEnterprise, "push_device_config")
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": device.name,
                "state": "ACTIVE",
                "policyName": "enterprises/test/policies/default",
                "hardwareInfo": {"serialNumber": "PROV-SN2"},
            }
        )
        active_mdm._handle_status_report_notification(mdm_device)
        mock_push.assert_not_called()

    def test_handle_status_report_notification_no_push_when_device_specific_policy(self, mocker):
        """_handle_status_report_notification() does not push config when the policy
        is already device-specific (name ends with the device_id)."""
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="provdev3",
            name="enterprises/test/devices/provdev3",
            app_user_name="user1",
            raw_mdm_device={
                "name": "enterprises/test/devices/provdev3",
                "state": "PROVISIONING",
                "policyName": "enterprises/test/policies/fleet1_provdev3",
            },
        )
        mock_push = mocker.patch.object(AndroidEnterprise, "push_device_config")
        active_mdm = AndroidEnterprise()
        mdm_device = MDMDevice(
            {
                "name": device.name,
                "state": "ACTIVE",
                "policyName": "enterprises/test/policies/fleet1_provdev3",
                "hardwareInfo": {"serialNumber": "PROV-SN3"},
            }
        )
        active_mdm._handle_status_report_notification(mdm_device)
        mock_push.assert_not_called()

    def test_delete_device_success(self, fleet, monkeypatch, organization):
        """delete_device() calls enterprises.devices.delete."""
        device = DeviceFactory(fleet=fleet)
        active_mdm = AndroidEnterprise(organization=organization)
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("devices.delete")),
        )
        active_mdm.delete_device(device)  # should not raise

    def test_delete_device_404_logs_warning_and_does_not_raise(
        self, fleet, monkeypatch, caplog, organization
    ):
        """delete_device() logs a WARNING and does not raise when the MDM returns 404."""
        device = DeviceFactory(fleet=fleet)
        active_mdm = AndroidEnterprise(organization=organization)
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("devices.delete", status_code=404)),
        )
        active_mdm.delete_device(device)
        assert any(
            record
            for record in caplog.records
            if record.levelname == "WARNING"
            and {
                ("event", "Device not found in Android Enterprise; it may already be wiped"),
                ("device_name", device.name),
            }
            <= record.msg.items()
        )

    def test_delete_device_non_404_error_raises(self, fleet, monkeypatch, organization):
        """delete_device() re-raises non-404 HTTP errors from the MDM."""
        device = DeviceFactory(fleet=fleet)
        active_mdm = AndroidEnterprise(organization=organization)
        monkeypatch.setattr(
            active_mdm.api,
            "_requestBuilder",
            self.get_mock_request_builder(MockAPIResponse("devices.delete", status_code=500)),
        )
        with pytest.raises(HttpError) as exc:
            active_mdm.delete_device(device)
        assert exc.value.status_code == 500


@pytest.mark.django_db
class TestCredentials(TestAndroidEnterpriseOnly):
    """Tests for AndroidEnterprise.credentials property."""

    def test_no_env_var_raises(self, del_amapi_service_account_file):
        """Raises ValueError when ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not set."""
        with pytest.raises(
            ValueError, match="ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not configured"
        ):
            assert AndroidEnterprise().credentials

    def test_nonexistent_file_raises(self, monkeypatch):
        """Raises ValueError when ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE points to a non-existent path."""
        monkeypatch.setenv("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE", "/nonexistent/path/sa.json")
        with pytest.raises(
            ValueError, match="ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not configured"
        ):
            assert AndroidEnterprise().credentials

    def test_valid_file_returns_credentials(self, set_amapi_service_account_file):
        """Returns Credentials with the expected project_id and scopes when a valid file is configured."""
        credentials = AndroidEnterprise().credentials
        assert credentials is not None
        assert credentials.project_id == "example-project"
        assert set(credentials.scopes) == set(ALL_SCOPES)


@pytest.mark.django_db
class TestGetSignupUrl(TestAndroidEnterpriseOnly):
    """Tests for AndroidEnterprise.get_signup_url method."""

    def test_calls_api_and_returns_result(self, set_amapi_service_account_file, mocker):
        """Calls signupUrls.create with the correct projectId and callbackUrl, and returns the API result."""
        expected = {
            "name": "signupUrls/C455570ef9b12bfc",
            "url": "https://enterprise.google.com/signup?token=abc",
        }
        mock_api = mocker.MagicMock()
        mock_api.signupUrls.return_value.create.return_value.execute.return_value = expected
        mocker.patch("apps.mdm.mdms.android_enterprise.build", return_value=mock_api)

        result = AndroidEnterprise().get_signup_url(callback_url="https://app.example.com/callback")

        assert result == expected
        mock_api.signupUrls.return_value.create.assert_called_once_with(
            projectId="example-project",
            callbackUrl="https://app.example.com/callback",
        )

    def test_raises_when_not_configured(self, del_amapi_service_account_file):
        """Raises ValueError (from _build_credentials) when the service account file is not set."""
        with pytest.raises(
            ValueError, match="ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not configured"
        ):
            AndroidEnterprise().get_signup_url(callback_url="https://app.example.com/callback")


@pytest.mark.django_db
class TestCreateEnterprise(TestAndroidEnterpriseOnly):
    """Tests for AndroidEnterprise.create_enterprise method."""

    @pytest.mark.parametrize("topic_exists", [True, False])
    def test_calls_api_and_returns_result(
        self, set_amapi_service_account_file, mocker, topic_exists
    ):
        """Calls enterprises.create including pubsub fields only when the topic exists."""
        expected = {"name": "enterprises/LC00lvvue0"}
        mock_api = mocker.MagicMock()
        mock_api.enterprises.return_value.create.return_value.execute.return_value = expected
        mocker.patch("apps.mdm.mdms.android_enterprise.build", return_value=mock_api)

        mdm = AndroidEnterprise()
        mocker.patch.object(mdm, "pubsub_enabled", return_value=topic_exists)
        result = mdm.create_enterprise(
            signup_name="signupUrls/C455570ef9b12bfc",
            enterprise_token="T1234abcd",
            display_name="Acme Corp",
        )

        assert result == expected
        expected_body: dict = {"enterpriseDisplayName": "Acme Corp"}
        if topic_exists:
            expected_body["pubsubTopic"] = mdm.pubsub_topic
            expected_body["enabledNotificationTypes"] = ["ENROLLMENT", "STATUS_REPORT"]
        mock_api.enterprises.return_value.create.assert_called_once_with(
            projectId="example-project",
            signupUrlName="signupUrls/C455570ef9b12bfc",
            enterpriseToken="T1234abcd",
            body=expected_body,
        )

    def test_raises_when_not_configured(self, del_amapi_service_account_file):
        """Raises ValueError (from _build_credentials) when the service account file is not set."""
        with pytest.raises(
            ValueError, match="ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not configured"
        ):
            AndroidEnterprise().create_enterprise(
                signup_name="signupUrls/C455570ef9b12bfc",
                enterprise_token="T1234abcd",
                display_name="Acme Corp",
            )


@pytest.mark.django_db
class TestPubsubEnabled(TestAndroidEnterpriseOnly):
    """Tests for AndroidEnterprise.pubsub_enabled method."""

    def test_returns_false_when_token_not_set(self, set_amapi_service_account_file, settings):
        """Returns False immediately (no API call) when ANDROID_ENTERPRISE_PUBSUB_TOKEN is unset."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        active_mdm = AndroidEnterprise()
        assert active_mdm.pubsub_enabled() is False

    def test_returns_true_when_token_set_and_topic_exists(
        self, set_amapi_service_account_file, monkeypatch, settings
    ):
        """Returns True when the token is configured and topics.get succeeds (200)."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "secret"
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.get", {"name": active_mdm.pubsub_topic}),
                prefix="pubsub.projects.",
            ),
        )
        assert active_mdm.pubsub_enabled() is True

    def test_returns_false_when_token_set_and_topic_not_found(
        self, set_amapi_service_account_file, monkeypatch, settings
    ):
        """Returns False when the token is configured but topics.get returns 404."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "secret"
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.get", status_code=404),
                prefix="pubsub.projects.",
            ),
        )
        assert active_mdm.pubsub_enabled() is False

    def test_reraises_other_http_errors(
        self, set_amapi_service_account_file, monkeypatch, settings
    ):
        """Re-raises non-404 HttpErrors (e.g., 403 permission denied) when the token is set."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "secret"
        active_mdm = AndroidEnterprise()
        monkeypatch.setattr(
            active_mdm.pubsub_api,
            "_requestBuilder",
            self.get_mock_request_builder(
                MockAPIResponse("topics.get", status_code=403),
                prefix="pubsub.projects.",
            ),
        )
        with pytest.raises(HttpError):
            active_mdm.pubsub_enabled()
