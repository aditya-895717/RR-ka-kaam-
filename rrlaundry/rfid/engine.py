"""
rfid/engine.py — Core RFID scan-processing engine.

Each process_sN_* function:
  - Takes (order_id: UUID, tags: list[str], user: User) -> dict
  - Runs inside a single atomic transaction
  - Creates RFIDScanEvent records for every matched tag
  - Creates a ReconciliationLog comparing expected vs received
  - On a count mismatch raises TransitLossFlag / DeliveryLossFlag;
    the exception carries .result so the API can return HTTP 200
    with the partial-success payload (DB is already committed).

This module is the single scan implementation: delivery/views.py,
delivery/api.py and rfid/api.py all delegate here. It also owns the
S1/S4 notification emails and the invoice trigger (a clean S4 that
leaves the order COMPLETED).

Missing-item detection is NOT here. check_stale_items() used to live
in this module and was a second detector competing with
notifications.jobs.check_missing_items; the two have been consolidated
into the latter, which the /api/notifications/sweep/ endpoint drives.
"""

import logging

from django.db import transaction
from django.utils import timezone

from hospital.models import ItemStatus, LaundryOrder, OrderItem, OrderStatus
from laundry.models import MissingItemAlert

from .models import ReconciliationLog, RFIDScanEvent, ScanPoint

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Exception classes — raised on reconciliation mismatch.
# Both carry a .result dict identical to the success payload so that
# rfid/api.py can return HTTP 200 with the partial-success body.
# ─────────────────────────────────────────────────────────────────────────────

class TransitLossFlag(Exception):
    """Raised by process_s2_received when received count < S1 pickup count."""
    def __init__(self, result: dict):
        self.result = result
        super().__init__(str(result))


class DeliveryLossFlag(Exception):
    """Raised by process_s4_delivery when delivered count < S3 dispatch count."""
    def __init__(self, result: dict):
        self.result = result
        super().__init__(str(result))


# ─────────────────────────────────────────────────────────────────────────────
# Side effects (email + billing)
#
# This engine is the single scan implementation for the whole system —
# delivery/views.py and delivery/api.py delegate here rather than carrying
# their own copies. That makes it the one place S1/S4 notifications fire, so
# there is exactly one email per scan event.
#
# Every side effect below is best-effort: the scan transaction has already
# committed by the time these run, and an email or billing failure must never
# roll back or mask a successful physical scan.
# ─────────────────────────────────────────────────────────────────────────────

def _delivery_partner_name(order) -> str:
    dp = order.delivery_partner
    if not dp:
        return ''
    return dp.user.full_name or dp.user.email


def _notify_pickup(order, scanned_tags):
    try:
        from notifications.brevo import send_pickup_notification
        send_pickup_notification(order, scanned_tags, _delivery_partner_name(order))
    except Exception:
        logger.exception('S1 pickup notification failed for order %s', order.order_id)


def _notify_delivery(order, delivered_tags, missing_tags):
    try:
        from notifications.brevo import send_delivery_notification
        send_delivery_notification(
            order, delivered_tags, missing_tags, _delivery_partner_name(order),
        )
    except Exception:
        logger.exception('S4 delivery notification failed for order %s', order.order_id)


def _generate_invoice_if_complete(order):
    """
    Invoice trigger: a system-verified S4 scan that leaves the order COMPLETED.

    COMPLETED is the terminal state this engine assigns when every dispatched
    item was scanned back in, so it is the single source of truth for billing.
    The hospital's manual 'confirm delivery' button is a receipt acknowledgement
    only and no longer gates invoicing.

    Idempotent: Invoice has a OneToOne on order, so a second S4 (partial
    re-scan) must not attempt a duplicate insert.
    """
    if order.status != OrderStatus.COMPLETED:
        return None
    try:
        from billing.models import Invoice
        if Invoice.objects.filter(order=order).exists():
            return None
        from billing.utils import create_invoice_for_order
        return create_invoice_for_order(order)
    except Exception:
        logger.exception('Invoice generation failed for order %s', order.order_id)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_order(order_id) -> LaundryOrder:
    """Fetch order or raise ValueError (converted to 400 by api.py)."""
    try:
        return LaundryOrder.objects.select_related(
            'hospital', 'laundry_partner', 'delivery_partner',
        ).get(order_id=order_id)
    except LaundryOrder.DoesNotExist:
        raise ValueError(f'Order {order_id} not found.')


