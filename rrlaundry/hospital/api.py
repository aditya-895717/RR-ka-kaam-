import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import (
    DeliveryProfile, HospitalDepartment, LaundryProfile, Role,
)
from billing.utils import create_invoice_for_order
from .models import (
    HospitalPartnerSelection, ItemStatus, LaundryOrder, OrderItem, OrderStatus,
)
from .serializers import (
    CreateOrderSerializer, DeliveryPartnerSerializer,
    LaundryOrderSerializer, LaundryPartnerSerializer,
)
from .views import _get_hospital_profile, _notify_delivery_partner

logger = logging.getLogger(__name__)


class _HospitalAPIBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user.role not in (Role.HOSPITAL_HEAD, Role.HOSPITAL_STAFF):
            self.permission_denied(request, message='Hospital role required.')
        self.hospital = _get_hospital_profile(request.user)
        if not self.hospital:
            self.permission_denied(request, message='No hospital profile found.')


class LaundryPartnerListAPI(_HospitalAPIBase):
    def get(self, request):
        partners = LaundryProfile.objects.filter(
            city__iexact=self.hospital.city,
            is_available=True,
        )
        return Response(LaundryPartnerSerializer(partners, many=True).data)


class DeliveryPartnerListAPI(_HospitalAPIBase):
    def get(self, request):
        partners = DeliveryProfile.objects.filter(
            city__iexact=self.hospital.city,
            is_available=True,
        ).select_related('user')
        return Response(DeliveryPartnerSerializer(partners, many=True).data)


class CreateOrderAPI(_HospitalAPIBase):
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        dept = get_object_or_404(
            HospitalDepartment, pk=data['department_id'], hospital=self.hospital,
        )
        selection = HospitalPartnerSelection.objects.filter(
            hospital=self.hospital, is_active=True,
        ).select_related('laundry_partner', 'delivery_partner').first()

        if not selection:
            return Response(
                {'error': 'No active partner selection. Set partners first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tag_numbers = [item['tag_number'] for item in data['items']]
        existing = list(
            OrderItem.objects.filter(tag_number__in=tag_numbers)
            .values_list('tag_number', flat=True)
        )
        if existing:
            return Response(
                {'error': f'Tag numbers already in system: {existing}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order = LaundryOrder.objects.create(
                hospital=self.hospital,
                laundry_partner=selection.laundry_partner,
                delivery_partner=selection.delivery_partner,
                department=dept,
                status=OrderStatus.CREATED,
                created_by=request.user,
            )
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    tag_number=item['tag_number'],
                    item_type=item['item_type'],
                    current_status=ItemStatus.WITH_HOSPITAL,
                    department=dept,
                )
                for item in data['items']
            ])

        _notify_delivery_partner(order)
        return Response(
            LaundryOrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailAPI(_HospitalAPIBase):
    def get(self, request, order_id):
        order = get_object_or_404(
            LaundryOrder.objects
            .select_related('department', 'laundry_partner', 'delivery_partner')
            .prefetch_related('items'),
            order_id=order_id,
            hospital=self.hospital,
        )
        return Response(LaundryOrderSerializer(order).data)


class ConfirmDeliveryAPI(_HospitalAPIBase):
    def post(self, request, order_id):
        order = get_object_or_404(
            LaundryOrder, order_id=order_id, hospital=self.hospital,
        )
        if order.status != OrderStatus.DELIVERED:
            return Response(
                {'error': 'Order must be DELIVERED before confirming receipt.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order.status = OrderStatus.COMPLETED
            order.save(update_fields=['status', 'updated_at'])
            order.items.update(current_status=ItemStatus.COMPLETED)

        create_invoice_for_order(order)
        return Response({'status': 'completed', 'order_id': str(order.order_id)})
