from django.db.models import Count
from django.utils.functional import cached_property
from django_filters import FilterSet, MultipleChoiceFilter

from apps.mdm.models import Device, Fleet
from apps.patterns.widgets import CheckboxSelectMultiple


class FleetMultipleChoiceFilter(MultipleChoiceFilter):
    """Like django-filter's built-in AllValuesMultipleFilter, but shows the
    Fleet name and number of devices as the choice label instead of an ID.
    """

    @cached_property
    def field(self):
        qs = (
            Fleet.objects.filter(devices__in=self.parent.queryset)
            .annotate(device_count=Count("devices"))
            .values_list("id", "name", "device_count")
        )
        self.extra["choices"] = [(id, f"{name} ({count})") for id, name, count in qs]
        return super().field


class DeviceFilter(FilterSet):
    fleet = FleetMultipleChoiceFilter(widget=CheckboxSelectMultiple)

    class Meta:
        model = Device
        fields = ["fleet"]
