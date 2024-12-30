import logging

from django.forms.utils import ErrorList

logger = logging.getLogger(__name__)


class PlatformErrorList(ErrorList):
    """
    Pattern Library-styled form errors.

    https://docs.djangoproject.com/en/4.1/ref/forms/api/#customizing-the-error-list-format
    """

    template_name = "patterns/forms/errors.html"


class PlatformFormMixin(object):
    """
    Form Mixin class to auto-style labels, errors, and inputs following the
    established standards.

    https://docs.djangoproject.com/en/4.1/ref/forms/api/#output-styles
    """

    template_name_div = "patterns/forms/div.html"
    template_name_label = "patterns/forms/label.html"

    def __init__(self, *args, **kwargs):
        kwargs["error_class"] = PlatformErrorList
        super().__init__(*args, **kwargs)

    def is_valid(self):
        """Always log form errors for debugging purposes"""
        is_valid = super().is_valid()
        if self.is_bound and not is_valid:
            logger.debug(
                f"{self.__class__.__name__} not valid", extra={"errors": self.errors}
            )
        return is_valid
