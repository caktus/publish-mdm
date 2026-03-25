import datetime as dt
import json
from collections import namedtuple
from unittest.mock import MagicMock, PropertyMock

import faker
import httplib2
import pytest
from django.contrib.sites.models import Site
from googleapiclient.errors import HttpError
from googleapiclient.http import RequestMockBuilder

from apps.mdm.mdms import AndroidEnterprise, MDMAPIError
from apps.mdm.mdms.android_enterprise import (
    ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT,
    PUBSUB_RESOURCE_NAME,
)
from apps.mdm.models import Device
from apps.publish_mdm.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from tests.mdm import TestAndroidEnterpriseOnly
from tests.publish_mdm.factories import AppUserFactory, ProjectFactory

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
    def fleet(self):
        return FleetFactory()

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
                qr_code_data=DEFAULT_COLLECT_SETTINGS,
            )
        else:
            device.app_user_name = ""
        device.save()
        return device

    @pytest.fixture
    def fleets(self, fleet):
        return [*FleetFactory.create_batch(2), fleet]

    def test_env_variables_not_set(self):
        """Ensure AndroidEnterprise.is_configured property returns False if the
        environment variables for Android Enterprise API credentials are not set.
        """
        active_mdm = AndroidEnterprise()
        assert not active_mdm.is_configured
        assert not active_mdm
        assert not active_mdm.api

    def test_env_variables_set(self, set_mdm_env_vars):
        """Ensure AndroidEnterprise.is_configured property returns True if the
        environment variables for Android Enterprise API credentials are set.
        """
        active_mdm = AndroidEnterprise()
        assert active_mdm.is_configured
        assert active_mdm
        assert active_mdm.api
        assert active_mdm.enterprise_name == f"enterprises/{active_mdm.enterprise_id}"

    def get_mock_request_builder(self, *responses):
        """Creates a RequestMockBuilder that can be used to mock API responses
        in the Google API Client. Takes MockAPIResponse objects as args, where
        the `method_id` should be without the 'androidmanagement.enterprises.'
        prefix.
        """
        responses_dict = {}
        for response in responses:
            if response.content:
                response_content = json.dumps(response.content)
            else:
                response_content = ""
            if response.status_code:
                response_obj = httplib2.Response({"status": response.status_code})
            else:
                # None results in a 200 response
                response_obj = None
            value = [response_obj, response_content.encode()]
            if response.expected_request_body is not None:
                # Will raise an error if the actual request body does not match exactly
                value.append(response.expected_request_body)
            responses_dict[f"androidmanagement.enterprises.{response.method_id}"] = value
        return RequestMockBuilder(responses_dict, check_unexpected=True)

    @pytest.mark.parametrize("with_default_app_user", [False, True])
    def test_pull_devices(
        self,
        fleet,
        devices_response,
        fleets,
        devices,
        set_mdm_env_vars,
        monkeypatch,
        with_default_app_user,
    ):
        """Ensures calling pull_devices() updates and creates Devices as expected."""
        if with_default_app_user:
            default_app_user = AppUserFactory(project=fleet.project)
            fleet.default_app_user = default_app_user
            fleet.save()

        active_mdm = AndroidEnterprise()

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

    def test_get_devices(self, mocker, monkeypatch, set_mdm_env_vars):
        """Ensures calling get_devices() downloads device data as expected."""
        active_mdm = AndroidEnterprise()
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

    def test_sync_fleet(self, fleet, devices, mocker, set_mdm_env_vars):
        """Ensure calling sync_fleet() calls pull_devices() for the specified fleet
        and push_device_config() for the fleet's devices whose app_user_name field is set.
        """
        # Make app_user_name blank for some devices
        fleet.devices.filter(id__in=[d.id for d in devices][:3]).update(app_user_name="")
        devices_to_push = fleet.devices.exclude(app_user_name="")

        active_mdm = AndroidEnterprise()
        mock_pull_devices = mocker.patch.object(active_mdm, "pull_devices")
        mock_push_device_config = mocker.patch.object(active_mdm, "push_device_config")
        active_mdm.sync_fleet(fleet)

        mock_pull_devices.assert_called_once()
        # push_device_config should be called only for the devices where
        # app_user_name is set
        mock_push_device_config.assert_has_calls(
            [mocker.call(device=device) for device in devices_to_push],
            any_order=True,
        )
        assert mock_push_device_config.call_count == len(devices_to_push)

    def test_sync_fleet_with_push_config_false(self, fleet, devices, mocker, set_mdm_env_vars):
        """Ensure calling sync_fleet() with push_config=False calls pull_devices()
        for the specified fleet but does not call push_device_config() for any device.
        """
        active_mdm = AndroidEnterprise()
        mock_pull_devices = mocker.patch.object(active_mdm, "pull_devices")
        mock_push_device_config = mocker.patch.object(active_mdm, "push_device_config")
        active_mdm.sync_fleet(fleet, push_config=False)

        mock_pull_devices.assert_called_once()
        mock_push_device_config.assert_not_called()

    def test_sync_fleets(self, fleets, mocker, set_mdm_env_vars):
        """Ensure calling sync_fleets() calls sync_fleet() for all fleets."""
        active_mdm = AndroidEnterprise()
        mock_sync_fleet = mocker.patch.object(active_mdm, "sync_fleet")
        active_mdm.sync_fleets()

        assert mock_sync_fleet.call_count == len(fleets)
        for call in mock_sync_fleet.call_list_args:
            assert call.args[0] in fleets

    @pytest.mark.parametrize("new_fleet", [True, False])
    def test_get_enrollment_qr_code(self, set_mdm_env_vars, monkeypatch, new_fleet):
        """Ensures get_enrollment_qr_code() makes the expected API request and updates
        the fleet's enroll_qr_code, enroll_token_expires_at, and enroll_token_value
        if successful.
        """
        active_mdm = AndroidEnterprise()
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
    def test_execute(self, monkeypatch, set_mdm_env_vars, api_error, raise_exception):
        """Test handling of API errors in the execute() function."""
        active_mdm = AndroidEnterprise()
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

    def test_create_or_update_policy(self, set_mdm_env_vars, monkeypatch, mocker):
        """Ensure create_or_update_policy() makes the expected API request."""
        active_mdm = AndroidEnterprise()
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

    @pytest.mark.parametrize("current_device_policy", ["own", "base", "other_fleet"])
    def test_push_device_config(
        self, fleet, set_mdm_env_vars, monkeypatch, mocker, current_device_policy
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
        active_mdm = AndroidEnterprise()
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

    def test_push_device_config_no_api_requests(self, fleet, set_mdm_env_vars, mocker):
        """Ensures push_device_config() does not make any API requests if
        Device.raw_mdm_device is not set (Device hasn't been pulled before)
        or policy data is not available.
        """
        device = DeviceFactory(fleet=fleet)
        active_mdm = AndroidEnterprise()
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

    # ------------------------------------------------------------------
    # configure_pubsub helpers
    # ------------------------------------------------------------------

    @pytest.fixture
    def mock_pubsub_api(self, mocker, set_mdm_env_vars):
        """Return a MagicMock wired up as the pubsub_api on a fresh AndroidEnterprise instance.

        Also mocks ``project_id``, ``pubsub_topic``, and ``pubsub_subscription``
        so that tests do not depend on real service-account key file content.
        """
        active_mdm = AndroidEnterprise()
        mock_api = MagicMock()
        mocker.patch.object(
            type(active_mdm), "pubsub_api", new_callable=PropertyMock, return_value=mock_api
        )
        mocker.patch.object(
            type(active_mdm),
            "project_id",
            new_callable=PropertyMock,
            return_value="my-project",
        )
        mocker.patch.object(
            type(active_mdm),
            "pubsub_topic",
            new_callable=PropertyMock,
            return_value="projects/my-project/topics/publish-mdm",
        )
        mocker.patch.object(
            type(active_mdm),
            "pubsub_subscription",
            new_callable=PropertyMock,
            return_value="projects/my-project/subscriptions/publish-mdm",
        )
        return active_mdm, mock_api

    def test_pubsub_topic_and_subscription_names(self, mocker, set_mdm_env_vars):
        """pubsub_topic and pubsub_subscription are derived from the project_id."""
        active_mdm = AndroidEnterprise()
        mocker.patch.object(
            type(active_mdm),
            "project_id",
            new_callable=PropertyMock,
            return_value="test-project",
        )
        assert active_mdm.pubsub_topic == f"projects/test-project/topics/{PUBSUB_RESOURCE_NAME}"
        assert (
            active_mdm.pubsub_subscription
            == f"projects/test-project/subscriptions/{PUBSUB_RESOURCE_NAME}"
        )

    def test_ensure_pubsub_topic_creates_topic(self, mock_pubsub_api):
        """_ensure_pubsub_topic() calls topics.create when the topic does not exist."""
        active_mdm, mock_api = mock_pubsub_api
        topic = "projects/my-project/topics/my-topic"
        active_mdm._ensure_pubsub_topic(topic)
        mock_api.projects().topics().create.assert_called_once_with(name=topic, body={})
        mock_api.projects().topics().create().execute.assert_called_once()

    def test_ensure_pubsub_topic_already_exists(self, mock_pubsub_api):
        """_ensure_pubsub_topic() silently ignores a 409 Conflict response."""
        active_mdm, mock_api = mock_pubsub_api
        mock_api.projects().topics().create().execute.side_effect = HttpError(
            httplib2.Response({"status": 409}), b"already exists"
        )
        topic = "projects/my-project/topics/my-topic"
        # Should not raise
        active_mdm._ensure_pubsub_topic(topic)

    def test_ensure_pubsub_topic_reraises_other_errors(self, mock_pubsub_api):
        """_ensure_pubsub_topic() re-raises non-409 HttpErrors."""
        active_mdm, mock_api = mock_pubsub_api
        mock_api.projects().topics().create().execute.side_effect = HttpError(
            httplib2.Response({"status": 403}), b"permission denied"
        )
        with pytest.raises(HttpError):
            active_mdm._ensure_pubsub_topic("projects/my-project/topics/my-topic")

    def test_grant_pubsub_publisher_adds_binding(self, mock_pubsub_api):
        """_grant_pubsub_publisher() adds the ADP service account to the IAM policy."""
        active_mdm, mock_api = mock_pubsub_api
        topic = "projects/my-project/topics/my-topic"
        # No existing bindings
        mock_api.projects().topics().getIamPolicy().execute.return_value = {"bindings": []}
        active_mdm._grant_pubsub_publisher(topic)
        # setIamPolicy should have been called with the new binding
        call_args = mock_api.projects().topics().setIamPolicy.call_args
        policy = call_args.kwargs["body"]["policy"]
        expected_member = f"serviceAccount:{ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT}"
        assert any(
            b["role"] == "roles/pubsub.publisher" and expected_member in b["members"]
            for b in policy["bindings"]
        )

    def test_grant_pubsub_publisher_already_granted(self, mock_pubsub_api):
        """_grant_pubsub_publisher() skips setIamPolicy when ADP already has publish rights."""
        active_mdm, mock_api = mock_pubsub_api
        topic = "projects/my-project/topics/my-topic"
        member = f"serviceAccount:{ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT}"
        mock_api.projects().topics().getIamPolicy().execute.return_value = {
            "bindings": [{"role": "roles/pubsub.publisher", "members": [member]}]
        }
        active_mdm._grant_pubsub_publisher(topic)
        mock_api.projects().topics().setIamPolicy.assert_not_called()

    def test_grant_pubsub_publisher_get_iam_policy_error(self, mock_pubsub_api):
        """_grant_pubsub_publisher() re-raises errors from getIamPolicy."""
        active_mdm, mock_api = mock_pubsub_api
        mock_api.projects().topics().getIamPolicy().execute.side_effect = HttpError(
            httplib2.Response({"status": 403}), b"permission denied"
        )
        with pytest.raises(HttpError):
            active_mdm._grant_pubsub_publisher("projects/my-project/topics/my-topic")
        mock_api.projects().topics().setIamPolicy.assert_not_called()

    def test_grant_pubsub_publisher_set_iam_policy_error(self, mock_pubsub_api):
        """_grant_pubsub_publisher() re-raises errors from setIamPolicy."""
        active_mdm, mock_api = mock_pubsub_api
        mock_api.projects().topics().getIamPolicy().execute.return_value = {"bindings": []}
        mock_api.projects().topics().setIamPolicy().execute.side_effect = HttpError(
            httplib2.Response({"status": 403}), b"permission denied"
        )
        with pytest.raises(HttpError):
            active_mdm._grant_pubsub_publisher("projects/my-project/topics/my-topic")

    def test_ensure_pubsub_subscription_creates_subscription(self, mock_pubsub_api):
        """_ensure_pubsub_subscription() calls subscriptions.create with push config."""
        active_mdm, mock_api = mock_pubsub_api
        topic = "projects/my-project/topics/my-topic"
        sub = "projects/my-project/subscriptions/my-topic"
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/"
        active_mdm._ensure_pubsub_subscription(topic, sub, push_endpoint)
        mock_api.projects().subscriptions().create.assert_called_once_with(
            name=sub,
            body={"topic": topic, "pushConfig": {"pushEndpoint": push_endpoint}},
        )

    def test_ensure_pubsub_subscription_already_exists(self, mock_pubsub_api):
        """_ensure_pubsub_subscription() calls modifyPushConfig on a 409 Conflict response."""
        active_mdm, mock_api = mock_pubsub_api
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/"
        sub = "projects/p/subscriptions/t"
        mock_api.projects().subscriptions().create().execute.side_effect = HttpError(
            httplib2.Response({"status": 409}), b"already exists"
        )
        # Should not raise
        active_mdm._ensure_pubsub_subscription("projects/p/topics/t", sub, push_endpoint)
        mock_api.projects().subscriptions().modifyPushConfig.assert_called_once_with(
            subscription=sub,
            body={"pushConfig": {"pushEndpoint": push_endpoint}},
        )

    def test_configure_pubsub_full_flow(self, mock_pubsub_api, monkeypatch):
        """configure_pubsub() calls all setup steps and patches the enterprise."""
        active_mdm, mock_api = mock_pubsub_api
        expected_topic = active_mdm.pubsub_topic
        expected_sub = active_mdm.pubsub_subscription
        push_endpoint = "https://example.com/mdm/api/amapi/notifications/?token=secret"

        monkeypatch.setattr(active_mdm, "_build_push_endpoint", lambda domain=None: push_endpoint)
        # Successful IAM fetch
        mock_api.projects().topics().getIamPolicy().execute.return_value = {"bindings": []}

        enterprise_patch_result = {
            "name": active_mdm.enterprise_name,
            "pubsubTopic": expected_topic,
            "enabledNotificationTypes": ["ENROLLMENT", "STATUS_REPORT"],
        }
        monkeypatch.setattr(
            active_mdm,
            "execute",
            lambda resource_method: enterprise_patch_result,
        )

        result = active_mdm.configure_pubsub(push_endpoint_domain="example.com")
        assert result == enterprise_patch_result
        # Verify topic was created with the auto-generated name
        mock_api.projects().topics().create.assert_called_once_with(name=expected_topic, body={})
        # Verify subscription was created with push endpoint
        mock_api.projects().subscriptions().create.assert_called_once_with(
            name=expected_sub,
            body={"topic": expected_topic, "pushConfig": {"pushEndpoint": push_endpoint}},
        )

    @pytest.mark.django_db
    def test_build_push_endpoint(self, mock_pubsub_api, settings):
        """_build_push_endpoint() returns the correct URL using the Site domain and token."""
        active_mdm, _ = mock_pubsub_api
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "mysecret"
        Site.objects.filter(pk=settings.SITE_ID).update(domain="app.example.com")
        endpoint = active_mdm._build_push_endpoint()
        assert endpoint == "https://app.example.com/mdm/api/amapi/notifications/?token=mysecret"

    @pytest.mark.django_db
    def test_build_push_endpoint_with_domain(self, mock_pubsub_api, settings):
        """_build_push_endpoint() uses the supplied domain instead of the Site domain."""
        active_mdm, _ = mock_pubsub_api
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "mysecret"
        endpoint = active_mdm._build_push_endpoint(domain="override.example.com")
        assert (
            endpoint == "https://override.example.com/mdm/api/amapi/notifications/?token=mysecret"
        )

    @pytest.mark.django_db
    def test_build_push_endpoint_raises_when_token_not_set(self, mock_pubsub_api, settings):
        """_build_push_endpoint() raises ValueError when ANDROID_ENTERPRISE_PUBSUB_TOKEN is unset."""
        active_mdm, _ = mock_pubsub_api
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        with pytest.raises(ValueError, match="ANDROID_ENTERPRISE_PUBSUB_TOKEN"):
            active_mdm._build_push_endpoint()
