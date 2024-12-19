from django.forms import widgets


class TextInput(widgets.TextInput):
    template_name = "patterns/forms/widgets/input.html"


class CheckboxSelectMultiple(widgets.CheckboxSelectMultiple):
    template_name = "patterns/forms/widgets/checkbox_select.html"
    option_template_name = "patterns/forms/widgets/checkbox_option.html"
