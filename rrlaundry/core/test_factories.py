"""
Shared factory helpers for creating test fixtures.
Import these in each app's tests.py to avoid repetition.
"""
from decimal import Decimal

from accounts.models import (
    DeliveryProfile, HospitalDepartment, HospitalProfile,
    LaundryProfile, LaundryWorkerProfile, Role, User,
)
from hospital.models import ItemStatus, ItemType, LaundryOrder, OrderItem, OrderStatus


def make_user(email='test@example.com', role=Role.HOSPITAL_HEAD, **kwargs):
    return User.objects.create_user(email=email, password='testpass', role=role, **kwargs)


def make_hospital_profile(user=None, **kwargs):
    if user is None:
        user = make_user(email='hosp@factory.com', role=Role.HOSPITAL_HEAD)
    defaults = dict(
        hospital_name='Test Hospital',
        hospital_address='1 Test St',
        city='Mumbai',
        area='Bandra',
        phone_number='9000000001',
    )
    defaults.update(kwargs)
    return HospitalProfile.objects.create(user=user, **defaults)


def make_laundry_profile(user=None, price_per_item=Decimal('50.00'), **kwargs):
    if user is None:
        user = make_user(email='laundry@factory.com', role=Role.LAUNDRY_ADMIN)
    defaults = dict(
        business_name='Test Laundry',
        address='2 Test Ave',
        city='Mumbai',
        area='Andheri',
        phone_number='9000000002',
        price_per_item=price_per_item,
    )
    defaults.update(kwargs)
    return LaundryProfile.objects.create(user=user, **defaults)


def make_delivery_profile(user=None, **kwargs):
    if user is None:
        user = make_user(email='delivery@factory.com', role=Role.DELIVERY_PARTNER)
    defaults = dict(city='Mumbai', area='Andheri', phone_number='9000000003')
    defaults.update(kwargs)
    return DeliveryProfile.objects.create(user=user, **defaults)


def make_order(hospital, laundry=None, delivery=None, created_by=None, status=OrderStatus.CREATED):
    return LaundryOrder.objects.create(
        hospital=hospital,
        laundry_partner=laundry,
        delivery_partner=delivery,
        created_by=created_by or hospital.user,
        status=status,
    )


def make_items(order, tags, status=ItemStatus.WITH_HOSPITAL, department=None):
    return [
        OrderItem.objects.create(
            order=order,
            tag_number=tag,
            item_type=ItemType.BEDSHEET,
            current_status=status,
            department=department,
        )
        for tag in tags
    ]