def _create_scan_events(order, scan_point, items, user, now):
    """Bulk-create RFIDScanEvent for every matched OrderItem."""
    events = [
        RFIDScanEvent(
            tag_number=item.tag_number,
            order_item=item,
            scan_point=scan_point,
            scanned_by=user,
            order=order,
        )
        for item in items
    ]
    RFIDScanEvent.objects.bulk_create(events)


# ─────────────────────────────────────────────────────────────────────────────
# S1 — Pickup at hospital (DELIVERY_PARTNER)
# ─────────────────────────────────────────────────────────────────────────────

def process_s1_pickup(order_id, tags: list, user) -> dict:
    """
    S1 — Pickup at hospital.

    Expected: all items belonging to the order (status WITH_HOSPITAL or any
    earlier state — operator scans what they physically collect).
    Matched items → PICKUP_SCANNED.
    Order → PICKUP_DONE when all items are scanned.
    No mismatch exception at S1; creates a ReconciliationLog for audit.
    """
    order = _get_order(order_id)

    if order.status not in (OrderStatus.CREATED, OrderStatus.PICKUP_DONE):
        raise ValueError(
            f'Order {order.short_id} is in status {order.status}; '
            'S1 pickup expects CREATED or PICKUP_DONE.'
        )

    now = timezone.now()
    tags_set = set(tags)

    with transaction.atomic():
        # Lock items belonging to this order for update
        all_items = list(
            OrderItem.objects.select_for_update()
            .filter(order=order)
        )
        item_map = {item.tag_number: item for item in all_items}

        matched_items = []
        unknown_tags = []

        for tag in tags:
            item = item_map.get(tag)
            if item:
                item.current_status = ItemStatus.PICKUP_SCANNED
                item.last_scanned_at = now
                matched_items.append(item)
            else:
                unknown_tags.append(tag)

        if matched_items:
            OrderItem.objects.bulk_update(
                matched_items, ['current_status', 'last_scanned_at']
            )

        _create_scan_events(order, ScanPoint.S1_PICKUP, matched_items, user, now)

        expected_count = len(all_items)
        received_count = len(matched_items)
        missing_tags = [t for t in item_map if t not in tags_set]

        ReconciliationLog.objects.create(
            order=order,
            scan_point_from=ScanPoint.S1_PICKUP,
            scan_point_to=ScanPoint.S1_PICKUP,
            expected_count=expected_count,
            received_count=received_count,
            missing_tags=missing_tags,
            is_matched=(received_count == expected_count),
        )

        # Advance order status if all items are picked up
        if not OrderItem.objects.filter(
            order=order,
            current_status=ItemStatus.WITH_HOSPITAL,
        ).exists():
            order.status = OrderStatus.PICKUP_DONE
            order.save(update_fields=['status', 'updated_at'])

    result = {
        'scan_point': 'S1_PICKUP',
        'order_id': str(order_id),
        'order_short_id': order.short_id,
        'expected_count': expected_count,
        'received_count': received_count,
        'missing_tags': missing_tags,
        'unknown_tags': unknown_tags,
        'is_matched': received_count == expected_count,
        'order_status': order.status,
    }

    _notify_pickup(order, [item.tag_number for item in matched_items])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# S2 — Received at laundry plant (LAUNDRY_ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

