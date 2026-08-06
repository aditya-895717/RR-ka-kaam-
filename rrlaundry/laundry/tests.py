from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounts.models import HospitalProfile, LaundryProfile, Role, User
from core.test_factories import (
    make_hospital_profile, make_laundry_profile, make_order,
    make_items, make_user,
)
from hospital.models import ItemStatus, ItemType, LaundryOrder, OrderItem, OrderStatus
from laundry.models import MissingItemAlert, WorkerItemAssignment


# ─── WorkerItemAssignment immutability ────────────────────────────────────────

class WorkerImmutabilityTests(TestCase):
    def setUp(self):
        self.hospital_user = make_user('hosp@laundry.com', Role.HOSPITAL_HEAD)
        self.hospital      = make_hospital_profile(self.hospital_user)
        self.laundry_user  = make_user('admin@laundry.com', Role.LAUNDRY_ADMIN)
        self.laundry       = make_laundry_profile(self.laundry_user)
        self.order         = make_order(self.hospital, laundry=self.laundry)
        self.item          = make_items(self.order, ['WIA-001'])[0]
        self.worker_user   = make_user('worker@laundry.com', Role.LAUNDRY_WORKER)
        self.assignment    = WorkerItemAssignment.objects.create(
            order_item=self.item,
            worker=self.worker_user,
            is_first_worker=True,
        )

    def test_first_worker_save_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.assignment.save()

    def test_first_worker_delete_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.assignment.delete()

    def test_non_first_worker_save_does_not_raise(self):
        worker2 = make_user('worker2@laundry.com', Role.LAUNDRY_WORKER)
        a2 = WorkerItemAssignment.objects.create(
            order_item=self.item,
            worker=worker2,
            is_first_worker=False,
        )
        a2.save()  # Must not raise

    def test_non_first_worker_can_be_deleted(self):
        worker2 = make_user('worker2@laundry.com', Role.LAUNDRY_WORKER)
        a2 = WorkerItemAssignment.objects.create(
            order_item=self.item,
            worker=worker2,
            is_first_worker=False,
        )
        a2.delete()
        self.assertFalse(WorkerItemAssignment.objects.filter(pk=a2.pk).exists())

    def test_unique_first_worker_constraint_enforced(self):
        worker2 = make_user('worker2b@laundry.com', Role.LAUNDRY_WORKER)
        with self.assertRaises(IntegrityError):
            WorkerItemAssignment.objects.create(
                order_item=self.item,
                worker=worker2,
                is_first_worker=True,
            )


# ─── MissingItemAlert ─────────────────────────────────────────────────────────

class MissingItemAlertTests(TestCase):
    def setUp(self):
        hospital_user = make_user('hosp2@laundry.com', Role.HOSPITAL_HEAD)
        hospital      = make_hospital_profile(hospital_user)
        laundry_user  = make_user('laundry2@laundry.com', Role.LAUNDRY_ADMIN)
        laundry       = make_laundry_profile(laundry_user)
        order         = make_order(hospital, laundry=laundry)
        self.item     = make_items(order, ['ALERT-001'], status=ItemStatus.AT_LAUNDRY)[0]
        stale_time    = timezone.now() - timezone.timedelta(hours=2)
        self.alert    = MissingItemAlert.objects.create(
            order_item=self.item,
            last_stage=ItemStatus.AT_LAUNDRY,
            last_updated_at=stale_time,
        )

    def test_resolve_sets_is_resolved_true(self):
        self.alert.resolve()
        self.assertTrue(self.alert.is_resolved)

    def test_resolve_sets_resolved_at(self):
        self.alert.resolve()
        self.assertIsNotNone(self.alert.resolved_at)

    def test_resolve_persists_to_db(self):
        self.alert.resolve()
        refreshed = MissingItemAlert.objects.get(pk=self.alert.pk)
        self.assertTrue(refreshed.is_resolved)
        self.assertIsNotNone(refreshed.resolved_at)

    def test_minutes_since_last_update_approximately_correct(self):
        self.alert.last_updated_at = timezone.now() - timezone.timedelta(minutes=90)
        self.alert.save()
        minutes = self.alert.minutes_since_last_update()
        # Allow ±2 minutes tolerance for slow test runners
        self.assertGreaterEqual(minutes, 88)
        self.assertLessEqual(minutes, 92)
