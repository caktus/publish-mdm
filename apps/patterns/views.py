from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.cache import patch_vary_headers
from django_filters.views import FilterView
from django_tables2 import SingleTableMixin


class HtmxListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    """
    Generic List View that supports filtering, ordering and pagination
    Required subclassed attributes:
        table_class: django_tables2.Table
        filterset_class: django_filters.Filterset
        template_name: str (path to list template)
        htmx_template_name: str (path to htmx list partial)
        staff_only_fields: tuple (fields to exclude in list for non-staff)
    """

    paginate_by = 15

    def get(self, request, *args, **kwargs):
        """
        Prevent browsers from caching HTMX requests by altering Vary header:
        https://github.com/adamchainz/django-htmx/issues/300
        """
        response = super().get(self, request, *args, **kwargs)
        if self.request.htmx:
            patch_vary_headers(response, ("HX-Request",))
        return response

    def get_template_names(self):
        if self.request.htmx:
            return self.htmx_template_name
        return self.template_name

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        if not self.request.user.is_staff:
            table.exclude = self.staff_only_fields
        return table
