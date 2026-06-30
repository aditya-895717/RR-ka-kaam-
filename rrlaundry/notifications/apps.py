import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        try:
            from django_q.models import Schedule
            Schedule.objects.get_or_create(
                func='notifications.jobs.check_missing_items',
                defaults={
                    'name':          'Missing Item Alert — every 5 min',
                    'schedule_type': Schedule.MINUTES,
                    'minutes':       5,
                    'repeats':       -1,
                },
            )
        except Exception:
            # DB not ready (initial migration) or django-q not installed — skip.
            logger.debug('Could not register check_missing_items schedule', exc_info=True)
