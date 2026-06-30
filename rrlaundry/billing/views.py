import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.models import HospitalProfile, LaundryProfile, Role

from .models import Invoice, InvoiceStatus

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_hospital_profile(user):
    try:
        return user.hospital_profile
    except Exception:
        pass
    try:
        return user.hospital_staff_profile.hospital
    except Exception:
        return None


def _get_laundry_profile(user):
    try:
        return user.laundry_profile
    except Exception:
        pass
    try:
        return user.laundry_worker_profile.laundry
    except Exception:
        return None


# ─── Mixins ───────────────────────────────────────────────────────────────────

class HospitalHeadMixin(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role != Role.HOSPITAL_HEAD:
            raise PermissionDenied
        self.profile = _get_hospital_profile(request.user)
        if not self.profile:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class LaundryAdminMixin(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role != Role.LAUNDRY_ADMIN:
            raise PermissionDenied
        self.profile = _get_laundry_profile(request.user)
        if not self.profile:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# ─── Hospital views ───────────────────────────────────────────────────────────

class InvoiceListView(HospitalHeadMixin):
    def get(self, request):
        qs = Invoice.objects.filter(hospital=self.profile).select_related(
            'order', 'laundry_partner',
        )
        status_filter = request.GET.get('status', '')
        if status_filter in (InvoiceStatus.PENDING, InvoiceStatus.PAID, InvoiceStatus.OVERDUE):
            if status_filter == InvoiceStatus.OVERDUE:
                qs = qs.filter(
                    status=InvoiceStatus.PENDING,
                    due_date__lt=timezone.now(),
                )
            else:
                qs = qs.filter(status=status_filter)

        paginator  = Paginator(qs, 20)
        page_obj   = paginator.get_page(request.GET.get('page'))
        query_string = request.GET.urlencode().replace(f"page={request.GET.get('page', '')}", '').strip('&')

        return render(request, 'billing/invoice_list.html', {
            'profile':       self.profile,
            'page_obj':      page_obj,
            'status_filter': status_filter,
            'query_string':  query_string,
        })


class InvoiceDetailView(HospitalHeadMixin):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(
            Invoice.objects.prefetch_related('line_items__department'),
            invoice_id=invoice_id,
            hospital=self.profile,
        )
        return render(request, 'billing/invoice_detail.html', {
            'profile': self.profile,
            'invoice': invoice,
        })

    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, invoice_id=invoice_id, hospital=self.profile)
        if invoice.status == InvoiceStatus.PENDING:
            invoice.status  = InvoiceStatus.PAID
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=['status', 'paid_at'])
            messages.success(request, f'Invoice {invoice.invoice_number} marked as paid.')
        return redirect('billing_invoice_detail', invoice_id=invoice_id)


# ─── Laundry views ────────────────────────────────────────────────────────────

class LaundryInvoiceListView(LaundryAdminMixin):
    def get(self, request):
        qs = Invoice.objects.filter(laundry_partner=self.profile).select_related(
            'order', 'hospital',
        )
        status_filter = request.GET.get('status', '')
        if status_filter in (InvoiceStatus.PENDING, InvoiceStatus.PAID, InvoiceStatus.OVERDUE):
            if status_filter == InvoiceStatus.OVERDUE:
                qs = qs.filter(
                    status=InvoiceStatus.PENDING,
                    due_date__lt=timezone.now(),
                )
            else:
                qs = qs.filter(status=status_filter)

        paginator    = Paginator(qs, 20)
        page_obj     = paginator.get_page(request.GET.get('page'))
        query_string = request.GET.urlencode().replace(f"page={request.GET.get('page', '')}", '').strip('&')

        return render(request, 'billing/laundry_invoice_list.html', {
            'profile':       self.profile,
            'page_obj':      page_obj,
            'status_filter': status_filter,
            'query_string':  query_string,
        })


class LaundryInvoiceDetailView(LaundryAdminMixin):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(
            Invoice.objects.prefetch_related('line_items__department'),
            invoice_id=invoice_id,
            laundry_partner=self.profile,
        )
        return render(request, 'billing/laundry_invoice_detail.html', {
            'profile': self.profile,
            'invoice': invoice,
        })


class MarkPaidView(LaundryAdminMixin):
    def post(self, request, invoice_id):
        invoice = get_object_or_404(
            Invoice, invoice_id=invoice_id, laundry_partner=self.profile,
        )
        if invoice.status == InvoiceStatus.PENDING:
            invoice.status  = InvoiceStatus.PAID
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=['status', 'paid_at'])
            messages.success(request, f'Invoice {invoice.invoice_number} marked as paid.')
        return redirect('billing_laundry_invoice_detail', invoice_id=invoice_id)
