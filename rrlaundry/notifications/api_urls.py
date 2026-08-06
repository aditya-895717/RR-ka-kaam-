from django.urls import path

from . import api
from .sweep import sweep

urlpatterns = [
    path('unread/',            api.UnreadNotificationsAPI.as_view(), name='api_notifications_unread'),
    path('read-all/',          api.MarkAllReadAPI.as_view(),         name='api_notifications_read_all'),
    path('<int:pk>/read/',     api.MarkReadAPI.as_view(),            name='api_notifications_mark_read'),
    # Token-protected cron target — hit every 5 min by an external pinger.
    path('sweep/',             sweep,                                name='api_notifications_sweep'),
]
