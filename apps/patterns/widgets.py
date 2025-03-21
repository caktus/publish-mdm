from django.forms import widgets


class CheckboxSelectMultiple(widgets.CheckboxSelectMultiple):
    template_name = "patterns/forms/widgets/checkbox_select.html"
    option_template_name = "patterns/forms/widgets/checkbox_option.html"


class FileInput(widgets.FileInput):
    template_name = "patterns/forms/widgets/file.html"


class Select(widgets.Select):
    template_name = "patterns/forms/widgets/select.html"


class TextInput(widgets.TextInput):
    template_name = "patterns/forms/widgets/input.html"


class InputWithAddon(widgets.TextInput):
    """An input with a button appended to its right end."""

    template_name = "patterns/forms/widgets/input_with_addon.html"

    def __init__(self, addon_content, addon_attrs=None, attrs=None):
        self.addon_content = addon_content
        self.addon_attrs = addon_attrs
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["addon"] = {"content": self.addon_content, "attrs": self.addon_attrs}
        return context
