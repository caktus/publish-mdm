import pytest
from django.conf import settings
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils.html import linebreaks
from import_export.tmp_storages import TempFolderStorage
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from apps.mdm.import_export import DeviceResource
from apps.mdm.mdms import get_active_mdm_class
from apps.mdm.models import Device, Fleet
from tests.mdm import TestAllMDMs
from tests.users.factories import UserFactory

from .factories import DeviceFactory, FleetFactory, PolicyFactory


@pytest.mark.django_db
class TestAdmin(TestAllMDMs):
    @pytest.fixture
    def user(self, client):
        user = UserFactory(is_staff=True, is_superuser=True)
        user.save()
        client.force_login(user=user)
        return user


class TestDeviceAdmin(TestAdmin):
    @pytest.fixture(autouse=True)
    def disable_dagster(self, settings):
        """Disable Dagster queuing for these tests."""
        settings.DAGSTER_URL = None

    @pytest.fixture
    def dataset(self, organization):
        # Create 3 Devices with the same Fleet
        fleet = FleetFactory(organization=organization)
        DeviceFactory.create_batch(3, fleet=fleet)
        # Create a Dataset in the format expected by the import functionality
        return DeviceResource().export()

    def check_import(self, client, dataset, expected_app_user_names):
        # Create a temp file as expected for the import confirmation step
        import_format = settings.IMPORT_EXPORT_FORMATS[0]()
        format_name = import_format.get_title()
        import_file_data = dataset.export(format_name)
        tmp_storage = TempFolderStorage(
            encoding="utf-8-sig",
            read_mode=import_format.get_read_mode(),
        )
        tmp_storage.save(import_file_data.encode())
        # Submit a form for confirming the import
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": f"test.{format_name}",
            "push_method": "all",
            "format": 0,
            "resource": "",
        }
        response = client.post(reverse("admin:mdm_device_process_import"), data=data, follow=True)
        assert response.status_code == 200
        assert response.redirect_chain == [(reverse("admin:mdm_device_changelist"), 302)]
        for id, app_user_name in expected_app_user_names.items():
            assert Device.objects.get(id=id).app_user_name == app_user_name
        return response

    def test_confirm_import_with_no_errors(self, client, user, dataset, mocker, organization):
        """Happy path: confirming an import and no errors occur when saving changes."""
        # Change the app_user_name on the first 2 devices
        expected_app_user_names = {}
        for index, row in enumerate(dataset[:2]):
            row = list(row)
            row[3] += "_edited"
            dataset[index] = row
            expected_app_user_names[row[0]] = row[3]
        # Add one new device
        new_device = DeviceFactory.build(fleet__organization=organization)
        dataset.append(
            [
                None,
                dataset[0][1],
                new_device.serial_number,
                new_device.app_user_name,
                new_device.device_id,
            ]
        )
        mocker.patch("apps.mdm.import_export.trigger_dagster_job")
        response = self.check_import(client, dataset, expected_app_user_names)
        # We should now have 4 Devices: 3 existing devices + 1 new device
        assert Device.objects.count() == 4
        assert (
            "Import finished: 1 new, 2 updated, 0 deleted and 1 skipped devices."
            in response.content.decode()
        )

    def test_confirm_import_with_errors(self, client, user, dataset, mocker):
        """Ensure error messages are shown for errors that occur during the
        confirmation step of an import, and any devices that were added/updated
        and did not have errors are saved in the database.
        """
        # Change the app_user_name on the first 2 devices
        expected_app_user_names = {}
        for index, row in enumerate(dataset[:2]):
            row = list(row)
            row[3] += "_edited"
            dataset[index] = row
            expected_app_user_names[row[0]] = row[3]
        # Add two new rows, but one will have a validation error (a duplicate device_id)
        for index, new_device in enumerate(DeviceFactory.build_batch(2)):
            row = [
                None,
                dataset[0][1],
                new_device.serial_number,
                new_device.app_user_name,
                new_device.device_id if index else dataset[0][-1],
            ]
            dataset.append(row)
        mocker.patch("apps.mdm.import_export.trigger_dagster_job")
        response = self.check_import(client, dataset, expected_app_user_names)
        # We should now have 4 Devices: 3 existing devices + 1 new device
        assert Device.objects.count() == 4
        response_content = response.content.decode()
        assert (
            "Import finished: 1 new, 2 updated, 0 deleted and 1 skipped devices."
            in response_content
        )
        # An error message for the validation error on one of the new Devices
        assert (
            "Row 4, Column 'device_id': Device with this Device ID already exists."
            in response_content
        )

    @pytest.mark.parametrize("mdm_api_error", [False, True], indirect=True)
    def test_device_save(self, client, user, mocker, mdm_api_error, organization):
        """Ensures push_device_config() is called when saving a Device in Admin
        and if there is an MDM API error it is displayed to the user.
        """
        MDM = get_active_mdm_class(organization)
        mock_push_device_config = mocker.patch.object(
            MDM, "push_device_config", side_effect=mdm_api_error
        )
        device = DeviceFactory(fleet__organization=organization)
        data = {
            "fleet": device.fleet_id,
            "serial_number": device.serial_number,
            "app_user_name": f"edited_{device.app_user_name}",
        }
        response = client.post(
            reverse("admin:mdm_device_change", args=[device.id]), data=data, follow=True
        )

        assert response.status_code == 200
        mock_push_device_config.assert_called_once()
        device.refresh_from_db()
        assert device.app_user_name == data["app_user_name"]
        if mdm_api_error:
            assertContains(
                response,
                f"Unable to update the device in {MDM.name} due to the following error:"
                f"<br><code>{mdm_api_error}</code>",
            )


