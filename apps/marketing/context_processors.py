from django.conf import settings

def marketing_site(request):
    """
    Add marketing site settings to the template context.
    """
    return {
        'USE_MARKETING_SITE': settings.USE_MARKETING_SITE,
    } 