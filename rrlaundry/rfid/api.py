import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from hospital.models import LaundryOrder
from .engine import (
    DeliveryLossFlag, TransitLossFlag,
    process_s1_pickup, process_s2_received,
    process_s3_dispatch, process_s4_delivery,
)
from .models import ReconciliationLog, RFIDScanEvent
from .serializers import (
    OrderReconciliationSerializer, RFIDScanEventSerializer, RFIDScanInputSerializer,
)

logger = logging.getLogger(__name__)


class _ScanBase(APIView):
    permission_classes = [IsAuthenticated]
    role_required: str | None = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.role_required and request.user.role != self.role_required:
            self.permission_denied(
                request,
                message=f'Role {self.role_required} is required for this scan point.',
            )

    def _run_scan(self, request, engine_fn):
        serializer = RFIDScanInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_id = serializer.validated_data['order_id']
        tags = serializer.validated_data['tags']

        try:
            result = engine_fn(order_id, tags, request.user)
            return Response(result, status=status.HTTP_201_CREATED)
        except (TransitLossFlag, DeliveryLossFlag) as exc:
            # Partial success — DB committed, but missing items detected.
            return Response(exc.result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Scan engine error [order=%s]', request.data.get('order_id'))
            return Response(
                {'error': 'Internal scan processing error.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class S1ScanAPI(_ScanBase):
    """POST /api/rfid/scan/s1/ — Pickup at hospital. DELIVERY_PARTNER only."""
    role_required = Role.DELIVERY_PARTNER

    def post(self, request):
        return self._run_scan(request, process_s1_pickup)


class S2ScanAPI(_ScanBase):
    """POST /api/rfid/scan/s2/ — Received at laundry plant. LAUNDRY_ADMIN only."""
    role_required = Role.LAUNDRY_ADMIN

    def post(self, request):
        return self._run_scan(request, process_s2_received)


class S3ScanAPI(_ScanBase):
    """POST /api/rfid/scan/s3/ — Dispatch from laundry plant. LAUNDRY_ADMIN only."""
    role_required = Role.LAUNDRY_ADMIN

    def post(self, request):
        return self._run_scan(request, process_s3_dispatch)


class S4ScanAPI(_ScanBase):
    """POST /api/rfid/scan/s4/ — Delivery at hospital. DELIVERY_PARTNER only."""
    role_required = Role.DELIVERY_PARTNER

    def post(self, request):
        return self._run_scan(request, process_s4_delivery)


class TagHistoryAPI(APIView):
    """GET /api/rfid/tag/<tag_number>/history/ — Full scan chain for a tag."""
    permission_classes = [IsAuthenticated]

    def get(self, request, tag_number):
        tag_number = tag_number.strip().upper()
        events = (
            RFIDScanEvent.objects
            .filter(tag_number=tag_number)
            .select_related('scanned_by', 'order__hospital')
            .order_by('scanned_at')
        )
        return Response(RFIDScanEventSerializer(events, many=True).data)


class OrderReconciliationAPI(APIView):
    """GET /api/rfid/order/<order_id>/reconciliation/ — Reconciliation logs for an order."""
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(LaundryOrder, order_id=order_id)
        logs = (
            ReconciliationLog.objects
            .filter(order=order)
            .order_by('logged_at')
        )
        return Response(OrderReconciliationSerializer(logs, many=True).data)
