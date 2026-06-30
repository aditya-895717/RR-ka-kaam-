from django.conf import settings
from django.db import models
from django.utils import timezone

from hospital.models import OrderItem


class FloorStage(models.TextChoices):
    RECEIVED = 'RECEIVED', 'Received'
    SORTING  = 'SORTING',  'Sorting'
    WASHING  = 'WASHING',  'Washing'
    DRYING   = 'DRYING',   'Drying'
    FOLDING  = 'FOLDING',  'Folding'
    READY    = 'READY',    'Ready for Dispatch'


# Maps floor stage → OrderItem.current_status
STAGE_TO_ITEM_STATUS = {
    FloorStage.RECEIVED: 'AT_LAUNDRY',
    FloorStage.SORTING:  'AT_LAUNDRY',
    FloorStage.WASHING:  'AT_LAUNDRY',
    FloorStage.DRYING:   'WASHED',
    FloorStage.FOLDING:  'WASHED',
    FloorStage.READY:    'WASHED',
}

# Stages that are still "in progress" at the plant (not READY)
IN_PROGRESS_STAGES = {
    FloorStage.RECEIVED,
    FloorStage.SORTING,
    FloorStage.WASHING,
    FloorStage.DRYING,
    FloorStage.FOLDING,
}


class ItemStageLog(models.Model):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name='stage_logs',
    )
    stage = models.CharField(max_length=20, choices=FloorStage.choices)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='stage_updates',
    )
    updated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.order_item.tag_number} → {self.stage} @ {self.updated_at}'


class WorkerItemAssignment(models.Model):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name='worker_assignments',
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='item_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_first_worker = models.BooleanField(default=False)

    class Meta:
        ordering = ['assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['order_item'],
                condition=models.Q(is_first_worker=True),
                name='unique_first_worker_per_item',
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            if WorkerItemAssignment.objects.filter(pk=self.pk, is_first_worker=True).exists():
                raise ValueError(
                    f'WorkerItemAssignment {self.pk} has is_first_worker=True '
                    'and is immutable — it cannot be changed.'
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_first_worker:
            raise ValueError(
                f'WorkerItemAssignment {self.pk} is the first-worker record '
                'for tag {self.order_item.tag_number} and cannot be deleted.'
            )
        super().delete(*args, **kwargs)

    def __str__(self):
        return (
            f'{self.order_item.tag_number} → '
            f'{self.worker} '
            f'{"(first)" if self.is_first_worker else ""}'
        )


class MissingItemAlert(models.Model):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name='alerts',
    )
    triggered_at = models.DateTimeField(auto_now_add=True)
    last_stage = models.CharField(max_length=20, choices=FloorStage.choices)
    last_updated_at = models.DateTimeField()
    assigned_worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts_assigned',
    )
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-triggered_at']

    def resolve(self):
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.save(update_fields=['is_resolved', 'resolved_at'])

    def minutes_since_last_update(self):
        delta = timezone.now() - self.last_updated_at
        return int(delta.total_seconds() // 60)

    def __str__(self):
        return f'Alert: {self.order_item.tag_number} — {self.last_stage}'
