import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

ALERT_THRESHOLD_MINUTES = 60


def check_missing_items():
    """
    Runs every 5 minutes (django-q2 schedule).
    Finds OrderItems stuck in an in-progress laundry stage for > 60 minutes
    and creates a MissingItemAlert if one does not already exist.
    """
    from django.db.models import OuterRef, Subquery
    from hospital.models import ItemStatus, OrderItem
    from laundry.models import (
        IN_PROGRESS_STAGES, FloorStage, ItemStageLog, MissingItemAlert,
        WorkerItemAssignment,
    )

    now = timezone.now()
    threshold = now - timezone.timedelta(minutes=ALERT_THRESHOLD_MINUTES)

    # Latest log per item via subquery
    latest_log_sub = ItemStageLog.objects.filter(
        order_item=OuterRef('pk'),
    ).order_by('-updated_at')

    # Items at the laundry with a floor stage log
    items_at_laundry = (
        OrderItem.objects
        .filter(current_status__in=[
            ItemStatus.AT_LAUNDRY,
            ItemStatus.WASHED,
            ItemStatus.RECEIVED_AT_PLANT,
        ])
        .annotate(
            latest_stage=Subquery(latest_log_sub.values('stage')[:1]),
            latest_log_at=Subquery(latest_log_sub.values('updated_at')[:1]),
        )
        .filter(
            latest_stage__in=list(IN_PROGRESS_STAGES),   # not READY yet
            latest_log_at__lt=threshold,                  # last update > 60m ago
            latest_log_at__isnull=False,
        )
    )

    created_count = 0
    for item in items_at_laundry:
        already_alerted = MissingItemAlert.objects.filter(
            order_item=item, is_resolved=False,
        ).exists()
        if already_alerted:
            continue

        # Fetch the first worker if assigned
        first_wa = WorkerItemAssignment.objects.filter(
            order_item=item, is_first_worker=True,
        ).select_related('worker').first()

        alert = MissingItemAlert.objects.create(
            order_item=item,
            last_stage=item.latest_stage,
            last_updated_at=item.latest_log_at,
            assigned_worker=first_wa.worker if first_wa else None,
        )
        created_count += 1

        # Notify laundry admin via dashboard bell
        try:
            from notifications.models import DashboardNotification, NotificationType
            laundry_admin = item.order.laundry_partner.user if item.order.laundry_partner else None
            if laundry_admin:
                DashboardNotification.objects.create(
                    recipient=laundry_admin,
                    title=f'Missing Item: {item.tag_number}',
                    message=(
                        f'Item {item.tag_number} has been idle at stage '
                        f'"{alert.get_last_stage_display()}" for over 1 hour. '
                        f'Last updated: {item.latest_log_at.strftime("%d %b %Y, %H:%M")}.'
                    ),
                    tag_number=item.tag_number,
                    notification_type=NotificationType.MISSING_ITEM,
                )
        except Exception:
            logger.exception('Failed to create dashboard notification for alert %s', alert.pk)

        logger.warning(
            'MissingItemAlert created: tag=%s last_stage=%s last_updated=%s',
            item.tag_number,
            item.latest_stage,
            item.latest_log_at,
        )

    if created_count:
        logger.info('check_missing_items: created %d new alert(s).', created_count)
    else:
        logger.debug('check_missing_items: no new alerts.')

    return created_count
