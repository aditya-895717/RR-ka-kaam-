import json

from django.test import Client, TestCase
from django.urls import reverse


class PingEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_ping_returns_200(self):
        resp = self.client.get(reverse('ping'))
        self.assertEqual(resp.status_code, 200)

    def test_ping_requires_no_authentication(self):
        resp = self.client.get(reverse('ping'))
        self.assertEqual(resp.status_code, 200)

    def test_ping_status_is_ok(self):
        resp = self.client.get(reverse('ping'))
        body = json.loads(resp.content)
        self.assertEqual(body['status'], 'ok')

    def test_ping_ts_field_present(self):
        resp = self.client.get(reverse('ping'))
        body = json.loads(resp.content)
        self.assertIn('ts', body)

    def test_ping_response_has_no_extra_keys(self):
        resp = self.client.get(reverse('ping'))
        body = json.loads(resp.content)
        self.assertEqual(set(body.keys()), {'status', 'ts'})

    def test_ping_has_no_side_effects(self):
        """
        /ping/ is unauthenticated, so it must never write. It previously ran a
        missing-item sweep, which let any anonymous caller trigger inserts.
        """
        from laundry.models import MissingItemAlert
        from notifications.models import DashboardNotification

        before = (MissingItemAlert.objects.count(), DashboardNotification.objects.count())
        resp = self.client.get(reverse('ping'))
        after = (MissingItemAlert.objects.count(), DashboardNotification.objects.count())

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(before, after)

    def test_ping_content_type_is_json(self):
        resp = self.client.get(reverse('ping'))
        self.assertIn('application/json', resp['Content-Type'])
