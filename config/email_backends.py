from bandit.backends.base import HijackBackendMixin
from django_ses import SESBackend


class HijackSESBackend(HijackBackendMixin, SESBackend):
    """
    This backend intercepts outgoing messages drops them to a single email
    address, using the SESBackend in django_ses.
    """

    pass
