from django.conf import settings


def sentry(request):
    """Inject Sentry JS loader script URL into template context."""
    return {
        "sentry_js_loader_script": getattr(settings, "SENTRY_JS_LOADER_SCRIPT", ""),
    }
