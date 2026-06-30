from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    MISSING_ITEM      = 'MISSING_ITEM',      'Missing Item'
    TRANSIT_LOSS      = 'TRANSIT_LOSS',      'Transit Loss'
    DELIVERY_COMPLETE = 'DELIVERY_COMPLETE', 'Delivery Complete'
    ORDER_RECEIVED    = 'ORDER_RECEIVED',    'Order Received'


class DashboardNotification(models.Model):
    recipient         = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='dashboard_notifications',
    )
    title             = models.CharField(max_length=200)
    message           = models.TextField()
    tag_number        = models.CharField(max_length=50, blank=True)
    notification_type = models.CharField(
        max_length=30, choices=NotificationType.choices,
        default=NotificationType.MISSING_ITEM,
    )
    is_read           = models.BooleanField(default=False)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.notification_type}] {self.title} → {self.recipient.email}'