def process_s2_received(order_id, tags: list, user) -> dict:
    """
    S2 — Received at laundry plant.

    Expected: items in PICKUP_SCANNED / IN_TRANSIT_OUTBOUND state.
    Matched items → AT_LAUNDRY (= RECEIVED_AT_PLANT in item status).
    Missing (expected but not scanned) → TRANSIT_LOSS_FLAG.
    Order → AT_LAUNDRY.
    Raises TransitLossFlag on any mismatch (DB already committed).
    """
    order = _get_order(order_id)

    if order.status not in (OrderStatus.PICKUP_DONE, OrderStatus.AT_LAUNDRY):
        raise ValueError(
            f'Order {order.short_id} is in status {order.status}; '
            'S2 received expects PICKUP_DONE.'
        )

    now = timezone.now()
    tags_set = set(tags)

    with transaction.atomic():
        # Items we expect at S2: those picked up at S1
        expected_items = list(
            OrderItem.objects.select_for_update()
            .filter(
                order=order,
                current_status__in=[
                    ItemStatus.PICKUP_SCANNED,
                    ItemStatus.IN_TRANSIT_OUTBOUND,
                ],
            )
        )
        item_map = {item.tag_number: item for item in expected_items}

        matched_items = []
        missing_items = []  # Expected at S2 but not scanned
        unknown_tags = []   # Scanned but not expected

        for tag in tags:
            item = item_map.get(tag)
            if item:
                item.current_status = ItemStatus.RECEIVED_AT_PLANT
                item.last_scanned_at = now
                matched_items.append(item)
            else:
                unknown_tags.append(tag)

        for tag, item in item_map.items():
            if tag not in tags_set:
                item.current_status = ItemStatus.TRANSIT_LOSS_FLAG
                item.last_scanned_at = now
                missing_items.append(item)

        items_to_update = matched_items + missing_items
        if items_to_update:
            OrderItem.objects.bulk_update(
                items_to_update, ['current_status', 'last_scanned_at']
            )

        _create_scan_events(order, ScanPoint.S2_RECEIVED, matched_items, user, now)

        expected_count = len(expected_items)
        received_count = len(matched_items)
        missing_tag_numbers = [item.tag_number for item in missing_items]

        ReconciliationLog.objects.create(
            order=order,
            scan_point_from=ScanPoint.S1_PICKUP,
            scan_point_to=ScanPoint.S2_RECEIVED,
            expected_count=expected_count,
            received_count=received_count,
            missing_tags=missing_tag_numbers,
            is_matched=(received_count == expected_count),
        )

        order.status = OrderStatus.AT_LAUNDRY
        order.save(update_fields=['status', 'updated_at'])

    result = {
        'scan_point': 'S2_RECEIVED',
        'order_id': str(order_id),
        'order_short_id': order.short_id,
        'expected_count': expected_count,
        'received_count': received_count,
        'missing_tags': missing_tag_numbers,
        'unknown_tags': unknown_tags,
        'is_matched': received_count == expected_count,
        'order_status': order.status,
    }

    if missing_items:
        raise TransitLossFlag(result)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# S3 — Dispatch from laundry plant (LAUNDRY_ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

