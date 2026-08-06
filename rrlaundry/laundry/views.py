import secrets
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import OuterRef, Subquery, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.forms import AdminCreateWorkerForm
from accounts.models import LaundryProfile, LaundryWorkerProfile, Role, User
from hospital.models import ItemStatus, LaundryOrder, OrderItem, OrderStatus

from .forms import PricingForm, StageUpdateForm
from .models import (
    FloorStage, IN_PROGRESS_STAGES, STAGE_TO_ITEM_STATUS,
    ItemStageLog, MissingItemAlert, WorkerItemAssignment,
)

_FLOOR_STATUSES = [ItemStatus.AT_LAUNDRY, ItemStatus.WASHED]


def _get_laundry_profile(user):
    try:
        return user.laundry_profile
    except LaundryProfile.DoesNotExist:
        pass
    try:
        return user.laundry_worker_profile.laundry
    except (LaundryWorkerProfile.DoesNotExist, AttributeError):
        pass
    return None


def _time_str(delta_seconds):
    s = int(delta_seconds)
    if s < 60:
        return f'{s}s'
    if s < 3600:
        return f'{s // 60}m'
    return f'{s // 3600}h {(s % 3600) // 60}m'


@method_decorator(login_required, name='dispatch')
class LaundryViewMixin(View):
    laundry_admin_only = False

    def dispatch(self, request, *args, **kwargs):
        role = request.user.role
        if role not in (Role.LAUNDRY_ADMIN, Role.LAUNDRY_WORKER):
            raise PermissionDenied
        if self.laundry_admin_only and role != Role.LAUNDRY_ADMIN:
            raise PermissionDenied
        self.profile = _get_laundry_profile(request.user)
        if not self.profile:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _unresolved_alert_count(self):
        return MissingItemAlert.objects.filter(
            order_item__order__laundry_partner=self.profile,
            is_resolved=False,
        ).count()

    def ctx(self, **extra):
        base = {
            'profile': self.profile,
            'unresolved_alerts': self._unresolved_alert_count(),
        }
        base.update(extra)
        return base


# ─────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────

class LaundryDashboardView(LaundryViewMixin):
    def get(self, request):
        today = timezone.localdate()

        # Items physically on the floor (AT_LAUNDRY or WASHED)
        floor_items = OrderItem.objects.filter(
            order__laundry_partner=self.profile,
            current_status__in=_FLOOR_STATUSES,
        )

        # Latest stage per item via subquery
        latest_stage_sub = ItemStageLog.objects.filter(
            order_item=OuterRef('pk'),
        ).order_by('-updated_at').values('stage')[:1]

        floor_items_annotated = floor_items.annotate(floor_stage=Subquery(latest_stage_sub))

        # Stage counts
        stage_counts = {}
        for stage_val, _label in FloorStage.choices:
            stage_counts[stage_val] = 0
        for item in floor_items_annotated:
            s = item.floor_stage
            if s and s in stage_counts:
                stage_counts[s] += 1

        # Active orders (not completed or dispatched)
        active_orders = LaundryOrder.objects.filter(
            laundry_partner=self.profile,
            status__in=['CREATED', 'PICKUP_DONE', 'AT_LAUNDRY'],
        ).count()

        # Unresolved alerts for items at this laundry
        unresolved_alerts = MissingItemAlert.objects.filter(
            order_item__in=floor_items,
            is_resolved=False,
        ).count()

        # Today's received: first stage log RECEIVED created today for items at this laundry
        my_item_ids = OrderItem.objects.filter(
            order__laundry_partner=self.profile,
        ).values_list('id', flat=True)

        received_today = ItemStageLog.objects.filter(
            order_item_id__in=my_item_ids,
            stage=FloorStage.RECEIVED,
            updated_at__date=today,
        ).values('order_item_id').distinct().count()

        # Today's dispatched orders
        dispatched_today = LaundryOrder.objects.filter(
            laundry_partner=self.profile,
            status='DISPATCHED',
            updated_at__date=today,
        ).count()

        # Recent stage activity (last 10 logs)
        recent_logs = ItemStageLog.objects.filter(
            order_item__in=floor_items,
        ).select_related('order_item', 'updated_by').order_by('-updated_at')[:10]

        return render(request, 'laundry/dashboard.html', self.ctx(
            stage_counts=stage_counts,
            floor_stage_labels={v: l for v, l in FloorStage.choices},
            active_orders=active_orders,
            unresolved_alerts=unresolved_alerts,
            received_today=received_today,
            dispatched_today=dispatched_today,
            total_on_floor=floor_items.count(),
            recent_logs=recent_logs,
        ))