class TestFleetAdmin(TestAdmin):
    @pytest.mark.parametrize("mdm_api_error", [False, True], indirect=True)
    def test_new_fleet(self, user, client, mocker, mdm_api_error, organization):
        """Ensures the add_group_to_policy() function is called for a new fleet."""
        fleet = FleetFactory.build(organization=organization, policy=PolicyFactory())
        data = {
            "organization": fleet.organization_id,
            "name": fleet.name,
            "mdm_group_id": fleet.mdm_group_id,
            "policy": fleet.policy_id,
        }
        MDM = get_active_mdm_class(organization)
        mock_add_group_to_policy = mocker.patch.object(
            MDM, "add_group_to_policy", side_effect=mdm_api_error
        )
        mocker.patch.object(MDM, "pull_devices")
        response = client.post(reverse("admin:mdm_fleet_add"), data=data, follow=True)

        assert response.status_code == 200
        mock_add_group_to_policy.assert_called_once()
        assert organization.fleets.count() == 1
        if mdm_api_error:
            assertContains(
                response,
                (
                    "The fleet has been saved but it could not be added to the "
                    f"{fleet.policy.name} policy in {MDM.name} due to the following error:"
                    f"<br><code>{mdm_api_error}</code>"
                ),
            )

    @pytest.mark.parametrize("policy_changed", [True, False])
    def test_existing_fleet(self, user, client, mocker, policy_changed, organization):
        """Ensures the add_group_to_policy() function is called for an existing fleet
        if its policy is changed.
        """
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleet = FleetFactory(organization=organization)
        data = {
            "organization": fleet.organization_id,
            "name": fleet.name,
            "mdm_group_id": fleet.mdm_group_id,
            "policy": PolicyFactory().id if policy_changed else fleet.policy_id,
        }
        mock_add_group_to_policy = mocker.patch.object(MDM, "add_group_to_policy")
        response = client.post(
            reverse("admin:mdm_fleet_change", args=[fleet.id]), data=data, follow=True
        )

        assert response.status_code == 200

        if policy_changed:
            mock_add_group_to_policy.assert_called_once()
        else:
            mock_add_group_to_policy.assert_not_called()

    def test_changelist_includes_fleet_from_deleted_organization(
        self, user, client, mocker, organization
    ):
        """Fleet changelist includes fleets belonging to soft-deleted organizations."""
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleet = FleetFactory(organization=organization)
        fleet.organization.soft_delete()

        response = client.get(reverse("admin:mdm_fleet_changelist"))

        assert response.status_code == 200
        assertContains(response, fleet.name)

    def test_change_form_organization_dropdown_includes_deleted_selected_org(
        self, user, client, mocker, organization
    ):
        """Fleet change form still shows a deleted organization in the dropdown."""
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleet = FleetFactory(organization=organization)
        fleet.organization.soft_delete()

        response = client.get(reverse("admin:mdm_fleet_change", args=[fleet.pk]))

        assert response.status_code == 200
        assertContains(response, f'value="{fleet.organization_id}" selected')

    def test_delete_fleet_successful(self, user, client, mocker, organization):
        """Ensures a Fleet is successfully deleted if it's not linked to any device
        either in the database or in the MDM.
        """
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleet = FleetFactory(organization=organization)
        mock_delete_group = mocker.patch.object(MDM, "delete_group", return_value=True)
        response = client.post(
            reverse("admin:mdm_fleet_delete", args=[fleet.id]), data={"post": "yes"}, follow=True
        )

        assert response.status_code == 200
        mock_delete_group.assert_called_once()
        assert not Fleet.objects.filter(pk=fleet.pk).exists()
        assertContains(response, f"The fleet “{fleet}” was deleted successfully.")

    def test_delete_fleet_no_api_credentials(self, user, client, mocker, organization):
        """Ensures a Fleet is not deleted if the active MDM's API access is not configured."""
        fleet = FleetFactory()
        MDM = get_active_mdm_class(organization)
        mock_delete_group = mocker.patch.object(MDM, "delete_group")
        response = client.post(
            reverse("admin:mdm_fleet_delete", args=[fleet.id]), data={"post": "yes"}, follow=True
        )

        assert response.status_code == 200
        mock_delete_group.assert_not_called()
        assertContains(response, "Cannot delete the fleet. Please try again later.")
        assert Fleet.objects.filter(pk=fleet.pk).exists()
        assertNotContains(response, f"The fleet “{fleet}” was deleted successfully.")
        assertRedirects(response, reverse("admin:mdm_fleet_changelist"))

    def test_delete_fleet_has_devices(self, user, client, mocker, organization):
        """Ensures a Fleet is not deleted if it's linked to some devices either in
        the database or in the MDM.
        """
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleet = FleetFactory(organization=organization)
        mock_delete_group = mocker.patch.object(MDM, "delete_group", return_value=False)
        response = client.post(
            reverse("admin:mdm_fleet_delete", args=[fleet.id]), data={"post": "yes"}, follow=True
        )

        assert response.status_code == 200
        mock_delete_group.assert_called_once()
        assertContains(response, "Cannot delete the fleet because it has devices linked to it.")
        assert Fleet.objects.filter(pk=fleet.pk).exists()
        assertNotContains(response, f"The fleet “{fleet}” was deleted successfully.")
        assertRedirects(response, reverse("admin:mdm_fleet_changelist"))

    def test_delete_fleet_api_error(self, user, client, mocker, mdm_api_error_class, organization):
        """Ensures a Fleet is not deleted if an API error occurs when deleting the
        group in the MDM.
        """
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleet = FleetFactory(organization=organization)
        api_error = mdm_api_error_class("error")
        mock_delete_group = mocker.patch.object(MDM, "delete_group", side_effect=api_error)
        response = client.post(
            reverse("admin:mdm_fleet_delete", args=[fleet.id]), data={"post": "yes"}, follow=True
        )

        assert response.status_code == 200
        mock_delete_group.assert_called_once()
        assertContains(
            response,
            f"Cannot delete the fleet due to the following {MDM.name} API error:"
            f"<br><code>{api_error}</code><br>"
            "Please try again later.",
        )
        assert Fleet.objects.filter(pk=fleet.pk).exists()
        assertNotContains(response, f"The fleet “{fleet}” was deleted successfully.")
        assertRedirects(response, reverse("admin:mdm_fleet_changelist"))

    def test_delete_selected_fully_successful(self, user, client, mocker, organization):
        """Ensures fleets are successfully deleted using the delete_selected action
        if they are not linked to any device either in the database or in the MDM.
        """
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleets = FleetFactory.create_batch(5, organization=organization)
        # Will delete 3 fleets, 2 should remain
        to_delete_ids = [i.pk for i in fleets[:3]]
        mock_delete_group = mocker.patch.object(MDM, "delete_group", return_value=True)
        data = {"post": "yes", "action": "delete_selected", "_selected_action": to_delete_ids}
        response = client.post(reverse("admin:mdm_fleet_changelist"), data=data, follow=True)

        assert response.status_code == 200
        assert mock_delete_group.call_count == 3
        assert not Fleet.objects.filter(pk__in=to_delete_ids).exists()
        assert Fleet.objects.filter(pk__in=[i.pk for i in fleets[3:]]).count() == 2
        assertContains(response, "Successfully deleted 3 fleets.")

    @pytest.mark.parametrize("partial_success", [True, False])
    def test_delete_selected_failures(
        self,
        user,
        client,
        mocker,
        partial_success,
        mdm_api_error_class,
        organization,
    ):
        """Ensures fleets are not deleted using the delete_selected action if
        they are linked to devices either in the database or in the MDM.
        """
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "pull_devices")
        fleets = FleetFactory.create_batch(6 if partial_success else 4, organization=organization)
        # Will try to delete all fleets. 2 will fail because they have devices,
        # 2 will fail because of an API error, the rest (if any) will be successful
        has_devices = {i.pk: i.name for i in fleets[:2]}
        api_errors = {i.pk: i.name for i in fleets[2:4]}
        successful = [i.pk for i in fleets[4:]]
        api_error = mdm_api_error_class("error")

        def delete_group(fleet):
            if fleet.pk in has_devices:
                return False
            if fleet.pk in api_errors:
                raise api_error
            return True

        mock_delete_group = mocker.patch.object(MDM, "delete_group", side_effect=delete_group)
        data = {
            "post": "yes",
            "action": "delete_selected",
            "_selected_action": [i.pk for i in fleets],
        }
        response = client.post(reverse("admin:mdm_fleet_changelist"), data=data, follow=True)

        assert response.status_code == 200
        assert mock_delete_group.call_count == len(fleets)
        assert Fleet.objects.filter(pk__in=has_devices | api_errors).count() == 4
        assertContains(
            response,
            "Cannot delete the following fleets because they have devices linked "
            f"to them: {linebreaks('\n'.join(sorted(has_devices.values())))}",
        )
        for name in api_errors.values():
            assertContains(
                response,
                f"Could not delete {name} due the following {MDM.name} API error:"
                f"<br><code>{api_error}</code><br>"
                "Please try again later.",
            )
        if partial_success:
            assert not Fleet.objects.filter(pk__in=successful).exists()
            assertContains(response, "Successfully deleted 2 fleets.")
        else:
            assertNotContains(response, "Successfully deleted ")

    def test_delete_selected_no_api_credentials(
        self, user, client, mocker, organization, unconfigure_mdm
    ):
        """Ensures fleets are not deleted using the delete_selected action if
        the active MDM's API access is not configured.
        """
        fleets = FleetFactory.create_batch(3, organization=organization)
        MDM = get_active_mdm_class(organization)
        mock_delete_group = mocker.patch.object(MDM, "delete_group")
        data = {
            "post": "yes",
            "action": "delete_selected",
            "_selected_action": [i.pk for i in fleets],
        }
        response = client.post(reverse("admin:mdm_fleet_changelist"), data=data, follow=True)

        assert response.status_code == 200
        mock_delete_group.assert_not_called()
        assert Fleet.objects.filter(pk__in=[i.pk for i in fleets]).count() == 3
        assertNotContains(response, "Successfully deleted ")

    @pytest.mark.parametrize("mdm_api_error", [False, True], indirect=True)
    def test_fleet_save(self, client, user, mocker, mdm_api_error, organization):
        """Ensures pull_devices() is called when saving a Fleet in Admin
        and if there is an MDM API error it is displayed to the user.
        """
        MDM = get_active_mdm_class(organization)
        mock_pull_devices = mocker.patch.object(MDM, "pull_devices", side_effect=mdm_api_error)
        fleet = FleetFactory(organization=organization)
        data = {
            "organization": fleet.organization_id,
            "name": f"edited {fleet.name}",
            "mdm_group_id": fleet.mdm_group_id,
            "policy": fleet.policy_id,
        }
        response = client.post(
            reverse("admin:mdm_fleet_change", args=[fleet.id]), data=data, follow=True
        )

        assert response.status_code == 200
        mock_pull_devices.assert_called_once()
        fleet.refresh_from_db()
        assert fleet.name == data["name"]
        if mdm_api_error:
            assertContains(
                response,
                f"Unable to pull the fleet's devices from {MDM.name} due to "
                f"the following error:<br><code>{mdm_api_error}</code>",
            )


