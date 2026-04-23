from typing import ClassVar

import django_tables2 as tables

from .models import Policy


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
