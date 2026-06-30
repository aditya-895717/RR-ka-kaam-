import uuid

from django.db import models

from accounts.models import DeliveryProfile
from hospital.models import LaundryOrder


class JobType(models.TextChoices):
    PICKUP   = 'PICKUP',   'Pickup (S1)'
    DELIVERY = 'DELIVERY', 'Delivery (S4)'


class JobStatus(models.TextChoices):
    ASSIGNED    = 'ASSIGNED',    'Assigned'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED   = 'COMPLETED',   'Completed'


class DeliveryJob(models.Model):
    job_id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order            = models.ForeignKey(
        LaundryOrder, on_delete=models.CASCADE, related_name='delivery_jobs',
    )
    delivery_partner = models.ForeignKey(
        DeliveryProfile, on_delete=models.CASCADE, related_name='jobs',
    )
    job_type  = models.CharField(max_length=10, choices=JobType.choices)
    status    = models.CharField(max_length=15, choices=JobStatus.choices, default=JobStatus.ASSIGNED)
    assigned_at  = models.DateTimeField(auto_now_add=True)
    started_at   = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'job_type'],
                name='unique_job_per_order_type',
            )
        ]

    def __str__(self):
        return f'{self.job_type} job for {self.order.short_id}'

    @property
    def short_id(self):
        return str(self.job_id)[:8].upper()

    def expected_item_count(self):
        return self.order.items.count()