class TestPolicyAdmin(TestAdmin):
    @pytest.mark.parametrize("mdm_api_error", [False, True], indirect=True)
    def test_new_policy(self, user, client, mocker, mdm_api_error, organization):
        """Ensures the create_or_update_policy() method is called for a new Policy
        when the active MDM has the method.
        """
        MDM = get_active_mdm_class(organization)
        data = {
            "name": "New policy",
            "policy_id": "policy",
            "odk_collect_package": "org.odk.collect.android",
            "device_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "device_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "work_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "work_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "developer_settings": "DEVELOPER_SETTINGS_DISABLED",
            "applications-TOTAL_FORMS": "0",
            "applications-INITIAL_FORMS": "0",
            "organization": organization.id,
        }
        mdm_has_method = hasattr(MDM, "create_or_update_policy")
        if mdm_has_method:
            mock_create_or_update_policy = mocker.patch.object(
                MDM, "create_or_update_policy", side_effect=mdm_api_error
            )
        mock_push_device_config = mocker.patch.object(MDM, "push_device_config")
        response = client.post(reverse("admin:mdm_policy_add"), data=data, follow=True)

        assert response.status_code == 200
        if mdm_has_method:
            mock_create_or_update_policy.assert_called_once()
            if mdm_api_error:
                assertContains(
                    response,
                    (
                        f"Could not update the policy in {MDM.name} due to "
                        "the following error:"
                        f"<br><code>{mdm_api_error}</code>"
                    ),
                )
        mock_push_device_config.assert_not_called()

    @pytest.mark.parametrize("mdm_api_error", [False, True], indirect=True)
    def test_existing_policy(
        self,
        user,
        client,
        mocker,
        mdm_api_error,
        mdm_api_error_class,
        organization,
    ):
        """Ensures the create_or_update_policy() method is called when editing a Policy
        and child-device config pushes are queued via Dagster.
        """
        policy = PolicyFactory(organization=organization)
        data = {
            "name": policy.name,
            "policy_id": policy.policy_id,
            "organization": policy.organization_id,
            "odk_collect_package": policy.odk_collect_package,
            "device_password_quality": policy.device_password_quality,
            "device_password_require_unlock": policy.device_password_require_unlock,
            "work_password_quality": policy.work_password_quality,
            "work_password_require_unlock": policy.work_password_require_unlock,
            "developer_settings": policy.developer_settings,
            "applications-TOTAL_FORMS": "0",
            "applications-INITIAL_FORMS": "0",
        }
        MDM = get_active_mdm_class(organization)
        mdm_has_method = hasattr(MDM, "create_or_update_policy")
        devices_to_push = []
        if mdm_has_method:
            mock_create_or_update_policy = mocker.patch.object(
                MDM, "create_or_update_policy", side_effect=mdm_api_error
            )
            fleet = FleetFactory(policy=policy)
            for device in DeviceFactory.build_batch(2, fleet=fleet):
                device.raw_mdm_device = {
                    "policyName": f"enterprises/test/policies/fleet{device.fleet_id}_{device.device_id}"
                }
                device.save()
                devices_to_push.append(device)
            DeviceFactory.create_batch(
                2,
                fleet=fleet,
                raw_mdm_device={"policyName": f"enterprises/test/policies/{policy.policy_id}"},
            )
        mock_push_device_config = mocker.patch.object(MDM, "push_device_config")
        mock_trigger = mocker.patch("apps.mdm.admin.trigger_dagster_job")

        response = client.post(
            reverse("admin:mdm_policy_change", args=[policy.id]), data=data, follow=True
        )

        assert response.status_code == 200
        mock_push_device_config.assert_not_called()
        if mdm_has_method:
            mock_create_or_update_policy.assert_called_once()
            if mdm_api_error:
                assertContains(
                    response,
                    (
                        f"Could not update the policy in {MDM.name} due to "
                        "the following error:"
                        f"<br><code>{mdm_api_error}</code>"
                    ),
                )
            if devices_to_push:
                mock_trigger.assert_called_once()
                device_pks = mock_trigger.call_args.kwargs["run_config"]["ops"][
                    "push_mdm_device_config"
                ]["config"]["device_pks"]
                assert set(device_pks) == {d.pk for d in devices_to_push}
        else:
            mock_trigger.assert_not_called()

    def test_policy_push_happens_after_inline_applications_saved(
        self, user, client, mocker, organization
    ):
        """MDM push is triggered in save_related(), so inline applications added in the
        same POST are already persisted when create_or_update_policy() is called.

        Regression test: the push was previously in save_model(), which runs before
        Django's save_related() persists inline formset rows.
        """
        MDM = get_active_mdm_class(organization)
        if not hasattr(MDM, "create_or_update_policy"):
            pytest.skip("MDM does not have create_or_update_policy")

        pushed_package_names = []

        def capture_policy(policy):
            pushed_package_names.extend(
                list(policy.applications.values_list("package_name", flat=True))
            )

        mocker.patch.object(MDM, "create_or_update_policy", side_effect=capture_policy)
        mocker.patch.object(MDM, "push_device_config")

        data = {
            "name": "Test Policy",
            "policy_id": "test_policy_inline",
            "odk_collect_package": "org.odk.collect.android",
            "device_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "device_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "work_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "work_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "developer_settings": "DEVELOPER_SETTINGS_DISABLED",
            "applications-TOTAL_FORMS": "1",
            "applications-INITIAL_FORMS": "0",
            "applications-MIN_NUM_FORMS": "0",
            "applications-MAX_NUM_FORMS": "1000",
            "applications-0-package_name": "com.example.inline",
            "applications-0-install_type": "FORCE_INSTALLED",
            "applications-0-order": "1",
            "organization": organization.id,
        }
        response = client.post(reverse("admin:mdm_policy_add"), data=data, follow=True)
        assert response.status_code == 200
        # The inline application must already be in the DB when the MDM push fires
        assert "com.example.inline" in pushed_package_names


