from django.contrib.messages import get_messages
from django.contrib.staticfiles.storage import staticfiles_storage
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
        'static': staticfiles_storage.url,
        'url': _url,
        'get_messages': get_messages,
    })
    return env
