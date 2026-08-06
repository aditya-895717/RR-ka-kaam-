import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import DeliveryProfile, Role

from rfid.engine import DeliveryLossFlag, process_s1_pickup, process_s4_delivery

from .models import DeliveryJob, JobStatus, JobType
from .utils import complete_job

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class DeliveryViewMixin(View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.role != Role.DELIVERY_PARTNER:
            raise PermissionDenied
        try:
            self.profile = request.user.delivery_profile
        except DeliveryProfile.DoesNotExist:
            return redirect('account_onboarding')
        return super().dispatch(request, *args, **kwargs)

    def ctx(self, **extra):
        return {'profile': self.profile, **extra}


# ─────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────

class DeliveryDashboardView(DeliveryViewMixin):
    def get(self, request):
        today = timezone.localdate()

        base_qs = DeliveryJob.objects.filter(delivery_partner=self.profile)

        pending_pickup = base_qs.filter(
            job_type=JobType.PICKUP,
            status__in=[JobStatus.ASSIGNED, JobStatus.IN_PROGRESS],
        ).select_related('order__hospital').order_by('assigned_at')

        pending_delivery = base_qs.filter(
            job_type=JobType.DELIVERY,
            status__in=[JobStatus.ASSIGNED, JobStatus.IN_PROGRESS],
        ).select_related('order__hospital').order_by('assigned_at')

        completed_today = base_qs.filter(
            status=JobStatus.COMPLETED,
            completed_at__date=today,
        ).count()

        from hospital.models import OrderItem
        items_scanned_today = OrderItem.objects.filter(
            order__delivery_partner=self.profile,
            last_scanned_at__date=today,
        ).count()

        return render(request, 'delivery/dashboard.html', self.ctx(
            pending_pickup=pending_pickup,
            pending_delivery=pending_delivery,
            completed_today=completed_today,
            items_scanned_today=items_scanned_today,
            today=today,
        ))


# ─────────────────────────────────────────────────────────────
# Job List
# ─────────────────────────────────────────────────────────────

class JobListView(DeliveryViewMixin):
    def get(self, request):
        qs = (
            DeliveryJob.objects
            .filter(delivery_partner=self.profile)
            .exclude(status=JobStatus.COMPLETED)
            .select_related('order__hospital', 'order__department')
            .order_by('assigned_at')
        )

        type_filter   = request.GET.get('type', '')
        status_filter = request.GET.get('status', '')

        if type_filter:
            qs = qs.filter(job_type=type_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)

        return render(request, 'delivery/job_list.html', self.ctx(
            jobs=qs,
            type_filter=type_filter,
            status_filter=status_filter,
            job_type_choices=JobType.choices,
            job_status_choices=[(v, l) for v, l in JobStatus.choices if v != JobStatus.COMPLETED],
        ))


# ─────────────────────────────────────────────────────────────
# Scan Pickup (S1)
# ─────────────────────────────────────────────────────────────

class ScanPickupView(DeliveryViewMixin):
    def get(self, request, job_id):
        job = get_object_or_404(
            DeliveryJob,
            job_id=job_id,
            delivery_partner=self.profile,
            job_type=JobType.PICKUP,
        )
        if job.status == JobStatus.COMPLETED:
            messages.info(request, 'This pickup job is already completed.')
            return redirect('delivery_job_list')

        # Mark IN_PROGRESS on first open
        if job.status == JobStatus.ASSIGNED:
            job.status = JobStatus.IN_PROGRESS
            job.started_at = timezone.now()
            job.save(update_fields=['status', 'started_at'])

        return render(request, 'delivery/scan_pickup.html', self.ctx(
            job=job,
            expected_items=list(
                job.order.items
                .values('tag_number', 'item_type')
                .order_by('tag_number')
            ),
        ))

    def post(self, request, job_id):
        job = get_object_or_404(
            DeliveryJob,
            job_id=job_id,
            delivery_partner=self.profile,
            job_type=JobType.PICKUP,
        )
        if job.status == JobStatus.COMPLETED:
            messages.error(request, 'This job is already completed.')
            return redirect('delivery_job_list')

        raw = request.POST.get('scanned_tags', '[]')
        try:
            tag_numbers = json.loads(raw)
            if not isinstance(tag_numbers, list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            messages.error(request, 'Invalid scan submission — please try again.')
            return redirect('delivery_scan_pickup', job_id=job_id)

        tag_numbers = [str(t).strip().upper() for t in tag_numbers if t]
        if not tag_numbers:
            messages.error(request, 'No items scanned. Scan at least one item before completing pickup.')
            return redirect('delivery_scan_pickup', job_id=job_id)

        # Delegated to rfid.engine — the single scan implementation. It writes
        # RFIDScanEvent + ReconciliationLog and sends the pickup notification,
        # none of which the old local processor did.
        try:
            result = process_s1_pickup(job.order.order_id, tag_numbers, request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('delivery_scan_pickup', job_id=job_id)

        complete_job(job)

        scanned_count = result['received_count']
        unknown = result['unknown_tags']
        if unknown:
            messages.warning(request, f'Pickup complete. {len(unknown)} unknown tag(s) ignored: {", ".join(unknown[:5])}.')
        if result['missing_tags']:
            messages.warning(
                request,
                f'{len(result["missing_tags"])} item(s) were not scanned and remain with the hospital.',
            )
        messages.success(request, f'Pickup complete — {scanned_count} item(s) scanned for Order #{job.order.short_id}.')
        return redirect('delivery_job_list')


# ─────────────────────────────────────────────────────────────
# Scan Delivery (S4)
# ─────────────────────────────────────────────────────────────

class ScanDeliveryView(DeliveryViewMixin):
    def get(self, request, job_id):
        job = get_object_or_404(
            DeliveryJob,
            job_id=job_id,
            delivery_partner=self.profile,
            job_type=JobType.DELIVERY,
        )
        if job.status == JobStatus.COMPLETED:
            messages.info(request, 'This delivery job is already completed.')
            return redirect('delivery_job_list')

        if job.status == JobStatus.ASSIGNED:
            job.status = JobStatus.IN_PROGRESS
            job.started_at = timezone.now()
            job.save(update_fields=['status', 'started_at'])

        from hospital.models import ItemStatus
        return render(request, 'delivery/scan_delivery.html', self.ctx(
            job=job,
            expected_items=list(
                job.order.items
                .filter(current_status=ItemStatus.DISPATCHED)
                .values('tag_number', 'item_type')
                .order_by('tag_number')
            ),
        ))

    def post(self, request, job_id):
        job = get_object_or_404(
            DeliveryJob,
            job_id=job_id,
            delivery_partner=self.profile,
            job_type=JobType.DELIVERY,
        )
        if job.status == JobStatus.COMPLETED:
            messages.error(request, 'This job is already completed.')
            return redirect('delivery_job_list')

        raw = request.POST.get('scanned_tags', '[]')
        try:
            tag_numbers = json.loads(raw)
            if not isinstance(tag_numbers, list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            messages.error(request, 'Invalid scan submission — please try again.')
            return redirect('delivery_scan_delivery', job_id=job_id)

        tag_numbers = [str(t).strip().upper() for t in tag_numbers if t]
        if not tag_numbers:
            messages.error(request, 'No items scanned. Scan at least one item before completing delivery.')
            return redirect('delivery_scan_delivery', job_id=job_id)

        # Delegated to rfid.engine. A short delivery raises DeliveryLossFlag
        # *after* the transaction commits — the scan is real, so the job is
        # still completed and the partial result is reported to the operator.
        try:
            result = process_s4_delivery(job.order.order_id, tag_numbers, request.user)
        except DeliveryLossFlag as flag:
            result = flag.result
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('delivery_scan_delivery', job_id=job_id)

        complete_job(job)

        scanned_count = result['received_count']
        if result['unknown_tags']:
            messages.warning(request, f'Delivery complete. {len(result["unknown_tags"])} unknown tag(s) ignored.')
        if result['missing_tags']:
            messages.warning(
                request,
                f'{len(result["missing_tags"])} item(s) were not delivered and have been flagged: '
                f'{", ".join(result["missing_tags"][:5])}.',
            )
        if result.get('invoice_number'):
            messages.success(request, f'Invoice {result["invoice_number"]} generated for Order #{job.order.short_id}.')
        messages.success(request, f'Delivery complete — {scanned_count} item(s) scanned for Order #{job.order.short_id}.')
        return redirect('delivery_job_list')


# ─────────────────────────────────────────────────────────────
# Job History
# ─────────────────────────────────────────────────────────────

class JobHistoryView(DeliveryViewMixin):
    def get(self, request):
        qs = (
            DeliveryJob.objects
            .filter(delivery_partner=self.profile, status=JobStatus.COMPLETED)
            .select_related('order__hospital', 'order__department')
            .order_by('-completed_at')
        )

        paginator = Paginator(qs, 20)
        page_obj  = paginator.get_page(request.GET.get('page'))

        return render(request, 'delivery/job_history.html', self.ctx(
            page_obj=page_obj,
        ))
