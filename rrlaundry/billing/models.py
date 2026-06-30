import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

from accounts.models import HospitalDepartment, HospitalProfile, LaundryProfile
from hospital.models import LaundryOrder


class InvoiceStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PAID    = 'PAID',    'Paid'
    OVERDUE = 'OVERDUE', 'Overdue'


class Invoice(models.Model):
    invoice_id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number  = models.CharField(max_length=30, unique=True, db_index=True)
    order           = models.OneToOneField(
        LaundryOrder, on_delete=models.CASCADE, related_name='invoice',
    )
    hospital        = models.ForeignKey(
        HospitalProfile, on_delete=models.CASCADE, related_name='invoices',
    )
    laundry_partner = models.ForeignKey(
        LaundryProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
    )
    price_per_item  = models.DecimalField(max_digits=10, decimal_places=2)
    total_items     = models.PositiveIntegerField(default=0)
    total_amount    = models.DecimalField(max_digits=12, decimal_places=2)
    status          = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.PENDING,
    )
    generated_at    = models.DateTimeField(auto_now_add=True)
    paid_at         = models.DateTimeField(null=True, blank=True)
    due_date        = models.DateTimeField()

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return self.invoice_number

    def is_overdue(self):
        return self.status == InvoiceStatus.PENDING and timezone.now() > self.due_date


class InvoiceLineItem(models.Model):
    invoice         = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='line_items',
    )
    department      = models.ForeignKey(
        HospitalDepartment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoice_line_items',
    )
    item_count      = models.PositiveIntegerField()
    price_per_item  = models.DecimalField(max_digits=10, decimal_places=2)
    line_total      = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['department__department_name']

    def __str__(self):
        dept = self.department.department_name if self.department else 'Unassigned'
        return f'{self.invoice.invoice_number} — {dept}: {self.item_count} items'
