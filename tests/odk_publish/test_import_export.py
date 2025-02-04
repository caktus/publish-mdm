import pytest
from tablib import Dataset

from apps.odk_publish import models, import_export


@pytest.mark.django_db
class TestAppUserResource:
    @pytest.fixture
    def template_variables(self):
        return [
            models.TemplateVariable.objects.create(name=i)
            for i in ("center_id", "center_label", "public_key", "manager_password")
        ]

    @pytest.fixture
    def project(self, template_variables):
        central_server = models.CentralServer.objects.create(
            base_url="https://odk-central.caktustest.net/"
        )
        project = models.Project.objects.create(
            name="Caktus Test",
            central_id=1,
            central_server=central_server,
        )
        project.template_variables.set(template_variables)
        return project

    @pytest.fixture
    def other_project(self, template_variables):
        myodkcloud = models.CentralServer.objects.create(base_url="https://myodkcloud.com/")
        project = models.Project.objects.create(
            name="Other Project",
            central_id=5,
            central_server=myodkcloud,
        )
        project.template_variables.set(template_variables)
        return project

    def test_export(self, project, other_project, template_variables):
        expected_export_values = set()

        # Create 5 users for each project
        for center_id in range(11030, 11040):
            app_user = models.AppUser.objects.create(
                name=center_id,
                project=project if center_id % 2 else other_project,
                central_id=center_id - 11000,
            )
            export_values = [app_user.id, app_user.name, app_user.central_id]
            for var, value in zip(
                template_variables,
                (center_id, f"Center {center_id}", f"key{center_id}", f"pass{center_id}"),
            ):
                models.AppUserTemplateVariable.objects.create(
                    app_user=app_user, template_variable=var, value=value
                )
                export_values.append(value)
            if app_user.project == project:
                expected_export_values.add(tuple(str(i) for i in export_values))

        resource = import_export.AppUserResource(project)
        dataset = resource.export(project.app_users.all())

        # Only data for the selected project should be exported
        assert len(dataset) == 5
        assert dataset.headers == [
            "id",
            "name",
            "central_id",
            "center_id",
            "center_label",
            "public_key",
            "manager_password",
        ]
        for i in range(len(dataset)):
            assert dataset.get(i) in expected_export_values

    def test_import(self, project):
        app_user1 = models.AppUser.objects.create(
            name=12345,
            project=project,
            central_id=1,
        )
        for var in project.template_variables.all():
            app_user1.app_user_template_variables.create(template_variable=var, value="test")

        app_user2 = models.AppUser.objects.create(
            name=67890,
            project=project,
            central_id=2,
        )
        assert models.AppUser.objects.count() == 2
        assert models.AppUserTemplateVariable.objects.count() == project.template_variables.count()

        csv_data = (
            "id,name,central_id,center_id,center_label,public_key,manager_password\n"
            f"{app_user1.id},11031,31,11031,Center 11031,key11031,pass11031\n"
            f"{app_user2.id},11033,33,11033,Center 11033,key11033,pass11033\n"
            ",11035,35,11035,Center 11035,key11035,pass11035\n"
            ",11037,37,11037,Center 11037,key11037,pass11037\n"
            ",11039,39,11039,Center 11039,key11039,pass11039\n"
        )
        dataset = Dataset().load(csv_data)
        resource = import_export.AppUserResource(project)
        resource.import_data(dataset)

        assert models.AppUser.objects.count() == 5
        assert (
            models.AppUserTemplateVariable.objects.count() == project.template_variables.count() * 5
        )

        app_user1.refresh_from_db()
        for i in dataset.dict:
            pk = i.pop("id")
            if pk:
                # Make sure user data has been added / updated
                app_user = models.AppUser.objects.get(pk=pk)
                assert app_user.name == i.pop("name")
                assert app_user.central_id == int(i.pop("central_id"))
                assert (
                    dict(
                        app_user.app_user_template_variables.values_list(
                            "template_variable__name", "value"
                        )
                    )
                    == i
                )
