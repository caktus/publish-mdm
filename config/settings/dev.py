from .base import *  # noqa

# flake8: noqa: F405

# task_always_eager
CELERY_TASK_ALWAYS_EAGER = True
# task_eager_propagates
CELERY_TASK_EAGER_PROPAGATES = True

DEBUG = True

INSTALLED_APPS += [
    "debug_toolbar",
    "django_watchfiles",
    "django_browser_reload",
]

ALLOWED_HOSTS = ["*"]

INTERNAL_IPS = [
    "127.0.0.1",
]

MIDDLEWARE += [
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

TEMPLATES[0]["APP_DIRS"] = False
TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
