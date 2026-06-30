from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import LaundryProfile, LaundryWorkerProfile, Role, User
from hospital.models import ItemStatus, LaundryOrder, OrderItem

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

        # Update OrderItem.current_status
        new_item_status = STAGE_TO_ITEM_STATUS.get(new_stage)
        if new_item_status:
            item.current_status = new_item_status
            item.save(update_fields=['current_status'])

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

    def get(self, request):
        worker_profiles = (
            LaundryWorkerProfile.objects
            .filter(laundry=self.profile)
            .select_related('user')
        )

        # Items currently assigned (on the floor) per worker
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

        return render(request, 'laundry/workers.html', self.ctx(
            worker_profiles=worker_profiles,
            worker_item_map=worker_item_map,
        ))


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
