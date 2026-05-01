from typing import ClassVar

import django_tables2 as tables
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from .models import EnrollmentToken, Policy


class PolicyTable(tables.Table):
    """A table for listing MDM Policies."""

    name = tables.LinkColumn(
        "mdm:policy-edit",
        args=[tables.A("organization__slug"), tables.A("pk")],
        attrs={"a": {"class": "text-primary-600 hover:underline"}},
    )
    policy_id = tables.Column(verbose_name="Policy ID")
    fleet_count = tables.Column(verbose_name="Fleets", orderable=False)

    class Meta:
        model = Policy
        fields = ("name", "policy_id", "fleet_count")
        template_name = "patterns/tables/table.html"
        attrs: ClassVar = {"th": {"scope": "col", "class": "px-4 py-3 whitespace-nowrap"}}
        orderable = False
        empty_text = 'No policies found. Click "Add policy" to create one.'


class EnrollmentTokenTable(tables.Table):
    """A table for listing EnrollmentTokens."""

    label = tables.LinkColumn(
        "mdm:enrollment-token-detail",
        args=[tables.A("organization__slug"), tables.A("pk")],
        attrs={"a": {"class": "text-primary-600 hover:underline"}},
        verbose_name="Label",
    )
    fleet = tables.Column(verbose_name="Fleet", orderable=False)
    status = tables.Column(verbose_name="Status", orderable=False, empty_values=())
    expires_at = tables.DateTimeColumn(verbose_name="Expires", format="Y-m-d H:i")
    created_at = tables.DateTimeColumn(verbose_name="Created", format="Y-m-d H:i")
    actions = tables.Column(verbose_name="Actions", orderable=False, empty_values=())

    class Meta:
        model = EnrollmentToken
        fields = ("label", "fleet", "status", "expires_at", "created_at", "actions")
        template_name = "patterns/tables/table.html"
        attrs: ClassVar = {"th": {"scope": "col", "class": "px-4 py-3 whitespace-nowrap"}}
        orderable = False
        empty_text = 'No enrollment tokens found. Click "Create Token" to create one.'

    def render_label(self, value, record):
        """Return the label, falling back to str(record) (token name or pk) when blank."""
        return value if value else str(record)

    def render_status(self, record):
        return render_to_string("includes/enrollment_token_status_badge.html", {"token": record})

    def render_actions(self, record):
        org_slug = record.organization.slug
        detail_url = reverse("mdm:enrollment-token-detail", args=[org_slug, record.pk])
        view_link = format_html(
            '<a href="{}" class="text-primary-600 hover:underline mr-2 text-sm">View</a>',
            detail_url,
        )
        if record.is_active:
            revoke_url = reverse("mdm:enrollment-token-revoke", args=[org_slug, record.pk])
            revoke_button = format_html(
                '<button type="button"'
                ' data-modal-target="revoke-token-modal"'
                ' data-modal-toggle="revoke-token-modal"'
                ' data-revoke-url="{}"'
                ' data-token-name="{}"'
                ' onclick="setRevokeTarget(this)"'
                ' class="text-red-600 hover:underline text-sm">Revoke</button>',
                revoke_url,
                str(record),
            )
            return format_html_join("", "{}", [(view_link,), (revoke_button,)])
        return view_link
