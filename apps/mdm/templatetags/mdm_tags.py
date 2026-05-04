from django import template
from django.utils.html import format_html

register = template.Library()

_INFO_ICON_SVG = (
    '<svg class="inline h-4 w-4" fill="none" viewBox="0 0 24 24"'
    ' stroke="currentColor" stroke-width="2" aria-hidden="true">'
    '<path stroke-linecap="round" stroke-linejoin="round"'
    ' d="M10 11h2v5m-2 0h4m-2.592-8.5h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />'
    "</svg>"
)

_TOGGLE_TRACK = (
    "relative h-5 w-9 rounded-full bg-gray-200"
    " after:absolute after:start-[2px] after:top-[2px]"
    " after:h-4 after:w-4 after:rounded-full after:border"
    " after:border-gray-300 after:bg-white after:transition-all after:content-['']"
    " peer-checked:bg-blue-600 peer-checked:after:translate-x-full"
    " peer-checked:after:border-white peer-focus:outline-none"
    " peer-focus:ring-2 peer-focus:ring-primary-300"
    " rtl:peer-checked:after:-translate-x-full"
    " dark:border-gray-600 dark:bg-gray-700"
    " dark:peer-checked:bg-blue-600 dark:peer-focus:ring-primary-800"
)


@register.simple_tag
def info_icon(tooltip_id):
    """Render a Flowbite tooltip trigger icon for the given tooltip_id.

    Usage:  {% load mdm_tags %}  {% info_icon "tooltip-my-field" %}

    Pair with a tooltip <div id="tooltip-my-field"> in the same template.
    Using a tag (not {% include %}) avoids template_rendered signal overhead
    and the associated context-copy recursion in Django's test client.
    """
    return format_html(
        '<span data-tooltip-target="{}" data-tooltip-style="light" class="tooltip-icon">'
        + _INFO_ICON_SVG
        + "</span>",
        tooltip_id,
    )


@register.simple_tag
def toggle_field(field, tooltip_id=""):
    """Render a Flowbite toggle-switch for a boolean BoundField.

    Usage:
        {% load mdm_tags %}
        {% toggle_field form.vpn_lockdown %}
        {% toggle_field form.kiosk_custom_launcher_enabled tooltip_id="tooltip-kiosk-launcher" %}

    When ``tooltip_id`` is omitted and the field has ``help_text``, a tooltip is
    automatically generated using the field name as the id and the help_text as
    the content.  When ``tooltip_id`` is explicitly provided the caller is
    responsible for supplying the matching tooltip ``<div>`` in the template.

    Using a tag (not {% include %}) avoids template_rendered signal overhead
    and the associated context-copy recursion in Django's test client.
    """
    checked = "checked" if field.value() else ""

    # Auto-generate a tooltip from help_text when no explicit tooltip_id is given.
    auto_tooltip_html = ""
    if not tooltip_id and field.help_text:
        tooltip_id = "tooltip-" + field.html_name.replace("_", "-")
        auto_tooltip_html = format_html(
            '<div id="{}" role="tooltip" class="tooltip-container">'
            "{}"
            '<div class="tooltip-arrow" data-popper-arrow></div>'
            "</div>",
            tooltip_id,
            field.help_text,
        )

    icon_html = (
        format_html(
            '<span data-tooltip-target="{}" data-tooltip-style="light" class="tooltip-icon">'
            + _INFO_ICON_SVG
            + "</span>",
            tooltip_id,
        )
        if tooltip_id
        else ""
    )
    errors_html = field.errors.as_ul()
    return format_html(
        '<label class="inline-flex cursor-pointer items-center gap-3" for="{}">'
        '<input type="checkbox" name="{}" id="{}" {} class="sr-only peer">'
        '<div class="{}"></div>'
        '<span class="text-sm font-medium text-gray-900 dark:text-white">{}</span>'
        "{}"
        "</label>"
        "{}"
        "{}",
        field.id_for_label,
        field.html_name,
        field.id_for_label,
        checked,
        _TOGGLE_TRACK,
        field.label,
        icon_html,
        errors_html,
        auto_tooltip_html,
    )
