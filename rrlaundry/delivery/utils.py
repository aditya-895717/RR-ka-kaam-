"""
delivery/utils.py — DeliveryJob lifecycle helpers.

Scan processing does NOT live here. It used to: this module carried
process_pickup_scan / process_delivery_scan, a second implementation of S1/S4
that ran in parallel with rfid/engine.py and was the one the portal actually
called. That copy wrote no RFIDScanEvent and no ReconciliationLog, never set
TRANSIT_LOSS_FLAG, and left a clean S4 order in DELIVERED where the engine
leaves it COMPLETED — so the audit trail and reconciliation the system exists
to provide were silently absent for every scan made through the UI.

delivery/views.py and delivery/api.py now delegate to rfid.engine, which is the
single scan implementation. The S1/S4 notification emails moved with it: they
are sent by rfid.engine via notifications.brevo.send_pickup_notification /
send_delivery_notification, so there is exactly one email per scan event. The
inline send_pickup_confirmation / send_delivery_confirmation that used to live
here were deleted rather than left dormant.

What remains here is job bookkeeping, which the engine has no concept of.
"""

import logging

from django.utils import timezone

from hospital.models import LaundryOrder

from .models import DeliveryJob, JobStatus, JobType

logger = logging.getLogger(__name__)


def complete_job(job: DeliveryJob) -> DeliveryJob:
    """
    Mark a delivery job finished.

    rfid.engine operates on orders and items and has no concept of DeliveryJob,
    so job bookkeeping stays here — it used to live inside the local scan
    processors the engine replaced.
    """
    job.status = JobStatus.COMPLETED
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'completed_at'])
    return job


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
