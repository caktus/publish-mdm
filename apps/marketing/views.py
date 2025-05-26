from django.shortcuts import render
from django.views.generic import TemplateView

# Create your views here.

class LandingPageView(TemplateView):
    """View for the marketing landing page."""
    template_name = "marketing/landing.html"
