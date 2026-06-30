from django.db.models import Count

from accounts.models import DeliveryProfile, LaundryProfile
from hospital.models import HospitalPartnerSelection


def get_available_laundry_partners(hospital_profile):
    current_id = (
        HospitalPartnerSelection.objects
        .filter(hospital=hospital_profile, is_active=True)
        .values_list('laundry_partner_id', flat=True)
        .first()
    )
    qs = (
        LaundryProfile.objects
        .filter(
            city__iexact=hospital_profile.city,
            area__iexact=hospital_profile.area,
            is_available=True,
        )
        .annotate(total_orders=Count('orders'))
        .select_related('user')
    )
    if current_id:
        qs = qs.exclude(pk=current_id)
    return qs


def get_available_delivery_partners(hospital_profile):
    return (
        DeliveryProfile.objects
        .filter(
            city__iexact=hospital_profile.city,
            area__iexact=hospital_profile.area,
            is_available=True,
        )
        .select_related('user')
    )