# ─────────────────────────────────────────────────────────────
# Processing Floor
# ─────────────────────────────────────────────────────────────

class ProcessingFloorView(LaundryViewMixin):
    def get(self, request):
        latest_log_sub = ItemStageLog.objects.filter(
            order_item=OuterRef('pk'),
        ).order_by('-updated_at')

        items = (
            OrderItem.objects
            .filter(
                order__laundry_partner=self.profile,
                current_status__in=_FLOOR_STATUSES,
            )
            .select_related('order__hospital', 'order', 'department')
            .annotate(
                floor_stage=Subquery(latest_log_sub.values('stage')[:1]),
                stage_updated_at=Subquery(latest_log_sub.values('updated_at')[:1]),
            )
        )

        # Alert set
        alert_item_ids = set(
            MissingItemAlert.objects.filter(
                is_resolved=False,
                order_item__in=items,
            ).values_list('order_item_id', flat=True)
        )

        # First-worker map
        first_worker_map = {
            wa.order_item_id: wa.worker
            for wa in WorkerItemAssignment.objects.filter(
                is_first_worker=True,
                order_item__in=items,
            ).select_related('worker')
        }

        # Workers list for the assign-worker dropdown
        workers = LaundryWorkerProfile.objects.filter(
            laundry=self.profile,
        ).select_related('user')

        # Group by stage
        grouped = OrderedDict()
        for stage_val, stage_label in FloorStage.choices:
            grouped[stage_val] = {'label': stage_label, 'items': []}

        now = timezone.now()
        for item in items:
            item.has_alert = item.pk in alert_item_ids
            item.first_worker = first_worker_map.get(item.pk)
            item.needs_worker = (
                item.floor_stage == FloorStage.WASHING
                and item.pk not in first_worker_map
            )
            if item.stage_updated_at:
                secs = (now - item.stage_updated_at).total_seconds()
                item.time_in_stage_str = _time_str(secs)
                item.stale = secs > 3600
            else:
                item.time_in_stage_str = '—'
                item.stale = False

            stage = item.floor_stage or FloorStage.RECEIVED
            if stage in grouped:
                grouped[stage]['items'].append(item)

        return render(request, 'laundry/processing_floor.html', self.ctx(
            grouped=grouped,
            workers=workers,
            floor_stage_labels={v: l for v, l in FloorStage.choices},
            total_items=items.count(),
            alert_count=len(alert_item_ids),
        ))


# ─────────────────────────────────────────────────────────────
# Update Item Stage (POST)
# ─────────────────────────────────────────────────────────────

class UpdateItemStageView(LaundryViewMixin):
    def post(self, request):
        form = StageUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Invalid stage update request.')
            return redirect('laundry_floor')

        tag_number = form.cleaned_data['tag_number']
        new_stage  = form.cleaned_data['new_stage']
        worker_id  = form.cleaned_data.get('worker_id')
        notes      = form.cleaned_data.get('notes', '')

        item = get_object_or_404(
            OrderItem,
            tag_number=tag_number,
            order__laundry_partner=self.profile,
        )

        # If moving to WASHING and no first_worker yet, worker_id is required
        if new_stage == FloorStage.WASHING:
            has_first_worker = WorkerItemAssignment.objects.filter(
                order_item=item, is_first_worker=True,
            ).exists()
            if not has_first_worker:
                if not worker_id:
                    messages.error(
                        request,
                        f'Tag {tag_number}: assign a worker before moving to Washing.',
                    )
                    return redirect('laundry_floor')
                try:
                    worker = User.objects.get(
                        pk=worker_id,
                        laundry_worker_profile__laundry=self.profile,
                    )
                except User.DoesNotExist:
                    messages.error(request, 'Selected worker not found.')
                    return redirect('laundry_floor')
                WorkerItemAssignment.objects.create(
                    order_item=item,
                    worker=worker,
                    is_first_worker=True,
                )

        # Create stage log
        ItemStageLog.objects.create(
            order_item=item,
            stage=new_stage,
            updated_by=request.user,
            notes=notes,
        )

        # Update OrderItem.current_status and reset the stale-alert clock
        new_item_status = STAGE_TO_ITEM_STATUS.get(new_stage)
        if new_item_status:
            item.current_status = new_item_status
        item.last_scanned_at = timezone.now()
        item.save(update_fields=['current_status', 'last_scanned_at'])

        messages.success(request, f'Tag {tag_number} moved to {new_stage}.')
        return redirect('laundry_floor')


