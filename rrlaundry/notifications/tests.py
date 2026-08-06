"""
Tests for the consolidated missing-item detector and the sweep endpoint.

check_missing_items is now the system's only missing-item detector — it
absorbed rfid.engine.check_stale_items, whose coverage previously lived in
rfid/tests.py::StaleAlertTests. The escalation cases below are the surviving
form of that coverage.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.test_factories import (
    make_hospital_profile, make_items, make_laundry_profile, make_order, make_user,
)
from accounts.models import Role
from hospital.models import ItemStatus
from laundry.models import FloorStage, ItemStageLog, MissingItemAlert
from notifications.jobs import check_missing_items
from notifications.models import DashboardNotification, NotificationType

TAGS = ['MI-001', 'MI-002', 'MI-003']


class MissingItemBase(TestCase):
    def setUp(self):
        self.hospital = make_hospital_profile()
        self.laundry = make_laundry_profile()
        self.worker = make_user(email='w@factory.com', role=Role.LAUNDRY_WORKER)
        self.order = make_order(self.hospital, laundry=self.laundry)
        self.items = make_items(self.order, TAGS)
        self.order.items.update(current_status=ItemStatus.AT_LAUNDRY)

    def _log_stage(self, item, stage=FloorStage.WASHING, minutes_ago=0):
        log = ItemStageLog.objects.create(
            order_item=item, stage=stage, updated_by=self.worker,
        )
        if minutes_ago:
            # auto_now_add cannot be set directly; backdate after insert.
            ItemStageLog.objects.filter(pk=log.pk).update(
                updated_at=timezone.now() - timezone.timedelta(minutes=minutes_ago)
            )
        return log


class CheckMissingItemsTests(MissingItemBase):
    def test_item_stuck_over_threshold_creates_alert(self):
        for item in self.items:
            self._log_stage(item, minutes_ago=90)
        result = check_missing_items()
        self.assertEqual(result['created'], 3)
        self.assertEqual(result['escalated'], 0)
        self.assertEqual(MissingItemAlert.objects.count(), 3)

    def test_alert_creates_dashboard_notification_for_laundry_admin(self):
        self._log_stage(self.items[0], minutes_ago=90)
        check_missing_items()
        note = DashboardNotification.objects.get()
        self.assertEqual(note.recipient, self.laundry.user)
        self.assertEqual(note.notification_type, NotificationType.MISSING_ITEM)
        self.assertEqual(note.tag_number, TAGS[0])
        self.assertIn(TAGS[0], note.title)

    def test_recent_item_does_not_alert(self):
        for item in self.items:
            self._log_stage(item, minutes_ago=10)
        result = check_missing_items()
        self.assertEqual(result['created'], 0)
        self.assertEqual(MissingItemAlert.objects.count(), 0)

    def test_item_with_no_stage_log_does_not_alert(self):
        result = check_missing_items()
        self.assertEqual(result['created'], 0)

    def test_ready_stage_is_not_in_progress_so_does_not_alert(self):
        for item in self.items:
            self._log_stage(item, stage=FloorStage.READY, minutes_ago=90)
        result = check_missing_items()
        self.assertEqual(result['created'], 0)

    def test_returns_dict_with_created_and_escalated(self):
        result = check_missing_items()
        self.assertIsInstance(result, dict)
        self.assertEqual(set(result), {'created', 'escalated'})


class EscalationTests(MissingItemBase):
    """Absorbed from the deleted rfid.engine.check_stale_items coverage."""

    def setUp(self):
        super().setUp()
        for item in self.items:
            self._log_stage(item, minutes_ago=90)

    def test_second_sweep_escalates_rather_than_duplicating(self):
        first = check_missing_items()
        second = check_missing_items()
        self.assertEqual(first['created'], 3)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['escalated'], 3)
        self.assertEqual(MissingItemAlert.objects.count(), 3)

    def test_escalation_does_not_reset_the_stuck_clock(self):
        """
        last_updated_at records when the item last actually moved. Refreshing
        it on escalation would make a long-stuck item look freshly flagged.
        """
        check_missing_items()
        alert = MissingItemAlert.objects.first()
        before = alert.last_updated_at
        stuck_before = alert.minutes_since_last_update()

        check_missing_items()
        alert.refresh_from_db()
        self.assertEqual(alert.last_updated_at, before)
        self.assertGreaterEqual(alert.minutes_since_last_update(), stuck_before)

    def test_resolved_alert_allows_a_new_alert(self):
        check_missing_items()
        MissingItemAlert.objects.all().update(is_resolved=True)
        result = check_missing_items()
        self.assertEqual(result['created'], 3)
        self.assertEqual(result['escalated'], 0)


@override_settings(SWEEP_TOKEN='test-sweep-token')
class SweepEndpointTests(MissingItemBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('api_notifications_sweep')

    def test_missing_token_is_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_wrong_token_is_403(self):
        self.assertEqual(self.client.get(self.url, {'token': 'nope'}).status_code, 403)

    @override_settings(SWEEP_TOKEN='')
    def test_unconfigured_token_fails_closed_with_503(self):
        self.assertEqual(self.client.get(self.url, {'token': 'anything'}).status_code, 503)

    def test_valid_token_runs_sweep_and_reports_counts(self):
        for item in self.items:
            self._log_stage(item, minutes_ago=90)
        resp = self.client.get(self.url, {'token': 'test-sweep-token'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['alerts_created'], 3)
        self.assertEqual(body['alerts_escalated'], 0)
        self.assertEqual(MissingItemAlert.objects.count(), 3)
        self.assertEqual(DashboardNotification.objects.count(), 3)

    def test_bearer_header_is_accepted(self):
        resp = self.client.get(self.url, HTTP_AUTHORIZATION='Bearer test-sweep-token')
        self.assertEqual(resp.status_code, 200)


class BrevoEmailContentTests(TestCase):
    """
    Asserts on what each Brevo function actually SENDS — recipient, subject and
    body content — not merely that it did not raise.

    send_email is patched at notifications.brevo.send_email, so nothing leaves
    the process and no Brevo credentials or quota are used. Live delivery is a
    separate manual check against Brevo's dashboard.
    """

    def setUp(self):
        from accounts.models import HospitalDepartment
        self.hospital = make_hospital_profile()
        self.hospital.user.full_name = 'Dr Rao'
        self.hospital.user.save()
        self.laundry = make_laundry_profile()
        self.delivery_user = make_user(email='dp@factory.com', role=Role.DELIVERY_PARTNER)
        self.dept = HospitalDepartment.objects.create(
            hospital=self.hospital, department_name='ICU',
        )
        self.order = make_order(self.hospital, laundry=self.laundry)
        self.order.department = self.dept
        self.order.save()
        self.items = make_items(self.order, TAGS, department=self.dept)

    def _capture(self):
        """Patch send_email and return the mock so call args can be asserted."""
        from unittest.mock import patch
        return patch('notifications.brevo.send_email', return_value=True)

    def test_otp_email_addresses_recipient_and_contains_code(self):
        from notifications.brevo import send_otp_email
        with self._capture() as m:
            send_otp_email('user@example.com', 'Dr Rao', '482913')
        to_email, to_name, subject, html = m.call_args[0]
        self.assertEqual(to_email, 'user@example.com')
        self.assertEqual(to_name, 'Dr Rao')
        self.assertIn('OTP', subject)
        self.assertIn('482913', html)
        self.assertIn('10 minutes', html)

    def test_pickup_notification_goes_to_hospital_with_counts(self):
        from notifications.brevo import send_pickup_notification
        with self._capture() as m:
            send_pickup_notification(self.order, TAGS, 'Anil Kumar')
        to_email, to_name, subject, html = m.call_args[0]
        self.assertEqual(to_email, self.hospital.user.email)
        self.assertIn(self.order.short_id, subject)
        self.assertIn('Pickup Confirmed', subject)
        self.assertIn('Anil Kumar', html)
        self.assertIn('ICU', html)
        self.assertIn('>3<', html)  # total item count cell

    def test_delivery_notification_renders_missing_tags_section(self):
        from notifications.brevo import send_delivery_notification
        with self._capture() as m:
            send_delivery_notification(self.order, TAGS[:2], [TAGS[2]], 'Anil Kumar')
        to_email, _, subject, html = m.call_args[0]
        self.assertEqual(to_email, self.hospital.user.email)
        self.assertIn('Delivery Complete', subject)
        self.assertIn('1 Item(s) Not Delivered', html)
        self.assertIn(TAGS[2], html)

    def test_delivery_notification_omits_missing_section_when_clean(self):
        from notifications.brevo import send_delivery_notification
        with self._capture() as m:
            send_delivery_notification(self.order, TAGS, [], 'Anil Kumar')
        _, _, _, html = m.call_args[0]
        self.assertNotIn('Not Delivered', html)

    def test_invoice_email_contains_number_total_and_department(self):
        from billing.engine import generate_invoice
        from notifications.brevo import send_invoice_email
        self.order.items.update(current_status=ItemStatus.DELIVERED)
        invoice = generate_invoice(self.order.order_id)
        with self._capture() as m:
            send_invoice_email(invoice)
        to_email, _, subject, html = m.call_args[0]
        self.assertEqual(to_email, self.hospital.user.email)
        self.assertIn(invoice.invoice_number, subject)
        self.assertIn(str(invoice.total_amount), html)
        self.assertIn('ICU', html)

    def test_job_assigned_email_names_job_type_and_hospital(self):
        from notifications.brevo import send_job_assigned_email
        with self._capture() as m:
            send_job_assigned_email('dp@factory.com', 'Anil Kumar', self.order, 'Pickup')
        to_email, to_name, subject, html = m.call_args[0]
        self.assertEqual(to_email, 'dp@factory.com')
        self.assertIn('Pickup', subject)
        self.assertIn(self.order.short_id, subject)
        self.assertIn(self.hospital.hospital_name, html)

    def test_send_email_returns_false_and_does_not_raise_without_api_key(self):
        """BREVO_API_KEY unset must degrade quietly, never break a scan."""
        from notifications.brevo import send_email
        with override_settings(BREVO_API_KEY=''):
            self.assertIs(send_email('a@b.com', 'A', 'S', '<p>x</p>'), False)
