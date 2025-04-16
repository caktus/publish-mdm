"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from apps.odk_publish.views import websockets_server_health, AcceptOrganizationInvite

urlpatterns = [
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("", include("apps.odk_publish.urls", namespace="odk_publish")),
    path("ws/health/", websockets_server_health),
    re_path(
        r"^accept-invite/(?P<key>\w+)/?$",
        AcceptOrganizationInvite.as_view(),
        name="accept-invite",
    ),
    path(r"", TemplateView.as_view(template_name="home.html"), name="home"),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns = (
        [
            path("__debug__/", include("debug_toolbar.urls")),
            path("__reload__/", include("django_browser_reload.urls")),
        ]
        + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
        + urlpatterns
    )
