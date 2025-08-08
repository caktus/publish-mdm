import json
import pytest
import faker
from requests import Response
from requests.exceptions import HTTPError
from requests.sessions import Session

from apps.mdm import tasks
from apps.mdm.models import Device
from apps.publish_mdm.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from tests.publish_mdm.factories import AppUserFactory

from .factories import DeviceFactory, FleetFactory

fake = faker.Faker()


@pytest.mark.django_db
class TestTasks:
    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    @pytest.fixture
    def devices(self, fleet):
        """Create 6 Devices, one with a blank device_id."""
        return DeviceFactory.create_batch(5, fleet=fleet) + [
            DeviceFactory(fleet=fleet, device_id="")
        ]

    def get_fake_device_data(self):
        data = {
            "last_sync_timestamp": int(fake.past_datetime().timestamp()),
            "manufacturer": fake.company(),
            "enrollment_type": fake.random_element(["fully_managed", "work_profile"]),
            "os_version": fake.android_platform_token(),
            "battery_level": fake.pyint(0, 100),
        }
        if fake.pybool():
            data["geolocation_positions"] = [
                {
                    "latitude": float(fake.latitude()),
                    "longitude": float(fake.longitude()),
                }
                for _ in range(2)
            ]
        return data

    def get_raw_mdm_device(self, device):
        """Create data for the Device.raw_mdm_device field based on other fields' values."""
        return {
            "id": device.device_id,
            "serial_number": device.serial_number,
            "name": device.name,
            "nickname": device.name,
            "user_id": f"user{device.device_id}",
            **self.get_fake_device_data(),
        }

    @pytest.fixture
    def devices_response(self, devices):
        """Mock response for a TinyMDM device listing API request."""
        return {
            "results": [
                # Existing devices, which should be updated in the DB
                {
                    "id": device.device_id,
                    "serial_number": (
                        f"updated-{device.serial_number}"
                        if device.device_id
                        else device.serial_number
                    ),
                    "name": f"updated-name-{device.name}",
                    "nickname": f"updated-nickname-{device.name}",
                    "user_id": f"user{device.device_id}",
                    **self.get_fake_device_data(),
                }
                for device in devices
            ]
            + [
                # New devices, which should be created in the DB
                self.get_raw_mdm_device(device)
                for device in DeviceFactory.build_batch(4)
            ]
        }

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
        return FleetFactory.create_batch(2) + [fleet]

    def test_get_tinymdm_session_without_env_variables(self):
        """Ensure get_tinymdm_session() returns None if the environment variables
        for TinyMDM API credentials are not set.
        """
        assert tasks.get_tinymdm_session() is None

    def test_get_tinymdm_session_with_env_variables(self, set_tinymdm_env_vars):
        """Ensure get_tinymdm_session() returns a requests Session object if the
        environment variables for TinyMDM API credentials are set.
        """
        assert isinstance(tasks.get_tinymdm_session(), Session)

    @pytest.mark.parametrize("device_in_different_fleet", [False, True])
    def test_pull_devices(
        self,
        fleet,
        requests_mock,
        devices_response,
        fleets,
        devices,
        set_tinymdm_env_vars,
        device_in_different_fleet,
    ):
        """Ensures calling pull_devices() updates and creates Devices as expected."""
        if device_in_different_fleet:
            # Change the fleet of one of the devices such that it does not match
            # the API response. The device should still be updated instead of
            # attempting to create a new Device which leads to an IntegrityError.
            devices[0].fleet = fleets[0]
            devices[0].save()

        requests_mock.get("https://www.tinymdm.net/api/v1/devices", json=devices_response)
        apps = {}
        for device in devices_response["results"]:
            apps[device["id"]] = [
                {
                    "package_name": f"org.{fake.word()}.{fake.word()}",
                    "app_name": fake.sentence(),
                    "version_code": fake.pyint(),
                    "version_name": fake.word(),
                }
                for _ in range(3)
            ]
            requests_mock.get(
                f"https://www.tinymdm.net/api/v1/devices/{device['id']}/apps",
                json={
                    "results": apps[device["id"]],
                },
            )

        session = tasks.get_tinymdm_session()
        tasks.pull_devices(session, fleet)

        # There should be 9 or 10 devices in the fleet now
        if device_in_different_fleet:
            assert fleet.devices.count() == 9
        else:
            assert fleet.devices.count() == 10
        # 4 devices are new
        assert fleet.devices.exclude(id__in=[i.id for i in devices]).count() == 4
        # Ensure the devices have the expected data from the API response
        db_devices = Device.objects.in_bulk(field_name="device_id")
        for device in devices_response["results"]:
            db_device = db_devices[device["id"]]
            assert db_device.serial_number == device["serial_number"]
            assert db_device.name == device["nickname"] or device["name"]
            assert db_device.raw_mdm_device == device

            # Ensure a snapshot has been saved with the expected data
            snapshot = db_device.latest_snapshot
            assert snapshot is not None
            assert snapshot.mdm_device == db_device
            assert snapshot.raw_mdm_device == device
            assert snapshot.serial_number == device["serial_number"]
            assert snapshot.name == device["nickname"] or device["name"]
            assert snapshot.last_sync.timestamp() == device["last_sync_timestamp"]

            for key in ("manufacturer", "os_version", "battery_level", "enrollment_type"):
                assert getattr(snapshot, key) == device[key]

            geolocation_positions = device.get("geolocation_positions")
            if geolocation_positions:
                assert snapshot.latitude == geolocation_positions[-1]["latitude"]
                assert snapshot.longitude == geolocation_positions[-1]["longitude"]

            # Ensure the apps have been saved with the expected data
            assert {tuple(i.values()) for i in apps[device["id"]]} == set(
                snapshot.apps.values_list(
                    "package_name", "app_name", "version_code", "version_name"
                )
            )

    @pytest.mark.parametrize("device", [False, True], indirect=True)
    def test_push_device_config(self, device, requests_mock, set_tinymdm_env_vars):
        """Ensures push_device_config() makes the expected API requests."""
        user_update_request = requests_mock.put(
            f"https://www.tinymdm.net/api/v1/users/{device.raw_mdm_device['user_id']}"
        )
        message_request = requests_mock.post("https://www.tinymdm.net/api/v1/actions/message")
        add_to_group_request = requests_mock.post(
            f"https://www.tinymdm.net/api/v1/groups/{device.fleet.mdm_group_id}/users/{device.raw_mdm_device['user_id']}"
        )
        session = tasks.get_tinymdm_session()
        tasks.push_device_config(session, device)

        if device.app_user_name:
            # Get QR code data from the AppUser
            app_user = device.fleet.project.app_users.get(name=device.app_user_name)
            qr_code_data = json.dumps(app_user.qr_code_data, separators=(",", ":"))
        else:
            qr_code_data = ""

        assert user_update_request.called_once
        assert user_update_request.last_request.json() == {
            "name": f"{device.app_user_name} - {device.device_id}",
            "custom_field_1": qr_code_data,
        }
        assert add_to_group_request.called_once
        assert not add_to_group_request.last_request.body
        if device.app_user_name:
            assert message_request.called_once
            assert message_request.last_request.json() == {
                "message": (
                    f"This device has been configured for App User {device.app_user_name}.\n\n"
                    "Please close and re-open the Collect app to see the new project.\n\n"
                    "In case of any issues, please open the TinyMDM app and reload the policy "
                    "or restart the device."
                ),
                "title": "Project Update",
                "devices": [device.device_id],
            }
        else:
            assert not message_request.called

    def test_push_device_config_new_device(self, fleet, set_tinymdm_env_vars):
        """Ensures calling push_device_config() with a Device whose `raw_mdm_device` field
        is not set does not raise a TypeError."""
        device = DeviceFactory.build(fleet=fleet, raw_mdm_device=None)
        device.save(push_to_mdm=False)
        session = tasks.get_tinymdm_session()
        tasks.push_device_config(session, device)

    def test_sync_fleet(self, fleet, devices, mocker, set_tinymdm_env_vars):
        """Ensure calling sync_fleet() calls pull_devices() for the specified fleet
        and push_device_config() for the fleet's devices whose app_user_name field is set.
        """
        # Make app_user_name blank for some devices
        fleet.devices.filter(id__in=[d.id for d in devices][:3]).update(app_user_name="")
        devices_to_push = fleet.devices.exclude(app_user_name="")

        mock_pull_devices = mocker.patch("apps.mdm.tasks.pull_devices")
        mock_push_device_config = mocker.patch("apps.mdm.tasks.push_device_config")
        session = tasks.get_tinymdm_session()
        tasks.sync_fleet(session, fleet)

        mock_pull_devices.assert_called_once()
        # push_device_config should be called only for the devices where
        # app_user_name is set
        mock_push_device_config.assert_has_calls(
            [mocker.call(session=session, device=device) for device in devices_to_push],
            any_order=True,
        )
        assert mock_push_device_config.call_count == len(devices_to_push)

    def test_sync_fleet_with_push_config_false(self, fleet, devices, mocker, set_tinymdm_env_vars):
        """Ensure calling sync_fleet() with push_config=False calls pull_devices()
        for the specified fleet but does not call push_device_config() for any device.
        """
        mock_pull_devices = mocker.patch("apps.mdm.tasks.pull_devices")
        mock_push_device_config = mocker.patch("apps.mdm.tasks.push_device_config")
        session = tasks.get_tinymdm_session()
        tasks.sync_fleet(session, fleet, push_config=False)

        mock_pull_devices.assert_called_once()
        mock_push_device_config.assert_not_called()

    def test_sync_fleets(self, fleets, mocker, set_tinymdm_env_vars):
        """Ensure calling sync_fleets() calls sync_fleet() for all fleets."""
        mock_sync_fleet = mocker.patch("apps.mdm.tasks.sync_fleet")
        tasks.sync_fleets()

        assert mock_sync_fleet.call_count == len(fleets)
        for call in mock_sync_fleet.call_list_args:
            assert isinstance(call.args[0], Session)
            assert call.args[1] in fleets

    def test_create_group(self, requests_mock, set_tinymdm_env_vars):
        """Ensures create_group() makes the expected API request and updates
        the fleet's mdm_group_id field if successful.
        """
        fleet = FleetFactory.build(mdm_group_id=None)
        json_response = {
            "id": fake.pystr(),
            "name": fleet.group_name,
            "policy_id": None,
            "creation_date": "2020-09-12 09:45:12",
            "modification_date": "2020-08-05 15:57:25",
        }
        create_group_request = requests_mock.post(
            "https://www.tinymdm.net/api/v1/groups", json=json_response, status_code=201
        )
        session = tasks.get_tinymdm_session()
        tasks.create_group(session, fleet)

        assert create_group_request.called_once
        assert create_group_request.last_request.json() == {
            "name": fleet.group_name,
        }
        assert fleet.mdm_group_id == json_response["id"]

    def test_add_group_to_policy(self, fleet, requests_mock, set_tinymdm_env_vars):
        """Ensures add_group_to_policy() makes the expected API request."""
        add_group_to_policy_request = requests_mock.post(
            f"https://www.tinymdm.net/api/v1/policies/{fleet.policy.policy_id}/members/{fleet.mdm_group_id}",
            status_code=204,
        )
        session = tasks.get_tinymdm_session()
        tasks.add_group_to_policy(session, fleet)

        assert add_group_to_policy_request.called_once
        assert not add_group_to_policy_request.last_request.body

    def test_get_enrollment_qr_code(self, fleet, requests_mock, set_tinymdm_env_vars):
        """Ensures get_enrollment_qr_code() makes the expected API request and updates
        the fleet's enroll_qr_code field if successful.
        """
        fleet = FleetFactory.build(enroll_qr_code=None)
        json_response = {
            "enrollment_qr_code_url": "https://www.tinymdm.net/qr_code.php?data=12345",
        }
        get_enrollment_qr_code_request = requests_mock.get(
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/enrollment_qr_code",
            json=json_response,
        )
        qr_code = fake.image()
        download_qr_code_request = requests_mock.get(
            json_response["enrollment_qr_code_url"],
            content=qr_code,
        )
        session = tasks.get_tinymdm_session()
        tasks.get_enrollment_qr_code(session, fleet)

        assert get_enrollment_qr_code_request.called_once
        assert download_qr_code_request.called_once
        assert fleet.enroll_qr_code is not None
        assert fleet.enroll_qr_code.read() == qr_code

    def test_delete_group_successful(self, fleet, requests_mock, set_tinymdm_env_vars):
        """Ensure deleting a group succeeds if it's not linked to devices in the
        database and in TinyMDM.
        """
        get_group_devices_request = requests_mock.get(
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/devices",
            json={"results": []},
        )
        delete_device_request = requests_mock.delete(
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}", status_code=204
        )
        session = tasks.get_tinymdm_session()
        result = tasks.delete_group(session, fleet)

        assert result
        assert get_group_devices_request.called_once
        assert delete_device_request.called_once

    def test_delete_group_fails_if_devices_in_db(self, fleet, requests_mock, set_tinymdm_env_vars):
        """Ensure deleting a group fails if it's linked to devices in the database."""
        DeviceFactory(fleet=fleet)
        session = tasks.get_tinymdm_session()
        result = tasks.delete_group(session, fleet)

        assert not result

    def test_delete_group_fails_if_devices_in_tinymdm(
        self, fleet, requests_mock, set_tinymdm_env_vars
    ):
        """Ensure deleting a group fails if it's linked to devices in TinyMDM."""
        get_group_devices_request = requests_mock.get(
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/devices",
            json={"results": [{"id": "somedevice"}]},
        )
        session = tasks.get_tinymdm_session()
        result = tasks.delete_group(session, fleet)

        assert not result
        assert get_group_devices_request.called_once

    def test_delete_group_succeeds_if_does_not_exist_in_tinymdm(
        self, fleet, requests_mock, set_tinymdm_env_vars
    ):
        """Ensure delete_group() returns True if a group with the Fleet's mdm_group_id
        does not exist in TinyMDM.
        """
        get_group_devices_request = requests_mock.get(
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/devices", status_code=404
        )
        session = tasks.get_tinymdm_session()
        result = tasks.delete_group(session, fleet)

        assert result
        assert get_group_devices_request.called_once

    def test_create_user(self, fleet, requests_mock, set_tinymdm_env_vars):
        """Ensures create_user() makes the expected API requests to create a user
        and add them to a group.
        """
        name = fake.name()
        email = fake.email()
        user_response = {
            "id": fake.pystr(),
            "name": name,
            "email": email,
            "enrollment_token": fake.pystr(),
            "is_anonymous": False,
            "policy_id": None,
            "group_id": None,
        }
        create_user_request = requests_mock.post(
            "https://www.tinymdm.net/api/v1/users", json=user_response
        )
        add_to_group_request = requests_mock.post(
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/users/{user_response['id']}"
        )
        session = tasks.get_tinymdm_session()
        tasks.create_user(session, name, email, fleet)

        assert create_user_request.called_once
        assert create_user_request.last_request.json() == {
            "name": name,
            "is_anonymous": False,
            "email": email,
            "send_email": True,
        }
        assert add_to_group_request.called_once
        assert not add_to_group_request.last_request.body

    @pytest.mark.parametrize("api_error", [(500, None), (499, {"error": {"message": "Reason"}})])
    @pytest.mark.parametrize("raise_for_status", [None, True, False])
    def test_request(self, requests_mock, set_tinymdm_env_vars, api_error, raise_for_status):
        """Test handling of API errors in the request() function."""
        url = "https://www.tinymdm.net/api/v1/some-endpoint"
        status_code, response_json = api_error
        requests_mock.get(url, status_code=status_code, json=response_json)
        session = tasks.get_tinymdm_session()
        kwargs = {}
        if raise_for_status is not None:
            kwargs["raise_for_status"] = raise_for_status
        expected_api_error = tasks.APIError(
            method="GET", url=url, status_code=status_code, error_data=response_json
        )

        if raise_for_status or raise_for_status is None:
            # Should raise an exception with its api_error attribute set to an APIError object
            with pytest.raises(HTTPError) as exc:
                tasks.request(session, "GET", url, **kwargs)
            assert exc.value.api_error == expected_api_error
        else:
            response = tasks.request(session, "GET", url, **kwargs)
            assert isinstance(response, Response)
            assert expected_api_error in session.api_errors
            if response_json is not None:
                assert response.json() == response_json

    def test_check_license_limit(self, requests_mock, set_tinymdm_env_vars):
        """Ensures check_license_limit() makes the expected API requests and
        returns a tuple with the devices limit and the number of enrolled devices.
        """
        limit = 10
        enrolled = 8
        account_info_request = requests_mock.get(
            "https://www.tinymdm.net/api/v1/enterprise/info", json={"paid_licence": limit}
        )
        devices_request = requests_mock.get(
            "https://www.tinymdm.net/api/v1/devices",
            json={"count": 8},
        )
        session = tasks.get_tinymdm_session()
        result = tasks.check_license_limit(session)

        assert account_info_request.called_once
        assert devices_request.called_once
        assert result == (limit, enrolled)

    @pytest.mark.parametrize("status_code", (429, 500))
    @pytest.mark.parametrize("method", ("GET", "POST"))
    def test_max_request_retries(self, responses, set_tinymdm_env_vars, method, status_code):
        """Ensure POSTs are retried only on 429 responses. GETs (and others that are retried
        by default) will be retried on 429, 500, 502, 503, or 504 responses.
        """
        url = "https://www.tinymdm.net/api/v1/some-endpoint"
        responses.add(method, url, status=status_code)
        session = tasks.get_tinymdm_session()
        response = tasks.request(session, method, url, raise_for_status=False)

        if method == "POST" and status_code != 429:
            # No retries
            expected_request_count = 1
        else:
            # Expect 6 total requests: initial request + 5 retries
            expected_request_count = 6

        assert responses.assert_call_count(url, expected_request_count)
        assert response.status_code == status_code

    @pytest.mark.parametrize("status_code", (429, 500))
    @pytest.mark.parametrize("method", ("GET", "POST"))
    def test_request_retries_until_success(
        self, responses, set_tinymdm_env_vars, method, status_code
    ):
        """Like test_max_request_retries above, but we eventually get a successful
        response before reaching the max allowed requests.
        """
        url = "https://www.tinymdm.net/api/v1/some-endpoint"
        # The third request returns a 200 response
        responses.add(method, url, status=status_code)
        responses.add(method, url, status=status_code)
        responses.add(method, url, status=200)
        session = tasks.get_tinymdm_session()
        response = tasks.request(session, method, url, raise_for_status=False)

        if method == "POST" and status_code != 429:
            # No retries
            responses.assert_call_count(url, 1)
            assert response.status_code == status_code
            responses.assert_all_requests_are_fired = False
        else:
            responses.assert_call_count(url, 3)
            assert response.status_code == 200
