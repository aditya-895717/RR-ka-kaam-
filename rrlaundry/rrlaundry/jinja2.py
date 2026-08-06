from django.contrib.messages import get_messages
from django.contrib.staticfiles.storage import staticfiles_storage
from django.template.defaultfilters import date as django_date
from django.template.defaultfilters import time as django_time
from django.template.defaultfilters import timesince as django_timesince
from django.urls import reverse
from jinja2 import Environment


def _url(viewname, *args, **kwargs):
    """Ergonomic wrapper: url('name', kwarg=val) or url('name', arg1)."""
    if args:
        return reverse(viewname, args=args)
    if kwargs:
        return reverse(viewname, kwargs=kwargs)
    return reverse(viewname)


def environment(**options):
    env = Environment(**options)
    env.globals.update({
        'static': lambda path: staticfiles_storage.url(path),
        'url': _url,
        'get_messages': get_messages,
    })
    # Jinja2 has no equivalent of Django's |date, so templates written against
    # Django template syntax raise TemplateSyntaxError("No filter named 'date'").
    # Django's own implementations are reused rather than reimplemented so that
    # format strings ('d M Y H:i') and TIME_ZONE handling behave identically.
    env.filters.update({
        'date': django_date,
        'time': django_time,
        'timesince': django_timesince,
    })
    return env
