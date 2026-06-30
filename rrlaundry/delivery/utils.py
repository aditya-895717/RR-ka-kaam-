import logging

from django.db import transaction
from django.utils import timezone

from hospital.models import ItemStatus, LaundryOrder, OrderItem, OrderStatus
from notifications.brevo import send_email

from .models import DeliveryJob, JobStatus, JobType

logger = logging.getLogger(__name__)


def create_pickup_job(order: LaundryOrder) -> DeliveryJob | None:
    """Create a PICKUP job when a new order is placed. Idempotent."""
    if not order.delivery_partner:
        return None
    job, _ = DeliveryJob.objects.get_or_create(
        order=order,
        job_type=JobType.PICKUP,
        defaults={'delivery_partner': order.delivery_partner},
    )
    return job


def create_delivery_job(order: LaundryOrder) -> DeliveryJob | None:
    """Create a DELIVERY job when the order is dispatched. Idempotent."""
    if not order.delivery_partner:
        return None
    job, _ = DeliveryJob.objects.get_or_create(
        order=order,
        job_type=JobType.DELIVERY,
        defaults={'delivery_partner': order.delivery_partner},
    )
    return job


def process_pickup_scan(job: DeliveryJob, tag_numbers: list[str]) -> tuple[int, list[str]]:
    """
    S1 — Pickup at hospital.
    Marks each tag as PICKUP_SCANNED, updates order to PICKUP_DONE if all done,
    marks the job COMPLETED.
    Returns (scanned_count, unknown_tags).
    """
    order = job.order
    scanned_count = 0
    unknown_tags: list[str] = []
    now = timezone.now()

    with transaction.atomic():
        for tag in tag_numbers:
            try:
                item = OrderItem.objects.select_for_update().get(
                    tag_number=tag, order=order,
                )
                item.current_status = ItemStatus.PICKUP_SCANNED
                item.last_scanned_at = now
                item.save(update_fields=['current_status', 'last_scanned_at'])
                scanned_count += 1
            except OrderItem.DoesNotExist:
                unknown_tags.append(tag)

        if scanned_count:
            order.refresh_from_db()
            if not order.items.filter(current_status=ItemStatus.WITH_HOSPITAL).exists():
                order.status = OrderStatus.PICKUP_DONE
                order.save(update_fields=['status', 'updated_at'])

        job.status = JobStatus.COMPLETED
        job.completed_at = now
        job.save(update_fields=['status', 'completed_at'])

    return scanned_count, unknown_tags


def process_delivery_scan(job: DeliveryJob, tag_numbers: list[str]) -> tuple[int, list[str]]:
    """
    S4 — Delivery to hospital.
    Marks each tag as DELIVERED, updates order to DELIVERED if all done.
    """
    order = job.order
    scanned_count = 0
    unknown_tags: list[str] = []
    now = timezone.now()

    with transaction.atomic():
        for tag in tag_numbers:
            try:
                item = OrderItem.objects.select_for_update().get(
                    tag_number=tag, order=order,
                )
                item.current_status = ItemStatus.DELIVERED
                item.last_scanned_at = now
                item.save(update_fields=['current_status', 'last_scanned_at'])
                scanned_count += 1
            except OrderItem.DoesNotExist:
                unknown_tags.append(tag)

        if scanned_count:
            order.refresh_from_db()
            if not order.items.filter(current_status=ItemStatus.DISPATCHED).exists():
                order.status = OrderStatus.DELIVERED
                order.save(update_fields=['status', 'updated_at'])

        job.status = JobStatus.COMPLETED
        job.completed_at = now
        job.save(update_fields=['status', 'completed_at'])

    return scanned_count, unknown_tags


def send_pickup_confirmation(order: LaundryOrder, scanned_count: int):
    try:
        hospital_email = order.hospital.user.email
        partner_name = (
            order.delivery_partner.user.full_name
            or order.delivery_partner.user.email
            if order.delivery_partner else 'Delivery Partner'
        )
        subject = f'Laundry Picked Up — Order #{order.short_id}'
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;padding:24px;">
          <h2 style="color:#003580;margin-bottom:8px;">Laundry Picked Up ✓</h2>
          <p style="color:#555;margin-bottom:16px;">
            Your laundry has been collected from <strong>{order.hospital.hospital_name}</strong>.
          </p>
          <table style="border-collapse:collapse;width:100%;font-size:14px;">
            <tr><td style="padding:6px 0;color:#888;width:130px;">Order ID</td><td><strong>#{order.short_id}</strong></td></tr>
            <tr><td style="padding:6px 0;color:#888;">Department</td><td>{order.department.department_name if order.department else '—'}</td></tr>
            <tr><td style="padding:6px 0;color:#888;">Items Collected</td><td><strong>{scanned_count}</strong></td></tr>
            <tr><td style="padding:6px 0;color:#888;">Collected By</td><td>{partner_name}</td></tr>
          </table>
          <p style="color:#555;margin-top:16px;">Items are on their way to the laundry plant.</p>
          <p style="color:#999;font-size:12px;margin-top:12px;">Track real-time progress in your Hospital Portal.</p>
        </div>
        """
        to_name = order.hospital.user.full_name or order.hospital.hospital_name
        send_email(hospital_email, to_name, subject, html)
    except Exception as exc:
        logger.warning('pickup_confirmation email failed for order %s: %s', order.order_id, exc)


def send_delivery_confirmation(order: LaundryOrder, scanned_count: int):
    try:
        hospital_email = order.hospital.user.email
        partner_name = (
            order.delivery_partner.user.full_name
            or order.delivery_partner.user.email
            if order.delivery_partner else 'Delivery Partner'
        )
        subject = f'Clean Laundry Delivered — Order #{order.short_id}'
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;padding:24px;">
          <h2 style="color:#003580;margin-bottom:8px;">Laundry Delivered ✓</h2>
          <p style="color:#555;margin-bottom:16px;">
            Your clean laundry has been returned to <strong>{order.hospital.hospital_name}</strong>.
          </p>
          <table style="border-collapse:collapse;width:100%;font-size:14px;">
            <tr><td style="padding:6px 0;color:#888;width:130px;">Order ID</td><td><strong>#{order.short_id}</strong></td></tr>
            <tr><td style="padding:6px 0;color:#888;">Department</td><td>{order.department.department_name if order.department else '—'}</td></tr>
            <tr><td style="padding:6px 0;color:#888;">Items Delivered</td><td><strong>{scanned_count}</strong></td></tr>
            <tr><td style="padding:6px 0;color:#888;">Delivered By</td><td>{partner_name}</td></tr>
          </table>
          <p style="color:#555;margin-top:16px;">
            Please verify the items received and confirm delivery in your Hospital Portal.
          </p>
          <p style="color:#999;font-size:12px;margin-top:12px;">Log in to confirm and close this order.</p>
        </div>
        """
        to_name = order.hospital.user.full_name or order.hospital.hospital_name
        send_email(hospital_email, to_name, subject, html)
    except Exception as exc:
        logger.warning('delivery_confirmation email failed for order %s: %s', order.order_id, exc)