def process_s3_dispatch(order_id, tags: list, user) -> dict:
    """
    S3 — Dispatch from laundry plant.

    Accepts tags currently in internal laundry stages
    (AT_LAUNDRY, RECEIVED_AT_PLANT, WASHED).
    Items NOT in TRANSIT_LOSS_FLAG are eligible.
    Matched items → DISPATCHED.
    Order → DISPATCHED.
    No mismatch exception — operator chooses which items to dispatch.
    """
    order = _get_order(order_id)

    if order.status not in (
        OrderStatus.AT_LAUNDRY,
        OrderStatus.PICKUP_DONE,   # Edge case: S2 skipped in testing
        OrderStatus.DISPATCHED,    # Allow partial re-dispatch
    ):
        raise ValueError(
            f'Order {order.short_id} is in status {order.status}; '
            'S3 dispatch expects AT_LAUNDRY.'
        )

    now = timezone.now()
    dispatchable_statuses = [
        ItemStatus.AT_LAUNDRY,
        ItemStatus.RECEIVED_AT_PLANT,
        ItemStatus.WASHED,
    ]

    with transaction.atomic():
        eligible_items = list(
            OrderItem.objects.select_for_update()
            .filter(order=order, current_status__in=dispatchable_statuses)
        )
        item_map = {item.tag_number: item for item in eligible_items}

        matched_items = []
        unknown_tags = []

        for tag in tags:
            item = item_map.get(tag)
            if item:
                item.current_status = ItemStatus.DISPATCHED
                item.last_scanned_at = now
                matched_items.append(item)
            else:
                unknown_tags.append(tag)

        if matched_items:
            OrderItem.objects.bulk_update(
                matched_items, ['current_status', 'last_scanned_at']
            )

        _create_scan_events(order, ScanPoint.S3_DISPATCH, matched_items, user, now)

        expected_count = len(eligible_items)
        received_count = len(matched_items)

        ReconciliationLog.objects.create(
            order=order,
            scan_point_from=ScanPoint.S2_RECEIVED,
            scan_point_to=ScanPoint.S3_DISPATCH,
            expected_count=expected_count,
            received_count=received_count,
            missing_tags=[t for t in item_map if t not in set(tags)],
            is_matched=(received_count == expected_count),
        )

        order.status = OrderStatus.DISPATCHED
        order.save(update_fields=['status', 'updated_at'])

        # S3 is the only place an order becomes DISPATCHED, so it is the point
        # at which the return leg needs a job. Without this the delivery partner
        # never receives an S4 job and the order can never be delivered.
        # get_or_create inside, so re-dispatching does not duplicate.
        from delivery.utils import create_delivery_job
        create_delivery_job(order)

    result = {
        'scan_point': 'S3_DISPATCH',
        'order_id': str(order_id),
        'order_short_id': order.short_id,
        'expected_count': expected_count,
        'received_count': received_count,
        'unknown_tags': unknown_tags,
        'is_matched': received_count == expected_count,
        'order_status': order.status,
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# S4 — Delivery at hospital (DELIVERY_PARTNER)
# ─────────────────────────────────────────────────────────────────────────────

def process_s4_delivery(order_id, tags: list, user) -> dict:
    """
    S4 — Delivery to hospital.

    Expected: items in DISPATCHED state (set by S3).
    Matched items → DELIVERED.
    Missing items stay DISPATCHED (flagged via DeliveryLossFlag).
    Order → DELIVERED when any items delivered; COMPLETED when all matched.
    Raises DeliveryLossFlag on any mismatch (DB already committed).
    """
    order = _get_order(order_id)

    if order.status not in (OrderStatus.DISPATCHED, OrderStatus.DELIVERED):
        raise ValueError(
            f'Order {order.short_id} is in status {order.status}; '
            'S4 delivery expects DISPATCHED.'
        )

    now = timezone.now()
    tags_set = set(tags)

    with transaction.atomic():
        expected_items = list(
            OrderItem.objects.select_for_update()
            .filter(order=order, current_status=ItemStatus.DISPATCHED)
        )
        item_map = {item.tag_number: item for item in expected_items}

        matched_items = []
        missing_tags = []
        unknown_tags = []

        for tag in tags:
            item = item_map.get(tag)
            if item:
                item.current_status = ItemStatus.DELIVERED
                item.last_scanned_at = now
                matched_items.append(item)
            else:
                unknown_tags.append(tag)

        for tag in item_map:
            if tag not in tags_set:
                missing_tags.append(tag)

        if matched_items:
            OrderItem.objects.bulk_update(
                matched_items, ['current_status', 'last_scanned_at']
            )

        _create_scan_events(order, ScanPoint.S4_DELIVERY, matched_items, user, now)

        expected_count = len(expected_items)
        received_count = len(matched_items)

        ReconciliationLog.objects.create(
            order=order,
            scan_point_from=ScanPoint.S3_DISPATCH,
            scan_point_to=ScanPoint.S4_DELIVERY,
            expected_count=expected_count,
            received_count=received_count,
            missing_tags=missing_tags,
            is_matched=(received_count == expected_count),
        )

        # Advance order status
        if not OrderItem.objects.filter(
            order=order,
            current_status=ItemStatus.DISPATCHED,
        ).exists():
            order.status = OrderStatus.COMPLETED
        else:
            order.status = OrderStatus.DELIVERED
        order.save(update_fields=['status', 'updated_at'])

    result = {
        'scan_point': 'S4_DELIVERY',
        'order_id': str(order_id),
        'order_short_id': order.short_id,
        'expected_count': expected_count,
        'received_count': received_count,
        'missing_tags': missing_tags,
        'unknown_tags': unknown_tags,
        'is_matched': received_count == expected_count,
        'order_status': order.status,
    }

    # Side effects run before the loss flag is raised — the DB is already
    # committed, so a partial delivery must still notify and (if it somehow
    # completed the order) bill, exactly as a clean one would.
    delivered_tags = [item.tag_number for item in matched_items]
    _notify_delivery(order, delivered_tags, missing_tags)
    invoice = _generate_invoice_if_complete(order)
    result['invoice_number'] = invoice.invoice_number if invoice else None

    if missing_tags:
        raise DeliveryLossFlag(result)

    return result