class TestPolicyAdminDagster(TestAdmin):
    """Tests that PolicyAdmin.save_related() uses Dagster for child-device pushes."""

    @pytest.fixture
    def policy_data_base(self):
        return {
            "name": "Dagster Test Policy",
            "policy_id": "dagster_test",
            "odk_collect_package": "org.odk.collect.android",
            "device_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "device_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "work_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "work_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "developer_settings": "DEVELOPER_SETTINGS_DISABLED",
            "applications-TOTAL_FORMS": "0",
            "applications-INITIAL_FORMS": "0",
        }

    @pytest.fixture
    def policy_with_child_devices(self, organization):
        policy = PolicyFactory(organization=organization)
        fleet = FleetFactory(policy=policy)
        devices = []
        for device in DeviceFactory.create_batch(2, fleet=fleet):
            device.raw_mdm_device = {
                "policyName": f"enterprises/test/policies/fleet{fleet.id}_{device.device_id}"
            }
            device.save()
            devices.append(device)
        return policy, devices

    def test_dagster_triggered_for_child_devices(
        self, user, client, mocker, organization, policy_with_child_devices
    ):
        """save_related() queues per-device config pushes via Dagster mdm_job."""
        MDM = get_active_mdm_class(organization)
        policy, devices = policy_with_child_devices
        mocker.patch.object(MDM, "create_or_update_policy")
        mock_push = mocker.patch.object(MDM, "push_device_config")
        mock_trigger = mocker.patch("apps.mdm.admin.trigger_dagster_job")
        data = {
            "name": policy.name,
            "policy_id": policy.policy_id,
            "odk_collect_package": policy.odk_collect_package,
            "device_password_quality": policy.device_password_quality,
            "device_password_require_unlock": policy.device_password_require_unlock,
            "work_password_quality": policy.work_password_quality,
            "work_password_require_unlock": policy.work_password_require_unlock,
            "developer_settings": policy.developer_settings,
            "applications-TOTAL_FORMS": "0",
            "applications-INITIAL_FORMS": "0",
            "organization": policy.organization.id,
        }

        response = client.post(
            reverse("admin:mdm_policy_change", args=[policy.id]), data=data, follow=True
        )

        assert response.status_code == 200
        mock_push.assert_not_called()
        mock_trigger.assert_called_once()
        call_kwargs = mock_trigger.call_args
        assert call_kwargs.kwargs["job_name"] == "mdm_job"
        device_pks = call_kwargs.kwargs["run_config"]["ops"]["push_mdm_device_config"]["config"][
            "device_pks"
        ]
        assert set(device_pks) == {d.pk for d in devices}

    def test_dagster_exception_shows_warning(
        self, user, client, mocker, organization, policy_with_child_devices
    ):
        """save_related() shows a warning and does not raise when trigger_dagster_job fails."""
        MDM = get_active_mdm_class(organization)
        if not hasattr(MDM, "create_or_update_policy"):
            pytest.skip("MDM does not have create_or_update_policy")
        policy, _ = policy_with_child_devices
        mocker.patch.object(MDM, "create_or_update_policy")
        dagster_error = Exception("Dagster unavailable")
        mock_trigger = mocker.patch("apps.mdm.admin.trigger_dagster_job", side_effect=dagster_error)
        data = {
            "name": policy.name,
            "policy_id": policy.policy_id,
            "odk_collect_package": policy.odk_collect_package,
            "device_password_quality": policy.device_password_quality,
            "device_password_require_unlock": policy.device_password_require_unlock,
            "work_password_quality": policy.work_password_quality,
            "work_password_require_unlock": policy.work_password_require_unlock,
            "developer_settings": policy.developer_settings,
            "applications-TOTAL_FORMS": "0",
            "applications-INITIAL_FORMS": "0",
            "organization": policy.organization.id,
        }

        response = client.post(
            reverse("admin:mdm_policy_change", args=[policy.id]), data=data, follow=True
        )

        assert response.status_code == 200
        mock_trigger.assert_called_once()
        assertContains(
            response,
            "Could not queue device policy updates due to "
            "the following error:"
            f"<br><code>{dagster_error}</code>",
        )