# ─────────────────────────────────────────────────────────────
# Pricing
# ─────────────────────────────────────────────────────────────

class PricingView(LaundryViewMixin):
    laundry_admin_only = True

    def get(self, request):
        form = PricingForm(initial={'price_per_item': self.profile.price_per_item})
        return render(request, 'laundry/pricing.html', self.ctx(form=form))

    def post(self, request):
        form = PricingForm(request.POST)
        if form.is_valid():
            new_price = form.cleaned_data['price_per_item']
            old_price = self.profile.price_per_item
            self.profile.price_per_item = new_price
            self.profile.save(update_fields=['price_per_item'])
            messages.success(
                request,
                f'Price updated from ₹{old_price} to ₹{new_price}. '
                'Applies to new orders only.',
            )
            return redirect('laundry_pricing')
        return render(request, 'laundry/pricing.html', self.ctx(form=form))


# ─────────────────────────────────────────────────────────────
# Worker Management
# ─────────────────────────────────────────────────────────────

class WorkerManagementView(LaundryViewMixin):
    laundry_admin_only = True

    def _worker_data(self):
        worker_profiles = (
            LaundryWorkerProfile.objects
            .filter(laundry=self.profile)
            .select_related('user')
        )
        floor_items = OrderItem.objects.filter(
            order__laundry_partner=self.profile,
            current_status__in=_FLOOR_STATUSES,
        )
        worker_item_map = {}
        for wp in worker_profiles:
            assigned_items = WorkerItemAssignment.objects.filter(
                worker=wp.user,
                order_item__in=floor_items,
                is_first_worker=True,
            ).select_related('order_item', 'order_item__order__hospital')
            worker_item_map[wp.user_id] = list(assigned_items)
        return worker_profiles, worker_item_map

    def get(self, request):
        worker_profiles, worker_item_map = self._worker_data()
        return render(request, 'laundry/workers.html', self.ctx(
            worker_profiles=worker_profiles,
            worker_item_map=worker_item_map,
            form=AdminCreateWorkerForm(),
        ))

    def post(self, request):
        form = AdminCreateWorkerForm(request.POST)
        if not form.is_valid():
            worker_profiles, worker_item_map = self._worker_data()
            return render(request, 'laundry/workers.html', self.ctx(
                worker_profiles=worker_profiles,
                worker_item_map=worker_item_map,
                form=form,
            ))
        cd = form.cleaned_data
        password = secrets.token_urlsafe(10)
        with transaction.atomic():
            user = User.objects.create_user(
                email=cd['email'],
                password=password,
                full_name=cd['full_name'],
                phone_number=cd.get('phone_number', ''),
                role=Role.LAUNDRY_WORKER,
                is_onboarded=True,
            )
            LaundryWorkerProfile.objects.create(
                user=user,
                laundry=self.profile,
                phone_number=cd.get('phone_number', ''),
            )
        messages.success(
            request,
            f'Worker account created for {cd["full_name"] or cd["email"]}. '
            f'Temporary password: {password} — share securely (shown once).',
        )
        return redirect('laundry_workers')


class DeactivateWorkerView(LaundryViewMixin):
    laundry_admin_only = True

    def post(self, request, user_id):
        wp = get_object_or_404(LaundryWorkerProfile, user_id=user_id, laundry=self.profile)
        wp.user.is_active = False
        wp.user.save(update_fields=['is_active'])
        messages.success(request, f'{wp.user.full_name or wp.user.email} has been deactivated.')
        return redirect('laundry_workers')


class ReactivateWorkerView(LaundryViewMixin):
    laundry_admin_only = True

    def post(self, request, user_id):
        wp = get_object_or_404(LaundryWorkerProfile, user_id=user_id, laundry=self.profile)
        wp.user.is_active = True
        wp.user.save(update_fields=['is_active'])
        messages.success(request, f'{wp.user.full_name or wp.user.email} has been reactivated.')
        return redirect('laundry_workers')


