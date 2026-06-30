from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DeliveryProfile, LaundryProfile, Role
from hospital.models import HospitalPartnerSelection, LaundryOrder, OrderStatus
from hospital.views import _get_hospital_profile
from .discovery import get_available_delivery_partners, get_available_laundry_partners


class _LaundryPartnerDiscoverySerializer(serializers.ModelSerializer):
    total_orders = serializers.SerializerMethodField()

    class Meta:
        model = LaundryProfile
        fields = ['id', 'business_name', 'area', 'city', 'phone_number', 'price_per_item', 'is_available', 'total_orders']

    def get_total_orders(self, obj):
        return getattr(obj, 'total_orders', 0)


class _DeliveryPartnerDiscoverySerializer(serializers.ModelSerializer):
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryProfile
        fields = ['id', 'partner_name', 'city', 'area', 'phone_number', 'vehicle_type', 'is_available']

    def get_partner_name(self, obj):
        return obj.user.full_name or obj.user.email


class _DiscoveryBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user.role not in (Role.HOSPITAL_HEAD, Role.HOSPITAL_STAFF):
            self.permission_denied(request, message='Hospital role required.')
        self.hospital = _get_hospital_profile(request.user)
        if not self.hospital:
            self.permission_denied(request, message='No hospital profile found.')


class LaundryPartnerDiscoveryAPI(_DiscoveryBase):
    def get(self, request):
        partners = get_available_laundry_partners(self.hospital)
        return Response(_LaundryPartnerDiscoverySerializer(partners, many=True).data)


class DeliveryPartnerDiscoveryAPI(_DiscoveryBase):
    def get(self, request):
        partners = get_available_delivery_partners(self.hospital)
        return Response(_DeliveryPartnerDiscoverySerializer(partners, many=True).data)


class SelectPartnersAPI(_DiscoveryBase):
    def post(self, request):
        if request.user.role != Role.HOSPITAL_HEAD:
            self.permission_denied(request, message='Hospital Head role required.')

        laundry_id = request.data.get('laundry_partner_id')
        delivery_id = request.data.get('delivery_partner_id')

        if not laundry_id or not delivery_id:
            return Response(
                {'error': 'laundry_partner_id and delivery_partner_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_orders = LaundryOrder.objects.filter(
            hospital=self.hospital,
        ).exclude(status__in=[OrderStatus.COMPLETED, OrderStatus.FLAGGED]).exists()

        if active_orders:
            return Response(
                {'error': 'Cannot change partners while active orders are in progress.'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            laundry = LaundryProfile.objects.get(pk=laundry_id, is_available=True)
        except LaundryProfile.DoesNotExist:
            return Response({'error': 'Invalid or unavailable laundry partner.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            delivery = DeliveryProfile.objects.select_related('user').get(pk=delivery_id, is_available=True)
        except DeliveryProfile.DoesNotExist:
            return Response({'error': 'Invalid or unavailable delivery partner.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            HospitalPartnerSelection.objects.filter(hospital=self.hospital).update(is_active=False)
            HospitalPartnerSelection.objects.create(
                hospital=self.hospital,
                laundry_partner=laundry,
                delivery_partner=delivery,
                is_active=True,
            )

        return Response({
            'status': 'selected',
            'laundry_partner': laundry.business_name,
            'delivery_partner': delivery.user.full_name or delivery.user.email,
        }, status=status.HTTP_201_CREATED)