class TestFleetAdminDeleteConfirmation(TestAdmin):
    """Tests for the GET paths in FleetAdmin that render confirmation pages."""

    def test_delete_view_shows_confirmation_page(self, user, client):
        """GET to the fleet delete URL renders the confirmation page (not the delete action)."""
        fleet = FleetFactory()
        response = client.get(reverse("admin:mdm_fleet_delete", args=[fleet.id]))
        assert response.status_code == 200
        # Confirmation page lists the object to be deleted
        assert fleet in response.context["deleted_objects"] or fleet.name in str(response.content)

    def test_delete_view_nonexistent_fleet_redirects(self, user, client):
        """GET to the fleet delete URL with a non-existent ID redirects to changelist."""
        response = client.get(reverse("admin:mdm_fleet_delete", args=[999999]))
        assert response.status_code == 302

    def test_delete_view_no_delete_permission_raises_403(self, client):
        """GET to the fleet delete URL by a user without delete permission returns 403."""
        # Staff user without delete_fleet permission
        staff_user = UserFactory(is_staff=True, is_superuser=False)
        staff_user.user_permissions.set(
            Permission.objects.filter(codename__in=["view_fleet", "change_fleet"])
        )
        staff_user.save()
        client.force_login(staff_user)
        fleet = FleetFactory()
        response = client.get(reverse("admin:mdm_fleet_delete", args=[fleet.id]))
        assert response.status_code == 403

    def test_delete_view_disallowed_to_field_raises_400(self, user, client):
        """GET to fleet delete URL with a non-unique _to_field returns 400."""
        fleet = FleetFactory()
        # 'name' is not a primary key or unique field, so it's not allowed as to_field
        response = client.get(
            reverse("admin:mdm_fleet_delete", args=[fleet.id]) + "?_to_field=name"
        )
        assert response.status_code == 400

    def test_delete_view_cannot_delete_title_when_related_perms_lacking(self, client):
        """Confirmation page shows 'Cannot delete' title when user lacks delete
        permission for a related object (device linked to the fleet)."""
        # Staff user with delete_fleet but NOT delete_device
        staff_user = UserFactory(is_staff=True, is_superuser=False)
        staff_user.user_permissions.set(
            Permission.objects.filter(
                codename__in=[
                    "view_fleet",
                    "change_fleet",
                    "delete_fleet",
                    "view_device",
                    "change_device",
                    "view_policy",
                    "change_policy",
                    "add_policy",
                ]
            )
        )
        staff_user.save()
        client.force_login(staff_user)
        fleet = FleetFactory()
        DeviceFactory(fleet=fleet)  # linked device requires delete_device permission
        response = client.get(reverse("admin:mdm_fleet_delete", args=[fleet.id]))
        assert response.status_code == 200
        # With missing device delete perm, title should indicate cannot delete
        assert "Cannot delete" in str(response.content) or response.context.get("perms_lacking")

    def test_delete_selected_shows_confirmation_page(self, user, client, mocker):
        """Posting delete_selected without 'post=yes' renders the confirmation page."""
        fleets = FleetFactory.create_batch(2)
        data = {
            "action": "delete_selected",
            "_selected_action": [fleet.pk for fleet in fleets],
        }
        response = client.post(reverse("admin:mdm_fleet_changelist"), data=data)
        assert response.status_code == 200
        # Should show confirmation page, not redirect
        assert (
            "delete" in response.context.get("title", "").lower()
            or b"delete" in response.content.lower()
        )