# ─────────────────────────────────────────────────────────────
# Alerts
# ─────────────────────────────────────────────────────────────

class AlertsView(LaundryViewMixin):
    def get(self, request):
        my_item_ids = OrderItem.objects.filter(
            order__laundry_partner=self.profile,
        ).values_list('id', flat=True)

        active_alerts = (
            MissingItemAlert.objects
            .filter(order_item_id__in=my_item_ids, is_resolved=False)
            .select_related('order_item__order__hospital', 'assigned_worker')
            .order_by('-triggered_at')
        )

        resolved_alerts = (
            MissingItemAlert.objects
            .filter(order_item_id__in=my_item_ids, is_resolved=True)
            .select_related('order_item__order__hospital', 'assigned_worker')
            .order_by('-resolved_at')[:30]
        )

        now = timezone.now()
        for alert in active_alerts:
            alert.stale_str     = _time_str((now - alert.last_updated_at).total_seconds())
            alert.triggered_str = _time_str((now - alert.triggered_at).total_seconds())

        return render(request, 'laundry/alerts.html', self.ctx(
            active_alerts=active_alerts,
            resolved_alerts=resolved_alerts,
            now=now,
        ))

    def post(self, request):
        alert_id = request.POST.get('alert_id')
        alert = get_object_or_404(
            MissingItemAlert,
            pk=alert_id,
            order_item__order__laundry_partner=self.profile,
        )
        alert.resolve()
        messages.success(
            request,
            f'Alert for tag {alert.order_item.tag_number} marked as resolved.',
        )
        return redirect('laundry_alerts')


# ─────────────────────────────────────────────────────────────
# Order List
# ─────────────────────────────────────────────────────────────

class LaundryOrderListView(LaundryViewMixin):
    def get(self, request):
        qs = (
            LaundryOrder.objects
            .filter(laundry_partner=self.profile)
            .select_related('hospital', 'delivery_partner__user')
            .order_by('-created_at')
        )

        status_filter = request.GET.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(request.GET.get('page'))

        from hospital.models import OrderStatus
        return render(request, 'laundry/order_list.html', self.ctx(
            page_obj=page_obj,
            status_filter=status_filter,
            order_status_choices=OrderStatus.choices,
            query_string=f'status={status_filter}',
        ))


# ─────────────────────────────────────────────────────────────
# Scan Items — S2 receive / S3 dispatch
#
# The laundry side of the RFID chain had no UI at all: S2 and S3 were
# reachable only through the raw DRF endpoints, so no human had ever driven
# them. These three views mirror the delivery portal's job-list -> scan-page
# pattern and delegate to rfid.engine, the single scan implementation.
# ─────────────────────────────────────────────────────────────

class ScanItemsView(LaundryViewMixin):
    """Landing page: orders awaiting S2 receive, and orders ready for S3 dispatch."""

    def get(self, request):
        base = LaundryOrder.objects.filter(
            laundry_partner=self.profile,
        ).select_related('hospital', 'department').prefetch_related('items')

        incoming = base.filter(status=OrderStatus.PICKUP_DONE).order_by('created_at')
        ready    = base.filter(status=OrderStatus.AT_LAUNDRY).order_by('created_at')

        # Counts shown per row are the items each scan actually expects, which
        # is not the same as the order's total item count once anything has
        # been flagged as a transit loss.
        for o in incoming:
            o.expected_count = o.items.filter(
                current_status__in=[ItemStatus.PICKUP_SCANNED, ItemStatus.IN_TRANSIT_OUTBOUND],
            ).count()
        for o in ready:
            o.expected_count = o.items.filter(
                current_status__in=[
                    ItemStatus.AT_LAUNDRY, ItemStatus.RECEIVED_AT_PLANT, ItemStatus.WASHED,
                ],
            ).count()

        return render(request, 'laundry/scan_items.html', self.ctx(
            incoming=incoming,
            ready=ready,
        ))


