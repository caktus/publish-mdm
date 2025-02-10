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
