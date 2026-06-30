from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DashboardNotification


def _time_ago(dt) -> str:
    secs = int((timezone.now() - dt).total_seconds())
    if secs < 60:
        return 'just now'
    if secs < 3600:
        return f'{secs // 60}m ago'
    if secs < 86400:
        return f'{secs // 3600}h ago'
    return f'{secs // 86400}d ago'


def _serialize(n: DashboardNotification) -> dict:
    return {
        'id':                n.id,
        'title':             n.title,
        'message':           n.message,
        'tag_number':        n.tag_number,
        'notification_type': n.notification_type,
        'time_ago':          _time_ago(n.created_at),
        'created_at':        n.created_at.isoformat(),
    }


class UnreadNotificationsAPI(APIView):
    """GET /api/notifications/unread/ — unread count + last 10."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            DashboardNotification.objects
            .filter(recipient=request.user, is_read=False)
            .order_by('-created_at')
        )
        return Response({
            'unread_count':  qs.count(),
            'notifications': [_serialize(n) for n in qs[:10]],
        })


class MarkReadAPI(APIView):
    """POST /api/notifications/<id>/read/ — mark single notification read."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        n = get_object_or_404(DashboardNotification, pk=pk, recipient=request.user)
        n.is_read = True
        n.save(update_fields=['is_read'])
        return Response({'status': 'read'})


class MarkAllReadAPI(APIView):
    """POST /api/notifications/read-all/ — mark all as read for current user."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = DashboardNotification.objects.filter(
            recipient=request.user, is_read=False,
        ).update(is_read=True)
        return Response({'status': 'all_read', 'marked': count})