class _LaundryScanBase(LaundryViewMixin):
    """Shared plumbing for the two scan pages."""

    template = None
    expected_statuses = ()
    required_order_status = None
    redirect_name = None

    def _get_order(self, order_id):
        return get_object_or_404(
            LaundryOrder.objects.select_related('hospital', 'department'),
            order_id=order_id,
            laundry_partner=self.profile,
        )

    def _expected_items(self, order):
        return list(
            order.items
            .filter(current_status__in=self.expected_statuses)
            .values('tag_number', 'item_type')
            .order_by('tag_number')
        )

    def _parse_tags(self, request):
        """Returns (tags, error_message)."""
        import json
        raw = request.POST.get('scanned_tags', '[]')
        try:
            tags = json.loads(raw)
            if not isinstance(tags, list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            return None, 'Invalid scan submission — please try again.'

        tags = [str(t).strip().upper() for t in tags if t]
        if not tags:
            return None, 'No items scanned. Scan at least one item before submitting.'
        return tags, None

    def get(self, request, order_id):
        order = self._get_order(order_id)
        if order.status != self.required_order_status:
            messages.info(
                request,
                f'Order #{order.short_id} is {order.get_status_display()} and is not '
                f'awaiting this scan.',
            )
            return redirect('laundry_scan_items')

        return render(request, self.template, self.ctx(
            order=order,
            expected_items=self._expected_items(order),
        ))


class ScanReceiveView(_LaundryScanBase):
    """S2 — receive an inbound consignment at the plant."""

    template = 'laundry/scan_receive.html'
    expected_statuses = (ItemStatus.PICKUP_SCANNED, ItemStatus.IN_TRANSIT_OUTBOUND)
    required_order_status = OrderStatus.PICKUP_DONE

    def post(self, request, order_id):
        from rfid.engine import TransitLossFlag, process_s2_received

        order = self._get_order(order_id)
        tags, err = self._parse_tags(request)
        if err:
            messages.error(request, err)
            return redirect('laundry_scan_receive', order_id=order_id)

        # A short scan is a real outcome, not an error: the engine commits,
        # flags the missing items TRANSIT_LOSS_FLAG, then raises so the caller
        # can report it. Both branches are success paths for the operator.
        try:
            result = process_s2_received(order.order_id, tags, request.user)
        except TransitLossFlag as flag:
            result = flag.result
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('laundry_scan_items')

        if result['unknown_tags']:
            messages.warning(
                request,
                f'{len(result["unknown_tags"])} tag(s) were not expected on this order '
                f'and were ignored: {", ".join(result["unknown_tags"][:5])}.',
            )
        if result['missing_tags']:
            messages.error(
                request,
                f'TRANSIT LOSS — {len(result["missing_tags"])} item(s) did not arrive and '
                f'have been flagged: {", ".join(result["missing_tags"][:5])}.',
            )
        messages.success(
            request,
            f'Received {result["received_count"]} of {result["expected_count"]} item(s) '
            f'for Order #{order.short_id}.',
        )
        return redirect('laundry_scan_items')


class ScanDispatchView(_LaundryScanBase):
    """S3 — dispatch a finished consignment back to the hospital."""

    template = 'laundry/scan_dispatch.html'
    expected_statuses = (
        ItemStatus.AT_LAUNDRY, ItemStatus.RECEIVED_AT_PLANT, ItemStatus.WASHED,
    )
    required_order_status = OrderStatus.AT_LAUNDRY

    def post(self, request, order_id):
        from rfid.engine import process_s3_dispatch

        order = self._get_order(order_id)
        tags, err = self._parse_tags(request)
        if err:
            messages.error(request, err)
            return redirect('laundry_scan_dispatch', order_id=order_id)

        # S3 raises no loss flag — the operator decides what physically ships.
        # Unscanned items simply stay at the plant for a later dispatch.
        try:
            result = process_s3_dispatch(order.order_id, tags, request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('laundry_scan_items')

        if result['unknown_tags']:
            messages.warning(
                request,
                f'{len(result["unknown_tags"])} tag(s) were not eligible for dispatch '
                f'and were ignored: {", ".join(result["unknown_tags"][:5])}.',
            )
        held_back = result['expected_count'] - result['received_count']
        if held_back > 0:
            messages.warning(
                request,
                f'{held_back} item(s) were not scanned and remain at the plant.',
            )
        messages.success(
            request,
            f'Dispatched {result["received_count"]} item(s) for Order #{order.short_id}. '
            f'A delivery job has been created for the return leg.',
        )
        return redirect('laundry_scan_items')
