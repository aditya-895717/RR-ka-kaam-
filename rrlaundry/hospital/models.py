import uuid

from django.conf import settings
from django.db import models

from accounts.models import (
    DeliveryProfile, HospitalDepartment, HospitalProfile, LaundryProfile,
)


class HospitalPartnerSelection(models.Model):
    hospital = models.ForeignKey(
        HospitalProfile, on_delete=models.CASCADE, related_name='partner_selections',
    )
    laundry_partner = models.ForeignKey(
        LaundryProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='hospital_selections',
    )
    delivery_partner = models.ForeignKey(
        DeliveryProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='hospital_selections',
    )
    selected_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-selected_at']

    def __str__(self):
        return (
            f'{self.hospital.hospital_name} → '
            f'{self.laundry_partner} + {self.delivery_partner}'
        )


class OrderStatus(models.TextChoices):
    CREATED     = 'CREATED',     'Created'
    PICKUP_DONE = 'PICKUP_DONE', 'Pickup Done'
    AT_LAUNDRY  = 'AT_LAUNDRY',  'At Laundry'
    DISPATCHED  = 'DISPATCHED',  'Dispatched'
    DELIVERED   = 'DELIVERED',   'Delivered'
    COMPLETED   = 'COMPLETED',   'Completed'
    FLAGGED     = 'FLAGGED',     'Flagged'


class ItemStatus(models.TextChoices):
    WITH_HOSPITAL        = 'WITH_HOSPITAL',        'With Hospital'
    PICKUP_SCANNED       = 'PICKUP_SCANNED',        'Pickup Scanned (S1)'
    IN_TRANSIT_OUTBOUND  = 'IN_TRANSIT_OUTBOUND',   'In Transit — Outbound'
    AT_LAUNDRY           = 'AT_LAUNDRY',            'At Laundry (S2)'
    RECEIVED_AT_PLANT    = 'RECEIVED_AT_PLANT',     'Received at Plant (S2)'
    TRANSIT_LOSS_FLAG    = 'TRANSIT_LOSS_FLAG',     'Transit Loss — Flagged'
    WASHED               = 'WASHED',                'Washed'
    IN_TRANSIT_RETURN    = 'IN_TRANSIT_RETURN',     'In Transit — Return'
    DISPATCHED           = 'DISPATCHED',            'Dispatched (S3)'
    DELIVERED            = 'DELIVERED',             'Delivered (S4)'
    COMPLETED            = 'COMPLETED',             'Completed'


class ItemType(models.TextChoices):
    BEDSHEET      = 'BEDSHEET',      'Bedsheet'
    PILLOW_COVER  = 'PILLOW_COVER',  'Pillow Cover'
    PATIENT_GOWN  = 'PATIENT_GOWN',  'Patient Gown'
    OT_DRAPE      = 'OT_DRAPE',      'OT Drape'
    OTHER         = 'OTHER',         'Other'


# Hospital-visible status labels — internal laundry stages are collapsed.
_ORDER_HOSPITAL_LABELS = {
    OrderStatus.CREATED:     'Created',
    OrderStatus.PICKUP_DONE: 'Picked Up',
    OrderStatus.AT_LAUNDRY:  'At Laundry Plant',
    OrderStatus.DISPATCHED:  'Out for Delivery',
    OrderStatus.DELIVERED:   'Delivered',
    OrderStatus.COMPLETED:   'Completed',
    OrderStatus.FLAGGED:     'Flagged',
}

_ITEM_INTERNAL = {ItemStatus.AT_LAUNDRY, ItemStatus.WASHED}

_ITEM_HOSPITAL_LABELS = {
    ItemStatus.WITH_HOSPITAL:       'With Hospital',
    ItemStatus.PICKUP_SCANNED:      'Picked Up',
    ItemStatus.IN_TRANSIT_OUTBOUND: 'Picked Up',
    ItemStatus.AT_LAUNDRY:          'At Laundry Plant',
    ItemStatus.RECEIVED_AT_PLANT:   'At Laundry Plant',
    ItemStatus.TRANSIT_LOSS_FLAG:   'Flagged (Transit)',
    ItemStatus.WASHED:              'At Laundry Plant',
    ItemStatus.IN_TRANSIT_RETURN:   'Out for Delivery',
    ItemStatus.DISPATCHED:          'Out for Delivery',
    ItemStatus.DELIVERED:           'Delivered',
    ItemStatus.COMPLETED:           'Completed',
}


class LaundryOrder(models.Model):
    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(
        HospitalProfile, on_delete=models.CASCADE, related_name='orders',
    )
    laundry_partner = models.ForeignKey(
        LaundryProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders',
    )
    delivery_partner = models.ForeignKey(
        DeliveryProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders',
    )
    department = models.ForeignKey(
        HospitalDepartment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders',
    )
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.CREATED,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_orders',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order {self.short_id} — {self.hospital.hospital_name}'

    @property
    def short_id(self):
        return str(self.order_id)[:8].upper()

    def hospital_status_label(self):
        return _ORDER_HOSPITAL_LABELS.get(self.status, self.status)


class OrderItem(models.Model):
    order = models.ForeignKey(
        LaundryOrder, on_delete=models.CASCADE, related_name='items',
    )
    tag_number = models.CharField(max_length=50, unique=True, db_index=True)
    item_type = models.CharField(
        max_length=20, choices=ItemType.choices, default=ItemType.BEDSHEET,
    )
    current_status = models.CharField(
        max_length=20, choices=ItemStatus.choices, default=ItemStatus.WITH_HOSPITAL,
    )
    department = models.ForeignKey(
        HospitalDepartment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='items',
    )
    added_at = models.DateTimeField(auto_now_add=True)
    last_scanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['tag_number']

    def __str__(self):
        return f'{self.tag_number} ({self.get_item_type_display()})'

    def hospital_status_label(self):
        return _ITEM_HOSPITAL_LABELS.get(self.current_status, self.current_status)

    def scan_progress(self):
        """Returns 0-4 integer representing how far through the RFID scan chain this item is."""
        progress_map = {
            ItemStatus.WITH_HOSPITAL:       0,
            ItemStatus.PICKUP_SCANNED:      1,
            ItemStatus.IN_TRANSIT_OUTBOUND: 1,
            ItemStatus.AT_LAUNDRY:          2,
            ItemStatus.RECEIVED_AT_PLANT:   2,
            ItemStatus.TRANSIT_LOSS_FLAG:   1,
            ItemStatus.WASHED:              2,
            ItemStatus.IN_TRANSIT_RETURN:   3,
            ItemStatus.DISPATCHED:          3,
            ItemStatus.DELIVERED:           4,
            ItemStatus.COMPLETED:           4,
        }
        return progress_map.get(self.current_status, 0)
