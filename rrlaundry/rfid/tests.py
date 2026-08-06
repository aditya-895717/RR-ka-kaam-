import uuid

from django.test import TestCase
from django.utils import timezone

from core.test_factories import (
    make_delivery_profile, make_hospital_profile, make_laundry_profile,
    make_items, make_order, make_user,
)
from hospital.models import ItemStatus, LaundryOrder, OrderStatus
from rfid.engine import (
    DeliveryLossFlag, TransitLossFlag,
    process_s1_pickup, process_s2_received, process_s3_dispatch, process_s4_delivery,
)
from rfid.models import ReconciliationLog, RFIDScanEvent

from accounts.models import Role


TAGS = ['TAG-001', 'TAG-002', 'TAG-003']


class EngineBase(TestCase):
    """Common fixtures for engine tests."""

    def setUp(self):
        self.hospital_user  = make_user('hosp@rfid.com',     Role.HOSPITAL_HEAD)
        self.laundry_user   = make_user('laundry@rfid.com',  Role.LAUNDRY_ADMIN)
        self.delivery_user  = make_user('delivery@rfid.com', Role.DELIVERY_PARTNER)

        self.hospital = make_hospital_profile(self.hospital_user)
        self.laundry  = make_laundry_profile(self.laundry_user)
        self.delivery = make_delivery_profile(self.delivery_user)

        self.order = make_order(
            self.hospital,
            laundry=self.laundry,
            delivery=self.delivery,
        )
        make_items(self.order, TAGS)


# ─── S1 Pickup ───────────────────────────────────────────────────────────────

class S1PickupTests(EngineBase):
    def test_full_match_order_advances_to_pickup_done(self):
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PICKUP_DONE)

    def test_full_match_result_is_matched_true(self):
        result = process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        self.assertTrue(result['is_matched'])
        self.assertEqual(result['received_count'], 3)
        self.assertEqual(result['missing_tags'], [])

    def test_full_match_sets_item_status_pickup_scanned(self):
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        statuses = list(
            self.order.items.values_list('current_status', flat=True)
        )
        self.assertTrue(all(s == ItemStatus.PICKUP_SCANNED for s in statuses))

    def test_partial_scan_records_missing_tags(self):
        result = process_s1_pickup(self.order.order_id, ['TAG-001'], self.delivery_user)
        self.assertFalse(result['is_matched'])
        self.assertEqual(result['received_count'], 1)
        self.assertEqual(len(result['missing_tags']), 2)

    def test_unknown_tags_reported_not_persisted(self):
        result = process_s1_pickup(
            self.order.order_id, ['TAG-001', 'UNKNOWN-XXX'], self.delivery_user
        )
        self.assertIn('UNKNOWN-XXX', result['unknown_tags'])
        self.assertFalse(self.order.items.filter(tag_number='UNKNOWN-XXX').exists())

    def test_reconciliation_log_created(self):
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        self.assertEqual(ReconciliationLog.objects.filter(order=self.order).count(), 1)

    def test_scan_events_created_for_matched_items(self):
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        self.assertEqual(RFIDScanEvent.objects.filter(order=self.order).count(), 3)

    def test_wrong_order_status_raises_value_error(self):
        self.order.status = OrderStatus.AT_LAUNDRY
        self.order.save()
        with self.assertRaises(ValueError):
            process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)

    def test_nonexistent_order_raises_value_error(self):
        with self.assertRaises(ValueError):
            process_s1_pickup(uuid.uuid4(), TAGS, self.delivery_user)


# ─── S2 Received ─────────────────────────────────────────────────────────────

