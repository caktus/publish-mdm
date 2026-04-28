import datetime as dt
from typing import ClassVar

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import mark_safe
from django.utils.timezone import now

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

    def render_status(self, record):
        if record.revoked_at:
            return mark_safe('<span class="badge-gray">Revoked</span>')
        if record.is_expired:
            return mark_safe('<span class="badge-red">Expired</span>')
        if record.expires_at and record.expires_at < now() + dt.timedelta(days=7):
            return mark_safe('<span class="badge-yellow">Expiring Soon</span>')
        return mark_safe('<span class="badge-green">Active</span>')

    def render_actions(self, record):
        org_slug = record.organization.slug
        detail_url = reverse("mdm:enrollment-token-detail", args=[org_slug, record.pk])
        revoke_url = reverse("mdm:enrollment-token-revoke", args=[org_slug, record.pk])
        links = [f'<a href="{detail_url}" class="text-primary-600 hover:underline mr-2">View</a>']
        if record.is_active:
            links.append(f'<a href="{revoke_url}" class="text-red-600 hover:underline">Revoke</a>')
        return mark_safe("".join(links))
