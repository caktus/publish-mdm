import django_tables2 as tables

from .models import FormTemplate, FormTemplateVersion


class FormTemplateTable(tables.Table):
    app_users = tables.Column(
        verbose_name="App Users",
        accessor="app_user_count",
        order_by=("app_user_count", "title_base"),
    )
    latest_version = tables.TemplateColumn(
        template_code="{{ record.latest_version.0.version }} - {{ record.latest_version.0.user.first_name }}",
        verbose_name="Latest Version",
    )
    title_base = tables.LinkColumn(
        "odk_publish:form-template-detail",
        args=[tables.A("project.organization.slug"), tables.A("project_id"), tables.A("pk")],
        attrs={"a": {"class": "text-primary-600 hover:underline"}},
    )

    class Meta:
        model = FormTemplate
        fields = ["title_base", "form_id_base"]
        template_name = "patterns/tables/table.html"
        attrs = {"th": {"scope": "col", "class": "px-4 py-3 whitespace-nowrap"}}
        orderable = False


class FormTemplateVersionTable(tables.Table):
    """A table for displaying the version history for a form template."""

    version = tables.Column(verbose_name="Version number")
    modified_at = tables.DateColumn(verbose_name="Date published")
    published_by = tables.Column(accessor="user__get_full_name")

    class Meta:
        model = FormTemplateVersion
        fields = ["version", "modified_at"]
        template_name = "patterns/tables/table.html"
        attrs = {"th": {"scope": "col", "class": "px-4 py-3 whitespace-nowrap"}}
        orderable = False