class S2ReceivedTests(EngineBase):
    def setUp(self):
        super().setUp()
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        self.order.refresh_from_db()

    def test_full_match_no_exception(self):
        result = process_s2_received(self.order.order_id, TAGS, self.laundry_user)
        self.assertTrue(result['is_matched'])

    def test_full_match_order_advances_to_at_laundry(self):
        process_s2_received(self.order.order_id, TAGS, self.laundry_user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.AT_LAUNDRY)

    def test_full_match_items_received_at_plant(self):
        process_s2_received(self.order.order_id, TAGS, self.laundry_user)
        statuses = list(self.order.items.values_list('current_status', flat=True))
        self.assertTrue(all(s == ItemStatus.RECEIVED_AT_PLANT for s in statuses))

    def test_partial_raises_transit_loss_flag(self):
        with self.assertRaises(TransitLossFlag):
            process_s2_received(self.order.order_id, ['TAG-001'], self.laundry_user)

    def test_transit_loss_db_committed_before_raise(self):
        try:
            process_s2_received(self.order.order_id, ['TAG-001'], self.laundry_user)
        except TransitLossFlag:
            pass
        self.assertEqual(
            self.order.items.get(tag_number='TAG-001').current_status,
            ItemStatus.RECEIVED_AT_PLANT,
        )
        self.assertEqual(
            self.order.items.get(tag_number='TAG-002').current_status,
            ItemStatus.TRANSIT_LOSS_FLAG,
        )

    def test_transit_loss_flag_carries_correct_counts(self):
        try:
            process_s2_received(self.order.order_id, ['TAG-001'], self.laundry_user)
        except TransitLossFlag as exc:
            self.assertEqual(exc.result['received_count'], 1)
            self.assertEqual(exc.result['expected_count'], 3)
            self.assertEqual(len(exc.result['missing_tags']), 2)
        else:
            self.fail('TransitLossFlag was not raised')

    def test_reconciliation_log_created(self):
        process_s2_received(self.order.order_id, TAGS, self.laundry_user)
        # Two logs total: one from S1, one from S2
        self.assertEqual(ReconciliationLog.objects.filter(order=self.order).count(), 2)


# ─── S3 Dispatch ─────────────────────────────────────────────────────────────

class S3DispatchTests(EngineBase):
    def setUp(self):
        super().setUp()
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        process_s2_received(self.order.order_id, TAGS, self.laundry_user)
        self.order.refresh_from_db()

    def test_dispatch_updates_item_status_to_dispatched(self):
        process_s3_dispatch(self.order.order_id, TAGS, self.laundry_user)
        statuses = list(self.order.items.values_list('current_status', flat=True))
        self.assertTrue(all(s == ItemStatus.DISPATCHED for s in statuses))

    def test_dispatch_advances_order_status(self):
        process_s3_dispatch(self.order.order_id, TAGS, self.laundry_user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.DISPATCHED)


# ─── S4 Delivery ─────────────────────────────────────────────────────────────

class S4DeliveryTests(EngineBase):
    def setUp(self):
        super().setUp()
        process_s1_pickup(self.order.order_id, TAGS, self.delivery_user)
        process_s2_received(self.order.order_id, TAGS, self.laundry_user)
        process_s3_dispatch(self.order.order_id, TAGS, self.laundry_user)
        self.order.refresh_from_db()

    def test_full_delivery_no_exception(self):
        result = process_s4_delivery(self.order.order_id, TAGS, self.delivery_user)
        self.assertTrue(result['is_matched'])

    def test_full_delivery_completes_order(self):
        process_s4_delivery(self.order.order_id, TAGS, self.delivery_user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.COMPLETED)

    def test_full_delivery_sets_items_delivered(self):
        process_s4_delivery(self.order.order_id, TAGS, self.delivery_user)
        statuses = list(self.order.items.values_list('current_status', flat=True))
        self.assertTrue(all(s == ItemStatus.DELIVERED for s in statuses))

    def test_partial_delivery_raises_delivery_loss_flag(self):
        with self.assertRaises(DeliveryLossFlag):
            process_s4_delivery(self.order.order_id, ['TAG-001'], self.delivery_user)

    def test_delivery_loss_db_committed_before_raise(self):
        try:
            process_s4_delivery(self.order.order_id, ['TAG-001'], self.delivery_user)
        except DeliveryLossFlag:
            pass
        self.assertEqual(
            self.order.items.get(tag_number='TAG-001').current_status,
            ItemStatus.DELIVERED,
        )
        self.assertEqual(
            self.order.items.get(tag_number='TAG-002').current_status,
            ItemStatus.DISPATCHED,
        )

    def test_delivery_loss_flag_carries_correct_counts(self):
        try:
            process_s4_delivery(self.order.order_id, ['TAG-001'], self.delivery_user)
        except DeliveryLossFlag as exc:
            self.assertEqual(exc.result['received_count'], 1)
            self.assertEqual(exc.result['expected_count'], 3)
            self.assertEqual(len(exc.result['missing_tags']), 2)
        else:
            self.fail('DeliveryLossFlag was not raised')

    def test_partial_delivery_order_status_is_delivered_not_completed(self):
        try:
            process_s4_delivery(self.order.order_id, ['TAG-001'], self.delivery_user)
        except DeliveryLossFlag:
            pass
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)


