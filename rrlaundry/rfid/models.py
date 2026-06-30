import uuid

from django.conf import settings
from django.db import models

from hospital.models import LaundryOrder, OrderItem


class ScanPoint(models.TextChoices):
    S1_PICKUP   = 'S1_PICKUP',   'S1 — Pickup (Hospital)'
    S2_RECEIVED = 'S2_RECEIVED', 'S2 — Received at Plant'
    S3_DISPATCH = 'S3_DISPATCH', 'S3 — Dispatch (Plant)'
    S4_DELIVERY = 'S4_DELIVERY', 'S4 — Delivery (Hospital)'


class RFIDScanEvent(models.Model):
    scan_id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag_number    = models.CharField(max_length=50, db_index=True)
    order_item    = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name='scan_events',
    )
    scan_point    = models.CharField(max_length=20, choices=ScanPoint.choices)
    scanned_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='scan_events',
    )
    scanned_at    = models.DateTimeField(auto_now_add=True)
    location_note = models.TextField(blank=True)
    order         = models.ForeignKey(
        LaundryOrder, on_delete=models.CASCADE, related_name='scan_events',
    )

    class Meta:
        ordering = ['scanned_at']
        indexes = [
            models.Index(fields=['tag_number', 'scan_point']),
            models.Index(fields=['order', 'scan_point']),
        ]

    def __str__(self):
        return f'{self.tag_number} @ {self.scan_point} — {self.scanned_at:%Y-%m-%d %H:%M}'


class ReconciliationLog(models.Model):
    order           = models.ForeignKey(
        LaundryOrder, on_delete=models.CASCADE, related_name='reconciliation_logs',
    )
    scan_point_from = models.CharField(max_length=20, choices=ScanPoint.choices)
    scan_point_to   = models.CharField(max_length=20, choices=ScanPoint.choices)
    expected_count  = models.PositiveIntegerField()
    received_count  = models.PositiveIntegerField()
    missing_tags    = models.JSONField(default=list)
    is_matched      = models.BooleanField(default=False)
    logged_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-logged_at']

    def __str__(self):
        status = 'OK' if self.is_matched else f'MISSING {len(self.missing_tags)}'
        return (
            f'Recon {self.order.short_id} '
            f'{self.scan_point_from}→{self.scan_point_to} [{status}]'
        )
