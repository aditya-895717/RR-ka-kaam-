import logging

from django.db import transaction
from django.utils import timezone

from hospital.models import ItemStatus, LaundryOrder, OrderItem, OrderStatus
from notifications.brevo import send_pickup_notification, send_delivery_notification
from .models import ReconciliationLog, RFIDScanEvent, ScanPoint

logger = logging.getLogger(__name__)


# ─── Custom exceptions ────────────────────────────────────────────────────────

class TransitLossFlag(Exception):
    """Raised after S2 reconciliation when one or more items are missing."""
    def __init__(self, result: dict):
        self.result = result
        super().__init__(
            f"Transit loss: {len(result.get('missing', []))} item(s) missing"
        )


class DeliveryLossFlag(Exception):
    """Raised after S4 reconciliation when one or more items are missing."""
    def __init__(self, result: dict):
        self.result = result
        super().__init__(
            f"Delivery loss: {len(result.get('missing', []))} item(s) missing"
        )


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_order(order_id) -> LaundryOrder:
    try:
        return LaundryOrder.objects.select_related(
            'hospital__user', 'delivery_partner__user', 'laundry_partner',
        ).get(order_id=order_id)
    except LaundryOrder.DoesNotExist:
        raise ValueError(f'Order {order_id} not found.')


def _normalise_tags(tag_list: list) -> list:
    return [t.strip().upper() for t in tag_list if str(t).strip()]


def _items_for_order(order: LaundryOrder, tags: list) -> dict:
    """Return {tag_number: OrderItem} for tags that belong to this order."""
    return {
        item.tag_number: item
        for item in OrderItem.objects.filter(order=order, tag_number__in=tags)
    }


def _validate_all_tags(order: LaundryOrder, tags: list) -> dict:
    """Raise ValueError if any tag is not in this order. Return items_map."""
    items_map = _items_for_order(order, tags)
    missing = [t for t in tags if t not in items_map]
    if missing:
        raise ValueError(f'Tags not found in order {order.short_id}: {missing}')
    return items_map


def _dp_name(order: LaundryOrder) -> str:
    dp = order.delivery_partner
    if not dp:
        return ''
    return dp.user.full_name or dp.user.email


# ─── Scan point processors ────────────────────────────────────────────────────

def process_s1_pickup(order_id, tag_list: list, scanned_by_user) -> dict:
    """
    S1 — Pickup at hospital.
    Validates every tag belongs to the order, creates scan events,
    sets items IN_TRANSIT_OUTBOUND, order → PICKUP_DONE.
    Raises ValueError on invalid tags.
    """
    order = _get_order(order_id)
    tags = _normalise_tags(tag_list)
    items_map = _validate_all_tags(order, tags)
    now = timezone.now()

    with transaction.atomic():
        RFIDScanEvent.objects.bulk_create([
            RFIDScanEvent(
                tag_number=tag,
                order_item=items_map[tag],
                scan_point=ScanPoint.S1_PICKUP,
                scanned_by=scanned_by_user,
                order=order,
                location_note='Hospital — Pickup',
            )
            for tag in tags
        ])
        OrderItem.objects.filter(
            pk__in=[items_map[t].pk for t in tags]
        ).update(
            current_status=ItemStatus.IN_TRANSIT_OUTBOUND,
            last_scanned_at=now,
        )
        order.status = OrderStatus.PICKUP_DONE
        order.save(update_fields=['status', 'updated_at'])

    try:
        send_pickup_notification(order, tags, _dp_name(order))
    except Exception:
        logger.exception('S1 email failed for order %s', order_id)

    return {
        'success': True,
        'scan_point': ScanPoint.S1_PICKUP,
        'scanned_count': len(tags),
        'order_id': str(order.order_id),
    }


def process_s2_received(order_id, tag_list: list, scanned_by_user) -> dict:
    """
    S2 — Received at laundry plant.
    Reconciles against S1 events. Creates ReconciliationLog.
    Raises TransitLossFlag (after DB commit) if any S1 tags are absent.
    """
    order = _get_order(order_id)
    tags = _normalise_tags(tag_list)
    now = timezone.now()

    expected_tags: set = set(
        RFIDScanEvent.objects
        .filter(order=order, scan_point=ScanPoint.S1_PICKUP)
        .values_list('tag_number', flat=True)
        .distinct()
    )

    received_set = set(tags)
    missing_tags = sorted(expected_tags - received_set)
    matched_tags = list(received_set & expected_tags)

    all_tags = list(received_set | expected_tags)
    items_map = _items_for_order(order, all_tags)

    with transaction.atomic():
        events = [
            RFIDScanEvent(
                tag_number=tag,
                order_item=items_map[tag],
                scan_point=ScanPoint.S2_RECEIVED,
                scanned_by=scanned_by_user,
                order=order,
                location_note='Laundry Plant — Received',
            )
            for tag in tags if tag in items_map
        ]
        if events:
            RFIDScanEvent.objects.bulk_create(events)

        if matched_tags:
            OrderItem.objects.filter(
                pk__in=[items_map[t].pk for t in matched_tags if t in items_map]
            ).update(
                current_status=ItemStatus.RECEIVED_AT_PLANT,
                last_scanned_at=now,
            )

        if missing_tags:
            missing_ids = [items_map[t].pk for t in missing_tags if t in items_map]
            if missing_ids:
                OrderItem.objects.filter(pk__in=missing_ids).update(
                    current_status=ItemStatus.TRANSIT_LOSS_FLAG,
                    last_scanned_at=now,
                )

        recon = ReconciliationLog.objects.create(
            order=order,
            scan_point_from=ScanPoint.S1_PICKUP,
            scan_point_to=ScanPoint.S2_RECEIVED,
            expected_count=len(expected_tags),
            received_count=len(matched_tags),
            missing_tags=missing_tags,
            is_matched=len(missing_tags) == 0,
        )

        order.status = OrderStatus.AT_LAUNDRY
        order.save(update_fields=['status', 'updated_at'])

    result = {
        'success': True,
        'scan_point': ScanPoint.S2_RECEIVED,
        'received': len(matched_tags),
        'missing': missing_tags,
        'order_id': str(order.order_id),
        'reconciliation_id': recon.pk,
        'is_matched': recon.is_matched,
    }

    if missing_tags:
        raise TransitLossFlag(result)

    return result


