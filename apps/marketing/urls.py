from django.urls import path

from . import views

app_name = "marketing"
urlpatterns = [
    path("", views.LandingPageView.as_view(), name="landing"),
] 