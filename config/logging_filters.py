import logging

from django.conf import settings

DEV_FILTERED_EVENTS = ["request_started", "request_finished", "task_started", "task_succeeded"]


class DevelopmentFilter(logging.Filter):
    """Filter out events in development so they don't clutter the console"""

    def filter(self, record):
        if settings.DEBUG and type(record.msg) is dict:
            event = record.msg.get("event")
            if event in DEV_FILTERED_EVENTS:
                return False
        return True
