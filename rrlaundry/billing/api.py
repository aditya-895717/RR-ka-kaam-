from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role

from .models import Invoice, InvoiceStatus
from .serializers import InvoiceSerializer


def _get_invoice_queryset(user):
    """Return invoices scoped to the authenticated user's role."""
    role = user.role
    if role == Role.HOSPITAL_HEAD:
        try:
            return Invoice.objects.filter(hospital=user.hospital_profile)
        except Exception:
            return Invoice.objects.none()
    if role == Role.LAUNDRY_ADMIN:
        try:
            return Invoice.objects.filter(laundry_partner=user.laundry_profile)
        except Exception:
            return Invoice.objects.none()
    return Invoice.objects.none()


class InvoiceListAPIView(APIView):
    def get(self, request):
        qs = _get_invoice_queryset(request.user).select_related(
            'hospital', 'laundry_partner', 'order',
        )
        status_filter = request.query_params.get('status', '')
        if status_filter in (InvoiceStatus.PENDING, InvoiceStatus.PAID, InvoiceStatus.OVERDUE):
            if status_filter == InvoiceStatus.OVERDUE:
                qs = qs.filter(status=InvoiceStatus.PENDING, due_date__lt=timezone.now())
            else:
                qs = qs.filter(status=status_filter)
        serializer = InvoiceSerializer(qs.prefetch_related('line_items__department'), many=True)
        return Response(serializer.data)


class InvoiceDetailAPIView(APIView):
    def get(self, request, invoice_id):
        qs      = _get_invoice_queryset(request.user)
        invoice = get_object_or_404(
            qs.prefetch_related('line_items__department'), invoice_id=invoice_id,
        )
        return Response(InvoiceSerializer(invoice).data)


class MarkPaidAPIView(APIView):
    def post(self, request, invoice_id):
        if request.user.role != Role.LAUNDRY_ADMIN:
            return Response({'detail': 'Only laundry admin can mark invoices as paid.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            laundry_profile = request.user.laundry_profile
        except Exception:
            return Response({'detail': 'Laundry profile not found.'}, status=status.HTTP_403_FORBIDDEN)

        invoice = get_object_or_404(Invoice, invoice_id=invoice_id, laundry_partner=laundry_profile)
        if invoice.status != InvoiceStatus.PENDING:
            return Response(
                {'detail': f'Invoice is already {invoice.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.status  = InvoiceStatus.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['status', 'paid_at'])
        return Response(InvoiceSerializer(invoice).data)
