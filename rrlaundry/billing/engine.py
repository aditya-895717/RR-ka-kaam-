import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from hospital.models import ItemStatus, LaundryOrder, OrderItem

logger = logging.getLogger(__name__)


def generate_invoice(order_id):
    """
    Generate Invoice + InvoiceLineItems for a delivered LaundryOrder.
    Invoice number format: INV-YYYYMMDD-XXXX (sequential per day).
    Raises if the order already has an invoice (OneToOne constraint).
    """
    from .models import Invoice, InvoiceLineItem, InvoiceStatus

    order = LaundryOrder.objects.select_related(
        'hospital', 'laundry_partner',
    ).get(order_id=order_id)

    laundry = order.laundry_partner
    price   = laundry.price_per_item if laundry else 0

    delivered   = OrderItem.objects.filter(order=order, current_status=ItemStatus.DELIVERED)
    total_items = delivered.count()
    dept_groups = list(delivered.values('department').annotate(count=Count('id')))

    with transaction.atomic():
        date_str = timezone.now().strftime('%Y%m%d')
        prefix   = f'INV-{date_str}-'
        last_num = (
            Invoice.objects
            .select_for_update()
            .filter(invoice_number__startswith=prefix)
            .aggregate(m=Max('invoice_number'))
        )['m']
        seq            = (int(last_num[-4:]) + 1) if last_num else 1
        invoice_number = f'{prefix}{seq:04d}'

        invoice = Invoice.objects.create(
            invoice_number  = invoice_number,
            order           = order,
            hospital        = order.hospital,
            laundry_partner = laundry,
            price_per_item  = price,
            total_items     = total_items,
            total_amount    = total_items * price,
            status          = InvoiceStatus.PENDING,
            due_date        = timezone.now() + timedelta(days=30),
        )

        if dept_groups:
            InvoiceLineItem.objects.bulk_create([
                InvoiceLineItem(
                    invoice        = invoice,
                    department_id  = g['department'],
                    item_count     = g['count'],
                    price_per_item = price,
                    line_total     = g['count'] * price,
                )
                for g in dept_groups
            ])

    try:
        from notifications.brevo import send_invoice_email
        send_invoice_email(invoice)
    except Exception:
        logger.exception('Invoice email failed for %s', invoice.invoice_number)

    return invoice