def process_s3_dispatch(order_id, tag_list: list, scanned_by_user) -> dict:
    """
    S3 — Dispatch from laundry plant.
    Validates tags, creates scan events, sets items IN_TRANSIT_RETURN,
    order → DISPATCHED. Raises ValueError on invalid tags.
    """
    order = _get_order(order_id)
    tags = _normalise_tags(tag_list)
    items_map = _validate_all_tags(order, tags)
    now = timezone.now()

    with transaction.atomic():
        RFIDScanEvent.objects.bulk_create([
            RFIDScanEvent(
                tag_number=tag,
                order_item=items_map[tag],
                scan_point=ScanPoint.S3_DISPATCH,
                scanned_by=scanned_by_user,
                order=order,
                location_note='Laundry Plant — Dispatch',
            )
            for tag in tags
        ])
        OrderItem.objects.filter(
            pk__in=[items_map[t].pk for t in tags]
        ).update(
            current_status=ItemStatus.IN_TRANSIT_RETURN,
            last_scanned_at=now,
        )
        order.status = OrderStatus.DISPATCHED
        order.save(update_fields=['status', 'updated_at'])

    return {
        'success': True,
        'scan_point': ScanPoint.S3_DISPATCH,
        'dispatched_count': len(tags),
        'order_id': str(order.order_id),
    }


def process_s4_delivery(order_id, tag_list: list, scanned_by_user) -> dict:
    """
    S4 — Delivery at hospital.
    Reconciles against S3 events. Creates ReconciliationLog.
    Triggers billing. Sends S4 email notification.
    Raises DeliveryLossFlag (after DB commit) if any S3 tags are absent.
    """
    order = _get_order(order_id)
    tags = _normalise_tags(tag_list)
    now = timezone.now()

    expected_tags: set = set(
        RFIDScanEvent.objects
        .filter(order=order, scan_point=ScanPoint.S3_DISPATCH)
        .values_list('tag_number', flat=True)
        .distinct()
    )

    received_set = set(tags)
    missing_tags = sorted(expected_tags - received_set)
    matched_tags = list(received_set & expected_tags)

    all_tags = list(received_set | expected_tags)
    items_map = _items_for_order(order, all_tags)

    with transaction.atomic():
        events = [
            RFIDScanEvent(
                tag_number=tag,
                order_item=items_map[tag],
                scan_point=ScanPoint.S4_DELIVERY,
                scanned_by=scanned_by_user,
                order=order,
                location_note='Hospital — Delivery',
            )
            for tag in tags if tag in items_map
        ]
        if events:
            RFIDScanEvent.objects.bulk_create(events)

        if matched_tags:
            OrderItem.objects.filter(
                pk__in=[items_map[t].pk for t in matched_tags if t in items_map]
            ).update(
                current_status=ItemStatus.DELIVERED,
                last_scanned_at=now,
            )

        recon = ReconciliationLog.objects.create(
            order=order,
            scan_point_from=ScanPoint.S3_DISPATCH,
            scan_point_to=ScanPoint.S4_DELIVERY,
            expected_count=len(expected_tags),
            received_count=len(matched_tags),
            missing_tags=missing_tags,
            is_matched=len(missing_tags) == 0,
        )

        order.status = OrderStatus.DELIVERED
        order.save(update_fields=['status', 'updated_at'])

    try:
        from billing.utils import create_invoice_for_order
        create_invoice_for_order(order)
    except Exception:
        logger.exception('Billing trigger failed for order %s', order_id)

    try:
        send_delivery_notification(order, matched_tags, missing_tags, _dp_name(order))
    except Exception:
        logger.exception('S4 email failed for order %s', order_id)

    result = {
        'success': True,
        'scan_point': ScanPoint.S4_DELIVERY,
        'delivered': len(matched_tags),
        'missing': missing_tags,
        'order_id': str(order.order_id),
        'reconciliation_id': recon.pk,
        'is_matched': recon.is_matched,
    }

    if missing_tags:
        raise DeliveryLossFlag(result)

    return result
