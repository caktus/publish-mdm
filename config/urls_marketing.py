from django.urls import path

from apps.marketing import views

urlpatterns = [
    path("", views.LandingPageView.as_view(), name="landing"),
] 