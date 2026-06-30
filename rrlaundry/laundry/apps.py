from django.apps import AppConfig


class LaundryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'laundry'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_register_q_schedule, sender=self)


def _register_q_schedule(sender, **kwargs):
    try:
        from django_q.models import Schedule
        Schedule.objects.update_or_create(
            name='check_missing_items',
            defaults={
                'func': 'notifications.jobs.check_missing_items',
                'schedule_type': Schedule.MINUTES,
                'minutes': 5,
            },
        )
    except Exception:
        pass
