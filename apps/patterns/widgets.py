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


class BaseEmailInput(widgets.EmailInput):
    """An EmailInput where a render_value argument can be passed to the constructor,
    similar to a PasswordInput: if render_value=False, the current value does not get
    rendered when the field is rendered.
    """

    def __init__(self, attrs=None, render_value=True):
        super().__init__(attrs)
        self.render_value = render_value

    def get_context(self, name, value, attrs):
        if not self.render_value:
            value = None
        return super().get_context(name, value, attrs)


class EmailInput(BaseEmailInput):
    template_name = "patterns/forms/widgets/input.html"


class PasswordInput(widgets.PasswordInput):
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


class CheckboxInput(widgets.CheckboxInput):
    template_name = "patterns/forms/widgets/checkbox.html"
