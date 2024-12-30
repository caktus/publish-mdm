import os

from .base import *  # noqa

# flake8: noqa: F405

# Critical settings
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(":")

### ADMINS and MANAGERS
ADMINS = (("Caktus Team", "team@caktusgroup.com"),)

# STATIC
# ------------------------------------------------------------------------------
STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}
# Performance optimizations
CACHE_HOST = os.getenv("CACHE_HOST", "redis://redis:6379/0")
if "redis" in CACHE_HOST:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_HOST,
        }
    }

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True") == "True"
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SESSION_COOKIE_SECURE
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "True") == "True"
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SESSION_COOKIE_HTTPONLY
SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True") == "True"
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-CSRF_COOKIE_SECURE
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "True") == "True"
# https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
# TODO: set this to 60 seconds first and then to 518400 once you prove the former works
SECURE_HSTS_SECONDS = 60
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "True") == "True"
)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "True") == "True"
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = (
    os.getenv("DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", "True") == "True"
)
# https://docs.djangoproject.com/en/3.2/ref/settings/#secure-referrer-policy
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "same-origin")

# CORS
# ------------------------------------------------------------------------------
# https://github.com/adamchainz/django-cors-headers#cors_allow_all_origins-bool
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "False") == "True"
# https://github.com/adamchainz/django-cors-headers#cors_allowed_origins-sequencestr
ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "")
if ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = ALLOWED_ORIGINS.split(";")

# CELERY
# ------------------------------------------------------------------------------
CELERY_SEND_TASK_ERROR_EMAILS = True

# SENTRY
# ------------------------------------------------------------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN")
SENTRY_SEND_DEFAULT_PII = os.getenv("SENTRY_SEND_DEFAULT_PII", "True") == "True"
if SENTRY_DSN:
    import sentry_sdk

    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), RedisIntegration(), CeleryIntegration()],
        environment=ENVIRONMENT,  # noqa: F405
        release=os.getenv("CONTAINER_IMAGE_TAG"),
        # % of captured performance monitoring transactions
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0)),
        # Attach user to error events
        send_default_pii=SENTRY_SEND_DEFAULT_PII,
    )
